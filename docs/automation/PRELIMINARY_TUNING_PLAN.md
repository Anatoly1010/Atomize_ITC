# Preliminary tuning — implementation plan

Planned 2026-09-13 with the operator and reviewed against the code the same
day. The YAML steps are implemented and checked offline. The full sequence
ran on the spectrometer on 2026-09-18 (see the roadmap session entry).

## Purpose and sequence

Prepare usable AWG echo presets for the existing fine-tuning procedure:
receiver ringing check → optional resonator scan → field search →
echo maximization by RV, field, then pulse length if needed → preset export.
The optional resonator scan extends the original v1 scope exclusion.

Use existing protocol validation, session state, hardware locks, failure
handling, acquisition workers and test-mode conventions. Keep each stage
separately callable, with a supplied example protocol composing the sequence.
No new dependencies. Do not launch real hardware while implementing the plan.

**Every transmit pulse in this extension is an AWG SINE pulse at the tuning
preset's DETECTION intermediate frequency (IF).** The engine parses only
`.phase_awg` presets, and the AWG worker has no MW-channel RECT pulse: its
types are SINE, GAUSS, WURST, SECH/TANH and BLANK, plus DETECTION and LASER.
RECT support in the engine stays out of scope. Consequences: the ringing
preset is a `.phase_awg`, the resonator scan is rewritten around an AWG SINE
pulse, and every frequency in this plan is a synthesizer (LO) setting with
the observation frequency ν = ν_LO − ν_IF, exactly as `primitives/field.py`
already defines it (`_synth_mhz`, `_detection_if_mhz`).

### YAML integration

Preliminary tuning is part of the existing auto-EPR YAML approach, invoked
through the same `epr-auto run <protocol>.yaml` entry point. There is no
separate preliminary-script interface. Register new steps in `steps.py`;
use the existing parameter validation, checkpoints, manifest and session
calibration handoff. The same YAML can continue directly into fine tuning.

Proposed step names are `tune.ringing_check`, `tune.resonator`,
`tune.find_echo`, `tune.maximize_echo`, `tune.save_presets` and
`bridge.set` (rotary vane and synthesizer frequency, with settling), the
last one so a later fine-tuning run can restore the handoff settings. Omit
`tune.resonator` to skip the scan. Final parameter schemas and the
executable example YAML will be added with implementation.

**Hard stop mechanism.** `_run_primitive` converts `RuntimeError` and
`ValueError` into a `StepFailure`, which `retries`, `on_fail: skip` and a
foreach in `on_fail: continue` mode all swallow. The ringing abort therefore
(a) performs the 60 dB return inside the step and (b) raises a dedicated
exception type that is neither `StepFailure` nor a `RuntimeError` /
`ValueError` subclass; the runner already treats such errors as hard aborts
(`RunnerAbort(hard=True)`). No YAML policy may bypass the return to 60 dB or
continue acquisition.

### Coexistence with MW bridge control

Current behavior: `EPRSession.ensure_hardware_locks()` locks field and
temperature only. The bridge window (UDP) and the device driver (TCP) send
their own commands and keep independent `prev_dB` values. `bridge.param` is
status, not ownership. Opening the window runs initialization (frequency,
attenuators, bandwidth, RV homing); closing it makes a relative move toward
60 dB from its own possibly stale `prev_dB`. Both the window and
`Micran_X_band_MW_bridge_v2` write `Rotary Vane:` to `bridge.param`; the
driver's no-argument `mw_bridge_rotary_vane()` reads it and `_vane_db()`
uses that getter, but reading the file never updates the driver's `prev_dB`.

Implemented 2026-09-13, the field/temperature pattern and nothing more:

- `bridge_param.py`, a twin of `field_param.py`: `Frequency`, `Rotary Vane`,
  `Lock` and `Source` fields, atomic replace. The driver and window keep
  rewriting their two lines in place, which preserves the lock lines.
- `ensure_hardware_locks()` also seizes the bridge lock as `epr_auto` and
  releases it on the same `finally` / `atexit` path. Test mode stays a
  no-op and never touches the lock or status files.
