# DEER treatment — roadmap

This is a **backlog + reference**, not a review log. The staged code review
(S1–S5) is complete and **stopped** — there is no S6 review round. The detailed
per-session reasoning lives in git history and in
[ROADMAP_ARCHIVE.md](ROADMAP_ARCHIVE.md) (the full 2947-line session log up to
2026-08-07); the per-stage findings are in `REVIEW_S1…S5_*.md`. Quote numbers
from those, not from memory.

Remaining work is engineering, not auditing: land the fixes already specified and
measured, and port. The estimator's external check against DeerLab is **closed**
(2026-08-08); what is left is the uncertainty band, which no engine here yet
reports honestly. Treat every item below as a plain task with a known measurement
behind it.

## Files

| file | size | repos |
|---|---|---|
| `atomize/math_modules/deer.py` | ~3930 | all 5 (plain / ITC / NIOCH / NIOCH_Q / Cryomech) |
| `atomize/control_center/deer_analysis.py` | ~3500 | ITC / NIOCH / NIOCH_Q only (lead: ITC) |

The two ship as a pair — `band_degenerate`, the per-component bound flags,
`ic_railed` and now `background['prep']` are produced in `deer.py` and consumed in
`deer_analysis.py`. Run `~/atomize_sync/sync_check.py` before porting. **ITC is ahead as of
2026-08-13**: the `s7q` grid fix is uncommitted in its tree and not ported. Before
it, all five repos were in sync (`deer.py` byte-identical across all 5,
`deer_analysis.py` across ITC/NIOCH/NIOCH_Q; the only remaining `sync_check`
report is the unrelated `ITC_FC.py`) — see the port entries below.

## The shipped stack today

What is on, opt-in, or off, and what each thing is for. Every one is measured in
the archive session that shipped it.

| mechanism | default | what it does |
|---|---|---|
| `pre_zero='even'` (Tikhonov) / `'even_fold'` (Mellin) / `'crop'` (gauss) | **on** | keeps pre-t₀ samples that pass a mirror test, restoring parity a t₀ error would dump into short r |
| `reg_edges=True` | **on** | closes the regularization operator's free ends so grid-edge mass is not ~3× under-penalized |
| `clamp_alias=True` | **on** | drops distance-grid points below `(4·ν_dd·dt)^(1/3)`, which the sampling cannot resolve |
| `tau_max=None` (Mellin) | **on** | data-driven cutoff selector, not a pinned 30 |
| multi-Gaussian: multi-start seeding + width floor `r⁴/(27·ν_dd·T)` | **on** | the seeding strategy is load-bearing (removing the even-spread seed costs −0.008 overlap); the "27" is **calibration, not physics** (the derived `r⁴/(3·ν_dd·T)` costs −0.145) |
| per-component bound flags (`sigma_at_floor`/`_ceiling`, `center_at_bound`) | **on** | a parameter pinned on its box bound is reported as a bound, not a ± measurement |
| `ic_railed` | **on** | warns when the criterion never turned over inside "N max" — N is set by the spin box, not the data (25/28 real traces at default cap). The GUI message now reads this as *"not a few discrete Gaussians — prefer the Tikhonov/Mellin engine"* rather than "raise N max" (2026-08-08): on real YopO the railing is a correlated residual, not more modes, and the regularized engine is the DeerLab-default way to handle it (see the DeerLab cross-check). |
| `echo_head` (Tikhonov parabolic head) | **OFF** | guarded pair-averaged echo-top head; worth only +0.0016 now and declines itself at high noise |
| `bg_start_early`, `conc_implausible` | reported | the two calibrated background-reliability detectors, on every engine |
| `k_disagrees` | reported as a *note* | the two background routes differ — 56 % detection at 45 % false alarm, NOT a reliability verdict |
| `background['prep']` (gauss `lsq`) | **on** | the engine re-fits its background, so `joint_background`'s reliability keys judge the *starting* estimate; they are parked there and labelled, never recomputed (2026-08-12, `S5T-1`) |

## Recently landed

- **`resid-band` — the residual view had no noise band on the Tikhonov engines,
  and the wrong one everywhere else** (`deer.py` + `deer_analysis.py`,
  2026-08-14). **UNCOMMITTED and NOT ported.** Three parts, all display-side; no
  estimator moves (λ and r_peak on `sample1_labB` are unchanged to 4 decimals on
  all four engines).

  1. **`deer_invert` and `deer_invert_joint` now return `noise_level`.** The band
     at `deer_analysis.py:2987` needs `noise_level` or `sigma_noise`; only the
     Mellin and gauss paths supplied either, so on `sequential` and `joint` — the
     default engine — **no band was drawn at all** and the residual had no scale.
     One `_tail_noise(t, bg['V_norm'])` per return dict, mirroring `deer.py:2764`.
     Reported only, never fed back into the fit. On labB it reads 0.001294 against
     a point-to-point 0.001192, i.e. **1.08x** — the estimator is honest here and
     the harness README's tail-drift concern does not bite on this trace.
  2. **A second band at ±σ/√w for the smoothed overlay.** The view draws the raw
     residual *and* a boxcar-smoothed "coherent" curve, and the eye follows the
     smooth one — but the only band was ±σ, which belongs to the raw trace. On
     labB `w = 13`, so the band was **√13 = 3.6x too wide** for the curve being
     judged. Measured there: raw residual 1.19 σ, smoothed 1.23 σ/√w on `joint`
     (1.5 on Mellin) — mildly structured, but nothing on screen distinguished 1.2
     from 12. Also trims the smoothed curve by `w` at each end, since `mode='same'`
     zero-pads and dragged those points toward zero — spuriously good exactly where
     a band invites the reader to look.
  3. **The interpretation text no longer names a cause that is ruled out.** Four
     sites read a coherent oscillation as an over-smoothed P(r); the sweeps above
     say α, broadening and the background grid all fail to move it. The
     `residual_whiteness` docstring keeps the classical reading and both citations,
     then states the case it misses with the numbers; the GUI's `structured`
     verdict now says structured ≠ over-smoothed and points at the σ/√w band before
     α or the background; the view tooltip explains that each curve has its own
     band.

  Gate: `py_compile` both files; λ / r_peak unchanged on all four engines
  (0.3786/2.163, 0.3724/2.163, 0.3759/2.112, 0.3833/2.316); `noise_level` present
  on 4/4 engines (was 2/4); `gui_smoke_deer.py` **PASS** with 7 curves; an
  offscreen Tikhonov render **PASS** (`engine joint`, `noise_level 0.001315`, both
  bands drawn).

- **`labBC-xcheck` — our engines against DeerLab 1.2 on each lab's own published
  recipe** (harness only, `deer_benchmark/xcheck_labBC.py`, 2026-08-14). Sample 1
  is the ring test's sample "A" (`sample1_labG.DSC` names it "YopO Probe A"). The
  `*_bckg.dat` files are each lab's zero-time-corrected normalized trace with
  THEIR OWN (1−λ)B in column 2 — labB's starts at exactly −120 ns, its stated zero
  time — but neither carries the end cut, so the harness applies it.

  **labB** (t₀ 120 ns, 800 ns cut, hom-3D, bg 1/3), lab's own λ = **0.382**:
  ours `sequential` 0.379 / `joint` 0.372 / `mellin` 0.376 / `gauss` 0.383,
  **DeerLab 0.378** — every method inside 0.011 of the lab. P(r) overlap against
  DeerLab **0.907–0.946**, best for `joint` (0.946), which is the like-for-like
  engine since both co-fit the background. **labC** (cut at 3200 ns), lab's own
  λ = 0.349: ours 0.306–0.348, DeerLab 0.332, overlap **0.896–0.982** (again
  `joint` best). **Do not read labC's residual numbers** — after its cut only
  1.2 µs remains past 2 µs and the white-noise floor there (median 0.467 σ) is
  above both the data (0.298) and every model (0.104–0.153).

  **DeerLab gotcha worth keeping:** passing `experiment=ex_4pdeer(tau1, tau2)` on
  these traces **breaks the fit**. It primes pathway 1's reference time from τ₁ on
  the assumption that `t` is the raw pulse-position axis; these traces are already
  zero-time corrected, so on labC it ran away to **λ = 0.112, r_mean 6.21 nm**
  against 0.335 / 2.54 for our Mellin on the same trace. With the reference time
  free from a zero prior it converges to 5e-05 µs. Freeze it at 0 — correct here,
  and it takes labB from >20 min to **193 s**.

