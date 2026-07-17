# Hardware checklist — what can be run on the spectrometer TODAY

Everything below is implemented and dry-run-verified but has never touched
the real instrument (epr_auto Phases 2/3/5). Ordered so that each item
builds confidence for the next; items 1–3 are safe to interleave with
normal lab work. Date of writing: 2026-07-17.

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
```

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

## NOT yet hardware-runnable (do not try)

- `exp.t1` / `exp.t2` — Phase 4 stubs (they log and return canned values).
- `apply_cal` on a real acquisition — the patch itself runs (and is
  validated in the exp stubs' logs), but nothing acquires from the patched
  preset until Phase 4.
- `scan_control` / max_duration — the executor channel exists, no policy
  calls it yet (Phase 4).

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
