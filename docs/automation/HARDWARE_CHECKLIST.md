# Hardware validation checklist

Updated 2026-09-19. There were two hardware sessions: **11 September tested fine tuning**; **18 September worked toward the complete preliminary → fine-tuning → experiment workflow**. The final independent preliminary and fine-tuning runs worked without issues. The logic improved on 18 September, and the final combined preliminary → fine-tuning → T2 run passed that evening. Numerical results and artifact locations are recorded in [ROADMAP.md](ROADMAP.md); current preliminary behavior is in [PRELIMINARY_TUNING_PLAN.md](PRELIMINARY_TUNING_PLAN.md).

RV means rotary-vane attenuation of microwave excitation. VA means receiver video attenuation, set through Video Attenuation 1 (VA1) and Video Attenuation 2 (VA2) before the ADC.

## What has been exercised

| Session | Recorded hardware evidence | Limit of that evidence |
| --- | --- | --- |
| 2026-09-11, coal | Auto-phase round trip, accumulating echo window, amplitude calibration and high-rail detection, explicit EDFS, repeated fine tuning and supporting T2 checks. | Fine-tuning session only; not preliminary preparation or the final three-run design. |
| 2026-09-18, coal | Preliminary and fine tuning each worked independently without issues; logic was improved during the session. Recorded runs include 5/5 preliminary completion and fine tuning through EDFS/repeated calibration. Normal bridge coexistence with the window already open. | The evening chain (`preliminary_run3` → `fine_run4` → `t2`) is the acceptance evidence below; earlier numerical results retain the pulse settings used at the time. |

The 2026-09-19 live-rate and early-range policy/worker checks, protocol dry runs and GUI/engine equivalence pass. No live-rate transition or adaptive temperature-range measurement was made on hardware.

GUI launcher dummy-data checks and operator dry-run Stop passed. Do not treat those as live cancellation, Windows launcher, or FPGA recovery validation. The 100 mV ringing stop never triggered in the recorded hardware sessions.

## Before a lab run

- Keep the main Atomize GUI open for LivePlot. Open the MW bridge window and let its vane homing finish; it may remain open and should become read-only during automation.
- Close the temperature-control tool and stop other acquisitions holding field/temperature/bridge locks. The standalone field-control window may remain open and should back off while locked. Preserve instrument settings and ownership; do not clear busy status to bypass FPGA reboot recovery.
- Start supervised. Answer checkpoints in the main-window dialogs or a real terminal. Choose the sample's field/frequency bounds, fixed RV and pulse lengths before running; dry-run the exact protocol first.
- Record protocol and preset versions, active device configuration, bridge settings, CSVs, `manifest.json`, the protocol copy and `worker_stdout.log`. Relative `output` resolves from the launch directory; `publish_dir` resolves from the preliminary YAML's directory.
- Use **Stop protocol** or terminal `Ctrl-C` for the normal save/drain/abort path. A second interrupt requests bounded forced cleanup. Do not use terminal killing as a routine check; forced process loss needs an explicit board-recovery plan.

Commands from the ITC checkout on Linux (`python` instead of `python3` on Windows for non-hardware checks):

```bash
python3 -m atomize.epr_auto validate <protocol>.yaml
python3 -m atomize.epr_auto run <protocol>.yaml --test
python3 -m atomize.epr_auto run <protocol>.yaml
```

A protocol names `.phase_awg` files; it does not define pulse geometry. Explicit preset names resolve beside the protocol, then in `atomize/epr_auto/presets/`, then the shipped experiments. Defaults use only the shipped directory. Use sample-specific copies and inspect the generated worker settings; `window`, phase, field and calibration can override stored values. Parameter defaults and full examples belong in the published epr_auto reference, not duplicated here.

## Validated three-run workflow

Use `~/experimental_data/Melnikov/2026_09_18_coal_auto/` with `preliminary.yaml`, the generated `tuned/fine_tuning.yaml`, and `t2.yaml`. Ticked on 2026-09-18 from the evening chain (`runs/2026-09-18_preliminary_run3`, `fine_run4`, `t2`).

