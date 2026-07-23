# DEER treatment + math — staged review plan

A thorough review of the DEER/PDS analysis stack, split into **6 self-contained
sessions**. Each is one sitting: a scope small enough to hold in one context, its
own ground truth, and a written verdict. Sessions are ordered so each builds on
the last — but only S1 is a hard prerequisite for the rest.

**Under review** (~5.6 k lines + docs):

| | lines |
|---|---|
| `atomize/math_modules/deer.py` | 2592 |
| `atomize/control_center/deer_analysis.py` | 2981 |
| `atomize/control_center/data_treatment.py` (DEER paths only) | — |
| `/home/anatoly/atomize_docs/docs/functions/math_modules/deer.md` | — |

**Out of scope:** NUA sampling (separate concern, own open finding — see the
`deer-nua-sampling` notes), and the unported round-4/5 GUI work to plain Atomize
(a sync task, not a correctness question).

---

## Why this order

The three engines (Tikhonov, Mellin, multi-Gaussian) all consume the **same**
kernel, background and zero-time. An error there is invisible to cross-engine
comparison, because it biases all three *identically* — three engines agreeing is
not evidence when they share a wrong kernel. So the shared foundation is reviewed
first and alone (S1), and cross-engine agreement is only meaningful afterwards (S6).

After S1, sessions 2–5 are independent and can be reordered or dropped freely.

---

## Ground truth available — use it, don't rebuild it

Substantial validation already exists. Each session below names what applies.

- **`~/deer_benchmark/`** — real-data DeerLab cross-check on the YopO ring test
  (Zenodo 5092869): P(r) overlap 0.978, |Δpeak| 0.024 nm over 27 traces.
  `benchmark.py`, `batch.py`, `compare.py`, plus 4 labelled datasets.
- **`~/deer_benchmark/synth/`** — ground-truth synthetic suite, `bench_gauss.py`,
  `cmp_gauss.py`, and a `diag/` folder of targeted diagnostics
  (`diag_mellin_droop.py`, `diag_bg_shrink.py`, `diag_adaptdelta.py`, …).
- **`deer.simulate()`** (deer.py:2512) — forward model for round-trip tests.
- **DeerLab 0.14.2** installed, but **currently broken**: it needs a
  `scipy.integrate.cumtrapz` shim (removed in this scipy) and `matplotlib`.
  **Fix this before S2** — it is the strongest external check in the whole plan.

> A round-trip through `simulate()` only tests self-consistency. Where a session
> says *analytic*, derive the expected number independently — that is the only
> check that catches a shared convention error.

---

## Method (same bar that worked for the epr_auto review)

Per session:

1. **Read** the scoped code fully; skim the rest for context.
2. **Hunt** the listed failure modes. Every bug/risk needs a concrete scenario
   (inputs → wrong output) and file:line evidence.
3. **Check numerically.** Scripts go **outside** the repo (`~/deer_benchmark/` or
   a temp dir). For a math claim, reproducing the wrong number is the evidence.
4. **Verify** each bug/risk with **2 independent adversarial skeptics**, default
   stance REFUTED. (Reuse `~/epr_auto_dev/review_wf_ef0c3f4c/physics.js` as the
   workflow template — swap the CONTEXT/PROMPT blocks.)
5. **Record the formulas checked and found CORRECT**, not just the defects. This
   was the most reused output of the epr_auto review — it stops the next session
   re-deriving what's settled.
6. **Write** `docs/deer/REVIEW_S<n>_<topic>.md` and tick the status table below.

Severity: `bug` = wrong numbers/crash · `risk` = needs specific conditions ·
`note` = no action.

---

## S1 — Foundations: kernel, background, zero-time · Opus + blind-derivation panel

**The one that must be right.** Everything downstream inherits these.

**Scope** — `deer.py`: `dipolar_frequency`/`dipolar_kernel` + `NU_DD` (40–101),
`_echo_top`/`_no_background` (101–157), `background_fit`/`_bg_model`/
`background_general` (157–294), `_parabolic_zero_time`/`fit_zero_time`
(2248–2411). GUI: Source / Phase / Background tabs.

**Hunt**
- `NU_DD = 52.04 MHz·nm³` — derive it from μ₀g²μ_B²/(4πh) and confirm units and
  digits. Every distance in every result scales with this constant.
- Kernel discretisation: the `dr` weighting and whether `K·P` is a Riemann sum or
  assumes normalised masses — an inconsistency here rescales λ, not shape, so it
  hides from overlap metrics.
- Powder average: orientation grid density, and whether the 1−3cos²θ integral is
  done in cosθ (uniform) or θ (not uniform — a classic silent error).
- Background: the fractal `exp(-k·t^(d/3))` exponent convention; `fit_dim` freedom
  vs `dim`; behaviour when `bg_start` lands before the dipolar evolution has decayed.
- Zero-time: the parabolic fit's `drop`/`search_frac` heuristics on an asymmetric
  or noisy echo; what happens when the maximum is at the trace edge.

