"""Preview-only auto controls and the zero-order phase feedback path."""

import importlib
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox


@pytest.fixture(params=['awg_phasing_insys', 'phasing_insys'])
def auto_window(request, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication.instance() or QApplication([])
    cls = importlib.import_module('atomize.control_center.' + request.param).MainWindow
    window = SimpleNamespace(
        is_experiment=False, is_testing=False, l_mode=0, live_edit_on=0,
        opened=0, zero_order=0.0, deg_rad=180 / np.pi,
        win_width=100.0, time_per_point=0.4,
        digitizer_process=Mock(), parent_conn_dig=Mock(), message=Mock(),
        errors=Mock(), Quad_cor=QCheckBox(), Zero_order=QDoubleSpinBox(),
    )
    window.digitizer_process.is_alive.return_value = True
    window.Zero_order.setRange(-0.1, 360.1)
    window.Zero_order.setDecimals(4)
    for name in ('auto_phase', 'auto_window', '_live_run_alive', 'parse_message', 'zero_order_func'):
        setattr(window, name, MethodType(getattr(cls, name), window))
    window.Zero_order.valueChanged.connect(lambda _: window.zero_order_func())
    yield window
    window.Zero_order.deleteLater()
    window.Quad_cor.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('action', ['auto_phase', 'auto_window'])
@pytest.mark.parametrize('blocked_state', ['preflight', 'experiment', 'stopped'])
def test_auto_controls_reject_non_live_preview(auto_window, action, blocked_state):
    if blocked_state == 'preflight':
        auto_window.is_testing = True
    elif blocked_state == 'experiment':
        auto_window.is_experiment = True
    else:
        auto_window.digitizer_process.is_alive.return_value = False

    getattr(auto_window, action)()

    auto_window.parent_conn_dig.send.assert_not_called()
    auto_window.message.assert_called_once()


@pytest.mark.parametrize('action, command', [('auto_phase', 'AP'), ('auto_window', 'AW250')])
@pytest.mark.parametrize('l_mode', [0, 1])
def test_auto_controls_allow_preview_without_live_edit(auto_window, action, command, l_mode):
    auto_window.l_mode = l_mode
    getattr(auto_window, action)()

    auto_window.parent_conn_dig.send.assert_called_once_with(command)
    auto_window.message.assert_not_called()


def test_auto_phase_updates_spinbox_and_worker_phase(auto_window):
    auto_window.parent_conn_dig.recv.return_value = ('AutoPhase', (123.456789, 55.0))

    auto_window.parse_message()

    assert auto_window.Zero_order.value() == 123.4568
    assert auto_window.zero_order == pytest.approx(np.radians(123.4568))
    auto_window.parent_conn_dig.send.assert_called_once()
    command = auto_window.parent_conn_dig.send.call_args.args[0]
    assert command.startswith('ZO')
    assert float(command[2:]) == pytest.approx(np.radians(123.4568))


def test_auto_phase_response_ignored_after_frequency_correction_enabled(auto_window):
    auto_window.Zero_order.setValue(42.0)
    auto_window.parent_conn_dig.send.reset_mock()
    auto_window.Quad_cor.setChecked(True)
    auto_window.parent_conn_dig.recv.return_value = ('AutoPhase', (123.456789, 55.0))

    auto_window.parse_message()

    assert auto_window.Zero_order.value() == 42.0
    assert auto_window.zero_order == pytest.approx(np.radians(42.0))
    auto_window.parent_conn_dig.send.assert_not_called()


def test_auto_phase_request_rejects_frequency_correction(auto_window):
    auto_window.Quad_cor.setChecked(True)

    auto_window.auto_phase()

    auto_window.parent_conn_dig.send.assert_not_called()
    auto_window.message.assert_called_once()
