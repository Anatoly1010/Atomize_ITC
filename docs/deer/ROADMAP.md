# DEER treatment — roadmap & session log

Working agreement, mirroring `docs/automation/ROADMAP.md`: each session picks the
next item, updates this file before ending, and records anything that needs real
data or a lab decision. The staged review itself is planned in
[REVIEW_PLAN.md](REVIEW_PLAN.md) — update that when the plan changes, don't fork it here.

Model note: sessions are Opus. Fable is not currently available; S1 and S3 use a
**blind-derivation panel** instead (agents derive the constants from first
principles with no sight of the code, and the results are diffed afterwards). See
the plan's *Model allocation* for why that substitutes.

## Under review

| | lines |
|---|---|
| `atomize/math_modules/deer.py` | 2592 |
| `atomize/control_center/deer_analysis.py` | 2981 |
| `atomize/control_center/data_treatment.py` (DEER paths) | — |

## Review status

| Session | Status | Report |
|---|---|---|
| S1 Foundations — kernel, background, zero-time | **DONE + FIXED** 2026-07-23 | [REVIEW_S1_foundations.md](REVIEW_S1_foundations.md) |
| S2 Tikhonov + NNLS | **DONE + VERIFIED + FIXED** 2026-07-28 | [REVIEW_S2_tikhonov.md](REVIEW_S2_tikhonov.md) |
| S3 Mellin transform core | **DONE + VERIFIED + FIXED** 2026-07-29 | [REVIEW_S3_mellin.md](REVIEW_S3_mellin.md) |
| S4 Mellin engine + joint background | **DONE + VERIFIED + FIXED** 2026-07-30 — 13 findings judged: 10 confirmed, 3 plausible, 0 refuted; all confirmed fixed, **none as suggested**. H1 and H2 both answered and closed. | [REVIEW_S4_mellin_engine.md](REVIEW_S4_mellin_engine.md) |
| S5 Multi-Gaussian | not started | |
| S6 Cross-engine, validation, GUI | not started — carries the on-demand residual bootstrap, the joint/Mellin band propagation S4 disclosed, S3's ME₁-ε placement, and S4's note queue | |

---

## Session 2026-07-23 — S1 foundations: reviewed, 4 confirmed defects, ALL FIXED

Run `wf_c5eab96a-a1b` — 19 agents, 1.01 M tokens, ~78 min. Structure: 3 blind
derivers + 1 code reviewer concurrently, then a reconciler that saw both, then
2 adversarial skeptics per bug/risk.

### The physics core is CLEARED — do not re-derive

The blind panel agreed **unanimously to 8 significant figures**, with zero
repo-touching tool calls (verified from the transcripts, not assumed):

| Quantity | D1 | D2 | D3 | Code |
|---|---|---|---|---|
| ν_dd (MHz·nm³) | 52.041016 | 52.04101582 | 52.041016 | 52.04 ✓ |
| powder measure | cos θ | cos θ | cos θ | cos θ ✓ |

Also confirmed correct and **not to be re-derived in S2–S6**: the 2π convention
(52.04 is the cyclic prefactor, applied before multiplying t); the `(1−3cos²θ)`
angular factor integrated uniformly in cos θ (the classic silent error is NOT
present); `B(t) = exp(−k·t)` with fractal d entering as `d/3`, reducing correctly
at d = 3; `dipolar_kernel` vs DeerLab `dipolarkernel` (max dev 1.6e-4, quadrature);
`background_general` vs `bg_hom3d` — **max dev 4e-11** once compared correctly
(DeerLab takes concentration in µM, not a rate; conversion k = 9.9739e-4·λ·C[µM],
itself derived independently by the panel).

So the nightmare case — a wrong kernel biasing all three engines identically,
invisible to cross-engine comparison — is ruled out.

### Defects were in the handling AROUND the kernel — all fixed

Fixes applied in this session, each verified against the failure it targets:

- [x] **`deer.py` — pre-zero-time samples fed to the kernel as |t|** (bug).
      `dipolar_kernel` evaluates `|w·t|`, and nothing masked `t >= 0` after the
      zero-time shift, so the echo RISING EDGE was modelled as ordinary dipolar
      evolution; the non-negative inversion piled P(r) mass at short r to
      manufacture the decay. **True 5.0 nm pair reported as ~2.7 nm, no warning.**
      Fix: new `_crop_pre_zero()` called at all five engine entry points
      (`deer_invert`, `_joint`, `_mellin`, `_gauss`, `deer_validate`).
      Verified: 5.00 nm pair with 200 ns of pre-t0 data now returns **4.96 nm**.
      **Why 27 traces of DeerLab benchmarking never caught it:**
      `~/deer_benchmark/benchmark.py:46` crops `t >= 0` itself, and the GUI does
      not — "Fit" zero-time is on by default with Trim reset to 0 on every new
      trace. *Any future validation must exercise the GUI's path.*
