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
        
        # Phase correction
        self.deg_rad = 57.2957795131
        self.sec_order_coef = -2*np.pi/2

        self.design_tab_1()
        self.design_tab_2()
        self.design_tab_3()
        self.design_tab_4()

        self.laser_q_switch_delay = 0 #160000 # in ns

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

    def closeEvent(self, event):
        event.ignore()
        self.turn_off()

    def design_tab_1(self):
        self.setObjectName("MainWindow")
        self.setWindowTitle("RECT Channel Pulse Control")
        self.setStyleSheet("background-color: rgb(42,42,64);")

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_pulse.png')
        self.setWindowIcon( QIcon(icon_path) )
        self.path = os.path.join(path_to_main, '..', '..', '..', '..', 'experimental_data')

        self.setMinimumHeight(580)
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
        labels = [("Start", "label_1"), ("Length", "label_2"), ("Start Increment", "label_3"), ("Length Increment", "label_4"), ("Type", "label_5"), ("Phase", "label_6"), ("Repetition Rate", "label_7"), ("Magnetic Field", "label_8")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(130, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")


        # ---- Boxes ----
        pulses = [(QDoubleSpinBox, 0, 100e6, 0, 3.2, 1, " ns", "_st", "_start"),
                  (QDoubleSpinBox, 0, 1900, 0, 3.2, 1, " ns", "_len", "_length"),
                  (QDoubleSpinBox, 0, 1e6, 0, 3.2, 1, " ns", "_st_inc", "_st_increment"),
                  (QDoubleSpinBox, 0, 320, 0, 3.2, 1, " ns", "_len_inc", "_len_increment")
                 ]

        for j in range(1, 5):
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
                # parameter name pulse_set[8]
                spin_box.valueChanged.connect(
                        lambda val, idx = i, s7 = pulse_set[7], s8 = pulse_set[8]: 
                        self.update_pulse_param(idx, s7, s8)
                        )

                start_value = self.round_and_change(spin_box)
                setattr(self, f"p{i}{pulse_set[8]}", start_value)
                self.gridLayout.addWidget(spin_box, j + 2, i)

                if j == 1:
                    lbl = QLabel(f"{i}")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                    lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
                    self.gridLayout.addWidget(lbl, 0, i)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        self.gridLayout.addWidget(hline(), 1, 0, 1, 10)
        self.gridLayout.addWidget(hline(), 7, 0, 1, 10)

        # ---- Combo boxes----
        combo_boxes = [("DETECTION", "_type", "_type", "_typ", ["DETECTION"]),
                       ("MW", "_type", "_type", "_typ", ["LASER", "MW"]),
                       ("MW", "_type", "_type", "_typ", ["MW"])
                      ]

        label_widget = getattr(self, f"label_5")
        label_widget.setFixedSize(130, 26)
        self.gridLayout.addWidget(label_widget, 8, 0)

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

            self.gridLayout.addWidget(combo, 8, i)

        self.gridLayout.addWidget(hline(), 9, 0, 1, 10)

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

            self.gridLayout.addWidget(txt, 10, i)

        label_widget = getattr(self, f"label_6")
        label_widget.setFixedSize(130, 26)
        self.gridLayout.addWidget(label_widget, 10, 0)
        self.gridLayout.addWidget(hline(), 11, 0, 1, 10)


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

        label_widget = getattr(self, f"label_7")
        self.buttons_layout.addWidget(label_widget, 0, 0)
        label_widget.setFixedSize(130, 26)
        label_widget = getattr(self, f"label_8")
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
        labels = [("Laser Type", "label_0")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(130, 26)
            lbl.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")

        # ---- Combo box----
        combo_laser = ["Nd:YaG", "Combo_laser", "", self.combo_laser_fun, ["Nd:YaG", "NovoFEL"]]

        combo = QComboBox()
        setattr(self, combo_laser[1], combo)
        combo.currentIndexChanged.connect(combo_laser[3])
        combo.addItems(combo_laser[4])
        combo.setCurrentText(combo_laser[0])
        combo.setFixedSize(130, 26)
        combo.setStyleSheet("""
            QComboBox 
            { color : rgb(193, 202, 227); 
            selection-color: rgb(211, 194, 78); 
            selection-background-color: rgb(63, 63, 97);
            outline: none;
            }
            """)

        self.combo_laser_fun()

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        # ---- Layout placement ----
        gridLayout.addWidget(self.label_0, 0, 0)
        gridLayout.addWidget(self.Combo_laser, 0, 1)

        gridLayout.addWidget(hline(), 1, 0, 1, 2)

        gridLayout.setRowStretch(2, 1)
        gridLayout.setColumnStretch(2, 1)

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
        self.p_to_drop = int( self.P_to_drop.value() )

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
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "Pulse Phase List (*.phase)",\
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
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "Pulse Phase List (*.phase)",\
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

        try:
            self.P_to_drop.setValue( int( lines[14].split(':  ')[1] ) )
            self.Zero_order.setValue( float( lines[15].split(':  ')[1] ) )
            self.First_order.setValue( float( lines[16].split(':  ')[1] ) )
            self.Second_order.setValue( float( lines[17].split(':  ')[1] ) )
            self.Combo_laser.setCurrentText( str( lines[18].split(':  ')[1] ) )

        except IndexError:
            pass
        self.setter(text, 0, self.P1_type, self.P1_st, self.P1_len, self.Phase_1)
        self.setter(text, 1, self.P2_type, self.P2_st, self.P2_len, self.Phase_2)
        self.setter(text, 2, self.P3_type, self.P3_st, self.P3_len, self.Phase_3)
        self.setter(text, 3, self.P4_type, self.P4_st, self.P4_len, self.Phase_4)
        self.setter(text, 4, self.P5_type, self.P5_st, self.P5_len, self.Phase_5)
        self.setter(text, 5, self.P6_type, self.P6_st, self.P6_len, self.Phase_6)
        self.setter(text, 6, self.P7_type, self.P7_st, self.P7_len, self.Phase_7)
        self.Rep_rate.setValue( float( lines[7].split(':  ')[1] ) )
        self.Field.setValue( float( lines[8].split(':  ')[1] ) )

        #self.live_mode.setCheckState(Qt.CheckState.Unchecked)
        self.fft_box.setCheckState(Qt.CheckState.Unchecked)
        self.Quad_cor.setCheckState(Qt.CheckState.Unchecked)
        self.Win_left.setValue( round(float( lines[11].split(':  ')[1] ), 1) )
        self.Win_right.setValue( round(float( lines[12].split(':  ')[1] ), 1) )
        self.Acq_number.setValue( int( lines[13].split(':  ')[1] ) )
        self.Dec.setValue( int( lines[19].split(':  ')[1] ) )

        self.dig_stop()

        self.fft = 0
        self.quad = 0
        self.opened = 0

    def setter(self, text, index, typ, st, leng, phase):
        """
        Auxiliary function to set all the values from *.pulse file
        """
        array = text.split('\n')[index].split(':  ')[1].split(',  ')

        typ.setCurrentText( array[0] )
        st.setValue( float( array[1] ) )
        leng.setValue( float( array[2] ) )
        phase.setPlainText( str( (array[3])[1:-1] ) )

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        if filename[-5:] != 'phase':
            filename = filename + '.phase'
        with open(filename, 'w') as file:
            file.write( 'P1:  ' + self.P1_type.currentText() + ',  ' + str(self.P1_st.value()) + ',  ' + str(self.P1_len.value()) + ',  ' + str('[' + ','.join(self.ph_1) + ']') + '\n' )
            file.write( 'P2:  ' + self.P2_type.currentText() + ',  ' + str(self.P2_st.value()) + ',  ' + str(self.P2_len.value()) + ',  ' + str('[' + ','.join(self.ph_2) + ']') + '\n' )
            file.write( 'P3:  ' + self.P3_type.currentText() + ',  ' + str(self.P3_st.value()) + ',  ' + str(self.P3_len.value()) + ',  ' + str('[' + ','.join(self.ph_3) + ']') + '\n' )
            file.write( 'P4:  ' + self.P4_type.currentText() + ',  ' + str(self.P4_st.value()) + ',  ' + str(self.P4_len.value()) + ',  ' + str('[' + ','.join(self.ph_4) + ']') + '\n' )
            file.write( 'P5:  ' + self.P5_type.currentText() + ',  ' + str(self.P5_st.value()) + ',  ' + str(self.P5_len.value()) + ',  ' + str('[' + ','.join(self.ph_5) + ']') + '\n' )
            file.write( 'P6:  ' + self.P6_type.currentText() + ',  ' + str(self.P6_st.value()) + ',  ' + str(self.P6_len.value()) + ',  ' + str('[' + ','.join(self.ph_6) + ']') + '\n' )
            file.write( 'P7:  ' + self.P7_type.currentText() + ',  ' + str(self.P7_st.value()) + ',  ' + str(self.P7_len.value()) + ',  ' + str('[' + ','.join(self.ph_7) + ']') + '\n' )
            file.write( 'Rep rate:  ' + str(self.Rep_rate.value()) + '\n' )
            file.write( 'Field:  ' + str(self.Field.value()) + '\n' )
            file.write( 'Points:  ' + str(2016) + '\n' )
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

    def phase_converted(self, ph_str):
        if ph_str == '+x':
            return '+x'
        elif ph_str == '-x':
            return '-x'
        elif ph_str == '+y':
            return '+y'
        elif ph_str == '-y':
            return '-y'

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

    def remove_ns(self, string1):
        return string1.split(' ')[0]

    def add_ns(self, string1):
        """
        Function to add ' ns'
        """
        return str( string1 ) + ' ns'

    def check_length(self, length):
        self.errors.clear()

        if int( length ) != 0 and int( length ) < 12:
            self.errors.appendPlainText( 'Pulse should be longer than 12 ns' )

        return length

    def closeEvent(self, event):
        """
        A function to do some actions when the main window is closing.
        """
        event.ignore()
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
        return self.add_ns( doubleBox.value() )

    def decimat(self):
        """
        A function to set decimation coefficient
        """
        self.decimation = self.Dec.value()
        self.time_per_point = 0.4 * self.decimation

    def update_pulse_param(self, index, attr_suffix, val_suffix):
        spin_widget = getattr(self, f"P{index}{attr_suffix}")
        new_value = self.round_and_change(spin_widget)
        setattr(self, f"p{index}{val_suffix}", new_value)
        #print(f"Updated: p{index}{val_suffix} = {new_value}")

    def update_pulse_type(self, index):

        combo = getattr(self, f"P{index}_type")
        text = combo.currentText()
        
        setattr(self, f"p{index}_typ", text)
        
        if index == 2:
            self.laser_flag = 1 if text == 'LASER' else 0
            
        #print(f"Pulse {index} type set to: {text}")

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
        #path_file = os.path.join(path_to_main, 'digitizer_insys.param')

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

        file_to_read.write('Window Left: ' + str( int(self.cur_win_left) ) +'\n') #/ self.time_per_point
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
        worker = Worker()

        for i in range(1, 10):
            data = [
                getattr(self, f'p{i}_typ'),
                getattr(self, f'p{i}_start'),
                getattr(self, f'p{i}_length'),
                getattr(self, f'ph_{i}'),
                getattr(self, f'p{i}_st_increment'),
                getattr(self, f'p{i}_len_increment')
            ]
            setattr(self, f'p{i}_exp', data)

    def dig_start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """
        worker = Worker()

        for i in range(1, 10):
            data = [
                getattr(self, f'p{i}_typ'),
                getattr(self, f'p{i}_start'),
                getattr(self, f'p{i}_length'),
                getattr(self, f'ph_{i}')
            ]
            setattr(self, f'p{i}_list', data)

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
            self.decimation, self.l_mode, self.number_averages, self.cur_win_left, 
            self.cur_win_right, self.p1_list, self.p2_list, self.p3_list, self.p4_list, 
            self.p5_list, self.p6_list, self.p7_list, self.laser_flag, 
            self.repetition_rate.split(' ')[0], 
            self.mag_field, self.fft, self.quad, self.zero_order, self.first_order, 
            self.second_order, self.p_to_drop, self.combo_laser_num, self.laser_q_switch_delay, 
            self.p8_list, self.p9_list ) )

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(193, 202, 227); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")

        #self.progress_bar.setValue(0)

        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')
        
        self.is_testing = True
        self.timer.start(100)

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

        time.sleep(0.1)

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
            self.decimation, self.l_mode, self.number_averages, self.cur_win_left, 
            self.cur_win_right, self.p1_list, self.p2_list, self.p3_list, self.p4_list, 
            self.p5_list, self.p6_list, self.p7_list, self.laser_flag, 
            self.repetition_rate.split(' ')[0], 
            self.mag_field, self.fft, self.quad, self.zero_order, self.first_order, 
            self.second_order, self.p_to_drop, self.combo_laser_num, self.laser_q_switch_delay,
            self.p8_list, self.p9_list ) )

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ") 

        self.digitizer_process.start()
        self.parent_conn_dig.send('start')
        self.timer.start(100)

# The worker class that run the digitizer in a different thread
class Worker():
    def __init__(self):
        super(Worker, self).__init__()
        # initialization of the attribute we use to stop the experimental script
        # when button Stop is pressed
        #from atomize.main.client import LivePlotClient

        self.command = 'start'
    
    def dig_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22, p23, p24, p25):
        """
        function that contains updating of the digitizer
        """
        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
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
            bh15.magnet_field( p15 ) #, calibration = 'True'

            process = 'None'
            
            # p1 decimation
            # p2 LIVE MODE

            #parameters for initial initialization

            #p4 window left
            #p5 window right
            
            if p13 != 1:
                pb.pulser_repetition_rate( str(p14) + ' Hz' )
                pulses = [p6, p7, p8, p9, p10, p11, p12, p24, p25]

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if int(float(length_str)) != 0:
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3]
                        )

            else:
                if p22 == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                    q_delay = p23
                elif p22 == 2:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )
                    q_delay = p23
                else:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )

                pulses = [p6, p7, p8, p9, p10, p11, p12, p24, p25]

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2]
                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            POINTS = 1
            pb.digitizer_decimation(p1)
            DETECTION_WINDOW = round( pb.adc_window * 3.2, 1 )
            TR_ADC = round(3.2 / 8, 1)
            WIN_ADC = int( pb.adc_window * 8 / p1 )

            data = np.zeros( ( 2, WIN_ADC, 1 ) )
            ##data = np.random.random( ( 2, WIN_ADC, 1 ) )
            x_axis = np.linspace(0, ( DETECTION_WINDOW - TR_ADC), num = WIN_ADC) 

            t_res = 0.4 * p1
            pb.digitizer_number_of_averages(p3)
            PHASES = len( p6[3] )
            
            pb.pulser_open()
            
            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the digitizer
            while self.command != 'exit':
                # always test our self.command attribute for stopping the script when neccessary

                if self.command[0:2] == 'PO':            
                    #points_value = int( self.command[2:] )
                    #dig.digitizer_stop()
                    #dig.digitizer_number_of_points( points_value )
                    pass

                elif self.command[0:2] == 'HO':
                    #posstrigger_value = int( self.command[2:] )
                    #dig.digitizer_stop()
                    #dig.digitizer_posttrigger( posstrigger_value )
                    pass

                elif self.command[0:2] == 'LM':
                    pass
                    #p2 = int( self.command[2:] )

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
                    bh15.magnet_field( p15 ) #, calibration = 'True'
                elif self.command[0:2] == 'FF':
                    p16 = int( self.command[2:] )
                elif self.command[0:2] == 'QC':
                    p17 = int( self.command[2:] )
                elif self.command[0:2] == 'ZO':
                    p18 = float( self.command[2:] )
                elif self.command[0:2] == 'FO':
                    p19 = float( self.command[2:] )
                elif self.command[0:2] == 'SO':
                    p20 = float( self.command[2:] )
                elif self.command[0:2] == 'PD':
                    p21 = int( self.command[2:] )

                # check integration window
                if p4 > WIN_ADC:
                    p4 = WIN_ADC
                if p5 > WIN_ADC:
                    p5 = WIN_ADC

                # phase cycle
                PHASES = len( p6[3] )

                #pb.pulser_visualize()

                for i in range( PHASES ):
                    pb.pulser_next_phase()
                    if p2 == 0:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 1)
                    elif p2 == 1:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 0)
                    ##general.wait('100 ms')
                    ##data = np.random.random( ( 2, WIN_ADC, 1 ) )

                    data_x = data[0].ravel()
                    data_y = data[1].ravel()

                    if p16 == 0:
                        # acquisition cycle
                        int_x = round( np.sum( data_x[p4:p5] ) * 1 * t_res , 1 ) #( 10**(10) * t_res )
                        int_y = round( np.sum( data_y[p4:p5] ) * 1 * t_res , 1 )

                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), 
                            xscale = 's', yscale = 'mV', label = 'ch', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9), 
                            text = 'I/Q ' + str(int_x) + '/' + str(int_y)
                            )

                    else:
                        # acquisition cycle
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), xscale = 's', 
                            yscale = 'mV', label = 'ch', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9)
                            )

                        if p17 == 0:
                            freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1)
                            m_val = round( np.amax( abs_values ), 2 )
                            i_max = abs(round( freq_axis[ np.argmax( abs_values ) ], 2))
                            general.plot_1d('FFT', freq_axis * 1e6, abs_values, xname = 'Offset', 
                                label = 'FFT', xscale = 'Hz', 
                                yscale = 'A.U.', text = 'Max ' + str(m_val)
                                ) #str(m_val)
                        else:
                            if p21 > len( data_x ) - 0.4 * p1:
                                p21 = len( data_x ) - 0.8 * p1
                                general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                            # fixed resolution of digitizer; 0.4 ns
                            freq, fft_x, fft_y = fft.fft( x_axis[p21:] , data_x[p21:], data_y[p21:], t_res * 1, re = 'True' )
                            data_fft = fft.ph_correction( freq * 1e6, fft_x, fft_y, p18, p19, p20 )
                            general.plot_1d('FFT', freq, ( data_fft[0], data_fft[1] ), 
                                xname = 'Offset', xscale = 'Hz', 
                                yscale = 'A.U.', label = 'FFT'
                                )

                self.command = 'start'
                
                if PHASES != 1:
                    pb.pulser_pulse_reset()
                else:
                    pass
                
                # poll() checks whether there is data in the Pipe to read
                # we use it to stop the script if the exit command was sent from the main window
                # we read data by conn.recv() only when there is the data to read
                if conn.poll() == True:
                    self.command = conn.recv()

            if self.command == 'exit':
                #print('exit')
                pb.pulser_close()
                conn.send( ('', f'Pulses are stopped') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def dig_test(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, p21, p22, p23, p24, p25):
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
            bh15.magnet_field( p15 ) #, calibration = 'True'

            process = 'None'
            
            # p1 decimation
            # p2 LIVE MODE

            #parameters for initial initialization

            #p4 window left
            #p5 window right
            
            if p13 != 1:
                pb.pulser_repetition_rate( str(p14) + ' Hz' )
                pulses = [p6, p7, p8, p9, p10, p11, p12, p24, p25]

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if int(float(length_str)) != 0:
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3]
                        )

            else:
                if p22 == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                    q_delay = p23
                elif p22 == 2:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )
                    q_delay = p23
                else:
                    pb.pulser_repetition_rate( str(p14) + ' Hz' )

                pulses = [p6, p7, p8, p9, p10, p11, p12, p24, p25]

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2]
                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            POINTS = 1
            pb.digitizer_decimation(p1)
            DETECTION_WINDOW = round( pb.adc_window * 3.2, 1 )
            TR_ADC = round(3.2 / 8, 1)
            WIN_ADC = int( pb.adc_window * 8 / p1 )

            data = np.zeros( ( 2, WIN_ADC, 1 ) )
            ##data = np.random.random( ( 2, WIN_ADC, 1 ) )
            x_axis = np.linspace(0, ( DETECTION_WINDOW - TR_ADC), num = WIN_ADC) 

            t_res = 0.4 * p1
            pb.digitizer_number_of_averages(p3)
            PHASES = len( p6[3] )
            
            pb.pulser_open()
            
            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the digitizer
            while self.command != 'exit':
                # always test our self.command attribute for stopping the script when neccessary

                if self.command[0:2] == 'PO':            
                    #points_value = int( self.command[2:] )
                    #dig.digitizer_stop()
                    #dig.digitizer_number_of_points( points_value )
                    pass

                elif self.command[0:2] == 'HO':
                    #posstrigger_value = int( self.command[2:] )
                    #dig.digitizer_stop()
                    #dig.digitizer_posttrigger( posstrigger_value )
                    pass

                elif self.command[0:2] == 'LM':
                    pass
                    #p2 = int( self.command[2:] )

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
                    bh15.magnet_field( p15 ) #, calibration = 'True'
                elif self.command[0:2] == 'FF':
                    p16 = int( self.command[2:] )
                elif self.command[0:2] == 'QC':
                    p17 = int( self.command[2:] )
                elif self.command[0:2] == 'ZO':
                    p18 = float( self.command[2:] )
                elif self.command[0:2] == 'FO':
                    p19 = float( self.command[2:] )
                elif self.command[0:2] == 'SO':
                    p20 = float( self.command[2:] )
                elif self.command[0:2] == 'PD':
                    p21 = int( self.command[2:] )

                # check integration window
                if p4 > WIN_ADC:
                    p4 = WIN_ADC
                if p5 > WIN_ADC:
                    p5 = WIN_ADC

                # phase cycle
                PHASES = len( p6[3] )

                #pb.pulser_visualize()

                for i in range( PHASES ):
                    pb.pulser_next_phase()
                    if p2 == 0:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 1)
                    elif p2 == 1:
                        data[0], data[1] = pb.digitizer_get_curve(POINTS, PHASES, live_mode = 0)
                    ##general.wait('100 ms')
                    ##data = np.random.random( ( 2, WIN_ADC, 1 ) )

                    data_x = data[0].ravel()
                    data_y = data[1].ravel()

                    if p16 == 0:
                        # acquisition cycle
                        int_x = round( np.sum( data_x[p4:p5] ) * 1 * t_res , 1 ) #( 10**(10) * t_res )
                        int_y = round( np.sum( data_y[p4:p5] ) * 1 * t_res , 1 )

                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), 
                            xscale = 's', yscale = 'mV', label = 'ch', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9), 
                            text = 'I/Q ' + str(int_x) + '/' + str(int_y)
                            )

                    else:
                        # acquisition cycle
                        general.plot_1d('Dig', x_axis / 1e9, ( data_x, data_y ), xscale = 's', 
                            yscale = 'mV', label = 'ch', 
                            vline = (p4 * t_res / 1e9, p5 * t_res / 1e9)
                            )

                        if p17 == 0:
                            freq_axis, abs_values = fft.fft(x_axis, data_x, data_y, t_res * 1)
                            m_val = round( np.amax( abs_values ), 2 )
                            i_max = abs(round( freq_axis[ np.argmax( abs_values ) ], 2))
                            general.plot_1d('FFT', freq_axis * 1e6, abs_values, xname = 'Offset', 
                                label = 'FFT', xscale = 'Hz', 
                                yscale = 'A.U.', text = 'Max ' + str(m_val))
                                 #str(m_val)
                        else:
                            if p21 > len( data_x ) - 0.4 * p1:
                                p21 = len( data_x ) - 0.8 * p1
                                general.message('Maximum length of the data achieved. A number of drop points was corrected.')
                            # fixed resolution of digitizer; 0.4 ns
                            freq, fft_x, fft_y = fft.fft( x_axis[p21:] , data_x[p21:], data_y[p21:], t_res * 1, re = 'True' )
                            data_fft = fft.ph_correction( freq * 1e6, fft_x, fft_y, p18, p19, p20 )
                            general.plot_1d('FFT', freq, ( data_fft[0], data_fft[1] ), 
                                xname = 'Offset', xscale = 'Hz', 
                                yscale = 'A.U.', label = 'FFT'
                                )

                if PHASES != 1:
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
                #print('exit')
                pb.pulser_close()
                #pb.pulser_pulse_list()
                conn.send( ('test', f'{pb.pulser_pulse_list()}') )

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
