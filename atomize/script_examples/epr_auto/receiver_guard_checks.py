"""Offline receiver checks with the existing digitizer buffer readout."""
import sys
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.device_modules.Insys_FPGA import Insys_FPGA
from atomize.control_center.awg_phasing_insys import Worker
from atomize.epr_auto.engine import executor
import atomize.general_modules.general_functions as general


def packet(nid, level):
    data = np.zeros(40, dtype=np.int32)
    data[0], data[2] = np.int32(-1437269761), nid
    data[8::2] = level
    return data


def fake_readout():
    pb = Insys_FPGA.__new__(Insys_FPGA)
    pb.test_flag = 'fake-readout'
    pb.flag_adc_buffer = 0
    pb._acq_worker = None
    pb.dec_coef = 1
    pb.adc_window = 2
    pb.proc_thread = 0
    pb.flag_sum_brd = 1
    pb.nIP_No_brd = 0
    pb.nStrmBufTotalCnt_brd = 0
    pb.strmBufNum_brd = 16
    pb.gimSum_brd = 1
    pb.adc_sens = 1.0
    pb.detection_phase_list = ['+x'] * 4
    pb.det_residual_by_nid = {}
    pb._rep_time_ns = lambda: 1_000_000
    pb.overflow_check = lambda n, fresh, total, used: fresh
    return pb


def ready_buffer(pb, data):
    pb.nStrmBufSizeb_brd = data.nbytes
    pb.brdDataBuf_brd = np.zeros_like(data)
    available = pb.nStrmBufTotalCnt_brd + 1
    pb.AdcStreamGetBufState = lambda: available
    pb.AdcStreamGetBuf_buf = lambda target: np.copyto(target, data)


def live_buffer_checks():
    pb = fake_readout()
    for level in (12, 24):
        data = np.r_[np.full(13, 777, dtype=np.int32),
                     np.concatenate([packet(n % 4, level) for n in range(400)]),
                     packet(0, 999)[:23]]
        ready_buffer(pb, data)
        i, q = pb.digitizer_get_curve(1, 4, live_mode=1)
        assert np.allclose(i, level) and np.allclose(q, 0)
        assert np.array_equal(pb.count_nip, [100, 100, 100, 100])
    print('PASS: live buffers contain 100 cycles; fragments and previous buffer are excluded')


def sweep_buffer_checks():
    pb = fake_readout()
    worker = Worker()
    guard = worker.receiver_guard_settings({'limit_mv': 200, 'start_ns': 0})
    ready_buffer(pb, np.concatenate([packet(n, 150 if n < 4 else 600) for n in range(6)]))
    i, q, rng = pb.digitizer_get_curve(3, 4, partial=True)
    time_ns = np.arange(i.shape[0]) * 0.4
    assert rng == (0, 2) and np.max(i[:, 1]) == 300
    assert worker.receiver_guard_excess(guard, time_ns, i, q, rng, pb.count_nip, 4) is None
    ready_buffer(pb, np.concatenate([packet(6, 600), packet(7, 600)]))
    i, q, rng = pb.digitizer_get_curve(3, 4, partial=True)
    assert rng == (1, 2)
    assert worker.receiver_guard_excess(guard, time_ns, i, q, rng, pb.count_nip, 4) == (1, 600)
    with patch.object(pb, 'AdcStreamGetBufState', wraps=pb.AdcStreamGetBufState) as state:
        assert pb.digitizer_get_curve(3, 4, partial=True) == (None, None, None)
    assert state.call_count == 1
    print('PASS: completed received point is checked; incomplete phases and no-data reads do not wait')


def trace_validation_checks():
    class InvalidTrace:
        receiver_guard = {'limit_mv': 200, 'start_ns': 0}

        def dig_on(self, conn, script_test):
            for _ in range(2):
                general.plot_1d('trace', np.arange(3) * 1e-9,
                                (np.full(3, np.nan), np.zeros(3)))

    class TracePipe:
        def send(self, value):
            pass

    for script_test in (True, False):
        original = general.plot_1d
        try:
            with patch.object(executor.signal, 'signal'):
                executor._trace_child(InvalidTrace(), TracePipe(), (), 2, 1, script_test)
        except ValueError as error:
            assert not script_test and 'malformed readout' in str(error)
        else:
            assert script_test, 'live malformed trace was silently ignored'
        finally:
            general.plot_1d = original


if __name__ == '__main__':
    live_buffer_checks()
    sweep_buffer_checks()
    trace_validation_checks()
    print('receiver guard buffer checks passed')
