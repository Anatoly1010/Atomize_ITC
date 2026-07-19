"""Step registry: maps protocol step names to parameter specs and implementations.

The tuning/field steps (Phase 2) delegate to atomize.epr_auto.primitives —
imported lazily inside the step functions, never at module scope: the
primitives pull in the engine (PyQt6 + general_functions via
awg_phasing_insys), and this module must stay importable for headless
validation before test/real mode is decided.

Judge policy: every primitive returns (result, judge_reports). In a live run
any failed judge aborts the step (StepFailure) except the advisory ones
(pi_ratio_linearity — a compression diagnostic, not a data-quality gate);
in a dry-run judges are logged only. Rail-triggered automatic fallback to
tune.power_for_length is a Phase 3 runner-policy item — until then a rail
failure surfaces as a StepFailure carrying the judge's hint.
"""
from dataclasses import dataclass
from typing import Callable

from atomize.epr_auto.params import (
    AutoOr, Bool, CalMap, Choice, FieldStr, Float, Int, PairOf, ParamError,
    PresetFile, TimeStr, parse_field_g, parse_time_ns,
)


class StepFailure(RuntimeError):
    """Raised by a step implementation when the step itself failed
    (bad data, judge rejection); the runner reports it without a traceback.
    `rails` ('high'/'low') is set when the failure came from the
    amplitude_rails judge — the runner's trigger for the coarse-stage
    fallback (ARCHITECTURE.md 'Rail-triggered fallback')."""

    def __init__(self, msg, rails=None):
        super().__init__(msg)
        self.rails = rails


@dataclass
class StepSpec:
    name: str
    summary: str
    params: dict
    func: Callable
    check: Callable | None = None  # cross-parameter validation; may fill mode-dependent defaults


STEPS: dict[str, StepSpec] = {}


def register(name, summary, params=None, check=None):
    def deco(func):
        STEPS[name] = StepSpec(name, summary, params or {}, func, check)
        return func
    return deco


# ---------------------------------------------------------------- helpers

# Advisory judges warn but never abort: pi_ratio_linearity is a compression
# diagnostic; fit_quality reports the GLOBAL nutation fit while pi/pi2 come
# from de-biased local estimates (a mediocre adj-R2 does not invalidate
# them); convergence is power_for_length's failure diagnostic (its hard gate
# is pi_length_target). NOTE Phase 4: relaxation-fit steps must gate on a
# differently-named hard judge (e.g. 'relaxation_fit'), not 'fit_quality'.
_ADVISORY_JUDGES = ('pi_ratio_linearity', 'fit_quality', 'convergence')


def _run_primitive(session, func, advisory_extra=(), **kwargs):
    """Call a primitive, log its judge reports, gate on them (live only).
    advisory_extra names judges that are advisory for THIS step only (e.g. the
    exp.* relaxation steps demote echo_snr: relaxation_fit is their hard gate,
    and a noisy-but-valid decay must not also be aborted on SNR — echo_snr
    stays a hard gate for tune.*/field.*)."""
    try:
        result, judge_reports = func(session, **kwargs)
    except StepFailure:
        raise
    except (ValueError, RuntimeError) as e:
        # expected failure modes: bad preset/arguments (ValueError), engine /
        # vane / lock errors (RuntimeError incl. EngineError) — report as a
        # failed step, not a traceback
        raise StepFailure(str(e)) from None
    session.last_judges = list(judge_reports)   # runner -> manifest
    for j in judge_reports:
        session.log(f'      {j}')
    if not session.test:
        advisory = _ADVISORY_JUDGES + tuple(advisory_extra)
        hard = [j for j in judge_reports
                if not j.passed and j.name not in advisory]
        if hard:
            rails = next((j.details.get('rail') for j in hard
                          if j.name == 'amplitude_rails'), None)
            raise StepFailure('; '.join(str(j) for j in hard), rails=rails)
    return result


# ---------------------------------------------------------------- tuning

@register('tune.auto_phase',
          'Acquire an echo and zero the signal phase (principal-axis auto_phase_zero)',
          params={
              'preset': PresetFile(default='hahn_echo_4s.phase_awg'),
              'points': Int(min=2, default=4,
                            help='sweep points for the quick phase acquisition'),
              'scans': Int(min=1, default=1),
          })
def tune_auto_phase(session, preset, points, scans):
    from atomize.epr_auto.primitives import tune
    return _run_primitive(session, tune.auto_phase,
                          preset=preset, points=points, scans=scans)


