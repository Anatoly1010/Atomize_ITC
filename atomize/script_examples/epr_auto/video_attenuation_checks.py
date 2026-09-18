"""Offline receiver video-attenuation checks; run with Python and `test`."""
import copy
import math
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.engine import executor
from atomize.epr_auto.engine import snapshot
from atomize.epr_auto.params import PRESET_DIR
from atomize.epr_auto.primitives import preliminary as p
from atomize.epr_auto.session import EPRSession


class NoBridgeAccess:
    def __getattr__(self, name):
        raise AssertionError(f'test mode accessed bridge method {name}')


class Bridge:
    def __init__(self, video1=0, video2=0):
        self.video1, self.video2 = video1, video2
        self.writes = []

    def mw_bridge_att_prm(self, value=None):
        if value is not None:
            self.video1 = value
            self.writes.append(('video1_db', value))
        return f'VA1: {self.video1} dB'

    def mw_bridge_att2_prm(self, value=None):
        if value is not None:
            self.video2 = value
            self.writes.append(('video2_db', value))
        return f'VA2: {self.video2} dB'


def session(video1=0, video2=0, enabled=True):
    return SimpleNamespace(test=True, mw_bridge=NoBridgeAccess(),
                           state={'bridge': {'video1_db': video1, 'video2_db': video2},
                                  '_adjust_video': enabled}, log=lambda message: None)


def receiver_level(peak_mv, limit_mv=200, point_index=None):
    details = {'peak_mv': peak_mv, 'limit_mv': limit_mv}
    if point_index is not None:
        details['point_index'] = point_index
    return executor.ReceiverLevelExceeded(details)


def policy_checks():
    current = session(2, 1)
    assert p._video_settings(current) == {'video1_db': 2, 'video2_db': 1}
    assert p._video_policy(current, False) is False
    assert p._video_policy(current, None) is False
    assert p._video_policy(current, True) is True
    print('PASS: test-mode video policy uses session state without bridge access')


def raise_checks():
    exact = session()
    before = copy.deepcopy(exact.state)
    try:
        p._raise_video(exact, 200)
    except ValueError:
        pass
    else:
        raise AssertionError('exactly 200 mV requested video attenuation')
    assert exact.state == before

    two_db = session()
    p._raise_video(two_db, 200 * 10 ** (2.001 / 20))
    assert two_db.state['bridge'] == {'video1_db': 4.0, 'video2_db': 0}

    half_db = session(30, 0)
    p._raise_video(half_db, 200 * 10 ** (0.501 / 20))
    assert half_db.state['bridge'] == {'video1_db': 30, 'video2_db': 1.0}

    exhausted = session(30, 31.5)
    try:
        p._raise_video(exhausted, 201)
    except ValueError as error:
        assert 'exhausted' in str(error)
    else:
        raise AssertionError('exhausted video attenuation was accepted')
    print('PASS: receiver excess rounds upward on VA1 then VA2 and stops at the limit')


def trace_checks():
    pre = SimpleNamespace(field=3445.0,
                          slots=[SimpleNamespace(length=100.0, st_inc=0.0, len_inc=0.0)])
    fingerprint = (pre.field, [(slot.length, slot.st_inc, slot.len_inc) for slot in pre.slots])
    repeated = session()
    calls = []

    def trace(current, candidate, tag, limit_mv=None):
        calls.append((current, candidate, tag, limit_mv))
        if len(calls) == 1:
            raise receiver_level(201)
        return ('time', 'i', 'q', 'path')

    with patch.object(p, '_trace', side_effect=trace):
        assert p._receiver_trace(repeated, pre, 'video', limit_mv=200) == ('time', 'i', 'q', 'path')
    assert len(calls) == 2
    assert all(call[1] is pre and call[2:] == ('video', 200) for call in calls)
    assert (pre.field, [(slot.length, slot.st_inc, slot.len_inc) for slot in pre.slots]) == fingerprint
    assert repeated.state['bridge'] == {'video1_db': 2.0, 'video2_db': 0}

    disabled = session(enabled=False)
    with patch.object(p, '_trace', return_value=('time', 'i', 'q', 'path')) as trace_mock:
        p._receiver_trace(disabled, pre, 'disabled')
    trace_mock.assert_called_once_with(disabled, pre, 'disabled')
    assert disabled.state['bridge'] == {'video1_db': 0, 'video2_db': 0}
    print('PASS: excess remeasures unchanged excitation; disabled mode skips receiver guard')


