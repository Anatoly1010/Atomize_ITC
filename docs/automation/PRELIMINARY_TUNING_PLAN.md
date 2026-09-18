# Preliminary tuning — current design and validation

Updated 2026-09-18. Implemented in `atomize/epr_auto`. Hardware work comprised two sessions: 11 September tested fine tuning; 18 September improved the logic and worked toward the complete workflow. The final independent preliminary and fine-tuning runs worked without issues. The final combined preliminary → fine-tuning → T2 run is still pending. See [ROADMAP.md](ROADMAP.md) for dated evidence and [HARDWARE_CHECKLIST.md](HARDWARE_CHECKLIST.md) for remaining checks.

## Purpose and sequence

Prepare AWG presets for fine tuning and a later experiment:

```text
ringing check → [resonator scan] → echo field search → amplitude/field optimization → preset export
preliminary.yaml → tuned/fine_tuning.yaml → experiment protocol
```

Use the existing YAML runner, validation, session state, locks, checkpoints and acquisition workers. Start from [protocols/preliminary_tuning.yaml](../../protocols/preliminary_tuning.yaml). Registered steps are `tune.ringing_check`, `tune.resonator`, `tune.find_echo`, `tune.maximize_echo`, `tune.save_presets`, `tune.apply_calibration` and `bridge.set`; schemas live in `preliminary_steps.py`, implementation in `primitives/preliminary.py`.

Every transmit pulse in preliminary tuning is AWG SINE at the echo preset's DETECTION IF. RECT automation remains out of scope. The first two steps use built-in sequences, accept `if_mhz` (default 50 MHz), and accept no `preset`. Their IF must match the later echo preset. Frequencies are synthesizer settings, with observation frequency `ν = ν_LO − ν_IF`; do not add IF twice.

## Bridge ownership and movement

- Open the MW bridge window before a live run and let its homing finish. It may stay open: the runner owns `field.param`, `temp.param` and `bridge.param` as `epr_auto`; the bridge window polls its lock every second, blocks manual/init/exit commands while locked, and resynchronizes on handback. Test mode never takes these locks.
- Capture the age of the vane record before acquiring the bridge lock, because that lock write changes the file timestamp. Wait for the window's lock poll before motion.
- Limit homing from a position other than 60 dB waits the full `FULL_TRAVEL_S = 70.596` plus 0.2 s margin. If already recorded at 60 dB, wait only the remaining recorded travel. Join the driver thread; its old seven-second timer alone is insufficient. Relative commands sent during Limit homing can be lost.
- Ordinary `bridge.set` waits out a recorded move, adopts the recorded vane position, then moves relative to it. A stale `epr_auto` bridge lock causes re-homing. Relative moves use `_vane_set` with the calibrated, from-above approach and settling wait.
- Hardware failure paths attempt a settled return to 60 dB and raise `PreliminaryAbort`; retry, skip and foreach continuation cannot swallow this hard stop. Report `return to 60 dB FAILED` when the return fails.
- Operator cancellation homes RV only inside the ringing ladder. Stop at a checkpoint or another step leaves RV unchanged while workers drain and owned locks are released. Preserve FPGA ownership and reboot-recovery checks; do not clear busy state to bypass recovery.

Normal bridge coexistence was observed on hardware with the window opened first. Other startup orders, close/abort cases and final recovery changes remain in the hardware checklist.

## 1. Receiver ringing check

`tune.ringing_check` sets a nonresonant `field` (default 100 G), retains the current frequency, homes to 60 dB, and visits **60, 40, 20, 10, 5, 0 dB**. At each point: move → settle → acquire → check. Only a pass permits the next move; there is one ladder per preliminary run.

The internal `ringing_check.phase_awg` has DETECTION and one SINE pulse, both `[+x,+x]`, at the same IF. The default SINE length is 102.4 ns, DETECTION length 640 ns, repetition rate 500 Hz, with 10 acquisitions and one scan. Both DAC amplitudes are 260 mV. Validate the additive phase cycle on the built worker arguments before hardware access. Later pulses must remain within the tested length, DAC amplitude and IF limits; `max_length` must cover preliminary and calibration pulses.

The limit is **100 mV on the maximum unsmoothed `hypot(I, Q)` after protection**. Demodulation rotates I/Q without changing this magnitude. Do not integrate, smooth, reject narrow transients or blank the onset. Missing, nonfinite or otherwise invalid traces fail the check. A failure or cancellation inside the ladder attempts the settled 60 dB return before aborting. Save traces, attenuation, maxima and calculated protection endpoints.

