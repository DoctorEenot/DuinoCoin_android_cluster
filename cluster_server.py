import socket
import time
import configparser
import json
import requests
import threading
import struct
import select
import traceback
import logging

minerVersion = "2.4"  # Version number
resourcesFolder = "PCMiner_" + str(minerVersion) + "_resources"
username = ''
efficiency= ''
donationlevel= ''
debug= ''
threadcount= ''
requestedDiff= ''
rigIdentifier= ''
lang= ''
algorithm= ''
config = configparser.ConfigParser()
serveripfile = ("https://raw.githubusercontent.com/"
    + "revoxhere/"
    + "duino-coin/gh-pages/"
    + "serverip.txt")  # Serverip file
masterServer_address = ''
masterServer_port = 0

MIN_PARTS = 5
INC_COEF = 3



logger = logging.getLogger('Cluster_Server')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('Cluster_Server.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)




# Config loading section
def loadConfig():
    global username
    global efficiency
    global donationlevel
    global debug
    global threadcount
    global requestedDiff
    global rigIdentifier
    global lang
    global algorithm

    logger.info('Loading config')
    config.read(resourcesFolder + "/Miner_config.cfg")
    username = config["miner"]["username"]
    efficiency = config["miner"]["efficiency"]
    threadcount = config["miner"]["threads"]
    requestedDiff = config["miner"]["requestedDiff"]
    donationlevel = config["miner"]["donate"]
    algorithm = config["miner"]["algorithm"]
    rigIdentifier = config["miner"]["identifier"]
    debug = config["miner"]["debug"]
    # Calulate efficiency for use with sleep function
    efficiency = (100 - float(efficiency)) * 0.01


time_for_device = 90

class Device:
    def __init__(self,name,address):
        self.name = name
        self.last_job = None
        self.last_updated = time.time()
        self.busy = False

    def is_alive(self):
        return (time.time()-self.last_updated)<time_for_device
    def update_time(self):
        self.last_updated = time.time()
    def isbusy(self):
        return self.busy
    def job_stopped(self):
        self.last_job = None
        self.busy = False
    def job_started(self,job):
        self.busy = True
        self.last_job = job

    def __str__(self):
        return self.name+' '+str(self.address)
    def __repr__(self):
        return str(self)



devices = {}


server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, 1 )
server_socket.setblocking(False)
SERVER_ADDRESS = ('0.0.0.0',9090)
server_socket.bind(SERVER_ADDRESS)

master_server_socket = socket.socket()

def connect_to_master():
    logger.info('CONNECTING TO MASTER')
    global master_server_socket
    try:
        master_server_socket.close()
    except:
        pass
    while True:
        master_server_socket = socket.socket()
        # Establish socket connection to the server
        try:
            master_server_socket.connect((str(masterServer_address),
                                        int(masterServer_port)))
            serverVersion = master_server_socket.recv(3).decode().rstrip("\n")  # Get server version
        except Exception as e:
            continue
        break



def register(dispatcher,event):
    '''
    event = {'t':'e',
              'event':'register',
              'name':'Test',
              'address':('127.0.0.1',1234),
              'callback':socket}
    '''
    global devices
    
    logger.info('Register')
    device = devices.get(event.address,None)
    if device != None:
        event.callback.sendto(b'{"t":"a",\
                                "status":"ok",\
                                "message":"already exists"}',
                                event.address)
        return None

    devices[event.address] = Device(event.name,event.address)
    event.callback.sendto(b'{"t":"a",\
                             "status":"ok",\
                             "message":"device added"}',
                             event.address)
    
    event.dict_representation['event'] = 'job_done'
    event.dict_representation['result'] = None
    dispatcher.add_to_queue(event)

    return None

def ping(dispatcher,event):
    '''
    event = {'t':'e',
             'event':'ping',
             'address':('127.0.0.1',1234),
              'callback':socket}
    '''
    global devices

    logger.info('Ping')
    device = devices.get(event.address,None)
    if device == None:
        event.callback.sendto(b'{"t":"e",\
                             "event":"register",\
                             "message":"You must register in cluster"}',
                              event.address)
        return None
    
    device.update_time()
    data = b'{"t":"a","status":"ok","message":"server is running"}'
    event.callback.sendto(data,event.address)
    return None

JOB = None
JOB_START = None
JOB_END = None
JOB_PART = None
JOB_MAX = None
JOB_START_SECRET = 'ejnejkfnhiuhwefiy87usdf'


def job_start(dispatcher,event):
    '''
    event = {'t':'e',
             'event':'job_start',
             'secret':'',
             'callback':socket}
    '''
    global JOB
    global JOB_START
    global JOB_END
    global JOB_PART
    global JOB_START_SECRET
    global algorithm
    global JOB_MAX
    
    logger.info('Job is starting')
    if event.secret != JOB_START_SECRET:
        logger.warning('bad secret')
        return

    for addr,device in devices.items():
        if device.isbusy():
            continue
        data = json.dumps({'t':'e',
                        'event':'start_job',
                        'lastBlockHash':JOB[0],
                        'expectedHash':JOB[1],
                        'start':JOB_START,
                        'end':JOB_END,
                        'algorithm':algorithm})
        device.job_started([JOB[0],JOB[1],JOB_START,JOB_END])
        JOB_START = JOB_END
        JOB_END += JOB_PART
        event.callback.sendto(data.encode('ascii'),addr)

