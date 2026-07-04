#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QEventLoop, QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox,
                             QComboBox, QCheckBox, QPushButton, QGridLayout, QFrame)
import atomize.device_modules.Lakeshore_335 as ls
import atomize.general_modules.general_functions as general
import atomize.control_center.temp_param as temp_param
from atomize.general_modules.gui_style import CHECKBOX_STYLE

# Styling constants reused from the other control-center windows
_FG = "rgb(193, 202, 227)"
_LBL_NORMAL = "QLabel { color : rgb(193, 202, 227); font-weight: bold; }"
_LBL_GREEN = "QLabel { color : rgb(126, 211, 78); font-weight: bold; }"
_BUSY_BTN = ("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); "
             "border-style: outset; color: rgb(63, 63, 97); font-weight: bold; }")
_IDLE_BTN = ("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); "
             "border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } "
             "QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; "
             "font-weight: bold; }")

_LOCK_SOURCE = 'temp_control'
_HOLD_COUNT = 3          # consecutive in-band polls required before "reached"
_POLL_MS = 1000          # background/wait poll cadence (kept slow: GPIB is slow)


class MainWindow(QMainWindow):
    """
    A main window class for the Lakeshore temperature controller:
    setter (setpoint + heater), waiter (per-channel band around setpoint),
    notifier (visual busy state + log), and a cross-process lock so the GUI and
    an experiment never touch the same GPIB session at once.
    """
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.ls335 = None
        self.device_ok = False      # True only while the Lakeshore is connected

        self.point = 80.0
        self.cur_range = 'Off'
        self.waiting = False        # True only while our own Set & Wait loop runs
        self.holding_lock = False   # True while we own the cross-process lock
        self.stop_flag = False
        self.lock_banner = False    # cached "locked by another source" state

        self.design()

        # The window must open even when the Lakeshore is powered off: connect
        # defensively (base_device calls sys.exit() -> SystemExit on failure) and
        # fall back to an "offline" mode with a Reconnect button.
        self._try_connect()
        self._set_online_ui(self.device_ok)

        # Background poll: reads temp.param for lock state; touches the device
        # ONLY when we own the bus (nobody else is locked) and it is connected.
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.poll)
        self.status_timer.start(_POLL_MS)
        self.poll()

    # ------------------------------------------------------------------ design
    def design(self):
        self.setObjectName("MainWindow")
        self.setWindowTitle("Temperature Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_temp.png')
        self.setWindowIcon(QIcon(icon_path))

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        grid = QGridLayout()
        grid.setContentsMargins(15, 10, 10, 10)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(20)
        centralwidget.setLayout(grid)

        def label(text, w=190):
            lbl = QLabel(text)
            lbl.setFixedSize(w, 26)
            lbl.setStyleSheet("QLabel { color : %s; font-weight: bold; }" % _FG)
            return lbl

        def dspin(v_min, v_max, val, step, dec, suf):
            sb = QDoubleSpinBox()
            sb.setRange(v_min, v_max)
            sb.setStyleSheet("QDoubleSpinBox { color : %s; selection-background-color: "
                             "rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}" % _FG)
            sb.setSingleStep(step)
            sb.blockSignals(True)
            sb.setValue(val)
            sb.setDecimals(dec)
            sb.setSuffix(suf)
            sb.setFixedSize(130, 26)
            sb.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            sb.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            sb.setKeyboardTracking(False)
            sb.blockSignals(False)
            return sb

        def check(text, checked):
            cb = QCheckBox(text)
            cb.setChecked(checked)
            cb.setStyleSheet(CHECKBOX_STYLE)
            cb.setFixedSize(90, 26)
            return cb

        # ---- Setpoint & heater ----
        self.label_set = label("Set Temperature")
        self.Set_point = dspin(0.3, 320, self.point, 0.1, 2, " K")
        self.Set_point.valueChanged.connect(self.set_point)

        self.label_heater = label("Heater Range")
        self.combo_range = QComboBox()
        self.combo_range.blockSignals(True)
        self.combo_range.addItems(["Off", "High", "Medium", "Low"])
        self.combo_range.setCurrentText("Off")
        self.combo_range.blockSignals(False)
        self.combo_range.currentIndexChanged.connect(self.heater_range)
        self.combo_range.setFixedSize(130, 26)
        self.combo_range.setStyleSheet(
            "QComboBox { color : %s; selection-color: rgb(211, 194, 78); "
            "selection-background-color: rgb(63, 63, 97); outline: none; }" % _FG)

        # ---- Live readback + per-channel gate ----
        self.label_A = label("A:  --- K", 150)
        self.check_A = check("wait", True)
        self.tol_A = dspin(0.01, 50, 0.5, 0.1, 2, " K")

        self.label_B = label("B:  --- K", 150)
        self.check_B = check("wait", True)
        self.tol_B = dspin(0.01, 50, 0.5, 0.1, 2, " K")

        # ---- Timeout ----
        self.label_timeout = label("Wait Timeout")
        self.timeout_box = dspin(0.1, 600, 30, 1, 1, " min")

        # ---- Status ----
        self.label_status = QLabel("")
        self.label_status.setFixedSize(360, 26)
        self.label_status.setStyleSheet("QLabel { color : rgb(211, 194, 78); font-weight: bold; }")

        # ---- Buttons ----
        self.button_wait = QPushButton("Set && Wait")
        self.button_stop = QPushButton("Stop")
        self.button_reconnect = QPushButton("Reconnect")
        self.button_off = QPushButton("Exit")
        for btn, func in ((self.button_wait, self.set_and_wait),
                          (self.button_stop, self.stop_wait),
                          (self.button_reconnect, self.reconnect),
                          (self.button_off, self.turn_off)):
            btn.setFixedSize(140, 40)
            btn.clicked.connect(func)
            btn.setStyleSheet(_IDLE_BTN)
        self.button_stop.setEnabled(False)

        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        # ---- Layout ----
        grid.addWidget(self.label_set, 0, 0)
        grid.addWidget(self.Set_point, 0, 1)
        grid.addWidget(self.label_heater, 1, 0)
        grid.addWidget(self.combo_range, 1, 1)

        grid.addWidget(hline(), 2, 0, 1, 3)

        grid.addWidget(self.label_A, 3, 0)
        grid.addWidget(self.check_A, 3, 1)
        grid.addWidget(self.tol_A, 3, 2)
        grid.addWidget(self.label_B, 4, 0)
        grid.addWidget(self.check_B, 4, 1)
        grid.addWidget(self.tol_B, 4, 2)

        grid.addWidget(self.label_timeout, 5, 0)
        grid.addWidget(self.timeout_box, 5, 1)

        grid.addWidget(self.label_status, 6, 0, 1, 3)

        grid.addWidget(hline(), 7, 0, 1, 3)

        grid.addWidget(self.button_wait, 8, 0)
        grid.addWidget(self.button_stop, 8, 1)
        grid.addWidget(self.button_off, 9, 0)
        grid.addWidget(self.button_reconnect, 9, 1)

        grid.setRowStretch(10, 2)
        grid.setColumnStretch(3, 2)

    # ---------------------------------------------------------- connection mgmt
    def _try_connect(self):
        """Attempt to open the Lakeshore. Never raises: on failure the module
        calls sys.exit() (SystemExit); we swallow it and stay offline."""
        try:
            self.ls335 = ls.Lakeshore_335()
            self.device_ok = getattr(self.ls335, 'status_flag', 1) == 1
        except SystemExit:
            self.ls335 = None
            self.device_ok = False
        except Exception:
            self.ls335 = None
            self.device_ok = False
        return self.device_ok

    def _go_offline(self):
        """A device call failed mid-session: drop to offline instead of dying."""
        self.device_ok = False
        self.ls335 = None
        self._set_online_ui(False)

    def _set_online_ui(self, online):
        """Enable/disable the setter+waiter widgets to match connection state."""
        for w in (self.Set_point, self.combo_range, self.button_wait,
                  self.tol_A, self.tol_B, self.check_A, self.check_B,
                  self.timeout_box):
            w.setEnabled(online)
        self.Set_point.setReadOnly(not online)
        self.button_reconnect.setEnabled(not online)
        if not online:
            self.label_A.setText("A:  --- K")
            self.label_B.setText("B:  --- K")
            self.label_status.setText("Device offline")
        else:
            self.label_status.setText("")

    def reconnect(self):
        self.label_status.setText("Connecting...")
        QApplication.processEvents()
        self._try_connect()
        self._set_online_ui(self.device_ok)
        if self.device_ok:
            self.lock_banner = False
            self.poll()

    # -------------------------------------------------------------- device I/O
    def _safe_read(self, channel):
        """Read one channel; return float K or None on any failure (e.g. dead A)."""
        if not self.device_ok or self.ls335 is None:
            return None
        try:
            return float(self.ls335.tc_temperature(channel))
        except SystemExit:
            # base_device calls sys.exit() when the transport drops -> go offline
            self._go_offline()
            return None
        except Exception:
            return None

    def _fmt(self, value):
        return "%.2f K" % value if value is not None else "--- K"

    def _update_labels(self, t_a, t_b):
        self.label_A.setText("A:  " + self._fmt(t_a))
        self.label_B.setText("B:  " + self._fmt(t_b))

    def _read_device_and_publish(self):
        """We own the bus here: read both channels and mirror to temp.param."""
        t_a = self._safe_read('A')
        t_b = self._safe_read('B')
        self._update_labels(t_a, t_b)
        try:
            temp_param.write_status(setpoint=self.point, temp_a=t_a, temp_b=t_b)
        except OSError:
            pass

    def _show_from_file(self):
        """Someone else owns the bus: display last-published values, no device I/O."""
        data = temp_param.read()
        self.label_A.setText("A:  " + data.get('TempA', '---') + " K")
        self.label_B.setText("B:  " + data.get('TempB', '---') + " K")

    # ----------------------------------------------------------------- polling
    def poll(self):
        # While our own wait loop runs it owns the reads/labels; don't double up.
        if self.waiting:
            return
        if not self.device_ok:
            return
        if temp_param.is_locked():
            self.apply_lock_state(True)
            self._show_from_file()
        else:
            self.apply_lock_state(False)
            self._read_device_and_publish()

    def apply_lock_state(self, locked):
        if locked == self.lock_banner:
            return
        self.lock_banner = locked
        self.Set_point.setReadOnly(locked)
        self.combo_range.setEnabled(not locked)
        self.button_wait.setEnabled(not locked)
        self.tol_A.setEnabled(not locked)
        self.tol_B.setEnabled(not locked)
        self.check_A.setEnabled(not locked)
        self.check_B.setEnabled(not locked)
        self.timeout_box.setEnabled(not locked)
        if locked:
            source = temp_param.lock_source() or 'experiment'
            self.label_status.setText("Locked (%s running)" % source.replace('_', ' '))
        else:
            self.label_status.setText("")

    # ------------------------------------------------------------------ setter
    def set_point(self):
        if self.lock_banner or not self.device_ok:
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.point)
            self.Set_point.blockSignals(False)
            return
        self.point = round(float(self.Set_point.value()), 3)
        try:
            self.ls335.tc_setpoint(self.point)
        except SystemExit:
            self._go_offline()
            return
        try:
            temp_param.write_status(setpoint=self.point)
        except OSError:
            pass

    def heater_range(self):
        if self.lock_banner or not self.device_ok:
            return
        self.cur_range = self.combo_range.currentText()
        try:
            self.ls335.tc_heater_range(self.chose_range(self.cur_range))
        except SystemExit:
            self._go_offline()

    def chose_range(self, text):
        return {'High': '50 W', 'Medium': '5 W', 'Low': '0.5 W'}.get(text, 'Off')

    # ------------------------------------------------------------------ waiter
    def _channel_ok(self, temp, enabled, tol):
        return bool(enabled) and temp is not None and abs(temp - self.point) < float(tol)

    def _in_band(self):
        """Return (all_enabled_in_band, t_a, t_b, a_ok, b_ok)."""
        t_a = self._safe_read('A')
        t_b = self._safe_read('B')
        a_on, b_on = self.check_A.isChecked(), self.check_B.isChecked()
        a_ok = self._channel_ok(t_a, a_on, self.tol_A.value())
        b_ok = self._channel_ok(t_b, b_on, self.tol_B.value())
        enabled = [ok for on, ok in ((a_on, a_ok), (b_on, b_ok)) if on]
        ok = all(enabled) if enabled else False
        return ok, t_a, t_b, a_ok, b_ok

    def _color_labels(self, a_ok, b_ok):
        """Green while an enabled channel is inside its threshold; else default."""
        self.label_A.setStyleSheet(_LBL_GREEN if a_ok else _LBL_NORMAL)
        self.label_B.setStyleSheet(_LBL_GREEN if b_ok else _LBL_NORMAL)

    def set_and_wait(self):
        # Guards: offline, another driver holds the bus, or we're already waiting.
        if self.lock_banner or self.waiting or not self.device_ok:
            return
        if not (self.check_A.isChecked() or self.check_B.isChecked()):
            self.label_status.setText("Enable at least one channel to wait")
            return

        # Claim the controller so nothing else touches the GPIB while we wait.
        temp_param.set_lock(_LOCK_SOURCE)
        self.holding_lock = True
        self.waiting = True
        self.stop_flag = False
        self.button_wait.setStyleSheet(_BUSY_BTN)
        self.button_wait.setEnabled(False)
        self.button_stop.setEnabled(True)

        deadline = time.monotonic() + float(self.timeout_box.value()) * 60.0
        held = 0
        result = 'Timeout'
        try:
            # (Re)assert setpoint on the device before waiting.
            self.point = round(float(self.Set_point.value()), 3)
            self.ls335.tc_setpoint(self.point)

            while time.monotonic() < deadline:
                if self.stop_flag:
                    result = 'Aborted'
                    break
                if not self.device_ok:
                    result = 'Device lost'
                    break
                ok, t_a, t_b, a_ok, b_ok = self._in_band()
                self._update_labels(t_a, t_b)
                self._color_labels(a_ok, b_ok)
                try:
                    temp_param.write_status(setpoint=self.point, temp_a=t_a, temp_b=t_b)
                except OSError:
                    pass
                held = held + 1 if ok else 0
                self.label_status.setText("Waiting...  A: %s  B: %s"
                                          % (self._fmt(t_a), self._fmt(t_b)))
                if held >= _HOLD_COUNT:
                    result = 'Reached'
                    break
                # sleep until the next poll, but never past the deadline
                nap = min(_POLL_MS, max(0, int((deadline - time.monotonic()) * 1000)))
                if nap <= 0:
                    break
                loop = QEventLoop()
                QTimer.singleShot(nap, loop.quit)
                loop.exec()
                QApplication.processEvents()
        except SystemExit:
            # the Lakeshore dropped while we were driving it
            self._go_offline()
            result = 'Device lost'
        finally:
            self.waiting = False
            self.holding_lock = False
            temp_param.clear_lock()
            self._color_labels(False, False)   # revert channel labels to default
            self.button_wait.setStyleSheet(_IDLE_BTN)
            self.button_stop.setEnabled(False)
            if self.device_ok:
                self.button_wait.setEnabled(True)
            else:
                self._set_online_ui(False)

        self.label_status.setText("%s (setpoint %.2f K)" % (result, self.point))
        general.message("Temperature %s: setpoint %.2f K" % (result.lower(), self.point))

    def stop_wait(self):
        self.stop_flag = True

    # ------------------------------------------------------------------- close
    def closeEvent(self, event):
        self.stop_flag = True
        if self.holding_lock:
            temp_param.clear_lock()
            self.holding_lock = False
        event.accept()

    def quit(self):
        self.stop_flag = True
        if self.holding_lock:
            temp_param.clear_lock()
            self.holding_lock = False
        sys.exit()

    def turn_off(self):
        self.quit()


def main():
    app = QApplication(sys.argv)
    from atomize.general_modules.gui_style import apply_app_style
    apply_app_style(app, app_id='Atomize.ITC.TempControl')
    main = MainWindow()
    main.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
