"""Tuning primitives: auto-phase, pi calibration (fine), power-for-length (coarse).

All acquisition goes through the engine (snapshot -> Worker); every primitive
first pre-flights its exact WorkerArgs with script_test=True (the Worker
child forces test-mode devices for that run), then acquires for real — or,
in a dry-run session, stops after the pre-flight and returns a canned result
so the judges and the state flow are still exercised end-to-end.

Physics conventions (see ARCHITECTURE.md 'Flip-angle knobs'):
- The nutation presets are inversion-detection sequences: the swept pulse
  precedes a fixed selective echo pair, so the echo goes as cos(theta) of
  the swept pulse — pi at the first minimum, pi/2 at the zero crossing.
- In an Amplitude-sweep preset the swept pulse is the one with a nonzero
  Start Increment (the worker's name_list criterion); in a length-nutation
  preset it is the one with a nonzero Length Increment.
- theta(x) is fitted as b*x + s*x^2: the quadratic term absorbs amplifier
  compression, so amp(pi) and amp(pi/2) come out independently instead of
  assuming amp(pi) = 2*amp(pi/2).
"""
import math
import time

import numpy as np
from scipy.optimize import curve_fit

from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.primitives.judges import (
    JudgeReport, amplitude_rails, convergence, echo_snr, fit_quality,
    phase_coherence, pi_ratio_linearity,
)

# canned dry-run numbers (ratio deliberately != 2: the linearity judge must
# not learn to expect the ideal value)
_CANNED_PI, _CANNED_PI2 = 68.0, 33.5


# --------------------------------------------------------------- plumbing

def _session_overrides(session):
    """Calibration results earlier steps stored: flow them into every build."""
    ov = {}
    ap = session.state.get('auto_phase')
    if ap:
        ov['zero_order_deg'] = ap['zero_order_deg']
    fd = session.state.get('field')
    if fd:
        ov['field'] = float(str(fd).split(' ')[0])
    return ov


def _build(session, preset_path, exp_name, slot_coef=None, **overrides):
    """Preset -> (preset, WorkerArgs) with session calibrations + explicit
    overrides applied. slot_coef=(slot_index, value) overrides one pulse's
    amplitude coefficient (a nested field build_worker_args overrides can't
    reach). Accepts a path or an already-loaded Preset (which is mutated —
    pass a fresh parse, never a cached one)."""
    preset = preset_path if isinstance(preset_path, snapshot.Preset) \
        else snapshot.load_preset(preset_path)
    if slot_coef is not None:
        idx, value = slot_coef
        preset.slots[idx].coef = float(value)
    ov = _session_overrides(session)
    ov.update({k: v for k, v in overrides.items() if v is not None})
    wa = snapshot.build_worker_args(preset, exp_name=exp_name, **ov)
    return preset, wa


def _acquire(session, wa, sweep_type, tag, log=None):
    """Pre-flight, then acquire. Returns (x, i, q, path) or None in test mode."""
    if wa.iq_cor != 1:
        # check up front (not at acquire_1d time, after hardware may already
        # have moved) so the --test pre-flight rejects such a preset too
        raise ValueError("preset must be saved with 'IQ Correction:  2' "
                         '(IQ-corrected 1-D data) for automation acquisitions')
    executor.run_worker(wa, sweep_type, script_test=True)
    if session.test:
        return None
    session.ensure_hardware_locks()
    path = session.save_path(tag)
    x, i, q = executor.acquire_1d(wa, sweep_type, path,
                                  on_message=log and (lambda m: log(f'      worker: {m}')))
    return x, i, q, path


def _phase_deg(sig):
    from atomize.math_modules.fft import Fast_Fourier
    return Fast_Fourier.auto_phase_zero(sig)


def _to_real(sig):
    """Rotate a complex trace onto its principal axis (ph_correction
    convention: multiply by exp(+i*phi))."""
    phi = _phase_deg(sig)
    return (sig * np.exp(1j * np.radians(phi))).real


