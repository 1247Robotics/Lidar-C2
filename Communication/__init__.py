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

RANDOM_ID = random.randint(0, 0xFFFFFFFF).to_bytes(4, byteorder='big')

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
    print("Creating socket")
    self.create_socket()
    print("Entering C2 discovery loop")
    self.c2_ip = self.discover_c2()
    if self.c2_ip is None:
      print("Failed to discover C2")
      print("Exiting")
      return
    print("Recieved Response")
    print("C2 IP: " + self.c2_ip)

    print("Connecting to C2")
    self.connect_to_c2()
    print("Connected to C2")

    print("Starting inbound loop")
    threading.Thread(target=self.inbound_loop).start()
    print("Started inbound loop")

    print("Starting outbound loop")
    threading.Thread(target=self.outbound_loop).start()
    print("Started outbound loop")

    print("Starting processing loop")
    threading.Thread(target=self.processing_loop).start()
    print("Started processing loop")
  
  def create_socket(self):
    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.sock.bind(('', 0))
    self.discovery_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.discovery_sock.bind(('', DISCOVERY_PORT))

  def discover_c2(self):
    self.discovery_sock.settimeout(5)
    self.discovery_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # Enable broadcast


    tries = 0

    while tries < 1000:
      self.discovery_sock.sendto(DISCOVER_MESSAGE + RANDOM_ID, ('<broadcast>', DISCOVERY_PORT))

      try:
        data, addr = self.discovery_sock.recvfrom(1024)
        print(data)
        if data == RANDOM_ID:
          return addr[0]
      except socket.timeout:
        pass
      tries += 1

    return None

  def connect_to_c2(self):
    self.sock.connect((self.c2_ip, OPERATING_PORT))

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

  '''
  Get a message from the message queue
  Returns: A message from the message queue
  '''
  def get(self, block=True, timeout: float | None = None):
    return self.messageQueue.get(block, timeout)
  
  '''
  Get a message from the message queue without blocking
  Returns: A message from the message queue or None if the queue is empty
  '''
  def get_nowait(self):
    return self.messageQueue.get_nowait()
    
Communication()
