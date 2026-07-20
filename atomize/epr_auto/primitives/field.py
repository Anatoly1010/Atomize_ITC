"""Field primitives: echo-detected field sweep + direct field set.

The EDFS acquisition itself drives the magnet stepwise inside the Worker
(exp_field); the final working point is then set through the session's
BH_15 handle, which keeps field.param's Field value current on every real
move. The session seizes the field.param lock first so the interactive
field-control tool stays off the device (same discipline as the experiment
runner GUIs).
"""
import numpy as np

from atomize.epr_auto.params import parse_field_g
from atomize.epr_auto.primitives.judges import JudgeReport, echo_snr
from atomize.epr_auto.primitives.tune import _acquire, _build


# h/mu_B in Gauss per MHz: B[G] = 0.71447704 * nu[MHz] / g
_G_PER_MHZ = 0.71447704
# an SNR score this far above the pure-noise ceiling (~1) counts as a weak
# line for the failure diagnosis, even though it is below the judge's floor
_WEAK_LINE_SCORE = 1.5


def _diagnose_weak(snr_judge, x, sig):
    """Name what to check on a failed echo-SNR judge (details['diagnosis'])."""
    peak_g = float(x[int(np.argmax(np.abs(sig)))])
    if snr_judge.score >= _WEAK_LINE_SCORE:
        snr_judge.details['diagnosis'] = (
            f'weak line found near {peak_g:.1f} G (score '
            f'{snr_judge.score:.2f}) — increase scans, or narrow the '
            'range around it')
    else:
        snr_judge.details['diagnosis'] = (
            'flat everywhere: no echo anywhere in the range — check the '
            'resonator tuning, temperature, g-factor guess and sample '
            'position')


def _synth_mhz(session):
    ans = str(session.mw_bridge.mw_bridge_synthesizer())
    try:
        return float(ans.replace('Frequency:', '').replace('MHz', '').strip())
    except ValueError:
        raise RuntimeError(f'cannot parse synthesizer answer {ans!r}') from None


def edfs(session, preset, range, points, scans, pick='max', value=None,
         g=2.0023, span='250 G', offset='0 G', target_snr=None,
         _escalated=False):
    """Echo-detected field sweep over range=[start, end] ('<x> G/mT/T'
    strings); pick the working field ('max' = magnitude maximum of the
    sweep, 'value' = the given field) and set the magnet to it.

    range='auto' is the initial signal search: center = h*nu/(g*mu_B) from
    the synthesizer readout + offset (the magnet is not absolutely
    calibrated — pass the setup's known shift; the result's shift_g reports
    the measured line-minus-center distance to feed back in). +/- span
    around that. On a failed echo-SNR judge the span widens x2 and the
    sweep re-runs ONCE; a second failure surfaces with a diagnosis ('flat
    everywhere' vs 'weak line found') naming what to check."""
    center = None
    if range == 'auto':
        nu = _synth_mhz(session)
        half = parse_field_g(span)
        off = parse_field_g(offset)
        center = _G_PER_MHZ * nu / float(g) + off
        lo, hi = center - half, center + half
        session.log(f'      range auto: synthesizer {nu:.0f} MHz, g = {g}'
                    + (f', offset {off:+.1f} G' if off else '')
                    + f' -> center {center:.1f} G, span +/- {half:.0f} G')
        if lo < 0:
            # a span wider than the center (low nu / high g, or the x2
            # escalation) would command a negative start the magnet cannot take
            session.log(f'      span exceeds the center — clamping the sweep '
                        f'start {lo:.1f} -> 0 G')
            lo = 0.0
    else:
        lo, hi = (parse_field_g(v) for v in range)
    step = (hi - lo) / (points - 1)
    # validate the pick BEFORE the (multi-minute) sweep, so --test and the
    # live run both reject a bad configuration up front
    if pick == 'value':
        picked_g = parse_field_g(value)
        if not (lo <= picked_g <= hi):
            raise ValueError(f'pick value {picked_g} G is outside the sweep '
                             f'range ({lo:.1f}..{hi:.1f} G)')
    elif pick != 'max':
        raise ValueError(f"pick {pick!r} is not available headless "
                         "(marker needs the interactive tools)")

    pre, wa = _build(session, preset, exp_name='EDFS',
                     start_field=lo, end_field=hi, step_field=step,
                     scans=scans)
    if target_snr is not None:
        # SNR-driven scan ceiling on the exp_field ScanData channel — the
        # stop metric is the same echo_snr this step's hard judge uses below,
        # so an early stop can never deliver a sweep the judge then rejects
        wa.scan_data_flag = 1
    from atomize.epr_auto.primitives.exp import _snr_policy
    acq = _acquire(session, wa, pre.sweep_type, 'edfs', log=session.log,
                   on_scan_data=_snr_policy(session, target_snr, scans))

    if acq is None:
        field_g = picked_g if pick == 'value' else (lo + hi) / 2
        result = {'field': f'{field_g:.1f} G', 'pick': pick, 'canned': True}
        session.state['field'] = result['field']
        return result, [JudgeReport('echo_snr', True, float('inf'),
                                    {'note': 'dry-run, not judged'})]

    x, i, q, path = acq                      # x in Gauss (worker's axis)
    sig = i + 1j * q
    snr_judge = echo_snr(sig)

    if not snr_judge.passed:
        _diagnose_weak(snr_judge, x, sig)
        # pick='value' names a field independent of the echo, so the sweep's
        # SNR neither helps nor blocks it: no escalation, and the magnet is
        # still parked at the requested field below (the failed judge, with
        # its diagnosis, surfaces through the step's judges as usual)
        if pick != 'value':
            if range == 'auto' and not _escalated:
                wide = f'{2 * parse_field_g(span)} G'
                session.log(f'      no echo above the SNR floor — widening '
                            f'the span to +/- {parse_field_g(wide):.0f} G '
                            'and re-running (one escalation)')
                return edfs(session, preset, 'auto', points, scans, pick,
                            value, g, wide, offset, target_snr,
                            _escalated=True)
            # the search ladder ends at the human: name the precondition to
            # check, and do NOT move the magnet to a noise maximum
            return ({'field': None, 'pick': pick, 'data_file': path},
                    [snr_judge])
        session.log('      echo SNR below the floor — pick: value still '
                    'sets the requested field')

    field_g = picked_g if pick == 'value' else \
        float(x[int(np.argmax(np.abs(sig)))])

    set_result, set_judges = set_field(session, f'{field_g:.2f} G')
    result = {'field': set_result['field'], 'pick': pick, 'data_file': path}
    if center is not None:
        # measured line-minus-predicted-center: the setup's calibration
        # shift, ready to be fed back as the offset parameter
        result['shift_g'] = round(field_g - center, 1)
    return result, [snr_judge] + set_judges


def set_field(session, value):
    """Set the magnet to '<x> G/mT/T'. BH_15 itself writes the new value into
    field.param on every real move; the session lock keeps the interactive
    field tool away while we own the device."""
    field_g = parse_field_g(value)
    if session.test:
        session.state['field'] = f'{field_g:.2f} G'
        return {'field': session.state['field'], 'canned': True}, []

    session.ensure_hardware_locks()
    bh = session.field_controller
    bh.magnet_setup(field_g, 1)              # same pattern as BH_15's own restore
    reached = bh.magnet_field(field_g)
    session.state['field'] = f'{field_g:.2f} G'
    ok = reached is None or abs(float(reached) - field_g) <= 0.1
    judge = JudgeReport('field_set', ok,
                        float(reached) if reached is not None else field_g,
                        {'requested_g': field_g})
    return {'field': session.state['field']}, [judge]
