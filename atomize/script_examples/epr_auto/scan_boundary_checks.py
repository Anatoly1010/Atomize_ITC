"""Offline complete-scan readout and acknowledged early-finish checks."""
from collections import deque
from contextlib import ExitStack
import io
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.control_center.awg_phasing_insys import Worker
from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.params import PRESET_DIR
import atomize.general_modules.general_functions as general


class FakeFPGA:
    def __init__(self, phases):
        self.phases = phases
        self.reads = 0
        self.scan_reads = []
        self.resets = 0
        self.closed = 0
        self.data = None
        self.rate = None

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    def digitizer_window_points(self):
        return 8

    def pulser_repetition_rate(self, rate=None):
        if rate is not None:
            self.rate = rate
        return self.rate

    def digitizer_get_curve(self, points, phases, *, current_scan, total_scan, partial):
        self.reads += 1
        self.scan_reads.append((current_scan, total_scan))
        if self.reads % (points * phases):
            return None, None, None
        if current_scan != total_scan:
            return None, None, None
        self.data = np.full((8, points), (current_scan + 1) / 2)
        return self.data.copy(), np.zeros_like(self.data), (0, points)

    def pulser_pulse_reset(self):
        self.resets += 1
        assert self.data is not None, 'scan reset occurred before complete readout'

    def digitizer_demodulate(self, i, q, *args, **kwargs):
        return i[0].copy(), q[0].copy()

    def digitizer_at_exit(self):
        return self.data.copy(), np.zeros_like(self.data)

    def digitizer_window(self):
        return 3.2

    def pulser_close(self):
        self.closed += 1

    def pulser_pulse_list(self):
        return ''

    def awg_pulse_list(self):
        return ''


class BoundaryPipe:
    def __init__(self, commands):
        self.commands = commands
        self.messages = []
        self.pending = deque()

    def send(self, value):
        self.messages.append(value)
        if value[0] == 'ScanData':
            self.pending.extend(self.commands(value[1][0]))
        elif value[0] == 'Open':
            self.pending.append('FLdummy.csv')

    def poll(self, timeout=None):
        return bool(self.pending)

    def recv(self):
        return self.pending.popleft()


def worker_checks():
    for method, preset_name, builder in (
            ('exp', 'hahn_echo_4s.phase_awg', 'exp_args'),
            ('exp_log', 'inversion_recovery_echo_4s_log.phase_awg', 'exp_log_args')):
        pre = snapshot.load_preset(PRESET_DIR / preset_name)
        wa = snapshot.build_worker_args(pre, exp_name='ScanBoundaryCheck', points=4, scans=3)
        wa.iq_cor = 1
        wa.save2d = 0
        wa.scan_data_flag = wa.scan_data_wait = 1
        for label, commands, expected in (
                ('continue', lambda scan: ['ScanContinue'], 3),
                ('resize', lambda scan: ['SC1', 'ScanContinue'], 1),
                ('stop', lambda scan: ['exit'], 1),
                ('parent_exit', lambda scan: [], 1)):
            worker = Worker()
            executor._hand_attrs(worker, wa)
            pb = FakeFPGA(len(wa.rect[0][3]))
            pipe = BoundaryPipe(commands)
            saver = Mock()
            temp = SimpleNamespace(tc_setpoint=Mock(return_value=80),
                                   tc_temperature=Mock(return_value=80))
            with ExitStack() as stack:
                stack.enter_context(patch('atomize.control_center.awg_phasing_insys.parent_process', return_value=SimpleNamespace(is_alive=lambda: label != 'parent_exit')))
                stack.enter_context(patch('atomize.device_modules.Insys_FPGA.Insys_FPGA', return_value=pb))
                stack.enter_context(patch('atomize.device_modules.Lakeshore_335.Lakeshore_335', return_value=temp))
                stack.enter_context(patch('atomize.device_modules.BH_15.BH_15'))
                stack.enter_context(patch('atomize.device_modules.Micran_X_band_MW_bridge_v2.Micran_X_band_MW_bridge_v2'))
                stack.enter_context(patch('atomize.general_modules.csv_opener_saver.Saver_Opener', return_value=saver))
                stack.enter_context(patch('atomize.control_center.awg_phasing_insys.temp_param.write_status'))
                for name in ('set_plotting_async', 'plot_1d', 'plot_2d', 'update_2d', 'wait'):
                    stack.enter_context(patch.object(general, name))
                getattr(worker, method)(pipe, *getattr(wa, builder)(), script_test=False)
            frames = [payload for kind, payload in pipe.messages if kind == 'ScanData']
            errors = [payload for kind, payload in pipe.messages if kind == 'Error']
            if label == 'parent_exit':
                assert len(errors) == 1 and 'acknowledgment' in errors[0], errors
                assert saver.save_data.call_count == 0
            else:
                assert not errors, errors
                assert saver.save_data.call_count == 1
                saved = saver.save_data.call_args.args[1]
                assert np.all(saved[:, 1] == (expected + 1) / 2), saved
                assert pipe.messages[-1][0] == ''
            assert len(frames) == expected, (method, label, len(frames))
            for scan, i, q in frames:
                assert np.all(i == (scan + 1) / 2), (method, label, scan, i)
                assert np.all(q == 0)
            assert pb.reads == expected * len(frames[0][1]) * pb.phases
            assert pb.resets == expected and pb.closed >= 1
            assert temp.tc_setpoint.call_count == expected, 'Stop entered the next scan temperature wait'
            assert all(current == total for current, total in pb.scan_reads)
        print(f'PASS {method}: complete readout, continued accumulation, no extra scan, Stop and parent-exit cleanup')