- The bridge window polls the lock every 1 s (`refresh_lock_state`). While
  locked: banner "Bridge control locked (epr auto running)", all setters and
  Reset disabled, the published frequency and RV shown with widget signals
  blocked; `rot_vane`, `synt`, `cutoff_changed` (fires at construction),
  `initialize` and `initialize_at_exit` return early, so opening the window
  sends nothing and closing it makes no RV move. When the lock clears the
  window re-reads `Rotary Vane:` and `Frequency:` into `curr_dB` / `prev_dB`
  and the widgets with signals blocked, then re-enables manual commands.
  The window may stay open. Verified offscreen: locked construction, values
  published while locked, skipped exit move, resync on unlock.
- Ordering on the automation side: set the lock, wait at least one poll
  period (1 s), then home the vane with the limit switch (section 1).
  Because the home does not depend on `prev_dB`, a stale or in-flight GUI
  move cannot corrupt the automation's position.
- Crash: as for field/temperature. The lock file remains; the next
  `epr_auto` run reclaims its own source, the operator clears it otherwise.
  Every preliminary run homes first, so the RV position is authoritative
  regardless of what a crashed run left behind. Not in scope: atomic
  cross-process acquisition, moving/settled state publishing, crash-cleanup
  motion, changes to field/temperature code.
- Still to test on hardware: both startup orders, close during automation,
  normal handback and abort.

## 1. Receiver ringing check

- Preset `atomize/control_center/experiments/ringing_check.phase_awg`
  (replaces the RECT `ringing_check.phase`): P1 DETECTION at 0 ns, 640 ns,
  IF equal to the tuning preset's DETECTION IF; P2 SINE at 0 ns, 102.4 ns,
  same IF, amplitude coefficient 100; both `[+x,+x]`; 500 Hz; 10
  acquisitions; one scan; all increments zero; other slots inactive.
  Automation overrides the placeholder field with the nonresonant `field`
  parameter (default 100 G) and keeps the current frequency. Validate the `+x,+x` invariant on the built
  worker arguments (receiver phase list and SINE phase list) after
  expansion; a violation is a hard-stop implementation error before any
  hardware command, never a skippable step.
- Run the check **once per preliminary run**, with the longest pulse length
  the run may reach (the section 4 length-search upper bound, or the preset
  length when no search is configured), so one check covers every later
  setting. There is no ringing gate during RV optimization.
- Readout: the existing `acquire_trace` path with its forced demodulation
  is acceptable. `digitizer_demodulate` is a pure rotation by
  exp(−i2πf t), so |I + iQ| is unchanged by it. Threshold on the maximum of
  |I + iQ| in mV after protection ends; this bounds the per-channel maximum
  from above and is the conservative form. No integrals, no smoothing, no
  transient-width rejection, no skipping of the onset.
- Home to 60 dB in Limit mode first. The limit-switch homing speed is not
  calibrated (the 36 ms/step red/green calibration applies to relative
  moves only), and the bridge ignores a relative command that arrives while
  homing runs — measured 2026-09-18, when a 12 dB move sent 23 s after a
  home from 12 dB was lost and a trace was taken at 60 dB. So after a home
  from any position other than 60 dB wait the full 0→60 dB travel (70.6 s)
  plus 0.2 s margin. If the vane is recorded at 60 dB in `bridge.param`
  (the bridge window's last target, which it also records for its open/close
  homing), wait only what remains of the full travel since that record was
  written, normally nothing. Read that age before taking the bridge lock:
  the lock write itself rewrites `bridge.param` (found 2026-09-18, it made
  every first home wait the full travel). Join the Limit thread first; its legacy
  seven-second first-home timer alone is insufficient. Homing resets
  `prev_dB` and rewrites `bridge.param`.
