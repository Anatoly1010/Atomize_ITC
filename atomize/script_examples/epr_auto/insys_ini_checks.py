"""Check Insys INI integrity using temporary files and no hardware."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('run with the test argument; no hardware is used')

import atomize.device_modules.Insys_FPGA as insys


SAMPLE = (b'[Option]\r\nstreamBufSizeKb = 1024 ; buffer\r\n'
          b';BaseClockValue = 999.0\r\nBaseClockValue = 999.0 ; clock\r\n'
          b'ClockSource = 0x3\r\nStartBaseSource = 0\r\nUnrelated = retained\r\n')


def reset(paths):
    for path in paths:
        path.write_bytes(SAMPLE)
        os.chmod(path, 0o640)


def test_mode_checks(paths):
    reset(paths)

    def construct(_):
        pb = insys.Insys_FPGA()
        assert pb._status_owner is None and not pb._brd_open
        return pb.clock_value if pb.ext_clock else 200.0

    with ThreadPoolExecutor(max_workers=4) as pool:
        clocks = list(pool.map(construct, range(12)))
    assert len(set(clocks)) == 1
    expected = SAMPLE.replace(b'BaseClockValue = 999.0 ; clock',
                              f'BaseClockValue = {clocks[0]} ; clock'.encode())
    assert all(path.read_bytes() == expected for path in paths)

    pb = insys.Insys_FPGA()
    before = [path.read_bytes() for path in paths]
    pb.change_ini_file('streamBufSizeKb = 1024', 'streamBufSizeKb = 512')
    pb.change_two_ini_files('exam_edac.ini', 'ClockSource = 0x3', 'ClockSource = 0x2')
    assert [path.read_bytes() for path in paths] == before
    pb.change_three_ini_files('exam_adc.ini', 'BaseClockValue = ', '300.0')
    pb.change_three_ini_files('exam_edac.ini', 'BaseClockValue = ', '300.0')
    expected = expected.replace(f'BaseClockValue = {clocks[0]} ; clock'.encode(),
                                b'BaseClockValue = 300.0 ; clock')
    assert all(path.read_bytes() == expected for path in paths)
    pb.change_three_ini_files('exam_adc.ini', 'streamBufSizeKb = ', '512')
    assert paths[0].read_bytes() == expected.replace(b'streamBufSizeKb = 1024',
                                                     b'streamBufSizeKb = 512')
    assert paths[1].read_bytes() == expected


def write_checks(paths):
    reset(paths)
    pb = insys.Insys_FPGA()
    pb.test_flag = 'real'
    adc, dac = paths
    reset(paths)
    with patch('builtins.print', side_effect=AssertionError('INI writing used stdout')):
        pb.change_ini_file('StartBaseSource = 0', 'StartBaseSource = 7')
        pb.change_two_ini_files('exam_edac.ini', 'ClockSource = 0x3', 'ClockSource = 0x2')
        pb.change_three_ini_files('exam_adc.ini', 'BaseClockValue = ', '200.0')
        pb.change_three_ini_files('exam_edac.ini', 'BaseClockValue = ', '200.0')
        pb._set_stream_buffer_kb(512)
    expected_adc = SAMPLE.replace(b'StartBaseSource = 0', b'StartBaseSource = 7')
    expected_adc = expected_adc.replace(b'BaseClockValue = 999.0 ; clock',
                                        b'BaseClockValue = 200.0 ; clock')
    expected_adc = expected_adc.replace(b'streamBufSizeKb = 1024', b'streamBufSizeKb = 512')
    expected_dac = SAMPLE.replace(b'ClockSource = 0x3', b'ClockSource = 0x2')
    expected_dac = expected_dac.replace(b'BaseClockValue = 999.0 ; clock',
                                        b'BaseClockValue = 200.0 ; clock')
    assert adc.read_bytes() == expected_adc and dac.read_bytes() == expected_dac
    assert adc.stat().st_mode & 0o777 == 0o640

    pb.adc_window = 2000
    pb.pulser_repetition_rate('2000 Hz')
    assert adc.read_bytes() == expected_adc.replace(b'streamBufSizeKb = 512',
                                                     b'streamBufSizeKb = 4096')
    assert dac.read_bytes() == expected_dac


def failure_checks(adc):
    pb = insys.Insys_FPGA()
    original = adc.read_bytes()
    for name in ('fsync', 'replace'):
        with patch.object(insys.os, name, side_effect=OSError('injected write failure')):
            try:
                pb.change_three_ini_files(adc.name, 'BaseClockValue = ', '400.0')
            except OSError:
                pass
            else:
                raise AssertionError('write failure was hidden')
        assert adc.read_bytes() == original
        assert not list(adc.parent.glob('*.tmp'))
    try:
        pb._rewrite_ini(adc.name, lambda text: '')
    except ValueError:
        pass
    else:
        raise AssertionError('empty replacement was accepted')
    assert adc.read_bytes() == original
    adc.write_bytes(b'')
    try:
        pb.change_three_ini_files(adc.name, 'BaseClockValue = ', '400.0')
    except ValueError:
        pass
    else:
        raise AssertionError('empty input was accepted')
    finally:
        adc.write_bytes(original)


def concurrent_checks(adc):
    writers = [insys.Insys_FPGA() for _ in range(2)]
    adc.write_bytes(SAMPLE)
    allowed = {SAMPLE.replace(b'BaseClockValue = 999.0 ; clock',
                              f'BaseClockValue = {value} ; clock'.encode())
               for value in ('999.0', '200.0', '300.0')}

    def writer(pb, value):
        for _ in range(30):
            pb.change_three_ini_files(adc.name, 'BaseClockValue = ', value)
            assert adc.read_bytes() in allowed

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(writer, pb, value)
                   for pb, value in zip(writers, ('200.0', '300.0'))]
        while not all(future.done() for future in futures):
            assert adc.read_bytes() in allowed
        for future in futures:
            future.result()
    assert adc.read_bytes() in allowed and not list(adc.parent.glob('*.tmp'))


def main():
    dac_config = Path(insys.__file__).resolve().parent / 'config' / 'PB_Insys_DAC_config.ini'
    with tempfile.TemporaryDirectory(prefix='insys-ini-check-') as directory:
        root = Path(directory)
        fake_module = root / 'atomize' / 'device_modules' / 'Insys_FPGA.py'
        fake_module.parent.mkdir(parents=True)
        fake_config = fake_module.parent / 'config'
        fake_config.mkdir()
        (fake_config / dac_config.name).write_bytes(dac_config.read_bytes())
        (root / 'libs').mkdir()
        paths = [root / 'libs' / name for name in ('exam_adc.ini', 'exam_edac.ini')]
        reset(paths)
        with patch.object(insys, '__file__', str(fake_module)):
            test_mode_checks(paths)
            write_checks(paths)
            failure_checks(paths[0])
            concurrent_checks(paths[0])
    print('PASS: test-mode constructor and BaseClock setter write isolated INIs')
    print('PASS: other setters remain test-mode no-ops; real setters preserve settings')
    print('PASS: concurrent and failed writes preserve complete INIs')


if __name__ == '__main__':
    main()