def _swept_slot(preset, mode):
    """Index (into preset.slots) of the pulse the sweep moves: nonzero
    st_inc for Amplitude presets, nonzero len_inc for length nutation."""
    attr = 'st_inc' if mode == 'amplitude' else 'len_inc'
    hits = [i for i, s in enumerate(preset.slots)
            if i > 0 and s.active and getattr(s, attr) != 0.0]
    if len(hits) != 1:
        raise ValueError(
            f'{preset.path}: expected exactly one swept pulse '
            f'(active P2..P9 with nonzero {attr}), found {len(hits)}')
    return hits[0]


# ------------------------------------------------------------- auto-phase

def auto_phase(session, preset, points=4, scans=1):
    """Acquire a short echo run, measure the residual signal phase
    (principal-axis auto_phase_zero) and store the corrected zero-order
    (digitizer_demodulate rotates by exp(-i*zero_order), so the update is
    zero_order_new = zero_order_used - phi_residual)."""
    pre, wa = _build(session, preset, exp_name='AutoPhase',
                     points=points, scans=scans)
    acq = _acquire(session, wa, pre.sweep_type, 'auto_phase', log=session.log)

    if acq is None:
        result = {'phase_deg': 0.0, 'zero_order_deg': pre.zero_order_deg,
                  'canned': True}
        session.state['auto_phase'] = {'zero_order_deg': pre.zero_order_deg}
        return result, [JudgeReport('phase_coherence', True, float('inf'),
                                    {'note': 'dry-run, not judged'})]

    x, i, q, path = acq
    sig = i + 1j * q
    phi = _phase_deg(sig)
    used = pre.zero_order_deg          # post-build: includes session override
    new_zero = round((used - phi) % 360.0, 2)

    session.state['auto_phase'] = {'zero_order_deg': new_zero}
    result = {'phase_deg': round(phi, 2), 'zero_order_deg': new_zero,
              'data_file': path}
    # phase_coherence, not echo_snr: a `points`-long trace has too few
    # point-to-point differences for the MAD-of-diff noise estimate
    return result, [phase_coherence(sig)]


# --------------------------------------------------------- pi calibration

def _nutation_model(x, a, b, s, k, c0):
    return a * np.cos(b * x + s * x ** 2) * np.exp(-k * x) + c0


