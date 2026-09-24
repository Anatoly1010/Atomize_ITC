# EPR automation — roadmap

Updated 2026-09-19. Keep this file focused on current status, open work and dated evidence. Current preliminary-tuning decisions live in [PRELIMINARY_TUNING_PLAN.md](PRELIMINARY_TUNING_PLAN.md); bench acceptance checks live in [HARDWARE_CHECKLIST.md](HARDWARE_CHECKLIST.md). General design and the GUI/engine contract remain in [ARCHITECTURE.md](ARCHITECTURE.md).

The hardware work comprises **two sessions**: **11 September — fine tuning only**; **18 September — implementation and trials of the complete workflow**. The final independent preliminary and fine-tuning runs worked without issues. The logic was improved on 18 September, and the final combined preliminary → fine-tuning → T2 run passed that evening.

RV means rotary-vane attenuation of microwave excitation. VA means receiver video attenuation, set through Video Attenuation 1 (VA1) and Video Attenuation 2 (VA2) before the ADC.

## Implemented

- YAML validation, test mode, supervised/checkpointed/autonomous runs, retries and failure policies, manifests, protocol copies, notifications, and field/temperature series with `foreach`.
- Engine reuse of `awg_phasing_insys.Worker`, preset/snapshot equivalence, trace capture, phase/window/pulse calibration, EDFS, temperature control, T1/T2 acquisitions, and downward-only scan limits from duration/SNR.
- Live repetition-rate selection: one open card, fixed field and τ, ordinary nonempty `digitizer_get_curve(live_mode=1)` results. Three consecutive returned curves within 5% qualify by default; old or mixed-rate packet content is accepted as returned, without packet tags or epoch filtering. The rate then changes without a pause or reopening. The tuning grid has a 10 Hz minimum and default; during tuning the Worker pins a 512 KB ADC buffer regardless of ADC window or rate, then restores the prior buffer setting after completion, Stop or failure. No live-rate-specific `Insys_FPGA` changes are required. Available fine pulse calibration is applied. `max_wait` bounds each rate and partial observations survive failure or Stop. The [live-rate example](../../protocols/rep_rate_live.yaml) remains an explicit dry-run example; hardware validation remains open.
- Optional `adjust_range: true` on T1/T2: assess the complete accumulated curve during the first one to three scans before SNR stopping. A confirmed plateau keeps the accumulation; a clearly unfinished tail permits one early extension after timing and budget checks. An uncertain early decision resumes ordinary SNR control without a late repeat. The accepted final curve carries a 55% T2-baseline or 47-point T1-plateau range recommendation to the next temperature in the same run. Warming can shorten the next span by at most 25%; cooling cannot shorten it. Carried/repaired T1 ranges use a fresh full-grid timing-compatible rate. The [T1/T2 series](../../protocols/temperature_series_t1t2.yaml), [T2-only series](../../protocols/temperature_series_t2.yaml) and [single T2](../../protocols/t2_auto_range.yaml) examples combine SNR and range control; [range notes](RELAXATION_RANGE.md) describe the behavior. Live validation remains open.
- Preliminary ringing gate, optional AWG resonator scan, echo search, fixed-RV amplitude optimization and four-preset fine-tuning export. The final design sets both echo pulses to a common length; the Rabi pulse may use its own `calibration_length`. Amplitude optimization now uses one existing 2D worker per coarse/fine stage, with paired `a` / `2a` values, full traces and reuse of measured coarse points. See the preliminary plan for exact behavior.
- Strong-sample receiver control: live RV approach through 60/40/20/15/10/5/0 dB, one 200 mV threshold, optional `adjust_video`, calculated VA1/VA2 changes, and ready-buffer field/amplitude checks that can report an earlier completed point. A VA change starts fresh comparisons. Final video check and VA handoff are implemented, with preliminary repetition-rate selection capped at 10 kHz, including `rep_rate: auto` from an earlier accepted `tune.rep_rate`. Hardware commissioning remains on the checklist.
- Main-window protocol launcher with dry-run dialogs, Stop/Force stop, worker drain, duplicate-run and exit guards. Operator GUI dry runs and Stop passed; live cleanup and Windows launcher execution remain unverified. Plan: [GUI_PROTOCOL_LAUNCHER_PLAN.md](GUI_PROTOCOL_LAUNCHER_PLAN.md). Regression scripts: `atomize/script_examples/epr_auto/gui_launcher_checks.py`, `gui_runner_checks.py` and `worker_stop_checks.py`.
- Connected plot dots become grey after 10 s idle; the change is now carried to Atomize, NIOCH, NIOCH_Q and Cryomech. It is no longer backlog.
- The public reference is maintained in `atomize_docs`. The 2026-09-19 update covers live-rate tuning and adaptive relaxation ranges, with a regenerated step reference and a passing strict MkDocs build.

