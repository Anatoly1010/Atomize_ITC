"""Experiment primitives: T2 (Hahn echo decay, linear tau sweep) and T1
(inversion recovery, log-time sweep) on the engine's acquire_1d path, with
relaxation fits.

Sweep mechanics (mirrors the Worker's own axis rules):
- Linear Time: the swept delay lives in the pulses — every slot with a
  nonzero start increment moves, in the fixed ratio the preset encodes
  (hahn: pi moves 1 unit/point, DETECTION 2). tau_start/tau_step re-anchor
  and re-scale those increments (`_retau`); the worker's time axis starts at
  the DETECTION start (= 2*tau_start for a re-anchored Hahn echo; a manual-x0
  preset uses its own x0/xdelta instead) with the DETECTION increment
  (2*tau_step) as its step, so the SAVED axis x IS the physical evolution
  time 2*tau = 2*tau_start + i*2*tau_step — the correct T2 axis. The T2 fit
  runs on this ABSOLUTE axis (see `_fit_stretched`): it must NOT rebase to
  x - x[0], because x[0] = 2*tau_start is a nonzero origin that, for a
  stretched exponential, does not fold into the amplitude.
- Log Time: the worker builds the delays itself from Log Start/Log End
  (10^linspace, grid-rounded, deduplicated — the POINT COUNT MAY SHRINK),
  and offsets/scales the axis using the preset's moving pulses or manual
  origin. t_start/t_end map to log10(ns); the swept ADDED delay spans
  ~[0, t_end - t_start] with
  t_start setting the log-spacing density floor (the GUI's own semantics).

Fits use a characteristic-time initial guess (1/e crossing of the tail-
anchored amplitude) — a free fit from generic p0 degenerates on log-spaced
T1 data. Gated by the HARD `relaxation_fit` judge (deliberately not named
'fit_quality', which steps.py treats as advisory).
"""
import copy
import time

import numpy as np
from scipy.optimize import curve_fit

from atomize.epr_auto.engine import snapshot
from atomize.epr_auto.primitives.judges import (
    JudgeReport, echo_snr, relaxation_fit,
)
from atomize.epr_auto.primitives.tune import (
    _acquire, _build, _data_files, _full_2d, _resolve_rep_rate, _to_real)
from atomize.epr_auto.primitives.relaxation_range import decision, plateau
from atomize.epr_auto.primitives import relaxation_series


def _fmt_s(seconds):
    """0.0000018 -> '1.8 us' (3 significant digits)."""
    ns = float(seconds) * 1e9
    for unit, div in (('ns', 1.0), ('us', 1e3), ('ms', 1e6)):
        if abs(ns) < 1000.0 * div:
            return f'{ns / div:.3g} {unit}'
    return f'{ns / 1e9:.3g} s'


def _load(preset, want):
    pre = copy.deepcopy(preset) if isinstance(preset, snapshot.Preset) \
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
    if not any(i == 0 for i, _ in moving):
        # DETECTION (slot 0) frozen => the echo does not track the sweep, so
        # the worker's axis is a pulse-POSITION sweep, not an evolution-time
        # decay (e.g. 4pdeer, whose only moving slot is the pump). exp.t2 on
        # such a preset would report a meaningless "T2"; reject it loudly.
        raise ValueError(f'{pre.path}: the DETECTION pulse does not move '
                         '(st_inc == 0) — not a moving-echo (Hahn) T2 preset; '
                         'exp.t2 needs the echo to follow the tau sweep')
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
    # A single Status tick can spike `projected` on a transient wall-clock
    # stall (e.g. the per-scan temperature-settle wait, ~8 s with no pct
    # advance); require the over-budget condition to persist K consecutive
    # ticks before cutting, so a momentary spike is not made permanent by the
    # ratchet. Still ratchet-DOWN only once a cut is committed.
    OVER_TICKS = 3
    state = {'limit': None, 'over': 0}

    def control(pct, elapsed_s):
        # wait for a stable projection: early Status ticks (setup, first
        # points) extrapolate wildly
        if pct < 2 or elapsed_s < 10:
            return state['limit']
        projected = elapsed_s * 100.0 / pct
        if projected <= budget_s * 1.05:      # 5% grace: don't cut for jitter
            state['over'] = 0                 # transient over-run: reset streak
            return state['limit']
        state['over'] += 1
        if state['over'] < OVER_TICKS:        # not yet a sustained over-run
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


