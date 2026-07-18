# Hardware checklist — what can be run on the spectrometer TODAY

Everything below is implemented and dry-run-verified but has never touched
the real instrument (epr_auto Phases 2/3/5, and Phase 4 — items 8–10).
Ordered so that each item builds confidence for the next; items 1–3 are
safe to interleave with normal lab work. Written 2026-07-17; Phase 4 items
added 2026-07-18.

## Prerequisites (once per lab session)

- Launch the main Atomize GUI first — the Worker child pushes live plots to
  its LivePlot server; a real run dies without it. Keep it open.
- Close the interactive field / temperature tools (or expect the runner to
  refuse: it seizes the `field.param` / `temp_param` locks as `epr_auto`
  and releases them in `finally` + `atexit`).
- Run from the repo root. The CLI chdirs to `libs/` itself (Insys driver
  requirement) and pre-flights every step in test mode before touching
  hardware.
- Every acquisition lands in the run directory (default
  `~/epr_data/epr_auto_<date>_<sample>/`) together with `manifest.json`
  (per-step params/results/judges/attempts) and a copy of the protocol.
- Any step can be wrapped in a one-step YAML; snippets below are complete
  files. Start everything in `autonomy: supervised` (Enter to continue at
  every step) until trusted.

```bash
python -m atomize.epr_auto run <protocol>.yaml --test   # always dry-run first
python -m atomize.epr_auto run <protocol>.yaml          # live
python -m atomize.epr_auto steps                        # list all steps + params
python -m atomize.epr_auto validate <file>.yaml         # check without running
```

## Presets — where the pulse sequence actually comes from

**A protocol never describes a pulse sequence.** It names a `.phase_awg`
preset, and every pulse parameter — types, starts, lengths, amplitude
coefficients, phase-cycle text, increments, rep rate, detection window — is
read out of that file by `engine/snapshot.py:load_preset`, using the same
line indices as the phasing GUI's `open_file()`. To change a sequence, edit
or copy the preset; the YAML can only reach the scalars a step chooses to
expose.

The snippets below mostly write a step as a bare string:

```yaml
steps:
  - tune.auto_phase          # <- no preset named, but one IS used
```

That is the shorthand form (`protocol.py:_parse_step`); the loader fills in
every omitted parameter from its spec default, so the line above is exactly
equivalent to:

```yaml
steps:
  - tune.auto_phase:
      preset: hahn_echo_4s.phase_awg    # the default, filled in for you
      points: 4
      scans: 1
```

Use that mapping form (note the colon and the indented block) to name your
own preset. Defaults per step:

| step | default preset |
|---|---|
| `tune.auto_phase` | `hahn_echo_4s.phase_awg` |
| `tune.echo_window` | `hahn_echo_4s.phase_awg` |
| `tune.power_for_length` | `rabi_echo_4s.phase_awg` |
| `tune.pi_calibration` | `ampl_4s.phase_awg` (mode: amplitude) / `rabi_echo_4s.phase_awg` (mode: length) |
| `field.edfs` | `ed_4s.phase_awg` |
| `exp.t2` | `hahn_echo_4s.phase_awg` |
| `exp.t1` | `inversion_recovery_echo_4s_log.phase_awg` |

Rules (`params.py:PresetFile`, `primitives/tune.py:_build`):

- A bare name resolves against **your protocol's own directory first**, then
  `atomize/control_center/experiments/`; an absolute path also works. A name
  that resolves nowhere is a load-time error with a file:line, not a
  surprise at the bench.
- The preset must be saved with **`IQ Correction:  2`** (IQ-corrected 1-D
  data) or the step is rejected at pre-flight — checked up front, before any
  hardware moves.
- `python -m atomize.epr_auto steps` prints every step's parameters and
  defaults, and `validate` resolves each preset to its absolute path without
  running anything. Use both before a bench session.
- What runs is *not* the preset as saved: the step's own parameters
  (`points`, `scans`, …) plus the session's calibrations override it —
  `field.edfs` replaces the stored `Field:`, `tune.echo_window` replaces
  `Window left/right` (consumed by exp.* via `window: auto`; `window:
  preset` pins the stored values), `tune.auto_phase` replaces the
  zero-order, and `tune.pi_calibration`'s result patches the exp.* pulse
  amplitudes (`apply_cal`; `none` opts out). exp.t2 additionally re-anchors
  the tau sweep (`tau_start`/`tau_step`) and exp.t1 the log axis
  (`t_start`/`t_end`); both can override `rep_rate`. So the preset supplies
  the pulse *geometry*; the run supplies the state.
- Choosing a preset per step is rarely about the experiment: `tune.auto_phase`
  just needs an echo, so `hahn_echo_4s` serves. Override it only when that
  sequence does not suit the sample — e.g. its fixed 288 ns τ is too long for
  a short-Tm sample, so you copy the preset with a shorter τ and point at the
  copy.

## 1. tune.auto_phase — first hardware contact (no moving parts)

Sets only the digitizer demod phase. Compare `zero_order_deg` with the
value you would set by hand in the phasing tool.

```yaml
sample: hw_check
autonomy: supervised
steps:
  - tune.auto_phase
```

