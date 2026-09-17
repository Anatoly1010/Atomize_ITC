# TR-EPR — High-Resolution Acquisition + Host-Side Shot Averaging (plan)

Project: transient (time-resolved) EPR on the ITC endstation, controlled by
`atomize/control_center/tr_control.py` with two Keysight DSOX2012A scopes
(`atomize/device_modules/Keysight_2000_Xseries.py`, `_2.py`; Ethernet, see
`device_modules/config/Keysight_2000_Xseries*_config.ini`).

Status (2026-09-17): **REJECTED after Gates 0 and 1 on the real machine.** Hres gives
no measurable noise reduction on scope 1 (noise is preamp-dominated, see Gate 1) and
the per-shot host loop only just keeps up with the 10 Hz laser (Gate 0). Keep
`Average` mode. Nothing in `tr_control.py` has been changed. Raw data, scripts and
the figure of the 2026-09-17 session: `~/experimental_data/Melnikov/2026_09_17_scope_hres_test/` on the ITC box.

## Detection chain (as of 2026-09-15)

- Diode → preamplifier (DC–5 MHz, two identical single-ended outputs) → scope 1
  (1 MΩ input, high-impedance tap on the line) → scope 2 (50 Ω input, terminates
  the line). Chain order is correct; scope 2 must stay connected and on 50 Ω
  whenever scope 1 is used, otherwise scope 1 sees an open line and ringing after
  the laser spike.
- No field modulation, no lock-in. Scope 1 = fast time window, scope 2 = slow
  window (`t_step` vs `t_step_2` in the script).
- The two preamp outputs are copies of one single-ended signal; they cannot be
  used differentially for SNR (noise fully correlated). Keep the second output for
  the second scope / a second vertical range.

## What the script does today

| Item | Where | Behaviour |
|---|---|---|
| Acquisition type | `tr_control.py` 857–870 | both scopes `oscilloscope_acquisition_type('Average')` |
| Off-resonance averages p6 | 1120–1122 | `oscilloscope_number_of_averages(p6)` → `ACQ:COUNt` |
| On-resonance averages p8 | 1176–1178 | same, once before the field loop |
| One trace per field point | 1194–1196 | `oscilloscope_start_acquisition()` = `:DIGitize` → scope collects `COUNt` laser shots, returns one averaged WORD trace |
| Scan averaging | 1200 ff. | running mean over scans `j` in numpy; off-res trace subtracted |
| Record length | 872 | `oscilloscope_record_length(4000)` → 3839 real points in Average mode (driver `points_list_average_real`) |

Driver facts that matter (`Keysight_2000_Xseries.py`):

- `ac_type_dic = {'Normal': NORM, 'Average': AVER, 'Hres': HRES, 'Peak': PEAK}` —
  a single enum on the scope, **Average and Hres are mutually exclusive**.
- `oscilloscope_number_of_averages()` (line 286) sets `ACQ:COUNt` **only** in
  Average mode; in Hres it prints "Your are in HRES mode" and does nothing.
- `oscilloscope_record_length()` uses `points_list` (…, 2000, 5000, …) outside
  Average mode → a request of 4000 becomes 5000 in Hres.
- `oscilloscope_start_acquisition()` = `WAV:FORM WORD` + `*ESR?;:DIGitize;*OPC?`
  (blocking until the acquisition completes).
- No wrapper for `:CHANnel<n>:BWLimit` or segmented memory (`:ACQuire:MODE SEGMented`).

**Consequence:** flipping the string `'Average'` → `'Hres'` today gives one laser
shot per field point, p6/p8 silently ignored, record length 5000. Do not do this.

## Why Hres could help, and where it cannot

Hres averages the raw samples that land in each output point (box-car inside one
acquisition). It removes noise **above** the effective bandwidth
`f_eff ≈ f_sample / (2 · samples_per_point)` — i.e. only scope front-end noise
outside the 5 MHz preamp band. It does **not** reduce preamp/detector noise; only
shot averaging does that.

| Scope | Window (example) | samples / point | noise removed above |
|---|---|---|---|
| 1 (fast) | 40 µs / 4000 pts, 2 GSa/s | ~20 | ~50 MHz — small gain |
| 2 (slow) | 400 µs / 4000 pts, memory-limited ~250 MSa/s | ~25 | ~12 MHz — most of the scope noise band |

Average mode already returns >8-bit data (WORD of the averaged trace), so the
"more bits" argument for Hres is mostly moot here; the real gain is the in-shot
sample averaging, and it is worth it only if scope noise is not negligible against
preamp output noise (Gate 1 decides).

## Gates (in order)

