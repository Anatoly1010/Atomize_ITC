"""Offline Worker amplitude-table checks; run with Python and the `test` argument."""
import copy
import sys
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.control_center.awg_phasing_insys import Worker
from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.params import PRESET_DIR
import atomize.general_modules.general_functions as general


class Pipe:
    def __init__(self):
        self.messages = []

    def send(self, value):
        self.messages.append(value)

    def poll(self):
        return False


class FakeFPGA:
    def __init__(self):
        self.pulse_array_awg = []
        self.pulse_array_init_awg = []
        self.pulse_array_pulser = []
        self.rep_rate = None

    def awg_time_resolution(self, value):
        self.grid = value

    def awg_correction_off(self):
        pass

    def awg_amplitude(self, *args):
        pass

    def pulser_pulse(self, **pulse):
        self.pulse_array_pulser.append(pulse)

    def awg_pulse(self, **pulse):
        pulse['amp'] = 100 / float(pulse['amplitude'])
        self.pulse_array_awg.append(pulse)
        self.pulse_array_init_awg = copy.deepcopy(self.pulse_array_awg)

    def pulser_repetition_rate(self, value=None):
        if value is not None:
            self.rep_rate = value
        return self.rep_rate

    def pulser_default_synt(self, value):
        pass

    def digitizer_decimation(self, value):
        pass

    def digitizer_window_points(self):
        return 8

    def pulser_open(self):
        pass

    def digitizer_number_of_averages(self, value):
        pass

    def awg_next_phase(self):
        pass

    def pulser_update(self):
        values = {pulse['name']: round(100 / pulse['amp'], 1)
                  for pulse in self.pulse_array_awg if pulse['name'] in ('P2', 'P4')}
        timing = {pulse['name']: (pulse['delta_start'], pulse['length_increment'])
                  for pulse in self.pulse_array_pulser}
        updates.append((values, timing))

    def digitizer_get_curve(self, *args, **kwargs):
        return None, None, None

    def pulser_shift(self):
        pass

    def awg_pulse_reset(self):
        self.pulse_array_awg = copy.deepcopy(self.pulse_array_init_awg)

    def awg_redefine_amplitude(self, *, name, amplitude):
        redefined.append((list(name), list(amplitude)))
        for pulse_name, value in zip(name, amplitude):
            next(pulse for pulse in self.pulse_array_awg if pulse['name'] == pulse_name)['amp'] = 100 / value

    def pulser_pulse_reset(self):
        pass

    def digitizer_at_exit(self):
        return np.zeros((8, 3)), np.zeros((8, 3))

    def digitizer_window(self):
        return 3.2

    def pulser_close(self):
        pass

    def digitizer_demodulate(self, i, q, *args, **kwargs):
        return np.zeros(i.shape[-1]), np.zeros(i.shape[-1])

    def pulser_pulse_list(self):
        return ''

    def awg_pulse_list(self):
        return ''


class FakeLakeshore:
    def tc_setpoint(self):
        return 4.2

    def tc_temperature(self, channel):
        return 4.2


class FakeField:
    def magnet_field(self, field):
        pass


class FakeBridge:
    def mw_bridge_rotary_vane(self):
        return '60 dB'

    def mw_bridge_att_prm(self):
        return '0 dB'

    def mw_bridge_att2_prm(self):
        return '0 dB'

    def mw_bridge_att2_prd(self):
        return '0 dB'

    def mw_bridge_synthesizer(self):
        return '9500 MHz'


def worker_table_checks():
    global updates, redefined
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    for slot in pre.slots:
        slot.st_inc = slot.len_inc = slot.st_inc2 = 0.0
    wa = snapshot.build_worker_args(pre, exp_name='AmplitudeTableCheck', points=3, scans=2)
    wa.iq_cor = 1
    wa.save2d = 1
    wa.amplitude_sweep = {'axis': [10.0, 30.0, 50.0],
                          'pulses': {'P2': [10.0, 30.0, 50.0],
                                     'P4': [20.0, 60.0, 100.0]}}
    worker = Worker()
    executor._hand_attrs(worker, wa)
    assert worker.amplitude_sweep == wa.amplitude_sweep
    updates = []
    redefined = []

    pipe = Pipe()
    with patch('atomize.device_modules.Insys_FPGA.Insys_FPGA', FakeFPGA), \
            patch('atomize.device_modules.Lakeshore_335.Lakeshore_335', FakeLakeshore), \
            patch('atomize.device_modules.BH_15.BH_15', FakeField), \
            patch('atomize.device_modules.Micran_X_band_MW_bridge_v2.Micran_X_band_MW_bridge_v2', FakeBridge), \
            patch.object(general, 'scans', side_effect=lambda scans: iter((1, 2))):
        worker.exp_amplitude(pipe, *wa.exp_amplitude_args(), script_test=True)
    assert pipe.messages == [('test', '')], pipe.messages
    phases = len(wa.rect[0][3])
    assert len(updates) == 3 * 2 * phases, len(updates)
    pairs = [values for values, _ in updates]
    assert pairs[:phases] == [{'P2': 10.0, 'P4': 20.0}] * phases
    assert pairs[phases:2 * phases] == [{'P2': 30.0, 'P4': 60.0}] * phases
    assert pairs[2 * phases:3 * phases] == [{'P2': 50.0, 'P4': 100.0}] * phases
    assert pairs[3 * phases:] == pairs[:3 * phases]
    assert redefined == [(['P2', 'P4'], [30.0, 60.0]),
                         (['P2', 'P4'], [50.0, 100.0])] * 2
    assert all(all(float(delta.split()[0]) == float(length.split()[0]) == 0
                   for delta, length in timing.values()) for _, timing in updates), updates[0][1]
    print('PASS: Worker table amplitudes, phase ordering, scan repeats and zero timing increments')


worker_table_checks()
