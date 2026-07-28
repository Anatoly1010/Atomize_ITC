# S2 — Tikhonov + NNLS · COMPLETE (verified, fixes applied)

Both stages are done and the confirmed fixes are in the tree. Stage 1 was six
independent dimension reviewers; stage 2 was **2 adversarial skeptics per finding,
default stance REFUTED**, each required to reproduce the evidence chain itself.

| | |
|---|---|
| Stage 1 run | `wf_789813f0-a0b` — 6 reviewers, ~2.9 M tokens, 3 h 20 min |
| Stage 2 run | `wf_502ac692-564` — 28 skeptics, 2.4 M tokens, 7 h 43 min |
| Raw findings | `~/deer_benchmark/s2_review_findings.json` |
| Verdicts + both skeptics' reasoning | `~/deer_benchmark/s2_verify_results.json` |
| Outcome | 38 raw → 15 unique bug/risk → **9 confirmed, 3 plausible, 2 refuted** (+ 1 fixed in stage 1) |

The stage-2 prompt carried three warnings from the interim report: the CI cluster
is correlated, the ME1 finding must be judged against the *fixed* code, and
finding 5's `k` regime may be unreachable. All three changed the outcome — see
*What the warnings bought* below.

---

## Verdicts

Numbering follows the interim report. `x N` = reviewers who independently landed
on that line.

| | file:line | claim | verdict | severity |
|---|---|---|---|---|
| 1 | `deer.py:629` **x3** | joint `F_fit`/`residuals` built from `P_norm`, not the solved `P` | **CONFIRMED** | bug ↔ risk (split) |
| 2 | `deer_analysis.py:1845` **x2** | GUI overwrote `res['t']` with the uncropped axis | fixed in stage 1 | bug |
| 3 | `deer.py:547` | `alpha_factor` 2–4× collapses CI coverage | **CONFIRMED** | bug ↔ risk (split) |
| 4 | `deer.py:452` | docstring calls the band conservative; it under-covers at the modes | PLAUSIBLE | note |
| 5 | `deer.py:614` | joint engine biases mean r on strong backgrounds | PLAUSIBLE | note ↔ risk (split) |
| 6 | `deer.py:358` | scipy `nnls` raises 'Maximum iterations' and aborts the inversion | **CONFIRMED** | risk |
| 7 | `deer_analysis.py:2368` | ME1 error bar silently `nan` on every real trace | **REFUTED** (4/4) | — |
| 8 | `deer.py:443` | `tikhonov_ci` is a bias-blind sampling band | **CONFIRMED** | risk |
| 9 | `deer.py:630` | joint CI ignores background/λ variance | **CONFIRMED** | bug |
| 10 | `deer.py:544` **x2** | α grid ceiling 1e3 is in dr-dependent units and pins silently | **CONFIRMED** | risk |
| 11 | `deer.py:422` | `curvature` argmax includes the κ=0 sentinels | PLAUSIBLE | note |
| 12 | `deer.py:469` | band diverges as α → 0, wrecking the P(r) plot scale | **CONFIRMED** | risk |
| 13 | `deer.py:616` | λ pin fails silently on undecayed tails | **CONFIRMED** | risk |
| 14 | `deer_analysis.py:2503` | reliability bands use `ptp` of the acquisition axis | **REFUTED** (4/4) | — |
| 15 | `deer_analysis.py:1838` | manual-α runs still pay the full 36-point scan | **CONFIRMED** | note ↔ risk (split) |

"Split" = the two skeptics agreed the defect is real and disagreed only on severity.

## What the warnings bought

**Both axis-downstream findings (7 and 14) were refuted 4/4.** Each skeptic first
reproduced the *pre-fix* failure — `IndexError: ... size 338 ... 354` for ME1 —
then showed the current tree is clean: ME1 = 0.002157 nm on `sample1_labA` (the
value finding 7 quoted as unreachable), finite on 18/18 engine × trace × `fit_t0`
combinations. On finding 14 a skeptic caught something sharper: **the numbers the
finding calls wrong (3.366 / 5.609 nm) are the pre-fix values, and 3.3140 / 5.5233
— its own "should be" figures — are what the code now emits.** Residual error is
one Δt, in the conservative direction. Without the warning these would very likely
have been confirmed against the reviewers' transcripts.

**The CI cluster split instead of confirming four times.** Findings 8 and 9 carry
the load; 3 confirmed with split severity; 4 collapsed to a wording note — skeptic 2
could not reproduce its decisive claim in the finding's *own* headline scenario
(reported/empirical sd ≥ 1.09 in every support bin, i.e. conservative exactly as the
docstring said). The shared, non-double-counted residue is ~1.3×, comparable to
DeerLab's own intrinsic under-coverage. What is specific: the joint engine's
extra ~7× (finding 9) and the α-factor collapse (finding 3).