- [x] **`background_fit` could return negative λ** (bug). `A` is bounded at 1.5,
      `lam = 1 − A`, and the only guard was `abs(lam) < 1e-6` — so λ down to −0.5
      passed through and `F = (V/B − (1−λ))/λ` handed a SIGN-FLIPPED form factor to
      the non-negative inversion. Both sibling routines already clipped; this one
      did not. Fix: clip to [0.02, 1.0] **plus** a `RuntimeWarning` and
      `lambda_degenerate` / `lambda_raw` in the result dict — clipping alone only
      converts a sign flip into a differently-wrong answer, so the caller must be
      told the tail fit was degenerate rather than shown a confident distance.
- [x] **Zero-time: boxcar `mode='same'` zero-padding** (risk). Depressed the first
      and last `w//2` samples, pinning the argmax at `w//2` when the trace already
      began at t0 → t0 = −14 ns, outside the data, contradicting the docstring's
      promised residual fallback. Fix: edge-preserving padding. Verified: that case
      now returns `None` → fallback engages.
- [x] **Zero-time: peak beyond the 30 % search cap** (note). `i0` landed on the
      search-window boundary while the trace was still rising; measured +184 ns
      error with no failure signal. Fix: return `None` when `i0 >= ns−1`.
- [x] **Zero-time: asymmetric fit window** (was PLAUSIBLE — resolved by hand, see
      below). The two threshold walks are independent and the docstring promised
      symmetry. Fix: symmetric half-width **plus** clipping the vertex to its own
      window, returning `None` when it extrapolates outside.

### The skeptics split on the asymmetric window — settled on real data

Worth recording as method, not just result. Skeptic 1 CONFIRMED it (+38 ns bias at
zero noise); skeptic 2 REFUTED it, correctly observing that `deer.simulate` is
**even in t**, so a trace generated the way every existing benchmark generates one
is symmetric about t0 and shows no bias.

Both were reasoning from synthetic data. I settled it on the **real Bruker traces**
in `~/deer_benchmark/`:

| trace | R/L window ratio | parabola vertex | echo max |
|---|---|---|---|
| sample1/2 (4 traces) | 0.9–1.25 | ≈ argmax | fine |
| sample3_labA | **3.5** | 0.0787 | 0.1000 (−21 ns) |
| sample3_labB | **22.0** | **−0.9053** | 0.0320 (**~940 ns outside**) |

So the asymmetry is real on real data, worse than either skeptic's estimate, and in
the worst case the vertex lands entirely outside the echo region — unclipped. Both
skeptics were reasoning from a forward model that cannot exhibit the effect.
**Lesson for S2–S6: `deer.simulate` is even in t; a finding about time-asymmetry
cannot be confirmed or refuted with it. Use real traces.**

### Regression after the fixes

- Kernel vs DeerLab unchanged (1.6e-4); background vs `bg_hom3d` 4e-11.
- Synthetic recovery: 3.0 / 4.0 / 5.0 nm → 3.00 / 4.02 / 4.96 nm.
- All four engines (sequential / joint / mellin / gauss) run end-to-end, agree
  within 0.04 nm on a 4.0 nm test case.
- Real Bruker traces: sane t0 on all, catastrophic cases now fall back cleanly.

### Not changed (deliberately)

