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
| π-calibration modes | **Amplitude sweep (default for AWG**, fixed length ⇒ fixed bandwidth, no time-grid quantization; preset `ampl_4s.phase_awg`) and length-increment nutation (`rabi_echo_4s.phase_awg`) — `mode: amplitude \| length` |
| AWG timing grid | **3.2 ns default; opt-in 0.8 ns** (one DAC sample) via the preset's trailing `AWG grid:  0.8` line / GUI Settings toggle / `pb.awg_time_resolution('0.8 ns')`. TTL stays on 3.2 ns; sub-tick = zero samples in the DAC buffer; detection window residual corrected digitally at readout (use decimation ≤ 2). Plan: `docs/automation/AWG_FINE_STEP_PLAN.md` |
| π-calibration strategy | **Two-stage** (agreed 2026-07-16): coarse = rotary vane sets the power regime ("power for desired length"), fine = per-pulse AWG amplitude sweep at fixed length. Classical length nutation stays available as `mode: length` (see "Flip-angle knobs" and "Tune-up completeness" below) |
| Experiments v1 | T1 (inversion recovery), T2/Tm (Hahn echo decay) |
| Channel | **AWG first** (awg_phasing_insys path); RECT in a later phase |
| Sequence source | Existing `*.phase_awg` presets + the sequence/acquisition machinery inside `atomize/control_center/awg_phasing_insys.py` |
| Detection pulses during calibration | **Soft/selective pair at ~3–4× the target length** (target 22 ns ⇒ 60–90 ns) at **proportionally lower amplitude** — standard rule `amp_det = amp_cal · L_target/L_det` (amp nearly linear); optional one-shot refine re-run (agreed 2026-07-17, see "Tune-up completeness") |
| Integration window | `tune.echo_window` primitive: echo-trace acquisition → auto window, stored relative to the DETECTION pulse start; runs before auto-phase (agreed 2026-07-17) |
| Temperature | `temp.set` / `temp.wait` primitives mirroring temp_control's setter-waiter (band, hold count, wall-clock timeout) under the temp_param lock (agreed 2026-07-17) |
| Initial signal search | `field.edfs range: auto` from synthesizer frequency + g (default 2.0023) with one widen-and-retry escalation; truly blind search stays human (agreed 2026-07-17) |

## Flip-angle knobs: length / AWG amplitude / rotary vane

Three knobs set the flip angle; they have fixed roles, not interchangeable ones:

- **Length** = an experimental *requirement* (bandwidth/selectivity), chosen by
  the protocol, quantized to the active AWG time grid (3.2 ns default, 0.8 ns
  opt-in — see the AWG-timing-grid decision above) — not a free tuning knob on AWG.
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

**Temperature rules:** temperature detunes the resonator, so the demod
zero-order drifts — but B₁ is untouched, so the rules are *not* the vane
rules. Measured on the 2026-07-03 oTP series (`~/Documents/OTP/
2026_07_03_ap210_oTP_new`, `t1/` + `t2/` presets), at constant pulse
amplitudes (84 % / 42 %, Ampl 260/260, 32 ns throughout — nobody re-calibrated
power between temperatures):

| T | 80 K | 120 K | 160 K | 200 K | 240 K | 280 K |
|---|---|---|---|---|---|---|
| zero-order | 215° | 207° | 192° | 160° | 80° | 25° |

A monotonic 190° swing. Hence: (a) a setpoint move beyond `rephase_delta`
(default 1 K — the swing averages ~1°/K and is steeper at the warm end, so
1 K keeps the carried error at the phase-noise level) invalidates
**auto-phase only** — `session.invalidate_phase`, checked in both `temp.set`
and `temp.wait`; (b) the fine amplitude calibration **survives** a
temperature change — only the vane moves B₁, and in practice the vane is
re-set only after a large ΔT, to hold bandwidth; (c) `tune.auto_phase`
stamps `temperature_k` on its result so the manifest records where each
phase was taken — before any temp step has run, the stamp is the measured
channel-B temperature (None only if the Lakeshore is unreachable, which
falls back to an unconditional drop on the first temp step).

The same series also shows what zero-order does *not* depend on: it is
identical for T1 and T2 at matched (T, field) in 25 of 26 pairs — despite
their DETECTION pulses starting at 678.4 ns vs 409.6 ns — and identical
across 3000–3460 G. Zero-order is a property of the detection chain and
resonator state, never of the pulse sequence: one `tune.auto_phase` serves
every experiment at a given (temperature, vane) state.

**RECT channel (later phase):** no per-pulse amplitude, so the modes are true
alternatives there — power-for-length when bandwidth matters, plain length
nutation otherwise.

## Tune-up completeness (agreed 2026-07-17)

