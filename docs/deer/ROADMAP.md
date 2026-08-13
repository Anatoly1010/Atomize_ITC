# DEER treatment — roadmap

This is a **backlog + reference**, not a review log. The staged code review
(S1–S5) is complete and **stopped** — there is no S6 review round. The detailed
per-session reasoning lives in git history and in
[ROADMAP_ARCHIVE.md](ROADMAP_ARCHIVE.md) (the full 2947-line session log up to
2026-08-07); the per-stage findings are in `REVIEW_S1…S5_*.md`. Quote numbers
from those, not from memory.

Remaining work is engineering, not auditing: land the fixes already specified and
measured, port, and close the two external-validation gaps. Treat every item
below as a plain task with a known measurement behind it.

## Files

| file | size | repos |
|---|---|---|
| `atomize/math_modules/deer.py` | ~3500 | all 5 (plain / ITC / NIOCH / NIOCH_Q / Cryomech) |
| `atomize/control_center/deer_analysis.py` | ~3240 | ITC / NIOCH / NIOCH_Q only (lead: ITC) |

The two ship as a pair — `band_degenerate`, the per-component bound flags,
`ic_railed` and now `background['prep']` are produced in `deer.py` and consumed in
`deer_analysis.py`. Run `~/atomize_sync/sync_check.py` before porting. **All five
repos are in sync as of 2026-08-13** (`deer.py` byte-identical across all 5,
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

- **Port of the 2026-08-13 work — DONE.** Byte-identical straight file copies from
  ITC, each landed on the repo's default branch (branch → ff-merge), **not
  pushed**. `S4-quick`: ITC `4bf5b29`, plain `6a3a104`, NIOCH `c16c7e1`, NIOCH_Q
  `7dcdd67`, Cryomech `6d36153`, docs `e2b7f66`. The `mc`-comment + `ic_railed`
  docs pair: ITC `f177bd1`, NIOCH `d6f4bb4`, NIOCH_Q `7e07b05`, docs `5857330`.
  `sync_check.py` clean afterwards apart from the unrelated `ITC_FC.py`.

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

- **Port of both — DONE 2026-08-12.** Byte-identical straight file copies from ITC,
  each landed on the repo's default branch (branch → ff-merge), **not pushed**.
  `S5T-1`: ITC `0c86b21`, plain `35be646`, NIOCH `14e4307`, NIOCH_Q `eb9d6db`,
  Cryomech `ad4285d`, docs `640f053`. `callsites-1`: ITC `ad14dfc`,
  plain `755939c`, NIOCH `c84425a`, NIOCH_Q `393abc2`, Cryomech `41f51c9`, docs
  `c905aa4`. `sync_check.py` clean afterwards apart from the unrelated
  `ITC_FC.py`.

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

- **Port to the forks — DONE 2026-08-08.** The three ITC commits (`f4e7c82` round-2,
  `0a61a3e` S5T-9, `3cd7c83` ic_railed reframe + UI) mirrored to all forks as a
  byte-identical straight file copy — verified each fork sat at a clean linear ITC
  ancestor (`a82fba1`) with no local changes, all files LF, and `sync_check.py`
  clean afterward (only the unrelated `Sibir_1.py` still `~`). Fork commits: plain
  `ba0d70e` (deer.py), NIOCH `87d9bec` (both), NIOCH_Q `359f03d` (both), Cryomech
  `937d995`/branch `main` (deer.py). `deer_analysis.py` lives only in
  ITC/NIOCH/NIOCH_Q.

## Pending — do first

Nothing is blocked. The stack is in sync, the estimator's external check is
closed, `S5G-4` and the gauss `mc` validation question are settled, the
2026-08-05 audit is down to its one behaviour-change item, and `S5T-1` /
`callsites-1` / `S4-quick` are landed — pick from the backlog below. Biggest
lever: the residual bootstrap (uncertainty item 2). Cheapest useful: telling the
user the validation band is drawn at one fixed N, which `S4-quick` just made
true.

## Pending — backlog

Open findings. Each carries its own measurement in the archive / `REVIEW_S5`.
None needs another review round; they need a fix and a gate.

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
- Triage's cuts-for-cap, reasons in `~/deer_benchmark/s5_persist/triage_queue.json`:
  **`xengine-3`** (triage's own "strongest"), `xengine-2`, `batch-1`, `me1-1`,
  `ci-1`, `status-1`, `robust-5`, `docs-7`. (`callsites-1` is **done** — see
  *Recently landed*.)

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
- **A HEAD-vs-now comparison cannot read a key the fix introduced.** `S4-quick`'s
  first pass measured "how often did the band mix N" by reading
  `trials[i]['n_gauss']` on both arms — a key only the fixed arm has. It reported
  a confident **0/28** where the answer was **25/28**, and it looked exactly like
  a clean null. Measure the OLD behaviour by re-running the old code, never by
  reading a field it does not populate.
- **`deer.simulate` is even in t** — a finding about time-asymmetry cannot be
  confirmed or refuted on it; use the real Bruker traces in `~/deer_benchmark/`.
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