- **`s7q` — the Mellin engine was inverting on a truncated distance grid**
  (`deer.py` + `deer_analysis.py`, 2026-08-13). **UNCOMMITTED, and gated only at
  the first extension constant — see *Pending — do first*.**

  The caller's `r_max` was an estimator parameter here, not a display window:
  `_masses` area-normalizes over the grid it is handed and `F_fit = K@masses`, so
  truncating deletes the long-r mass the inverse recovered and rescales the rest.
  The forward fit then decays too fast, running coherently UNDER the data across
  the head and the first microsecond and over it in the tail. Tikhonov re-fits
  P(r) on the same grid and absorbs the cut, so only Mellin shows it — which is
  why it read as a Mellin-specific "residual near t0". **The GUI's own auto rule
  `r_max = 5*(T/2)^(1/3)` lands in the biased zone on essentially every real
  trace**, so the default configuration was the one that triggered it.

  Median |coherent residual| in sigma-of-the-mean, 28-trace corpus at the auto
  r_max, windows [(0.05,0.2), (0.2,0.5), (0.5,2.0)] us: HEAD **2.52 / 9.60 /
  15.59** -> **1.15 / 0.74 / 0.61**, Tikhonov control 0.62 / 0.43 / 0.31. Traces
  worse on the auto grid than on a widened one **27/28 -> 15/28**, so the grid
  dependence is gone rather than reduced. Dose-response on `sample1_labB` (signed
  area beyond the cut vs the 0.5-2 us residual): 4.5 % -> +60.3, **0.4 % -> +8.8**,
  0.0 % -> -0.6 — a 0.4 % truncation buys ~1 sigma of per-sample offset, because
  that mass sits where the kernel has barely decayed at 1 us. `r_mean` moved
  2.512 -> 2.681 nm over r_max 6.0 -> 8.0. **Not the tau_max selector**, though it
  is grid-coupled too: pinning tau_max at 22 or 32 reproduces every cell to two
  decimals, and at r_max 6.0 pinning is *worse* (+52.9 vs +47.1) — the selector's
  collapse to tau_max = 6 was partly compensating.

  Fix: the inverse, the normalization behind `F_fit`, the `_nonneg_cumulative`
  fallback, the `FIT_PEAK_TOL` test and the tau_max selector all run on an internal
  grid extended upward at the same `dr` to `r_max + max(10, 1.4*(r_max - r_min))`
  nm; the returned `P`/`P_norm`/`P_density`/`P_std`/MC band stay on the caller's
  grid with the caller-grid normalization, so no downstream consumer moves. New
  keys `mass_outside` / `grid_truncated` (`MASS_OUTSIDE_TOL` 2e-3) and a GUI note.
  **The extension length is measured, not guessed**: `+5 nm / 0.7x` leaves a third
  of the bias in the 0.5-2 us window (1.51 vs 0.55 at double, 0.55 again at
  triple), so `max(10, 1.4x)` is the convergence point.

  Gate at the *first* (`+5 nm`) constant, `~/deer_benchmark/s7q/`: invariance
  **0.000e+00** on seq / joint / general / gauss_lsq / gauss_none (29 traces);
  Mellin density bit-identical on the caller's grid at pinned tau=22/crop; the two
  keys on 29/29 results with **0/28** false alarms on a widened grid (healthy range
  -0.00316..+0.00140 against 2e-3); `gui_smoke.py` **ALL PASS**; self-test PASS.
  Synthetic catalogue (756 rows) **d = -0.0004, t = -1.02** — 724/756 rows
  bit-identical, only the 32 tau_max-moved rows change, 12 better / 20 worse, sign
  test p = 0.215.

- **`s7q`'s second half — nearest-twin `even_fold` pairing: measured and
  REJECTED**, i.e. reporting defect (6)'s obvious fix is a dead end.

  It failed the test it was written for. Mellin's echo head is ~30x more
  zero-time-sensitive than Tikhonov — on `sample1_labB` one 8 ns sample of t0
  error takes the 0-50 ns residual from +29 to -30 sigma-of-the-mean while joint
  stays inside ±5, and half a sample already costs +15. Nearest-twin pairing moves
  that scan's peak-to-peak by **0.2 %** (labB 59.71 -> 59.58, labC 48.39 -> 48.39,
  labD 115.85 -> 115.83, labF 49.17 -> 48.84). **The fold defect and the t0
  sensitivity are separate problems** — the ±1-sample swing is genuine
  misregistration against the pinned F(0)=1 analytic term, which no pairing rule
  can absorb. That is the finding worth keeping.

  And it costs overlap: vs the old pairing, both on the grid fix, **d = -0.0016,
  t = -2.60** over 756 rows, changing 380/756, 163 better / 217 worse, **sign test
  p = 0.0065**. Against that it bought a 3x head improvement at the operating point
  on exactly ONE real trace (labD z50 +39.69 -> +13.10 at frac 0; a three-arm run
  confirms that is the fold change, not the grid extension). Reverted —
  `_crop_pre_zero` is byte-identical to HEAD. **The roadmap's warning reproduces
  independently**: `even_fold` still beats `pre_zero='crop'` by **+0.0067** with the
  shipped pairing, against the archive's historical +0.0064 (t 5.2).

- **`S4-quick` — the gauss `deer_validate` N hole + three S4 note-queue items**
  (`deer.py` + `deer_analysis.py`, 2026-08-13). One behaviour change and three
  reporting fixes, in one gate.

  1. **`deer_validate(engine='gauss')` pins `n_gauss`** to the central trial's
     pick, exactly as it already pins `tau_max`/`n_tau`/`delta` for Mellin
     (`S4-1`). Left free, the component count is re-selected per trial and the
     band is part model-selection jump. Measured over the 9-trial sweep on 28 real
     traces: **2/28** mixed N on the default `lsq` route — but **25/28** on
     `bg_engine='general'`, which is the route whose band the GUI actually draws
     (`band_degenerate` is structural for a co-fitting background, so the `lsq`
     ribbon was never shown). The mixing is not marginal: `sample2_labG` swept
     `[2,1,1,1,1,4,4,4,4]`, `sample1_labC` `[3,4,2,2,1,1,1,1,1]`. On `lsq`,
     `sample2_labD` is the clean demonstration — eight trials at N=3, one at N=4,
     and the **entire 0.140 band was that one model switch** (pinned: 7.5e-06).
     Consensus P(r) and `r_mean` barely move on `lsq` (median |ΔP| ≤ 2.3e-05, the
     median absorbs a minority of trials); on `general` they move materially
     (median |ΔP| up to 0.72, `r_mean` up to 0.15 nm), and the band width moves
     **both ways** (8.43 → 1.96, 5.06 → 2.88, but 0.19 → 0.31), which is what
     removing a model switch does rather than a uniform narrowing. Each trial's
     count is now reported in `trials[i]['n_gauss']`.
  2. **`joint_background` reports `k_fit_failed`.** Both arms of `_fit_rate`
     swallowed a failure and returned the SEQUENTIAL `kref`, which makes
     `k_ratio` exactly 1.0 — indistinguishable from the two background routes
     agreeing perfectly. Now flagged, warned about, and added to `_PREP_BG_KEYS`
     so it travels with its siblings on the gauss `lsq` path; a non-finite `k`
     counts as a failure too (the NaN used to travel on).
  3. **The λ clamps are three named constants.** The four sites were never one
     number: `LAM_MIN` 0.02 everywhere, `LAM_MAX` 1.0 where λ comes from a fitted
     background amplitude (a physical bound — `_no_background` exists precisely
     for λ→1 data), `LAM_MAX_PINNED` 0.95 where it comes from a tail pin, which
     has failed rather than measured if it reads that high. Only
     `background_general` moves (0.98 → 1.0, joining the other background-model
     route); it needs g(0) < 0.05, which no real trace reaches.
  4. **The `'discrepancy'` and `'lcurve'` τmax selectors are removed**, with
     `noise_space` / `taumax_extend` / `extend_short_frac` and the resolution
     extension. Both lost to `'penalty'` and both were broken as recorded: the
     discrepancy threshold was floored at `min(sigma_fit)` so something always
     passed, making it plain `argmin(sigma_fit)` on 17/28 real traces — the exact
     over-fit it was written to avoid — and the L-curve scored curvature only on
     interior candidates, so it could never return either end of the grid and had
     no no-corner fallback. They **raise** rather than being deleted quietly:
     `deer_invert_mellin` ends in `**_ignored`, so a silent removal would have
     swallowed the argument and run `'penalty'` — the inert-guard trap below.

  Gate (`~/deer_benchmark/s4q/`): **max |ΔP| = |Δλ| = |Δk| = 0.000e+00** over 28
  real + 1 synthetic × 10 engine configs against `HEAD`; `k_fit_failed` present on
  87/87 joint-background results (HEAD 0) and fired on none; no λ-clamp flag
  changed state; all five removed arguments raise; the joint/Mellin validation
  paths bit-identical. `gui_smoke.py` **ALL PASS** — the flag renders on both the
  top-level and the labelled `prep` route, Mellin still auto-selects its cutoff,
  and the gauss validate path completes with all 9 trials at one N.

