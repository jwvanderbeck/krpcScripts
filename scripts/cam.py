#connection = krpc.connect(name = "Ascent", address="10.0.1.10", rpc_port=50000, stream_port=50001)

import krpc
import time
import argparse
import sys
import os

parser = argparse.ArgumentParser(description='Toggles a hullcamera on or off')
parser.add_argument('--server', '-server', type=str, dest='serverIP', default=None)
parser.add_argument('--port', '-port', type=int, dest='serverPort', default=50000)
parser.add_argument('--camera', '-cam', type=int, dest='cameraNum', default=0)
args = parser.parse_args()


# setup connection
if args.serverIP:
	connection = krpc.connect(name = "Ascent", address=args.serverIP, rpc_port=args.serverPort, stream_port=args.serverPort+1)
else:
	connection = krpc.connect(name = "Ascent", rpc_port=args.serverPort, stream_port=args.serverPort+1)

vessel = connection.space_center.active_vessel
cameras = vessel.parts.with_name('hc.wideangle')
print cameras
cameras[args.cameraNum].modules[0].trigger_event('Activate Camera')
