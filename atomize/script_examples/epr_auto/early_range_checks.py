"""Exercise early range decisions together with SNR accumulation; no hardware."""
import copy
import sys
from contextlib import nullcontext
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.params import PRESET_DIR
from atomize.epr_auto.primitives import exp, relaxation_timing
from atomize.epr_auto.primitives.judges import JudgeReport
from atomize.epr_auto.session import EPRSession
from atomize.epr_auto.steps import _run_primitive


def exercise(kind, mode, *, budget=None, rejected=False, scans=8, adjust=True, target=10,
             late_budget=False, fail_check=False):
    session = EPRSession('early-range', 'autonomous', False)
    session.log = lambda value: None
    session.state['temperature'] = {'setpoint': 80, 'reached': True}
    preset = ('hahn_echo_4s.phase_awg' if kind == 't2'
              else 'inversion_recovery_echo_4s_log.phase_awg')
    options = dict(preset=PRESET_DIR / preset, points=300, scans=scans,
                   target_snr=target, rep_rate=100, adjust_range=adjust, max_duration=budget)
    if kind == 't2':
        options.update(tau_start='204.8 ns', tau_step='22.4 ns')
    else:
        options.update(t_start='204.8 ns', t_end='6 ms')
    acquired, current = [], {'k': 0}

    def acquire(s, wa, sweep, tag, **kwargs):
        record = {'args': copy.deepcopy(wa), 'tag': tag, 'limits': [], 'completed': 0}
        acquired.append(record)
        if kind == 't2':
            x = 409.6e-9 + np.arange(wa.points) * float(wa.rect[0][4].split()[0]) * 1e-9
            good = 1000 * np.exp(-x / .5e-6)
            short = 1000 * np.exp(-x / 15e-6)
        else:
            grid = exp._log_grid(wa)
            x = (grid - grid[0] + 204.8) * 1e-9
            good = 500 - 1000 * np.exp(-x / .1e-3)
            short = 1000 * (1 - np.exp(-x / .1))
        limit = wa.scans
        for k in range(1, wa.scans + 1):
            current['k'] = k
            initial = len(acquired) == 1
            unfinished = mode in ('short', 'delayed', 'noisy', 'always_short') and initial
            if mode == 'always_short':
                unfinished = True
            y = short if unfinished else good
            if initial and ((mode == 'delayed' and k < 3) or (mode == 'noisy' and k <= 3)):
                y = np.random.default_rng(k).normal(0, 100, len(x))
            callback = kwargs['on_scan_data']
            new_limit = None
            if callback is not None:
                assert wa.scan_data_flag == 1 and wa.scan_data_wait == 1
                new_limit = callback(k, y, np.zeros(len(y)))
            record['limits'].append(new_limit)
            if new_limit is not None:
                limit = min(limit, new_limit)
            record['completed'] = k
            if k >= limit:
                break
        return x, y, np.zeros(len(y)), f'{tag}.csv'

    def snr(sig):
        return JudgeReport('echo_snr', True, 2 * current['k'], {})

    preflight = {'side_effect': ValueError('invalid revised pulse geometry')} if rejected else {'return_value': {'status': 'test-ok'}}
    maximum = {'side_effect': ValueError('fixed Nd:YAG rate of 9.9 Hz does not fit')} if rejected else {'return_value': 80}
    real_plateau, plateau_calls = exp.plateau, []

    def flaky_plateau(*args):
        plateau_calls.append(args)
        if len(plateau_calls) == 1:
            raise KeyError('injected check failure')
        return real_plateau(*args)

    def late_remaining(check):
        return -1.0 if check.report['status'] == 'extend' else 1e6

    with patch.object(exp, '_acquire', side_effect=acquire), \
            (patch.object(exp, 'plateau', flaky_plateau) if fail_check else nullcontext()), \
            (patch.object(exp._EarlyRangeCheck, 'remaining', late_remaining) if late_budget else nullcontext()), \
            patch.object(exp, 'echo_snr', side_effect=snr), \
            patch.object(executor, 'run_worker', **preflight) as check, \
            patch.object(relaxation_timing, 'maximum_t1_rate', **maximum) as rate:
        if budget is not None:
            with patch.object(exp.time, 'monotonic', side_effect=[0] + [2] * 20):
                result = _run_primitive(session, getattr(exp, kind), advisory_extra=('echo_snr',), **options)
        else:
            result = _run_primitive(session, getattr(exp, kind), advisory_extra=('echo_snr',), **options)
    if kind == 't2' and check.call_count:
        assert check.call_args.kwargs['script_test'] is True
    return result, acquired


def main():
    for kind in ('t2', 't1'):
        result, runs = exercise(kind, 'good')
        assert len(runs) == 1 and runs[0]['completed'] == 5
        assert result['range_adjustment']['early_check']['status'] == 'confirmed'
        assert result['range_adjustment']['early_check']['checked_scans'] == 1
        assert result['data_file'] == f'{kind}.csv'
        assert 'next_range' in result['range_adjustment']

        result, runs = exercise(kind, 'short')
        assert [r['completed'] for r in runs] == [1, 5]
        assert result['range_adjustment']['status'] == 'repeated'
        assert result['range_adjustment']['initial']['data_file'] == f'{kind}.csv'
        assert result['data_file'] == f'{kind}_revised.csv'
        assert result['range_adjustment']['plateau_confirmed']
        if kind == 't1':
            assert result['rep_rate_hz'] == 80

        result, runs = exercise(kind, 'delayed')
        assert [r['completed'] for r in runs] == [3, 5]
        assert result['range_adjustment']['early_check']['checked_scans'] == 3
        assert runs[0]['limits'][:2] == [None, None]

        result, runs = exercise(kind, 'delayed', target=2)
        assert [r['completed'] for r in runs] == [3, 1]

        result, runs = exercise(kind, 'noisy')
        assert len(runs) == 1 and runs[0]['completed'] == 5
        assert result['range_adjustment']['early_check']['status'] == 'unresolved'
        assert result['range_adjustment']['status'] == 'kept_unconfirmed'
        assert 'next_range' not in result['range_adjustment']

        result, runs = exercise(kind, 'always_short')
        assert [r['completed'] for r in runs] == [1, 5]
        assert not result['range_adjustment']['plateau_confirmed']

        result, runs = exercise(kind, 'short', rejected=True)
        assert len(runs) == 1 and runs[0]['completed'] == 5
        assert result['range_adjustment']['status'] == 'skipped_limits'

        result, runs = exercise(kind, 'short', budget='1 s')
        assert len(runs) == 1 and runs[0]['completed'] == 5
        assert result['range_adjustment']['status'] == 'skipped_budget'

        result, runs = exercise(kind, 'short', budget='1000 s', late_budget=True)
        assert [r['completed'] for r in runs] == [1, 1] and runs[1]['args'].scans == 1
        assert result['range_adjustment']['status'] == 'repeated'

        result, runs = exercise(kind, 'good', fail_check=True)
        assert len(runs) == 1 and runs[0]['completed'] == 5
        assert result['range_adjustment']['status'] == 'failed'

        result, runs = exercise(kind, 'good', adjust=False)
        assert len(runs) == 1 and runs[0]['completed'] == 5
        assert 'range_adjustment' not in result
        print(f'PASS: {kind} early repair, retained scans, SNR, noisy window, no late/repeated repair, limits, '
              'committed extension and failed check')
    print('ALL PASS')


if __name__ == '__main__':
    main()