def send_results(result):
    global algorithm
    global minerVersion
    global rigIdentifier

    logger.info('Sending results')
    logger.debug(str(result))
    while True:
        try:
            master_server_socket.send(bytes(
                                    str(result[0])
                                    + ","
                                    + str(result[1])
                                    + ","
                                    + "Official PC Miner ("
                                    + str(algorithm)
                                    + ") v" 
                                    + str(minerVersion)
                                    + ","
                                    + str(rigIdentifier),
                                    encoding="utf8"))
            feedback = master_server_socket.recv(8).decode().rstrip("\n")
            break
        except:
            connect_to_master()

    if feedback == 'GOOD':
        logger.info('Hash accepted')
    elif feedback == 'BLOCK':
        logger.info('Hash blocked')
    else:
        logger.info('Hash rejected')

def job_done(dispatcher,event):
    '''
    event = {'t':'e',
            'event':'job_done',
            'result':[1,1] | 'None',
            'address':('127.0.0.1',1234),
            'callback':socket}
    '''
    global JOB
    global JOB_START
    global JOB_END
    global JOB_PART
    global algorithm
    global JOB_MAX

    logger.info('job done packet')
    if (event.result == 'None' \
        or event.result == None):
        logger.info('Empty block')
        device = devices.get(event.address,None)
        if device == None:
            logger.warning('device is not registered')
            event.callback.sendto(b'{"t":"e",\
                             "event":"register",\
                             "message":"You must register in cluster"}',
                              event.address)
            return None
        if not device.is_alive():
            logger.warning('Device '+device.name+' '+str(event.address)+' is dead')
            data = json.dumps({'t':'e',
                                'event':'ping'})
            event.callback.sendto(data.encode('ascii'),event.address)
            return None

        if JOB == None:
            logger.info('Job is already over')
            data = b'{"t":"a",\
                    "status":"ok",\
                    "message":"No job to send"}'
            event.callback.sendto(data,event.address)
            return

        job = JOB
        job_start = JOB_START
        job_end = JOB_END


        increase = True

        if JOB_START == JOB_MAX:
            increase = False
            for addr,device in devices.items():
                if device.isbusy() and addr != event.address:
                    increase = True
                    job = device.last_job[:2]
                    job_start,job_end = device.last_job[2:]
                    break
            if not increase:
                logger.debug('Giving up on that block')
                data = b'{"t":"e","event":"stop_job","message":"terminating job"}'
                logger.debug('stopping workers')
                for addr,device in devices.items():
                    device.job_stopped()
                    event.callback.sendto(data,addr)
                JOB = None
                JOB_START = None
                JOB_END = None
                JOB_PART = None
                JOB_MAX = None
                return
                
        else:
            for addr,device in devices.items():
                if device.busy and not device.is_alive():
                    increase = False
                    job = device.last_job[:2]
                    job_start,job_end = device.last_job[2:]
                    device.job_stopped()
                    break

        data = json.dumps({'t':'e',
                        'event':'start_job',
                        'lastBlockHash':job[0],
                        'expectedHash':job[1],
                        'start':job_start,
                        'end':job_end,
                        'algorithm':algorithm})
        device.job_started([job[0],job[1],job_start,job_end])
        if increase:
            JOB_START = JOB_END
            if JOB_MAX - JOB_END<JOB_PART:
                JOB_END = JOB_MAX+1
            else:
                JOB_END += JOB_PART+1
        event.callback.sendto(data.encode('ascii'),event.address)
    
    else:
        logger.info('accepted result')
        #if event.result == None or event.result == 'None':
        #    logger.debug('Giving up on that block')
        #else:
        send_results(event.result)
        data = b'{"t":"e","event":"stop_job","message":"terminating job"}'
        logger.debug('stopping workers')
        for addr,device in devices.items():
            device.job_stopped()
            event.callback.sendto(data,addr)
        JOB = None
        JOB_START = None
        JOB_END = None
        JOB_PART = None
        JOB_MAX = None