def executor_checks():
    for label, callback in (
            ('none', None),
            ('continue', lambda *args: None),
            ('resize', lambda *args: 1),
            ('error', Mock(side_effect=ValueError('callback failed')))):
        worker, conn, process = Worker(), Mock(), Mock()
        frames = [('ScanData', (1, np.ones(4), np.zeros(4))),
                  ('Open', ''), ('', 'Experiment check finished')]
        conn.poll.return_value = True
        conn.recv.side_effect = frames
        wa = SimpleNamespace(exp_args=lambda: (), scan_data_flag=1, scan_data_wait=1)
        with patch.object(executor, 'Worker', return_value=worker), \
                patch.object(executor, 'Pipe', return_value=(conn, Mock())), \
                patch.object(executor, 'Process', return_value=process), \
                patch.object(executor, '_wind_down'), patch('sys.stdout', new=io.StringIO()):
            result = executor.run_worker(wa, 'Linear Time', save_path='dummy.csv', on_scan_data=callback)
        sent = [call.args[0] for call in conn.send.call_args_list]
        assert sent == (['SC1'] if label == 'resize' else []) + ['ScanContinue', 'FLdummy.csv'], sent
        assert result == {'status': 'finished', 'file': 'dummy.csv'}
    for sweep, expected in (('Log Time', ['SC1', 'ScanContinue']), ('Field', ['SC1'])):
        worker, conn, process = Worker(), Mock(), Mock()
        conn.poll.return_value = True
        conn.recv.side_effect = [('Status', 5), ('ScanData', (1, np.ones(4), np.zeros(4))),
                                 ('', 'Experiment check finished')]
        wa = SimpleNamespace(exp_log_args=lambda: (), exp_field_args=lambda: (),
                             scan_data_flag=1, scan_data_wait=1)
        with patch.object(executor, 'Worker', return_value=worker), \
                patch.object(executor, 'Pipe', return_value=(conn, Mock())), \
                patch.object(executor, 'Process', return_value=process), \
                patch.object(executor, '_wind_down'):
            executor.run_worker(wa, sweep, save_path='dummy.csv',
                                scan_control=lambda *args: 1, on_scan_data=lambda *args: 3)
        assert [call.args[0] for call in conn.send.call_args_list] == expected
    worker = Worker()
    worker.scan_data_wait = 1
    pipe = BoundaryPipe(lambda scan: ['SC2', 'SC1', 'ScanContinue'])
    worker.command = 'SC3'
    assert worker._scan_data_boundary(pipe, 1, np.ones(4), np.zeros(4), 8) == 1
    assert worker.command == 'start' and not pipe.pending
    worker.scan_data_wait = 0
    assert worker._scan_data_boundary(pipe, 1, np.ones(4), np.zeros(4), 8) == 8
    worker.scan_data_wait = 1
    conn = Mock()
    conn.poll.side_effect = [False] * 200 + [True]
    conn.recv.return_value = 'ScanContinue'
    parent = Mock()
    parent.is_alive.return_value = True
    with patch('atomize.control_center.awg_phasing_insys.parent_process', return_value=parent):
        assert worker._scan_data_boundary(conn, 1, np.ones(4), np.zeros(4), 8) == 8
    assert parent.is_alive.call_count == 200, 'valid callbacks must not expire after 30 seconds'
    conn.poll.side_effect = None
    conn.poll.return_value = True
    conn.recv.side_effect = EOFError
    try:
        worker._scan_data_boundary(conn, 1, np.ones(4), np.zeros(4), 8)
    except EOFError:
        pass
    else:
        raise AssertionError('disconnected pipe did not release the boundary wait')
    print('PASS executor: every policy result acknowledges; queued scan limits are consumed before continuing')


def threaded_readout_checks():
    from atomize.script_examples.epr_auto.receiver_guard_checks import fake_readout, packet

    pb = fake_readout()
    pb.proc_thread = 1
    pb._acq_lock = threading.Lock()
    pb._acq_pool_bufsize = 0
    try:
        for scan in (1, 2):
            packets = [packet(nid, scan * 10) for nid in range(12)]
            buffers = [np.concatenate(packets[:8]),
                       np.concatenate(packets[8:] + [np.zeros(40, dtype=np.int32)] * 4)]
            pb.nStrmBufSizeb_brd = buffers[0].nbytes
            pb.nIP_No_brd = 12
            pb.N_IP = 0
            previous = pb.nStrmBufTotalCnt_brd
            polls = 0

            def available():
                nonlocal polls
                polls += 1
                return previous + (1 if polls < 3 else 2)

            def read(target):
                np.copyto(np.ctypeslib.as_array(target)[:buffers[0].size], buffers.pop(0))

            pb.AdcStreamGetBufState = available
            pb.AdcStreamGetBuf_buf = read
            i, q, touched = pb.digitizer_get_curve(3, 4, current_scan=scan, total_scan=scan, partial=True)
            assert touched == (0, 3) and np.allclose(i, 5 * (scan + 1)) and np.allclose(q, 0)
            assert np.all(pb.count_nip == scan), pb.count_nip
            assert pb._acq_pending == 0 and pb._acq_worker.is_alive()
            assert polls >= 3 and not buffers
    finally:
        pb._acq_worker_stop()
    print('PASS digitizer: each scan drains delayed final packets, flushes the thread and retains earlier accumulations')


if __name__ == '__main__':
    threaded_readout_checks()
    worker_checks()
    executor_checks()
    print('ALL PASS')
