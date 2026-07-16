"""Quality judges: numeric verdicts attached to every primitive's result.

Each judge returns a JudgeReport (pass/fail + score + details). Judges never
raise on bad data quality — a failed judge IS the answer; the step layer (or
the operator, per autonomy policy) decides whether that aborts the protocol.
Numpy-only on purpose: no scipy dependency in the decision layer.
"""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class JudgeReport:
    name: str
    passed: bool
    score: float                 # scalar figure of merit (higher = better)
    details: dict = field(default_factory=dict)

    def __str__(self):
        det = ', '.join(f'{k}={v:.4g}' if isinstance(v, float) else f'{k}={v}'
                        for k, v in self.details.items())
        return f'[{"PASS" if self.passed else "FAIL"}] {self.name}: ' \
               f'score={self.score:.4g}' + (f' ({det})' if det else '')

    def as_dict(self):
        return {'name': self.name, 'passed': self.passed,
                'score': self.score, **self.details}


def echo_snr(y, min_snr=3.0):
    """SNR of a 1-D echo/sweep trace, robust to the smooth signal underneath:
    noise sigma from the median absolute point-to-point difference
    (MAD-of-diff), score = peak deviation from the median baseline in units
    of the tallest excursion noise ALONE would produce on a trace this long
    (sigma * sqrt(2 ln N), extreme-value scaling). Pure noise scores ~1;
    min_snr=3 means the signal peak stands 3x above that ceiling. Works on
    real or complex input."""
    y = np.asarray(y).ravel()
    if np.iscomplexobj(y):
        y = y - (np.median(y.real) + 1j * np.median(y.imag))
        dev = np.abs(y)
    else:
        dev = np.abs(y - np.median(y))
    peak = float(np.max(dev))
    sigma = float(np.median(np.abs(np.diff(y))) / (np.sqrt(2) * 0.6745))
    if sigma == 0:            # canned/test data — report as passing but mark it
        return JudgeReport('echo_snr', True, float('inf'),
                           {'noise': 0.0, 'note': 'zero noise (test data?)'})
    ceiling = sigma * np.sqrt(2 * np.log(max(len(y), 2)))
    snr = peak / ceiling
    return JudgeReport('echo_snr', snr >= min_snr, snr,
                       {'min_snr': min_snr, 'noise_sigma': sigma})


def phase_coherence(sig, min_r=0.7):
    """Resultant length R = |sum sig| / sum|sig| of a complex trace: 1.0 when
    every point shares one phase, ~1/sqrt(N) for pure noise. This is the
    right 'is the echo there, with a well-defined phase' gate for the SHORT
    traces auto_phase acquires — echo_snr's MAD-of-diff sigma has too few
    point-to-point differences to work with there. Unipolar traces only
    (sign flips cancel in the resultant)."""
    sig = np.asarray(sig).ravel()
    denom = float(np.sum(np.abs(sig)))
    if denom == 0:
        return JudgeReport('phase_coherence', False, 0.0,
                           {'note': 'zero signal — no echo acquired'})
    r = float(np.abs(np.sum(sig)) / denom)
    return JudgeReport('phase_coherence', r >= min_r, r,
                       {'min_r': min_r, 'n': int(sig.size)})


def fit_quality(y, y_fit, n_params, min_adj_r2=0.9):
    """RMSE + adjusted R² of a fit (same stats the Data Treatment tool
    reports); pass when adj-R² clears ``min_adj_r2``."""
    y = np.asarray(y, float).ravel()
    y_fit = np.asarray(y_fit, float).ravel()
    resid = y - y_fit
    n = len(y)
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    if ss_tot == 0:
        return JudgeReport('fit_quality', False, 0.0,
                           {'rmse': rmse, 'note': 'flat data, R2 undefined'})
    r2 = 1 - ss_res / ss_tot
    dof = n - n_params - 1
    adj_r2 = 1 - (1 - r2) * (n - 1) / dof if dof > 0 else r2
    return JudgeReport('fit_quality', adj_r2 >= min_adj_r2, float(adj_r2),
                       {'rmse': rmse, 'r2': float(r2), 'min_adj_r2': min_adj_r2})


def convergence(values, tol=0.02):
    """Relative change between the last two iterates of a calibration loop;
    pass when it is within ``tol``. ``values`` needs >= 2 entries."""
    values = [float(v) for v in values]
    if len(values) < 2:
        return JudgeReport('convergence', False, float('inf'),
                           {'note': 'needs at least two iterations'})
    prev, last = values[-2], values[-1]
    denom = max(abs(prev), abs(last), 1e-12)
    rel = abs(last - prev) / denom
    return JudgeReport('convergence', rel <= tol, float(rel),
                       {'tol': tol, 'prev': prev, 'last': last})


def pi_ratio_linearity(amp_pi, amp_pi2, max_deviation=0.3):
    """Amplifier-linearity diagnostic from the fine amplitude calibration:
    amp(pi)/amp(pi/2) should be ~2 for a linear chain; a large deviation
    flags compression (suggest more rotary-vane attenuation). See
    ARCHITECTURE.md 'Flip-angle knobs'."""
    ratio = float(amp_pi) / float(amp_pi2)
    dev = abs(ratio - 2.0)
    report = JudgeReport('pi_ratio_linearity', dev <= max_deviation, ratio,
                         {'deviation': dev, 'max_deviation': max_deviation})
    if not report.passed:
        report.details['hint'] = 'compression suspected: add vane attenuation ' \
                                 'and re-run tune.power_for_length'
    return report


def amplitude_rails(amp_pi, low=30.0, high=99.0):
    """Rail check for the fine amplitude sweep (units: % of AWG full scale):
    pi above ``high`` means the sweep cannot reach pi (underpowered), pi
    below ``low`` wastes DAC dynamic range (overpowered). Either failure is
    the runner's trigger to fall back to tune.power_for_length."""
    amp_pi = float(amp_pi)
    if amp_pi >= high:
        return JudgeReport('amplitude_rails', False, amp_pi,
                           {'rail': 'high', 'high': high,
                            'hint': 'cannot reach pi: reduce vane attenuation'})
    if amp_pi <= low:
        return JudgeReport('amplitude_rails', False, amp_pi,
                           {'rail': 'low', 'low': low,
                            'hint': 'pi too low on the DAC scale: add vane attenuation'})
    return JudgeReport('amplitude_rails', True, amp_pi, {'low': low, 'high': high})