Protection timing is derived from a throwaway test-mode `Insys_FPGA` using the worker setup and prepared TTL pulses. `protection_trace_start_ns` transfers the measured standard Hahn defense-transient early edge (147.6 ns; recorded window 147.6–155.2 ns) by the calculated difference in protection endpoints. The recorded September spectrometer calculation was `134.4 − (−211.2) + 147.6 = 493.2 ns` for a 102.4 ns pulse. This is reference evidence, not a universal hard-coded start: active device config and pulse geometry determine each run's result. The September raw CSV was unavailable at the recorded session path during the timing review; no fresh fit was claimed.

Receiver ringing and the resonator's reflected-diode signal are separate measurements; the diode scan below is not subject to the receiver's 100 mV gate.

## 2. Optional resonator frequency selection

`tune.resonator` sets RV to 10 dB and calls `tune_preset.Worker.scan_awg` in a child process. It uses the AWG SINE sequence and the existing diode/Keysight acquisition. The child closes the pulser and restores the prior synthesizer setting on completion or failure; the parent then applies an accepted center.

The GUI retains RECT mode and supports AWG mode with IF 1–280 MHz. Optional trailing `Pulse Mode:` and `AWG Frequency:` lines in `.tn` files preserve old files as RECT. CSV headers record mode, IF and pulse length. This GUI format and worker path must stay consistent with automation.

Selection procedure:

1. Validate array shape, finite values, ordered frequency/time samples and units. Locate the pulse and trailing edge from the ensemble, accounting for trigger offset; allow an explicit `region`.
2. Subtract the pre-pulse baseline and determine the ringing polarity. Average one common early-ringing time window across all frequencies; never maximize over time independently for each frequency.
3. Smooth modestly across frequency to locate a candidate while retaining the original section. Check noise, competitors, clipping, scan edges and centers from windows shifted by **1 ns and 2 ns**.
4. Reject weak, competing, boundary, clipped or unstable peaks with diagnostic maps/sections. Do not expand the supplied frequency bounds automatically. Apply an accepted synthesizer value directly and invalidate phase, window and pulse calibration.

Use `window: 4 ns` for the bench-recommended selection width; the parameter default remains 2 ns. Typical `precision_mhz` is 5; points are not restricted to a 5 MHz grid. The scope is set to 200 ns range, 160 ns delay, CH1 50 mV/div, CH2 1 V/div with trigger at 0.75 V. The measured source of single-frequency jitter remains unresolved.

Reference data on the Linux box:

- `/home/anatoly/Documents/00_Exp_data/2026_06_23_sifter/01_resonator_tune.tn`: RECT, 102.4 ns, 500 Hz, 9200–9600 MHz at 1 MHz steps, 10 averages, one scan.
- `/home/anatoly/Documents/00_Exp_data/2026_06_24_sifter/01_resonator_tune.csv`: `(640, 401)` time/frequency array, 0.3125 ns sampling. The selector returns 9439 MHz (reported near 9440 MHz at 5 MHz precision); recorded window 152.8125–154.6875 ns and later windows gave 9439, 9439 and 9436 MHz. This was a RECT scan: an AWG scan of the same resonator needs synthesizer frequency higher by IF.

## 3. Find an echo

`tune.find_echo` uses the supplied SINE echo preset with normal phase cycling, fixed `attenuation_db` (default 10 dB, allowed 0–60), and a common `pulse_length` for both microwave pulses. Omitted length uses the shortest active microwave pulse in the preset, snapped to its AWG grid.

Sweep the supplied field center/span with the existing field worker, integrating raw `hypot(I, Q)` over the full detection window. At the best field, acquire a trace and require a delayed, resolved echo to establish the integration window. No passing echo means stop and return to 60 dB; there is no automatic wider search or power increase.

`frequency_shift_mhz` is a signed integer offset from the resonator-selected synthesizer value, or the initial bridge frequency when the scan is omitted. Repeated searches reuse that reference rather than accumulating shifts. The selected frequency carries into maximization and the exported handoff. Zero increments are used only for preliminary measurements; exported presets retain their original sweep increments.

## 4. Maximize the echo

`tune.maximize_echo` holds RV and the common pulse length fixed, inheriting `tune.find_echo` settings unless explicitly overridden. It replaces the earlier RV and pulse-length searches.

1. Scan π/2 amplitude `a`, with π amplitude `2a`, over `amplitude_range` (default 5–50 %). Use `coarse_step` (5 %) followed by `fine_step` (1 %) around the best point. Both pulses have the same length; pulse roles come from `pulse_map` or preset inference.
2. A maximum at the upper bound aborts with `reduce attenuation`; the lower bound aborts with `increase attenuation`. The operator chooses a new fixed RV setting before rerunning.
3. Refine the field in `field_span` (default 10 G, 21 points), restore the best combination and confirm the echo. A result that does not reproduce is rejected.

