"""Experiment primitives: T2 (Hahn echo decay, linear tau sweep) and T1
(inversion recovery, log-time sweep) on the engine's acquire_1d path, with
relaxation fits.

Sweep mechanics (mirrors the Worker's own axis rules):
- Linear Time: the swept delay lives in the pulses — every slot with a
  nonzero start increment moves, in the fixed ratio the preset encodes
  (hahn: pi moves 1 unit/point, DETECTION 2). tau_start/tau_step re-anchor
  and re-scale those increments (`_retau`); the worker's time axis then
  starts at the first moving P2..P9 pulse's start with the DETECTION
  increment as its step, i.e. total evolution time — the correct T2 axis.
- Log Time: the worker builds the delays itself from Log Start/Log End
  (10^linspace, grid-rounded, deduplicated — the POINT COUNT MAY SHRINK),
  and offsets the axis by the first moving pulse's start. t_start/t_end map
  to log10(ns); the swept ADDED delay spans ~[0, t_end - t_start] with
  t_start setting the log-spacing density floor (the GUI's own semantics).

Fits use a characteristic-time initial guess (1/e crossing of the tail-
anchored amplitude) — a free fit from generic p0 degenerates on log-spaced
T1 data. Gated by the HARD `relaxation_fit` judge (deliberately not named
'fit_quality', which steps.py treats as advisory).
"""
import numpy as np
from scipy.optimize import curve_fit

from atomize.epr_auto.engine import snapshot
from atomize.epr_auto.primitives.judges import (
    JudgeReport, echo_snr, relaxation_fit,
)
from atomize.epr_auto.primitives.tune import _acquire, _build, _to_real


def _fmt_s(seconds):
    """0.0000018 -> '1.8 us' (3 significant digits)."""
    ns = float(seconds) * 1e9
    for unit, div in (('ns', 1.0), ('us', 1e3), ('ms', 1e6)):
        if abs(ns) < 1000.0 * div:
            return f'{ns / div:.3g} {unit}'
    return f'{ns / 1e9:.3g} s'


def _load(preset, want):
    pre = preset if isinstance(preset, snapshot.Preset) \
        else snapshot.load_preset(preset)
    if pre.sweep_type != want:
        raise ValueError(f'{pre.path}: needs a {want!r} preset, '
                         f'got {pre.sweep_type!r}')
    return pre


def _window_override(pre, window):
    """window='preset' pins the preset's own stored window by overriding the
    session echo_window entry _build would otherwise flow in ('auto')."""
    if window == 'preset':
        return {'win_left_ns': pre.win_left_ns,
                'win_right_ns': pre.win_right_ns}
    return {}


def _retau(pre, tau_start_ns, tau_step_ns):
    """Re-anchor a Linear Time preset's tau sweep in place.

    Moving pulses = active slots with nonzero start increment (DETECTION
    included). Their increments encode the per-point shift RATIO (hahn: pi 1
    unit, DETECTION 2 — the echo moves at twice the pi delay); the sweep's
    tau anchor is the first moving P2..P9 pulse's start — the same pulse the
    worker takes as the axis start (f_delay). Each moving pulse gets
    start += units * (tau_start - anchor) and st_inc = units * tau_step,
    which preserves the geometry ratios for any preset of this family.
    Returns the grid-snapped (tau_start, tau_step) actually applied."""
    g = pre.awg_grid
    moving = [(i, s) for i, s in enumerate(pre.slots)
              if s.active and s.st_inc != 0.0]
    anchor = next((s for i, s in moving if i > 0), None)
    if anchor is None:
        raise ValueError(f'{pre.path}: no swept pulse (active P2..P9 with a '
                         'nonzero start increment)')
    tau_start = snapshot._snap(tau_start_ns, g)
    tau_step = snapshot._snap(tau_step_ns, g)
    base = min(abs(s.st_inc) for _, s in moving)
    tau0 = anchor.start
    for i, s in moving:
        units = s.st_inc / base
        new_start = round(s.start + units * (tau_start - tau0), 1)
        if new_start < 0:
            raise ValueError(
                f'{pre.path}: tau_start {tau_start} ns moves P{i + 1} to '
                f'{new_start} ns (< 0) — the preset geometry cannot reach it')
        s.start = new_start
        s.st_inc = round(units * tau_step, 1)
    return tau_start, tau_step


