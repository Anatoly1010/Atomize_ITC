"""Stop during preflight must never start acquisition."""

import importlib
from types import SimpleNamespace, MethodType
from unittest.mock import Mock, mock_open

import pytest


@pytest.mark.parametrize('name', ['cw_control', 'tune_preset', 'phasing_insys', 'awg_phasing_insys'])
@pytest.mark.parametrize('action', ['complete', 'stop', 'exit', 'broken_pipe'])
@pytest.mark.parametrize('experiment', [False, True])
def test_preflight_completion(monkeypatch, name, action, experiment):
    module = importlib.import_module('atomize.control_center.' + name)
    cls = module.MainWindow
    phasing = 'phasing' in name
    process = Mock(exitcode=0)
    process.is_alive.return_value = True
    conn = Mock()
    conn.poll.return_value = False
    window = SimpleNamespace(
        stop_requested=False, exit_clicked=0, is_testing=True, last_error=False,
        is_experiment=experiment, opened=0, rep_active=1,
        p1_length='100 ns', cur_win_left=0, cur_win_right=10, decimation=1,
        timer=Mock(), monitor_timer=Mock(), progress_bar=Mock(), errors=Mock(),
        button_start=Mock(), button_start_exp=Mock(), button_update=Mock(),
        run_main_experiment=Mock(), run_experiment=Mock(), stop_rep_countdown=Mock(),
        start_rep_countdown=Mock(), message=Mock(), button_blue=Mock(),
    )
    setattr(window, 'digitizer_process' if phasing else 'exp_process', process)
    setattr(window, 'parent_conn_dig' if phasing else 'parent_conn', conn)
    window.check_process_status = MethodType(cls.check_process_status, window)
    window.parse_message = MethodType(cls.parse_message, window)
    if phasing:
        window.dig_stop = MethodType(cls.dig_stop, window)
    for lock in ('field_param', 'temp_param'):
        if hasattr(module, lock):
            monkeypatch.setattr(getattr(module, lock), 'clear_lock', Mock())
    monkeypatch.setattr('builtins.open', mock_open())
    if action == 'exit':
        cls.turn_off(window)
    elif action in ('stop', 'broken_pipe'):
        if action == 'broken_pipe':
            conn.send.side_effect = BrokenPipeError
        getattr(cls, 'dig_stop' if phasing else 'stop')(window)
    process.is_alive.return_value = False
    cls.check_messages(window)
    if action == 'complete':
        expected = window.run_experiment if phasing and experiment else window.run_main_experiment
        expected.assert_called_once()
    else:
        window.run_main_experiment.assert_not_called()
        window.run_experiment.assert_not_called()
        window.start_rep_countdown.assert_not_called()
        window.errors.appendPlainText.assert_not_called()
        assert window.stop_requested
        window.progress_bar.setValue.assert_called_with(0)
    assert not window.is_testing