- Then visit **60, 40, 20, 10, 5, 0 dB** through the existing `_vane_set`
  (from-above approach, calibrated settle wait). At every point: move →
  settle → acquire → check; only a pass permits the next dB. Do not queue
  moves ahead of acquisition. A missing or invalid trace is a failed check.
  0 dB may be commanded in Limit mode, which uses the limit switch like the
  60 dB home and makes the low end authoritative too. Approximate move
  times from the calibration curve: the full ladder ≈ 49 s, the return to
  60 dB ≈ 49 s.
- Compute the end of LNA_PROTECT from a throwaway test-mode `Insys_FPGA()`
  after the same setup calls the worker makes (prepared TTL pulse array),
  including `protect_awg_delay`, joined protection intervals and the
  detection/ADC time origin. Resolve the origin during hardware validation.
  Do not hard-code the ≈150 ns transient seen on September 11 or the echo
  finder's 200 ns exclusion.
- Above 100 mV: stop the sequence, command 60 dB in Limit mode, wait,
  record the offending trace and attenuation, and raise the hard-abort
  exception. An acquisition error or operator abort attempts the same
  return; report a failed return explicitly rather than claiming the RV is
  safe.
- Save the traces, calculated protection endpoints and measured maxima.

The resonator scan below measures a separate reflected-diode signal; its
deliberate ringing is not the receiver's 100 mV stop criterion.

## 2. Optional resonator frequency selection

Implemented 2026-09-13 in `tune_preset.py`: a **Pulse Mode** combo (RECT /
AWG) and an **AWG Frequency** box (1–280 MHz, default 50, enabled in AWG
mode). RECT keeps the untouched `exp_on` / `exp_test` workers. AWG runs
`Worker.scan_awg` (wrapped by `exp_on_awg` / `exp_test_awg`): the same
setup calls as the AWG phasing worker (TRIGGER_AWG gate plus a CH0 SINE
pulse at the IF, `awg_next_phase` + `pulser_update` per phase), the same
Keysight diode acquisition (CH1 negated, CH2 trigger, averages, record
length) and synthesizer stepping, the previous synthesizer value restored
at the end. `scan_awg` returns the `[frequency, time]` array so the runner
step can call it directly; the pipe protocol is only in the wrappers. The
`.tn` file gains optional trailing `Pulse Mode:` and `AWG Frequency:`
lines; old files load as RECT. The CSV header records the mode, IF and
pulse length. Verified in test mode without hardware (both modes) and by a
`.tn` round-trip offscreen. The runner step still has to set RV = 10 dB via
`_vane_set` and wait for RV and synthesizer settling before calling it.

**Frequency bookkeeping.** The scan axis is the synthesizer setting; the
observation frequency at each point is ν_LO − ν_IF. Select on the
synthesizer axis and apply the selected value directly, provided the scan IF
equals the tuning preset's DETECTION IF (`_detection_if_mhz`). A mismatch
is rejected. Record synthesizer, IF and observation frequency.
There is no separate "AWG offset" parameter.

Operator-provided `.tn` reference:
`/home/anatoly/Documents/00_Exp_data/2026_06_23_sifter/01_resonator_tune.tn`:
102.4 ns pulse, 500 Hz, 9200–9600 MHz at 1 MHz steps, 10 averages, one
scan. Retain these settings as defaults. This file is the RECT scan format;
it holds no AWG or IF information.

### Data evidence

Reference CSV:
`/home/anatoly/Documents/00_Exp_data/2026_06_24_sifter/01_resonator_tune.csv`,
array `[time, frequency]`, shape `(640, 401)`, 0.3125 ns sample spacing,
9200–9600 MHz at 1 MHz steps, 102.4 ns RECT pulse. Times are relative to the
first saved sample. The saved voltage is positive; the worker negates CH1.

The during-pulse section contains several dips. The trailing-edge ringing
gives the dominant feature: the largest sample is 71.4196 mV at 153.75 ns and
9441 MHz. Median-subtracting before 40 ns, averaging 153–155 ns and smoothing
across five frequency points gives 9439 MHz; the 152–154 and 154–156 ns
windows give 9438 and 9439 MHz; 156–158 ns gives 9433 MHz. These are
exploratory calculations, not validated windows. Because this scan was RECT,
≈9440 MHz is an observation frequency; an AWG SINE scan of the same resonator
peaks at synthesizer ≈ 9440 MHz + IF.

