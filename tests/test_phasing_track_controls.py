"""Track controls retain references until explicitly switched off."""

import importlib
import json
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, mock_open

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton


@pytest.fixture(params=['awg_phasing_insys', 'phasing_insys'])
def track_window(request, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])
    module = importlib.import_module('atomize.control_center.' + request.param)
    cls = module.MainWindow
    window = SimpleNamespace(
        is_experiment=False, is_testing=False, stop_requested=False, l_mode=0,
        live_edit_on=0, fft=1, quad=0, opened=1, exit_clicked=0,
        p1_length='100 ns', cur_win_left=0, cur_win_right=10, decimation=1,
        parent_conn_dig=Mock(), digitizer_process=Mock(pid=1234, exitcode=0),
        button_track=QPushButton('T'), message=Mock(), errors=Mock(),
        timer=Mock(), monitor_timer=Mock(), message_panel=Mock(),
        progress_bar=Mock(), button_blue=Mock(), button_update=Mock(),
        button_start_exp=Mock(), run_main_experiment=Mock(), run_experiment=Mock(),
    )
    window.button_track.setCheckable(True)
    window.parent_conn_dig.poll.return_value = False
    window.digitizer_process.is_alive.return_value = True
    window.timer.isActive.return_value = True
    for name in ('_track_available', '_live_run_alive', 'track_curves', '_track_command',
                 'clear_track', 'check_messages', 'check_process_status', 'parse_message', 'dig_stop'):
        setattr(window, name, MethodType(getattr(cls, name), window))
    for lock in ('field_param', 'temp_param'):
        monkeypatch.setattr(getattr(module, lock), 'clear_lock', Mock())
    yield window
    window.button_track.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('l_mode', [0, 1])
def test_track_captures_both_preview_modes_without_live_edit(track_window, l_mode):
    track_window.l_mode = l_mode
    track_window.button_track.setChecked(True)

    track_window.track_curves()

    assert track_window.button_track.isChecked()
    track_window.message.assert_called_once()
    command = track_window.message.call_args.args[0]
    assert command.startswith('track ')
    assert json.loads(command[6:]) == {'action': 'capture', 'pid': 1234, 'fft': True, 'quad': 0}


@pytest.mark.parametrize('state', ['preflight', 'experiment', 'stopped'])
def test_track_cannot_activate_outside_running_preview(track_window, state):
    track_window.is_testing = state == 'preflight'
    track_window.is_experiment = state == 'experiment'
    track_window.digitizer_process.is_alive.return_value = state != 'stopped'
    track_window.button_track.setChecked(True)

    track_window.track_curves()

    assert not track_window.button_track.isChecked()
    track_window.message.assert_not_called()


@pytest.mark.parametrize('state', ['preflight', 'experiment', 'stopped'])
def test_track_can_always_be_switched_off(track_window, state):
    track_window.is_testing = state == 'preflight'
    track_window.is_experiment = state == 'experiment'
    track_window.digitizer_process.is_alive.return_value = state != 'stopped'
    track_window.button_track.setChecked(False)

    track_window.track_curves()

    track_window.message.assert_called_once()
    command = track_window.message.call_args.args[0]
    assert json.loads(command[6:])['action'] == 'clear'
    assert not track_window.button_track.isEnabled()


def test_track_remains_checked_and_enabled_across_worker_restart(track_window):
    track_window.button_track.setChecked(True)
    track_window.digitizer_process.is_alive.return_value = False
    track_window.stop_requested = True

    track_window.check_messages()

    assert track_window.button_track.isChecked()
    assert track_window.button_track.isEnabled()
    track_window.message.assert_not_called()

    track_window.digitizer_process.pid = 5678
    track_window.digitizer_process.is_alive.return_value = True
    track_window.stop_requested = False
    track_window.check_messages()

    assert track_window.button_track.isChecked()
    assert track_window.button_track.isEnabled()
    track_window.message.assert_not_called()


def test_track_off_stays_disabled_after_worker_stops(track_window):
    track_window.digitizer_process.is_alive.return_value = False

    track_window.check_messages()

    assert not track_window.button_track.isChecked()
    assert not track_window.button_track.isEnabled()
    track_window.message.assert_not_called()


def test_stopping_preview_preserves_track(track_window, monkeypatch):
    track_window.button_track.setChecked(True)
    monkeypatch.setattr('builtins.open', mock_open())

    track_window.dig_stop()

    assert track_window.stop_requested
    assert track_window.button_track.isChecked()
    assert track_window.button_track.isEnabled()
    track_window.message.assert_not_called()


def test_worker_error_preserves_track(track_window):
    track_window.button_track.setChecked(True)
    track_window.parent_conn_dig.recv.return_value = ('Error', 'Preview failed')

    track_window.parse_message()

    assert track_window.button_track.isChecked()
    assert track_window.button_track.isEnabled()
    track_window.message.assert_called_once_with('Preview failed')