# cuts the measured projection undershoot from ~50-80% of runs to ~25% at ~15% extra scans (2026-07-23 review, P6)
_PROJECTION_MARGIN = 1.15


def _snr_policy(session, target_snr, scans):
    """on_scan_data consumer for the executor's opt-in 'ScanData' channel:
    SNR-driven scan count. `scans` is the ceiling; after each completed scan k
    the accumulated curve's SNR is measured with judges.echo_snr — the SAME
    metric as the final judge, so the stopping rule and pass/fail agree
    (MAD-of-diff noise sigma: fit-residual sigma is inflated by systematic
    misfit that more scans cannot average down). sqrt(N) scaling projects the
    needed total, N ~ k * (target/SNR_k)^2:
    - SNR_k >= target: stop now ('SC k' — a direct measurement, any k);
    - else shrink the ceiling to the projection, but only from k >= 2 (one
      early noisy estimate must not cut the run) and never below k.
    The executor's shared ratchet min-combines this with _duration_policy and
    never re-raises a sent limit. None when no target is set; a target with
    scans <= 1 is announced as inert (the policy only ever LOWERS the scan
    ceiling — with one scan there is nothing to shrink, and it never raises
    the count to chase the target)."""
    if target_snr is None:
        return None
    if int(scans) <= 1:
        session.log(f'      warning: target_snr {float(target_snr):g} has no '
                    f'effect with scans: {scans} — it only lowers the scan '
                    'ceiling; set scans to the acceptable time budget')
        return None
    target = float(target_snr)
    state = {'announced': False}

    def control(k, i_arr, q_arr):
        snr = echo_snr(np.asarray(i_arr, float) + 1j * np.asarray(q_arr, float))
        if not np.isfinite(snr.score):      # canned/zero-noise guard
            return None
        if snr.score >= target:
            session.log(f'      target_snr {target:g}: reached '
                        f'{snr.score:.1f} after scan {k} of {scans} — stopping')
            return k
        if k < 2:
            return None
        # margin: echo_snr grows slower than sqrt(k) (max|y| is noise-inflated at low k), so a raw projection undershoots the target
        needed = int(np.ceil(k * (_PROJECTION_MARGIN * target / snr.score) ** 2))
        if needed < scans and not state['announced']:
            state['announced'] = True
            session.log(f'      target_snr {target:g}: SNR {snr.score:.1f} '
                        f'after scan {k} -> projected {needed} of {scans} scans')
        return max(k, needed) if needed < scans else None

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
    """y = a * exp(-(x/t2)^beta) + c fitted against the ABSOLUTE saved axis x,
    which for a Hahn echo IS the total evolution time 2*tau (the worker's
    Linear-Time axis starts at the DETECTION start = 2*tau_start with the
    DETECTION increment 2*tau_step as its step; an xd!=0 preset uses its own
    x0/xdelta — either way x is the physical evolution-time axis). Do NOT
    rebase to x - x[0]: x[0] = 2*tau_start is a nonzero origin that, for a
    stretched exponential (beta != 1), does NOT fold into the amplitude —
    exp(-((x-x0)/t2)^beta) is not a rescaling of exp(-(x/t2)^beta) — so
    dropping it biased t2 and beta 8-32% low. data_treatment fits this same
    absolute-axis model."""
    x = np.asarray(x_s, float)
    y = np.asarray(y, float)
    c0 = _tail_mean(y)
    a0 = float(y[0] - c0) or float(np.max(np.abs(y - c0))) or 1.0
    t2_0 = _char_time(x, y, c0, a0)
    span = float(x[-1]) if x[-1] > 0 else 1.0
    lo = [-np.inf, span * 1e-4, 0.3, -np.inf]
    hi = [np.inf, span * 100, 3.0, np.inf]
    p0 = [a0, min(max(t2_0, lo[1] * 2), hi[1] / 2), 1.0, c0]

    def model(x, a, t2, beta, c):
        return a * np.exp(-(x / t2) ** beta) + c

    p, _ = curve_fit(model, x, y, p0=p0, bounds=(lo, hi), maxfev=20000)
    return {'t_s': float(p[1]), 'beta': round(float(p[2]), 3),
            'amplitude': float(p[0]), 'offset': float(p[3]),
            'y_fit': model(x, *p), 'n_params': 4}