### Selection algorithm

1. Validate array dimensions, finite values, frequency ordering and time
   sampling. Retain the saved polarity and record voltage units explicitly.
2. Locate the pulse and its trailing-edge region from the ensemble of time
   traces, constrained by the known pulse duration. Account for scope
   trigger offset. Allow an explicit time-region override.
3. Estimate each frequency's baseline from the pre-pulse samples. Determine
   ringing polarity from the baseline-subtracted trailing edge so either
   diode polarity works.
4. Within the trailing-edge region, locate the dominant ringing feature and
   select one short, common time window around its early maximum. Average
   this window at every frequency to produce a signed frequency section. Do
   not maximize over time independently at each frequency.
5. Use modest frequency smoothing only to locate a candidate peak. Retain
   and plot the original section. The operator specifies **5 MHz as typical
   selection precision**; report the center to about 5 MHz and apply it at
   the synthesizer's resolution. Scan points are not restricted to a 5 MHz
   grid.
6. Check the peak against baseline noise, competing peaks, scan boundaries,
   clipping and nearby early-time windows. Use 5 MHz as the default allowed
   variation between nearby window estimates. Other acceptance limits and
   the window width are configurable and must be validated on measured
   scans.
7. If the peak is weak, ambiguous, clipped, at the boundary, or unstable
   across nearby windows, stop with the map and sections for operator
   review. Do not silently expand the supplied frequency range.
8. Apply the selected synthesizer setting per the bookkeeping above and
   validate it against the synthesizer limits before changing hardware.

Record the synthesizer setting, IF, observation frequency, chosen time
window, original and processed sections, and quality checks. After a
frequency change call the session's invalidation for phase, window and
pulse calibration. When this stage is skipped, retain the current frequency
and record it for the later presets.

## 3. Find an echo

- Set a supplied RV value in 5–10 dB via `_vane_set` and use a separate
  supplied tuning preset with its default AWG pulses and normal phase
  cycling. YAML selects this preset; the ringing preset never replaces it.
- Order, so no prior integration window is needed:
  1. Field sweep over the specified center and span with explicit point
     count and acquisition effort, reusing the field worker and echo/noise
     judges, integrating the **full detection window on magnitude** (the
     receiver transient cancels under the normal cycle).
  2. At the best field acquire a time trace, verify a delayed, resolved
     echo (not a receiver transient), and establish its integration window.
  3. The narrow re-sweep with that window is section 4.2.
- If no echo passes, stop; no silent wider-field or higher-power search.
  Return the RV to 60 dB on this exit.
- Keep the best validated field and echo window for maximization.

## 4. Maximize the echo

Revised 2026-09-18 at the bench (operator decision; the original RV and
pulse-length searches were run once on hardware and then replaced). The
rotary vane attenuation is fixed by the operator per sample, the pulse
lengths are fixed by the preset, and only the amplitudes move:

