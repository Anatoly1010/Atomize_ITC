"""AWG preliminary tuning steps and settled bridge control."""
import copy
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

from atomize.epr_auto.errors import PreliminaryAbort
from atomize.epr_auto.engine import executor, snapshot
from atomize.epr_auto.params import PRESET_DIR, parse_time_ns, parse_field_g
from atomize.epr_auto.primitives import tune
from atomize.epr_auto.primitives.field import _detection_if_mhz, _synth_mhz
from atomize.epr_auto.primitives.judges import echo_snr


def _claim(session):
    if not session.test and not session.state.get('_bridge_ready'):
        session.state['_vane_record'] = (_vane_record_age_s(), time.monotonic())
        session.ensure_hardware_locks()
        time.sleep(1.1)
        session.state['_bridge_ready'] = True


def _vane_age_s(session):
    """Age of the vane record as seen before this run's lock rewrote bridge.param."""
    record = session.state.get('_vane_record')
    if record is None:
        return _vane_record_age_s()
    age, seen = record
    return age + time.monotonic() - seen


FULL_TRAVEL_S = 70.596


def _vane_record_age_s():
    """Seconds since bridge.param last changed; a recorded move may still be in flight before FULL_TRAVEL_S."""
    from atomize.control_center import bridge_param
    try:
        return time.time() - Path(bridge_param.path()).stat().st_mtime
    except OSError:
        return 0.0


def _home(session):
    _claim(session)
    mw = session.mw_bridge
    if not session.test:
        try:
            mw.p1.join()
        except (AttributeError, TypeError):
            pass
        origin = mw.prev_dB if session.state.get('_rv_homed') else tune._vane_db(mw)
        if origin != 60:
            wait_s = FULL_TRAVEL_S
        elif session.state.get('_rv_homed'):
            wait_s = 0.0
        else:
            wait_s = max(0.0, FULL_TRAVEL_S - _vane_age_s(session))
        started = time.monotonic()
    mw.mw_bridge_rotary_vane(60.0, mode='Limit')
    if not session.test:
        mw.p1.join()
        time.sleep(max(0, wait_s + 0.2 - (time.monotonic() - started)))
    session.invalidate_fine_calibrations('RV home')
    session.state.setdefault('bridge', {})['attenuation_db'] = 60.0
    session.state['_rv_homed'] = True


def _abort(session, reason):
    session.discard_staged_state()
    session.state.pop('ringing_check', None)
    try:
        _home(session)
    except BaseException as error:
        raise PreliminaryAbort(f'{reason}; return to 60 dB FAILED: {error}') from error
    raise PreliminaryAbort(f'{reason}; RV returned to 60 dB')


def _stale_bridge_lock(session):
    if session.test:
        return False
    from atomize.control_center import bridge_param
    if not os.path.exists(bridge_param.path()):
        return True
    return bridge_param.is_locked() and bridge_param.lock_source() == 'epr_auto'


def _adopt_recorded_vane(session):
    """Trust bridge.param after any recorded move has finished; the driver then moves relative to it."""
    mw = session.mw_bridge
    if not session.test:
        time.sleep(max(0.0, FULL_TRAVEL_S - _vane_age_s(session)))
        mw.prev_dB = mw.curr_dB = tune._vane_db(mw)
    session.state['_rv_homed'] = True


def bridge_set(session, attenuation_db=None, frequency_mhz=None, video1_db=None, video2_db=None):
    """Set external bridge settings and invalidate dependent calibrations."""
    for value, maximum, step in ((video1_db, 30, 2), (video2_db, 31.5, 0.5)):
        if value is not None and (not math.isfinite(value) or not 0 <= value <= maximum
                                  or not math.isclose(value / step, round(value / step))):
            raise ValueError(f'video attenuation must be on the {step:g} dB grid within 0–{maximum:g} dB')
    stale = _stale_bridge_lock(session)
    _claim(session)
    mw = session.mw_bridge
    if frequency_mhz is not None:
        if not mw.synthesizer_min <= frequency_mhz <= mw.synthesizer_max:
            raise ValueError('synthesizer frequency outside device limits')
    if attenuation_db is not None:
        if not session.state.get('_rv_homed'):
            _home(session) if stale else _adopt_recorded_vane(session)
        tune._vane_set(session, attenuation_db)
        session.invalidate_fine_calibrations('RV move')
    if frequency_mhz is not None:
        mw.mw_bridge_synthesizer(int(frequency_mhz))
        if not session.test:
            time.sleep(0.3)
        session._drop(('auto_phase', 'pi_calibration', 'echo_window'), 'frequency move')
    result = dict(session.state.get('bridge', {}))
    if attenuation_db is not None:
        result['attenuation_db'] = float(attenuation_db)
    if frequency_mhz is not None:
        result['frequency_mhz'] = int(frequency_mhz)
    session.state['bridge'] = result
    for key, value, method in (('video1_db', video1_db, 'mw_bridge_att_prm'),
                               ('video2_db', video2_db, 'mw_bridge_att2_prm')):
        if value is not None:
            if not session.test:
                setter = getattr(mw, method)
                setter(value)
                time.sleep(0.1)
                actual = float(setter().split(':')[-1].split()[0])
                if not math.isclose(actual, value, abs_tol=1e-6):
                    raise ValueError(f'{key} readback differs from requested setting')
            result[key] = float(value)
    return result, []


def _video_settings(session):
    """Read both attenuators; test mode uses only simulated session settings."""
    values = {}
    if not session.test:
        _claim(session)
    for key, method, maximum, step in (
            ('video1_db', 'mw_bridge_att_prm', 30, 2),
            ('video2_db', 'mw_bridge_att2_prm', 31.5, 0.5)):
        if session.test:
            value = session.state.get('bridge', {}).get(key, 0.0)
        else:
            value = float(getattr(session.mw_bridge, method)().split(':')[-1].split()[0])
        if (not math.isfinite(value) or not 0 <= value <= maximum
                or not math.isclose(value / step, round(value / step))):
            raise ValueError(f'invalid {key} readback')
        values[key] = value
    session.state.setdefault('bridge', {}).update(values)
    return values


