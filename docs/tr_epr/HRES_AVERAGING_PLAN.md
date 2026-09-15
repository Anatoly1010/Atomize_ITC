# TR-EPR — High-Resolution Acquisition + Host-Side Shot Averaging (plan)

Project: transient (time-resolved) EPR on the ITC endstation, controlled by
`atomize/control_center/tr_control.py` with two Keysight DSOX2012A scopes
(`atomize/device_modules/Keysight_2000_Xseries.py`, `_2.py`; Ethernet, see
`device_modules/config/Keysight_2000_Xseries*_config.ini`).

Status (2026-09-15): **PLANNED, not started.** Gate 0 (duty-cycle measurement on the
real machine) must be passed before any code is written. Nothing in `tr_control.py`
has been changed for this plan.

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

| Config | len(y) | t_mean / s | t_max / s | 1/f_rep / s | shots missed |
|---|---|---|---|---|---|
| scope 1, CH1 | | | | | |
| scope 2, CH1 | | | | | |
| scope 1 + scope 2 | | | | | |
| scope 1 CH1+CH2 + scope 2 | | | | | |

### Gate 0b — segmented memory available? (only if Gate 0 is marginal)

- Query `*OPT?` on both scopes; look for `SGM`.
- If present: `:ACQuire:MODE SEGMented`, `:ACQuire:SEGMented:COUNt <p8>`, one
  `:DIGitize` captures p8 consecutive shots with no dead time; then loop
  `:ACQuire:SEGMented:INDex k` + `:WAVeform:DATA?`. Segmented works with Hres and
  Normal, **not** with Average. Measure the total capture + readout time for p8 = 10.
- If absent: decision is Average (status quo) vs. Hres with the missed-shot penalty.

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

## Open questions

- Laser repetition rate `f_rep` used in practice (needed for Gate 0).
- Do the scopes have the SGM option (`*OPT?`)?
- Typical windows of scope 1 and scope 2 (decides samples/point and the real Hres gain).
- Is `Atomize_NIOCH_Q/.../tr_control.py` (single scope, CH4) meant to get the same change later?

## Session log

- 2026-09-15 — Analysis of `tr_control.py` and the Keysight driver; plan written.
  Decision: do not implement until the duty cycle (Gate 0) is measured on the
  real machine.