def _period_check(pre, extent_ns, knob):
    """Friendly version of the driver's 'sequence longer than one repetition
    period' assert: name the knobs (the estimate errs slightly long — by
    ~t_start on the log sweep — so a borderline pass here can still be
    caught by the authoritative driver check in the pre-flight)."""
    period_ns = 1e9 / pre.rep_rate
    if extent_ns >= period_ns:
        raise ValueError(
            f'{pre.path}: the sweep extends the sequence to '
            f'~{extent_ns / 1e6:.2f} ms but the repetition period at '
            f'{pre.rep_rate} Hz is {period_ns / 1e6:.2f} ms — lower rep_rate '
            f'or shorten {knob}')


def _apply_rep_rate(pre, rep_rate):
    if rep_rate is not None:
        pre.rep_rate = float(rep_rate)


def _duration_policy(session, max_duration, scans):
    """scan_control consumer for the executor's 'SC<n>' channel (the Phase 3
    adaptive-scan hook): when the projected wall-clock time exceeds the
    max_duration budget, shrink the scan count so the run finishes inside it
    with the data acquired so far intact. Ratchets down only — a limit is
    never raised back once sent. None when no budget is set."""
    if max_duration is None:
        return None
    from atomize.epr_auto.params import parse_time_ns
    budget_s = parse_time_ns(max_duration) / 1e9
    state = {'limit': None}

    def control(pct, elapsed_s):
        # wait for a stable projection: early Status ticks (setup, first
        # points) extrapolate wildly
        if pct < 2 or elapsed_s < 10:
            return state['limit']
        projected = elapsed_s * 100.0 / pct
        if projected <= budget_s * 1.05:      # 5% grace: don't cut for jitter
            return state['limit']
        n = int(max(1, min(scans, scans * budget_s / projected)))
        if state['limit'] is None:
            session.log(f'      max_duration {max_duration}: projected '
                        f'{projected:.0f} s over budget {budget_s:.0f} s -> '
                        f'scan limit {n} of {scans}')
        if state['limit'] is None or n < state['limit']:
            state['limit'] = n
        return state['limit']

    return control


def _char_time(x, y, asymptote, amplitude):
    """Initial guess for the fit's characteristic time: first x where
    |y - asymptote| decays below |amplitude|/e. A free fit from a generic p0
    degenerates on log-spaced T1 sweeps (most points sit in the plateau);
    this anchors it to the data's own crossing."""
    dev = np.abs(y - asymptote)
    thresh = abs(amplitude) / np.e
    below = np.nonzero(dev <= thresh)[0]
    if below.size and x[below[0]] > 0:
        return float(x[below[0]])
    return float(x[-1] / 3) if x[-1] > 0 else 1.0