def _raise_video(session, peak_mv, limit_mv=200):
    """Apply the calculated gain reduction, rounding upward on each device grid."""
    if not math.isfinite(peak_mv) or peak_mv <= limit_mv:
        raise ValueError('invalid receiver excess')
    values = _video_settings(session)
    remaining = 20 * math.log10(peak_mv / limit_mv)
    changes = {}
    for key, maximum, step in (('video1_db', 30, 2), ('video2_db', 31.5, 0.5)):
        if remaining <= 0:
            break
        increase = min(maximum - values[key], step * math.ceil(remaining / step))
        if increase:
            changes[key] = values[key] + increase
            remaining -= increase
    if not changes:
        raise ValueError('signal too strong: video attenuation range exhausted')
    bridge_set(session, **changes)
    session.log(f'      receiver {peak_mv:g} mV > {limit_mv:g} mV; video attenuation {changes}')


def _video_policy(session, adjust_video):
    enabled = session.state.get('_adjust_video', True) if adjust_video is None else adjust_video
    session.state['_adjust_video'] = bool(enabled)
    if enabled:
        _video_settings(session)
    return bool(enabled)


def _receiver_guard(wa, limit_mv=200):
    wa.receiver_guard = {'limit_mv': float(limit_mv), 'start_ns': protection_trace_start_ns(wa)}


def _repetition_rate(session, pre, rep_rate, inherit=True):
    rep_rate = tune._resolve_rep_rate(session, rep_rate)
    if rep_rate is None:
        rep_rate = session.state.get('preliminary_echo', {}).get('rep_rate', pre.rep_rate) if inherit else pre.rep_rate
    if not math.isfinite(rep_rate) or not 0.1 <= rep_rate <= 10000:
        raise ValueError('preliminary repetition rate must be within 0.1–10000 Hz')
    pre.rep_rate = float(rep_rate)


def _sine_preset(path):
    pre = copy.deepcopy(path) if isinstance(path, snapshot.Preset) else snapshot.load_preset(path)
    freq = _detection_if_mhz(pre)
    for slot in pre.slots[1:]:
        if slot.active and (slot.typ != 'SINE' or slot.freq != freq):
            raise ValueError('preliminary tuning requires SINE pulses at the DETECTION IF')
    return pre


def protection_end_ns(wa):
    """Replay AWG worker pulse setup in a test driver and inspect prepared TTLs."""
    from atomize.device_modules.Insys_FPGA import Insys_FPGA
    original = sys.argv[:]
    try:
        sys.argv = ['', 'test']
        pb = Insys_FPGA()
    finally:
        sys.argv = original
    pb.awg_time_resolution(f'{wa.awg_grid} ns')
    pb.awg_amplitude('CH0', str(wa.ch0_ampl), 'CH1', str(wa.ch1_ampl))
    det = wa.rect[0]
    pb.pulser_pulse(name='P1', channel=det[0], start=det[1], length=det[2], phase_list=det[3])
    for i, (tp, ap) in enumerate(zip(wa.rect[1:], wa.awg)):
        if float(tp[1].split()[0]) == 0:
            continue
        if ap[0] != 'SINE':
            raise ValueError('protection timing requires AWG SINE pulses')
        pb.awg_pulse(name=f'P{2*i+2}', channel='CH0', func=ap[0],
                     frequency=ap[1], length=ap[3], sigma=ap[4], start=ap[5],
                     amplitude=ap[6], phase_list=ap[7])
        pb.pulser_pulse(name=f'P{2*i+3}', channel='TRIGGER_AWG', start=tp[0], length=tp[1])
    pb.pulser_repetition_rate(f'{wa.rep_rate} Hz')
    rows = pb.preparing_to_bit_pulse_pulser(pb.pulse_array_pulser)
    protect = rows[(rows[:, 0].astype(int) & (1 << pb.channel_dict_pulser['LNA_PROTECT'])) != 0]
    detection = rows[(rows[:, 0].astype(int) & (1 << pb.channel_dict_pulser['DETECTION'])) != 0]
    if len(protect) == 0 or len(detection) != 1:
        raise ValueError('cannot resolve LNA_PROTECT and DETECTION timing')
    return float((protect[:, 2].max() - detection[0, 1]) * pb.timebase_pulser)


def protection_trace_start_ns(wa):
    """Map TTL timing to the early edge of the measured September 11 transient."""
    reference = snapshot.load_preset(PRESET_DIR / 'hahn_echo_4s.phase_awg')
    reference_wa = snapshot.build_worker_args(reference, exp_name='DefenseReference')
    return protection_end_ns(wa) - protection_end_ns(reference_wa) + 147.6


def _trace(session, pre, tag, limit_mv=None):
    wa = snapshot.build_worker_args(copy.deepcopy(pre), exp_name=tag)
    wa.iq_cor = 1
    if limit_mv is not None:
        _receiver_guard(wa, limit_mv)
    executor.acquire_trace(wa, script_test=True)
    if session.test:
        t = np.arange(0, pre.slots[0].length, 0.4 * pre.decimation)
        center = min(300, pre.slots[0].length * 0.6)
        v = 10 * np.exp(-0.5 * ((t - center) / 25)**2)
        return t, v, np.zeros_like(v), None
    session.ensure_hardware_locks()
    t, i, q = executor.acquire_trace(wa, n_sweeps=pre.scans, on_message=session.log)
    t = np.asarray(t) * 1e9
    i, q = np.asarray(i), np.asarray(q)
    if (len(t) < 3 or i.shape != t.shape or q.shape != t.shape
            or not np.isfinite([t, i, q]).all() or np.any(np.diff(t) <= 0)):
        raise ValueError('missing or invalid trace')
    path = session.save_path(tag)
    np.savetxt(path, np.column_stack((t, i, q)), delimiter=',', header='time_ns,I_mV,Q_mV')
    return t, i, q, path


def _receiver_trace(session, pre, tag, limit_mv=200, restart=False):
    """Remeasure unchanged excitation settings after each video correction."""
    if not session.state.get('_adjust_video', False):
        return _trace(session, pre, tag)
    changed = False
    while True:
        try:
            result = _trace(session, pre, tag, limit_mv=limit_mv)
        except executor.ReceiverLevelExceeded as error:
            _raise_video(session, error.peak_mv, limit_mv)
            changed = True
            continue
        if changed and restart:
            raise _VideoChanged
        return result


class _VideoChanged(Exception):
    """Restart a comparison after its receiver gain changed."""