@register('tune.echo_window',
          'Set the integration window from an averaged echo trace (center = '
          'smoothed |V| max, width = FWHM x factor); run BEFORE tune.auto_phase',
          params={
              'preset': PresetFile(default='hahn_echo_4s.phase_awg'),
              'factor': Float(min=1, max=10, default=2.0,
                              help='window width as a multiple of the echo FWHM'),
              'sweeps': Int(min=1, default=3,
                            help='full phase cycles to average for the trace'),
          })
def tune_echo_window(session, preset, factor, sweeps):
    from atomize.epr_auto.primitives import tune
    return _run_primitive(session, tune.echo_window,
                          preset=preset, factor=factor, sweeps=sweeps)


@register('tune.power_for_length',
          'Coarse stage: step the rotary vane until pi lands at the target length '
          '(see ARCHITECTURE.md "Flip-angle knobs")',
          params={
              'target_length': TimeStr(required=True, help='desired pi pulse length'),
              'amplitude': Float(min=1, max=100, default=95.0,
                                 help='AWG amplitude (%) held during the vane scan'),
              'preset': PresetFile(default='rabi_echo_4s.phase_awg',
                                   help='length-nutation preset used to measure pi'),
              'tolerance': TimeStr(default='3.2 ns'),
              'max_iter': Int(min=1, default=4),
              'rehome': Choice('no', 'limit', default='no',
                               help='limit: true re-home at the 60 dB switch first'),
          })
def tune_power_for_length(session, target_length, amplitude, preset,
                          tolerance, max_iter, rehome):
    from atomize.epr_auto.primitives import tune
    return _run_primitive(session, tune.power_for_length,
                          target_length=target_length, amplitude=amplitude,
                          preset=preset, tolerance=tolerance,
                          max_iter=max_iter, rehome=rehome)


def _check_pi_calibration(params, ctx):
    if params['preset'] is None:
        default = 'ampl_4s.phase_awg' if params['mode'] == 'amplitude' else 'rabi_echo_4s.phase_awg'
        params['preset'] = PresetFile().validate(default, ctx)


@register('tune.pi_calibration',
          'Fine stage: sweep AWG amplitude at fixed length (default) or length '
          'nutation; fit pi and pi/2 independently',
          params={
              'preset': PresetFile(help='defaults to ampl_4s / rabi_echo_4s by mode'),
              'mode': Choice('amplitude', 'length', default='amplitude'),
              'channel': Choice('AWG', default='AWG'),
              'points': Int(min=2, help='sweep points (default: preset value)'),
              'scans': Int(min=1, help='scans (default: preset value)'),
              'step': Float(min=0.01, help='amplitude step in % (Amplitude mode; '
                                           'default: preset value)'),
              'refine': Bool(default=False,
                             help='re-run the nutation once with the re-scaled '
                                  'soft detection pair (new-sample insurance)'),
          },
          check=_check_pi_calibration)
def tune_pi_calibration(session, preset, mode, channel, points, scans, step,
                        refine):
    from atomize.epr_auto.primitives import tune
    return _run_primitive(session, tune.pi_calibration,
                          preset=preset, mode=mode, channel=channel,
                          points=points, scans=scans, step=step,
                          refine=refine)


# ---------------------------------------------------------------- field

def _check_edfs(params, ctx):
    if params['pick'] == 'value' and params['value'] is None:
        raise ParamError("pick: value requires the 'value' parameter")
    if params['pick'] == 'marker':
        raise ParamError('pick: marker needs the interactive tools — '
                         'use max or value (operator pick is a Phase 3 item)')
    if params['range'] != 'auto':
        lo, hi = (parse_field_g(v) for v in params['range'])
        if lo >= hi:
            raise ParamError(f"range must be [low, high], got {params['range']}")
    elif parse_field_g(params['span']) <= 0:
        # the auto range is center +/- span, so a zero span is the same
        # degenerate lo == hi sweep the explicit-range check rejects above
        raise ParamError(f"range: auto needs a positive span, got {params['span']!r}")