`NU_DD = 52.04` is kept. The panel's 52.041016 differs by 2e-5 relative → 7e-6 in
r, far below any experimental resolution, and changing it would shift every
historical result for no physical gain. The **docstring** credits the wrong g
(it says g = 2.0023 while the value corresponds to g_e = 2.0023193) — noted, not
yet corrected. Other notes (form-factor reporting difference between
`deer_invert` and `deer_invert_joint`, the `(k·t)^(d/3)` vs `k·t^(d/3)` convention,
the hardcoded 52.04 in `_gauss_mc`'s Pake band) are recorded in the S1 report.

---

## Session 2026-07-25 — S2 Tikhonov: review stage done, verification deferred

Run `wf_789813f0-a0b` — six concurrent dimension reviewers (α selection, NNLS
algebra, CI coverage, joint engine, orchestration+GUI, DeerLab cross-check),
~2.9 M tokens, 3 h 20 min. Stopped deliberately after stage 1; the 2-skeptic
verification is the next session's work. Full interim report:
[REVIEW_S2_tikhonov.md](REVIEW_S2_tikhonov.md).

**38 raw findings → 15 unique bug/risk** (merged by file:line, so the three
reviewers who independently hit `deer.py:629` become one finding carrying all
three write-ups) **+ 17 notes. None verified** — S1 refuted findings that looked
just as solid at this stage.

### Fixed in-session — an S1 regression, not a stage-1 hypothesis

S1's `_crop_pre_zero` shortened the engines' result arrays, but all three engine
tabs then restored the **full** acquisition axis (`res['t'] = x * tf`), so the DEER
window raised `ValueError ... 354 ... 338` on every real trace — **all 28** YopO
traces carry pre-t₀ samples (4–40 each). Reproduced directly, then fixed at
`deer_analysis.py:1844` / `:1924` / `:2012` with `res['t'] = x[t_us >= 0] * tf`
(masking on `t_us` so it is bit-identical to the engine's own crop), and verified
by driving the GUI's exact transform over all 28 traces: axis length now matches
the result arrays on 28/28.

*Lesson: S1 verified its fix against the math and the benchmark harness, not
against the GUI — and `benchmark.py:46` pre-crops where the GUI does not. That is
the second time this session boundary bit. Any engine-signature change needs one
GUI-path smoke run before the session closes.*

### The headline measurement: no regression from S1, but the CI is narrow

DeerLab cross-check over 28 real YopO traces holds at overlap **0.9781** and
|Δpeak| **0.0245 nm** (historical 0.978 / 0.024), and the harness-crop vs
`_crop_pre_zero` paths agree to **1.00000** on all 28. α selection matches DeerLab
EXACTLY on a shared grid; the regularization operator matches to 2.6e-11 up to dr²
with no boundary off-by-one; λ round-trip and `∫P_density dr = 1.0000` are clean.

The open question is **uncertainty, not the point estimate**: measured coverage of
the nominal 95 % band runs 0.94 (narrow, low noise) down to 0.75 (bimodal) and
**0.19 at the `alpha_factor` 2–4 the docstring itself recommends**. DeerLab's band
under-covers too (0.883) but is 3.6× wider on real data. Whether that is a defect
or intrinsic to covariance CIs on a constrained estimator is exactly what the
skeptics are for.

---

## Session 2026-07-28 — S2 stage 2: verified, 9 confirmed, all fixed

Run `wf_502ac692-564` — 28 skeptics (2 per finding, default stance REFUTED),
2.4 M tokens, 7 h 43 min, 0 errors. **9 confirmed, 3 plausible, 2 refuted.** Full
verdicts and both skeptics' reasoning per finding:
`~/deer_benchmark/s2_verify_results.json`. Report:
[REVIEW_S2_tikhonov.md](REVIEW_S2_tikhonov.md).

### Priming the skeptics with the report's own caveats changed three verdicts

The interim report's *For the reviewer of stage 2* section was injected into the
skeptic prompts as per-finding caveats keyed by `file:line` (in
`~/deer_benchmark/s2_verify.js`), not left as prose for a human to remember:

- Both findings downstream of the in-session axis fix (ME1 `nan`, `ptp` reliability
  bands) came back **REFUTED 4/4**, each skeptic reproducing the pre-fix failure
  first and then the fixed behaviour. One went further: the numbers finding 14 calls
  wrong are the pre-fix values, and its own "should be" figures are what the code now
  emits. Told to judge the committed-then transcript, they would very likely have
  confirmed both.
- The four-route CI cluster split (2 confirmed, 1 confirmed-with-split-severity,
  1 down to a wording note) instead of confirming four times.
- Finding 5 downgraded to a note on reachability — k = 0.20–0.40 /µs against a real
  maximum of 0.0473.

*Lesson: a caveat that only exists in the report does not reach the agent that needs
it. Ship review context as prompt data keyed to the finding it qualifies.*

### Fixed (all 9 confirmed, plus 2 of 3 plausible as documentation)

Wrong numbers: joint `F_fit` from `P_norm` (reported R² −1.90 where the true fit
gives +0.25 when P(r) mass sits outside the r grid); `tikhonov_nnls` aborting the
whole scan on scipy's 600-iteration default. Silent failures now announced:
`at_bound` on a grid-edge α, `corner_ok` for the L-corner, and
`lambda_raw`/`lambda_clamped`/`tail_abs_F`/`k_ratio` from `joint_background` with a
`RuntimeWarning` and a ⚠ line in the DEER window. Presentation/cost: the diverging
band no longer drives the P(r) autoscale (at α = 1e-4 the band reaches 4376 nm⁻¹
against a 3.25 nm⁻¹ peak; P(r) now fills 90.9 % of the axis instead of being
squashed flat), manual α skips the selection scan (**14.69 s → 0.38 s in the
GUI**), and
every "95% CI" label now says the band propagates noise only, with the measured
coverage numbers. Details and the four deliberate non-changes — the
`joint_background` collapse guard above all, which belongs to S4 — are in the report.

### Regression gate

Real ring-test set, GUI path, both engines: 56/56 inversions complete, `sum(P)`
0.975–1.009, **0/56** α-at-boundary, `tail_abs_F` max 0.045 (threshold 0.05, 0/28
fire), k cross-check fires on 6/28 joint runs (ratios 2.1–59×; in the two extreme
ones it is the *sequential* fit that collapsed, k on its 1e-4 floor / 2.5e-4). GUI smoke-run offscreen per the S1 lesson: both engines,
`fit_t0`, manual α, α×3 and the L-curve view all render with
`len(res['t']) == len(form_factor)` = 338/338. DeerLab cross-check re-run post-fix
(`~/deer_benchmark/batch.py`, 28/28 traces): mean P(r) overlap **0.978** (min
0.816), mean |Δpeak| **0.024 nm** (max 0.327), mean |Δλ| vs the labs' own values
0.0259 — identical to the pre-fix S2 baseline and to the historical figures, so
none of the S2 fixes moved the sequential result.

## Session 2026-07-29 — S3 Mellin core: 7 confirmed, 0 refuted, all fixed

Run `wf_080dd2f1-054` — 26 agents, 2.36 M tokens, ~5 h, 0 errors. Same structure as
S1: 3 blind derivers + 2 code reviewers concurrently, then a reconciler that saw
both, then 2 skeptics per bug/risk. **7 confirmed, 3 plausible, 0 refuted, 11
notes.** Report: [REVIEW_S3_mellin.md](REVIEW_S3_mellin.md).

### The transform is CLEARED — do not re-derive

The panel agreed **to 12 significant figures** on Φ(s), on the reflected forward
relation `Ṽ(s) = Φ(s)·P(1−s)`, on the inverse prefactor `(1/2π)·w^(−1/2)` and on the
w→r Jacobian `3w/r`; the code matches all of them. The decisive check was a
**convention-sensitivity sweep**: the unnormalized recovered area is 0.9837, and
every alternative convention breaks it loudly (no conjugation → 8e-5, Jacobian r^−3
→ 2.98, w without the 2π → mean 1.65 nm instead of 2.99). So the session's stated
nightmare — a bespoke transform with a silent convention error and no external
implementation to catch it — is ruled out.

### The defects were all in the layer AROUND the transform

`mellin_delta`'s floor was an **absolute** 90 ns, so for r₀ ≲ 2.5 nm it handed most
of the first dipolar oscillation to a single parabola: overlap **0.166 at 1.6 nm**.
It was tuned on a synthetic benchmark whose 13 distributions all peak between 3.0
and 4.3 nm — precisely where the clamp is harmless. Fixed with a `floor_ratio`, so
the floor may stretch δ to at most 2× the trace's own decay scale: 0.166 → 0.678 at
1.6 nm, 0.763 → 0.908 at 2.0 nm, and **bit-identical at r₀ ≥ 3.0 nm**.

*Lesson, and it is the same shape as S1's and S2's: a constant tuned on a benchmark
inherits that benchmark's blind spot. Check the range a tuning set actually covers
before trusting a tuned default outside it.*

### The one wrong number, found three ways

`_MELLIN_I_S[1] = 4.35466` is **0.92 % too high** — it corresponds to Φ(1/3) taken
as **3 exactly** instead of 2.972800. Found independently by the moments reviewer,
by the blind reconciler, and by me before the panel returned. n = 2, 3, 4 are right
to their own rounding and, incidentally, are the g_e set, not the "for g=2" the
comment claimed. Consequence is confined: `I(s)` is consumed only by
`moment_error_apriori`, so every ME₁ was low by 0.908 %.

*The blind panel earned its cost here. The constant is quoted to six digits with a
paper citation, and the paper's own anchor number (std(M1) = 0.0400 nm) is closer to
the WRONG constant than to the right one — so nothing except an independent
derivation could have adjudicated it.*

### Also fixed

The parabolic echo-top correction silently switched itself off below 3 samples in
its fit window (a purely acquisition-driven jump: overlap 0.968 at dt = 32 ns,
0.849 at 40 ns); `_tail_noise` returned a 10.8–12.5× inflated σ for 12–28 positive
samples by putting the convolution edge back that the line above had just removed;
the docstring's and tooltip's "conservative bound" guarantee on ME₁ is false
(measured std/ME₁ up to 2.64, RMSE/ME₁ to 41.8) and is now stated as a noise floor;
and the GUI printed a mean from the signed density beside a width and skew from the
clipped one — a gap of up to 6.4× the ME₁ shown next to it.

*My first `_tail_noise` fix was wrong and the verification caught it: the suggested
`resid[hi-4:hi]` slides into the LEFT zero-padded edge, which `mode='same'` also
creates and which the finding never mentioned. Verify a fix against the failure it
targets, not against the finding's prose.*

### Regression gate

GUI smoke run offscreen (the S1 lesson), Mellin engine with `fit_t0`, all 28 real
ring-test traces: **28/28** complete, axis lengths matched, moments finite — and the
δ spinbox reads 0.09 on real data, confirming directly that the S3-1 fix does not
touch the real-trace regime. DeerLab cross-check re-run post-fix (28/28): overlap
**0.978** (min 0.816), |Δpeak| **0.024 nm**, |Δλ| **0.0259** — identical to the S2
baseline, so nothing here moved the Tikhonov path. Synthetic δ gate: bit-identical
at r₀ ≥ 3.0 nm across four noise levels, large wins below 2.5 nm. All four engines
run end-to-end.

### Environment

**`sympy` and `mpmath` were not installed**, though S1's and S2's environment blocks
both told their agents they were. S3 leans on symbolic work harder than any other
session, so this was found and fixed early (sympy 1.14.0, mpmath 1.3.0). Do not
propagate an environment claim without checking it.

## Session 2026-07-30 — S4: 10 confirmed, 0 refuted, all fixed

Two runs: `wf_79b3f216-ad5` (24 agents; stages 1–2 plus 15 of the 24 skeptics, then
paused) and `wf_f77b0b07-2aa` (the standalone continuation from a **new** session —
11 skeptics, 0 errors, banking the 15 verdicts already collected). Full report:
[REVIEW_S4_mellin_engine.md](REVIEW_S4_mellin_engine.md).

Structure: 5 concurrent dimension reviewers (joint-background rate fit, τmax
selection, MC band + noise, forward fit/δ/droop, call sites) → triage that merged
**38 raw findings into a 12-entry queue** → 2 adversarial skeptics per finding,
default stance REFUTED. A 13th entry was added mid-flight, spun out of S4-8's
refutation, and got its own two skeptics. Final: **10 CONFIRMED, 3 PLAUSIBLE, 0
REFUTED**; every confirmed finding fixed and **not one landed as suggested**.

### Both big hand-overs are answered

- **H1 (collapse guard)** — CONFIRMED, mechanism fully characterized: `vss(log k)`
  has 3–4 local minima and the two adopted branches differ by **0.032 % in vss while
  k differs 19×**, so `minimize_scalar` is picking a *basin*. One 10 ns `bg_start`
  step moves the reported mean **3.517 → 4.527 nm**. Two new facts S2 did not have:
  the bad branch **is already flagged** (14/14 mis-branches in a noise ensemble fired
  `k_disagrees`), so it is a knife-edge not a silent failure; and *dropping the wide
  fit* survived both skeptics' gates (mean |ln k/k_true| 0.176 → 0.095, adjacent jump
  2.24 → 0.012, 28 real traces move ≤ 0.027 nm) while the weaker "drop only the decay
  test" variant was refuted. **The wide cap is now deleted** (re-gated in-session:
  long-r family bit-identical, adjacent |Δln k| 2.2333 → 0.0093, real traces 0.46 %
  median in k / ≤ 0.031 nm in mean distance), and `joint_background` is ~2× faster.
