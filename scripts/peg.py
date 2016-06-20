import krpc
import time
import math
import sys
import numpy

"""
Navigation is responsible for maintining the craft's navigation state such as position, velocity, etc.
It is a digital analogue to and Inertial guidance system
"""
class Navigation(object):


class FlightData(object):
	def __init__(self, vessel):
		self.initialized = True
		self.vessel = vessel

	def CurrentStageTWR(self):
		vessel = self.vessel
		currentThrust = vessel.available_thrust
		g = vessel.orbit.body.surface_gravity
		twr = currentThrust / (vessel.mass*g)
		return twr

	def StageVacuumSpecificImpulse(self, stage):
		thrust = 0
		fuelConsumption = 0
		vessel = self.vessel
		allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
		for part in allEngineParts:
			if part.stage == stage:
				if part.engine.can_restart:
					thrust += part.engine.max_thrust
					fuelConsumption = fuelConsumption + (part.engine.max_thrust / part.engine.vacuum_specific_impulse)
		if fuelConsumption <= 0.0:
			return 0.0
		else:
			return thrust / fuelConsumption


	def StageBurnTime(self, stage):
		# tonnes of propellant * Isp * 9.80665 / thrust
		# build a list of propellants used by all engines in the stage
		vessel = self.vessel
		Isp = self.StageVacuumSpecificImpulse(stage) # seconds
		thrust = 0 # newtons
		allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
		stagePropellants = []
		for part in allEngineParts:
			if part.stage == stage and part.engine and part.engine.can_restart:
				thrust += part.engine.max_thrust
				for prop in part.engine.propellants:
					if not prop in stagePropellants:
						stagePropellants.append(prop)
		# get a list of all resources in the stage
		allResources = vessel.resources_in_decouple_stage(stage, cumulative = True).all
		propellantMass = 0
		for resource in allResources:
				if resource.name in stagePropellants:
					propellantMass += (resource.amount * resource.density)
		if thrust > 0.0:
			return propellantMass * Isp * 9.80665 / thrust
		else:
			return 0.0


# PEG code adapted from the kOS scripts here:
# https://github.com/Noiredd/PEGAS
def square(a):
	return numpy.power(a, 2)