1. **Amplitude:** with the echo window from section 3, scan the pi/2
   amplitude a over a bounded range (default 5–50 % of full scale) with the
   pi pulse at 2a, coarse grid then a finer grid around the best point.
   The operator gives the target pi length (`pulse_length`, on the echo
   search and the scan; default the preset's shortest MW pulse) and every
   echo pulse takes it, so pi differs from pi/2 only in amplitude (a first
   bench run with 32 and 64 ns pulses at a and 2a gave pi four times the
   pi/2 area and a wrong optimum). For
   a Hahn echo the signal follows sin³ of the flip angle, so the maximum is
   the pi/2 point itself and a, 2a are directly usable pulses. A maximum on
   the upper edge (pi would exceed 100 %) or the lower edge aborts with
   "reduce" / "increase attenuation"; the operator then changes the RV
   parameter rather than the protocol searching power on its own.
2. **Field:** a narrower sweep around the best echo at the chosen amplitudes.
3. Restore the best combination and confirm the echo there; if confirmation
   fails, abort with diagnostics.

Pulse roles come from an explicit `pulse_map` or the preset's own two
amplitude/length levels. Hold acquisition effort and the echo measurement
method constant across comparisons; reject noise-only improvements. The RV
may not go below the attenuation the section 1 ladder covered (0 dB).

## 5. Export for fine tuning

Save new preset copies in the run directory, preserving the input presets.
Export the chosen field, pulse settings, detection timing and integration
window into the applicable preset tables. Record synthesizer frequency, IF,
RV attenuation and other settings not represented by `.phase_awg` in the run
manifest and in a companion handoff protocol that restores them through
`bridge.set` before the fine-tuning chain.

Prepare the echo, amplitude-calibration and field-sweep presets needed by
the previously tested fine-tuning chain. Keep selective calibration
detection-pulse roles intact; preliminary echo maximization is not a
measurement of pi or pi/2. Apply the existing calibration-transfer rules
only after the fine calibration has actually run.

Scale the calibration preset to the tuned echo (added 2026-09-18 after the
shipped `ampl_4s` amplitudes, meant for several times more B1, gave no echo
and a high amplitude rail at 12 dB): the largest tuned pulse area
(length × amplitude × envelope area) is taken as pi; the swept pulse becomes
a SINE long enough to pass pi at about 65 % of full scale, capped at the
ringing-tested length; the detection pair takes the tuned echo pulses
themselves (lower preset amplitude ← smaller tuned area), keeping the
pair's timing and phase cycle. A sweep that cannot reach pi is logged as a
warning and left to the fine-tuning rail judges.

Revised the same day: the fine calibration tunes a separate Rabi pulse at
its own target, `calibration_length` (default the preliminary length),
detected with the preliminary pair. The handoff exports four presets:
`echo` (preliminary pulses) for the first echo-window/auto-phase pass,
`calibration` (swept pulse at the fine target, preliminary detection
pair), and `field` plus `echo_cal` with every pulse at the fine target and
placeholder amplitudes; the handoff's `tune.apply_calibration` steps rewrite
those two files with the measured pi/2 and pi amplitudes right after the
first calibration, so the EDFS, the second pass and the closing calibration
run on calibrated pulses. The handoff (`fine_tuning.yaml` and its four
presets) is published to `publish_dir` (default `tuned` beside the
preliminary protocol; the run directory keeps an archive copy) and closes
with one more `tune.apply_calibration` that writes the final amplitudes,
zero-order phase, echo window and field into `tuned/echo_cal.phase_awg`,
so a separate experiment protocol run later (`exp.t2` with
`window: preset`, `apply_cal: none`) needs nothing from the tuning
session: the day is preliminary → fine → experiment, three runs from one
folder. Fine-tuning runs land in `runs/<date>_fine` beside the folder's
other runs.

The handoff's field sweep covers the `tune.find_echo` span (or `field_span`
when given) in `field_points` (default 200) around the tuned field, not the 10 G refinement
sweep of section 4 (2026-09-18: that sweep clipped the coal line on both
sides and the EDFS pick was meaningless).

`bridge.set` in the handoff no longer homes the vane unless a crashed run
left the bridge lock behind: it waits out any recorded move still in
flight, adopts the recorded position as the driver's origin and moves
relative to it (operator decision 2026-09-18, replacing the 12→60→12 dB
travel at every fine-tuning start).

Reload exported presets through the existing parser and pre-flight their
worker arguments. The handoff protocol then invokes the existing
echo-window, auto-phase, pi-calibration and field-refinement sequence in
the tested order.

## Implementation and verification checklist

- [x] Read the existing automation, RV and resonator-scan paths.
- [x] Inspect and plot the real resonator scan and time/frequency sections.
- [x] Specify the full sequence and frequency-selection approach.
- [x] Review against the code (2026-09-13): AWG SINE everywhere, magnitude
      threshold, hard-abort exception, `_vane_set` reuse, minimal bridge
      lock, single ringing ladder to 0 dB, `bridge.set` step.