- **H2 (λ/k CI propagation)** — the Mellin MC band **does** inherit the deficit. Two
  reviewers contradicted each other (1.0× vs 2–11×) and the skeptics resolved it to a
  single knob: band/scatter at the peak is **0.457 at the GUI's default Auto τmax**
  and 0.746 at `tau_max=30`, with bit-identical background fits. *The narrow
  configuration is the default.* Method lesson recorded: never validate this band at
  a pinned high cutoff — it inflates it 3.0–3.7× and hides the defect. **Disclosed,
  not re-derived:** the Mellin result now carries `ci_kind = 'mc_fixed_bg'` and the
  tooltip states the real noise source, the conditioning and the measured 78–91 %
  coverage. The bootstrap that would actually fix it is deferred to S6 — at 418 ms
  per realization it is ~21 s at the GUI's n_mc = 50, on a path wired to live update.

### The unexpected one

**S4-6, from the call-sites reviewer, outside the nominal scope:** a Bruker file that
states no time unit was read in whatever unit the selector happened to show, and µs is
the session default with no `else` branch and no settings restore. Roughly a quarter
of the validation corpus is affected (hand-saved / third-party-converted files; every
file written by our own spectrometer carries its unit). Reproduced through the real
GUI: peak **16.11 nm** instead of 2.438 nm, R² nan, and a 171-character integer
printed into the info panel from `%.2f` on `lambda_raw`. **Fixed and re-verified
through the GUI:** the unit is now inferred from the trace span before the trace is
registered, the advisory survives into the final status line, `_unit_changed`
re-derives the auto distance window, and **no file reports a distance above 9 nm**
where seven did before.