def final_step_checks():
    staged = []
    disabled = SimpleNamespace(test=False, state={'_adjust_video': False},
                               stage_state=lambda key, value: staged.append((key, value)))
    result, judges = p.video_attenuation(disabled, 'unused', adjust_video=False)
    assert not judges and result == {'adjust_video': False, 'skipped': True}
    assert staged == [('video_attenuation', result)]

    slots = [SimpleNamespace(length=64.0, st_inc=1.0, len_inc=2.0, st_inc2=3.0)]
    pre = SimpleNamespace(field=3445.0, slots=slots)
    before = (pre.field, [slot.length for slot in pre.slots])
    bridge = Bridge(video1=4, video2=1)
    writes, traces, stage = bridge.writes, [], []
    live = SimpleNamespace(test=False, mw_bridge=bridge,
                           state={'bridge': {'video1_db': 4, 'video2_db': 1}},
                           log=lambda message: None,
                           stage_state=lambda key, value: stage.append((key, value)))
    trace = (np.array([0.0, 1.0, 2.0]), np.array([100.0, 0.0, 0.0]),
             np.zeros(3), 'trace.csv')

    def receiver(current, candidate, tag, limit_mv):
        traces.append((current, candidate, tag, limit_mv))
        return trace

    with patch.object(p, '_claim'), patch.object(p.time, 'sleep'), \
            patch.object(p.tune, 'load_tuned_preset', return_value=pre), \
            patch.object(p, '_sine_preset', return_value=pre), \
            patch.object(p.snapshot, 'build_worker_args', return_value=object()), \
            patch.object(p, 'protection_trace_start_ns', return_value=0.0), \
            patch.object(p, '_receiver_trace', side_effect=receiver):
        result, judges = p.video_attenuation(live, 'final.phase_awg')
    assert not judges and result['video1_db'] == result['video2_db'] == 0
    assert writes == [('video2_db', 0.5), ('video2_db', 0.0),
                      ('video1_db', 2), ('video1_db', 0)]
    assert len(traces) == 5 and all(call[1] is pre for call in traces)
    assert traces[0][2:] == ('video_check', 200)
    assert all(call[2:] == ('video_open_check', 200) for call in traces[1:])
    assert pre.field == before[0] and [slot.length for slot in pre.slots] == before[1]
    assert all((slot.st_inc, slot.len_inc, slot.st_inc2) == (0.0, 0.0, 0.0)
               for slot in pre.slots)
    assert stage == [('video_attenuation', result)]

    protected = Bridge(video1=4, video2=1)
    guarded = SimpleNamespace(test=False, mw_bridge=protected,
                              state={'bridge': {'video1_db': 4, 'video2_db': 1}},
                              log=lambda message: None, stage_state=lambda key, value: None)
    high_trace = (np.array([0.0, 1.0, 2.0]), np.array([195.0, 0.0, 0.0]),
                  np.zeros(3), 'trace.csv')
    with patch.object(p, '_claim'), patch.object(p.time, 'sleep'), \
            patch.object(p.tune, 'load_tuned_preset', return_value=pre), \
            patch.object(p, '_sine_preset', return_value=pre), \
            patch.object(p.snapshot, 'build_worker_args', return_value=object()), \
            patch.object(p, 'protection_trace_start_ns', return_value=0.0), \
            patch.object(p, '_receiver_trace', return_value=high_trace):
        p.video_attenuation(guarded, 'final.phase_awg')
    assert protected.writes == []
    print('PASS: final video step skips when disabled and opens VA2 then VA1 only below the limit')