def _fit_recovery(x_s, y):
    """y = a - b * exp(-t/t1) on t = x - x[0]. Unlike the stretched T2 fit,
    this model is a single exponential, so the constant axis origin genuinely
    folds into b (exp(-x0/t1) rescales b) and t1 is exact — rebasing is safe
    here and keeps the fit well-conditioned."""
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
    measured = {'npoints': int(len(x)), 'start_s': float(x[0]),
                'end_s': float(x[-1]), **_data_files(path)}
    try:
        fit = fit_func(x, y)
    except (RuntimeError, ValueError) as e:   # curve_fit no-convergence
        judge = JudgeReport('relaxation_fit', False, 0.0,
                            {'note': f'fit failed: {e}'})
        return ({key: None, 'fit': fit_name, **measured, **extra},
                [snr, judge])
    judge = relaxation_fit(y, fit['y_fit'], fit['n_params'])
    result = {key: _fmt_s(fit['t_s']), f'{key}_s': fit['t_s'],
              'fit': fit_name, **measured,
              **{k: v for k, v in fit.items() if k not in ('y_fit', 'n_params', 't_s')},
              **extra}
    return result, [snr, judge]


def _measure(session, pre, wa, tag, scans, max_duration, target_snr, range_check=None):
    snr_policy = _snr_policy(session, target_snr, scans)
    on_scan_data = None
    if snr_policy is not None or range_check is not None:
        wa.scan_data_flag = 1
        wa.scan_data_wait = 1

        def on_scan_data(k, i_arr, q_arr):
            if range_check is not None:
                try:
                    limit = range_check(k, i_arr, q_arr)
                except Exception as error:
                    range_check.report.update(status='failed', reason=str(error))
                    session.log(f'      adjust_range: check failed; continue current range — {error}')
                    limit = None
                if limit is not None or range_check.pending:
                    return limit
            return None if snr_policy is None else snr_policy(k, i_arr, q_arr)

    return _acquire(session, wa, pre.sweep_type, tag, log=session.log,
                    scan_control=_duration_policy(session, max_duration, scans),
                    on_scan_data=on_scan_data)


def _log_grid(wa):
    raw = 10 ** np.linspace(wa.log_start, wa.log_end, wa.points)
    return np.unique(wa.awg_grid * np.round(raw / wa.awg_grid))


def _revised_sweep(session, pre, wa, acq, kind, plan, max_points,
                    minimum_span=0.0, check_period=True):
    """Preserve spacing where possible and count the actual snapped grid."""
    revised = copy.deepcopy(pre)
    x = np.asarray(acq[0], float)
    window = {'win_left_ns': pre.win_left_ns, 'win_right_ns': pre.win_right_ns}
    if kind == 't2':
        count = (2 * len(x) - 1 if plan['action'] == 'extend'
                 else plan['target_points'])
        count = max(count, int(np.ceil(1 + minimum_span * (len(x) - 1))))
        points = min(count, max_points)
        swept = [s for s in revised.slots if s.active and s.st_inc != 0]
        step = min(abs(s.st_inc) for s in swept)
        if count > max_points:
            if revised.xdelta != 0:
                raise ValueError('cannot rescale a manual T2 axis at adjust_max_points')
            new_step = snapshot._snap(step * (count - 1) / (points - 1), revised.awg_grid)
            for s in swept:
                s.st_inc = round(s.st_inc / step * new_step, 1)
        if check_period:
            _period_check(revised, snapshot.AWG_OUTPUT_SHIFT_NS + max(
                s.start + s.length + (points - 1) * s.st_inc
                for s in revised.slots if s.active), 'the revised tau sweep')
        revised, args = _build(session, revised, exp_name='T2_revised', points=points, **window)
        _full_2d(args, wa.save2d)
        return revised, args
    grid = _log_grid(wa)
    if len(grid) != len(x):
        raise ValueError('saved T1 axis does not match the prepared logarithmic grid')
    scale = (x[-1] - x[0]) / (grid[-1] - grid[0])
    if not np.allclose(x, x[0] + scale * (grid - grid[0]), rtol=1e-5, atol=1e-11):
        raise ValueError('saved T1 axis is inconsistent with the prepared logarithmic grid')
    spacing = (wa.log_end - wa.log_start) / (wa.points - 1)
    if plan['action'] == 'extend':
        end = grid[0] + 2 * (grid[-1] - grid[0])
    elif plan['target_points'] <= len(grid):
        end = grid[plan['target_points'] - 1]
    else:
        extra = plan['target_points'] - len(grid)
        end = min(grid[-1] * 10 ** min(extra * spacing, 1),
                  grid[0] + 2 * (grid[-1] - grid[0]))
    floor = grid[0] + minimum_span * (grid[-1] - grid[0])
    limited = end < floor
    log_end = snapshot._log_snap(np.log10(max(end, floor)), wa.awg_grid == snapshot.AWG_GRID_NS)
    requested_end = log_end
    while wa.awg_grid * round(10 ** log_end / wa.awg_grid) < floor:
        requested_end += 0.001
        log_end = snapshot._log_snap(requested_end, wa.awg_grid == snapshot.AWG_GRID_NS)
    points = min(max_points, max(60, int(round((log_end - wa.log_start) / spacing)) + 1))
    revised, args = _build(session, revised, exp_name='T1_revised', points=points,
                            log_start=wa.log_start, log_end=log_end, **window)
    _full_2d(args, wa.save2d)
    if plan['action'] == 'resize' and plan['target_points'] <= len(grid) and not limited:
        wanted = min(plan['target_points'], max_points)
        for _ in range(8):
            actual = len(_log_grid(args))
            if actual == wanted or args.points >= max_points:
                break
            points = min(max_points, max(60, args.points + wanted - actual))
            revised, args = _build(session, revised, exp_name='T1_revised', points=points,
                                    log_start=wa.log_start, log_end=log_end, **window)
            _full_2d(args, wa.save2d)
    return revised, args


