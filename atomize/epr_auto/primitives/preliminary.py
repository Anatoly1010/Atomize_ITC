"""AWG preliminary tuning steps and settled bridge control."""
import copy
import json
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
        session.ensure_hardware_locks()
        time.sleep(1.1)
        session.state['_bridge_ready'] = True


def _home(session):
    _claim(session)
    mw = session.mw_bridge
    if not session.test:
        pending = getattr(mw, 'p1', None)
        if pending is not None:
            pending.join()
        origin = mw.prev_dB if session.state.get('_rv_homed') else 0.0
        wait_s = abs(36 * (int(mw.calibration(60)) - int(mw.calibration(origin)))) / 1000
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


def bridge_set(session, attenuation_db=None, frequency_mhz=None):
    """Set external bridge settings and invalidate dependent calibrations."""
    _claim(session)
    mw = session.mw_bridge
    if frequency_mhz is not None:
        if not mw.synthesizer_min <= frequency_mhz <= mw.synthesizer_max:
            raise ValueError('synthesizer frequency outside device limits')
    if attenuation_db is not None:
        if not session.state.get('_rv_homed'):
            _home(session)
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
    return result, []


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


def _trace(session, pre, tag):
    wa = snapshot.build_worker_args(copy.deepcopy(pre), exp_name=tag)
    wa.iq_cor = 1
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


def ringing_check(session, if_mhz=50, max_length='102.4 ns'):
    """Run one settled RV ladder; every failed check hard-aborts the protocol."""
    if session.state.get('ringing_check'):
        _abort(session, 'ringing_check may run only once per preliminary run')
    try:
        pre = snapshot.load_preset(PRESET_DIR / 'ringing_check.phase_awg')
        freq = if_mhz
        length = snapshot._snap(parse_time_ns(max_length), pre.awg_grid)
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
    try:
        _home(session)
        session.state['bridge']['frequency_mhz'] = int(_synth_mhz(session))
        if not session.test:
            from atomize.control_center import field_param
            if not Path(field_param.path()).is_file():
                raise ValueError('current field is unavailable in field.param')
            pre.field = float(field_param.read()['Field'])
            if not np.isfinite(pre.field):
                raise ValueError('current field in field.param is invalid')
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
    result = {'max_length_ns': length, 'if_mhz': freq, 'min_attenuation_db': 0,
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
        if length > checked['max_length_ns']:
            raise PreliminaryAbort('resonator pulse exceeds the ringing-tested length')
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
            or max(snapshot._snap(s.length, pre.awg_grid) for s in pre.slots[1:] if s.active) > checked['max_length_ns']
            or pre.ampl_1 > checked['ampl_1'] or pre.ampl_2 > checked['ampl_2']):
        raise PreliminaryAbort('tuning preset exceeds the ringing-tested IF, length or DAC amplitude')


def _echo_preset(session, path, scans, averages):
    pre = _sine_preset(tune.load_tuned_preset(session, path))
    pre.scans, pre.averages = scans, averages
    for s in pre.slots:
        s.st_inc = s.len_inc = s.st_inc2 = 0.0
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
    executor.run_worker(wa, 'Field', script_test=True)
    if session.test:
        center = (fields[0]+fields[-1])/2
        scores = np.exp(-((fields-center)/max(1,(fields[-1]-fields[0])/5))**2)
        paths = []
    else:
        path = session.save_path(tag)
        executor.run_worker(wa, 'Field', save_path=path, on_message=session.log)
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


def find_echo(session, preset, center, span, points=41, attenuation_db=10,
              scans=1, averages=10, search_from='200 ns', min_width='20 ns',
              frequency_shift_mhz=0):
    """Full-window magnitude field search followed by resolved-echo validation."""
    try:
        pre = _echo_preset(session, preset, scans, averages)
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
        bridge_set(session, attenuation_db=attenuation_db, frequency_mhz=frequency)
        best, sweep = _sweep(session, pre, np.linspace(lo, hi, points), None, 'find_echo')
        t, i, q, path = _field_trace(session, pre, best, 'echo_confirm')
        window = _window(t, i, q, parse_time_ns(search_from), parse_time_ns(min_width), session.test)
        pre.win_left_ns, pre.win_right_ns = window.values()
        session.state['field'] = f'{best} G'
        session.stage_state('echo_window', window)
        _remember_preset(session, pre)
        result = {'field_g': best, 'attenuation_db': attenuation_db, 'window': window,
                  'frequency_reference_mhz': reference, 'frequency_shift_mhz': frequency_shift_mhz,
                  'synthesizer_mhz': frequency, 'observation_mhz': frequency - _detection_if_mhz(pre),
                  'sweep': sweep, 'data_file': path, 'canned': session.test}
        session.stage_state('preliminary_echo', result)
        return result, []
    except BaseException as error:
        _abort(session, f'echo search stopped: {error}')


