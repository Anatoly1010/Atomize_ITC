#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import traceback
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QTextEdit, QGridLayout, QFrame, QCheckBox, QFileDialog, QVBoxLayout, QTabWidget, QScrollArea, QHBoxLayout, QPlainTextEdit, QProgressBar,  QTreeView, QHeaderView, QSizeGrip, QLineEdit, QFileIconProvider
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
        try:
            path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', 'libs')
            os.chdir(path_to_main2) 
        except FileNotFoundError:
            path_to_main2 = os.path.join(os.path.abspath(os.getcwd()), '..', '..', 'libs')
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

        self.is_experiment = False
        self.exit_clicked = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_messages)
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_process_status)
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
            QTabWidget::pane {
                border: 1px solid rgb(43, 43, 77); 
                top: -1px; 
                background: rgb(63, 63, 97);
            }
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
        labels = [("Start", "label_1"), ("Length", "label_2"), ("Start Increment", "label_3"), ("Length Increment", "label_4"), ("Type", "label_5"), ("Phase", "label_6"), ("Repetition Rate", "label_7"), ("Magnetic Field", "label_8"), ("Progress", "label_p1")]

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


        #---- Progress Bar ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedSize(130, 15)
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

        label_widget = getattr(self, f"label_p1")
        self.buttons_layout.addWidget(label_widget, 0, 2)
        self.buttons_layout.addWidget(self.progress_bar, 0, 3)

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
        labels = [("Acquisitions", "label_17"), ("Integration Left", "label_18"), ("Integration Right", "label_19"), ("Decimation", "label_20"), ("Points", "label_e1"), ("Scans", "label_e2"), ("Experiment Name", "label_e3"), ("Curve Name", "label_e4"), ("Start Field", "label_f1"), ("End Field", "label_f2"), ("Field Step", "label_f3"), ("Sweep Type", "label_c1"), ("Log[Start Time]", "label_e5"), ("Log[End Time]", "label_e6")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            setattr(self, attr_name, lbl)
            lbl.setFixedSize(130, 26)
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
                      (QDoubleSpinBox, "Log_start", "cur_log_start", self.log_start, 0, 10, 1, 0.01, 3, ""),
                      (QDoubleSpinBox, "Log_end", "cur_log_end", self.log_end, 0, 10, 7, 0.01, 3, "")
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

        # ---- Text Edits ----
        text_edit = [("EXP", "text_edit_exp_name", "cur_exp_name", self.exp_name),
                     ("c1", "text_edit_curve", "cur_curve_name", self.curve_name)
                    ]

        for text, attr_name, par_name, func in text_edit:
            txt = QTextEdit(text)
            setattr(self, attr_name, txt)
            setattr(self, par_name, txt.toPlainText())
            txt.textChanged.connect(func)
            txt.setFixedSize(130, 26)
            txt.setAcceptRichText(False)
            txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setStyleSheet("QTextEdit { color : rgb(211, 194, 78) ; selection-background-color: rgb(211, 194, 78); selection-color: rgb(63, 63, 97);}")

        # ---- Combo boxes----
        combo_boxes = [("Linear Time", "combo_sweep", "cur_sweep", self.sweep_type, 
                        [
                        "Linear Time", "Field", "Log Time"
                        ])
                      ]

        for cur_text, attr_name, par_name, func, item in combo_boxes:
            combo = QComboBox()
            setattr(self, attr_name, combo)
            setattr(self, par_name, combo.currentText())
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

        left_grid.addWidget(self.label_e5, 5, 0)
        left_grid.addWidget(self.Log_start, 5, 1)
        left_grid.addWidget(self.label_e6, 6, 0)
        left_grid.addWidget(self.Log_end, 6, 1)

        left_grid.addWidget(hline(), 7, 0, 1, 2)

        left_grid.addWidget(self.label_e3, 8, 0)
        left_grid.addWidget(self.text_edit_exp_name, 8, 1)
        left_grid.addWidget(self.label_e4, 9, 0)
        left_grid.addWidget(self.text_edit_curve, 9, 1)

        left_grid.addWidget(hline(), 10, 0, 1, 2)

        left_grid.setRowStretch(11, 1)
        left_grid.setColumnStretch(11, 1)

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
        third_grid.setRowStretch(4, 1)
        third_grid.setColumnStretch(4, 1)

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

    def sweep_type(self):
        self.cur_sweep = self.combo_sweep.currentText()
        #Linear Time; Field; Log Time

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
        filedialog = QFileDialog(self, 'Open File', directory = self.path, filter = "Pulse Phase List (*.phase)", options = QFileDialog.Option.DontUseNativeDialog)
        
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
        filedialog = QFileDialog(self, 'Save File', directory = self.path, filter = "Pulse Phase List (*.phase)", options = QFileDialog.Option.DontUseNativeDialog)
        filedialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

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
        self.opened = 1
        text = open(filename).read()
        lines = text.split('\n')

        try:
            self.P_to_drop.setValue( int( lines[16].split(':  ')[1] ) )
            self.Zero_order.setValue( float( lines[17].split(':  ')[1] ) )
            self.First_order.setValue( float( lines[18].split(':  ')[1] ) )
            self.Second_order.setValue( float( lines[19].split(':  ')[1] ) )
            self.Combo_laser.setCurrentText( str( lines[20].split(':  ')[1] ) )

        except IndexError:
            pass
        self.setter(text, 0, self.P1_type, self.P1_st, self.P1_len, self.Phase_1, self.P1_st_inc, self.P1_len_inc)
        self.setter(text, 1, self.P2_type, self.P2_st, self.P2_len, self.Phase_2, self.P2_st_inc, self.P2_len_inc)
        self.setter(text, 2, self.P3_type, self.P3_st, self.P3_len, self.Phase_3, self.P3_st_inc, self.P3_len_inc)
        self.setter(text, 3, self.P4_type, self.P4_st, self.P4_len, self.Phase_4, self.P4_st_inc, self.P4_len_inc)
        self.setter(text, 4, self.P5_type, self.P5_st, self.P5_len, self.Phase_5, self.P5_st_inc, self.P5_len_inc)
        self.setter(text, 5, self.P6_type, self.P6_st, self.P6_len, self.Phase_6, self.P6_st_inc, self.P6_len_inc)
        self.setter(text, 6, self.P7_type, self.P7_st, self.P7_len, self.Phase_7, self.P7_st_inc, self.P7_len_inc)
        self.setter(text, 7, self.P8_type, self.P8_st, self.P8_len, self.Phase_8, self.P8_st_inc, self.P8_len_inc)
        self.setter(text, 8, self.P9_type, self.P9_st, self.P9_len, self.Phase_9, self.P9_st_inc, self.P9_len_inc)

        self.Rep_rate.setValue( float( lines[9].split(':  ')[1] ) )
        self.Field.setValue( float( lines[10].split(':  ')[1] ) )

        #self.live_mode.setCheckState(Qt.CheckState.Unchecked)
        self.fft_box.setCheckState(Qt.CheckState.Unchecked)
        self.Quad_cor.setCheckState(Qt.CheckState.Unchecked)
        self.Win_left.setValue( round(float( lines[13].split(':  ')[1] ), 1) )
        self.Win_right.setValue( round(float( lines[14].split(':  ')[1] ), 1) )
        self.Acq_number.setValue( int( lines[15].split(':  ')[1] ) )
        self.Dec.setValue( int( lines[21].split(':  ')[1] ) )

        self.box_points.setValue( int( lines[22].split(':  ')[1] ) )
        self.box_scan.setValue( int( lines[23].split(':  ')[1] ) )
        self.Log_start.setValue( float( lines[24].split(':  ')[1] ) )
        self.Log_end.setValue( float( lines[25].split(':  ')[1] ) )
        self.box_st_field.setValue( float( lines[26].split(':  ')[1] ) )
        self.box_end_field.setValue( float( lines[27].split(':  ')[1] ) )
        self.box_step_field.setValue( float( lines[28].split(':  ')[1] ) )
        self.combo_sweep.setCurrentText( str( lines[29].split(':  ')[1] ) )

        self.dig_stop()

        self.fft = 0
        self.quad = 0
        self.opened = 0

    def setter(self, text, index, typ, st, leng, phase, d_start, len_inc):
        """
        Auxiliary function to set all the values from *.pulse file
        """
        array = text.split('\n')[index].split(':  ')[1].split(',  ')

        typ.setCurrentText( array[0] )
        st.setValue( float( array[1] ) )
        leng.setValue( float( array[2] ) )
        phase.setPlainText( str( (array[3])[1:-1] ) )
        d_start.setValue( float( array[4] ) )
        len_inc.setValue( float( array[5] ) )

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        if filename[-5:] != 'phase':
            filename = filename + '.phase'
        with open(filename, 'w') as file:
            for i in range(1, 10):

                p_type = getattr(self, f'P{i}_type').currentText()
                p_st = getattr(self, f'P{i}_st').value()
                p_len = getattr(self, f'P{i}_len').value()
                ph_list = getattr(self, f'ph_{i}')
                d_start = getattr(self, f'P{i}_st_inc').value()
                len_inc = getattr(self, f'P{i}_len_inc').value()
                
                ph_str = f"[{','.join(ph_list)}]"
                file.write(f"P{i}:  {p_type},  {p_st},  {p_len},  {ph_str},  {d_start},  {len_inc}\n")

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

            file.write( 'Points:  ' + str( self.box_points.value() ) + '\n' )
            file.write( 'Scans:  ' + str( self.box_scan.value() ) + '\n' )
            file.write( 'Log Start:  ' + str( self.Log_start.value() ) + '\n' )
            file.write( 'Log End:  ' + str( self.Log_end.value() ) + '\n' )
            file.write( 'Start Field:  ' + str( self.box_st_field.value() ) + '\n' )
            file.write( 'End Field:  ' + str( self.box_end_field.value() ) + '\n' )
            file.write( 'Field Step:  ' + str( self.box_step_field.value() ) + '\n' )
            file.write( 'Sweep Type:  ' + self.combo_sweep.currentText() + '\n' )

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
            self.digitizer_process = Process( target = worker.exp_test, args = ( 
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_win_left, self.cur_exp_name, self.cur_curve_name,
                self.cur_win_right, self.p1_exp, self.p2_exp, self.p3_exp, self.p4_exp, 
                self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp, self.laser_flag, 
                self.repetition_rate.split(' ')[0], 
                self.mag_field, self.combo_laser_num, self.laser_q_switch_delay
                ) 
            )
        elif self.cur_sweep == 'Field':
            self.digitizer_process = Process( target = worker.exp_field_test, args = ( 
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_start_field,
                self.cur_end_field, self.cur_step,
                self.cur_win_left, self.cur_exp_name, self.cur_curve_name,
                self.cur_win_right, self.p1_exp, self.p2_exp, self.p3_exp, self.p4_exp, 
                self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp, self.laser_flag, 
                self.repetition_rate.split(' ')[0], 
                self.combo_laser_num, self.laser_q_switch_delay
                ) 
            )
        elif self.cur_sweep == 'Log Time':
            self.digitizer_process = Process( target = worker.exp_log_test, args = ( 
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_log_start, self.cur_log_end,
                self.cur_win_left, self.cur_exp_name, self.cur_curve_name,
                self.cur_win_right, self.p1_exp, self.p2_exp, self.p3_exp, self.p4_exp, 
                self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp, self.laser_flag, 
                self.repetition_rate.split(' ')[0], self.mag_field,
                self.combo_laser_num, self.laser_q_switch_delay
                ) 
            )

        self.button_start_exp.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(193, 202, 227); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        self.digitizer_process.start()
        # send a command in a different thread about the current state
        self.parent_conn_dig.send('start')
        
        self.is_testing = True
        self.is_experiment = True
        self.timer.start(200)

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

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(193, 202, 227); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

        #self.progress_bar.setValue(0)

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
                    time.sleep(0.2)
                    if self.is_experiment == False:
                        self.run_main_experiment()
                    else:
                        self.run_experiment()
                else:
                    self.last_error = False

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

        if self.exit_clicked == 1:
            sys.exit()

    def open_dialog(self):
        file_data = self.file_handler.create_file_dialog(multiprocessing = True)        

        if file_data:
            self.parent_conn_dig.send( 'FL' + str( file_data ) )
        else:
            self.parent_conn_dig.send( 'FL' + '' )

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

        self.button_update.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }") 

        self.digitizer_process.start()
        self.parent_conn_dig.send('start')
        self.timer.start(200)

    def run_experiment(self):

        worker = Worker()
        self.parent_conn_dig, self.child_conn_dig = Pipe()
        
        if self.cur_sweep == 'Linear Time':
            self.digitizer_process = Process( target = worker.exp, args = ( 
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_win_left, self.cur_exp_name, self.cur_curve_name,
                self.cur_win_right, self.p1_exp, self.p2_exp, self.p3_exp, self.p4_exp, 
                self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp, self.laser_flag, 
                self.repetition_rate.split(' ')[0], 
                self.mag_field, self.combo_laser_num, self.laser_q_switch_delay
                ) 
            )
        elif self.cur_sweep == 'Field':
            self.digitizer_process = Process( target = worker.exp_field, args = ( 
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_start_field,
                self.cur_end_field, self.cur_step,
                self.cur_win_left, self.cur_exp_name, self.cur_curve_name,
                self.cur_win_right, self.p1_exp, self.p2_exp, self.p3_exp, self.p4_exp, 
                self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp, self.laser_flag, 
                self.repetition_rate.split(' ')[0], 
                self.combo_laser_num, self.laser_q_switch_delay
                ) 
            )
        elif self.cur_sweep == 'Log Time':
            self.digitizer_process = Process( target = worker.exp_log, args = ( 
                self.child_conn_dig,
                self.decimation, self.number_averages, self.cur_scan, self.cur_points,
                self.cur_log_start, self.cur_log_end,
                self.cur_win_left, self.cur_exp_name, self.cur_curve_name,
                self.cur_win_right, self.p1_exp, self.p2_exp, self.p3_exp, self.p4_exp, 
                self.p5_exp, self.p6_exp, self.p7_exp, self.p8_exp, self.p9_exp, self.laser_flag, 
                self.repetition_rate.split(' ')[0], self.mag_field,
                self.combo_laser_num, self.laser_q_switch_delay
                ) 
            )

        self.button_start_exp.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }") 

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
                    if i == 1 and length_val == 0:
                        raise ValueError(f"LASER pulse has zero length")

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
                conn.close()

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def round_to_closest(self, x, y):
        """
        A function to round x to divisible by y
        """
        return round(( y * ( ( x // y ) + (round(x % y, 2) > 0) ) ), 1)

    def exp(self, conn, decimation, num_ave, scans, points,
            win_left, exp_name, curve_name,
            win_right, p1_exp, p2_exp, p3_exp, p4_exp, 
            p5_exp, p6_exp, p7_exp, p8_exp, p9_exp, laser_flag, 
            rep_rate, field, laser_num, q_switch_delay):
        
        import traceback

        try:
            #import random
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.Insys_FPGA as pb_pro
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.BH_15 as bh
            import atomize.device_modules.Micran_X_band_MW_bridge_v2 as mwBridge
            import atomize.general_modules.csv_opener_saver as openfile

            pb = pb_pro.Insys_FPGA()
            file_handler = openfile.Saver_Opener()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            pb.win_left = win_left
            pb.win_right = win_right

            #p1_exp DETECTION
            if p1_exp[4] != '0.0 ns':
                #delta_start
                step = round( float( p1_exp[4].split(' ')[0] ), 1)
            elif p1_exp[5] != '0.0 ns':
                #length_increment
                step = round( float( p1_exp[5].split(' ')[0] ), 1)
            else:
                #prevent no increment
                step = 1
                conn.send( ('Message', 'No START or LENGTH increment; the time axis corresponds to the number of points in the experiment') )
            
            general.plot_remove(exp_name)

            POINTS = points
            STEP = step
            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(p1_exp[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            EXP_NAME = exp_name
            CURVE_NAME = curve_name

            bh15.magnet_field( field )
            general.wait('2000 ms')

            if laser_flag != 1:
                pb.pulser_repetition_rate( REP_RATE )
                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if int(float(length_str)) != 0:
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3],
                            delta_start=p[4],
                            length_increment=p[5]
                        )

            else:
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                elif laser_num == 2:
                    pb.pulser_repetition_rate( REP_RATE )
                else:
                    pb.pulser_repetition_rate( REP_RATE )

                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_switch_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2],
                            'delta_start': p[4],
                            'length_increment': p[5]

                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            pb.digitizer_decimation(DEC_COEF)
            #points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)
            data = np.zeros( ( 2, POINTS ) )
            x_axis = np.linspace(0, (POINTS - 1)*STEP, num = POINTS) 

            while self.command != 'exit':

                k = 1
                while k <= SCANS:

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        for i in range(PHASES):
                            #r_data = np.random.random( 2 )
                            #data[0, j] = r_data[0]
                            #data[1, j] = r_data[1]
                            
                            pb.pulser_next_phase()

                            if step != 1:
                                general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                            else:
                                general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))

                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        pb.pulser_shift()
                        pb.pulser_increment()

                        conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit(integral = True)
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()
                    k += 1

                self.command = 'exit'

            if self.command == 'exit':
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if step != 1:
                    general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                else:
                    general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30
                
                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
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
                    f"Time (ns), I (A.U.), Q (A.U.)"
                )

                conn.send(('Open', ''))
                
                while True:
                    if conn.poll():
                        msg = conn.recv()
                        if msg.startswith('FL'):
                            file_data = msg[2:]
                            break
                    general.wait('200 ms')


                file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('', f'Experiment {exp_name} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
    
    def exp_test(self, conn, decimation, num_ave, scans, points,
            win_left, exp_name, curve_name,
            win_right, p1_exp, p2_exp, p3_exp, p4_exp, 
            p5_exp, p6_exp, p7_exp, p8_exp, p9_exp, laser_flag, 
            rep_rate, field, laser_num, q_switch_delay):
        
        import traceback

        sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            general.test_flag = 'test'
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

            pb.win_left = win_left
            pb.win_right = win_right

            #p1_exp DETECTION
            if p1_exp[4] != '0.0 ns':
                #delta_start
                step = round( float( p1_exp[4].split(' ')[0] ), 1)
            elif p1_exp[5] != '0.0 ns':
                #length_increment
                step = round( float( p1_exp[5].split(' ')[0] ), 1)
            else:
                #prevent no increment
                step = 1
                #conn.send( ('Message', 'No START or LENGTH increment; the time axis corresponds to the number of points in the experiment') )

            POINTS = points
            STEP = step
            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(p1_exp[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            EXP_NAME = exp_name
            CURVE_NAME = curve_name

            bh15.magnet_field( field )
            general.wait('2000 ms')

            if laser_flag != 1:
                pb.pulser_repetition_rate( REP_RATE )
                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if int(float(length_str)) != 0:
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3],
                            delta_start=p[4],
                            length_increment=p[5]
                        )

            else:
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                elif laser_num == 2:
                    pb.pulser_repetition_rate( REP_RATE )
                else:
                    pb.pulser_repetition_rate( REP_RATE )

                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_switch_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if i == 1 and length_val == 0:
                        raise ValueError(f"LASER pulse has zero length")

                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2],
                            'delta_start': p[4],
                            'length_increment': p[5]

                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            pb.digitizer_decimation(DEC_COEF)
            #points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)
            data = np.zeros( ( 2, POINTS ) )
            x_axis = np.linspace(0, (POINTS - 1)*STEP, num = POINTS) 

            while self.command != 'exit':

                for k in general.scans(SCANS):

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        for i in range(PHASES):
                            
                            pb.pulser_next_phase()

                            ##data = np.random.random( ( 2, POINTS ) )
                            if step != 1:
                                general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                            else:
                                general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))

                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        pb.pulser_shift()
                        pb.pulser_increment()

                        #conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit(integral = True)
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()


                    pb.pulser_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                if step != 1:
                    general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j*STEP, 1)))
                else:
                    general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Point', xscale = '', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Time: ' + str(k) + ' / ' + str(round(j, 1)))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
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
                    f"Time (ns), I (A.U.), Q (A.U.)"
                )

                #conn.send(('Open', ''))
                
                #while True:
                #    if conn.poll():
                #        msg = conn.recv()
                #        if msg.startswith('FL'):
                #            file_data = msg[2:]
                #            break
                #    general.wait('200 ms')


                #file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('test', f'') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def exp_field(self, conn, decimation, num_ave, scans, start_field,
            end_field, step_field, win_left, exp_name, curve_name,
            win_right, p1_exp, p2_exp, p3_exp, p4_exp, 
            p5_exp, p6_exp, p7_exp, p8_exp, p9_exp, laser_flag, 
            rep_rate, laser_num, q_switch_delay):
        import traceback

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
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

            pb.win_left = win_left
            pb.win_right = win_right

            START_FIELD = start_field
            END_FIELD = end_field
            FIELD_STEP = step_field
            
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(p1_exp[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            EXP_NAME = exp_name
            CURVE_NAME = curve_name

            #general.plot_remove(exp_name)

            bh15.magnet_field( start_field )
            general.wait('2000 ms')

            if laser_flag != 1:
                pb.pulser_repetition_rate( REP_RATE )
                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    
                    if int(float(length_str)) != 0:
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3],
                            delta_start=p[4],
                            length_increment=p[5]
                        )

            else:
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                elif laser_num == 2:
                    pb.pulser_repetition_rate( REP_RATE )
                else:
                    pb.pulser_repetition_rate( REP_RATE )

                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_switch_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2],
                            'delta_start': p[4],
                            'length_increment': p[5]

                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            pb.digitizer_decimation(DEC_COEF)
            #points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)

            POINTS = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
            data = np.zeros( ( 2, POINTS ) )
            x_axis = np.linspace(START_FIELD, END_FIELD, num = POINTS)

            while self.command != 'exit':
                k = 1

                while k <= SCANS:

                    field = START_FIELD

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):

                        bh15.magnet_field(field)#, calibration = 'True')

                        for i in range(PHASES):
                        
                            #r_data = np.random.random( 2 )
                            #data[0, j] = r_data[0]
                            #data[1, j] = r_data[1]

                            process = general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Field', xscale = 'G', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Field: ' + str(k) + ' / ' + str(field), pr = process)

                            pb.pulser_next_phase()


                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        field = round( (FIELD_STEP + field), 3 )

                        pb.pulser_shift()

                        conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit(integral = True)
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()

                    k += 1

                self.command = 'exit'

            if self.command == 'exit':
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Field', xscale = 'G', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Field: ' + str(k) + ' / ' + str(field))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR Experiment\n"
                    f"{'Start Field:':<{w}} {START_FIELD} G\n"
                    f"{'End Field:':<{w}} {END_FIELD} G\n"
                    f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
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
                    f"Field (G), I (A.U.), Q (A.U.)"
                )

                conn.send(('Open', ''))
                
                while True:
                    if conn.poll():
                        msg = conn.recv()
                        if msg.startswith('FL'):
                            file_data = msg[2:]
                            break
                    general.wait('200 ms')


                file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('', f'Experiment {exp_name} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def exp_field_test(self, conn, decimation, num_ave, scans, start_field,
            end_field, step_field, win_left, exp_name, curve_name,
            win_right, p1_exp, p2_exp, p3_exp, p4_exp, 
            p5_exp, p6_exp, p7_exp, p8_exp, p9_exp, laser_flag, 
            rep_rate, laser_num, q_switch_delay):

        import traceback

        sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            general.test_flag = 'test'
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

            pb.win_left = win_left
            pb.win_right = win_right

            START_FIELD = start_field
            END_FIELD = end_field
            FIELD_STEP = step_field
            
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(p1_exp[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            EXP_NAME = exp_name
            CURVE_NAME = curve_name

            bh15.magnet_field( start_field )
            general.wait('2000 ms')

            if laser_flag != 1:
                pb.pulser_repetition_rate( REP_RATE )
                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if p[4] != '0.0 ns':
                        raise ValueError(f"Please remove Start Increments for all pulses")

                    if int(float(length_str)) != 0:
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3],
                            delta_start=p[4],
                            length_increment=p[5]
                        )

            else:
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                elif laser_num == 2:
                    pb.pulser_repetition_rate( REP_RATE )
                else:
                    pb.pulser_repetition_rate( REP_RATE )

                pulses = [
                        p1_exp, p2_exp, p3_exp, p4_exp, 
                        p5_exp, p6_exp, p7_exp, p8_exp, 
                        p9_exp
                        ]

                for i, p in enumerate(pulses):
                    if p[4] != '0.0 ns':
                        raise ValueError(f"Please remove Start Increments for all pulses")

                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_switch_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if i == 1 and length_val == 0:
                        raise ValueError(f"LASER pulse has zero length")

                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2],
                            'delta_start': p[4],
                            'length_increment': p[5]

                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            pb.digitizer_decimation(DEC_COEF)
            #points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)

            POINTS = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1
            data = np.zeros( ( 2, POINTS ) )
            x_axis = np.linspace(START_FIELD, END_FIELD, num = POINTS)

            while self.command != 'exit':

                for k in general.scans(SCANS):

                    field = START_FIELD

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):

                        bh15.magnet_field(field)#, calibration = 'True')

                        for i in range(PHASES):

                            
                            ##data = np.random.random( ( 2, POINTS ) )
                            process = general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Field', xscale = 'G', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Field: ' + str(k) + ' / ' + str(field), pr = process)

                            pb.pulser_next_phase()

                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        field = round( (FIELD_STEP + field), 3 )

                        pb.pulser_shift()

                        #conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit(integral = True)
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                general.plot_1d(exp_name, x_axis, ( data[0], data[1] ), xname = 'Field', xscale = 'G', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Field: ' + str(k) + ' / ' + str(field))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR Experiment\n"
                    f"{'Start Field:':<{w}} {START_FIELD} G\n"
                    f"{'End Field:':<{w}} {END_FIELD} G\n"
                    f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
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
                    f"Field (G), I (A.U.), Q (A.U.)"
                )

                #conn.send(('Open', ''))
                
                #while True:
                #    if conn.poll():
                #        msg = conn.recv()
                #        if msg.startswith('FL'):
                #            file_data = msg[2:]
                #            break
                #    general.wait('200 ms')


                #file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('test', f'') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def exp_log(self, conn, decimation, num_ave, scans, points,
            log_start, log_end, win_left, exp_name, curve_name,
            win_right, p1_exp, p2_exp, p3_exp, p4_exp, 
            p5_exp, p6_exp, p7_exp, p8_exp, p9_exp, laser_flag, 
            rep_rate, field, laser_num, q_switch_delay):

        import traceback

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
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
            POINTS = len( nonlinear_time )
            x_axis = (np.insert(nonlinear_time , 0, 0))[:-1]

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            pb.win_left = win_left
            pb.win_right = win_right

            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(p1_exp[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            EXP_NAME = exp_name
            CURVE_NAME = curve_name

            bh15.magnet_field( field )
            general.wait('2000 ms')


            #### Creating different delays for different pulses
            name_list = []
            rel_shift = np.array( [] )
            pulses = [
                    p1_exp, p2_exp, p3_exp, p4_exp, 
                    p5_exp, p6_exp, p7_exp, p8_exp, 
                    p9_exp
                    ]

            for p in pulses:
                length_str = p[2].split(' ')[0]
                if int(float(length_str)) != 0:
                    rel_shift = np.append(rel_shift, float(p[4].split(' ')[0]) ) 
            
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
                x_axis = x_axis * rel_shift[0] + self.round_to_closest( float(p1_exp[1].split(" ")[0]) , 3.2)
            else:
                indices = np.where(rel_shift[1:] != 0)[0] + 1
                if indices.size > 0:
                    x_axis = x_axis * rel_shift[indices[0]] + self.round_to_closest( float(pulses[indices[0]][1].split(" ")[0]) , 3.2)
                else:
                    ## this is for start increments: [3.2 3.2 3.2]
                    raise ValueError(f"Pulses do not have Start Increments")
            ####

            if laser_flag != 1:
                pb.pulser_repetition_rate( REP_RATE )

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if int(float(length_str)) != 0:
                        name_list.append(f'P{i}')
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3],
                            delta_start=f"{self.round_to_closest( nonlinear_time[0] * rel_shift[i], 3.2 )} ns"
                        )

            else:
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                elif laser_num == 2:
                    pb.pulser_repetition_rate( REP_RATE )
                else:
                    pb.pulser_repetition_rate( REP_RATE )

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_switch_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if length_val != 0:
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2],
                            'delta_start': f"{self.round_to_closest( nonlinear_time[0] * rel_shift[i], 3.2 )} ns"
                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            pb.digitizer_decimation(DEC_COEF)
            #points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)
            data = np.zeros( ( 2, POINTS ) )

            while self.command != 'exit':

                for k in general.scans(SCANS):

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        for i in range(PHASES):
                            
                            #r_data = np.random.random( 2 )
                            #data[0, j] = r_data[0]
                            #data[1, j] = r_data[1]
                            pb.pulser_next_phase()

                            process = general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Point: ' + str(k) + ' / ' + str(j), pr = process)


                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        # nonlinear_time_shift is calculated from the initial position of the pulses
                        if j > 0:
                            new_delta_start = nonlinear_time[j] - nonlinear_time[j-1]

                            delta_starts = [f"{self.round_to_closest(x * new_delta_start, 3.2)} ns" for x in rel_shift]
                            pb.pulser_redefine_delta_start(name = name_list, delta_start = delta_starts )

                        pb.pulser_shift()

                        conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit(integral = True)
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                    pb.pulser_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Point: ' + str(k) + ' / ' + str(j))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR Log Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {tb} ns\n"
                    f"{'Log[T Start]:':<{w}} {T_start}\n"
                    f"{'Log[T End]:':<{w}} {T_end}\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"Time (ns), I (A.U.), Q (A.U.)"
                )

                conn.send(('Open', ''))
                
                while True:
                    if conn.poll():
                        msg = conn.recv()
                        if msg.startswith('FL'):
                            file_data = msg[2:]
                            break
                    general.wait('200 ms')

                file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('', f'Experiment {exp_name} finished') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def exp_log_test(self, conn, decimation, num_ave, scans, points,
            log_start, log_end, win_left, exp_name, curve_name,
            win_right, p1_exp, p2_exp, p3_exp, p4_exp, 
            p5_exp, p6_exp, p7_exp, p8_exp, p9_exp, laser_flag, 
            rep_rate, field, laser_num, q_switch_delay):
        import traceback

        sys.argv = ['', 'test']

        try:
            import time
            import datetime
            import numpy as np
            import atomize.general_modules.general_functions as general
            general.test_flag = 'test'
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
            POINTS = len( nonlinear_time )
            x_axis = (np.insert(nonlinear_time , 0, 0))[:-1]

            file_handler = openfile.Saver_Opener()
            pb = pb_pro.Insys_FPGA()
            bh15 = bh.BH_15()
            ls335 = ls.Lakeshore_335()
            mw = mwBridge.Micran_X_band_MW_bridge_v2()

            pb.win_left = win_left
            pb.win_right = win_right

            FIELD = field
            AVERAGES = num_ave
            SCANS = scans
            PHASES = len(p1_exp[3])
            DEC_COEF = decimation
            process = 'None'
            REP_RATE = f'{rep_rate} Hz'
            EXP_NAME = exp_name
            CURVE_NAME = curve_name

            bh15.magnet_field( field )
            general.wait('2000 ms')

            #### Creating different delays for different pulses
            name_list = []
            rel_shift = np.array( [] )
            pulses = [
                    p1_exp, p2_exp, p3_exp, p4_exp, 
                    p5_exp, p6_exp, p7_exp, p8_exp, 
                    p9_exp
                    ]

            for p in pulses:
                length_str = p[2].split(' ')[0]
                if int(float(length_str)) != 0:
                    rel_shift = np.append(rel_shift, float(p[4].split(' ')[0]) ) 
            
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
                x_axis = x_axis * rel_shift[0] + self.round_to_closest( float(p1_exp[1].split(" ")[0]) , 3.2)
            else:
                indices = np.where(rel_shift[1:] != 0)[0] + 1
                if indices.size > 0:
                    x_axis = x_axis * rel_shift[indices[0]] + self.round_to_closest( float(pulses[indices[0]][1].split(" ")[0]) , 3.2)
                else:
                    ## this is for start increments: [3.2 3.2 3.2]
                    raise ValueError(f"Pulses do not have Start Increments")
            ####

            if laser_flag != 1:
                pb.pulser_repetition_rate( REP_RATE )

                for i, p in enumerate(pulses):
                    length_str = p[2].split(' ')[0]
                    if int(float(length_str)) != 0:
                        name_list.append(f'P{i}')
                        pb.pulser_pulse(
                            name=f'P{i}',
                            channel=p[0],
                            start=p[1],
                            length=p[2],
                            phase_list=p[3],
                            delta_start=f"{self.round_to_closest( nonlinear_time[0] * rel_shift[i], 3.2 )} ns"
                        )

            else:
                if laser_num == 1:
                    pb.pulser_repetition_rate( '9.9 Hz' )
                elif laser_num == 2:
                    pb.pulser_repetition_rate( REP_RATE )
                else:
                    pb.pulser_repetition_rate( REP_RATE )

                for i, p in enumerate(pulses):
                    if i != 1:
                        start_val = float(p[1].split(' ')[0]) + q_switch_delay
                        p[1] = f"{self.round_to_closest(start_val, 3.2)} ns"

                    length_val = int(float(p[2].split(' ')[0]))
                    if i == 1 and length_val == 0:
                        raise ValueError(f"LASER pulse has zero length")

                    if length_val != 0:
                        name_list.append(f'P{i}')
                        kwargs = {
                            'name': f'P{i}',
                            'channel': p[0],
                            'start': p[1],
                            'length': p[2],
                            'delta_start': f"{self.round_to_closest( nonlinear_time[0] * rel_shift[i], 3.2 )} ns"
                        }
                        
                        if i != 1:
                            kwargs['phase_list'] = p[3]
                            
                        pb.pulser_pulse(**kwargs)

            pb.digitizer_decimation(DEC_COEF)
            #points_window = pb.digitizer_window_points()

            pb.pulser_open()
            pb.digitizer_number_of_averages(AVERAGES)
            data = np.zeros( ( 2, POINTS ) )

            while self.command != 'exit':

                for k in general.scans(SCANS):

                    if self.command == 'exit':
                        break

                    for j in range(POINTS):
                        for i in range(PHASES):
                            
                            ##data = np.random.random( ( 2, POINTS ) )
                            pb.pulser_next_phase()

                            process = general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Point: ' + str(k) + ' / ' + str(j), pr = process)

                            data[0], data[1] = pb.digitizer_get_curve( POINTS, PHASES, current_scan = k, total_scan = SCANS, integral = True )

                        # nonlinear_time_shift is calculated from the initial position of the pulses
                        if j > 0:
                            new_delta_start = nonlinear_time[j] - nonlinear_time[j-1]

                            delta_starts = [f"{self.round_to_closest(x * new_delta_start, 3.2)} ns" for x in rel_shift]
                            pb.pulser_redefine_delta_start(name = name_list, delta_start = delta_starts )

                        pb.pulser_shift()

                        #conn.send( ('Status', int( 100 * (( k - 1 ) * POINTS + j + 1) / POINTS / SCANS)) )

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            data[0], data[1] = pb.digitizer_at_exit(integral = True)
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()
                    
                    pb.pulser_pulse_reset()

                self.command = 'exit'

            if self.command == 'exit':
                tb = round( pb.digitizer_window(), 1)
                pb.pulser_close()

                general.plot_1d(exp_name, x_axis / 1e9, ( data[0], data[1] ), xname = 'Time', xscale = 's', yname = 'Area', yscale = 'A.U.', label = curve_name, text = 'Scan / Point: ' + str(k) + ' / ' + str(j))

                now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                w = 30

                # Data saving
                header = (
                    f"{'Date:':<{w}} {now}\n"
                    f"{'Experiment:':<{w}} Pulsed EPR Log Experiment\n"
                    f"{'Field:':<{w}} {FIELD} G\n"
                    f"{general.fmt(mw.mw_bridge_rotary_vane(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att2_prm(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_att1_prd(), w)}\n"
                    f"{general.fmt(mw.mw_bridge_synthesizer(), w)}\n"
                    f"{'Repetition Rate:':<{w}} {pb.pulser_repetition_rate()}\n"
                    f"{'Number of Scans:':<{w}} {SCANS}\n"
                    f"{'Averages:':<{w}} {AVERAGES}\n"
                    f"{'Points:':<{w}} {POINTS}\n"
                    f"{'Window:':<{w}} {tb} ns\n"
                    f"{'Log[T Start]:':<{w}} {T_start}\n"
                    f"{'Log[T End]:':<{w}} {T_end}\n"
                    f"{'Temperature:':<{w}} {ls335.tc_temperature('A')} K\n"
                    f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                    f"{'-'*50}\n"
                    f"Pulse List:\n{pb.pulser_pulse_list()}"
                    f"{'-'*50}\n"
                    f"Time (ns), I (A.U.), Q (A.U.)"
                )

                #conn.send(('Open', ''))
                
                #while True:
                #    if conn.poll():
                #        msg = conn.recv()
                #        if msg.startswith('FL'):
                #            file_data = msg[2:]
                #            break
                #    general.wait('200 ms')


                #file_handler.save_data(file_data, np.c_[x_axis, data[0], data[1]], header = header, mode = 'w')

                conn.send( ('test', f'') )

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    
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