def ringing_peak(time_ns, i_mv, q_mv, protection_ns):
    """Maximum unsmoothed magnitude after protection, rejecting invalid readout."""
    t, i, q = (np.asarray(a, dtype=float) for a in (time_ns, i_mv, q_mv))
    if (t.ndim != 1 or len(t) < 3 or i.shape != t.shape or q.shape != t.shape
            or not np.isfinite([t,i,q]).all() or np.any(np.diff(t) <= 0)):
        raise ValueError('missing or invalid ringing trace')
    mask = t >= protection_ns
    if not np.any(mask):
        raise ValueError('no samples after LNA_PROTECT')
    return float(np.max(np.hypot(i[mask], q[mask])))


def ringing_check(session, if_mhz=50, pulse_length='102.4 ns', field='100 G', done=False):
    """Run one settled RV ladder at a nonresonant field; every failed check hard-aborts the protocol.
    With done=True the operator declares an earlier pass at this IF: the preflight
    still runs and the limits are recorded, but the RV, field and receiver are not touched."""
    if session.state.get('ringing_check'):
        _abort(session, 'ringing_check may run only once per preliminary run')
    try:
        pre = snapshot.load_preset(PRESET_DIR / 'ringing_check.phase_awg')
        freq = if_mhz
        length = snapshot._snap(parse_time_ns(pulse_length), pre.awg_grid)
        pre.slots[0].start = pre.slots[1].start = 0.0
        pre.slots[1].coef = 100
        pre.slots[1].length = length
        pre.slots[0].length = snapshot._snap(max(640, length + 512))
        pre.slots[0].freq = pre.slots[1].freq = int(freq)
        pre.ampl_1 = 260
        pre.ampl_2 = 260
        pre.rep_rate, pre.averages, pre.scans, pre.decimation = 500, 10, 1, 1
        wa = snapshot.build_worker_args(pre, exp_name='RingingCheck')
        active_awg = [a for a in wa.awg if float(a[3].split()[0]) != 0]
        if (wa.rect[0][3] != ['+x', '+x'] or len(active_awg) != 1
                or active_awg[0][0] != 'SINE' or active_awg[0][7] != ['+x', '+x']):
            raise PreliminaryAbort('ringing preset must retain +x,+x on DETECTION and SINE')
        end_ns = protection_trace_start_ns(wa)
        ttl_end_ns = protection_end_ns(wa)
        if not 0 <= end_ns < pre.slots[0].length - 0.4:
            raise ValueError('protection end lies outside the digitizer trace')
        executor.acquire_trace(wa, script_test=True)
    except PreliminaryAbort:
        raise
    except Exception as error:
        raise PreliminaryAbort(f'ringing preflight failed before hardware access: {error}') from error
    history = []
    if done:
        session.log(f'      ringing: declared done by the operator at IF {freq} MHz, {length} ns; no RV moves')
        result = {'pulse_length_ns': length, 'if_mhz': freq, 'min_attenuation_db': 0, 'field_g': None,
                  'protection_end_ns': end_ns, 'protection_ttl_end_ns': ttl_end_ns,
                  'defense_reference_window_ns': [147.6, 155.2], 'measurements': [],
                  'declared': True, 'canned': session.test, 'ampl_1': pre.ampl_1, 'ampl_2': pre.ampl_2}
        session.stage_state('ringing_check', result)
        return result, []
    try:
        _home(session)
        session.state['bridge']['frequency_mhz'] = int(_synth_mhz(session))
        pre.field = parse_field_g(field)
        for db in (60, 40, 20, 10, 5, 0):
            session.log(f'      ringing: RV {db} dB — move, settle, acquire, check')
            bridge_set(session, attenuation_db=db)
            t, i, q, path = _trace(session, pre, f'ringing_{db}dB')
            peak = ringing_peak(t, i, q, end_ns)
            history.append({'attenuation_db': db, 'peak_mv': peak, 'data_file': path})
            if not session.test:
                (session.run_dir / 'ringing_check.json').write_text(json.dumps(
                    {'protection_end_ns': end_ns, 'protection_ttl_end_ns': ttl_end_ns,
                     'defense_reference_window_ns': [147.6, 155.2], 'measurements': history}, indent=2) + '\n')
            if peak > 100:
                raise ValueError(f'ringing {peak:.2f} mV exceeds 100 mV at {db} dB')
    except BaseException as error:
        _abort(session, f'ringing check stopped: {error}')
    result = {'pulse_length_ns': length, 'if_mhz': freq, 'min_attenuation_db': 0, 'field_g': pre.field,
              'protection_end_ns': end_ns, 'protection_ttl_end_ns': ttl_end_ns,
              'defense_reference_window_ns': [147.6, 155.2],
              'measurements': history, 'canned': session.test,
              'ampl_1': pre.ampl_1, 'ampl_2': pre.ampl_2}
    session.stage_state('ringing_check', result)
    return result, []


def resonator(session, if_mhz=50, start_mhz=9200, end_mhz=9600, step_mhz=1,
              pulse_length='102.4 ns', averages=10, scans=1, window='2 ns',
              precision_mhz=5, min_snr=5, competitor_ratio=0.8,
              region=None, clip_mv=None):
    """Acquire the AWG diode scan and select the synthesizer frequency."""
    from atomize.epr_auto.engine.resonator import acquire
    from atomize.epr_auto.primitives.resonator import select_frequency
    previous = None
    try:
        checked = session.state.get('ringing_check')
        if not checked:
            raise PreliminaryAbort('run tune.ringing_check before preliminary acquisition')
        freq = if_mhz
        if freq != checked['if_mhz']:
            raise PreliminaryAbort('resonator IF differs from the ringing-tested IF')
        length = snapshot._snap(parse_time_ns(pulse_length))
        path = None if session.test else session.save_path('resonator')
        args = ('Resonator', length, start_mhz, 500, scans, end_mhz,
                step_mhz, averages, freq)
        acquire(args, test=True, log=session.log)
        bridge_set(session, attenuation_db=10)
        previous = _synth_mhz(session)
        if session.test:
            result = {'accepted': True, 'frequency_mhz': round((start_mhz + end_mhz) / 2),
                      'canned': True}
        else:
            data = acquire(args, path, log=session.log)
            headers = Path(path).read_text().splitlines()[:20]
            from atomize.epr_auto.params import parse_time_ns as time_ns
            dt = time_ns(next(line.split(':', 1)[1].strip() for line in headers
                              if 'Time Resolution:' in line))
            axis = start_mhz + np.arange(data.shape[0]) * step_mhz
            result = select_frequency(np.arange(data.shape[1]) * dt, axis, data.T * 1000,
                                      length, parse_time_ns(window), precision_mhz,
                                      min_snr, competitor_ratio,
                                      None if region is None else [parse_time_ns(x) for x in region],
                                      clip_mv)
            Path(path).with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
            import atomize.general_modules.general_functions as general
            general.plot_1d('Resonator section', axis, np.asarray(result['section_mv']),
                            xname='Synthesizer', xscale='MHz', yname='Diode', yscale='mV')
            if not result['accepted']:
                raise ValueError('; '.join(result['reasons']))
        selected = int(round(result['frequency_mhz']))
        bridge_set(session, frequency_mhz=selected)
        result.update({'synthesizer_mhz': selected, 'if_mhz': freq,
                       'observation_mhz': selected - freq, 'data_file': path})
        session.stage_state('resonator', result)
        return result, []
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        if previous is not None:
            try:
                bridge_set(session, frequency_mhz=previous)
            except BaseException as restore_error:
                error = f'{error}; frequency restore failed: {restore_error}'
        _abort(session, f'resonator scan stopped: {error}')