Expect: `phase_coherence` PASS, echo mostly in I after a re-run
(`phase_deg` near 0 on the second pass). Record: zero_order before/after.

Scope of one auto-phase (ARCHITECTURE.md 'Temperature rules'): the result is
a property of the detection chain, not of the sequence — the same value
serves T1, T2, ESEEM and DEER at a given (temperature, vane) state, so it is
run once per state and *not* once per experiment. It does drift strongly with
temperature (190° over 80–280 K on oTP), so a setpoint move beyond
`rephase_delta` (default 1 K) drops it and the protocol must re-run
`tune.auto_phase` after the new temperature settles. The fine calibration is
not dropped — temperature does not move B₁.

## 2. tune.echo_window — NEW Phase 5, engine trace path (no moving parts)

First hardware exercise of `executor.acquire_trace` (dig_on preview reused
by the engine, accumulating mode). The 'Dig' plot in the GUI shows the
preview live while the engine captures it.

NOTE this doubles as the first-ever hardware use of dig_on's accumulating
readout (the "L. mode" checkbox path, l_mode=1 → live_mode=0): the code
audit says it reuses the everyday multi-scan exp accumulate machinery
(per-cycle pack-counter reset, blocking per-cycle drain), but nobody has
run it. Watch for: a stall at a cycle boundary (drain never satisfied), a
NaN/blank 'Dig' frame becoming the result (guarded engine-side — would
surface as 'preview ended without a captured trace'), or a trace whose SNR
does NOT grow with `sweeps:` (accumulation not actually happening).
Single-phase presets are rejected by the engine on purpose — the
accumulating readout is only well-defined per phase cycle.

```yaml
sample: hw_check
autonomy: supervised
steps:
  - tune.echo_window:
      factor: 2.0
      sweeps: 3
```

Expect: `win_left/right_ns` bracketing the echo you see in the phasing
tool's preview; `echo_in_trace` + `echo_snr` PASS; trace CSV in the run
dir. Cross-check: open the preset in the phasing GUI and eyeball the
window against the echo. Record: center_ns, fwhm_ns, window, trace file.

## 3. tune.pi_calibration (amplitude mode) — fine cal + detection pair

```yaml
sample: hw_check
autonomy: supervised
steps:
  - tune.auto_phase
  - tune.pi_calibration:
      mode: amplitude
      retries: 1
      # refine: true        # second pass with the re-scaled detection pair
```

Expect: pi/pi2 within a few % of your manual values, ratio ≈ 2 (judge
`pi_ratio_linearity`), `amplitude_rails` PASS, and the NEW
`detection_pair` result key with the inverse-length-scaled pair
amplitudes — sanity-check them against the preset's stored 9/18-style
values. With `refine: true`: the second nutation should reproduce pi/pi2
within the fit noise (this validates the amp-linearity scaling rule on
hardware). Record: pi, pi2, ratio, detection_pair, both data files.

## 4. field.edfs — explicit range first, then range: auto

MOVES THE MAGNET. Explicit range (known sample) first:

```yaml
sample: hw_check
autonomy: supervised
steps:
  - field.edfs:
      range: [338 mT, 352 mT]
      pick: max
      checkpoint: true
```

Then the NEW auto search — this is the calibration-shift measurement run:

```yaml
sample: hw_check
autonomy: supervised
steps:
  - field.edfs:
      range: auto
      g: 2.0023           # your sample's g
      # offset: 0 G       # fill in after the first run (see shift_g)
      checkpoint: true
```

Expect: the line found inside the sweep; the result's **`shift_g` is the
measured line-minus-predicted-center distance — write it down and put it
into `offset:` for this setup from now on** (the magnet is not absolutely
calibrated; this is the standing correction). Also worth one deliberate
failure: set `g` absurdly (e.g. 4.5) and check the one span-×2 escalation
fires, the magnet is NOT moved afterwards, and the failure diagnosis
("flat everywhere" vs "weak line found") makes sense.

## 5. temp.set / temp.wait — Lakeshore on

```yaml
sample: hw_check
autonomy: supervised
steps:
  - temp.set:
      setpoint: 80.0
      heater_range: 5 W
  - temp.wait:
      band: 0.3
      channels: B
      timeout: 1800 s
```

Expect: same behavior as the temp_control "Set && Wait" button; an open
temp_control window keeps showing live readings (the waiter mirrors into
temp.param). Also check the timeout path: unreachable setpoint + short
timeout → `temperature_band` FAIL → the step's on_fail policy fires.

## 6. tune.power_for_length — coarse stage (MOVES THE ROTARY VANE)

Most invasive single primitive; run only after 1–3 look right.
`checkpoint: true` (default in tune_up.yaml) asks before the chain runs.

```yaml
sample: hw_check
autonomy: supervised
steps:
  - tune.power_for_length:
      target_length: 32 ns
      amplitude: 95
      checkpoint: true
```

Expect: converges within `max_iter: 4` (judge `pi_length_target`),
from-above vane approach audible, reported (attenuation_db, pi_length)
describing the final vane state. Record: iterations, dB trail from the
log, final pi length.

