"""Focused checks for the T1 repetition-rate search; no hardware access."""

from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.engine.executor import EngineError
from atomize.epr_auto.primitives.relaxation_timing import maximum_t1_rate


def main():
    source = SimpleNamespace(scans=12, rep_rate='500.0', laser_flag=0,
                             laser_num=0)
    seen = []

    def check_rate(wa, sweep_type, script_test):
        assert sweep_type == 'Log Time' and script_test is True
        assert wa.scans == 1
        seen.append(float(wa.rep_rate))
        if float(wa.rep_rate) > 123.4:
            raise EngineError('worker error:\nAssertionError: Pulse sequence is longer than one period of the repetition rate')

    with patch('atomize.epr_auto.primitives.relaxation_timing.executor.run_worker',
               side_effect=check_rate):
        assert maximum_t1_rate(source) == 123.4
    assert source.scans == 12 and source.rep_rate == '500.0'
    assert len(seen) <= 23

    bounded = SimpleNamespace(**vars(source), log_start=3, log_end=8,
                              points=100, awg_grid=3.2)
    with patch('atomize.epr_auto.primitives.relaxation_timing.executor.run_worker',
               side_effect=check_rate):
        assert maximum_t1_rate(bounded) == 123.4

    laser = SimpleNamespace(scans=1, rep_rate='500.0', laser_flag=1,
                            laser_num=1)
    with patch('atomize.epr_auto.primitives.relaxation_timing.executor.run_worker',
               side_effect=check_rate):
        assert maximum_t1_rate(laser) == 9.9

    def bad_sequence(wa, sweep_type, script_test):
        raise EngineError('worker error:\nPulse overlaps another pulse')

    with patch('atomize.epr_auto.primitives.relaxation_timing.executor.run_worker',
               side_effect=bad_sequence):
        try:
            maximum_t1_rate(source)
        except EngineError as exc:
            assert 'overlaps' in str(exc)
        else:
            raise AssertionError('unrelated preflight failure was hidden')

    from atomize.epr_auto.params import PRESET_DIR
    preset = snapshot.load_preset(PRESET_DIR / 'inversion_recovery_echo_4s_log.phase_awg')
    wa = snapshot.build_worker_args(preset, 'T1 timing check', points=5, scans=1,
                                    log_start=np.log10(500),
                                    log_end=np.log10(5_000_000), rep_rate=100)
    from atomize.device_modules.Insys_FPGA import Insys_FPGA
    original_update = Insys_FPGA.pulser_update
    with TemporaryDirectory() as directory:
        capture = Path(directory) / 'pulse_starts.txt'

        def recording_update(self):
            detection = next(p for p in self.pulse_array_pulser
                             if p['channel'] == 'DETECTION')
            with capture.open('a', encoding='ascii') as output:
                output.write(detection['start'].split(' ')[0] + '\n')
            return original_update(self)

        with patch.object(Insys_FPGA, 'pulser_update', recording_update):
            executor.run_worker(wa, 'Log Time', script_test=True)
        starts = [float(line) for line in capture.read_text().splitlines()]

    first = starts[0]
    measured = [round(start - first, 1) for start in starts]
    actual = [value for index, value in enumerate(measured)
              if index == 0 or value != measured[index - 1]]
    grid = np.unique(wa.awg_grid * np.round(
        10 ** np.linspace(wa.log_start, wa.log_end, wa.points) / wa.awg_grid))
    expected = [round(value - grid[0], 1) for value in grid]
    assert actual == expected, (actual, expected)

    preset.slots[1].typ = 'LASER'
    preset.laser = 'Nd:YaG'
    laser_wa = snapshot.build_worker_args(preset, 'Nd:YAG timing check',
                                          points=5, scans=1,
                                          log_start=np.log10(500),
                                          log_end=np.log10(5_000_000),
                                          rep_rate=500)
    assert laser_wa.rep_rate == '9.9'
    original_rate = Insys_FPGA.pulser_repetition_rate
    with TemporaryDirectory() as directory:
        capture = Path(directory) / 'rates.txt'

        def recording_rate(self, *rate):
            if rate:
                with capture.open('a', encoding='ascii') as output:
                    output.write(rate[0] + '\n')
            return original_rate(self, *rate)

        with patch.object(Insys_FPGA, 'pulser_repetition_rate', recording_rate):
            executor.run_worker(laser_wa, 'Log Time', script_test=True)
        assert capture.read_text().splitlines() == ['9.9 Hz']
    assert maximum_t1_rate(laser_wa) == 9.9

    from atomize.epr_auto.primitives import exp
    from atomize.epr_auto.session import EPRSession
    session = EPRSession('laser-test', 'autonomous', True)
    session.log = lambda message: None
    result, _ = exp.t1(session, preset, '500 ns', '5 ms', points=5, scans=1,
                       rep_rate=500, adjust_range=True)
    assert result['canned'] and result['rep_rate_hz'] == 9.9

    too_long = snapshot.build_worker_args(preset, 'Nd:YAG long range',
                                          points=5, scans=1,
                                          log_start=np.log10(500),
                                          log_end=np.log10(150_000_000),
                                          rep_rate=500)
    try:
        maximum_t1_rate(too_long)
    except ValueError as error:
        assert 'fixed Nd:YAG rate of 9.9 Hz' in str(error)
    else:
        raise AssertionError('range beyond the 9.9 Hz period was accepted')
    print('PASS: rate limits, unrelated failures and actual Log Time pulse positions')


if __name__ == '__main__':
    main()
