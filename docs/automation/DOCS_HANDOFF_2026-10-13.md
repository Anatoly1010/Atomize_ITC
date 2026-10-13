# Documentation handoff — session 2026-10-13

For a session on the Windows machine, where `../atomize_docs` lives. Read that repository's
`CLAUDE.md` before editing it. Delete this file once the change is published.

## Resonator-profile correction: `lo` parameter (Insys FM214x3GDA)

`Insys_FPGA.awg_correction()` takes a new keyword `lo = None`, the synthesizer frequency in MHz.
Each swept-pulse sample is now mapped to its absolute microwave frequency `lo − IF`, so the
resonator centre `f0` may lie anywhere in the swept band (for example f0 = 9381 MHz at 59 MHz IF
with the synthesizer at 9440 MHz). Without `lo` the LO is assumed at `f0`. The AWG phasing tool
passes `lo` from `bridge.param` automatically. Spectrum M4I 6631 X8 is unchanged.

In the published `awg_correction` reference (the page mirroring `atomize/documentation/functions/awg.md`),
apply the same four edits as the in-repo page:

1. Ideal-model example: append `lo = 9750` to the call:
   `awg_correction(only_pi_half = 'False', model = 'ideal', f0 = 9700, q_factor = 88, phase_correction = 'True', low_level = 16, limit = 23, lo = 9750)`
2. Replace "mapped to its instantaneous chirp frequency (flipped high-frequency-first for an `LO − RF` bridge)"
   with "mapped to its absolute microwave frequency `lo − IF` (an `LO − RF` bridge)".
3. After "where `f0` is the resonator centre frequency in MHz and `q_factor` the loaded Q." add:
   "`lo` (Insys FM214x3GDA) is the synthesizer frequency in MHz, so `f0` may lie anywhere in the
   swept band; without it the LO is assumed at `f0`."
4. Defaults line: add `lo = None` after `limit = 23`.

Do not add this to the endstation page.