### Method notes worth keeping

- **Two reviewers disagreeing was more productive than either being right.** The H2
  contradiction was only resolvable because both had left runnable harnesses; the
  skeptics re-ran them on one shared setup and found the single differing knob. Give
  contradicting findings to the skeptics as one queue entry, not two.
- **Priming the skeptics with triage caveats keyed to `file:line` again changed
  verdicts** — S4-3's "with no flag" headline was refuted by both skeptics on exactly
  the point its caveat flagged (the warning already exists and fires 17/17).
- **API 529s killed 3 of the first 6 agents.** Because `resumeFromRunId` is
  same-session only, the recovery path had to be built by hand; it now exists as
  `~/deer_benchmark/s4_persist/build_resume.py` +
  `~/deer_benchmark/s4_verify_resume.js` and is reusable for S5/S6. Long
  multi-agent review runs should persist their stage output outside the session
  directory *as they go*, not at the end. (The builder itself had a latent bug — a
  line-anchored substitution that left the previous data block behind — found and
  fixed when the continuation session first ran it.)
- **A refuted payload was worth more than a confirmation, twice.** S4-8 and S4-10
  both had exact mechanisms and over-reached consequences; both times the corrected
  aim came out of the adversarial pass, not the review pass.
- **Ask the skeptics to gate the fix, not only the finding.** All 13 suggested fixes
  were wrong, incomplete or optimistic, and three would have made things worse.