## 7. Full canonical chain + runner policies

```bash
python -m atomize.epr_auto run protocols/tune_up.yaml        # supervised-ish (checkpointed)
```

Runs power_for_length → edfs(auto) → echo_window → auto_phase →
pi_calibration → field.set. While it runs, verify the Phase 3 machinery on
real hardware:

- `manifest.json` rewritten after every step; kill the terminal mid-run
  once and check the manifest still reads consistently (status stays the
  last written state, no truncation).
- `retries: 1` on pi_calibration: if a judge fails transiently, one retry.
- Rail fallback: provoke by calibrating with a too-low held amplitude so
  pi lands beyond the sweep (`rails: high`) → the runner should offer /
  auto-run the coarse re-tune (+ auto_phase re-run), recorded in the
  manifest as 'ok (rail fallback)' entries.
- `notify: telegram` (needs bot token in main_config.ini): checkpoint /
  finish / abort messages arrive.
- Repeat once with `autonomy: autonomous` end-to-end: no prompts,
  checkpoints auto-approved with notifications.

## 8. exp.t2 — first real experiment on the engine path (Phase 4, NEW)

Needs a phased detection chain: run after item 1 (or inside a tuned
protocol). The magnet stays wherever the session put it.

```yaml
sample: hw_check
autonomy: supervised
steps:
  - tune.auto_phase
  - exp.t2:
      tau_start: 300 ns
      tau_step: 12 ns
      points: 400
      scans: 4
      checkpoint: true
```

The sweep is the preset's own, re-anchored: every moving pulse shifts in
the preset's increment ratio, so P3 lands at `tau_start` and DETECTION at
its preset offset + 2×; the time axis is total evolution time. First bench
run: check the pulse geometry on the scope after re-anchoring, then compare
the acquisition with a manual phasing-tool run of the same preset.

Expect: `echo_snr` + `relaxation_fit` PASS (the latter gates on dAICc vs
the no-signal null ≥ 150, calibrated on the 2026-07-03 oTP campaign;
`adj_r2`/`rmse` are informational in the manifest), fitted `t2`/`beta`
matching a manual fit of the saved CSV (Data Treatment). If
`tune.pi_calibration` ran earlier in the protocol, the pulse amplitudes
are patched first (log line `apply_cal -> ...`; `apply_cal: none` opts
out, an explicit map like `{P2: pi2, P3: pi}` overrides the inference).
Record: t2, beta, dAICc score, data file.

## 9. exp.t1 — Log Time sweep (Phase 4, NEW; mind rep_rate)

```yaml
sample: hw_check
autonomy: supervised
steps:
  - tune.auto_phase
  - exp.t1:
      t_start: 500 ns
      t_end: 2 ms
      points: 300
      scans: 4
      rep_rate: 100        # the sweep must fit one repetition period
      checkpoint: true
```

`t_start`/`t_end` map to the preset's Log Start/End (log10 ns); the worker
grid-rounds and deduplicates the log axis, so **`npoints` in the result is
expected below `points`** — not a bug. The step pre-checks that the
sequence at `t_end` fits one repetition period and names the knob in the
error; physically the period must also exceed ~5× the expected T1 (the
preset's 480 Hz suits sub-ms T1 only). Fit: a − b·exp(−t/T1) with a
characteristic-time initial guess (validated against the oTP campaign
data). Bench cross-check: T1 vs the manual run at matched (T, field) —
the 2026-07-03 campaign values are the reference. Record: t1, npoints,
dAICc score, data file.

## 10. max_duration + the overnight chain

The scan_control policy's bench debut: give exp.t2 a `max_duration` about
half the projected run time and watch the log line (`max_duration ...:
projected N s over budget M s -> scan limit k of K`) followed by an early
finish with the data acquired so far saved and fitted (the scan count only
ever shrinks — 'SC<n>' ratchet). Then the full unattended chain:

```bash
python -m atomize.epr_auto run protocols/overnight_t2.yaml   # checkpointed
```

tune-up steps → exp.t2, with `manifest.json` carrying per-step
params/judges/fit results. This is the Phase 4 exit criterion.

## Other pending bench items (outside epr_auto)

- **Insys swComp hybrid wait + acq/parse speedups** — ported byte-identical
  to all repos, UNCOMMITTED, pending an ITC hardware re-test (DEER scan
  timing back to normal, data identical). See memory notes / commit after.
- **Live Edit round 8** — AWG-Start amp-gate tracking + N/B mid-preview
  reshape on the running preview (phasing tool, Live mode on).
- **ESEEM Avg** — final re-validation of the cumulative τ-averaging sweep
  incl. the just-pushed cut/copy/paste/reset Inc2 fix (`f5411fc`).
- **0.8 ns AWG fine step** — lab-bench validation plan in
  `docs/automation/AWG_FINE_STEP_PLAN.md` (echo position/shape vs the
  3.2 ns grid, opt-in preset line `AWG grid:  0.8`).
- **Benchmark `points_plot` suite** — `~/q/2026_07_06_insys_efficiency_auto/`
  run_benchmarks.py, lab run pending.
