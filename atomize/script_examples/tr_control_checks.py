"""Offline tr_control _wait_armed checks with stub scopes; run with Python and the `test` argument."""
import sys
import threading
import time
from multiprocessing import Pipe

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.control_center.tr_control import Worker, _wait_armed


class StubScope:
    def __init__(self, run_for, trigger):
        self.test_flag = 'real'
        self.run_for = run_for
        self.trigger = trigger
        self.commands = []
        self.start = time.monotonic()

    def oscilloscope_command(self, command):
        self.commands.append(command)

    def oscilloscope_query(self, command):
        if command == ':OPERegister:CONDition?':
            return '+8\n' if time.monotonic() - self.start < self.run_for else '+0\n'
        if command == ':TER?':
            return '+1\n' if self.trigger else '+0\n'
        raise AssertionError(command)


def run(scope, timeout, exit_after=None, message=None):
    parent, child = Pipe()
    if exit_after is not None:
        threading.Timer(exit_after, parent.send, args=(message,)).start()
    t0 = time.monotonic()
    result = _wait_armed([scope], child, timeout)
    return result, time.monotonic() - t0


scope = StubScope(run_for=0, trigger=False)
result, _ = run(scope, 0.2)
assert result == 'done' and scope.commands == [], (result, scope.commands)
print('PASS: RUN clear returns done')

scope = StubScope(run_for=0.5, trigger=True)
result, elapsed = run(scope, 0.2)
assert result == 'done' and elapsed >= 0.5 and ':STOP' not in scope.commands, (result, elapsed, scope.commands)
print('PASS: steady triggers keep a 0.5 s accumulation alive past a 0.2 s timeout')

scope = StubScope(run_for=10, trigger=False)
result, elapsed = run(scope, 0.2)
assert result == ('no_trigger', 0) and scope.commands == [':STOP'] and 0.2 <= elapsed < 0.4, (result, elapsed, scope.commands)
print('PASS: no trigger for 0.2 s returns no_trigger and stops the scope')

scope = StubScope(run_for=10, trigger=True)
result, elapsed = run(scope, 0.2, exit_after=0.3, message='exit')
assert result == 'exit' and scope.commands == [':STOP'] and elapsed < 0.3 + 0.1, (result, elapsed, scope.commands)
print('PASS: exit on the pipe returns within one poll and stops the scope')

scope = StubScope(run_for=10, trigger=True)
result, _ = run(scope, 0.2, exit_after=0.1, message='SC5')
assert result == ('command', 'SC5') and scope.commands == [], (result, scope.commands)
print('PASS: other pipe commands are handed back to the caller')

worker = Worker()
worker.trigger_timeout_s = 0.1
scope = StubScope(run_for=10, trigger=False)
parent, child = Pipe()
assert worker._acquire_point([scope], child, 3400.0) is False and worker.command == 'exit'
text = 'scope 1: no trigger for 0.1 s at field 3400.0 G'
assert parent.recv() == ('Message', text + '; retrying the point')
assert parent.recv() == ('Message', text + '; second loss, stopping the measurement') and not parent.poll()
assert scope.commands.count('*CLS;:SINGle') == 2 and scope.commands.count(':STOP') == 2, scope.commands
print('PASS: a lost trigger is retried once, then stops the run with the field')

print('ALL PASS')