### What was fixed

Order per the report: S4-6 first, then S4-1 and S4-4, re-baseline, then S4-2.

- **S4-6** — the time unit is inferred from the trace span before the trace is
  registered, the advisory is folded into the loader's final status line (it was
  being clobbered), `_unit_changed` re-derives the auto distance window while it
  still holds auto values, and `%.2f` → `%.3g` on `lambda_raw` in both the panel and
  the engine warning.
- **S4-1** — `deer_validate` pins `tau_max`, `n_tau` and `delta` for
  `engine='mellin'`. Gated on a background-start sweep deliberately straddling a
  cutoff change: trials used to mix τmax **{12, 32, 40}** (n_tau {800, 2133, 2667});
  they now all inherit the central trial's, and the reported band area drops
  **0.163 → 0.018 (9.0×)**.
- **S4-4** — the wide-cap collapse guard is deleted; `k_at_bound` (S4-3) added
  alongside it, since the bracket-edge case is what survives.
- **S4-8(b) + S4-13** — `deer_validate` returns per-trial `trials` / `trial_spread`
  with a majority rule, and the reported row now describes **one** density (the
  central trial) with the ensemble reported separately. On S4-8's own demo the
  bifurcation is gone: r_mean **4.412 → 3.499 nm** (truth 3.500), trial spread
  **1.10 → 0.016 nm**.
- **S4-2** — the short-r taper is an absolute window (`fit_rmin_abs`,
  `fit_rmin_width`), not a fraction of the r range, re-tuned over nine candidate
  windows. Grid dependence of the reported mean **0.617 → 0.009 nm**, r_min bias
  **0.319 → 0.000**, bimodal population error **0.240 → 0.010**, at a deliberate
  mid-r cost (overlap 0.805 → 0.762) that the sweep shows is unavoidable: every
  wider window buys that back by deleting a real short-r peak.
- **The echo-top parabola** (found while gating, not a queued finding, pre-existing):
  on a noisy shallow-modulation trace the δ crossing and the curvature window are
  both set by single noisy samples, so δ collapses (141 → 37 ns from σ 0.02 → 0.04)
  and |b| reaches ~560 against a noise-only scatter of ~230 — leaving the forward fit
  above the data across the whole echo top. Fixed by smoothing the crossing (a no-op
  below rel-noise ≈ 0.09, so the tuned regime is untouched by construction) and a
  9-sample curvature-window floor **under the same gate** — ungated it degraded the
  28 real traces (residual up to 6.6× worse, one peak moved 1.40 nm), because on
  clean data the parabola is only valid very near the echo top. Gated, all 28 real
  traces are bit-identical. **The fits are repaired; the distributions are
  not** — the broken curvature had been an accidental regularizer, so every way of
  repairing it costs ~0.10 overlap on the case it fixes. The real lever is the
  zero-time fit (+0.085 overlap, and it removes most of the collapse): queued below.
- **S4-7 / S4-9 / S4-11** — fit quality judged against the independent noise floor
  with the "overfit" arm dropped and `neg_area` added; the τmax-selection checkbox
  relabelled, rewired to refit, and four false docstrings corrected; `_tail_noise`
  returns NaN for "cannot measure" so a missing CI band says why.

**Not implemented, by verdict:** S4-10 (0/28 real traces at a bound, 25/28 already
flagged, and both the proposed detector and the tighter `[2, 4]` dimension range were
refuted — DeerLab's own bounds are wider) and S4-12 (R² −29 … −288 already announces
it, and the proposed clamp is inert *and* makes the result look more plausible).

### Regression gate

Pre-fix baselines were taken from a pristine `git worktree` at HEAD, so every "before"
number below is the shipped code, not a memory of it.

- **`unit.py`** — passes. Two synthetic values move slightly with the tight-cap
  background (`sum(P)` 0.2532 → 0.2510, R² 0.2518 → 0.2493) on a case deliberately
  built with the truth *outside* the r grid; its assertions (interior index,
  `corner_ok`, `at_bound`) still hold.
- **`check.py`**, 28 real traces × both engines — **identical counts**: 0 α-at-bound,
  6 joint warnings, 6 `k_disagrees`, 0 traces with `tail_abs_F` > 0.05, `sum(P)`
  0.994–1.008. Per-trace λ and R² match the baseline to 3–5 dp.
- **`gui_smoke.py`** (offscreen, the S1 lesson) — every substantive field identical:
  α, `ci_kind`, axis lengths 338/338, band behaviour, statuses; joint λ 0.414 → 0.415.
  Only the CPU times differ (the machine was running 15 jobs).
