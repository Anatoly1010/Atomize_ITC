# Sibling handoff — 2026-09-24, accumulation preview and sweeps

For a session on the Windows machine, where the sibling Atomize repositories
and `D:\Melnikov\11_Programming\atomize_sync\sync_check.py` live. Port the
changes below into every sibling that has the same files, then delete this
file. It is separate from `SIBLING_HANDOFF_2026-09-24.md` (commit 657b905);
either can be ported first.

Section 1–2 are in commit c894e65, sections 3–5 in the later commits that touch this file; one diff covers all:

```powershell
$c = git log -1 --format=%H -- docs/SIBLING_HANDOFF_2026-09-24_sweeps.md
git diff c894e65^ $c -- atomize/control_center/awg_phasing_insys.py atomize/control_center/phasing_insys.py atomize/epr_auto/engine/executor.py atomize/epr_auto/steps.py atomize/script_examples/epr_auto/receiver_guard_checks.py atomize/documentation/functions/digitizer.md > itc_2026_09_24_sweeps.patch
```

In each sibling: `git apply --3way itc_2026_09_24_sweeps.patch`. The two
phasing tools use CRLF line endings; keep them. Skip a file the sibling does
not have (`atomize/epr_auto/` may be ITC-only), and port a hunk by hand when
the surrounding code differs.

## 1. Accumulation mode: equal shots per phase

`Worker.dig_on`, `l_mode == 1` branch, in `awg_phasing_insys.py` and
`phasing_insys.py`. The readout was blocking at the last phase until a ~1 MB
driver block filled, and the board repeated that phase meanwhile (count_nip
`[41 40 40 2444]`). It is now
`pb.digitizer_get_curve(POINTS, PHASES, live_mode = 0, current_scan = 0)`,
which never blocks, and the loop `continue`s when it returns `None`: count_nip
`[594 592 592 594]`, about 10× more complete cycles per second. Live mode is
unchanged. It relies on `digitizer_get_curve`'s `current_scan` / `total_scan`
drain logic in `Insys_FPGA.py`; check the sibling's copy has it.

## 2. Runner: cycles counted from count_nip (only if the sibling has `atomize/epr_auto/`)

`executor._trace_child` counted one cycle per redraw, which no longer holds
after section 1. It now wraps the pipe and takes `min(count_nip)` from
dig_on's per-cycle `'Count'` message; `n_sweeps` is a minimum. The `phases`
argument is gone (the call in `receiver_guard_checks.py` changes with it), and
the `tune.echo_window` `sweeps` help reads "minimum full phase cycles…".

## 3. Amplitude sweep keeps pulse positions

`Worker.exp_amplitude` in `awg_phasing_insys.py`. Pulses are selected by a
non-zero start increment, which was also applied as `delta_start`, so each
marked pulse moved every point (hardware: echo 345 → 432 ns). P1, the AWG
triggers (both branches) and LASER now get `delta_start='0.0 ns'`.

The same function also no longer sets an amplitude after the last point
(`else:` → `elif j + 1 < POINTS:`). The test pass used to reject a sweep
ending exactly at 100 %; the end-of-scan `awg_pulse_reset()` restores the
first amplitude.

## 4. Field sweep refuses P1 and LASER start increments

`Worker.exp_field` in `awg_phasing_insys.py`. The test pass already raised
`Please remove Start Increments for all pulses` for AWG triggers. It now does
the same for P1 (DETECTION) and, in the laser branch, LASER, matching
`phasing_insys.py`.

## 5. Phase correction: one Zero Order sign; First/Second Order are FFT-only

Both phasing tools. Since cdc8147 the First/Second Order controls are FFT-view
values (deg/MHz, deg/MHz²), but experiments still passed them to
`digitizer_demodulate` as time-domain rad/s and rad/s². A 9.2 deg/MHz value
left 2 % of the integral.
- `dig_on` FFT branch: `fft.ph_correction(..., -zero_order, -first_order * 1e-9, -second_order * 1e-18)`,
  so FFT mode rotates like the time trace and the Auto phase value carries over.
- AWG `exp*` methods: every `digitizer_demodulate(..., iq_freq, zp, first_order, sec_order, integral = True)`
  becomes `(..., iq_freq, zp, 0, 0, integral = True)` (12 sites).
- The `digitizer_insys.param` writer stores `First order: 0.0` and `Second order: 0.0`.
- Ranges: First Order ±5400 deg/MHz (15 µs windows); Points to Drop 0–37500 with suffix ' pts'.
- Phase Correction tooltip adds "First and Second Order affect only the FFT view."
- `atomize/documentation/functions/digitizer.md`: `digitizer_read_settings` and
  `digitizer_demodulate` text says the tools store only Zero Order.

**Also port by hand to the siblings' own phasing tools.** cdc8147 was checked
on six tools, so the siblings' non-Insys tools (for Spectrum or oscilloscope
digitizers) probably carry the same 2026-09-20 change and the same two bugs. The
ITC patch does not cover them. In each sibling, find them with
`Select-String -Path atomize\control_center\*.py -Pattern 'first_order \* 1e-9', ' deg/MHz'`
(the older copies in `other_versions/` do not have it), and in each tool found:
negate the three `ph_correction` arguments; pass `0, 0` instead of
`first_order, sec_order` in every experiment `digitizer_demodulate` call (the
count differs per tool); write `0.0` for First/Second order in its param-file
writer; widen First Order to ±360 × the longest detection window in µs
(±5400 for 15 µs); and give Points to Drop a range that covers that window
plus the ' pts' suffix. Check on hardware: in Live FFT with Phase Correction on,
the time-domain Auto phase value phases the FFT peak, and an experiment gives the
same integrals with First Order 0 and non-zero.

## Checks

- `sync_check.py` after porting.
- No `atomize/epr_auto/engine/snapshot.py` mirror change: presets, value
  formatting, `expand_phase_cycling`, worker signatures and `dig_start_exp`
  packing are untouched.
- Test mode: a Field sweep with a P1 start increment stops with the message
  above. A GUI amplitude sweep of 20 points from 5 % in 5 % steps passes, and
  21 points is refused.
- On a spectrometer: Accumulation mode shows roughly equal count_nip values,
  and an amplitude sweep with one marked pulse keeps the echo in place.
