"""Run a Worker method in a child process and speak its pipe protocol.

The Worker (from awg_phasing_insys) reports over a multiprocessing Pipe:
    ('Status', pct)    progress percentage
    ('Message', text)  operator-facing note
    ('Error', text)    exception + traceback from the child
    ('Open', '')       request for a save path; answered with 'FL<path>'
    ('test', '')       script_test pre-flight finished successfully
    ('', 'Experiment <name> finished')   real run finished (after saving)
Commands into the worker: 'exit' (stop; the worker still reads out the
accumulated data and saves), 'SC<n>' (resize scan count mid-run — the
scan_control callback below is the channel for judge/budget-driven
early finish; a count at or below the scans already done makes the
worker finish after the current scan, still reading out and saving).
"""
import time
from multiprocessing import Pipe, Process

import numpy as np

from atomize.control_center.awg_phasing_insys import Worker
from atomize.epr_auto.engine.snapshot import CORRECTION_ATTRS, SWEEP_TYPES

# Worker method per preset sweep type
SWEEP_METHOD = {
    'Linear Time': ('exp', 'exp_args'),
    'Log Time': ('exp_log', 'exp_log_args'),
    'Amplitude': ('exp_amplitude', 'exp_amplitude_args'),
    'Field': ('exp_field', 'exp_field_args'),
    'ESEEM Avg': ('exp_eseem', 'exp_eseem_args'),
}

# Keep the hand-maintained method map in lockstep with the preset loader:
# fail at import time instead of silently skipping a whole sweep family
# (load_preset accepts everything in SWEEP_TYPES).
if set(SWEEP_METHOD) != set(SWEEP_TYPES):
    raise ImportError('executor.SWEEP_METHOD is out of sync with '
                      'snapshot.SWEEP_TYPES: '
                      f'{sorted(set(SWEEP_METHOD) ^ set(SWEEP_TYPES))}')


class EngineError(RuntimeError):
    pass


def run_worker(worker_args, sweep_type, save_path=None, script_test=False,
               on_status=None, on_message=None, poll_s=0.2,
               scan_control=None):
    """Execute one experiment; blocks until the worker finishes.

    save_path answers the worker's 'Open' request (required for a real run —
    the worker always saves; pass script_test=True for the no-save pre-flight).
    on_status(pct) / on_message(text) are optional progress callbacks.
    scan_control(pct, elapsed_s) is the adaptive-scan command channel: called
    on every Status tick; return an int to resize the worker's scan count
    ('SC<n>' — shrink to finish early with data intact), or None to leave it.
    Raises EngineError on a worker-side error; KeyboardInterrupt sends 'exit'
    and waits for the worker to read out and save, however long that takes
    (a second KeyboardInterrupt force-terminates the worker, losing the data).
    """
    if sweep_type not in SWEEP_METHOD:
        raise EngineError(f'sweep type {sweep_type!r} is not runnable '
                          f'(supported: {", ".join(SWEEP_METHOD)})')
    if not script_test and save_path is None:
        raise EngineError('save_path is required for a real run')

    method_name, args_builder = SWEEP_METHOD[sweep_type]
    args = getattr(worker_args, args_builder)()

    worker = Worker()
    # AWG timing grid + resonator-correction state travel as worker
    # attributes (pickled with the instance), exactly like the GUI's
    # dig_start_exp / _hand_correction_to_worker.
    _hand_attrs(worker, worker_args)
    parent_conn, child_conn = Pipe()
    process = Process(target=getattr(worker, method_name),
                      args=(child_conn, *args, script_test))
    process.start()

    t_start = time.monotonic()
    scans_sent = None            # last 'SC<n>' sent (send only on change)
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
                if scan_control is not None:
                    new_scans = scan_control(payload, time.monotonic() - t_start)
                    if new_scans is not None and int(new_scans) != scans_sent:
                        scans_sent = int(new_scans)
                        parent_conn.send(f'SC{scans_sent}')
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
        parent_conn.send('exit')
        # Let the worker read out + save, however long that takes — the GUI
        # stop path never hard-kills a saving worker either. A second
        # KeyboardInterrupt gives up (data is lost: the finally block
        # terminates the still-running child).
        try:
            while True:
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
        except KeyboardInterrupt:
            pass
        raise
    finally:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join()