def _covered(session, pre):
    checked = session.state.get('ringing_check')
    if not checked:
        raise PreliminaryAbort('run tune.ringing_check before preliminary acquisition')
    if (_detection_if_mhz(pre) != checked['if_mhz']
            or pre.ampl_1 > checked['ampl_1'] or pre.ampl_2 > checked['ampl_2']):
        raise PreliminaryAbort('tuning preset exceeds the ringing-tested IF or DAC amplitude')


def _echo_preset(session, path, scans, averages, pulse_length=None):
    """Tuning copy of the echo preset: no increments, and every MW pulse at the target pi
    length (default: the shortest active pulse) so pi differs from pi/2 only in amplitude."""
    pre = _sine_preset(tune.load_tuned_preset(session, path))
    pre.scans, pre.averages = scans, averages
    for s in pre.slots:
        s.st_inc = s.len_inc = s.st_inc2 = 0.0
    if pulse_length is None:
        length = min(s.length for s in pre.slots[1:] if s.active)
    else:
        length = snapshot._snap(parse_time_ns(pulse_length), pre.awg_grid)
    for s in pre.slots[1:]:
        if s.active:
            s.length = length
    if session.state.get('field'):
        pre.field = parse_field_g(session.state['field'])
    wa = snapshot.build_worker_args(copy.deepcopy(pre), exp_name='EchoSearch')
    if len(set(wa.rect[0][3])) < 2:
        raise ValueError('echo tuning requires a cancelling receiver phase cycle')
    _covered(session, pre)
    return pre


def _field_trace(session, pre, field_g, tag):
    pre.field = float(field_g)
    return _trace(session, pre, tag)


def _remember_preset(session, pre):
    selected = copy.deepcopy(pre)
    source = snapshot.load_preset(pre.path)
    for slot, original in zip(selected.slots, source.slots):
        slot.st_inc, slot.len_inc, slot.st_inc2 = original.st_inc, original.len_inc, original.st_inc2
    session.stage_state('_preliminary_preset', selected)


def _window(t, i, q, search_from, min_width, test=False):
    mag = np.hypot(i, q)
    dt = float(np.median(np.diff(t)))
    smoothed = tune._smooth(mag, max(3, round(3 / dt)) | 1)
    center, width, resolved, rejected = tune._find_echo(t, smoothed,
                                                      search_from, min_width)
    judge = echo_snr(i + 1j*q)
    if center is None or not resolved or (not test and not judge.passed):
        raise ValueError(f'no resolved echo: {judge}; rejected {rejected}')
    left, right = max(t[0], center - width), min(t[-1], center + width)
    return {'win_left_ns': float(left), 'win_right_ns': float(right)}


def _score(t, i, q, window=None):
    mask = np.ones(len(t), dtype=bool) if window is None else (
        (t >= window['win_left_ns']) & (t <= window['win_right_ns']))
    if np.count_nonzero(mask) < 3:
        raise ValueError('echo window contains fewer than three samples')
    return float(np.sum(np.hypot(i[mask], q[mask])) * np.median(np.diff(t)))


def _sweep(session, pre, fields, window, tag):
    if fields[0] < 0 or fields[-1] <= fields[0]:
        raise ValueError('field sweep requires increasing nonnegative bounds')
    wa = snapshot.build_worker_args(copy.deepcopy(pre), exp_name=tag,
                                    start_field=float(fields[0]), end_field=float(fields[-1]),
                                    step_field=float((fields[-1]-fields[0])/(len(fields)-1)*(1-1e-9)))
    wa.iq_cor = 0
    if session.state.get('_adjust_video', False):
        _receiver_guard(wa)
    executor.run_worker(wa, 'Field', script_test=True)
    if session.test:
        center = (fields[0]+fields[-1])/2
        scores = np.exp(-((fields-center)/max(1,(fields[-1]-fields[0])/5))**2)
        paths = []
    else:
        path = session.save_path(tag)
        try:
            executor.run_worker(wa, 'Field', save_path=path, on_message=session.log)
        except executor.ReceiverLevelExceeded as error:
            _raise_video(session, error.peak_mv)
            check = copy.deepcopy(pre)
            check.field = float(fields[error.point_index])
            _receiver_trace(session, check, 'field_video_confirm')
            raise _VideoChanged from error
        paths = [path, str(Path(path).with_name(Path(path).stem+'_1.csv'))]
        i, q = (np.loadtxt(name, delimiter=',', ndmin=2) for name in paths)
        if (i.shape != q.shape or i.shape[0] != len(fields)
                or i.shape[1] < 3 or not np.isfinite([i,q]).all()):
            raise ValueError('invalid raw field sweep')
        t = np.arange(i.shape[1]) * 0.4 * pre.decimation
        scores = np.asarray([_score(t, a, b, window) for a,b in zip(i,q)])
    judge = echo_snr(scores)
    if not session.test and not judge.passed:
        raise ValueError(f'no echo in the supplied field range: {judge}')
    best = int(np.argmax(scores))
    return float(fields[best]), {'fields_g': list(map(float, fields)),
                                'scores': scores.tolist(), 'data_files': paths}