def maximize_echo(session, preset, rv_range, field_span='10 G', points=21,
                  coarse_step_db=2, scans=1, averages=10, improvement=0.05,
                  length_range=None, length_points=5, pulse_map=None,
                  search_from='200 ns', min_width='20 ns'):
    """Finite RV, field and optional mapped pulse-length optimization."""
    try:
        pre = _echo_preset(session, preset, scans, averages)
        if not session.state.get('preliminary_echo'):
            raise ValueError('run tune.find_echo first')
        low, high = rv_range
        if low < session.state['ringing_check']['min_attenuation_db']:
            raise ValueError('RV search exceeds the ringing-tested power')
        window = dict(session.state['echo_window'])
        trials = []
        scores = {}

        def measure(db):
            db = round(float(db) * 2) / 2
            if db in scores:
                return scores[db]
            bridge_set(session, attenuation_db=db)
            t, i, q, path = _trace(session, pre, 'rv_optimize')
            score = _score(t, i, q, window)
            if session.test:
                score *= 1 + np.exp(-((db - (low + high) / 2) / 3)**2)
            scores[db] = score
            trials.append({'attenuation_db': db, 'score': score, 'data_file': path})
            return score

        grid = np.unique(np.r_[np.arange(high, low, -coarse_step_db), low])
        for db in grid[::-1]:
            measure(db)
        coarse_best = max(scores, key=scores.get)
        fine = np.arange(max(low, coarse_best-coarse_step_db),
                         min(high, coarse_best+coarse_step_db)+0.25, 0.5)
        for db in fine[::-1]:
            measure(db)
        peak = max(scores.values())
        best_db = max(db for db, score in scores.items() if score >= peak / (1 + improvement))
        bridge_set(session, attenuation_db=best_db)
        half = parse_field_g(field_span) / 2
        best_field, field_sweep = _sweep(session, pre,
                                        np.linspace(pre.field-half, pre.field+half, points),
                                        window, 'field_optimize')
        pre.field = best_field
        t, i, q, path = _trace(session, pre, 'before_length')
        best_score = _score(t, i, q, window)
        length_trials = []
        power_limited = (best_db == low and len(scores) > 1
                         and scores[low] > scores[sorted(scores)[1]] * (1 + improvement))
        if length_range is not None and power_limited:
            if not pulse_map or pulse_map == 'none':
                raise ValueError('length search requires pulse_map with explicit pi/pi2 roles')
            lo, hi = map(parse_time_ns, length_range)
            indices = {int(name[1:])-1: role for name, role in pulse_map.items()}
            active = {i for i, s in enumerate(pre.slots[1:], 1) if s.active}
            if set(indices) != active or len(active) != 2 or set(indices.values()) != {'pi', 'pi2'}:
                raise ValueError('length search requires an explicit two-pulse pi2/pi echo map')
            p2 = next(i for i, role in indices.items() if role == 'pi2')
            pi = next(i for i, role in indices.items() if role == 'pi')
            original = copy.deepcopy(pre)
            base_length = original.slots[p2].length
            if lo < base_length:
                raise ValueError('insufficient-power search may only lengthen the pulses')
            for length in np.unique([snapshot._snap(x, pre.awg_grid)
                                     for x in np.linspace(lo, hi, length_points)]):
                candidate = copy.deepcopy(original)
                factor = length / base_length
                for idx in active:
                    candidate.slots[idx].length = snapshot._snap(original.slots[idx].length * factor,
                                                                 pre.awg_grid)
                shift2 = (original.slots[p2].length-candidate.slots[p2].length) / 2
                shiftpi = (original.slots[pi].length-candidate.slots[pi].length) / 2
                for idx, shift in ((p2, shift2), (pi, shiftpi)):
                    candidate.slots[idx].start = snapshot._snap(original.slots[idx].start+shift,
                                                                pre.awg_grid)
                offset = max(0, -min(candidate.slots[idx].start for idx in active))
                for s in candidate.slots:
                    if s.active:
                        s.start += offset
                _covered(session, candidate)
                protection_end_ns(snapshot.build_worker_args(copy.deepcopy(candidate), exp_name='LengthCheck'))
                t, i, q, path = _trace(session, candidate, 'length_optimize')
                candidate_window = _window(t, i, q, parse_time_ns(search_from),
                                           parse_time_ns(min_width), session.test)
                score = _score(t, i, q, candidate_window)
                length_trials.append({'pi2_length_ns': float(length), 'score': score, 'data_file': path})
                if score > best_score * (1 + improvement):
                    pre, window, best_score = candidate, candidate_window, score
        bridge_set(session, attenuation_db=best_db)
        pre.field = best_field
        t, i, q, path = _trace(session, pre, 'optimized_echo_confirm')
        confirmed = _window(t, i, q, parse_time_ns(search_from), parse_time_ns(min_width), session.test)
        if _score(t, i, q, confirmed) < best_score / (1 + improvement):
            raise ValueError('best echo did not reproduce on confirmation')
        pre.win_left_ns, pre.win_right_ns = confirmed.values()
        session.state['field'] = f'{best_field} G'
        _remember_preset(session, pre)
        session.stage_state('echo_window', confirmed)
        result = {'attenuation_db': best_db, 'field_g': best_field, 'rv_trials': trials,
                  'field_sweep': field_sweep, 'length_trials': length_trials,
                  'power_limited': power_limited, 'data_file': path, 'canned': session.test}
        session.stage_state('preliminary_optimum', result)
        return result, []
    except BaseException as error:
        _abort(session, f'echo maximization stopped: {error}')


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
                         f'Save Each Cycle:  {2 * pre.save_each}', f'AWG grid:  {pre.awg_grid}']
    with Path(destination).open('x') as output:
        output.write('\n'.join(lines) + '\n')


