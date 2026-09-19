"""Offline repetition-rate and preliminary handoff checks; run with Python and `test`."""
import copy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import snapshot
from atomize.epr_auto.params import PRESET_DIR
from atomize.epr_auto.primitives import preliminary, tune
from atomize.epr_auto.protocol import load_protocol
from atomize.epr_auto.session import EPRSession
from atomize.epr_auto.steps import StepFailure, _run_primitive


PRESET = PRESET_DIR / 'hahn_echo_4s.phase_awg'


def resolve_checks():
    session = EPRSession('check', 'autonomous', True)
    session.log = lambda message: None
    pre = SimpleNamespace(rep_rate=500.0)
    try:
        preliminary._repetition_rate(session, pre, 'auto')
    except ValueError as error:
        assert 'run tune.rep_rate first' in str(error)
    else:
        raise AssertionError('missing recommendation accepted')
    session.state['preliminary_echo'] = {'rep_rate': 250.0}
    preliminary._repetition_rate(session, pre, None)
    assert pre.rep_rate == 250.0
    session.state['rep_rate'] = {'rep_rate_hz': 166.7, 't1_eff_s': .0012,
                                 'mode': 'quantitative'}
    preliminary._repetition_rate(session, pre, 'auto')
    assert pre.rep_rate == 166.7
    for rate in (10000.1, float('inf'), float('nan'), .09):
        session.state['rep_rate']['rep_rate_hz'] = rate
        try:
            preliminary._repetition_rate(session, pre, 'auto')
        except ValueError as error:
            assert '0.1–10000' in str(error)
        else:
            raise AssertionError(f'invalid recommendation {rate} accepted')
    assert pre.rep_rate == 166.7
    session.invalidate_rep_rate('temperature changed')
    try:
        tune._resolve_rep_rate(session, 'auto')
    except ValueError:
        pass
    else:
        raise AssertionError('invalidated recommendation reused')
    print('PASS: auto resolution, inheritance, missing/stale results and preliminary rate bounds')


def procedure_checks(directory):
    rates = np.geomspace(10, 2000, 6)

    def run(amplitudes, **kwargs):
        session = EPRSession('check', 'autonomous', False, output=directory)
        session.log = lambda message: None
        selected = snapshot.load_preset(PRESET)
        selected.slots[1].length = selected.slots[2].length = 64.0
        selected.slots[1].coef, selected.slots[2].coef = 20, 40
        session.state['_preliminary_preset'] = selected
        session.state['temperature'] = {'reached': True, 'setpoint': 295.0}
        original = copy.deepcopy(selected)
        seen = []

        def acquire(current, wa, grid, points, scans, max_wait):
            assert wa.awg[0][3] == wa.awg[1][3] == '64.0 ns'
            assert (wa.awg[0][6], wa.awg[1][6]) == (20, 40)
            assert all(r[4] == r[5] == '0.0 ns' for r in wa.rect[:1])
            assert all(r[2] == r[3] == '0.0 ns' for r in wa.rect[1:])
            seen.extend(grid)
            return [np.full(points * scans, amp * np.exp(.7j))
                    for amp in amplitudes], 'synthetic_live.csv'

        with patch.object(tune, '_acquire_live_rates', side_effect=acquire):
            try:
                result = _run_primitive(session, tune.rep_rate, preset=PRESET, **kwargs)
            except StepFailure:
                assert 'rep_rate' not in session.state and not session._staged_state
                result = None
        assert selected == original
        assert np.allclose(seen, np.geomspace(kwargs.get('rate_min', 10),
                                              kwargs.get('rate_max', 2000), 6))
        return result, session

    recovery = 1 - np.exp(-1 / rates / .002)
    quantitative, session = run(recovery)
    assert np.isclose(quantitative['t1_eff_s'], .002, rtol=.001)
    assert quantitative['rep_rate_hz'] == 100.0
    sensitivity, _ = run(recovery, mode='sensitivity')
    assert np.isclose(sensitivity['rep_rate_hz'], 1 / (1.26 * .002), rtol=.001)
    flat, _ = run(np.ones(6), rate_max=1999.99)
    assert flat['t1_eff_s'] is None and flat['rep_rate_hz'] == 1999.99
    assert run(1 - np.exp(-1 / rates / .1))[0] is None
    assert run(np.zeros(6))[0] is None
    assert run(np.array([1.0, 1.04, .98, 1.03, .96, 1.01]))[0] is None
    slower_recommendation, _ = run(1 - np.exp(-1 / rates / .025))
    assert np.isclose(slower_recommendation['rep_rate_hz'], 8), slower_recommendation
    with patch.object(tune, '_acquire_live_rates') as acquire:
        for lower, upper in ((9.9, 2000), (10, 9.9), (10, float('inf'))):
            try:
                tune.rep_rate(session, PRESET, rate_min=lower, rate_max=upper)
            except ValueError as error:
                assert '10–100000 Hz' in str(error)
            else:
                raise AssertionError('out-of-range tuning grid accepted')
        acquire.assert_not_called()
    try:
        tune._recommend_rate(5, 5, 'quantitative', 2000, session.log)
    except ValueError as error:
        assert 'minimum of 0.1 Hz' in str(error)
    else:
        raise AssertionError('unattainable recommendation accepted')
    assert tune._recommend_rate(1 / (5 * 999.99), 5, 'quantitative', 999.99,
                                session.log) <= 999.99
    print('PASS: quantitative/sensitivity fits, flat/noisy/saturated/zero curves and attainable rates')
    print('PASS: every rate uses the selected preliminary pulses without changing the stored preset')