def _rv_approach(session, pre, attenuation_db):
    """Monitor the existing live preview while opening RV through the requested ladder."""
    ladder = [db for db in (60, 40, 20, 15, 10, 5, 0) if db > attenuation_db]
    ladder.append(float(attenuation_db))
    approach = []
    if session.test:
        for db in ladder:
            if db != 60:
                bridge_set(session, attenuation_db=db)
            t, i, q, path = _receiver_trace(session, pre, 'rv_approach')
            approach.append({'attenuation_db': db, 'data_file': path,
                             **_video_settings(session)})
        return approach
    from atomize.epr_auto.engine.live_receiver import monitor_trace
    wa = snapshot.build_worker_args(copy.deepcopy(pre), exp_name='RVLiveApproach')
    wa.iq_cor = 1
    executor.acquire_trace(wa, script_test=True)
    start_ns = protection_trace_start_ns(wa)
    index, settled_at, discard_frame = 0, 0.0, False

    def adjust(t, i, q):
        nonlocal index, settled_at, discard_frame
        if discard_frame:
            discard_frame = False
            return False
        t_ns = np.asarray(t) * 1e9
        peak = ringing_peak(t_ns, i, q, start_ns)
        if peak > 200:
            _raise_video(session, peak)
            discard_frame = True
            return False
        if time.monotonic() < settled_at:
            return False
        path = session.save_path('rv_approach')
        np.savetxt(path, np.column_stack((t_ns, i, q)), delimiter=',', header='time_ns,I_mV,Q_mV')
        approach.append({'attenuation_db': ladder[index], 'peak_mv': peak,
                         'data_file': path, **_video_settings(session)})
        if index == len(ladder) - 1:
            return True
        previous, target = ladder[index], ladder[index + 1]
        mw = session.mw_bridge
        travel_s = abs(int(mw.calibration(target)) - int(mw.calibration(previous))) * 0.036
        mw.mw_bridge_rotary_vane(target)
        settled_at = time.monotonic() + travel_s + 0.2
        session.invalidate_fine_calibrations('RV move')
        session.state.setdefault('bridge', {})['attenuation_db'] = target
        index += 1
        return False

    monitor_trace(wa, adjust, on_message=session.log)
    return approach


def find_echo(session, preset, center, span, points=41, attenuation_db=10,
              scans=1, averages=10, search_from='200 ns', min_width='20 ns',
              frequency_shift_mhz=0, pulse_length=None, adjust_video=True, rep_rate=None):
    """Full-window magnitude field search followed by resolved-echo validation."""
    try:
        pre = _echo_preset(session, preset, scans, averages, pulse_length)
        _repetition_rate(session, pre, rep_rate, inherit=False)
        enabled = _video_policy(session, adjust_video)
        lo = parse_field_g(center) - parse_field_g(span) / 2
        hi = parse_field_g(center) + parse_field_g(span) / 2
        if lo < 0:
            raise ValueError('field range crosses zero')
        reference = session.state.get('resonator', {}).get('synthesizer_mhz')
        if reference is None:
            reference = session.state.get('_echo_frequency_reference_mhz')
            if reference is None:
                _claim(session)
                reference = int(_synth_mhz(session))
                session.state['_echo_frequency_reference_mhz'] = reference
        frequency = reference + frequency_shift_mhz
        if attenuation_db < session.state['ringing_check']['min_attenuation_db']:
            raise ValueError('RV setting exceeds the ringing-tested power')
        approach = []
        if enabled:
            _home(session)
            bridge_set(session, frequency_mhz=frequency)
            pre.field, pre.scans = parse_field_g(center), 1
            approach = _rv_approach(session, pre, attenuation_db)
            pre.scans = scans
        else:
            bridge_set(session, attenuation_db=attenuation_db, frequency_mhz=frequency)
        while True:
            try:
                best, sweep = _sweep(session, pre, np.linspace(lo, hi, points), None, 'find_echo')
                pre.field = best
                t, i, q, path = _receiver_trace(session, pre, 'echo_confirm', restart=True)
                break
            except _VideoChanged:
                session.log('      video attenuation changed; repeating field search')
        window = _window(t, i, q, parse_time_ns(search_from), parse_time_ns(min_width), session.test)
        pre.win_left_ns, pre.win_right_ns = window.values()
        session.state['field'] = f'{best} G'
        session.stage_state('echo_window', window)
        _remember_preset(session, pre)
        result = {'field_g': best, 'attenuation_db': attenuation_db, 'window': window,
                  'pulse_length_ns': pre.slots[1].length,
                  'rep_rate': pre.rep_rate, 'adjust_video': enabled, 'rv_approach': approach,
                  'video': _video_settings(session) if enabled else None,
                  'frequency_reference_mhz': reference, 'frequency_shift_mhz': frequency_shift_mhz,
                  'synthesizer_mhz': frequency, 'observation_mhz': frequency - _detection_if_mhz(pre),
                  'sweep': sweep, 'data_file': path, 'canned': session.test}
        session.stage_state('preliminary_echo', result)
        return result, []
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        _abort(session, f'echo search stopped: {error}')


def _echo_roles(pre, pulse_map):
    if pulse_map and pulse_map != 'none':
        roles = {int(name[1:]) - 1: role for name, role in pulse_map.items()}
    else:
        roles = {int(name[1:]) - 1: role for name, role in tune._infer_cal_map(pre).items()}
    active = {i for i, s in enumerate(pre.slots[1:], 1) if s.active}
    if set(roles) != active or sorted(roles.values()) != ['pi', 'pi2']:
        raise ValueError('amplitude scan requires a two-pulse pi2/pi echo map')
    return (next(i for i, r in roles.items() if r == 'pi2'),
            next(i for i, r in roles.items() if r == 'pi'))


