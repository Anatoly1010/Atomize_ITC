"""FPGA protection without loading the vendor library or accessing hardware."""

import os
import importlib
import runpy
import signal
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6 import QtCore
from PyQt6.QtWidgets import QApplication

from atomize.device_modules.Insys_FPGA import Insys_FPGA
from atomize.general_modules import insys_status
from atomize.main.main import MainExtended
from atomize.main.main_window import MainWindow
from atomize.main.queue import QueueList


@pytest.fixture
def status(monkeypatch, tmp_path):
    path = tmp_path / 'status'
    monkeypatch.setattr(insys_status, 'status_path', lambda: path)
    monkeypatch.setattr(insys_status, 'boot_id', lambda: 'boot-a')
    monkeypatch.setattr(insys_status, 'process_identity', lambda pid: ('S', '123'))
    monkeypatch.setattr(insys_status, '_legacy_previous_boot', lambda path: False)
    return path


@pytest.fixture
def board(status):
    board = Insys_FPGA.__new__(Insys_FPGA)
    board.path_status_file = str(status)
    board.test_flag = 'None'
    board._status_owner = None
    board._brd_open = False
    board._recovery_required = False
    board._board_released = False
    board.ext_trigger = 0
    for name in ('initBrd', 'closeBrd'):
        setattr(board, name, Mock(return_value=2))
    for name in ('setZero_GIM', 'rst_GIM', 'setSync_GIM', 'setEnable_GIM',
                 'setDACEnable_GIM', 'setSwitchEn_GIM'):
        setattr(board, name, Mock(return_value=1))
    board.getDAC_ChanNum = Mock(return_value=2)
    board.getStrmBufSizeb = Mock(return_value=8)
    board.getStreamBufNum = Mock(return_value=2)
    board._acq_worker_stop = Mock()
    board._rep_time_ns = Mock(return_value=1000)
    board._stream_buffer_kb_for = Mock(return_value=4)
    board.adc_window = 1024
    return board


def test_successful_open_close_and_repeat_close(board, status):
    board.initBrd.side_effect = lambda: 2 if status.read_text().startswith('Status:  On\n') else 0
    board.pulser_open()
    assert board._brd_open
    assert insys_status.blocking_reason()
    board.pulser_close()
    board.pulser_close()
    board.closeBrd.assert_called_once()
    assert insys_status.blocking_reason() is None
    assert status.read_text() == 'Status:  Off\n'


def test_rejected_real_open_and_cleanup_preserve_other_owner(board, status):
    owner = insys_status.claim()
    original = status.read_bytes()
    with pytest.raises(RuntimeError, match='already opened'):
        board.pulser_open()
    board.pulser_close()
    assert status.read_bytes() == original
    assert insys_status.is_owner(owner)
    board.initBrd.assert_not_called()
    board.closeBrd.assert_not_called()


@pytest.mark.parametrize('busy', [False, True])
def test_test_mode_never_writes_or_clears_status(board, status, busy):
    if busy:
        insys_status.claim()
    board.test_flag = 'test'
    original = status.read_bytes() if status.exists() else None
    if busy:
        with pytest.raises(RuntimeError, match='already opened'):
            board.pulser_open()
    else:
        board.pulser_open()
        assert board.nStrmBufSizeb_brd == 4096
    board.pulser_close()
    assert (status.read_bytes() if status.exists() else None) == original
    board.initBrd.assert_not_called()
    board.closeBrd.assert_not_called()


def test_incorrect_test_can_be_corrected_without_reboot(board, status):
    board.test_flag = 'test'
    board._stream_buffer_kb_for.side_effect = ValueError('Invalid script parameter')
    with pytest.raises(ValueError):
        board.pulser_open()
    board.pulser_close()
    assert not status.exists()
    board._stream_buffer_kb_for.side_effect = None
    board.pulser_open()
    assert not status.exists()


