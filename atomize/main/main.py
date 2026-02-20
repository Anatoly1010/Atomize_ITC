import os
import sys
import time
import ctypes
import threading
from pathlib import Path
from PyQt6 import QtWidgets, uic, QtCore, QtGui
from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton, QComboBox, QCheckBox, QVBoxLayout, QApplication
from PyQt6.QtGui import QColor
from atomize.main.main_window import MainWindow
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

###
# All modifications can be found with # mod
###

class MainExtended(MainWindow):

    def __init__(self, *args, **kwargs):
        """
        A function for connecting actions and creating a main window.
        """
        super().__init__(*args, **kwargs)
        path_to_main = Path(__file__).parent
        self.path_to_main = os.path.join(path_to_main, '..', '..', 'libs')

        self.process_tr = QtCore.QProcess(self)
        self.process_osc = QtCore.QProcess(self)
        self.process_osc2 = QtCore.QProcess(self)
        self.process_cw = QtCore.QProcess(self)
        self.process_temp = QtCore.QProcess(self)
        self.process_field = QtCore.QProcess(self)
        self.process_mw = QtCore.QProcess(self)
        self.process_tune_preset = QtCore.QProcess(self)
        self.process_phasing = QtCore.QProcess(self)
        self.process_awg_phasing = QtCore.QProcess(self)
        self.process_t2 = QtCore.QProcess(self)
        self.process_t1 = QtCore.QProcess(self)
        self.process_ed = QtCore.QProcess(self)
        self.process_eseem = QtCore.QProcess(self)

        self.all_processes = [self.process_tr, self.process_osc, 
            self.process_osc2, self.process_cw, self.process_temp, 
            self.process_field, self.process_mw, self.process_tune_preset, 
            self.process_phasing, self.process_awg_phasing, self.process_t2, 
            self.process_t1, self.process_ed, self.process_eseem
        ]

        for process in self.all_processes:
            process.readyReadStandardOutput.connect(self.handle_output_control_center)

        if self.system == 'Windows':
            for process in self.all_processes:
                process.setProgram('python.exe')
        elif self.system == 'Linux':
            for process in self.all_processes:
                process.setProgram('python3')

        self.set_control_center()

        self.skip_lines = 0

    def handle_output_control_center(self):


        sending_process = self.sender()
        if not sending_process:
            return

        raw_data = sending_process.readAllStandardOutput().data().decode(self.system_encoding, errors='replace')
        if raw_data.startswith("print "):
            msg = raw_data[6:].strip()
            self.text_errors.appendPlainText(msg)
        # Insys stdOut
        elif raw_data.startswith("before "):
            self.skip_lines = 1
        elif 'ret = 0' in raw_data:
            self.skip_lines = 0
        elif raw_data.startswith("closing "):
            pass
        elif self.skip_lines != 1:
            self.text_errors.appendPlainText(raw_data[:-1])

    # control tab design
    def set_control_center(self):
        
        tab3 = QWidget()
        main_layout = QVBoxLayout(tab3)
        gridlayout = QGridLayout()
        gridlayout.setContentsMargins(5, 7, 5, 5)
        main_layout.addLayout(gridlayout)

        self.tabwidget.addTab(tab3, "EPR Endstation Control")
        self.tabwidget.tabBar().setTabTextColor(2, QColor(193, 202, 227))
        self.tabwidget.tabBar().setStyleSheet(" font-weight: bold ") 

        button_list = []

        button_name_1 = ["CW EPR", "TR EPR", "2012A; IP x.2.21", "2012A_2; IP x.2.22", "Set Temperature", "Set MF"]
        button_name_2 = ["Pulsed MW Bridge", "", "RECT Channel", "AWG Channel"]
        button_name_3 = ["Resonator Tuning", "T2 Measurement", "T1 Measurement", "ED Spectrum", "3pESEEM"]

        actions_1 = [self.start_cw, self.start_tr_control, self.start_osc_control, self.start_osc_control_2, self.start_temp_control, self.start_field_control]
        actions_2 = [self.start_mw_control, None, self.start_rect_phasing, self.start_awg_phasing]
        actions_3 = [self.start_tune_preset, self.start_t2_preset, self.start_t1_preset, self.start_ed_preset, self.start_eseem_preset]

        columns_data = [(button_name_1, actions_1, 1), (button_name_2, actions_2, 2), (button_name_3, actions_3, 3)]

        for names, actions, col_idx in columns_data:
            for row_idx, name in enumerate(names):
                if not name:
                    continue
                
                btn = QPushButton(name)
                btn.setFixedSize(140, 40)
                btn.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } QPushButton:pressed {background-color: rgb(211, 194, 78); border-style: inset; font-weight: bold; }")

                if actions and row_idx < len(actions) and actions[row_idx]:
                    btn.clicked.connect(actions[row_idx])
                    
                gridlayout.addWidget(btn, row_idx , col_idx)
                button_list.append(btn)

        # Open Script:
        label = QLabel("Open Script:")
        label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        label.setFixedWidth(100)
        gridlayout.addWidget(label, 0, 4)

        combo_items = [" Tuning", " T2 Echo Shape", " ED Spectrum", " ESEEM Echo Shape"]
        self.script_chooser = QComboBox()
        self.script_chooser.addItems(combo_items)
        self.script_chooser.setFixedSize(140, 40)
        gridlayout.addWidget(self.script_chooser, 0, 5)
        self.script_chooser.setStyleSheet("""
                QComboBox { 
                    background-color: rgb(63, 63, 97);
                    color: rgb(193, 202, 227); 
                    border: 1px solid rgb(43, 43, 77);
                    border-radius: 4px;
                    padding: 0px 10px 0px 10px; 
                    font-weight: bold;
                }
                
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 22px;
                    border-left: 1px solid rgb(43, 43, 77); 
                    border-top-right-radius: 3px;
                    border-bottom-right-radius: 3px;
                }

                QComboBox::down-arrow {
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 4px solid rgb(193, 202, 227);
                    width: 0;
                    height: 0;
                    margin-top: 1px; 
                    margin-right: 2px;
                }

                QComboBox QAbstractItemView {
                    background-color: rgb(42, 42, 64);
                    color: rgb(193, 202, 227);
                    selection-background-color: rgb(63, 63, 97);
                    selection-color: rgb(211, 194, 78);
                    border: 1px solid rgb(63, 63, 97);
                    outline: none;
                }
            """)

        self.script_chooser.currentIndexChanged.connect(self.script_open_combo)
        self.script = self.text_to_script_name( self.script_chooser.currentText() )
        # preopen script
        #self.open_file( self.script )

        # Test option
        label_2 = QLabel("Test Scripts:")
        label_2.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        label_2.setFixedWidth(100)
        gridlayout.addWidget(label_2, 1, 4)

        self.checkTests = QCheckBox("")
        gridlayout.addWidget(self.checkTests, 1, 5)
        self.checkTests.setStyleSheet("""
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

        self.checkTests.setFixedSize(140, 40)
        self.checkTests.setChecked(True)
        self.checkTests.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)


        #gridlayout.setColumnMinimumWidth(0, 20)
        #gridlayout.setRowMinimumHeight(0, 12)
        gridlayout.setHorizontalSpacing(15)
        gridlayout.setColumnStretch(6, 3)
        gridlayout.setRowStretch(6, 3)

        bottom_label = QLabel("https://anatoly1010.github.io/atomize_docs/; Version 0.3.1; 15/02/2026")
        bottom_label.setStyleSheet("QLabel { color : rgb(193, 202, 227); font-weight: bold; }")
        main_layout.addWidget(bottom_label)

    # redefined method
    def closeEvent(self, event):
        """
        A function to do some actions when the main window is closing.
        """
        processes = [
            self.process_python, self.process_tr, self.process_osc, 
            self.process_osc2, self.process_cw, self.process_temp, 
            self.process_field, self.process_mw, self.process_tune_preset, 
            self.process_phasing, self.process_awg_phasing, self.process_t2, 
            self.process_t1, self.process_ed, self.process_eseem
        ]

        active_processes = []
        for p in processes:
            try:
                if p and p.state() != QtCore.QProcess.ProcessState.NotRunning:
                    active_processes.append(p)
            except AttributeError:
                pass

        if active_processes:
            event.ignore()
            self.text_errors.appendPlainText(f"{len(active_processes)} process is still running. Please terminate it")
        else:
            sys.exit()

    # redefined method
    def quit(self):
        """
        A function to quit the programm
        """
        processes = [
            self.process_python, self.process_tr, self.process_osc, 
            self.process_osc2, self.process_cw, self.process_temp, 
            self.process_field, self.process_mw, self.process_tune_preset, 
            self.process_phasing, self.process_awg_phasing, self.process_t2, 
            self.process_t1, self.process_ed, self.process_eseem
        ]

        active_processes = []
        for p in processes:
            try:
                if p and p.state() != QtCore.QProcess.ProcessState.NotRunning:
                    active_processes.append(p)
            except AttributeError:
                pass

        if active_processes:
            self.text_errors.appendPlainText(f"{len(active_processes)} process is still running. Please terminate it")
        else:
            sys.exit()

    # redefined method
    def start_experiment(self):
        """
        A function to run an experimental script using python.exe.
        """
        if len(self.script_queue.keys()) != 0:
            self.queue = 1
            first_index = self.script_queue.namelist_model.index(0, 0 )
            self.script_queue.namelist_view.setCurrentIndex(first_index)            
        else:
            self.queue = 0

        if self.queue == 0:
            name = self.script
        else:
            name = self.script_queue.values()[0]

        if self.script != '':
            stamp = os.stat(name).st_mtime
        else:
            self.text_errors.appendPlainText('No experimental script is opened')
            return

        # mod
        if self.checkTests.checkState().value == 2:
            self.test(name)
            exec_code = self.success
            #self.process.waitForFinished( msecs = self.test_timeout ) # timeout in msec
        elif self.checkTests.checkState().value == 0:
            self.test_flag = 0
            exec_code = True
            self.text_errors.appendPlainText("Testing of experimental scripts are disabled")
        # mod

        if self.test_flag == 1:
            self.text_errors.appendPlainText("Experiment cannot be started, since test is not passed. Test execution timeout is " +\
                                str( self.test_timeout / 60000 ) + " minutes")
            return
        elif self.test_flag == 0 and exec_code == True:
            self.process_python.setArguments([name])
            self.button_start.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(211, 194, 78); border-style: outset; color: rgb(63, 63, 97); font-weight: bold; } ")
            self.process_python.start()
            self.pid = self.process_python.processId()
            print(f'SCRIPT PROCESS ID: {self.pid}')

    # redefined method
    def on_finished_checking(self, exit_code, exit_status, loop, process):
        """
        A function to add the information about errors found during syntax checking
        to a dedicated text box in the main window of the programm.
        """
        text = process.readAllStandardOutput().data().decode(self.system_encoding, errors='replace')
        text_errors_script = process.readAllStandardError().data().decode(self.system_encoding, errors='replace')
        if text_errors_script == '':
            self.text_errors.appendPlainText("No errors are found")
            self.test_flag = 0
        elif text_errors_script != '':
            self.test_flag = 1
            self.text_errors.appendPlainText(text_errors_script)
            # mod
            path_status_file = os.path.join(self.path_to_main, 'status')
            file_to_read = open(path_status_file, 'w')
            file_to_read.write('Status:  Off' + '\n')
            file_to_read.close()
            # mod

        self.button_test.setStyleSheet("QPushButton {border-radius: 4px; background-color: rgb(63, 63, 97); border-style: outset; color: rgb(193, 202, 227); font-weight: bold; } ")

        self.success = (exit_status == QtCore.QProcess.ExitStatus.NormalExit and exit_code == 0)
        loop.quit()

    # redefined method
    @QtCore.pyqtSlot(str)
    def add_error_message(self, data):
        """
        A function for adding an error message to a dedicated text box in the main window of the programm;
        This function runs when Helper.changedSignal.emit(str) is emitted.
        :param data: string
        """
        self.text_errors.appendPlainText(str(data))

        if data == 'Script stopped':
            self.script_queue.clear()
            self.queue = 0
            #mod
            #self.process_python.close()
            self.process_python.terminate()
            time.sleep(2)
            self.process_python.close()
            # mod

    ##### new methods:
    def start_eseem_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_eseem.setArguments([os.path.join('..','atomize/control_center/eseem_preset_insys.py')])
        self.process_eseem.start()

    def start_ed_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_ed.setArguments([os.path.join('..','atomize/control_center/echo_det_preset_insys.py')])
        self.process_ed.start()

    def start_t1_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_t1.setArguments([os.path.join('..','atomize/control_center/t1_preset_insys.py')])
        self.process_t1.start()

    def start_t2_preset(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_t2.setArguments([os.path.join('..','atomize/control_center/t2_preset_insys.py')])
        self.process_t2.start()

    def start_rect_phasing(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_phasing.setArguments([os.path.join('..','atomize/control_center/phasing_insys.py')])
        self.process_phasing.start()

    def start_awg_phasing(self):
        """
        A function to run an phasing for rect channel.
        """
        self.process_awg_phasing.setArguments([os.path.join('..','atomize/control_center/awg_phasing_insys.py')])
        self.process_awg_phasing.start()

    def start_tune_preset(self):
        """
        A function to run tuning.
        """
        self.process_tune_preset.setArguments([os.path.join('..','atomize/control_center/tune_preset.py')])
        self.process_tune_preset.start()

    def start_mw_control(self):
        """
        A function to run an pulse_creator.
        """
        self.process_mw.setArguments([os.path.join('..','atomize/control_center/mw_bridge_control.py')])
        self.process_mw.start()

    def start_tr_control(self):
        """
        A function to run an pulse_creator.
        """
        self.process_tr.setArguments([os.path.join('..','atomize/control_center/tr_control.py')])
        self.process_tr.start()
    
    def start_osc_control(self):
        """
        A function to run an Keysight control.
        """
        self.process_osc.setArguments([os.path.join('..','atomize/control_center/osc_control.py')])
        self.process_osc.start()

    def start_field_control(self):
        """
        A function to run an Field control.
        """
        self.process_field.setArguments([os.path.join('..','atomize/control_center/field_control.py')])
        self.process_field.start()

    def start_osc_control_2(self):
        """
        A function to run an Keysight control.
        """
        self.process_osc2.setArguments([os.path.join('..','atomize/control_center/osc_control_2.py')])
        self.process_osc2.start()

    def start_cw(self):
        """
        A function to run an Keysight control.
        """
        self.process_cw.setArguments([os.path.join('..','atomize/control_center/cw_control.py')])
        self.process_cw.start()

    def start_temp_control(self):
        """
        A function to run an Keysight control.
        """
        self.process_temp.setArguments([os.path.join('..','atomize/control_center/temp_control.py')])
        self.process_temp.start()

    def script_open_combo(self):
        self.script = self.text_to_script_name( self.script_chooser.currentText() )
        self.open_file(  os.path.join(self.script ))

    def text_to_script_name(self, text_to_parse):

        if text_to_parse == ' Tuning':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/01_resonator_tuning.py')
        elif text_to_parse == ' T2 Echo Shape':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/keysight/02_t2_baseline_echo_shape.py')
        elif text_to_parse == ' ED Spectrum':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/keysight/03_echo_detected_spectrum_baseline.py')
        elif text_to_parse == ' ESEEM Echo Shape':
            return os.path.join(self.path_to_main, '..', 'atomize/tests/pulse_epr/keysight/07_eseem_phase_echo_shape.py')

def main():
    """
    A function to run the main window of the programm.
    """
    # Windows taskbar
    try:
        myappid = 'atomize'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass
    
    app = QtWidgets.QApplication(sys.argv)
    main = MainExtended(ptm = '../../libs')
    main.show()
    sys.exit( app.exec() )

if __name__ == '__main__':
    main()