def _amplitude_sweep(session, pre, amplitudes, p2, pi, tag):
    """Acquire a stage's paired amplitudes with one FPGA initialization and full traces."""
    candidate = copy.deepcopy(pre)
    amplitudes = np.asarray(amplitudes, dtype=float)
    candidate.slots[p2].coef = float(amplitudes[0])
    candidate.slots[pi].coef = round(2 * float(amplitudes[0]), 1)
    _covered(session, candidate)
    wa = snapshot.build_worker_args(candidate, exp_name=tag, points=len(amplitudes), save2d=1)
    wa.iq_cor = 1
    wa.amplitude_sweep = {
        'axis': amplitudes.tolist(),
        'pulses': {f'P{2*p2}': amplitudes.tolist(),
                   f'P{2*pi}': np.round(2 * amplitudes, 1).tolist()},
    }
    if session.state.get('_adjust_video', False):
        _receiver_guard(wa)
    executor.run_worker(wa, 'Amplitude', script_test=True)
    samples = int(round(parse_time_ns(wa.rect[0][2]) / 0.4) / wa.decimation)
    t = np.arange(samples) * 0.4 * wa.decimation
    if session.test:
        center = min(300, pre.slots[0].length * 0.6)
        i = np.tile(10 * np.exp(-0.5 * ((t - center) / 25)**2), (len(amplitudes), 1))
        return t, i, np.zeros_like(i), []
    session.ensure_hardware_locks()
    path = session.save_path(tag)
    try:
        executor.run_worker(wa, 'Amplitude', save_path=path, on_message=session.log)
    except executor.ReceiverLevelExceeded as error:
        _raise_video(session, error.peak_mv)
        a = float(amplitudes[error.point_index])
        candidate.slots[p2].coef, candidate.slots[pi].coef = a, round(2 * a, 1)
        _receiver_trace(session, candidate, 'amplitude_video_confirm')
        raise _VideoChanged from error
    base = Path(path).with_suffix('')
    paths = [path, f'{base}_2d.csv', f'{base}_2d_1.csv']
    curve, i, q = (np.loadtxt(name, delimiter=',', ndmin=2) for name in paths)
    if (curve.shape != (len(amplitudes), 3) or not np.isfinite(curve).all()
            or not np.allclose(curve[:, 0], amplitudes, rtol=1e-6, atol=1e-6)
            or samples < 3 or i.shape != (len(amplitudes), samples) or q.shape != i.shape
            or not np.isfinite([i, q]).all()):
        raise ValueError('invalid raw amplitude sweep')
    return t, i, q, paths


def maximize_echo(session, preset, attenuation_db=None, amplitude_range=(5, 50),
                  coarse_step=5, fine_step=1, field_span='10 G', points=21,
                  scans=1, averages=10, improvement=0.05, pulse_map=None,
                  search_from='200 ns', min_width='20 ns', pulse_length=None,
                  adjust_video=None, rep_rate=None):
    """Fixed-RV amplitude scan (pi/2 at a, pi at 2a), field refinement and confirmation."""
    try:
        if not session.state.get('preliminary_echo'):
            raise ValueError('run tune.find_echo first')
        if pulse_length is None and session.state['preliminary_echo'].get('pulse_length_ns'):
            pulse_length = f"{session.state['preliminary_echo']['pulse_length_ns']} ns"
        pre = _echo_preset(session, preset, scans, averages, pulse_length)
        _repetition_rate(session, pre, rep_rate)
        enabled = _video_policy(session, adjust_video)
        if attenuation_db is None:
            attenuation_db = session.state['preliminary_echo']['attenuation_db']
        if attenuation_db < session.state['ringing_check']['min_attenuation_db']:
            raise ValueError('RV setting exceeds the ringing-tested power')
        p2, pi = _echo_roles(pre, pulse_map)
        window = dict(session.state['echo_window'])
        low, high = map(float, amplitude_range)
        bridge_set(session, attenuation_db=attenuation_db)
        initial = copy.deepcopy(pre)
        while True:
            pre = copy.deepcopy(initial)
            try:
                trials, scores, measured = [], {}, {}

                def measure_stage(values, tag):
                    values = sorted({round(float(a), 1) for a in values} - scores.keys())
                    if not values:
                        return
                    t, i, q, paths = _amplitude_sweep(session, pre, values, p2, pi, tag)
                    for row, a in enumerate(values):
                        score = measured[a] = _score(t, i[row], q[row], window)
                        if session.test:
                            score *= 1 + np.exp(-((a - (low + high) / 2) / 8) ** 2)
                        scores[a] = score
                        trials.append({'pi2_amplitude': a, 'pi_amplitude': round(2 * a, 1),
                                       'score': score, 'data_file': paths[1] if paths else None,
                                       'data_files': paths[1:], 'data_row': row})

                measure_stage(np.r_[np.arange(low, high, coarse_step), high], 'amplitude_coarse')
                coarse_best = max(scores, key=scores.get)
                fine = np.arange(max(low, coarse_best - coarse_step),
                                 min(high, coarse_best + coarse_step) + fine_step / 2, fine_step)
                measure_stage(fine[fine <= high], 'amplitude_fine')
                best_a = max(scores, key=scores.get)
                if best_a >= high - fine_step / 2:
                    raise ValueError(f'echo still growing at {best_a:g} % (pi at {2 * best_a:g} %): reduce attenuation')
                if best_a <= low + fine_step / 2:
                    raise ValueError(f'echo already falling at {best_a:g} %: increase attenuation')
                best_score = measured[best_a]
                pre.slots[p2].coef, pre.slots[pi].coef = best_a, round(2 * best_a, 1)
                half = parse_field_g(field_span) / 2
                best_field, field_sweep = _sweep(session, pre,
                                                np.linspace(pre.field-half, pre.field+half, points),
                                                window, 'field_optimize')
                pre.field = best_field
                t, i, q, path = _receiver_trace(session, pre, 'optimized_echo_confirm', restart=True)
                confirmed = _window(t, i, q, parse_time_ns(search_from), parse_time_ns(min_width), session.test)
                if _score(t, i, q, confirmed) < best_score / (1 + improvement):
                    raise ValueError('best echo did not reproduce on confirmation')
                break
            except _VideoChanged:
                session.log('      video attenuation changed; repeating amplitude and field optimization')
        pre.win_left_ns, pre.win_right_ns = confirmed.values()
        session.state['field'] = f'{best_field} G'
        _remember_preset(session, pre)
        session.stage_state('echo_window', confirmed)
        result = {'attenuation_db': float(attenuation_db), 'field_g': best_field,
                  'rep_rate': pre.rep_rate, 'adjust_video': enabled,
                  'video': _video_settings(session) if enabled else None,
                  'pi2_amplitude': best_a, 'pi_amplitude': round(2 * best_a, 1),
                  'amplitude_trials': trials, 'field_sweep': field_sweep,
                  'data_file': path, 'canned': session.test}
        session.stage_state('preliminary_optimum', result)
        return result, []
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        _abort(session, f'echo maximization stopped: {error}')