- [x] Create `ringing_check.phase_awg`; retire the RECT `.phase` twin.
- [x] Implement the ringing step: Limit home, ladder, magnitude threshold,
      pulse-derived protection timing, in-step 60 dB return, hard-abort
      exception recognized by the runner.
- [x] `bridge_param.py`, session lock extension, bridge-window poll timer,
      locked init / close / Off paths, resync on unlock (offscreen-tested).
- [x] AWG SINE mode in `tune_preset.py` with a RECT/AWG combo, IF box and a
      runner-callable `Worker.scan_awg` (test-mode verified).
- [x] Implement and offline-validate resonator selection on the reference CSV.
- [x] `tune.resonator` step: RV = 10 dB, settling, call `scan_awg`, run the
      selection, apply the synthesizer value.
- [x] Implement echo search (sweep → trace → window), bounded maximization,
      preset export, `bridge.set` and the handoff protocol.
- [x] Register step parameters and provide a complete example protocol.
- [x] Exercise test mode without hardware, including failure and abort paths.
- [x] Verify `+x,+x` on the built worker arguments, and that no ringing
      gate runs during the amplitude scan.
- [x] Check known-center synthetic scans of both signs, noise, competing
      peaks, edge peaks and clipping; report the real scan's window
      sensitivity.
- [x] Re-run GUI/engine equivalence if worker signatures, preset handling or
      argument packing change, as required by CLAUDE.md.
- [x] Use the calibrated GUI RV movement duration and September 11 defense-transient timing.
- [x] Supervised end-to-end run on hardware (2026-09-18): bridge coexistence,
      frequency selection, echo search and maximization, handoff export.
- [x] Exported fine-tuning protocol on hardware (2026-09-18, coal at 4 dB:
      echo window, auto-phase, pi calibration, 120 G EDFS, repeat).
- [ ] The final three-run day (`2026_09_18_coal_auto`: preliminary →
      `tuned/fine_tuning.yaml` with `tune.apply_calibration` → `t2.yaml`).
- [ ] Ringing hard-stop/return (never triggered on this resonator).

## Implementation notes and verification (2026-09-13)

The executable [protocol](../../protocols/preliminary_tuning.yaml) runs all five stages;
omit `tune.resonator` to retain the current synthesizer frequency. Its sample,
frequency bounds, field center and field span are examples to set for the
sample. `bridge.set` is also available independently for the exported handoff.
Neither `tune.ringing_check` nor `tune.resonator` accepts a `preset` parameter.
Both use built-in sequences with `if_mhz` defaulting to 50 MHz; these values
must match each other and the later echo preset's DETECTION IF. The internal
ringing `.phase_awg` retains `+x,+x` on both DETECTION and SINE. Pulse length
and IF are applied before validating its expanded additive cycle. Its DAC
amplitudes are fixed at 260 mV, matching the resonator worker; later echo
presets are checked against that tested amplitude and pulse-length limit.

`tune.find_echo.frequency_shift_mhz` defaults to 0 (integer MHz). The bridge
is set to the resonator-selected synthesizer frequency plus this signed
shift before the field sweep; positive means a higher observation frequency,
since the AWG IF stays unchanged. Without a resonator scan, the reference is
the bridge frequency at the first echo search, retained to avoid cumulative
shifts on repeated searches. Optimization keeps this setting and the exported
fine-tuning YAML restores it. For example, `frequency_shift_mhz: -50` tunes
the echo 50 MHz below the resonator center for a two-frequency experiment.

The field search uses `Worker.exp_field`'s saved raw two-channel arrays,
integrating `hypot(I,Q)` over time before selecting the field. This avoids
cancellation within a broad integration window and keeps the existing
single-worker field sweep. Subsequent trace confirmation uses `acquire_trace`.
Zero sweep increments apply only to preliminary measurements; exported echo
presets retain the source's increments for later experiments.

