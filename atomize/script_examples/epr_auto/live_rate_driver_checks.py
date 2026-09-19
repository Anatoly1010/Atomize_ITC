"""Offline checks for ordinary Insys packet parsing and a pinned stream size."""

from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('run with the test argument; no hardware is used')

import atomize.device_modules.Insys_FPGA as insys


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def packet(nid, payload, header=insys._HEADER_SIG):
    row = np.zeros(8 + len(payload), dtype=np.int32)
    row[0] = header
    row[2] = nid
    row[8:] = payload
    return row


def parser_card(decimation=1, total_points=2):
    pb = insys.Insys_FPGA()
    pb.adc_window = 1
    pb.dec_coef = decimation
    pb._acc_dec = decimation
    pb.nStrmBufSizeb_brd = 4096
    pb.data_raw = np.zeros(total_points * 16 // decimation, dtype=np.int64)
    pb.count_nip = np.zeros(total_points, dtype=np.int32)
    pb.tail_carry = np.empty(0, dtype=np.int32)
    pb._last_processed_nid = -1
    return pb


def buffer_checks():
    check(not hasattr(insys.Insys_FPGA, '_configure_live_rates')
          and not hasattr(insys.Insys_FPGA, '_select_live_rate'),
          'obsolete live-rate driver methods remain')
    with patch.object(insys.insys_status, 'ensure_available'):
        for rate in (10, 20, 2000):
            for window in (200, 700, 2000):
                pb = insys.Insys_FPGA()
                pb.adc_window = window
                pb._stream_buffer_kb_for = lambda rep_time, adc_window: 512
                pb.pulser_repetition_rate(f'{rate} Hz')
                pb.pulser_open()
                check(pb.nStrmBufSizeb_brd == 512 * 2**10,
                      f'buffer changed at {rate} Hz with ADC window {window}')
                check(pb.pulser_repetition_rate() == f'{rate} Hz',
                      'repetition-rate setter lost the requested rate')
                check(not any(name.startswith('_live_rate') for name in vars(pb)),
                      'obsolete live-rate driver state remains')


def parser_checks():
    payload = np.arange(16, dtype=np.int32)
    pb = parser_card()
    lo, hi = pb._process_packet_stream(packet(0, payload), 16, 24, 2, False)
    check((lo, hi) == (0, 0) and pb.count_nip[0] == 1,
          'ordinary packet was not parsed')

    pb = parser_card()
    lo, hi = pb._process_packet_stream(packet(2, payload), 16, 24, 2, False)
    check(lo is None and hi is None and not pb.count_nip.any(),
          'out-of-range packet was accepted')

    pb = parser_card()
    repeated = np.concatenate((packet(0, payload), packet(0, payload + 1)))
    pb._process_packet_stream(repeated, 16, 24, 2, False)
    check(pb.count_nip[0] == 2 and np.all(pb.data_raw[:16] == payload * 2 + 1),
          'repeated nid accumulation is wrong')

    pb = parser_card(decimation=2, total_points=1)
    pb._process_packet_stream(packet(0, payload), 16, 24, 1, False)
    expected = payload.reshape(4, 2, 2).sum(axis=1).reshape(-1)
    check(np.array_equal(pb.data_raw, expected), 'decimation accumulation is wrong')

    pb = parser_card()
    first = packet(0, payload)
    pb.gen_2d_array_from_buffer(first[:10], 1, 1, 1, 1, False)
    check(pb.tail_carry.size == 10, 'split packet was not carried')
    pb.gen_2d_array_from_buffer(first[10:], 1, 1, 1, 1, False)
    check(pb.count_nip[0] == 1, 'split packet was not reassembled')


def gim_checks():
    pb = insys.Insys_FPGA()
    pb.test_flag = 'real'
    calls = []
    for name in ('setSwitchEn_GIM', 'rstFIFO_GIM', 'setWriteEnable_GIM',
                 'setFIFOCnt_GIM', 'writeIP', 'set1stChanImpLen_GIM',
                 'setSelect_GIM'):
        setattr(pb, name, lambda *args, _name=name: calls.append((_name, args)) or 1)
    pb.setId_GIM = lambda *args: calls.append(('setId_GIM', args)) or 1
    pb.setGIM_mode = lambda *args: calls.append(('setGIM_mode', args)) or 1
    pb.data_buf_IP_GIM_brd = (0, np.zeros(0, dtype=np.int32))
    pb.adc_window = 1
    pb.nIP_No_brd = 3
    pb.flag_sum_brd = 1
    pb._det_residue_samples = lambda: 0
    pb.write_data_GIM_brd()
    check(('setId_GIM', (1, 3, 0)) in calls,
          'GIM packet ID differs from physical nIP')
    check(('setGIM_mode', (1, 0, 1)) in calls,
          'GIM FIFO parity differs from physical nIP')


def main():
    dac_config = Path(insys.__file__).resolve().parent / 'config' / 'PB_Insys_DAC_config.ini'
    with tempfile.TemporaryDirectory(prefix='insys-driver-check-') as directory:
        root = Path(directory)
        fake_module = root / 'atomize' / 'device_modules' / 'Insys_FPGA.py'
        fake_module.parent.mkdir(parents=True)
        fake_config = fake_module.parent / 'config'
        fake_config.mkdir()
        (fake_config / dac_config.name).write_bytes(dac_config.read_bytes())
        libs = root / 'libs'
        libs.mkdir()
        sample = ('[Option]\nstreamBufSizeKb = 1024\nBaseClockValue = 999.0\n'
                  'ClockSource = 0x3\nStartBaseSource = 0\n')
        for name in ('exam_adc.ini', 'exam_edac.ini'):
            (libs / name).write_text(sample, encoding='utf-8')
        with patch.object(insys, '__file__', str(fake_module)):
            buffer_checks()
            parser_checks()
            gim_checks()
    print('PASS: pinned 512 KB buffer across rates and ADC windows')
    print('PASS: ordinary packet parsing and physical GIM packet IDs')


if __name__ == '__main__':
    main()
