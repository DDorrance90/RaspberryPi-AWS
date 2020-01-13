#############################################################################################
#  .----------------.  .----------------. 
# | .--------------. || .--------------. |      Derek Dorrance
# | |  ________    | || |  ________    | |      Salish Kootenai College
# | | |_   ___ `.  | || | |_   ___ `.  | |      derekdorrance@student.skc.edu
# | |   | |   `. \ | || |   | |   `. \ | |
# | |   | |    | | | || |   | |    | | | |
# | |  _| |___.' / | || |  _| |___.' / | |
# | | |________.'  | || | |________.'  | |
# | |              | || |              | |
# | '--------------' || '--------------' |
#  '----------------'  '----------------' 
###############################################################################################

import datetime
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
import time
import sys
import dateutil.parser
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import serial
import logging

log = logging.getLogger('apscheduler.executors.default')
log.setLevel(logging.INFO)  # DEBUG

fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
h = logging.StreamHandler()
h.setFormatter(fmt)
log.addHandler(h)

cwd = os.path.abspath(os.path.dirname(__file__))
host = "a2lhntaumznuq2-ats.iot.us-west-2.amazonaws.com"
rootCAPath = os.path.join(cwd, "root-CA.crt")
certificatePath = os.path.join(cwd, "DerekPC.cert.pem")
privateKeyPath = os.path.join(cwd, "DerekPC.private.key")
deviceShadowHandler = None
thingName = "DerekPC"
serialArduino = None 
FILL_LEVEL = 7.0
scheduler = BackgroundScheduler()

def Run () :
    global serialArduino
    serialArduino.write("[CMD]".encode())

class callbackContainer:
    def __init__(self, deviceShadowInstance):
        self.deviceShadowInstance = deviceShadowInstance

    def customShadowCallback_Update(self, payload, responseStatus, token):
       foo = 'bar'

    def customShadowCallback_Delta(self, payload, responseStatus, token):
        global scheduler
        payloadJSON = json.loads(payload)
        if payloadJSON["state"].get("deviceRunning") : 
            if str(payloadJSON["state"]["deviceRunning"]) == "On": # Received update to run. Check fill.

                print("Checking fill level and running motor")

                Run() 
                lastFeedTime = datetime.datetime.now().isoformat()
                updatePayload = {"state": {"desired": {"deviceRunning": "Off"}, "reported": {
                    "lastFeedTime": str(lastFeedTime)}}}
                self.deviceShadowInstance.shadowUpdate(json.dumps(
                    updatePayload), self.customShadowCallback_Update, 5)


        if  payloadJSON["state"].get("events")  : # Events were updated
            Events = payloadJSON["state"].get("events")
            scheduler.remove_all_jobs() 

            for e in Events :
                eventTime = str(e.get("start")) 
                eventTime = dateutil.parser.isoparse(eventTime)
                print(eventTime)
                scheduler.add_job(Run, 'date', run_date=eventTime, misfire_grace_time=10)

            scheduler.print_jobs() 
            updatePayload = {"state": {"reported" : {"events" : Events }}}  
            self.deviceShadowInstance.shadowUpdate(json.dumps(updatePayload), self.customShadowCallback_Update , 5)

    def loadEvents (self, payload, responseStatus, token) :
        global scheduler
        payload = json.loads(payload) 
        Events = payload["state"]["desired"].get("events") 
        for e in Events :
            eventTime = str(e.get("start")) 
            eventTime = dateutil.parser.isoparse(eventTime)
            scheduler.add_job(Run, 'date', run_date=eventTime, misfire_grace_time=10)
        scheduler.print_jobs() 
            



def ConnectAWS():
    myAWSIoTMQTTShadowClient = None
    myAWSIoTMQTTShadowClient = AWSIoTMQTTShadowClient("RaspberryPi")
    myAWSIoTMQTTShadowClient.configureEndpoint(host, 443)
    myAWSIoTMQTTShadowClient.configureCredentials(
        rootCAPath, privateKeyPath, certificatePath)
    myAWSIoTMQTTShadowClient.configureAutoReconnectBackoffTime(1, 32, 20)
    myAWSIoTMQTTShadowClient.configureConnectDisconnectTimeout(10)  # 10 sec
    myAWSIoTMQTTShadowClient.configureMQTTOperationTimeout(5)  # 5 sec
    myAWSIoTMQTTShadowClient.connect()
    deviceShadowHandler = myAWSIoTMQTTShadowClient.createShadowHandlerWithName(
        thingName, True)
   

    return deviceShadowHandler

def ArduinoLoop (s) :
    global FILL_LEVEL
    if(s.in_waiting > 0) :
        try:
            data = s.readline() # [stat] USData 3600
            value = float(data)
            FILL_LEVEL = value / 10
        except:
            print("Bad Data from Sensor")

def DieWithGrace () :
    global scheduler
    scheduler.shutdown()

def main():
    global FILL_LEVEL, serialArduino, scheduler
    TICK_TIME = 0
    ##   Do the Arduino thing
    if len(sys.argv) != 2  :
        USB_DEV = "/dev/ttyUSB0"
    else :
        USB_DEV = sys.argv[1] 
    scheduler.start()
    serialArduino = serial.Serial(USB_DEV, 9600)

    deviceShadowHandler = ConnectAWS()
    cbContainer = callbackContainer(deviceShadowHandler)
    deviceShadowHandler.shadowRegisterDeltaCallback(
        cbContainer.customShadowCallback_Delta)
    deviceShadowHandler.shadowGet(cbContainer.loadEvents, 5)

    try:
        while True:
            ArduinoLoop(serialArduino)
            if(TICK_TIME > 450000) : # About every 20 seconds depending on CPU
                strTime = str(datetime.datetime.now().isoformat())
                updatePayload = {"state" : { "reported": {"isEmpty": FILL_LEVEL, "lastUpdate": strTime }}}
                deviceShadowHandler.shadowUpdate(
                    json.dumps(updatePayload), cbContainer.customShadowCallback_Update, 5)
                TICK_TIME = 0
            TICK_TIME += 1
    except(KeyboardInterrupt, SystemExit) :
        DieWithGrace();  


if __name__ == "__main__":
    main()
