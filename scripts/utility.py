import krpc
import time
import math
import sys

class FlightData(object):
	def __init__(self, vessel):
		self.initialized = True
		self.vessel = vessel

	def CurrentStageTWR(self, vessel):
		currentThrust = vessel.available_thrust
		g = vessel.orbit.body.surface_gravity
		twr = currentThrust / (vessel.mass*g)
		return twr
