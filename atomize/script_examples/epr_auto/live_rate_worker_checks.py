"""Offline checks for fresh live readouts, rate transitions and worker cleanup."""
from collections import deque
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.control_center.awg_phasing_insys import Worker
from atomize.device_modules.Insys_FPGA import Insys_FPGA
import atomize.device_modules.Insys_FPGA as insys
from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.params import PRESET_DIR
import atomize.general_modules.general_functions as general


def args():
    pre = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    wa = snapshot.build_worker_args(pre, exp_name='LiveRateCheck')
    wa.iq_cor = 1
    return wa


def worker_checks():
    wa = args()
    pb = Insys_FPGA()
    calls, reads = [], []
    epoch_reads = {}
    opened = Mock(wraps=pb.pulser_open)
    closed = Mock(wraps=pb.pulser_close)
    phases = len(wa.rect[0][3])

    def read(points, ph, live_mode):
        assert points == 1 and live_mode == 1
        epoch = 0 if float(pb.pulser_repetition_rate().split()[0]) == 10 else 1
        epoch_reads[epoch] = epoch_reads.get(epoch, 0) + 1
        count = epoch_reads[epoch]
        reads.append((epoch, count))
        if count == 1:
            return None, None
        pb.nStrmBufTotalCnt_brd += 1
        pb.count_nip = np.ones(ph, dtype=int)
        wave = np.ones((int(pb.adc_window * 8 / pb.dec_coef), 1)) * (epoch + 1)
        if count == 2:
            wave[:] = np.nan
        elif count == 3:
            wave[:] = epoch + .5
        return wave, np.zeros_like(wave)

    class Pipe:
        def __init__(self):
            self.pending = deque()
            self.messages = []
            self.valid = {0: 0, 1: 0}

        def send(self, message):
            self.messages.append(message)
            if message[0] == 'LiveCurve':
                epoch, i, q, valid, number = message[1]
                if valid:
                    self.valid[epoch] += 1
                    if self.valid[epoch] == 3:
                        self.pending.append('LR1' if epoch == 0 else 'exit')

        def poll(self, *unused):
            return bool(self.pending)

        def recv(self):
            value = self.pending.popleft()
            calls.append(value)
            return value

    worker = Worker()
    executor._hand_attrs(worker, wa)
    worker.live_rates = (10.0, 2000.0)
    pipe = Pipe()
    with ExitStack() as stack:
        stack.enter_context(patch('atomize.device_modules.Insys_FPGA.Insys_FPGA', return_value=pb))
        field = stack.enter_context(patch('atomize.device_modules.BH_15.BH_15'))
        stack.enter_context(patch.object(pb, 'pulser_open', opened))
        stack.enter_context(patch.object(pb, 'pulser_close', closed))
        stack.enter_context(patch.object(pb, 'digitizer_get_curve', side_effect=read))
        for name in ('set_plotting_async', 'plot_1d'):
            stack.enter_context(patch.object(general, name))
        worker.dig_on(pipe, *wa.dig_args(l_mode=0), script_test=False)
    errors = [message for message in pipe.messages if message[0] == 'Error']
    assert not errors, errors
    frames = [message[1] for message in pipe.messages if message[0] == 'LiveCurve']
    assert opened.call_count == 1 and closed.call_count >= 1
    assert pb.nStrmBufSizeb_brd == 512 * 1024
    assert not any(name.startswith('_live_rate') for name in vars(pb))
    assert field.return_value.magnet_field.call_count == 1
    assert calls == ['LR1', 'exit'], calls
    assert len(frames) == len(reads) - 2, 'empty readouts were counted as curves'
    assert sum(not frame[3] for frame in frames) == 2
    assert [message[1] for message in pipe.messages if message[0] == 'LiveRate'] == [0, 1]
    assert any(message[0] == 'LiveEnd' for message in pipe.messages)
    print('PASS: Worker uses ordinary driver, one open/field setup, 512 KB, 10 -> 2000 Hz, transition curves and cleanup')