def _range_settings(pre, wa, kind):
    if kind == 't2':
        moving = [s for s in pre.slots if s.active and s.st_inc != 0]
        anchor = next(s for s in pre.slots[1:] if s.active and s.st_inc != 0)
        return {'points': wa.points, 'tau_start_ns': anchor.start,
                'tau_step_ns': min(abs(s.st_inc) for s in moving),
                'span_ns': (wa.points - 1) * abs(pre.slots[0].st_inc)}
    grid = _log_grid(wa)
    return {'points': wa.points, 'log_start': wa.log_start, 'log_end': wa.log_end,
            'span_ns': float(grid[-1] - grid[0])}


def _reuse_range(session, pre, wa, kind, key):
    """Apply only sweep controls to freshly loaded and calibrated pulses."""
    selected = relaxation_series.choose(session, key)
    if selected is None:
        return pre, wa, None
    settings = selected['range']
    candidate = copy.deepcopy(pre)
    overrides = {'points': settings['points'], 'win_left_ns': pre.win_left_ns,
                 'win_right_ns': pre.win_right_ns}
    try:
        if kind == 't2':
            _retau(candidate, settings['tau_start_ns'], settings['tau_step_ns'])
        else:
            overrides.update(log_start=settings['log_start'], log_end=settings['log_end'])
        candidate, args = _build(session, candidate, exp_name=kind.upper(), **overrides)
        _full_2d(args, wa.save2d)
        if kind == 't1':
            from atomize.epr_auto.primitives.relaxation_timing import maximum_t1_rate
            rate = maximum_t1_rate(args)
            args.rep_rate = str(rate)
            candidate.rep_rate = rate
        else:
            _period_check(candidate, snapshot.AWG_OUTPUT_SHIFT_NS + max(
                s.start + s.length + (args.points - 1) * s.st_inc
                for s in candidate.slots if s.active), 'the carried tau sweep')
    except ValueError as error:
        session.log(f'      adjust_range: carried range cannot be used — {error}; using protocol range')
        return pre, wa, {'status': 'skipped_limits', 'reason': str(error), **selected}
    session.log(f"      adjust_range: using range from {selected['source_data_file']} "
                f"at {selected['source_temperature_k']} K; {args.points} requested points, "
                f'{float(args.rep_rate):g} Hz')
    return candidate, args, {'status': 'used', **selected}


