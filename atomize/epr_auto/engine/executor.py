"""Run a Worker method in a child process and speak its pipe protocol.

The Worker (from awg_phasing_insys) reports over a multiprocessing Pipe:
    ('Status', pct)    progress percentage
    ('Message', text)  operator-facing note
    ('Error', text)    exception + traceback from the child
    ('Open', '')       request for a save path; answered with 'FL<path>'
    ('test', '')       script_test pre-flight finished successfully
    ('', 'Experiment <name> finished')   real run finished (after saving)
Commands into the worker: 'exit' (stop; the worker still reads out the
accumulated data and saves), 'SC<n>' (resize scan count mid-run).
"""
import time
from multiprocessing import Pipe, Process

from atomize.control_center.awg_phasing_insys import Worker

# Worker method per preset sweep type
SWEEP_METHOD = {
    'Linear Time': ('exp', 'exp_args'),
    'Log Time': ('exp_log', 'exp_log_args'),
    'Amplitude': ('exp_amplitude', 'exp_amplitude_args'),
    'Field': ('exp_field', 'exp_field_args'),
    'ESEEM Avg': ('exp_eseem', 'exp_eseem_args'),
}


class EngineError(RuntimeError):
    pass


def run_worker(worker_args, sweep_type, save_path=None, script_test=False,
               on_status=None, on_message=None, poll_s=0.2):
    """Execute one experiment; blocks until the worker finishes.

    save_path answers the worker's 'Open' request (required for a real run —
    the worker always saves; pass script_test=True for the no-save pre-flight).
    on_status(pct) / on_message(text) are optional progress callbacks.
    Raises EngineError on a worker-side error; KeyboardInterrupt sends 'exit'
    (the worker reads out, saves and finishes cleanly).
    """
    if sweep_type not in SWEEP_METHOD:
        raise EngineError(f'sweep type {sweep_type!r} is not runnable '
                          f'(supported: {", ".join(SWEEP_METHOD)})')
    if not script_test and save_path is None:
        raise EngineError('save_path is required for a real run')

    method_name, args_builder = SWEEP_METHOD[sweep_type]
    args = getattr(worker_args, args_builder)()

    worker = Worker()
    parent_conn, child_conn = Pipe()
    process = Process(target=getattr(worker, method_name),
                      args=(child_conn, *args, script_test))
    process.start()

    stopping = False
    try:
        while True:
            if not parent_conn.poll(poll_s):
                if not process.is_alive():
                    # No terminal message: the child died (or, in a test run,
                    # finished right after 'test' was consumed below).
                    raise EngineError('worker exited without reporting a result')
                continue

            kind, payload = parent_conn.recv()
            if kind == 'Error':
                raise EngineError(f'worker error:\n{payload}')
            if kind == 'Status':
                if on_status is not None:
                    on_status(payload)
            elif kind == 'Message':
                if on_message is not None:
                    on_message(payload)
            elif kind == 'Open':
                parent_conn.send(f'FL{save_path}')
            elif kind == 'test':
                return {'status': 'test-ok'}
            elif kind == '' and str(payload).endswith('finished'):
                return {'status': 'finished', 'file': save_path}
            # anything else ('Count', ...) is preview-only chatter — ignore

    except KeyboardInterrupt:
        if not stopping:
            stopping = True
            parent_conn.send('exit')
            # Let the worker read out + save; surface its remaining messages.
            deadline = time.time() + 60
            while time.time() < deadline:
                if parent_conn.poll(poll_s):
                    kind, payload = parent_conn.recv()
                    if kind == 'Open':
                        parent_conn.send(f'FL{save_path}')
                    elif kind == 'Error':
                        raise EngineError(f'worker error during stop:\n{payload}')
                    elif kind == 'test' or (kind == '' and str(payload).endswith('finished')):
                        return {'status': 'stopped', 'file': save_path}
                elif not process.is_alive():
                    break
            raise
    finally:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join()
