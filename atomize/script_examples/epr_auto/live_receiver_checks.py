"""Offline live-receiver frame-handshake checks; run with Python and `test`."""
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

import atomize.general_modules.general_functions as general
from atomize.epr_auto.engine import live_receiver as live
from atomize.epr_auto.primitives import preliminary as p


class ChildConnection:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def send(self, value):
        self.sent.append(value)

    def recv(self):
        return self.replies.pop(0)


class PreviewWorker:
    def __init__(self):
        self.args = None

    def dig_on(self, pipe, *args):
        self.args = args
        time = np.array([0.0, 1.0, 2.0])
        for _ in range(2):
            general.plot_1d('live', time, (np.ones(3), np.zeros(3)))
        pipe.send(('Count', '[1 1]'))


class PartialPreviewWorker(PreviewWorker):
    def dig_on(self, pipe, *args):
        self.args = args
        time = np.array([0.0, 1.0, 2.0])
        for _ in range(2):
            general.plot_1d('live', time, (np.array([np.nan, 0.0, 0.0]), np.zeros(3)))
        pipe.send(('Count', '[1 1]'))
        for _ in range(2):
            general.plot_1d('live', time, (np.ones(3), np.zeros(3)))
        pipe.send(('Count', '[1 1]'))


class StalePreviewWorker(PreviewWorker):
    def dig_on(self, pipe, *args):
        self.args = args
        time = np.array([0.0, 1.0, 2.0])
        for _ in range(2):
            general.plot_1d('live', time, (np.ones(3), np.zeros(3)))
        for _ in range(2):
            general.plot_1d('live', time, (np.array([np.nan, 0.0, 0.0]), np.zeros(3)))
        pipe.send(('Count', '[1 1]'))


class IncompletePreviewWorker(PreviewWorker):
    def dig_on(self, pipe, *args):
        self.args = args
        time = np.array([0.0, 1.0, 2.0])
        for _ in range(2):
            general.plot_1d('live', time, (np.ones(3), np.zeros(3)))
        pipe.send(('Count', '[1 0]'))


class ParentConnection:
    def __init__(self, events):
        self.events = list(events)
        self.commands = []
        self.closed = False

    def poll(self, timeout):
        return bool(self.events)

    def recv(self):
        return self.events.pop(0)

    def send(self, value):
        self.commands.append(value)

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, target, args):
        self.target, self.args = target, args
        self.started = False

    def start(self):
        self.started = True

    def is_alive(self):
        return True


def child_handshake_checks():
    worker = PreviewWorker()
    conn = ChildConnection(['continue'])
    original = general.plot_1d
    try:
        live._live_child(worker, conn, ('worker-args',), phases=2)
    finally:
        general.plot_1d = original
    count, trace, end = conn.sent
    assert count == ('Count', '[1 1]') and trace[0] == 'LiveTrace' and end == ('LiveEnd', '')
    assert np.array_equal(trace[1][0], np.array([0.0, 1.0, 2.0]))
    assert worker.args == ('worker-args', False)
    partial = PartialPreviewWorker()
    partial_conn = ChildConnection(['continue'])
    original = general.plot_1d
    try:
        live._live_child(partial, partial_conn, ('worker-args',), phases=2)
    finally:
        general.plot_1d = original
    assert [kind for kind, _ in partial_conn.sent] == ['Count', 'Count', 'LiveTrace', 'LiveEnd']
    stale = StalePreviewWorker()
    stale_conn = ChildConnection([])
    original = general.plot_1d
    try:
        live._live_child(stale, stale_conn, ('worker-args',), phases=2)
    finally:
        general.plot_1d = original
    assert [kind for kind, _ in stale_conn.sent] == ['Count', 'LiveEnd']
    incomplete = IncompletePreviewWorker()
    incomplete_conn = ChildConnection([])
    original = general.plot_1d
    try:
        live._live_child(incomplete, incomplete_conn, ('worker-args',), phases=2)
    finally:
        general.plot_1d = original
    assert [kind for kind, _ in incomplete_conn.sent] == ['Count', 'LiveEnd']
    print('PASS: child advances only on complete Count-gated cycles and never reuses an old plot')


