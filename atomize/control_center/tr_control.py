#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
from atomize.general_modules.gui_style import REFINED_STYLES, style_file_dialog
import time
import numpy as np
from multiprocessing import Process, Pipe
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QTextEdit, QGridLayout, QFrame, QCheckBox, QProgressBar, QFileDialog,  QTreeView, QHeaderView, QSizeGrip, QLineEdit, QFileIconProvider, QTabWidget
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt, QTimer
import atomize.general_modules.csv_opener_saver as openfile
import atomize.general_modules.last_dir as ldir
import atomize.control_center.field_param as field_param
import atomize.control_center.temp_param as temp_param
from atomize.general_modules.gui_style import CHECKBOX_STYLE

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

        self.save_scan = 0
        self.two_side = 0
        self.save_hdf5 = 0
        self.design()
        self.exit_clicked = 0
        self.stop_requested = False

        """
        Create a process to interact with an experimental script that will run on a different thread.
        We need a different thread here, since PyQt GUI applications have a main thread of execution that runs the event loop and GUI. If you launch a long-running task in this thread, then your GUI will freeze until the task terminates. During that time, the user won’t be able to interact with the application
        """

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_messages)
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.check_process_status)
        self.file_handler = openfile.Saver_Opener()

    def design(self):

        self.setObjectName("MainWindow")
        self.setWindowTitle("TR EPR")
        self.setStyleSheet(REFINED_STYLES['WINDOW_STYLE'])

        path_to_main = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(path_to_main, 'gui/icon_tr.ico')
        self.setWindowIcon( QIcon(icon_path) )
        self.path = os.path.join(path_to_main, '..', '..', '..', '..', 'experimental_data')

        self.tabs = QTabWidget()
        self.tabs.setTabShape(QTabWidget.TabShape.Rounded)
        self.tabs.setStyleSheet(REFINED_STYLES['TAB_STYLE'])
        self.setCentralWidget(self.tabs)
        self.tr_tab = QWidget()
        self.tabs.addTab(self.tr_tab, 'TR EPR')

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(14, 10, 7, 10)
        gridLayout.setVerticalSpacing(4)
        gridLayout.setHorizontalSpacing(20)

        self.tr_tab.setLayout(gridLayout)

        # ---- Labels & Inputs ----
        labels = [("Start Field", "label_1"), ("End Field", "label_2"), ("Field Step", "label_3"), ("Off-Resonance Field", "label_4"), ("Off-Resonance Acquisitions", "label_5"), ("Acquisitions", "label_6"), ("Number of Scans", "label_7"), ("Save Each Scan", "label_8"), ("Two-Side Measurement", "label_9"), ("Number of Oscilloscopes", "label_10"), ("Trigger Channel", "label_11"), ("Experiment Name", "label_12"), ("Progress", "label_13"), ("Save as HDF5", "label_14")]

        for name, attr_name in labels:
            lbl = QLabel(name)
            lbl.setFixedSize(190, 26)
            setattr(self, attr_name, lbl)
            lbl.setStyleSheet(REFINED_STYLES['LABEL_STYLE'])


        # ---- Boxes ----
        double_boxes = [(QDoubleSpinBox, "box_st_field", "cur_start_field", self.st_field, 0, 15000, 3000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_end_field", "cur_end_field", self.end_field, 0, 15000, 4000, 1, 1, " G"),
                      (QDoubleSpinBox, "box_step_field", "cur_step", self.step_field, 0.01, 50, 0.5, 0.1, 2, " G"),
                      (QDoubleSpinBox, "box_off_res_field", "cur_offres_field", self.offres_field, 0, 15000, 500, 1, 1, " G"),
                      (QSpinBox, "box_ave", "cur_ave", self.ave, 2, 2000, 10, 1, 0, ""),
                      (QSpinBox, "box_ave_offres", "cur_ave_offres", self.ave_offres, 2, 2000, 10, 1, 0, ""),
                      (QSpinBox, "box_scan", "cur_scan", self.scan, 1, 100, 1, 1, 0, "")
                        ]

        for widget_class, attr_name, par_name, func, v_min, v_max, cur_val, v_step, dec, suf in double_boxes:
            spin_box = widget_class()
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setRange(v_min, v_max)
                spin_box.setStyleSheet(REFINED_STYLES['COMPACT_FIELD_STYLE'])
            else:
                spin_box.setRange(int(v_min), int(v_max))
                spin_box.setStyleSheet(REFINED_STYLES['COMPACT_FIELD_STYLE'])
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


        # ---- Combo boxes----
        combo_boxes = [("1", "combo_num_osc", "cur_num_osc", self.num_osc, 
                        [
                        "1", "2", "2 + THz Pulse"
                        ]),
                      ("CH2", "combo_trig_ch", "cur_trig_ch", self.trig_ch, 
                        [
                        "CH2", "Ext"
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
            combo.setStyleSheet(REFINED_STYLES['COMBO_STYLE'])

            if par_name == 'cur_num_osc' and len( str( self.cur_num_osc ) ) > 1:
                self.cur_num_osc = 3
            elif par_name == 'cur_num_osc':
                self.cur_num_osc = int( self.cur_num_osc )

        # ---- Text Edits ----
        text_edit = [("TR", "text_edit_exp_name", "cur_exp_name", self.exp_name),
                    ]

        for text, attr_name, par_name, func in text_edit:
            txt = QTextEdit(text)
            setattr(self, attr_name, txt)
            setattr(self, par_name, txt.toPlainText())
            txt.textChanged.connect(func)
            txt.setFixedSize(130, 26)
            txt.setAcceptRichText(False)
            txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setStyleSheet(REFINED_STYLES['COMPACT_TEXT_STYLE'])
            txt.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # ---- Check Boxes ----
        check_boxes = [("checkbox_back_scan", self.two_side_measure),
                       ("check_scan", self.save_each_scan),
                       ("check_hdf5", self.save_as_hdf5)
                       ]

        for attr_name, func in check_boxes:
            check = QCheckBox("")
            setattr(self, attr_name, check)
            check.stateChanged.connect(func)
            check.setFixedSize(130, 26)
            check.setStyleSheet(CHECKBOX_STYLE)

        # ---- Buttons ----
        buttons = [("Start", "button_start", self.start),
                   ("Stop", "button_stop", self.stop),
                   ("Exit", "button_off", self.turn_off) ]

        for name, attr_name, func in buttons:
            btn = QPushButton(name)
            btn.setFixedSize(140, 40)
            btn.clicked.connect(func)
            btn.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'])
            setattr(self, attr_name, btn)

        # ---- Separators ----
        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        # ---- Progress Bar ----
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedSize(130, 15)
        self.progress_bar.setTextVisible(True)
        #self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.progress_bar.setStyleSheet(REFINED_STYLES['PROGRESS_STYLE'])

        # ---- Layout placement ----
        gridLayout.addWidget(self.label_1, 0, 0)
        gridLayout.addWidget(self.box_st_field, 0, 1)
        gridLayout.addWidget(self.label_2, 1, 0)
        gridLayout.addWidget(self.box_end_field, 1, 1)
        gridLayout.addWidget(self.label_3, 2, 0)
        gridLayout.addWidget(self.box_step_field, 2, 1)
        gridLayout.addWidget(self.label_4, 3, 0)
        gridLayout.addWidget(self.box_off_res_field, 3, 1)

        gridLayout.addWidget(hline(), 4, 0, 1, 2)

        gridLayout.addWidget(self.label_5, 5, 0)
        gridLayout.addWidget(self.box_ave_offres, 5, 1)
        gridLayout.addWidget(self.label_6, 6, 0)
        self.box_ave.setToolTip('Shots per field point. 16-128 recommended: fewer wastes time re-arming the scope, more gains nothing over extra scans.')
        gridLayout.addWidget(self.box_ave, 6, 1)
        gridLayout.addWidget(self.label_7, 7, 0)
        gridLayout.addWidget(self.box_scan, 7, 1)
        gridLayout.addWidget(self.label_8, 8, 0)
        gridLayout.addWidget(self.check_scan, 8, 1)
        gridLayout.addWidget(self.label_9, 9, 0)
        gridLayout.addWidget(self.checkbox_back_scan, 9, 1)
        gridLayout.addWidget(self.label_14, 10, 0)
        gridLayout.addWidget(self.check_hdf5, 10, 1)

        gridLayout.addWidget(hline(), 11, 0, 1, 2)

        gridLayout.addWidget(self.label_10, 12, 0)
        gridLayout.addWidget(self.combo_num_osc, 12, 1)
        gridLayout.addWidget(self.label_11, 13, 0)
        gridLayout.addWidget(self.combo_trig_ch, 13, 1)

        gridLayout.addWidget(hline(), 14, 0, 1, 2)

        gridLayout.addWidget(self.label_12, 15, 0)
        gridLayout.addWidget(self.text_edit_exp_name, 15, 1)

        gridLayout.addWidget(hline(), 16, 0, 1, 2)

        gridLayout.addWidget(self.label_13, 17, 0)
        gridLayout.addWidget(self.progress_bar, 17, 1)

        gridLayout.addWidget(hline(), 18, 0, 1, 2)

        gridLayout.addWidget(self.button_start, 19, 0)
        gridLayout.addWidget(self.button_stop, 20, 0)
        gridLayout.addWidget(self.button_off, 21, 0)

        gridLayout.setRowStretch(22, 2)
        gridLayout.setColumnStretch(21, 2)
        self.design_half_field()

        self.scope_tabs = [ScopeTab(self, 0), ScopeTab(self, 1)]
        for tab in self.scope_tabs:
            self.tabs.addTab(tab, f'Scope {tab.number}')
        self.tabs.currentChanged.connect(self.fit_tab)
        self.fit_tab(0)
        QTimer.singleShot(0, lambda: self.fit_tab(self.tabs.currentIndex()))
        self.set_scopes_editable(True)

    def design_half_field(self):
        grid = self.tr_tab.layout()
        items = []
        while grid.count():
            position = grid.getItemPosition(0)
            items.append((grid.takeAt(0), position))
        for item, (row, column, rows, columns) in items:
            grid.addItem(item, row if row < 3 else row + 4, column, rows, columns)
        grid.setRowStretch(22, 0)
        grid.setRowStretch(26, 2)
        grid.setColumnStretch(21, 0)
        label = QLabel('Half-Field Measurement')
        label.setStyleSheet(REFINED_STYLES['LABEL_STYLE'])
        self.enable_half = QCheckBox()
        self.enable_half.setStyleSheet(CHECKBOX_STYLE)
        self.enable_half.setFixedSize(130, 26)
        self.enable_half.setToolTip('One background, half-field sweep, then main-field sweep = one scan.')
        grid.addWidget(label, 3, 0)
        grid.addWidget(self.enable_half, 3, 1)
        self.half_boxes = []
        self.half_labels = []
        for row, (text, value) in enumerate((('Half-Field Start', 1600), ('Half-Field End', 1800), ('Half-Field Step', 2)), 4):
            box = QDoubleSpinBox()
            box.setDecimals(2 if row == 6 else 1)
            box.setRange(0.01 if row == 6 else 0, 50 if row == 6 else 15000)
            box.setValue(value)
            box.setSuffix(' G')
            box.setFixedSize(130, 26)
            box.setKeyboardTracking(False)
            box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            box.setStyleSheet(REFINED_STYLES['COMPACT_FIELD_STYLE'])
            label = QLabel(text)
            label.setStyleSheet(REFINED_STYLES['LABEL_STYLE'])
            grid.addWidget(label, row, 0)
            grid.addWidget(box, row, 1)
            self.half_boxes.append(box)
            self.half_labels.append(label)
        self.enable_half.toggled.connect(self.toggle_half)
        self.toggle_half()

    def toggle_half(self):
        for widget in self.half_boxes + self.half_labels:
            widget.setVisible(self.enable_half.isChecked())
        self.fit_tab(self.tabs.currentIndex())

    def set_half_editable(self, editable):
        self.enable_half.setEnabled(editable)
        for box in self.half_boxes:
            box.setEnabled(editable)

    def fit_tab(self, index):
        """Fix the window height to the visible tab, like a single-page tool; the window manager honours a fixed size."""
        page = self.tabs.widget(index)
        page.layout().activate()
        pages = [self.tabs.widget(i).sizeHint().height() for i in range(self.tabs.count())]
        tab_bar = self.tabs.tabBar().sizeHint().height()
        frame = self.tabs.sizeHint().height() - tab_bar - max(pages)
        height = self.menuBar().sizeHint().height() + tab_bar + frame + page.sizeHint().height()
        self.setFixedSize(self.sizeHint().width(), height)

    def set_scopes_editable(self, editable):
        """Scope tabs are read-only while the experiment worker owns the scopes; Scope 2 needs two scopes."""
        self.scopes_editable = editable
        second = self.cur_num_osc > 1
        self.tabs.setTabEnabled(2, second)
        self.scope_tabs[0].setEnabled(editable)
        self.scope_tabs[1].setEnabled(editable and second)

    def menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(REFINED_STYLES['MENU_STYLE'])
        file_menu = menubar.addMenu("File")

        menubar.setFixedHeight(27)

        self.action_read = QAction("Read from file", self)
        self.action_read.triggered.connect( self.open_file_dialog )
        file_menu.addAction(self.action_read)

        self.action_save = QAction("Save to file", self)
        self.action_save.triggered.connect(self.save_file_dialog)
        file_menu.addAction(self.action_save)

    def two_side_measure(self):
        """
        Turn on/off backward measurement
        """
        if self.checkbox_back_scan.checkState().value == 2: # checked
            self.two_side = 1
        elif self.checkbox_back_scan.checkState().value == 0: # unchecked
            self.two_side = 0

    def closeEvent(self, event):
        event.ignore()
        self.turn_off()

    def quit(self):
        """
        A function to quit the programm
        """
        self.turn_off()
        sys.exit()

    def save_each_scan(self):
        """
        Turn on/off save each scan when using one oscilloscope
        """
        if self.check_scan.checkState().value == 2: # checked
            self.save_scan = 1
        elif self.check_scan.checkState().value == 0: # unchecked
            self.save_scan = 0

    def save_as_hdf5(self):
        """
        Write the 2D data as a single .h5 file instead of CSV; with Save Each
        Scan on, the per-scan snapshots become slices of one 'scans' dataset
        instead of a whole extra file per scan
        """
        if self.check_hdf5.checkState().value == 2: # checked
            self.save_hdf5 = 1
        elif self.check_hdf5.checkState().value == 0: # unchecked
            self.save_hdf5 = 0

    def exp_name(self):
        self.cur_exp_name = self.text_edit_exp_name.toPlainText()
        #print( self.cur_exp_name )

    def trig_ch(self):
        """
        A function to send a trigger channel
        """
        self.cur_trig_ch = str( self.combo_trig_ch.currentText() )
        #print(self.cur_end_field)

    def end_field(self):
        """
        A function to send an end field value
        """
        self.cur_end_field = round( float( self.box_end_field.value() ), 3 )
        #print(self.cur_end_field)

    def st_field(self):
        """
        A function to send a start field value
        """
        self.cur_start_field = round( float( self.box_st_field.value() ), 3 )
        #print(self.cur_start_field)

    def step_field(self):
        """
        A function to send a step field value
        """
        self.cur_step = round( float( self.box_step_field.value() ), 3 )
        #print(self.cur_step)

    def offres_field(self):
        """
        A function to send an off-resonance field
        """
        self.cur_offres_field = round( float( self.box_off_res_field.value() ), 3 )
        #print(self.cur_lock_ampl)

    def scan(self):
        """
        A function to send a number of scans
        """
        self.cur_scan = int( self.box_scan.value() )
        #print(self.cur_scan)
        try:
            self.parent_conn.send( 'SC' + str( self.cur_scan ) )
        except AttributeError:
            pass
            #self.message('Experimental script is not running')

    def ave(self):
        """
        A function to send a number of averages
        """
        self.cur_ave = int( self.box_ave.value() )
        #print(self.cur_ave)

    def num_osc(self):
        """
        A function to send number of oscilloscopes
        """
        if len( self.combo_num_osc.currentText() ) > 1:
            self.cur_num_osc = 3
        else:
            self.cur_num_osc = int( self.combo_num_osc.currentText() )
        if not hasattr(self, 'scope_tabs'):
            return
        if self.cur_num_osc == 1:
            self.scope_tabs[1].request_exit()
        self.set_scopes_editable(getattr(self, 'scopes_editable', True))
        for tab in self.scope_tabs:
            tab.send(('SET', 'num_osc', self.cur_num_osc))

    def ave_offres(self):
        """
        A function to send a number of averages for off-resonance
        """
        self.cur_ave_offres = int( self.box_ave_offres.value() )
        #print(self.cur_ave_offres)

    def turn_off(self):
        """
         A function to turn off a program.
        """
        self.exit_clicked = 1
        self.stop_requested = True
        self.pending_start = False
        for tab in self.scope_tabs:
            tab.request_exit()
        try:
            self.parent_conn.send( 'exit' )
            self.monitor_timer.start(200)
        except AttributeError:
            sys.exit()
            #self.message('Experimental script is not running')

    def check_process_status(self):
        if getattr(self, 'pending_start', False):
            if any(tab.is_alive() for tab in self.scope_tabs):
                return
            self.pending_start = False
            self.monitor_timer.stop()
            self.start()
            return

        if self.exp_process.is_alive():
            return
        
        self.monitor_timer.stop()
        self.set_half_editable(True)
        self.set_scopes_editable(True)
        self.exp_process.join() 
        #self.timer.stop()
        self.progress_bar.setValue(0)
        self.button_start.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'])
        field_param.clear_lock()
        temp_param.clear_lock()

        if self.exit_clicked == 1:
            sys.exit()

    def stop(self):
        """
        A function to stop script
        """
        self.stop_requested = True
        try:
            self.parent_conn.send( 'exit' )
            self.monitor_timer.start(200)

        except AttributeError:
            pass
            #self.message('Experimental script is not running')

    def start(self):
        """
        Button Start; Run function script(pipe_addres, four parameters of the experimental script)
        from Worker class in a different thread
        Create a Pipe for interaction with this thread
        self.param_i are used as parameters for script function
        """
        worker = Worker()
        # prevent running two processes
        try:
            if self.exp_process.is_alive() == True:
                return
        except AttributeError:
            pass

        if any(tab.is_alive() for tab in self.scope_tabs):
            for tab in self.scope_tabs:
                tab.request_exit()
            self.pending_start = True
            if not self.monitor_timer.isActive():
                self.monitor_timer.start(200)
            return

        self.stop_requested = False
        self.last_error = False
        if self.cur_start_field >= self.cur_end_field:
            self.cur_start_field, self.cur_end_field = self.cur_end_field, self.cur_start_field

            self.box_end_field.setValue( self.cur_end_field )
            self.box_st_field.setValue( self.cur_start_field )

        self.pending_half_field = None
        if self.enable_half.isChecked():
            from atomize.control_center.tr_two_fields import field_axis
            half = tuple(box.value() for box in self.half_boxes)
            try:
                field_axis(*half)
                field_axis(self.cur_start_field, self.cur_end_field, self.cur_step)
                if half[1] >= self.cur_start_field:
                    raise ValueError('Half-field range must be below the main-field range.')
            except ValueError as error:
                self.message(str(error))
                self.progress_bar.setToolTip(str(error))
                return
            self.pending_half_field = half

        worker.half_field = self.pending_half_field
        worker.trigger_timeout_s = self.scope_tabs[0].trigger_timeout()
        test_target = worker.exp_test_two_fields if worker.half_field is not None else worker.exp_test
        self.parent_conn, self.child_conn = Pipe()
        # a process for running function script 
        # sending parameters for initial initialization
        self.exp_process = Process( target = test_target, args = ( self.child_conn, self.cur_offres_field, self.cur_exp_name, self.cur_end_field, self.cur_start_field, self.cur_step, self.cur_ave_offres, self.cur_scan, self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, self.two_side, ) )
            

        self.button_start.setStyleSheet(REFINED_STYLES['PRIMARY_BUTTON_STYLE'])
        self.progress_bar.setValue(0)

        self.exp_process.start()

        # send a command in a different thread about the current state
        self.parent_conn.send('start')
        field_param.set_lock('tr_control')
        temp_param.set_lock('tr_control')

        self.is_testing = True 
        self.set_half_editable(False)
        self.set_scopes_editable(False)
        self.timer.start(300)

    def message(self, *text):
        if len(text) == 1:
            print(f'{text[0]}', flush=True)
        else:
            print(f'{text}', flush=True)

    def parse_message(self):
        msg_type, data = self.parent_conn.recv()
            
        if msg_type == 'Status':
            self.progress_bar.setValue(int(data))
        elif msg_type == 'ScanComplete':
            self.progress_bar.setToolTip(f'Completed scans: {data}')
        elif msg_type == 'Open':
            self.open_dialog()
        elif msg_type == 'Message':
            self.message(data)
        elif msg_type == 'Error':
            self.last_error = True
            self.timer.stop()
            self.progress_bar.setValue(0)
            if msg_type != 'test':
                self.message(data)
            self.button_start.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'])
        else:
            self.timer.stop()
            self.progress_bar.setValue(0)
            if msg_type != 'test':
                self.message(data)
                self.button_start.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'])

    def check_messages(self):


        if not hasattr(self, 'last_error'):
            self.last_error = False

        while self.parent_conn.poll():
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
        
        if self.exp_process.is_alive() and not self.timer.isActive():
            self.exp_process.join()

        if hasattr(self, 'exp_process') and not self.exp_process.is_alive():
            if self.parent_conn.poll():
                #return
                self.parse_message()

            self.timer.stop()

            if getattr(self, 'is_testing', False):
                self.is_testing = False
                if not self.last_error and not self.stop_requested and not self.exit_clicked:
                    self.last_error = False 
                    time.sleep(0.3)
                    self.run_main_experiment()
                else:
                    self.last_error = False
                    field_param.clear_lock()
                    temp_param.clear_lock()
            else:
                field_param.clear_lock()
                temp_param.clear_lock()
                self.button_start.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'])

        if not self.exp_process.is_alive() and not getattr(self, 'is_testing', False):
            self.set_half_editable(True)
            self.set_scopes_editable(True)

    def open_dialog(self):
        file_data = self.file_handler.create_file_dialog(multiprocessing = True,
            directory = ldir.load('tr', self.path),
            fmt = 'h5' if self.save_hdf5 == 1 else 'csv')

        if file_data:
            if file_data != 'None':
                self.save_file(file_data.rsplit('.', 1)[0])
            self.parent_conn.send( 'FL' + str( file_data ) )
        else:
            self.parent_conn.send( 'FL' + '' )

    def run_main_experiment(self):

        worker = Worker()
        worker.half_field = getattr(self, 'pending_half_field', None)
        worker.trigger_timeout_s = self.scope_tabs[0].trigger_timeout()

        self.parent_conn, self.child_conn = Pipe()

        self.exp_process = Process( target = worker.exp_on, args = ( self.child_conn, self.cur_offres_field, self.cur_exp_name, self.cur_end_field, self.cur_start_field, self.cur_step, self.cur_ave_offres, self.cur_scan, self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, self.two_side, ) )
            
        self.exp_process.start()
        self.parent_conn.send('start')
        self.timer.start(300)

    def open_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Open File', directory = ldir.load('tr', self.path), filter = "TR Parameters (*.tr)", options = QFileDialog.Option.DontUseNativeDialog)
        
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

        style_file_dialog(filedialog)
        
        filedialog.setFileMode(QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.open_file)
        filedialog.show()

    def save_file_dialog(self):
        """
        A function to open a new window for choosing a pulse list
        """
        filedialog = QFileDialog(self, 'Save File', directory = ldir.load('tr', self.path), filter = "TR Parameters (*.tr)", options = QFileDialog.Option.DontUseNativeDialog)
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

        style_file_dialog(filedialog)

        filedialog.setFileMode(QFileDialog.FileMode.AnyFile)
        filedialog.fileSelected.connect(self.save_file)
        filedialog.show()

    def open_file(self, filename):
        """
        A function to open a pulse list
        :param filename: string
        """
        self.path = os.path.dirname(filename)
        ldir.save('tr', self.path)
        text = open(filename).read()
        lines = text.split('\n')

        self.box_st_field.setValue( float( lines[0].split(':  ')[1] ) )
        self.box_end_field.setValue( float( lines[1].split(':  ')[1] ) )
        self.box_step_field.setValue( float( lines[2].split(':  ')[1] ) )
        self.box_off_res_field.setValue( float( lines[3].split(':  ')[1] ) )
        self.box_ave_offres.setValue( int( lines[4].split(':  ')[1] ) )
        self.box_ave.setValue( int( lines[5].split(':  ')[1] ) )
        self.box_scan.setValue( int( lines[6].split(':  ')[1] ) )

        if int( lines[7].split(':  ')[1] ) == 2:
            self.check_scan.setCheckState(Qt.CheckState.Checked)
        else:
            self.check_scan.setCheckState(Qt.CheckState.Unchecked)
        if int( lines[8].split(':  ')[1] ) == 2:
            self.checkbox_back_scan.setCheckState(Qt.CheckState.Checked)
        else:
            self.checkbox_back_scan.setCheckState(Qt.CheckState.Unchecked)

        self.combo_num_osc.setCurrentText( str( lines[9].split(':  ')[1] ) )
        self.combo_trig_ch.setCurrentText( str( lines[10].split(':  ')[1] ) )
        extra = dict(line.split(':  ', 1) for line in lines[11:] if ':  ' in line)
        self.enable_half.setChecked(extra.get('Half Field Enabled', '0') == '1')
        for box, key in zip(self.half_boxes, ('Half Start Field', 'Half End Field', 'Half Field Step')):
            if key in extra:
                box.setValue(float(extra[key]))
        for tab in self.scope_tabs:
            tab.load(extra)

    def save_file(self, filename):
        """
        A function to save a new pulse list
        :param filename: string
        """
        self.path = os.path.dirname(filename)
        ldir.save('tr', self.path)
        if filename[-2:] != 'tr':
            filename = filename + '.tr'
        with open(filename, 'w') as file:
            file.write( 'Start Field:  ' + str(self.box_st_field.value()) + '\n' )
            file.write( 'End Field:  ' + str(self.box_end_field.value()) + '\n' )
            file.write( 'Field Step:  ' + str(self.box_step_field.value()) + '\n' )
            file.write( 'Off Resonance Field:  ' + str(self.box_off_res_field.value()) + '\n' )
            file.write( 'Off Resonance Averages:  ' + str(self.box_ave_offres.value()) + '\n' )
            file.write( 'Averages:  ' + str(self.box_ave.value()) + '\n' )
            file.write( 'Scans:  ' + str(self.box_scan.value()) + '\n' )
            file.write( 'Save Each Scan:  ' + str(self.check_scan.checkState().value) + '\n' )
            file.write( 'Two-Side:  ' + str(self.checkbox_back_scan.checkState().value) + '\n' )
            file.write( 'Number of Oscilloscopes:  ' + str(self.combo_num_osc.currentText()) + '\n' )
            file.write( 'Trigger Channel:  ' + str(self.combo_trig_ch.currentText()) + '\n' )
            if self.enable_half.isChecked():
                file.write('Half Field Enabled:  1\n')
                for box, key in zip(self.half_boxes, ('Half Start Field', 'Half End Field', 'Half Field Step')):
                    file.write(f'{key}:  {box.value()}\n')
            for tab in self.scope_tabs:
                for key, value in tab.save():
                    file.write(f'{key}:  {value}\n')

class ScopeTab(QWidget):
    """
    Settings and live preview of one Keysight scope. The scope is driven only by
    a Worker.scope_on child process between Connect and Disconnect; this widget
    never imports the device module, whose constructor exits when the scope is absent.
    """
    FIELDS = (('window_us', 'Window'), ('offset_us', 'Horizontal Offset'), ('ch1_scale_mv', 'CH1 Scale'),
              ('ch1_offset_mv', 'CH1 Offset'), ('ch2_scale_mv', 'CH2 Scale'), ('ch2_offset_mv', 'CH2 Offset'),
              ('live_averages', 'Live Acquisitions'), ('trigger_timeout_s', 'Trigger Timeout'))

    def __init__(self, main, index):
        super().__init__()
        self.main = main
        self.index = index
        self.number = index + 1
        self.process = None
        self.conn = None
        self.connected = False
        self.finished = False
        self.scope_timer = QTimer()
        self.scope_timer.timeout.connect(self.check_session)

        tb_min, tb_max, sens_min, sens_max, self.address = self.read_limits()

        grid = QGridLayout()
        grid.setContentsMargins(14, 10, 7, 10)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(20)
        self.setLayout(grid)

        def label(text):
            lbl = QLabel(text)
            lbl.setFixedSize(190, 26)
            lbl.setStyleSheet(REFINED_STYLES['LABEL_STYLE'])
            return lbl

        def hline():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            line.setLineWidth(2)
            return line

        def button(text, func):
            btn = QPushButton(text)
            btn.setFixedSize(140, 40)
            btn.clicked.connect(func)
            btn.setStyleSheet(REFINED_STYLES['BUTTON_STYLE'])
            return btn

        offset_max = 8 * sens_max * 1000
        boxes = [(QDoubleSpinBox, 'window_us', math.ceil(tb_min * 1e7) / 10, tb_max * 1e6, 500, 10, 1, ' us'),
                 (QDoubleSpinBox, 'offset_us', -tb_max * 1e6, tb_max * 1e6, 0, 1, 1, ' us'),
                 (QSpinBox, 'ch1_scale_mv', max(1, math.ceil(sens_min * 1000)), sens_max * 1000, 200, 10, 0, ' mV'),
                 (QSpinBox, 'ch1_offset_mv', -offset_max, offset_max, 0, 10, 0, ' mV'),
                 (QSpinBox, 'ch2_scale_mv', max(1, math.ceil(sens_min * 1000)), sens_max * 1000, 200, 10, 0, ' mV'),
                 (QSpinBox, 'ch2_offset_mv', -offset_max, offset_max, 0, 10, 0, ' mV'),
                 (QSpinBox, 'live_averages', 2, 2000, 2, 1, 0, ''),
                 (QDoubleSpinBox, 'trigger_timeout_s', 0.5, 60, 2.0, 0.5, 1, ' s')]
        self.boxes = {}
        for widget_class, name, v_min, v_max, cur_val, v_step, dec, suf in boxes:
            spin_box = widget_class()
            if isinstance(spin_box, QDoubleSpinBox):
                spin_box.setDecimals(dec)
                spin_box.setRange(v_min, v_max)
            else:
                spin_box.setRange(int(v_min), int(v_max))
            spin_box.setStyleSheet(REFINED_STYLES['COMPACT_FIELD_STYLE'])
            spin_box.setSingleStep(v_step)
            spin_box.setValue(cur_val)
            spin_box.setSuffix(suf)
            spin_box.setFixedSize(130, 26)
            spin_box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.PlusMinus)
            spin_box.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            spin_box.setKeyboardTracking(False)
            spin_box.valueChanged.connect(lambda value, name = name: self.send(('SET', name, value)))
            self.boxes[name] = spin_box

        self.status = QLabel('Not connected')
        self.status.setFixedSize(130, 26)
        self.status.setStyleSheet(REFINED_STYLES['LABEL_STYLE'])
        self.button_connect = button('Connect', self.connect_clicked)
        self.button_read = button('Read', lambda: self.send(('READ', )))
        self.button_run = button('Run', lambda: self.send(('RUN', )))
        self.button_stop = button('Stop', lambda: self.send(('STOP', )))
        self.check_live = QCheckBox('')
        self.check_live.setFixedSize(130, 26)
        self.check_live.setStyleSheet(CHECKBOX_STYLE)
        self.check_live.toggled.connect(lambda checked: self.send(('LIVE', int(checked))))

        grid.addWidget(label('Status'), 0, 0)
        grid.addWidget(self.status, 0, 1)
        grid.addWidget(hline(), 1, 0, 1, 2)
        row = 2
        for group in (('window_us', 'offset_us'), ('ch1_scale_mv', 'ch1_offset_mv', 'ch2_scale_mv', 'ch2_offset_mv'), ('live_averages', 'trigger_timeout_s')):
            for name in group:
                grid.addWidget(label(dict(self.FIELDS)[name]), row, 0)
                grid.addWidget(self.boxes[name], row, 1)
                row += 1
            if name != 'trigger_timeout_s':
                grid.addWidget(hline(), row, 0, 1, 2)
                row += 1
        grid.addWidget(label('Live'), row, 0)
        grid.addWidget(self.check_live, row, 1)
        grid.addWidget(hline(), row + 1, 0, 1, 2)
        for offset, btn in enumerate((self.button_connect, self.button_read, self.button_run, self.button_stop), 2):
            grid.addWidget(btn, row + offset, 0)
        grid.setRowStretch(row + 6, 2)
        grid.setColumnStretch(2, 2)
        self.reset()

    def read_limits(self):
        """Box ranges and the scope address from the module config; no instrument is touched."""
        name = 'Keysight_2000_Xseries_config.ini' if self.index == 0 else 'Keysight_2000_Xseries_2_config.ini'
        legacy = 'Keysight_2012a_config.ini' if self.index == 0 else 'Keysight_2012a_2_config.ini'
        address = '192.168.2.21/.22'
        try:
            import atomize.main.local_config as lconf
            import atomize.device_modules.config.config_utils as cutil
            path = cutil.config_path(lconf.load_config_device(), name, legacy = legacy)
            specific = cutil.read_specific_parameters(path)
            limits = [float(specific[key]) for key in ('timebase_min', 'timebase_max', 'sensitivity_min', 'sensitivity_max')]
            address = cutil.read_conf_util(path)['ethernet_address'].split('::')[1]
        except (OSError, KeyError, ValueError, IndexError):
            limits = [5e-9, 50, 0.001, 5]
        return (*limits, address)

    def settings(self):
        values = {name: box.value() for name, box in self.boxes.items()}
        values['num_osc'] = self.main.cur_num_osc
        return values

    def trigger_timeout(self):
        return float(self.boxes['trigger_timeout_s'].value())

    def is_alive(self):
        return self.process is not None and self.process.is_alive()

    def send(self, command):
        if self.connected and self.is_alive():
            self.conn.send(command)

    def request_exit(self):
        if self.is_alive():
            self.conn.send('exit')
            self.status.setText('Disconnecting…')

    def connect_clicked(self):
        if self.is_alive():
            self.request_exit()
            return

        worker = Worker()
        parent_conn, child_conn = Pipe()
        test_process = Process(target = worker.scope_on, args = (child_conn, self.index, self.settings(), True))
        test_process.start()
        test_process.join(30)
        if test_process.is_alive():
            test_process.terminate()
            test_process.join()
        replies = []
        while parent_conn.poll():
            replies.append(parent_conn.recv())
        if not any(kind == 'test' for kind, data in replies):
            for kind, data in replies:
                self.main.message(data)
            if not replies:
                self.main.message(f'scope {self.number}: settings check did not finish')
            return

        self.conn, child_conn = Pipe()
        self.process = Process(target = worker.scope_on, args = (child_conn, self.index, self.settings()))
        self.finished = False
        self.process.start()
        self.status.setText('Connecting…')
        self.button_connect.setText('Disconnect')
        self.scope_timer.start(200)

    def check_session(self):
        while self.conn.poll():
            try:
                kind, data = self.conn.recv()
            except (EOFError, OSError):
                break
            if kind == 'Settings':
                self.write_boxes(data)
                if not self.connected:
                    self.connected = True
                    self.status.setText('Connected')
                    for widget in (self.button_read, self.button_run, self.button_stop, self.check_live):
                        widget.setEnabled(True)
            elif kind == 'Live':
                self.check_live.blockSignals(True)
                self.check_live.setChecked(bool(data))
                self.check_live.blockSignals(False)
            elif kind == 'Message':
                self.main.message(data)
            else:
                self.finished = True
                self.main.message(data)

        if self.process.is_alive():
            return
        self.process.join()
        if not self.finished:
            self.main.message(f'scope {self.number} did not answer — check power and network of {self.address}')
        self.reset()

    def write_boxes(self, values):
        for name, value in values.items():
            if name in self.boxes:
                box = self.boxes[name]
                box.blockSignals(True)
                box.setValue(float(value) if isinstance(box, QDoubleSpinBox) else int(round(value)))
                box.blockSignals(False)

    def reset(self):
        self.scope_timer.stop()
        self.connected = False
        self.process = None
        self.status.setText('Not connected')
        self.button_connect.setText('Connect')
        self.check_live.blockSignals(True)
        self.check_live.setChecked(False)
        self.check_live.blockSignals(False)
        for widget in (self.button_read, self.button_run, self.button_stop, self.check_live):
            widget.setEnabled(False)

    def save(self):
        return [(f'Scope{self.number} {label}', self.boxes[name].value()) for name, label in self.FIELDS]

    def load(self, extra):
        for name, label in self.FIELDS:
            key = f'Scope{self.number} {label}'
            if key in extra:
                self.boxes[name].setValue(float(extra[key]) if isinstance(self.boxes[name], QDoubleSpinBox) else int(float(extra[key])))

def _arm(scope):
    """Clears the status registers and arms one acquisition without blocking the parser."""
    scope.oscilloscope_command(':WAVeform:FORMat WORD')
    scope.oscilloscope_command('*CLS;:SINGle')

def _wait_armed(scopes, conn, trigger_timeout_s, poll_s = 0.05):
    """
    Polls the armed scopes until every one has stopped. Returns 'done', 'exit',
    ('no_trigger', index) when a scope saw no trigger for trigger_timeout_s, or
    ('command', value) when a pipe command other than 'exit' arrives.
    """
    if any(getattr(scope, 'test_flag', None) == 'test' for scope in scopes):
        return 'done'

    running = set(range(len(scopes)))
    last_trigger = {index: time.monotonic() for index in running}
    while True:
        if conn.poll():
            command = conn.recv()
            if command == 'exit':
                for scope in scopes:
                    scope.oscilloscope_command(':STOP')
                return 'exit'
            return ('command', command)

        for index in sorted(running):
            scope = scopes[index]
            if not int(scope.oscilloscope_query(':OPERegister:CONDition?')) & 8:
                running.discard(index)
                continue
            if int(scope.oscilloscope_query(':TER?')) == 1:
                last_trigger[index] = time.monotonic()
            elif time.monotonic() - last_trigger[index] > trigger_timeout_s:
                scope.oscilloscope_command(':STOP')
                return ('no_trigger', index)

        if not running:
            return 'done'
        time.sleep(poll_s)

# The worker class that run the digitizer in a different thread
class Worker():
    def __init__(self):
        super(Worker, self).__init__()
        # initialization of the attribute we use to stop the experimental script

        self.command = 'start'
        self.half_field = None
        self.testing_two_fields = False
        self.trigger_timeout_s = 2.0

    def _append_scan_h5(self, filename, matrix, scan):
        """
        'Save Each Scan' for an .h5 file: the cumulative average after scan j
        replaces I and is appended as slice j-1 of the resizable 'scans'
        dataset, instead of the CSV path's whole extra file per scan.
        """
        import h5py

        matrix = np.asarray( matrix, dtype = 'float32' )

        with h5py.File(filename, 'a') as file_for_save:
            file_for_save['I'][...] = matrix

            if 'scans' not in file_for_save:
                file_for_save.create_dataset(
                    'scans',
                    shape = (0, ) + matrix.shape,
                    maxshape = (None, ) + matrix.shape,
                    chunks = (1, ) + matrix.shape,
                    dtype = 'float32'
                )

            scans = file_for_save['scans']
            scans.resize(scan, axis = 0)
            scans[scan - 1] = matrix

    def _acquire_point(self, scopes, conn, field, on_command = None):
        """
        Arms every scope and waits for the accumulation; a lost trigger is retried
        once, then the run stops through the normal Stop path (ramp-back and save).
        Returns False when the run is stopping.
        """
        for attempt in range(2):
            for scope in scopes:
                _arm(scope)
            result = _wait_armed(scopes, conn, self.trigger_timeout_s)
            while isinstance(result, tuple) and result[0] == 'command':
                if on_command is None:
                    self.command = result[1]
                else:
                    on_command(result[1])
                result = _wait_armed(scopes, conn, self.trigger_timeout_s)

            if result == 'done':
                return True
            if result == 'exit':
                self.command = 'exit'
                return False

            text = f'scope {result[1] + 1}: no trigger for {self.trigger_timeout_s:g} s at field {field} G'
            for index, scope in enumerate(scopes):
                if index != result[1]:
                    scope.oscilloscope_command(':STOP')
            if attempt == 1:
                conn.send( ('Message', text + '; second loss, stopping the measurement') )
                self.command = 'exit'
                return False
            conn.send( ('Message', text + '; retrying the point') )

    def exp_test_two_fields(self, conn, *parameters):
        """Check the two-range acquisition through native device test modes."""
        sys.argv = ['', 'test']
        import atomize.general_modules.general_functions as general
        general.test_flag = 'test'
        self.testing_two_fields = True
        self.exp_on(conn, *parameters)

    def scope_on(self, conn, scope_index, settings, script_test = False):
        """
        Scope-tab session: owns one scope between Connect and Disconnect, applies
        and reads back settings, and streams live traces. With script_test it only
        pushes the tab values through the test-mode setters and returns.
        """
        import traceback

        number = scope_index + 1
        if script_test:
            sys.argv = ['', 'test']
        scope = None
        closing = False
        try:
            import atomize.general_modules.general_functions as general
            if script_test:
                general.test_flag = 'test'
            import pyqtgraph as pg
            if scope_index == 0:
                import atomize.device_modules.Keysight_2000_Xseries as key
            else:
                import atomize.device_modules.Keysight_2000_Xseries_2 as key

            scope = key.Keysight_2000_Xseries()
            scope.oscilloscope_timeout('5 s')
            test_mode = scope.test_flag == 'test'
            state = dict(settings)
            setters = {
                'window_us': lambda v: scope.oscilloscope_timebase(f'{float(v)} us'),
                'offset_us': lambda v: scope.oscilloscope_horizontal_offset(f'{float(v)} us'),
                'ch1_scale_mv': lambda v: scope.oscilloscope_sensitivity('CH1', f'{int(v)} mV'),
                'ch1_offset_mv': lambda v: scope.oscilloscope_offset('CH1', f'{int(v)} mV'),
                'ch2_scale_mv': lambda v: scope.oscilloscope_sensitivity('CH2', f'{int(v)} mV'),
                'ch2_offset_mv': lambda v: scope.oscilloscope_offset('CH2', f'{int(v)} mV'),
            }
            getters = {
                'window_us': lambda: pg.siEval(scope.oscilloscope_timebase()) * 1e6,
                'offset_us': lambda: pg.siEval(scope.oscilloscope_horizontal_offset()) * 1e6,
                'ch1_scale_mv': lambda: pg.siEval(scope.oscilloscope_sensitivity('CH1')) * 1e3,
                'ch1_offset_mv': lambda: pg.siEval(scope.oscilloscope_offset('CH1')) * 1e3,
                'ch2_scale_mv': lambda: pg.siEval(scope.oscilloscope_sensitivity('CH2')) * 1e3,
                'ch2_offset_mv': lambda: pg.siEval(scope.oscilloscope_offset('CH2')) * 1e3,
            }

            if script_test:
                for name, setter in setters.items():
                    setter(settings[name])
                scope.oscilloscope_number_of_averages(int(settings['live_averages']))
                conn.send( ('test', f'scope {number} settings ok') )
                return

            conn.send( ('Settings', {name: getter() for name, getter in getters.items()}) )

            live = False
            averages_set = False
            losses = 0

            def handle(command):
                nonlocal live, averages_set, losses
                if command == 'exit':
                    return False
                kind = command[0]
                if kind == 'SET':
                    name, value = command[1], command[2]
                    state[name] = value
                    if name in setters:
                        setters[name](value)
                        conn.send( ('Settings', {name: getters[name]()}) )
                    elif name != 'num_osc':
                        averages_set = False
                        conn.send( ('Settings', {name: value}) )
                elif kind == 'READ':
                    conn.send( ('Settings', {name: getter() for name, getter in getters.items()}) )
                elif kind == 'LIVE':
                    live = bool(command[1])
                    averages_set = False
                    losses = 0
                elif kind == 'RUN':
                    scope.oscilloscope_run()
                elif kind == 'STOP':
                    scope.oscilloscope_stop()
                return True

            while True:
                if not live:
                    if conn.poll(0.2) and not handle(conn.recv()):
                        break
                    continue

                if conn.poll():
                    if not handle(conn.recv()):
                        break
                    continue

                if not averages_set:
                    scope.oscilloscope_number_of_averages(int(state['live_averages']))
                    averages_set = True
                _arm(scope)
                result = _wait_armed([scope], conn, float(state['trigger_timeout_s']))
                if result == 'exit':
                    break
                if isinstance(result, tuple) and result[0] == 'command':
                    scope.oscilloscope_stop()
                    if not handle(result[1]):
                        break
                    continue
                if isinstance(result, tuple):
                    losses += 1
                    conn.send( ('Message', f"scope {number}: no trigger for {float(state['trigger_timeout_s']):g} s") )
                    if losses >= 3:
                        live = False
                        conn.send( ('Live', 0) )
                        conn.send( ('Message', f'scope {number}: live stopped after three trigger losses') )
                    else:
                        conn.poll(1.0)
                    continue

                losses = 0
                if test_mode:
                    time.sleep(0.2)
                channels = ['CH1', 'CH2'] if scope_index == 0 and int(state['num_osc']) == 3 else ['CH1']
                for channel in channels:
                    y = scope.oscilloscope_get_curve(channel)
                    preamble = scope.oscilloscope_preamble(channel)
                    t = preamble[5] + np.arange(len(y)) * preamble[4]
                    general.plot_1d('TR Live', t, y, xname = 'Time', xscale = 's', yname = 'Signal', yscale = 'V', label = f'Scope {number} {channel}')

            closing = True

        except SystemExit:
            pass
        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )
        finally:
            if scope is not None:
                try:
                    scope.oscilloscope_stop()
                    scope.close_connection()
                except Exception:
                    pass
            if closing:
                conn.send( ('', f'scope {number} session closed') )

    def exp_on(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12):
        """
        function that contains experimental script
        """
        # [                  1,                 2,                  3,                    4, ]
        #self.cur_offres_field, self.cur_exp_name, self.cur_end_field, self.cur_start_field, 
        # [          5,                   6,              7,           8,                9,               10,             11,       12 ]
        #self.cur_step, self.cur_ave_offres, self.cur_scan, self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, self.two_side,

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import traceback

        try:
            if self.testing_two_fields and self.half_field is None:
                raise ValueError('Half-field parameters are required for the two-range test.')
            import datetime
            import atomize.general_modules.general_functions as general
            import atomize.device_modules.Keysight_2000_Xseries as key
            import atomize.device_modules.Keysight_2000_Xseries_2 as key2
            import atomize.device_modules.BH_15 as itc
            import pyqtgraph as pg
            #import atomize.device_modules.ITC_FC as itc
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.Agilent_53131a as ag
            import atomize.general_modules.csv_opener_saver as openfile

            w = 30
            file_handler = openfile.Saver_Opener()
            process = 'None'
            ag53131a = ag.Agilent_53131a()
            ls335 = ls.Lakeshore_335()
            a2012 = key.Keysight_2000_Xseries()
            a2012.oscilloscope_timeout('5 s')
            #bh15 = itc.ITC_FC()
            bh15 = itc.BH_15()
            
            ag53131a.freq_counter_digits(8)
            ag53131a.freq_counter_stop_mode('Digits')

            if p9 == 1:
                a2012.oscilloscope_trigger_channel(p10)
                a2012.oscilloscope_acquisition_type('Average')
                a2012.oscilloscope_run_stop()

            else:
                a2012_2 = key2.Keysight_2000_Xseries()
                a2012_2.oscilloscope_timeout('5 s')
                
                a2012.oscilloscope_trigger_channel(p10)
                a2012.oscilloscope_acquisition_type('Average')
                a2012.oscilloscope_run_stop()

                a2012_2.oscilloscope_trigger_channel('Ext')
                a2012_2.oscilloscope_acquisition_type('Average')
                a2012_2.oscilloscope_run_stop()

            scopes = [a2012] if p9 == 1 else [a2012, a2012_2]

            a2012.oscilloscope_record_length( 4000 )
            try:
                real_length = a2012.oscilloscope_record_length( )
            except ZeroDivisionError:
                general.message('Incorrect Trigger Channel')

            ##t_res = round( a2012.oscilloscope_timebase() / real_length, 7 )    # in us
            ##t_res_rough = round( t_res, 3 )
            t_res = a2012.oscilloscope_time_resolution()
            t_step = float(f"{pg.siEval(t_res):.4g}")

            ##real_length = 4000
            if p9 > 1:
                a2012_2.oscilloscope_record_length( 4000 )
                try:
                    real_length_2 = a2012_2.oscilloscope_record_length( )
                except ZeroDivisionError:
                    general.message('Incorrect Trigger Channel')                
                #print(a2012_2.oscilloscope_record_length( ))
                #t_res_2 = round( a2012_2.oscilloscope_timebase() / real_length, 7 ) # in us
                #t_res_2_rough = round( t_res_2, 3 )
                t_res_2 = a2012_2.oscilloscope_time_resolution()
                t_step_2 = float(f"{pg.siEval(t_res_2):.4g}")

            if self.half_field is not None:
                from atomize.control_center.tr_two_fields import acquire
                lengths = [real_length] if p9 == 1 else [real_length, real_length_2]
                steps = [t_step] if p9 == 1 else [t_step, t_step_2]
                resolutions = [t_res] if p9 == 1 else [t_res, t_res_2]
                acquire(self, conn, general, file_handler, bh15, scopes, ls335, ag53131a,
                        resolutions, lengths, steps, (p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12),
                        test_mode=self.testing_two_fields)
                return

            # parameters for initial initialization
            field = 100
            START_FIELD = p4
            END_FIELD = p3
            FIELD_STEP = p5
            OFFRES_FIELD = p1
            initialization_step = 10
            SCANS = p7
            points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1

            #bh15.magnet_setup( 100, FIELD_STEP)

            if p9 == 1:
                data = np.zeros( (2, real_length, points + 1) )
            elif p9 == 2:
                data = np.zeros( (2, real_length, points + 1) )
                data_2 = np.zeros( (2, real_length_2, points + 1) )
            else:
                data = np.zeros( (3, real_length, points + 1) )
                data_2 = np.zeros( (2, real_length_2, points + 1) )

            # row 0 of the saved matrix is the off-resonance trace; the axis
            # labels the sweep rows that follow it, from START_FIELD up
            sweep_axis = START_FIELD + np.arange(points + 1) * FIELD_STEP
            axes_2d = ( np.arange(real_length) * t_step, sweep_axis )
            axes_units_2d = ( 's', 'G' )
            if p9 > 1:
                axes_2d_2 = ( np.arange(real_length_2) * t_step_2, sweep_axis )
            
            temp_start = str( ls335.tc_temperature('A') )

            # Oscilloscopes bugs
            #a2012.oscilloscope_number_of_averages(2)
            #if p9 > 1:
            #    a2012_2.oscilloscope_number_of_averages(2)

            #a2012.oscilloscope_start_acquisition()
            #if p9 > 1:
            #    a2012_2.oscilloscope_start_acquisition()
            
            #if p9 == 1:
            #    y = a2012.oscilloscope_get_curve('CH1')

            #elif p9 == 2:
            #    y = a2012.oscilloscope_get_curve('CH1')
            #    y2 = a2012_2.oscilloscope_get_curve('CH1')

            conn.send(('Open', ''))
            
            while True:
                if conn.poll():
                    msg = conn.recv()
                    if msg.startswith('FL'):
                        file_save_1 = msg[2:]
                        file_handler.save_cancelled = file_save_1 in (None, '', 'None')
                        break
                general.wait('200 ms')

            # the derived files follow whatever format the chosen name carries
            base_name, ext = os.path.splitext(file_save_1)

            if p9 == 1:
                pass
            elif p9 == 2:
                file_save_2 = f"{base_name}_osc2{ext}"
            elif p9 == 3:
                file_save_2 = f"{base_name}_osc2{ext}"
                file_save_3 = f"{base_name}_pulse{ext}"

            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the script
            while self.command != 'exit':
                # Start of experiment
                while field < OFFRES_FIELD:
                    field = bh15.magnet_field( field + initialization_step)
                    field = field + initialization_step
                    general.wait('30 ms')

                # Data saving
                j = 1
                if p9 == 1:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )
                    
                    file_handler.save_header(file_save_1, header = header, mode = 'w')
                elif p9 == 2:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    file_handler.save_header(file_save_1, header = header, mode = 'w')
                    file_handler.save_header(file_save_2, header = header_2, mode = 'w')

                elif p9 == 3:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temp Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temp End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    file_handler.save_header(file_save_1, header = header, mode = 'w')
                    file_handler.save_header(file_save_2, header = header_2, mode = 'w')
                    file_handler.save_header(file_save_3, header = header, mode = 'w')

                while j <= SCANS:
                    if self.command == 'exit':
                        break

                    field = bh15.magnet_field( OFFRES_FIELD )
                    field = OFFRES_FIELD

                    general.wait('4000 ms')

                    a2012.oscilloscope_number_of_averages(p6)
                    if p9 > 1:
                        a2012_2.oscilloscope_number_of_averages(p6)
                    
                    if not self._acquire_point(scopes, conn, OFFRES_FIELD):
                        break

                    ##ch_time = np.random.randint(250, 500, 1)
                    if p9 == 1:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                        
                    elif p9 == 2:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data_2[0, :, 0] = ( data_2[0, :, 0] * (j - 1) + y2 ) / j
                        data_2[1, :, 0] = ( data_2[0, :, 0] - data_2[0, :, 0] )
                        data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                    elif p9 == 3:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        y3 = a2012.oscilloscope_get_curve('CH2')
                        ##y3 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[2, :, 0] = ( data[2, :, 0] * (j - 1) + y3 ) / j

                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data_2[0, :, 0] = ( data_2[0, :, 0] * (j - 1) + y2 ) / j
                        data_2[1, :, 0] = ( data_2[1, :, 0] - data_2[0, :, 0] )
                        data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                    while field < START_FIELD:
                        field = bh15.magnet_field( field + initialization_step)
                        general.wait('30 ms')
                        field = field + initialization_step

                    field = bh15.magnet_field( START_FIELD )
                    field = START_FIELD

                    general.wait('4000 ms')

                    a2012.oscilloscope_number_of_averages(p8)
                    if p9 > 1:
                        a2012_2.oscilloscope_number_of_averages(p8)

                    i = 0

                    if p12 == 0:
                        j = j
                    elif p12 == 1:
                        j = 2*j - 1

                    while field <= END_FIELD:
                        
                        if self.command == 'exit':
                            break

                        general.wait('80 ms')

                        if not self._acquire_point(scopes, conn, field):
                            break

                        field_next = round( (FIELD_STEP + field), 3 )
                        bh15.magnet_field(field_next)


                        ##ch_time = np.random.randint(250, 500, 1)
                        if p9 == 1:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            
                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        elif p9 == 2:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y2 = a2012_2.oscilloscope_get_curve('CH1')
                            ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data_2[0, :, i+1] = ( data_2[0, :, i+1] * (j - 1) + y2) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                            data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                            data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                        elif p9 == 3:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y2 = a2012_2.oscilloscope_get_curve('CH1')
                            ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y3 = a2012.oscilloscope_get_curve('CH2')
                            ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data_2[0, :, i+1] = ( data_2[0, :, i+1] * (j - 1) + y2) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                            data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                            data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )
                            data[2, :, i+1] = ( data[2, :, i+1] * (j - 1) + y3 ) / j

                        #start_time = time.time()

                        if p12 == 0:
                            conn.send( ('Status', int( 100 * ((j - 1) * points + i + 1) / points / SCANS)) )
                        elif p12 == 1:
                            conn.send( ('Status', int( 100 * ((j - 1) * points + i + 1) / points / SCANS / 2)) )


                        process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_step), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                        if p9 > 1:

                            process = general.plot_2d( f"{p2}_2", data_2[:,:,1:points+1], xname='Time', start_step=( (0, t_step_2), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                        #general.message( str( time.time() - start_time ) )

                        field = field_next

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                        i += 1

                    if p12 == 1:

                        field = round( (-FIELD_STEP + field), 3 )
                        bh15.magnet_field(field)

                        while i > 0:
                            
                            if self.command == 'exit':
                                break

                            i -= 1
                            general.wait('80 ms')

                            if not self._acquire_point(scopes, conn, field):
                                break

                            if i > 0:
                                field_next = round( (-FIELD_STEP + field), 3 )
                                bh15.magnet_field(field_next)
                            else:
                                field_next = field

                            ##ch_time = np.random.randint(250, 500, 1)
                            if p9 == 1:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                            elif p9 == 2:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y2 = a2012_2.oscilloscope_get_curve('CH1')
                                ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data_2[0, :, i+1] = ( data_2[0, :, i+1] * j + y2) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                                data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                                data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                            elif p9 == 3:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y2 = a2012_2.oscilloscope_get_curve('CH1')
                                ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y3 = a2012.oscilloscope_get_curve('CH2')
                                ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data_2[0, :, i+1] = ( data_2[0, :, i+1] * j + y2) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                                data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                                data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )
                                data[2, :, i+1] = ( data[2, :, i+1] * j + y3 ) / ( j + 1 )

                            #start_time = time.time()
                            conn.send( ('Status', int( 100 * (( j ) * points - i + points) / points / SCANS / 2)) )

                            process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_step), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                            if p9 > 1:

                                process = general.plot_2d( f"{p2}_2", data_2[:,:,1:points+1],  xname='Time', start_step=( (0, t_step_2), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                            field = field_next

                            # check our polling data
                            if self.command[0:2] == 'SC':
                                SCANS = int( self.command[2:] )
                                self.command = 'start'
                            elif self.command == 'exit':
                                break
                            
                            if conn.poll() == True:
                                self.command = conn.recv()


                    if j != SCANS:
                        while field > OFFRES_FIELD:
                            field = bh15.magnet_field( field - initialization_step)
                            field = field - initialization_step
                            general.wait('30 ms')
                    
                        field = bh15.magnet_field( OFFRES_FIELD )
                        field = OFFRES_FIELD
                    
                    if p9 == 1 and p11 == 1 and p12 == 0:
                        # the chosen name decides the format; a cancelled dialog
                        # ('None') falls through to the guarded CSV calls
                        if ext.lower() == '.h5':
                            if j == 1:
                                file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header, axes = axes_2d, axes_units = axes_units_2d)
                            self._append_scan_h5(file_save_1, np.transpose( data[0, :, :] ), j)
                        elif j == 1:
                            file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                        else:
                            file_save_j = f"{base_name}_{j}_scans{ext}"
                            file_handler.save_data(file_save_j, np.transpose( data[0, :, :] ), header = header)

                    j += 1

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':
                #general.message(f'Script {p2} finished')
                
                temp_end = str( ls335.tc_temperature('B') )
                if p9 == 1 and p11 == 0:
                    ##t_res = 1
                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header, axes = axes_2d, axes_units = axes_units_2d)
                elif p9 == 2:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header, axes = axes_2d, axes_units = axes_units_2d)
                    file_handler.save_data(file_save_2, np.transpose( data_2[0, :, :] ), header = header_2, axes = axes_2d_2, axes_units = axes_units_2d)
                elif p9 == 3:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header, axes = axes_2d, axes_units = axes_units_2d)
                    file_handler.save_data(file_save_2, np.transpose( data_2[0, :, :] ), header = header_2, axes = axes_2d_2, axes_units = axes_units_2d)
                    file_handler.save_data(file_save_3, np.transpose( data[2, :, :] ), header = header, axes = axes_2d, axes_units = axes_units_2d)

                while field > OFFRES_FIELD:
                    field = bh15.magnet_field( field - initialization_step)
                    field = field - initialization_step
                field = bh15.magnet_field( OFFRES_FIELD )
                field = OFFRES_FIELD

                conn.send( ('', f'Script {p2} finished') )
                general.wait('200 ms')
                conn.close()

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

    def exp_test(self, conn, p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12):
        """
        function that contains experimental script
        """
        # [                  1,                 2,                  3,                    4, ]
        #self.cur_offres_field, self.cur_exp_name, self.cur_end_field, self.cur_start_field, 
        # [          5,                   6,              7,           8,                9,               10,             11,       12 ]
        #self.cur_step, self.cur_ave_offres, self.cur_scan, self.cur_ave, self.cur_num_osc, self.cur_trig_ch, self.save_scan, self.two_side,

        # should be inside dig_on() function;
        # freezing after digitizer restart otherwise
        import traceback

        sys.argv = ['', 'test']

        try:
            import datetime
            import atomize.general_modules.general_functions as general
            general.test_flag = 'test'
            import atomize.device_modules.Keysight_2000_Xseries as key
            import atomize.device_modules.Keysight_2000_Xseries_2 as key2
            import atomize.device_modules.BH_15 as itc
            import pyqtgraph as pg
            #import atomize.device_modules.ITC_FC as itc
            import atomize.device_modules.Lakeshore_335 as ls
            import atomize.device_modules.Agilent_53131a as ag
            import atomize.general_modules.csv_opener_saver as openfile

            w = 30
            file_handler = openfile.Saver_Opener()
            process = 'None'
            ag53131a = ag.Agilent_53131a()
            ls335 = ls.Lakeshore_335()
            a2012 = key.Keysight_2000_Xseries()
            a2012.oscilloscope_timeout('5 s')
            #bh15 = itc.ITC_FC()
            bh15 = itc.BH_15()
            
            ag53131a.freq_counter_digits(8)
            ag53131a.freq_counter_stop_mode('Digits')

            if p9 == 1:
                a2012.oscilloscope_trigger_channel(p10)
                a2012.oscilloscope_acquisition_type('Average')
                a2012.oscilloscope_run_stop()

            else:
                a2012_2 = key2.Keysight_2000_Xseries()
                a2012_2.oscilloscope_timeout('5 s')
                
                a2012.oscilloscope_trigger_channel(p10)
                a2012.oscilloscope_acquisition_type('Average')
                a2012.oscilloscope_run_stop()

                a2012_2.oscilloscope_trigger_channel('Ext')
                a2012_2.oscilloscope_acquisition_type('Average')
                a2012_2.oscilloscope_run_stop()

            scopes = [a2012] if p9 == 1 else [a2012, a2012_2]

            a2012.oscilloscope_record_length( 4000 )
            try:
                real_length = a2012.oscilloscope_record_length( )
            except ZeroDivisionError:
                general.message('Incorrect Trigger Channel')

            ##t_res = round( a2012.oscilloscope_timebase() / real_length, 7 )    # in us
            ##t_res_rough = round( t_res, 3 )
            t_res = a2012.oscilloscope_time_resolution()
            t_step = float(f"{pg.siEval(t_res):.4g}")

            ##real_length = 4000
            if p9 > 1:
                a2012_2.oscilloscope_record_length( 4000 )
                try:
                    real_length_2 = a2012_2.oscilloscope_record_length( )
                except ZeroDivisionError:
                    general.message('Incorrect Trigger Channel')                
                #print(a2012_2.oscilloscope_record_length( ))
                #t_res_2 = round( a2012_2.oscilloscope_timebase() / real_length, 7 ) # in us
                #t_res_2_rough = round( t_res_2, 3 )
                t_res_2 = a2012_2.oscilloscope_time_resolution()
                t_step_2 = float(f"{pg.siEval(t_res_2):.4g}")

            # parameters for initial initialization
            field = 100
            START_FIELD = p4
            END_FIELD = p3
            FIELD_STEP = p5
            OFFRES_FIELD = p1
            initialization_step = 10
            SCANS = p7
            points = int( (END_FIELD - START_FIELD) / FIELD_STEP ) + 1

            #bh15.magnet_setup( 100, FIELD_STEP)

            if p9 == 1:
                data = np.zeros( (2, real_length, points + 1) )
            elif p9 == 2:
                data = np.zeros( (2, real_length, points + 1) )
                data_2 = np.zeros( (2, real_length_2, points + 1) )
            else:
                data = np.zeros( (3, real_length, points + 1) )
                data_2 = np.zeros( (2, real_length_2, points + 1) )
            
            temp_start = str( ls335.tc_temperature('A') )

            # Oscilloscopes bugs
            #a2012.oscilloscope_number_of_averages(2)
            #if p9 > 1:
            #    a2012_2.oscilloscope_number_of_averages(2)

            #a2012.oscilloscope_start_acquisition()
            #if p9 > 1:
            #    a2012_2.oscilloscope_start_acquisition()
            
            #if p9 == 1:
            #    y = a2012.oscilloscope_get_curve('CH1')

            #elif p9 == 2:
            #    y = a2012.oscilloscope_get_curve('CH1')
            #    y2 = a2012_2.oscilloscope_get_curve('CH1')

            #conn.send(('Open', ''))
            
            #while True:
            #    if conn.poll():
            #        msg = conn.recv()
            #        if msg.startswith('FL'):
            #            file_save_1 = msg[2:]
            #            break
            #    general.wait('200 ms')

            #if p9 == 1:
            #    pass
            #elif p9 == 2:
            #    file_save_2 = f"{file_save_1[0:-4]}_osc2.csv"
            #elif p9 == 3:
            #    file_save_2 = f"{file_save_1[0:-4]}_osc2.csv"
            #    file_save_3 = f"{file_save_1[0:-4]}_pulse.csv"

            # the idea of automatic and dynamic changing is
            # sending a new value of repetition rate via self.command
            # in each cycle we will check the current value of self.command
            # self.command = 'exit' will stop the script
            while self.command != 'exit':
                # Start of experiment
                while field < OFFRES_FIELD:
                    field = bh15.magnet_field( field + initialization_step)
                    field = field + initialization_step
                    general.wait('30 ms')

                # Data saving
                #j = 1
                if p9 == 1:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )
                    
                    #file_handler.save_header(file_save_1, header = header, mode = 'w')
                elif p9 == 2:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    #file_handler.save_header(file_save_1, header = header, mode = 'w')
                    #file_handler.save_header(file_save_2, header = header_2, mode = 'w')

                elif p9 == 3:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temp Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temp End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    #file_handler.save_header(file_save_1, header = header, mode = 'w')
                    #file_handler.save_header(file_save_2, header = header_2, mode = 'w')
                    #file_handler.save_header(file_save_3, header = header, mode = 'w')

                for j in general.scans(SCANS):
                    if self.command == 'exit':
                        break

                    field = bh15.magnet_field( OFFRES_FIELD )
                    field = OFFRES_FIELD

                    general.wait('4000 ms')

                    a2012.oscilloscope_number_of_averages(p6)
                    if p9 > 1:
                        a2012_2.oscilloscope_number_of_averages(p6)
                    
                    if not self._acquire_point(scopes, conn, OFFRES_FIELD):
                        break

                    ##ch_time = np.random.randint(250, 500, 1)
                    if p9 == 1:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                        
                    elif p9 == 2:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data_2[0, :, 0] = ( data_2[0, :, 0] * (j - 1) + y2 ) / j
                        data_2[1, :, 0] = ( data_2[0, :, 0] - data_2[0, :, 0] )
                        data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                    elif p9 == 3:
                        y = a2012.oscilloscope_get_curve('CH1')
                        ##y = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[0, :, 0] = ( data[0, :, 0] * (j - 1) + y ) / j
                        data[1, :, 0] = ( data[0, :, 0] - data[0, :, 0] )
                        data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        y3 = a2012.oscilloscope_get_curve('CH2')
                        ##y3 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data[2, :, 0] = ( data[2, :, 0] * (j - 1) + y3 ) / j

                        y2 = a2012_2.oscilloscope_get_curve('CH1')
                        ##y2 = 1 + 10*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))
                        data_2[0, :, 0] = ( data_2[0, :, 0] * (j - 1) + y2 ) / j
                        data_2[1, :, 0] = ( data_2[1, :, 0] - data_2[0, :, 0] )
                        data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                    while field < START_FIELD:
                        field = bh15.magnet_field( field + initialization_step)
                        general.wait('30 ms')
                        field = field + initialization_step

                    field = bh15.magnet_field( START_FIELD )
                    field = START_FIELD

                    general.wait('4000 ms')

                    a2012.oscilloscope_number_of_averages(p8)
                    if p9 > 1:
                        a2012_2.oscilloscope_number_of_averages(p8)

                    i = 0

                    if p12 == 0:
                        j = j
                    elif p12 == 1:
                        j = 2*j - 1

                    while field <= END_FIELD:
                        
                        if self.command == 'exit':
                            break

                        general.wait('80 ms')

                        if not self._acquire_point(scopes, conn, field):
                            break

                        field_next = round( (FIELD_STEP + field), 3 )
                        bh15.magnet_field(field_next)


                        ##ch_time = np.random.randint(250, 500, 1)
                        if p9 == 1:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            
                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                        elif p9 == 2:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y2 = a2012_2.oscilloscope_get_curve('CH1')
                            ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data_2[0, :, i+1] = ( data_2[0, :, i+1] * (j - 1) + y2) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                            data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                            data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                        elif p9 == 3:
                            y = a2012.oscilloscope_get_curve('CH1')
                            ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y2 = a2012_2.oscilloscope_get_curve('CH1')
                            ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                            y3 = a2012.oscilloscope_get_curve('CH2')
                            ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                            data[0, :, i+1] = ( data[0, :, i+1] * (j - 1) + y ) / j
                            data_2[0, :, i+1] = ( data_2[0, :, i+1] * (j - 1) + y2) / j
                            data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                            data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                            data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                            data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )
                            data[2, :, i+1] = ( data[2, :, i+1] * (j - 1) + y3 ) / j

                        #start_time = time.time()

                        #if p12 == 0:
                        #    conn.send( ('Status', int( 100 * ((j - 1) * points + i + 1) / points / SCANS)) )
                        #elif p12 == 1:
                        #    conn.send( ('Status', int( 100 * ((j - 1) * points + i + 1) / points / SCANS / 2)) )


                        process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_step), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                        if p9 > 1:

                            process = general.plot_2d( f"{p2}_2", data_2[:,:,1:points+1], xname='Time', start_step=( (0, t_step_2), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                        #general.message( str( time.time() - start_time ) )

                        field = field_next

                        # check our polling data
                        if self.command[0:2] == 'SC':
                            SCANS = int( self.command[2:] )
                            self.command = 'start'
                        elif self.command == 'exit':
                            break
                        
                        if conn.poll() == True:
                            self.command = conn.recv()

                        i += 1

                    if p12 == 1:

                        field = round( (-FIELD_STEP + field), 3 )
                        bh15.magnet_field(field)

                        while i > 0:
                            
                            if self.command == 'exit':
                                break

                            i -= 1
                            general.wait('80 ms')

                            if not self._acquire_point(scopes, conn, field):
                                break

                            if i > 0:
                                field_next = round( (-FIELD_STEP + field), 3 )
                                bh15.magnet_field(field_next)
                            else:
                                field_next = field

                            ##ch_time = np.random.randint(250, 500, 1)
                            if p9 == 1:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )

                            elif p9 == 2:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y2 = a2012_2.oscilloscope_get_curve('CH1')
                                ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data_2[0, :, i+1] = ( data_2[0, :, i+1] * j + y2) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                                data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                                data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )

                            elif p9 == 3:
                                y = a2012.oscilloscope_get_curve('CH1')
                                ##y = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y2 = a2012_2.oscilloscope_get_curve('CH1')
                                ##y2 = 1 + 100*np.exp(-axis_x/ch_time) + 7*np.random.normal(size = (4000))
                                y3 = a2012.oscilloscope_get_curve('CH2')
                                ##y3 = 1 + 100*np.exp(-axis_x/ch_time) + 50*np.random.normal(size = (4000))

                                data[0, :, i+1] = ( data[0, :, i+1] * j + y ) / ( j + 1 )
                                data_2[0, :, i+1] = ( data_2[0, :, i+1] * j + y2) / ( j + 1 )
                                data[1, :, i+1] = ( data[0, :, i+1] - data[0, :, 0] )
                                data[1, :, :] = ( data[1, :, :] - data[1, 0, :] )
                                data_2[1, :, i+1] = ( data_2[0, :, i+1] - data_2[0, :, 0] )
                                data_2[1, :, :] = ( data_2[1, :, :] - data_2[1, 0, :] )
                                data[2, :, i+1] = ( data[2, :, i+1] * j + y3 ) / ( j + 1 )

                            #start_time = time.time()
                            #conn.send( ('Status', int( 100 * (( j ) * points - i + points) / points / SCANS / 2)) )

                            process = general.plot_2d( p2, data[:,:,1:points+1],  xname='Time', start_step=( (0, t_step), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                            if p9 > 1:

                                process = general.plot_2d( f"{p2}_2", data_2[:,:,1:points+1],  xname='Time', start_step=( (0, t_step_2), (START_FIELD, FIELD_STEP) ), xscale='s', yname='Field', yscale='G', zname='Intensity', zscale='V', pr = process, text = 'S / F: ' + str(j) + ' / ' + str(field))

                            field = field_next

                            # check our polling data
                            if self.command[0:2] == 'SC':
                                SCANS = int( self.command[2:] )
                                self.command = 'start'
                            elif self.command == 'exit':
                                break
                            
                            if conn.poll() == True:
                                self.command = conn.recv()


                    if j != SCANS:
                        while field > OFFRES_FIELD:
                            field = bh15.magnet_field( field - initialization_step)
                            field = field - initialization_step
                            general.wait('30 ms')
                    
                        field = bh15.magnet_field( OFFRES_FIELD )
                        field = OFFRES_FIELD
                    
                    #if p9 == 1 and p11 == 1 and p12 == 0:
                        #if j == 1:
                            #file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                        #else:
                            #file_save_j = file_save_1.split('.csv')[0] + f'_{j}_scans.csv'
                            #file_handler.save_data(file_save_j, np.transpose( data[0, :, :] ), header = header)

                    #j += 1

                # finish succesfully
                self.command = 'exit'

            if self.command == 'exit':
                #general.message(f'Script {p2} finished')
                
                temp_end = str( ls335.tc_temperature('B') )
                if p9 == 1 and p11 == 0:
                    ##t_res = 1
                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    #file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                elif p9 == 2:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    #file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                    #file_handler.save_data(file_save_2, np.transpose( data_2[0, :, :] ), header = header_2)
                elif p9 == 3:

                    now = datetime.datetime.now().strftime("%d-%m-%Y %H-%M-%S")
                    temp_end = str( ls335.tc_temperature('A') )

                    header = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    header_2 = (
                        f"{'Date:':<{w}} {now}\n"
                        f"{'Experiment:':<{w}} Time Resolved EPR Spectrum\n"
                        f"{'Start Field:':<{w}} {START_FIELD} G\n"
                        f"{'End Field:':<{w}} {END_FIELD} G\n"
                        f"{'Field Step:':<{w}} {FIELD_STEP} G\n"
                        f"{'Off-Resonance Field:':<{w}} {OFFRES_FIELD} G\n"
                        f"{'Off-Resonance Averages:':<{w}} {p6}\n"
                        f"{'Number of Averages:':<{w}} {p8}\n"
                        f"{'Number of Scans:':<{w}} {SCANS}\n"
                        f"{'Temperature Start Exp:':<{w}} {temp_start} K\n"
                        f"{'Temperature End Exp:':<{w}} {temp_end} K\n"
                        f"{'Temperature Cernox:':<{w}} {ls335.tc_temperature('B')} K\n"
                        f"{'Record Length:':<{w}} {real_length} Points\n"
                        f"{'Time Resolution:':<{w}} {t_res_2}\n"
                        f"{'Frequency:':<{w}} {ag53131a.freq_counter_frequency('CH3')}\n"
                        f"{'-'*50}\n"
                        f"2D Data"
                    )

                    #file_handler.save_data(file_save_1, np.transpose( data[0, :, :] ), header = header)
                    #file_handler.save_data(file_save_2, np.transpose( data_2[0, :, :] ), header = header_2)
                    #file_handler.save_data(file_save_3, np.transpose( data[2, :, :] ), header = header)

                while field > OFFRES_FIELD:
                    field = bh15.magnet_field( field - initialization_step)
                    field = field - initialization_step
                field = bh15.magnet_field( OFFRES_FIELD )
                field = OFFRES_FIELD

                conn.send( ('test', f'Script {p2} finished') )
                conn.close()

        except BaseException as e:
            exc_info = f"{type(e)} \n{str(e)} \n{traceback.format_exc()}"
            conn.send( ('Error', exc_info) )

def main():
    """
    A function to run the main window of the programm.
    """
    app = QApplication(sys.argv)
    from atomize.general_modules.gui_style import apply_app_style
    apply_app_style(app, app_id='Atomize.ITC.TRControl', desktop='tr')
    main = MainWindow()
    main.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