@pytest.mark.parametrize('failure', [-499, 0, OSError('initialization failed')])
def test_failed_initialization_requires_reboot(board, status, failure):
    if isinstance(failure, Exception):
        board.initBrd.side_effect = failure
    else:
        board.initBrd.return_value = failure
    with pytest.raises((RuntimeError, OSError)):
        board.pulser_open()
    with pytest.raises(RuntimeError, match='requires reboot'):
        board.pulser_close()
    assert insys_status.blocking_reason() == insys_status.REBOOT_REQUIRED
    board.setZero_GIM.assert_not_called()


def test_failure_after_open_can_release_board(board):
    board.setZero_GIM.return_value = -498
    with pytest.raises(RuntimeError, match='setZero_GIM'):
        board.pulser_open()
    assert board._brd_open
    board.pulser_close()
    assert insys_status.blocking_reason() is None


@pytest.mark.parametrize('step,failure', [
    (step, failure) for step in ('_acq_worker_stop', 'setEnable_GIM', 'setDACEnable_GIM', 'setSwitchEn_GIM', 'closeBrd')
    for failure in ('exception', 'return') if step != '_acq_worker_stop' or failure == 'exception'
])
def test_failed_cleanup_stays_blocked(board, step, failure):
    board.pulser_open()
    if failure == 'exception':
        getattr(board, step).side_effect = OSError('cleanup failed')
    else:
        getattr(board, step).return_value = -498
    with pytest.raises(RuntimeError, match='requires reboot'):
        board.pulser_close()
    assert insys_status.blocking_reason() == insys_status.REBOOT_REQUIRED
    board.closeBrd.assert_called_once()
    with pytest.raises(RuntimeError, match='requires reboot'):
        board.pulser_close()
    board.closeBrd.assert_called_once()


@pytest.mark.parametrize('identity', [None, ('Z', '123'), ('X', '123'), ('S', '999')])
def test_dead_or_reused_owner_requires_reboot(status, monkeypatch, identity):
    insys_status.claim()
    original = status.read_bytes()
    def identify(pid):
        if identity is None:
            raise FileNotFoundError
        return identity
    monkeypatch.setattr(insys_status, 'process_identity', identify)
    assert insys_status.blocking_reason() == insys_status.REBOOT_REQUIRED
    assert status.read_bytes() == original


def test_reboot_allows_new_owner_without_test_writes(status, monkeypatch):
    owner = insys_status.claim()
    insys_status.require_reboot(owner)
    original = status.read_bytes()
    monkeypatch.setattr(insys_status, 'boot_id', lambda: 'boot-b')
    insys_status.ensure_available()
    assert status.read_bytes() == original
    new_owner = insys_status.claim()
    assert new_owner['Boot'] == 'boot-b'
    assert not insys_status.is_owner(owner)
    insys_status.release(new_owner)


def test_other_instance_and_forked_child_cannot_release(status, monkeypatch):
    owner = insys_status.claim()
    original = status.read_bytes()
    with pytest.raises(RuntimeError):
        insys_status.release({**owner, 'Token': 'another-instance'})
    monkeypatch.setattr(insys_status.os, 'getpid', lambda: int(owner['PID']) + 1)
    with pytest.raises(RuntimeError):
        insys_status.release(owner)
    assert status.read_bytes() == original


def test_unreadable_and_malformed_status_block(status, monkeypatch):
    status.write_text('broken status')
    assert 'Cannot verify' in insys_status.blocking_reason()
    monkeypatch.setattr(insys_status, '_read', Mock(side_effect=PermissionError('denied')))
    assert 'Cannot verify' in insys_status.blocking_reason()


def test_legacy_busy_file_requires_stop_or_reboot(status, monkeypatch):
    status.write_text('Status:  On\n')
    assert 'without owner information' in insys_status.blocking_reason()
    monkeypatch.setattr(insys_status, '_legacy_previous_boot', lambda path: True)
    assert insys_status.blocking_reason() is None
    assert status.read_text() == 'Status:  On\n'


def test_canonical_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    expected = Path(insys_status.__file__).resolve().parents[2] / 'libs/status'
    monkeypatch.chdir(tmp_path)
    assert insys_status.status_path() == expected


def test_linux_process_start_parsing_with_parentheses(monkeypatch):
    stat = '42 (worker (preview)) S ' + ' '.join(['0'] * 18 + ['12345', '0'])
    monkeypatch.setattr(Path, 'read_text', lambda self: stat)
    assert insys_status.process_identity(42) == ('S', '12345')


