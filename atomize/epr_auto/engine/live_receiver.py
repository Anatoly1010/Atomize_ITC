"""Use the phasing tool's live preview while the parent adjusts the bridge."""
import signal
import time
from multiprocessing import Pipe, Process

import numpy as np

from atomize.epr_auto.engine import executor


class _PreviewPipe:
    """Keep an exit consumed by the frame handshake for dig_on's next poll."""
    def __init__(self, conn):
        self.conn = conn
        self.stopping = False
        self.frame = None
        self.skip = False

    def keep(self, frame):
        if self.skip:
            self.skip = False
        else:
            self.frame = frame

    def send(self, value):
        self.conn.send(value)
        if value[0] != 'Count' or self.stopping or self.frame is None:
            return
        frame, self.frame = self.frame, None
        self.conn.send(('LiveTrace', frame))
        command = self.conn.recv()
        if command == 'exit':
            self.stopping = True
        elif command != 'continue':
            raise executor.EngineError(f'unexpected live receiver command: {command!r}')
        self.skip = True

    def poll(self, *args):
        return self.stopping or self.conn.poll(*args)

    def recv(self):
        return 'exit' if self.stopping else self.conn.recv()


def _live_child(worker, conn, args):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    executor._quiet_worker_stdout()
    import atomize.general_modules.general_functions as general
    pipe = _PreviewPipe(conn)
    original = general.plot_1d

    def capture(name, x, y, *a, **kw):
        try:
            original(name, x, y, *a, **kw)
        except Exception:
            pass
        if pipe.stopping:
            return
        t, i, q = (np.asarray(v, dtype=float) for v in (x, y[0], y[1]))
        if (t.ndim != 1 or len(t) < 3 or i.shape != t.shape or q.shape != t.shape
                or not np.isfinite([t, i, q]).all()):
            return
        pipe.keep((t.copy(), i.copy(), q.copy()))

    general.plot_1d = capture
    worker.dig_on(pipe, *args, False)
    conn.send(('LiveEnd', ''))


def monitor_trace(worker_args, on_trace, on_message=None, poll_s=0.2):
    """Run dig_on(l_mode=0); on_trace(t_seconds, I_mV, Q_mV) returns True to stop.

    Every finite live snapshot holds a complete phase cycle and enters the
    frame handshake at the end of a cycle; the first snapshot completed after
    a handshake may span that bridge change and is discarded.
    The handshake completes bridge changes before the next phase cycle.
    Callback errors stop the worker and propagate; they cannot silently disable
    receiver control. Live snapshots never accumulate across video settings.
    """
    phases = len(worker_args.rect[0][3])
    if phases < 2:
        raise executor.EngineError('live receiver monitoring requires a phase-cycled preset')
    worker = executor.Worker()
    executor._hand_attrs(worker, worker_args)
    parent, child = Pipe()
    process = Process(target=_live_child,
                      args=(worker, child, worker_args.dig_args(l_mode=0)))
    timeout = max(60.0, 10 * phases * worker_args.averages / float(worker_args.rep_rate))
    process.start()
    last_frame = time.monotonic()
    stopping = False
    try:
        while True:
            if time.monotonic() - last_frame > timeout:
                raise executor.EngineError('live receiver stalled: no valid current trace')
            if not parent.poll(poll_s):
                if not process.is_alive():
                    raise executor.EngineError('live receiver exited without a result')
                continue
            kind, payload = parent.recv()
            if kind == 'Error':
                raise executor.EngineError(f'live receiver error:\n{payload}')
            if kind == 'Message':
                executor._safe_call(on_message, payload)
            elif kind == 'LiveTrace':
                last_frame = time.monotonic()
                stopping = bool(on_trace(*payload))
                parent.send('exit' if stopping else 'continue')
            elif kind == 'LiveEnd':
                if not stopping:
                    raise executor.EngineError('live receiver stopped before the RV approach completed')
                return
    finally:
        executor._wind_down(parent, process, None, poll_s)
        parent.close()
        child.close()