- **S4 GUI-path smoke** (new, `~/deer_benchmark/s4_fix/s4_gui_smoke.py`) — the panel
  code S4 touched renders in all four modes: Mellin + CI, Mellin + Validate,
  Tikhonov + Validate, and a trace too short to measure a noise floor, which now
  prints *"no band: the noise level could not be measured"* and the new
  `k pinned at its search bracket edge` flag instead of silently dropping the band.
- **DeerLab cross-check, pre-fix baseline** — overlap **0.978** (min 0.816),
  |Δpeak| **0.024 nm** (max 0.327), |Δλ| **0.0259** over 28/28 traces, matching the
  S2 and S3 figures exactly.

## Notes ready to implement (S5/S6 queue)

Unverified — no skeptic ran on these — but each carries the reviewer's own numbers.
Full text in `~/deer_benchmark/s4_persist/s4_triage_notes.json`, summary in the S4
report.

1. **Widen the τmax candidate grid.** `[6 … 40]` clamps silently at both ends where
   `l_curve` warns; the ceiling is picked on 10 of 28 real traces. `[3 … 60]` gains
   +0.017 mean overlap over 72 synthetic conditions (oracle +0.045) for ~35 % cost.
   Needs a boundary flag either way. *Closest finding to the verification cut.*
2. **Guard `_masses` relatively, not absolutely.** It normalizes by the signed area
   with a fallback only at |area| < 1e-12, nine orders below the smallest reachable
   value; at low λ a negative area returns the exact negative of the honest density.
   The guard must be `area < eta·positive_area`, gated on the synthetic suite.
3. **Make a failed `_fit_rate` visible.** Both arms end in
   `except Exception: return kref, d0`, so a failure degrades to the sequential fit
   with `k_ratio` exactly 1.0 and no warning; one non-finite sample before `bg_start`
   is enough, and the NaN travels on into the inversion.