### Gate 0 — duty cycle of host-side shot averaging (real machine, no code change)

Question: can the host complete `DIGitize` + WORD readout of one trace faster than
the laser period, for both scopes, over Ethernet? If not, Hres + host averaging
costs up to 2× measurement time per field point.

Procedure (Atomize GUI open, laser running at its normal repetition rate
`f_rep` = ___ Hz, scopes in their usual windows, trigger as in a real run):

1. Standalone script (do not touch `tr_control.py`), one scope at a time:
   ```python
   import time, numpy as np
   import atomize.device_modules.Keysight_2000_Xseries as key
   sc = key.Keysight_2000_Xseries()
   sc.oscilloscope_acquisition_type('Hres')
   sc.oscilloscope_record_length(4000)        # note the real value returned
   n = 50; t = np.zeros(n)
   for k in range(n):
       t0 = time.perf_counter()
       sc.oscilloscope_start_acquisition()    # waits for one laser trigger
       y = sc.oscilloscope_get_curve('CH1')
       t[k] = time.perf_counter() - t0
   print(len(y), t.mean(), t.std(), t.min(), t.max())
   ```
2. Record `t_mean`, `t_max`, and `len(y)` for: scope 1 alone, scope 2 alone,
   both scopes back-to-back in one loop (as `tr_control` would do with p9 = 2/3),
   and with `CH2` read as well (p9 = 3 path).
3. Repeat with `oscilloscope_record_length(2000)` and `(5000)` to see how much is
   transfer vs. fixed overhead.
4. Compare with the laser period `1/f_rep`. Expected outcome classes:
   - `t_max < 1/f_rep` for the combined loop → every shot caught; **Hres + simple
     loop is viable**, per-point time ≈ p8 / f_rep (same as now).
   - `1/f_rep < t_max < 2/f_rep` → every other shot missed; per-point time ≈ 2·p8/f_rep.
     Acceptable for the off-resonance point (p6), questionable for the sweep (p8).
     → need segmented memory (Gate 0b) or keep Average mode.
   - `t_max > 2/f_rep` → not viable without segmented memory.
5. Also note whether `t` is bimodal (trigger wait vs. readout) — a histogram of `t`
   tells the readout cost directly.

Fill in:

Measured 2026-09-17, scope 1 (`192.168.2.21`, DSO-X 2012A fw 02.67, options MEMUP,
SGM, BW10), laser trigger on CH2 at **f_rep = 10 Hz** (1/f_rep = 0.100 s), window
100 µs / position 40 µs (10 µs pre-trigger), CH1 15 mV/div 1 MΩ BWL on, both channels
displayed as in a real run. 40 shots per row; "missed" = iterations longer than
0.15 s. Scope 2 was not measured (not requested).

| Config (Hres unless noted) | requested → real points | t_mean / s | t_max / s | shots missed |
|---|---|---|---|---|
| scope 1, CH1 | 2000 → 1920 | 0.102 | 0.162 | 0–1 |
| scope 1, CH1 | 4000 → **3840** | 0.190 | 0.392 | 12 / 40 |
| scope 1, CH1 | 5000 → 3840 | 0.189 | 0.396 | 12 / 40 |
| scope 1, CH1 | 10000 → 7680 | 0.100 | 0.112 | 0 |
| scope 1, CH1 + CH2 | 4000 → 3840 | 0.212 | 0.638 | 6 / 30 |
| scope 1, driver pair `start_acquisition` + `get_curve` | 4000 → 3840 | 0.120 | 0.326 | 2 / 30 |
| Average, COUNt 10 (status quo) | 4000 → 3839 | 1.17 | 1.30 | – |
| Average, COUNt 20 (status quo) | 4000 → 3839 | 2.12 | 2.33 | – |

Breakdown of one Hres shot (second run, 8 shots per length): `:DIGitize` + `*OPC?`
0.06–0.075 s, `:WAVeform:DATA?` 0.015–0.025 s for every length up to 7680, and
`:WAVeform:PREamble?` 0.01 s *or* 0.12–0.17 s — the preamble query, not the
transfer, is what randomly pushes an iteration over the laser period. The driver's
`oscilloscope_get_curve` queries the preamble on every call, so a host loop is
at best marginal at 10 Hz (0.10 s per shot with no headroom) and in practice loses
25–50 % of the shots at 3840 points. In Normal mode `:DIGitize` alone takes 0.13 s
and every second shot is lost (5 shots/s).