def _learn_range(session, pre, wa, acq, kind, key, max_points, result, judges):
    """Prepare the next range without another measurement at this temperature."""
    report = result['range_adjustment']
    record = report.get('final', report['initial'])
    if record['plateau']['status'] != 'confirmed':
        return
    if not any(j.name == 'relaxation_fit' and j.passed for j in judges):
        return
    measured = _range_settings(pre, wa, kind)
    plan = decision(record['plateau'], kind, record['npoints'])
    proposed = measured
    if plan.get('next_action') == 'resize':
        next_plan = {**plan, 'action': 'resize'}
        try:
            candidate, args = _revised_sweep(session, pre, wa, acq, kind, next_plan,
                                             max_points, minimum_span=0.75, check_period=False)
            proposed = _range_settings(candidate, args, kind)
        except ValueError as error:
            report['planning_note'] = str(error)
    report['next_range'] = proposed
    report['next_range_rule'] = 'warming: shorten by at most 25%; cooling/unknown: retain measured span'
    relaxation_series.stage(session, key, measured, proposed, acq[3])
    session.log(f"      adjust_range: accepted current curve; next range span "
                f"{_fmt_s(proposed['span_ns'] * 1e-9)}, {proposed['points']} requested points")


def _range_record(acq, wa, kind):
    x, i, q, path = acq
    measured = plateau(x, _to_real(i + 1j * q), kind)
    return {**_data_files(path), 'npoints': len(x),
            'start_s': float(x[0]), 'end_s': float(x[-1]),
            'rep_rate_hz': float(wa.rep_rate), 'plateau': measured}


class _EarlyRangeCheck:
    """Use up to three complete scans before allowing normal SNR accumulation."""

    def __init__(self, session, pre, wa, kind, max_points, scans, max_duration, started):
        from atomize.epr_auto.params import parse_time_ns
        self.session, self.pre, self.wa, self.kind = session, pre, wa, kind
        self.max_points = max_points
        self.limit = min(3, scans)
        self.started = started
        self.budget = None if max_duration is None else parse_time_ns(max_duration) / 1e9
        self.revised = None
        self.report = {'status': 'pending', 'checked_scans': 0}

    @property
    def pending(self):
        return self.report['status'] == 'pending'

    def remaining(self):
        return None if self.budget is None else self.budget - (time.monotonic() - self.started)

    def __call__(self, k, i_arr, q_arr):
        if not self.pending:
            return self.report['checked_scans'] if self.revised is not None else None
        grid = _log_grid(self.wa) if self.kind == 't1' else np.arange(self.wa.points)
        y = _to_real(np.asarray(i_arr) + 1j * np.asarray(q_arr))
        measured = plateau(grid, y, self.kind)
        plan = decision(measured, self.kind, len(grid))
        self.report.update(checked_scans=k, reason=plan['reason'],
                           plateau={key: value for key, value in measured.items() if key != 'onset_s'})
        if plan['action'] == 'keep':
            self.report['status'] = 'confirmed'
            self.session.log(f'      adjust_range: plateau confirmed after scan {k}; continue accumulation')
        elif plan['action'] == 'extend':
            seconds = self.remaining()
            if seconds is not None and seconds <= 0:
                self.report.update(status='skipped_budget', reason='time budget exhausted')
                return None
            try:
                preview = (grid * 1e-9, np.asarray(i_arr), np.asarray(q_arr), '')
                revised, args = _revised_sweep(self.session, self.pre, self.wa, preview,
                                               self.kind, plan, self.max_points)
                if self.kind == 't1':
                    from atomize.epr_auto.primitives.relaxation_timing import maximum_t1_rate
                    revised.rep_rate = maximum_t1_rate(args)
                    args.rep_rate = str(revised.rep_rate)
                else:
                    from atomize.epr_auto.engine import executor
                    executor.run_worker(args, 'Linear Time', script_test=True)
            except (ValueError, RuntimeError) as error:
                self.report.update(status='skipped_limits', reason=str(error))
                self.session.log(f'      adjust_range: extension unavailable; continue current range — {error}')
                return None
            seconds = self.remaining()
            if seconds is not None and seconds < _scan_seconds(args, self.kind):
                self.report.update(status='skipped_budget', reason='remaining budget is shorter than one revised scan')
                self.session.log('      adjust_range: no time for an extension; continue current range')
                return None
            self.revised = revised, args
            self.report['status'] = 'extend'
            self.session.log(f'      adjust_range: unfinished tail after scan {k}; stop early for one extension')
            return k
        elif k >= self.limit:
            self.report['status'] = 'unresolved'
            self.session.log(f'      adjust_range: tail uncertain after {k} scans; continue current range without a late repeat')
        return None