- **`general-2p` — `background_general` auto-fits the identifiable form**
  (`deer.py`, 2026-08-13). The backlog head, fixed. With neither `c` nor `d`
  supplied — which is what the GUI's *Auto (fit)* sends — the auto-fit now fits
  `g = a·exp(b·t)`, so `c = 0` and `a` **is** g(0): λ is measured, not extrapolated
  along the degenerate direction. Supplying `c` or `d` still fits all four (the
  caller is asserting a shape the tail cannot supply), and `fit=False` manual mode
  is untouched. The silent seed fallback is gone too: `fit_failed` is reported and
  warns, and `n_free` (2 / 4 / 0) says which model actually ran.
  Gate (`~/deer_benchmark/s6q/gate_general.py`, 28 traces × 5 trim settings):
  every other engine **0.000e+00**; on the general route **25 → 0** collapses,
  λ within 20 % of the joint engine **81 → 134** of 140, trim spread of λ
  **median 0.325 → 0.008** (>30 % on 14/28 → 5/28, which is the joint engine's own
  figure), and |Δr_mean| against joint **worst 4.235 → 0.530 nm**. The six cells
  still outside 20 % are all on traces where the *joint* reference itself falls
  apart under trimming (its λ moves 88–129 % and drops to 0.066–0.116), i.e. the
  trace rather than the fit. `gui_smoke.py` **ALL PASS**, including that the panel
  writes `c = 0` back and manual mode still offers all four boxes.

- **`S6-triage` — six of the eight triage cuts in groups 1–2** (`deer.py` +
  `deer_analysis.py`, 2026-08-13). **Every claim was re-measured first**
  (`~/deer_benchmark/s6q/repro.log`) and three did not survive contact — see
  *Corrections of record*. What landed:

  - **`_flag_not_deer_like`** (`robust-5`): two specific tells recorded on every
    engine result — `form_factor_implausible` (max|F| > 1.2, since a normalized
    form factor is bounded by F(0)=1) and `lambda_collapsed` (λ at or below
    `LAM_MIN`). Thresholds set from the healthy range, not guessed: over 84 real
    results max|F| spans **0.914–1.046** and λ **0.224–0.505**. Pure noise reads
    4.73 and is caught; the bare exponential fits λ = 0.0000 under `joint` and is
    caught. **The gate then found the real payoff, which the design never aimed
    at**: `bg_engine='general'` collapsing. On **4 of 29** traces its empirical
    g(t) swallowed the modulation, reaching max|F| 1.33 / 4.25 / 13.1 / **18.4**
    with λ at **0.040–0.258** of the joint engine's on the same trace (every other
    trace 0.52–1.16, median 0.94) — one of them reported as a 7.85 nm distribution
    with **half its mass on the grid edges**. Known gap, stated in the docstring: a
    smooth decay the background cannot absorb (that exponential under
    `bg_engine='none'`, a linear ramp) still passes.
  - **`xengine-2` — the blind spot is documented, the obvious fix is REJECTED.**
    Confirmed hard: on a 5.5 nm synthetic at `bg_start` 1.50 µs, Mellin returns
    4.598 nm (**0.90 nm short**) at 0.80 periods and is **not** flagged while the
    joint engine, only 0.42 nm short, **is** — the detector normalizes by the fit's
    own r_mean and the failure biases exactly that number short, so it is least
    sensitive where the fit is worst. Re-referencing to the trace-supported cap
    `5·(Tmax/2)^(1/3)` was measured and **fires 84/84** — the `k_collapsed` failure
    mode. A real repair needs the 1260-cell recalibration, not a swapped
    denominator; until then the docstring and `deer.md` say a pass is weak evidence.
  - **`batch-1`** — "Process all" no longer runs a validation sweep it then
    discards; the tick is restored afterwards and the summary panel says validation
    was not run. Note the filed **10.9×** cost is stale (it predates S2's
    `scan_lcurve` fix): re-measured at **~1.5×**. The waste is real either way —
    the sweep's own base result is bit-identical (`max|ΔP|` 0.000e+00) to the plain
    inversion the batch keeps.
  - **`me1-1`** — the printed `mean ± ME₁` is a noise-only a priori floor on a fit
    whose dominant error is model selection. Re-measured: moving "N max" over 2/3/4
    shifts the mean by **13.6–41.2×** the printed bar (filed as 88.7×). The shared
    moments tooltip now says so and names the multi-Gaussian case.
  - **`status-1`** — the status line keyed on `validate_flag` while the compute
    branch keys on `validate_flag and gmethod != 'mc'`, so Validate + Monte-Carlo
    announced a sweep that never ran. One-line fix, same condition.
  - **`docs-7`** — **both** citations were wrong, not one: `Dzuba, JMR 275 (2016) 1`
    → **J. Magn. Reson. 269 (2016) 113**, and `Matveeva et al., Z. Phys. Chem. 231
    (2017) 463` → **231 (2017) 671**. Fixed at all four `deer.py` sites, the GUI
    tooltip and the `deer.md` bibliography (which also gained the full titles).

  Gate (`~/deer_benchmark/s6q/`): **max |ΔP| = |Δλ| = |Δk| = 0.000e+00** over 28
  real + 1 synthetic × 6 engine configs; the three new keys on 174/174 results
  (HEAD 0); **zero alarms on the fitted-background engines**; every `general` alarm
  independently corroborated by the λ ratio, with the alarms at ≤ 0.258 and every
  quiet trace at ≥ 0.521. `gui_smoke.py` **ALL PASS**.

- **Gauss `mc` background-start validation stays OFF — decided 2026-08-13**
  (`deer_analysis.py`, comment only). `_gauss_compute`'s guard
  (`validate_flag and gmethod != 'mc'`) rested on two stated grounds; after
  `callsites-1` only one of them survives, and it is enough. Measured: the mc
  self-ensemble is the band `S5-4` put at **0.27–0.72 coverage against a nominal
  0.95** (0.00 when it collapses) — optimizer spread thresholded by a tolerance
  carrying no noise scale, so "it has its own band" is **false**; the sweep band
  on mc is real, not flat-valley jitter (**P_spread 0.329** over 9 trials against
  **5.2e-07** for the `lsq` run `band_degenerate` exists to disown); but the cost
  is ~9 × 76 s ≈ **11 min** per YopO trace against ~48 s for one `lsq`
  inversion. A ten-minute wait behind a checkbox that reads as free is the worse
  product, so the guard is untouched and only its **reason** is corrected — it now
  says cost, and says the ensemble band is the weakest of the three, not the
  strongest. No behaviour change, so no gate. Revisit if the trial grid is ever
  cut for mc.

- **`deer.md`'s `ic_railed` box now agrees with the GUI** (docs repo, 2026-08-13).
  It told the reader to raise `N max` until the criterion turns over; the GUI
  stopped saying that on 2026-08-08. It now says a railed selection means the data
  is not a few discrete Gaussians and points at the Tikhonov/Mellin engine, while
  keeping the measured fact that the criterion *does* turn over at N=5–7 once the
  cap is lifted — with the reason those extra components are not modes.