- [x] **Preliminary stage in the combined run:** both microwave pulses use the chosen common length, π/2 amplitude `a` and π amplitude `2a`, at a fixed operator-selected RV. Verify geometry against the preset/scope, the amplitude maximum lies inside the configured range, field refinement reproduces the echo, and no RV/length search is performed.
- [x] **Ringing/frequency:** confirm nonresonant field, settled rung order 60/40/20/10/5/0 dB, magnitude limit and calculated protection start. Use `window: 4 ns` for resonator selection; verify centers from +1 ns/+2 ns windows and synthesizer-minus-IF bookkeeping.
- [x] **Export:** confirm `echo`, `calibration`, `field` and `echo_cal` presets plus `fine_tuning.yaml` under `tuned/`, with an archive in the preliminary run's `handoff_NNN/`. With `output: runs/{date}_preliminary` from the working folder, the archive is under that `runs/` child; do not confuse this with literal `output: runs/`.
- [x] **Fine stage in the combined run:** Rabi pulse uses `calibration_length`, its detection pair uses the preliminary pulses, and `tune.apply_calibration` writes measured amplitudes into both `field` and `echo_cal` before EDFS. Inspect the pulse roles and values in those files.
- [x] **EDFS:** use the original `find_echo` span recentered on the tuned field (or explicit export override), default 200 points; confirm the line is not clipped by the narrower preliminary refinement span.
- [x] **Closing calibration:** after repeated window/phase/calibration, confirm the final `echo_cal.phase_awg` contains measured amplitudes, zero-order phase, echo window and field. Fine-run data should be under `runs/<date>_fine`.
- [x] **Separate T2 run:** consume `tuned/echo_cal.phase_awg` with `window: preset` and `apply_cal: none`, while retaining/restoring RV and synthesizer settings. Confirm no calibration state from the previous process is needed. The comparison with a matched manual run was not made.
- [x] **Repeat-run records:** verify earlier manifests/CSVs remain intact and a fresh `_run2`/`_run3` directory is selected where required.

## Live stop, bridge and failure checks

These are targeted checks; the ordinary successful workflow does not prove them.

- [ ] **Bridge lifecycle:** test both startup orders, close while automation holds the lock, normal handback and abort. No queued setter, initialization or exit move should run while locked; widgets and driver position must resynchronize afterwards.
- [ ] **Recorded move handling:** confirm the September fixes through the combined run, including the record-age handling, waiting for an in-flight move, and a same-setting `bridge.set` without an unnecessary 60 dB excursion. A stale runner bridge lock must take the recovery/homing path. Confirm Limit homing waits the full travel unless an existing 60 dB record accounts for it.
- [ ] **Ringing failure:** exercise a controlled rejection without deliberately exposing the receiver to excess power. Confirm no next rung is commanded, the sequence stops, the settled 60 dB return is attempted, and the protocol hard-aborts despite retries/skip/foreach continuation. Record return failures as failures, never as successful homing.
- [ ] **Cancellation:** during the ringing ladder, Stop must return RV to 60 dB. At a checkpoint or another step it must leave RV unchanged while saving/draining the worker and releasing owned locks.
- [ ] **Launcher cleanup:** live normal Stop, bounded Force stop, interruption during save, duplicate launch/exit guards and relaunch. Verify partial CSV/manifest status and FPGA release; only the owner releases the board. Windows launcher checks remain separate and pending.
- [ ] **Resonator rejection/stop:** confirm diagnostics for clipped/boundary/unstable scans and pulser cleanup/previous-frequency restoration on cancellation. Investigate narrow-window dropouts if they persist.

## Targeted tuning checks

Use these when a change affects the corresponding behavior; do not repeat all checks for unrelated edits.

