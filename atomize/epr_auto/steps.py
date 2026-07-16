"""Step registry: maps protocol step names to parameter specs and implementations.

Phase 0: implementations are dry-run stubs — they validate wiring (lazy
test-mode device creation, parameter plumbing, state flow) and return canned
results marked with 'canned': True. Real acquisition arrives with the engine
(Phase 1) and the tuning/experiment primitives (Phases 2/4); the specs here
are the stable protocol-facing contract.
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


# ---------------------------------------------------------------- tuning

@register('tune.auto_phase',
          'Acquire an echo and zero the signal phase (principal-axis auto_phase_zero)')
def tune_auto_phase(session):
    # Touching session.pulser here exercises the lazy test-mode device path
    # end-to-end in every dry-run.
    session.log(f'      pulser: {session.pulser.pulser_name()}')
    session.log('      [stub] would acquire echo and apply auto-phase (Phase 2)')
    return {'phase_deg': 0.0, 'canned': True}


@register('tune.power_for_length',
          'Coarse stage: step the rotary vane until pi lands at the target length '
          '(see ARCHITECTURE.md "Flip-angle knobs")',
          params={
              'target_length': TimeStr(required=True, help='desired pi pulse length'),
              'amplitude': Float(min=1, max=100, default=95.0,
                                 help='AWG amplitude (%) held during the vane scan'),
          })
def tune_power_for_length(session, target_length, amplitude):
    session.log('      [stub] would scan rotary vane (same-direction approach) '
                'and invalidate auto-phase + fine calibration (Phase 2)')
    return {'attenuation_db': 12.0, 'target_length': target_length, 'canned': True}


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
              'points': Int(min=2, default=50),
              'scans': Int(min=1, default=1),
          },
          check=_check_pi_calibration)
def tune_pi_calibration(session, preset, mode, channel, points, scans):
    session.log(f'      [stub] would run {mode} sweep from {preset} (Phase 2)')
    # amp(pi)/amp(pi/2) deliberately != 2 in the canned result: the linearity
    # judge must not learn to expect the ideal ratio.
    result = {'pi': 68.0, 'pi2': 33.5, 'unit': '%', 'mode': mode, 'canned': True}
    session.state['pi_calibration'] = result
    return result


# ---------------------------------------------------------------- field

def _check_edfs(params, ctx):
    if params['pick'] == 'value' and params['value'] is None:
        raise ParamError("pick: value requires the 'value' parameter")
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
    session.log(f'      [stub] would sweep {range[0]} .. {range[1]} ({points} pts) '
                f'from {preset}, pick={pick} (Phase 2)')
    field_g = parse_field_g(value) if pick == 'value' else \
        (parse_field_g(range[0]) + parse_field_g(range[1])) / 2
    result = {'field': f'{field_g:.1f} G', 'pick': pick, 'canned': True}
    session.state['field'] = result['field']
    return result


@register('field.set',
          'Set the magnetic field directly',
          params={'value': FieldStr(required=True)})
def field_set(session, value):
    session.log('      [stub] would set BH_15 (respecting field.param lock) (Phase 2)')
    session.state['field'] = value
    return {'field': value, 'canned': True}


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
