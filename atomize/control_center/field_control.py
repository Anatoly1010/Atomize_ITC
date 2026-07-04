#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QEventLoop, QTimer, QEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QGridLayout, QFrame
#import atomize.device_modules.ITC_FC as itc
import atomize.device_modules.BH_15 as itc
import atomize.general_modules.general_functions as general
import atomize.control_center.field_param as field_param

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)

        # The window must open even when the magnet PSU / BH-15 is powered off or
        # the GPIB bus is down. Connecting is deferred to _try_connect(), which
        # swallows the SystemExit / exception the module raises on a dead bus and
        # leaves us in an "offline" mode with a Reconnect button.
        self.itc_fc = None
        self.device_ok = False

        self.cur_field = 0
        self.cur_field_2 = 0
        self.field_locked = False
        self.path_status_file = field_param.path()

        self.design()

        self._try_connect()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_field_status)
        self.status_timer.start(300)

        self.read_no_set_field()
        self.cur_field = self.cur_field_2
        self._set_online_ui(self.device_ok)

    def design(self):

        self.setObjectName("MainWindow")
        self.setWindowTitle("Field Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_f.png')
        self.setWindowIcon( QIcon(icon_path) )

        centralwidget = QWidget(self)
        self.setCentralWidget(centralwidget)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 10, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        centralwidget.setLayout(gridLayout)

        # ---- Labels & Inputs ----
        labels = [("Set Magnetic Field", "label_1"), ("Field Setting Step", "label_2") ]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(190, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        self.label_lock = QLabel("")
        self.label_lock.setFixedSize(320, 26)
        self.label_lock.setStyleSheet("QLabel { color : rgb(211, 194, 78); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "Set_point", "field", self.set_field, 0, 15100, 0, 0.5, 2, " G"), 
                        (QDoubleSpinBox, "box_ini", "initialization_step", self.set_ini, 0.1, 100, 10, 1, 1, " G")
                        ]

        for widget_class, attr_name, par_name, func, v_min, v_max, cur_val, v_step, dec, suf in double_boxes:
            spin_box = widget_class()
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setRange(v_min, v_max)
                spin_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")                
            else:
                spin_box.setRange(int(v_min), int(v_max))
                spin_box.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")                
            spin_box.setSingleStep(v_step)
            spin_box.setValue(cur_val)
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setDecimals(dec)
            spin_box.setSuffix(suf)
            spin_box.valueChanged.connect(func)
            spin_box.setFixedSize(130, 26)
            spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            
            spin_box.setKeyboardTracking( False )
            
            setattr(self, attr_name, spin_box)
            if isinstance(spin_box, QDoubleSpinBox):
                setattr(self, par_name, float(spin_box.value()))
            else:
                setattr(self, par_name, int(spin_box.value()))


        # ---- Buttons ----
        buttons = [("Exit", "button_off", self.turn_off),
                   ("Set Zero Field", "button_stop", self.update_stop),
                   ("Reconnect", "button_reconnect", self.reconnect) ]

        for name, attr_name, func in buttons:
            btn = QPushButton(name)
            btn.setFixedSize(140, 40)
            btn.clicked.connect(func)
            btn.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
            setattr(self, attr_name, btn)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line


        # ---- Layout placement ----
        gridLayout.addWidget(self.label_1, 0, 0)
        gridLayout.addWidget(self.Set_point, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.box_ini, 1, 1)
        gridLayout.addWidget(self.label_lock, 2, 0, 1, 2)

        gridLayout.addWidget(hline(), 3, 0, 1, 2)

        gridLayout.addWidget(self.button_stop, 4, 0)
        gridLayout.addWidget(self.button_off, 5, 0)
        gridLayout.addWidget(self.button_reconnect, 6, 0)

        gridLayout.setRowStretch(7, 2)
        gridLayout.setColumnStretch(6, 2)

    def refresh_field_status(self):
        locked = field_param.is_locked()
        if locked:
            self.read_no_set_field()
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.cur_field_2)
            self.Set_point.blockSignals(False)
        self.apply_field_lock_state(locked)

    def apply_field_lock_state(self, locked=None):
        # While offline the enabled/disabled state is owned by _set_online_ui;
        # don't let the lock logic re-enable the setter widgets under it.
        if not self.device_ok:
            return
        if locked is None:
            locked = field_param.is_locked()
        self.field_locked = locked

        self.Set_point.setReadOnly(locked)
        self.Set_point.setEnabled(True)
        self.box_ini.setEnabled(not locked)
        self.button_stop.setEnabled(not locked)

        if locked:
            source = field_param.lock_source()
            source_text = source.replace('_', ' ') if source else 'experiment'
            self.label_1.setText("Current Magnetic Field")
            self.label_lock.setText(f"Field control locked ({source_text} running)")
        else:
            self.label_1.setText("Set Magnetic Field")
            self.label_lock.setText("")

    # ---------------------------------------------------------- connection mgmt
    def _try_connect(self):
        """Open the BH-15 magnet controller. Never raises: the module sys.exit()s
        (SystemExit) or throws when the GPIB bus / magnet PSU is down; swallow it
        and stay offline."""
        try:
            self.itc_fc = itc.BH_15()
            self.device_ok = getattr(self.itc_fc, 'status_flag', 1) == 1
        except SystemExit:
            self.itc_fc = None
            self.device_ok = False
        except Exception:
            self.itc_fc = None
            self.device_ok = False
        return self.device_ok

    def _go_offline(self):
        """A device call failed mid-session: drop to offline instead of dying."""
        self.device_ok = False
        self.itc_fc = None
        self._set_online_ui(False)

    def _set_online_ui(self, online):
        """Match the widgets to the connection state: online hands control back to
        the field-lock logic; offline disables the setter widgets, shows a banner
        and enables the Reconnect button."""
        self.button_reconnect.setEnabled(not online)
        if online:
            self.apply_field_lock_state()
        else:
            self.Set_point.setReadOnly(True)
            self.Set_point.setEnabled(False)
            self.box_ini.setEnabled(False)
            self.button_stop.setEnabled(False)
            self.label_1.setText("Set Magnetic Field")
            self.label_lock.setText("Device offline")

    def reconnect(self):
        self.label_lock.setText("Connecting...")
        QApplication.processEvents()
        self._try_connect()
        self._set_online_ui(self.device_ok)

    def closeEvent(self, event):
        event.ignore()

        if self.field_locked:
            sys.exit()

        # Offline: nothing to ramp down and no bus to talk to -> just close.
        if not self.device_ok:
            sys.exit()

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        QApplication.processEvents()

        while self.cur_field > ( self.initialization_step + 1 ):
            self.cur_field = self.itc_fc.magnet_field( self.cur_field - self.initialization_step )
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.cur_field)
            self.Set_point.blockSignals(False)
            loop = QEventLoop()
            QTimer.singleShot(15, loop.quit)
            loop.exec()
            
            QApplication.processEvents()

        self.cur_field = 0
        self.cur_field_2 = 0
        self.field = 0
        self.itc_fc.magnet_field( self.cur_field )
        self.Set_point.setValue(self.cur_field)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")

        sys.exit()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self.on_window_focused()
        super().changeEvent(event)

    def on_window_focused(self):
        self.refresh_field_status()

    def quit(self):
        """
        A function to quit the programm
        """
        if self.field_locked:
            sys.exit()

        # Offline: nothing to ramp down and no bus to talk to -> just close.
        if not self.device_ok:
            sys.exit()

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        QApplication.processEvents()

        while self.cur_field > ( self.initialization_step + 1 ):
            self.cur_field = self.itc_fc.magnet_field( self.cur_field - self.initialization_step )
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.cur_field)
            self.Set_point.blockSignals(False)
            loop = QEventLoop()
            QTimer.singleShot(15, loop.quit)
            loop.exec()
            
            QApplication.processEvents()

        self.cur_field = 0
        self.cur_field_2 = 0
        self.field = 0
        self.itc_fc.magnet_field( self.cur_field )
        self.Set_point.setValue(self.cur_field)
        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")

        sys.exit()

    def set_ini(self):
        """
        A function to change inizialization step
        """
        if self.field_locked:
            self.box_ini.blockSignals(True)
            self.box_ini.setValue(self.initialization_step)
            self.box_ini.blockSignals(False)
            return
        self.initialization_step = int( self.box_ini.value() )

    def set_field(self):
        """
        A function to change set point
        """
        if self.field_locked:
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.cur_field_2)
            self.Set_point.blockSignals(False)
            return

        # No magnet controller -> can't ramp; ignore the request (the setter is
        # disabled while offline, this only guards a programmatic trigger).
        if not self.device_ok:
            return

        self.read_no_set_field()
        self.field = float( self.Set_point.value() )
        self.write_field(self.field)

        if self.cur_field_2 != self.cur_field:
            self.itc_fc.magnet_setup( self.cur_field_2, 1 )
            self.itc_fc.magnet_field( self.cur_field_2 )

        self.cur_field = self.cur_field_2

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        QApplication.processEvents()
        
        if self.cur_field < self.field:
            while self.cur_field < self.field:
                self.cur_field = self.itc_fc.magnet_field( self.cur_field + self.initialization_step )
                self.Set_point.blockSignals(True)
                self.Set_point.setValue(self.cur_field)
                self.Set_point.blockSignals(False)
                loop = QEventLoop()
                QTimer.singleShot(15, loop.quit)
                loop.exec()
                
                QApplication.processEvents()

            self.cur_field = self.itc_fc.magnet_field( self.field )
            self.cur_field = self.field
            
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.cur_field)
            self.Set_point.blockSignals(False)
        else:
            while self.cur_field > self.field:
                self.cur_field = self.itc_fc.magnet_field( self.cur_field - self.initialization_step )
                self.Set_point.blockSignals(True)
                self.Set_point.setValue(self.cur_field)
                self.Set_point.blockSignals(False)
                loop = QEventLoop()
                QTimer.singleShot(15, loop.quit)
                loop.exec()
                
                QApplication.processEvents()

            self.cur_field = self.itc_fc.magnet_field( self.field )
            self.cur_field =  self.field 
            self.Set_point.blockSignals(True)
            self.Set_point.setValue(self.cur_field)
            self.Set_point.blockSignals(False)

        self.button_stop.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")

    def update_stop(self):
        """
        A function to stop oscilloscope
        """
        if self.field_locked:
            return
        self.Set_point.setValue( 0 )

    def turn_off(self):
        """
        A function to turn off a programm.
        """
        self.quit()

    def read_field(self):
        self.read_no_set_field()
        self.cur_field = self.cur_field_2
        self.Set_point.setValue(self.cur_field)

    def read_no_set_field(self):
        try:
            self.cur_field_2 = field_param.current_field()
        except (FileNotFoundError, ValueError):
            pass

    def write_field(self, field):
        if self.field_locked:
            return
        try:
            field_param.write_field(field)
        except OSError:
            pass

def main():
    """
    A function to run the main window of the programm.
    """
    app = QApplication(sys.argv)
    from atomize.general_modules.gui_style import apply_app_style
    apply_app_style(app, app_id='Atomize.ITC.FieldControl')
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
