#/usr/bin/python3

import requests
import os
import stem
import stem.control
import stem.process
import queue
import time
from pathlib import Path
import threading
from time import sleep
import shutil
import sys

SOCKS1=9050
CONTROL1=9051
SOCKS2=9052
CONTROL2=9053

content_q=queue.Queue()
desc_q=queue.Queue()

global_public_address=""
global_bootstrapped=False
global_test_successful=False

callback="insjkuap5yirruszchhdistljaspbqjg55cxsdflgadbn4w4yfop3xqa"
condition="If_you_see_my_face..."

def hs_desc_content_listener(event):
    content_q.put(event)

def hs_desc_listener(event):
    desc_q.put(event)

def make_private_hsdesc(controller):
    controller.add_event_listener(hs_desc_content_listener, stem.control.EventType.HS_DESC_CONTENT)
    response=controller.create_ephemeral_hidden_service(8080)
    time.sleep(5)
    
    print(f"OK, we detected {content_q.qsize()} events")
    event_0=content_q.get()
    # There are always two descriptors for the two different time zones that could be chosen!
    event=content_q.get()
    
    v3Desc_0=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(event_0.descriptor._raw_contents)
    v3Desc=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(event.descriptor._raw_contents)
     
    onion_address=event.address
    print(f"Created new ephemeral onion service with id: {onion_address}")
    return (onion_address, str(v3Desc), str(v3Desc_0))
    
def circ_event_listener(event):
    #print(f"Received circ event for circ {event.id}: Status={event.status}; purpose={event.purpose}; Path={event.path}; HS_State={event.hs_state}")
    if event.purpose=="HS_CLIENT_INTRO" and event.status=="BUILT":
        print(f"Received confirmation that the introduction circuit is ready with id: {event.id}. Sending hssub for {global_public_address} now...")
        response=client_controller.msg(f"POSTHSSUB publisher={address} circuit={event.id} condition={condition} callback={callback}");
        print(f"HSSUB was sent with response: {response}")

def test_event(event):
    global global_test_successful
    data_entries=event._parsed_content[0][2].decode().split(" ")
    condition_received=data_entries[1]
    callback_received=data_entries[2]
    print(f"HS-SUB Registration received. Call {callback_received} if {condition_received} happens.") 
    if callback==callback_received and condition == condition_received:
        global_test_successful=True

# Need Log listener to find out when Tor is finally bootstrapped
def log_listener(event):
    if "Bootstrapped" in event.message:
        print(event.message)
    if "Bootstrapped 100\%" in event.message:
        print("Bootstrapping is complete")
        global_bootstrapped=True        


server_tor_process=None
client_tor_process=None
#Ensure that the Tor process data directory is cleared to have new bootstrapping
Path(f"/tmp/tor_test_{SOCKS1}").mkdir(exist_ok=True)
shutil.rmtree(f"/tmp/tor_test_{SOCKS1}")
Path(f"/tmp/tor_test_{SOCKS1}").mkdir(exist_ok=True)
try:
    server_tor_process=stem.process.launch_tor_with_config(
            config = {
                'SocksPort': str(SOCKS1),
                'ControlPort': str(CONTROL1),
                'PublishHidServDescriptors': str(0),
                'DataDirectory' : f"/tmp/tor_test_{SOCKS1}",
                'HashedControlPassword' : '16:D875FDB5B8B11D4260C87886B8DDE1D3425912F99030EEF3A4EB4AD717',
                'Log': 'debug file /tmp/test_server_debug.log',
                'SafeLogging': '0',
                },
            tor_cmd='../src/app/tor'
            )
    server_controller=stem.control.Controller.from_port(address='127.0.0.1', port=CONTROL1)
    server_controller.authenticate('tor')
    server_controller.add_event_listener(log_listener, stem.control.EventType.NOTICE)
    server_controller.add_event_listener(test_event, 'HS_SUB')
    #server_controller._event_listeners['MALFORMED_EVENTS']=[malformed_event]
    #print("Waiting for tor instance to bootstrap")
    #while global_bootstrapped==False:
    #    sleep(1)
    #print("Tor server instance ready, continuing")
    address, desc1,desc2 = make_private_hsdesc(server_controller)
    print(f"Onion Service is waiting to receive HSSUB with address: {address}")
    global_public_address=address 

	# OK, now we have an waiting subscriber, now try to send a HSSUB message to it: 
    Path(f"/tmp/tor_test_{SOCKS2}").mkdir(exist_ok=True)
    shutil.rmtree(f"/tmp/tor_test_{SOCKS2}")
    Path(f"/tmp/tor_test_{SOCKS2}").mkdir(exist_ok=True)
    client_tor_process=stem.process.launch_tor_with_config(
            config = {
                'SocksPort': str(SOCKS2),
                'ControlPort': str(CONTROL2),
                'PublishHidServDescriptors': str(0),
                'DataDirectory' : f"/tmp/tor_test_{SOCKS2}",
                'HashedControlPassword' : '16:D875FDB5B8B11D4260C87886B8DDE1D3425912F99030EEF3A4EB4AD717',
                'Log': 'debug file /tmp/test_client_debug.log',
                'SafeLogging': '0',
                },
            tor_cmd='../src/app/tor'
            )

    client_controller=stem.control.Controller.from_port(address='127.0.0.1', port=CONTROL2)
    client_controller.authenticate('tor')
    client_controller.add_event_listener(circ_event_listener, stem.control.EventType.CIRC)
    result=client_controller.msg(f"POSTHSDESCRIPTOR address={address}\n{desc1}")
    result=client_controller.msg(f"POSTHSDESCRIPTOR address={address}\n{desc2}")
    print("Waiting for 30s to make sure both tor instances are bootstrapped before sending POSTHSSUB")
    sleep(30)

    print(f"Launch circuit for address: {address}")
    #response=client_controller.msg(f"POSTHSSUB publisher={address} condition={condition} callback={callback}");	
    response=client_controller.msg(f"LAUNCH_BY_EXTEND onionaddress={address}");	
    print(response)
    print("Waiting for HSSUB to be received")
    timeout=0
    while not global_test_successful and  timeout < 60:
        sleep(1)
        timeout+=1
    
    if global_test_successful:
        print("HS_SUB was successful")
        sys.exit(0)
    else:
        print("Test timed out, HS_SUB was not successful")
        sys.exit(1)

    server_tor_process.kill()
    client_tor_process.kill()
except Exception as ex:
    raise ex
finally: 
    if server_tor_process: 
        server_tor_process.kill()
    if client_tor_process: 
        client_tor_process.kill()