**Ground truth** — analytic Pake doublet (`_pake_transform`, deer.py:1543) against
a hand-derived one; a single-δ P(r) through `dipolar_kernel` vs the closed-form
dipolar oscillation; DeerLab's `dipolarkernel`/`bg_hom3d` once the shim is in.

**Exit** — kernel and background confirmed against an *independent* derivation, or
defects logged. Everything after this assumes S1 passed.

> **DONE 2026-07-23** — see [REVIEW_S1_foundations.md](REVIEW_S1_foundations.md).
> Physics core CLEARED: the blind panel agreed unanimously to 8 s.f. on ν_dd and on
> the cos θ powder measure, and the code matches. Four defects found in the handling
> *around* the kernel (negative time, zero-time fit, negative λ). **S1-1 (negative-time
> samples fed as |t|) must be fixed before S2/S4/S5**, or every engine benchmark
> inherits it.

---

## S2 — Tikhonov + NNLS · Opus

**Scope** — `regularization_matrix`, `tikhonov_nnls`, `_menger`, `l_curve`,
`default_r_axis`, `_normalize_masses`, `tikhonov_ci` (294–443); `deer_invert`,
`deer_invert_joint` (443–654). GUI: Tikhonov tab.

**Hunt**
- α selection: GCV vs L-curve/Menger — does the GCV functional match the standard
  form for the *constrained* (NNLS) problem, where the effective DOF is not `tr(H)`?
- 2nd-order regularisation matrix boundary rows (the usual off-by-one).
- **CI coverage.** `tikhonov_ci` uses covariance/curvature. Test it: simulate
  N traces at known noise, count how often the 95 % band covers truth. A band
  that reads 95 % and covers 60 % is a publication hazard.
- `deer_invert_joint`'s λ pinning and its interaction with background.

**Ground truth** — the **strongest** in the plan: DeerLab on real YopO (27 traces)
plus synthetic. Largely validated already, so this session is confirmation +
CI-coverage, which the existing benchmarks do *not* test.

---

## S3 — Mellin transform core · Opus + blind-derivation panel

**The riskiest math in the stack.** Bespoke analytic engine with **no external
implementation to check against** — DeerLab has no equivalent, so every prior
validation is self-consistency. Highest chance of a silent convention error.

**Scope** — `mellin_kernel_spectrum`, `mellin_signal_spectrum`, `mellin_inverse`
(654–737); `mellin_delta` (869–905); `_tail_noise`, `residual_whiteness`
(905–974); `_MELLIN_I_S`, `distribution_moments`, `moment_error_apriori`
(974–1059).

**Hunt**
- The Mellin transform pair itself: sign/offset of the complex exponent, the
  strip of convergence, and whether the inverse's contour matches the forward.
- `_MELLIN_I_S = {1: 4.35466, 2: 3.06158, 3: 2.77339, 4: 2.56993}` — magic
  constants. Derive each analytically; a wrong one silently biases that moment only.
- `moment_error_apriori`: the error propagation's small-N and low-SNR behaviour.
- `mellin_delta`'s `level=0.95, floor=0.09, cap=0.12` — where do the floor/cap
  come from, and what happens at the clamp boundaries?
- `du=0.02`, `n_u=512`, `parabolic=True` — discretisation adequacy; test convergence
  by halving.

**Ground truth** — **analytic only.** Compute the Mellin transform of a P(r) with
a closed form (log-normal, Gaussian) by hand/sympy and compare. Cross-check moments
against `distribution_moments` on ground-truth distributions. The `i^(-2/3)` NUA
relation is an independent anchor.

---

## S4 — Mellin engine + joint background · Opus

**Scope** — `joint_background` (737–869), `deer_invert_mellin` (1059–1522, the
single largest function in the module).

**Hunt**
- τmax via the discrepancy principle — noise-estimate sensitivity, and the failure
  mode when the trace is too short.
- The documented hardening (full-tail-λ + `r_max` cap) against short `bg_end` /
  short traces — does it cover the boundary it claims?
- Monte-Carlo CI: draw count, seeding, and whether it is reproducible.
- The known **droop** (`diag_mellin_droop.py` exists) — is it understood and bounded?

**Ground truth** — the `diag/` diagnostics in `~/deer_benchmark/synth/`; synthetic
ground truth; agreement with Tikhonov within CI (meaningful *only* if S1 passed).

---

## S5 — Multi-Gaussian · Opus

Largest block (726 lines) and the most recently reworked (round 8: joint V-space
fit `V = A[1−S+K·masses]B` with `λ = Σmasses = S`, multi-start seeding, width floor
`r⁴/(27·ν_dd·T)`).

**Scope** — `_gauss_seed_centers`, `_pake_transform`, `_gauss_mc` (1522–1709);
`deer_invert_gauss` (1709–2248). GUI: Multi-Gaussian tab.