| Check | Acceptance evidence |
| --- | --- |
| Auto-phase | Two passes leave a predominantly real echo and small residual phase; use the current 16-point default, not the retired four-point example. Record zero order and coherence. |
| Echo window | Accumulating preview has no cycle-boundary stall/blank result; SNR improves with averaging. Window brackets the resolved echo, with `search_from: 200 ns` and `min_width: 20 ns` excluding the measured defense transient. Record FWHM, edges and trace. |
| Amplitude calibration | Compare π/π2 with manual values and check rails, calibrated shape/area transfer and detection-pair scaling. Inspect the rewritten field/echo-cal arguments and preset reload in test mode. If `refine: true` is used, confirm repeat agreement. Fine calibration need not force a ratio of exactly 2. |
| EDFS | Check line location and width in an explicit sample-appropriate range, then auto prediction/offset. The −7.5 G default is setup-specific; record `shift_g` when remeasuring. Exercise no-line escalation only with bounded fields and verify failure does not choose a noise maximum. |

Remaining commissioning:

- [ ] **Staged preliminary amplitude search:** compare full-trace scores and the selected `a` / `2a` pair against single-trace measurements at matched settings. Confirm one FPGA initialization per nonempty coarse/fine stage, correct sparse fine points and repeated scans, the 50/100 % endpoint, matrix rows/axes and Stop/partial-save cleanup. Measure total elapsed time; the estimated initialization saving is not yet a hardware result.
- [ ] **Strong-sample approach:** verify ringing → live RV opening through 60/40/20/15/10/5/0 dB (ending at the requested RV) → field search → pulse tuning → final video check. Confirm that the phasing live mode stays running and adjusts VA while RV moves; advance to the next RV only after settling and a level at most 200 mV. For field and amplitude scans, verify ready-buffer checks only use columns with every receiver phase and that an excess stops at the reported completed point, which may precede the current command. Verify VA increase and remeasurement of that reported point, then fresh comparison with old-VA scores discarded. Check disabled `adjust_video`, exact VA grids and readback, VA1→VA2 escalation, VA2→VA1 reopening, exhausted range and missing-data failures, Stop/ownership cleanup, and the final target-preset check after fine calibration. Confirm handoff VA settings and repetition rate in all four presets; rates above 10 kHz reject.
- [ ] **Temperature:** `temp.set`/`temp.wait`, reached-setpoint state, in-band hold and a deliberately short timeout at a suitable setpoint. Verify locking and readout. A move beyond `rephase_delta` (default 1 K) invalidates receiver phase and the repetition-rate recommendation; it does not invalidate fine pulse calibration.
- [ ] **Repetition rate:** use [rep_rate_live.yaml](../../protocols/rep_rate_live.yaml) with sample-specific field/preset settings and compare the live `tune.rep_rate` curve with a hand-measured recovery curve/T1. Confirm one open card at the fixed field/fixed tau, ordinary `digitizer_get_curve(live_mode=1)` observations including old or mixed-rate packet content, the tuning-only 512 KB ADC buffer and restoration of the prior `streamBufSizeKb` after completion, Stop or failure, three consecutive nonempty curves within `(max |sig| − min |sig|) / mean |sig| ≤ 5%`, and `scans` as disjoint stable groups. Check quantitative versus sensitivity modes, no extrapolation above tested rates, and saturated/flat-grid cases; 5% steadiness does not establish quantitative 1% accuracy. Compare stability with manual measurements and with automatic fine calibration when available, and verify selected preliminary pulse values, inherited field/echo window/phase, `*_rep_rate_live.csv` partial history, `*_rep_rate_curve.csv`, timeout/Stop cleanup and recommendation failure. Confirm automatic tuning rejects Nd:YAG's fixed 9.9 Hz rate. Hardware validation is pending.
- [ ] **T1:** validate log-grid deduplication (`npoints` may be below requested points), period fit and calibrated pulse transfer. Verify corrected log increments reach the saved final delay; the former worker repeated the first increment. Compare the saved curve/fit with a matched manual acquisition.
- [ ] **Adaptive T1/T2 temperature ranges:** run [the T1/T2](../../protocols/temperature_series_t1t2.yaml) and [T2-only](../../protocols/temperature_series_t2.yaml) examples after setting the real sample, field and presets. Check range assessment after the first full scan, including the final ADC point, and up to three scans when noisy. A confirmed plateau must continue the same accumulation toward `target_snr`, even with excess baseline; a clearly unfinished tail must stop early only after its extension passes timing and budget checks. An unavailable extension must keep accumulating the current range. An uncertain early decision must resume SNR control without a late repeat. Check both saved files after one extension, no second repair, active scan/duration limits during assessment, and shared duration accounting. Verify that next-temperature recommendations approach 55% T2 baseline or 47 T1 plateau points, the warming 25% shortening cap, and no shortening on cooling. Confirm failed fits, Stop, RV invalidation and a new run do not carry a recommendation. During the T1 timing calculation, verify that the scan-boundary pause does not lose ADC buffers or alter the accumulated curve. For carried/repaired T1, compare the full-grid maximum timing-compatible rate with measured physical recovery; check fixed 9.9 Hz Nd:YAG and the absence of automatic rate tuning. Dry-run does not establish these live properties.
- [ ] **T2/relaxation gate:** confirm the physical `2τ` axis after re-anchoring and fit on its absolute origin. Recheck the hard `relaxation_fit` criterion `dAICc/n >= 0.375` on a new real T1/T2 series; `echo_snr` is advisory for relaxation experiments. Record β, fitted time, score and data path.
- [ ] **Full 2D data:** T2 with `save_2d: true` and `target_snr`: `_2d.h5` appears, `I`/`Q`/`t`/`sweep` shapes match the CSV, and integrating `I`/`Q` over the echo window through `digitizer_demodulate` reproduces the 1D CSV. Stop mid-scan leaves a partial matrix recorded as `data_file_2d`; `adjust_range` with an extension records two matrices under `range_adjustment`; EDFS gives a field-points × window-samples matrix with the field axis in `sweep`.
- [ ] **Duration limit:** choose `max_duration` below the projected run duration; confirm a downward-only scan limit and saved/fitted partial data.
- [ ] **Adaptive SNR/series:** check `field.edfs target_snr` on a strong line and `foreach` T1/T2 over suitable fields. Strong signals should stop early, weak ones approach the scan ceiling; combined duration/SNR limits must never increase scans. Check loop tags and continuation after a controlled failed iteration, then run the same preset interactively as a GUI regression.
- [ ] **Runner policies:** transient retry, manifest updates, notifications when configured, and an autonomous run without prompts. Verify interruption remains an abort and is never retried or continued by foreach.