## Hardware validation status

The completed three-run workflow is recorded in `~/experimental_data/Melnikov/2026_09_18_coal_auto/`:

```text
preliminary.yaml → tuned/fine_tuning.yaml → t2.yaml
```

- [x] All three ran with the final equal-length preliminary pair, separate Rabi `calibration_length`, both pre-EDFS `tune.apply_calibration` calls, and the closing write to `tuned/echo_cal.phase_awg`.
- [x] The separate experiment consumed that file with `window: preset` and `apply_cal: none`, while retaining/restoring the tuned RV and synthesizer settings.
- [x] Confirmed `tuned/` publication beside the protocol, archive under the configured preliminary run directory, fine data under `runs/<date>_fine`, and repeat-run preservation.

Remaining hardware checks:

- [ ] Verify the new staged amplitude search against matched single-trace measurements: paired amplitudes, repeated scans, full-trace scores, Stop/partial saves and elapsed time. The approximately 32 s initialization saving for an 18-trial search is an estimate, not a bench result.
- [ ] Commission live receiver monitoring during RV motion, 200 mV corrections, optional VA control, ready-buffer sweep guards and final video checks after calibration.
- [ ] Verify final bridge record-age/no-home behavior and remaining lifecycle cases: alternate startup order, close during automation, handback and abort. Normal operation with the bridge window opened first has been observed.
- [ ] Exercise the ringing hard stop and settled 60 dB return, including reported return failures. No recorded trace exceeded 100 mV; this is not yet hardware-validated.
- [ ] Verify live launcher Stop/Force stop, saved partial data, worker/FPGA cleanup, lock release and relaunch. Keep Windows launcher validation separate from the Windows CLI dry run.
- [ ] Measure the cause of resonator selection jitter if it continues: FPGA trigger/AWG clock crossing versus scope trigger. `window: 4 ns` is recommended; 2 ns remains the code default.
- [ ] Compare live rate convergence with manual tuning, including the rate transition, ordinary curve handling, timeout/Stop and one FPGA initialization.
- [ ] Validate early T1/T2 range decisions on a temperature series: retain a sufficient first range through target SNR, extend an unfinished range only once, and carry accepted range recommendations to the next temperature.
- [ ] Complete the remaining T1, temperature, duration/SNR, EDFS early-stop, field-series and autonomous-run checks listed in the hardware checklist. Recheck the `dAICc/n >= 0.375` relaxation gate on a new real T1/T2 series.

- [ ] AWG 0.8 ns grid: echo-level checks passed on 2026-09-24. These covered the 0.8 ns τ sweep, residual flatness at decimation 1 and 2, the one-tick gate change, and log, amplitude and preview paths. Still open: scope check of the TTL/DAC residual positions 0–3, Field sweep, ESEEM Avg, decimation 4, and live edit of a sub-tick start. See [AWG_FINE_STEP_PLAN.md](AWG_FINE_STEP_PLAN.md).

`tune.power_for_length` remains implemented but is not part of the intended daily flow. Its hardware commissioning and length-rail/coarse-fallback checks are deferred unless that path is needed again.

## Implementation backlog

- [ ] Protocol parameters for resonator-correction overrides and measured-H loading; the engine already carries the correction fields.
- [ ] RECT-channel calibration and automation.
- [ ] Optional detection `tau` for `exp.t1`, with an explicit rule for invalidating/recomputing the echo window or using `window: preset`.
- [ ] Full-2D acquisitions: keep adaptive decisions on worker-side per-column integrals sent as ScanData; save matrices separately.
- [ ] Automatic three-pulse ESEEM with varied temperature and tau, including tau averaging; broader ESEEM/DEER experiment steps. ESEEM Avg ScanData is monitor-only while its scan count is fixed.
- [ ] Assistant support for protocol authoring and checkpoints.
- [ ] Active resonator tuning after assessing an actuation path; distinct from the implemented frequency-selection scan.
- [ ] Port the automation layer to other variants once stable; the shared grey-dot update is already distributed.

Deferred operator decisions from the July review: EDFS magnet parking after a failed scan, whether the 1.15 SNR projection margin needs further correction on hardware, and a warning when sensitivity-mode repetition rate is used by quantitative T1/T2. Read the original evidence before choosing changes. `_FLAT_SPREAD` rework and preset-hash caching were left as optional work, not accepted requirements.