- **`callsites-1` — the gauss solver now reaches the engine** (`deer.py`,
  2026-08-12). `deer_invert(engine='gauss', method='mc')` dropped `method` and ran
  `lsq`: a different **estimator**, not a different search. `method` does double
  duty — α criterion on the regularized engines, solver on gauss — and the two
  name sets are disjoint, so it is now forwarded when it names a solver and
  ignored when it names a criterion. Stated in both docstrings and `deer.md`.
  This also **takes `S5T-1`'s `bg_cofit` branch out of latency**: `deer_validate`
  can finally validate `mc`. Gate (`~/deer_benchmark/s5t1/gate_callsites.py`, 6
  real + 1 synthetic, baseline = the S5T-1 commit): every existing route
  (`seq`, `seq_lcurve`, `joint`, `mellin`, `gauss_default`, `gauss_gcv`,
  `gauss_lsq`) **0.000e+00**; the two solvers differ by **0.295** in P(r), so the
  silent substitution was material; HEAD returned the lsq answer bit-exactly and
  the fix returns the direct-mc answer bit-exactly; and unpatched `deer_validate`
  now reports `band_degenerate=False` with **P_spread 0.329 vs HEAD's 5.2e-07** —
  six orders apart, which is the direct evidence the mc band was real and the
  structural disowning was wrong for that solver.

- **`S5T-1` full scope + the bundled `bg_cofit` fix** (`deer.py` + `deer_analysis.py`,
  2026-08-12). The multi-Gaussian `lsq` engine re-fits the background, so
  `joint_background`'s reliability keys described an estimate that no longer
  existed. They are now **moved, never recomputed** (recomputing `k_ratio` is the
  measured regression that got the original fix rejected) into
  `background['prep']` via a `_PREP_BG_KEYS` list, and all four consumers follow:
  the GUI panel prints them as one labelled *"the background this fit STARTED
  from"* note instead of as verdicts; `deer_validate`'s per-trial `flagged` vote
  reads `prep`; `joint_background` takes `prep_only=True` and reworded its
  RuntimeWarning; the docstrings and `deer.md` say which background each key
  judges. `bg_start_early` stays top-level (it is re-derived from the final P(r)),
  `A` is refreshed to `1 − λ_fit`, and the `mc` path is untouched — it never
  re-fits. Bundled: `deer_validate`'s `bg_cofit` no longer disowns the band for
  `method='mc'`, which inverts the *prepared* form factor and so does follow
  `bg_start`. That test reads the **solver off the base result**, not off
  `kwargs`: `deer_validate`'s own `method` is the α selector, and `deer_invert`
  drops the gauss solver entirely (triage's `callsites-1`), so the kwargs route
  would have been inert. Consequence at the time: the mc branch was correct but
  unreachable — the gate exercised it through a patched forwarder, and
  `callsites-1` (above, same session) then made it live.
  Gate (`~/deer_benchmark/s5t1/`): **max |ΔP| = |Δλ| = |Δk| = 0.000e+00** over 28
  real + 1 synthetic trace × 6 engine configs against `HEAD`, prep values
  bit-equal to HEAD's stale top-level ones, and `gui_smoke.py` **ALL PASS**.

- **2026-08-05 audit, items 3/4/5/7/9 + the batch clamp line** (`deer.py` +
  `deer_analysis.py`, 2026-08-10). `deer_validate` forwards `clamp_alias` (the
  `False` escape hatch raised a shape mismatch); `pre_zero` is honoured on every
  engine through a `None` "engine default" sentinel, with `pre_zero_engine` kept
  as the older spelling and the false "always crop" docstring corrected;
  `engine='joint'` forwards `head_level`/`head_cap`/`head_ratio_max`;
  `deer_validate` receives `echo_head` so ticking both no longer drops the head;
  the reliability shading reads a new `res['t_max_us']` (largest positive t)
  instead of `ptp(res['t'])`, which under `pre_zero='even'` included the pre-t₀
  span; the echo-head checkbox greys out under the three background models that
  drop it; "Process all" reports the alias clamp. Gate: **max abs Δ = 0.000e+00**
  over 28 real + 1 synthetic trace × 7 engine configs × 2 validate paths against
  `HEAD`, the gauss catalogue **100 % bit-identical** to the same-box baseline,
  and an offscreen GUI run ALL PASS (`~/deer_benchmark/s0805/gui_smoke.py`).
  Item **(8)**'s "the GUI never reads the `echo_head` dict" was **already fixed**
  before this session — `deer_analysis.py` reports all three outcomes; only its
  checkbox half needed doing. Item (6) deliberately left open.

- **S5 round-2 reporting fixes** (`deer.py` + `deer_analysis.py`) — bound flags,
  `mass`/`mass_fraction`, MC-band relabel, `ic_railed`, strict `s_hi*0.999` width
  cap + per-seed `_solve` guard + `ic_failed`, docstring corrections. Gate: **max
  abs Δoverlap / Δmean / Δcentre = 0.000e+00** over 156+144 synthetic + 28 real
  runs. Committed `f4e7c82`.
- **`S5T-9`** (`deer_analysis.py` only) — a refit queued during a fit used to drain
  as Tikhonov regardless of the requesting engine. Fix: `_deer_pending` carries the
  engine tag and the drain **dispatches on the tag**, not the shown engine (the V2B
  defect that converted an explicit *Run Tikhonov* into a gauss run); a
  `_live_update`/`_live_update_tikhonov` split so an α edit drives Tikhonov while a
  gauss result is shown; `_set_engine_panel()` marks a superseded engine's panel;
  `clear_all` clears `gauss_info`. **Validated** against the real file offscreen
  (`t9c_fix.py base` → all 5 scenarios correct; explicit Run-Tikhonov-behind-gauss
  returns `joint` with the gauss panel struck; reverse returns `gauss`; Mellin
  still renders). Committed 2026-08-08.

- **DeerLab `dd_gaussN` cross-check — DONE 2026-08-08, the estimator is externally
  validated.** Matched-N (`dd_gauss`/`dd_gauss2`/`dd_gauss3`), matched conventions
  (reftime 0, same crop/alias grid/echo-top, `bg_hom3d` κ·D = 9.974e-4 to 5 digits).
  **Synthetic, known truth (20 runs):** Atomize–truth **0.950** vs DeerLab–truth
  **0.949**; engine agreement 1.000 at N=1,2 and 0.949 at N=3, the only
  disagreements being local-minimum coin-flips going *both* directions. **Real YopO
  (12 DL traces):** ov(ship~DL) **0.999 / 0.957 (median) / 0.887** at N=1/2/3; N=1,2
  equivalent, N=3 scatter is genuine ill-posedness (both engines, the criterion-rails
  regime). **Decisive corroboration:** in DeerLab's *own* free box, **8/12** N=3 fits
  put a component above r_max (up to ~19 nm) — the far-mass pathology is not an
  Atomize bug, an independent implementation does the same, and the round-2
  `center_at_bound` flag is the honest report of it. Verdict + numbers:
  `~/deer_benchmark/s5_gauss/deerlab_x/VERDICT.md`; harness `synth_xcheck.py` /
  `real_xcheck.py` / `dlx.py`. Dataset: `~/deer_benchmark/synth/gauss/`.

### Ports

Byte-identical straight file copies from ITC, each landed on the repo's default
branch (branch → ff-merge), **not pushed**. `deer_analysis.py` lives only in
ITC / NIOCH / NIOCH_Q. `sync_check.py` clean after every one of these, apart from
the unrelated `ITC_FC.py` (`Sibir_1.py` on the 08-08 round).

| change | ITC | plain | NIOCH | NIOCH_Q | Cryomech | docs |
|---|---|---|---|---|---|---|
| `general-2p` (`deer.py` only) | `62ff610` | `541c840` | `fa2a3f4` | `2693a25` | `3974046` | `f366a9f` |
| `S6-triage` | `6a6f299` | `48952dd` | `c9724ea` | `9b4bfd2` | `8ff1edd` | `e621bab` |
| `mc`-comment + `ic_railed` docs | `f177bd1` | — | `d6f4bb4` | `7e07b05` | — | `5857330` |
| `S4-quick` | `4bf5b29` | `6a3a104` | `c16c7e1` | `7dcdd67` | `6d36153` | `e2b7f66` |
| `callsites-1` | `ad14dfc` | `755939c` | `c84425a` | `393abc2` | `41f51c9` | `c905aa4` |
| `S5T-1` | `0c86b21` | `35be646` | `14e4307` | `eb9d6db` | `ad4285d` | `640f053` |
| round-2 + `S5T-9` + `ic_railed` reframe (08-08) | `f4e7c82` `0a61a3e` `3cd7c83` | `ba0d70e` | `87d9bec` | `359f03d` | `937d995` | — |

**`s7q` is NOT ported** — see *Pending — do first*.

## Pending — do first

The stack is **no longer in sync** — `s7q` sits uncommitted in the ITC tree and is
not ported (item 1 below closes that). Otherwise nothing is blocked: the
estimator's external check is closed, `S5G-4` and the gauss `mc` validation
question are settled, the
2026-08-05 audit is down to its one behaviour-change item, and `S5T-1` /
`callsites-1` / `S4-quick` / `S6-triage` / `general-2p` are landed. The triage
queue is spent apart from `xengine-3`, which needs re-filing before it is worth
anything.

Ranked, from the backlog below:
1. **Close out `s7q`.** The grid fix is uncommitted and its full gate ran at the
   FIRST extension constant; the constant was then raised to `max(10, 1.4x)` on
   the convergence measurement, with only the corpus and the self-test re-run at
   it. In order: **re-run the 756-trace synthetic gate** — the one that matters,
   since the tau_max selector now scores on the extended grid and a longer
   extension can move more than the 32 rows that shifted at `+5 nm` (harness ready:
   `~/deer_benchmark/s7q/fold_bench_x2.py`, 2-arm, ~28 min on 4 cores; acceptance
   is that `d = -0.0004, t = -1.02` does not get materially worse); re-run
   `gate.py` and `gui_smoke.py`, where invariance and identity should hold in
   principle but the `mass_outside` values and the false-alarm count do move;
   check the cost, since the working grid is now ~2.7x the caller's and the Mellin
   inverse scales with `len(w)*n_tau`; **port** to the other four repos and run
   `sync_check.py`; then **update `atomize_docs`**
   (`docs/functions/math_modules/deer.md`) — document `mass_outside` /
   `grid_truncated`, say that `r_max` is an estimator parameter for this engine
   rather than a display window, and **fix the stale `tau_max=30.0` in the
   `deer_invert_mellin` signature block**, which the prose below it already
   contradicts.
2. **The residual bootstrap** (uncertainty item 2) — biggest lever in the file,
   and the right answer for the `ic_railed` / N-undetermined case too.
3. **Say the validation band is drawn at one fixed N** — cheap, and `S4-quick`
   made it true.
4. **Catch a smooth non-dipolar decay** — the gap `_flag_not_deer_like` leaves.

## Pending — backlog

Open findings. Each carries its own measurement in the archive / `REVIEW_S5`.
None needs another review round; they need a fix and a gate.

**Real-data residuals — the 2026-08-13 item is CLOSED and was wrong in both
directions (2026-08-14, `diag_long_t_osc.py` / `diag_short_r_arms.py` /
`xcheck_labBC.py`).** Its two candidate explanations were (a) ESEEM and (b) an
unfitted short-r dipolar component, with "the frequency is field-dependent under
(a)" as the discriminator. Neither survives, and neither does the discriminator.

- **The filed discriminator cannot be run on this corpus.** Every ring-test lab
  is Q-band: `A1CT` spans **1.1860–1.2291 T (3.5 %)** against a measured line
  spread of 1.15–13.68 MHz. The field lever arm is ~1000x too short. The `.DSC`
  files sitting unread beside the `.dat` traces carry this, and much more.
- **(a) ESEEM is out, on two independent tests.** The amplitude at each trace's
  own ²H Larmor line is a **sample** property, not a **lab** property —
  sample1 0.34/0.15/0.63/0.99/0.54/0.62 σ across labs A–F, sample2 ~0.32, samples
  3 and 4 ~0.12 — and `labF` is the clean control, same lab and same `dt` = 8 ns
  for all four mutants at 0.62 / 0.16 / — / 0.26. And ²H was **designed out of the
  acquisition**: 26 of 27 traces run `m = 8` observer-τ steps of `d31 = 16 ns` =
  **128 ns**, against a ²H Larmor period of **124.5–129.0 ns** at these fields, so
  the residual Dirichlet suppression is 0.2–2.8 % — and the observed amplitude does
  not follow it (**corr = −0.07** over 26 traces; ESEEM needs it strongly positive).
- **(b) is out as filed, and the sign is the interesting part.** Splitting the
  spectrum of the DATA's form factor from the MODEL's, past 2 µs: over 27 traces
  the model carries **less** 4–12 MHz than the data (0.200 vs 0.385 σ), so nothing
  is generally "missing". On sample 1 alone the ratio is **0.95**, and on
  `labB`/`labE`/`labF` the model carries **more** than the data — the fit ripples
  where the trace does not.
- **"Both engines reproduce it to within one FFT bin" is too strong**: **4 of 10**
  strong lines agree within 0.5 MHz. The filed 5.1–6.9 MHz moves to ~6–8 MHz once
  the trace decay is Hann-windowed out of the periodogram.
- **What it actually is, from labB at labB's own published recipe** (t₀ 120 ns,
  800 ns cut, hom-3D, bg at 1/3): the data's own 4–12 MHz amplitude is **0.321 σ
  against a white-noise 95th percentile of 0.312** — i.e. *not significant*; the
  earlier evidence for a real data oscillation was a periodogram peak/median ratio
  of 7.3, which is not a significance test. The model's is 0.51–0.60 σ and a model
  has no noise, so it is all structure: the fitted 2.16 nm peak's own
  ν_dd = 5.1 MHz still ringing where the data is noise-dominated. Data-minus-model
  is then coherent **by construction**, with nothing inadequate about the fit.
