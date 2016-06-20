# copernicus 1

import krpc
import time
import math
import argparse
import sys
import curses
import os
import utility
import numpy

parser = argparse.ArgumentParser(description='Handles rocket ascent, gravity turn, and insertion into orbit')
parser.add_argument('--server', '-server', type=str, dest='serverIP', default=None)
parser.add_argument('--port', '-port', type=int, dest='serverPort', default=50000)
args = parser.parse_args()

# setup connection
if args.serverIP:
	connection = krpc.connect(name = "Ascent", address=args.serverIP, rpc_port=args.serverPort, stream_port=args.serverPort+1)
else:
	connection = krpc.connect(name = "Ascent", rpc_port=args.serverPort, stream_port=args.serverPort+1)

vessel = connection.space_center.active_vessel
timeToApoapsis = connection.add_stream(getattr, vessel.orbit, 'time_to_apoapsis')

vessel.control.rcs = True
ap = vessel.auto_pilot
ap.reference_frame = vessel.orbital_reference_frame
ap.engage()
ap.target_direction = (0,1,0)
while timeToApoapsis() > 3:
	os.system('cls' if os.name == 'nt' else 'clear')
	print "Waiting on Apoapsis...{0} seconds".format(timeToApoapsis())
	time.sleep(1)

print "Apoapsis reached.  Deploying satellite."
vessel.control.activate_next_stage()