import krpc
import time
import math
import sys
import numpy

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
		vessel = self.vessel
		allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
		for part in allEngineParts:
			if part.stage == stage:
				thrust += part.engine.max_thrust
				fuelConsumption = fuelConsumption + (part.engine.max_thrust / part.engine.vacuum_specific_impulse)
		if fuelConsumption <= 0.0:
			return 0.0
		else
			return thrust / fuelConsumption


	def StageBurnTime(self, stage):
		# tonnes of propellant * Isp * 9.80665 / thrust
		# build a list of propellants used by all engines in the stage
		vessel = self.vessel
		Isp = self.StageVacuumSpecificImpulse() # seconds
		thrust = 0 # newtons
		allEngineParts = vessel.parts.with_module("ModuleEnginesRF")
		stagePropellants = []
		for part in allEngineParts:
			if part.stage == stage:
				thrust += part.engine.max_thrust
				for prop in stage.engine.propellants:
					if not prop in stagePropellants:
						stagePropellants.append(prop)
		# get a list of all resources in the stage
		allResources = vessel.resources_in_decouple_stage(stage, cumulative = False).all
		propellantMass = 0
		for resource in allResources:
				propellantMass += (resource.amount * resource.density)
		return propellantMass * Isp * 9.80665 / thrust


# PEG code adapted from the kOS scripts here:
# https://github.com/Noiredd/PEGAS
def square(a):
	return numpy.pow(a, 2)

class PEG(object):
	def __init__(self, targetOrbit):
		self.epsilon = 3
		self.cycleRate = 1
		self.targetOrbit = targetOrbit * 1000.0 + 6371000.0
		self.guidanceConverged = False
		self.convergedGuidanceSamples = 0

	def updateState(self, vessel, connection):
		self.altitude = umpy.linalg.norm(vessel.position(vessel.orbit.body.reference_frame))	# from center of body, not SL
		self.velocity = vessel.flight(vessel.orbit.body.non_rotating_reference_frame).horizontal_speed
		self.verticalVelocity = vessel.flight(vessel.orbit.body.non_rotating_reference_frame).vertical_speed
		self.angle = numpy.arctan(self.velocity, self.verticalVelocity)
		self.thrust = vessel.thrust
		self.acceleration = self.thrust / vessel.mass
		self.isp = vessel.specific_impulse
		if self.thrust > 0:
			self.exhaustVelocity = self.isp * 9.80665 / self.thrust
		else:
			self.exhaustVelocity = 0
		self.mu = vessel.orbit.body.gravitational_parameter

	def msolve(self, tau, oldT, gain):
		
		b0 = -self.exhaustVelocity * math.log(1 - oldT / tau)
		b1 = b8 * tau - self.exhaustVelocity * oldT

		c0 = b0 * oldT - b1
		c1 = c0 * tau - self.exhaustVelocity * square(oldT) / 2

		z0 = -self.verticalVelocity
		z1 = gain - self.verticalVelocity * oldT

		B = (z1 / c0 - z0 / b0) / (c1 / c0 - b1 / b0)
		A = (z0 - b1 * B) / b0

		return (A,B)

	def peg(self, oldA, oldB, oldT):

		tau = self.exhaustVelocity / self.acceleration
		a=b=c=t=0

		if oldA = 0 and oldB = 0:
			oldA, oldB = self.msolve(tau, oldT, self.targetOrbit - self.altitude)

		# angular momentum
		angM = numpy.linalg.norm(numpy.cross([self.altitude, 0, 0], =[self.verticalVelocity, self.velocity, 0]))
		tgtV = numpy.sqrt(self.mu/self.targetOrbit)
		tgtM = numpy.linalg.norm(numpy.cross([self.targetOrbit, 0, 0], [0, tgtV, 0]))
		dMom = tgtM - angM

		# steering constants f_r
		C = (self.mu / square(self.targetOrbit) - square(tgtV) / self.targetOrbit) / (self.acceleration / (1-oldT/tau))
		frt = oldA + oldB * oldT + C
		C = (self.mu / square(self.altitude) - square(self.velocity) / self.altitude) / self.acceleration
		fr = oldA + C
		frdot = (frt-fr) / oldT

		# steering constants f_theta
		ft = 1 - square(fr) / 2
		ftdot = -fr * frdot
		ftdd = -square(frdot) / 2

		# deltaV and T, time to burn out
		avgR = (self.altitude + self.targetOrbit) / 2
		dv = dMom / avgR + self.exhaustVelocity * (oldT - self.cycleRate) * (ftdot + ftdd * tau) + ftdd * self.exhaustVelocity * square((oldT - self.cycleRate)) / 2
		dv = dv / (ft + ftdot * tau + ftdd * square(tau))
		T = tau * (1 - numpy.exp((-dv/self.exhaustVelocity)))

		if T >= self.epsilon:
			A, B = self.msolve(tau, oldT, self.targetOrbit - self.altitude)
		else:
			A = oldA
			B - oldB

		return (A, B, C, T)


