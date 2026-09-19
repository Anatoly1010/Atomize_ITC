"""Offline range decisions and acquisition handoff checks; run with `test`."""
import copy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import snapshot
from atomize.epr_auto.params import PRESET_DIR
from atomize.epr_auto.primitives import exp, relaxation_timing, relaxation_series
from atomize.epr_auto.primitives.relaxation_range import decision, plateau
from atomize.epr_auto.protocol import ProtocolError, load_protocol
from atomize.epr_auto.session import EPRSession
from atomize.epr_auto.steps import _run_primitive, StepFailure
from atomize.epr_auto.primitives.judges import JudgeReport


def session():
    value = EPRSession('range-check', 'autonomous', False)
    value.log = lambda message: None
    return value


def analysis_checks():
    x = np.arange(500) * 44.8e-9 + 409.6e-9
    decay = 1000 * np.exp(-x / 1e-6)
    found = plateau(x, decay, 't2')
    assert found['status'] == 'confirmed'
    assert 4e-6 < found['onset_s'] < 7e-6
    assert decision(found, 't2', len(x))['action'] == 'keep'
    assert decision(found, 't2', len(x))['next_action'] == 'resize'
    assert plateau(x, -decay, 't2')['onset_index'] == found['onset_index']
    drifting = 1000 * np.exp(-x / 15e-6)
    assert plateau(x, drifting, 't2')['status'] != 'confirmed'
    assert decision(plateau(x, np.zeros(500), 't2'), 't2', 500)['action'] == 'skip'
    noisy = np.random.default_rng(19).normal(0, 100, len(x))
    assert plateau(x, noisy, 't2')['status'] == 'unusable'
    assert plateau(x[:20], decay[:20], 't2')['status'] == 'unusable'
    invalid = decay.copy()
    invalid[10] = np.nan
    assert plateau(x, invalid, 't2')['status'] == 'unusable'
    assert plateau(x[::-1], decay, 't2')['status'] == 'unusable'
    short = {'status': 'confirmed', 'baseline_points': 100, 'onset_index': 400}
    assert decision(short, 't2', 500)['action'] == 'keep'
    assert decision(short, 't2', 500)['target_points'] > 500
    imprecise = {'status': 'unconfirmed', 'range_insufficient': False, 'reason': 'noise'}
    assert decision(imprecise, 't2', 500)['action'] == 'skip'
    print('PASS: measured plateau, short confirmed baseline, inversion, drifting/flat/noisy/invalid traces')


def run(current, kind, options):
    return _run_primitive(current, getattr(exp, kind), advisory_extra=('echo_snr',), **options)