def inheritance_and_handoff_checks():
    pre = SimpleNamespace(rep_rate=500.0)
    inherited = SimpleNamespace(state={'preliminary_echo': {'rep_rate': 250.0}})
    p._repetition_rate(inherited, pre, None)
    assert pre.rep_rate == 250.0
    p._repetition_rate(inherited, pre, 1000.0)
    assert pre.rep_rate == 1000.0

    exported = SimpleNamespace(test=True, sample='check', log=lambda message: None,
                               state={
                                   'preliminary_optimum': {'field_g': 3445.0},
                                   'preliminary_echo': {'sweep': {'fields_g': [3400.0, 3500.0]}},
                                   'echo_window': {'win_left_ns': 200.0, 'win_right_ns': 400.0},
                                   'bridge': {'frequency_mhz': 9440, 'video1_db': 2.0, 'video2_db': 1.5},
                                   '_adjust_video': True,
                               })
    tuned = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    with patch.object(p.tune, 'load_tuned_preset', return_value=tuned), \
            patch.object(p.executor, 'run_worker'):
        result, judges = p.save_presets(
            exported, str(PRESET_DIR / 'hahn_echo_4s.phase_awg'),
            str(PRESET_DIR / 'ampl_4s.phase_awg'), str(PRESET_DIR / 'ed_4s.phase_awg'))
    assert not judges
    steps = result['protocol']['steps']
    assert steps[0]['bridge.set']['video1_db'] == 2.0
    assert steps[0]['bridge.set']['video2_db'] == 1.5
    assert steps[-1] == {'tune.video_attenuation': {'preset': 'echo_cal.phase_awg',
                                                     'adjust_video': True}}
    print('PASS: repetition rate inherits and the handoff restores VA before its final check')


def approach_ladder_checks():
    pre = SimpleNamespace(field=0.0, scans=4, rep_rate=500.0,
                          slots=[SimpleNamespace(length=640.0), SimpleNamespace(length=32.0)])
    stages, moves, traces = [], [], []
    approaching = SimpleNamespace(
        test=True, mw_bridge=NoBridgeAccess(), log=lambda message: None,
        state={'ringing_check': {'min_attenuation_db': 0},
               'resonator': {'synthesizer_mhz': 9440},
               'bridge': {'video1_db': 0, 'video2_db': 0}},
        stage_state=lambda key, value: stages.append((key, value)),
    )

    def bridge(current, attenuation_db=None, frequency_mhz=None, **video):
        moves.append((attenuation_db, frequency_mhz, video))

    def receiver(current, candidate, tag, limit_mv=200, restart=False):
        traces.append((candidate, tag, limit_mv, restart))
        return np.arange(3.0), np.ones(3), np.zeros(3), None

    with patch.object(p, '_echo_preset', return_value=pre), \
            patch.object(p, '_home'), patch.object(p, 'bridge_set', side_effect=bridge), \
            patch.object(p, '_receiver_trace', side_effect=receiver), \
            patch.object(p, '_sweep', return_value=(3445.0, {'fields_g': [3400.0, 3500.0]})), \
            patch.object(p, '_window', return_value={'win_left_ns': 200.0, 'win_right_ns': 400.0}), \
            patch.object(p, '_remember_preset'), patch.object(p, '_detection_if_mhz', return_value=50):
        result, judges = p.find_echo(approaching, 'final.phase_awg', '3445 G', '100 G',
                                     attenuation_db=12)
    assert not judges and result['adjust_video'] is True
    assert [row['attenuation_db'] for row in result['rv_approach']] == [60, 40, 20, 15, 12]
    assert [move[0] for move in moves if move[0] is not None] == [40.0, 20.0, 15.0, 12.0]
    assert all(not move[2] for move in moves)
    assert [trace[1] for trace in traces] == ['rv_approach'] * 5 + ['echo_confirm']
    print('PASS: test-mode echo approach follows the fixed RV ladder without VA bridge calls')