def video_attenuation(session, preset, adjust_video=None, limit_mv=200):
    """Adjust the receiver on the final preset, preserving pulse lengths and field."""
    try:
        enabled = _video_policy(session, adjust_video)
        if not enabled:
            result = {'adjust_video': False, 'skipped': True}
            session.stage_state('video_attenuation', result)
            return result, []
        if not math.isfinite(limit_mv) or not 0 < limit_mv <= 200:
            raise ValueError('video level limit must be within 0–200 mV')
        pre = _sine_preset(tune.load_tuned_preset(session, preset))
        for slot in pre.slots:
            slot.st_inc = slot.len_inc = slot.st_inc2 = 0.0
        wa = snapshot.build_worker_args(copy.deepcopy(pre), exp_name='VideoCheck')
        start_ns = protection_trace_start_ns(wa)
        t, i, q, path = _receiver_trace(session, pre, 'video_check', limit_mv)
        peak = ringing_peak(t, i, q, start_ns)
        if not session.test:
            stop = False
            for key, step in (('video2_db', 0.5), ('video1_db', 2)):
                while not stop:
                    values = _video_settings(session)
                    if values[key] < step or peak * 10**(step / 20) > limit_mv:
                        break
                    requested = values[key] - step
                    bridge_set(session, **{key: requested})
                    t, i, q, path = _receiver_trace(session, pre, 'video_open_check', limit_mv)
                    peak = ringing_peak(t, i, q, start_ns)
                    stop = _video_settings(session) != {**values, key: requested}
        result = {'adjust_video': True, 'limit_mv': limit_mv, 'peak_mv': peak,
                  **_video_settings(session), 'data_file': path, 'canned': session.test}
        session.stage_state('video_attenuation', result)
        return result, []
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        _abort(session, f'video attenuation adjustment stopped: {error}')


def _write_preset(pre, destination):
    lines = Path(pre.path).read_text().splitlines()
    for idx, s in enumerate(pre.slots):
        fields = [s.typ, s.start, s.length, s.sigma, s.freq, s.sweep, s.coef,
                  f'[{s.phase_text}]', s.st_inc, s.len_inc]
        if len(lines[idx].split(':  ')[1].split(',  ')) > 10:
            fields.append(s.st_inc2)
        lines[idx] = f'P{idx+1}:  ' + ',  '.join(map(str, fields))
    for idx, attr in {9:'rep_rate',10:'field',12:'ampl_1',13:'ampl_2',14:'phase_deg',
                      19:'win_left_ns',20:'win_right_ns',
                      21:'averages',23:'zero_order_deg',28:'points',29:'scans',
                      32:'start_field',33:'end_field',34:'step_field',35:'sweep_type'}.items():
        lines[idx] = lines[idx].split(':  ')[0] + ':  ' + str(getattr(pre, attr))
    lines = lines[:39] + [f'Amplitude Step:  {pre.step_ampl}', f'Cycles:  {pre.cycles}',
                         f'Save Each Cycle:  {2 * pre.save_each}', f'AWG grid:  {pre.awg_grid}',
                         f'MW source:  {pre.mw_source}',
                         'SYNT2 pulses:  ' + ','.join(map(str, pre.synt2_rows))]
    if Path(destination).exists():
        staged = Path(destination).with_suffix('.tmp')
        staged.write_text('\n'.join(lines) + '\n')
        os.replace(staged, destination)
        return
    with Path(destination).open('x') as output:
        output.write('\n'.join(lines) + '\n')


def apply_calibration(session, preset, pulse_map=None, destination=None):
    """Write the session's tuning into a preset file so the file alone can drive a later run:
    calibrated amplitudes, zero-order phase, echo window and field."""
    pre = snapshot.load_preset(preset)
    mapping = None if not pulse_map or pulse_map == 'none' else dict(pulse_map)
    patched = tune.apply_calibration(session, pre, mapping)
    if patched is None:
        raise ValueError('no pi_calibration result in the session (run tune.pi_calibration first)')
    if session.state.get('auto_phase'):
        pre.zero_order_deg = session.state['auto_phase']['zero_order_deg']
    if session.state.get('echo_window'):
        pre.win_left_ns = session.state['echo_window']['win_left_ns']
        pre.win_right_ns = session.state['echo_window']['win_right_ns']
    if session.state.get('field'):
        pre.field = parse_field_g(session.state['field'])
    executor.run_worker(snapshot.build_worker_args(copy.deepcopy(pre), exp_name='ApplyCheck'),
                        pre.sweep_type, script_test=True)
    target = Path(destination) if destination else Path(preset)
    result = {'preset': str(preset), 'written': str(target), 'patched': patched,
              'zero_order_deg': pre.zero_order_deg, 'field_g': pre.field,
              'window_ns': [pre.win_left_ns, pre.win_right_ns]}
    if session.test:
        return {**result, 'canned': True}, []
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_preset(pre, target)
    return result, []


def _scale_calibration(cal, pre, length_ns):
    """Fit the amplitude-calibration preset to the tuned echo: the swept (Rabi) pulse becomes a
    SINE of the fine target length, and the detection pair takes the preliminary pulses
    (lower preset amplitude <- smaller tuned area)."""
    tuned = sorted(((s.length * s.coef / 100 * tune._slot_area(s, pre.awg_grid), s)
                    for s in pre.slots[1:] if s.active), key=lambda item: item[0])
    pi_area, pi_slot = tuned[-1]
    swept = tune._swept_slot(cal, 'amplitude')
    sweep_hi = cal.slots[swept].coef + (cal.points - 1) * cal.step_ampl
    cal.slots[swept].typ, cal.slots[swept].sigma, cal.slots[swept].length = 'SINE', 0.0, length_ns
    notes = []
    expected = 100 * pi_area / length_ns
    if expected > sweep_hi:
        notes.append(f'amplitude sweep ends at {sweep_hi:g} % but pi on a {length_ns:g} ns pulse is '
                     f'expected near {expected:.0f} %; the calibration will rail unless power is raised')
    pair = sorted((s for i, s in enumerate(cal.slots) if i > 0 and i != swept and s.active),
                  key=lambda s: s.coef)
    for dst, (_, src) in zip(pair, tuned[-len(pair):]):
        dst.typ, dst.length, dst.sigma, dst.coef = src.typ, src.length, src.sigma, src.coef
    return notes