class PEG(object):
	def __init__(self, vessel, connection, targetOrbit = 185000.0, loopTime = 1.0, insertionStage = 0):
		self.epsilon = 3
		self.cycleRate = loopTime
		self.targetOrbit = targetOrbit + 6371000.0
		self.guidanceConverged = False
		self.convergedGuidanceSamples = 0
		self.isp = -1
		self.vessel = vessel
		self.insertionStage = insertionStage
		self.engineList = []
		allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
		for part in allEngineParts:
			if part.stage == insertionStage:
				if part.engine.can_restart:
					self.engineList.append(part)
		self.altitude = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'mean_altitude')
		self.velocity = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.non_rotating_reference_frame), 'horizontal_speed')
		self.verticalVelocity = connection.add_stream(getattr, vessel.flight(vessel.orbit.body.non_rotating_reference_frame), 'vertical_speed')
		self.mu = -1.0


	def StageVacuumSpecificImpulse(self, stage):
		print "Calculating Isp for stage {0}".format(stage)
		vessel = self.vessel
		thrust = 0
		fuelConsumption = 0
		allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
		for part in allEngineParts:
			if part.stage == stage:
				if part.engine.can_restart:
					print part.name
					thrust += part.engine.max_thrust
					fuelConsumption = fuelConsumption + (part.engine.max_thrust / part.engine.vacuum_specific_impulse)
		if fuelConsumption <= 0.0:
			return 0.0
		else:
			return thrust / fuelConsumption


	def updateState(self, vessel, connection):
		# self.altitude = numpy.linalg.norm(vessel.position(vessel.orbit.body.reference_frame))	# from center of body, not SL
		# self.velocity = vessel.flight(vessel.orbit.body.non_rotating_reference_frame).horizontal_speed
		# # self.velocity = math.sqrt(square(vessel.flight(vessel.orbit.body.non_rotating_reference_frame).speed) - square(vessel.flight(vessel.orbit.body.non_rotating_reference_frame).vertical_speed))
		# self.verticalVelocity = vessel.flight(vessel.orbit.body.non_rotating_reference_frame).vertical_speed
		self.angle = numpy.arctan2(self.velocity, self.verticalVelocity)
		self.thrust = 0.0
		for engine in self.engineList:
			self.thrust  = self.thrust + engine.thrust
		self.acceleration = self.thrust / vessel.mass
		if self.isp <= 0:
			self.isp = self.StageVacuumSpecificImpulse(self.insertionStage)
		if self.thrust > 0:
			self.exhaustVelocity = self.isp * 9.80665# / self.thrust
		else:
			self.exhaustVelocity = 0.01
		if self.mu <= 0.0:
			self.mu = vessel.orbit.body.gravitational_parameter

	def msolve(self, tau, oldT, gain):
		print "msolve tau: {0}, oldT: {1}, gain: {2}".format(tau, oldT, gain)
		if tau == 0.0:
			tau = 0.01
		x = max(0.01, min(1, 1-oldT/tau))
		b0 = -self.exhaustVelocity * math.log(x)
		b1 = b0 * tau - self.exhaustVelocity * oldT

		c0 = b0 * oldT - b1
		c1 = c0 * tau - self.exhaustVelocity * square(oldT) / 2

		z0 = -self.verticalVelocity()
		z1 = gain - self.verticalVelocity() * oldT

		B = (z1 / c0 - z0 / b0) / (c1 / c0 - b1 / b0)
		A = (z0 - b1 * B) / b0
		print "A {0}. B {1}".format(A,B)
		return (A,B)

	def peg(self, oldA, oldB, oldT, deltaTime = 0):
		# print "peg oldA: {0}, oldB: {1}, oldT {2}".format(oldA, oldB, oldT)
		deltaTime = self.cycleRate# + 0.5
		tau = self.exhaustVelocity / self.acceleration
		# print "tau: {0}".format(tau)
		A=B=C=T=0

		if oldA == 0 and oldB == 0:
			oldA, oldB = self.msolve(tau, oldT, self.targetOrbit - self.altitude())

		# angular momentum
		angM = numpy.linalg.norm(numpy.cross([self.altitude(), 0, 0], [self.verticalVelocity(), self.velocity(), 0]))
		# print "angM: {0}".format(angM)
		tgtV = numpy.sqrt(self.mu/self.targetOrbit)
		# print "tgtV: {0}".format(tgtV)
		tgtM = numpy.linalg.norm(numpy.cross([self.targetOrbit, 0, 0], [0, tgtV, 0]))
		# print "tgtM: {0}".format(tgtM)
		dMom = tgtM - angM
		# print "dMom: {0}".format(dMom)

		# steering constants f_r
		C = (self.mu / square(self.targetOrbit) - square(tgtV) / self.targetOrbit) / (self.acceleration / (1-oldT/tau))
		# print "C: {0}".format(C)
		frt = oldA + oldB * oldT + C
		# print "frt: {0}".format(frt)
		C = (self.mu / square(self.altitude()) - square(self.velocity()) / self.altitude()) / self.acceleration
		# print "C: {0}".format(C)
		fr = oldA + C
		# print "fr: {0}".format(fr)
		frdot = (frt-fr) / oldT
		# print "frdot: {0}".format(frdot)

		# steering constants f_theta
		ft = 1 - square(fr) / 2
		# print "ft: {0}".format(ft)
		ftdot = -fr * frdot
		# print "ftdot: {0}".format(ftdot)
		ftdd = -square(frdot) / 2
		# print "ftdd: {0}".format(ftdd)

		# deltaV and T, time to burn out
		avgR = (self.altitude() + self.targetOrbit) / 2
		# print "avgR: {0}".format(avgR)
		# print "exhaustVelocity: {0}".format(self.exhaustVelocity)
		# print "oldT: {0}".format(oldT)
		# print "cycleRate: {0}".format(self.cycleRate)
		dv = dMom / avgR + self.exhaustVelocity * (oldT - deltaTime) * (ftdot + ftdd * tau) + ftdd * self.exhaustVelocity * square((oldT - deltaTime)) / 2
		# print "dv: {0}".format(dv)
		dv = dv / (ft + ftdot * tau + ftdd * square(tau))
		# print "dv: {0}".format(dv)
		T = tau * (1 - numpy.exp((-dv/self.exhaustVelocity)))
		# print "T: {0}".format(T)

		if T >= self.epsilon * peg.cycleRate:
			A, B = self.msolve(tau, oldT, self.targetOrbit - self.altitude())
		else:
			A = oldA
			B - oldB

		return (A, B, C, T)


