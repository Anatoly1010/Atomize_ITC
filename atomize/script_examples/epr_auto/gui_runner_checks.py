"""Exercise GUI stdin prompts, stop and cleanup with injected dummy steps."""
import json
import os
import time
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')

from atomize.epr_auto.gui_io import PREFIX


def check(directory, mode):
    path = Path(directory) / 'dummy.yaml'
    coarse = '  - tune.power_for_length:\n      target_length: 32 ns\n' if mode == 'rail' else ''
    path.write_text('sample: dummy\nautonomy: supervised\nnotify: none\nsteps:\n' + coarse +
                    '  - field.set:\n      value: 3400 G\n      on_fail: ask\n')
    code = '''
import sys, time
from atomize.epr_auto import cli
from atomize.epr_auto.steps import STEPS, StepFailure
calls = 0
def dummy(session, **kwargs):
    global calls
    calls += 1
    if MODE in ('stop', 'blocking'):
        print('DUMMY STEP ACTIVE', flush=True)
        if MODE == 'blocking':
            time.sleep(5)
        while True:
            time.sleep(.05)
    if calls == 1:
        raise StepFailure('injected dummy failure', rails='high' if MODE == 'rail' else None)
    return {'dummy': True}
STEPS['field.set'].func = dummy
STEPS['tune.power_for_length'].func = lambda *a, **kw: {'dummy': True}
from atomize.epr_auto.session import EPRSession
release = EPRSession.release_hardware_locks
def checked_release(self):
    release(self)
    print('CLEANUP COMPLETE', flush=True)
EPRSession.release_hardware_locks = checked_release
sys.exit(cli.main(['run', PATH, '--test', '--gui']))
'''.replace('MODE', repr(mode)).replace('PATH', repr(str(path)))
    process = subprocess.Popen([sys.executable, '-u', '-c', code], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = queue.Queue()
    def read():
        for line in process.stdout:
            lines.put(line.rstrip())
        lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    output, prompts = [], []
    stop_at = None
    try:
        while True:
            line = lines.get(timeout=20)
            if line is None:
                break
            output.append(line)
            reply = None
            if line.startswith(PREFIX):
                kind = json.loads(line[len(PREFIX):])['kind']
                prompts.append(kind)
                if mode == 'eof':
                    process.stdin.close()
                else:
                    reply = {'checkpoint':'continue', 'failure':'retry', 'rail':'yes'}[kind]
            elif line == 'DUMMY STEP ACTIVE':
                stop_at = time.monotonic()
                reply = 'stop'
            if reply is not None:
                process.stdin.write(reply + '\n')
                process.stdin.flush()
        assert process.wait(timeout=5) == (2 if mode in ('stop', 'blocking', 'eof') else 0), output
        assert 'CLEANUP COMPLETE' in output, output
        if mode == 'blocking':
            assert time.monotonic() - stop_at < 2, 'Stop did not interrupt the blocking sleep'
        if mode == 'failure':
            assert prompts == ['checkpoint', 'failure'], prompts
        if mode == 'rail':
            assert prompts == ['checkpoint', 'checkpoint', 'rail'], prompts
        print('PASS:', mode, 'prompts and cleanup')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()


with tempfile.TemporaryDirectory() as directory:
    for mode in ('failure', 'rail', 'stop', 'eof') + (('blocking',) if os.name == 'posix' else ()):
        check(directory, mode)
print('ALL PASS')
