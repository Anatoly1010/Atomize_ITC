"""Offline tr_control :DIGitize / serial-poll checks with stub scopes; run with Python and the `test` argument."""
import sys
import threading
import time
from multiprocessing import Pipe

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.control_center.tr_control import Worker, _arm, _wait_armed


class StubDevice:
    def __init__(self, scope):
        self.scope = scope
        self.clears = 0

    def read_stb(self):
        elapsed = time.monotonic() - self.scope.tr_armed
        stb = 0
        if self.scope.trigger_after is not None and elapsed >= self.scope.trigger_after:
            stb |= 1
        if elapsed >= self.scope.run_for:
            stb |= 32
        return stb

    def clear(self):
        self.clears += 1
        self.scope.commands.append('clear')


class StubScope:
    def __init__(self, run_for, trigger_after, count = 16):
        self.test_flag = 'real'
        self.run_for = run_for
        self.trigger_after = trigger_after
        self.count = count
        self.commands = []
        self.device = StubDevice(self)

    def oscilloscope_command(self, command):
        self.commands.append(command)

    def oscilloscope_query(self, command):
        self.commands.append(command)
        if command == '*CLS;*ESE 1;:ACQuire:COUNt?':
            return f'+{self.count}\n'
        raise AssertionError(command)


def run(scope, timeout, send_after = None, message = None):
    parent, child = Pipe()
    _arm(scope)
    scope.commands.clear()
    if send_after is not None:
        threading.Timer(send_after, parent.send, args = (message, )).start()
    t0 = time.monotonic()
    result = _wait_armed([scope], child, timeout)
    return result, time.monotonic() - t0


scope = StubScope(run_for = 0, trigger_after = 0)
_arm(scope)
assert scope.commands == [':WAVeform:FORMat WORD', '*CLS;*ESE 1;:ACQuire:COUNt?', ':DIGitize;*OPC'] and scope.tr_count == 16, scope.commands
result, _ = run(scope, 0.2)
assert result == 'done' and scope.commands == [] and scope.tr_shot_s is not None, (result, scope.commands)
print('PASS: arm sends FORMat, the synchronised COUNt query and DIGitize; ESB returns done')

scope = StubScope(run_for = 0.5, trigger_after = 0.05)
result, elapsed = run(scope, 0.2)
assert result == 'done' and elapsed >= 0.5 and scope.commands == [], (result, elapsed, scope.commands)
assert abs(scope.tr_shot_s - 0.5 / 16) < 0.01, scope.tr_shot_s
print('PASS: a 0.5 s accumulation with TRG seen stays alive past a 0.2 s timeout and calibrates the shot time')

scope = StubScope(run_for = 10, trigger_after = None)
result, elapsed = run(scope, 0.2)
assert result == ('no_trigger', 0, 'no trigger for 0.2 s') and scope.commands == ['clear', ':STOP'] and 0.2 <= elapsed < 0.4, (result, elapsed, scope.commands)
print('PASS: no TRG for 0.2 s returns no_trigger and aborts with clear and STOP')

scope = StubScope(run_for = 10, trigger_after = 0.01, count = 4)
scope.tr_shot_s = 0.05
result, elapsed = run(scope, 0.1)
assert result == ('no_trigger', 0, 'accumulation ran past 0.5 s') and scope.commands == ['clear', ':STOP'], (result, scope.commands)
assert 0.5 <= elapsed < 0.7 and scope.tr_shot_s is None, (elapsed, scope.tr_shot_s)
print('PASS: a calibrated scope running past 2 * count * shot + timeout is aborted and recalibrates')

scope = StubScope(run_for = 10, trigger_after = 0.01)
result, elapsed = run(scope, 0.2, send_after = 0.3, message = 'exit')
assert result == 'exit' and scope.commands == ['clear', ':STOP'] and elapsed < 0.3 + 0.1, (result, elapsed, scope.commands)
print('PASS: exit on the pipe returns within one poll and aborts the scope')

scope = StubScope(run_for = 10, trigger_after = 0.01)
result, _ = run(scope, 0.2, send_after = 0.1, message = 'SC5')
assert result == ('command', 'SC5') and scope.commands == [], (result, scope.commands)
print('PASS: other pipe commands are handed back without touching the scope')

worker = Worker()
worker.trigger_timeout_s = 0.1
scope = StubScope(run_for = 10, trigger_after = None)
parent, child = Pipe()
assert worker._acquire_point([scope], child, 3400.0) is False and worker.command == 'exit'
text = 'scope 1: no trigger for 0.1 s at field 3400.0 G'
assert parent.recv() == ('Message', text + '; retrying the point')
assert parent.recv() == ('Message', text + '; second loss, stopping the measurement') and not parent.poll()
assert scope.commands.count(':DIGitize;*OPC') == 2 and scope.commands.count(':STOP') == 2 and scope.device.clears == 2, scope.commands
print('PASS: a lost trigger is retried once, then stops the run with the field')

print('ALL PASS')