@register('field.edfs',
          'Echo-detected field sweep; pick the working field and set the magnet. '
          "range: auto centers on h*nu/(g*mu_B) from the synthesizer readout",
          params={
              'preset': PresetFile(default='ed_4s.phase_awg'),
              'range': AutoOr(PairOf(FieldStr()), required=True,
                              help="[start, end] field, or 'auto'"),
              'points': Int(min=2, default=200),
              'scans': Int(min=1, default=1),
              'pick': Choice('max', 'marker', 'value', default='max'),
              'value': FieldStr(help='field to set when pick: value'),
              'g': Float(min=0.1, max=20, default=2.0023,
                         help='g-factor for the range: auto center'),
              'span': FieldStr(default='250 G',
                               help='half-width of the range: auto sweep'),
              'offset': FieldStr(signed=True, default='0 G',
                                 help='known magnet-calibration shift added to '
                                      'the range: auto center'),
          },
          check=_check_edfs)
def field_edfs(session, preset, range, points, scans, pick, value, g, span,
               offset):
    from atomize.epr_auto.primitives import field as field_primitives
    return _run_primitive(session, field_primitives.edfs,
                          preset=preset, range=range, points=points,
                          scans=scans, pick=pick, value=value, g=g, span=span,
                          offset=offset)


@register('field.set',
          'Set the magnetic field directly',
          params={'value': FieldStr(required=True)})
def field_set(session, value):
    from atomize.epr_auto.primitives import field as field_primitives
    return _run_primitive(session, field_primitives.set_field, value=value)


# ---------------------------------------------------------------- temperature

@register('temp.set',
          'Set the Lakeshore 335 setpoint (and heater range); returns '
          'immediately — pair with temp.wait',
          params={
              'setpoint': Float(min=0.1, max=400, required=True, help='kelvin'),
              'heater_range': Choice(*('Off', '0.5 W', '5 W', '50 W'),
                                     help='unchanged when omitted'),
              'rephase_delta': Float(min=0, default=5.0,
                                     help='invalidate auto_phase once the setpoint '
                                          'moves this many K from where the phase '
                                          'was measured (0 = any change)'),
          })
def temp_set(session, setpoint, heater_range, rephase_delta):
    from atomize.epr_auto.primitives import temp
    return _run_primitive(session, temp.set_temperature,
                          setpoint=setpoint, heater_range=heater_range,
                          rephase_delta=rephase_delta)


@register('temp.wait',
          'Wait until the temperature holds inside the band (temp_control '
          'setter-waiter semantics); timeout fails the step',
          params={
              'band': Float(min=0.01, default=0.2, help='+/- kelvin around the setpoint'),
              'channels': Choice('A', 'B', 'AB', default='B'),
              'hold': Int(min=1, default=3,
                          help='consecutive in-band polls (1 s cadence) required'),
              'timeout': TimeStr(default='1800 s'),
              'setpoint': Float(min=0.1, max=400,
                                help='default: the setpoint already on the device'),
              'rephase_delta': Float(min=0, default=5.0,
                                     help='invalidate auto_phase once the setpoint '
                                          'moves this many K from where the phase '
                                          'was measured (0 = any change)'),
          })
def temp_wait(session, band, channels, hold, timeout, setpoint, rephase_delta):
    from atomize.epr_auto.primitives import temp
    return _run_primitive(session, temp.wait_temperature,
                          band=band, channels=channels, hold=hold,
                          timeout=timeout, setpoint=setpoint,
                          rephase_delta=rephase_delta)


# ---------------------------------------------------------------- experiments

def _apply_cal(session, preset, mapping):
    """Load the experiment preset and patch it with the session's
    pi_calibration result (explicit {slot: role} map, 'none' = deliberate
    skip, or inferred from the preset's own two amplitude levels). Returns
    the (possibly patched) Preset the exp primitive acquires with."""
    from atomize.epr_auto.engine import snapshot
    from atomize.epr_auto.primitives import tune
    try:
        pre = snapshot.load_preset(preset)
    except (ValueError, RuntimeError, IndexError) as e:
        # a corrupt/truncated preset (PresetError is a ValueError; a malformed
        # line can IndexError) is loaded here, OUTSIDE _run_primitive's try —
        # convert it to StepFailure so retries/on_fail apply, matching how the
        # sibling steps (which load inside the primitive) handle it
        raise StepFailure(str(e)) from None
    if mapping == 'none':
        # deliberate opt-out: acquire with the preset's stored values even
        # though a calibration exists (e.g. a preset whose roles can't be
        # inferred and whose stored amplitudes are already trusted)
        if session.state.get('pi_calibration'):
            session.log('      apply_cal: none — pi_calibration deliberately '
                        'not applied, preset-stored values in force')
        return pre
    try:
        patched = tune.apply_calibration(session, pre, mapping)
    except ValueError as e:
        raise StepFailure(str(e)) from None
    if patched:
        desc = ', '.join(f"{k}: {v['field']}={v['value']} {v['unit']} ({v['role']})"
                         for k, v in patched.items())
        session.log(f'      apply_cal -> {desc}')
    return pre