Five gaps identified in review of the Phase 2/3 plan; decisions fixed here,
implementation items in ROADMAP Phase 5.

### Length-nutation results must flow downstream (classical approach)

`tune.pi_calibration(mode='length')` already measures π/π₂ **lengths**
(`rabi_echo_4s.phase_awg`, nonzero Length Increment) — what's missing is the
consumer: experiment presets never receive the calibrated values (neither
lengths nor amplitudes; session state stores them, nothing reads them).
Decision:

- Session state (`pi_calibration`: pi/pi2 + unit + mode) is applied to later
  builds through an explicit per-step mapping, e.g.
  `apply_cal: {P2: pi2, P3: pi}` (slot → role) on `exp.*` steps.
- Default when `apply_cal` is omitted: infer by coefficient ratio among the
  active hard MW pulses (the preset's own two amplitude levels map to π and
  π/2); ambiguity ⇒ validation error asking for the explicit map. Soft
  detection pulses (see next section) are excluded by the length criterion.
- Length-mode values are grid-quantized before patching (3.2 ns default; π/2
  on the coarse grid is coarse — the opt-in 0.8 ns fine grid is the fix).
  Amplitude-mode values patch the amplitude coefficient at fixed length.

### Detection pulses inside the π/π₂ calibration sequences

Lab convention (2026-07-17): the detection pair is **soft/selective** — about
3–4× the target pulse length (target 22 ns ⇒ detection 60–90 ns). The presets
already encode this: `ampl_4s` sweeps a 28.8 ns GAUSS and detects with an
86.4 ns SINE pair at low amplitude coefficients (9/18 — linear regime).
Selective detection watches only the on-resonance packet the hard pulse
rotates, and its low amplitude keeps it out of amplifier compression.

- **Never patch the detection pair with the target's calibrated amplitudes
  directly** — longer pulse ⇒ certainly lower amplitude. The rule is
  **proportional inverse-length scaling**:
  `amp_det(θ) = amp_cal(θ) · L_target / L_det`. The amplifier is nearly
  linear (lab measurement 2026-07-17), so this scaling is the *standard* way
  the pair is set after every fine calibration, not an optional refinement.
- Bootstrap (why the chicken-and-egg is soft): first pass runs the
  preset-stored detection values as-is. The nutation extremum *position* is
  first-order independent of detection-pair errors (they scale the echo, they
  don't move the minimum), and the coarse vane stage keeps the global B₁
  scale ≈right.
- `refine: true` (default off): re-run the nutation once with the re-scaled
  pair — worth it on a new sample where the preset's stored pair was far off.
- Slot roles: swept pulse = nonzero st_inc/len_inc (existing worker
  criterion); detection pair = the remaining active MW pulses, identified as
  *soft* by length ≥ 2.5× the swept pulse's (`tune._SOFT_LEN_RATIO`, shared
  with `apply_cal`'s role inference so the two primitives can never classify
  the same pulse both ways; the cut must sit between 2 — a length-encoded π
  is exactly 2× its π/2 — and ~3, where real detection pairs start).

### Integration window (`tune.echo_window`)

Today the preset's `Window left/right` is used verbatim (snapshot converts
ns → points); nothing tunes it. New primitive:

- Acquire the **averaged echo trace** at current settings — needs a new
  engine capability: `executor.acquire_trace` reusing the Worker's preview
  (dig_on-style) path; the engine currently speaks only the sweep-integral
  protocol. **[F]** — Worker preview semantics are subtle.
- Rotate by the current zero-order, echo center = max of smoothed |V(t)|,
  width = FWHM × factor (default ≈ 2, configurable), snap to the ADC grid;
  judge: echo fully inside the trace + SNR floor.
- Store the window **relative to the DETECTION pulse start** (offset, width)
  so it transfers across presets whose τ (hence absolute echo position)
  differs; `_session_overrides` applies it to every later build. `exp.*`
  steps get `window: auto | preset` (default auto once calibrated).
- **Ordering rule:** echo_window runs *before* `tune.auto_phase` — auto-phase
  integrates over the window, so a mis-set window degrades the phase
  estimate. Canonical chain: power_for_length → field.edfs → echo_window →
  auto_phase → pi_calibration.

### Temperature (`temp.set` / `temp.wait`)

Mirror the proven temp_control setter-waiter (memory
`temperature-control-feature`): Lakeshore 335 via the session's lazy device;
`temp.set {channel, setpoint, heater_range}`, `temp.wait {band, hold,
timeout}` — per-channel band around the setpoint, consecutive in-band polls
(hold default 3 at 1 s cadence — GPIB is slow), wall-clock timeout ⇒
StepFailure so the `on_fail`/retry/notify policy applies. temp_param lock
seized with source 'epr_auto' (already in session.ensure_hardware_locks).
Temperature *series* (T1 vs T): v1 = explicit repeated steps in the YAML; the
`foreach:` block is Phase 6 (see "Series & SNR-driven scans" below).

