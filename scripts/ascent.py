import krpc
import time
import math
import argparse
import sys
import curses
import os
import utility

parser = argparse.ArgumentParser(description='Handles rocket ascent, gravity turn, and insertion into orbit')
parser.add_argument('--ignition-time', "-ignition", type=int, dest='ignitionTime', default=5)
parser.add_argument('--countdown-start', "-start", type=int, dest='countdownStart', default=20)
parser.add_argument('--boosters', type=bool, dest='useBoosters', default=False)
parser.add_argument('--verify-booster-ignition', type=bool, dest='verifyBoosters', default=False)
parser.add_argument('--liftoff-twr', '-twr', type=float, dest='liftoffTWR', default=1.05)
parser.add_argument('--thrust-req', '-thrust', type=float, dest='thrustThreshold', default=0.99)
parser.add_argument('--turn-start', '-turn', type=float, dest='turnStart', default=90)
parser.add_argument('--target-ap', '-ap', type=float, dest='targetAP', default=185000.00)
parser.add_argument('--max-pitchmod', '-maxpitch', type=float, dest='maxPitchMod', default=30.00)
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
orbitalSpeed = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.non_rotating_reference_frame), 'speed')

# Pre-launch setup
vessel.control.sas = False
vessel.control.rcs = False
vessel.control.throttle = 1

# FlightData utility
fd = utility.FlightData(vessel)

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

turn_start_altitude = 500
turn_end_altitude = 185000
turn_angle = 0
targetOrbitalSpeed = 7797.33 # for a 185x185 orbit
angleModifier = 0.0
lastAP = 0
lastSpeed = 0
inOrbit = False
previousFlightData = {
	'surfaceSpeed' : 0.0,
	'orbitalSpeed' : 0.0,
	'apoapsis' : 0.0,
	'periapsis' : -50000000.0,
	'pitch' : 90.0,
	'pitchMod' : 0.0,
	'targetApoapsisHit' : False
}
currentFlightData = dict(previousFlightData)
loopTime = 0.5
while not inOrbit:
	# Calculate new data
	currentFlightData['surfaceSpeed'] = surfaceSpeed()
	currentFlightData['orbitalSpeed'] = orbitalSpeed()
	currentFlightData['apoapsis'] = apoapsis()
	currentFlightData['periapsis'] = periapsis()
	surfaceVelocityDelta = (currentFlightData['surfaceSpeed'] - previousFlightData['surfaceSpeed']) * (1 / loopTime)
	if (surfaceVelocityDelta <= 0.0):
		surfaceVelocityDelta = 0.1
	orbitalVelocityDelta = (currentFlightData['orbitalSpeed'] - previousFlightData['orbitalSpeed']) * (1 / loopTime)
	if (orbitalVelocityDelta <= 0.0):
		orbitalVelocityDelta = 0.1
	timeToInsertion = (targetOrbitalSpeed - currentFlightData['orbitalSpeed']) / orbitalVelocityDelta
	apDelta = (currentFlightData['apoapsis'] - previousFlightData['apoapsis']) * (1 / loopTime)
	timeToTargetAP = (args.targetAP - currentFlightData['apoapsis']) / apDelta

	# determine mode
	if currentFlightData['surfaceSpeed'] < args.turnStart:
		currentMode = "ASCENT"
	elif currentFlightData['surfaceSpeed'] >= args.turnStart and currentFlightData['surfaceSpeed'] < 1000.0:
		currentMode = "PITCH PROGRAM MOD1"
	elif currentFlightData['surfaceSpeed'] >= 1000.0 and not currentFlightData['targetApoapsisHit']:
		currentMode = "PITCH PROGRAM MOD2"
	elif currentFlightData['targetApoapsisHit'] and currentFlightData['orbitalSpeed'] < targetOrbitalSpeed - 1000.0:
		currentMode = ['APOAPSIS MOD1']
	elif currentFlightData['targetApoapsisHit'] and currentFlightData['orbitalSpeed'] < targetOrbitalSpeed:
		currentMode = ['INSERTION']

	# Data blocks
	print "MODE:", currentMode
	if currentMode in ['ASCENT', 'PITCH PROGRAM MOD1', 'PITCH PROGRAM MOD2']:
		print "SURFACE"
		print "======="
		print "Velocity: {0}m/s".format(round(currentFlightData['surfaceSpeed'], 2))
		print "Acceleration: {0}m/s".format(round(surfaceVelocityDelta, 2))
		if currentMode == 'ASCENT':
			print "TT Pitch Program: {0} seconds".format( round((args.turnStart - currentFlightData['surfaceSpeed']) / surfaceVelocityDelta, 2) )
	if currentMode in ['PITCH PROGRAM MOD1', 'PITCH PROGRAM MOD2', 'APOAPSIS MOD1', 'INSERTION']:
		print ""
		print "ORBIT"
		print "====="
		print "Velocity:", orbitalSpeed()
		print "Acceleration: {0}m/s".format(round(orbitalVelocityDelta, 2))
		print "Apoapsis: {0}m".format(round(currentFlightData['apoapsis'], 2))
		print "AP Delta: {0}m/s".format(round(apDelta,2))
		print "Periapsis: {0}m".format(round(currentFlightData['periapsis'], 2))
		print "TT Insertion: {0} seconds".format(round(timeToInsertion, 2))
		print "TT Target Apoapsis: {0} seconds".format(round(timeToTargetAP,2))
	
	print "FLIGHT"
	print "======"
	print "Pitch set: {0} degrees".format(round(currentFlightData['pitch'],2))
	print "Pitch mod: {0} degrees".format(round(currentFlightData['pitchMod'],2))

	# Determine base pitch.  This is calculated to get us to 45 degrees at roughly 1km/s (1083 m/s to be exact) and 0 pitch close to orbital speed (7848 m/s to be exact)
	if currentMode != "ASCENT":
		currentFlightData['pitch'] = 90 - 3.9 * pow( (currentFlightData['surfaceSpeed'] - 45), 0.35 )
	if not currentFlightData['targetApoapsisHit']:
		if currentFlightData['apoapsis'] >= args.targetAP:
			currentFlightData['targetApoapsisHit'] = True
	if currentMode == "PITCH PROGRAM MOD2":
		# in Pitch mod2 we basically continue along our gravity turn but are watching for us to get the right AP
		# Here we are looking at how quickly our AP is increasing, along with our time to insertion
		# If we detect that we will get to insertion before obtaining the desired AP, we will pitch up slightly from the base pitch
		# The reverse is also true, if we detect we will hit the AP well before insertion, we pitch down slightly
		# check that we won't hit AP at all
		if timeToTargetAP > timeToInsertion:
			print ""
			print "PITCH MOD - TTAP - Pitch Up"
			currentFlightData['pitchMod'] += 1.0
		if timeToTargetAP < (timeToInsertion * 0.7):
			print ""
			print "PITCH MOD - TTAP - Pitch Down"
			currentFlightData['pitchMod'] -= 1.0

	# apply pitch and pitch mod
	if currentMode != "ASCENT":
		if currentFlightData['pitchMod'] < -args.maxPitchMod:
			currentFlightData['pitchMod'] = -args.maxPitchMod
		if currentFlightData['pitchMod'] > args.maxPitchMod:
			currentFlightData['pitchMod'] = args.maxPitchMod
		finalPitchAngle = currentFlightData['pitch'] + currentFlightData['pitchMod']
		vessel.auto_pilot.target_pitch_and_heading(finalPitchAngle, 90)

	# store current flight data as last flight data for use next loop
	previousFlightData = dict(currentFlightData)

	time.sleep(loopTime)
	os.system('cls' if os.name == 'nt' else 'clear')