def journal_checks(directory):
    session = EPRSession('journal', 'autonomous', False, output=directory)
    session.log = lambda message: None
    session.ensure_hardware_locks = lambda: None
    wa = snapshot.build_worker_args(snapshot.load_preset(PRESET), exp_name='Journal')
    calls = []

    def acquire(wa, rates, points, scans, max_wait, **kwargs):
        calls.append(kwargs.get('script_test', False))
        if kwargs.get('script_test'):
            return {'status': 'test-ok'}
        kwargs['on_curve']({'rate_index': 0, 'rate_hz': 20., 'elapsed_s': 1.,
                            'buffer': 1, 'i': 1., 'q': 0., 'valid': True, 'spread': None})
        raise tune.executor.EngineError('did not stabilize')

    with patch.object(tune.executor, 'acquire_live_rates', side_effect=acquire):
        try:
            tune._acquire_live_rates(session, wa, [20, 2000], 3, 1, 120)
        except tune.executor.EngineError:
            pass
        else:
            raise AssertionError('failed live acquisition accepted')
    assert calls == [True, False]
    path = next(session.run_dir.glob('*_rep_rate_live.csv'))
    assert len(path.read_text().splitlines()) == 2
    assert 'rep_rate' not in session.state
    print('PASS: partial live observations survive a failed acquisition without a recommendation')


def handoff_checks(directory):
    session = EPRSession('check', 'autonomous', False, output=directory)
    session.log = lambda message: None
    selected = snapshot.load_preset(PRESET)
    selected.rep_rate = 166.7
    session.state.update({
        '_preliminary_preset': selected, 'preliminary_optimum': {'field_g': selected.field},
        'preliminary_echo': {'sweep': {'fields_g': [3400, 3500]}},
        'echo_window': {'win_left_ns': 200, 'win_right_ns': 400},
        'bridge': {'attenuation_db': 10, 'frequency_mhz': 9440},
    })
    with patch.object(preliminary.executor, 'run_worker'):
        result, _ = preliminary.save_presets(
            session, PRESET, PRESET_DIR / 'ampl_4s.phase_awg',
            PRESET_DIR / 'ed_4s.phase_awg', publish_dir=Path(directory) / 'tuned')
    assert len(result['presets']) == 4
    assert all(snapshot.load_preset(path).rep_rate == 166.7 for path in result['presets'])
    protocol = Path(directory) / 'order.yaml'
    protocol.write_text('sample: check\nsteps:\n  - tune.maximize_echo:\n      rep_rate: auto\n')
    assert any('no earlier tune.rep_rate' in warning for warning in load_protocol(protocol).warnings)
    protocol.write_text('sample: check\nsteps:\n  - tune.rep_rate\n'
                        '  - tune.maximize_echo:\n      rep_rate: auto\n')
    assert not any('no earlier tune.rep_rate' in warning for warning in load_protocol(protocol).warnings)
    print('PASS: all four written/reloaded handoff presets retain the rate; ordering warns before a run')


if __name__ == '__main__':
    resolve_checks()
    with tempfile.TemporaryDirectory() as directory:
        procedure_checks(directory)
        handoff_checks(directory)
        journal_checks(directory)
