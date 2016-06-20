import orbitalMechanics
import numpy

class Avionics(object):
	def __init__(self):
		pass

	def requiredCircularOrbitalSpeed(self, mu, radius):
		return numpy.sqrt(mu/radius)

	def requiredOribitalSpeed(self, mu, radius, semiMajorAxis):
		return orbitalMechanics.visVisa(mu, radius, semiMajorAxis)

class AvionicsSolver(object):
	def __init__(self, vessel, connection, active = True):
		self.active = active
		self.vessel = vessel
		self.connection = connection
		if active:
			self.AddStreams()

	def AddStreams(self):
		self.mu = connection.add_stream(getattr, self.vessel.body.body, 'gravitational_parameter')
		self.radius = connection.add_stream(getattr, self.vessel.orbit, 'radius')
		self.semiMajorAxis = connection.add_stream(getattr, self.vessel.orbit, 'semi_major_axis')


	def RemoveStreams(self):
		self.mu.remove()
		self.radius.remove()
		self.semiMajorAxis.remove()

	def SetActive(self, active = True):
		self.active = active
		if active:
			self.AddStreams()
		else:
			self.RemoveStreams()

	def OrbitalSpeed(radius = None, semiMajorAxis = None):
		if not radius:
			radius = self.radius()
		if not semiMajorAxis:
			semiMajorAxis = self.semiMajorAxis()

		return orbitalMechanics.visVisa(self.mu(), radius, semiMajorAxis)