def t2_checks():
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    original = copy.deepcopy(pre)
    current = session()
    current.state['echo_window'] = {'win_left_ns': 0, 'win_right_ns': 32}
    current.state['temperature'] = {'setpoint': 80, 'reached': True}
    seen = []

    def acquire(s, wa, sweep, tag, **kwargs):
        seen.append(copy.deepcopy(wa))
        assert wa.win_left == int(pre.win_left_ns / (0.4 * pre.decimation))
        assert wa.win_right != int(32 / (0.4 * pre.decimation))
        step = float(wa.rect[0][4].split()[0]) * 1e-9
        x = 409.6e-9 + np.arange(wa.points) * step
        y = 1000 * np.exp(-x / 1e-6)
        return x, y, np.zeros(len(x)), f'{tag}_{len(seen)}.csv'

    options = dict(preset=pre, tau_start='204.8 ns', tau_step='22.4 ns',
                   points=500, scans=1, window='preset', rep_rate=100,
                   adjust_range=True)
    with patch.object(exp, '_acquire', side_effect=acquire):
        first = run(current, 't2', options)
        assert len(seen) == 1 and first['range_adjustment']['status'] == 'keep'
        assert first['data_file'] == 't2_1.csv'
        assert first['range_adjustment']['next_range']['points'] == 376
        assert len(current.state[relaxation_series.STATE_KEY]) == 1
        current.state['temperature'] = {'setpoint': 100, 'reached': True}
        second = run(current, 't2', options)
        assert len(seen) == 2 and seen[1].points == 376
        assert second['range_adjustment']['carried_range']['source_data_file'] == first['data_file']
        current.state['temperature'] = {'setpoint': 80, 'reached': True}
        third = run(current, 't2', options)
        assert len(seen) == 3 and seen[2].points == 376
        assert third['range_adjustment']['carried_range']['cooling_or_unknown_guard']
    assert pre == original
    assert seen[0].rect[0][4] == seen[1].rect[0][4]
    assert seen[0].awg == seen[1].awg

    with patch.object(exp, '_acquire', side_effect=acquire):
        result = run(current, 't2', {**options, 'adjust_range': False})
    assert len(seen) == 4 and seen[-1].points == 500
    assert 'range_adjustment' not in result

    def unfinished(s, wa, sweep, tag, **kwargs):
        seen.append(copy.deepcopy(wa))
        x = 409.6e-9 + np.arange(wa.points) * float(wa.rect[0][4].split()[0]) * 1e-9
        y = 1000 * np.exp(-x / 15e-6)
        kwargs['on_scan_data'](1, y, np.zeros(len(x)))
        return x, y, np.zeros(len(x)), f'{tag}.csv'

    seen.clear()
    with patch.object(exp, '_acquire', side_effect=unfinished), \
            patch.object(exp.time, 'monotonic', side_effect=[0, 2]):
        result, _ = exp.t2(session(), **options, max_duration='1 s')
    assert len(seen) == 1 and result['range_adjustment']['status'] == 'skipped_budget'

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt()

    previous = copy.deepcopy(current.state[relaxation_series.STATE_KEY])
    with patch.object(exp, '_acquire', side_effect=cancel) as acquisition:
        try:
            run(current, 't2', options)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError('Stop was swallowed')
    assert acquisition.call_count == 1
    assert current.state[relaxation_series.STATE_KEY] == previous
    print('PASS: one T2 per temperature; bounded warming shrink, cooling guard, window, budget and Stop')


def t1_checks():
    current = session()
    current.state['temperature'] = {'setpoint': 80, 'reached': True}
    pre = snapshot.load_preset(PRESET_DIR / 'inversion_recovery_echo_4s_log.phase_awg')
    seen = []

    def acquire(s, wa, sweep, tag, **kwargs):
        seen.append(copy.deepcopy(wa))
        grid = exp._log_grid(wa)
        x = (grid - grid[0] + 204.8) * 1e-9
        y = 500 - 1000 * np.exp(-x / .1e-3)
        return x, y, np.zeros(len(x)), f'{tag}_{len(seen)}.csv'

    options = dict(preset=pre, t_start='204.8 ns', t_end='6 ms', points=300,
                   scans=1, rep_rate=100, adjust_range=True)
    with patch.object(exp, '_acquire', side_effect=acquire), \
            patch.object(relaxation_timing, 'maximum_t1_rate', return_value=220.2) as rate:
        first = run(current, 't1', options)
        assert len(seen) == 1 and rate.call_count == 0
        current.state['temperature'] = {'setpoint': 100, 'reached': True}
        second = run(current, 't1', options)
        assert len(seen) == 2 and rate.call_count == 1
        assert seen[0].rep_rate == '100.0' and seen[1].rep_rate == '220.2'
        assert second['rep_rate_hz'] == 220.2
        assert second['range_adjustment']['carried_range']['source_data_file'] == first['data_file']
        assert seen[1].log_end < seen[0].log_end
        span0, span1 = [np.ptp(exp._log_grid(wa)) for wa in seen]
        assert span1 >= .75 * span0

    current.state['temperature'] = {'setpoint': 120, 'reached': True}
    seen.clear()
    with patch.object(exp, '_acquire', side_effect=acquire), \
            patch.object(relaxation_timing, 'maximum_t1_rate',
                         side_effect=ValueError('T1 sequence does not fit the fixed Nd:YAG rate of 9.9 Hz')):
        result = run(current, 't1', options)
    assert len(seen) == 1 and seen[0].points == 300
    assert result['range_adjustment']['carried_range']['status'] == 'skipped_limits'
    seen.clear()

    def still_recovering(s, wa, sweep, tag, **kwargs):
        seen.append(copy.deepcopy(wa))
        grid = exp._log_grid(wa)
        x = (grid - grid[0] + 204.8) * 1e-9
        y = 1000 * (1 - np.exp(-x / .1))
        if kwargs['on_scan_data'] is not None:
            kwargs['on_scan_data'](1, y, np.zeros(len(x)))
        return x, y, np.zeros(len(x)), f'{tag}.csv'

    with patch.object(exp, '_acquire', side_effect=still_recovering), \
            patch.object(relaxation_timing, 'maximum_t1_rate', return_value=80):
        result, _ = exp.t1(session(), **options)
    assert len(seen) == 2
    assert seen[1].log_end > seen[0].log_end
    assert not result['range_adjustment']['plateau_confirmed']
    assert result['range_adjustment']['initial']['data_file'] == 't1.csv'
    assert result['data_file'] == 't1_revised.csv'
    assert float(result['t_end'].split()[0]) < 12.1e6
    print('PASS: carried T1 rate is recalculated; invalid range fallback; unfinished tails extend once only')


