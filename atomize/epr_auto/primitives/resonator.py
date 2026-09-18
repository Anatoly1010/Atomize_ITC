"""Frequency selection from a diode time/frequency map, independent of hardware."""
import numpy as np
from scipy.signal import find_peaks


def select_frequency(time_ns, frequency_mhz, voltage_mv, pulse_ns=102.4,
                     window_ns=2.0, precision_mhz=5.0, min_snr=5.0,
                     competitor_ratio=0.8, region_ns=None, clip_mv=None):
    """Return diagnostics and a center from a common early-ringing window.

    Input is [time, frequency]. Failed quality checks retain the selected
    sections for review but never produce an accepted hardware setting.
    """
    t, f, v = (np.asarray(a, dtype=float) for a in
               (time_ns, frequency_mhz, voltage_mv))
    if (t.ndim != 1 or f.ndim != 1 or len(t) < 20 or len(f) < 7
            or v.shape != (len(t), len(f)) or not np.isfinite(v).all()
            or not np.isfinite(t).all() or not np.isfinite(f).all()
            or np.any(np.diff(t) <= 0) or np.any(np.diff(f) <= 0)):
        raise ValueError('resonator requires finite ordered axes and a [time, frequency] map')
    dt, df = float(np.median(np.diff(t))), float(np.median(np.diff(f)))
    if not np.allclose(np.diff(t), dt) or not np.allclose(np.diff(f), df):
        raise ValueError('resonator axes must be uniformly sampled')
    if window_ns <= 0 or pulse_ns <= 0 or precision_mhz <= 0:
        raise ValueError('pulse, window and precision must be positive')
    initial = np.median(v[:max(3, len(t) // 10)], axis=0)
    envelope = np.median(np.abs(v - initial), axis=1)
    baseline_samples = max(3, len(t) // 10)
    baseline_noise = 1.4826 * np.median(np.abs(v[:baseline_samples] - initial))
    level = np.median(envelope[:baseline_samples]) + 6 * max(float(baseline_noise), 1e-9)
    sustained = max(3, round(1.0 / dt))
    above = envelope > level
    starts = np.flatnonzero(np.convolve(above.astype(int),
                                       np.ones(sustained, dtype=int), mode='valid') == sustained)
    if len(starts) == 0:
        raise ValueError('no sustained pulse onset above baseline noise')
    onset = int(starts[0])
    if onset < 4:
        raise ValueError('no pre-pulse baseline; specify a trace containing the pulse onset')
    baseline_end = max(3, onset - max(2, round(5 / dt)))
    residual = v - np.median(v[:baseline_end], axis=0)
    noise = max(float(1.4826 * np.median(np.abs(
        residual[:baseline_end] - np.median(residual[:baseline_end], axis=0)))), 1e-9)
    search_from = None
    if region_ns is None:
        end = t[onset] + pulse_ns
        region_ns = (end - max(10.0, pulse_ns * 0.12), end + max(10.0, pulse_ns * 0.12))
        search_from = end
    lo, hi = map(float, region_ns)
    candidates = np.flatnonzero((t >= lo) & (t <= hi))
    if len(candidates) < 3:
        raise ValueError('trailing-edge region lies outside the recorded trace')
    # The reflected-pulse plateau can exceed the ringing, so search only after the nominal end.
    searched = candidates if search_from is None else candidates[t[candidates] >= search_from]
    if len(searched) == 0:
        raise ValueError('trailing-edge region lies outside the recorded trace')
    local = residual[searched]
    flat_peak = np.unravel_index(np.argmax(np.abs(local)), local.shape)
    peak_time = int(searched[flat_peak[0]])
    polarity = 1 if local[flat_peak] >= 0 else -1
    width = max(1, round(window_ns / dt))
    smooth_n = max(1, round(precision_mhz / df))
    smooth_n = min(smooth_n | 1, (len(f) // 3) | 1)

    def section(center):
        left = center - width // 2
        right = left + width
        if left < candidates[0] or right > candidates[-1] + 1:
            raise ValueError('ringing window touches the search boundary; adjust the time region')
        raw = polarity * residual[left:right].mean(axis=0)
        smooth = np.convolve(np.pad(raw, smooth_n // 2, mode='edge'),
                             np.ones(smooth_n) / smooth_n, mode='valid')
        return left, right, raw, smooth

    left, right, raw, smooth = section(peak_time)
    best = int(np.argmax(smooth))
    floor = float(np.median(np.r_[smooth[:3], smooth[-3:]]))
    height = float(smooth[best] - floor)
    snr = height / noise
    shift = max(1, round(1.0 / dt))
    nearby = []
    for center in (peak_time, peak_time + shift, peak_time + 2*shift):
        _, _, _, s = section(center)
        nearby.append(float(f[np.argmax(s)]))
    peaks, _ = find_peaks(smooth, prominence=max(noise * min_snr, height * 0.1))
    rivals = [int(k) for k in peaks if abs(f[k] - f[best]) > precision_mhz]
    reasons = []
    if best <= smooth_n // 2 or best >= len(f) - 1 - smooth_n // 2:
        reasons.append('peak at frequency boundary')
    if snr < min_snr:
        reasons.append('weak ringing peak')
    if any(smooth[k] - floor >= competitor_ratio * height for k in rivals):
        reasons.append('competing frequency peaks')
    if max(nearby) - min(nearby) > precision_mhz:
        reasons.append('center changes across nearby early windows')
    raw_peak = polarity * residual[peak_time]
    if clip_mv is not None and np.max(np.abs(v)) >= clip_mv:
        reasons.append('scope clipping limit reached')
    if np.count_nonzero(np.isclose(raw_peak, raw_peak.max(), rtol=0, atol=1e-12)) >= 4:
        reasons.append('flat peak consistent with clipping')
    return {
        'accepted': not reasons, 'reasons': reasons,
        'frequency_mhz': float(f[best]),
        'reported_frequency_mhz': float(precision_mhz * round(f[best] / precision_mhz)),
        'precision_mhz': precision_mhz, 'nearby_centers_mhz': nearby,
        'window_ns': [float(t[left]), float(t[right - 1] + dt)],
        'peak_time_ns': float(t[peak_time]), 'polarity': polarity,
        'snr': float(snr), 'noise_mv': noise,
        'section_mv': raw.tolist(), 'smoothed_section_mv': smooth.tolist(),
        'frequency_axis_mhz': f.tolist(),
    }
