# EPR automation — roadmap

Updated 2026-09-18. Keep this file focused on current status, open work and dated evidence. Current preliminary-tuning decisions live in [PRELIMINARY_TUNING_PLAN.md](PRELIMINARY_TUNING_PLAN.md); bench acceptance checks live in [HARDWARE_CHECKLIST.md](HARDWARE_CHECKLIST.md). General design and the GUI/engine contract remain in [ARCHITECTURE.md](ARCHITECTURE.md).

The hardware work comprises **two sessions**: **11 September — fine tuning only**; **18 September — implementation and trials of the complete workflow**. The final independent preliminary and fine-tuning runs worked without issues. The logic was improved on 18 September; the final combined preliminary → fine-tuning → T2 run is still pending.

## Implemented

- YAML validation, test mode, supervised/checkpointed/autonomous runs, retries and failure policies, manifests, protocol copies, notifications, and field/temperature series with `foreach`.
- Engine reuse of `awg_phasing_insys.Worker`, preset/snapshot equivalence, trace capture, phase/window/pulse calibration, EDFS, temperature control, T1/T2 acquisitions, repetition-rate selection, and downward-only scan limits from duration/SNR.
- Preliminary ringing gate, optional AWG resonator scan, echo search, fixed-RV amplitude optimization and four-preset fine-tuning export. The final design sets both echo pulses to a common length; the Rabi pulse may use its own `calibration_length`. See the preliminary plan for exact behavior.
- Main-window protocol launcher with dry-run dialogs, Stop/Force stop, worker drain, duplicate-run and exit guards. Operator GUI dry runs and Stop passed; live cleanup and Windows launcher execution remain unverified. Plan: [GUI_PROTOCOL_LAUNCHER_PLAN.md](GUI_PROTOCOL_LAUNCHER_PLAN.md). Regression scripts: `atomize/script_examples/epr_auto/gui_launcher_checks.py`, `gui_runner_checks.py` and `worker_stop_checks.py`.
- Connected plot dots become grey after 10 s idle; the change is now carried to Atomize, NIOCH, NIOCH_Q and Cryomech. It is no longer backlog.
- Public epr_auto documentation and regenerated step reference committed and pushed in `atomize_docs` as `614a3f0`. The completed documentation handoff is retired. Strict MkDocs build and the revised preliminary example's five-stage dry run passed on Windows.

## Pending hardware validation

The next validation vehicle is `~/experimental_data/Melnikov/2026_09_18_coal_auto/`:

```text
preliminary.yaml → tuned/fine_tuning.yaml → t2.yaml
```

- [ ] Run all three with the final equal-length preliminary pair, separate Rabi `calibration_length`, both pre-EDFS `tune.apply_calibration` calls, and the closing write to `tuned/echo_cal.phase_awg`.
- [ ] Confirm the separate experiment consumes that file with `window: preset` and `apply_cal: none`, while retaining/restoring the tuned RV and synthesizer settings.
- [ ] Verify `tuned/` publication beside the protocol, archive under the configured preliminary run directory, fine data under `runs/<date>_fine`, and repeat-run preservation.
- [ ] Verify final bridge record-age/no-home behavior and remaining lifecycle cases: alternate startup order, close during automation, handback and abort. Normal operation with the bridge window opened first has been observed.
- [ ] Exercise the ringing hard stop and settled 60 dB return, including reported return failures. No recorded trace exceeded 100 mV; this is not yet hardware-validated.
- [ ] Verify live launcher Stop/Force stop, saved partial data, worker/FPGA cleanup, lock release and relaunch. Keep Windows launcher validation separate from the Windows CLI dry run.
- [ ] Measure the cause of resonator selection jitter if it continues: FPGA trigger/AWG clock crossing versus scope trigger. `window: 4 ns` is recommended; 2 ns remains the code default.
- [ ] Complete the remaining T1, repetition-rate, temperature, duration/SNR, EDFS early-stop, field-series and autonomous-run checks listed in the hardware checklist. Recheck the `dAICc/n >= 0.375` relaxation gate on a new real T1/T2 series.