Keep acquisition effort and scoring comparable, and stay within the ringing-tested power and pulse limits. The equal-length requirement corrects the intermediate 32/64 ns at `a/2a` design, which gave four times the pulse area for the nominal π pulse. Recorded results from that earlier pulse pair should not be presented as measurements of the corrected equal-length pair.

## 5. Export for fine tuning

`tune.save_presets` preserves input presets and publishes `fine_tuning.yaml` plus four `.phase_awg` files to `publish_dir` (default `tuned/` beside the preliminary protocol). An archive remains in `<preliminary run_dir>/handoff_NNN/`. `output` controls that run directory and resolves from the launch directory; `publish_dir` resolves from the protocol directory. Fine-run data go to `<publish_dir parent>/runs/<date>_fine`.

| File | Role |
| --- | --- |
| `echo.phase_awg` | Preliminary pair for the first echo-window and phase measurements. |
| `calibration.phase_awg` | SINE Rabi pulse at `calibration_length`, detected with the preliminary pair. |
| `field.phase_awg` | Field sweep with both echo pulses at `calibration_length`. |
| `echo_cal.phase_awg` | Equal-length echo pair for the second tuning pass and later experiments. |

`calibration_length` defaults to the preliminary length and cannot exceed the ringing-tested maximum. Field/echo-cal amplitudes start as scaled placeholders; measured fine calibration replaces them. Exported presets are reloaded and their exact worker arguments pre-flighted.

The generated sequence is:

```text
bridge.set
→ echo_window(echo) → auto_phase(echo) → pi_calibration(calibration)
→ apply_calibration(field) → apply_calibration(echo_cal)
→ field.edfs(field)
→ echo_window(echo_cal) → auto_phase(echo_cal) → pi_calibration(calibration)
→ apply_calibration(echo_cal)
```

The EDFS uses the original `find_echo` span recentered on the tuned field, with `field_points: 200`, unless `field_span` overrides it. The narrower preliminary refinement span clipped the coal line and is not the handoff default.

The closing `tune.apply_calibration` writes pulse amplitudes, zero-order phase, echo window and field into `echo_cal.phase_awg`. It rewrites the named preset unless an absolute `destination` is supplied. A separate experiment uses `tuned/echo_cal.phase_awg`, `window: preset`, and `apply_cal: none`; retain or restore RV and synthesizer settings separately because the preset does not store them.

## Verification and remaining work

Recorded offline coverage includes both diode signs; weak/competing/edge/clipped and nonfinite scans; protection changes with pulse length; ladder ordering and hard-abort precedence; amplitude bounds; export/reload and handoff validation; bridge lock/handback behavior; resonator stop handling. GUI/engine equivalence previously reported ALL PASS. These are historical results, not new hardware checks.

Linux regression commands (`python` instead of `python3` on Windows; the equivalence harness is Linux-only):

```bash
python3 -m atomize.epr_auto validate protocols/preliminary_tuning.yaml
QT_QPA_PLATFORM=offscreen python3 -m atomize.epr_auto run protocols/preliminary_tuning.yaml --test
QT_QPA_PLATFORM=offscreen python3 atomize/script_examples/epr_auto/preliminary_checks.py test
python3 atomize/script_examples/epr_auto/resonator_stop_checks.py test
QT_QPA_PLATFORM=offscreen python3 ~/epr_auto_dev/gui_vs_engine.py
python3 -m atomize.epr_auto.preset_hash
```

- [x] Fine tuning exercised on 2026-09-11; preliminary and fine tuning each used independently without issues on 2026-09-18, as confirmed by the operator. The roadmap preserves recorded pulse settings and results.
- [x] Public documentation and regenerated step reference committed and pushed in `atomize_docs` as `614a3f0`; strict build and the revised five-stage example dry run passed.
- [ ] Final three-run day in `~/experimental_data/Melnikov/2026_09_18_coal_auto/`: equal-length preliminary pulses → current `tuned/fine_tuning.yaml` → `t2.yaml` using the saved calibration.
- [ ] Final publication layout, bridge record-age/no-move behavior, live cancellation and recovery scenarios; use the hardware checklist.
- [ ] Ringing hard-stop and settled 60 dB return on hardware; no measured trace exceeded 100 mV in the recorded runs.
- [ ] Identify the resonator timing-jitter source if it continues to affect selection.