- **It is not suppressible, and that is measured, not assumed.** α over **32x**:
  −14 % on the ripple, +18 % on the full-trace residual. Direct P(r) broadening to
  w = 0.35 nm: −25 % at **3x** the full-trace residual (and the peak is already
  FWHM 0.867 nm — there is no narrow feature to blame). Deleting all P(r) below
  2 nm: −19 % joint / −30 % Mellin, with 0.41–0.47 σ surviving. labB's entire
  background validation grid (start 1/3–2/3 x dimension 2–3, 18 cells): **±5 %**.
  Damping it means changing the FORWARD MODEL, not the inversion.
- **DeerLab 1.2 does the same thing**, at 1.58x data against our joint 1.63x, so
  it is not an artifact of this implementation. See the cross-check entry below.
- **NOTE** the 28-trace corpus residual numbers quoted throughout this file are
  dominated by this band on the sample-1 traces — that part of the old item
  stands. `sample1_labD` may still be a genuine data oscillation (0.87 σ over 469
  points) and is NOT the same case as labB; the old item lumped them.

  *Follow-up, `diag_mellin_levers.py` 2026-08-14:* **"Mellin has an excess ripple"
  does not generalize, and one of the two candidate levers is inert.** Over the six
  usable sample-1 traces at the GUI's own auto window the model's 4-12 MHz
  amplitude is **0.585 σ for Mellin against 0.623 for joint** — Mellin is the
  *lower* of the two. The 0.590-vs-0.516 excess is specific to **labB at labB's
  recipe**. What does generalize is that Mellin fits worse overall: rms 1.598
  (t > 2 µs) / 1.605 (all) against joint's 1.337 / 1.282.

  - **`wiener` is a dead lever here.** 0.01 / 0.03 / 0.10 / 0.30 move the ripple
    **−0.1 / −0.2 / −0.6 / −1.7 %**. It damps the inverse filter's noise gain, and
    the ripple is not propagated noise, so there is nothing for it to bite on. Do
    not re-try it for this.
  - **`fit_rmin_abs` works on the ripple and the cost is superlinear.** 2.2 →
    −18.5 % ripple at rms_all 1.605 → **1.864** (+16 %); 2.5 → −38.4 % at **4.285**
    (2.7x); 3.0 → −49.6 % at **9.873** (6x). Only 2.2 is arguably a trade rather
    than a wreck. Note `fit_rmin_width` alone cannot lengthen the taper — the
    window is `[r[0], r[0] + min(fit_rmin_abs - r[0], fit_rmin_width)]`, so on the
    GUI's 1.5 nm grid bottom `fit_rmin_abs` is the binding bound.

  **And then `fit_rmin_abs` turned out to be an accuracy fix, not a trade.** The
  synthetic gate at 2.2 (156 rows): overlap **0.8793 → 0.8829**, **147 better / 3
  worse / 6 same**, every condition up (easy 0.9230 → 0.9249, hard 0.8564 →
  0.8603, nobg 0.8586 → 0.8635), residual slightly down, and no case changed its
  δ. So the taper window has been too short all along and the "+16 % full-trace
  residual" that looked like the price is not an accuracy cost.

  **2.1 is the operating point, not 2.2** (`bench_resid_real`, 28 traces, regional):

  | variant | head | head mean | post | pre | full | DW |
  |---|---|---|---|---|---|---|
  | shipped (2.0) | 2.576 | **+0.32** | 1.639 | 4.717 | 1.891 | 1.106 |
  | **2.1** | **2.417** | **+0.01** | 1.638 | 4.893 | 1.913 | 1.100 |
  | 2.2 | 2.504 | **−0.51** | 1.696 | 5.317 | 2.020 | 1.054 |

  The head **mean** — the coherent echo-top offset, the systematic that matters —
  crosses zero between 2.1 and 2.2, so 2.1 is near an optimum rather than a
  compromise: it removes the shipped +0.32 σ bias where 2.2 overshoots to −0.51 σ.
  At 2.1 the fitted region is untouched (post 1.638 vs 1.639, **6 better / 3
  worse**) and head rms is the best of the three; the full-trace +1.2 % is entirely
  the pre-t₀ block (4.717 → 4.893), which is the echo-symmetry display quantity and
  not a fit residual (`README_resid.md` rule 3).

  **Both values clear the synthetic gate, monotonically** (156 rows): 2.1 gives
  **0.8793 → 0.8810**, 142 better / 3 worse / 11 same; 2.2 gives **0.8829**, 147 /
  3 / 6. So 2.2 is the better *accuracy* setting and 2.1 the better *forward-fit*
  one, and **2.1 is what shipped** — the overlap difference is 0.0019 on a
  synthetic corpus, while 2.2's −0.51 σ head-mean bias is a coherent systematic on
  every real trace, and this file has rejected changes for exactly that before
  (`s7q`: "running coherently UNDER the data across the head").

  **`fit_rmin_abs` is not a minimum distance**, and the entry above is easy to
  misread as one. The grid bottom is the minimum (raised further by `clamp_alias`
  to `(4·nu_dd·dt)^(1/3)` — 0.941 nm at dt = 4 ns, 1.185 at 8, 1.493 at 16, 1.882
  at 32, so on sample 1 it is not binding against the GUI's 1.5 nm). What
  `fit_rmin_abs` sets is the top of the raised-cosine ramp, which runs from **0 at
  the grid bottom** to 1; mass below it is attenuated, not cut. A hard floor there
  is the already-rejected `rmin-2.0` (corpus 1.671 → 2.082). Weights on the GUI
  grid: at r = 1.9 nm, **0.905 (2.0) / 0.750 (2.1) / 0.611 (2.2)**; at 2.0 nm,
  1.000 / 0.933 / 0.812. Sample 1's peak sits at 2.11-2.16 nm with FWHM 0.867, so
  what the ramp bites is its **short-r flank**, not the peak (0.992 even at 2.2) —
  which is the mechanism behind the head-mean sign flip: cut too much of the flank
  and F_fit loses its fast-decaying kernels, decays too slowly, and sits above the
  data at the echo top.

  **`fit_rmin_width` had to move too, or the change is inert.** The window is
  `[r[0], r[0] + min(fit_rmin_abs - r[0], fit_rmin_width)]`, so at the shipped
  width 0.5 a `fit_rmin_abs` of 2.1 on a 1.5 nm grid still gives the OLD ramp
  [1.5, 2.0] exactly. Both defaults moved: **2.0/0.5 → 2.1/1.0**, which is what
  both benches ran. Both benches used a 1.5 nm grid bottom, so grids starting
  lower are extrapolation — the width cap now binds only below r[0] = 1.1 nm.

  **Landed 2026-08-14, UNCOMMITTED and NOT ported.** Gate: `py_compile`; defaults
  read 2.1 / 1.0; no caller anywhere in the repo pins either, so the GUI and
  `epr_auto` inherit it; on labB λ 0.3759 and r_peak 2.112 are unchanged with
  P(r < 2 nm) 0.0988 → 0.0856 and r_mean 2.623 → 2.636; `gui_smoke_deer.py`
  **PASS**. The `deer.md` prose says the constant is calibration and that neither
  parameter is a minimum distance.

**Multi-Gaussian (S5):**
- **Report that the component count is unstable across the background sweep.**
  Opened by `S4-quick`: pinning `n_gauss` is right (the band must measure
  background sensitivity, not model selection), but the old free-N behaviour
  *accidentally* surfaced N instability as a wide band, and the pin hides it —
  on `bg_engine='general'` **25/28** real traces re-select N across the sweep,
  several spanning the whole 1–4 range. That is a real reliability signal and it
  now has no reporting route. Cheap version: a second per-trial fit at free N
  purely to record the count (doubles validation time, so it wants to be opt-in);
  cheaper still: say in the GUI that the band is drawn at one fixed N. Numbers:
  `~/deer_benchmark/s4q/mix_general_N.log`.
- Triage's remaining cuts-for-cap, reasons in
  `~/deer_benchmark/s5_persist/triage_queue.json`: **`xengine-3`** — but see
  *Corrections of record*: its filed claim (joint and Mellin take λ/k *verbatim
  from the same call*) is false on today's code, and the surviving point is that
  the two share an estimator and a code path, so their agreement is not
  independent corroboration. **Re-file with that wording and a number before
  acting on it.** (`callsites-1`, `xengine-2`, `batch-1`, `me1-1`, `ci-1`,
  `status-1`, `robust-5`, `docs-7` are **done** — see *Recently landed*.)
- **Catch a smooth non-dipolar decay.** `_flag_not_deer_like` catches the loud
  failures but not a bare exponential under `bg_engine='none'` (λ 0.560, |F| 1.003
  → 6.32 nm) or a linear ramp (0.318, 1.029 → 6.75 nm). The obvious test — no
  oscillation in F — would also trip a genuinely broad P(r), so it needs its own
  false-alarm run over the real traces first.
- **Recalibrate `bg_start_early` on a non-circular reference distance** (1260
  cells, the original sweep). The swapped-denominator shortcut is already
  measured and rejected (84/84). Until then the detector's pass is weak evidence.

**Background engines — nothing open here.** Kept as the measurement record behind
`general-2p` and its two rejected alternatives; do not re-open without new data.

- **Why `background_general`'s auto-fit was degenerate — λ was an extrapolation
  from parameters the tail window cannot identify.** Investigated and **FIXED**
  2026-08-13 (`~/deer_benchmark/s6q/general_*.log`, fix in *Recently landed* as
  `general-2p`); this is the same defect `S6-triage` first saw as "collapses on
  4/29 traces", but bigger and with a clear mechanism.

  *Mechanism.* λ = 1 − g(0) = 1 − a·exp(b·c). Only the product `b·c` reaches g(0),
  and it is fitted where `d^t` has already decayed to a few percent, then applied
  at full weight at t=0. Fitted `c` comes back as −642 / +25 / −83 / −88 against
  `b` ~ −0.001: individually meaningless. On `sample2_labG` that multiplies the
  baseline by e^0.59 = 1.81, so g(0) = 1.22 > 1, λ goes negative and clamps.
  `sample3_labA` is the same degeneracy with `a → 0.0000` against `b·c → +20.7`.
  The existing `d_lo` guard measures the term's decay *across the window*, not
  *from t=0 to the window*, so it never binds.

  *Identifiability, measured.* `curve_fit`'s covariance (which the shipped call
  throws away) says the four coefficients are not separately determined:
  **|corr(a, c)| median 0.986**, above 0.99 on 6/15, and a covariance condition
  number of **2.9e23** against **2.2e2** for the 2-parameter form — numerically
  singular, so the reported per-parameter errors are meaningless in both directions
  (`c` at 6e-17 on one trace, `b` and `c` at 155× their own value on another). `b`
  is the one genuinely measured coefficient; `d` sits on its lower bound on 4/15.
  Roughly **two determined degrees of freedom out of four**.

  *And half the time it does not converge at all.* On **13 of 28** traces
  `curve_fit` raises `maxfev` and the `except Exception: popt = p0` fallback
  silently substitutes the SEED — `c = 0`, i.e. the log-linear 2-parameter fit.
  The other 15 converge into the degenerate valley with `c` = −1.3e5 / −2.2e5 /
  −9.5e4 / −7.1e4 / −5778 / −1517 / −642. So the engine runs one of two quite
  different models per trace, chosen by whether the optimizer gave up, with nothing
  in the result to say which — and the traces that behave well are the ones where
  the fit FAILED. This also explains the AICc split below: the 14 traces where the
  4-parameter form is not preferred are the fallbacks, with RSS identical to the
  2-parameter fit by construction.

  *Scale.* Not 4 traces — across five trim settings λ moves by **>30 % on 13/28**
  traces (worst 3.6×), oscillating in and out of the clamp: `sample4_labA` gives
  0.453, 0.453, **0.020**, 0.020, 0.020 and `sample3_labG` gives 0.342, **0.020**,
  0.334, **0.020**, 0.020. **15 of 140** trace×trim combinations collapse. The
  reported distance follows: `sample2_labG` flips between **3.75 and 7.85 nm** on
  two points of trim. Trimming does not fix it and is not monotone (collapse count
  by trim: 3, 5, 4, 5, **8**, 4, 6 …), so no operating procedure helps.

  *The fix this pointed to, and what shipped.* Auto-fit the identifiable
  2-parameter form `a·exp(b·t)` (where `a` **is** g(0)) unless the caller supplies
  `c`/`d`, keeping the 4-parameter form for the manual case where the user asserts
  the shape. Pre-fix bench over the same 28 traces × 5 trims: spread of λ
  **median 0.008 vs 0.276**, **0/140** collapses vs 15/140, λ within 20 % of the
  joint engine on **133/140** vs 81/140, r_mean agreeing with joint to a **median
  0.004 nm**. Its residual instability (5/28) is *exactly the joint engine's* on the
  same traces, i.e. real trace behaviour rather than engine degeneracy. The shipped
  gate reproduced this end-to-end (25 → 0 collapses, 81 → 134/140) — see
  `general-2p`.

  *The cost, stated plainly.* The two extra parameters are **not** worthless where
  the fit converges: AICc prefers them on **14/28** traces (ΔAICc to −320) and they
  cut tail RSS by a median 7 %, best 66 %. But that better tail description is
  bought along a direction the data does not constrain, which is exactly why λ
  swings. And for the 13 fallback traces the proposed fix changes **nothing** — it
  is already what runs, just deliberately instead of by optimizer failure, and
  reported instead of silent. That is the conclusion: **this engine's extra
  flexibility is a manual-mode feature**, because a tail-only window cannot
  identify a term that has decayed inside it.

  Whatever is done about the model, two things are defects on their own: the fit
  **discards `pcov`** so nothing can report that a coefficient is undetermined, and
  the **`except Exception: popt = p0` fallback is silent** — a failed fit and a
  successful one are indistinguishable in the returned dict.