### Series & SNR-driven scans (`foreach:` / `target_snr:`) — Phase 6 (implemented 2026-07-19)

The motivating workflow is relaxation times at fixed T across several fields
(the standard T1/T2-vs-position measurement). Two independent pieces:

**`foreach:` block** — one loop variable, `$VAR` substitution into the
repeated steps (field series: `field.set {value: $B}` + exp.*; temperature
series: temp.set/temp.wait + exp.*). Manifest + CSV names stamp the loop
value; a StepFailure inside one iteration records it and continues to the
next value by default (a dead field position must not kill the series —
unlike the global `on_fail`). **Field moves do NOT invalidate auto_phase**:
measured on the 2026-07 oTP campaign (ED-sweep phase flat to ±3.5° across
the line; raw per-field T2 curves ≤4.8° spread; exp.* re-rotates onto the
principal axis before fitting anyway). Temperature moves keep
`rephase_delta`. Tune once at the line max, then loop.

**`target_snr:` on exp.t1/t2** — `scans` becomes the ceiling; a second
scan_control consumer on the existing 'SC<n>' channel projects the needed
count from √N scaling (after scan k: N ≈ k·(target/SNR_k)²) and ratchets
down, composed with `max_duration` (min wins). Stop metric =
`judges.echo_snr` on the rotated accumulated curve — same metric as the
final judge; noise sigma stays MAD-of-diff, because fit-residual sigma is
inflated by systematic misfit (ESEEM modulation) that more scans cannot
reduce — a residual-based criterion would over-scan without bound. The Worker
sends an opt-in scan-boundary `('ScanData', (k, data_x, data_y))` message
from `exp`/`exp_log`, gated on the `scan_data_flag` worker ATTRIBUTE (set via
`_hand_attrs` like awg_grid_cur; the GUI never sets it ⇒ GUI runs unchanged).
run_worker's `on_scan_data(k, i, q)` consumes it; scan_control and
on_scan_data share ONE downward-only resize ratchet (`_maybe_resize`), which
is what "min wins" means mechanically: a resize is only ever sent below the
lowest already sent. Validation data + numbers: ROADMAP Phase 6; harness
`~/epr_auto_dev/field_phase_snr_check.py`.

### Initial signal search (`field.edfs range: auto`)

Not user-only, but the ladder ends at the human:

1. Protocol gives an explicit range (current behaviour, unchanged).
2. `range: auto`: center = h·ν/(g·μ_B) from the synthesizer readout
   (`mw_bridge_synthesizer`), `g:` param (default 2.0023), `span:` param
   (default ±25 mT).
3. On a failed echo-SNR judge: **one** automatic escalation — widen the span
   ×2 and re-run — then stop escalating.
4. Still nothing ⇒ StepFailure whose judge report distinguishes "flat
   everywhere" (resonator / detection window / sample problem — human) from
   "weak line found" (more scans might do); autonomy policy decides ask vs
   notify+abort.

A truly blind search (unknown g, mis-tuned resonator, wrong detection window)
is out of scope by design — the failure report must say *which* precondition
to check, not just "no signal".

## Layered design

```
protocols/*.yaml                      what to do (declarative, diffable)
        │
atomize/epr_auto/runner.py            step executor: checkpoints, retries,
        │                             judges, results manifest, notifications
atomize/epr_auto/primitives/          tune.auto_phase / tune.pi_calibration /
        │                             field.edfs / exp.t1 / exp.t2 + judges
atomize/epr_auto/engine/              snapshot.py: preset → exact Worker arg
        │                             tuples; executor.py: runs the Worker +
        │                             speaks its pipe protocol
awg_phasing_insys.Worker              the REUSED, hardware-validated scan/
        │                             acquisition loop (not extracted — the
        │                             GUI pickles this same class)
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

## Engine ↔ GUI contract (Phase 1)

`engine/snapshot.py` mirrors, line for line, the GUI pipeline
`open_file/setter → update_* handlers → dig_start_exp` packing. The sweep
type picks the Worker method: Linear Time→`exp`, Log Time→`exp_log`,
Amplitude→`exp_amplitude`, Field→`exp_field` (ESEEM Avg: not supported yet).
**Any edit to either side must be followed by re-running
`~/epr_auto_dev/gui_vs_engine.py`** (offscreen GUI vs engine, all presets,
element-wise). Executor stop semantics: sending 'exit' still reads out and
saves — treat operator stop as "finish early", not "discard".

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
