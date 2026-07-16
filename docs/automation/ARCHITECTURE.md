# EPR Experiment Automation — Architecture

Project: automated pulsed-EPR experiments on the ITC endstation (Insys FM214x3GDA),
built on Atomize. Companion file: [ROADMAP.md](ROADMAP.md) (phases + session log).

## Decisions (agreed 2026-07-16)

| Question | Decision |
|---|---|
| Overall shape | Shared **primitives library** + **declarative protocol runner** first; GUI/assistant layers may come later on the same engine |
| Protocol format | **YAML** for sequence/parameters; custom logic as named Python step plugins |
| Execution context | Terminal process **with the Atomize GUI open** (deer_bench.py pattern: LivePlot socket reachable, cwd = `libs/`); also launchable through the GUI Start button (argv-compatible) |
| Autonomy | Policy knob per protocol: `supervised` (pause every step) / `checkpointed` (pause at `checkpoint: true` steps) / `autonomous` (judges auto-approve, Telegram notify) |
| Tuning scope v1 | auto-phase, π/π₂ calibration, EDFS + field setup. Resonator tuning: out of scope |
| π-calibration modes | **Amplitude sweep (default for AWG**, fixed length ⇒ fixed bandwidth, no 3.2 ns grid; preset `ampl_4s.phase_awg`) and length-increment nutation (`rabi_echo_4s.phase_awg`) — `mode: amplitude \| length` |
| π-calibration strategy | **Two-stage** (agreed 2026-07-16): coarse = rotary vane sets the power regime ("power for desired length"), fine = per-pulse AWG amplitude sweep at fixed length. See "Flip-angle knobs" below |

## Flip-angle knobs: length / AWG amplitude / rotary vane

Three knobs set the flip angle; they have fixed roles, not interchangeable ones:

- **Length** = an experimental *requirement* (bandwidth/selectivity), chosen by
  the protocol, quantized to the 3.2 ns grid — not a free tuning knob on AWG.
- **Rotary vane attenuator** (`mw_bridge_rotary_vane`, 0.1 dB steps) = coarse,
  **global** (scales B₁ of every pulse at once — cannot set π and π/2
  independently at equal length), mechanical, slow (36 ms/step, ~7 s homing),
  position **dead-reckoned** (stepper steps relative to `prev_dB`; true re-home
  only at the 0/60 dB limits).
- **AWG amplitude** = fine, per-pulse, instant, repeatable; amplitude → B₁ is
  nonlinear near amplifier compression; running far below full scale wastes
  DAC dynamic range.

**Default AWG calibration procedure:**
1. *Coarse (optional, infrequent)* — `tune.power_for_length`: AWG amplitude at
   ~90–95 %, step the vane until the π condition lands at the protocol's target
   length. Run once per sample/resonator setup, or when stage 2 hits its rails.
2. *Fine (every experiment)* — `tune.pi_calibration(mode=amplitude)`: per-pulse
   amplitude sweep at fixed length; calibrate π and π/2 **independently** (do
   NOT assume amp(π/2) = amp(π)/2 — compression). Judge: the measured
   amp(π)/amp(π/2) ratio is a linearity diagnostic; large deviation from 2 ⇒
   flag compression, suggest more vane attenuation.

**Rail-triggered fallback:** if the fine sweep can't reach π below 100 %
amplitude, or reaches it only below ~30 % (wasted dynamic range), the runner
falls back to stage 1 automatically (subject to autonomy policy).

**Vane rules:** (a) after ANY vane move, auto-phase and fine amplitude
calibration are invalidated and must re-run (B₁ changed for everything, incl.
the detection echo); (b) approach set-points from the same direction (or
overshoot-and-return) to kill backlash; (c) Limit-mode re-home at the start of
long autonomous runs (position is dead-reckoned); (d) vane moves default to
`checkpoint: true` in checkpointed mode.

**RECT channel (later phase):** no per-pulse amplitude, so the modes are true
alternatives there — power-for-length when bandwidth matters, plain length
nutation otherwise.
| Experiments v1 | T1 (inversion recovery), T2/Tm (Hahn echo decay) |
| Channel | **AWG first** (awg_phasing_insys path); RECT in a later phase |
| Sequence source | Existing `*.phase_awg` presets + the sequence/acquisition machinery inside `atomize/control_center/awg_phasing_insys.py` |

## Layered design

