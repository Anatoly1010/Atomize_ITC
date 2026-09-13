"""Exercise the actual AWG scan loop with fake devices and stop messages."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise SystemExit('Run this offline check with the test argument')


def scan_loop():
    source = Path(__file__).resolve().parents[2] / 'control_center' / 'tune_preset.py'
    tree = ast.parse(source.read_text())
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == 'scan_awg')
    loop = next(node for node in ast.walk(method)
                if isinstance(node, ast.While)
                and ast.unparse(node.test) == "self.command != 'exit'")
    return compile(ast.Module(body=[loop], type_ignores=[]), str(source), 'exec')


def check(code, name, stop_poll, expected_reads):
    state = {'reads': 0, 'after_stop': 0, 'polls': 0}
    worker = SimpleNamespace(command='start')

    def curve(*args):
        state['reads'] += 1
        state['after_stop'] += worker.command == 'exit'
        return np.ones(2)

    def poll():
        state['polls'] += 1
        return state['polls'] == stop_poll

    namespace = dict(
        self=worker, SCANS=5, START_FREQ=0, END_FREQ=2, STEP=1, points=3,
        data=np.zeros((3, 2)), np=np, test=False, p2='mock', t_step=1,
        mw=SimpleNamespace(mw_bridge_synthesizer=lambda *args: None),
        a2012=SimpleNamespace(oscilloscope_start_acquisition=lambda: None,
                             oscilloscope_get_curve=curve),
        general=SimpleNamespace(wait=lambda *args: None,
                                plot_2d=lambda *args, **kwargs: None),
        conn=SimpleNamespace(send=lambda *args: None, poll=poll, recv=lambda: 'exit'))
    exec(code, namespace)
    assert state['after_stop'] == 0, (name, state)
    assert state['reads'] == expected_reads, (name, state)
    if stop_poll is None:
        np.testing.assert_allclose(namespace['data'], -np.ones((3, 2)))
    print(f'PASS {name}: {state["reads"]} reads, none after stop')


if __name__ == '__main__':
    code = scan_loop()
    check(code, 'stop before first discarded acquisition', 1, 0)
    check(code, 'stop before first frequency point', 2, 1)
    check(code, 'stop after first frequency point', 3, 2)
    check(code, 'stop at next scan boundary', 8, 4)
    check(code, 'normal five-scan acquisition', None, 20)
    print('ALL PASS')
