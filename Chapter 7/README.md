# Optimizing onion services for M2M communication
This repository complements chapter 7 of my dissertation on privacy perserving networking for distributed systems. 
It discussed an approach to improve Onion Service performance for communication patterns relying on a Pub/Sub structure. 

## Bypassing the HSDir
Skipping uploads to the HSDir for debugging purposes is a functionality already implemented in Tor. This branch adds an additional feature to return a not-uploaded descriptor via the Control Protocol to the user creating the onion service. 
Additionally, a second feature was implemented to load new service descriptors via the control protocol. 

## Sending 1-way messages instead of RENDEZVOUS cells
If only a single message must be sent to an onion service, using the regular procedure of establishing a rendezvous node is inefficient. Instead, the message can be included in the RENDEZVOUS cell instead of the rendzevous request. 
This was implemented via a new function in the Control Protocl that directly adds information to a message. 

## Subscribing with 1-way messages
A good example for 1-way messages are subscribe request within a Pub/Sub system. By minimizing the service descriptor to fit into the rendezvous cell, it is possible to sent subscription requests within a single direct request. 
This is essentiallly an improvement of the functionality of sending a 1-way message. 


# Tor Default README

Tor protects your privacy on the internet by hiding the connection
between your Internet address and the services you use. We believe Tor
is reasonably secure, but please ensure you read the instructions and
configure it properly.

To build Tor from source:
        ./configure && make && make install

To build Tor from a just-cloned git repository:
        sh autogen.sh && ./configure && make && make install

Home page:
        https://www.torproject.org/

Download new versions:
        https://www.torproject.org/download/download.html

Documentation, including links to installation and setup instructions:
        https://www.torproject.org/docs/documentation.html

Making applications work with Tor:
        https://gitlab.torproject.org/legacy/trac/-/wikis/doc/TorifyHOWTO

Frequently Asked Questions:
        https://www.torproject.org/docs/faq.html

Release timeline:
        https://gitlab.torproject.org/tpo/core/team/-/wikis/NetworkTeam/CoreTorReleases

To get started working on Tor development:
        See the doc/HACKING directory.