Retired review proposals should not reappear as open tasks: callback/flag pairing was replaced by policy-gated ScanData; callback cleanup was fixed; OVER_TICKS persistence was replaced by the projection margin; the extra `k >= 2` guard and substitution-context change were rejected.

## Hardware session record

### 2026-09-11 — fine tuning

Coal at room temperature on the ITC spectrometer. Protocols, presets and results are under `~/experimental_data/Melnikov/epr_auto_coal/`. This session exercised fine tuning, not preliminary preparation or the later three-run workflow. Recorded T2 measurements were supporting checks of the tuned acquisition path.

- Auto-phase round trip: zero order 37.0° then residual 5.75°, with a real-positive echo; typical run-to-run scatter 3–5°.
- Accumulating echo preview: no stall/blank frame; FWHM 56 ns, window 244–358 ns, SNR 11. The echo sits about 300 ns after DETECTION.
- Amplitude calibration: high rail at 12 dB; at 6 dB, π 76 %, π/2 40 %, ratio 1.90, SNR 8.7.
- Explicit EDFS: line maximum 3445.73 G, FWHM 14 G, peak/noise about 110. The −7.5 G offset from the 9680 MHz prediction became this setup's default; remeasure for another magnet/sample.
- T2 check: 205 ns, β 0.95, dAICc/point 2.94, adjusted R² 0.95. The nine-step fine-tuning/check protocol later completed 9/9, with calibrated EDFS at 3444.72 G, repeated π values 78.5/75.2 %, and an 80-point T2 check at 123 ns, β 0.81. Different tail coverage affected the stretched-exponential fit; these are not identical acquisition comparisons.

The defense transient could out-peak the echo; `search_from: 200 ns` and `min_width: 20 ns` addressed it. Subsequent September work addressed the separate-process vane origin and the shipped calibration presets' unsuitable B1 assumptions through recorded-position adoption and sample-specific export.

### 2026-09-18 — complete-workflow implementation and trials

Work expanded to preliminary preparation and its fine-tuning handoff, with logic improvements during the session. The operator confirms the final independent preliminary and fine-tuning runs worked without issues; the complete preliminary → fine-tuning → T2 run passed in the evening (below). The recorded measurements below retain their original pulse settings for context:

- `preliminary_coal.yaml` completed 5/5 on run 3 (`runs/2026-09-18_preliminary_run3` in the coal bench directory). Ringing ladder at 100 G, synthesizer 9696 MHz / observation 9646 MHz, resonator section SNR 220 and centers within 1 MHz. The earlier RV-search design chose about 12 dB and 3437 G, with 32/64 ns pulses and window 241.6–400.8 ns.
- Ringing peaks 17–68 mV at 494–496 ns were power-independent protection transients; no >100 mV stop occurred. Bridge coexistence worked with the window already open.
- Fine-tuning trials exposed a dropped relative move during Limit homing and a calibration preset whose detection pair assumed more B1. Fixes included full Limit travel timing, recorded-position adoption, reading record age before lock writes, and scaling export to the preliminary pair.
- Run 5 and its intermediate handoff worked at 4 dB, 9696 MHz and 3436.5 G. The 32/64 ns pair used 35/70 % amplitudes. Fine calibration gave π 55.8 % / π/2 28.0 %, ratio 1.99; EDFS over 3376–3496 G found 3435.6 G with FWHM 15.7 G; repeat π was 55.2 %, ratio 1.98.
- The design was then corrected to equal-length echo pulses at `a/2a`, with a separate Rabi target, four exported presets and explicit calibration writes. The final combined preliminary → fine-tuning → T2 run passed that evening (below). The earlier 32/64 ns pair at `a/2a` had a fourfold area ratio; its numerical results describe that earlier setting, not the corrected equal-length pair.

**Evening: the complete chain passed.** `~/experimental_data/Melnikov/2026_09_18_coal_auto/` holds `preliminary.yaml` → `tuned/fine_tuning.yaml` → `t2.yaml`, run in that order with the final logic (`runs/2026-09-18_preliminary_run3`, `runs/2026-09-18_fine_run4`, `runs/2026-09-18_t2`, 17:37–17:53):

- Preliminary: ladder 45–76 mV at 100 G; resonator 9692 MHz (4 ns window, SNR ~155, shifted windows within 2 MHz); echo at 3432 G, 4 dB, 64 ns pair; amplitude maximum 20/40 %, field refinement 3430.5 G; `calibration_length: 38.4 ns` exported.
- Fine: Rabi 38.4 ns gave π 90.0 % then 89.4 % (ratio 2.05/2.06), EDFS 3435.6 G with FWHM 18 G and 1–3 % edges over 3372.5–3492.5 G; final `echo_cal.phase_awg` carries 38.4 ns pulses at 43.4/89.4 %, zero order 54°, window 227.6–338 ns, field 3435.63 G.
- T2 on that preset (`window: preset`, `apply_cal: none`, 200 points, 2 scans, 44 s): stretched exponential T2 = 208 ns, β 0.99, echo SNR 19, ΔAICc/n 4.5 on the absolute 2τ origin. No manual comparison run was made.

