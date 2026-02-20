#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import traceback
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QTextEdit, QGridLayout, QFrame, QCheckBox, QFileDialog, QVBoxLayout, QTabWidget, QScrollArea, QHBoxLayout, QPlainTextEdit
from PyQt6.QtGui import QIcon, QColor, QAction
from PyQt6.QtCore import Qt, QTimer
import atomize.general_modules.general_functions as general
import atomize.general_modules.csv_opener_saver as openfile

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
        path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', 'libs')  #, '..', '..', 'libs'
        os.chdir(path_to_main2)
        #####
        
        self.awg_output_shift = 0 #494 # in ns

        # Phase correction
        self.deg_rad = 57.2957795131
        self.sec_order_coef = -2*np.pi/2
        
        self.design_tab_1()
        self.design_tab_2()
        self.design_tab_3()
        self.design_tab_4()
        self.design_tab_5()

        self.laser_q_switch_delay = 0

        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI will freeze until the task terminates. During that time, the user won’t be able to interact with the application
        """

        self.exit_clicked = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_messages)
        #self.monitor_timer = QTimer()
        #self.monitor_timer.timeout.connect(self.check_process_status)
        self.file_handler = openfile.Saver_Opener()

    def closeEvent(self, event):
        event.ignore()
        self.turn_off()

    def menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("QMenuBar { color: rgb(193, 202, 227); font-weight: bold; font-size: 14px; } QMenu::item { color: rgb(211, 194, 78); } QMenu::item:selected {color: rgb(193, 202, 227); }")
        file_menu = menubar.addMenu("File")
        menubar.setFixedHeight(27)

        self.action_read = QAction("Read from file", self)
        self.action_read.triggered.connect( self.open_file_dialog )
        file_menu.addAction(self.action_read)

        self.action_save = QAction("Save to file", self)
        self.action_save.triggered.connect(self.save_file_dialog)
        file_menu.addAction(self.action_save)

    def design_tab_1(self):
        self.setObjectName("MainWindow")
        self.setWindowTitle("AWG Channel Pulse Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_pulse.png')
        self.setWindowIcon( QIcon(icon_path) )
        self.path = os.path.join(path_to_main, '..', '..', '..', '..', 'experimental_data')

        self.setMinimumHeight(700)
        self.setMinimumWidth(1360)
        self.setMaximumWidth(2200)

        central_container = QWidget()
        self.setCentralWidget(central_container)
        main_window_layout = QVBoxLayout(central_container)
        main_window_layout.setContentsMargins(0, 0, 0, 0)
        main_window_layout.setSpacing(0)

        self.tab_pulse = QTabWidget()
        main_window_layout.addWidget(self.tab_pulse)

        self.tab_pulse.setTabShape(QTabWidget.TabShape.Rounded)
        self.tab_pulse.setStyleSheet("""
            QTabBar::tab { 
                width: 151px; 
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
            /* Скрываем кнопки по бокам (стрелки) */
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
        labels = [("Start", "label_1"), ("Length", "label_2"), ("Sigma", "label_3"), ("Start Increment", "label_4"), ("Length Increment", "label_5"), ("Frequency", "label_6"), ("Frequency Sweep", "label_7"), ("Amplitude", "label_8"), ("Phase", "label_9"), ("Type", "label_10"), ("Repetition Rate", "label_11"), ("Magnetic Field", "label_12")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(130, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        pulses = [(QDoubleSpinBox, 0, 100e6, 0, 3.2, 1, " ns", "_st", "_start"),
                  (QDoubleSpinBox, 0, 1900, 0, 3.2, 1, " ns", "_len", "_length"),
                  (QDoubleSpinBox, 0, 1900, 0, 3.2, 1, " ns", "_sig", "_sigma"),
                  (QDoubleSpinBox, 0, 1e6, 0, 3.2, 1, " ns", "_st_inc", "_st_increment"),
                  (QDoubleSpinBox, 0, 320, 0, 3.2, 1, " ns", "_len_inc", "_len_increment")
                 ]

        for j in range(1, 6):
            pulse_set = pulses[j-1]
            label_widget = getattr(self, f"label_{j}")
            self.gridLayout.addWidget(label_widget, j + 2, 0)

            for i in range(1, 10):
                spin_box = (pulse_set[0])()
                spin_box.setRange(pulse_set[1], pulse_set[2])
                spin_box.setStyleSheet("QDoubleSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
                spin_box.setSingleStep(pulse_set[4])
                if (i == 1) and (j == 1):
                    spin_box.setValue(576)
                elif (i == 1) and (j == 2):
                    spin_box.setRange(0, 6.4e3)
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
                spin_box.setFixedSize(130, 26)
                spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)

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
                
                self.update_pulse_value(i, pulse_set[7], pulse_set[8], v2_sfx)
                self.gridLayout.addWidget(spin_box, j + 2, i)

                if j == 1:
                    lbl = QLabel(f"{i}")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                    lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
                    self.gridLayout.addWidget(lbl, 0, i)


        awg_pulses = [
            (QSpinBox, -1000, 1000, 50, 5, 0, " MHz", "_fr", "_freq"),
            (QSpinBox, -1000, 1000, 350, 5, 0, " MHz", "_sw", "wurst_sweep_cur_"),
            (QSpinBox, 1, 100, 100, 1, 0, " %", "_cf", "_coef")
        ]

        for j in range(9, 12):
            pulse_set = awg_pulses[j - 9]
            label_widget = getattr(self, f"label_{j - 3}")
            self.gridLayout.addWidget(label_widget, j, 0)

            for i in range(1, 10):
                spin_box = pulse_set[0]()
                spin_box.setRange(int(pulse_set[1]), int(pulse_set[2]))
                spin_box.setStyleSheet("QSpinBox { color : rgb(193, 202, 227); selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
                spin_box.setSingleStep(pulse_set[4])
                
                if i == 1:
                    if j == 9 or j == 10:
                        spin_box.setRange(0, 0)
                    elif j == 11:
                        spin_box.setRange(100, 100)
                else:  
                    spin_box.setValue(pulse_set[3])

                spin_box.setSuffix(pulse_set[6])
                spin_box.setFixedSize(130, 26)
                spin_box.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
                spin_box.setKeyboardTracking(False)

                attr_name = f"P{i}{pulse_set[7]}"
                setattr(self, attr_name, spin_box)
                
                if pulse_set[7] == "_cf":
                    spin_box.valueChanged.connect(lambda _, idx = i: self.update_coef_param(idx))
                    self.update_coef_param(i)
                else:
                    prefix = "P"
                    v_name = "p" if pulse_set[7] == "_fr" else ""
                    spin_box.valueChanged.connect(
                        lambda _, idx=i, p=prefix, s=pulse_set[7], v = pulse_set[8]: 
                        self.update_awg_generic(idx, s, v)
                    )
                    self.update_awg_generic(i, pulse_set[7], pulse_set[8])

                self.gridLayout.addWidget(spin_box, j, i)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        self.gridLayout.addWidget(hline(), 1, 0, 1, 10)
        self.gridLayout.addWidget(hline(), 8, 0, 1, 10)
        self.gridLayout.addWidget(hline(), 12, 0, 1, 10)

        # ---- Combo boxes----
        combo_boxes = [("DETECTION", "_type", "_type", "_typ", ["DETECTION"]),
                       ("SINE", "_type", "_type", "_typ", ["SINE", "GAUSS", "SINC", "WURST", "SECH/TANH", "LASER"]),
                       ("SINE", "_type", "_type", "_typ", ["SINE", "GAUSS", "SINC", "WURST", "SECH/TANH"])
                      ]

        label_widget = getattr(self, f"label_9")
        label_widget.setFixedSize(130, 26)
        self.gridLayout.addWidget(label_widget, 13, 0)

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
            combo.setFixedSize(130, 26)
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

            self.gridLayout.addWidget(combo, 13, i)

        
        label_widget = getattr(self, f"label_10")
        label_widget.setFixedSize(130, 26)
        self.gridLayout.addWidget(label_widget, 14, 0)
        self.gridLayout.addWidget(hline(), 15, 0, 1, 10)

        # ---- Text Edits ----
        text_edit = ["+x,-x", "+x,-x", "+x,+x"]

        for i in range(1, 10):
            if i == 1:
                txt = QTextEdit(text_edit[0])
            elif i == 2:
                txt = QTextEdit(text_edit[1])
            else:
                txt = QTextEdit(text_edit[2])
            txt.setFixedSize(130, 60)
            txt.setAcceptRichText(False)
            #txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
            
            setattr(self, f"Phase_{i}", txt)
            txt.textChanged.connect(lambda idx = i: self.update_pulse_phase(idx))
            self.update_pulse_phase(i)

            self.gridLayout.addWidget(txt, 14, i)

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
            rr_box.setFixedSize(130, 26)
            rr_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            rr_box.setKeyboardTracking( False )
            setattr(self, attr_name, rr_box)
            if attr_name == "Rep_rate":
                setattr(self, par_name, str( rr_box.value() ) + ' Hz')
            elif attr_name == 'Field':
                setattr(self, par_name, float( rr_box.value() ))

            self.buttons_layout.addWidget(rr_box, box_c, 1)
            box_c += 1

        label_widget = getattr(self, f"label_11")
        self.buttons_layout.addWidget(label_widget, 0, 0)
        label_widget.setFixedSize(130, 26)
        label_widget = getattr(self, f"label_12")
        label_widget.setFixedSize(130, 26)
        self.buttons_layout.addWidget(label_widget, 1, 0)
        self.buttons_layout.addWidget(hline(), 2, 0, 1, 12)

        # ---- Buttons ----
        buttons = [("Run Pulses", "button_update", self.update),
                   ("Stop Pulses", "button_stop", self.dig_stop),
                   ("Exit", "button_off", self.turn_off),
                   ("Start Experiment", "button_start_exp", self.start_exp),
                   ("Stop Experiment", "button_stop_exp", self.stop_exp)
                    ]

        btn_c = 3
        btn_cl = 0
        for name, attr_name, func in buttons:
            btn = QPushButton(name)
            btn.setFixedSize(130, 40)
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
        setattr(self, "errors", txt)
        txt.setStyleSheet("QPlainTextEdit { color : rgb(211, 194, 78) ; selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")
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
        labels = [("Acquisitions", "label_17"), ("Integration Left", "label_18"), ("Integration Right", "label_19"), ("Decimation", "label_20")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(130, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QSpinBox, "Acq_number", "number_averages", self.acq_number, 1, 1e4, 1, 1, 0, ""),
                      (QSpinBox, "Dec", "decimation", self.decimat, 1, 4, 1, 1, 0, ""),
                      (QDoubleSpinBox, "Win_left", "cur_win_left", self.win_left, 0, 6400, 0, 0.4, 1, " ns"),
                      (QDoubleSpinBox, "Win_right", "cur_win_right", self.win_right, 0, 6400, 320, 0.4, 1, " ns")
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
        left_grid.setRowStretch(2, 1)
        left_grid.setColumnStretch(2, 1)

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
        
        container_layout.addLayout(left_grid)
        container_layout.addSpacing(20)
        container_layout.addLayout(right_grid)

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
        labels = [("Points to Drop", "label_11"), ("Zero Order", "label_12"), ("First Order", "label_13"), ("Second Order", "label_14"), ("Live FFT", "label_15"), ("Quadrature", "label_16")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(130, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QSpinBox, "P_to_drop", "p_to_drop", self.p_to_drop_func, 0, 1e4, 0, 1, 0, ""),
                      (QDoubleSpinBox, "Zero_order", "zero_order", self.zero_order_func, -0.1, 360.1, 0, 0.1, 4, " deg"),
                      (QDoubleSpinBox, "First_order", "first_order", self.first_order_func, -100, 100, 0, 0.001, 4, ""),
                      (QDoubleSpinBox, "Second_order", "second_order", self.second_order_func, -100, 100, 0, 0.001, 4, " MHz/ns")
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

            spin_box.setKeyboardTracking( False )
            
            setattr(self, attr_name, spin_box)
            if isinstance(spin_box, QDoubleSpinBox):
                if attr_name == 'Zero_order':
                    setattr(self, par_name, float(spin_box.value() / self.deg_rad))
                else:
                    setattr(self, par_name, float(spin_box.value()))

            else:
                setattr(self, par_name, int(spin_box.value()))

        if self.second_order != 0.0:
            self.second_order = self.sec_order_coef / ( float( self.Second_order.value() ) * 1000 )

        self.l_mode = 0

        # ---- Check Boxes ----
        check_boxes = [("fft_box", self.fft_online),
                       ("Quad_cor", self.quad_online)]

        for attr_name, func in check_boxes:
            check = QCheckBox("")
            setattr(self, attr_name, check)
            check.stateChanged.connect(func)
            check.setStyleSheet("""
                QCheckBox { 
                    color: rgb(193, 202, 227); 
                    background-color: transparent; 
                    font-weight: bold;
                    spacing: 8px; 
                }

                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    background-color: rgb(63, 63, 97);
                    border: 1px solid rgb(83, 83, 117);
                    border-radius: 3px;
                }

                QCheckBox::indicator:hover {
                    border: 1px solid rgb(211, 194, 78);
                }

                QCheckBox::indicator:pressed {
                    background-color: rgb(83, 83, 117);
                }

                QCheckBox::indicator:checked {
                    background-color: rgb(211, 194, 78);
                    border: 3px solid rgb(63, 63, 97); 
                }
            """)
            check.setFixedSize(130, 26)

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

        gridLayout.addWidget(hline(), 2, 0, 1, 2)
        
        gridLayout.addWidget(self.label_11, 3, 0)
        gridLayout.addWidget(self.P_to_drop, 3, 1)
        gridLayout.addWidget(self.label_12, 4, 0)
        gridLayout.addWidget(self.Zero_order, 4, 1)
        gridLayout.addWidget(self.label_13, 5, 0)
        gridLayout.addWidget(self.First_order, 5, 1)
        gridLayout.addWidget(self.label_14, 6, 0)
        gridLayout.addWidget(self.Second_order, 6, 1)

        gridLayout.addWidget(hline(), 7, 0, 1, 2)

        gridLayout.setRowStretch(8, 2)
        gridLayout.setColumnStretch(8, 2)

        # flag for not writing the data when digitizer is off
        self.opened = 0
        self.fft = 0
        self.quad = 0
        self.double_change = 0

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
            lbl.setFixedSize(130, 26)
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
            combo.setFixedSize(130, 26)
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
        dig_setting_page = QWidget()
        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(15, 15, 10, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        dig_setting_page.setLayout(gridLayout)

        self.tab_pulse.addTab(dig_setting_page, "AWG")
        self.tab_pulse.tabBar().setTabTextColor(4, QColor(193, 202, 227))

        # ---- Labels & Inputs ----
        labels = [("Amplitude I", "label_a1"), ("Amplitude Q", "label_a2"), ("Phase", "label_a3"), ("N [wurst; sech/tanh]", "label_a4"), ("b [sech/tanh]", "label_a5"), ("Resonator Profile", "label_a6")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(143, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Boxes ----
        double_boxes = [(QSpinBox, "Ampl_1", "ch0_ampl", self.ch0_amp, 1, 260, 260, 1, 0, ""),
                        (QSpinBox, "Ampl_2", "ch1_ampl", self.ch1_amp, 1, 260, 260, 1, 0, ""),
                        (QDoubleSpinBox, "Phase", "cur_phase", self.awg_phase, 0, 360, 90, 0.1, 2, " deg"),
                        (QSpinBox, "N_wurst", "n_wurst_cur", self.n_wurst, 1, 100, 10, 1, 0, ""),
                        (QDoubleSpinBox, "B_sech", "b_sech_cur", self.b_sech_func, 0.005, 10, 0.02, 0.001, 3, " 1/ns")
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
        combo_laser = [("No", "Combo_cor", "", self.combo_cor_fun, ["No", "Only Pi/2", "All"])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_laser:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            combo.currentIndexChanged.connect(func)
            combo.addItems(item)
            combo.setCurrentText(cur_text)
            combo.setFixedSize(130, 26)
            combo.setStyleSheet("""
                QComboBox 
                { color : rgb(193, 202, 227); 
                selection-color: rgb(211, 194, 78); 
                selection-background-color: rgb(63, 63, 97);
                outline: none;
                }
                """)

        self.combo_cor_fun()

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
        right_grid.addWidget(hline(), 5, 0, 1, 2)

        right_grid.setRowStretch(6, 1)
        right_grid.setColumnStretch(6, 1)
        
        container_layout.addLayout(left_grid)
        container_layout.addSpacing(20)
        container_layout.addLayout(right_grid)

        container_layout.addStretch(1) 
        gridLayout.addLayout(container_layout, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        gridLayout.setColumnStretch(1, 1)
        gridLayout.setRowStretch(1, 1)

    def update_coef_param(self, index):
        attr_name = f"P{index}_cf"
        
        if hasattr(self, attr_name):
            widget = getattr(self, attr_name)
            val = widget.value()
            value = val
            
            setattr(self, f"p{index}_coef", value)
            #print(f"Updated p{index}_coef to {value}")
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

    def update_pulse_phase(self, index):

        text_edit = getattr(self, f"Phase_{index}")
        temp = text_edit.toPlainText().strip()
        
        try:
            if len(temp) >= 2: #and temp[0] == '[' and temp[-1] == ']':
                content = temp[:].split(',') #[1:-1]
                phases = [p.strip() for p in content if p.strip()]
                
                if len(phases) == 1:
                    phases.append(phases[0])
                
                setattr(self, f"ph_{index}", phases)
                
        except (IndexError, AttributeError):
            pass

    def update_awg_generic(self, index, attr_suffix, val_suffix):
        widget = getattr(self, f"P{index}{attr_suffix}")
        value = self.add_mhz(widget.value()) if "_freq" in val_suffix or "wurst" in val_suffix else widget.value()
        
        target_attr = f"p{index}{val_suffix}" if val_suffix.startswith("_") else f"{val_suffix}{index}"
        setattr(self, target_attr, value)
        #print(f"Updated: {target_attr} = {value}")

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

        #print(f"Updated: p{index}{val1_suffix} = {val1}")
 
    def start_exp(self):
        pass

    def stop_exp(self):
        pass

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
            self.message('Digitizer is not running')

    def zero_order_func(self):
        """
        A function to change the zero order phase correction value
        """
        self.zero_order = float( self.Zero_order.value() ) / self.deg_rad

        # cycling
        if self.zero_order < 0.0:
            self.Zero_order.setValue(360.0)
            self.zero_order = float( self.Zero_order.value() )/ self.deg_rad
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
                self.message('Digitizer is not running')

    def first_order_func(self):
        """
        A function to change the first order phase correction value
        """
        self.first_order = float( self.First_order.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'FO' + str( self.first_order ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def second_order_func(self):
        """
        A function to change the second order phase correction value
        """
        self.second_order = float( self.Second_order.value() )
        if self.second_order != 0.0:
            self.second_order = self.sec_order_coef / ( float( self.Second_order.value() ) * 1000 )
        
        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'SO' + str( self.second_order ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def p_to_drop_func(self):
        """
        A function to change the number of points to drop
        """
        self.p_to_drop = float( self.P_to_drop.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'PD' + str( self.p_to_drop ) )
            except AttributeError:
                self.message('Digitizer is not running')

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
            self.message('Digitizer is not running')

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
            self.message('Digitizer is not running')

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
                self.message('Digitizer is not running')

    def win_right(self):
        self.cur_win_right = int( float( self.Win_right.value() ) / self.time_per_point )
        if round( self.cur_win_right * self.time_per_point, 1) > round( float( self.remove_ns( self.p1_length ) ), 1):
            self.cur_win_right = int( round( float( self.remove_ns( self.p1_length ) ), 1) / self.time_per_point )
            self.Win_right.setValue( round( self.cur_win_right * self.time_per_point, 1) )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'WR' + str( self.cur_win_right ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def acq_number(self):
        """
        A function to change number of averages
        """
        self.number_averages = int( self.Acq_number.value() )

        if self.opened == 0:
            try:
                self.parent_conn_dig.send( 'NA' + str( self.number_averages ) )
            except AttributeError:
                self.message('Digitizer is not running')

    def open_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "AWG pulse phase list (*.phase_awg)",\
            options = QFileDialog.Option.DontUseNativeDialog)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

    def save_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "AWG pulse phase list (*.phase_awg)",\
            options = QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        # use QFileDialog.DontUseNativeDialog to change directory
        filedialog.setStyleSheet("QWidget { background-color : rgb(42, 42, 64); color: rgb(211, 194, 78);}")
        filedialog.setFileMode(QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file)
        filedialog.show()

    def open_file(self, filename):
        """
        A function to open a pulse list
        :param filename: string
        """
        self.opened = 1

        text = open(filename).read()
        lines = text.split('\n')

        self.setter(text, 0, self.P1_type, self.P1_st, self.P1_len, self.P1_sig, self.P1_fr, self.P1_sw, self.P1_cf, self.Phase_1)
        self.setter(text, 1, self.P2_type, self.P2_st, self.P2_len, self.P2_sig, self.P2_fr, self.P2_sw, self.P2_cf, self.Phase_2)
        self.setter(text, 2, self.P3_type, self.P3_st, self.P3_len, self.P3_sig, self.P3_fr, self.P3_sw, self.P3_cf, self.Phase_3)
        self.setter(text, 3, self.P4_type, self.P4_st, self.P4_len, self.P4_sig, self.P4_fr, self.P4_sw, self.P4_cf, self.Phase_4)
        self.setter(text, 4, self.P5_type, self.P5_st, self.P5_len, self.P5_sig, self.P5_fr, self.P5_sw, self.P5_cf, self.Phase_5)
        self.setter(text, 5, self.P6_type, self.P6_st, self.P6_len, self.P6_sig, self.P6_fr, self.P6_sw, self.P6_cf, self.Phase_6)
        self.setter(text, 6, self.P7_type, self.P7_st, self.P7_len, self.P7_sig, self.P7_fr, self.P7_sw, self.P7_cf, self.Phase_7)

        self.Rep_rate.setValue( float( lines[7].split(':  ')[1] ) )
        self.Field.setValue( float( lines[8].split(':  ')[1] ) )
        #self.Delay.setValue( float( lines[9].split(':  ')[1] ) )
        self.Ampl_1.setValue( int( lines[10].split(':  ')[1] ) )
        self.Ampl_2.setValue( int( lines[11].split(':  ')[1] ) )
        self.Phase.setValue( float( lines[12].split(':  ')[1] ) )
        self.N_wurst.setValue( int( lines[13].split(':  ')[1] ) )
        self.B_sech.setValue( float( lines[14].split(':  ')[1] ) )

        #self.live_mode.setCheckState(Qt.CheckState.Unchecked)
        self.fft_box.setCheckState(Qt.CheckState.Unchecked)
        self.Quad_cor.setCheckState(Qt.CheckState.Unchecked)
        self.Win_left.setValue( round(float( lines[17].split(':  ')[1] ), 1) )
        self.Win_right.setValue( round(float( lines[18].split(':  ')[1] ), 1) )
        self.Acq_number.setValue( int( lines[19].split(':  ')[1] ) )
        self.Dec.setValue( int( lines[25].split(':  ')[1] ) )

        try:
            self.P_to_drop.setValue( int( lines[20].split(':  ')[1] ) )
            self.Zero_order.setValue( float( lines[21].split(':  ')[1] ) )
            self.First_order.setValue( float( lines[22].split(':  ')[1] ) )
            self.Second_order.setValue( float( lines[23].split(':  ')[1] ) )
            #self.Combo_osc.setCurrentText( str( lines[24].split(':  ')[1] ) )
        except IndexError:
            pass

        self.dig_stop()

        self.fft = 0
        self.quad = 0
        self.opened = 0

    def setter(self, text, index, typ, st, leng, sig, freq, w_sweep, coef, phase):
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
        coef.setValue( int( array[6] ) )
        phase.setPlainText( str( (array[7])[1:-1] ) )

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        if filename[-9:] != 'phase_awg':
            filename = filename + '.phase_awg'
        with open(filename, 'w') as file:
            file.write( 'P1:  ' + self.P1_type.currentText() + ',  ' + str(self.P1_st.value()) + ',  ' + str(self.P1_len.value()) + ',  '\
                + str(self.P1_sig.value()) + ',  ' + str(self.P1_fr.value()) + ',  ' + str(self.P1_sw.value()) + ',  '\
                + str(self.P1_cf.value()) + ',  ' + str('[' + ','.join(self.ph_1) + ']') + '\n' )
            file.write( 'P2:  ' + self.P2_type.currentText() + ',  ' + str(self.P2_st.value()) + ',  ' + str(self.P2_len.value()) + ',  '\
                + str(self.P2_sig.value()) + ',  ' + str(self.P2_fr.value()) + ',  ' + str(self.P2_sw.value()) + ',  '\
                + str(self.P2_cf.value()) + ',  ' + str('[' + ','.join(self.ph_2) + ']') + '\n' )
            file.write( 'P3:  ' + self.P3_type.currentText() + ',  ' + str(self.P3_st.value()) + ',  ' + str(self.P3_len.value()) + ',  '\
                + str(self.P3_sig.value()) + ',  ' + str(self.P3_fr.value()) + ',  ' + str(self.P3_sw.value()) + ',  '\
                + str(self.P3_cf.value()) + ',  ' + str('[' + ','.join(self.ph_3) + ']') + '\n' )
            file.write( 'P4:  ' + self.P4_type.currentText() + ',  ' + str(self.P4_st.value()) + ',  ' + str(self.P4_len.value()) + ',  '\
                + str(self.P4_sig.value()) + ',  ' + str(self.P4_fr.value()) + ',  ' + str(self.P4_sw.value()) + ',  '\
                + str(self.P4_cf.value()) + ',  ' + str('[' + ','.join(self.ph_4) + ']') + '\n' )
            file.write( 'P5:  ' + self.P5_type.currentText() + ',  ' + str(self.P5_st.value()) + ',  ' + str(self.P5_len.value()) + ',  '\
                + str(self.P5_sig.value()) + ',  ' + str(self.P5_fr.value()) + ',  ' + str(self.P5_sw.value()) + ',  '\
                + str(self.P5_cf.value()) + ',  ' + str('[' + ','.join(self.ph_5) + ']') + '\n' )
            file.write( 'P6:  ' + self.P6_type.currentText() + ',  ' + str(self.P6_st.value()) + ',  ' + str(self.P6_len.value()) + ',  '\
                + str(self.P6_sig.value()) + ',  ' + str(self.P6_fr.value()) + ',  ' + str(self.P6_sw.value()) + ',  '\
                + str(self.P6_cf.value()) + ',  ' + str('[' + ','.join(self.ph_6) + ']') + '\n' )
            file.write( 'P7:  ' + self.P7_type.currentText() + ',  ' + str(self.P7_st.value()) + ',  ' + str(self.P7_len.value()) + ',  '\
                + str(self.P7_sig.value()) + ',  ' + str(self.P7_fr.value()) + ',  ' + str(self.P7_sw.value()) + ',  '\
                + str(self.P7_cf.value()) + ',  ' + str('[' + ','.join(self.ph_7) + ']') + '\n' )

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
            file.write( 'Oscilloscope:  ' + str('2012a') + '\n' )
            file.write( 'Decimation:  ' + str( self.Dec.value() ) + '\n' )

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

    def closeEvent(self, event):
        """
        A function to do some actions when the main window is closing.
        """
        event.ignore()
        self.dig_stop()
        sys.exit()

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

    def decimat(self):
        """
        A function to set decimation coefficient
        """
        self.decimation = self.Dec.value()
        self.time_per_point = 0.4 * self.decimation

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
        ###    self.message('Digitizer is not running')

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

        try:
            self.parent_conn_dig.send( 'RR' + str( self.repetition_rate.split(' ')[0] ) )
        except AttributeError:
            self.message('Digitizer is not running')

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
            self.message('Digitizer is not running')

    def update(self):
        """
        A function to run pulses
        """
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

        file_to_read.close()

        if self.opened == 0:
            try:
                self.parent_conn_dig.send('exit')
                #self.monitor_timer.start(200)
                self.digitizer_process.join()
                self.check_process_status()
            except AttributeError:
                if self.exit_clicked == 1:
                    sys.exit()

    def dig_start_exp(self):
        pass

    def dig_start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """
        worker = Worker()

        self.p1_list = [self.p1_typ, self.p1_start, self.p1_length, self.ph_1]

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
        self.digitizer_process = Process( target = worker.dig_test, args = ( self.child_conn_dig, 
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
            self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay ) )

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(193, 202, 227); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")
               
        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')
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
            """)

    def parse_message(self):
        msg_type, data = self.parent_conn_dig.recv()
        
        if msg_type == 'Status':
            pass
            #self.progress_bar.setValue(int(data))
        elif msg_type == 'Open':
            self.open_dialog()
        elif msg_type == 'Message':
            self.errors.appendPlainText(data)
        elif msg_type == 'Error':
            self.last_error = True
            self.timer.stop()
            #self.progress_bar.setValue(0)
            if msg_type != 'test':
                self.message(data)
            self.errors.appendPlainText(data)
            self.button_blue()                   
        else:
            self.timer.stop()
            self.errors.appendPlainText(data)
            #self.progress_bar.setValue(0)
            if msg_type != 'test':
                self.message(data)
                self.button_blue()

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
                break

        #time.sleep(0.1)

        if hasattr(self, 'digitizer_process') and not self.digitizer_process.is_alive():
            if self.parent_conn_dig.poll():
                #return #better to repeat the whole logic
                self.parse_message()

            self.timer.stop()

            if getattr(self, 'is_testing', False):
                self.is_testing = False
                if not self.last_error:
                    self.last_error = False 
                    time.sleep(0.1)
                    self.run_main_experiment()
                else:
                    self.last_error = False

    def check_process_status(self):
        if self.digitizer_process.is_alive():
            return
        
        #self.monitor_timer.stop()
        #self.digitizer_process.join()
        self.timer.stop()
        #self.progress_bar.setValue(0)
        self.errors.clear()
        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; }  ")

        if self.exit_clicked == 1:
            sys.exit()

    def open_dialog(self):
        file_data = self.file_handler.create_file_dialog(multiprocessing = True)        

        if file_data:
            self.parent_conn.send( 'FL' + str( file_data ) )
        else:
            self.parent_conn.send( 'FL' + '' )

    def run_main_experiment(self):

        worker = Worker()
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
            self.laser_flag, self.combo_laser_num, self.laser_q_switch_delay ) )

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ") 

        self.digitizer_process.start()
        self.parent_conn_dig.send('start')
        self.timer.start(200)

# The worker class that run the digitizer in a different thread
class Worker():
    def __init__(self):
        super(Worker, self).__init__()
        # initialization of the attribute we use to stop the experimental script
        # when button Stop is pressed
        #from atomize.main.client import LivePlotClient

        self.command = 'start'
        
    def dig_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22, p23, p24, p25, p26, p27, p28, p29, p30, p31, p32, p33, p34, p35, p36, p37, p38, p39, p40, p41, p42 ):
        """
        function that contains updating of the digitizer
        """
        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        #import time
        import traceback


        try:
            import time
            import numpy as np
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.math_modules.fft as fft_module
            import atomize.device_modules.BH_15 as itc

            pb = pb_pro.Insys_FPGA()
            fft = fft_module.Fast_Fourier()
            bh15 = itc.BH_15()
            #bh15.magnet_setup( p15, 0.5 )
            bh15.magnet_field( p15 ) #, calibration = 'True' )

            process = 'None'
            num_ave = p3

            ###
            pb.phase_shift_ch1_seq_mode_awg = p17
            ###

            # correction from file
            if p33 == 0:
                pass
            elif p33 == 1:
                path_to_main = os.path.abspath( os.getcwd() )
                path_file = os.path.join(path_to_main, '../atomize/control_center/correction.param')
                file_to_read = open(path_file, 'r')

                text_from_file = file_to_read.read().split('\n')
                # ['BL: 5.92087', 'A1: 412.868', 'X1: -124.647', 'W1: 62.0069', 'A2: 420.717', 'X2: -35.8879', 
                # 'W2: 34.4214', A3: 9893.97', 'X3: 12.4056', 'W3: 150.304', 'LOW: 16', 'LIMIT: 23', '']

                coef = [float( text_from_file[0].split(' ')[1] ), 
                        float( text_from_file[1].split(' ')[1] ), 
                        float( text_from_file[2].split(' ')[1] ), 
                        float( text_from_file[3].split(' ')[1] ), 
                        float( text_from_file[4].split(' ')[1] ), 
                        float( text_from_file[5].split(' ')[1] ), 
                        float( text_from_file[6].split(' ')[1] ), 
                        float( text_from_file[7].split(' ')[1] ), 
                        float( text_from_file[8].split(' ')[1] ), 
                        float( text_from_file[9].split(' ')[1] )
                        ]

                pb.awg_correction(only_pi_half = 'True', 
                    coef_array = coef, 
                    low_level = float( text_from_file[10].split(' ')[1] ), 
                    limit = float( text_from_file[11].split(' ')[1] )
                    )

            elif p33 == 2:
                path_to_main = os.path.abspath( os.getcwd() )
                path_file = os.path.join(path_to_main, '../atomize/control_center/correction.param')
                file_to_read = open(path_file, 'r')

                text_from_file = file_to_read.read().split('\n')
                # ['BL: 5.92087', 'A1: 412.868', 'X1: -124.647', 'W1: 62.0069', 'A2: 420.717', 'X2: -35.8879', 
                # 'W2: 34.4214', A3: 9893.97', 'X3: 12.4056', 'W3: 150.304', 'LOW: 16', 'LIMIT: 23', '']
                
                coef = [float( text_from_file[0].split(' ')[1] ), 
                        float( text_from_file[1].split(' ')[1] ), 
                        float( text_from_file[2].split(' ')[1] ), 
                        float( text_from_file[3].split(' ')[1] ), 
                        float( text_from_file[4].split(' ')[1] ), 
                        float( text_from_file[5].split(' ')[1] ), 
                        float( text_from_file[6].split(' ')[1] ),
                        float( text_from_file[7].split(' ')[1] ),  
                        float( text_from_file[8].split(' ')[1] ), 
                        float( text_from_file[9].split(' ')[1] )
                        ]

                pb.awg_correction(only_pi_half = 'False', 
                    coef_array = coef, 
                    low_level = float( text_from_file[10].split(' ')[1] ),
                    limit = float( text_from_file[11].split(' ')[1] )
                    )
            
            pb.awg_amplitude('CH0', str(p18), 'CH1', str(p19) )

            # DETECTION pulse
            if int(float(p6[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=p6[0], start=p6[1], length=p6[2], phase_list=p6[3])

            #Laser flag
            if p40 != 1:
                pb.pulser_repetition_rate( str(p14) + ' Hz' )

                trigger_pulses = [p7, p8, p9, p10, p11, p12, p36, p37]
                awg_params = [p21, p22, p23, p24, p25, p26, p38, p39]

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
                            awg_kwargs.update({'n': p13, 'b': p32})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1]
                            )

            else:
                if p41 == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                    q_delay = p42
                elif p41 == 2:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )
                    q_delay = p42
                else:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )

                #p7 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER', 
                    start=p7[0], 
                    length=p7[1]
                )

                trigger_pulses = [p8, p9, p10, p11, p12, p36, p37]
                awg_params = [p22, p23, p24, p25, p26, p38, p39]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):

                    if int(float(tp[1].split(' ')[0])) != 0:
                        # add q_delay
                        start_val = float(tp[0].split(' ')[0]) + q_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_delay
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
                            awg_kwargs.update({'n': p13, 'b': p32})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1]
                            )                

            pb.pulser_default_synt(p34)

            
            POINTS = 1
            pb.digitizer_decimation(p1)
            DETECTION_WINDOW = round( pb.adc_window * 3.2, 1 )
            TR_ADC = round( 3.2 / 8, 1 )
            WIN_ADC = int( pb.adc_window * 8 / p1 )

            data = np.zeros( ( 2, WIN_ADC, 1 ) )
            ##data = np.random.random( ( 2, WIN_ADC, 1 ) )
            x_axis = np.linspace(0, ( DETECTION_WINDOW - TR_ADC), num = WIN_ADC)

            t_res = 0.4 * p1
            pb.digitizer_number_of_averages(p3)
            PHASES = len( p6[3] )
            
            #pb.pulser_visualize()
            pb.pulser_open()

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
                    num_ave = int( self.command[2:] )
                    #print( num_ave )
                    pb.digitizer_number_of_averages( num_ave )

                elif self.command[0:2] == 'WL':
                    p4 = int( self.command[2:] )
                elif self.command[0:2] == 'WR':
                    p5 = int( self.command[2:] )
                elif self.command[0:2] == 'RR':
                    p14 = float( self.command[2:] )
                    #print( p14 )
                    if p14 > 49:
                        pb.pulser_repetition_rate( str(p14) + ' Hz' )
                    else:
                        conn.send( ('Message', 'For REPETITION RATE lower then 50 Hz, please, press RUN PULSES') )

                elif self.command[0:2] == 'FI':
                    p15 = float( self.command[2:] )
                    bh15.magnet_field( p15 )#, calibration = 'True' )
                elif self.command[0:2] == 'FF':
                    p16 = int( self.command[2:] )
                elif self.command[0:2] == 'QC':
                    p27 = int( self.command[2:] )
                elif self.command[0:2] == 'ZO':
                    p28 = float( self.command[2:] )
                elif self.command[0:2] == 'FO':
                    p29 = float( self.command[2:] )
                elif self.command[0:2] == 'SO':
                    p30 = float( self.command[2:] )
                elif self.command[0:2] == 'PD':
                    p31 = int( self.command[2:] )
                elif self.command[0:2] == 'LM':
                    #p2 = int( self.command[2:] )
                    pass

                ###
                ###awg.phase_x = p17

                # check integration window
                if p4 > WIN_ADC:
                    p4 = WIN_ADC
                if p5 > WIN_ADC:
                    p5 = WIN_ADC

                # phase cycle
                PHASES = len( p6[3] )

                for i in range( PHASES ):

                    pb.awg_next_phase()
                    pb.pulser_update()
                    
                    if p2 == 0:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 1)
                    elif p2 == 1:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 0)
                    ##general.wait('100 ms')
                    ##data = np.random.random( ( 2, WIN_ADC, 1 ) )

                    data_x = data[0].ravel()
                    data_y = data[1].ravel()

                    if p16 == 0:                
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), 
                            xscale = 's', yscale = 'mV', label = 'ch', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9)
                            )

                    else:
                        # acquisition cycle
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), 
                            label = 'ch', xscale = 's', yscale = 'mV', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9) 
                            )

                        if p27 == 0:
                            freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1)
                            m_val = round( np.amax( abs_values ), 2 )
                            general.plot_1d('FFT', freq_axis * 1e6, abs_values, 
                                xname = 'Offset', label = 'FFT', xscale = 'Hz', 
                                yscale = 'A.U.', text = 'Max ' + str(m_val)
                                )
                        else:
                            if p31 > len( data_x ) - 0.4 * p1:
                                p31 = len( data_x ) - 0.8 * p1
                                general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                            # fixed resolution of digitizer; 2 ns
                            freq, fft_x, fft_y = fft.fft( x_axis[p31:], data_x[p31:], data_y[p31:], t_res * 1, re = 'True' )
                            data_fft = fft.ph_correction( freq * 1e6, fft_x, fft_y, p28, p29, p30 )
                            general.plot_1d('FFT', freq, ( data_fft[0], data_fft[1] ), 
                                xname = 'Offset', xscale = 'Hz', 
                                yscale = 'A.U.', label = 'FFT'
                                )

                self.command = 'start'
                if PHASES != 1:
                    pb.awg_pulse_reset()
                    pb.pulser_pulse_reset()
                else:
                    pass
                
                # poll() checks whether there is data in the Pipe to read
                # we use it to stop the script if the exit command was sent from the main window
                # we read data by conn.recv() only when there is the data to read
                if conn.poll() == True:
                    self.command = conn.recv()

            if self.command == 'exit':
                ##print('exit')
                pb.pulser_close()
                conn.send( ('', f'Pulses are stopped') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )            


    def dig_test(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22, p23, p24, p25, p26, p27, p28, p29, p30, p31, p32, p33, p34, p35, p36, p37, p38, p39, p40, p41, p42):
        """
        function that contains updating of the digitizer
        """
        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        #import time
        import traceback

        sys.argv = ['', 'test']

        try:
            import time
            import numpy as np
            import atomize.general_modules.general_functions as general
            general.test_flag = 'test'
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.math_modules.fft as fft_module
            import atomize.device_modules.BH_15 as itc

            pb = pb_pro.Insys_FPGA()
            fft = fft_module.Fast_Fourier()
            bh15 = itc.BH_15()
            #bh15.magnet_setup( p15, 0.5 )
            bh15.magnet_field( p15 ) #, calibration = 'True' )

            process = 'None'
            num_ave =  p3

            ###
            pb.phase_shift_ch1_seq_mode_awg = p17
            ###

            # correction from file
            if p33 == 0:
                pass
            elif p33 == 1:
                path_to_main = os.path.abspath( os.getcwd() )
                path_file = os.path.join(path_to_main, '../atomize/control_center/correction.param')
                file_to_read = open(path_file, 'r')

                text_from_file = file_to_read.read().split('\n')
                # ['BL: 5.92087', 'A1: 412.868', 'X1: -124.647', 'W1: 62.0069', 'A2: 420.717', 'X2: -35.8879', 
                # 'W2: 34.4214', A3: 9893.97', 'X3: 12.4056', 'W3: 150.304', 'LOW: 16', 'LIMIT: 23', '']

                coef = [float( text_from_file[0].split(' ')[1] ), 
                        float( text_from_file[1].split(' ')[1] ), 
                        float( text_from_file[2].split(' ')[1] ), 
                        float( text_from_file[3].split(' ')[1] ), 
                        float( text_from_file[4].split(' ')[1] ), 
                        float( text_from_file[5].split(' ')[1] ), 
                        float( text_from_file[6].split(' ')[1] ), 
                        float( text_from_file[7].split(' ')[1] ), 
                        float( text_from_file[8].split(' ')[1] ), 
                        float( text_from_file[9].split(' ')[1] )
                        ]

                pb.awg_correction(only_pi_half = 'True', 
                    coef_array = coef, 
                    low_level = float( text_from_file[10].split(' ')[1] ), 
                    limit = float( text_from_file[11].split(' ')[1] )
                    )

            elif p33 == 2:
                path_to_main = os.path.abspath( os.getcwd() )
                path_file = os.path.join(path_to_main, '../atomize/control_center/correction.param')
                file_to_read = open(path_file, 'r')

                text_from_file = file_to_read.read().split('\n')
                # ['BL: 5.92087', 'A1: 412.868', 'X1: -124.647', 'W1: 62.0069', 'A2: 420.717', 'X2: -35.8879', 
                # 'W2: 34.4214', A3: 9893.97', 'X3: 12.4056', 'W3: 150.304', 'LOW: 16', 'LIMIT: 23', '']
                
                coef = [float( text_from_file[0].split(' ')[1] ), 
                        float( text_from_file[1].split(' ')[1] ), 
                        float( text_from_file[2].split(' ')[1] ), 
                        float( text_from_file[3].split(' ')[1] ), 
                        float( text_from_file[4].split(' ')[1] ), 
                        float( text_from_file[5].split(' ')[1] ), 
                        float( text_from_file[6].split(' ')[1] ),
                        float( text_from_file[7].split(' ')[1] ),  
                        float( text_from_file[8].split(' ')[1] ), 
                        float( text_from_file[9].split(' ')[1] )
                        ]

                pb.awg_correction(only_pi_half = 'False', 
                    coef_array = coef, 
                    low_level = float( text_from_file[10].split(' ')[1] ),
                    limit = float( text_from_file[11].split(' ')[1] )
                    )
            
            pb.awg_amplitude('CH0', str(p18), 'CH1', str(p19) )

            # DETECTION pulse
            if int(float(p6[2].split(' ')[0])) != 0:
                pb.pulser_pulse(name='P1', channel=p6[0], start=p6[1], length=p6[2], phase_list=p6[3])

            #Laser flag
            if p40 != 1:
                pb.pulser_repetition_rate( str(p14) + ' Hz' )

                trigger_pulses = [p7, p8, p9, p10, p11, p12, p36, p37]
                awg_params = [p21, p22, p23, p24, p25, p26, p38, p39]

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
                            awg_kwargs.update({'n': p13, 'b': p32})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1]
                            )

            else:
                if p41 == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                    q_delay = p42
                elif p41 == 2:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )
                    q_delay = p42
                else:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )

                #p7 is LASER pulse
                pb.pulser_pulse(
                    name=f'L1',
                    channel='LASER', 
                    start=p7[0], 
                    length=p7[1]
                )

                trigger_pulses = [p8, p9, p10, p11, p12, p36, p37]
                awg_params = [p22, p23, p24, p25, p26, p38, p39]

                for i, (tp, ap) in enumerate(zip(trigger_pulses, awg_params)):

                    if int(float(tp[1].split(' ')[0])) != 0:
                        # add q_delay
                        start_val = float(tp[0].split(' ')[0]) + q_delay
                        tp[0] = f"{self.round_to_closest(start_val, 3.2)} ns"
                        start_val_awg = float(ap[5].split(' ')[0]) + q_delay
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
                            awg_kwargs.update({'n': p13, 'b': p32})
                            
                        pb.awg_pulse(**awg_kwargs)

                        if ap[0] != 'BLANK':
                            pb.pulser_pulse(
                                name=f'P{2*i + 3}',
                                channel='TRIGGER_AWG', 
                                start=tp[0], 
                                length=tp[1]
                            )                

            pb.pulser_default_synt(p34)
            
            POINTS = 1
            pb.digitizer_decimation(p1)
            DETECTION_WINDOW = round( pb.adc_window * 3.2, 1 )
            TR_ADC = round( 3.2 / 8, 1 )
            WIN_ADC = int( pb.adc_window * 8 / p1 )

            data = np.zeros( ( 2, WIN_ADC, 1 ) )
            ##data = np.random.random( ( 2, WIN_ADC, 1 ) )
            x_axis = np.linspace(0, ( DETECTION_WINDOW - TR_ADC), num = WIN_ADC)

            t_res = 0.4 * p1
            pb.digitizer_number_of_averages(p3)
            PHASES = len( p6[3] )
            
            #pb.pulser_visualize()
            pb.pulser_open()

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
                    num_ave = int( self.command[2:] )
                    #print( num_ave )
                    pb.digitizer_number_of_averages( num_ave )

                elif self.command[0:2] == 'WL':
                    p4 = int( self.command[2:] )
                elif self.command[0:2] == 'WR':
                    p5 = int( self.command[2:] )
                elif self.command[0:2] == 'RR':
                    p14 = float( self.command[2:] )
                    #print( p14 )
                    if p14 > 49:
                        pb.pulser_repetition_rate( str(p14) + ' Hz' )
                    else:
                        pass
                        #conn.send( ('Message', 'For REPETITION RATE lower then 50 Hz, please, press RUN PULSES') )

                elif self.command[0:2] == 'FI':
                    p15 = float( self.command[2:] )
                    bh15.magnet_field( p15 )#, calibration = 'True' )
                elif self.command[0:2] == 'FF':
                    p16 = int( self.command[2:] )
                elif self.command[0:2] == 'QC':
                    p27 = int( self.command[2:] )
                elif self.command[0:2] == 'ZO':
                    p28 = float( self.command[2:] )
                elif self.command[0:2] == 'FO':
                    p29 = float( self.command[2:] )
                elif self.command[0:2] == 'SO':
                    p30 = float( self.command[2:] )
                elif self.command[0:2] == 'PD':
                    p31 = int( self.command[2:] )
                elif self.command[0:2] == 'LM':
                    #p2 = int( self.command[2:] )
                    pass

                ###
                ###awg.phase_x = p17

                # check integration window
                if p4 > WIN_ADC:
                    p4 = WIN_ADC
                if p5 > WIN_ADC:
                    p5 = WIN_ADC

                # phase cycle
                PHASES = len( p6[3] )

                for i in range( PHASES ):

                    pb.awg_next_phase()
                    pb.pulser_update()
                    
                    if p2 == 0:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 1)
                    elif p2 == 1:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 0)
                    ##general.wait('100 ms')
                    ##data = np.random.random( ( 2, WIN_ADC, 1 ) )

                    data_x = data[0].ravel()
                    data_y = data[1].ravel()

                    if p16 == 0:                
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), 
                            xscale = 's', yscale = 'mV', label = 'ch', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9)
                            )

                    else:
                        # acquisition cycle
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), 
                            label = 'ch', xscale = 's', yscale = 'mV', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9) 
                            )

                        if p27 == 0:
                            freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1)
                            m_val = round( np.amax( abs_values ), 2 )
                            general.plot_1d('FFT', freq_axis * 1e6, abs_values, 
                                xname = 'Offset', label = 'FFT', xscale = 'Hz', 
                                yscale = 'A.U.', text = 'Max ' + str(m_val)
                                )
                        else:
                            if p31 > len( data_x ) - 0.4 * p1:
                                p31 = len( data_x ) - 0.8 * p1
                                general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                            # fixed resolution of digitizer; 2 ns
                            freq, fft_x, fft_y = fft.fft( x_axis[p31:], data_x[p31:], data_y[p31:], t_res * 1, re = 'True' )
                            data_fft = fft.ph_correction( freq * 1e6, fft_x, fft_y, p28, p29, p30 )
                            general.plot_1d('FFT', freq, ( data_fft[0], data_fft[1] ), 
                                xname = 'Offset', xscale = 'Hz', 
                                yscale = 'A.U.', label = 'FFT'
                                )

                if PHASES != 1:
                    pb.awg_pulse_reset()
                    pb.pulser_pulse_reset()
                else:
                    pass
                
                self.command = 'exit'

                # poll() checks whether there is data in the Pipe to read
                # we use it to stop the script if the exit command was sent from the main window
                # we read data by conn.recv() only when there is the data to read
                if conn.poll() == True:
                    self.command = conn.recv()

            if self.command == 'exit':
                ##print('exit')
                pb.pulser_close()
                conn.send( ('test', f'{pb.awg_pulse_list()}') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )            

    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return round(( y * ( ( x // y ) + (round(x % y, 2) > 0) ) ), 1)

def main():
    """
    A function to run the main window of the programm.
    """
    app = QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