**Reporting defects from the 2026-08-05 audit — only (6) is left:**
- (6) `'even_fold'` pairs by `searchsorted`, so an off-grid t₀ folds outward
  (~74 % of dt at the echo top). **Fixing it re-opens the +0.0064 that justified
  the Mellin default** — needs a benchmark re-run, not a one-liner. This is the
  only one of the ten that is a behaviour change rather than a reporting fix.

**S4 note queue (unverified, each carries the reviewer's numbers):**
- widen the τmax candidate grid `[6…40]` → `[3…60]` (+0.017 mean overlap, needs a
  boundary flag);
- guard `_masses` relatively (`area < η·positive_area`) not at the useless 1e-12;
- decide `du=0.005` as default (+0.016 overlap at 1.46× cost — data-driven rule
  rejected);
- `joint_background` defaults `bg_start` to 0.6× span while every other engine
  uses 0.5× (invisible from the GUI, visible to scripts/mirrors).

## Uncertainty backlog — "a band that deserves the name"

S2 did the zero-risk half (no band claims coverage it lacks). These fix specific
measured holes; neither is a true CI on its own (a band centred on a regularized
estimate cannot cover the truth at the mode — the dominant error there is bias).
Judge against the existing coverage harnesses `~/deer_benchmark/{sk1_ci,sk2_cicov,sk1_cicov2}/`.

1. **Propagate the joint fit's λ/k covariance.** The joint band is **7–8.6× too
   narrow** where the identical formula is honest to ~1.3× in sequential mode —
   `tikhonov_ci` conditions on a background and λ that are themselves fitted.
   Either propagate the rate-fit covariance into the linear band, or bootstrap
   (item 2). Do **not** re-fit τmax per realization (folds a discrete selection
   into a Gaussian summary). Acceptance: band/scatter within ~1.5× at k=0.05 and
   k=0.30, sequential unchanged.
2. **Residual-bootstrap the whole pipeline, on demand.** Resample residuals, refit
   bg+λ+P(r) per trial, percentile bands. ~1.6–1.8 s per inversion under load → a
   few minutes for 200 trials. A **button**, never the live path; `rThread`. Be
   explicit in the UI that it does not fix the mode's bias. **This is DeerLab's own
   `bootstrap_analysis` (`bootan`) approach** — verified 2026-08-08 that DeerLab
   defaults to a *non-parametric* regularized P(r) (P is a free grid vector,
   complexity set continuously by `regparam='aic'`) and leans on bootstrap for
   honest uncertainty, rather than committing to a discrete component count. It is
   therefore the right answer for the multi-Gaussian `ic_railed` / N-undetermined
   case too: a bootstrapped band shows the distribution is uncertain instead of
   forcing a verdict on N. Applies across all engines.

Not queued (considered, rejected): Wahba's Bayesian σ²G⁻¹ (moves every shipped
band/CSV), undersmoothing at α/4–α/8 (only cheap route that covers the truth, but
needs a calibration pass). Revisit once 1 and 2 land.