def _scan_seconds(wa, kind):
    points = len(_log_grid(wa)) if kind == 't1' else wa.points
    return points * len(wa.rect[0][3]) * wa.averages / float(wa.rep_rate)


def _adjust_range(session, pre, wa, acq, kind, scans, target_snr, range_check):
    """Use only an early extension decision; never restart a long completed run."""
    initial = _range_record(acq, wa, kind)
    plan = decision(initial['plateau'], kind, initial['npoints'])
    early = range_check.report
    report = {'status': plan['action'], 'reason': plan['reason'], 'initial': initial,
              'early_check': early}
    if range_check.revised is None:
        if early['status'] in ('skipped_budget', 'skipped_limits', 'failed'):
            report.update(status=early['status'], reason=early['reason'])
        elif plan['action'] == 'extend':
            report.update(status='kept_unconfirmed', reason='no early extension decision; no late repeat')
        session.log(f"      adjust_range: {report['reason']}")
        return acq, pre, wa, report
    seconds = range_check.remaining()
    revised, args = range_check.revised
    if kind == 't1':
        rate = float(args.rep_rate)
        session.log(f'      revised T1: maximum timing-compatible repetition rate {rate:g} Hz')
    actual_points = len(_log_grid(args)) if kind == 't1' else args.points
    minimum_scan_s = _scan_seconds(args, kind)
    if seconds is not None:
        # the early stop already reserved one revised scan
        seconds = max(seconds, minimum_scan_s)
    repeat_scans = scans if seconds is None else min(scans, max(1, int(seconds / minimum_scan_s)))
    args.scans = revised.scans = repeat_scans
    repeat_duration = None if seconds is None else f'{seconds:.9g} s'
    session.log(f"      adjust_range: {plan['reason']} — one revised acquisition, "
                f'{actual_points} points, {repeat_scans} scans')
    second = _measure(session, revised, args, f'{kind}_revised', repeat_scans,
                       repeat_duration, target_snr)
    if second is None:
        return acq, pre, wa, {**report, 'status': 'dry_run'}
    final = _range_record(second, args, kind)
    checked = decision(final['plateau'], kind, final['npoints'])
    satisfied = final['plateau']['status'] == 'confirmed'
    if not satisfied:
        session.log(f"      adjust_range: plateau not confirmed ({checked['reason']}); "
                    'no further automatic acquisition')
    report.update(status='repeated', final=final, plateau_confirmed=satisfied,
                  requested_points=args.points, scans=repeat_scans)
    return second, revised, args, report


def t2(session, preset, tau_start, tau_step, points, scans, window='auto',
       max_duration=None, rep_rate=None, target_snr=None, adjust_range=False,
       adjust_max_points=4096, save_2d=False):
    """Hahn echo decay: linear tau sweep re-anchored to tau_start/tau_step,
    stretched-exponential fit. `preset` may be an already-loaded (e.g.
    apply_cal-patched) Preset."""
    from atomize.epr_auto.params import parse_time_ns
    started = time.monotonic()
    pre = _load(preset, 'Linear Time')
    tau_s, tau_st = _retau(pre, parse_time_ns(tau_start),
                           parse_time_ns(tau_step))
    _apply_rep_rate(pre, _resolve_rep_rate(session, rep_rate))
    pre, wa = _build(session, pre, exp_name='T2', points=points, scans=scans,
                     **_window_override(pre, window))
    _full_2d(wa, save_2d)
    pre.rep_rate = float(wa.rep_rate)
    key, carried = None, None
    if adjust_range:
        key = relaxation_series.context_key(session, pre, 't2', _range_settings(pre, wa, 't2'),
                                             adjust_max_points)
        pre, wa, carried = _reuse_range(session, pre, wa, 't2', key)
        settings = _range_settings(pre, wa, 't2')
        tau_s, tau_st = settings['tau_start_ns'], settings['tau_step_ns']
    _period_check(pre, snapshot.AWG_OUTPUT_SHIFT_NS + max(
        s.start + s.length + (wa.points - 1) * s.st_inc
        for s in pre.slots if s.active), 'the tau sweep (tau_step x points)')
    early = (_EarlyRangeCheck(session, pre, wa, 't2', adjust_max_points,
                              scans, max_duration, started) if adjust_range else None)
    acq = _measure(session, pre, wa, 't2', scans, max_duration, target_snr, early)
    extra = {'tau_start_ns': tau_s, 'tau_step_ns': tau_st, 'window': window,
             'rep_rate_hz': float(wa.rep_rate)}
    if acq is None:
        if adjust_range:
            extra['range_adjustment'] = {'status': 'dry_run', 'reason': 'measured data required'}
        return ({'t2': '1.8 us', 'fit': 'stretched_exp', 'canned': True,
                 **extra},
                [JudgeReport('relaxation_fit', True, float('inf'),
                             {'note': 'dry-run, not judged'})])
    if adjust_range:
        acq, pre, wa, report = _adjust_range(session, pre, wa, acq, 't2', scans, target_snr, early)
        extra['range_adjustment'] = report
        if carried is not None:
            report['carried_range'] = carried
        extra['tau_step_ns'] = min(abs(s.st_inc) for s in pre.slots if s.active and s.st_inc != 0)
    extra['rep_rate_hz'] = float(wa.rep_rate)
    result, judges = _finish(session, acq, _fit_stretched, 't2', 'stretched_exp', extra)
    if adjust_range:
        _learn_range(session, pre, wa, acq, 't2', key, adjust_max_points, result, judges)
    return result, judges