def _tail_mean(y):
    return float(np.mean(y[-max(3, len(y) // 10):]))


def _fit_stretched(x_s, y):
    """y = a * exp(-(t/t2)^beta) + c on t = x - x[0] (the constant axis
    offset — the preset's initial tau — folds into a, leaving t2 exact)."""
    x = np.asarray(x_s, float)
    y = np.asarray(y, float)
    t = x - x[0]
    c0 = _tail_mean(y)
    a0 = float(y[0] - c0) or float(np.max(np.abs(y - c0))) or 1.0
    t2_0 = _char_time(t, y, c0, a0)
    span = float(t[-1]) if t[-1] > 0 else 1.0
    lo = [-np.inf, span * 1e-4, 0.3, -np.inf]
    hi = [np.inf, span * 100, 3.0, np.inf]
    p0 = [a0, min(max(t2_0, lo[1] * 2), hi[1] / 2), 1.0, c0]

    def model(t, a, t2, beta, c):
        return a * np.exp(-(t / t2) ** beta) + c

    p, _ = curve_fit(model, t, y, p0=p0, bounds=(lo, hi), maxfev=20000)
    return {'t_s': float(p[1]), 'beta': round(float(p[2]), 3),
            'amplitude': float(p[0]), 'offset': float(p[3]),
            'y_fit': model(t, *p), 'n_params': 4}


def _fit_recovery(x_s, y):
    """y = a - b * exp(-t/t1) on t = x - x[0] (b absorbs the offset)."""
    x = np.asarray(x_s, float)
    y = np.asarray(y, float)
    t = x - x[0]
    a0 = _tail_mean(y)                      # recovered asymptote
    b0 = float(a0 - y[0]) or float(np.max(np.abs(y - a0))) or 1.0
    t1_0 = _char_time(t, y, a0, b0)
    span = float(t[-1]) if t[-1] > 0 else 1.0
    lo = [-np.inf, -np.inf, span * 1e-5]
    hi = [np.inf, np.inf, span * 100]
    p0 = [a0, b0, min(max(t1_0, lo[2] * 2), hi[2] / 2)]

    def model(t, a, b, t1):
        return a - b * np.exp(-t / t1)

    p, _ = curve_fit(model, t, y, p0=p0, bounds=(lo, hi), maxfev=20000)
    return {'t_s': float(p[2]), 'amplitude': float(p[1]),
            'offset': float(p[0]), 'y_fit': model(t, *p), 'n_params': 3}


def _finish(session, acq, fit_func, key, fit_name, extra):
    """Shared tail: rotate, fit, judge, package."""
    x, i, q, path = acq
    sig = i + 1j * q
    y = _to_real(sig)
    snr = echo_snr(sig)
    try:
        fit = fit_func(x, y)
    except (RuntimeError, ValueError) as e:   # curve_fit no-convergence
        judge = JudgeReport('relaxation_fit', False, 0.0,
                            {'note': f'fit failed: {e}'})
        return ({key: None, 'fit': fit_name, 'data_file': path, **extra},
                [snr, judge])
    judge = relaxation_fit(y, fit['y_fit'], fit['n_params'])
    result = {key: _fmt_s(fit['t_s']), f'{key}_s': fit['t_s'],
              'fit': fit_name, 'npoints': int(len(x)), 'data_file': path,
              **{k: v for k, v in fit.items() if k not in ('y_fit', 'n_params', 't_s')},
              **extra}
    return result, [snr, judge]


def t2(session, preset, tau_start, tau_step, points, scans, window='auto',
       max_duration=None, rep_rate=None):
    """Hahn echo decay: linear tau sweep re-anchored to tau_start/tau_step,
    stretched-exponential fit. `preset` may be an already-loaded (e.g.
    apply_cal-patched) Preset."""
    from atomize.epr_auto.params import parse_time_ns
    pre = _load(preset, 'Linear Time')
    tau_s, tau_st = _retau(pre, parse_time_ns(tau_start),
                           parse_time_ns(tau_step))
    _apply_rep_rate(pre, rep_rate)
    _period_check(pre, snapshot.AWG_OUTPUT_SHIFT_NS + max(
        s.start + s.length + (points - 1) * s.st_inc
        for s in pre.slots if s.active), 'the tau sweep (tau_step x points)')
    pre, wa = _build(session, pre, exp_name='T2', points=points, scans=scans,
                     **_window_override(pre, window))
    acq = _acquire(session, wa, pre.sweep_type, 't2', log=session.log,
                   scan_control=_duration_policy(session, max_duration, scans))
    extra = {'tau_start_ns': tau_s, 'tau_step_ns': tau_st, 'window': window}
    if acq is None:
        return ({'t2': '1.8 us', 'fit': 'stretched_exp', 'canned': True,
                 **extra},
                [JudgeReport('relaxation_fit', True, float('inf'),
                             {'note': 'dry-run, not judged'})])
    return _finish(session, acq, _fit_stretched, 't2', 'stretched_exp', extra)


def t1(session, preset, t_start, t_end, points, scans, window='auto',
       max_duration=None, rep_rate=None):
    """Inversion recovery: log-time sweep (Log Start/End = log10 ns),
    a - b*exp(-t/T1) fit with the characteristic-time initial guess. The
    worker deduplicates the grid-rounded log axis, so the result's npoints
    may be below `points`. A T1 sweep needs 1/rep_rate longer than the
    sequence at t_end — and physically several times the expected T1."""
    from atomize.epr_auto.params import parse_time_ns
    pre = _load(preset, 'Log Time')
    t_start_ns = parse_time_ns(t_start)
    t_end_ns = parse_time_ns(t_end)
    log_start = float(np.log10(t_start_ns))
    log_end = float(np.log10(t_end_ns))
    _apply_rep_rate(pre, rep_rate)
    _period_check(pre, snapshot.AWG_OUTPUT_SHIFT_NS + (t_end_ns - t_start_ns)
                  + max(s.start + s.length for s in pre.slots if s.active),
                  't_end')
    pre, wa = _build(session, pre, exp_name='T1', points=points, scans=scans,
                     log_start=log_start, log_end=log_end,
                     **_window_override(pre, window))
    acq = _acquire(session, wa, pre.sweep_type, 't1', log=session.log,
                   scan_control=_duration_policy(session, max_duration, scans))
    extra = {'t_start': ' '.join(str(t_start).split()),
             't_end': ' '.join(str(t_end).split()), 'window': window}
    if acq is None:
        return ({'t1': '1.2 ms', 'fit': 'exp_recovery', 'canned': True,
                 **extra},
                [JudgeReport('relaxation_fit', True, float('inf'),
                             {'note': 'dry-run, not judged'})])
    return _finish(session, acq, _fit_recovery, 't1', 'exp_recovery', extra)