@register('exp.t2',
          'Hahn echo decay (T2/Tm), linear tau sweep, with fit',
          params={
              'preset': PresetFile(default='hahn_echo_4s.phase_awg'),
              'tau_start': TimeStr(default='300 ns'),
              'tau_step': TimeStr(default='12 ns'),
              'points': Int(min=2, required=True),
              'scans': Int(min=1, default=1),
              'window': Choice('auto', 'preset', default='auto',
                               help='auto: tune.echo_window result; preset: stored values'),
              'apply_cal': CalMap(help='slot -> pi/pi2 map; none = do not patch; '
                                       'omitted = inferred from the preset '
                                       'amplitude levels'),
              'max_duration': TimeStr(help='wall-clock budget; the scan count '
                                           'shrinks mid-run to finish inside it '
                                           '(data acquired so far is kept)'),
              'rep_rate': Float(min=0.1, max=100000,
                                help='repetition rate in Hz (default: preset '
                                     'value); the sweep must fit one period'),
              'target_snr': Float(min=1,
                                  help='SNR-driven scan count: scans becomes '
                                       'the ceiling; stop early once the '
                                       'accumulated curve reaches this '
                                       'echo_snr score (min wins vs '
                                       'max_duration)'),
          })
def exp_t2(session, preset, tau_start, tau_step, points, scans, window,
           apply_cal, max_duration, rep_rate, target_snr):
    pre = _apply_cal(session, preset, apply_cal)
    from atomize.epr_auto.primitives import exp as exp_primitives
    return _run_primitive(session, exp_primitives.t2, advisory_extra=('echo_snr',),
                          preset=pre, tau_start=tau_start, tau_step=tau_step,
                          points=points, scans=scans, window=window,
                          max_duration=max_duration, rep_rate=rep_rate,
                          target_snr=target_snr)


def _check_t1(params, ctx):
    if parse_time_ns(params['t_start']) >= parse_time_ns(params['t_end']):
        raise ParamError(f"t_start must be < t_end, got {params['t_start']} .. {params['t_end']}")


@register('exp.t1',
          'Inversion recovery (T1), log-time sweep, with fit',
          params={
              'preset': PresetFile(default='inversion_recovery_echo_4s_log.phase_awg'),
              't_start': TimeStr(default='500 ns'),
              't_end': TimeStr(default='5 ms'),
              'points': Int(min=2, required=True),
              'scans': Int(min=1, default=1),
              'window': Choice('auto', 'preset', default='auto',
                               help='auto: tune.echo_window result; preset: stored values'),
              'apply_cal': CalMap(help='slot -> pi/pi2 map; none = do not patch; '
                                       'omitted = inferred from the preset '
                                       'amplitude levels'),
              'max_duration': TimeStr(help='wall-clock budget; the scan count '
                                           'shrinks mid-run to finish inside it '
                                           '(data acquired so far is kept)'),
              'rep_rate': Float(min=0.1, max=100000,
                                help='repetition rate in Hz (default: preset '
                                     'value); a T1 sweep needs 1/rep_rate '
                                     'beyond t_end plus the sequence tail'),
              'target_snr': Float(min=1,
                                  help='SNR-driven scan count: scans becomes '
                                       'the ceiling; stop early once the '
                                       'accumulated curve reaches this '
                                       'echo_snr score (min wins vs '
                                       'max_duration)'),
          },
          check=_check_t1)
def exp_t1(session, preset, t_start, t_end, points, scans, window, apply_cal,
           max_duration, rep_rate, target_snr):
    pre = _apply_cal(session, preset, apply_cal)
    from atomize.epr_auto.primitives import exp as exp_primitives
    return _run_primitive(session, exp_primitives.t1, advisory_extra=('echo_snr',),
                          preset=pre, t_start=t_start, t_end=t_end,
                          points=points, scans=scans, window=window,
                          max_duration=max_duration, rep_rate=rep_rate,
                          target_snr=target_snr)