**Finding 5 downgraded on reachability.** Both skeptics reproduced the guard
mechanism at `deer.py:889` exactly (k = 0.2321, λ = 0.697 to 4 s.f.) and confirmed
the tight-cap fit recovers the truth in 12/12 cells — the information *is* in the
data and the wide-cap preference discards it. But it needs k = 0.40 /µs against a
real ring-test maximum of 0.0473. Two refinements to the interim caveat: the onset
is nearer than assumed (first failure at k = 0.089, 20.5 % decay), and on the GUI's
own auto-`bg_start` **a 1.5 ns shift in the background cursor flips the mean by
1.3 nm** — a knife-edge, not a smooth bias.

---

## Fixes applied

### Wrong numbers shipped to the user

- [x] **`deer.py:629` — joint `F_fit` from the solved masses** (finding 1).
      `F_fit = K@P_masses`, matching `deer_invert:551` and the Mellin/Gaussian
      engines; `P_norm` stays for `P_density` only. The old line divided the fit by
      `sum(P)`, which pinned it to exactly 1.0 at t = 0 whatever the fit did.
      Consumers were the displayed R², the Durbin–Watson / lag-1 "white vs
      structured" verdict, the V(t)+fit overlay and the CSV export. On real traces
      the effect is ≤ 1 % (`sum(P)` = 0.975–1.009 measured over all 28), but with a
      truth outside the r grid the **reported R² was −1.90 where the true fit gives
      +0.25** — verified restored to +0.2518 on that exact scenario.

- [x] **`deer.py:358` — `tikhonov_nnls` no longer aborts** (finding 6). scipy's
      default `maxiter` (3n) raised `RuntimeError('Maximum number of iterations
      reached')` at the top of the α grid on a fine r axis, killing the whole scan;
      the solve needs 601–700 iterations against a default of 600. Now solves with
      `maxiter = max(3n, 5000)` and degrades to a clipped `lstsq` if even that
      fails, with a `TypeError` fallback for scipy builds without the keyword.
      Verified on the exact crash scenario: completes, `sum(P)` = 0.2532.

### Silent failures that now announce themselves

- [x] **`deer.py:424` — α pinned to the grid edge is flagged** (finding 10).
      `l_curve` returns `at_bound` and raises a `RuntimeWarning` when the pick lands
      on the first or last grid point; the DEER window shows it next to the
      background line. A boundary hit was previously indistinguishable from an
      interior optimum, and it is reachable at default settings on broad
      distributions (GCV wants α ≈ 4×10³ against a ceiling of 10³, costing 0.59 nm
      of peak position). Measured on the ring-test set: **0 of 56 inversions hit a
      boundary**, so the flag is quiet on real data.

- [x] **`deer.py:422` — `curvature` searches the interior only** (finding 11).
      `kappa[0]`/`kappa[-1]` are unfilled sentinels that could win the `argmax`;
      the search is now `kappa[1:-1]` and falls back to GCV with `corner_ok=False`
      when no corner exists. Both skeptics showed the sentinel never actually won
      (0 of 112 configurations), so this changes no current result — it removes a
      real edge case on caller-supplied narrow grids.

- [x] **`joint_background` reports why λ should not be trusted** (findings 13, 5).
      New keys `lambda_raw` / `lambda_clamped` / `tail_abs_F` / `k_ref` / `k_ratio`
      / `k_disagrees`, plus a `RuntimeWarning` naming the conditions that fired —
      matching what `background_fit` has done since S1. The λ pin only forces
      mean F = 0 over its window; **mean |F| there is the quantity that says whether
      the tail decayed at all**, and it reads 0.384 on the 1 µs / 4.5 nm case where
      λ comes out 6.6× low. Thresholds checked against the real set: `tail_abs_F`
      maxes at 0.045 (threshold 0.05, 0 of 28 fire); the k cross-check fires on
      6 of 28 joint runs (ratios 2.1–59×), and in the two extreme ones it is the
      *sequential* fit that has collapsed — k on its 1e-4 floor for `sample3_labA`,
      2.5e-4 for `sample4_labC` — which is exactly the disagreement worth
      surfacing, in the direction that says "cross-check", not "joint is wrong".

### Presentation and cost

- [x] **`deer_analysis.py` — the band no longer drives the P(r) autoscale**
      (finding 12). The band items are added with `ignoreBounds=True` in both the
      single-result and batch paths. The covariance band diverges as α → 0
      (reviewers measured 4.7×10⁴ nm⁻¹ at the spinbox minimum on a real trace) and
      `autoRange` was scaling to it, leaving P(r) in < 3 % of the plot height.
      Verified in the real window offscreen: at α = 1e-4 the band reaches
      4376 nm⁻¹ against a 3.25 nm⁻¹ peak, the y-range now stays 3.41, and **P(r)
      fills 90.9 % of the axis**.