def executor_checks():
    wa = args()
    curves = [
        ('LiveRate', 0),
        ('LiveCurve', (0, 1.0, 0., True, 1)),
        ('LiveCurve', (0, 1.0, 0., True, 1)),
        ('LiveCurve', (0, 99., 0., False, 2)),
        ('LiveCurve', (0, 1.0, 0., True, 3)),
        ('LiveCurve', (0, 1.01, 0., True, 4)),
        ('LiveCurve', (0, 1.02, 0., True, 5)),
        ('LiveCurve', (0, 999., 0., True, 6)),
        ('LiveRate', 1),
        ('LiveCurve', (0, 999., 0., True, 7)),
        ('LiveCurve', (1, 2., 0., True, 8)),
        ('LiveCurve', (1, 2.01, 0., True, 9)),
        ('LiveCurve', (1, 2.02, 0., True, 10)),
        ('LiveEnd', ''),
    ]
    for label in ('ok', 'stop', 'error', 'callback', 'timeout', 'interrupt', 'preflight'):
        conn, process = Mock(), Mock()
        conn.poll.return_value = True
        process.is_alive.return_value = True
        events = list(curves)
        if label == 'stop':
            events = [('LiveEnd', '')]
        if label == 'error':
            events = [('Error', 'device failure')]
        if label == 'interrupt':
            conn.poll.side_effect = KeyboardInterrupt
        conn.recv.side_effect = events
        observed = []
        callback = observed.append if label != 'callback' else Mock(side_effect=OSError('save failed'))
        with ExitStack() as stack:
            stack.enter_context(patch.object(executor, 'Pipe', return_value=(conn, Mock())))
            stack.enter_context(patch.object(executor, 'Process', return_value=process))
            drain = stack.enter_context(patch.object(executor, '_wind_down'))
            if label == 'timeout':
                stack.enter_context(patch.object(executor.time, 'monotonic', side_effect=[0, 121]))
            try:
                result = executor.acquire_live_rates(wa, [20, 2000], on_curve=callback,
                                                       script_test=label == 'preflight')
            except (executor.EngineError, OSError, KeyboardInterrupt):
                assert label not in ('ok', 'preflight'), label
            else:
                assert label in ('ok', 'preflight'), label
                if label == 'ok':
                    assert np.allclose(result, [[1, 1.01, 1.02], [2, 2.01, 2.02]])
                    assert len(observed) == 8, observed
                    assert [call.args[0] for call in conn.send.call_args_list] == ['LR1', 'exit']
                else:
                    assert result == {'status': 'test-ok'}
            drain.assert_called_once()
            assert process.call_count == 0
    for rates in ([9.9, 2000], [10, 100001], [10, float('nan')]):
        with patch.object(executor, 'Process') as process:
            try:
                executor.acquire_live_rates(wa, rates)
            except executor.EngineError as error:
                assert '10–100000 Hz' in str(error)
            else:
                raise AssertionError('out-of-range live acquisition accepted')
            process.assert_not_called()
    print('PASS: duplicate/queued previous-rate/invalid readouts excluded, convergence, cleanup and 10 Hz minimum')