def _hand_attrs(worker, worker_args):
    """Copy the launch-time worker attributes (grid + correction state) the
    GUI sets next to Process creation — shared by run_worker/acquire_trace."""
    worker.awg_grid_cur = getattr(worker_args, 'awg_grid', 3.2)
    for attr in CORRECTION_ATTRS:
        if hasattr(worker_args, attr):
            setattr(worker, attr, getattr(worker_args, attr))


def _trace_child(worker, conn, args, phases, n_sweeps, script_test):
    """Child-process target for acquire_trace: run the Worker's dig_on
    preview UNMODIFIED, capturing the trace it hands to general.plot_1d
    (dig_on never sends data over the pipe — the GUI reads it off the
    LivePlot). The capture forwards to the real plot_1d, so a GUI that is
    open still shows the live 'Dig' preview. After each full phase cycle a
    'Status' percentage is reported; the parent answers 100% with 'exit',
    dig_on winds down through its normal stop path (pulser_close), and the
    last completed cycle's trace goes back as ('Trace', (t, i, q)). With
    l_mode=1 the digitizer accumulates across cycles, so that final trace
    is the phase-cycled average of everything acquired."""
    import atomize.general_modules.general_functions as general
    state = {'calls': 0, 'cycles': 0, 'done': None}
    orig_plot = general.plot_1d

    def capture(strname, xd, yd, *a, **kw):
        state['calls'] += 1
        if state['calls'] % phases == 0:
            state['cycles'] += 1
            t = np.asarray(xd, dtype=float)
            i = np.asarray(yd[0], dtype=float)
            q = np.asarray(yd[1], dtype=float)
            # A readout with no fresh driver buffer returns (None, None),
            # which dig_on writes into its data array as NaN. The
            # cycle-boundary readout blocks for the cycle's last pack
            # (is_drain), so this should not happen here — but a NaN frame
            # must never become the returned trace.
            if np.isfinite(i).all() and np.isfinite(q).all():
                state['done'] = (t.tolist(), i.tolist(), q.tolist())
            conn.send(('Status', min(100, int(100 * state['cycles'] / n_sweeps))))
        try:
            orig_plot(strname, xd, yd, *a, **kw)
        except Exception:
            pass

    general.plot_1d = capture
    worker.dig_on(conn, *args, script_test)
    if state['done'] is not None:
        conn.send(('Trace', state['done']))
    conn.send(('TraceEnd', ''))