Other facts from the run: Hres and Normal sample at 1 GSa/s, Average at 250 MSa/s;
Hres rounds 4000 to 3840 points (not 5000 as the driver's `points_list` assumed);
the driver's `*ESR?;:DIGitize;*OPC?` write left two unread responses, so every
acquisition logged `-410 Query INTERRUPTED` on the scope (harmless). Both fixed in
the Keysight 2000/3000 modules on 2026-09-17: `oscilloscope_record_length` now
sends the request and reports the value the scope actually set, and
`oscilloscope_start_acquisition` sends `*CLS;:DIGitize` (still non-blocking, so
two scopes are armed in parallel as before). The 3034T at `192.168.2.20` rounds
4000 to 3999 (Average/Hres) and 3829 (Normal).

### Gate 0b — segmented memory available? (only if Gate 0 is marginal)

- Query `*OPT?` on both scopes; look for `SGM`.
- If present: `:ACQuire:MODE SEGMented`, `:ACQuire:SEGMented:COUNt <p8>`, one
  `:DIGitize` captures p8 consecutive shots with no dead time; then loop
  `:ACQuire:SEGMented:INDex k` + `:WAVeform:DATA?`. Segmented works with Hres and
  Normal, **not** with Average. Measure the total capture + readout time for p8 = 10.
- If absent: decision is Average (status quo) vs. Hres with the missed-shot penalty.

Measured 2026-09-17: `*OPT?` reports **SGM present**. Segmented Hres, 3840 points:
10 segments captured in 1.04 s (no shot lost), readout 1.30 s (0.13 s per segment,
preamble-dominated as above) → 2.34 s total vs 1.17 s for Average COUNt 10. With 20
segments: 4.6–5.6 s vs 2.1–2.3 s for Average COUNt 20. Segmented removes the
missed-shot problem but the readout still makes it ~2× slower than Average unless
the preamble is read once per setup instead of once per segment (then ≈ 2.6 s,
still not faster than Average).

### Gate 1 — noise budget (10 minutes, no code)

Decide whether scope noise is even relevant:

1. Preamp input terminated (50 Ω), scope in its usual range/window, Normal mode,
   single shot: rms of the trace = `σ_preamp+scope`.
2. Preamp disconnected, scope input terminated: rms = `σ_scope`.
3. Same two with `:CHANnel1:BWLimit ON` (20 MHz analog limit).
4. Same two in Hres mode.

Do this for both scopes. If `σ_scope ≪ σ_preamp+scope` (say < 1/3), Hres and BWLimit
buy nothing measurable and the plan stops at "enable BWLimit, keep Average".

| Scope | mode | preamp terminated / mV rms | scope terminated / mV rms |
|---|---|---|---|
| 1 | Normal | | |
| 1 | Normal + BWL | | |
| 1 | Hres | | |
| 2 | Normal | | |
| 2 | Normal + BWL | | |
| 2 | Hres | | |

Done in situ on 2026-09-17 instead (bridge tuned, detector connected to CH1, laser
firing, the −0.7 mV transient buried in single-shot noise — all traces look flat), so
the rows above were replaced by a direct single-shot comparison, 10 shots per
cell, 3840 points, 15 mV/div. "baseline" = rms of the 10 µs pre-trigger part,
"hf" = rms of the point-to-point difference / √2 (noise above ~20 MHz).

| Scope 1, single shot | baseline / mV rms | hf / mV rms |
|---|---|---|
| Normal, BWL on | 4.06 | 1.45 |
| Hres, BWL on | 4.10 | 1.42 |
| Normal, BWL off | 3.96 | 1.62 |
| Hres, BWL off | 4.10 | 1.51 |

Neither Hres nor the 20 MHz bandwidth limit changes the single-shot noise: the
4 mV rms is preamp/detector noise inside the 5 MHz band, and scope front-end noise
above the Hres/BWL cut-off is negligible against it. The plan stops here.

20-shot traces (same settings, 3 repeats each, mean ± std; SNR not quoted because
the transient (−0.7 mV, see "Shots per point") is below the noise at 20 shots and the "peak" of every trace is the 4σ noise maximum):

| Mode | time per trace / s | baseline / mV rms | hf / mV rms |
|---|---|---|---|
| Average COUNt 20 (status quo) | 2.20 ± 0.10 | 0.85 ± 0.03 | 0.315 |
| Hres, 20 shots host-averaged | 3.96 ± 0.84 | 0.87 ± 0.03 | 0.325 |
| Normal, 20 shots host-averaged | 5.5 ± 0.6 | 0.86 ± 0.03 | 0.341 |
| Segmented Hres, 20 segments | 5.0 ± 0.4 | 0.97 ± 0.06 | 0.321 |

All four are at the 4.06 / √20 = 0.91 mV shot-noise limit; Average is the fastest.
One of the three segmented traces sat ~9 mV above the others (DC level shift of
the whole trace) — not investigated, possibly detector drift during that capture.

### Decision (2026-09-17)

Gate 1 fails (no noise gain) and Gate 0 is marginal (10 Hz laser, ~0.10 s per shot
with a randomly slow preamble query). **Keep `Average` mode in `tr_control.py`.**
BWL is already on for CH1 on scope 1 and makes no difference either. Gate 2 below
is kept for reference only and must not be implemented.

### Gate 2 — implementation (only after Gates 0 and 1 say yes)

Scope of the change, in `Atomize_ITC` only:

1. **Bandwidth limit** (independent of the rest; do it even if Hres is rejected):
   in the setup block after `oscilloscope_trigger_channel(...)`,
   `a2012.device_write(':CHANnel1:BWLimit ON')` (and CH2 for p9 = 3, and `a2012_2`).
   Optionally add `oscilloscope_bandwidth_limit(channel, state)` to the driver.
2. **GUI:** combo "Acquisition: Average / Hres" → new parameter p13 (saved/loaded
   with the other parameters in `open_file` / `save_file`; header line added).
3. **Setup:** `oscilloscope_acquisition_type(p13)`; call `oscilloscope_number_of_averages`
   only when p13 == 'Average'. Record length: either accept 5000 in Hres (arrays
   already use the queried `real_length`) or add 4000 to `points_list` in the driver
   after checking the scope accepts it.
4. **One helper replaces every `start_acquisition` + `get_curve` pair** (five call
   sites: off-res, forward sweep, backward sweep, × p9 = 1/2/3):
   ```python
   def read_trace(scope, ch, n_shots, mode):
       if mode == 'Average':
           scope.oscilloscope_start_acquisition()
           return scope.oscilloscope_get_curve(ch)
       acc = 0.0
       for _ in range(n_shots):
           scope.oscilloscope_start_acquisition()
           acc = acc + scope.oscilloscope_get_curve(ch)
       return acc / n_shots
   ```
   In Hres mode with two scopes, interleave the scopes inside the shot loop so
   both see the same laser shots (`DIGitize` on both, then read both) — this is
   also what the "scope 1 + scope 2" row of Gate 0 measures.
   If Gate 0b chose segmented memory, `read_trace` does one segmented `DIGitize`
   and averages the segments instead.
5. Scan averaging, off-res subtraction, plotting, saving: unchanged.
6. Mirror to `exp_test()` (test mode) and to `tr_two_fields.acquire` if it takes
   the scopes' traces through the same path.

Acceptance: same field sweep, same p6/p8/scans, in Average and in Hres; compare
(a) wall-clock time per scan, (b) rms of the off-resonance trace, (c) peak SNR of
the transient on both scopes. Keep Hres as default only if (c) improves on at least
one scope and (a) is within the budget agreed after Gate 0.

## Shots per point in Average mode (measured 2026-09-17, scope 1)

Question: is there an optimal `ACQ:COUNt` per field point, given the scope's digital
averaging, before the rest of the averaging is done host-side over scans?
Same settings as above (15 mV/div, 3839 points, 10 Hz laser). Noise = rms of the
10 µs pre-trigger baseline; "hf" = point-to-point rms / √2. Single shot: 4.08 mV rms
= 6.8 LSB (LSB 0.603 mV). Averaged WORD data carry 4 extra bits (step 0.038 mV).

| COUNt | baseline rms / mV | single / √N | ratio | time / trace | duty cycle |
|---|---|---|---|---|---|
| 2 | 2.92 | 2.89 | 1.01 | 0.5 s | 39 % |
| 4 | 2.16 | 2.04 | 1.06 | 0.7 s | 55 % |
| 8 | 1.50 | 1.44 | 1.04 | 1.0 s | 78 % |
| 16 | 0.99 | 1.02 | 0.97 | 1.6 s | 100 % |
| 32 | 0.76 | 0.72 | 1.05 | 3.2 s | 99 % |
| 64 | 0.57 | 0.51 | 1.11 | 6.4 s | 99 % |
| 128 | 0.34 | 0.36 | 0.95 | 12.8 s | 100 % |
| 256 | 0.26 | 0.26 | 1.00 | 25.7 s | 100 % |
| 512 | 0.11 (*) | 0.18 | 0.61 | 51 s | 100 % |
| 1024 | 0.12 | 0.13 | 0.92 | 103 s | 100 % |

Host-side averaging of scope-averaged traces at 256 shots total: 16 × COUNt 16 gives
0.23 mV, 8 × 32 0.23 mV, 4 × 64 0.26 mV, 2 × 128 0.22 mV — identical to a single
COUNt 256 trace (0.26 mV). The scope's averaging is therefore as good as numpy
averaging, and the output quantisation (0.038 mV / √12 = 0.011 mV) would only
matter above ~10⁵ shots. No "digital noise" floor was reached.

(*) The single 512-shot trace is anomalous: the DC level sat at 51 mV instead of
~15 mV and the transient amplitude dropped to a third; the detector level moved
during that 51 s acquisition (the DC level was also seen to drift by several mV
between other long traces). This, not the arithmetic, is the risk of a large COUNt.

There *is* a transient at the field used: a −0.7 mV dip lasting ~25 µs after the
laser spike, invisible at 20 shots (SNR 0.8), SNR 3 at 256 shots, SNR 6 at 1024.
The earlier statement that no transient was present was wrong; the 20-shot
comparison above stands, since it was a noise comparison.

Recommendation: `COUNt` (p6/p8) between 16 and 128 per point. Below 16 the scope
spends most of the time re-arming (duty cycle 39–78 %); above ~128 nothing is
gained in noise over doing the rest in scans, while a level drift during one long
acquisition corrupts the point and a stop loses all of it. Scans (host averaging)
cost only the per-point overhead, now mostly hidden under the field step.

## Readout overlap in `tr_control.py` (2026-09-17)

`oscilloscope_wait_acquisition()` (`*OPC?`) was added to the Keysight 2000/3000/4000
X-series modules. The forward and backward field loops in `exp_on` / `exp_test`
now arm the scope(s), wait for the shots, step the magnet to the next point, and
only then read the traces and plot, so the readout and plotting run during the
field settling instead of before it. The 80 ms settling wait is unchanged; the
data-to-field assignment, the end state of the magnet and the ramp back are the
same as before (verified in test mode with a traced two-sided sweep, p9 = 1/2/3).

Hardware check (2026-09-17, scope 1 only, 3428–3438 G step 2 G two-sided, COUNt 16,
off-resonance 3380 G): 12 points in 1.86 s per point with the overlap against
1.83 s per point with the previous code (run-to-run scatter ±0.1 s). **No measurable
gain**: after `*OPC?` the readout plus plot is only ~50 ms, and the remaining
~0.2 s per point is the 80 ms settling wait, the random wait for the first laser
shot (0–100 ms) and the BH-15 call, none of which can be hidden. The loop runs at
~87 % of the laser-shot limit for COUNt 16 and higher for larger counts. The
reordering is kept because it is verified and harmless, but it buys nothing.

## Open questions

- ~~Laser repetition rate `f_rep` used in practice~~ — 10 Hz (measured 2026-09-17).
- ~~Do the scopes have the SGM option (`*OPT?`)?~~ — scope 1 yes; scope 2 not checked.
- Typical window of scope 2 (scope 1 was 100 µs / 3840 points on 2026-09-17).
- Is `Atomize_NIOCH_Q/.../tr_control.py` (single scope, CH4) meant to get the same change later?

## Session log

- 2026-09-15 — Analysis of `tr_control.py` and the Keysight driver; plan written.
  Decision: do not implement until the duty cycle (Gate 0) is measured on the
  real machine.
- 2026-09-17 — Gates 0, 0b and 1 measured on scope 1 with the laser at 10 Hz and
  the tuned bridge on CH1 (standalone scripts, scope setup saved and restored via
  `:SYSTem:SETup`). Hres ≈ Normal ≈ Average in noise; host loop marginal at 10 Hz;
  segmented capture works but reads out 2× slower than Average. Plan rejected,
  `tr_control.py` unchanged.
- 2026-09-17 — Average-mode readout budget on scope 1 (COUNt 10/20/50): `:DIGitize`
  completes in N × 0.1 s + ≤ 0.03 s, `:WAVeform:DATA?` 0.02 s (WORD and BYTE alike),
  `:WAVeform:PREamble?` 0.01–0.27 s but back-to-back traces still take N × 0.1 s
  + 0.00–0.07 s, i.e. the scope is at the laser-shot limit; the slow preamble is the
  scope being busy after the acquisition, not transfer time, so caching it gains
  nothing. Only fewer shots, fewer field points, or hiding the readout under the
  magnet step can shorten a scan.
- 2026-09-17 — COUNt sweep 2…1024 and host-vs-scope averaging (section "Shots per
  point"); readout overlap implemented in `tr_control.py` with the new
  `oscilloscope_wait_acquisition()`; raw data in `~/experimental_data/Melnikov/2026_09_17_scope_hres_test/`.
