# -*- coding: utf-8 -*-

import os
import re
import sys
import math
import time
import json
import tempfile
import traceback
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QTextEdit, QGridLayout, QFrame, QCheckBox, QFileDialog, QVBoxLayout, QTabWidget, QScrollArea, QHBoxLayout, QPlainTextEdit, QProgressBar,  QTreeView, QHeaderView, QSizeGrip, QLineEdit, QFileIconProvider
from PyQt6.QtGui import QIcon, QColor, QAction, QTextCursor
from PyQt6.QtCore import Qt, QTimer
import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.last_dir as ldir
import atomize.control_center.field_param as field_param
import atomize.control_center.temp_param as temp_param
from atomize.control_center.time_log_spinbox import TimeLogSpinBox
# Shared dark-theme styling; apply_app_style() pins this process to the Fusion
# style so QComboBox / QSpinBox / QLineEdit render identically on Linux/Windows.
from atomize.general_modules.gui_style import apply_app_style, CHECKBOX_STYLE

# Reload-signal file written by the Sequence Calculator (sequence_calculator.py).
# While this window is open we poll it and reload the named preset when the
# nonce changes for our channel, so "Open in AWG" updates the window in place.
SEQCALC_SIGNAL = os.path.join(tempfile.gettempdir(), 'atomize_seqcalc.param')
SEQCALC_CHANNEL = 'awg'