def acquire_trace(worker_args, n_sweeps=1, script_test=False,
                  on_status=None, on_message=None, poll_s=0.2):
    """Averaged echo trace via the Worker's dig_on preview path.

    Runs n_sweeps full phase cycles in the accumulating (l_mode=1) readout,
    stops the preview exactly like the GUI Stop button ('exit' over the
    pipe) and returns (t_ns, i_mv, q_mv) numpy arrays — the trace is already
    demodulated and rotated by the preset's phase orders when iq_cor == 1.
    script_test=True runs dig_on's single-shot validation pass instead and
    returns {'status': 'test-ok'}.

    INVARIANT — no mid-run parameter changes: the accumulating readout's
    driver buffer (data_raw/count_nip) is allocated once and NEVER cleared
    on a parameter change, so any live-edit command ('PU'/'NA'/'RR'/'FI',
    ...) would sum new-parameter shots into old-parameter data and corrupt
    the average (the GUI tunes in live mode, where the buffer resets every
    call, for exactly this reason). This function therefore sends nothing
    but 'start' and 'exit' — never add live-edit commands here. To change
    any parameter, return and call acquire_trace again: each call spawns a
    fresh child with a fresh accumulator.
    """
    args = worker_args.dig_args()
    phases = len(worker_args.rect[0][3])
    if phases < 2:
        # dig_on only calls pulser_pulse_reset when PHASES != 1, so with a
        # single phase nIP_No_brd grows past total_points: the blocking
        # drain (is_drain) never fires after the first readout and the
        # parser's in-range filter may drop every later pack's nid — the
        # accumulating readout is only well-defined per phase-cycle.
        raise EngineError(
            'acquire_trace needs a phase-cycled preset (>= 2 steps); '
            'single-phase presets never reset the pack counter in the '
            'accumulating preview readout. Add a 2-step cycle (e.g. +x, -x).')
    worker = Worker()
    _hand_attrs(worker, worker_args)
    parent_conn, child_conn = Pipe()
    process = Process(target=_trace_child,
                      args=(worker, child_conn, args, phases,
                            max(1, int(n_sweeps)), script_test))
    process.start()
    parent_conn.send('start')

    trace = None
    exit_sent = False
    try:
        while True:
            if not parent_conn.poll(poll_s):
                if not process.is_alive():
                    raise EngineError('worker exited without reporting a trace')
                continue

            kind, payload = parent_conn.recv()
            if kind == 'Error':
                raise EngineError(f'worker error:\n{payload}')
            if kind == 'Status':
                if on_status is not None:
                    on_status(payload)
                if payload >= 100 and not exit_sent and not script_test:
                    # 'exit' is the ONLY command this loop may ever send:
                    # anything else is a live edit, which corrupts the
                    # accumulating buffer (see the docstring invariant)
                    exit_sent = True   # script_test single-shots on its own
                    try:
                        parent_conn.send('exit')
                    except (BrokenPipeError, OSError):
                        pass
            elif kind == 'Message':
                if on_message is not None:
                    on_message(payload)
            elif kind == 'Trace':
                trace = payload
            elif kind == 'TraceEnd':
                if script_test:
                    return {'status': 'test-ok'}
                if trace is None:
                    raise EngineError('preview ended without a captured trace')
                t, i, q = (np.asarray(v, dtype=float) for v in trace)
                return t, i, q
            # 'PulseList' / 'Count' / 'Average' / ('', 'Pulses are stopped')
            # are preview chatter — ignore

    except KeyboardInterrupt:
        try:
            parent_conn.send('exit')
        except (BrokenPipeError, OSError):
            pass
        raise
    finally:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join()


def load_1d(path):
    """Load a worker 1-D save (iq_cor == 1 format: axis, I, Q columns,
    '# '-commented header lines). Returns (axis, i, q) float arrays."""
    arr = np.genfromtxt(path, dtype=float, delimiter=',', encoding='latin1')
    if arr.ndim != 2 or arr.shape[1] < 3:
        raise EngineError(f'{path}: expected a 3-column 1-D save, '
                          f'got shape {getattr(arr, "shape", None)}')
    return arr[:, 0], arr[:, 1], arr[:, 2]


def acquire_1d(worker_args, sweep_type, save_path,
               on_status=None, on_message=None):
    """Run a real experiment to completion and return its 1-D result
    (axis, i, q). The axis unit is the sweep's: seconds for the time sweeps,
    % for Amplitude, Gauss for Field.

    Requires worker_args.iq_cor == 1 (preset 'IQ Correction:  2'), otherwise
    the worker writes the raw 2-D format this loader does not parse.
    """
    if worker_args.iq_cor != 1:
        raise EngineError("acquire_1d needs iq_cor == 1 "
                          "(preset 'IQ Correction:  2')")
    run_worker(worker_args, sweep_type, save_path=save_path,
               on_status=on_status, on_message=on_message)
    return load_1d(save_path)
