import numpy as np
import time
from Operation import Operations

pi = np.pi

class LaunchManager(Operations):
    def __init__(self, target_orbit, target_inc):
        Operations.__init__(self, target_orbit, target_inc)

        self.vessel_flight_bdy = self.conn.add_stream(self.vessel.flight, self.bdy_reference_frame())
        self.vessel_sur_speed = self.conn.add_stream(getattr, self.vessel_flight_bdy(), 'speed')
        self.latitude = self.conn.add_stream(getattr, self.vessel.flight(), 'latitude')

        self.lAz_data = self.azimuth_init()
        self.Q = self.conn.add_stream(getattr, self.vessel.flight(), 'dynamic_pressure')
        self.pitch = self.conn.add_stream(getattr, self.vessel.flight(), 'pitch')

        self.altitude = self.conn.add_stream(getattr, self.vessel.flight(), 'mean_altitude')
        self.period = self.conn.add_stream(getattr, self.vessel.orbit, 'period')

        self.pitchSet = 90
        self.azimuthSet = 90
        self.pitchRate = 1.6
        self.onInsertionStage = False

        self.liftoffTWR = 1.37
        self.pitchMode = "ASCENT"
        # Calculate spline points for pitch program based on liftoff TWR and target Apogee
        p1 = -30000*self.liftoffTWR + 80000
        p2 = (7/36) * target_orbit + (25000/9)
        self.pitchProgramX = np.array([0,max(p1,p2), target_orbit, target_orbit + 50000])
        self.pitchProgramY = np.array([90,45, 0, 0])
        self.pitchProgram = np.poly1d(np.polyfit(self.pitchProgramX, self.pitchProgramY, 3))

        # -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
        #         S E T   H E A D I N G          #
        # -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#

    def pitch_and_heading(self):

        if self.vessel_sur_speed() < 80: 
            self.pitchMode = "ASCENT"
            self.ap.target_pitch_and_heading(90, 90)
        elif (self.apoapsis_altitude() < (self.target_orbit_alt * .92)) or self.vessel_sur_speed() < 2200:
            p = self.gravity_pitch()
            self.pitchSet = p.item()
            a = self.azimuth(self.lAz_data)
            self.ap.target_pitch_and_heading(p.item(), a.item())
        else:
            if self.onInsertionStage: 
                p = self.insertion_pitch()
                self.pitchSet = p.item()
                a = self.azimuth(self.lAz_data)
                self.ap.target_pitch_and_heading(p.item(), a.item())
            else:
                p = self.gravity_pitch()
                self.pitchSet = p.item()
                a = self.azimuth(self.lAz_data)
                self.ap.target_pitch_and_heading(p.item(), a.item())


    def gravity_pitch(self):
        _t_ap_dv = self.target_apoapsis_speed_dv()
        _speed = self.vessel_sur_speed()

        def pitch_calcs():
            # _pitch = (85 - (1.45 * np.sqrt(_speed))) + (_t_ap_dv / 2)
            # _pitch = (85 - (self.pitchRate * np.sqrt(_speed))) + (_t_ap_dv / 2)
            # _pitch = 90 - 2.5 * pow( (speed - 45), 0.4 )
            return self.pitchProgram(self.altitude())
            return _pitch

        self.pitchMode = "GRAVITY TURN"
        return pitch_calcs()

    def insertion_pitch(self):
        _circ_dv = self.circ_dv()
        _t_ap_dv = self.target_apoapsis_speed_dv()
        _m = np.rad2deg(self.mean_anomaly())
        _burn_time = self.maneuver_burn_time(self.circ_dv())

        def pitch_calcs_low():
                return (_t_ap_dv * (_circ_dv / 1000)) + (_m - (180 - (_burn_time / 12)))

        def pitch_calcs_high():
                return (_t_ap_dv * (_circ_dv / 1000)) + (_m - 180)

        if self.target_orbit_alt <= 250000: 
            self.pitchMode = "INS LOW"
            return pitch_calcs_low()
        else: 
            self.pitchMode = "INS HIGH"
            return pitch_calcs_high()

    def azimuth_init(self):

        _R_eq = self.radius_eq
        _inc = float(self.target_orbit_inc)
        _lat = self.latitude()
        _to = float(self.target_orbit_alt)
        _mu = self.mu
        _Rot_p = self.rotational_period
        node = "Ascending"

        if _inc < 0:
            node = "Descending"
            _inc = np.fabs(_inc)

        if (np.fabs(_lat)) > _inc: _inc = np.fabs(_lat)

        if (180 - np.fabs(_lat)) < _inc: _inc = (180 - np.fabs(_lat))

        velocity_eq = (2 * pi * _R_eq) / _Rot_p
        t_orb_v = np.sqrt(_mu / (_to + _R_eq))

        return _inc, _lat, velocity_eq, t_orb_v, node

    @staticmethod
    def azimuth(_lAz_data):
        _inc = _lAz_data[0]
        _lat = _lAz_data[1]
        velocity_eq = _lAz_data[2]

        def _az_calc():
            inert_az = np.arcsin(max(min(np.cos(np.deg2rad(_inc)) / np.cos(np.deg2rad(_lat)), 1), -1))
            _VXRot = _lAz_data[3] * np.sin(inert_az) - velocity_eq * np.cos(np.deg2rad(_lat))
            _VYRot = _lAz_data[3] * np.cos(inert_az)

            return np.rad2deg(np.fmod(np.arctan2(_VXRot, _VYRot) + 360, 360))
        _az = _az_calc()

        if _lAz_data[4] == "Ascending": return _az

        if _lAz_data[4] == "Descending":
            if _az <= 90: return 180 - _az
            elif _az >= 270: return 540 - _az

    def circ_dv(self):
        _circ_v = self.circular_speed_calc(self.apoapsis_radius(), self.mu)
        _v_ap = self.ap_v_calc(self.apoapsis_radius(), self.periapsis_radius(), self.mu)

        return self.circ_dv_calc(_circ_v, _v_ap)

    def target_apoapsis_speed_dv(self):
        _v_ap = self.ap_v_calc(self.apoapsis_radius(), self.periapsis_radius(), self.mu)

        return self.ap_dv_calc(self.radius_eq, self.periapsis_radius(), self.mu, float(self.target_orbit_alt), _v_ap)

    # noinspection PyAttributeOutsideInit
    def flameout(self, _mode):
        if self.eng_status(self.get_active_engine(), "Status") == "Flame-Out!":
            self.control.activate_next_stage()
            time.sleep(1.5)
            self.mode = _mode

    @staticmethod
    def twr_calc(_thrust, _mass, _alt, _r_eq, _mu):

        _twr = (_thrust / ((_mu / ((_alt + _r_eq) ** 2)) * _mass))
        return _twr

    @staticmethod
    def circ_dv_calc(_circ_v, _v_ap):
        _circ_dv_calc = _circ_v - _v_ap
        return _circ_dv_calc

    @staticmethod
    def ap_v_calc(_R_ap, _R_pe, _mu):
        _v_ap = np.sqrt((2 * _mu * _R_pe) / (_R_ap * (_R_ap + _R_pe)))
        return _v_ap

    @staticmethod
    def ap_dv_calc(_R_eq, _R_pe, _mu, _to, _v_ap):
        _t_radius = _to + _R_eq
        _t_ap_v = np.sqrt((2 * _mu * _R_pe) / (_t_radius * (_t_radius + _R_pe)))
        _t_ap_dv = _v_ap - _t_ap_v
        return _t_ap_dv

    @staticmethod
    def orbital_period(a, mu):
        t = 2 * pi * np.sqrt(a * a * a / mu)
        return t