**Hunt**
- Multi-start seeding: does it actually escape local minima, or does the reported
  improvement (correctN 0.54→0.80) come from the seeding *count* rather than the
  strategy? Test against a random-restart control.
- **Model selection** — how is the number of Gaussians chosen, and is the criterion
  (AIC/BIC/F-test?) valid for a constrained nonlinear fit? Over-fitting here
  invents peaks, the worst DEER failure mode.
- The width floor `r⁴/(27·ν_dd·T)` — derive it; check the constant 27.
- Parametric CI from fit covariance: valid only near a quadratic minimum with
  masses off their bounds. Check behaviour when a mass is pinned at zero.

**Ground truth** — `bench_gauss.py`, `cmp_gauss.py`, synthetic ground truth with
known N; the round-8 baseline (overlap 0.846→0.885) as a regression floor.

---

## S6 — Cross-engine consistency, validation, GUI · Opus

Only meaningful once S1 is settled.

**Scope** — `deer_validate` (2427–2512), `simulate` (2512–2592); `deer_analysis.py`
plumbing (~3 k lines, read for parameter passing, not algorithms); the DEER paths
in `data_treatment.py`; `deer.md` docs.

**Hunt**
- **Do the three engines agree** on the same data, within their stated CIs? Any
  systematic offset is a finding — and by construction it is *not* in the shared
  foundation (S1 cleared that), so it is engine-specific.
- **CI semantics are not comparable.** Tikhonov = covariance/curvature, Mellin =
  Monte-Carlo, Gaussian = parametric fit-covariance. The GUI presents all three as
  "95 %". Do they mean the same thing? If not, say so in the UI.
- Duplicated DEER code between `data_treatment.py` and `deer_analysis.py` — do both
  paths produce identical results, and is one stale?
- Batch mode: parameter passing per engine.
- Docs vs behaviour in `deer.md`; defaults quoted correctly.

---

## Model allocation

**All six sessions run on Opus.** Fable is not required for any of them — it was a
preference, not a prerequisite. Precedent: the epr_auto physics/numerics review
(2026-07-23) was earmarked for Fable, run on Opus instead, and found two
hardware-affecting numerical bugs (a 1.84× pulse-envelope error and a 1.746×
estimator mis-scaling), each with reproduced numbers. Same class of work as S1/S3.

What actually decides quality on math review is **independent derivation and
external cross-check**, not model tier. Two sessions get a compensating protocol.

### Compensating protocol — S1 and S3 only

These were the Fable candidates. Run them on Opus with three additions:

1. **Derivation is mandatory, not confirmation.** The reviewer derives the quantity
   from first principles and shows the arithmetic. "Checked, looks right" is not a
   result. Applies to `NU_DD`, the powder-average integral, `_MELLIN_I_S`, the
   `mellin_delta` floor/cap, the Gaussian width-floor constant 27.
2. **Blind-derivation panel for the magic constants.** Spawn 2–3 agents to derive
   the same constant **from scratch, without being shown the code's value**, then
   compare against the code afterwards. This defeats anchoring — the specific
   failure mode of any model asked "is this constant right?", which invites
   agreement. Disagreement between the blind derivations is itself a finding.
3. **2 adversarial skeptics** per bug/risk, default stance REFUTED, as elsewhere.

### The substitution that matters most

**Fixing the DeerLab shim removes most of S1's exposure.** DeerLab's
`dipolarkernel` and `bg_hom3d` are an independent implementation of exactly what
S1 reviews — worth more than any model upgrade, and free.

That leaves **S3 as the only genuinely exposed session**: bespoke analytic math
with no external implementation anywhere to check against. If Fable becomes
available again, spend it there. Until then, S3 leans hardest on the blind-derivation
panel and on symbolic checks (sympy) against closed-form transform pairs.

---

## Before you start

- [x] **Fix DeerLab** — DONE. matplotlib was already present; only `cumtrapz` needed
      shimming. Non-invasive: `~/deer_benchmark/deerlab_shim.py`, imported before
      `deerlab` (site-packages untouched). Verified `dipolarkernel`, `bg_hom3d`,
      `dipolarbackground`. **Use it in every later session.**
- [ ] Decide whether findings get fixed per-session or batched at the end.
      Per-session risks invalidating later sessions' baselines; batching risks a
      long list. *Recommendation:* batch S1 fixes immediately (everything depends
      on them), batch the rest to the end.

## Status

| Session | Model | Status | Report |
|---|---|---|---|
| S1 Foundations | Opus + blind-derivation panel | **DONE** 2026-07-23 — 4 confirmed, 1 plausible | [REVIEW_S1_foundations.md](REVIEW_S1_foundations.md) |
| S2 Tikhonov | Opus | not started | |
| S3 Mellin core | Opus + blind-derivation panel | not started | |
| S4 Mellin engine | Opus | not started | |
| S5 Multi-Gaussian | Opus | not started | |
| S6 Cross-engine + GUI | Opus | not started | |