def test_legacy_reboot_uses_file_timestamp(tmp_path, monkeypatch):
    path = tmp_path / 'status'
    path.write_text('Status:  On\n')
    monkeypatch.setattr(Path, 'read_text', lambda self: 'cpu 0 0\nbtime 100\n')
    os.utime(path, (90, 90))
    assert insys_status._legacy_previous_boot(path)
    os.utime(path, (110, 110))
    assert not insys_status._legacy_previous_boot(path)


def test_status_write_failure_prevents_hardware_initialization(board, monkeypatch):
    monkeypatch.setattr(insys_status, '_write', Mock(side_effect=PermissionError('read-only status')))
    with pytest.raises(PermissionError):
        board.pulser_open()
    board.initBrd.assert_not_called()
    board.pulser_close()
    board.closeBrd.assert_not_called()


def test_successful_close_can_retry_failed_status_write(board, status, monkeypatch):
    board.pulser_open()
    write = insys_status._write
    monkeypatch.setattr(insys_status, '_write', Mock(side_effect=PermissionError('status write failed')))
    with pytest.raises(PermissionError):
        board.pulser_close()
    assert status.read_text().startswith('Status:  On\n')
    monkeypatch.setattr(insys_status, '_write', write)
    board.pulser_close()
    assert insys_status.blocking_reason() is None
    board.closeBrd.assert_called_once()


def test_stop_during_initialization_cannot_clear_unreleased_board(board):
    board.initBrd.side_effect = board.pulser_close
    with pytest.raises(RuntimeError, match='requires reboot'):
        board.pulser_open()
    assert insys_status.blocking_reason() == insys_status.REBOOT_REQUIRED
    board.closeBrd.assert_not_called()


def test_unknown_boot_prevents_claim_but_allows_read_only_test(board, status, monkeypatch):
    monkeypatch.setattr(insys_status, 'boot_id', lambda: None)
    board.test_flag = 'test'
    board.pulser_open()
    board.test_flag = 'None'
    with pytest.raises(RuntimeError, match='Cannot identify'):
        board.pulser_open()
    assert not status.exists()
    board.initBrd.assert_not_called()


@pytest.fixture
def window(status, monkeypatch, tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])
    script = tmp_path / 'script.py'
    script.write_text('pass\n')
    window = SimpleNamespace(
        script=str(script), script_queue=QueueList(None), queue=0,
        process_python=Mock(), process_test=Mock(), text_errors=Mock(),
        checkTests=Mock(), button_start=Mock(), button_test=Mock(),
        main_button_styles={'PRIMARY_BUTTON_STYLE': '', 'WORKSPACE_ACTIVE_STYLE': '', 'WORKSPACE_ACTION_STYLE': ''},
        test_flag=0, checked=1, flag_opened_script_changed=0,
        cached_stamp=script.stat().st_mtime, cached_stamp2=script.stat().st_mtime,
        system_encoding='utf-8', success=True,
        process_phasing=Mock(), process_awg_phasing=Mock(),
    )
    window.process_python.state.return_value = QtCore.QProcess.ProcessState.NotRunning
    window.checkTests.checkState.return_value = QtCore.Qt.CheckState.Unchecked
    window._fpga_blocked = MethodType(MainExtended._fpga_blocked, window)
    window.test = MethodType(MainWindow.test, window)
    yield window
    window.script_queue.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('tests', [QtCore.Qt.CheckState.Checked, QtCore.Qt.CheckState.Unchecked])
@pytest.mark.parametrize('queued', [False, True])
def test_busy_guard_blocks_cached_disabled_and_queued_runs(window, tests, queued):
    insys_status.claim()
    window.checkTests.checkState.return_value = tests
    if queued:
        window.script_queue['0'] = window.script
    original = window.script_queue.values()
    MainExtended.start_experiment(window)
    window.process_python.start.assert_not_called()
    window.process_test.start.assert_not_called()
    assert window.script_queue.values() == original


