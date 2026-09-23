# Insys live snapshots: complete phase cycles

Status 2026-09-23: implemented, offline checks pass, **hardware check pending**. Uncommitted until the docs are approved.

## Problem

The live preview of `awg_phasing_insys.py` / `phasing_insys.py` (Accumulation Mode off, `dig_on` with `l_mode = 0`) calls `Insys_FPGA.digitizer_get_curve(POINTS, PHASES, live_mode = 1)` once per phase step. Every phase step yields one ADC window (nid 0…PHASES−1, restarted every cycle), and the card delivers data only one full stream buffer at a time, about `number_adc_window_in_buffer()` windows.

Live mode used to reset `data_raw` / `count_nip` / `tail_carry` on every call and combine only the buffers that arrived since the previous call. When a buffer holds fewer windows than the phase cycle (`PHASES >= number_adc_window_in_buffer()`), some phases were missing from every snapshot; they were counted as zero and the phase combination was wrong. The test-mode preflight only printed `!!!TOO MANY PHASES FOR LIVE MODE!!!`.

Experiments and the preview with Accumulation Mode on (`live_mode = 0`) were never affected: they sum every buffer.

## Fix

`Insys_FPGA.digitizer_get_curve`, live branch only:

- The accumulator reset moved into `_acq_reset(total_points, adc_window, live_mode)`. Experiment mode calls it exactly as before.
- Live mode resets only when the first buffer after a returned snapshot arrives (`self._live_fresh`, or a changed `count_nip` size). Until every nid has a packet (`count_nip.all()`), buffers keep being summed, including the packet cut at a buffer boundary, and the call returns `None, None`.
- A complete snapshot is finalized over the whole point range and sets `_live_fresh = 1`. Calls without a new buffer leave the last snapshot (and `count_nip`) in place, so the dig_on Count readout shows the displayed snapshot.
- When a buffer holds more windows than the cycle, every buffer is already complete, so the results are byte-identical to the old code.
- Consequence: with a long cycle the preview refreshes once per complete cycle, which can take several buffers.

Messages: the preflight line is now `PHASE CYCLE EXCEEDS ADC BUFFER: LIVE PREVIEW UPDATES ONCE PER FULL CYCLE` + `ADC WINDOWS IN BUFFER: N` (both workers), and the pinned banner in `phasing_messages.py` reads "LIVE MODE BUFFER · Phase cycle exceeds ADC buffer: live preview updates once per full cycle · ADC windows in buffer: N".

`epr_auto`:

- `awg_phasing_insys.Worker.dig_on`: live repetition-rate tuning no longer raises `Too many phases for live repetition-rate tuning`.
- `engine/live_receiver.py` (RV approach receiver monitor): it used to accept only the frame plotted at the last phase step of a cycle, and only when that step's `count_nip` was complete, so frames arrived only when a buffer landed on that step. It now keeps the latest complete (finite) snapshot and hands it over at the end of each cycle; the first snapshot completed after each handshake is discarded, because it may span the bridge change. `_live_child` lost its `phases` argument.

## Files

- `atomize/device_modules/Insys_FPGA.py` — `_acq_reset`, live branch of `digitizer_get_curve`, `_live_fresh` init, docstring.
- `atomize/control_center/awg_phasing_insys.py`, `phasing_insys.py` — preflight message; rate-tuning check removed (AWG only).
- `atomize/control_center/phasing_messages.py` — banner text.
- `atomize/epr_auto/engine/live_receiver.py`, `atomize/script_examples/epr_auto/live_receiver_checks.py`.
- Docs: `atomize/documentation/functions/digitizer.md`; `atomize_docs` `functions/digitizer.md`, `projects/epr_auto/tuning.md`, `projects/epr_auto/protocols.md`; `docs/automation/PRELIMINARY_TUNING_PLAN.md`, `ROADMAP.md`.
- `Insys_FPGA.py` is byte-identical across the five forks; porting it is not done yet.

## Offline evidence (2026-09-23)

`python3 ~/pulser_optim/live_snapshot_check.py test` (fake driver; compares with the pre-fix module from commit `1c58c62`): ALL PASS.

- 16 phases, ~5.3 windows per buffer: complete curves every ~4 buffers, equal to an independent model to 5e-6; the old code was off by up to 126 on a signal of ~16. Same with decimation 2.
- 4 phases, ~20 windows per buffer: new == old call by call (same `None` pattern, identical curves and `count_nip`).
- Idle calls keep the last snapshot; the next buffer starts a fresh one.
- Experiment mode: full / partial / integral results identical to the old code.

Also passing: `receiver_guard_checks.py`, `live_receiver_checks.py`, the other `atomize/script_examples/epr_auto/*_checks.py` (`preliminary_checks.py` fails at the ringing reference both before and after this change — installed config copy, see ROADMAP), and dry runs of `protocols/rep_rate_live.yaml`, `preliminary_tuning.yaml`, `tune_up.yaml`.

## Hardware check

Windows per buffer: `number_adc_window_in_buffer()` = buffer / (`adc_window` × 64 + 32) bytes. Below ~49 Hz the buffer is 128 KB for windows ≤ 819 ns (`adc_window` ≤ 256), so a 512 ns window gives 12 windows per buffer; a 16-step cycle then exceeds it. At faster rates the buffer is 1024 KB (4096 KB for windows ≥ 3.2 µs).

1. **Long cycle, AWG phasing.** Echo preset with a 16-step phase cycle, 512 ns detection window, 20 Hz, a few averages. Update (preflight):
   - [ ] the new message and banner appear with `ADC windows in buffer: 12`;
   - [ ] the live preview shows an undistorted echo, refreshed about once per cycle, with no NaN/blank frames between;
   - [ ] the Count line shows every phase non-zero;
   - [ ] the echo agrees (shape, phase, amplitude within noise) with the same settings in Accumulation Mode;
   - [ ] a live pulse edit re-arms; at most the first curve after it looks mixed.
2. **Long cycle, RECT phasing (`phasing_insys.py`).** Same as step 1.
3. **Short cycle regression.** 2- or 4-step echo at ~1 kHz, normal window: preview, refresh rate and Count behave as before; T (reference), Auto Phase and Auto Window still work.
4. **`epr_auto` rate tuning.** `protocols/rep_rate_live.yaml` as usual: rates advance, stable groups form, the 512 KB buffer is restored afterwards. If time allows, repeat with a cycle longer than the 512 KB buffer (e.g. a 3.2 µs window, 8+ steps), which was refused before.
5. **`epr_auto` receiver monitor.** `tune.find_echo` RV approach in `preliminary_tuning.yaml`: live frames arrive at each ladder step, VA adjusts, no `live receiver stalled`.

If step 1 fails, revert only the `Insys_FPGA.py` part and re-check that the old warning still appears.
