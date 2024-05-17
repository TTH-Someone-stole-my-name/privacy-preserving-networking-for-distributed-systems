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
import datetime

SOCKS1=9050
CONTROL1=9051
SOCKS2=9052
CONTROL2=9053

content_q=queue.Queue()
desc_q=queue.Queue()
global hssub_circuits
hssub_circuits=[]

global_public_address=""
global_bootstrapped=False
global_test_successful=False

tor1_proxy={'http':f"socks5h://localhost:{SOCKS1}"}
tor2_proxy={'http':f"socks5h://localhost:{SOCKS2}"}
callback="insjkuap5yirruszchhdistljaspbqjg55cxsdflgadbn4w4yfop3xqa"
callback_descriptor=""
callback_descriptor_backup=""
condition="If_you_see_my_face..."

from http.server import BaseHTTPRequestHandler, HTTPServer
class TestServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes("<html><head><title>Callback to onion service successful</title></head>", "utf-8"))
        self.wfile.write(bytes("<p>Request: %s</p>" % self.path, "utf-8"))
        self.wfile.write(bytes("<body>", "utf-8"))
        self.wfile.write(bytes("<p>Awesome, this test was passed successful</p>", "utf-8"))
        self.wfile.write(bytes("</body></html>", "utf-8"))

def serve_website(server):
    server.serve_forever()


def hs_desc_content_listener(event):
    content_q.put(event)

def hs_desc_listener(event):
    desc_q.put(event)

def make_private_hsdesc(controller, port):
    controller.add_event_listener(hs_desc_content_listener, stem.control.EventType.HS_DESC_CONTENT)
    response=controller.create_ephemeral_hidden_service(port)
    time.sleep(5)
    
    print(f"OK, we detected {content_q.qsize()} events")
    event_0=content_q.get()
    # There are always two descriptors for the two different time zones that could be chosen!
    event=content_q.get()
    
    v3Desc_0=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(event_0.descriptor._raw_contents)

    v3Desc=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(event.descriptor._raw_contents)
     
    #TODO Find out which of those two descriptors is the right one
    #with open('/tmp/desc0','w') as desc0:
    #    desc0.write((event_0.descriptor._raw_contents).decode())
    #with open('/tmp/desc1','w') as desc0:
    #    desc0.write((event.descriptor._raw_contents).decode())
    
    onion_address=event.address
    print(f"Created new ephemeral onion service with id: {onion_address}")
    #print(v3Desc.revision_counter)
    #print(v3Desc_0.revision_counter)

    if v3Desc.revision_counter > v3Desc_0.revision_counter:
        if datetime.datetime.utcnow().hour < 12:
            return (onion_address, str(v3Desc), str(v3Desc_0))
        else:
            return (onion_address, str(v3Desc_0), str(v3Desc))
    else:
        if datetime.datetime.utcnow().hour < 12:
            return (onion_address, str(v3Desc_0), str(v3Desc))
        else:
            return (onion_address, str(v3Desc), str(v3Desc_0))
    
def circ_event_listener(event):
    #print(f"Received circ event for circ {event.id}: Status={event.status}; purpose={event.purpose}; Path={event.path}; HS_State={event.hs_state}")
    if event.purpose=="HS_CLIENT_INTRO" and event.status=="BUILT" and event.id in hssub_circuits:
        print(f"Received confirmation that the introduction circuit is ready with id: {event.id}. Sending hssub for {global_public_address} now...")
        print(f"Sending: POSTHSSUB publisher={address} circuit={event.id} condition={condition} callback={callback}\nHere would be the entire descriptor");
        response=client_controller.msg(f"POSTHSSUB publisher={address} circuit={event.id} condition={condition} callback={callback}\n{callback_descriptor}");
        print(f"HSSUB was sent with response: {response}")
        if not response.is_ok(): 
            print("Should have sent the other descriptor...")
            #sent_desc=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(callback_descriptor)
            #print(type(sent_desc))
            #print(sent_desc.revision_counter)
            
            response=client_controller.msg(f"POSTHSSUB publisher={address} circuit={event.id} condition={condition} callback={callback}\n{callback_descriptor_backup}");
            print(f"HSSUB was sent with response: {response}")
            if not response.is_ok():
                sys.exit(1)
    #else:
    #    print(f"{event.id} is not in {hssub_circuits}")
        

def test_event(event):
    global global_test_successful
    data_entries=event._parsed_content[0][2].decode().split(" ")
    condition_received=data_entries[1]
    callback_received=data_entries[2]
    print(f"HS-SUB Registration received. Call {callback_received} if {condition_received} happens.") 
    hostname=f"http://{callback_received}.onion:8081/"
    print(f"Testing provided callback for {hostname}")
    print("Testing if client can reach callback itself")
    client_controller.msg(f"POSTHSDESCRIPTOR address={callback}\n{callback_descriptor}")
    local_result=requests.get(hostname, proxies=tor2_proxy)
    print(local_result)
    print("Testing if server can reach callback")
    result=requests.get(hostname, proxies=tor1_proxy)
    if(result.status_code == 200):
        global_test_successful=True
    
    #if callback==callback_received and condition == condition_received:
    #    global_test_successful=True


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
    
    address, desc1,desc2 = make_private_hsdesc(server_controller, 8080)
    print(f"Server controller is accepting HSSUB on: {address}.onion")
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
    if not result.is_ok():
        print("POSTHSDESCRIPTOR failed, no reason to continue")
        sys.exit(1)
    callback, callback_descriptor,callback_descriptor_backup = make_private_hsdesc(client_controller, 8081)
    print(f"Client controller is waiting for callback on {callback}")
    web_server=HTTPServer(('127.0.0.1', 8081), TestServer)
    web_thread=threading.Thread(target=serve_website, args=(web_server,), daemon=True)
    web_thread.start()
    print("Waiting for 30s to make sure both tor instances are bootstrapped before sending POSTHSSUB")
    sleep(30)

    print(f"Launch circuit for address: {address}")
    circuit_id=client_controller.msg(f"LAUNCH_BY_EXTEND onionaddress={address}");
    hssub_circuits.append(circuit_id.content()[0][2])
    
    print("Waiting for HSSUB to be received")
    timeout=0
    while not global_test_successful and  timeout < 60:
        sleep(1)
        timeout+=1
    
    if global_test_successful:
        print("HS_SUB with callback was successful")
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