def maximize_video_restart_checks():
    for failure in ('fine', 'field'):
        session = EPRSession('check', 'autonomous', False)
        session.log = lambda message: None
        session.state.update({
            '_adjust_video': True,
            'bridge': {'video1_db': 0, 'video2_db': 0},
            'echo_window': {'win_left_ns': 0.0, 'win_right_ns': 99.0},
            'ringing_check': {'if_mhz': 50, 'min_attenuation_db': 0,
                              'ampl_1': 260, 'ampl_2': 260},
            'preliminary_echo': {'attenuation_db': 8.0},
        })
        generation, batches, fields, confirmations = [0], [], [], []
        time = np.arange(100.0)
        envelope = np.exp(-0.5 * ((time - 50.0) / 12.0) ** 2)

        def amplitude_batch(current, candidate, amplitudes, p2, pi, tag):
            axis = np.asarray(amplitudes, dtype=float)
            batches.append((generation[0], tag, axis.copy()))
            if failure == 'fine' and generation[0] == 0 and tag == 'amplitude_fine':
                generation[0] = 1
                current.state['bridge']['video2_db'] = 0.5
                raise p._VideoChanged
            signal = np.maximum(0.0, 100.0 - (axis - 30.0) ** 2)
            return time, np.outer(signal, envelope), np.zeros((len(axis), len(time))), [
                f'{tag}.csv', f'{tag}_2d.csv', f'{tag}_2d_1.csv']

        def field_sweep(current, candidate, axis, window, tag):
            fields.append(generation[0])
            if failure == 'field' and generation[0] == 0:
                generation[0] = 1
                current.state['bridge']['video2_db'] = 0.5
                raise p._VideoChanged
            return float(np.median(axis)), {'fields_g': axis.tolist()}

        def confirmation(current, candidate, tag, limit_mv=200, restart=False):
            confirmations.append((generation[0], candidate.slots[1].coef, candidate.slots[2].coef,
                                  tag, restart))
            return time, 100.0 * envelope, np.zeros_like(time), None

        with patch.object(p, '_video_policy', return_value=True), \
                patch.object(p, '_video_settings', return_value={'video1_db': 0, 'video2_db': 0.5}), \
                patch.object(p, 'bridge_set'), patch.object(p, '_amplitude_sweep', side_effect=amplitude_batch), \
                patch.object(p, '_sweep', side_effect=field_sweep), \
                patch.object(p, '_receiver_trace', side_effect=confirmation), \
                patch.object(p, '_window', return_value={'win_left_ns': 0.0, 'win_right_ns': 99.0}), \
                patch.object(p, '_remember_preset'):
            result, judges = p.maximize_echo(
                session, str(PRESET_DIR / 'hahn_echo_4s.phase_awg'),
                pulse_map={'P2': 'pi2', 'P3': 'pi'})
        assert not judges and result['pi2_amplitude'] == 30.0 and result['pi_amplitude'] == 60.0
        assert [(generation, tag) for generation, tag, _ in batches] == [
            (0, 'amplitude_coarse'), (0, 'amplitude_fine'),
            (1, 'amplitude_coarse'), (1, 'amplitude_fine'),
        ]
        assert all(trial['data_file'].startswith('amplitude_') for trial in result['amplitude_trials'])
        assert len(result['amplitude_trials']) == 18
        assert fields == ([0, 1] if failure == 'field' else [1])
        assert confirmations == [(1, 30.0, 60.0, 'optimized_echo_confirm', True)]
    print('PASS: video changes discard prior amplitude caches and reconfirm the new VA optimum')


def receiver_point_confirmation_checks():
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    session = SimpleNamespace(test=False, state={'_adjust_video': False}, log=lambda message: None,
                              save_path=lambda tag: f'/tmp/{tag}.csv',
                              ensure_hardware_locks=lambda: None)
    received = []

    def run_worker(*args, **kwargs):
        if kwargs.get('save_path'):
            raise receiver_level(250, point_index=1)

    with patch.object(p, '_covered'), patch.object(p.executor, 'run_worker', side_effect=run_worker), \
            patch.object(p, '_raise_video'), patch.object(p, '_receiver_trace', side_effect=lambda current, candidate, tag: received.append((candidate.slots[1].coef, candidate.slots[2].coef, tag))):
        try:
            p._amplitude_sweep(session, pre, [10.0, 20.0, 30.0], 1, 2, 'amplitude')
        except p._VideoChanged:
            pass
        else:
            raise AssertionError('amplitude receiver limit did not restart')
    assert received == [(20.0, 40.0, 'amplitude_video_confirm')]

    received.clear()
    fields = np.array([3440.0, 3445.0, 3450.0])
    with patch.object(p.executor, 'run_worker', side_effect=run_worker), \
            patch.object(p, '_raise_video'), patch.object(p, '_receiver_trace', side_effect=lambda current, candidate, tag: received.append((candidate.field, tag))):
        try:
            p._sweep(session, pre, fields, None, 'field')
        except p._VideoChanged:
            pass
        else:
            raise AssertionError('field receiver limit did not restart')
    assert received == [(3445.0, 'field_video_confirm')]
    print('PASS: amplitude and field receiver limits confirm the exact stopped point')


policy_checks()
raise_checks()
trace_checks()
final_step_checks()
inheritance_and_handoff_checks()
approach_ladder_checks()
maximize_video_restart_checks()
receiver_point_confirmation_checks()
print('ALL PASS')
