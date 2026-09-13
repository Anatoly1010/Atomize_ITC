"""Offline GUI launcher integration checks with a real dry-run child process."""
import os
import sys
import tempfile
import time
from pathlib import Path

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtCore, QtWidgets
from atomize.main.protocol_launcher import ProtocolLauncher

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
launcher = ProtocolLauncher()
messages = []
launcher.log.connect(messages.append)


def pump(until, seconds=20):
    deadline = time.monotonic() + seconds
    while not until():
        app.processEvents()
        if time.monotonic() > deadline:
            launcher.request_stop()
            raise AssertionError('GUI test timeout: ' + '\n'.join(messages[-8:]))
        time.sleep(.01)


def run(path, replies, expected):
    messages.clear()
    assert launcher.start_protocol(path)
    assert not launcher.start_protocol(path), 'duplicate launch accepted'
    seen = []
    def done():
        dialog = launcher.dialog
        if dialog is not None and dialog not in seen:
            assert dialog.windowModality() == QtCore.Qt.WindowModality.NonModal
            seen.append(dialog)
            action = replies.pop(0)
            if action == 'close':
                dialog.reject()
            elif action == 'stop':
                launcher.request_stop()
            else:
                next(b for b in dialog.buttons() if b.text() == action).click()
        return launcher.process.state() == QtCore.QProcess.ProcessState.NotRunning and launcher.run_button.isEnabled()
    pump(done, seconds=90)
    assert not replies, replies
    assert launcher.status.text() == 'Protocol ' + expected, messages
    assert launcher.dialog is None
    print('PASS:', expected, len(seen), 'dialogs')


with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'dummy.yaml'
    path.write_text('sample: dummy\nautonomy: supervised\nnotify: none\nsteps:\n  - field.set:\n      value: 3400 G\n  - field.set:\n      value: 3410 G\n')
    run(path, ['Continue', 'Continue'], 'finished')
    run(path, ['Skip', 'Continue'], 'finished')
    assert any('skipped by operator' in line for line in messages)
    for action in ('Abort', 'close', 'stop'):
        run(path, [action], 'aborted')
    bad = Path(directory) / 'bad.yaml'
    bad.write_text('sample: dummy\nsteps:\n  - nonexistent.step\n')
    run(bad, [], 'invalid')
    assert any('INVALID:' in line for line in messages), 'stderr missing'
    run(path, ['Continue', 'Continue'], 'finished')
    from unittest.mock import patch
    with patch.object(sys, 'executable', str(Path(directory) / 'missing-python')):
        run(path, [], 'crashed')

from unittest.mock import Mock, patch
for kind, label, reply in [('failure','Retry',b'retry\n'), ('failure','Skip',b'skip\n'),
                           ('rail','Re-run coarse stage',b'yes\n'), ('rail','No',b'no\n')]:
    process = Mock()
    process.state.return_value = QtCore.QProcess.ProcessState.Running
    launcher.stopping = False
    with patch.object(launcher, 'process', process):
        launcher._prompt({'kind':kind, 'prompt':'Injected dummy prompt'})
        next(b for b in launcher.dialog.buttons() if b.text() == label).click()
        process.write.assert_called_once_with(reply)
    assert launcher.dialog is None
print('PASS: failure and coarse-stage dialog replies')

full_protocol = Path(__file__).resolve().parents[3] / 'protocols' / 'preliminary_tuning.yaml'
run(full_protocol, ['Continue'] * 5, 'finished')

from unittest.mock import patch
from atomize.main.main import MainExtended, MainWindow

def base_init(self, *args, **kwargs):
    QtWidgets.QMainWindow.__init__(self)
    self.tabwidget = QtWidgets.QTabWidget(self)
    self.text_errors = QtWidgets.QPlainTextEdit(self)
    self.process_python = QtCore.QProcess(self)

with patch.object(MainWindow, '__init__', base_init):
    window = MainExtended()
assert window.process_protocol in window.all_processes
assert window.protocol_launcher.dry_run.isChecked()
assert window.checkTests.isChecked()
window.protocol_launcher.dry_run.setChecked(False)
assert window.checkTests.isChecked(), 'Dry run changed Test Scripts'
window.process_protocol.start(sys.executable, ['-c', 'import time; time.sleep(2)'])
pump(lambda: window.process_protocol.state() == QtCore.QProcess.ProcessState.Running)
class CloseEvent:
    ignored = False
    def ignore(self):
        self.ignored = True
close = CloseEvent()
window.closeEvent(close)
window.quit()
assert close.ignored
assert 'process is still running' in window.text_errors.toPlainText()
pump(lambda: window.process_protocol.state() == QtCore.QProcess.ProcessState.NotRunning)
window.deleteLater()
print('PASS: ITC tab integration, independent checkbox and active-process close guards')

launcher.deleteLater()
app.processEvents()
print('ALL PASS')
