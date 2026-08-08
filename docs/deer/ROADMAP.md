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

The two ship as a pair — `band_degenerate`, the per-component bound flags and
`ic_railed` are produced in `deer.py` and consumed in `deer_analysis.py`. Run
`~/atomize_sync/sync_check.py` before porting. As of 2026-08-07 the port is a
**straight file copy**: all forks are byte-identical to ITC's pre-S5 state.

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

## Recently landed

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

## Pending — do first

1. **Port to the forks.** ITC now leads by two commits: the round-2 fixes
   (`deer.py`, all 5 repos + `deer_analysis.py`, ITC/NIOCH/NIOCH_Q) and `S5T-9`
   (`deer_analysis.py` only). Straight file copy after `sync_check.py` — the two
   files still ship as a pair. **This is now the only do-first item** — the
   estimator's external check is closed (above).

## Pending — backlog

Open findings. Each carries its own measurement in the archive / `REVIEW_S5`.
None needs another review round; they need a fix and a gate.

**Multi-Gaussian (S5):**
- `S5G-4` — the only genuinely open item: claims the stale-floor guard fails for a
  component migrating *inward*, which contradicts the report's own *Cleared*
  table. One of the two is wrong; settle it.
- `S5T-1` full scope — stale `joint_background` reliability keys (incl.
  `deer_validate`'s per-trial `flagged` vote) shipped beside refitted k/λ, across
  four consumers. Large; land the namespace/label route across all four at once —
  shipping half is worse than none.
- `deer_validate` `bg_cofit` test keys on `engine=='gauss' and bg_engine!='general'`
  and **ignores `method`** — latent, harmless only because the GUI skips `mc`
  validation.
- `engine='gauss'` has the **identical** `deer_validate` hole S4-1 fixed for
  Mellin: `n_gauss` is re-selected per trial, so the validation band mixes
  component counts.
- Triage's cuts-for-cap, reasons in `~/deer_benchmark/s5_persist/triage_queue.json`:
  **`xengine-3`** (triage's own "strongest"), `xengine-2`, `callsites-1`,
  `batch-1`, `me1-1`, `ci-1`, `status-1`, `robust-5`, `docs-7`.

**Reporting defects from the 2026-08-05 audit (items 3–9 still open):**
- (3) `deer_validate(clamp_alias=False)` raises — clamps its own grid but forwards
  `True` to the per-trial `deer_invert` → shape mismatch. Public escape hatch.
- (4) `pre_zero` silently ignored on Mellin/gauss (pops `pre_zero_engine`);
  `deer_invert`'s docstring still says they "always crop", false since `2f10ce7`.
- (5) `deer_invert(engine='joint')` drops `**kwargs` — `head_level`/`head_cap`/
  `head_ratio_max` inert on that path.
- (6) `'even_fold'` pairs by `searchsorted`, so an off-grid t₀ folds outward
  (~74 % of dt at the echo top). **Fixing it re-opens the +0.0064 that justified
  the Mellin default** — needs a benchmark re-run, not a one-liner.
- (7) `echo_head` + Validate silently drops the head (`:1946` omits it).
- (8) `echo_head` is a no-op with no pre-t₀ samples and the outcome is never read
  from the result dict.
- (9) reliability shading is engine-dependent — `ptp(res['t'])` includes the
  pre-t₀ span under `pre_zero='even'`, so Tikhonov and Mellin draw the green/yellow
  boundary at different r on identical data.
- The batch "Process all" summary still reports no clamp for any engine.

**S4 note queue (unverified, each carries the reviewer's numbers):**
- widen the τmax candidate grid `[6…40]` → `[3…60]` (+0.017 mean overlap, needs a
  boundary flag);
- guard `_masses` relatively (`area < η·positive_area`) not at the useless 1e-12;
- make a failed `_fit_rate` visible (both arms swallow to the sequential fit with
  `k_ratio` exactly 1.0, NaN travels on);
- unify the λ clamp (0.95 / 1.0 / 0.98 in one module);
- decide `du=0.005` as default (+0.016 overlap at 1.46× cost — data-driven rule
  rejected);
- the two non-default τmax methods (`'discrepancy'`, `'lcurve'`) are broken and
  unreachable from the GUI — fix or remove;
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
  **Check what range a benchmark covers before believing a null.**
- **Any engine-signature change needs one GUI-path smoke run before the session
  closes** — applies to result-dict *keys* as much as array lengths (the
  2026-08-05 audit found detectors that never reached the window).
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

## Environment

Heavy catalogue jobs run on `fel@172.16.16.1` (6 cores, ~4–5×). Pin
`OMP/OPENBLAS/MKL_NUM_THREADS=1` for agent multiprocessing pools. The
[REVIEW_PLAN.md](REVIEW_PLAN.md) staged-review process is retired — kept for
reference only.