def buffer_restore_checks():
    source_config = Path(insys.__file__).parent / 'config' / 'PB_Insys_DAC_config.ini'
    with tempfile.TemporaryDirectory(prefix='live-rate-restore-') as directory:
        root = Path(directory)
        module = root / 'atomize' / 'device_modules' / 'Insys_FPGA.py'
        config = module.parent / 'config'
        config.mkdir(parents=True)
        (config / source_config.name).write_bytes(source_config.read_bytes())
        libs = root / 'libs'
        libs.mkdir()
        adc, dac = libs / 'exam_adc.ini', libs / 'exam_edac.ini'
        original = (b'[Option]\r\nstreamBufSizeKb = 2048 ; retained comment\r\n'
                    b'BaseClockValue = 100.0\r\nUnrelated = retained\r\n')
        for mode in ('complete', 'stop', 'read_error', 'open_error', 'close_error', 'restore_error'):
            for path in (adc, dac):
                path.write_bytes(original)
            with patch.object(insys, '__file__', str(module)):
                pb = Insys_FPGA()
                original_adc, original_dac = adc.read_bytes(), dac.read_bytes()
                active_adc = original_adc.replace(b'streamBufSizeKb = 2048', b'streamBufSizeKb = 512')
                state = {'open': False, 'restored': False, 'stages': set()}
                messages, pending = [], deque()
                original_rate = pb.pulser_repetition_rate
                original_write = pb._set_stream_buffer_kb
                original_open = pb.pulser_open

                def write(kb):
                    restoring = int(kb) == 2048
                    if restoring:
                        assert not state['open'], 'buffer restored before card close'
                    previous = pb.test_flag
                    pb.test_flag = 'real'
                    try:
                        if restoring and mode == 'restore_error':
                            with patch.object(insys.os, 'replace', side_effect=OSError('injected restore failure')):
                                original_write(kb)
                        else:
                            original_write(kb)
                    finally:
                        pb.test_flag = previous
                    if restoring:
                        state['restored'] = True

                def rate(*values):
                    result = original_rate(*values)
                    if values:
                        write(pb._stream_buffer_kb_for(pb._rep_time_ns(), pb.adc_window))
                    return result

                def opened():
                    assert adc.read_bytes() == active_adc
                    if mode == 'open_error':
                        raise OSError('injected open failure')
                    original_open()
                    state['open'] = True

                def closed():
                    state['open'] = False
                    if mode == 'close_error':
                        raise OSError('injected close failure')

                def read(points, phases, live_mode):
                    assert adc.read_bytes() == active_adc
                    assert pb.nStrmBufSizeb_brd == 512 * 1024
                    if mode == 'read_error':
                        raise OSError('injected read failure')
                    pb.nStrmBufTotalCnt_brd += 1
                    pb.count_nip = np.ones(phases, dtype=int)
                    wave = np.ones((int(pb.adc_window * 8 / pb.dec_coef), 1))
                    return wave, np.zeros_like(wave)

                class Pipe:
                    def send(self, message):
                        messages.append(message)
                        if message[0] == 'LiveCurve':
                            index = message[1][0]
                            if index not in state['stages']:
                                state['stages'].add(index)
                                pending.append('exit' if mode == 'stop' or index == 1 else 'LR1')
                        elif message[0] == 'LiveEnd':
                            assert state['restored'] and adc.read_bytes() == original_adc

                    def poll(self, *unused):
                        return bool(pending)

                    def recv(self):
                        return pending.popleft()

                worker = Worker()
                worker.live_rates = (10.0, 2000.0)
                with ExitStack() as stack:
                    stack.enter_context(patch.object(insys, 'Insys_FPGA', return_value=pb))
                    stack.enter_context(patch('atomize.device_modules.BH_15.BH_15'))
                    for name, replacement in (('pulser_repetition_rate', rate),
                                               ('_set_stream_buffer_kb', write),
                                               ('pulser_open', opened), ('pulser_close', closed),
                                               ('digitizer_get_curve', read)):
                        stack.enter_context(patch.object(pb, name, side_effect=replacement))
                    for name in ('set_plotting_async', 'plot_1d'):
                        stack.enter_context(patch.object(general, name))
                    worker.dig_on(Pipe(), *args().dig_args(l_mode=0), script_test=False)
                assert not state['open']
                assert dac.read_bytes() == original_dac
                errors = [payload for kind, payload in messages if kind == 'Error']
                ended = any(kind == 'LiveEnd' for kind, _ in messages)
                if mode == 'restore_error':
                    assert adc.read_bytes() == active_adc
                    assert errors and 'restoration failed' in errors[-1] and not ended
                else:
                    assert adc.read_bytes() == original_adc and state['restored'], mode
                    assert bool(errors) == (mode in ('read_error', 'open_error', 'close_error')), errors
                    assert ended == (mode in ('complete', 'stop'))
                assert not list(libs.glob('*.tmp'))
    print('PASS: 512 KB restored after close on completion/Stop/read/open/close errors; failed restore keeps INI intact and reports error')


if __name__ == '__main__':
    worker_checks()
    executor_checks()
    buffer_restore_checks()