def series_checks():
    current = session()
    current.state['temperature'] = {'setpoint': 80, 'reached': True}
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    options = dict(preset=pre, tau_start='204.8 ns', tau_step='22.4 ns',
                   points=500, scans=1, rep_rate=100, adjust_range=True)
    seen = []

    def acquire(s, wa, sweep, tag, **kwargs):
        seen.append(copy.deepcopy(wa))
        x = 409.6e-9 + np.arange(wa.points) * float(wa.rect[0][4].split()[0]) * 1e-9
        return x, 1000 * np.exp(-x / 1e-6), np.zeros(len(x)), f'{tag}_{len(seen)}.csv'

    with patch.object(exp, '_acquire', side_effect=acquire):
        current.state['field'] = '3318 G'
        run(current, 't2', options)
        current.state['temperature']['setpoint'] = 100
        current.state['auto_phase'] = {'zero_order_deg': 25}
        current.state['echo_window'] = {'win_left_ns': 40, 'win_right_ns': 120}
        result = run(current, 't2', options)
        assert seen[-1].points == 376
        assert np.isclose(seen[-1].zero_order, 25 / snapshot.DEG_RAD)
        assert seen[-1].win_left == int(40 / (.4 * pre.decimation))
        assert seen[-1].win_right == int(120 / (.4 * pre.decimation))
        current.state['field'] = '3320 G'
        run(current, 't2', options)
        assert seen[-1].points == 500
        assert len(current.state[relaxation_series.STATE_KEY]) == 2
        current.state['field'] = '3318 G'
        current.state['temperature']['setpoint'] = 120
        run(current, 't2', options)
        assert seen[-1].points < 376
        run(current, 't2', {**options, 'points': 600})
        assert seen[-1].points == 600
        changed = copy.deepcopy(pre)
        changed.slots[1].coef *= .9
        run(current, 't2', {**options, 'preset': changed})
        assert seen[-1].points == 500
        previous = copy.deepcopy(current.state[relaxation_series.STATE_KEY])
        current.state['temperature']['reached'] = False
        run(current, 't2', options)
        assert seen[-1].points == 500
        assert current.state[relaxation_series.STATE_KEY] == previous
        current.state['temperature']['reached'] = True
        current.state['temperature']['setpoint'] = 140
        failed = JudgeReport('relaxation_fit', False, 0, {'reason': 'test rejection'})
        with patch.object(exp, 'relaxation_fit', return_value=failed):
            try:
                run(current, 't2', options)
            except StepFailure:
                pass
            else:
                raise AssertionError('failed fit was accepted')
        assert current.state[relaxation_series.STATE_KEY] == previous
        assert not current._staged_state
        current.test = True
        run(current, 't2', options)
        assert current.state[relaxation_series.STATE_KEY] == previous
        current.test = False
    current.invalidate_phase('temperature')
    assert current.state[relaxation_series.STATE_KEY] == previous
    current.invalidate_fine_calibrations('vane')
    assert relaxation_series.STATE_KEY not in current.state
    print('PASS: field/pulse/seed isolation, fresh phase/window, unsettled temperature, judge gate, dry run and RV')