def _smooth(y):
    w = max(3, len(y) // 20) | 1
    return np.convolve(y, np.ones(w) / w, mode='same')


def _theta_root(b, s, target):
    """Smallest positive x with b*x + s*x^2 == target (None if unreachable)."""
    if abs(s) < 1e-12:
        return target / b if b > 0 else None
    disc = b * b + 4 * s * target
    if disc < 0:
        return None
    roots = [r for r in ((-b + math.sqrt(disc)) / (2 * s),
                         (-b - math.sqrt(disc)) / (2 * s)) if r > 0]
    return min(roots) if roots else None


def _oriented_fit(x, y):
    """auto_phase_zero's principal axis is sign-blind, so the rotated trace
    can come out as -cos(theta); the model has no phase-offset term, so a
    flipped trace is unfittable and would poison the argmin fallback (the
    -cos minimum sits at theta=0). Resolve the orientation from the leading
    points — theta(x[0]) < pi/2 in the nutation presets, so a +cos trace
    starts positive — and fit; flip as a rescue only if that fit fails.
    (Fitting both and comparing SSR is NOT safe: the quadratic theta term
    can absorb a pi offset over a finite window, yielding a plausible-SSR
    fit with garbage roots.) Returns (oriented_y, popt, y_fit)."""
    if np.mean(y[:max(3, len(y) // 10)]) < 0:
        y = -y
    popt, y_fit = _fit_nutation(x, y)
    if popt is None:
        popt, y_fit = _fit_nutation(x, -y)
        if popt is not None:
            y = -y
    return y, popt, y_fit


# physical bounds on the fractional chirp r = s*x_max/b (theta' at the sweep
# end = b*(1+2r)): amplifier compression only SLOWS the rotation, moderately —
# without this bound the fit has a second basin (small b, large positive s:
# an accelerating chirp) that matches ~1.5 periods with a plausible SSR but a
# completely wrong theta shape between 0 and pi, wrecking the pi/2 root.
_R_MIN, _R_MAX = -0.35, 0.15


def _fit_nutation(x, y):
    """Fit y = a*cos(theta)*exp(-k*x) + c0, theta = b*x + s*x^2, with the
    chirp fitted as the bounded fraction r = s*x_max/b (see _R_MIN/_R_MAX).
    Returns ((a, b, s, k, c0), y_fit) or (None, None) on no convergence."""
    x_max = float(x[-1])
    ys = _smooth(y)
    x_min = x[int(np.argmin(ys))]
    if x_min <= x[0]:
        x_min = x[len(x) // 2]        # minimum at the left edge: bad seed
    p0 = [(ys.max() - ys.min()) / 2, math.pi / x_min, 0.0, 0.0, float(ys.mean())]
    span = float(x[-1] - x[0]) or 1.0
    bounds = ([0, 1e-6 / span, _R_MIN, 0, -np.inf],
              [np.inf, np.inf, _R_MAX, 10 / span, np.inf])

    def model_r(xx, a, b, r, k, c0):
        return a * np.cos(b * xx * (1 + r * xx / x_max)) * np.exp(-k * xx) + c0

    try:
        p, _ = curve_fit(model_r, x, y, p0=p0, bounds=bounds, maxfev=20000)
    except (RuntimeError, ValueError):
        return None, None
    a, b, r, k, c0 = p
    popt = (a, b, b * r / x_max, k, c0)          # callers see (a,b,s,k,c0)
    return popt, _nutation_model(x, *popt)


def _refine_minimum(x, y, x0, half_width):
    """Local parabola through the raw data around x0 -> vertex. The extremum
    position is model-independent (invariant under the theta(x) mapping), so
    this de-biases pi against the fit's s/k degeneracy."""
    # keep the window symmetric: a window clipped by the sweep edge skews
    # the parabola vertex
    half_width = min(half_width, x0 - x[0], x[-1] - x0)
    m = (x >= x0 - half_width) & (x <= x0 + half_width)
    if m.sum() < 5:
        return x0
    c = np.polyfit(x[m], y[m], 2)
    if c[0] <= 0:                      # not minimum-shaped: keep the fit root
        return x0
    v = -c[1] / (2 * c[0])
    return float(v) if x0 - half_width <= v <= x0 + half_width else x0


def _anchored_pi2(x, y, x_pi, popt):
    """pi/2 via an anchored re-fit: pin theta(x_pi) = pi at the (model-free)
    refined minimum, i.e. s = (pi - b*x_pi)/x_pi^2, and re-fit the rest.
    Pinning the theta map at the measured extremum removes the baseline /
    envelope degeneracy from the pi/2 root, which then comes out as reliably
    as pi itself (benchmark: sd ~0.4 vs ~2.4 units for the free fit's root).
    Returns None when the re-fit does not converge."""
    a0, b0, s0, k0, c00 = popt
    span = float(x[-1] - x[0]) or 1.0
    x_max = float(x[-1])
    # the anchor makes s a function of b, so the physical chirp bound
    # r = s*x_max/b in [_R_MIN, _R_MAX] becomes a b range (r decreases in b)
    b_lo = math.pi * x_max / (x_pi * (_R_MAX * x_pi + x_max))
    b_hi = math.pi * x_max / (x_pi * (_R_MIN * x_pi + x_max))

    def model(xx, a, b, k, c0):
        s = (math.pi - b * x_pi) / x_pi ** 2
        return a * np.cos(b * xx + s * xx ** 2) * np.exp(-k * xx) + c0

    try:
        p, _ = curve_fit(model, x, y,
                         p0=[a0, min(max(b0, b_lo), b_hi), max(k0, 1e-9), c00],
                         bounds=([0, b_lo, 0, -np.inf],
                                 [np.inf, b_hi, 10 / span, np.inf]),
                         maxfev=20000)
    except (RuntimeError, ValueError):
        return None
    b = p[1]
    return _theta_root(b, (math.pi - b * x_pi) / x_pi ** 2, math.pi / 2)


def pi_calibration(session, preset, mode='amplitude', channel='AWG',
                   points=None, scans=None, step=None, hold_amplitude=None):
    """Fine stage: nutation curve of the swept pulse -> amp/length of pi and
    pi/2, extracted independently through the theta(x) = b*x + s*x^2 fit.

    mode='amplitude': Amplitude-sweep preset, axis in % of AWG full scale
    (step overrides the preset's Amplitude Step). mode='length': linear-time
    nutation preset, axis converted to ns. hold_amplitude overrides the swept
    pulse's amplitude coefficient (used by power_for_length)."""
    if channel != 'AWG':
        raise ValueError('only the AWG channel is supported (RECT is a later phase)')

    want = 'Amplitude' if mode == 'amplitude' else 'Linear Time'
    pre_probe = snapshot.load_preset(preset)
    if pre_probe.sweep_type != want:
        raise ValueError(f'{preset}: mode {mode!r} needs a {want!r} preset, '
                         f'got {pre_probe.sweep_type!r}')
    slot = _swept_slot(pre_probe, mode)

    pre, wa = _build(session, pre_probe, exp_name='PiCal',
                     slot_coef=(slot, hold_amplitude) if hold_amplitude is not None else None,
                     points=points, scans=scans, step_ampl=step)
    sweep = pre.sweep_type
    acq = _acquire(session, wa, sweep, f'pi_cal_{mode}', log=session.log)
    unit = '%' if mode == 'amplitude' else 'ns'

    if acq is None:
        pi_v, pi2_v = _CANNED_PI, _CANNED_PI2
        result = {'pi': pi_v, 'pi2': pi2_v, 'unit': unit, 'mode': mode,
                  'ratio': round(pi_v / pi2_v, 3), 'rails': None, 'canned': True}
        session.state['pi_calibration'] = result
        judges = [pi_ratio_linearity(pi_v, pi2_v)]
        if mode == 'amplitude':
            judges.append(amplitude_rails(pi_v))
        return result, judges

    x, i, q, path = acq
    if mode == 'length':
        x = x * 1e9                    # worker saves the time axis in seconds
    sig = i + 1j * q

    judges = [echo_snr(sig)]
    y, popt, y_fit = _oriented_fit(x, _to_real(sig))
    if popt is not None:
        _, b, s, _, _ = popt
        judges.append(fit_quality(y, y_fit, n_params=5))
        pi_v = _theta_root(b, s, math.pi)
        pi2_v = _theta_root(b, s, math.pi / 2)
        # de-bias against the fit's s/k degeneracy: pi from the model-free
        # parabola vertex at the observed minimum, pi/2 from a re-fit with
        # theta anchored at that measured pi
        if pi_v is not None and pi_v <= x[-1]:
            w = (math.pi / 2) / (b + 2 * s * pi_v) if (b + 2 * s * pi_v) > 0 else 0
            if w > 0:
                pi_v = _refine_minimum(x, y, pi_v, w)
            anchored = _anchored_pi2(x, y, pi_v, popt)
            if anchored is not None:
                pi2_v = anchored
    else:
        # fallback: direct extremum / zero crossing on the smoothed curve,
        # oriented by the leading points (theta(x[0]) < pi/2 in the presets,
        # so a +cos trace starts positive)
        judges.append(JudgeReport('fit_quality', False, 0.0,
                                  {'note': 'nutation fit did not converge; '
                                           'direct extremum used'}))
        if np.mean(y[:max(3, len(y) // 10)]) < 0:
            y = -y
        ys = _smooth(y)
        pi_v = float(x[int(np.argmin(ys))])
        c0 = (ys.max() + ys.min()) / 2
        below = np.nonzero(ys < c0)[0]
        pi2_v = float(x[below[0]]) if below.size else None

    rails = None
    if pi_v is None or pi_v > x[-1]:
        # pi not reached within the sweep: x[-1] is a lower bound (still
        # usable as a direction for the coarse-stage vane math)
        rails, pi_v = 'high', float(x[-1])
    if mode == 'amplitude':
        rail_judge = amplitude_rails(100.0 if rails == 'high' else pi_v)
        judges.append(rail_judge)
        if not rail_judge.passed:
            rails = rails or rail_judge.details.get('rail')

    pi_v = round(float(pi_v), 2) if pi_v is not None else None
    pi2_v = round(float(pi2_v), 2) if pi2_v is not None else None
    result = {'pi': pi_v, 'pi2': pi2_v, 'unit': unit, 'mode': mode,
              'ratio': round(pi_v / pi2_v, 3) if pi_v and pi2_v else None,
              'rails': rails, 'data_file': path}
    if pi_v and pi2_v:
        judges.append(pi_ratio_linearity(pi_v, pi2_v))
    session.state['pi_calibration'] = result
    return result, judges


# ------------------------------------------------------- power for length

def _vane_db(mw):
    ans = str(mw.mw_bridge_rotary_vane())
    try:
        return float(ans.replace('dB', '').strip().split()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f'cannot parse rotary vane answer {ans!r}') from None


def _vane_set(session, target_db, overshoot=1.0):
    """Move the vane with the same-direction (from-above) approach to kill
    backlash, and wait out the mechanical move (36 ms/motor-step via the
    device's own calibration curve) — the vane must be at rest before the
    next acquisition starts in a separate worker process."""
    mw = session.mw_bridge
    target_db = round(float(target_db), 1)
    prev = _vane_db(mw)                # one read; track position locally
    seq = [target_db] if target_db <= prev else \
        [min(target_db + overshoot, 60.0), target_db]
    for db in seq:
        mw.mw_bridge_rotary_vane(db)
        if not session.test:
            wait_s = abs(36.0 * (mw.calibration(db) - mw.calibration(prev))) / 1000.0
            time.sleep(wait_s + 0.2)
        prev = db
    return target_db


def power_for_length(session, target_length, amplitude=95.0,
                     preset=None, tolerance='3.2 ns', max_iter=4,
                     rehome='no'):
    """Coarse stage: step the rotary vane until pi (measured by a length
    nutation at the held AWG amplitude) lands at the target length.
    B1 scales as 10^(-dB/20), so each iteration jumps
    dB += 20*log10(target/measured). Any vane move invalidates auto-phase
    and the fine calibration (session state) — re-run them after."""
    from atomize.epr_auto.params import parse_time_ns
    if preset is None:
        raise ValueError('power_for_length needs a length-nutation preset path')
    target_ns = parse_time_ns(target_length)
    tol_ns = parse_time_ns(tolerance)
    mw = session.mw_bridge

    if rehome == 'limit' and not session.test:
        mw.mw_bridge_rotary_vane(60.0, mode='Limit')   # true re-home at a switch
        time.sleep(8.0)
        session.invalidate_fine_calibrations('vane re-home')

    lengths, atten_history = [], [_vane_db(mw)]
    for it in range(1, max_iter + 1):
        result, cal_judges = pi_calibration(
            session, preset, mode='length', hold_amplitude=amplitude)
        if result.get('canned'):
            # dry-run: pretend the first measurement already hit the target
            res = {'attenuation_db': atten_history[-1],
                   'pi_length': f'{target_ns} ns', 'target_length': target_length,
                   'iterations': 1, 'canned': True}
            return res, [JudgeReport('pi_length_target', True, target_ns,
                                     {'note': 'dry-run, not judged'})]

        measured = result['pi']
        if measured is None:
            raise RuntimeError('length nutation did not yield a pi length '
                               f'(iteration {it})')
        lengths.append(measured)
        session.log(f'      iteration {it}: pi = {measured} ns '
                    f'@ {atten_history[-1]} dB (target {target_ns} ns)')
        if abs(measured - target_ns) <= tol_ns:
            break
        if it == max_iter:
            # out of iterations: do NOT move the vane past the last
            # measurement — the reported (attenuation, pi_length) pair must
            # describe the state the vane is actually in
            break
        new_db = atten_history[-1] + 20.0 * math.log10(target_ns / measured)
        new_db = _vane_set(session, min(max(new_db, 0.0), 60.0))
        atten_history.append(new_db)
        session.invalidate_fine_calibrations(f'vane -> {new_db} dB')

    final = lengths[-1]
    on_target = abs(final - target_ns) <= tol_ns
    judges = [JudgeReport('pi_length_target', on_target, final,
                          {'target_ns': target_ns, 'tol_ns': tol_ns})]
    if not on_target and len(lengths) >= 2:
        # diagnostic for the failure only: on success the target judge is the
        # gate (a single large-but-correct vane jump is not a defect)
        judges.append(convergence(lengths, tol=tol_ns / target_ns))
    result = {'attenuation_db': atten_history[-1], 'pi_length': f'{final} ns',
              'target_length': target_length, 'iterations': len(lengths)}
    session.state['power_for_length'] = result
    return result, judges