## Explicitly rejected — do not re-propose without new data

Each was implemented and **measured worse** than what it replaces:
- **`S5G-4`'s symmetric re-floor loop** (2026-08-10) — the defect is real: `_solve`
  only ever *raises* a component's width bound, so one migrating **inward** keeps
  its seed centre's higher floor. It reaches the user (**10/368** reported
  components on the 156-row catalogue, worst **2.13× too broad**; **5/105** on the
  28 real traces). Letting the bound also fall to `_sigma_floor(fitted centre)`
  clears every stale slot and buys **Δoverlap −0.0011 (t −1.16)**, correct-N
  0.801 → 0.814, with one row at **−0.131**; on real data it changes nothing
  (N identical 0/28, peak ≤ 0.033 nm). Mechanism: at long r the *calibrated* floor
  `r⁴/(27·ν_dd·T)` sits **below** the true width and the width direction is
  near-flat, so a relaxed bound lets least_squares collapse the component to a
  spike — the stale bound was accidental spike protection. Same shape as `S5-5`
  option A. Numbers + harnesses: `~/deer_benchmark/s5g4/VERDICT.md`.
- **Pinning `background_general`'s λ to the tail baseline instead of extrapolating
  it** (2026-08-13) — the obvious separation of "good shape, bad λ", and it is
  **inert**: `B(t) = g(t)/g(0)`, so a wrong g(0) scales B by that same factor and
  the pin `1 − mean(V/B)` inherits it exactly. Measured over 28 traces × 5 trims,
  pinned vs extrapolated λ agree to the third decimal (median ratio to joint 0.944
  vs 0.943), with identical collapse counts and identical trim instability
  (>30 % on 13/28 both ways). The shape and the t=0 level are not separable.
- `S5-5` option A — re-key `_has_spurious` on the per-centre floor: correct-N
  0.843 → 0.731; on the 13 rows it changes, N right 12/13 before, 0/13 after (it
  deletes the genuine weak far mode).
- `S5T-1`'s `k_ratio`/`conc` recomputes — break working detectors.
- `S5T-4`'s "re-fit λ around the mc optimum" — worse than the two-step estimator.
- `S5T-5`'s frequency-band low-cut — amputates every dipolar frequency past ~3.9 nm.
- `S5-3`'s `k_collapsed` detector — 5 false alarms on 148 healthy runs.
- `S5-4`'s band suppression — `mc_tol`/`mc_trials` tuning is dead on arrival (the
  band is bimodal: exactly 0 or ~0.7, carries no noise scale).
- `S5G-1`'s `n_eff`/pre-whitening criterion remedy — inert (returns identical N).
- The Mellin δ `floor_ratio` opening (2026-07-31) — destroys r=2.0–2.6 nm.