def t1(session, preset, t_start, t_end, points, scans, window='auto',
       max_duration=None, rep_rate=None, target_snr=None, adjust_range=False,
       adjust_max_points=4096, save_2d=False):
    """Inversion recovery: log-time sweep (Log Start/End = log10 ns),
    a - b*exp(-t/T1) fit with the characteristic-time initial guess. The
    worker deduplicates the grid-rounded log axis, so the result's npoints
    may be below `points`. A T1 sweep needs 1/rep_rate longer than the
    sequence at t_end — and physically several times the expected T1."""
    from atomize.epr_auto.params import parse_time_ns
    started = time.monotonic()
    pre = _load(preset, 'Log Time')
    t_start_ns = parse_time_ns(t_start)
    t_end_ns = parse_time_ns(t_end)
    log_start = float(np.log10(t_start_ns))
    log_end = float(np.log10(t_end_ns))
    _apply_rep_rate(pre, _resolve_rep_rate(session, rep_rate))
    pre, wa = _build(session, pre, exp_name='T1', points=points, scans=scans,
                     log_start=log_start, log_end=log_end,
                     **_window_override(pre, window))
    _full_2d(wa, save_2d)
    pre.rep_rate = float(wa.rep_rate)
    key, carried = None, None
    if adjust_range:
        key = relaxation_series.context_key(session, pre, 't1', _range_settings(pre, wa, 't1'),
                                             adjust_max_points)
        pre, wa, carried = _reuse_range(session, pre, wa, 't1', key)
    if carried is None or carried['status'] != 'used':
        _period_check(pre, snapshot.AWG_OUTPUT_SHIFT_NS + (t_end_ns - t_start_ns)
                      + max(s.start + s.length for s in pre.slots if s.active),
                      't_end')
    early = (_EarlyRangeCheck(session, pre, wa, 't1', adjust_max_points,
                              scans, max_duration, started) if adjust_range else None)
    acq = _measure(session, pre, wa, 't1', scans, max_duration, target_snr, early)
    extra = {'t_start': ' '.join(str(t_start).split()),
             't_end': ' '.join(str(t_end).split()), 'window': window,
             'rep_rate_hz': float(wa.rep_rate)}
    if acq is None:
        if adjust_range:
            extra['range_adjustment'] = {'status': 'dry_run', 'reason': 'measured data required'}
        return ({'t1': '1.2 ms', 'fit': 'exp_recovery', 'canned': True,
                 **extra},
                [JudgeReport('relaxation_fit', True, float('inf'),
                             {'note': 'dry-run, not judged'})])
    if adjust_range:
        acq, pre, wa, report = _adjust_range(session, pre, wa, acq, 't1', scans, target_snr, early)
        extra['range_adjustment'] = report
        if carried is not None:
            report['carried_range'] = carried
        extra['t_start'] = f'{10 ** wa.log_start:.9g} ns'
        extra['t_end'] = f'{10 ** wa.log_end:.9g} ns'
    extra['rep_rate_hz'] = float(wa.rep_rate)
    result, judges = _finish(session, acq, _fit_recovery, 't1', 'exp_recovery', extra)
    if adjust_range:
        _learn_range(session, pre, wa, acq, 't1', key, adjust_max_points, result, judges)
    return result, judges