The amplitude scan keeps the preset lengths; `amplitude_range`, `coarse_step`
and `fine_step` are protocol parameters and `attenuation_db` defaults to the
`tune.find_echo` setting. The exported calibration preset takes the tuned
pulses as its detection pair and the tuned pi pulse's shape and length as
the swept pulse, so pi is expected at the tuned pi amplitude; aim the RV so
that 2a lands near 60 % of full scale.

The resonator scan runs in a child process, pre-flights the same AWG worker,
and serves its existing save/stop pipe messages. AWG frequency changes now
settle before diode acquisition; its cleanup closes the pulser and restores
the prior synthesizer frequency even on failure. The parent applies the
accepted center after the child has finished.

The real June 24 scan selects **9439 MHz**, reported as **9440 MHz** at 5 MHz
precision. Its common window is 152.8125–154.6875 ns; this and two neighboring
later early-ringing windows give 9439, 9439 and 9436 MHz. Later windows are
used for the stability check so an abrupt synthetic onset cannot accidentally
compare against the before-ringing signal. The comparison windows are shifted
by 1 ns and 2 ns regardless of the window width (2026-09-18: with a 4 ns
window, shifts scaled to the width walked off the 2 ns ring-down spike and
failed the check on a good scan). Original and processed sections,
window and reasons for rejection are saved alongside the diode CSV.

Commands used without hardware:

```bash
python3 -m atomize.epr_auto validate protocols/preliminary_tuning.yaml
QT_QPA_PLATFORM=offscreen python3 -m atomize.epr_auto run protocols/preliminary_tuning.yaml --test
QT_QPA_PLATFORM=offscreen python3 atomize/script_examples/epr_auto/preliminary_checks.py test
python3 atomize/script_examples/epr_auto/resonator_stop_checks.py test
QT_QPA_PLATFORM=offscreen python3 ~/epr_auto_dev/gui_vs_engine.py
python3 -m atomize.epr_auto.preset_hash
```

The example dry-run completes 5/5. Offline checks cover both diode signs,
weak/competing/edge/clipped peaks, nonfinite data, protection timing changes
with pulse length, every-rung ordering, threshold abort before the next RV
move, hard-abort precedence over retries/skip, the amplitude scan with its
range-edge aborts, calibration export, preset reload and handoff YAML validation. GUI/engine
equivalence reports ALL PASS. The prepared protection endpoint for the
102.4 ns test pulse has a TTL endpoint of 134.4 ns relative to DETECTION (spectrometer pulser delays).
The September 11 standard Hahn preset has a calculated endpoint of −211.2 ns
and its measured defense transient occupies the recorded 147.6–155.2 ns
window (peak approximately 150 ns). Transfer this measured reference by
the calculated difference in protection timing. Start the ringing check at
the window's early edge: 134.4 − (−211.2) + 147.6 = 493.2 ns, so the initial
amplitude is included. No additional onset blanking is applied. The raw
September CSV is not present at the session-log path on this machine; this
calibration uses the recorded window and the operator-confirmed standard
Hahn timing, rather than claiming a fresh fit to that trace.

No live hardware was operated during implementation.

Independent agent review (2026-09-13) found and corrected five issues:

- Resonator precondition failures and repeated ringing checks now home RV before aborting.
- The initial review added runner-level homing on cancellation; the revised GUI plan supersedes this: only interruption inside the ringing ladder homes RV. Stop at a checkpoint or in another step leaves RV unchanged while workers drain and locks are released.
- A manual RV command waiting for a previous move rechecks the automation lock before sending.
- Resonator stop exits the remaining scans and checks pending commands before starting another acquisition.
- Pulse onset uses a sustained rise above baseline noise so strong, broad trailing ringing cannot replace the leading edge.

Offline regressions cover these paths; the resonator still selects 9439 MHz on the real June 24 CSV.
The operator resolved the two timing questions using existing calibration:
RV movement follows the calibrated GUI red/green duration, and protection
is aligned to the September 11 defense transient as described above.
