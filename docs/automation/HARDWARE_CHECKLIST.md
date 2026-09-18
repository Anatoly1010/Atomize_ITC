# Hardware validation checklist

Updated 2026-09-18. There were two hardware sessions: **11 September tested fine tuning**; **18 September worked toward the complete preliminary → fine-tuning → experiment workflow**. The final independent preliminary and fine-tuning runs worked without issues. The logic improved on 18 September; the final combined preliminary → fine-tuning → T2 run remains pending. Numerical results and artifact locations are recorded in [ROADMAP.md](ROADMAP.md); current preliminary behavior is in [PRELIMINARY_TUNING_PLAN.md](PRELIMINARY_TUNING_PLAN.md).

## What has been exercised

| Session | Recorded hardware evidence | Limit of that evidence |
| --- | --- | --- |
| 2026-09-11, coal | Auto-phase round trip, accumulating echo window, amplitude calibration and high-rail detection, explicit EDFS, repeated fine tuning and supporting T2 checks. | Fine-tuning session only; not preliminary preparation or the final three-run design. |
| 2026-09-18, coal | Preliminary and fine tuning each worked independently without issues; logic was improved during the session. Recorded runs include 5/5 preliminary completion and fine tuning through EDFS/repeated calibration. Normal bridge coexistence with the window already open. | The complete preliminary → fine-tuning → T2 run with the final logic is pending; historical numerical results retain the pulse settings used at the time. |

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

## Next: the final three-run workflow

Use `~/experimental_data/Melnikov/2026_09_18_coal_auto/` with `preliminary.yaml`, the generated `tuned/fine_tuning.yaml`, and `t2.yaml`. The unchecked items below are acceptance checks for this combined run, not claims that preliminary or fine tuning have never worked independently.

- [ ] **Preliminary stage in the combined run:** both microwave pulses use the chosen common length, π/2 amplitude `a` and π amplitude `2a`, at a fixed operator-selected RV. Verify geometry against the preset/scope, the amplitude maximum lies inside the configured range, field refinement reproduces the echo, and no RV/length search is performed.
- [ ] **Ringing/frequency:** confirm nonresonant field, settled rung order 60/40/20/10/5/0 dB, magnitude limit and calculated protection start. Use `window: 4 ns` for resonator selection; verify centers from +1 ns/+2 ns windows and synthesizer-minus-IF bookkeeping.
- [ ] **Export:** confirm `echo`, `calibration`, `field` and `echo_cal` presets plus `fine_tuning.yaml` under `tuned/`, with an archive in the preliminary run's `handoff_NNN/`. With `output: runs/{date}_preliminary` from the working folder, the archive is under that `runs/` child; do not confuse this with literal `output: runs/`.
- [ ] **Fine stage in the combined run:** Rabi pulse uses `calibration_length`, its detection pair uses the preliminary pulses, and `tune.apply_calibration` writes measured amplitudes into both `field` and `echo_cal` before EDFS. Inspect the pulse roles and values in those files.
- [ ] **EDFS:** use the original `find_echo` span recentered on the tuned field (or explicit export override), default 200 points; confirm the line is not clipped by the narrower preliminary refinement span.
- [ ] **Closing calibration:** after repeated window/phase/calibration, confirm the final `echo_cal.phase_awg` contains measured amplitudes, zero-order phase, echo window and field. Fine-run data should be under `runs/<date>_fine`.
- [ ] **Separate T2 run:** consume `tuned/echo_cal.phase_awg` with `window: preset` and `apply_cal: none`, while retaining/restoring RV and synthesizer settings. Confirm no calibration state from the previous process is needed; compare the stored sequence and fit with a matched manual run.
- [ ] **Repeat-run records:** verify earlier manifests/CSVs remain intact and a fresh `_run2`/`_run3` directory is selected where required.

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

- [ ] **Temperature:** `temp.set`/`temp.wait`, reached-setpoint state, in-band hold and a deliberately short timeout at a suitable setpoint. Verify locking and readout. A move beyond `rephase_delta` (default 1 K) invalidates receiver phase; it does not invalidate fine pulse calibration.
- [ ] **Repetition rate:** compare `tune.rep_rate` with a hand-measured recovery curve/T1. Check quantitative versus sensitivity modes, no extrapolation above tested rates, and saturated/flat-grid cases.
- [ ] **T1:** validate log-grid deduplication (`npoints` may be below requested points), period fit and calibrated pulse transfer. Compare the saved curve/fit with a matched manual acquisition.
- [ ] **T2/relaxation gate:** confirm the physical `2τ` axis after re-anchoring and fit on its absolute origin. Recheck the hard `relaxation_fit` criterion `dAICc/n >= 0.375` on a new real T1/T2 series; `echo_snr` is advisory for relaxation experiments. Record β, fitted time, score and data path.
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
