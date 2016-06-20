import numpy
import math

def visVisa(mu, radius, semiMajorAxis):
	return math.sqrt( mu*(2.0/radius - 1.0/semiMajorAxis) )
