"""Step registry: maps protocol step names to parameter specs and implementations.

The tuning/field steps (Phase 2) delegate to atomize.epr_auto.primitives —
imported lazily inside the step functions, never at module scope: the
primitives pull in the engine (PyQt6 + general_functions via
awg_phasing_insys), and this module must stay importable for headless
validation before test/real mode is decided. The exp.* steps are still
dry-run stubs until Phase 4.

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
    Choice, FieldStr, Float, Int, PairOf, ParamError, PresetFile, TimeStr,
    parse_field_g, parse_time_ns,
)


class StepFailure(RuntimeError):
    """Raised by a step implementation when the step itself failed
    (bad data, judge rejection); the runner reports it without a traceback."""


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


def _run_primitive(session, func, **kwargs):
    """Call a primitive, log its judge reports, gate on them (live only)."""
    try:
        result, judge_reports = func(session, **kwargs)
    except (ValueError, RuntimeError) as e:
        # expected failure modes: bad preset/arguments (ValueError), engine /
        # vane / lock errors (RuntimeError incl. EngineError) — report as a
        # failed step, not a traceback
        raise StepFailure(str(e)) from None
    for j in judge_reports:
        session.log(f'      {j}')
    if not session.test:
        hard = [j for j in judge_reports
                if not j.passed and j.name not in _ADVISORY_JUDGES]
        if hard:
            raise StepFailure('; '.join(str(j) for j in hard))
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
          },
          check=_check_pi_calibration)
def tune_pi_calibration(session, preset, mode, channel, points, scans, step):
    from atomize.epr_auto.primitives import tune
    return _run_primitive(session, tune.pi_calibration,
                          preset=preset, mode=mode, channel=channel,
                          points=points, scans=scans, step=step)


# ---------------------------------------------------------------- field

def _check_edfs(params, ctx):
    if params['pick'] == 'value' and params['value'] is None:
        raise ParamError("pick: value requires the 'value' parameter")
    if params['pick'] == 'marker':
        raise ParamError('pick: marker needs the interactive tools — '
                         'use max or value (operator pick is a Phase 3 item)')
    lo, hi = (parse_field_g(v) for v in params['range'])
    if lo >= hi:
        raise ParamError(f"range must be [low, high], got {params['range']}")


@register('field.edfs',
          'Echo-detected field sweep; pick the working field and set the magnet',
          params={
              'preset': PresetFile(default='ed_4s.phase_awg'),
              'range': PairOf(FieldStr(), required=True, help='[start, end] field'),
              'points': Int(min=2, default=200),
              'scans': Int(min=1, default=1),
              'pick': Choice('max', 'marker', 'value', default='max'),
              'value': FieldStr(help='field to set when pick: value'),
          },
          check=_check_edfs)
def field_edfs(session, preset, range, points, scans, pick, value):
    from atomize.epr_auto.primitives import field as field_primitives
    return _run_primitive(session, field_primitives.edfs,
                          preset=preset, range=range, points=points,
                          scans=scans, pick=pick, value=value)


@register('field.set',
          'Set the magnetic field directly',
          params={'value': FieldStr(required=True)})
def field_set(session, value):
    from atomize.epr_auto.primitives import field as field_primitives
    return _run_primitive(session, field_primitives.set_field, value=value)


# ---------------------------------------------------------------- experiments

@register('exp.t2',
          'Hahn echo decay (T2/Tm), linear tau sweep, with fit',
          params={
              'preset': PresetFile(default='hahn_echo_4s.phase_awg'),
              'tau_start': TimeStr(default='300 ns'),
              'tau_step': TimeStr(default='12 ns'),
              'points': Int(min=2, required=True),
              'scans': Int(min=1, default=1),
          })
def exp_t2(session, preset, tau_start, tau_step, points, scans):
    session.log(f'      [stub] would acquire {points} pts x {scans} scans '
                f'from {preset} (Phase 4)')
    return {'t2': '1.8 us', 'fit': 'stretched_exp', 'canned': True}


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
          },
          check=_check_t1)
def exp_t1(session, preset, t_start, t_end, points, scans):
    session.log(f'      [stub] would acquire log sweep {t_start} .. {t_end}, '
                f'{points} pts x {scans} scans from {preset} (Phase 4)')
    return {'t1': '1.2 ms', 'fit': 'exp_recovery', 'canned': True}
