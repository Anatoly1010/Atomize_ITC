"""Process isolation for the existing AWG resonator-scan worker."""
import signal
import sys
from multiprocessing import Pipe, Process

import numpy as np

from atomize.epr_auto.engine.executor import EngineError, _quiet_worker_stdout, _wind_down


class _Pipe:
    def __init__(self, conn):
        self.conn = conn

    def send(self, value):
        self.conn.send(value)

    def poll(self):
        return self.conn.poll()

    def recv(self):
        return self.conn.recv()

    def close(self):
        pass


def _child(conn, args, test):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _quiet_worker_stdout()
    sys.argv = [sys.argv[0], 'test' if test else 'None']
    from atomize.control_center.tune_preset import Worker
    try:
        data = Worker().scan_awg(_Pipe(conn), *args, test=test)
        if data is None:
            raise ValueError('resonator scan returned no data')
        conn.send(('Done', ''))
    except BaseException as error:
        conn.send(('Error', str(error)))
    finally:
        conn.close()


def acquire(args, path=None, test=False, log=None):
    """Run the scan, serving save/stop messages and draining on interruption."""
    parent, child = Pipe()
    process = Process(target=_child, args=(child, args, test))
    process.start()
    child.close()
    try:
        while True:
            if not parent.poll(0.2):
                if not process.is_alive():
                    raise EngineError('resonator worker exited without completion')
                continue
            try:
                kind, payload = parent.recv()
            except EOFError:
                raise EngineError('resonator worker closed before completion') from None
            if kind == 'Error':
                raise EngineError(payload)
            if kind == 'Open':
                if path is None:
                    raise EngineError('resonator requested a file without an output path')
                parent.send(f'FL{path}')
            if kind == 'Status' and log:
                log(f'      resonator scan: {payload}%')
            if kind == 'Done':
                return None if test else np.loadtxt(path, delimiter=',').T
    finally:
        _wind_down(parent, process, path, 0.2)
        parent.close()