# while orbitalSpeed() < targetOrbitalSpeed * 1.20:
# 	pass
# 	print "Orbital speed:", orbitalSpeed()
# 	speedRateOfChange = (orbitalSpeed() - lastSpeed) * 2
# 	if speedRateOfChange <= 0:
# 		speedRateOfChange = 1
# 	print "Speed is increasing at {0} m/s".format(speedRateOfChange)
# 	lastSpeed = orbitalSpeed()
# 	if orbitalSpeed() < targetOrbitalSpeed:
# 		deltaSpeed = targetOrbitalSpeed - orbitalSpeed()
# 		print "Difference between current speed and orbital speed is", deltaSpeed
# 		print "Will reach orbital speed in {0} seconds".format(deltaSpeed / speedRateOfChange)

# 	if apoapsis() > lastAP:
# 		lastAP = apoapsis()
# 		isAPIncreasing = True
# 	else:
# 		isAPIncreasing = False

# 	if surfaceSpeed() < args.turnStart:
# 		print "Surface velocity {0}m/s, waiting for {1}m/s to begin turn.".format(surfaceSpeed(), args.turnStart)
# 		os.system('cls' if os.name == 'nt' else 'clear')
# 		time.sleep(0.5)
# 		continue
# 	if surfaceSpeed() > 1000.0 and periapsis() < 180000:
# 		if apoapsis() > turn_end_altitude and isAPIncreasing:
# 			print "Pitching down"
# 			angleModifier -= 0.5
# 			if angleModifier < -20:
# 				angleModifier = -20.0
# 		if apoapsis() < turn_end_altitude and not isAPIncreasing:
# 			print "Pitching up"
# 			angleModifier += 0.5
# 			if angleModifier > 20:
# 				angleModifier = 20.0
# 	if altitude() > turn_start_altitude:
# 		# frac = (altitude() - turn_start_altitude) / (turn_end_altitude - turn_start_altitude)
# 		angle = 90 - 1.4*pow((surfaceSpeed() - 45),0.5)
# 		angle += angleModifier
# 		os.system('cls' if os.name == 'nt' else 'clear')
# 		print "Calculated pitch angle:", round(angle, 2)
# 		twr = fd.CurrentStageTWR(vessel)
# 		print "Calculated TWR", round(twr,2)
# 		if abs(angle - turn_angle) > 0.1:
# 			turn_angle = angle
# 			vessel.auto_pilot.target_pitch_and_heading(turn_angle, 90)
# 		time.sleep(0.5)
# 		continue
	
# 	if periapsis() >= 180000:
# 		break

# 	time.sleep(0.5)
# 	continue

vessel.control.throttle = 0
vessel.auto_pilot.disengage()