def save_presets(session, preset, calibration_preset, field_preset):
    """Export new preset copies and a YAML protocol restoring bridge settings."""
    import yaml
    pre = tune.load_tuned_preset(session, preset)
    if not session.state.get('preliminary_optimum'):
        raise PreliminaryAbort('run tune.maximize_echo before saving the handoff')
    field_pre = _sine_preset(field_preset)
    field_pre.awg_grid = pre.awg_grid
    cal = snapshot.load_preset(calibration_preset)
    freq = int(_detection_if_mhz(pre))
    for target in (field_pre, cal):
        target.field = pre.field
        target.ampl_1, target.ampl_2 = pre.ampl_1, pre.ampl_2
        target.phase_deg = pre.phase_deg
        target.slots[0].freq = freq
        for s in target.slots[1:]:
            if s.active:
                s.freq = freq
    active = [s for s in pre.slots[1:] if s.active]
    target_active = [s for s in field_pre.slots[1:] if s.active]
    if len(active) != len(target_active):
        raise ValueError('field preset must have the same echo-pulse count as the tuned preset')
    for src, dst in zip(active, target_active):
        dst.start, dst.length, dst.coef = src.start, src.length, src.coef
    field_pre.slots[0].start = pre.slots[0].start
    field_pre.slots[0].length = pre.slots[0].length
    bounds = session.state['preliminary_optimum']['field_sweep']['fields_g']
    field_pre.start_field, field_pre.end_field = bounds[0], bounds[-1]
    field_pre.step_field = (bounds[-1] - bounds[0]) / (len(bounds) - 1)
    for target in (pre, field_pre):
        target.win_left_ns = session.state['echo_window']['win_left_ns']
        target.win_right_ns = session.state['echo_window']['win_right_ns']
    for target in (pre, cal, field_pre):
        wa = snapshot.build_worker_args(copy.deepcopy(target), exp_name='HandoffCheck')
        executor.run_worker(wa, target.sweep_type, script_test=True)
    names = ('echo.phase_awg', 'calibration.phase_awg', 'field.phase_awg')
    steps = [
        {'bridge.set': dict(session.state['bridge'])},
        {'tune.echo_window': {'preset': names[0]}},
        {'tune.auto_phase': {'preset': names[0]}},
        {'tune.pi_calibration': {'preset': names[1], 'mode': 'amplitude'}},
        {'field.edfs': {'preset': names[2], 'range': [f'{field_pre.start_field} G', f'{field_pre.end_field} G']}},
        {'tune.echo_window': {'preset': names[0]}},
        {'tune.auto_phase': {'preset': names[0]}},
    ]
    steps.append({'tune.pi_calibration': {'preset': names[1], 'mode': 'amplitude'}})
    document = {'sample': session.sample, 'autonomy': 'supervised', 'steps': steps}
    if session.test:
        return {'presets': list(names), 'protocol': document, 'canned': True}, []
    directory = session.run_dir / f'handoff_{session._save_counter+1:03d}'
    directory.mkdir()
    for name, target in zip(names, (pre, cal, field_pre)):
        _write_preset(target, directory / name)
        loaded = snapshot.load_preset(directory / name)
        executor.run_worker(snapshot.build_worker_args(loaded, exp_name='SavedCheck'),
                            loaded.sweep_type, script_test=True)
    path = directory / 'fine_tuning.yaml'
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    from atomize.epr_auto.protocol import load_protocol
    load_protocol(path)
    return {'presets': [str(directory / n) for n in names], 'protocol': str(path)}, []