def _at_length(pre, length_ns):
    """Copy of the tuned echo with every MW pulse at length_ns and linearly rescaled amplitudes
    as placeholders; the fine calibration replaces the amplitudes when the copy is used."""
    out = copy.deepcopy(pre)
    for s in out.slots[1:]:
        if s.active:
            s.coef = min(100.0, round(s.coef * s.length / length_ns, 1))
            s.length = length_ns
    return out


def save_presets(session, preset, calibration_preset, field_preset,
                 field_span=None, field_points=200, calibration_length=None, publish_dir=None):
    """Export new preset copies and a YAML protocol restoring bridge settings."""
    import yaml
    pre = tune.load_tuned_preset(session, preset)
    if not session.state.get('preliminary_optimum'):
        raise PreliminaryAbort('run tune.maximize_echo before saving the handoff')
    tuned_length = max(s.length for s in pre.slots[1:] if s.active)
    cal_length = tuned_length if calibration_length is None else snapshot._snap(
        parse_time_ns(calibration_length), pre.awg_grid)
    echo_cal = _at_length(pre, cal_length)
    field_pre = _sine_preset(field_preset)
    field_pre.awg_grid = pre.awg_grid
    cal = snapshot.load_preset(calibration_preset)
    for note in _scale_calibration(cal, pre, cal_length):
        session.log(f'      calibration preset: {note}')
    freq = int(_detection_if_mhz(pre))
    for target in (field_pre, cal):
        target.field = pre.field
        target.rep_rate = pre.rep_rate
        target.ampl_1, target.ampl_2 = pre.ampl_1, pre.ampl_2
        target.phase_deg = pre.phase_deg
        target.slots[0].freq = freq
        for s in target.slots[1:]:
            if s.active:
                s.freq = freq
    active = [s for s in echo_cal.slots[1:] if s.active]
    target_active = [s for s in field_pre.slots[1:] if s.active]
    if len(active) != len(target_active):
        raise ValueError('field preset must have the same echo-pulse count as the tuned preset')
    for src, dst in zip(active, target_active):
        dst.start, dst.length, dst.coef = src.start, src.length, src.coef
    field_pre.slots[0].start = pre.slots[0].start
    field_pre.slots[0].length = pre.slots[0].length
    if field_span is None:
        searched = session.state['preliminary_echo']['sweep']['fields_g']
        half = (searched[-1] - searched[0]) / 2
    else:
        half = parse_field_g(field_span) / 2
    if pre.field - half < 0:
        raise ValueError('EDFS span extends below zero field')
    field_pre.start_field, field_pre.end_field = pre.field - half, pre.field + half
    field_pre.step_field = 2 * half / (field_points - 1)
    for target in (pre, echo_cal, field_pre):
        target.win_left_ns = session.state['echo_window']['win_left_ns']
        target.win_right_ns = session.state['echo_window']['win_right_ns']
    exports = (pre, cal, field_pre, echo_cal)
    for target in exports:
        wa = snapshot.build_worker_args(copy.deepcopy(target), exp_name='HandoffCheck')
        executor.run_worker(wa, target.sweep_type, script_test=True)
    names = ('echo.phase_awg', 'calibration.phase_awg', 'field.phase_awg', 'echo_cal.phase_awg')
    roles = tune._infer_cal_map(pre)
    steps = [
        {'bridge.set': dict(session.state['bridge'])},
        {'tune.echo_window': {'preset': names[0]}},
        {'tune.auto_phase': {'preset': names[0]}},
        {'tune.pi_calibration': {'preset': names[1], 'mode': 'amplitude'}},
        {'tune.apply_calibration': {'preset': names[2], 'pulse_map': roles}},
        {'tune.apply_calibration': {'preset': names[3], 'pulse_map': roles}},
        {'field.edfs': {'preset': names[2], 'range': [f'{field_pre.start_field} G', f'{field_pre.end_field} G'],
                        'points': int(field_points)}},
        {'tune.echo_window': {'preset': names[3]}},
        {'tune.auto_phase': {'preset': names[3]}},
        {'tune.pi_calibration': {'preset': names[1], 'mode': 'amplitude'}},
        {'tune.apply_calibration': {'preset': names[3], 'pulse_map': roles}},
    ]
    steps.append({'tune.video_attenuation': {
        'preset': names[3], 'adjust_video': session.state.get('_adjust_video', True)}})
    document = {'sample': session.sample, 'autonomy': 'supervised', 'steps': steps}
    from atomize.epr_auto.protocol import load_protocol
    if session.test:
        import tempfile
        with tempfile.TemporaryDirectory() as scratch:
            probe = Path(scratch) / 'fine_tuning.yaml'
            probe.write_text(yaml.safe_dump(document, sort_keys=False))
            for name in names:
                (Path(scratch) / name).write_text(Path(pre.path).read_text())
            load_protocol(probe)
        return {'presets': list(names), 'protocol': document, 'calibration_length_ns': cal_length,
                'canned': True}, []
    archive = session.run_dir / f'handoff_{session._save_counter+1:03d}'
    archive.mkdir()
    publish = Path(publish_dir) if publish_dir else session.run_dir / 'tuned'
    publish.mkdir(parents=True, exist_ok=True)
    document['output'] = str(publish.parent / 'runs' / '{date}_fine')
    for name, target in zip(names, exports):
        for folder in (archive, publish):
            _write_preset(target, folder / name)
        loaded = snapshot.load_preset(publish / name)
        executor.run_worker(snapshot.build_worker_args(loaded, exp_name='SavedCheck'),
                            loaded.sweep_type, script_test=True)
    text = yaml.safe_dump(document, sort_keys=False)
    (archive / 'fine_tuning.yaml').write_text(text)
    path = publish / 'fine_tuning.yaml'
    path.write_text(text)
    load_protocol(path)
    return {'presets': [str(publish / n) for n in names], 'protocol': str(path),
            'archive': str(archive), 'calibration_length_ns': cal_length}, []