- [ ] Separate AWG 0.8 ns bench checks remain open: TTL/DAC residual positions 0–3, 0.8 ns tau sweep, residual flatness and GIM re-arm across a one-tick gate change. See [AWG_FINE_STEP_PLAN.md](AWG_FINE_STEP_PLAN.md).

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

Work expanded to preliminary preparation and its fine-tuning handoff, with logic improvements during the session. The operator confirms the final independent preliminary and fine-tuning runs worked without issues; the complete preliminary → fine-tuning → T2 run remains pending. The recorded measurements below retain their original pulse settings for context:

- `preliminary_coal.yaml` completed 5/5 on run 3 (`runs/2026-09-18_preliminary_run3` in the coal bench directory). Ringing ladder at 100 G, synthesizer 9696 MHz / observation 9646 MHz, resonator section SNR 220 and centers within 1 MHz. The earlier RV-search design chose about 12 dB and 3437 G, with 32/64 ns pulses and window 241.6–400.8 ns.
- Ringing peaks 17–68 mV at 494–496 ns were power-independent protection transients; no >100 mV stop occurred. Bridge coexistence worked with the window already open.
- Fine-tuning trials exposed a dropped relative move during Limit homing and a calibration preset whose detection pair assumed more B1. Fixes included full Limit travel timing, recorded-position adoption, reading record age before lock writes, and scaling export to the preliminary pair.
- Run 5 and its intermediate handoff worked at 4 dB, 9696 MHz and 3436.5 G. The 32/64 ns pair used 35/70 % amplitudes. Fine calibration gave π 55.8 % / π/2 28.0 %, ratio 1.99; EDFS over 3376–3496 G found 3435.6 G with FWHM 15.7 G; repeat π was 55.2 %, ratio 1.98.
- The design was then corrected to equal-length echo pulses at `a/2a`, with a separate Rabi target, four exported presets and explicit calibration writes. **The final combined preliminary → fine-tuning → T2 run remains pending.** The earlier 32/64 ns pair at `a/2a` had a fourfold area ratio; its numerical results describe that earlier setting, not the corrected equal-length pair.

The 10 G refinement span clipped the EDFS line, so the handoff now uses the original search span. Narrow 2 ns resonator windows showed 4–9 % single-frequency dropouts; the recommended window is 4 ns with stability comparisons shifted by 1 ns and 2 ns. Worker stdout now goes to the run's `worker_stdout.log`.

## Offline evidence and maintenance

- July oTerPhenyl phase/SNR and 56-/71-trace analyses are retained under the Linux `~/Documents/OTP/` datasets and `~/epr_auto_dev/field_phase_snr_check.py`. They support the field-phase behavior and relaxation gate; they are not additional automation hardware sessions.
- The 2026-07-23 review's 13 confirmed findings were fixed on 2026-07-24. The three then-shipped protocols passed `run --test`; `~/epr_auto_dev/gui_vs_engine.py` reported ALL PASS. The removed full review is recoverable at commit `be42789`; scripts remain under `~/epr_auto_dev/review_wf_ef0c3f4c/`.
- Preliminary offline regressions cover hard-abort precedence, ladder ordering, selection failures, amplitude bounds and export/reload. The June resonator reference and commands are in the preliminary plan.
- Re-run GUI/engine equivalence after changes covered by the repository mirror rule. Report Linux-only harnesses and hardware checks accurately; a Windows dry run is not bench validation.
- After registry changes regenerate `atomize_docs/docs/projects/epr_auto/steps.md` with `docgen`; update prose/schema pages as applicable and run the strict documentation build. No endstation-page expansion for routine control details.
- Record the next bench result against the open checks above, including protocol/preset versions and artifact paths. Keep detailed debugging history in commits rather than rebuilding a session transcript here.

The pre-cleanup session log is available with `git show 56a1a66:docs/automation/ROADMAP.md`. Separate non-automation bench work remains in the hardware checklist and [AWG_FINE_STEP_PLAN.md](AWG_FINE_STEP_PLAN.md).