def parent_handshake_checks():
    frame = (np.array([0.0, 1.0, 2.0]), np.ones(3), np.zeros(3))
    parent = ParentConnection([('Count', '[1 1]'), ('LiveTrace', frame),
                               ('Count', '[1 1]'), ('LiveTrace', frame), ('LiveEnd', '')])
    child = ParentConnection([])
    process = []
    rv = SimpleNamespace(active=True)
    writes, callbacks = [], []

    def on_trace(time, i, q):
        callbacks.append((time, i, q))
        assert rv.active
        writes.append(('video2_db', 0.5))
        return len(callbacks) == 2

    worker_args = SimpleNamespace(
        rect=[[None, None, None, ['+x', '-x']]], averages=1, rep_rate=1000,
        dig_args=lambda l_mode: ('dig', l_mode),
    )

    def make_process(*args, **kwargs):
        candidate = FakeProcess(*args, **kwargs)
        process.append(candidate)
        return candidate

    with patch.object(live, 'Pipe', return_value=(parent, child)), \
            patch.object(live, 'Process', side_effect=make_process), \
            patch.object(live.executor, 'Worker', return_value=object()), \
            patch.object(live.executor, '_hand_attrs'), \
            patch.object(live.executor, '_wind_down'):
        live.monitor_trace(worker_args, on_trace, poll_s=0)
    assert process[0].started
    assert process[0].args[2] == ('dig', 0)
    assert writes == [('video2_db', 0.5), ('video2_db', 0.5)]
    assert parent.commands == ['continue', 'exit']
    assert parent.closed and child.closed
    print('PASS: parent acknowledges every live frame after the mid-motion VA callback')


def rv_approach_checks():
    class Vane:
        def __init__(self):
            self.p1 = SimpleNamespace(active=False)
            self.targets = []

        def calibration(self, value):
            return value

        def mw_bridge_rotary_vane(self, value):
            self.p1.active = True
            self.targets.append(value)

    vane = Vane()
    calls, video_updates = [], []
    session = SimpleNamespace(
        test=False, mw_bridge=vane, state={'bridge': {'video1_db': 0, 'video2_db': 0}},
        log=lambda message: None, save_path=lambda tag: 'rv_live.csv',
        invalidate_fine_calibrations=lambda reason: calls.append(reason),
    )
    worker_args = SimpleNamespace(iq_cor=0)
    pre = object()

    def monitor(args, callback, on_message):
        for peak in (100.0, 250.0, 999.0, 100.0, 100.0, 100.0, 100.0):
            stopped = callback(np.array([0.0, 1e-9, 2e-9]),
                               np.array([peak, 0.0, 0.0]), np.zeros(3))
            if stopped:
                return
        raise AssertionError('RV approach did not finish')

    clock = iter(range(1000, 20000, 1000))
    with patch('atomize.epr_auto.engine.live_receiver.monitor_trace', side_effect=monitor), \
            patch.object(p.snapshot, 'build_worker_args', return_value=worker_args), \
            patch.object(p.executor, 'acquire_trace'), \
            patch.object(p, 'protection_trace_start_ns', return_value=0.0), \
            patch.object(p, '_video_settings', return_value={'video1_db': 0, 'video2_db': 0}), \
            patch.object(p, '_raise_video', side_effect=lambda current, peak: video_updates.append(
                (peak, vane.p1.active))), \
            patch.object(p.np, 'savetxt'), patch.object(p.time, 'monotonic', side_effect=clock):
        approach = p._rv_approach(session, pre, 12)
    assert [row['attenuation_db'] for row in approach] == [60, 40, 20, 15, 12]
    assert vane.targets == [40, 20, 15, 12]
    assert video_updates == [(250.0, True)]
    assert calls == ['RV move'] * 4
    print('PASS: live RV approach acknowledges frames and adjusts video while vane motion remains active')


def watchdog_checks():
    parent = ParentConnection([])
    child = ParentConnection([])
    worker_args = SimpleNamespace(
        rect=[[None, None, None, ['+x', '-x']]], averages=1, rep_rate=1000,
        dig_args=lambda l_mode: ('dig', l_mode),
    )
    with patch.object(live, 'Pipe', return_value=(parent, child)), \
            patch.object(live, 'Process', side_effect=FakeProcess), \
            patch.object(live.executor, 'Worker', return_value=object()), \
            patch.object(live.executor, '_hand_attrs'), \
            patch.object(live.executor, '_wind_down'), \
            patch.object(live.time, 'monotonic', side_effect=(0.0, 61.0)):
        try:
            live.monitor_trace(worker_args, lambda *frame: False, poll_s=0)
        except live.executor.EngineError as error:
            assert 'stalled' in str(error)
        else:
            raise AssertionError('live receiver accepted a missing frame stream')
    print('PASS: invalid or absent frames reach the receiver watchdog')

    parent = ParentConnection([('Count', '[1 0]')] * 3)
    with patch.object(live, 'Pipe', return_value=(parent, ParentConnection([]))), \
            patch.object(live, 'Process', side_effect=FakeProcess), \
            patch.object(live.executor, 'Worker', return_value=object()), \
            patch.object(live.executor, '_hand_attrs'), \
            patch.object(live.executor, '_wind_down'), \
            patch.object(live.time, 'monotonic', side_effect=(0.0, 1.0, 61.0)):
        try:
            live.monitor_trace(worker_args, lambda *frame: False, poll_s=0)
        except live.executor.EngineError as error:
            assert 'stalled' in str(error) and len(parent.events) == 2
        else:
            raise AssertionError('status traffic bypassed the frame watchdog')


child_handshake_checks()
parent_handshake_checks()
rv_approach_checks()
watchdog_checks()
print('ALL PASS')