- [x] **`deer_analysis.py:1838` — manual α skips the selection scan** (finding 15).
      `scan_lcurve=(alpha is None or the L-curve view is showing)`. Measured in the
      GUI itself: **14.69 s → 0.38 s, 38×**. Selecting the L-curve view still pays
      for the scan, so that view and the `_lcurve.csv` export keep working; when a
      result was computed without one, the status line now says why and what to do.

- [x] **Uncertainty labelling stops promising coverage it does not deliver**
      (findings 3, 4, 8, 9). `tikhonov_ci`'s docstring, the `deer_invert`
      `alpha_factor` docstring, the checkbox ("Show 95% uncertainty band"), its
      tooltip, the α-strength tooltip and the CSV header now state that the band
      propagates **noise only**, exclude the DeerLab-equivalence claim, and carry
      the measured numbers: coverage at the mode 0.84 at 1×, 0.08 at 2×, ~0 at 3×;
      1.6–3.6× narrower than DeerLab with the opposite α dependence; up to 7×
      narrower again under the joint engine. Results carry `ci_kind` (`'noise'` /
      `'noise_fixed_bg'`) so the distinction is machine-readable.

- [x] **ME1 is no longer rounded to `±0.00`** in the summary table (a cosmetic
      residual both skeptics noted while refuting finding 7 — the table used `.2f`
      on a ~0.002 nm quantity).

## Deliberately not changed

- **The `joint_background` collapse guard** (`deer.py:889`, findings 5 and 9's root
  cause). The suggested loosening — reject a wide-cap rate well below the tight one
  regardless of decay — cannot be tuned from the failing case alone: the wide cap
  exists because a genuine long-r component biases the tight-cap k *high*, and in
  that legitimate regime `k_w < 0.5·k_t` too. A skeptic also measured that on the
  wide grid the collapsed k genuinely fits V-space better (vss 0.005883 vs
  0.006654), so a residual comparison does not separate the cases either. The
  diagnostic half is shipped instead; changing the numerics needs the synthetic
  suite re-run as a gate, which is S4 work (joint background is S4's subject).
- **The CI estimator itself.** Switching σ²MMᵀ → σ²G⁻¹ is 1.44× wider and was
  measured to lift peak coverage 0.800 → 0.925 — still short of nominal, and it
  would move every user's plotted band and exported CSV. The honest labelling
  costs nothing and does not pretend to fix coverage; a calibrated interval already
  exists in `deer_validate` and the Monte-Carlo engines.
- **α's dr-dependent units** (finding 10's other half). Normalizing `L` by `dr^order`
  would make α resolution-independent and DeerLab-comparable, but it silently
  reinterprets every saved α and every value in the spinbox. Documented in
  `l_curve`'s docstring and the docs site instead.
- **Widening the default α grid.** A skeptic showed GCV can have *no* interior
  minimum on this near-vertical L-curve, so a wider grid trades a visible pin for a
  worse silent one. The `at_bound` flag is the load-bearing part.

## Regression evidence

All post-fix, on this tree:

Harnesses kept in `~/deer_benchmark/s2_fix/`: `unit.py` (the four math fixes on
their own failing scenarios), `check.py` (28 real traces × 2 engines, GUI path),
`gui_smoke.py` (the real window offscreen). Re-run all three after any change to
the Tikhonov path.

| check | result |
|---|---|
| Real ring-test set, both engines, GUI path (no pre-crop) | 56/56 inversions complete, no exceptions |
| `sum(P)` over 28 traces | 0.975–1.009 (unchanged; the F_fit fix is ≤ 1 % here) |
| α at a grid boundary | 0/56 |
| `tail_abs_F` > 0.05 | 0/28 (max 0.045) |
| k cross-check fires | 6/28 joint runs, 2 of them from a collapsed *sequential* k |
| GUI offscreen smoke (fit_t0, both engines, manual α, α×3, L-curve view) | all render, `len(res['t']) == len(form_factor)` = 338/338 |
| DeerLab cross-check, 28/28 traces | overlap **0.978** (min 0.816), \|Δpeak\| **0.024 nm** (max 0.327), \|Δλ\| vs labs 0.0259 — unchanged from the pre-fix baseline |

## Carried forward

- **17 notes** in `s2_review_findings.json` → `notes`, unverified. The l_curve
  docstring note (measured behaviour is the inverse of what it claimed) is now
  fixed as part of finding 11's docs; the rest stand.
- **Port to the fork family.** `deer.py` is byte-identical across plain /
  NIOCH / NIOCH_Q / Cryomech (`c3ebd21f`) and ITC has diverged since **S1** — the
  S1 fixes were never ported either. `deer_analysis.py` exists only in ITC /
  NIOCH / NIOCH_Q. One port should carry S1 + S2 together.
- **S3** (Mellin core) is next per [REVIEW_PLAN.md](REVIEW_PLAN.md). Note that S4's
  subject, `joint_background`, now owns the deferred guard question above.