Fixes during the evening: the resonator selector searched the trailing-edge peak from 12 ns before the pulse end and picked the reflected-pulse plateau when it exceeded the ringing (rejected an acceptable scan as "window touches the search boundary"); it now searches after the nominal pulse end. `tune.ringing_check` gained `done: true` for same-day reruns and its `max_length` became `pulse_length`: the ladder no longer limits later pulse lengths, only the IF and DAC amplitudes carry forward. A hand edit of `tuned/calibration.phase_awg` only changes the Rabi pulse (fine runs 1–3 transferred a 38.4 ns calibration onto 64 ns pairs by the length ratio); the experiment length must go through `calibration_length` and a preliminary rerun.

Next, agreed the same evening and subsequently implemented as described in the preliminary plan: a strong-sample RV approach for `tune.find_echo` with a 200 mV working threshold and VA1/VA2 adjustment, a `tune.video_attenuation` step before experiments, and an operator `rep_rate` (10 kHz cap) on the preliminary steps with `auto` from `tune.rep_rate` as a follow-on.

The 10 G refinement span clipped the EDFS line, so the handoff now uses the original search span. Narrow 2 ns resonator windows showed 4–9 % single-frequency dropouts; the recommended window is 4 ns with stability comparisons shifted by 1 ns and 2 ns. Worker stdout now goes to the run's `worker_stdout.log`.

## Offline evidence and maintenance