def request_job(dispatcher,event):
    '''
    event = {'t':'e',
             'event':'requets_job',
             'secret':'',
             'parts':10}
    '''
    global JOB
    global JOB_START
    global JOB_END
    global JOB_PART
    global JOB_START_SECRET
    global JOB_MAX
    global algorithm
    global username
    global requestedDiff
    global master_server_socket

    logger.info('requesting job')
    if event.secret != JOB_START_SECRET:
        logger.warning('bad secret')
        return
    while True:
        try:
            if algorithm == "XXHASH":
                master_server_socket.send(bytes(
                    "JOBXX,"
                    + str(username)
                    + ","
                    + str(requestedDiff),
                    encoding="utf8"))
            else:
                master_server_socket.send(bytes(
                    "JOB,"
                    + str(username)
                    + ","
                    + str(requestedDiff),
                    encoding="utf8"))
        except Exception as e:
            logger.error('asking for job error accured')
            connect_to_master()
            continue
        try:
            job = master_server_socket.recv(128).decode().rstrip("\n")
        except:
            connect_to_master()
            continue
        job = job.split(",")
        if job[0] == 'BAD':
            logger.warning('GOT "BAD" PACKET IN RESPONSE')
            return
        elif job[0] == '':
            logger.warning('CONNECTION WITH MASTER SERVER WAS BROKEN')
            connect_to_master()
            continue
        logger.info('job accepted')
        logger.info('Difficulty: '+str(job[2]))
        logger.debug(str(job))
        JOB = job[:2]
        real_difficulty = (100*int(job[2]))
        JOB_MAX = real_difficulty
        JOB_START = 0
        JOB_PART = ((real_difficulty-JOB_START)//MIN_PARTS)
        JOB_END = JOB_PART
        break


class Event(object):
    def __init__(self,input:dict):
        self.dict_representation = input
    def __dict__(self):
        return super(Event, self).__getattribute__('dict_representation')
    #def event_name(self) -> str:
    #    return self.dict_representation['event']
    def __getattribute__(self, item):
        # Calling the super class to avoid recursion
        return super(Event, self).__getattribute__(item)
    def __getattr__(self, item):
        
        try:
            return super(Event, self).__getattribute__('dict_representation')[item]
        except:
            logger.warning('NO SUCH ELEMENT AS '+str(item))
            pass
    def __str__(self):
        return str(self.dict_representation)

class Dispatcher:
    def __init__(self):
        self.actions = {}
        self.queue = []

    def register(self,event_name,action):
        self.actions[event_name] = action
    
    def add_to_queue(self,event:Event):
        logger.debug('added event')
        self.queue.append(event)

    def clear_queue(self):
        self.queue = []

    def dispatch_event(self):
        try:
            event = self.queue.pop(0)
        except:
            return None
        logger.debug('dispatching event')
        func = self.actions.get(event.event,None)
        if func == None:
            logger.warning('NO SUCH ACTION '+event.event)
            return None
        return self.actions[event.event](self,event)


def server():
    global server_socket
    global devices
    global MIN_PARTS
    global INC_COEF

    logger.debug('Initializing dispatcher')
    event_dispatcher = Dispatcher()
    event_dispatcher.register('register',register)
    event_dispatcher.register('ping',ping)
    event_dispatcher.register('job_start',job_start)
    event_dispatcher.register('job_done',job_done)
    event_dispatcher.register('request_job',request_job)
    logger.debug('Dispatcher initialized')

    while True:
        # recieving events
        data = None
        try:
            data, address = server_socket.recvfrom(1024)
        except:
            pass

        # parsing events and registering events
        if data != None:
            data_is_ok = False
            try:
                message = json.loads(data.decode('ascii'))
                data_is_ok = True
            except:
                logger.warning("can't parse packet")
                logger.debug(str(data))
            if data_is_ok:
                logger.debug('accepted packet')
                logger.debug(str(message))
                if message['t'] == 'e':
                    message['address'] = address
                    message['callback'] = server_socket
                    event = Event(message)
                    event_dispatcher.add_to_queue(event)
                else:
                    device = devices.get(address,None)
                    if device == None:
                        server_socket.sendto(b'{"t":"e",\
                                                "event":"register",\
                                                "message":"You must register in cluster"}',
                                                address)
                    else:
                        device.update_time()
        
        # dispatching events
        try:
            event_dispatcher.dispatch_event()
        except Exception as e:
            logger.error('CANT DISPATCH EVENT')
            logger.debug('Traceback',exc_info=e)


        # request job and start it
        if len(devices)>0:
            if JOB == None:
                MIN_PARTS = len(devices)+INC_COEF
                logger.debug('MIN_PARTS is setted to '+str(MIN_PARTS))
                event_dispatcher.clear_queue()
                event = Event({'t':'e',
                               'event':'request_job',
                               'secret':JOB_START_SECRET,
                               'parts':20})
                event_dispatcher.add_to_queue(event)
                event = Event({'t':'e',
                               'event':'job_start',
                               'secret':JOB_START_SECRET,
                               'callback':server_socket})
                event_dispatcher.add_to_queue(event)


        # cleenup devices
        for address,device in devices.items():
            if not device.is_alive()\
                and not device.busy:
                del devices[address]
                break
        
        time.sleep(0.5)



if __name__ == '__main__':
    logger.info('STARTING SERVER')
    loadConfig()
    logger.info('Getting Master server info')
    while True:
        try:
            res = requests.get(serveripfile, data=None)
            break
        except:
            pass
        logger.info('getting data again')
        time.sleep(10)

    if res.status_code == 200:
        logger.info('Master server info accepted')
        # Read content and split into lines
        content = (res.content.decode().splitlines())
        masterServer_address = content[0]  # Line 1 = pool address
        masterServer_port = content[1]  # Line 2 = pool port
    else:
        raise Exception('CANT GET MASTER SERVER ADDRESS')

    try:
        server()
    except Exception as e:
        #tr = traceback.format_exc()
        logger.error('ERROR ACCURED',exc_info=e)

    input()

    