4. **Unify the λ clamp** — 0.95 / 1.0 / 0.98 in one module.
5. **`du = 0.005` as the default?** H3 is answered: the aliasing story is refuted
   (S3's overlap gap was a forward-model r-quadrature artifact); what `du` costs is
   noise decimation (mean-distance bias +0.037 → +0.009 nm). The two reviewers split
   on changing the default (+0.016 overlap at 1.46× cost vs no action); both rejected
   a data-driven `du = dt/Tmax` rule.
6. **The two non-default τmax methods are broken** and unreachable from the GUI:
   `'discrepancy'` silently becomes argmin(σ_fit) on 17/28 traces, `'lcurve'` cannot
   return its end candidates and has no no-corner fallback. Fix or remove.
7. **The forward model is a rectangle sum over the user's r grid** and needs
   dr ≪ r⁴/(6·ν_dd·T); the GUI default violates it 6× at r = 2 nm on a 10 µs trace.
   Not reachable on real traces, but it affects the Tikhonov kernel too.
8. **`joint_background` defaults `bg_start` to 0.6 × span** while every other engine
   uses 0.5 × span — invisible from the GUI, but scripts and mirrors see it.
9. ~~Fit the zero-time on a lightly smoothed trace.~~ **DONE** — see below.

## The zero-time lever — applied (2026-07-31)

The +0.085 overlap figure was an **oracle**: it came from handing the engine the
true t0. The realizable fraction from a better estimator is **+0.033**, and getting
it needed a specific diagnosis rather than "smooth more".

The weak link is not the smoothing width but the `drop`-walk that sets the fit
window: it thresholds the smoothed trace `drop` below the peak, so once the smoothed
noise is a sizeable fraction of that drop it stops on noise and hands the parabola a
window a few samples wide. Above a measured noise-to-amplitude ratio of 0.055 the
window is now widened to >= 8 samples either side, the parabola is fitted to the
smoothed trace, and the edge-padded samples are dropped. A symmetric boxcar leaves a
quadratic's vertex exactly where it was — verified, not assumed — but
`np.pad(mode='edge')` does not, and on a DEER trace the echo sits near the start so
the window reaches the edge on ~35 % of traces (bias -1 to -3 ns); hence the guard.

**Measured** (12 condition x shape pairs x 4 noise levels, both engines, paired
seeds): +0.0328 Mellin and +0.0339 Tikhonov overlap at hard sigma 0.04, +0.0074 /
+0.0078 at sigma 0.02, and the Tikhonov mean-distance error halved (0.225 -> 0.113
nm). Bit-identical on the whole `easy` condition, on `hard` sigma <= 0.01, and on
**all 28 real traces** (their noise-to-amplitude ratio is 0.004-0.025 against a gate
of 0.055, so the new path never fires on real data).

**Why this one shipped where `xcheck` did not.** The `fit_zero_time` docstring
records an earlier, more accurate t0 estimator that *lost* 0.015 overlap: it raised
the worst-case error, and a slightly-late t0 had been cancelling a Mellin-specific
forward bias. Three checks separate this change from that trap — both engines move
together and by the same amount (a cancellation would move them oppositely), the
gain appears at two different noise levels rather than only where the bias bites,
and the worst-case t0 error is unchanged (120 ns, one seed where the estimator fails
outright rather than imprecisely). Two independently written estimators, one mine and
one an agent's, produced +0.033 on this metric.

*Caveat for whoever revisits it:* at 4 seeds the +0.033 is ~2.7 sigma on its own; the
cross-engine and cross-implementation agreement is what carries it, not the single
number. The 0.055 gate is derived from the walk geometry but calibrated on this
benchmark's amplitude scale — a dataset landing between 0.048 and 0.067 would sit on
the boundary, and none exists to test that.

## Next session — S5 (multi-Gaussian)

Hand-overs that were waiting for S4 are all resolved: H1 → S4-4 (fixed), H2 → S4-5
(disclosed; the bootstrap is S6), H3 → refuted and reframed (note 5 above),
H4 → S4-11 (fixed), H5 → S4-12 (plausible, no action).

Carried into S5 by S4's own findings: `engine='gauss'` has the **identical**
`deer_validate` hole S4-1 fixed for Mellin — `n_gauss` is re-selected per trial
through the same `**kwargs`, so the validation band mixes component counts.

**The port is now four sessions deep.** `deer.py` is byte-identical across plain /
NIOCH / NIOCH_Q / Cryomech while ITC carries S1 + S2 + S3 + S4; `deer_analysis.py`
exists only in ITC / NIOCH / NIOCH_Q. Port together, and run
`~/atomize_sync/sync_check.py` first.

## Queued: a band that deserves the name (from the S2 CI findings)

S2 did the zero-risk half — the band no longer claims coverage it does not have.
These two are the other half. **No band centred on a regularized estimate can cover
the truth at the mode**, because the dominant error there is bias, not noise, so
neither of these is a "true CI" on its own; each fixes a specific, measured hole.
"Match DeerLab" is not the target — DeerLab's own band measured 0.883 support /
0.480 modal coverage in S2. Judge both against the skeptics' coverage harnesses,
which already exist: `~/deer_benchmark/{sk1_ci,sk2_cicov,sk1_cicov2}/`.

### 1. Propagate the joint fit's λ/k covariance — **S6** (S4 disclosed it, did not fix it)

Targets confirmed finding 9, the largest verified error in the uncertainty
machinery: the joint band is **7–8.6× too narrow** where the *identical* formula is
honest to ~1.3× in sequential mode on the same data (skeptic controls: coverage of
the ensemble *mean* at the peak 0.033 joint vs 0.900 sequential; band/scatter ratio
0.133 vs 0.96). `tikhonov_ci` conditions on the fitted background and λ, and in the
joint engine those are themselves fitted — their scatter dominates. This is a
defect, not a philosophical limit, and it is self-contained: either propagate the
rate fit's covariance into the linear band, or bootstrap the joint pipeline
(item 2). Acceptance: band/scatter ratio within ~1.5× on the S2 Monte-Carlo setups
at k = 0.05 and k = 0.30, with the sequential engine unchanged.

S4 confirmed the same deficit in the **Mellin** MC band (S4-5) and shipped only the
honest half — a distinct `ci_kind`, and a tooltip that states the noise source, the
conditioning and the measured coverage. Two constraints it added for whoever
implements this: re-fitting `tau_max` per realization folds a *discrete* selection
instability into a Gaussian ±1.96σ summary and must not be done (re-fit the
background and λ only, cutoff pinned); and the cost, 418 ms per realization, is ~21 s
at the GUI's n_mc = 50 on a path wired to live update — so it needs a button and an
n_mc cap, not a checkbox.

### 2. Residual bootstrap over the whole pipeline, on demand — **S6**

Resample the fit residuals, refit background + λ + P(r) per trial, take percentile
bands — what DeerLab does, and now cheap enough to be practical: one inversion at
fixed α with `scan_lcurve=False` measures **1.6–1.8 s under load, 0.38 s idle**
(GUI smoke run), so 200 trials is ~1.5–6 min single-threaded and well under a
minute across the 4 cores. A button, never the live-update path; `rThread` is the
house concurrency primitive. **Be explicit in the UI about what it does not fix:**
bootstrapping a biased estimator gives an interval for the estimator's expectation,
so the mode still under-covers. Re-selecting α per trial (rather than freezing it)
folds in the selection variance and costs 36× more — measure whether it is worth it.

Two further options were considered and are NOT queued: swapping the estimator to
Wahba's Bayesian form σ²G⁻¹ (one line, 1.44× wider, support coverage 0.800 → 0.925,
but it moves every shipped band and CSV and still leaves the mode optimistic), and
undersmoothing the band at α/4–α/8 (the only cheap route that genuinely covers the
truth, needs a calibration pass). Revisit both once 1 and 2 land and there is a
coverage table to argue from.