```
protocols/*.yaml                      what to do (declarative, diffable)
        │
atomize/epr_auto/runner.py            step executor: checkpoints, retries,
        │                             judges, results manifest, notifications
atomize/epr_auto/primitives/          tune.auto_phase / tune.pi_calibration /
        │                             field.edfs / exp.t1 / exp.t2 + judges
atomize/epr_auto/engine/              preset-driven sequence builder +
        │                             scan/acquisition loop (extracted from
        │                             awg_phasing_insys internals)
device modules (Insys_FPGA, Micran bridge, BH_15, Lakeshore_335)
```

Each layer is usable without the ones above it (primitives callable from a
plain script; engine usable without protocols).

## Package layout (target)

```
atomize/epr_auto/
    __init__.py
    cli.py            # python -m atomize.epr_auto run <protocol.yaml> [--test]
    session.py        # EPRSession: device handles, autonomy policy, run directory
    protocol.py       # YAML load + schema validation + whole-protocol test-mode pre-flight
    runner.py         # step loop, checkpoint gating, retry policy, manifest
    steps.py          # registry mapping YAML step names -> primitive callables
    engine/
        sequence.py   # .phase_awg preset -> pulse program (from awg_phasing_insys)
        acquisition.py# scan loop, digitizer readout, phase-cycle handling
    primitives/
        tune.py       # auto_phase(), pi_calibration()
        field.py      # edfs(), set_field()
        relaxation.py # t1(), t2()
        judges.py     # echo SNR, fit quality, convergence — pass/fail + score
protocols/            # in-repo example protocols (overnight_t2.yaml, ...)
docs/automation/      # this file + ROADMAP.md
```

## Protocol schema (v1 sketch)

```yaml
sample: RO2411
autonomy: checkpointed        # supervised | checkpointed | autonomous
output: ~/epr_data/{date}_{sample}/   # run directory; manifest + CSVs land here
steps:
  - tune.auto_phase: {}
  - field.edfs:
      preset: ed_4s.phase_awg
      range: [338 mT, 352 mT]
      pick: max               # max | marker | value
      checkpoint: true
  - tune.pi_calibration:
      preset: rabi_echo_4s.phase_awg
      channel: AWG
  - exp.t2:
      preset: hahn_echo_4s.phase_awg
      tau_start: 300 ns
      tau_step: 12 ns
      points: 400
      scans: 16
```

Steps reference `*.phase_awg` presets (same format the Sequence Calculator and
phasing tools use — see memory `awg-preset-format`) with per-step parameter
overrides. Calibration results (π length/amplitude, phase, field) flow forward:
later steps see them via the session state and presets are patched accordingly.

## Hard constraints (learned from the codebase — do not violate)

- **GUI must be running** for LivePlot; the client raises
  `EnvironmentError` otherwise. Runner checks and degrades to save-only mode
  with a clear message.
- **cwd must be `Atomize_ITC/libs`** before instantiating `Insys_FPGA`
  (driver reads `brd.ini` / `exam_adc.ini` relative to cwd). `cli.py` does this.
- **Test-mode pre-flight**: before touching hardware, the whole protocol is
  replayed against throwaway test-mode device instances (`argv[1] == 'test'`
  semantics) so overlap/length asserts reject bad protocols up front — same
  trick as the phasing tools' LiveReject validation.
- `general.message(...)`, never bare `print()`, in anything the GUI may launch.
- Time values are `"<float> <unit>"` strings everywhere.
- **TRIGGER_AWG pulses have a hidden same-named `+'AWG'` amp-gate partner**
  (see memory `eseem-averaging-feature` / `live-edit-no-restart`): shifting/
  redefining MW pulses must keep the partner in sync.
- Respect the cross-process GPIB locks (`temp_param`, `field.param`) when
  touching Lakeshore/BH_15 — same discipline as the four experiment runners.
- Buffer forcing order: `streamBufSizeKb` only after `pulser_repetition_rate`
  (memory `insys-benchmark-automation`).

## Reference code

- `~/q/2026_07_06_insys_efficiency_auto/deer_bench.py` — proven terminal-launch
  scan loop against real hardware (env-JSON config, GUI open, cwd=libs).
- `atomize/control_center/awg_phasing_insys.py` — sequence building, phase
  cycling, sweep types (incl. log-time for T1), digitizer handling to extract.
- `atomize/script_examples/EPR_endstation/Pulsed_EPR/AWG/Relaxation/T2.py`,
  `cpmg*.py` — existing relaxation acquisition scripts.
- `atomize/control_center/experiments/*.phase_awg` — preset library
  (ed_4s, rabi_echo_4s, hahn_echo_4s, inversion_recovery_echo_4s_log, ...).
- `atomize/math_modules/fft.py` `auto_phase_zero` (principal-axis, sign-blind)
  — the auto-phase math; relaxation fits in the data-treatment math.