class MainWindow(QMainWindow):
    """
    A main window class
    """
    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window
        """
        super(MainWindow, self).__init__(*args, **kwargs)
        self.menu()

        #####
        try:
            path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', 'libs')
            os.chdir(path_to_main2) 
        except FileNotFoundError:
            path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', '..', 'libs')
            os.chdir(path_to_main2)
        #####
        
        self.awg_output_shift = 0 #494 # in ns

        # Phase correction
        self.deg_rad = 180 / np.pi #57.2957795131
        self.first_order_coef = 180 / np.pi * 1e-9
        self.sec_order_coef = 180 / np.pi * 1e-18

        # ---- Live Edit (no-restart re-arm) ----
        # When enabled, edits to a running preview's AWG amplitude / frequency /
        # start are pushed to the worker over the existing pipe and applied with
        # a live awg_update()/pulser_update() -- no card teardown. Debounced so a
        # burst of edits coalesces into one re-arm. live_sig captures the
        # structure the running worker was opened with (active AWG-pulse count,
        # phase-cycle length, decimation, laser mode); live_starts captures the
        # pulse start positions. A structural change, or a Start edit that would
        # overlap / reorder the sequence (changing dac_window), falls back to a
        # full restart. Initialised before design_tab_1(), because the pulse
        # spin-boxes fire their handlers (schedule_live_apply) during that build.
        self.live_edit_on = 0
        self.live_sig = None
        self.live_starts = ()
        self.live_timer = QTimer()
        self.live_timer.setSingleShot(True)
        self.live_timer.timeout.connect(self.live_apply)

        # ---- Link mode state ----
        # link_param selects which pulse parameter is coupled ('Off' when
        # disabled); link_factor maps pulse index -> weight (0 = No). Editing a
        # linked pulse's active parameter by delta shifts every other linked
        # pulse proportionally (unit = delta / factor_edited; pulse_j += unit *
        # factor_j). Initialised before design_tab_1(), because the pulse
        # spin-boxes connect link_source_changed during that build. Defaulting
        # link_param to 'Off' keeps build-time value snaps inert.
        self.link_param = 'Off'
        self.link_factor = {i: 0.0 for i in range(1, 10)}
        self._linking = False
        self._link_prev = {}

        self.design_tab_1()
        self.design_tab_2()
        self.design_tab_3()
        self.design_tab_4()
        self.design_tab_5()
        self.design_tab_6()

        self.laser_q_switch_delay = 0

        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI will freeze until the task terminates. During that time, the user won’t be able to interact with the application
        """

        self.is_experiment = False
        self.exit_clicked = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_messages)
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_process_status)
        self.file_handler = openfile.Saver_Opener()

        # Watch for "Open in AWG" requests from the Sequence Calculator and
        # reload the preset into this already-open window. Seed the seen-nonce
        # from the current signal file so a stale request (or the one we were
        # just launched with via argv) does not fire a spurious reload.
        self._seqcalc_nonce = self._read_seqcalc_nonce()
        self.seqcalc_timer = QTimer()
        self.seqcalc_timer.timeout.connect(self.check_seqcalc_reload)
        self.seqcalc_timer.start(400)

    def _read_seqcalc_nonce(self):
        try:
            with open(SEQCALC_SIGNAL) as f:
                parts = f.read().split('\n')
            return parts[2].strip() if len(parts) >= 3 else ''
        except OSError:
            return ''

    def check_seqcalc_reload(self):
        """Poll the Sequence Calculator signal file; reload on a new request."""
        try:
            with open(SEQCALC_SIGNAL) as f:
                parts = f.read().split('\n')
        except OSError:
            return
        if len(parts) < 3:
            return
        channel, path, nonce = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not nonce or nonce == self._seqcalc_nonce:
            return
        self._seqcalc_nonce = nonce
        if channel == SEQCALC_CHANNEL and os.path.isfile(path):
            # This window is already open and likely tuned (field, rep rate,
            # window, decimation, scans, sweep, amplitudes...). Apply ONLY the
            # pulse layout from the calculator; never touch those parameters.
            self.apply_seqcalc_pulses(path)

    def closeEvent(self, event):
        event.ignore()
        self.turn_off()

    def menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar { 
                color: rgb(193, 202, 227); 
                font-weight: bold; 
                font-size: 14px;  
                
                border-bottom: 2px solid rgb(60, 65, 85); 
                margin-bottom: 1px;
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                                  stop:0.95 transparent, 
                                  stop:1.0 rgb(100, 105, 130));
                
                padding-top: 2px; 
                padding-bottom: 1px; 
            } 
            QMenu::item { color: rgb(193, 202, 227); } 
            QMenu::item:selected { color: rgb(211, 194, 78); background-color: rgb(63, 63, 97); } 
            QMenuBar::item:selected { background-color: rgb(63, 63, 97); }
        """)
        file_menu = menubar.addMenu("File")
        pulse_menu = menubar.addMenu("Pulse")
        self.exp_menu = menubar.addMenu("Experiment")

        menubar.setFixedHeight(27)

        self.action_read = QAction("Read from file", self)
        self.action_read.triggered.connect( self.open_file_dialog )
        file_menu.addAction(self.action_read)

        self.action_save = QAction("Save to file", self)
        self.action_save.triggered.connect(self.save_file_dialog)
        file_menu.addAction(self.action_save)

        self.reset_all = QAction("Reset All", self)
        self.reset_all.triggered.connect(self.reset_all_func)
        pulse_menu.addAction(self.reset_all)

        pulse_menu.addSeparator()

        reset_pulse_menu = pulse_menu.addMenu("Reset Pulse...")

        self.pulse_actions = []

        for i in range(1, 10):
            action_text = f"P{i}"
            action = QAction(action_text, self)
            
            action.triggered.connect(lambda checked, p=i: self.reset_pulse_func(p))
            
            reset_pulse_menu.addAction(action)
            self.pulse_actions.append(action)

        pulse_menu.addSeparator()

        copy_pulse_menu = pulse_menu.addMenu("Copy Pulse...")

        self.copy_pulse_actions = []

        for i in range(1, 10):
            action_text = f"P{i}"
            action = QAction(action_text, self)
            
            action.triggered.connect(lambda checked, p=i: self.copy_pulse_func(p))
            
            copy_pulse_menu.addAction(action)
            self.copy_pulse_actions.append(action)

        cut_pulse_menu = pulse_menu.addMenu("Cut Pulse...")

        self.cut_pulse_actions = []

        for i in range(1, 10):
            action_text = f"P{i}"
            action = QAction(action_text, self)
            
            action.triggered.connect(lambda checked, p=i: self.cut_pulse_func(p))
            
            cut_pulse_menu.addAction(action)
            self.cut_pulse_actions.append(action)

        paste_pulse_menu = pulse_menu.addMenu("Paste Pulse...")

        self.paste_pulse_actions = []

        for i in range(1, 10):
            action_text = f"P{i}"
            action = QAction(action_text, self)
            
            action.triggered.connect(lambda checked, p=i: self.paste_pulse_func(p))
            
            paste_pulse_menu.addAction(action)
            self.paste_pulse_actions.append(action)

        self.menu_exp()

    def menu_exp(self):
        cwd = os.getcwd()

        if os.path.basename(cwd) == 'libs':
            cwd = os.path.abspath(os.path.join(cwd, '..', 'atomize', 'control_center'))

        t2_sequences = {
            'Hahn Echo; 2S': 'hahn_echo_2s.phase_awg',
            'Hahn Echo; 4S': 'hahn_echo_4s.phase_awg'
        }

        t2_exp_menu = self.exp_menu.addMenu('T₂')
        
        for label, file_name in t2_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            t2_exp_menu.addAction(action)

        t1_exp_menu = self.exp_menu.addMenu('T₁')

        t1_sequences = {
            'Invertion Recovery Echo; 4S; Log': 'inversion_recovery_echo_4s_log.phase_awg'
        }

        for label, file_name in t1_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            t1_exp_menu.addAction(action)

        nutation_exp_menu = self.exp_menu.addMenu('Nutation')

        nutation_sequences = {
            'Rabi Nutation Echo; 4S': 'rabi_echo_4s.phase_awg'
        }

        for label, file_name in nutation_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            nutation_exp_menu.addAction(action)

        ed_exp_menu = self.exp_menu.addMenu('Echo-Detected')

        ed_sequences = {
            'Echo-Detected; 2S': 'ed_2s.phase_awg',
            'Echo-Detected; 4S': 'ed_4s.phase_awg'
        }

        for label, file_name in ed_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            ed_exp_menu.addAction(action)

        eseem_exp_menu = self.exp_menu.addMenu('ESEEM')

        eseem_sequences = {
            '3pESEEM; 4S': '3peseem_4s.phase_awg',
            'HYSCORE; 16S': 'hyscore_16s.phase_awg',
        }

        for label, file_name in eseem_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            eseem_exp_menu.addAction(action)

        pds_exp_menu = self.exp_menu.addMenu('PDS')

        pds_sequences = {
            '4pDEER; 8S': '4pdeer_8s.phase_awg',
            'SIFTER; 16S': 'sifter_16s.phase_awg',
        }

        for label, file_name in pds_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            pds_exp_menu.addAction(action)

        setup_exp_menu = self.exp_menu.addMenu('Setup')

        setup_sequences = {
            'Amplitude Setup; 4S': 'ampl_4s.phase_awg',
        }

        for label, file_name in setup_sequences.items():
            full_path = os.path.join(cwd, 'experiments', file_name)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, name=full_path: self.set_preset_exp(name))
            setup_exp_menu.addAction(action)

    def set_preset_exp(self, filename):
        self.open_file(filename)

    def cut_pulse_func(self, pulse_number):
        self.copy_pulse_func(pulse_number)

        if pulse_number == 1:
            values = [576, 816, 0, 0, 0, 0, 100, 0, "+x,-x", "DETECTION"]
        else:
            values = [0, 0, 0, 0, 50, 350, 100, 0, "+x,+x", "SINE"]

        suffixes = ["_st", "_len", "_st_inc", "_len_inc", "_fr", "_sw", "_cf", "_sig"]
        
        for i, suffix in enumerate(suffixes):
            getattr(self, f"P{pulse_number}{suffix}").setValue(values[i])

        phase_widget = getattr(self, f"Phase_{pulse_number}")
        new_phase_text = str(values[8])
        phase_widget.setPlainText(new_phase_text)
            
        combo_widget = getattr(self, f"P{pulse_number}_type")
        new_combo_text = str(values[9])
        combo_widget.setCurrentText(new_combo_text)

    def paste_pulse_func(self, pulse_number):
        if self.pulse_buffer is None:
            return

        getattr(self, f"P{pulse_number}_st").setValue(self.pulse_buffer['st'])
        getattr(self, f"P{pulse_number}_len").setValue(self.pulse_buffer['len'])
        getattr(self, f"P{pulse_number}_st_inc").setValue(self.pulse_buffer['st_inc'])
        getattr(self, f"P{pulse_number}_len_inc").setValue(self.pulse_buffer['len_inc'])
        getattr(self, f"Phase_{pulse_number}").setPlainText(self.pulse_buffer['phase'])
        getattr(self, f"P{pulse_number}_type").setCurrentText(self.pulse_buffer['type'])
        getattr(self, f"P{pulse_number}_fr").setValue(self.pulse_buffer['freq'])
        getattr(self, f"P{pulse_number}_sw").setValue(self.pulse_buffer['sweep'])
        getattr(self, f"P{pulse_number}_cf").setValue(self.pulse_buffer['coef'])
        getattr(self, f"P{pulse_number}_sig").setValue(self.pulse_buffer['sigma'])
    
    def copy_pulse_func(self, pulse_number):
        self.pulse_buffer = {
            'st': getattr(self, f"P{pulse_number}_st").value(),
            'len': getattr(self, f"P{pulse_number}_len").value(),
            'st_inc': getattr(self, f"P{pulse_number}_st_inc").value(),
            'len_inc': getattr(self, f"P{pulse_number}_len_inc").value(),
            'phase': getattr(self, f"Phase_{pulse_number}").toPlainText(),
            'type': getattr(self, f"P{pulse_number}_type").currentText(),
            'freq': getattr(self, f"P{pulse_number}_fr").value(),
            'sweep': getattr(self, f"P{pulse_number}_sw").value(),
            'coef': getattr(self, f"P{pulse_number}_cf").value(),
            'sigma': getattr(self, f"P{pulse_number}_sig").value(),
        }

    def reset_pulse_func(self, pulse_number):
        if pulse_number == 1:
            values = [576, 816, 0, 0, 50, 0, 100, 0, "+x,-x", "DETECTION"]
        elif pulse_number == 2:
            values = [0, 22.4, 0, 0, 50, 350, 100, 0, "+x,-x", "SINE"]
        elif pulse_number == 3:
            values = [288, 44.8, 0, 0, 50, 350, 100, 0, "+x,+x", "SINE"]
        else:
            values = [0, 0, 0, 0, 50, 350, 100, 0, "+x,+x", "SINE"]

        suffixes = ["_st", "_len", "_st_inc", "_len_inc", "_fr", "_sw", "_cf", "_sig"]
        
        for i, suffix in enumerate(suffixes):
            getattr(self, f"P{pulse_number}{suffix}").setValue(values[i])

        phase_widget = getattr(self, f"Phase_{pulse_number}")
        new_phase_text = str(values[8])
        phase_widget.setPlainText(new_phase_text)
            
        combo_widget = getattr(self, f"P{pulse_number}_type")
        new_combo_text = str(values[9])
        combo_widget.setCurrentText(new_combo_text)

    def reset_all_func(self):
        for i in range(1, 10):
            self.reset_pulse_func(i)

    def design_tab_1(self):
        self.setObjectName("MainWindow")
        self.setWindowTitle("AWG Channel Pulse Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_pulse.png')
        self.setWindowIcon( QIcon(icon_path) )
        self.path = os.path.join(path_to_main, '..', '..', '..', '..', 'experimental_data')

        self.setMinimumHeight(774)
        self.setMinimumWidth(1720)
        self.setMaximumWidth(2660)

        central_container = QWidget()
        self.setCentralWidget(central_container)
        main_window_layout = QVBoxLayout(central_container)
        main_window_layout.setContentsMargins(0, 0, 0, 0)
        main_window_layout.setSpacing(0)

        self.tab_pulse = QTabWidget()
        main_window_layout.addWidget(self.tab_pulse)

        self.tab_pulse.setTabShape(QTabWidget.TabShape.Rounded)
        self.tab_pulse.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgb(43, 43, 77); 
                top: -1px; 
                background: rgb(63, 63, 97);
            }
            QTabBar::tab { 
                width: 190px; 
                height: 25px;
                font-weight: bold; 
                color: rgb(193, 202, 227);
                background: rgb(63, 63, 97);
                border: 1px solid rgb(43, 43, 77);
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                color: rgb(211, 194, 78);
                background: rgb(83, 83, 117); 
                border-bottom: 2px solid rgb(211, 194, 78);
            }
            QTabBar::tab:hover {
                background: rgb(73, 73, 107);
            }
        """)

        pulse_page = QWidget()
        pulse_page_layout = QVBoxLayout(pulse_page)
        pulse_page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.horizontalScrollBar().setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        #scroll.setFixedHeight(383)

        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: rgb(43, 43, 77); 
                height: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgb(193, 202, 227); 
                min-width: 20px;
                border-radius: 5px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: rgb(211, 194, 78); 
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)

        container = QWidget()
        scroll.setWidget(container)
        tab_layout = QVBoxLayout(container)
        
        self.gridLayout = QGridLayout()
        self.gridLayout.setContentsMargins(5, 5, 0, 0)
        self.gridLayout.setVerticalSpacing(4)
        self.gridLayout.setHorizontalSpacing(20)
        
        tab_layout.addLayout(self.gridLayout)
        tab_layout.addStretch()

        pulse_page_layout.addWidget(scroll)
        self.tab_pulse.addTab(pulse_page, "Pulses")
        self.tab_pulse.tabBar().setTabTextColor(0, QColor(193, 202, 227))

        buttons_widget = QWidget()
        self.buttons_layout = QGridLayout(buttons_widget)
        self.buttons_layout.setContentsMargins(15, 10, 10, 10)
        self.buttons_layout.setVerticalSpacing(6)
        self.buttons_layout.setHorizontalSpacing(20)
        
        main_window_layout.addWidget(buttons_widget)

        # ---- Labels & Inputs ----
        labels = [("Start", "label_1"), ("Length", "label_2"), ("Sigma", "label_3"), ("Start Increment", "label_4"), ("Length Increment", "label_5"), ("Frequency", "label_6"), ("Frequency Sweep", "label_7"), ("Amplitude", "label_8"), ("Type", "label_9"), ("Phase", "label_10"), ("Repetition Rate", "label_11"), ("Magnetic Field", "label_12"), ("Progress", "label_p1"), ("Start Increment 2", "label_si2")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(170, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        pulses = [(QDoubleSpinBox, 0, 100e6, 0, 3.2, 1, " ns", "_st", "_start"),
                  (QDoubleSpinBox, 0, 1900, 0, 3.2, 1, " ns", "_len", "_length"),
                  (QDoubleSpinBox, 0, 1900, 0, 3.2, 1, " ns", "_sig", "_sigma"),
                  (QDoubleSpinBox, 0, 1e6, 0, 3.2, 1, " ns", "_st_inc", "_st_increment"),
                  (QDoubleSpinBox, 0, 1e6, 0, 3.2, 1, " ns", "_st_inc2", "_st_increment2"),
                  (QDoubleSpinBox, 0, 320, 0, 3.2, 1, " ns", "_len_inc", "_len_increment")
                 ]
        # Start Increment 2 (ESEEM tau-averaging) sits directly under Start
        # Increment. Its label is label_si2 (out of the sequential label_N
        # range), so the per-row labels are mapped explicitly here.
        pulse_labels = ["label_1", "label_2", "label_3", "label_4", "label_si2", "label_5"]
        # Explicit grid rows: a separator is inserted at row 6 (above Start
        # Increment), so the three increment rows live at 7/8/9.
        pulse_rows = [3, 4, 5, 7, 8, 9]

        for j in range(1, 7):
            pulse_set = pulses[j-1]
            grid_row = pulse_rows[j-1]
            label_widget = getattr(self, pulse_labels[j-1])
            self.gridLayout.addWidget(label_widget, grid_row, 0)

            for i in range(1, 10):
                spin_box = (pulse_set[0])()
                spin_box.setRange(pulse_set[1], pulse_set[2])
                spin_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
                spin_box.setSingleStep(pulse_set[4])
                if (i == 1) and (j == 1):
                    spin_box.setValue(576)
                elif (i == 1) and (j == 2):
                    spin_box.setRange(0, 12.8e3)
                    spin_box.setValue(816)
                elif (i == 1) and (j == 3):
                    spin_box.setRange(0, 0)
                elif (i == 2) and (j == 2):
                    spin_box.setValue(22.4)
                elif (i == 3) and (j == 1):
                    spin_box.setValue(288)
                elif (i == 3) and (j == 2):
                    spin_box.setValue(44.8)
                else:  
                    spin_box.setValue(pulse_set[3])
                spin_box.setDecimals(pulse_set[5])
                spin_box.setSuffix(pulse_set[6])
                spin_box.setFixedSize(170, 26)
                spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
                spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
                
                spin_box.setKeyboardTracking( False )
                # widget name pulse_set[7]
                setattr(self, f"P{i}{pulse_set[7]}", spin_box)

                if pulse_set[7] == "_st":
                    v2_sfx = "_start_rect"
                elif pulse_set[7] == "_len":
                    v2_sfx = "_b"
                else:
                    v2_sfx = None

                spin_box.valueChanged.connect(
                    lambda val, idx = i, s7 = pulse_set[7], s8 = pulse_set[8], v2 = v2_sfx:
                    self.update_pulse_value(idx, s7, s8, v2)
                )
                # Start / Length are linkable (Position / Length).
                if pulse_set[7] in ('_st', '_len'):
                    spin_box.valueChanged.connect(
                        lambda val, idx = i, s7 = pulse_set[7]: self.link_source_changed(idx, s7)
                    )

                self.update_pulse_value(i, pulse_set[7], pulse_set[8], v2_sfx)
                self.gridLayout.addWidget(spin_box, grid_row, i)

                if j == 1:
                    lbl = QLabel(f"{i}")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                    lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
                    self.gridLayout.addWidget(lbl, 0, i)


        awg_pulses = [
            (QSpinBox, -1000, 1000, 50, 5, 0, " MHz", "_fr", "_freq"),
            (QSpinBox, -1000, 1000, 350, 5, 0, " MHz", "_sw", "wurst_sweep_cur_"),
            (QDoubleSpinBox, 0.1, 100, 100, 0.5, 1, " %", "_cf", "_coef")
        ]

        for j in range(11, 14):
            pulse_set = awg_pulses[j - 11]
            label_widget = getattr(self, f"label_{j - 5}")
            self.gridLayout.addWidget(label_widget, j, 0)

            for i in range(1, 10):
                spin_box = pulse_set[0]()
                if isinstance(spin_box, QDoubleSpinBox):
                    spin_box.setRange(pulse_set[1], pulse_set[2])
                    spin_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97); }")
                else:
                    spin_box.setRange(int(pulse_set[1]), int(pulse_set[2]))
                    spin_box.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")

                spin_box.setSingleStep(pulse_set[4])
                
                if i == 1:
                    if j == 11 or j == 12:
                        spin_box.setValue(pulse_set[3])
                        #spin_box.setRange(0, 0)
                    elif j == 13:
                        spin_box.setRange(100, 100)
                else:
                    spin_box.setValue(pulse_set[3])

                if isinstance(spin_box, QDoubleSpinBox):
                    spin_box.setDecimals(pulse_set[5])

                spin_box.setSuffix(pulse_set[6])
                spin_box.setFixedSize(170, 26)
                spin_box.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
                spin_box.setKeyboardTracking(False)
                spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu) 

                attr_name = f"P{i}{pulse_set[7]}"
                setattr(self, attr_name, spin_box)
                                
                if pulse_set[7] == "_cf":
                    spin_box.valueChanged.connect(lambda _, idx = i: self.update_coef_param(idx))
                    self.update_coef_param(i)
                    # Amplitude is linkable.
                    spin_box.valueChanged.connect(lambda _, idx = i: self.link_source_changed(idx, "_cf"))
                else:
                    prefix = "P"
                    v_name = "p" if pulse_set[7] == "_fr" else ""
                    spin_box.valueChanged.connect(
                        lambda _, idx=i, p=prefix, s=pulse_set[7], v = pulse_set[8]:
                        self.update_awg_generic(idx, s, v)
                    )
                    self.update_awg_generic(i, pulse_set[7], pulse_set[8])
                    # Frequency is linkable (the sweep box '_sw' is not).
                    if pulse_set[7] == "_fr":
                        spin_box.valueChanged.connect(lambda _, idx = i: self.link_source_changed(idx, "_fr"))

                self.gridLayout.addWidget(spin_box, j, i)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        self.gridLayout.addWidget(hline(), 1, 0, 1, 10)
        self.gridLayout.addWidget(hline(), 6, 0, 1, 10)
        self.gridLayout.addWidget(hline(), 10, 0, 1, 10)
        self.gridLayout.addWidget(hline(), 14, 0, 1, 10)

        # ---- Combo boxes----
        combo_boxes = [("DETECTION", "_type", "_type", "_typ", ["DETECTION"]),
                       ("SINE", "_type", "_type", "_typ", ["SINE", "GAUSS", "SINC", "WURST", "SECH/TANH", "LASER"]),
                       ("SINE", "_type", "_type", "_typ", ["SINE", "GAUSS", "SINC", "WURST", "SECH/TANH"])
                      ]

        label_widget = getattr(self, f"label_9")
        label_widget.setFixedSize(170, 26)
        self.gridLayout.addWidget(label_widget, 15, 0)

        self.laser_flag = 0

        for i in range(1, 10):
            combo = QComboBox()
            combo.setStyleSheet("""
                QComboBox 
                { color : rgb(193, 202, 227); 
                selection-color: rgb(211, 194, 78); 
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)
            combo.setFixedSize(170, 26)
            if i == 1:
                combo.addItems(combo_boxes[i-1][4])
                combo.setCurrentText(combo_boxes[i][0])
            elif i == 2:
                combo.addItems(combo_boxes[i-1][4])
                combo.setCurrentText(combo_boxes[i][0])
            else:
                combo.addItems(combo_boxes[2][4])
                combo.setCurrentText(combo_boxes[2][0])

            setattr(self, f"P{i}{combo_boxes[2][1]}", combo)

            combo.currentTextChanged.connect(lambda _, idx = i: self.update_pulse_type(idx))
            setattr(self, f"p{i}_typ", combo.currentText())

            self.gridLayout.addWidget(combo, 15, i)


        label_widget = getattr(self, f"label_10")
        label_widget.setFixedSize(170, 26)
        self.gridLayout.addWidget(label_widget, 16, 0)
        self.gridLayout.addWidget(hline(), 17, 0, 1, 10)

        # ---- Text Edits ----
        text_edit = ["+x,-x", "+x,-x", "+x,+x"]

        for i in range(1, 10):
            if i == 1:
                txt = QTextEdit(text_edit[0])
            elif i == 2:
                txt = QTextEdit(text_edit[1])
            else:
                txt = QTextEdit(text_edit[2])
            txt.setFixedSize(170, 60)
            txt.setAcceptRichText(False)
            #txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setStyleSheet("""
                QTextEdit { 
                    color: rgb(211, 194, 78); 
                    selection-background-color: rgb(211, 194, 78); 
                    selection-color: rgb(63, 63, 97);
                }

                QScrollBar:vertical {
                    border: none;
                    background: rgb(43, 43, 77); 
                    width: 10px;
                    margin: 0px;
                }

                QScrollBar::handle:vertical {
                    background: rgb(193, 202, 227); 
                    min-height: 20px;
                    border-radius: 5px;
                }

                QScrollBar::handle:vertical:hover {
                    background: rgb(211, 194, 78); 
                }

                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }

                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """)

            setattr(self, f"Phase_{i}", txt)
            txt.textChanged.connect(lambda idx = i: self.update_pulse_phase(idx))
            self.update_pulse_phase(i)

            self.gridLayout.addWidget(txt, 16, i)
            txt.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # ---- Link factor row ----
        # Per-pulse weight for Link mode. The coupled parameter is chosen in the
        # Settings tab; the weight here (No / 0.5x / 1x / 2x) scales how far this
        # pulse moves relative to the pulse being edited.
        self.link_row_label = QLabel("Link")
        self.link_row_label.setFixedSize(170, 26)
        self.link_row_label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.gridLayout.addWidget(self.link_row_label, 18, 0)

        for i in range(1, 10):
            combo = QComboBox()
            combo.addItems(["No", "0.5x", "1x", "2x"])
            combo.setCurrentText("No")
            combo.setFixedSize(170, 26)
            combo.setStyleSheet("""
                QComboBox
                { color : rgb(193, 202, 227);
                selection-color: rgb(211, 194, 78);
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)
            setattr(self, f"P{i}_lk", combo)
            combo.currentTextChanged.connect(lambda _, idx = i: self.update_link_factor(idx))
            self.gridLayout.addWidget(combo, 18, i)

        # ---- Boxes----
        boxes = [(QDoubleSpinBox, "Rep_rate", "repetition_rate", self.rep_rate, 0.1, 20e3, 500, 1, 1, " Hz"),
                 (QDoubleSpinBox, "Field", "mag_field", self.field, 10, 15.1e3, 3493, 0.5, 2, " G")]
        
        box_c = 0
        for widget_class, attr_name, par_name, func, v_min, v_max, cur_val, v_step, dec, suf in boxes:
            rr_box = widget_class()
            rr_box.setRange(v_min, v_max)
            rr_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
            rr_box.setSingleStep(v_step)
            rr_box.setValue(cur_val)
            rr_box.setDecimals(dec)
            rr_box.setSuffix(suf)
            rr_box.valueChanged.connect(func)
            rr_box.setFixedSize(170, 26)
            rr_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            rr_box.setKeyboardTracking( False )
            setattr(self, attr_name, rr_box)
            if attr_name == "Rep_rate":
                setattr(self, par_name, str( rr_box.value() ) + ' Hz')
            elif attr_name == 'Field':
                setattr(self, par_name, float( rr_box.value() ))

            self.buttons_layout.addWidget(rr_box, box_c, 1)
            box_c += 1
            rr_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        label_widget = getattr(self, f"label_11")
        self.buttons_layout.addWidget(label_widget, 0, 0)
        label_widget.setFixedSize(170, 26)
        label_widget = getattr(self, f"label_12")
        label_widget.setFixedSize(170, 26)
        self.buttons_layout.addWidget(label_widget, 1, 0)
        self.buttons_layout.addWidget(hline(), 2, 0, 1, 12)

        #---- Progress Bar ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedSize(170, 15)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgb(83, 83, 117);
                border-radius: 4px;
                background-color: rgb(42, 42, 64);
                color: rgb(211, 194, 78);
                font-weight: bold;
                text-align: right; 
                margin-right: 40px;
                height: 20px;
            }

            QProgressBar::chunk {
                background-color: rgb(193, 202, 227);
                border-radius: 2px;
            }
        """)

        # Live Edit controls (Live mode + Apply delay) live in the Settings tab.
        label_widget = getattr(self, f"label_p1")
        self.buttons_layout.addWidget(label_widget, 0, 2)
        self.buttons_layout.addWidget(self.progress_bar, 0, 3)

        self._update_rep_time_display()

        # ---- Buttons ----
        buttons = [("Run Pulses", "button_update", self.update),
                   ("Stop", "button_stop", self.dig_stop),
                   ("Exit", "button_off", self.turn_off),
                   ("Start Experiment", "button_start_exp", self.start_exp)
                   ]

        #("Stop Experiment", "button_stop_exp", self.stop_exp)
        btn_c = 3
        btn_cl = 0
        for name, attr_name, func in buttons:
            btn = QPushButton(name)
            btn.setFixedSize(170, 40)
            btn.clicked.connect(func)
            btn.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
            setattr(self, attr_name, btn)
            if name == "Start Experiment":
                btn_c = 3
                btn_cl = 1
            self.buttons_layout.addWidget(btn, btn_c, btn_cl)
            btn_c += 1
        
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        txt.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        setattr(self, "errors", txt)

        txt.setStyleSheet("""
            QPlainTextEdit { 
                color: rgb(211, 194, 78); 
                selection-background-color: rgb(211, 194, 78); 
                selection-color: rgb(63, 63, 97);
            }

            QScrollBar:vertical {
                border: none;
                background: rgb(43, 43, 77); 
                width: 10px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: rgb(193, 202, 227); 
                min-height: 20px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical:hover {
                background: rgb(211, 194, 78); 
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                    border: none;
                    background: rgb(43, 43, 77); 
                    height: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:horizontal {
                    background: rgb(193, 202, 227); 
                    min-width: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: rgb(211, 194, 78); 
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                    background: none;
                }

        """)

        self.buttons_layout.addWidget(txt, 3, 2, 3, 10)

        #self.buttons_layout.setRowStretch(6, 11)
        #self.buttons_layout.setColumnStretch(6, 11)

    def design_tab_2(self):
        dig_setting_page = QWidget()
        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 15, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        dig_setting_page.setLayout(gridLayout)

        self.tab_pulse.addTab(dig_setting_page, "Acquisition")
        self.tab_pulse.tabBar().setTabTextColor(1, QColor(193, 202, 227))

        # ---- Labels & Inputs ----
        labels = [("Acquisitions", "label_17"), ("Integration Left", "label_18"), ("Integration Right", "label_19"), ("Decimation", "label_20"), ("Points", "label_e1"), ("Scans", "label_e2"), ("Experiment Name", "label_e3"), ("Curve Name", "label_e4"), ("Start Field", "label_f1"), ("End Field", "label_f2"), ("Field Step", "label_f3"), ("Sweep Type", "label_c1"), ("Start Log Time", "label_e5"), ("End Log Time", "label_e6"),
            ('X<sub style="font-size: 12pt;">0</sub>', "label_e7"), ("ΔX ", "label_e8"),
            ("Amplitude Step", "label_f4"), ("Cycles", "label_cyc"), ("Save Each Cycle", "label_save_cyc")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(170, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QSpinBox, "Acq_number", "number_averages", self.acq_number, 1, 1e4, 1, 1, 0, ""),
                      (QSpinBox, "Dec", "decimation", self.decimat, 1, 4, 1, 1, 0, ""),
                      (QDoubleSpinBox, "Win_left", "cur_win_left", self.win_left, 0, 6400, 0, 0.4, 1, " ns"),
                      (QDoubleSpinBox, "Win_right", "cur_win_right", self.win_right, 0, 6400, 320, 0.4, 1, " ns"),
                      (QSpinBox, "box_points", "cur_points", self.points, 1, 20000, 500, 10, 0, ""),
                      (QSpinBox, "box_scan", "cur_scan", self.scan, 1, 100, 1, 1, 0, ""),
                      (QDoubleSpinBox, "box_st_field", "cur_start_field", self.st_field, 0, 15000, 3000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_end_field", "cur_end_field", self.end_field, 0, 15000, 4000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_step_field", "cur_step", self.step_field, 0.01, 50, 0.5, 0.1, 2, " G"),
                      (QDoubleSpinBox, "X0", "cur_x0", self.x0, -100e6, 100e6, 0, 3.2, 1, " ns"),
                      (QDoubleSpinBox, "XDelta", "cur_xdelta", self.xdelta, -100e6, 100e6, 0, 3.2, 1, " ns"),
                      (QDoubleSpinBox, "box_step_ampl", "cur_ampl_step", self.step_ampl, 0.1, 5, 1, 0.1, 1, " %"),
                      (QSpinBox, "box_cycles", "cur_cycles", self.cycles_func, 1, 1024, 8, 1, 0, "")
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
            spin_box.setFixedSize(170, 26)
            spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

            spin_box.setKeyboardTracking( False )
            
            setattr(self, attr_name, spin_box)
            if isinstance(spin_box, QSpinBox):
                if attr_name == 'Dec':
                    setattr(self, par_name, int(spin_box.value()))
                    self.time_per_point = 0.4 * self.decimation
                else:
                    setattr(self, par_name, int(spin_box.value()))
            else:
                if attr_name == 'Win_left' or attr_name == 'Win_right':
                    setattr(self, par_name, int( float( spin_box.value() ) / self.time_per_point ))
                else:
                    setattr(self, par_name, float(spin_box.value()))
        
        self.X0.setToolTip('X<sub style="font-size: 12pt;">0</sub> value for the custom X-axis.<br>In a Log Time experiment a non-zero X<sub style="font-size: 12pt;">0</sub> sets the X-axis start point; if left at 0 the start is taken from the detection pulse timing (or the first pulse with a non-zero Start Increment).')
        self.XDelta.setToolTip('ΔX value for the custom X-axis. Applied if not equal to 0.')
        self.box_step_ampl.setToolTip('A pulse with a variable amplitude can be specified using the Start Increment parameter in the Pulses tab.')

        # ---- Log Time spinboxes ----
        # UI shows plain time + unit (ns/us/ms/s); self.cur_log_start /
        # self.cur_log_end stay as log10(time_in_ns) so the worker (exp_log)
        # and preset files don't change.
        for attr_name, par_name, func, log_default in [
            ("Log_start", "cur_log_start", self.log_start, 1.0),
            ("Log_end",   "cur_log_end",   self.log_end,   7.0),
        ]:
            tspin = TimeLogSpinBox()
            tspin.setValue(log_default)
            tspin.valueChanged.connect(func)
            tspin.setFixedSize(170, 26)
            setattr(self, attr_name, tspin)
            setattr(self, par_name, float(tspin.value()))

        self.Log_start.setToolTip('Pulses with a log-step can be specified using the Start Increment parameter in the Pulses tab. Only relative increments of the pulses are important.\nA non-zero X0 sets the X-axis start point; otherwise the detection pulse timing (or the first pulse with a non-zero Start Increment) is used.')
        self.Log_end.setToolTip('Pulses with a log-step can be specified using the Start Increment parameter in the Pulses tab. Only relative increments of the pulses are important.\nA non-zero X0 sets the X-axis start point; otherwise the detection pulse timing (or the first pulse with a non-zero Start Increment) is used.')

        # ---- Text Edits ----
        text_edit = [("E_AWG", "text_edit_exp_name", "cur_exp_name", self.exp_name),
                     ("c1", "text_edit_curve", "cur_curve_name", self.curve_name)
                    ]

        for text, attr_name, par_name, func in text_edit:
            txt = QTextEdit(text)
            setattr(self, attr_name, txt)
            setattr(self, par_name, txt.toPlainText())
            txt.textChanged.connect(func)
            txt.setFixedSize(170, 26)
            txt.setAcceptRichText(False)
            txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
            txt.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # ---- Combo boxes----
        combo_boxes = [("Linear Time", "combo_sweep", "cur_sweep", self.sweep_type,
                        [
                        "Linear Time", "Field", "Log Time", "Amplitude", "ESEEM Avg"
                        ])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_boxes:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            setattr(self, par_name, combo.currentText())
            combo.currentIndexChanged.connect(func)
            combo.addItems(item)
            combo.setCurrentText(cur_text)
            combo.setFixedSize(170, 26)
            combo.setStyleSheet("""
                QComboBox 
                { color : rgb(193, 202, 227); 
                selection-color: rgb(211, 194, 78); 
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)

        self.combo_sweep.setToolTip('Linear Time: standard linear delay/length increment experiment.\nField: field-sweep experiment.\nLog Time: log10 delay/length increment experiment.\nAmplitude: pulse-amplitude increment experiment.\nESEEM Avg: ESEEM tau-averaging — repeats the linear-time scan over several cycles, shifting the pulses set by Start Increment 2 (Pulses tab) cumulatively each cycle, then averages.')

        self.box_cycles.setToolTip('ESEEM Avg only: number of averaging cycles. Each cycle the pulses are shifted by Start Increment 2 (Pulses tab) cumulatively (cycle 0 = base, cycle c = base + c·Inc2).')

        # ---- Save-each-cycle checkbox (ESEEM Avg) ----
        self.save_each_cycle = 0
        self.Save_each = QCheckBox("")
        self.Save_each.stateChanged.connect(self.save_each_func)
        self.Save_each.setStyleSheet(CHECKBOX_STYLE)
        self.Save_each.setFixedSize(170, 26)
        self.Save_each.setToolTip('ESEEM Avg only: when checked, additionally save each cycle’s raw trace to its own file (suffixed by the cycle index), alongside the averaged result.')

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        container_layout = QHBoxLayout()

        left_grid = QGridLayout()
        left_grid.setVerticalSpacing(4)
        left_grid.setHorizontalSpacing(20)
        left_grid.addWidget(self.label_17, 0, 0)
        left_grid.addWidget(self.Acq_number, 0, 1)
        left_grid.addWidget(hline(), 1, 0, 1, 2)

        left_grid.addWidget(self.label_e1, 2, 0)
        left_grid.addWidget(self.box_points, 2, 1)
        left_grid.addWidget(self.label_e2, 3, 0)
        left_grid.addWidget(self.box_scan, 3, 1)
        left_grid.addWidget(hline(), 4, 0, 1, 2)

        left_grid.addWidget(self.label_e7, 5, 0)
        left_grid.addWidget(self.X0, 5, 1)
        left_grid.addWidget(self.label_e8, 6, 0)
        left_grid.addWidget(self.XDelta, 6, 1)

        left_grid.addWidget(hline(), 8, 0, 1, 2)

        left_grid.addWidget(self.label_e5, 9, 0)
        left_grid.addWidget(self.Log_start, 9, 1)
        left_grid.addWidget(self.label_e6, 10, 0)
        left_grid.addWidget(self.Log_end, 10, 1)

        left_grid.addWidget(hline(), 11, 0, 1, 2)

        left_grid.addWidget(self.label_e3, 12, 0)
        left_grid.addWidget(self.text_edit_exp_name, 12, 1)
        left_grid.addWidget(self.label_e4, 13, 0)
        left_grid.addWidget(self.text_edit_curve, 13, 1)

        left_grid.addWidget(hline(), 14, 0, 1, 2)

        left_grid.setRowStretch(15, 1)
        left_grid.setColumnStretch(15, 1)

        right_grid = QGridLayout()
        right_grid.setVerticalSpacing(4)
        right_grid.setHorizontalSpacing(20)
        right_grid.addWidget(self.label_18, 0, 0)
        right_grid.addWidget(self.Win_left, 0, 1)
        right_grid.addWidget(self.label_19, 1, 0)
        right_grid.addWidget(self.Win_right, 1, 1)
        right_grid.addWidget(self.label_20, 2, 0)
        right_grid.addWidget(self.Dec, 2, 1)
        right_grid.addWidget(hline(), 3, 0, 1, 2)
        right_grid.setRowStretch(4, 1)
        right_grid.setColumnStretch(4, 1)

        third_grid = QGridLayout()
        third_grid.setVerticalSpacing(4)
        third_grid.setHorizontalSpacing(20)
        third_grid.addWidget(self.label_f1, 0, 0)
        third_grid.addWidget(self.box_st_field, 0, 1)
        third_grid.addWidget(self.label_f2, 1, 0)
        third_grid.addWidget(self.box_end_field, 1, 1)
        third_grid.addWidget(self.label_f3, 2, 0)
        third_grid.addWidget(self.box_step_field, 2, 1)
        third_grid.addWidget(hline(), 3, 0, 1, 2)

        third_grid.addWidget(self.label_f4, 4, 0)
        third_grid.addWidget(self.box_step_ampl, 4, 1)
        third_grid.addWidget(hline(), 5, 0, 1, 2)
        third_grid.addWidget(self.label_cyc, 6, 0)
        third_grid.addWidget(self.box_cycles, 6, 1)
        third_grid.addWidget(self.label_save_cyc, 7, 0)
        third_grid.addWidget(self.Save_each, 7, 1)

        third_grid.addWidget(hline(), 8, 0, 1, 2)
        third_grid.setRowStretch(9, 1)
        third_grid.setColumnStretch(9, 1)

        forth_grid = QGridLayout()
        forth_grid.setVerticalSpacing(4)
        forth_grid.setHorizontalSpacing(20)
        forth_grid.addWidget(self.label_c1, 0, 0)
        forth_grid.addWidget(self.combo_sweep, 0, 1)
        forth_grid.addWidget(hline(), 1, 0, 1, 2)
        forth_grid.setRowStretch(2, 1)
        forth_grid.setColumnStretch(2, 1)

        container_layout.addLayout(left_grid)
        container_layout.addSpacing(20)
        container_layout.addLayout(right_grid)
        container_layout.addSpacing(20)
        container_layout.addLayout(third_grid)
        container_layout.addSpacing(20)
        container_layout.addLayout(forth_grid)

        container_layout.addStretch(1) 
        gridLayout.addLayout(container_layout, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        gridLayout.setColumnStretch(1, 1)
        gridLayout.setRowStretch(1, 1)

    def design_tab_3(self):
        fft_setting_page = QWidget()
        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 15, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        fft_setting_page.setLayout(gridLayout)

        self.tab_pulse.addTab(fft_setting_page, "FFT")
        self.tab_pulse.tabBar().setTabTextColor(2, QColor(193, 202, 227))

        # ---- Labels & Inputs ----
        labels = [("Points to Drop", "label_11"), ("Zero Order", "label_12"), ("First Order", "label_13"), ("Second Order", "label_14"), ("Live FFT", "label_15"), ("Phase Correction", "label_16"), ("Shift Offset", "label_fft1"), ("Save 2D", "label_fft2")]

        #
        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(170, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QSpinBox, "P_to_drop", "p_to_drop", self.p_to_drop_func, 0, 1e4, 0, 1, 0, ""),
                      (QDoubleSpinBox, "Zero_order", "zero_order", self.zero_order_func, -0.1, 360.1, 0, 0.5, 4, " deg"),
                      (QDoubleSpinBox, "First_order", "first_order", self.first_order_func, -100, 100, 0, 0.001, 4, " deg/ns"),
                      (QDoubleSpinBox, "Second_order", "second_order", self.second_order_func, -100, 100, 0, 0.001, 4, ' deg/ns²')
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
            spin_box.setFixedSize(170, 26)
            spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

            spin_box.setKeyboardTracking( False )
            
            setattr(self, attr_name, spin_box)
            if isinstance(spin_box, QDoubleSpinBox):
                if attr_name == 'Zero_order':
                    setattr(self, par_name, float(spin_box.value() / self.deg_rad))
                elif attr_name == 'First_order':
                    setattr(self, par_name, float(spin_box.value() / self.first_order_coef))
                else:
                    setattr(self, par_name, float(spin_box.value() / self.sec_order_coef))

            else:
                setattr(self, par_name, int(spin_box.value()))


        self.P_to_drop.setToolTip('Time zero for the FFT calculation')

        #if self.second_order != 0.0:
        #    self.second_order = self.sec_order_coef / ( float( self.Second_order.value() ) * 1000 )

        self.l_mode = 0

        # ---- Check Boxes ----
        check_boxes = [("fft_box", self.fft_online),
                       ("Quad_cor", self.quad_online),
                       ("IQ_corr", self.iq_online),
                       ("Save2D", self.save_2d)]

        for attr_name, func in check_boxes:
            check = QCheckBox("")
            setattr(self, attr_name, check)
            check.stateChanged.connect(func)
            check.setStyleSheet(CHECKBOX_STYLE)
            check.setFixedSize(170, 26)
            if attr_name == 'IQ_corr':
                check.setChecked(True)

        self.fft_box.setToolTip('Show amplitude FFT of raw I/Q data.')
        
        self.Quad_cor.setToolTip('Apply phase correction in the frequency domain: exp(i·(φ₀ + φ₁·f + φ₂·f²))')

        self.IQ_corr.setToolTip('When checked, apply time-domain zero-order phase correction: exp(i·φ₀),\nwhere φ₀ is set by the Frequency of the DETECTION pulse.In this case, only the integrated signal is plotted.\nWhen unchecked, the full 2D arrays are plotted.')
        
        self.Save2D.setToolTip('When checked, save both 1D and 2D arrays in the Shift Offset mode.')

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line


        # ---- Layout placement ----
        gridLayout.addWidget(self.label_15, 0, 0)
        gridLayout.addWidget(self.fft_box, 0, 1)
        gridLayout.addWidget(self.label_16, 1, 0)
        gridLayout.addWidget(self.Quad_cor, 1, 1)
        gridLayout.addWidget(self.label_fft1, 2, 0)
        gridLayout.addWidget(self.IQ_corr, 2, 1)
        gridLayout.addWidget(self.label_fft2, 3, 0)
        gridLayout.addWidget(self.Save2D, 3, 1)

        gridLayout.addWidget(hline(), 4, 0, 1, 2)
        
        gridLayout.addWidget(self.label_11, 5, 0)
        gridLayout.addWidget(self.P_to_drop, 5, 1)
        gridLayout.addWidget(self.label_12, 6, 0)
        gridLayout.addWidget(self.Zero_order, 6, 1)
        gridLayout.addWidget(self.label_13, 7, 0)
        gridLayout.addWidget(self.First_order, 7, 1)
        gridLayout.addWidget(self.label_14, 8, 0)
        gridLayout.addWidget(self.Second_order, 8, 1)

        gridLayout.addWidget(hline(), 9, 0, 1, 2)

        gridLayout.setRowStretch(10, 2)
        gridLayout.setColumnStretch(10, 2)

        # flag for not writing the data when digitizer is off
        self.opened = 0
        self.fft = 0
        self.quad = 0
        self.double_change = 0
        self.iq_cor = 1
        self.save2d = 0

    def design_tab_4(self):
        laser_setting_page = QWidget()
        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 15, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        laser_setting_page.setLayout(gridLayout)

        self.tab_pulse.addTab(laser_setting_page, "Source / Laser")
        self.tab_pulse.tabBar().setTabTextColor(3, QColor(193, 202, 227))

        # ---- Labels & Inputs ----
        labels = [("Laser", "label_s0"), ("MW Source", "label_s1")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(170, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Combo box----
        combo_laser = [("Nd:YaG", "Combo_laser", "", self.combo_laser_fun, ["Nd:YaG", "NovoFEL"]),
                       ("1", "Combo_synt", "", self.combo_synt_fun, ["1", "2"])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_laser:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            combo.currentIndexChanged.connect(func)
            combo.addItems(item)
            combo.setCurrentText(cur_text)
            combo.setFixedSize(170, 26)
            combo.setStyleSheet("""
                QComboBox 
                { color : rgb(193, 202, 227); 
                selection-color: rgb(211, 194, 78); 
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)
        
        self.combo_synt_fun()
        self.combo_laser_fun()

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        # ---- Layout placement ----
        gridLayout.addWidget(self.label_s1, 0, 0)
        gridLayout.addWidget(self.Combo_synt, 0, 1)
        gridLayout.addWidget(self.label_s0, 1, 0)
        gridLayout.addWidget(self.Combo_laser, 1, 1)

        gridLayout.addWidget(hline(), 2, 0, 1, 2)

        gridLayout.setRowStretch(3, 1)
        gridLayout.setColumnStretch(3, 1)

    def design_tab_5(self):
        # measured complex transfer for the 'measured' correction model (loaded
        # from a 3-column file); None => triple-Lorentzian magnitude-only fit.
        self.meas_freq_cur = None
        self.meas_H_cur = None
        self._meas_h_path = ''
        self.meas_h_fmt_cur = 'GHz · dB · deg'

        dig_setting_page = QWidget()
        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 15, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        dig_setting_page.setLayout(gridLayout)

        self.tab_pulse.addTab(dig_setting_page, "AWG")
        self.tab_pulse.tabBar().setTabTextColor(4, QColor(193, 202, 227))

        # ---- Labels & Inputs ----
        labels = [("Amplitude I", "label_a1"), ("Amplitude Q", "label_a2"), ("Phase", "label_a3"), ("N [wurst; sech/tanh]", "label_a4"), ("b [sech/tanh]", "label_a5"), ("Resonator Profile", "label_a6"), ("Correction Model", "label_a7"), ('Resonator f<sub style="font-size: 12pt;">0</sub>', "label_a8"), ("Resonator Q", "label_a9"), ("Measured H(f)", "label_a10"), ("Load H(f)", "label_a11")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(170, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QSpinBox, "Ampl_1", "ch0_ampl", self.ch0_amp, 1, 260, 260, 1, 0, ""),
                        (QSpinBox, "Ampl_2", "ch1_ampl", self.ch1_amp, 1, 260, 260, 1, 0, ""),
                        (QDoubleSpinBox, "Phase", "cur_phase", self.awg_phase, 0, 360, 90, 0.1, 2, " deg"),
                        (QSpinBox, "N_wurst", "n_wurst_cur", self.n_wurst, 1, 100, 10, 1, 0, ""),
                        (QDoubleSpinBox, "B_sech", "b_sech_cur", self.b_sech_func, 0.005, 10, 0.02, 0.001, 3, " 1/ns"),
                        (QDoubleSpinBox, "F0_res", "f0_cur", self.f0_func, 1000, 100000, 9700, 10, 1, " MHz"),
                        (QDoubleSpinBox, "Q_res", "q_cur", self.q_func, 1, 100000, 88, 1, 1, "")
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
            spin_box.setFixedSize(170, 26)
            spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

            spin_box.setKeyboardTracking( False )
            
            setattr(self, attr_name, spin_box)
            if isinstance(spin_box, QSpinBox):
                    setattr(self, par_name, int(spin_box.value()))
            else:
                if attr_name == 'Phase':
                    setattr(self, par_name, float( spin_box.value() * np.pi * 2 / 360 ) )
                else:
                    setattr(self, par_name, float(spin_box.value()))

        # ---- Combo box----
        combo_laser = [("No", "Combo_cor", "", self.combo_cor_fun, ["No", "Only Pi/2", "All"]),
                       ("Measured", "Combo_model", "", self.combo_model_fun, ["Measured", "Ideal RLC", "Ideal RLC + phase"]),
                       ("GHz · dB · deg", "Combo_resfmt", "", self.resfmt_fun, ["GHz · dB · deg", "GHz · lin · deg", "GHz · lin · rad", "GHz · Re · Im", "MHz · dB · deg", "MHz · Re · Im"])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_laser:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            combo.currentIndexChanged.connect(func)
            combo.addItems(item)
            combo.setCurrentText(cur_text)
            combo.setFixedSize(170, 26)
            combo.setStyleSheet("""
                QComboBox 
                { color : rgb(193, 202, 227); 
                selection-color: rgb(211, 194, 78); 
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)

        self.combo_cor_fun()
        self.combo_model_fun()
        self.resfmt_fun()

        # ---- Load measured H(f) button + status ----
        self.Btn_resH = QPushButton("Load…")
        self.Btn_resH.setFixedSize(170, 26)
        self.Btn_resH.setStyleSheet("""
            QPushButton
            { color : rgb(193, 202, 227);
            selection-color: rgb(211, 194, 78);
            selection-background-color: rgb(63, 63, 97);
            }
            """)
        self.Btn_resH.clicked.connect(self.open_resonator)

        self.reson_file_lbl = QLabel("(no file)")
        self.reson_file_lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); }")
        self.reson_file_lbl.setWordWrap(True)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        container_layout = QHBoxLayout()

        left_grid = QGridLayout()
        left_grid.setVerticalSpacing(4)
        left_grid.setHorizontalSpacing(20)
        left_grid.addWidget(self.label_a4, 0, 0)
        left_grid.addWidget(self.N_wurst, 0, 1)
        left_grid.addWidget(self.label_a5, 1, 0)
        left_grid.addWidget(self.B_sech, 1, 1)
        left_grid.addWidget(hline(), 2, 0, 1, 2)
        left_grid.setRowStretch(3, 1)
        left_grid.setColumnStretch(3, 1)

        right_grid = QGridLayout()
        right_grid.setVerticalSpacing(4)
        right_grid.setHorizontalSpacing(20)
        right_grid.addWidget(self.label_a1, 0, 0)
        right_grid.addWidget(self.Ampl_1, 0, 1)
        right_grid.addWidget(self.label_a2, 1, 0)
        right_grid.addWidget(self.Ampl_2, 1, 1)
        right_grid.addWidget(self.label_a3, 2, 0)
        right_grid.addWidget(self.Phase, 2, 1)
        right_grid.addWidget(hline(), 3, 0, 1, 2)
        right_grid.addWidget(self.label_a6, 4, 0)
        right_grid.addWidget(self.Combo_cor, 4, 1)
        right_grid.addWidget(self.label_a7, 5, 0)
        right_grid.addWidget(self.Combo_model, 5, 1)
        right_grid.addWidget(self.label_a8, 6, 0)
        right_grid.addWidget(self.F0_res, 6, 1)
        right_grid.addWidget(self.label_a9, 7, 0)
        right_grid.addWidget(self.Q_res, 7, 1)
        right_grid.addWidget(self.label_a10, 8, 0)
        right_grid.addWidget(self.Combo_resfmt, 8, 1)
        right_grid.addWidget(self.label_a11, 9, 0)
        right_grid.addWidget(self.Btn_resH, 9, 1)
        right_grid.addWidget(self.reson_file_lbl, 10, 0, 1, 2)
        right_grid.addWidget(hline(), 11, 0, 1, 2)

        right_grid.setRowStretch(12, 1)
        right_grid.setColumnStretch(9, 1)
        
        container_layout.addLayout(left_grid)
        container_layout.addSpacing(20)
        container_layout.addLayout(right_grid)

        container_layout.addStretch(1) 
        gridLayout.addLayout(container_layout, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        gridLayout.setColumnStretch(1, 1)
        gridLayout.setRowStretch(1, 1)

    def design_tab_6(self):
        settings_page = QWidget()
        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 15, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        settings_page.setLayout(gridLayout)

        self.tab_pulse.addTab(settings_page, "Settings")
        self.tab_pulse.tabBar().setTabTextColor(5, QColor(193, 202, 227))

        # ---- Separator ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        # ---- Live Edit controls ----
        live_label = QLabel("Live mode")
        live_label.setFixedSize(170, 26)
        live_label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.live_edit_box = QCheckBox("")
        self.live_edit_box.setStyleSheet(CHECKBOX_STYLE)
        self.live_edit_box.setFixedSize(170, 26)
        self.live_edit_box.setToolTip(
            "When enabled, edits to a pulse's Amplitude, Frequency, Sigma, Type "
            "and Start are applied to the running sequence immediately, without "
            "restarting the card. A Start edit that would overlap or reorder the "
            "sequence, a LASER on/off, and any change to Length / phase cycle / "
            "pulse count / decimation, trigger an automatic restart instead. No "
            "effect until a sequence is running.")
        self.live_edit_box.stateChanged.connect(self.live_edit_toggle)

        debounce_label = QLabel("Apply delay")
        debounce_label.setFixedSize(170, 26)
        debounce_label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.Debounce = QSpinBox()
        self.Debounce.setRange(200, 5000)
        self.Debounce.setSingleStep(50)
        self.Debounce.setValue(800)
        self.Debounce.setSuffix(" ms")
        self.Debounce.setFixedSize(170, 26)
        self.Debounce.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self.Debounce.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.Debounce.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
        self.Debounce.setToolTip("Delay after the last pulse edit before it is pushed to the running sequence.")

        # ---- Link mode: coupled parameter ----
        link_param_label = QLabel("Link Parameter")
        link_param_label.setFixedSize(170, 26)
        link_param_label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        self.Combo_link = QComboBox()
        self.Combo_link.addItems(["Off", "Amplitude", "Length", "Position", "Frequency"])
        self.Combo_link.setCurrentText("Off")
        self.Combo_link.setFixedSize(170, 26)
        self.Combo_link.setStyleSheet("""
            QComboBox
            { color : rgb(193, 202, 227);
            selection-color: rgb(211, 194, 78);
            selection-background-color: rgb(63, 63, 97);
            outline: none;
            }
            """)
        self.Combo_link.setToolTip(
            "Couple this parameter across pulses. Set a per-pulse weight "
            "(No / 0.5x / 1x / 2x) in the Link row of the Pulses tab; editing "
            "the parameter on any linked pulse shifts every other linked pulse "
            "proportionally to its weight.")
        self.Combo_link.currentTextChanged.connect(self.link_param_changed)

        gridLayout.addWidget(live_label, 0, 0)
        gridLayout.addWidget(self.live_edit_box, 0, 1)
        gridLayout.addWidget(debounce_label, 1, 0)
        gridLayout.addWidget(self.Debounce, 1, 1)
        gridLayout.addWidget(hline(), 2, 0, 1, 2)
        gridLayout.addWidget(link_param_label, 3, 0)
        gridLayout.addWidget(self.Combo_link, 3, 1)
        gridLayout.addWidget(hline(), 4, 0, 1, 2)

        gridLayout.setColumnStretch(2, 1)
        gridLayout.setRowStretch(5, 1)

        # All pulse spin-boxes now exist; snapshot their values so the first
        # linked edit computes the correct delta.
        self._seed_link_prev()

    # ---- Link mode helpers ----
    def _link_suffix(self):
        """Spin-box suffix for the currently coupled parameter, or None."""
        return {'Amplitude': '_cf', 'Length': '_len',
                'Position': '_st', 'Frequency': '_fr'}.get(self.link_param)

    def _seed_link_prev(self):
        for suf in ('_st', '_len', '_cf', '_fr'):
            for i in range(1, 10):
                box = getattr(self, f"P{i}{suf}", None)
                if box is not None:
                    self._link_prev[(suf, i)] = box.value()

    def link_param_changed(self, _text = None):
        self.link_param = self.Combo_link.currentText()

    def update_link_factor(self, index):
        txt = getattr(self, f"P{index}_lk").currentText()
        self.link_factor[index] = {'No': 0.0, '0.5x': 0.5, '1x': 1.0, '2x': 2.0}.get(txt, 0.0)

    def link_source_changed(self, index, suffix):
        """A linkable spin-box changed: shift the other linked pulses in step."""
        box = getattr(self, f"P{index}{suffix}")
        new_val = box.value()
        prev = self._link_prev.get((suffix, index), new_val)
        self._link_prev[(suffix, index)] = new_val

        # Re-entrancy guard (we are the one moving the other boxes), inactive
        # parameter, or this pulse is not linked -> nothing to propagate.
        if self._linking or suffix != self._link_suffix():
            return
        f_edit = self.link_factor.get(index, 0.0)
        if f_edit == 0.0:
            return
        delta = new_val - prev
        if delta == 0:
            return

        unit = delta / f_edit
        self._linking = True
        clamped = False
        try:
            for j in range(1, 10):
                if j == index:
                    continue
                f_j = self.link_factor.get(j, 0.0)
                if f_j == 0.0:
                    continue
                box_j = getattr(self, f"P{j}{suffix}", None)
                if box_j is None:
                    continue
                target = box_j.value() + unit * f_j
                # QSpinBox/QDoubleSpinBox silently clamp to their range. For the
                # amplitude (_cf, 0.1..100 %) a coupled shift can drive a linked
                # pulse past the 100 % ceiling; detect that so the operator is told
                # the coupling is no longer strictly proportional instead of it
                # breaking silently.
                if target > box_j.maximum() + 1e-9 or target < box_j.minimum() - 1e-9:
                    clamped = True
                # '_fr' boxes are integer QSpinBoxes; PyQt6 setValue(int)
                # rejects a float, so coerce for them (unit*factor can be
                # fractional, e.g. a 0.5x weight on an odd delta).
                if isinstance(box_j, QDoubleSpinBox):
                    box_j.setValue(target)
                else:
                    box_j.setValue(int(round(target)))
                self._link_prev[(suffix, j)] = box_j.value()
        finally:
            self._linking = False

        if clamped:
            if suffix == '_cf':
                self.message('Link: a coupled amplitude hit the 0.1-100 % limit '
                             'and was clamped; the link is no longer proportional.')
            else:
                self.message('Link: a coupled value hit its limit and was clamped; '
                             'the link is no longer proportional.')

    def x0(self):
        self.cur_x0 = self.round_and_change_no_ns(self.X0)
    
    def xdelta(self):
        self.cur_xdelta = self.round_and_change_no_ns(self.XDelta)

    def log_start(self):
        self.cur_log_start = round( float( self.Log_start.value() ), 3 )

    def log_end(self):
        self.cur_log_end = round( float( self.Log_end.value() ), 3 )

    def end_field(self):
        """
        A function to send an end field value
        """
        self.cur_end_field = round( float( self.box_end_field.value() ), 3 )

    def st_field(self, value):
        """
        A function to send a start field value
        """
        self.cur_start_field = round( float( value ), 3 )

    def step_field(self):
        """
        A function to send a step field value
        """
        self.cur_step = round( float( self.box_step_field.value() ), 3 )

    def step_ampl(self):
        """
        A function to send a step amplitude value
        """
        self.cur_ampl_step = round( float( self.box_step_ampl.value() ), 1 )

    def sweep_type(self):
        self.cur_sweep = self.combo_sweep.currentText()

    def curve_name(self):
        self.cur_curve_name = self.text_edit_curve.toPlainText()
        #print( self.cur_curve_name )

    def exp_name(self):
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        #print( self.cur_exp_name )

    def scan(self):
        """
        A function to send a number of scans
        """
        self.cur_scan = int( self.box_scan.value() )
        try:
            self.parent_conn_dig.send( 'SC' + str( self.cur_scan ) )
        except AttributeError:
            pass

    def points(self):
        self.cur_points = int( self.box_points.value() )
        #print(self.cur_start_field)

    def cycles_func(self):
        """
        A function to update the number of ESEEM-averaging cycles.
        """
        self.cur_cycles = int( self.box_cycles.value() )

    def save_each_func(self):
        """
        Toggle saving each ESEEM-averaging cycle to its own file.
        """
        if self.Save_each.checkState().value == 2: # checked
            self.save_each_cycle = 1
        elif self.Save_each.checkState().value == 0: # unchecked
            self.save_each_cycle = 0

    def start_exp(self):
        if self.is_experiment == True:
            return

        self.dig_stop()
        self.dig_start_exp()

    def stop_exp(self):
        self.dig_stop()

    def update_coef_param(self, index):
        attr_name = f"P{index}_cf"
        
        if hasattr(self, attr_name):
            widget = getattr(self, attr_name)
            val = widget.value()
            value = val

            setattr(self, f"p{index}_coef", value)
            #print(f"Updated p{index}_coef to {value}")
            # Amplitude is a live-editable field (no dac_window change).
            self.schedule_live_apply()
        else:
            pass
            #print(f"Warning: {attr_name} not found")

    def update_pulse_type(self, index):

        combo = getattr(self, f"P{index}_type")
        text = combo.currentText()
        
        setattr(self, f"p{index}_typ", text)

        if index == 2:
            self.laser_flag = 1 if text == 'LASER' else 0

        #print(f"Pulse {index} type set to: {text}")
        # Type applies live (span-preserving; the worker sets function + freq
        # shape + n/b atomically). A LASER on/off instead flips laser_flag, which
        # is in the structure signature, so that case auto-restarts.
        self.schedule_live_apply()

    ###
    def update_pulse_phase(self, index):

        #text_edit = getattr(self, f"Phase_{index}")
        #temp = text_edit.toPlainText().strip()

        try:
            active_phases = []
            num_pulses = []
            for i in range(1, 10):
                attr_name = f"ph_{i}"
                p_len = getattr(self, f"P{i}_len").value()

                if not hasattr(self, attr_name) or p_len != 0.0:
                    phase_text = getattr(self, f"Phase_{i}").toPlainText().strip()
                    if p_len != 0.0:
                        active_phases.append(phase_text)
                        num_pulses.append(i)
                    setattr(self, attr_name, phase_text)

            a = self.expand_phase_cycling(*active_phases)
            setattr(self, "ph_1", a['receiver'])
            
            for i, pulse_phase in enumerate(a['pulses']):
                setattr(self, f"ph_{num_pulses[i+1]}", pulse_phase)
            
            #print(f"P0: {self.ph_1}")
            #print(f"P1: {self.ph_2}")
            #print(f"P2: {self.ph_3}")
            #print(f"P3: {self.ph_4}")
            #print(f"P4: {self.ph_5}")

            #if len(temp) >= 2: #and temp[0] == '[' and temp[-1] == ']':
            #    content = temp[:].split(',') #[1:-1]
            #    phases = [p.strip() for p in content if p.strip()]
                
            #    if len(phases) == 1:
            #        phases.append(phases[0])
                
            #    setattr(self, f"ph_{index}", phases)

        except (IndexError, AttributeError, Exception) as e:
            pass

        # The phase cycle is not live-editable (it changes the number of phases /
        # the GIM buffer layout). Route it through the debounced path so the edit
        # auto-restarts (announced) instead of silently waiting for Run Pulses.
        self.schedule_live_apply()

    def update_awg_generic(self, index, attr_suffix, val_suffix):
        widget = getattr(self, f"P{index}{attr_suffix}")
        value = self.add_mhz(widget.value()) if "_freq" in val_suffix or "wurst" in val_suffix else widget.value()

        target_attr = f"p{index}{val_suffix}" if val_suffix.startswith("_") else f"{val_suffix}{index}"
        setattr(self, target_attr, value)
        #print(f"Updated: {target_attr} = {value}")
        # Frequency / frequency-sweep are live-editable (no dac_window change).
        self.schedule_live_apply()

    ###
    def update_pulse_value(self, index, attr_suffix, val1_suffix, val2_suffix = None):
        """
        Универсальный обработчик для Pulse Start и Pulse Length.
        index: 1, 2, 3...
        attr_suffix: '_st' или '_len' (имя виджета)
        val1_suffix: '_start' или '_length' (основная переменная)
        val2_suffix: '_start_rect' или 'b' (второстепенная переменная)
        """
        spin_widget = getattr(self, f"P{index}{attr_suffix}")
        val1, val2 = self.round_and_change(spin_widget)

        if index == 1 and attr_suffix == '_st':
            setattr(self, f"p{index}_a", val1)
            if val2_suffix:
                setattr(self, f"p{index}{val1_suffix}", val2)
        else:
            setattr(self, f"p{index}{val1_suffix}", val1)
            if val2_suffix:
                setattr(self, f"p{index}{val2_suffix}", val2)

        if attr_suffix == '_len':
            self.update_pulse_phase(1)
        #print(f"Updated: p{index}{val1_suffix} = {val1}")

        # Start and Sigma apply live (Start guarded to stay non-overlapping /
        # array-ordered; Sigma is span-preserving). Length is not live-editable
        # (it changes dac_window), so it is in the structure signature and its
        # edit auto-restarts. Increment fields only affect swept experiments, not
        # the preview, so they are left alone.
        if attr_suffix in ('_st', '_len', '_sig'):
            self.schedule_live_apply()

    # ---- Live Edit helpers ----
    def live_edit_toggle(self):
        self.live_edit_on = 1 if self.live_edit_box.isChecked() else 0

    def _live_run_alive(self):
        """A dig_on preview is running (not a long experiment) and reachable."""
        if getattr(self, 'is_experiment', False):
            return False
        proc = getattr(self, 'digitizer_process', None)
        try:
            return proc is not None and proc.is_alive()
        except (AttributeError, ValueError):
            return False

    def _live_active_awg(self):
        """
        GUI indices of the active AWG pulses, in the same order and with the
        same filter dig_on setup uses (rect3.. in LASER mode, rect2.. otherwise;
        active == non-zero length). This is exactly the order of pb.pulse_array_awg.
        """
        rng = range(3, 10) if self.laser_flag == 1 else range(2, 10)
        out = []
        for k in rng:
            length = float(str(getattr(self, f'p{k}_length')).split(' ')[0])
            if length != 0:
                out.append(k)
        return out

    def _live_snapshot(self):
        """
        Live-editable state per active AWG pulse: [k, amplitude, frequency,
        awg_start, trigger_start, type, sigma]. frequency is a [start, end] pair
        for WURST / SECH-TANH, a scalar 'X MHz' otherwise. Type and sigma are
        span-preserving (same length -> same dac_window), so they re-arm live
        like amplitude/frequency. Plus the DETECTION start and its frequency (the
        latter only sets the digitizer IQ demod frequency, so it re-arms live).
        """
        pulses = []
        for k in self._live_active_awg():
            typ = getattr(self, f'p{k}_typ')
            if typ in ('WURST', 'SECH/TANH'):
                freq = [getattr(self, f'p{k}_freq'), getattr(self, f'wurst_sweep_cur_{k}')]
            else:
                freq = getattr(self, f'p{k}_freq')
            pulses.append([
                k,
                getattr(self, f'p{k}_coef'),
                freq,
                getattr(self, f'p{k}_start'),
                getattr(self, f'p{k}_start_rect'),
                typ,
                getattr(self, f'p{k}_sigma'),
            ])
        return {'p1': getattr(self, 'p1_start'),
                'p1_freq': getattr(self, 'p1_freq', None), 'pulses': pulses}

    def _structure_sig(self, snap):
        """
        Everything that is NOT live-editable: phase-cycle length, decimation,
        laser mode, active-pulse count and per-pulse length. Amplitude /
        frequency / start / sigma / type all re-arm live (type is span-preserving
        and the worker sets function + freq-shape + n/b atomically). A LASER
        on/off is caught via laser_flag (it changes the whole setup path); a
        Length change is caught here (it changes dac_window). A change to any of
        these makes the next live edit fall back to a full restart.
        """
        phases = len(self.ph_1) if getattr(self, 'ph_1', None) is not None else 0
        # Hash every active pulse's phase text, not just the receiver step count:
        # phases are not in the live 'PU' payload, so ANY phase-cycle edit (a
        # content change that keeps the same number of steps, or a step-count
        # change) must fall back to the announced restart instead of being
        # silently dropped.
        phase_sig = self._phase_sig()
        fixed = tuple((e[0], str(getattr(self, f'p{e[0]}_length'))) for e in snap['pulses'])
        # The DETECTION pulse (P1) length sets adc_window, which is baked into the
        # stream buffer / WIN_ADC / x_axis / data_raw at pulser_open -- it cannot
        # be re-armed live, so a detection-window change forces a restart.
        det_len = str(getattr(self, 'p1_length', ''))
        return (phases, phase_sig, self.decimation, self.laser_flag, fixed, det_len)

    def _phase_sig(self):
        """Normalized phase text of every active (non-zero-length) pulse, keyed by
        index. Any edit to a phase box changes this, forcing a live-edit restart
        (phases can only be applied by rebuilding, never via the 'PU' payload)."""
        out = []
        for i in range(1, 10):
            try:
                if float(str(getattr(self, f'p{i}_length')).split(' ')[0]) == 0:
                    continue
            except (ValueError, AttributeError):
                continue
            box = getattr(self, f'Phase_{i}', None)
            if box is not None:
                out.append((i, box.toPlainText().strip().lower().replace(' ', '')))
        return tuple(out)

    def _live_starts(self, snap):
        """Just the start columns, to detect whether an edit actually moved a pulse."""
        return tuple((e[0], str(e[3]), str(e[4])) for e in snap['pulses']) + (str(snap['p1']),)

    def _ns(self, s):
        return float(str(s).split(' ')[0])

    def _live_start_bases(self, snap):
        """Baseline start floats (detection, and per-pulse awg/trigger) recorded
        at Run Pulses, so live edits can be sent as GUI-space deltas."""
        return {
            'p1': self._ns(snap['p1']),
            'pulses': {e[0]: (self._ns(e[3]), self._ns(e[4])) for e in snap['pulses']},
        }

    def _live_start_safe(self, snap):
        """
        A Start change is live-safe only if the TRIGGER_AWG windows stay
        non-overlapping and in array order: each window must start at/after the
        previous one ends. Then dac_window == sum(lengths) is unchanged and the
        single-joined segment<->trigger mapping is preserved. Any overlap or
        reorder changes the merged buffer / mapping and needs a restart.
        """
        prev_end = None
        for e in snap['pulses']:
            k = e[0]
            length = float(str(getattr(self, f'p{k}_length')).split(' ')[0])
            s = float(str(e[4]).split(' ')[0])   # trigger start
            if prev_end is not None and s < prev_end - 0.05:
                return False
            prev_end = s + length
        return True

    def _validate_live_edit(self):
        """
        Reject-and-keep-running pre-check for a live edit: return an error string
        if the proposed phase cycle is invalid, else None. expand_phase_cycling
        silently LCM-reconciles lengths and coerces unknown tokens to '+x', so a
        cycle typo would otherwise slip straight to the card. On a non-None return
        live_apply neither pushes 'PU' nor restarts -- the running preview is left
        untouched and the error is shown. (Timing overlap is handled separately by
        the _live_start_safe -> restart path, since an overlap is a valid rebuild
        for the AWG single-joined buffer, not an error.)

        Checks: (1) every phase token in a plain comma list is recognized;
        (2) all *cycled* (>=2-step) plain lists share one length (a length-1 list
        is a non-cycling fixed phase and is exempt; bracket/paren notation is an
        intentional Kronecker expansion and is skipped).
        """
        valid = {'+x', '-x', '+y', '-y', 'x', 'y', 'i', '-i', '+', '-', '0'}
        simple_lens = []
        for i in range(1, 10):
            length = float(str(getattr(self, f'p{i}_length')).split(' ')[0])
            if length == 0:
                continue
            raw = getattr(self, f'Phase_{i}').toPlainText().strip()
            if '[' in raw or '(' in raw:
                continue
            toks = [t.strip().lower().replace(' ', '')
                    for t in raw.split(',') if t.strip()]
            for t in toks:
                if t not in valid:
                    return f'unrecognized phase "{t}" in pulse P{i}.'
            if len(toks) >= 2:
                simple_lens.append((i, len(toks)))

        if simple_lens:
            i0, L0 = simple_lens[0]
            for i, L in simple_lens[1:]:
                if L != L0:
                    return (f'phase-cycle length mismatch: P{i} has {L} steps but '
                            f'P{i0} has {L0} (receiver and every cycled pulse must '
                            f'share one length).')
        return None

    def schedule_live_apply(self):
        """(Re)start the debounce timer when live edit is armed and a preview runs.
        Defensive getattr: this is invoked from update_pulse_phase() during widget
        construction, before live_edit_on / opened are set."""
        if (getattr(self, 'live_edit_on', 0) and getattr(self, 'opened', 1) == 0
                and self._live_run_alive()):
            self.live_timer.start(int(self.Debounce.value()))

    def live_apply(self):
        """
        Debounce fired: push amplitude / frequency / start into the running
        worker as a 'PU' snapshot. A structural change, or a Start edit that
        would overlap or reorder the sequence, transparently restarts instead; an
        invalid phase cycle is rejected and the running preview is left untouched.
        """
        if not (self.live_edit_on and self.opened == 0 and self._live_run_alive()):
            return

        err = self._validate_live_edit()
        if err is not None:
            self.errors.appendPlainText(
                'Live Edit rejected — ' + err
                + ' Preview left running; fix the value.')
            return

        # update() tears down the worker via dig_stop(), whose
        # check_process_status() clears the log -- so announce a restart AFTER it,
        # or the label is wiped microseconds after it is written and never seen.
        # The new preview then appends its pulse lists below.
        snap = self._live_snapshot()
        if self._structure_sig(snap) != self.live_sig:
            self.update()
            self.errors.appendPlainText(
                'Live Edit: rebuild-only parameter changed (length / LASER / phase '
                'cycle / pulse count / decimation / detection window) — full '
                'restart performed.')
            return

        if self._live_starts(snap) != self.live_starts and not self._live_start_safe(snap):
            self.update()
            self.errors.appendPlainText(
                'Live Edit: the new Start times would overlap or reorder the '
                'pulses — full restart performed.')
            return

        # Send amplitude / frequency absolute, but starts as GUI-space deltas
        # from the recorded baseline (the worker adds them to the pristine
        # post-setup start, preserving the channel shift / LASER offset).
        base = getattr(self, 'live_base', None)
        if base is None:
            return
        payload = {'p1_d': self._ns(snap['p1']) - base['p1'],
                   'p1_freq': snap.get('p1_freq'), 'pulses': []}
        for e in snap['pulses']:
            k = e[0]
            if k not in base['pulses']:
                return  # active set drifted from baseline; a restart will resync
            a_base, t_base = base['pulses'][k]
            payload['pulses'].append([k, e[1], e[2],
                                      self._ns(e[3]) - a_base,
                                      self._ns(e[4]) - t_base,
                                      e[5], e[6]])   # type, sigma
        try:
            self.parent_conn_dig.send('PU' + json.dumps(payload))
        except (AttributeError, BrokenPipeError, OSError):
            pass

    def start_exp(self):
        if self.is_experiment == True:
            return

        self.dig_stop()
        self.dig_start_exp()

    def stop_exp(self):
        self.dig_stop()

    def combo_laser_fun(self):
        """
        A function to set a default laser
        """
        txt = str( self.Combo_laser.currentText() )
        if txt == 'Nd:YaG':
            self.combo_laser_num = 1
            self.laser_q_switch_delay = 0
        elif txt == 'NovoFEL':
            self.combo_laser_num = 2
            self.laser_q_switch_delay = 0

    def combo_synt_fun(self):
        """
        A function to set a default synthetizer for AWG arm
        """
        self.combo_synt = int( self.Combo_synt.currentText() )

    def combo_cor_fun(self):
        """
        A function to set a correction mode for awg pulses
        """
        txt = str( self.Combo_cor.currentText() )
        if txt == 'No':
            self.combo_cor = 0
        elif txt == 'Only Pi/2':
            self.combo_cor = 1
        elif txt == 'All':
            self.combo_cor = 2

    def combo_model_fun(self):
        """Resonator-correction model: measured profile or ideal RLC (+ phase)."""
        txt = str( self.Combo_model.currentText() )
        if txt == 'Measured':
            self.cor_model_cur = 'measured'
            self.phase_cor_cur = 'False'
        elif txt == 'Ideal RLC':
            self.cor_model_cur = 'ideal'
            self.phase_cor_cur = 'False'
        elif txt == 'Ideal RLC + phase':
            self.cor_model_cur = 'ideal'
            self.phase_cor_cur = 'True'

    def f0_func(self):
        """Resonator centre frequency (MHz) for the ideal-RLC correction."""
        self.f0_cur = float( self.F0_res.value() )

    def q_func(self):
        """Loaded Q for the ideal-RLC correction."""
        self.q_cur = float( self.Q_res.value() )

    def resfmt_fun(self):
        """Column format of the measured H(f) file; re-parse if one is loaded."""
        self.meas_h_fmt_cur = str( self.Combo_resfmt.currentText() )
        if getattr(self, '_meas_h_path', ''):
            self._load_meas_h(self._meas_h_path)

    def _parse_transfer(self, c0, c1, c2):
        """(freq_MHz, H_complex) from three columns per the H(f) format combo."""
        fmt = self.meas_h_fmt_cur
        f = c0 if fmt.startswith('MHz') else c0 * 1000.0      # -> MHz (device uses MHz)
        if 'Re · Im' in fmt:
            H = c1 + 1j * c2
        else:
            mag = 10.0 ** ( c1 / 20.0 ) if 'dB' in fmt else c1
            ph = np.deg2rad( c2 ) if 'deg' in fmt else c2
            H = mag * np.exp( 1j * ph )
        return f, H

    def open_resonator(self):
        """Load a 3-column measured transfer function (f, magnitude, phase)."""
        path = self.file_handler.open_file_dialog( multiprocessing = True,
                                                   directory = ldir.load('phase_awg', self.path) )
        if not path or path == 'None':
            return
        self._meas_h_path = path
        self._load_meas_h(path)

    def _load_meas_h(self, path):
        """Parse the measured complex transfer; store arrays for the worker."""
        try:
            _, data = self.file_handler.open_1d(path)
            data = np.atleast_2d(data)
            if data.shape[0] < 3:
                self.reson_file_lbl.setText("✗ needs ≥ 3 columns (f, mag, phase)")
                self.meas_freq_cur = None
                self.meas_H_cur = None
                return
            f, H = self._parse_transfer( np.asarray(data[0], float),
                                         np.asarray(data[1], float),
                                         np.asarray(data[2], float) )
            mask = ~( np.isnan(f) | np.isnan(H.real) | np.isnan(H.imag) )
            if mask.sum() < 2:
                self.reson_file_lbl.setText("✗ < 2 valid points")
                self.meas_freq_cur = None
                self.meas_H_cur = None
                return
            self.meas_freq_cur = f[mask]
            self.meas_H_cur = H[mask]
            self.reson_file_lbl.setText("✓ %s (%d pts)" % ( os.path.basename(path), int(mask.sum()) ))
        except Exception:
            self.reson_file_lbl.setText("✗ load failed")
            self.meas_freq_cur = None
            self.meas_H_cur = None

    def _hand_correction_to_worker(self, worker):
        """Copy the AWG resonator-correction GUI state onto a freshly created
        Worker so its _apply_awg_correction() (running in the child process) can
        read the model / f0 / Q / phase-correction settings.
        """
        worker.cor_model_cur = self.cor_model_cur
        worker.f0_cur = self.f0_cur
        worker.q_cur = self.q_cur
        worker.phase_cor_cur = self.phase_cor_cur
        worker.meas_freq_cur = self.meas_freq_cur
        worker.meas_H_cur = self.meas_H_cur

    def b_sech_func(self):
        """
        A function to set b_sech parameter for the SECH/TANH pulse
        """
        self.b_sech_cur = float( self.B_sech.value() )

    def quad_online(self):
        """
        Turn on/off Quadrature phase correction
        """
        if self.Quad_cor.checkState().value == 2: # checked
            self.quad = 1
        elif self.Quad_cor.checkState().value == 0: # unchecked
            self.quad = 0
        
        try:
            self.parent_conn_dig.send( 'QC' + str( self.quad ) )
        except AttributeError:
            pass

    def iq_online(self):
        """
        Turn on/off IQ  correction
        """
        if self.IQ_corr.checkState().value == 2: # checked
            self.iq_cor = 1
        elif self.IQ_corr.checkState().value == 0: # unchecked
            self.iq_cor = 0
        
        #try:
        #    self.parent_conn_dig.send( 'QC' + str( self.quad ) )
        #except AttributeError:
        #    pass

    def save_2d(self):
        """
        """
        if self.Save2D.checkState().value == 2: # checked
            self.save2d = 1
        elif self.Save2D.checkState().value == 0: # unchecked
            self.save2d = 0
        
        #try:
        #    self.parent_conn_dig.send( 'SV' + str( self.quad ) )
        #except AttributeError:
        #    pass

    def zero_order_func(self):
        """
        A function to change the zero order phase correction value
        """
        self.zero_order = float( self.Zero_order.value() ) / self.deg_rad

        # cycling
        if self.zero_order < 0.0:
            self.Zero_order.setValue(360.0)
            self.zero_order = float( self.Zero_order.value() ) / self.deg_rad
        else:
            pass

        if self.zero_order > 2*np.pi:
            self.Zero_order.setValue(0.0)
            self.zero_order = float( self.Zero_order.value() ) / self.deg_rad
        else:
            pass

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'ZO' + str( self.zero_order ) )
            except AttributeError:
                pass

    def first_order_func(self):
        """
        A function to change the first order phase correction value
        """
        self.first_order = float( self.First_order.value() ) / self.first_order_coef

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'FO' + str( self.first_order ) )
            except AttributeError:
                pass

    def second_order_func(self):
        """
        A function to change the second order phase correction value
        """
        self.second_order = float( self.Second_order.value() ) / self.sec_order_coef
        
        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'SO' + str( self.second_order ) )
            except AttributeError:
                pass

    def p_to_drop_func(self):
        """
        A function to change the number of points to drop
        """
        self.p_to_drop = int( self.P_to_drop.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'PD' + str( self.p_to_drop ) )
            except AttributeError:
                pass

    def fft_online(self):
        """
        Turn on/off FFT
        """

        if self.fft_box.checkState().value == 2: # checked
            self.fft = 1
        elif self.fft_box.checkState().value == 0: # unchecked
            self.fft = 0
        
        try:
            self.parent_conn_dig.send( 'FF' + str( self.fft ) )
        except AttributeError:
            pass

    def change_live_mode(self):
        """
        Turn on/off live mode
        """

        if self.live_mode.checkState().value == 2: # checked
            self.l_mode = 1
        elif self.live_mode.checkState().value == 0: # unchecked
            self.l_mode = 0
        
        try:
            self.parent_conn_dig.send( 'LM' + str( self.l_mode ) )
        except AttributeError:
            pass

    def win_left(self):
        """
        A function to change left integration window
        """
        self.cur_win_left = int( float( self.Win_left.value() ) / self.time_per_point )
        if round( self.cur_win_left * self.time_per_point, 1) > round( float( self.remove_ns( self.p1_length ) ), 1):
            self.cur_win_left = int( round( float( self.remove_ns( self.p1_length ) ), 1) / self.time_per_point )
            self.Win_left.setValue( round( self.cur_win_left * self.time_per_point, 1) )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'WL' + str( self.cur_win_left ) )
            except AttributeError:
                pass

    def win_right(self):
        self.cur_win_right = int( float( self.Win_right.value() ) / self.time_per_point )
        if round( self.cur_win_right * self.time_per_point, 1) > round( float( self.remove_ns( self.p1_length ) ), 1):
            self.cur_win_right = int( round( float( self.remove_ns( self.p1_length ) ), 1) / self.time_per_point )
            self.Win_right.setValue( round( self.cur_win_right * self.time_per_point, 1) )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'WR' + str( self.cur_win_right ) )
            except AttributeError:
                pass

    def acq_number(self):
        """
        A function to change number of averages
        """
        self.number_averages = int( self.Acq_number.value() )

        #if self.opened == 0:
        try:
            self.parent_conn_dig.send( 'NA' + str( self.number_averages ) )
        except AttributeError:
            pass

    def open_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Open File', directory = ldir.load('phase_awg', self.path), filter = "AWG pulse phase list (*.phase_awg)", options = QFileDialog.Option.DontUseNativeDialog)

        filedialog.setMinimumWidth(800)
        
        tree = filedialog.findChild(QTreeView)
        header = tree.header()
        for i in range(header.count()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        buttons = filedialog.findChildren(QPushButton)
        seen_texts = []
        for btn in buttons:
            if btn.text() in seen_texts:
                btn.hide()
            else:
                seen_texts.append(btn.text())
        
        line_edit = filedialog.findChild(QLineEdit)

        if line_edit:
            line_edit.setCompleter(None)

        size_grip = filedialog.findChild(QSizeGrip)
        if size_grip:
            size_grip.setVisible(False)

        filedialog.setStyleSheet("""
            QFileDialog, QDialog { 
                background-color: rgb(42, 42, 64); 
                color: rgb(193, 202, 227);
                font-size: 11px;
            }

            QFileDialog QListView {
                min-width: 150px; 
                background-color: rgb(35, 35, 55);
                border: 1px solid rgb(63, 63, 97);
                color: rgb(193, 202, 227);
            }

            QTreeView {
                min-width: 500px;
                background-color: rgb(35, 35, 55);
                border: 1px solid rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                outline: none;
            }

            QFileDialog QFrame#qt_contents, QFileDialog QWidget {
                background-color: rgb(42, 42, 64);
            }
            
            QFileDialog QToolBar {
                background-color: rgb(42, 42, 64);
                border-bottom: 1px solid rgb(63, 63, 97);
                min-height: 34px; 
                padding: 2px;
            }

            QToolButton {
                background-color: rgb(63, 63, 97);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 4px;
                min-height: 23px; 
                max-height: 23px;
                min-width: 23px;
                qproperty-iconSize: 14px 14px; 
                margin: 0px 2px;
                vertical-align: middle;
            }

            QToolButton:hover {
                border: 1px solid rgb(211, 194, 78);
                background-color: rgb(83, 83, 117);
            }

            QLineEdit, QComboBox {
                background-color: rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 3px;
                padding: 2px 5px;
                min-height: 16px; 
            }

            QLineEdit:focus, QFileDialog QComboBox:focus {
                border: 1px solid rgb(211, 194, 78);
                color: rgb(211, 194, 78);
                outline: none;
            }

            QFileDialog QComboBox#lookInCombo {
                background-color: rgb(42, 42, 64);
                color: rgb(193, 202, 227);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 3px;
                padding-left: 5px;
                min-height: 19px;
                max-height: 19px;
                selection-background-color: rgb(48, 48, 75);
                selection-color: rgb(211, 194, 78);
            }

            QFileDialog QComboBox#lookInCombo QAbstractItemView {
                outline: none;
                border: 1px solid rgb(48, 48, 75);
                background-color: rgb(42, 42, 64);
            }

            QFileDialog QDialogButtonBox QPushButton {
                background-color: rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 4px;
                font-weight: bold;
                min-height: 23px;
                max-height: 23px;
                min-width: 75px;
                padding: 0px 12px;
            }

            QFileDialog QDialogButtonBox QPushButton:hover {
                background-color: rgb(83, 83, 117);
                border: 1px solid rgb(211, 194, 78);
                color: rgb(211, 194, 78);
            }
            
            QHeaderView::section {
                background-color: rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                padding: 4px;
                border: none;
                border-right: 1px solid rgb(83, 83, 117);
                min-height: 20px;
            }

            QScrollBar:vertical {
                border: none; background: rgb(43, 43, 77); 
                width: 10px; margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgb(193, 202, 227); min-height: 20px; border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover { background: rgb(211, 194, 78); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

            QScrollBar:horizontal {
                border: none; 
                background: rgb(43, 43, 77); 
                height: 10px; 
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgb(193, 202, 227); 
                min-width: 20px; 
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover { 
                background: rgb(211, 194, 78); 
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
                width: 0px; 
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { 
                background: none; 
            }

            QFileDialog QDialogButtonBox {
                background-color: rgb(42, 42, 64);
                border-top: 1px solid rgb(63, 63, 97);
                padding: 6px;
            }

            QFileDialog QLabel {
                color: rgb(193, 202, 227);
            }

            QFileDialog QListView::item:hover {
                background-color: rgb(48, 48, 75);
                color: rgb(211, 194, 78);
            }

            QHeaderView {
                background-color: rgb(63, 63, 97);
            }

            QFileDialog QListView#sidebar:inactive, 
            QTreeView:inactive {
                selection-background-color: rgb(35, 35, 55);
                selection-color: rgb(211, 194, 78);
            }

            QTreeView::item:hover { 
                background-color: rgb(48, 48, 75);
                color: rgb(211, 194, 78); 
                } 
            QTreeView::item:selected:inactive, 
            QFileDialog QListView#sidebar::item:selected:inactive {
                selection-background-color: rgb(63, 63, 97);
                selection-color: rgb(211, 194, 78);
            }
            QFileDialog QListView#sidebar::item {
                padding-left: 5px; 
                padding-top: 5px;
            }

            QMenu {
                background-color: rgb(42, 42, 64);
                border: 1px solid rgb(63, 63, 97);
                padding: 3px;
            }
            QMenu::item { color: rgb(211, 194, 78); } 
            QMenu::item:selected { 
                background-color: rgb(48, 48, 75); 
                color: rgb(211, 194, 78);
                }

        """)
        filedialog.setFileMode(QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

    def save_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Save File', directory = ldir.load('phase_awg', self.path), filter = "AWG pulse phase list (*.phase_awg)", options = QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

        filedialog.setMinimumWidth(800)
        tree = filedialog.findChild(QTreeView)
        header = tree.header()
        for i in range(header.count()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        buttons = filedialog.findChildren(QPushButton)
        seen_texts = []
        for btn in buttons:
            if btn.text() in seen_texts:
                btn.hide()
            else:
                seen_texts.append(btn.text())
        
        line_edit = filedialog.findChild(QLineEdit)

        if line_edit:
            line_edit.setCompleter(None)

        size_grip = filedialog.findChild(QSizeGrip)
        if size_grip:
            size_grip.setVisible(False)

        filedialog.setStyleSheet("""
            QFileDialog, QDialog { 
                background-color: rgb(42, 42, 64); 
                color: rgb(193, 202, 227);
                font-size: 11px;
            }

            QFileDialog QListView {
                min-width: 150px; 
                background-color: rgb(35, 35, 55);
                border: 1px solid rgb(63, 63, 97);
                color: rgb(193, 202, 227);
            }

            QTreeView {
                min-width: 500px;
                background-color: rgb(35, 35, 55);
                border: 1px solid rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                outline: none;
            }

            QFileDialog QFrame#qt_contents, QFileDialog QWidget {
                background-color: rgb(42, 42, 64);
            }
            
            QFileDialog QToolBar {
                background-color: rgb(42, 42, 64);
                border-bottom: 1px solid rgb(63, 63, 97);
                min-height: 34px; 
                padding: 2px;
            }

            QToolButton {
                background-color: rgb(63, 63, 97);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 4px;
                min-height: 23px; 
                max-height: 23px;
                min-width: 23px;
                qproperty-iconSize: 14px 14px; 
                margin: 0px 2px;
                vertical-align: middle;
            }

            QToolButton:hover {
                border: 1px solid rgb(211, 194, 78);
                background-color: rgb(83, 83, 117);
            }

            QLineEdit, QComboBox {
                background-color: rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 3px;
                padding: 2px 5px;
                min-height: 16px; 
            }

            QLineEdit:focus, QFileDialog QComboBox:focus {
                border: 1px solid rgb(211, 194, 78);
                color: rgb(211, 194, 78);
                outline: none;
            }

            QFileDialog QComboBox#lookInCombo {
                background-color: rgb(42, 42, 64);
                color: rgb(193, 202, 227);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 3px;
                padding-left: 5px;
                min-height: 19px;
                max-height: 19px;
                selection-background-color: rgb(48, 48, 75);
                selection-color: rgb(211, 194, 78);
            }

            QFileDialog QComboBox#lookInCombo QAbstractItemView {
                outline: none;
                border: 1px solid rgb(48, 48, 75);
                background-color: rgb(42, 42, 64);
            }

            QFileDialog QDialogButtonBox QPushButton {
                background-color: rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                border: 1px solid rgb(83, 83, 117);
                border-radius: 4px;
                font-weight: bold;
                min-height: 23px;
                max-height: 23px;
                min-width: 75px;
                padding: 0px 12px;
            }

            QFileDialog QDialogButtonBox QPushButton:hover {
                background-color: rgb(83, 83, 117);
                border: 1px solid rgb(211, 194, 78);
                color: rgb(211, 194, 78);
            }
            
            QHeaderView::section {
                background-color: rgb(63, 63, 97);
                color: rgb(193, 202, 227);
                padding: 4px;
                border: none;
                border-right: 1px solid rgb(83, 83, 117);
                min-height: 20px;
            }

            QScrollBar:vertical {
                border: none; background: rgb(43, 43, 77); 
                width: 10px; margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgb(193, 202, 227); min-height: 20px; border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover { background: rgb(211, 194, 78); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

            QScrollBar:horizontal {
                border: none; 
                background: rgb(43, 43, 77); 
                height: 10px; 
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgb(193, 202, 227); 
                min-width: 20px; 
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover { 
                background: rgb(211, 194, 78); 
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { 
                width: 0px; 
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { 
                background: none; 
            }

            QFileDialog QDialogButtonBox {
                background-color: rgb(42, 42, 64);
                border-top: 1px solid rgb(63, 63, 97);
                padding: 6px;
            }

            QFileDialog QLabel {
                color: rgb(193, 202, 227);
            }

            QFileDialog QListView::item:hover {
                background-color: rgb(48, 48, 75);
                color: rgb(211, 194, 78);
            }

            QHeaderView {
                background-color: rgb(63, 63, 97);
            }

            QFileDialog QListView#sidebar:inactive, 
            QTreeView:inactive {
                selection-background-color: rgb(35, 35, 55);
                selection-color: rgb(211, 194, 78);
            }

            QTreeView::item:hover { 
                background-color: rgb(48, 48, 75);
                color: rgb(211, 194, 78); 
                } 
            QTreeView::item:selected:inactive, 
            QFileDialog QListView#sidebar::item:selected:inactive {
                selection-background-color: rgb(63, 63, 97);
                selection-color: rgb(211, 194, 78);
            }
            QFileDialog QListView#sidebar::item {
                padding-left: 5px; 
                padding-top: 5px;
            }

            QMenu {
                background-color: rgb(42, 42, 64);
                border: 1px solid rgb(63, 63, 97);
                padding: 3px;
            }
            QMenu::item { color: rgb(211, 194, 78); } 
            QMenu::item:selected { 
                background-color: rgb(48, 48, 75); 
                color: rgb(211, 194, 78);
                }

        """)

        filedialog.setFileMode(QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file)
        filedialog.show()

    def open_file(self, filename):
        """
        A function to open a pulse list
        :param filename: string
        """
        # Block loading a preset while an experiment is running: it would
        # overwrite the GUI and leak digitizer/field commands into the running
        # experiment's command pipe. Only valid when idle or previewing
        # (Run Pulses).
        if self.is_experiment:
            self.message('Cannot load a preset while an experiment is running.')
            return

        self.path = os.path.dirname(filename)
        ldir.save('phase_awg', self.path)
        self.opened = 1

        # A preset does not define pulse linking; reset the Link row to No and
        # the Settings Link parameter to Off so a freshly loaded sequence starts
        # uncoupled (this also keeps the pulse values loaded below from
        # triggering link propagation).
        self.Combo_link.setCurrentText("Off")
        for i in range(1, 10):
            getattr(self, f"P{i}_lk").setCurrentText("No")

        text = open(filename).read()
        lines = text.split('\n')

        self.setter(text, 0, self.P1_type, self.P1_st, self.P1_len, self.P1_sig, self.P1_fr, self.P1_sw, self.P1_cf, self.Phase_1, self.P1_st_inc, self.P1_len_inc, self.P1_st_inc2)
        self.setter(text, 1, self.P2_type, self.P2_st, self.P2_len, self.P2_sig, self.P2_fr, self.P2_sw, self.P2_cf, self.Phase_2, self.P2_st_inc, self.P2_len_inc, self.P2_st_inc2)
        self.setter(text, 2, self.P3_type, self.P3_st, self.P3_len, self.P3_sig, self.P3_fr, self.P3_sw, self.P3_cf, self.Phase_3, self.P3_st_inc, self.P3_len_inc, self.P3_st_inc2)
        self.setter(text, 3, self.P4_type, self.P4_st, self.P4_len, self.P4_sig, self.P4_fr, self.P4_sw, self.P4_cf, self.Phase_4, self.P4_st_inc, self.P4_len_inc, self.P4_st_inc2)
        self.setter(text, 4, self.P5_type, self.P5_st, self.P5_len, self.P5_sig, self.P5_fr, self.P5_sw, self.P5_cf, self.Phase_5, self.P5_st_inc, self.P5_len_inc, self.P5_st_inc2)
        self.setter(text, 5, self.P6_type, self.P6_st, self.P6_len, self.P6_sig, self.P6_fr, self.P6_sw, self.P6_cf, self.Phase_6, self.P6_st_inc, self.P6_len_inc, self.P6_st_inc2)
        self.setter(text, 6, self.P7_type, self.P7_st, self.P7_len, self.P7_sig, self.P7_fr, self.P7_sw, self.P7_cf, self.Phase_7, self.P7_st_inc, self.P7_len_inc, self.P7_st_inc2)
        self.setter(text, 7, self.P8_type, self.P8_st, self.P8_len, self.P8_sig, self.P8_fr, self.P8_sw, self.P8_cf, self.Phase_8, self.P8_st_inc, self.P8_len_inc, self.P8_st_inc2)
        self.setter(text, 8, self.P9_type, self.P9_st, self.P9_len, self.P9_sig, self.P9_fr, self.P9_sw, self.P9_cf, self.Phase_9, self.P9_st_inc, self.P9_len_inc, self.P9_st_inc2)

        self.Field.setValue( float( lines[10].split(':  ')[1] ) )
        #self.Delay.setValue( float( lines[9].split(':  ')[1] ) )
        self.Ampl_1.setValue( int( lines[12].split(':  ')[1] ) )
        self.Ampl_2.setValue( int( lines[13].split(':  ')[1] ) )
        self.Phase.setValue( float( lines[14].split(':  ')[1] ) )
        self.N_wurst.setValue( int( lines[15].split(':  ')[1] ) )
        self.B_sech.setValue( float( lines[16].split(':  ')[1] ) )

        #self.live_mode.setCheckState(Qt.CheckState.Unchecked)
        #self.fft_box.setCheckState(Qt.CheckState.Unchecked)
        #self.Quad_cor.setCheckState(Qt.CheckState.Unchecked)
        self.Win_left.setValue( round(float( lines[19].split(':  ')[1] ), 1) )
        self.Win_right.setValue( round(float( lines[20].split(':  ')[1] ), 1) )
        self.Acq_number.setValue( int( lines[21].split(':  ')[1] ) )
        self.Dec.setValue( int( lines[27].split(':  ')[1] ) )

        try:
            self.P_to_drop.setValue( int( lines[22].split(':  ')[1] ) )
            self.Zero_order.setValue( float( lines[23].split(':  ')[1] ) )
            self.First_order.setValue( float( lines[24].split(':  ')[1] ) )
            self.Second_order.setValue( float( lines[25].split(':  ')[1] ) )
            self.Combo_laser.setCurrentText( str( lines[26].split(':  ')[1] ) )
        except IndexError:
            pass

        self.box_points.setValue( int( lines[28].split(':  ')[1] ) )
        self.box_scan.setValue( int( lines[29].split(':  ')[1] ) )
        self.Log_start.setValue( float( lines[30].split(':  ')[1] ) )
        self.Log_end.setValue( float( lines[31].split(':  ')[1] ) )
        self.box_st_field.setValue( float( lines[32].split(':  ')[1] ) )
        self.box_end_field.setValue( float( lines[33].split(':  ')[1] ) )
        self.box_step_field.setValue( float( lines[34].split(':  ')[1] ) )
        self.combo_sweep.setCurrentText( str( lines[35].split(':  ')[1] ) )
        self.Rep_rate.setValue( float( lines[9].split(':  ')[1] ) )

        try:
            if int(lines[36].split(':  ')[1]) == 2:
                self.IQ_corr.setChecked(True)
            else:
                self.IQ_corr.setChecked(False)
            self.X0.setValue( float( lines[37].split(':  ')[1] ) )
            self.XDelta.setValue( float( lines[38].split(':  ')[1] ) )

            self.box_step_ampl.setValue( float( lines[39].split(':  ')[1] ) )
        except IndexError:
            pass

        # ESEEM-averaging fields are appended at the very end; older presets
        # without them are left at their defaults.
        try:
            self.box_cycles.setValue( int( lines[40].split(':  ')[1] ) )
            if int( lines[41].split(':  ')[1] ) == 2:
                self.Save_each.setChecked(True)
            else:
                self.Save_each.setChecked(False)
        except (IndexError, ValueError):
            pass

        self.dig_stop()

        self.fft = 0
        self.quad = 0
        self.opened = 0

        # A freshly loaded preset no longer matches whatever sequence a
        # preview is still running (the dig_stop above is a no-op while
        # opened == 1). If Run Pulses is active, stop it now so the operator
        # restarts cleanly with Run Pulses on the loaded sequence.
        if self._live_run_alive():
            self.dig_stop()

    def setter(self, text, index, typ, st, leng, sig, freq, w_sweep, coef, phase, d_start, len_inc, d_start2 = None):
        """
        Auxiliary function to set all the values from *.awg file
        """
        array = text.split('\n')[index].split(':  ')[1].split(',  ')

        typ.setCurrentText( array[0] )
        if index != 0:
            st.setValue( float( array[1] ) )
            leng.setValue( float( array[2] ) )
            sig.setValue( float( array[3] ) )
        else:
            st.setValue( float( array[1] ) )
            leng.setValue( float( array[2] ) )
            sig.setValue( float( array[3] ) )

        freq.setValue( int( array[4] ) )
        w_sweep.setValue( int( array[5] ) )
        coef.setValue( float( array[6] ) )
        phase.setPlainText( str( (array[7])[1:-1] ) )
        d_start.setValue( float( array[8] ) )
        len_inc.setValue( float( array[9] ) )
        # Start Increment 2 is appended after the original fields; older presets
        # (without it) fall back to 0 so they still load.
        if d_start2 is not None:
            d_start2.setValue( float( array[10] ) if len( array ) > 10 else 0.0 )

    def apply_seqcalc_pulses(self, filename):
        """Apply ONLY the pulse layout from a Sequence-Calculator preset.

        Unlike ``open_file`` (which restores a whole experiment), this leaves
        every tuned acquisition parameter alone — field, rep rate, detection
        window, decimation, scans, sweep type, amplitudes, IQ correction, etc.
        It is what the calculator's "Open in AWG" pushes into an already-open,
        already-tuned window, so a delay/phase tweak never clobbers the setup.

        Per pulse it sets the start position and the phase. P1 is the detection
        pulse: its start is the detection position and its phase is the receiver.
        The number of pulses follows the preset (a pulse is "used" when its
        length field is non-zero). Lengths, types, amplitudes, frequencies and
        increments the operator already tuned are preserved; we assign them only
        for a pulse the preset newly switches on (currently length 0), and we
        switch a pulse off (length 0) when the new sequence no longer uses it.
        """
        # Same pipe-leak risk as open_file: block while an experiment runs.
        if self.is_experiment:
            self.message('Cannot apply pulses while an experiment is running.')
            return

        self.opened = 1

        # A preset does not define pulse linking; reset the Link row to No and
        # the Settings Link parameter to Off so the pushed layout starts
        # uncoupled (this also keeps the pulse Starts set below from triggering
        # link propagation).
        self.Combo_link.setCurrentText("Off")
        for i in range(1, 10):
            getattr(self, f"P{i}_lk").setCurrentText("No")

        lines = open(filename).read().split('\n')
        for i in range(1, 10):
            try:
                array = lines[i - 1].split(':  ')[1].split(',  ')
            except IndexError:
                continue
            preset_len = float( array[2] )
            used = (i == 1) or (preset_len != 0.0)
            st_box = getattr(self, f'P{i}_st')
            len_box = getattr(self, f'P{i}_len')
            if used:
                st_box.setValue( float( array[1] ) )
                getattr(self, f'Phase_{i}').setPlainText( str( array[7][1:-1] ) )
                if len_box.value() == 0.0:          # pulse newly switched on
                    getattr(self, f'P{i}_type').setCurrentText( array[0] )
                    len_box.setValue( preset_len )
            else:
                len_box.setValue( 0.0 )             # drop a now-unused pulse
        self.dig_stop()
        self.fft = 0
        self.quad = 0
        self.opened = 0

        # If Run Pulses is active, stop the running preview so the loaded layout
        # is applied cleanly on the next Run Pulses (see open_file).
        if self._live_run_alive():
            self.dig_stop()

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        self.path = os.path.dirname(filename)
        ldir.save('phase_awg', self.path)
        if filename[-9:] != 'phase_awg':
            filename = filename + '.phase_awg'
        with open(filename, 'w') as file:
            for i in range(1, 10):
                p_type = getattr(self, f'P{i}_type').currentText()
                st = getattr(self, f'P{i}_st').value()
                length = getattr(self, f'P{i}_len').value()
                sig = getattr(self, f'P{i}_sig').value()
                fr = getattr(self, f'P{i}_fr').value()
                sw = getattr(self, f'P{i}_sw').value()
                cf = getattr(self, f'P{i}_cf').value()
                #ph = getattr(self, f'ph_{i}')
                ph_list = getattr(self, f'Phase_{i}').toPlainText().strip()
                d_start = getattr(self, f'P{i}_st_inc').value()
                len_inc = getattr(self, f'P{i}_len_inc').value()
                d_start2 = getattr(self, f'P{i}_st_inc2').value()

                ph_str =  f"[{ph_list}]"#f"[{','.join(ph)}]"

                # Start Increment 2 is appended last so older readers ignore it.
                file.write(f"P{i}:  {p_type},  {st},  {length},  {sig},  {fr},  {sw},  {cf},  {ph_str},  {d_start},  {len_inc},  {d_start2}\n")


            file.write( 'Rep rate:  ' + str(self.Rep_rate.value()) + '\n' )
            file.write( 'Field:  ' + str(self.Field.value()) + '\n' )
            file.write( 'Delay:  ' + str(0) + '\n' )
            file.write( 'Ampl 1:  ' + str(self.Ampl_1.value()) + '\n' )
            file.write( 'Ampl 2:  ' + str(self.Ampl_2.value()) + '\n' )
            file.write( 'Phase:  ' + str(self.Phase.value()) + '\n' )
            file.write( 'N WURST; SECH/TANH:  ' + str(self.N_wurst.value()) + '\n' )
            file.write( 'B SECH/TANH:  ' + str(self.B_sech.value()) + '\n' )
            file.write( 'Points:  ' + str( 2016 ) + '\n' )
            file.write( 'Horizontal offset:  ' + str( 1024 ) + '\n' )
            file.write( 'Window left:  ' + str(self.Win_left.value()) + '\n' )
            file.write( 'Window right:  ' + str(self.Win_right.value()) + '\n' )
            file.write( 'Acquisitions:  ' + str(self.Acq_number.value()) + '\n' )
            file.write( 'Points to Drop:  ' + str(self.P_to_drop.value()) + '\n' )
            file.write( 'Zero order:  ' + str(self.Zero_order.value()) + '\n' )
            file.write( 'First order:  ' + str(self.First_order.value()) + '\n' )
            file.write( 'Second order:  ' + str(self.Second_order.value()) + '\n' )
            file.write( 'Laser:  ' + str( self.Combo_laser.currentText() ) + '\n' )
            file.write( 'Decimation:  ' + str( self.Dec.value() ) + '\n' )

            file.write( 'Points:  ' + str( self.box_points.value() ) + '\n' )
            file.write( 'Scans:  ' + str( self.box_scan.value() ) + '\n' )
            file.write( 'Log Start:  ' + str( self.Log_start.value() ) + '\n' )
            file.write( 'Log End:  ' + str( self.Log_end.value() ) + '\n' )
            file.write( 'Start Field:  ' + str( self.box_st_field.value() ) + '\n' )
            file.write( 'End Field:  ' + str( self.box_end_field.value() ) + '\n' )
            file.write( 'Field Step:  ' + str( self.box_step_field.value() ) + '\n' )
            file.write( 'Sweep Type:  ' + self.combo_sweep.currentText() + '\n' )
            file.write( 'IQ Correction:  ' + str( self.IQ_corr.checkState().value ) + '\n' )

            file.write( 'X0:  ' + str( self.X0.value() ) + '\n' )
            file.write( 'dX:  ' + str( self.XDelta.value() ) + '\n' )

            file.write( 'Amplitude Step:  ' + str( self.box_step_ampl.value() ) + '\n' )

            # ESEEM-averaging settings (appended at the end for backward compat)
            file.write( 'Cycles:  ' + str( self.box_cycles.value() ) + '\n' )
            file.write( 'Save Each Cycle:  ' + str( self.Save_each.checkState().value ) + '\n' )

    def remove_ns(self, string1):
        return string1.split(' ')[0]

    def add_ns(self, string1):
        """
        Function to add ' ns'
        """
        return str( string1 ) + ' ns'

    def add_mhz(self, string1):
        """
        Function to add ' MHz'
        """
        return str( string1 ) + ' MHz'

    def check_length(self, length):
        self.errors.clear()

        if int( length ) != 0 and int( length ) < 12:
            self.errors.appendPlainText( 'Pulse length should be longer than 12 ns' )

        return length

    def round_length(self, length):
        return self.add_ns( length )

    def quit(self):
        """
        A function to quit the programm
        """
        self.dig_stop()
        sys.exit()

    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return round(( y * ( ( x // y ) + (round(x % y, 2) > 0) ) ), 1)

    def round_and_change(self, doubleBox):
        """
        """
        raw = doubleBox.value()
        current = self.round_to_closest( raw, 3.2 )
        if current != raw:
            doubleBox.setValue( current )
        return self.add_ns( doubleBox.value() ), self.add_ns( round(doubleBox.value() + self.awg_output_shift, 1) )

    def round_and_change_no_ns(self, doubleBox):
        """
        """
        raw = doubleBox.value()
        current = self.round_to_closest( raw, 3.2 )
        if current != raw:
            doubleBox.setValue( current )
        return doubleBox.value()

    def decimat(self):
        """
        A function to set decimation coefficient
        """
        current = self.Dec.value()
        
        if current == 3:
            new_val = 4 if self.decimation == 2 else 2
            self.Dec.blockSignals(True)
            self.Dec.setValue(new_val)
            self.Dec.blockSignals(False)
            self.decimation = new_val
        else:
            self.decimation = current

        self.time_per_point = 0.4 * self.decimation
        self.win_left()
        self.win_right()

        # Decimation is fixed at pulser_open; a live change can only be honored
        # by a restart -- the debounced path detects the structural change.
        self.schedule_live_apply()

    def n_wurst(self):
        """
        A function to set n_wurst parameter for the WURST and SECH/TANH pulses
        """
        self.n_wurst_cur = int( self.N_wurst.value() )

    def ch0_amp(self):
        """
        A function to set AWG CH0 amplitude
        """
        self.ch0_ampl = self.Ampl_1.value()

    def ch1_amp(self):
        """
        A function to set AWG CH1 amplitude
        """
        self.ch1_ampl = self.Ampl_2.value()
    
    def awg_phase(self):
        """
        A function to set AWG CH1 phase shift
        """
        self.cur_phase = self.Phase.value() * np.pi * 2 / 360
        ####
        ###try:
        ###    self.errors.appendPlainText( str( self.cur_phase ) )
        ###    self.parent_conn_dig.send( 'PH' + str( self.cur_phase ) )
        ###except AttributeError:
        ###    pass

    def phase_converted(self, ph_str):
        if ph_str == '+x':
            return 0
        elif ph_str == '-x':
            return 3.141593
        elif ph_str == '+y':
            return -1.57080
        elif ph_str == '-y':
            return -4.712390

    def rep_rate(self):
        """
        A function to change a repetition rate
        """
        self.repetition_rate = str( self.Rep_rate.value() ) + ' Hz'

        if self.laser_flag != 1:
            pass
        elif self.laser_flag == 1 and self.combo_laser_num == 1:
            self.repetition_rate = '9.9 Hz'
            ###self.pb.pulser_repetition_rate( self.repetition_rate )
            self.Rep_rate.setValue(9.9)
            self.errors.appendPlainText( '9.9 Hz is a maximum repetiton rate with LASER pulse' )
        elif self.laser_flag == 1 and self.combo_laser_num == 2:
            pass

        self._update_rep_time_display()

        try:
            self.parent_conn_dig.send( 'RR' + str( self.repetition_rate.split(' ')[0] ) )
        except AttributeError:
            pass

    def _update_rep_time_display(self):
        rate_hz = float( self.Rep_rate.value() )
        if rate_hz <= 0:
            self.Rep_rate.setSuffix(" Hz")
            return
        t_s = 1.0 / rate_hz
        if   t_s >= 1.0:   val, unit = t_s,       "s"
        elif t_s >= 1e-3:  val, unit = t_s * 1e3, "ms"
        elif t_s >= 1e-6:  val, unit = t_s * 1e6, "µs"
        else:              val, unit = t_s * 1e9, "ns"
        self.Rep_rate.setSuffix(f" Hz | {val:.1f} {unit}")

    def field(self):
        """
        A function to change a magnetic field
        """
        self.mag_field = float( self.Field.value() )
        ###self.bh15.magnet_field( self.mag_field )
        try:
            #self.errors.appendPlainText( str( self.mag_field ) )
            self.parent_conn_dig.send( 'FI' + str( self.mag_field ) )
        except AttributeError:
            pass

    def update(self):
        """
        A function to run pulses
        """
        if self.is_experiment == True:
            return

        self.dig_stop()
        self.dig_start()

    def dig_stop(self):
        """
        A function to stop digitizer
        """
        path_to_main = os.path.abspath( os.getcwd() )
        path_file = os.path.join(path_to_main, '../atomize/control_center/digitizer_insys.param')
        #path_file = os.path.join(path_to_main, '../../atomize/control_center/digitizer_insys.param')

        #self.opened = 0

        file_to_read = open(path_file, 'w')
        file_to_read.write('Points: ' + str( self.p1_length ) +'\n')
        file_to_read.write('Sample Rate: ' + str( 2500 ) +'\n')
        file_to_read.write('Posstriger: ' + str( 1024 ) +'\n')
        file_to_read.write('Range: ' + str( 200 ) +'\n')
        file_to_read.write('CH0 Offset: ' + str( 0 ) +'\n')
        file_to_read.write('CH1 Offset: ' + str( 0 ) +'\n')
        
        if self.cur_win_right < self.cur_win_left:
            self.cur_win_left, self.cur_win_right = self.cur_win_right, self.cur_win_left
        if self.cur_win_right == self.cur_win_left:
            self.cur_win_right += 1 #self.time_per_point

        file_to_read.write('Window Left: ' + str( int(self.cur_win_left ) ) +'\n') #/ self.time_per_point
        file_to_read.write('Window Right: ' + str( int(self.cur_win_right ) ) +'\n') #/ self.time_per_point
        file_to_read.write('Decimation: ' + str( self.decimation ) +'\n')
        # phase corrections (worker units: rad, rad/s, rad/s^2) so acquisition
        # scripts can pick them up via digitizer_read_settings() without a preset
        file_to_read.write('Zero order: ' + str( getattr(self, 'zero_order', 0.0) ) +'\n')
        file_to_read.write('First order: ' + str( getattr(self, 'first_order', 0.0) ) +'\n')
        file_to_read.write('Second order: ' + str( getattr(self, 'second_order', 0.0) ) +'\n')

        file_to_read.close()

        if self.opened == 0:
            try:
                self.parent_conn_dig.send('exit')
                # Pulse mode (Run Pulses): tear down synchronously so update() /
                # start_exp() can restart immediately on the *next* line -- by the
                # time dig_start()/dig_start_exp() runs, the old worker is dead, so
                # its is_alive() guard passes and the intermediate button style is
                # overwritten in the same callback (no visible flash). The
                # digitizer stall-watchdog bounds this join, and the worker's
                # finally runs pulser_close(), so the GUI can't freeze and strand
                # the card. Experiment mode (long acquisitions) stays non-blocking
                # via monitor_timer.
                if self.is_experiment == False:
                    self.digitizer_process.join()
                    self.check_process_status()
                else:
                    self.monitor_timer.start(200)
            except AttributeError:
                if self.exit_clicked == 1:
                    sys.exit()

    def dig_start_exp(self):
        worker = Worker()
        self._hand_correction_to_worker(worker)

        self.p1_exp = [self.p1_typ, self.p1_start, self.p1_length,
                        self.ph_1, self.p1_st_increment, self.p1_len_increment, self.p1_freq
                        ]

        for i in range(2, 10):
            rect_start = getattr(self, f'p{i}_start_rect')
            pulse_len =  getattr(self, f'p{i}_length')
            delta_start =  getattr(self, f'p{i}_st_increment')
            length_increment =  getattr(self, f'p{i}_len_increment')
            #self.round_length(getattr(self, f'P{i}_len').value())
            setattr(self, f'p{i}_exp', [rect_start, pulse_len, delta_start, length_increment])

            awg_data = [
                getattr(self, f'p{i}_typ'),
                getattr(self, f'p{i}_freq'),
                getattr(self, f'wurst_sweep_cur_{i}'),
                getattr(self, f'p{i}_length'),
                getattr(self, f'p{i}_sigma'),
                getattr(self, f'p{i}_start'),
                getattr(self, f'p{i}_coef'),
                getattr(self, f'ph_{i}'),
                getattr(self, f'p{i}_st_increment'),
                getattr(self, f'p{i}_len_increment')
            ]
            setattr(self, f'p{i}_awg_exp', awg_data)

        # ESEEM tau-averaging: per-pulse second start increment ("X ns" strings),
        # one entry per pulse P1..P9. Consumed only by the "ESEEM Avg" sweep type.
        # Stored on self so the real run (run_experiment) can reuse it after the
        # preflight test pass.
        self.eseem_inc2 = [ getattr(self, f'p{i}_st_increment2') for i in range(1, 10) ]

        if self.laser_flag == 1:
            if self.combo_laser_num == 1:
                self.Rep_rate.setValue(9.9)
            elif self.combo_laser_num == 2:
                pass

        # prevent running two processes
        try:
            if ( self.digitizer_process.is_alive() == True ):
                return
        except AttributeError:
            pass

        self.parent_conn_dig, self.child_conn_dig = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        if self.cur_sweep == 'Linear Time':
            self.digitizer_process = Process( target = worker.exp, args = (
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp,
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field,
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp,
                self.p4_awg_exp,
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp,
                self.p9_awg_exp,
                self.b_sech_cur,
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.cur_x0, self.cur_xdelta, self.first_order, self.second_order,
                self.save2d, True ) )
        elif self.cur_sweep == 'Field':
            self.digitizer_process = Process( target = worker.exp_field, args = (
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_start_field,
                self.cur_end_field, self.cur_step,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp,
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0],
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp,
                self.p4_awg_exp,
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp,
                self.p9_awg_exp,
                self.b_sech_cur,
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.first_order, self.second_order, self.save2d, True ) )
        elif self.cur_sweep == 'Log Time':
            self.digitizer_process = Process( target = worker.exp_log, args = (
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_log_start, self.cur_log_end,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp,
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field,
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp,
                self.p4_awg_exp,
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp,
                self.p9_awg_exp,
                self.b_sech_cur,
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.cur_x0, self.cur_xdelta, self.first_order, self.second_order,
                self.save2d, True ) )
        elif self.cur_sweep == 'Amplitude':
            self.digitizer_process = Process( target = worker.exp_amplitude, args = (
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_ampl_step, self.mag_field,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp,
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0],
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp,
                self.p4_awg_exp,
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp,
                self.p9_awg_exp,
                self.b_sech_cur,
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.first_order, self.second_order, self.save2d, True ) )
        elif self.cur_sweep == 'ESEEM Avg':
            self.digitizer_process = Process( target = worker.exp_eseem, args = (
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp,
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field,
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp,
                self.p4_awg_exp,
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp,
                self.p9_awg_exp,
                self.b_sech_cur,
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.cur_x0, self.cur_xdelta, self.first_order, self.second_order,
                self.save2d, self.eseem_inc2, self.cur_cycles, self.save_each_cycle, True ) )

        self.button_start_exp.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(193, 202, 227); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')
        ###
        self.last_error = False
        ###
        self.is_testing = True
        self.is_experiment = True
        field_param.set_lock('awg_phasing_insys')
        temp_param.set_lock('awg_phasing_insys')
        self.timer.start(200)

    def dig_start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """
        worker = Worker()
        self._hand_correction_to_worker(worker)

        self.p1_list = [self.p1_typ, self.p1_start, self.p1_length, self.ph_1, self.p1_freq]

        for i in range(2, 10):
            rect_start = getattr(self, f'p{i}_start_rect')
            pulse_len =  getattr(self, f'p{i}_length')
            #self.round_length(getattr(self, f'P{i}_len').value())
            setattr(self, f'p{i}_list', [rect_start, pulse_len])

            awg_data = [
                getattr(self, f'p{i}_typ'),
                getattr(self, f'p{i}_freq'),
                getattr(self, f'wurst_sweep_cur_{i}'),
                getattr(self, f'p{i}_length'),
                getattr(self, f'p{i}_sigma'),
                getattr(self, f'p{i}_start'),
                getattr(self, f'p{i}_coef'),
                getattr(self, f'ph_{i}')
            ]
            setattr(self, f'p{i}_awg_list', awg_data)

        # Baseline the structure + start positions this preview opens with, so
        # later live edits can tell a re-armable change from one that needs a
        # restart (structural change, or a Start that overlaps/reorders).
        _snap0 = self._live_snapshot()
        self.live_sig = self._structure_sig(_snap0)
        self.live_starts = self._live_starts(_snap0)
        self.live_base = self._live_start_bases(_snap0)

        if self.laser_flag == 1:
            if self.combo_laser_num == 1:
                self.Rep_rate.setValue(9.9)
            elif self.combo_laser_num == 2:
                pass

        # prevent running two processes
        try:
            if self.digitizer_process.is_alive() == True:
                return
        except AttributeError:
            pass
        
        self.parent_conn_dig, self.child_conn_dig = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.digitizer_process = Process( target = worker.dig_on, args = ( self.child_conn_dig,
            self.decimation, self.l_mode, self.number_averages,  self.cur_win_left,
            self.cur_win_right, self.p1_list, self.p2_list, self.p3_list,
            self.p4_list, self.p5_list, self.p6_list, self.p7_list,
            self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field, self.fft,
            self.cur_phase, self.ch0_ampl, self.ch1_ampl, 0, self.p2_awg_list, self.p3_awg_list,
            self.p4_awg_list,
            self.p5_awg_list, self.p6_awg_list, self.p7_awg_list, self.quad, self.zero_order,
            self.first_order, self.second_order, self.p_to_drop, self.b_sech_cur,
            self.combo_cor, self.combo_synt, 0, self.p8_list, self.p9_list, self.p8_awg_list,
            self.p9_awg_list,
            self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay,
            self.iq_cor, True ) )

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(193, 202, 227); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
               
        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')
        ###
        self.last_error = False
        ###
        self.is_testing = True
        self.timer.start(200)

    def turn_off(self):
        """
        A function to turn off a programm.
        """
        self.exit_clicked = 1
        self.dig_stop()

    def message(self, *text):
        if len(text) == 1:
            print(f'{text[0]}', flush=True)
        else:
            print(f'{text}', flush=True)

    def button_blue(self):
        self.button_update.setStyleSheet("""
                QPushButton {
                    border-radius: 4px; 
                    background-color: rgb(63, 63, 97); 
                    border-style: outset; 
                    color: rgb(193, 202, 227); 
                    font-weight: bold; 
                }
                QPushButton:pressed {
                background-color: rgb(211, 194, 78); 
                border-style: inset; 
                font-weight: bold; 
                }
            """)
        self.button_start_exp.setStyleSheet("""
                QPushButton {
                    border-radius: 4px; 
                    background-color: rgb(63, 63, 97); 
                    border-style: outset; 
                    color: rgb(193, 202, 227); 
                    font-weight: bold; 
                }
                QPushButton:pressed {
                    background-color: rgb(211, 194, 78); 
                    border-style: inset; 
                    font-weight: bold; 
                }
            """)

    def parse_message(self):
        msg_type, data = self.parent_conn_dig.recv()
        
        if msg_type == 'Status':
            self.progress_bar.setValue(int(data))
        elif msg_type == 'Open':
            self.open_dialog()
        elif msg_type == 'Message':
            self.errors.appendPlainText(data)
        elif msg_type == 'Error':
            self.last_error = True
            self.timer.stop()
            self.is_experiment = False
            self.progress_bar.setValue(0)
            self.message(data)
            self.errors.appendPlainText(data)
            self.button_blue()
        elif msg_type == 'Average':
            self.Acq_number.setValue(int(data))
        elif msg_type == 'Count':
            self.update_count_nip(data)
        elif msg_type == 'PulseList':
            self.update_pulse_list_display(data)
        elif msg_type == 'LiveReject':
            # The worker's test-mode Insys rebuild found the live edit invalid
            # (e.g. an overlap the AMP_ON/LNA_PROTECT join cannot resolve). The
            # running preview was left on the previous sequence; surface why.
            self.errors.appendPlainText('Live Edit rejected — ' + str(data)
                + ' Preview left running; fix the value.')
        else:
            self.timer.stop()
            if ( data.startswith('Exp') ) and (msg_type == 'test'):
                pass
            else:
                self.errors.appendPlainText(data)
            if msg_type != 'test':
                self.message(data)
                self.button_blue()
                self.progress_bar.setValue(0)
                if self.monitor_timer.isActive():
                    pass
                else:
                    self.is_experiment = False

    def update_count_nip(self, text):
        """
        Show the live count_nip array in the errors log, refreshing only that
        line. If the last line is already a count_nip readout it is replaced in
        place; otherwise a new one is appended. Any other messages already in the
        log are left untouched.
        """
        marker = 'count_nip: '
        line = marker + text
        cursor = self.errors.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        if cursor.selectedText().startswith(marker):
            cursor.insertText(line)
        else:
            self.errors.appendPlainText(line)

    def update_pulse_list_display(self, text):
        """
        Show the current pulse lists in the log after a live edit, refreshing the
        block in place (from the marker line to the end) so repeated live edits
        do not stack copies. Any messages above the marker are left untouched.
        """
        marker = '--- Live AWG pulse list ---'
        block = marker + '\n' + text
        doc = self.errors.toPlainText()
        idx = doc.rfind(marker)
        cursor = self.errors.textCursor()
        if idx != -1:
            cursor.setPosition(idx)
            cursor.movePosition(QTextCursor.MoveOperation.End,
                                QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(block)
        else:
            self.errors.appendPlainText(block)

    def check_messages(self):
        if not hasattr(self, 'last_error'):
            self.last_error = False

        while self.parent_conn_dig.poll():
            try:
                self.parse_message()
            except EOFError:
                self.timer.stop()
                break
            except Exception as e:
                # never swallow silently: surface the failure in the TextEdit
                import traceback
                self.errors.appendPlainText('GUI message-pump error:\n' + traceback.format_exc())
                break

        if self.digitizer_process.is_alive() and not self.timer.isActive():
            self.digitizer_process.join()

        if hasattr(self, 'digitizer_process') and not self.digitizer_process.is_alive():
            if self.parent_conn_dig.poll():
                #return #better to repeat the whole logic
                self.parse_message()

            self.timer.stop()

            if getattr(self, 'is_testing', False):
                self.is_testing = False
                exit_code = getattr(self.digitizer_process, 'exitcode', None)
                # A clean preflight returns exitcode 0. If it died WITHOUT sending
                # an 'Error' (hard crash in a ctypes device call, a kill, a non-zero
                # sys.exit, a hang we just joined) last_error is still False but
                # exitcode != 0 -- surface that instead of silently starting the run.
                if (not self.last_error) and (exit_code in (0, None)):
                    self.last_error = False 
                    time.sleep(0.2)
                    if self.is_experiment == False:
                        self.run_main_experiment()
                    else:
                        self.run_experiment()
                else:
                    if not self.last_error:
                        self.errors.appendPlainText(
                            'Preflight process exited abnormally (exitcode ' + str(exit_code) +
                            ') without reporting an error; experiment not started.')
                        if hasattr(self, 'progress_bar'):
                            self.progress_bar.setValue(0)
                        if hasattr(self, 'button_blue'):
                            self.button_blue()
                        self.is_experiment = False
                    self.last_error = False
                    field_param.clear_lock()
                    temp_param.clear_lock()
            else:
                field_param.clear_lock()
                temp_param.clear_lock()

    def check_process_status(self):
        if self.digitizer_process.is_alive():
            return

        self.monitor_timer.stop()

        if self.is_experiment == True:
            self.digitizer_process.join()
            self.progress_bar.setValue(0)
            self.button_start_exp.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }  QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        else:
            self.errors.clear()
            self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }  QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")
        
        #self.timer.stop()
        self.is_experiment = False
        field_param.clear_lock()
        temp_param.clear_lock()

        if self.exit_clicked == 1:
            sys.exit()

    def open_dialog(self):
        file_data = self.file_handler.create_file_dialog(multiprocessing = True,
            directory = ldir.load('phase_awg', self.path))

        if file_data:
            if file_data != 'None':
                self.save_file(file_data.split(".csv")[0])
            self.parent_conn_dig.send( 'FL' + str( file_data ) )
        else:
            self.parent_conn_dig.send( 'FL' + '' )

    def run_main_experiment(self):

        worker = Worker()
        self._hand_correction_to_worker(worker)
        self.parent_conn_dig, self.child_conn_dig = Pipe()

        self.digitizer_process = Process( target = worker.dig_on, args = ( self.child_conn_dig, 
            self.decimation, self.l_mode, self.number_averages,  self.cur_win_left, 
            self.cur_win_right, self.p1_list, self.p2_list, self.p3_list, 
            self.p4_list, self.p5_list, self.p6_list, self.p7_list, 
            self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field, self.fft, 
            self.cur_phase, self.ch0_ampl, self.ch1_ampl, 0, self.p2_awg_list, self.p3_awg_list, 
            self.p4_awg_list, 
            self.p5_awg_list, self.p6_awg_list, self.p7_awg_list, self.quad, self.zero_order, 
            self.first_order, self.second_order, self.p_to_drop, self.b_sech_cur, 
            self.combo_cor, self.combo_synt, 0, self.p8_list, self.p9_list, self.p8_awg_list, 
            self.p9_awg_list, 
            self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay,
            self.iq_cor ) )

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }") 

        self.digitizer_process.start()
        self.parent_conn_dig.send('start')
        self.timer.start(200)

    def run_experiment(self):

        worker = Worker()
        self._hand_correction_to_worker(worker)
        self.parent_conn_dig, self.child_conn_dig = Pipe()
        
        if self.cur_sweep == 'Linear Time':
            self.digitizer_process = Process( target = worker.exp, args = ( 
                self.child_conn_dig, 
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp, 
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field, 
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp, 
                self.p4_awg_exp, 
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp, 
                self.p9_awg_exp,
                self.b_sech_cur, 
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.cur_x0, self.cur_xdelta, self.first_order, self.second_order,
                self.save2d ) )
        elif self.cur_sweep == 'Field':
            self.digitizer_process = Process( target = worker.exp_field, args = ( 
                self.child_conn_dig, 
                self.decimation, self.number_averages, self.cur_scan, self.cur_start_field,
                self.cur_end_field, self.cur_step,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp, 
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], 
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp, 
                self.p4_awg_exp, 
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp, 
                self.p9_awg_exp,
                self.b_sech_cur, 
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order, 
                self.first_order, self.second_order, self.save2d ) )
        elif self.cur_sweep == 'Log Time':
            self.digitizer_process = Process( target = worker.exp_log, args = ( 
                self.child_conn_dig, 
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_log_start, self.cur_log_end,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp, 
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field, 
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp, 
                self.p4_awg_exp, 
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp, 
                self.p9_awg_exp,
                self.b_sech_cur, 
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.cur_x0, self.cur_xdelta, self.first_order, self.second_order,
                self.save2d) )
        elif self.cur_sweep == 'Amplitude':
            self.digitizer_process = Process( target = worker.exp_amplitude, args = ( 
                self.child_conn_dig, 
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_ampl_step, self.mag_field,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp, 
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], 
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp, 
                self.p4_awg_exp, 
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp, 
                self.p9_awg_exp,
                self.b_sech_cur, 
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.first_order, self.second_order, self.save2d ) )
        elif self.cur_sweep == 'ESEEM Avg':
            self.digitizer_process = Process( target = worker.exp_eseem, args = (
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_exp_name, self.cur_curve_name,
                self.p1_exp, self.p2_exp, self.p3_exp,
                self.p4_exp, self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp,
                self.n_wurst_cur, self.repetition_rate.split(' ')[0], self.mag_field,
                self.ch0_ampl, self.ch1_ampl, self.p2_awg_exp, self.p3_awg_exp,
                self.p4_awg_exp,
                self.p5_awg_exp, self.p6_awg_exp, self.p7_awg_exp, self.p8_awg_exp,
                self.p9_awg_exp,
                self.b_sech_cur,
                self.combo_cor, self.combo_synt,
                self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay, self.cur_phase,
                self.iq_cor, self.cur_win_left, self.cur_win_right, self.zero_order,
                self.cur_x0, self.cur_xdelta, self.first_order, self.second_order,
                self.save2d, self.eseem_inc2, self.cur_cycles, self.save_each_cycle ) )

        self.button_start_exp.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        self.digitizer_process.start()
        self.parent_conn_dig.send('start')
        self.timer.start(200)

    def expand_phase_cycling(self, p_input, *pulse_args):
        phases = ['+x', '+y', '-x', '-y']
        norm = {'x':0, 'y':1, '-x':2, '-y':3, '+':0, '-':2, 'i':1, '-i':3, '0':0}

        def parse_to_indices(s):
            if not s: return [0]
            if isinstance(s, list):
                return [phases.index(p.strip()) if p.strip() in phases else norm.get(p.strip().lower().replace(' ', ''), 0) for p in s]
            
            s_clean = s.replace(' ', '')
            if ',' in s_clean:
                parts = [p for p in s_clean.split(',') if p]
                return [phases.index(p) if p in phases else norm.get(p.lower(), 0) for p in parts]
               
            def get_recursive(st):
                st = st.replace('D', '').lower().replace(' ', '')
                if not st: return [0]
                if '[' not in st and '(' not in st:
                    return [norm.get(st.strip(), 0)]
                is_quad = st.startswith('[')
                inner = get_recursive(st[1:-1])
                steps, shift = (4, 1) if is_quad else (2, 2)
                return [(p_idx + step * shift) % 4 for step in range(steps) for p_idx in inner]
            
            return get_recursive(s_clean)

        raw_sequences = [parse_to_indices(arg) for arg in pulse_args]
        
        target_len = 1
        for i, seq in enumerate(raw_sequences):
            arg = pulse_args[i]
            if isinstance(arg, str) and ('(' in arg or '[' in arg):
                if len(seq) > 1: target_len *= len(seq)
        
        if target_len == 1:
            for seq in raw_sequences:
                if len(seq) > 1:
                    target_len = abs(target_len * len(seq)) // math.gcd(target_len, len(seq))
        
        if target_len < 2: target_len = 2

        pulses_final = []
        current_repeat = 1
        for i, seq in enumerate(raw_sequences):
            arg = pulse_args[i]
            if isinstance(arg, str) and ('(' in arg or '[' in arg):
                expanded = [p for p in seq for _ in range(current_repeat)]
                final = (expanded * (target_len // len(expanded) + 1))[:target_len]
                current_repeat *= len(seq)
            else:
                final = (seq * (target_len // len(seq) + 1))[:target_len]
            pulses_final.append(final)


        if isinstance(p_input, (list, str)) and not any(ph in str(p_input).lower() for ph in ['x','y']):
            if isinstance(p_input, str):
                coeffs = [float(x) for x in re.findall(r'-?\d+\.?\d*', p_input)]
            else:
                coeffs = p_input
                
            receiver_indices = []
            for step in range(target_len):
                rec_sum = sum(coeffs[i] * pulses_final[i][step] 
                              for i in range(min(len(coeffs), len(pulses_final))))
                receiver_indices.append(int(round(rec_sum)) % 4)
        else:
            det_indices = parse_to_indices(p_input)
            receiver_indices = (det_indices * (target_len // len(det_indices) + 1))[:target_len]

        to_str = lambda indices: [phases[i] for i in indices]
        return {"pulses": [to_str(p) for p in pulses_final], "receiver": to_str(receiver_indices)}

# The worker class that run the digitizer in a different thread
class Worker():
    def __init__(self):
        super(Worker, self).__init__()
        # initialization of the attribute we use to stop the experimental script
        # when button Stop is pressed
        #from atomize.main.client import LivePlotClient

        self.command = 'start'

        # AWG resonator-correction settings; set by the MainWindow before the
        # process is launched (see _apply_awg_correction). Defaults keep the
        # worker usable even if they are not provided.
        self.cor_model_cur = 'measured'
        self.f0_cur = 9700.0
        self.q_cur = 88.0
        self.phase_cor_cur = 'False'
        # measured complex transfer for the 'measured' model (None => triple-
        # Lorentzian magnitude-only fit from correction.param)
        self.meas_freq_cur = None
        self.meas_H_cur = None

    def _apply_awg_correction(self, pb, mode):
        """Read correction.param and push resonator-correction settings to pb.

        mode 0 = off, 1 = only Pi/2 (high-amplitude pulses), 2 = all swept pulses.
        The measured triple-Lorentzian magnitude fit (+ LOW/LIMIT clamp) comes
        from correction.param; the model (measured / ideal RLC), f0, Q and the
        phase-correction flag are handed over from the AWG-tab controls. When a
        measured complex transfer H(f) has been loaded, its magnitude AND phase
        are passed to the 'measured' model (meas_freq / meas_H) instead of the
        magnitude-only Lorentzian fit.
        """
        if mode == 0:
            pb.awg_correction_off()
            return

        path_file = os.path.join( os.path.abspath( os.getcwd() ),
                                  '../atomize/control_center/correction.param' )
        with open(path_file, 'r') as file_to_read:
            text_from_file = file_to_read.read().split('\n')
        coef = [ float( text_from_file[i].split(' ')[1] ) for i in range(10) ]

        pb.awg_correction(only_pi_half = ('True' if mode == 1 else 'False'),
            coef_array = coef,
            low_level = float( text_from_file[10].split(' ')[1] ),
            limit = float( text_from_file[11].split(' ')[1] ),
            model = self.cor_model_cur, f0 = self.f0_cur, q_factor = self.q_cur,
            phase_correction = self.phase_cor_cur,
            meas_freq = self.meas_freq_cur, meas_H = self.meas_H_cur )

    def dig_on(self, conn, decimation, l_mode, n_averages, win_left, win_right, rect1, rect2, rect3, rect4, rect5, rect6, rect7, n_wurst, rep_rate, mag_field, fft_flag, cur_phase, ch0_ampl, ch1_ampl, trig_delay, awg2, awg3, awg4, awg5, awg6, awg7, quad, zero_order, first_order, second_order, p_to_drop, b_sech, combo_cor, combo_synt, _reserved, rect8, rect9, awg8, awg9, laser_flag, laser_num, laser_qsw_delay, iq_corr, script_test=False ):
        """
        function that contains updating of the digitizer.

        When script_test is True, run a single-shot phasing validation pass
        (enforce extra input checks, suppress 'Average'/'Message' callbacks,
        plot without I/Q text, emit the composed pulse list at the end).
        """
        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        #import time

        import traceback

        if script_test:
            sys.argv = ['', 'test']

        try:
            import time
            import numpy as np
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            # Route this scan's plot_1d / plot_2d through the non-blocking
            # coalescing worker so the acquisition loop isn't paced by the GUI.
            general.set_plotting_async(True)
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.math_modules.fft as fft_module
            import atomize.device_modules.BH_15 as itc

            pb = pb_pro.Insys_FPGA()
            fft = fft_module.Fast_Fourier()
            bh15 = itc.BH_15()
            #bh15.magnet_setup( mag_field, 0.5 )
            bh15.magnet_field( mag_field ) #, calibration = 'True' )

            process = 'None'
            num_ave = n_averages
            iq_cor = iq_corr

            ###
            pb.phase_shift_ch1_seq_mode_awg = cur_phase
            ###

            # correction from file (measured profile from correction.param;
            # model / f0 / Q / phase from the AWG-tab controls)
            self._apply_awg_correction(pb, combo_cor)

            pb.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl) )

            # Ordered record of the exact awg_pulse / pulser_pulse setup calls
            # (user-space kwargs). A live edit is validated by replaying these
            # into a throwaway test-mode Insys with shifted starts (see the 'PU'
            # handler), so the overlap check sees exactly what the real build did.
            pulser_setup_calls = []

            # DETECTION pulse
            iq_freq = -int( rect1[4].split(" MHz")[0] )
            if int(float(rect1[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=rect1[0], start=rect1[1], length=rect1[2], phase_list=rect1[3])
                pulser_setup_calls.append({'kind': 'pulser', 'kwargs': {
                    'name': 'P1', 'channel': rect1[0], 'start': rect1[1],
                    'length': rect1[2], 'phase_list': rect1[3]}})

            #Laser flag
            if laser_flag != 1:

                trigger_pulses = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [awg2, awg3, awg4, awg5, awg6, awg7, awg8, awg9]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if int(float(tp[1].split(' ')[0])) != 0:
                        
                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]
                        
                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7]
                        }
                        
                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech})
                            
                        pb.awg_pulse(**awg_kwargs)
                        pulser_setup_calls.append({'kind': 'awg', 'kwargs': dict(awg_kwargs)})

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1]
                            )
                            pulser_setup_calls.append({'kind': 'pulser', 'kwargs': {
                                'name': f'P{2*i + 3}', 'channel': 'TRIGGER_AWG',
                                'start': tp[0], 'length': tp[1]}})
                pb.pulser_repetition_rate( str(rep_rate) + ' Hz' )

            else:

                if script_test and int(float(rect2[1].split(' ')[0])) == 0:
                    raise ValueError("LASER pulse has zero length")
                #rect2 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER',
                    start=rect2[0],
                    length=rect2[1]
                )
                pulser_setup_calls.append({'kind': 'pulser', 'kwargs': {
                    'name': 'L1', 'channel': 'LASER',
                    'start': rect2[0], 'length': rect2[1]}})

                trigger_pulses = [rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [awg3, awg4, awg5, awg6, awg7, awg8, awg9]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):

                    if int(float(tp[1].split(' ')[0])) != 0:
                        # add q_delay
                        start_val = float(tp[0].split(' ')[0]) + laser_qsw_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + laser_qsw_delay
                        ap[5] = f"{self.round_to_closest(start_val_awg, 3.2)} ns"

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech})

                        pb.awg_pulse(**awg_kwargs)
                        pulser_setup_calls.append({'kind': 'awg', 'kwargs': dict(awg_kwargs)})

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1]
                            )
                            pulser_setup_calls.append({'kind': 'pulser', 'kwargs': {
                                'name': f'P{2*i + 3}', 'channel': 'TRIGGER_AWG',
                                'start': tp[0], 'length': tp[1]}})

                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                    #q_delay = laser_qsw_delay
                elif laser_num == 2:
                    pb.pulser_repetition_rate( str(rep_rate) + ' Hz' )
                    #q_delay = laser_qsw_delay
                else:
                    pb.pulser_repetition_rate( str(rep_rate) + ' Hz' )


            pb.pulser_default_synt(combo_synt)


            POINTS = 1
            pb.digitizer_decimation(decimation)
            # Live tuning runs in live_mode=1, which is always processed
            # synchronously; disable the background processing thread
            # explicitly so no worker resources are created in this process.
            pb.digitizer_processing_thread(0)
            DETECTION_WINDOW = round( pb.adc_window * 3.2, 1 )
            TR_ADC = round( 3.2 / 8, 1 )
            WIN_ADC = int( pb.adc_window * 8 / decimation )

            #31/03/2026
            if DETECTION_WINDOW <= 1200:
                ms_per_point = 1e-3
            else:
                ms_per_point = 1e-2

            data = np.zeros( ( 2, WIN_ADC, 1 ) )
            ##data = np.random.random( ( 2, WIN_ADC, 1 ) )
            x_axis = np.linspace(0, ( DETECTION_WINDOW - TR_ADC), num = WIN_ADC)

            t_res = 0.4 * decimation

            #31/03/2026
            rep_rate = float(rep_rate)
            if (n_averages / rep_rate ) < ms_per_point:
                n_averages = int( ms_per_point * rep_rate)
                #conn.send( ('Average', n_averages) )

            if not script_test:
                pb.digitizer_number_of_averages(n_averages)
            PHASES = len( rect1[3] )

            #pb.pulser_visualize()
            pb.pulser_open()

            # Pristine (post-setup) stored start of every pulse, keyed by name.
            # Live Edit ('PU') repositions a pulse as orig_start + GUI-space
            # delta: pulser_pulse bakes a channel-dependent shift into the stored
            # start (e.g. -trigger_awg_shift for TRIGGER_AWG, + the LASER
            # Q-switch delay), which neither a raw write nor pulser_redefine_start
            # reproduces. Because that transform is affine, adding the GUI delta
            # to the original stored value is correct for every channel without
            # having to know the shift -- and it never accumulates (always the
            # original + the total delta from the baseline the GUI recorded).
            _orig_pul_start = { p['name']: p['start'] for p in pb.pulse_array_pulser }
            _orig_awg_start = { p['name']: p['start'] for p in pb.pulse_array_awg }

            # Show the pulse lists in the log right after (re)programming, so they
            # are visible on every start and on every restart (a structural live
            # edit tears down and re-runs this setup). Live edits refresh the same
            # block in place from the 'PU' handler below.
            if not script_test:
                conn.send( ('PulseList', pb.awg_pulse_list()) )

            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the digitizer
            while self.command != 'exit':
                # always test our self.command attribute for stopping the script when neccessary

                if self.command[0:2] == 'PO':
                    #points_value = int( self.command[2:] )
                    #a2012.oscilloscope_stop()
                    #a2012.oscilloscope_timebase( str(points_value) + ' ns' )
                    #a2012.oscilloscope_run_stop()
                    pass

                elif self.command[0:2] == 'HO':
                    #posstrigger_value = int( self.command[2:] )
                    #a2012.oscilloscope_stop()
                    #a2012.oscilloscope_horizontal_offset( str(posstrigger_value) + ' ns' )
                    #a2012.oscilloscope_run_stop()
                    pass
                    
                elif self.command[0:2] == 'NA':
                    n_averages = int( self.command[2:] )

                    #31/03/2026
                    if (n_averages / rep_rate ) < ms_per_point:
                        n_averages = int( ms_per_point * rep_rate)
                        if not script_test:
                            conn.send( ('Average', n_averages) )

                    if not script_test:
                        pb.digitizer_number_of_averages( n_averages )

                elif self.command[0:2] == 'WL':
                    win_left = int( self.command[2:] )
                elif self.command[0:2] == 'WR':
                    win_right = int( self.command[2:] )
                elif self.command[0:2] == 'RR':
                    rep_rate = float( self.command[2:] )

                    #31/03/2026
                    if (n_averages / rep_rate ) < ms_per_point:
                        n_averages = int( ms_per_point * rep_rate)
                        pb.digitizer_number_of_averages( n_averages )
                        if not script_test:
                            conn.send( ('Average', n_averages) )

                    if rep_rate > 49:
                        pb.pulser_repetition_rate( str(rep_rate) + ' Hz' )
                    elif not script_test:
                        conn.send( ('Message', 'For REPETITION RATE lower then 50 Hz, please, press RUN PULSES') )

                elif self.command[0:2] == 'FI':
                    mag_field = float( self.command[2:] )
                    bh15.magnet_field( mag_field )#, calibration = 'True' )
                elif self.command[0:2] == 'FF':
                    fft_flag = int( self.command[2:] )
                elif self.command[0:2] == 'QC':
                    quad = int( self.command[2:] )
                elif self.command[0:2] == 'ZO':
                    zero_order = float( self.command[2:] )
                elif self.command[0:2] == 'FO':
                    first_order = float( self.command[2:] )
                elif self.command[0:2] == 'SO':
                    second_order = float( self.command[2:] )
                elif self.command[0:2] == 'PD':
                    p_to_drop = int( self.command[2:] )
                elif self.command[0:2] == 'LM':
                    #l_mode = int( self.command[2:] )
                    pass
                elif self.command[0:2] == 'PU':
                    # Live Edit: re-arm amplitude / frequency / start without a
                    # restart. Amplitude & frequency rebuild the DAC waveform;
                    # start only shifts the TRIGGER_AWG timing (the GUI has
                    # guaranteed the sequence stays non-overlapping and ordered,
                    # so dac_window is unchanged). Starts arrive as GUI-space
                    # deltas and are applied to the pristine post-setup value
                    # (orig_start + delta) so the channel shift / LASER offset is
                    # preserved and edits never accumulate. Both the live and the
                    # init arrays are written, because awg_pulse_reset() /
                    # pulser_pulse_reset() deep-copy the init arrays over the live
                    # ones after every phase cycle. The re-arm itself is applied
                    # by the awg_next_phase()/pulser_update() calls in the phase
                    # loop just below (same pattern as the amplitude sweep).
                    try:
                        snap = json.loads( self.command[2:] )
                    except (ValueError, TypeError):
                        snap = None

                    if snap is not None:
                        def _shift_start(orig_str, delta):
                            base = float( str(orig_str).split(' ')[0] )
                            return f"{self.round_to_closest(base + float(delta), 3.2)} ns"

                        # Validate the proposed geometry in a throwaway TEST-mode
                        # Insys before committing. The 'PU' payload only moves starts
                        # (amplitude/frequency/type/sigma are span-preserving), but a
                        # start move can still push the AMP_ON/LNA_PROTECT auto-defense
                        # windows into a genuine collision the geometric GUI check
                        # cannot see once those windows are joined. Replaying the exact
                        # setup calls (captured at build time) into a fresh test-mode
                        # card and running pulser_update() re-runs
                        # check_problem_pulses_phase_pulser(), whose overlap assert
                        # fires ONLY in test mode. pulser_open() is deliberately NOT
                        # used: in test mode it skips the check and would falsely assert
                        # "card already opened" against the live status file. A rejected
                        # edit is dropped -- the real pb is untouched, so the phase loop
                        # below simply keeps re-arming the previous sequence.
                        delta_by_name = {}
                        if 'p1_d' in snap:
                            delta_by_name['P1'] = snap['p1_d']
                        for entry in snap['pulses']:
                            k, amp, freq, a_delta, t_delta, typ, sigma = entry
                            if laser_flag == 1:
                                delta_by_name[f'P{2*(k-3)+2}'] = a_delta
                                delta_by_name[f'P{2*(k-3)+3}'] = t_delta
                            else:
                                delta_by_name[f'P{2*(k-2)+2}'] = a_delta
                                delta_by_name[f'P{2*(k-2)+3}'] = t_delta

                        reject = None
                        saved_argv = sys.argv
                        saved_tf = general.test_flag
                        try:
                            sys.argv = ['', 'test']
                            general.test_flag = 'test'
                            pbt = pb_pro.Insys_FPGA()
                            pbt.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl))
                            for c in pulser_setup_calls:
                                kw = dict(c['kwargs'])
                                kw['start'] = _shift_start(kw['start'],
                                                           delta_by_name.get(kw['name'], 0.0))
                                if c['kind'] == 'awg':
                                    pbt.awg_pulse(**kw)
                                else:
                                    pbt.pulser_pulse(**kw)
                            pbt.pulser_repetition_rate( str(rep_rate) + ' Hz' )
                            pbt.pulser_default_synt(combo_synt)
                            pbt.pulser_update()
                        except AssertionError as ae:
                            reject = str(ae) or 'pulses overlap after the edit'
                        except BaseException as be:
                            reject = str(be)
                        finally:
                            sys.argv = saved_argv
                            general.test_flag = saved_tf

                        if reject is not None:
                            if not script_test:
                                conn.send( ('LiveReject', reject) )
                        else:
                            # DETECTION frequency is not an AWG waveform or a
                            # pulse-geometry parameter -- it only sets the digitizer
                            # IQ demodulation frequency (iq_freq), applied per scan
                            # below. Re-arm it live with no card rebuild. Done inside
                            # the accepted branch so a rejected geometry edit leaves
                            # both the geometry AND the demod frequency untouched.
                            if snap.get('p1_freq') is not None:
                                try:
                                    iq_freq = -int( str(snap['p1_freq']).split(" MHz")[0] )
                                except (ValueError, TypeError):
                                    pass

                            awg_live = { p['name']: p for p in pb.pulse_array_awg }
                            awg_init = { p['name']: p for p in pb.pulse_array_init_awg }
                            pul_live = { p['name']: p for p in pb.pulse_array_pulser }
                            pul_init = { p['name']: p for p in pb.pulse_array_init_pulser }

                            # DETECTION start (P1, pulser side)
                            det = pul_live.get('P1')
                            if det is not None and 'P1' in _orig_pul_start:
                                new_det = _shift_start(_orig_pul_start['P1'], snap['p1_d'])
                                det['start'] = new_det
                                if 'P1' in pul_init:
                                    pul_init['P1']['start'] = new_det
                                pb.shift_count_pulser = 1

                            for entry in snap['pulses']:
                                k, amp, freq, a_delta, t_delta, typ, sigma = entry
                                # Name scheme mirrors dig_on setup: LASER mode packs
                                # AWG pulses from rect3.. (P1 detection, L1 laser),
                                # otherwise from rect2..; each active pulse is a
                                # waveform P{2i+2} plus its trigger P{2i+3}.
                                if laser_flag == 1:
                                    awg_name = f'P{2*(k-3)+2}'
                                    trg_name = f'P{2*(k-3)+3}'
                                else:
                                    awg_name = f'P{2*(k-2)+2}'
                                    trg_name = f'P{2*(k-2)+3}'

                                ap = awg_live.get(awg_name)
                                if ap is not None:
                                    # Type & sigma are span-preserving: set the
                                    # waveform function / sigma (and, for a swept
                                    # pulse, the chirp params n/b from the values this
                                    # run opened with) before the DAC is rebuilt.
                                    ap['function'] = typ
                                    ap['sigma'] = sigma
                                    if typ in ('WURST', 'SECH/TANH'):
                                        ap['n'] = n_wurst
                                        ap['b'] = b_sech
                                    pb.awg_redefine_amplitude(name=awg_name, amplitude=str(amp))
                                    pb.awg_redefine_frequency(name=awg_name, freq=freq)
                                    if awg_name in _orig_awg_start:
                                        ap['start'] = _shift_start(_orig_awg_start[awg_name], a_delta)
                                    ai = awg_init.get(awg_name)
                                    if ai is not None:
                                        ai['function'] = ap['function']
                                        ai['sigma'] = ap['sigma']
                                        ai['n'] = ap['n']
                                        ai['b'] = ap['b']
                                        ai['amp'] = ap['amp']
                                        ai['frequency'] = ap['frequency']
                                        ai['start'] = ap['start']
                                    pb.shift_count_awg = 1

                                tp = pul_live.get(trg_name)
                                if tp is not None and trg_name in _orig_pul_start:
                                    new_trg = _shift_start(_orig_pul_start[trg_name], t_delta)
                                    tp['start'] = new_trg
                                    if trg_name in pul_init:
                                        pul_init[trg_name]['start'] = new_trg
                                    pb.shift_count_pulser = 1

                            # Refresh the AWG pulse list shown in the log so it reflects
                            # the live-edited tables (init arrays). 'PulseList' is a
                            # side-effect-free message type the GUI refreshes in place;
                            # unlike 'test' it must not touch the message-pump timer
                            # while the preview is running.
                            if not script_test:
                                conn.send( ('PulseList', pb.awg_pulse_list()) )

                ###
                ###awg.phase_x = cur_phase

                # check integration window
                if win_left > WIN_ADC:
                    win_left = WIN_ADC
                if win_right > WIN_ADC:
                    win_right = WIN_ADC

                # phase cycle
                PHASES = len( rect1[3] )

                for i in range( PHASES ):

                    pb.awg_next_phase()
                    pb.pulser_update()
                    
                    if l_mode == 0:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 1)
                    elif l_mode == 1:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 0)
                    ##general.wait('100 ms')
                    ##data = np.random.random( ( 2, WIN_ADC, 1 ) )

                    data_x = data[0].ravel()
                    data_y = data[1].ravel()

                    if iq_cor == 1:
                        data_x, data_y = pb.digitizer_iq(data_x, data_y, iq_freq, zero_order, first_order, second_order)
                    else:
                        pass

                    if script_test:
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ),
                            xscale = 's', yscale = 'mV', label = 'ch',
                            vline = (win_left * t_res / 1e9, win_right * t_res / 1e9)
                            )
                    else:
                        int_x = round( np.sum( data_x[win_left:win_right] ) * 1 * t_res , 1 )
                        int_y = round( np.sum( data_y[win_left:win_right] ) * 1 * t_res , 1 )
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ),
                            xscale = 's', yscale = 'mV', label = 'ch',
                            vline = (win_left * t_res / 1e9, win_right * t_res / 1e9),
                            text = 'I/Q ' + str(int_x) + '/' + str(int_y)
                            )

                    if fft_flag == 1:

                        if quad == 0:
                            freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1)
                            m_val = round( np.amax( abs_values ), 2 )
                            general.plot_1d('FFT', freq_axis * 1e6, abs_values,
                                xname = 'Offset', label = 'FFT', xscale = 'Hz',
                                yscale = 'A.U.', text = 'Max ' + str(m_val)
                                )
                        else:
                            if p_to_drop > len( data_x ) - 0.4 * decimation:
                                p_to_drop = len( data_x ) - 0.8 * decimation
                                general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                            # fixed resolution of digitizer; 2 ns
                            freq, fft_x, fft_y = fft.fft( x_axis[p_to_drop:], data_x[p_to_drop:], data_y[p_to_drop:], t_res * 1, re = 'True' )
                            data_fft = fft.ph_correction( freq * 1e6, fft_x, fft_y, 0, 0, 0)
                            #, zero_order, first_order, second_order )
                            general.plot_1d('FFT', freq, ( data_fft[0], data_fft[1] ),
                                xname = 'Offset', xscale = 'Hz',
                                yscale = 'A.U.', label = 'FFT'
                                )

                if not script_test:
                    self.command = 'start'
                    # Live count_nip readout: send the per-nid packet-count array
                    # so the GUI can show acquisition progress dynamically. Sent
                    # as its own message type so the parent updates only this line
                    # and leaves the rest of the log intact. An all-zero array
                    # carries no information (often the case intentionally), so
                    # skip it rather than cluttering the log.
                    try:
                        if pb.count_nip is not None and np.any(pb.count_nip):
                            conn.send( ('Count', np.array2string(pb.count_nip, max_line_width = np.inf, threshold = np.inf)) )
                    except Exception:
                        pass
                if PHASES != 1:
                    pb.awg_pulse_reset()
                    pb.pulser_pulse_reset()
                else:
                    pass
                if script_test:
                    self.command = 'exit'

                # poll() checks whether there is data in the Pipe to read
                # we use it to stop the script if the exit command was sent from the main window
                # we read data by conn.recv() only when there is the data to read
                if conn.poll() == True:
                    self.command = conn.recv()

            if self.command == 'exit':
                ##print('exit')
                pb.pulser_close()
                if not script_test:
                    conn.send( ('', f'Pulses are stopped') )
                else:
                    # The composed pulse lists are now shown live via 'PulseList'
                    # after pulser_open in the real preview, so the preflight copy
                    # here is redundant. Keep only the TOO-MANY-PHASES warning.
                    if PHASES >= pb.number_adc_window_in_buffer():
                        str1 = '!!!TOO MANY PHASES FOR LIVE MODE!!!\n'
                        str2 = 'ADC WINDOWS IN BUFFER: '
                        conn.send( ('test', f'{str1}{str2}{pb.number_adc_window_in_buffer()}') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            # Always release the FPGA card, on every exit path (normal, Stop, or
            # exception). The card can only be freed by this process, so this is
            # the last line of defence against leaving it in an open state.
            try:
                pb.pulser_close()
            except Exception:
                pass

    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return round(( y * ( ( x // y ) + (round(x % y, 2) > 0) ) ), 1)

    def exp(self, conn, decimation, num_ave, scans, points,
            exp_name, curve_name, rect1, rect2,
            rect3, rect4, rect5, rect6, rect7, rect8, rect9,
            n_wurst, rep_rate, field, ch0_ampl,
            ch1_ampl, awg2, awg3, awg4,
            awg5, awg6, awg7, awg8, awg9,
            b_sech_cur, correction, synt, laser_flag, laser_num,
            q_switch_delay, iq_phase, iq_corr, win_left, win_right, zero_phase,
            x0, xd, first_order, sec_order, save2d, script_test=False):

        import traceback

        if script_test:
            sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            # Route this scan's plot_1d / plot_2d through the non-blocking
            # coalescing worker so the acquisition loop isn't paced by the GUI.
            general.set_plotting_async(True)
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.BH_15 as bh
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.general_modules.csv_opener_saver as openfile

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            iq_cor = iq_corr
            pb.win_left = win_left
            pb.win_right = win_right
            zp = zero_phase

            #rect1 DETECTION
            iq_freq = -int( rect1[6].split(" MHz")[0] )
            
            if xd == 0.0:

                pulses2 = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]

                if rect1[4] != '0.0 ns':
                    #delta_start
                    step = round( float( rect1[4].split(' ')[0] ), 1)
                    for p in pulses2:
                        if p[3] != '0.0 ns':
                            f_delay = self.round_to_closest( float(p[1].split(' ')[0]), 3.2)
                            break
                        else:
                            f_delay = self.round_to_closest( float(rect1[1].split(' ')[0]), 3.2)

                elif rect1[5] != '0.0 ns':
                    #length_increment
                    step = round( float( rect1[5].split(' ')[0] ), 1)
                    f_delay = self.round_to_closest( float(rect1[2].split(' ')[0]), 3.2)
                else:
                    for p in pulses2:
                        if p[2] != '0.0 ns':
                            step = round( float( p[2].split(' ')[0] ), 1)
                            f_delay = self.round_to_closest( float(p[0].split(' ')[0]), 3.2)
                            break
                        else:
                            #prevent no increment
                            step = 1
                            f_delay = 0
            else:
                step = round( xd, 1 )
                f_delay =  self.round_to_closest( x0, 3.2 )
            
            if step == 1 and not script_test:
                conn.send( ('Message', 'No START or LENGTH increment; the time axis corresponds to the number of points in the experiment') )
                general.plot_remove(exp_name)

            pb.phase_shift_ch1_seq_mode_awg = iq_phase

            # correction from file
            self._apply_awg_correction(pb, correction)
            
            pb.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl) )
            
            POINTS = points
            STEP = step
            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(rect1[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'

            if iq_cor == 1:
                EXP_NAME = exp_name
            elif iq_cor == 0:
                EXP_NAME = f'{exp_name}2D'

            # for awg pulse increments
            increment = 0

            bh15.magnet_field( field )
            general.wait('2000 ms')

            # DETECTION pulse
            if int(float(rect1[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=rect1[0], start=rect1[1], length=rect1[2], phase_list=rect1[3], delta_start=rect1[4], length_increment=rect1[5])

            #Laser flag
            if laser_flag != 1:

                trigger_pulses = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg2, awg3, awg4, awg5, 
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if ap[9] != '0.0 ns':
                        increment = 1

                    if int(float(tp[1].split(' ')[0])) != 0:
                        
                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]
                        
                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }
                        
                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1], 
                                delta_start=tp[2], 
                                length_increment=tp[3]
                            )
                pb.pulser_repetition_rate( REP_RATE )

            else:

                if script_test and int(float(rect2[1].split(' ')[0])) == 0:
                    raise ValueError("LASER pulse has zero length")
                #p7 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER',
                    start=rect2[0],
                    length=rect2[1],
                    delta_start=rect2[2],
                    length_increment=rect2[3]
                )

                trigger_pulses = [rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if ap[9] != '0.0 ns':
                        increment = 1

                    if int(float(tp[1].split(' ')[0])) != 0:
                        # add q_delay
                        start_val = float(tp[0].split(' ')[0]) + q_switch_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_switch_delay
                        ap[5] = f"{self.round_to_closest(start_val_awg, 3.2)} ns"

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=tp[2],
                                length_increment=tp[3]
                            )

                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                else:
                    pb.pulser_repetition_rate( REP_RATE )


            pb.pulser_default_synt(synt)

            pb.digitizer_decimation(DEC_COEF)
            points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)
            data = np.zeros( ( 2, points_window, POINTS ) )

            dec_calc = 0.4 * DEC_COEF / 1e9
            step_ns = STEP / 1e9

            x_axis = f_delay + np.linspace(0, (POINTS - 1)*STEP, num = POINTS)
            x_axis_plot = x_axis / 1e9
            a = 0
            # Partial-range readout state: rng = point range patched by the
            # most recent successful readout; data_x / data_y = persistent
            # per-point IQ-corrected integrals (patched per touched column).
            rng = None
            data_x = np.zeros( POINTS )
            data_y = np.zeros( POINTS )

            # general.scans() yields only 1 when test_flag == 'test'; production
            # mode uses a closure-based generator so the 'SC' command can
            # dynamically resize SCANS mid-run.
            def _scan_iter():
                if script_test:
                    yield from general.scans(SCANS)
                else:
                    k = 1
                    while k <= SCANS:
                        yield k
                        k += 1

            while self.command != 'exit':

                for k in _scan_iter():

                    sp = ls335.tc_setpoint()
                    ct = ls335.tc_temperature('B')

                    if not script_test:
                        temp_param.write_status(setpoint=sp, temp_b=ct)

                    if np.abs(sp - ct) > 0.8:
                        general.wait('8000 ms')

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        for i in range(PHASES):
                            # In test mode, only render the plot on j == 0 to keep the phasing
                            # loop fast — script_test inner iterations don't redraw.
                            if (not script_test) or j == 0:
                                if a is not None:
                                    if iq_cor == 0:
                                        # redraw only the columns patched by the last
                                        # readout (full frame on the very first draw)
                                        p0, p1 = rng if rng is not None else (0, POINTS)
                                        if step != 1:
                                            process = general.update_2d(
                                                EXP_NAME,
                                                data,
                                                p0, p1,
                                                start_step = ((0, dec_calc), (f_delay/1e9, step_ns)),
                                                xname = 'Time',
                                                xscale = 's',
                                                yname = 'Delay',
                                                yscale = 's',
                                                zname = 'Intensity',
                                                zscale = 'mV',
                                                text = f"Scan / Time: {k} / {j * STEP:.1f}",
                                                pr = process
                                            )
                                        else:
                                            process = general.update_2d(
                                                EXP_NAME,
                                                data,
                                                p0, p1,
                                                start_step = ((0, dec_calc), (0, 1)),
                                                xname = 'Time',
                                                xscale = 's',
                                                yname = 'Point',
                                                yscale = '',
                                                zname = 'Intensity',
                                                zscale = 'mV',
                                                text = f"Scan / Time: {k} / {j * STEP:.1f}",
                                                pr = process
                                            )
                                    elif iq_cor == 1:
                                        # data_x / data_y are patched per touched column
                                        # at the readout below -- no full-array recompute
                                        if step != 1:
                                            general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                                        else:
                                            general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))

                            pb.awg_next_phase()
                            pb.pulser_update()

                            if (not script_test) or j == 0:
                                # Partial-range readout: only the point columns
                                # recomputed from this call's buffers come back;
                                # patch them into the persistent arrays instead of
                                # copying the full O(points x window) frame.
                                a, b, rng = pb.digitizer_get_curve(
                                    POINTS,
                                    PHASES,
                                    current_scan = k,
                                    total_scan = SCANS,
                                    partial = True )
                                if a is not None:
                                    data[0][:, rng[0]:rng[1]] = a
                                    data[1][:, rng[0]:rng[1]] = b
                                    if iq_cor == 1:
                                        # IQ-corrected integrals for just the touched
                                        # columns: the digitizer_iq phase correction
                                        # depends only on the time axis, so per-column
                                        # patching is exact.
                                        dx, dy = pb.digitizer_iq(a, b, iq_freq, zp, first_order, sec_order, integral = True)
                                        data_x[rng[0]:rng[1]] = dx
                                        data_y[rng[0]:rng[1]] = dy

                        pb.pulser_shift()
                        if increment == 1:
                            pb.awg_increment()
                        else:
                            #pb.awg_pulse_reset()
                            pb.awg_shift()

                        pb.pulser_increment()

                        if not script_test:
                            conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit()
                            break

                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()
                    #if increment == 1:
                    pb.awg_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                # Final readout before releasing the card: digitizer_at_exit()
                # waits for the background processing thread to finish the
                # queued buffers and recomputes the exact accumulated state.
                # Covers natural completion of all scans; the Stop path inside
                # the loop already did the same (repeating it is harmless).
                data[0], data[1] = pb.digitizer_at_exit()
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if iq_cor == 0:
                    if step != 1:
                        general.plot_2d(
                            EXP_NAME, 
                            data, 
                            start_step = ((0, dec_calc), (f_delay/1e9, step_ns)), 
                            xname = 'Time', 
                            xscale = 's', 
                            yname = 'Delay', 
                            yscale = 's', 
                            zname = 'Intensity', 
                            zscale = 'mV', 
                            text = f"Scan / Time: {k} / {j * STEP:.1f}"
                        )
                    else:
                        general.plot_2d(
                            EXP_NAME, 
                            data, 
                            start_step = ((0, dec_calc), (0, 1)), 
                            xname = 'Time', 
                            xscale = 's', 
                            yname = 'Point', 
                            yscale = '', 
                            zname = 'Intensity', 
                            zscale = 'mV', 
                            text = f"Scan / Time: {k} / {j * STEP:.1f}"
                        )
                elif iq_cor == 1:
                    data_x, data_y = pb.digitizer_iq(data[0], data[1], iq_freq, zp, first_order, sec_order, integral = True)
                    if step != 1:
                        general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                    else:
                        general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))


                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR AWG Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {rect1[2]}\n"
                    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1f} ns\n"
                    f"{'Vertical Resolution:':<{w}} {STEP} ns\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                    f"{'-'*50}\n"
                    f"2D Data"
                )

                if iq_cor == 1:
                    header2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Pulsed EPR AWG Experiment\n"
                        f"{'Field:':<{w}} {FIELD} G\n"
                        f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                        f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Averages:':<{w}} {AVERAGES}\n"
                        f"{'Points:':<{w}} {POINTS}\n"
                        f"{'Window:':<{w}} {tb} ns\n"
                        f"{'Horizontal Resolution:':<{w}} {STEP} ns\n"
                        f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'-'*50}\n"
                        f"Pulse List:\n{pb.pulser_pulse_list()}"
                        f"{'-'*50}\n"
                        f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                        f"{'-'*50}\n"
                        f"Time (s), I (A.U.), Q (A.U.)"
                    )

                if script_test:
                    conn.send( ('test', f'') )
                else:
                    conn.send(('Open', ''))

                    while True:
                        if conn.poll():
                            msg = conn.recv()
                            if msg.startswith('FL'):
                                file_data = msg[2:]
                                break
                        general.wait('200 ms')

                    if iq_cor == 0:
                        file_handler.save_data(
                            file_data,
                            data,
                            header = header,
                            mode = 'w'
                        )
                    elif iq_cor == 1:

                        file_handler.save_data(
                            file_data,
                            np.c_[x_axis_plot, data_x, data_y],
                            header = header2,
                            mode = 'w'
                            )
                        if save2d == 1:
                            file_data2 = file_data.replace(".csv", "_2d.csv")

                            file_handler.save_data(
                                file_data2,
                                data,
                                header = header,
                                mode = 'w'
                        )

                    conn.send( ('', f'Experiment {EXP_NAME} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            # Always release the FPGA card, on every exit path (normal, Stop, or
            # exception). The card can only be freed by this process, so this is
            # the last line of defence against leaving it in an open state.
            try:
                pb.pulser_close()
            except Exception:
                pass

    def exp_eseem(self, conn, decimation, num_ave, scans, points,
            exp_name, curve_name, rect1, rect2,
            rect3, rect4, rect5, rect6, rect7, rect8, rect9,
            n_wurst, rep_rate, field, ch0_ampl,
            ch1_ampl, awg2, awg3, awg4,
            awg5, awg6, awg7, awg8, awg9,
            b_sech_cur, correction, synt, laser_flag, laser_num,
            q_switch_delay, iq_phase, iq_corr, win_left, win_right, zero_phase,
            x0, xd, first_order, sec_order, save2d,
            eseem_inc2, cycles, save_each, script_test=False):
        """
        ESEEM tau-averaging variant of exp().

        Runs the standard linear-time scan `cycles` times. Before each cycle's
        scan, the pulses whose per-pulse "Start Increment 2" (eseem_inc2, one
        "X ns" string per GUI pulse P1..P9) is non-zero are shifted cumulatively
        by that increment (cycle 0 = base, cycle c = base + c·Inc2). The normal
        "Start Increment 1" sweep then runs on top of the shifted base. Because
        pulser_pulse_reset() returns to the absolute base after every scan, the
        cycle offset is re-applied at the start of each scan.

        The digitizer averages on-board across every call for the whole run and
        never resets between cycles, so digitizer_get_curve always returns the
        cumulative average over all shots acquired so far. Because each cycle
        re-traces the same point/phase sequence with the pulses shifted by an
        extra tau, that running on-board average IS the tau-averaged result that
        suppresses nuclear ESEEM modulation — no software re-averaging is done.
        `data` therefore holds the current cumulative average throughout and is
        what we plot live and save at the end. With save_each set, each cycle's
        own trace is recovered by differencing the cumulative snapshots taken at
        the cycle boundaries (M_c = mean over cycles 0..c, so the individual
        cycle_c = (c+1)*M_c - c*M_{c-1}) and written to its own file.

        NOTE: the tau shift is applied on the pulser side only
        (pulser_redefine_delta_start + named pulser_shift). The AWG pulses follow
        their TRIGGER_AWG pulser pulses in time, exactly as in the normal scan.
        The exact behaviour for TRIGGER_AWG pulse pairs should be verified on
        hardware (see pulser_redefine_delta_start in Insys_FPGA.py).
        """

        import traceback

        if script_test:
            sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            # Route this scan's plot_1d / plot_2d through the non-blocking
            # coalescing worker so the acquisition loop isn't paced by the GUI.
            general.set_plotting_async(True)
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.BH_15 as bh
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.general_modules.csv_opener_saver as openfile

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            iq_cor = iq_corr
            pb.win_left = win_left
            pb.win_right = win_right
            zp = zero_phase

            #rect1 DETECTION
            iq_freq = -int( rect1[6].split(" MHz")[0] )

            if xd == 0.0:

                pulses2 = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]

                if rect1[4] != '0.0 ns':
                    #delta_start
                    step = round( float( rect1[4].split(' ')[0] ), 1)
                    for p in pulses2:
                        if p[3] != '0.0 ns':
                            f_delay = self.round_to_closest( float(p[1].split(' ')[0]), 3.2)
                            break
                        else:
                            f_delay = self.round_to_closest( float(rect1[1].split(' ')[0]), 3.2)

                elif rect1[5] != '0.0 ns':
                    #length_increment
                    step = round( float( rect1[5].split(' ')[0] ), 1)
                    f_delay = self.round_to_closest( float(rect1[2].split(' ')[0]), 3.2)
                else:
                    for p in pulses2:
                        if p[2] != '0.0 ns':
                            step = round( float( p[2].split(' ')[0] ), 1)
                            f_delay = self.round_to_closest( float(p[0].split(' ')[0]), 3.2)
                            break
                        else:
                            #prevent no increment
                            step = 1
                            f_delay = 0
            else:
                step = round( xd, 1 )
                f_delay =  self.round_to_closest( x0, 3.2 )

            if step == 1 and not script_test:
                conn.send( ('Message', 'No START or LENGTH increment; the time axis corresponds to the number of points in the experiment') )
                general.plot_remove(exp_name)

            pb.phase_shift_ch1_seq_mode_awg = iq_phase

            # correction from file
            self._apply_awg_correction(pb, correction)

            pb.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl) )

            POINTS = points
            STEP = step
            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(rect1[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            CYCLES = int(cycles)

            if iq_cor == 1:
                EXP_NAME = exp_name
            elif iq_cor == 0:
                EXP_NAME = f'{exp_name}2D'

            # for awg pulse increments
            increment = 0

            bh15.magnet_field( field )
            general.wait('2000 ms')

            # ESEEM tau-shift bookkeeping. For every pulser pulse we record its
            # logical name, its normal Inc1 delta_start (to restore) and its
            # Start Increment 2. During a cycle's offset the non-ESEEM pulses are
            # temporarily zeroed so a single (unnamed) pulser_shift moves only the
            # ESEEM pulses; the paired AWG entries follow their trigger pulse
            # automatically (a TRIGGER_AWG pulse and its 'P#AWG' partner share a
            # name and delta_start — see pulser_redefine_delta_start / pulser_shift
            # in Insys_FPGA.py).
            eseem_all_names = []
            eseem_all_inc1 = []
            eseem_all_inc2 = []

            def _eseem_add(pname, gui_idx, inc1_str):
                eseem_all_names.append(pname)
                eseem_all_inc1.append(inc1_str)
                eseem_all_inc2.append(eseem_inc2[gui_idx])

            # DETECTION pulse
            if int(float(rect1[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=rect1[0], start=rect1[1], length=rect1[2], phase_list=rect1[3], delta_start=rect1[4], length_increment=rect1[5])
                _eseem_add('P1', 0, rect1[4])

            #Laser flag
            if laser_flag != 1:

                trigger_pulses = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg2, awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if ap[9] != '0.0 ns':
                        increment = 1

                    if int(float(tp[1].split(' ')[0])) != 0:

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=tp[2],
                                length_increment=tp[3]
                            )
                            _eseem_add(f'P{2*i + 3}', i + 1, tp[2])
                pb.pulser_repetition_rate( REP_RATE )

            else:

                if script_test and int(float(rect2[1].split(' ')[0])) == 0:
                    raise ValueError("LASER pulse has zero length")
                #p7 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER',
                    start=rect2[0],
                    length=rect2[1],
                    delta_start=rect2[2],
                    length_increment=rect2[3]
                )
                _eseem_add('L1', 1, rect2[2])

                trigger_pulses = [rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if ap[9] != '0.0 ns':
                        increment = 1

                    if int(float(tp[1].split(' ')[0])) != 0:
                        # add q_delay
                        start_val = float(tp[0].split(' ')[0]) + q_switch_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_switch_delay
                        ap[5] = f"{self.round_to_closest(start_val_awg, 3.2)} ns"

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=tp[2],
                                length_increment=tp[3]
                            )
                            _eseem_add(f'P{2*i + 3}', i + 2, tp[2])

                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                else:
                    pb.pulser_repetition_rate( REP_RATE )


            pb.pulser_default_synt(synt)

            pb.digitizer_decimation(DEC_COEF)
            points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)

            dec_calc = 0.4 * DEC_COEF / 1e9
            step_ns = STEP / 1e9

            x_axis = f_delay + np.linspace(0, (POINTS - 1)*STEP, num = POINTS)
            x_axis_plot = x_axis / 1e9
            a = 0
            # Partial-range readout state: rng = point range patched by the
            # most recent successful readout; data_x / data_y = persistent
            # per-point IQ-corrected integrals (patched per touched column).
            rng = None
            data_x = np.zeros( POINTS )
            data_y = np.zeros( POINTS )

            # Whether any pulse actually carries a non-zero Start Increment 2.
            has_eseem = any( float( v.split(' ')[0] ) != 0 for v in eseem_all_inc2 )

            # `data` holds the digitizer's cumulative average and is filled in
            # place by every digitizer_get_curve call; it is the live-plotted and
            # final tau-averaged result (NO software re-averaging — re-summing the
            # already-cumulative arrays was the original bug). For the optional
            # per-cycle export we snapshot the cumulative average after each
            # completed cycle and difference the snapshots to recover individual
            # cycles. Allocated once so the live plot shows the running average
            # continuously rather than blanking to zeros at each cycle start.
            data = np.zeros( ( 2, points_window, POINTS ) )
            cycle_snapshots = []
            completed_cycles = 0
            k = 1
            j = 0

            def _scan_iter():
                if script_test:
                    yield from general.scans(SCANS)
                else:
                    kk = 1
                    while kk <= SCANS:
                        yield kk
                        kk += 1

            # In test mode every cycle exercises the same code path, so a single
            # cycle is enough for the preflight check (avoids redundant work).
            cycle_count = 1 if script_test else CYCLES

            for cycle in range(cycle_count):

                if self.command == 'exit':
                    break

                for k in _scan_iter():

                    sp = ls335.tc_setpoint()
                    ct = ls335.tc_temperature('B')

                    if not script_test:
                        temp_param.write_status(setpoint=sp, temp_b=ct)

                    if np.abs(sp - ct) > 0.8:
                        general.wait('8000 ms')

                    if self.command == 'exit':
                        break

                    # Re-apply the cumulative ESEEM offset on the freshly reset
                    # base: zero every pulse's delta_start except the ESEEM ones
                    # (set to Inc2), shift `cycle` times so only they move, then
                    # restore all Inc1 values so the point loop sweeps normally.
                    if cycle > 0 and has_eseem:
                        pb.pulser_redefine_delta_start(name = eseem_all_names, delta_start = eseem_all_inc2)
                        for _ in range(cycle):
                            pb.pulser_shift()
                        pb.pulser_redefine_delta_start(name = eseem_all_names, delta_start = eseem_all_inc1)

                    for j in range(POINTS):
                        for i in range(PHASES):
                            if (not script_test) or j == 0:
                                if a is not None:
                                    if iq_cor == 0:
                                        # redraw only the columns patched by the last
                                        # readout (full frame on the very first draw)
                                        p0, p1 = rng if rng is not None else (0, POINTS)
                                        if step != 1:
                                            process = general.update_2d(
                                                EXP_NAME,
                                                data,
                                                p0, p1,
                                                start_step = ((0, dec_calc), (f_delay/1e9, step_ns)),
                                                xname = 'Time',
                                                xscale = 's',
                                                yname = 'Delay',
                                                yscale = 's',
                                                zname = 'Intensity',
                                                zscale = 'mV',
                                                text = f"Cycle / Scan: {cycle + 1}/{CYCLES} / {k}",
                                                pr = process
                                            )
                                        else:
                                            process = general.update_2d(
                                                EXP_NAME,
                                                data,
                                                p0, p1,
                                                start_step = ((0, dec_calc), (0, 1)),
                                                xname = 'Time',
                                                xscale = 's',
                                                yname = 'Point',
                                                yscale = '',
                                                zname = 'Intensity',
                                                zscale = 'mV',
                                                text = f"Cycle / Scan: {cycle + 1}/{CYCLES} / {k}",
                                                pr = process
                                            )
                                    elif iq_cor == 1:
                                        # data_x / data_y are patched per touched column
                                        # at the readout below -- no full-array recompute
                                        if step != 1:
                                            general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = f'Cycle {cycle + 1}/{CYCLES} Scan {k}')
                                        else:
                                            general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = f'Cycle {cycle + 1}/{CYCLES} Scan {k}')

                            pb.awg_next_phase()
                            pb.pulser_update()

                            if (not script_test) or j == 0:
                                # Partial-range readout: only the point columns
                                # recomputed from this call's buffers come back;
                                # patch them into the persistent arrays instead of
                                # copying the full O(points x window) frame.
                                a, b, rng = pb.digitizer_get_curve(
                                    POINTS,
                                    PHASES,
                                    current_scan = k,
                                    total_scan = SCANS,
                                    partial = True )
                                if a is not None:
                                    data[0][:, rng[0]:rng[1]] = a
                                    data[1][:, rng[0]:rng[1]] = b
                                    if iq_cor == 1:
                                        # IQ-corrected integrals for just the touched
                                        # columns: the digitizer_iq phase correction
                                        # depends only on the time axis, so per-column
                                        # patching is exact.
                                        dx, dy = pb.digitizer_iq(a, b, iq_freq, zp, first_order, sec_order, integral = True)
                                        data_x[rng[0]:rng[1]] = dx
                                        data_y[rng[0]:rng[1]] = dy

                        pb.pulser_shift()
                        if increment == 1:
                            pb.awg_increment()
                        else:
                            pb.awg_shift()

                        pb.pulser_increment()

                        if not script_test:
                            denom = max( CYCLES * POINTS * SCANS, 1 )
                            conn.send( ('Status', int( 100 * ( cycle * POINTS * SCANS + ( k - 1 ) * POINTS + j + 1 ) / denom )) )

                        # check our polling data. Changing the scan count
                        # mid-run is disabled for ESEEM averaging: it would give
                        # cycles unequal shot counts, breaking both the on-board
                        # cumulative average and the per-cycle snapshot
                        # differencing. An 'SC' request is acknowledged but
                        # ignored (SCANS held fixed).
                        if self.command[0:2] == 'SC':
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit()
                            break

                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()
                    pb.awg_pulse_reset()

                # Interrupted mid-cycle: `data` still holds a valid cumulative
                # average (including the partial cycle), but it is not a complete
                # cycle boundary, so don't record it as a snapshot.
                if self.command == 'exit':
                    break

                # `data` is the digitizer's cumulative average through this cycle
                # (the last scan triggered an on-board drain, so the snapshot is
                # complete). Store it for the per-cycle differencing export.
                cycle_snapshots.append( np.copy(data) )
                completed_cycles += 1

                # Refresh the live plot with the cumulative tau-averaged trace.
                if a is not None and not script_test:
                    if iq_cor == 0:
                        if step != 1:
                            general.plot_2d(EXP_NAME, data, start_step = ((0, dec_calc), (f_delay/1e9, step_ns)), xname = 'Time', xscale = 's', yname = 'Delay', yscale = 's', zname = 'Intensity', zscale = 'mV', text = f"ESEEM average over {completed_cycles} cycle(s)")
                        else:
                            general.plot_2d(EXP_NAME, data, start_step = ((0, dec_calc), (0, 1)), xname = 'Time', xscale = 's', yname = 'Point', yscale = '', zname = 'Intensity', zscale = 'mV', text = f"ESEEM average over {completed_cycles} cycle(s)")
                    elif iq_cor == 1:
                        rdx, rdy = pb.digitizer_iq(data[0], data[1], iq_freq, zp, first_order, sec_order, integral = True)
                        if step != 1:
                            general.plot_1d(EXP_NAME, x_axis_plot, ( rdx, rdy ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = f"ESEEM average over {completed_cycles} cycle(s)")
                        else:
                            general.plot_1d(EXP_NAME, x_axis, ( rdx, rdy ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = f"ESEEM average over {completed_cycles} cycle(s)")

            self.command = 'exit'

            # `data` already holds the cumulative (tau-averaged) result returned
            # by the digitizer over every cycle/scan/shot — it is the final
            # answer as-is (this is the bug fix: no software division/re-average).

            if self.command == 'exit':
                # Final readout before releasing the card: digitizer_at_exit()
                # waits for the background processing thread to finish the
                # queued buffers and recomputes the exact accumulated state.
                # Covers natural completion of all scans; the Stop path inside
                # the loop already did the same (repeating it is harmless).
                data[0], data[1] = pb.digitizer_at_exit()
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if iq_cor == 0:
                    if step != 1:
                        general.plot_2d(
                            EXP_NAME,
                            data,
                            start_step = ((0, dec_calc), (f_delay/1e9, step_ns)),
                            xname = 'Time',
                            xscale = 's',
                            yname = 'Delay',
                            yscale = 's',
                            zname = 'Intensity',
                            zscale = 'mV',
                            text = f"ESEEM average over {completed_cycles} cycle(s)"
                        )
                    else:
                        general.plot_2d(
                            EXP_NAME,
                            data,
                            start_step = ((0, dec_calc), (0, 1)),
                            xname = 'Time',
                            xscale = 's',
                            yname = 'Point',
                            yscale = '',
                            zname = 'Intensity',
                            zscale = 'mV',
                            text = f"ESEEM average over {completed_cycles} cycle(s)"
                        )
                elif iq_cor == 1:
                    data_x, data_y = pb.digitizer_iq(data[0], data[1], iq_freq, zp, first_order, sec_order, integral = True)
                    if step != 1:
                        general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = f"ESEEM average over {completed_cycles} cycle(s)")
                    else:
                        general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = f"ESEEM average over {completed_cycles} cycle(s)")


                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # non-zero Start Increment 2 values, for the file header
                inc2_summary = ', '.join(
                    f"P{idx + 1}={val}" for idx, val in enumerate(eseem_inc2)
                    if float(val.split(' ')[0]) != 0
                ) or 'none'

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR AWG ESEEM-Averaged Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'ESEEM Cycles:':<{w}} {completed_cycles}\n"
                    f"{'Start Increment 2:':<{w}} {inc2_summary}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {rect1[2]}\n"
                    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1f} ns\n"
                    f"{'Vertical Resolution:':<{w}} {STEP} ns\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                    f"{'-'*50}\n"
                    f"2D Data"
                )

                if iq_cor == 1:
                    header2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Pulsed EPR AWG ESEEM-Averaged Experiment\n"
                        f"{'Field:':<{w}} {FIELD} G\n"
                        f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                        f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'ESEEM Cycles:':<{w}} {completed_cycles}\n"
                        f"{'Start Increment 2:':<{w}} {inc2_summary}\n"
                        f"{'Averages:':<{w}} {AVERAGES}\n"
                        f"{'Points:':<{w}} {POINTS}\n"
                        f"{'Window:':<{w}} {tb} ns\n"
                        f"{'Horizontal Resolution:':<{w}} {STEP} ns\n"
                        f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'-'*50}\n"
                        f"Pulse List:\n{pb.pulser_pulse_list()}"
                        f"{'-'*50}\n"
                        f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                        f"{'-'*50}\n"
                        f"Time (s), I (A.U.), Q (A.U.)"
                    )

                if script_test:
                    conn.send( ('test', f'') )
                else:
                    conn.send(('Open', ''))

                    while True:
                        if conn.poll():
                            msg = conn.recv()
                            if msg.startswith('FL'):
                                file_data = msg[2:]
                                break
                        general.wait('200 ms')

                    if iq_cor == 0:
                        file_handler.save_data(
                            file_data,
                            data,
                            header = header,
                            mode = 'w'
                        )
                    elif iq_cor == 1:

                        file_handler.save_data(
                            file_data,
                            np.c_[x_axis_plot, data_x, data_y],
                            header = header2,
                            mode = 'w'
                            )
                        if save2d == 1:
                            file_data2 = file_data.replace(".csv", "_2d.csv")

                            file_handler.save_data(
                                file_data2,
                                data,
                                header = header,
                                mode = 'w'
                        )

                    # Optionally save every cycle's own trace alongside the
                    # average. The digitizer only ever hands back the cumulative
                    # mean, so each individual cycle is recovered by differencing
                    # consecutive cumulative snapshots: with M_c = mean over
                    # cycles 0..c (cycle_snapshots[c]), the isolated trace is
                    # cycle_c = (c+1)*M_c - c*M_{c-1} (cycle 0 = M_0). Exact while
                    # every cycle carries the same shot count, which holds for all
                    # fully completed cycles.
                    if save_each:
                        for idx in range(len(cycle_snapshots)):
                            Mc = cycle_snapshots[idx]
                            if idx == 0:
                                cdat = Mc
                            else:
                                cdat = (idx + 1) * Mc - idx * cycle_snapshots[idx - 1]
                            cpath = file_data.replace(".csv", f"_cycle{idx}.csv")
                            if iq_cor == 0:
                                file_handler.save_data(cpath, cdat, header = header, mode = 'w')
                            elif iq_cor == 1:
                                cdx, cdy = pb.digitizer_iq(cdat[0], cdat[1], iq_freq, zp, first_order, sec_order, integral = True)
                                file_handler.save_data(cpath, np.c_[x_axis_plot, cdx, cdy], header = header2, mode = 'w')

                    conn.send( ('', f'Experiment {EXP_NAME} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            # Always release the FPGA card, on every exit path (normal, Stop, or
            # exception). The card can only be freed by this process, so this is
            # the last line of defence against leaving it in an open state.
            try:
                pb.pulser_close()
            except Exception:
                pass

    def exp_field(self, conn, decimation, num_ave, scans, start_field,
            end_field, step_field, exp_name,
            curve_name, rect1, rect2,
            rect3, rect4, rect5, rect6, rect7, rect8, rect9,
            n_wurst, rep_rate, ch0_ampl,
            ch1_ampl, awg2, awg3, awg4,
            awg5, awg6, awg7, awg8, awg9,
            b_sech_cur, correction, synt, laser_flag, laser_num,
            q_switch_delay, iq_phase, iq_corr, win_left, win_right, zero_phase,
            first_order, sec_order, save2d, script_test=False):

        import traceback

        if script_test:
            sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            # Route this scan's plot_1d / plot_2d through the non-blocking
            # coalescing worker so the acquisition loop isn't paced by the GUI.
            general.set_plotting_async(True)
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.BH_15 as bh
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.general_modules.csv_opener_saver as openfile

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            iq_cor = iq_corr
            pb.win_left = win_left
            pb.win_right = win_right
            zp = zero_phase

            pb.phase_shift_ch1_seq_mode_awg = iq_phase

            # correction from file
            self._apply_awg_correction(pb, correction)
            
            pb.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl) )
            
            START_FIELD = start_field
            END_FIELD = end_field
            FIELD_STEP = step_field

            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(rect1[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'

            if iq_cor == 1:
                EXP_NAME = f'{exp_name}_F'
            elif iq_cor == 0:
                EXP_NAME = f'{exp_name}_F_2D'

            bh15.magnet_field( start_field )
            general.wait('2000 ms')

            # DETECTION pulse
            iq_freq = -int( rect1[6].split(" MHz")[0] )
            if int(float(rect1[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=rect1[0], start=rect1[1], length=rect1[2], phase_list=rect1[3], delta_start=rect1[4], length_increment=rect1[5])

            #Laser flag
            if laser_flag != 1:

                trigger_pulses = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg2, awg3, awg4, awg5, 
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if int(float(tp[1].split(' ')[0])) != 0:
                        if script_test and tp[2] != '0.0 ns':
                            raise ValueError("Please remove Start Increments for all pulses")

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=tp[2],
                                length_increment=tp[3]
                            )
                pb.pulser_repetition_rate( REP_RATE )

            else:

                if script_test and int(float(rect2[1].split(' ')[0])) == 0:
                    raise ValueError("LASER pulse has zero length")
                #p7 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER',
                    start=rect2[0],
                    length=rect2[1],
                    delta_start=rect2[2],
                    length_increment=rect2[3]
                )

                trigger_pulses = [rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):

                    if int(float(tp[1].split(' ')[0])) != 0:
                        if script_test and tp[2] != '0.0 ns':
                            raise ValueError("Please remove Start Increments for all pulses")

                        start_val = float(tp[0].split(' ')[0]) + q_switch_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_switch_delay
                        ap[5] = f"{self.round_to_closest(start_val_awg, 3.2)} ns"

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=tp[2],
                                length_increment=tp[3]
                            )

                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                else:
                    pb.pulser_repetition_rate( REP_RATE )


            pb.pulser_default_synt(synt)

            pb.digitizer_decimation(DEC_COEF)
            points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)

            POINTS = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
            data = np.zeros( ( 2, points_window, POINTS ) )
            dec_calc = 0.4 * DEC_COEF / 1e9

            x_axis = np.linspace(START_FIELD, END_FIELD, num = POINTS)
            a = 0
            # Partial-range readout state: rng = point range patched by the
            # most recent successful readout; data_x / data_y = persistent
            # per-point IQ-corrected integrals (patched per touched column).
            rng = None
            data_x = np.zeros( POINTS )
            data_y = np.zeros( POINTS )

            def _scan_iter():
                if script_test:
                    yield from general.scans(SCANS)
                else:
                    k = 1
                    while k <= SCANS:
                        yield k
                        k += 1

            while self.command != 'exit':

                for k in _scan_iter():

                    field = START_FIELD
                    bh15.magnet_field(field)

                    sp = ls335.tc_setpoint()
                    ct = ls335.tc_temperature('B')

                    if not script_test:
                        temp_param.write_status(setpoint=sp, temp_b=ct)

                    if np.abs(sp - ct) > 0.8:
                        general.wait('8000 ms')

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):

                        bh15.magnet_field(field)#, calibration = 'True')

                        for i in range(PHASES):
                            # In test mode, only render on j == 0 (phasing speed-up).
                            if (not script_test) or j == 0:
                                if a is not None:
                                    if iq_cor == 0:
                                        # redraw only the columns patched by the last
                                        # readout (full frame on the very first draw)
                                        p0, p1 = rng if rng is not None else (0, POINTS)
                                        process = general.update_2d(
                                            EXP_NAME,
                                            data,
                                            p0, p1,
                                            start_step = ((0, dec_calc), (START_FIELD, FIELD_STEP)),
                                            xname = 'Time',
                                            xscale = 's',
                                            yname = 'Field',
                                            yscale = 'G',
                                            zname = 'Intensity',
                                            zscale = 'mV',
                                            text = f"Scan / Field: {k} / {field}",
                                            pr = process
                                        )
                                    elif iq_cor == 1:
                                        # data_x / data_y are patched per touched column
                                        # at the readout below -- no full-array recompute
                                        process = general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Field', xscale = 'G', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Field: ' + str(k) + ' / ' + str(field), pr = process)

                            pb.awg_next_phase()
                            pb.pulser_update()

                            if (not script_test) or j == 0:
                                # Partial-range readout: only the point columns
                                # recomputed from this call's buffers come back;
                                # patch them into the persistent arrays instead of
                                # copying the full O(points x window) frame.
                                a, b, rng = pb.digitizer_get_curve(
                                    POINTS,
                                    PHASES,
                                    current_scan = k,
                                    total_scan = SCANS,
                                    partial = True )
                                if a is not None:
                                    data[0][:, rng[0]:rng[1]] = a
                                    data[1][:, rng[0]:rng[1]] = b
                                    if iq_cor == 1:
                                        # IQ-corrected integrals for just the touched
                                        # columns: the digitizer_iq phase correction
                                        # depends only on the time axis, so per-column
                                        # patching is exact.
                                        dx, dy = pb.digitizer_iq(a, b, iq_freq, zp, first_order, sec_order, integral = True)
                                        data_x[rng[0]:rng[1]] = dx
                                        data_y[rng[0]:rng[1]] = dy

                        field = round( (FIELD_STEP + field), 3 )

                        pb.pulser_shift()
                        pb.awg_shift()
                        #pb.awg_pulse_reset()

                        if not script_test:
                            conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit()
                            break

                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()
                    pb.awg_pulse_reset()
                    general.wait('1000 ms')

                    while field > START_FIELD:
                        field -= 100
                        bh15.magnet_field( field )

                self.command = 'exit'

            if self.command == 'exit':
                # Final readout before releasing the card: digitizer_at_exit()
                # waits for the background processing thread to finish the
                # queued buffers and recomputes the exact accumulated state.
                # Covers natural completion of all scans; the Stop path inside
                # the loop already did the same (repeating it is harmless).
                data[0], data[1] = pb.digitizer_at_exit()
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if iq_cor == 0:
                    general.plot_2d(
                        EXP_NAME, 
                        data, 
                        start_step = ((0, dec_calc), (START_FIELD, FIELD_STEP)), 
                        xname = 'Time', 
                        xscale = 's', 
                        yname = 'Field', 
                        yscale = 'G', 
                        zname = 'Intensity', 
                        zscale = 'mV', 
                        text = f"Scan / Field: {k} / {field}"
                        )
                elif iq_cor == 1:
                    data_x, data_y = pb.digitizer_iq(data[0], data[1], iq_freq, zp, first_order, sec_order, integral = True)
                    general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Field', xscale = 'G', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Field: ' + str(k) + ' / ' + str(field))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR AWG Experiment\n"
                    f"{'Start Field:':<{w}} {START_FIELD} G\n"
                    f"{'End Field:':<{w}} {END_FIELD} G\n"
                    f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {rect1[2]}\n"
                    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1f} ns\n"
                    f"{'Vertical Resolution:':<{w}} {FIELD_STEP} G\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                    f"{'-'*50}\n"
                    f"2D Data"
                )
                if iq_cor == 1:
                    header2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Pulsed EPR AWG Experiment\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                        f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Averages:':<{w}} {AVERAGES}\n"
                        f"{'Window:':<{w}} {tb} ns\n"
                        f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'-'*50}\n"
                        f"Pulse List:\n{pb.pulser_pulse_list()}"
                        f"{'-'*50}\n"
                        f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                        f"{'-'*50}\n"
                        f"Field (G), I (A.U.), Q (A.U.)"
                    )

                if script_test:
                    conn.send( ('test', f'') )
                else:
                    conn.send(('Open', ''))

                    while True:
                        if conn.poll():
                            msg = conn.recv()
                            if msg.startswith('FL'):
                                file_data = msg[2:]
                                break
                        general.wait('200 ms')

                    if iq_cor == 0:
                        file_handler.save_data(
                            file_data,
                            data,
                            header = header,
                            mode = 'w'
                        )
                    elif iq_cor == 1:

                        file_handler.save_data(
                            file_data,
                            np.c_[x_axis, data_x, data_y],
                            header = header2,
                            mode = 'w'
                            )

                        if save2d == 1:
                            file_data2 = file_data.replace(".csv", "_2d.csv")

                            file_handler.save_data(
                                file_data2,
                                data,
                                header = header,
                                mode = 'w'
                            )

                    conn.send( ('', f'Experiment {EXP_NAME} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            # Always release the FPGA card, on every exit path (normal, Stop, or
            # exception). The card can only be freed by this process, so this is
            # the last line of defence against leaving it in an open state.
            try:
                pb.pulser_close()
            except Exception:
                pass

    def exp_log(self, conn, decimation, num_ave, scans, points,
            log_start, log_end, exp_name,
            curve_name, rect1, rect2,
            rect3, rect4, rect5, rect6, rect7, rect8, rect9,
            n_wurst, rep_rate, field, ch0_ampl,
            ch1_ampl, awg2, awg3, awg4,
            awg5, awg6, awg7, awg8, awg9,
            b_sech_cur, correction, synt, laser_flag, laser_num,
            q_switch_delay, iq_phase, iq_corr, win_left, win_right, zero_phase,
            x0, xd, first_order, sec_order, save2d, script_test=False):

        import traceback

        if script_test:
            sys.argv = ['', 'test']

        try:
            import time
            import textwrap
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            # Route this scan's plot_1d / plot_2d through the non-blocking
            # coalescing worker so the acquisition loop isn't paced by the GUI.
            general.set_plotting_async(True)
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.BH_15 as bh
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.general_modules.csv_opener_saver as openfile

            ### Nonlinear axis
            POINTS = points
            T_start = log_start
            T_end = log_end

            nonlinear_time_raw = 10 ** np.linspace( T_start, T_end, POINTS )
            nonlinear_time = np.unique( general.numpy_round( nonlinear_time_raw, 3.2 ) )
            nonlinear_diff = np.append(np.diff(nonlinear_time), 0)
            original_time = np.concatenate(([0], nonlinear_diff)).cumsum()
            POINTS = len( nonlinear_time )
            x_axis = original_time[:-1]

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            iq_cor = iq_corr
            pb.win_left = win_left
            pb.win_right = win_right
            zp = zero_phase

            pb.phase_shift_ch1_seq_mode_awg = iq_phase

            # correction from file
            self._apply_awg_correction(pb, correction)
            
            pb.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl) )
            
            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(rect1[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            
            if iq_cor == 1:
                EXP_NAME = f'{exp_name}_L'
            elif iq_cor == 0:
                EXP_NAME = f'{exp_name}_L2D'

            # for awg pulse increments
            increment = 0

            bh15.magnet_field( field )
            general.wait('2000 ms')

            #### Creating different delays for different pulses
            name_list = []
            rel_shift = np.array( [] )

            # DETECTION pulse; is added manually
            iq_freq = -int( rect1[6].split(" MHz")[0] )
            if int(float(rect1[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=rect1[0], start=rect1[1], length=rect1[2], phase_list=rect1[3], delta_start=rect1[4])
                name_list.append('P1')
                rel_shift = np.append(rel_shift, float(rect1[4].split(' ')[0]) )

            # Laser pulse also is added manually
            if laser_flag != 1:
                pulses = [
                        rect2, rect3, rect4, 
                        rect5, rect6, rect7, rect8, 
                        rect9
                        ]
            else:
                if int(float(rect2[1].split(' ')[0])) != 0:
                    name_list.append(f'L1')
                    rel_shift = np.append(rel_shift, float(rect2[2].split(' ')[0]) ) 
                pulses = [
                        rect3, rect4, 
                        rect5, rect6, rect7, rect8, 
                        rect9
                        ]

            for p in pulses:
                length_str = p[1].split(' ')[0]
                if int(float(length_str)) != 0:
                    rel_shift = np.append(rel_shift, float(p[2].split(' ')[0]) ) 
            
            # do not take into account the same shift
            unique_arr = np.unique(rel_shift)
            minim = np.min(unique_arr)
            rel_shift -= minim

            unique_arr = np.unique(rel_shift)
            if len(unique_arr) > 1:
                next_after_min = np.partition(unique_arr, 1)[1]
            else:
                next_after_min = 1

            rel_shift = ( (rel_shift ) / next_after_min).astype(int)

            if rel_shift[0] != 0.0:
                if x0 == 0:
                    x_axis = x_axis * rel_shift[0] + self.round_to_closest( float(rect1[1].split(" ")[0]) , 3.2)
                else:
                    x_axis = x_axis * rel_shift[0] + x0
            else:
                indices = np.where(rel_shift[1:] != 0)[0] + 1
                if indices.size > 0:
                    if x0 == 0:
                        x_axis = x_axis * rel_shift[indices[0]] + self.round_to_closest( float(pulses[indices[0]][1].split(" ")[0]) , 3.2)
                    else:
                        x_axis = x_axis * rel_shift[indices[0]] + x0
                else:
                    ## this is for start increments: [3.2 3.2 3.2]
                    raise ValueError(f"Pulses do not have Start Increments")

            if 'P1' in name_list:
                pb.pulser_redefine_delta_start(name = 'P1', delta_start = f"{self.round_to_closest( nonlinear_diff[0] * rel_shift[0], 3.2 )} ns")
            ####
            
            #Laser flag
            if laser_flag != 1:

                trigger_pulses = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg2, awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                # rel_shift only got entries for non-zero pulses (see the
                # build loop above), so we can't index it by the trigger-
                # pulse position. Track the actual rel_shift slot with a
                # counter that mirrors the build order.
                rs_idx = 1 if 'P1' in name_list else 0

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if int(float(tp[1].split(' ')[0])) != 0:

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            name_list.append(f'P{2*i + 3}')
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=f"{self.round_to_closest( nonlinear_diff[0] * rel_shift[rs_idx], 3.2 )} ns"
                            )
                        rs_idx += 1
                pb.pulser_repetition_rate( REP_RATE )

            else:

                if script_test and int(float(rect2[1].split(' ')[0])) == 0:
                    raise ValueError("LASER pulse has zero length")
                #p7 is LASER pulse — its rel_shift slot sits right after P1's (if P1 was added).
                if 'L1' in name_list:
                    laser_rs_idx = 1 if 'P1' in name_list else 0
                    laser_delta_start = f"{self.round_to_closest( nonlinear_diff[0] * rel_shift[laser_rs_idx], 3.2 )} ns"
                else:
                    laser_delta_start = '0.0 ns'
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER',
                    start=rect2[0],
                    length=rect2[1],
                    delta_start=laser_delta_start
                )

                trigger_pulses = [rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                # Same rel_shift indexing fix as the laser_flag != 1 branch.
                rs_idx = (1 if 'P1' in name_list else 0) + (1 if 'L1' in name_list else 0)

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if ap[9] != '0.0 ns':
                        increment = 1

                    if int(float(tp[1].split(' ')[0])) != 0:
                        # add q_delay
                        start_val = float(tp[0].split(' ')[0]) + q_switch_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_switch_delay
                        ap[5] = f"{self.round_to_closest(start_val_awg, 3.2)} ns"

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]

                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7]
                        }

                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})

                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            name_list.append(f'P{2*i + 3}')
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG',
                                start=tp[0],
                                length=tp[1],
                                delta_start=f"{self.round_to_closest( nonlinear_diff[0] * rel_shift[rs_idx], 3.2 )} ns"
                            )
                        rs_idx += 1
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                else:
                    pb.pulser_repetition_rate( REP_RATE )


            pb.pulser_default_synt(synt)

            pb.digitizer_decimation(DEC_COEF)
            points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)
            data = np.zeros( ( 2, points_window, POINTS ) )
            dec_calc = 0.4 * DEC_COEF / 1e9
            x_axis_plot = x_axis / 1e9
            a = 0
            # Partial-range readout state: rng = point range patched by the
            # most recent successful readout; data_x / data_y = persistent
            # per-point IQ-corrected integrals (patched per touched column).
            rng = None
            data_x = np.zeros( POINTS )
            data_y = np.zeros( POINTS )
            #####

            def _scan_iter():
                if script_test:
                    yield from general.scans(SCANS)
                else:
                    k = 1
                    while k <= SCANS:
                        yield k
                        k += 1

            while self.command != 'exit':

                for k in _scan_iter():

                    sp = ls335.tc_setpoint()
                    ct = ls335.tc_temperature('B')

                    if not script_test:
                        temp_param.write_status(setpoint=sp, temp_b=ct)

                    if np.abs(sp - ct) > 0.8:
                        general.wait('8000 ms')

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        for i in range(PHASES):
                            if (not script_test) or j == 0:
                                if a is not None:
                                    if iq_cor == 0:
                                        # redraw only the columns patched by the last
                                        # readout (full frame on the very first draw)
                                        p0, p1 = rng if rng is not None else (0, POINTS)
                                        general.update_2d(
                                            EXP_NAME,
                                            data,
                                            p0, p1,
                                            start_step = ((0, dec_calc), (0, 1)),
                                            xname = 'Time',
                                            xscale = 's',
                                            yname = 'Point',
                                            yscale = '',
                                            zname = 'Intensity',
                                            zscale = 'mV',
                                            text = f"Scan / Point: {k} / {j}"
                                        )
                                    elif iq_cor == 1:
                                        # data_x / data_y are patched per touched column
                                        # at the readout below -- no full-array recompute
                                        process = general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Point: ' + str(k) + ' / ' + str(j), pr = process)

                            pb.awg_next_phase()
                            pb.pulser_update()

                            if (not script_test) or j == 0:
                                # Partial-range readout: only the point columns
                                # recomputed from this call's buffers come back;
                                # patch them into the persistent arrays instead of
                                # copying the full O(points x window) frame.
                                a, b, rng = pb.digitizer_get_curve(
                                    POINTS,
                                    PHASES,
                                    current_scan = k,
                                    total_scan = SCANS,
                                    partial = True )
                                if a is not None:
                                    data[0][:, rng[0]:rng[1]] = a
                                    data[1][:, rng[0]:rng[1]] = b
                                    if iq_cor == 1:
                                        # IQ-corrected integrals for just the touched
                                        # columns: the digitizer_iq phase correction
                                        # depends only on the time axis, so per-column
                                        # patching is exact.
                                        dx, dy = pb.digitizer_iq(a, b, iq_freq, zp, first_order, sec_order, integral = True)
                                        data_x[rng[0]:rng[1]] = dx
                                        data_y[rng[0]:rng[1]] = dy

                        # nonlinear_time_shift is calculated from the initial position of the pulses
                        if j > 0:
                            new_delta_start = nonlinear_diff[j-1]

                            delta_starts = [f"{self.round_to_closest(x * new_delta_start, 3.2)} ns" for x in rel_shift]
                            pb.pulser_redefine_delta_start(name = name_list, delta_start = delta_starts )

                        pb.pulser_shift()
                        #pb.awg_pulse_reset()
                        pb.awg_shift()

                        if not script_test:
                            conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit()
                            break

                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()
                    pb.awg_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                # Final readout before releasing the card: digitizer_at_exit()
                # waits for the background processing thread to finish the
                # queued buffers and recomputes the exact accumulated state.
                # Covers natural completion of all scans; the Stop path inside
                # the loop already did the same (repeating it is harmless).
                data[0], data[1] = pb.digitizer_at_exit()
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if iq_cor == 0:
                    general.plot_2d(
                        EXP_NAME, 
                        data, 
                        start_step = ((0, dec_calc), (0, 1)), 
                        xname = 'Time', 
                        xscale = 's', 
                        yname = 'Point', 
                        yscale = '', 
                        zname = 'Intensity', 
                        zscale = 'mV', 
                        text = f"Scan / Point: {k} / {j}"
                    )
                elif iq_cor == 1:
                    data_x, data_y = pb.digitizer_iq(data[0], data[1], iq_freq, zp, first_order, sec_order, integral = True)
                    general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Point: ' + str(k) + ' / ' + str(j))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                max_val_len = len(f"{max(x_axis):.1f}")
                col_width = max_val_len + 2 
                
                cols_per_line = 6

                formatted_values = [f"{val:<{col_width}.1f}" for val in x_axis]

                rows = []
                for i in range(0, len(formatted_values), cols_per_line):
                    rows.append("".join(formatted_values[i : i + cols_per_line]))

                first_row = rows[0]
                indent = " " * (w + 1)
                other_rows = f"\n{indent}".join(rows[1:])

                v_res_formatted = f"{first_row}\n{indent}{other_rows}" if other_rows else first_row

                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR AWG Log Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {rect1[2]}\n"
                    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1f} ns\n"
                    f"{'Vertical Resolution (ns):':<{w}} {v_res_formatted}\n"
                    f"{'Lg(X0/ns):':<{w}} {T_start}\n"
                    f"{'Lg(ΔX/ns):':<{w}} {T_end}\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                    f"{'-'*50}\n"
                    f"2D Data"
                )
                if iq_cor == 1:
                    header2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Pulsed EPR AWG Log Experiment\n"
                        f"{'Field:':<{w}} {FIELD} G\n"
                        f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                        f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Averages:':<{w}} {AVERAGES}\n"
                        f"{'Points:':<{w}} {POINTS}\n"
                        f"{'Window:':<{w}} {tb} ns\n"
                        f"{'Lg(X0/ns):':<{w}} {T_start}\n"
                        f"{'Lg(ΔX/ns):':<{w}} {T_end}\n"
                        f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'-'*50}\n"
                        f"Pulse List:\n{pb.pulser_pulse_list()}"
                        f"{'-'*50}\n"
                        f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                        f"{'-'*50}\n"
                        f"Time (s), I (A.U.), Q (A.U.)"
                    )

                if script_test:
                    conn.send( ('test', f'') )
                else:
                    conn.send(('Open', ''))

                    while True:
                        if conn.poll():
                            msg = conn.recv()
                            if msg.startswith('FL'):
                                file_data = msg[2:]
                                break
                        general.wait('200 ms')

                    if iq_cor == 0:
                        file_handler.save_data(
                            file_data,
                            data,
                            header = header,
                            mode = 'w'
                        )
                    elif iq_cor == 1:

                        file_handler.save_data(
                            file_data,
                            np.c_[x_axis_plot, data_x, data_y],
                            header = header2,
                            mode = 'w'
                            )

                        if save2d == 1:
                            file_data2 = file_data.replace(".csv", "_2d.csv")
                            file_handler.save_data(
                                file_data2,
                                data,
                                header = header,
                                mode = 'w'
                            )

                    conn.send( ('', f'Experiment {EXP_NAME} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            # Always release the FPGA card, on every exit path (normal, Stop, or
            # exception). The card can only be freed by this process, so this is
            # the last line of defence against leaving it in an open state.
            try:
                pb.pulser_close()
            except Exception:
                pass

    def exp_amplitude(self, conn, decimation, num_ave, scans, points,
            step_ampl, field, exp_name,
            curve_name, rect1, rect2,
            rect3, rect4, rect5, rect6, rect7, rect8, rect9,
            n_wurst, rep_rate, ch0_ampl,
            ch1_ampl, awg2, awg3, awg4,
            awg5, awg6, awg7, awg8, awg9,
            b_sech_cur, correction, synt, laser_flag, laser_num,
            q_switch_delay, iq_phase, iq_corr, win_left, win_right, zero_phase,
            first_order, sec_order, save2d, script_test=False):

        import traceback

        if script_test:
            sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            # Route this scan's plot_1d / plot_2d through the non-blocking
            # coalescing worker so the acquisition loop isn't paced by the GUI.
            general.set_plotting_async(True)
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.BH_15 as bh
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.general_modules.csv_opener_saver as openfile

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            iq_cor = iq_corr
            pb.win_left = win_left
            pb.win_right = win_right
            zp = zero_phase

            #rect1 DETECTION
            iq_freq = -int( rect1[6].split(" MHz")[0] )
            
            pb.phase_shift_ch1_seq_mode_awg = iq_phase

            # correction from file
            self._apply_awg_correction(pb, correction)
            
            pb.awg_amplitude('CH0', str(ch0_ampl), 'CH1', str(ch1_ampl) )
            
            POINTS = points
            STEP = step_ampl
            FIELD = field

            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(rect1[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'

            if iq_cor == 1:
                EXP_NAME = f'{exp_name}_A'
            elif iq_cor == 0:
                EXP_NAME = f'{exp_name}_A_2D'

            bh15.magnet_field( FIELD )
            general.wait('2000 ms')

            
            name_list = []
            ampl_list = []

            # DETECTION pulse
            iq_freq = -int( rect1[6].split(" MHz")[0] )
            if int(float(rect1[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=rect1[0], start=rect1[1], length=rect1[2], phase_list=rect1[3], delta_start=rect1[4], length_increment=rect1[5])

            #Laser flag
            if laser_flag != 1:


                trigger_pulses = [rect2, rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg2, awg3, awg4, awg5, 
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):
                    if int(float(tp[1].split(' ')[0])) != 0:
                        if tp[2] != '0.0 ns':
                            name_list.append(f'P{2*i + 2}')
                            f_delay = float( ap[6] )
                            ampl_list.append( float( ap[6] ) )

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]
                        
                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }
                        
                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1], 
                                delta_start=tp[2], 
                                length_increment=tp[3]
                            )
                pb.pulser_repetition_rate( REP_RATE )

            else:

                if script_test and int(float(rect2[1].split(' ')[0])) == 0:
                    raise ValueError("LASER pulse has zero length")
                #p7 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER',
                    start=rect2[0],
                    length=rect2[1],
                    delta_start=rect2[2],
                    length_increment=rect2[3]
                )

                trigger_pulses = [rect3, rect4, rect5, rect6, rect7, rect8, rect9]
                awg_params = [
                                awg3, awg4, awg5,
                                awg6, awg7, awg8, awg9
                             ]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):

                    if int(float(tp[1].split(' ')[0])) != 0:
                        if tp[2] != '0.0 ns':
                            name_list.append(f'P{2*i + 2}')
                            f_delay = float( ap[6] )
                            ampl_list.append( float( ap[6] ) )

                        start_val = float(tp[0].split(' ')[0]) + q_switch_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_switch_delay
                        ap[5] = f"{self.round_to_closest(start_val_awg, 3.2)} ns"

                        is_complex = ap[0] in ['WURST', 'SECH/TANH']
                        freq = (ap[1], ap[2]) if is_complex else ap[1]
                        
                        awg_kwargs = {
                            'name': f'P{2*i + 2}',
                            'channel': 'CH0',
                            'func': ap[0],
                            'frequency': freq,
                            'length': ap[3],
                            'sigma': ap[4],
                            'start': ap[5],
                            'amplitude': ap[6],
                            'phase_list': ap[7],
                            'length_increment': ap[9]
                        }
                        
                        if is_complex:
                            awg_kwargs.update({'n': n_wurst, 'b': b_sech_cur})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1], 
                                delta_start=tp[2], 
                                length_increment=tp[3]
                            )

                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                else:
                    pb.pulser_repetition_rate( REP_RATE )


            if len(name_list) != 0:
                point_flag = 0
                pass
            else:
                step = step_ampl
                f_delay = 0
                point_flag = 1
                if not script_test:
                    conn.send( ('Message', 'No pulse is indicated for amplitude increment; the time axis corresponds to the number of points in the experiment') )

            pb.pulser_default_synt(synt)

            pb.digitizer_decimation(DEC_COEF)
            points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)

            data = np.zeros( ( 2, points_window, POINTS ) )
            dec_calc = 0.4 * DEC_COEF / 1e9

            x_axis = f_delay + np.linspace(0, (POINTS - 1)*STEP, num = POINTS)
            x_axis_plot = x_axis
            a = 0
            # Partial-range readout state: rng = point range patched by the
            # most recent successful readout; data_x / data_y = persistent
            # per-point IQ-corrected integrals (patched per touched column).
            rng = None
            data_x = np.zeros( POINTS )
            data_y = np.zeros( POINTS )

            def _scan_iter():
                if script_test:
                    yield from general.scans(SCANS)
                else:
                    k = 1
                    while k <= SCANS:
                        yield k
                        k += 1

            while self.command != 'exit':

                for k in _scan_iter():

                    sp = ls335.tc_setpoint()
                    ct = ls335.tc_temperature('B')

                    if not script_test:
                        temp_param.write_status(setpoint=sp, temp_b=ct)

                    if np.abs(sp - ct) > 0.8:
                        general.wait('8000 ms')

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):

                        for i in range(PHASES):
                            if (not script_test) or j == 0:
                                if a is not None:
                                    if iq_cor == 0:
                                        # redraw only the columns patched by the last
                                        # readout (full frame on the very first draw)
                                        p0, p1 = rng if rng is not None else (0, POINTS)
                                        if point_flag != 1:
                                            process = general.update_2d(
                                                EXP_NAME,
                                                data,
                                                p0, p1,
                                                start_step = ((0, dec_calc), (f_delay, step)),
                                                xname = 'Time',
                                                xscale = 's',
                                                yname = 'Amplitude',
                                                yscale = '%',
                                                zname = 'Intensity',
                                                zscale = 'mV',
                                                text = f"Scan / Amplitude: {k} / { (f_delay + j * STEP):.1f}",
                                                pr = process
                                            )
                                        else:
                                            process = general.update_2d(
                                                EXP_NAME,
                                                data,
                                                p0, p1,
                                                start_step = ((0, dec_calc), (0, 1)),
                                                xname = 'Time',
                                                xscale = 's',
                                                yname = 'Point',
                                                yscale = '',
                                                zname = 'Intensity',
                                                zscale = 'mV',
                                                text = f"Scan / Point: {k} / {j}",
                                                pr = process
                                            )
                                    elif iq_cor == 1:
                                        # data_x / data_y are patched per touched column
                                        # at the readout below -- no full-array recompute
                                        if point_flag != 1:
                                            general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Amplitude', xscale = '%', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Amplitude: ' + str(k) + ' / ' + str(round(f_delay + j * STEP, 1)))
                                        else:
                                            general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))

                            pb.awg_next_phase()
                            pb.pulser_update()

                            if (not script_test) or j == 0:
                                # Partial-range readout: only the point columns
                                # recomputed from this call's buffers come back;
                                # patch them into the persistent arrays instead of
                                # copying the full O(points x window) frame.
                                a, b, rng = pb.digitizer_get_curve(
                                    POINTS,
                                    PHASES,
                                    current_scan = k,
                                    total_scan = SCANS,
                                    partial = True )
                                if a is not None:
                                    data[0][:, rng[0]:rng[1]] = a
                                    data[1][:, rng[0]:rng[1]] = b
                                    if iq_cor == 1:
                                        # IQ-corrected integrals for just the touched
                                        # columns: the digitizer_iq phase correction
                                        # depends only on the time axis, so per-column
                                        # patching is exact.
                                        dx, dy = pb.digitizer_iq(a, b, iq_freq, zp, first_order, sec_order, integral = True)
                                        data_x[rng[0]:rng[1]] = dx
                                        data_y[rng[0]:rng[1]] = dy

                        pb.pulser_shift()
                        pb.awg_pulse_reset()

                        delta = STEP * (j + 1)
                        ampl_list_cur = [x + delta for x in ampl_list]

                        pb.awg_redefine_amplitude(name = name_list, amplitude = ampl_list_cur )

                        if not script_test:
                            conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit()
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()
                    pb.awg_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                # Final readout before releasing the card: digitizer_at_exit()
                # waits for the background processing thread to finish the
                # queued buffers and recomputes the exact accumulated state.
                # Covers natural completion of all scans; the Stop path inside
                # the loop already did the same (repeating it is harmless).
                data[0], data[1] = pb.digitizer_at_exit()
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if iq_cor == 0:
                    if point_flag != 1:
                        process = general.plot_2d(
                            EXP_NAME, 
                            data, 
                            start_step = ((0, dec_calc), (f_delay, step)), 
                            xname = 'Time', 
                            xscale = 's', 
                            yname = 'Amplitude', 
                            yscale = '%', 
                            zname = 'Intensity', 
                            zscale = 'mV', 
                            text = f"Scan / Amplitude: {k} / { (f_delay + j * STEP):.1f}",
                            pr = process
                        )
                    else:
                        process = general.plot_2d(
                            EXP_NAME, 
                            data, 
                            start_step = ((0, dec_calc), (0, 1)), 
                            xname = 'Time', 
                            xscale = 's', 
                            yname = 'Point', 
                            yscale = '', 
                            zname = 'Intensity', 
                            zscale = 'mV', 
                            text = f"Scan / Point: {k} / {j}",
                            pr = process
                        )
                elif iq_cor == 1:
                    data_x, data_y = pb.digitizer_iq(data[0], data[1], iq_freq, zp, first_order, sec_order, integral = True)
                    if point_flag != 1:
                        general.plot_1d(EXP_NAME, x_axis_plot, ( data_x, data_y ), xname = 'Amplitude', xscale = '%', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Amplitude: ' + str(k) + ' / ' + str(round(f_delay + j * STEP, 1)))
                    else:
                        general.plot_1d(EXP_NAME, x_axis, ( data_x, data_y ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))


                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR AWG Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {rect1[2]}\n"
                    f"{'Horizontal Resolution:':<{w}} {0.4 * DEC_COEF:.1f} ns\n"
                    f"{'Start Amplitude:':<{w}} {f_delay} %\n"
                    f"{'Vertical Resolution:':<{w}} {STEP} %\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                    f"{'-'*50}\n"
                    f"2D Data"
                )
                if iq_cor == 1:
                    header2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Pulsed EPR AWG Experiment\n"
                        f"{'Field:':<{w}} {FIELD} G\n"
                        f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_att2_prd(), w)}\n"
                        f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                        f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Averages:':<{w}} {AVERAGES}\n"
                        f"{'Points:':<{w}} {POINTS}\n"
                        f"{'Window:':<{w}} {tb} ns\n"
                        f"{'Start Amplitude:':<{w}} {f_delay} %\n"
                        f"{'Horizontal Resolution:':<{w}} {STEP} %\n"
                        f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'-'*50}\n"
                        f"Pulse List:\n{pb.pulser_pulse_list()}"
                        f"{'-'*50}\n"
                        f"AWG Pulse List:\n{pb.awg_pulse_list()}"
                        f"{'-'*50}\n"                        
                        f"Time (s), I (A.U.), Q (A.U.)"
                    )

                if script_test:
                    conn.send( ('test', f'') )
                else:
                    conn.send(('Open', ''))

                    while True:
                        if conn.poll():
                            msg = conn.recv()
                            if msg.startswith('FL'):
                                file_data = msg[2:]
                                break
                        general.wait('200 ms')

                    if iq_cor == 0:
                        file_handler.save_data(
                            file_data,
                            data,
                            header = header,
                            mode = 'w'
                        )
                    elif iq_cor == 1:

                        file_handler.save_data(
                            file_data,
                            np.c_[x_axis_plot, data_x, data_y],
                            header = header2,
                            mode = 'w'
                            )
                        if save2d == 1:
                            file_data2 = file_data.replace(".csv", "_2d.csv")

                            file_handler.save_data(
                                file_data2,
                                data,
                                header = header,
                                mode = 'w'
                            )

                    conn.send( ('', f'Experiment {EXP_NAME} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            # Always release the FPGA card, on every exit path (normal, Stop, or
            # exception). The card can only be freed by this process, so this is
            # the last line of defence against leaving it in an open state.
            try:
                pb.pulser_close()
            except Exception:
                pass

def main():
    """
    A function to run the main window of the programm.
    """
    app = QApplication(sys.argv)
    apply_app_style(app, app_id='Atomize.ITC.AWGPhasing')
    main = MainWindow()
    main.show()
    # Optional preset path (e.g. from the Sequence Calculator's one-click open).
    # argv[1] == 'test' is reserved for the script-side test mode, so skip it.
    if len(sys.argv) > 1 and sys.argv[1] not in ('', 'test') and os.path.isfile(sys.argv[1]):
        main.open_file(sys.argv[1])
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
