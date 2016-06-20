#connection = krpc.connect(name = "Ascent", address="10.0.1.10", rpc_port=50000, stream_port=50001)

import krpc
import time
import math
import argparse
import sys
import curses
import os
# import utility
import numpy
import Launch_Manager

parser = argparse.ArgumentParser(description='Handles rocket ascent, gravity turn, and insertion into orbit')
parser.add_argument('--ignition-time', "-ignition", type=int, dest='ignitionTime', default=5)
parser.add_argument('--countdown-start', "-start", type=int, dest='countdownStart', default=20)
parser.add_argument('--boosters', type=bool, dest='useBoosters', default=False)
parser.add_argument('--verify-booster-ignition', type=bool, dest='verifyBoosters', default=False)
parser.add_argument('--liftoff-twr', '-twr', type=float, dest='liftoffTWR', default=1.05)
parser.add_argument('--thrust-req', '-thrust', type=float, dest='thrustThreshold', default=0.99)
parser.add_argument('--turn-start', '-turn', type=float, dest='turnStart', default=90)
parser.add_argument('--target-ap', '-ap', type=float, dest='targetAP', default=185000.00)
parser.add_argument('--target-inclination', '-inc', type=float, dest='targetInclination', default=28.7)
parser.add_argument('--pitch-rate', '-pitch', type=float, dest='pitchRate', default=1.45)
parser.add_argument('--insertion-stage', '-ostage', type=int, dest='insertionStage', default=-1)
parser.add_argument('--peg-loop-time', '-looptime', type=float, dest='loopTime', default=1.0)
parser.add_argument('--server', '-server', type=str, dest='serverIP', default=None)
parser.add_argument('--port', '-port', type=int, dest='serverPort', default=50000)
args = parser.parse_args()


# setup connection
if args.serverIP:
	connection = krpc.connect(name = "Ascent", address=args.serverIP, rpc_port=args.serverPort, stream_port=args.serverPort+1)
else:
	connection = krpc.connect(name = "Ascent", rpc_port=args.serverPort, stream_port=args.serverPort+1)

vessel = connection.space_center.active_vessel
sys.stdout.flush()
print "Ascent script v2"
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
# fd = utility.FlightData(vessel)
lm = Launch_Manager.LaunchManager(args.targetAP, args.targetInclination)
lm.pitchRate = args.pitchRate


allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
firstStage = vessel.control.current_stage - 1
firstStageEngineParts = []
for part in allEngineParts:
	if part.stage == firstStage:
		firstStageEngineParts.append(part)

firstStageThrust = 0
for part in firstStageEngineParts:
	firstStageThrust += part.engine.max_thrust

if firstStageThrust <= 0:
	print "Launch aborted.  No first stage thrust found."
	sys.exit(1)

# Countdown starts at t-20 seconds
ignition = False
t = args.countdownStart
countdownClockPanel = connection.ui_extended.add_panel()
countdownClockPanel.size = (100,50)
while t > 0:
	# countdownDisplayText.content =  "T-{0} seconds\r".format(t)
	print "T-{0} seconds\r".format(t)
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
# countdownDisplayText.visible = False

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


# [21:12:43] <NathanKell> I _think_ what you would need is the following.
# [21:12:47] <NathanKell> Let's assume a 2-stage vehicle
# [21:13:19] <NathanKell> You will need, on first stage burnout, a time to apogee which, combined with further stretching of your orbit due to velocity increment, is >= required burn time of second stage.
# [21:13:45] <NathanKell> At simplest, we will assume we will circularize at apogee rather than after.
# [21:14:21] <NathanKell> _as a rule of thumb_ that means a minute lower time to apogee than your stage burn time (for these high-TWR stages)
# [21:14:42] <NathanKell> _also_ the apogee created by the first stage must not be higher than the desired final perigee.
# [21:15:09] <NathanKell> its distance from the final perigee will presumably be a function of the velocity vector at burnout.
# [21:16:04] <NathanKell> so your program needs to do two things.
# [21:17:24] <NathanKell> It needs to handle the first stage (calculating that apogee, and flying the first stage to procure it) and it needs to handle the second stage (managing pitch such that you hit your desired insertion altitude at 0m/s vertical velocity and at [circular orbital velocity at that height] horizontal velocity)