def test_guard_rechecks_after_preflight(window):
    window.checkTests.checkState.return_value = QtCore.Qt.CheckState.Checked
    window.test = lambda name: insys_status.claim()
    MainExtended.start_experiment(window)
    window.process_python.start.assert_not_called()


def test_idle_phasing_windows_do_not_block(window):
    window.process_phasing.state.return_value = QtCore.QProcess.ProcessState.Running
    window.process_awg_phasing.state.return_value = QtCore.QProcess.ProcessState.Running
    MainExtended.start_experiment(window)
    window.process_python.start.assert_called_once()


def test_failed_test_does_not_clear_running_owner(window, status):
    insys_status.claim()
    original = status.read_bytes()
    process = Mock()
    process.readAllStandardOutput.return_value = QtCore.QByteArray()
    process.readAllStandardError.return_value = QtCore.QByteArray(b'Invalid script')
    MainExtended.on_finished_checking(window, 1, QtCore.QProcess.ExitStatus.NormalExit, Mock(), process)
    assert not window.success
    assert status.read_bytes() == original


@pytest.mark.parametrize('termination', ['normal', 'stop', 'exception', 'interrupt'])
def test_real_deer_script_termination(board, monkeypatch, termination):
    import numpy as np
    from atomize.general_modules import general_functions as general
    from atomize.general_modules import csv_opener_saver as openfile

    filename = Path(__file__).resolve().parents[1] / 'atomize/script_examples/EPR_endstation/Pulsed_EPR/AWG/DEER/0_deer_for_test.py'
    for module_name, class_name, instance in (
        ('Insys_FPGA', 'Insys_FPGA', board),
        ('Micran_X_band_MW_bridge_v2', 'Micran_X_band_MW_bridge_v2', Mock()),
        ('Lakeshore_335', 'Lakeshore_335', Mock()),
        ('BH_15', 'BH_15', Mock()),
    ):
        module = importlib.import_module('atomize.device_modules.' + module_name)
        monkeypatch.setattr(module, class_name, lambda instance=instance: instance)
    saver = Mock()
    monkeypatch.setattr(openfile, 'Saver_Opener', lambda: saver)
    for name in ('pulser_pulse', 'awg_pulse', 'digitizer_decimation', 'pulser_default_synt',
                 'digitizer_number_of_averages', 'pulser_update', 'awg_next_phase',
                 'pulser_shift', 'awg_shift', 'pulser_pulse_reset', 'awg_pulse_reset', 'pulser_pulse_list'):
        setattr(board, name, Mock())
    board.pulser_repetition_rate = Mock(return_value='1000 Hz')
    board.count_ip = Mock(return_value=np.array([1]))
    handlers = {}
    monkeypatch.setattr(signal, 'signal', lambda number, handler: handlers.update({number: handler}))
    monkeypatch.setattr(general, 'scans', lambda scans: [1])
    monkeypatch.setattr(general, 'fmt', lambda value, width: str(value))
    monkeypatch.setattr(general, 'message', Mock())
    monkeypatch.setattr(general, 'plot_2d', Mock())
    def curve(*args, **kwargs):
        if termination == 'stop':
            handlers[signal.SIGTERM](signal.SIGTERM, None)
        if termination == 'exception':
            raise ValueError('Acquisition failed')
        if termination == 'interrupt':
            raise KeyboardInterrupt
        return None, None
    board.digitizer_get_curve = curve
    if termination == 'normal':
        runpy.run_path(str(filename))
        assert insys_status.blocking_reason() is None
        board.closeBrd.assert_called_once()
    elif termination == 'stop':
        with pytest.raises(NameError, match='file_data'):
            runpy.run_path(str(filename))
        assert insys_status.blocking_reason() is None
        board.closeBrd.assert_called_once()
        saver.save_data.assert_not_called()
    else:
        with pytest.raises(ValueError if termination == 'exception' else KeyboardInterrupt):
            runpy.run_path(str(filename))
        board.closeBrd.assert_not_called()
        assert insys_status.blocking_reason()
        monkeypatch.setattr(insys_status, 'process_identity', Mock(side_effect=FileNotFoundError))
        assert insys_status.blocking_reason() == insys_status.REBOOT_REQUIRED
