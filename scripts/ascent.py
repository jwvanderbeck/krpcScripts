import krpc
import time
import math
import argparse
import sys
import curses

parser = argparse.ArgumentParser(description='Handles rocket ascent, gravity turn, and insertion into orbit')
parser.add_argument('--ignition-time', "-ignition", type=int, dest='ignitionTime', default=5)
parser.add_argument('--countdown-start', "-start", type=int, dest='countdownStart', default=20)
parser.add_argument('--boosters', type=bool, dest='useBoosters', default=False)
parser.add_argument('--verify-booster-ignition', type=bool, dest='verifyBoosters', default=False)
parser.add_argument('--liftoff-twr', '-twr', type=float, dest='liftoffTWR', default=1.05)
parser.add_argument('--thrust-req', '-thrust', type=float, dest='thrustThreshold', default=0.99)
parser.add_argument('--turn-start', '-turn', type=float, dest='turnStart', default=90)
args = parser.parse_args()


# setup connection
connection = krpc.connect(name = "Ascent", address="10.0.1.10", rpc_port=50000, stream_port=50001)
vessel = connection.space_center.active_vessel
sys.stdout.flush()
print vessel.name, "preparing for launch..."

# setup streams
ut = connection.add_stream(getattr, connection.space_center, "ut")
altitude = connection.add_stream(getattr, vessel.flight(), 'mean_altitude')
apoapsis = connection.add_stream(getattr, vessel.orbit, 'apoapsis_altitude')
periapsis = connection.add_stream(getattr, vessel.orbit, 'periapsis_altitude')
eccentricity = connection.add_stream(getattr, vessel.orbit, 'eccentricity')
surfaceSpeed = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')

# Pre-launch setup
vessel.control.sas = False
vessel.control.rcs = False
vessel.control.throttle = 1

allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
firstStage = vessel.control.current_stage - 1
firstStageEngineParts = []
for part in allEngineParts:
	if part.stage == firstStage:
		firstStageEngineParts.append(part)

firstStageThrust = 0
for part in firstStageEngineParts:
	firstStageThrust += part.engine.max_thrust

# Countdown starts at t-20 seconds
ignition = False
t = args.countdownStart
while t > 0:
	print "T-{0} seconds\r".format(t)
	sys.stdout.flush()
	if t == args.ignitionTime and not ignition:
		print "Main engine ignition"
		# Activate the first stage
		vessel.control.activate_next_stage()
		# vessel.auto_pilot.reference_frame = vessel.surface_reference_frame
		vessel.auto_pilot.engage()
		vessel.auto_pilot.target_direction = (1,0,0)
		ignition = True
	if ignition:
		thrust = vessel.thrust/firstStageThrust
		print "Main engines at {0:.2%} of maximum thrust".format(thrust)
	t -= 1
	time.sleep(1)


# check engine thrust levels
thrust = vessel.thrust/firstStageThrust
print "Main engines at {0:.2%} of maximum thrust".format(thrust)
if thrust < args.thrustThreshold:
	print "Abort. Abort. Abort."
	print "On board computer signaled shut down.  Main engines not at proper thrust levels."
	vessel.control.throttle = 0
	vessel.auto_pilot.disengage()
	sys.exit(1)
# check TWR
availableThrust = vessel.thrust
if args.useBoosters:
	# If boosters are in use, we need to get their anticipated thrust levels
	# for now we assume they will all light properly
	allBoosterParts = vessel.parts.with_module("ModuleEnginesRF")
	nextStage = vessel.control.current_stage - 1
	nextStageBoosterParts = []
	for part in allBoosterParts:
		if part.stage == nextStage:
			nextStageBoosterParts.append(part)
	boosterThrust = 0
	for part in nextStageBoosterParts:
		boosterThrust += part.engine.max_thrust
	availableThrust += boosterThrust
g = vessel.orbit.body.surface_gravity
if availableThrust <= g * vessel.mass * args.liftoffTWR:
	print "Abort. Abort. Abort."
	if args.useBoosters:
		print "On board computer signaled shut down.  Available thrust plus anticipated booster thrust is insufficient for liftoff."
	else:
		print "On board computer signaled shut down.  Available thrust is insufficient for liftoff."
	vessel.control.throttle = 0
	vessel.auto_pilot.disengage()
	sys.exit(1)

print "Liftoff!"
vessel.control.activate_next_stage()
# speed = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')
# while speed() < args.turnStart:
# 	time.sleep(0.1)

turn_start_altitude = 500
turn_end_altitude = 160000
turn_angle = 0
while altitude() < turn_end_altitude:
	pass
	time.sleep(5)
	if surfaceSpeed() < args.turnStart:
		print "Surface velocity {0}m/s, waiting for {1}m/s to begin turn.".format(surfaceSpeed(), args.turnStart)
		time.sleep(1)
	if altitude() > turn_start_altitude and altitude() < turn_end_altitude:
		frac = (altitude() - turn_start_altitude) / (turn_end_altitude - turn_start_altitude)
		print "Turn fraction: ", frac
		new_turn_angle = frac * 90
		print "Calculated new turn angle: ", new_turn_angle
		if abs(new_turn_angle - turn_angle) > 0.1:
			turn_angle = new_turn_angle
			vessel.auto_pilot.target_pitch_and_heading(90-turn_angle, 90)

vessel.auto_pilot.disengage()

