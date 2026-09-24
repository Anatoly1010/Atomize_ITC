# Sibling handoff — 2026-09-24

For a session on the Windows machine, where the sibling Atomize repositories
and `D:\Melnikov\11_Programming\atomize_sync\sync_check.py` live. Port the
changes below into every sibling that has the same files, then delete this
file.

Everything listed here is in the commit that adds this file:

```powershell
$c = git log -1 --format=%H -- docs/SIBLING_HANDOFF_2026-09-24.md
git diff "$c^" $c -- atomize/control_center/awg_phasing_insys.py atomize/control_center/phasing_insys.py atomize/control_center/phasing_messages.py > itc_2026_09_24.patch
```

In each sibling: `git apply --3way itc_2026_09_24.patch`. The files use CRLF
line endings; keep them. Skip a file the sibling does not have, and port a
hunk by hand when the surrounding code differs.

## 0. Prerequisite: complete live snapshots (commit 74674f3)

Section 3 edits the buffer message introduced by 74674f3
(`PHASE CYCLE EXCEEDS ADC BUFFER: LIVE PREVIEW UPDATES ONCE PER FULL CYCLE`).
If a sibling still prints `!!!TOO MANY PHASES FOR LIVE MODE!!!`, port 74674f3
first, including its `atomize/device_modules/Insys_FPGA.py` part (not yet
ported to the siblings as of 2026-09-23).

## 1. Auto phase / Auto window use the last complete trace

`Worker.dig_on` in `awg_phasing_insys.py` and `phasing_insys.py`. A live
readout without a complete phase cycle returns `None`, which the preview
stores as a NaN trace; Auto phase then reported "no signal in the integration
window" almost every time. The preview now keeps `last_trace` (a copy of the
last finite demodulated I/Q plus the Zero Order it used). Auto phase and Auto
window work on it, and a request waits until one exists. Confirmed on
hardware.

## 2. Auto window placement is stable

Same function. The boxcar argmax only locates the echo; the window is then
centred on the half-maximum centroid of the envelope (baseline = median)
inside it, iterated three times. Before, a window wider than the echo moved
by ±40 ns between clicks; in simulation it now moves by under 1 ns.

## 3. Buffer message: banner and log split

- Both workers append a third line to the long-cycle preflight message:
  `Traces update once all steps arrive and average any repeats, so noise can differ between traces.`
- `phasing_messages.py`: `MessageLog.appendPlainText` sends the first two
  lines of that message to the banner (new `pinned` signal; the unused
  `appended` signal is gone) and only the third line to the log. The banner
  text is unchanged: `LIVE MODE BUFFER · Phase cycle exceeds ADC buffer: live preview updates once per full cycle · ADC windows in buffer: N`.
  The banner has no right-click menu.
- Hardware background: with a 16-step cycle and 16 windows per buffer, a
  trace spans one or two buffers, so its baseline noise alternates by about
  √2. The echo itself is correct.

## 4. Centred button glyphs

Both phasing tools: `button_track` (T), `button_auto_window` and
`button_auto_phase` (A) now go through `_set_glyph_style` like the × buttons,
and the × buttons (`button_track_clear`, `button_reset_links`) use 16 px
instead of 17 px so they can centre exactly.

## Checks

- `sync_check.py` after porting.
- No `atomize/epr_auto/engine/` mirror change is needed: nothing here touches
  presets, value formatting, `expand_phase_cycling`, worker signatures or
  `dig_start_exp` packing.
- On a spectrometer: preview → Auto phase gives a Zero Order and a repeat
  click gives nearly the same value; Auto window lands in the same place on
  repeated clicks.
