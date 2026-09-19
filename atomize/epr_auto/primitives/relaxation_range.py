"""Measured-tail decisions for temperature-series ranges and one repair pass."""
import numpy as np
from scipy.stats import t as student_t


def plateau(x, y, kind):
    """Locate a sustained 1% plateau independently of the relaxation fit.

    The reference tail must be precise and stable between thirds. Earlier
    block means must remain within tolerance including their noise margin;
    at least one qualifying block must precede the reference tail.
    This is an operational test, not a simultaneous confidence guarantee.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    result = {'status': 'unusable', 'tolerance_fraction': 0.01}
    if (x.ndim != 1 or y.shape != x.shape or len(x) < 60
            or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y))
            or np.any(np.diff(x) <= 0)):
        return {**result, 'reason': 'need at least 60 finite, increasing-axis points'}
    nref = min(100, len(y) // 5) if kind == 't2' else 30
    block = max(5, len(y) // 20) if kind == 't2' else 10
    reference = y[-nref:]
    level = float(reference.mean())
    contrast = float(abs(np.median(y[:5]) - level))
    sigma = float(reference.std(ddof=1))
    differences = np.diff(reference)
    noise = float(1.4826 * np.median(abs(differences - np.median(differences))) / np.sqrt(2))
    result.update(reference_points=nref, baseline=level, contrast=contrast,
                  noise_sigma=noise, reference_sigma=sigma, block_points=block)
    if contrast <= 0 or contrast < 10 * noise:
        return {**result, 'reason': 'insufficient measured relaxation contrast'}
    tolerance = 0.01 * contrast
    margin = float(student_t.ppf(0.975, nref - 1)) * sigma
    first, _, last = np.array_split(reference, 3)
    drift = abs(first.mean() - last.mean())
    drift_margin = margin * np.sqrt(1 / len(first) + 1 / len(last))
    result.update(status='unconfirmed', reference_drift_fraction=float(drift / contrast),
                  range_insufficient=False)
    if drift + drift_margin > tolerance:
        unfinished = drift > max(drift_margin, tolerance / 2)
        return {**result, 'range_insufficient': bool(unfinished),
                'reason': 'late reference is still drifting' if unfinished
                else 'late reference is too imprecise to confirm the plateau'}
    blocks = []
    for start in range(0, len(y) - nref, block):
        values = y[start:min(start + block, len(y) - nref)]
        if len(values) < max(5, block // 2):
            continue
        deviation = abs(values.mean() - level)
        error = margin * np.sqrt(1 / len(values) + 1 / nref)
        blocks.append((start, bool(deviation + error <= tolerance),
                       bool(deviation > error + tolerance / 2)))
    candidates = [i for i in range(len(blocks))
                  if all(good for _, good, _ in blocks[i:])]
    if not candidates:
        return {**result, 'range_insufficient': bool(blocks and blocks[-1][2]),
                'reason': 'no sustained plateau before the reference tail'}
    onset = blocks[candidates[0]][0]
    return {**result, 'status': 'confirmed', 'reason': 'measured plateau confirmed',
            'onset_index': onset, 'onset_s': float(x[onset]),
            'baseline_points': len(x) - onset,
            'baseline_fraction': (len(x) - onset) / len(x)}


def decision(analysis, kind, points):
    """Accept a confirmed plateau; resize the next pass and repair only truncation."""
    if analysis['status'] == 'unusable':
        return {'action': 'skip', 'reason': analysis['reason']}
    if analysis['status'] != 'confirmed':
        if analysis.get('range_insufficient'):
            return {'action': 'extend', 'reason': analysis['reason'], 'span_factor': 2.0}
        return {'action': 'skip', 'reason': analysis['reason']}
    count = analysis['baseline_points']
    accepted = (0.5 <= count / points <= 0.6 if kind == 't2'
                else 45 <= count <= 50)
    if accepted:
        return {'action': 'keep', 'next_action': 'keep',
                'reason': 'plateau confirmed; range already meets the planning target'}
    onset = analysis['onset_index']
    target = int(np.ceil(onset / 0.45)) if kind == 't2' else onset + 47
    if target < 60:
        return {'action': 'keep', 'next_action': 'keep',
                'reason': 'plateau confirmed; too few resolved points to shorten safely'}
    return {'action': 'keep', 'next_action': 'resize',
            'reason': 'plateau confirmed; adjust baseline coverage on the next acquisition',
            'target_points': target}