turn_start_altitude = 500
turn_end_altitude = 185000
turn_angle = 0
targetOrbitalSpeed = 7797.33 # for a 185x185 orbit
angleModifier = 0.0
lastAP = -100
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
# PEG test
# peg = utility.PEG(vessel, connection, args.targetAP, args.loopTime, args.insertionStage) # target a 185km orbit
print "Initial PEG Update"
# peg.updateState(vessel, connection)
pegInit = False
# stageBurnTime = fd.StageBurnTime(args.insertionStage)
A=B=C=0
pegStartup = 0
lastTime = ut()
pegTime = 0
pegEstimation = pegGuidance = pegConvergenceFactor = 0.0
rollComplete = False
# vessel.auto_pilot.target_roll = 0
currentMode = "PreLauch"
while currentMode != "Orbit":
	deltaTime = ut() - lastTime
	pegTime += deltaTime
	lastTime = ut()

	# Calculate new data
	currentFlightData['surfaceSpeed'] = surfaceSpeed()
	currentFlightData['orbitalSpeed'] = orbitalSpeed()
	currentFlightData['apoapsis'] = apoapsis()
	currentFlightData['periapsis'] = periapsis()
	# surfaceVelocityDelta = (currentFlightData['surfaceSpeed'] - previousFlightData['surfaceSpeed']) * (1 / args.loopTime)
	# if (surfaceVelocityDelta <= 0.0):
	# 	surfaceVelocityDelta = 0.1
	# orbitalVelocityDelta = (currentFlightData['orbitalSpeed'] - previousFlightData['orbitalSpeed']) * (1 / args.loopTime)
	# if (orbitalVelocityDelta <= 0.0):
	# 	orbitalVelocityDelta = 0.1
	# timeToInsertion = (targetOrbitalSpeed - currentFlightData['orbitalSpeed']) / orbitalVelocityDelta
	# apDelta = (currentFlightData['apoapsis'] - previousFlightData['apoapsis']) * (1 / args.loopTime)
	# timeToTargetAP = (args.targetAP - currentFlightData['apoapsis']) / apDelta

	# determine mode
	if currentFlightData['surfaceSpeed'] < args.turnStart:
		currentMode = "ASCENT"
	elif currentFlightData['surfaceSpeed'] >= args.turnStart:# and currentFlightData['surfaceSpeed'] < 1000.0:
		currentMode = "PITCH PROGRAM MOD1"

	if vessel.control.current_stage <= args.insertionStage:
		lm.onInsertionStage = True
		currentMode = "INSERTION"

	# Data blocks
	os.system('cls' if os.name == 'nt' else 'clear')
	print "MODE:", currentMode
	if currentMode in ['ASCENT', 'PITCH PROGRAM MOD1', 'PITCH PROGRAM MOD2']:
		print "SURFACE"
		print "======="
		print "Velocity: {0}m/s".format(round(currentFlightData['surfaceSpeed'], 2))
		# if currentMode == 'ASCENT':
		# 	print "TT Pitch Program: {0} seconds".format( round((args.turnStart - currentFlightData['surfaceSpeed']) / surfaceVelocityDelta, 2) )
	if currentMode in ['PITCH PROGRAM MOD1', 'PITCH PROGRAM MOD2', 'APOAPSIS MOD1', 'INSERTION', 'PEG']:
		print ""
		print "ORBIT"
		print "====="
		print "Velocity:", orbitalSpeed()
		print "Apoapsis: {0}m".format(round(currentFlightData['apoapsis'], 2))
		print "Periapsis: {0}m".format(round(currentFlightData['periapsis'], 2))
		print "AP dV: {0:.2f}m/s".format(lm.target_apoapsis_speed_dv())
		print "Circ dV: {0:.2f} m/s".format(lm.circ_dv())
		print "Circularization time {0:.2f}s".format((lm.maneuver_burn_time(lm.circ_dv())))
		print "Mean anomaly: {0:.2f}".format(lm.mean_anomaly())

		# print "Thrust: {0}kN".format(vessel.thrust * 1000.0)
		# print "Max Thrust: {0}kN".format(vessel.max_thrust * 1000.0)
		# print "Available Thrust: {0}kN".format(vessel.available_thrust * 1000.0)
	
	print ""
	print "FLIGHT"
	print "======"
	# print "Thrust {0}n / Max Thrust {1}n ({1}%)".format(vessel.thrust, vessel.max_thrust, vessel.thrust / vessel.max_thrust)
	print "Pitch set: {0:.2f} degrees".format(lm.pitchSet)
	print "Pitch mode: {0}".format(lm.pitchMode)
	# print "Pitch mod: {0:.2f} degrees".format(currentFlightData['pitchMod'])
	# print "Target Roll: {0:.2f}".format(vessel.auto_pilot.target_roll)
	# print "Roll Error: {0:.2f}".format(vessel.auto_pilot.roll_error)
	# print "Isp: {0} s".format(fd.StageVacuumSpecificImpulse(vessel.control.current_stage))
	print ""

	# Determine base pitch.  This is calculated to get us to 45 degrees at roughly 1km/s (1083 m/s to be exact) and 0 pitch close to orbital speed (7848 m/s to be exact)
	if currentMode not in ["ASCENT", "PEG"]:
		if currentMode == "PITCH PROGRAM MOD1":
			speed = currentFlightData['surfaceSpeed']
		else:
			speed = currentFlightData['orbitalSpeed']
		# currentFlightData['pitch'] = 90 - 1.4 * pow((surfaceSpeed() - 45),0.5)
		# currentFlightData['pitch'] = 90 - 2.5 * pow( (speed - 45), 0.4 )
		lm.pitch_and_heading()
	# if not currentFlightData['targetApoapsisHit']:
	# 	if currentFlightData['apoapsis'] >= args.targetAP:
	# 		currentFlightData['targetApoapsisHit'] = True
	# if currentMode == "PITCH PROGRAM MOD2":
	# 	# in Pitch mod2 we basically continue along our gravity turn but are watching for us to get the right AP
	# 	# Here we are looking at how quickly our AP is increasing, along with our time to insertion
	# 	# If we detect that we will get to insertion before obtaining the desired AP, we will pitch up slightly from the base pitch
	# 	# The reverse is also true, if we detect we will hit the AP well before insertion, we pitch down slightly
	# 	# check that we won't hit AP at all
	# 	if timeToTargetAP > timeToInsertion:
	# 		print ""
	# 		print "PITCH MOD - TTAP - Pitch Up"
	# 		currentFlightData['pitchMod'] += 1.0
	# 	if timeToTargetAP < (timeToInsertion * 0.7):
	# 		print ""
	# 		print "PITCH MOD - TTAP - Pitch Down"
	# 		currentFlightData['pitchMod'] -= 1.0

	if (lm.circ_dv() < 10) or (lm.orbital_period(lm.target_orbit_alt + lm.radius_eq, lm.mu) < lm.period()):
		currentMode = "Orbit"

	# store current flight data as last flight data for use next loop
	previousFlightData = dict(currentFlightData)

	# sleepTime = args.loopTime - pegTime
	# print "Remaning sleep time {0}".format(sleepTime)
	# sleepTime = max(0,sleepTime)
	# time.sleep(args.loopTime - pegTime)

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

