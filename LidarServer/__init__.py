import socket
import random
from enum import Enum
import json
import zlib
from queue import Queue
from cachetools import TTLCache
import threading

DISCOVERY_PORT = 5556
OPERATING_PORT = 5557
DISCOVER_MESSAGE = b"LIDAR_DISCOVERY"

#RANDOM_ID = random.randint(0, 0xFFFFFFFF).to_bytes(4, byteorder='big')

def hash(data):
  return zlib.crc32(data.encode())

def random_id():
  return random.randint(0, 0xFFFFFFFF)


class Communication:
  c2_ip = None
  sock = None
  inboundQueue = Queue()
  outboundQueue = Queue()
  outboundCache = TTLCache(maxsize=256, ttl=16)
  awaitingResend = TTLCache(maxsize=256, ttl=16)

  messageQueue = Queue()

  def __init__(self):
    print("Starting Communication")
    print("Creating sockets")
    self.create_sockets()
    
    print("Starting Search for Satilites")
    threading.Thread(target=self.discover_satilites).start()
    print("Started Search for Satilites")
    
    print("Starting Satilite Proccecing")
    threading.Thread(target=self.satilite_proccecing).start()
    print("Started Satilite Proccecing")
    
    print("Starting outbound loop")
    threading.Thread(target=self.outbound_loop).start()
    print("Started outbound loop")
    
    #print("Connecting to C2s")
    #self.connect_to_c2s()
    #print("Connected to C2s")
    

    '''
    print("Starting Communication")
    print("Creating sockets")
    self.create_sockets()
    print("Entering C2 discovery loop")
    self.c2_ip = self.discover_c2()
    if self.c2_ip is None:
      print("Failed to discover C2")
      print("Exiting")
      return
    print("Recieved Response")
    print("C2 IP: " + self.c2_ip)

    print("Connecting to C2s")
    self.connect_to_c2s()
    print("Connected to C2s")

    print("Starting inbound loop")
    threading.Thread(target=self.inbound_loop).start()
    print("Started inbound loop")

    print("Starting outbound loop")
    threading.Thread(target=self.outbound_loop).start()
    print("Started outbound loop")

    print("Starting processing loop")
    threading.Thread(target=self.processing_loop).start()
    print("Started processing loop")'''
  
  def create_sockets(self):
    self.operating_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.operating_sock.bind(('', 0))
    self.discovery_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.discovery_sock.bind(('', DISCOVERY_PORT))
    
    
  def connect_to_c2s(self):
    self.operating_sock.connect((self.c2_ip, OPERATING_PORT))
    #self.discovery_sock.connect((self.c2_ip, DISCOVERY_PORT))
    
  def request_resend(self, message_id, address):
    self.send_message({
      "address":address,
      "port":OPERATING_PORT,
      "type": "comms",
      "command": "resend",
      "message_id": message_id
    })
  def send_message(self, payload):
    self.outboundQueue.put(payload)
  
  def outbound_loop(self):
    while True:
      payload = self.outboundQueue.get()
      self.send_single_payload(payload)
      
  def send_single_payload(self, payload):
    self.sock.bind(payload["address"], payload["port"])

    message_id = random_id()
    payload = json.dumps(payload)
    hashedPayload = hash(payload)

    data = {
      "hash": hashedPayload,
      "message_id": message_id,
      "payload": payload
    }
    data = json.dumps(data)

    self.outboundCache[message_id] = payload

    self.sock.send(data.encode())
    
  def discover_satilites(self):
      self.discovery_sock.settimeout(5)
      self.satilites=[]
      while True:
          try:
            data, addr = self.discovery_sock.recvfrom(1024)
            if DISCOVER_MESSAGE in data:
                self.satilites+= [Satilite(addr, data)]
                satilite=self.satilites[-1]
                self.discovery_sock.sendto(satilite.id, (satilite.address, DISCOVERY_PORT))
                self.discovery_sock.bind(('', DISCOVERY_PORT))
  
          except socket.timeout:
            pass
          except Exception as e:
            print(e)
          
          for i, satilite in enumerate(self.satilites):
              for j, satilite2 in enumerate(self.satilites):
                  if not j==i:
                      if satilite==satilite2:
                          self.satilites.remove(satilite2)

  
  def satilite_proccecing(self):
      
      while True:
          
          
          rawData, addr=self.operating_sock.recv(4196)
          for satilite in self.satilites:
              if satilite.address == addr:
                  x=satilite
                  break
          data = x.checkData(rawData)
          
          if data ==None:
              self.request_resend(rawData["message_id"], x.address)
          else:
              self.inboundQueue.put(data)
  
  
class Satilite: 
    def __init__(self, addr, data):
        self.address=addr[0]
        self.id=data[len(DISCOVER_MESSAGE):]

    def checkData(self, data):
        if data["hash"]!=hash(data["payload"]):
            return None
        return data
        
  
  
'''
  def discover_c2(self):
    self.sock.settimeout(5)

    tries = 0

    while tries < 1000:
      self.sock.sendto(DISCOVER_MESSAGE + RANDOM_ID, ('<broadcast>', DISCOVERY_PORT))

      try:
        data, addr = self.sock.recvfrom(1024)
        if data == RANDOM_ID:
          return addr[0]
      except socket.timeout:
        pass
      tries += 1

    return None

  def inbound_loop(self):
    while True:
      data = self.sock.recv(4196)
      self.inboundQueue.put(data)

  def outbound_loop(self):
    while True:
      payload = self.outboundQueue.get()
      self.send_single_payload(payload)

  def send_single_payload(self, payload):
    message_id = random_id()
    payload = json.dumps(payload)
    hashedPayload = hash(payload)

    data = {
      "hash": hashedPayload,
      "message_id": message_id,
      "payload": payload
    }
    data = json.dumps(data)

    self.outboundCache[message_id] = payload

    self.sock.send(data.encode())

  def resend_id(self, message_id):
    if message_id in self.outboundCache:
      self.send_message(self.outboundCache[message_id])
    else:
      print("Message ID not in cache")

  def request_resend(self, message_id):
    self.send_message({
      "type": "comms",
      "command": "resend",
      "message_id": message_id
    })

  def decode_data(self, data):
    data = data.decode()
    data = json.loads(data)

    hash = data["hash"]
    message_id = data["message_id"]
    payload = data["payload"]

    malformed = False

    hashedPayload = hash(payload)

    if hash != hashedPayload:
      malformed = True

    return (message_id, payload, malformed)
  
  def send_message(self, payload):
    self.outboundQueue.put(payload)

  def is_comms_command(self, payload):
    return payload["type"] == "comms"
  
  def handle_comms_command(self, payload):
    if payload["command"] == "resend":
      self.resend_id(payload["message_id"])

  def processing_loop(self):
    while True:
      data = self.inboundQueue.get()
      message_id, payload, malformed = self.decode_data(data)

      if malformed:
        self.request_resend(message_id)        
        continue

      if self.is_comms_command(payload):
        self.handle_comms_command(payload)
        continue

      self.messageQueue.put(payload)

  
  Get a message from the message queue
  Returns: A message from the message queue
  
  def get(self, block=True, timeout: float | None = None):
    return self.messageQueue.get(block, timeout)
  
  
  Get a message from the message queue without blocking
  Returns: A message from the message queue or None if the queue is empty
  
  def get_nowait(self):
    return self.messageQueue.get_nowait()
    '''


Communication()
