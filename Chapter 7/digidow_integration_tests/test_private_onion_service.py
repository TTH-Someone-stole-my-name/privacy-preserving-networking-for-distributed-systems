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

SOCKS1=9050
CONTROL1=9051
SOCKS2=9052
CONTROL2=9053
HTTP=80
tor_client={'http':f"socks5h://localhost:{SOCKS2}", 'https':f"socks5h://localhost:{SOCKS2}"}

content_q=queue.Queue()
desc_q=queue.Queue()

def hs_desc_content_listener(event):
    #content_q.put(event.descriptor)
    content_q.put(event)
    #print(f"Received Event: {event.descriptor}")

def hs_desc_listener(event):
    desc_q.put(event)
    #print(event)

def get_hsdesc(controller, addr):
    controller.add_event_listener(hs_desc_content_listener, stem.control.EventType.HS_DESC_CONTENT)
    controller.add_event_listener(hs_desc_listener, stem.control.EventType.HS_DESC)

    print("Sending HSFETCH")
    result=controller.msg(f"HSFETCH {addr}" )
    if not result.is_ok():
        print("Sending HSFETCH request failed")
        print(result.content())
    else:
        print("Event was sent successfully. Waiting for response event")
        while content_q.qsize() < 1:
            if desc_q.qsize() > 1:
                print(desc_q.get())
            print("sleeping..")
            time.sleep(1)
    desc=content_q.get()
    return desc

def make_private_hsdesc(controller):
    controller.add_event_listener(hs_desc_content_listener, stem.control.EventType.HS_DESC_CONTENT)
    response=controller.create_ephemeral_hidden_service(8080)
    time.sleep(5)
    
    print(f"OK, we detected {content_q.qsize()} events")
    event_0=content_q.get()
    # Make sure to use the right descriptor (the one with the current time zone)
    event=content_q.get()
    
    v3Desc_0=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(event_0.descriptor._raw_contents)
    v3Desc=stem.descriptor.hidden_service.HiddenServiceDescriptorV3(event.descriptor._raw_contents)
     
    onion_address=event.address
    print(f"Created new ephemeral onion service with id: {onion_address}")
    #print(event_0)
    #print(event)
    #print(v3Desc)
    return (onion_address, str(v3Desc), str(v3Desc_0))


from http.server import BaseHTTPRequestHandler, HTTPServer
class TestServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes("<html><head><title>Personal onion service reached</title></head>", "utf-8"))
        self.wfile.write(bytes("<p>Request: %s</p>" % self.path, "utf-8"))
        self.wfile.write(bytes("<body>", "utf-8"))
        self.wfile.write(bytes("<p>Awesome, this test was passed successful</p>", "utf-8"))
        self.wfile.write(bytes("</body></html>", "utf-8"))

def serve_website(server):
    server.serve_forever()

# Have to develop my main test case: 
# 1. Start Tor Client
# 2. Start Web Server
# 3. Create onion service that is not published
# 4. Start 2nd Tor client
# 5. Connect to onion service via 2nd Tor client



# Step 1: Starts the Tor process for the onion service and attaches controller to it

server_tor_process=None
client_tor_process=None
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
    print("Step 1 completed")
    address, desc1,desc2 = make_private_hsdesc(server_controller)
    print(f"Step 2 completed: Onion Service is ready with address: {address}")
    web_server=HTTPServer(('127.0.0.1', 8080), TestServer)
    web_thread=threading.Thread(target=serve_website, args=(web_server,), daemon=True)
    web_thread.start()
    print("Web Server should be running now")
    # OK, now we have an unpublished onion service. Now to see if we can connect to it
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
    print("Client Tor process is ready")
    
    result=client_controller.msg(f"POSTHSDESCRIPTOR address={address}\n{desc1}")
    print(f"Uploaded HS-Descriptor 1 with: {result}")
    result=client_controller.msg(f"POSTHSDESCRIPTOR address={address}\n{desc2}")
    print(f"Uploaded HS-Descriptor 0 with: {result}")
     
    # Moment of Truth: Can I reach the created onion service via the client tor process

    hostname=f"http://{address}.onion:8080/"
    response=requests.get(hostname, proxies=tor_client)
    print(response.text)

    server_tor_process.kill()
    client_tor_process.kill()
except Exception as ex:
    raise ex
finally: 
    if server_tor_process: 
        server_tor_process.kill()
    if client_tor_process: 
        client_tor_process.kill()