- 2026-09-24 phase correction in both Insys phasing tools. Since cdc8147, First/Second Order are FFT-view values (deg/MHz, deg/MHz²), but experiments still applied them through `digitizer_demodulate` as time-domain rad/s and rad/s². A 9.2 deg/MHz setting left 2 % of the integral. Separately, FFT mode rotated by +Zero Order while the time trace and experiments use −Zero Order: on hardware the Auto phase value 348.4° left the FFT 20.9° off. Now the FFT uses the time-domain sign: Auto phase value plus First Order −9.2 gives +0.6° at the peak. Experiments and `digitizer_insys.param` use only Zero Order; on hardware, integrals with First Order 9.2 or Second Order 0.5 match 0 within noise. First Order range is ±5400 deg/MHz (15 µs windows); Points to Drop goes up to 37500 and gains a ' pts' suffix. No saved preset had non-zero first/second orders.
- 2026-09-24 amplitude and field sweeps. The GUI amplitude sweep selects pulses by a non-zero start increment but also advanced them by it every point. On hardware, P3 marked with 3.2 ns moved the echo 345 → 432 ns and out of the window. Pulses now keep their position; the signal grows 9 → 3000, matching the table-driven sweep (19 → 3067). The field sweep already refused AWG start increments in its test pass; the AWG tool now refuses a P1 or LASER start increment as well, like the RECT tool. Test mode passes. The GUI amplitude sweep no longer sets an amplitude after the last point. Its test pass used to reject a sweep ending exactly at 100 % (it asked for 105 %). The end-of-scan reset already restores the first amplitude; hardware, 2 scans 5–100 %: matches the single-scan curve. Sibling port: `docs/SIBLING_HANDOFF_2026-09-24_sweeps.md`.
- 2026-09-24 accumulating preview: the Accumulation-mode readout in both Insys phasing tools no longer blocks at the last phase. The board had repeated that phase for ~300 ms per cycle while a 1 MB block filled (hardware, `accum_mode.phase_awg`: count_nip `[41 40 40 2444]`, 40 cycles in ~12 s). Now counts are equal (`[594 592 592 594]`, 600 cycles in 17.6 s). `acquire_trace` counts complete cycles from `min(count_nip)`; `n_sweeps` is a minimum. Hardware: 300 sweeps → `[321 320 320 321]` in 12.1 s with a clean echo trace. The operator confirmed the AWG and RECT Accumulation-mode displays on hardware. atomize_docs follow-up: `ATOMIZE_DOCS_PENDING.md`.
- 2026-09-23 complete live snapshots: `digitizer_get_curve(live_mode=1)` now returns only complete phase cycles, summing several ADC buffers when one buffer holds fewer windows than the cycle; before, the missing phases were silently dropped. `tune.rep_rate` no longer refuses such cycles, and the live receiver monitor takes every complete snapshot and discards the first one after each handshake. Offline checks pass; the AWG long-cycle preview passed on hardware 2026-09-24 (16 steps, 16 windows per buffer: only complete snapshots, steady echo, baseline noise alternating by about √2 between one- and two-buffer traces). The remaining checklist is local on the spectrometer PC (`docs/INSYS_LIVE_SNAPSHOT.md`).
- 2026-09-19 current live-rate revision: tuning consumes ordinary `digitizer_get_curve(live_mode=1)` results, including old or mixed-rate packet content, and keeps the 5% / three-curve stability rule without packet tags or epoch filtering. The Worker pins a 512 KB ADC buffer only for tuning and restores the previous setting after the card closes on completion, Stop or failure. The driver acquisition methods match their pre-feature versions. Offline checks cover 512 KB across rates/windows, test-mode INI writes, concurrent updates, completion/Stop/acquisition errors, and atomic replacement failure; a restoration failure is reported without successful completion. Hardware validation remains pending.
- 2026-09-19 adaptive relaxation: operator examples at 3318 G motivated accepting the full 80 K T2 range (22.765 µs) and shortening subsequent warm-point ranges, while an unfinished 80 K T1 tail motivated one extension. The AWG Log Time worker now reaches the last grid point before readout. Nd:YAG is fixed at 9.9 Hz in the active Insys tools and engine; automatic rate tuning is unavailable. The earlier range/schema checks, dry run, revised-sequence preflights, pulse/rate capture and GUI/engine equivalence passed; the later temperature carryover policy still needs live validation.
- 2026-09-19 INI revision: atomic temporary-file replacement remains in place. `change_three_ini_files` writes in test mode for compatibility; initialization can therefore update `BaseClockValue`. The other INI setters retain their test guards, and test mode does not claim FPGA ownership. Nd:YAG remains fixed at 9.9 Hz and has no automatic rate tuning.
- 2026-09-19 repetition-rate review: preliminary search/maximization accept `auto`; the saturation scan uses the selected preliminary pulse settings. Poor saturation fits now fail the hard `rep_rate_fit` gate, rounding cannot exceed the fastest tested rate, and a required rate below 0.1 Hz fails instead of shortening the requested recovery period. Synthetic checks cover quantitative/sensitivity fits, flat/noisy/saturated/zero curves, invalidation, rate bounds and all four exported presets. Preliminary schema/video regressions, the seven-step preliminary dry run, T1/T2 automatic-rate dry runs and the strict documentation build passed. Hardware verification of steady-state recovery remains open; a flat curve's 5% tolerance does not establish a <1% saturation bound.
- Staged preliminary amplitude acquisition: protocol dry run, GUI/engine equivalence, targeted amplitude/export checks and worker stop checks passed. The full preliminary check script stopped at the ringing reference (496.4 ns versus 493.2 ns expected) only because the installed pulser config copy still had the pre-ef16693 protect delays; with the repository config it passes. Hardware speed/score validation remains open.
- July oTerPhenyl phase/SNR and 56-/71-trace analyses are retained under the Linux `~/Documents/OTP/` datasets and `~/epr_auto_dev/field_phase_snr_check.py`. They support the field-phase behavior and relaxation gate; they are not additional automation hardware sessions.
- The 2026-07-23 review's 13 confirmed findings were fixed on 2026-07-24. The three then-shipped protocols passed `run --test`; `~/epr_auto_dev/gui_vs_engine.py` reported ALL PASS. The removed full review is recoverable at commit `be42789`; scripts remain under `~/epr_auto_dev/review_wf_ef0c3f4c/`.
- Preliminary offline regressions cover hard-abort precedence, ladder ordering, selection failures, amplitude bounds and export/reload. The June resonator reference and commands are in the preliminary plan.
- Re-run GUI/engine equivalence after changes covered by the repository mirror rule. Report Linux-only harnesses and hardware checks accurately; a Windows dry run is not bench validation.
- After registry changes regenerate `atomize_docs/docs/projects/epr_auto/steps.md` with `docgen`; update prose/schema pages as applicable and run the strict documentation build. No endstation-page expansion for routine control details.
- Record the next bench result against the open checks above, including protocol/preset versions and artifact paths. Keep detailed debugging history in commits rather than rebuilding a session transcript here.

The pre-cleanup session log is available with `git show 56a1a66:docs/automation/ROADMAP.md`. Separate non-automation bench work remains in the hardware checklist and [AWG_FINE_STEP_PLAN.md](AWG_FINE_STEP_PLAN.md).