## Known tensions between the short-r mechanisms — read before adding another

Four shipped mechanisms attack the same artefact (spurious short-r / grid-edge
mass), each justified against a baseline lacking the others. The overlap is
measured: `echo_head` fell **+0.0046 → +0.0033 → +0.0016** as `pre_zero` and
`reg_edges` landed under it. **Anything new aimed at short-r mass must be measured
against all four**, or it books a gain already paid for elsewhere.

- **If this stack is ever simplified, `echo_head` is the piece to drop first** —
  it is the Tikhonov analogue of Mellin's δ-split with two fitted constants, faced
  a lower bar than S7's rejected Wiener filter, and is now worth only +0.0016.

## Method guardrails (the recurring traps, kept because each cost real time)

- **A constant tuned on a benchmark inherits that benchmark's blind spot.** Hit
  three times: S3's `mellin_delta` floor, the multi-Gaussian width floor, and
  `S5-5`'s `spike_weight_max` gate (base catalogue's smallest true weight 0.15 is
  above the 0.10 gate → the regime was unreachable, a clean null was an artefact).
  **Check what range a benchmark covers before believing a null.** Hit a fourth
  time in `S5G-4`: 8 hand-picked cases said *no* reported component ever carries a
  stale width bound (0/19), the 156-row catalogue said 10/368 and the real traces
  5/105. Small targeted case sets hide anything the multi-start seeding absorbs.
- **Any engine-signature change needs one GUI-path smoke run before the session
  closes** — applies to result-dict *keys* as much as array lengths (the
  2026-08-05 audit found detectors that never reached the window).
- **A guard keyed on an argument the caller never carries is inert, and looks
  fixed.** `S5T-1`'s bundled `bg_cofit` test was first written as
  `kwargs.get('method')` — but `deer_validate`'s `method` is the α selector (so it
  never lands in `kwargs`) *and* `deer_invert` dropped the gauss solver anyway, so
  the branch could not fire from any call. **Key a guard on the result, not on the
  arguments** (`base.get('method')`), and make the gate prove the branch actually
  executes — writing one exposed both plumbing gaps before either shipped.
- **Reproduce a filed finding before fixing it — half of them move.** Of the eight
  triage items taken up on 2026-08-13, one was already fixed (`ci-1`), one was
  false as written (`xengine-3`), and two had numbers off by 2–7× in *both*
  directions (`batch-1` 10.9× → 1.5×, `me1-1` 88.7× → 13–41×). Findings age against
  the code that fixed their neighbours. The reproduction cost 48 s.
- **A detector's false-alarm run must cover every engine it will ship on.**
  `_flag_not_deer_like` was calibrated on joint / Mellin / gauss, declared 0/84,
  and then fired on `general` in the gate — where it turned out to be **right**
  (4/29 collapsed background fits). A clean null on three of four routes is not a
  null. Same shape as the width-floor and `spike_weight_max` misses above.
- **A HEAD-vs-now comparison cannot read a key the fix introduced.** `S4-quick`'s
  first pass measured "how often did the band mix N" by reading
  `trials[i]['n_gauss']` on both arms — a key only the fixed arm has. It reported
  a confident **0/28** where the answer was **25/28**, and it looked exactly like
  a clean null. Measure the OLD behaviour by re-running the old code, never by
  reading a field it does not populate.
- **`deer.simulate` is even in t** — a finding about time-asymmetry cannot be
  confirmed or refuted on it; use the real Bruker traces in `~/deer_benchmark/`.
- **Every corpus number in this file is measured on UNTRIMMED YopO traces, against
  the project's own standing rule that they must be trimmed** (drop ~2 points off
  the start and ~80 off the end; both ends carry acquisition artifacts and the tail
  is the worse offender). The gap is not academic: at the 2/80 trim the Mellin
  long-t bias on `sample1_labB` falls from **-2.38 to -0.43** sigma-of-the-mean,
  labC from -2.42 to -0.29 and labF from -3.33 to -1.04 — but it moves the OTHER
  way on others (`sample2_labB` +0.75 -> **-4.08**, `sample4_labB` +0.44 ->
  **-5.21**, and joint on labD -0.35 -> -2.85), so trimming is not a uniform
  improvement and cannot simply be switched on. A/B comparisons on a fixed corpus
  stay valid — both arms see the same data — but any ABSOLUTE residual level quoted
  here is a raw-trace number. Trimming also shortens the trace, which moves the
  GUI's auto `r_max = 5*(T/2)^(1/3)` and the alias floor with it.
- **A measurement inherits every switch its harness silently set** — `S5T-8`'s fix
  was measured with `Fit t0` forced OFF; at GUI defaults (`Fit t0` ON) it would
  have printed "moving it won't shift the result" beside a control that shifts the
  mean 4.17 → 4.57 nm. The two-lens gate is the only thing that caught it.
- **Cross-machine floor is Δoverlap ≈ 0.0009, larger than real S5 effects** — pair
  ablations against a baseline computed on the *same box* (`fel_base.json` on
  `fel`), never across machines.
- **The SHORT subset is n=36 and swings ±0.01 between replications** — read t, not
  the mean, on any per-class number from it. (This is what put a noise figure into
  commit `150e429`'s message.)
- Roadmap sessions **before 2026-08-04** quote absolute `lo_mass` measured with the
  free-edge operator — internally consistent, not comparable with anything after
  `reg_edges`.

## Corrections of record

Figures stated as fact and later retracted. Full argument in the archive.

| claim | verdict |
|---|---|
| "clamping costs −0.0123 on the SHORT class at 32 ns" | noise read as fact (t=−0.6, n=36); reached commit `150e429` |
| Mellin `F0` sweep at a pinned `tau_max=30` | invalid — auto selection was silently off |
| `bg_start_early` "on every engine result" | was false when written — `deer_invert`'s own body lacked the call; fixed |
| "On artifact-free synthetic data 'mc' ties 'lsq'" | refuted — overlap Δ −0.0302 (t=−5.46), correct-N 0.808 → 0.644; deleted from docs |
| width floor's "27" presented as physics | it is calibration; `deer.md` now says so |
| `S5T-8` `bg_start_early` demotion (that moving the window "won't shift the result") | refuted at GUI defaults; reverted |
| `S5G-4` "contradicts the report's own *Cleared* table" | there was no contradiction — the *Cleared* entry measured **outward** migration, `S5G-4` is about **inward**; both are right |
| `xengine-3`'s "joint and Mellin take λ/k **verbatim from the same `joint_background` call**" | **false on today's code** — they differ on 3 of 4 real traces (λ 0.412647 vs 0.416425); Mellin re-runs the background under its own `pre_zero`. The weaker point (one estimator, one code path, so agreement is not independent corroboration) stands and needs re-filing |
| `batch-1`'s "10.4 s → 113.2 s, **10.9×**" | stale — predates S2's `scan_lcurve` fix, which made the plain inversion pay for the scan validation skips. Re-measured **~1.5×**. The discarded band is still real |
| `ci-1`'s "support-plane intervals print as +0.000" | **already fixed** by S5 round-2's bound flags: the truncated-grid case returns `center_at_bound=True` / `sigma_at_floor=True` and both the panel (`_PINNED`) and the CSV export (`_PIN`) print *(at range bound)* instead of a bar |
| `me1-1`'s "88.7×" | re-measured at **13.6–41.2×** over four real traces — same defect, smaller number |
| `deer.md`'s "a large fitted `a`/`c` is mathematically valid, λ is unaffected" (`background_general`) | **refuted** — λ is exactly what it affects: the same trade-off drove 25/140 collapses and a 3.6× swing in λ. Corrected on the page |

## Environment

Every `~/deer_benchmark/...` path below resolves to
`C:\Users\User\YandexDisk\deer_benchmark` on the Windows dev box and to
`~/Yandex.Disk/deer_benchmark` (via the `~/deer_benchmark` symlink) on Linux — the
same synced folder, so a harness can run on either. Windows has 6 cores, matching
`fel`, so catalogue jobs no longer have to be shipped out.

Heavy catalogue jobs run on `fel@172.16.16.1` (6 cores, ~4–5×). Pin
`OMP/OPENBLAS/MKL_NUM_THREADS=1` for agent multiprocessing pools. The
[REVIEW_PLAN.md](REVIEW_PLAN.md) staged-review process is retired — kept for
reference only.
