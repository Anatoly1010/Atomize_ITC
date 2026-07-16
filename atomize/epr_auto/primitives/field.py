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


def edfs(session, preset, range, points, scans, pick='max', value=None):
    """Echo-detected field sweep over range=[start, end] ('<x> G/mT/T'
    strings); pick the working field ('max' = magnitude maximum of the
    sweep, 'value' = the given field) and set the magnet to it."""
    lo, hi = (parse_field_g(v) for v in range)
    step = (hi - lo) / (points - 1)
    # validate the pick BEFORE the (multi-minute) sweep, so --test and the
    # live run both reject a bad configuration up front
    if pick == 'value':
        picked_g = parse_field_g(value)
        if not (lo <= picked_g <= hi):
            raise ValueError(f'pick value {picked_g} G is outside the sweep '
                             f'range ({lo}..{hi} G)')
    elif pick != 'max':
        raise ValueError(f"pick {pick!r} is not available headless "
                         "(marker needs the interactive tools)")

    pre, wa = _build(session, preset, exp_name='EDFS',
                     start_field=lo, end_field=hi, step_field=step,
                     scans=scans)
    acq = _acquire(session, wa, pre.sweep_type, 'edfs', log=session.log)

    if acq is None:
        field_g = picked_g if pick == 'value' else (lo + hi) / 2
        result = {'field': f'{field_g:.1f} G', 'pick': pick, 'canned': True}
        session.state['field'] = result['field']
        return result, [JudgeReport('echo_snr', True, float('inf'),
                                    {'note': 'dry-run, not judged'})]

    x, i, q, path = acq                      # x in Gauss (worker's axis)
    sig = i + 1j * q
    field_g = picked_g if pick == 'value' else \
        float(x[int(np.argmax(np.abs(sig)))])

    set_result, set_judges = set_field(session, f'{field_g:.2f} G')
    result = {'field': set_result['field'], 'pick': pick, 'data_file': path}
    return result, [echo_snr(sig)] + set_judges


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
