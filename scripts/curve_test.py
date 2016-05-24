import time

turn_start_altitude = 500.0
turn_end_altitude = 150000.0
altitude = 0.0
shape = turn_start_altitude + 500
while altitude < turn_end_altitude:
	altitude += 100
	if altitude > turn_start_altitude and altitude < turn_end_altitude:
		p1 = [0, turn_start_altitude]
		p2 = [shape, turn_start_altitude]
		p3 = [turn_end_altitude, turn_start_altitude]
		p4 = [turn_end_altitude, 0]
		frac = (altitude - turn_start_altitude) / (turn_end_altitude - turn_start_altitude)
		y = p1[1] * ((1-frac)*(1-frac)*(1-frac)) + p2[1] * 3 * ((1-frac)*(1-frac)) + p3[1] * 3 * (1-frac) * (frac*frac) + p4[1]
		print "Fraction:", frac
		print "Y:", y
	time.sleep(5)