def grid_checks():
    current = session()
    pre = snapshot.load_preset(PRESET_DIR / 'inversion_recovery_echo_4s_log.phase_awg')
    pre, wa = exp._build(current, pre, 'grid', points=700, scans=1,
                          log_start=np.log10(3.2), log_end=np.log10(5e6))
    grid = exp._log_grid(wa)
    assert len(grid) < wa.points
    x = (grid - grid[0] + 204.8) * 1e-9
    acq = (x, np.zeros(len(x)), np.zeros(len(x)), 'grid.csv')
    plan = {'action': 'resize', 'target_points': len(grid) - 60}
    _, revised = exp._revised_sweep(current, pre, wa, acq, 't1', plan, 4096)
    assert len(exp._log_grid(revised)) == plan['target_points']
    _, limited = exp._revised_sweep(current, pre, wa, acq, 't1', {'action': 'extend'}, 100)
    assert limited.points <= 100
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    exp._retau(pre, 204.8, 22.4)
    pre, wa = exp._build(current, pre, 'grid', points=500, scans=1)
    x = 409.6e-9 + np.arange(500) * 44.8e-9
    acq = (x, np.zeros(len(x)), np.zeros(len(x)), 'grid.csv')
    _, limited = exp._revised_sweep(current, pre, wa, acq, 't2', {'action': 'extend'}, 100)
    assert limited.points == 100
    step = float(limited.rect[0][4].split()[0])
    assert step > 44.8 and np.isclose(step / limited.awg_grid, round(step / limited.awg_grid))
    assert step * (limited.points - 1) >= 2 * 44.8 * 499
    pre.xdelta = 44.8
    try:
        exp._revised_sweep(current, pre, wa, acq, 't2', {'action': 'extend'}, 100)
    except ValueError as error:
        assert 'manual T2 axis' in str(error)
    else:
        raise AssertionError('manual T2 axis was silently rescaled')
    print('PASS: deduplicated log grids, point caps, hardware-rounded T2 step and manual-axis guard')


def schema_checks():
    with tempfile.TemporaryDirectory() as directory:
        protocol = Path(directory) / 'check.yaml'
        protocol.write_text('sample: range-check\nsteps:\n  - exp.t2:\n      points: 100\n')
        params = load_protocol(protocol).steps[0].params
        assert params['adjust_range'] is False and params['adjust_max_points'] == 4096
        protocol.write_text('sample: range-check\nsteps:\n  - exp.t1:\n      points: 100\n'
                            '      adjust_range: true\n      adjust_max_points: 300\n')
        assert load_protocol(protocol).steps[0].params['adjust_range'] is True
        for setting in ['adjust_range: yesplease', 'adjust_max_points: 59']:
            protocol.write_text('sample: range-check\nsteps:\n  - exp.t2:\n      points: 100\n'
                                f'      {setting}\n')
            try:
                load_protocol(protocol)
            except ProtocolError:
                pass
            else:
                raise AssertionError(f'invalid setting accepted: {setting}')
    print('PASS: opt-in schema and invalid values')


def dataset_checks(root):
    expected = {('t2', '80_3318G'): ('keep', None),
                ('t2', '240_3318G'): ('keep', 278),
                ('t1', '80_3318G'): ('extend', None),
                ('t1', '240_3318G_Long'): ('keep', 237)}
    for (kind, name), (action, points) in expected.items():
        data = np.loadtxt(root / kind / f'{name}.csv', delimiter=',')
        y = exp._to_real(data[:, 1] + 1j * data[:, 2])
        measured = plateau(data[:, 0], y, kind)
        plan = decision(measured, kind, len(data))
        assert plan['action'] == action, (name, plan)
        assert plan.get('target_points') == points, (name, plan)
    print('PASS: operator-calibrated 80 K / 240 K real-data decisions')


if __name__ == '__main__':
    analysis_checks()
    t2_checks()
    t1_checks()
    series_checks()
    grid_checks()
    schema_checks()
    if len(sys.argv) > 2:
        dataset_checks(Path(sys.argv[2]))
