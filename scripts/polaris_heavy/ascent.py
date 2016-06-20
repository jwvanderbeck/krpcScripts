# Polaris Heavy

import krpc
import time
import math
import argparse
import sys
import os
import numpy


def PitchProgramA(speed):
	return 	90 - 1.4 * pow((speed() - 45),0.5)



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

surfaceSpeed = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')

vessel.auto_pilot.engage()
vessel.auto_pilot.target_pitch_and_heading(90, 90)

while True:
	print surfaceSpeed()
	if surfaceSpeed() > 100:
		pitch = PitchProgramA(surfaceSpeed)
		vessel.auto_pilot.target_pitch_and_heading(pitch, 90)