The older `tune.power_for_length`/length-mode coarse-fallback route is implemented but outside the current daily workflow. Commission its SNR-gated moves, from-above settling, target convergence, length rails and fallback only if it is needed again. `protocols/tune_up.yaml` and `overnight_t2.yaml` remain examples of that older route, not evidence that the final three-run workflow has passed.

## Separate bench backlog

No later pass evidence was found for these inherited items; check their current implementation before scheduling a retest.

- [ ] Insys swComp hybrid wait/acquisition and parsing speedups: compare DEER scan timing and data. The old note claiming these were uncommitted is not a current status statement.
- [ ] Live Edit round 8: AWG-start amplitude-gate tracking and N/B changes during live preview.
- [ ] ESEEM Avg cumulative tau averaging and Inc2 cut/copy/paste/reset regression (`f5411fc`).
- [ ] 0.8 ns AWG grid: TTL versus DAC at residual positions 0–3, moving echo shape, four-point residual flatness and GIM re-arm when the gate changes by one tick. Follow [AWG_FINE_STEP_PLAN.md](AWG_FINE_STEP_PLAN.md).
- [ ] `points_plot` benchmark suite under `~/q/2026_07_06_insys_efficiency_auto/` (`run_benchmarks.py`).

After a lab session, record date, tested version, outcome and artifact path in the roadmap and tick only the checks actually performed. Earlier detailed snippets and session history remain available in git at `56a1a66`.
