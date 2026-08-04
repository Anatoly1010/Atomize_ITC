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
| `atomize/math_modules/deer.py` | 2992 |
| `atomize/control_center/deer_analysis.py` | 3213 |
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

## Session 2026-07-31 — zero time (2 rounds), Mellin δ rejected, pre-t₀ display

Not a review session: three targeted changes driven by broad distributions failing
at the highest synthetic noise. Two shipped, one rejected. The lasting methodological
lesson is in the δ entry — a rule tuned on a broad-heavy case list passed every check
that list could run and still destroyed short distances, which only a full shape sweep
exposed. Every number below is from seed bases the tuning never used.

### The zero-time lever — applied

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

### Round 2 — the centroid replaces the vertex

The window widening above was half the fix. On fresh seeds the broad distributions
were still failing: mean |t0 error| 16.5 → 11.3 ns from round 1, but `gauss_broad_long`
still averaged 37 ns with a 125 ns worst case, and a late t0 biases P(r) SHORT
(−0.49 nm on one spot-check). Two things break the parabola together, and both worsen
the broader P(r) is — the echo top goes flat, so the vertex −b/2a is a ratio of two
numbers that are both noise; and the argmax that anchors the window is a
winner-take-all pick among dozens of near-equal noisy samples, with up to 120 ns of
error on its own that no local refinement can undo.

Above the same 0.055 gate the statistic is now the **centroid of the echo top**
(`_centroid_zero_time`), iterated to a fixed point. V is even about t0, so the
centroid of any symmetric weight IS t0 — no curvature needed — and it is LINEAR in V,
so the same samples average instead of competing.

**Measured**, 21 shapes on a third seed base (out of sample for the tuning), 168
noisy traces: mean |t0 error| 15.2 → 10.5 ns, worst 163.7 → 63.7, concave-peak
failures 8 → 1 (each costs the caller a full residual search — 33 s → 0.4 s over the
noisy set). Overlap **+0.0098 Mellin (t = 2.73) and +0.0111 Tikhonov (t = 3.55)**:
both engines, both significant, no shape group regressing (sharp +0.007/+0.022, edges
−0.003/+0.005, short-r +0.008/+0.001, broad +0.018/+0.011). All 28 real traces
bit-identical. Three shapes dip past −0.01 on Mellin (rectangle, narrow-at-5 nm,
bimodal σ0.55) but Tikhonov *improves* on all three at n = 8, so they read as scatter.

Two corrections to round 1's write-up, both found by testing shapes it never used:

* "the whole easy condition is bit-identical" is **not** exact — a weak-modulation
  short-distance shape (2.0 nm) reaches ratio 0.059 at σ 0.02 and crosses the gate.
  The effect is negligible (t0 +0.42 → +0.37 ns) but the honest statement is
  "identical *below the gate*", not "identical on easy".
* the declared weakness — a trace whose zero time sits 1–3 samples into the record —
  is real as an estimator number (|t0| 29.1 → 31.3 ns at 1 sample) and **wrong as a
  verdict**: end-to-end the overlap *improves* on both engines there (+0.014/+0.018).
  A `min_pre` guard was built and rejected; every threshold that caught it mis-fired
  often enough elsewhere to cost more than it saved.

### The Mellin δ — direction confirmed, change REJECTED

Tested because the flat-echo failure looked like it might be a δ problem. It is not,
and the intuition that δ should be *lowered* is backwards: paired against the auto δ
on identical traces, δ = 40 ns costs −0.0135 overlap and δ = 200 ns gains **+0.0250
(t = 3.11)**, the optimum sitting ~1.7× the 96–140 ns the auto rule picks. It survives
pinning t0 to the truth, so it is a genuine δ effect and not the zero-time error in
disguise. Mechanism: at high noise the binding constraint is `floor_ratio`·d_raw — the
0.85-crossing collapses to ~50 ns under noise and 2× that caps δ near 100 ns, so the
floor/cap bump never gets to act.

A candidate rule that opens `floor_ratio` above the old bump ceiling was **rejected on
the shape sweep**. It gains +0.0106 overall (t = 2.58) and is bit-identical on easy,
but it destroys short distances: r = 2.0–2.6 nm loses −0.0267 with only 25 % of traces
improving and a −0.29 worst case. Within those cases the correlation between the δ
increase and the overlap change is **−0.707** — where the guard holds δ fixed nothing
moves, where it lets δ rise the trace is destroyed (87 → 156 ns costs 0.451 → 0.163).
The guard keys on `d_raw`, which at high noise is exactly the quantity that has
collapsed. A sound guard must key on the dipolar timescale (δ_max ∝ r³), which is not
known before the inversion — a research round, not a tweak. The gain is also narrower
than the tuning run implied: hard σ0.02/σ0.04 give +0.0006/+0.0015 (nil), and nearly
all of it comes from hard2 σ0.04.

### Pre-t₀ samples are now drawn in the GUI

`_crop_pre_zero` drops every t < 0 sample at the entry of all engines (the kernel
evaluates |ω·t|, so a negative-time sample would be modelled as +|t| evolution and
pile P(r) mass at short r), and `deer_analysis.py` mirrored that crop in the display
axis — so the whole pre-zero region vanished the moment you pressed Run. The engines
still see t ≥ 0 only; the display now rebuilds that block from the engines' OWN
positive-time arrays at |t|, since B(t) and F(t) = K(|t|)·P are exactly even, and adds
a t₀ marker. Verified: the mirrored fit reproduces the engine's fit to 0.0, B matches
exp(−(k|t|)^(d/3)) to 0.0, and the residual RMS over the restored region (0.0101)
matches the fitted region (0.0096) — the fit genuinely describes the pre-t₀ data.

### The Mellin echo-top double maximum — fixed (fit curve only)

Reported from the GUI once the pre-t0 region became visible: on
`gauss_narrow_broad` at sigma 0.04 the Mellin fit shows two maxima straddling
t = 0. It is a real defect and a **regression**, not a new one.

*Provable cause.* `dipolar_kernel` gives K(0, r) = 1 for every r, so
F_fit(0) = sum of the masses = 1. A negative mass at short r subtracts |m| at
t = 0 but less than that at t > 0, because its kernel decays fastest — so F_fit
RISES after the zero time. With non-negative masses summing to 1 and |K| <= 1,
F = K·m <= 1 = F(0) and an interior maximum is impossible. The negatives are the
sole cause; on the reported trace they total −0.137 and lift the fit to 1.0272.

*History.* `d619c3c` built F_fit from the non-negative density for exactly this
reason ("so a negative density can't flip the F_fit curvature at t=0 into a
spurious double peak"). Two days later `5778347` replaced it with `K@masses` of
the signed tapered density, "consistent with the displayed P(r)", betting its new
short-r taper would remove the spike at source. It does not — the taper spans only
r[0]→2.0 nm and negatives outside it still lift the fit. Measured on the 21-shape
catalogue: **a third of noisy traces carry the artifact** (85/252 at the true zero
time, worst rise +0.52), and 4 of the 28 real traces. A late zero time masks it,
which is why the previous round's t0 work is what exposed it.

*Fix.* The guard is restored, generalised, and put on ONE path — F_fit previously
took `K@masses` or `_fwd(f_r)` depending on `taper_short`, and `_fwd` itself
branched on `signed_fit`, so whether any guard applied depended on two unrelated
switches. F_fit is now always built from `_nonneg_cumulative(f_disp)`: isotonic
(PAVA) regression of the cumulative mass, which is the identity where nothing is
negative and *cancels* each ± noise pair instead of deleting the dip and keeping
the spike. Gate: **0/252 synthetic and 0/28 real** interior maxima, at both the
true and the fitted zero time. Reported P(r) **bit-identical** on 252/252
synthetic and 28/28 real traces. The cost is `sigma_fit` +5.8 % mean / +24 % worst
on real data — the signed fit was flattering itself by fitting with a
non-physical model, so a slightly worse honest residual is the correct outcome.

### Queued — project the REPORTED density too (blocked on short r)

Projecting `P_density` as well is better nearly everywhere and would make the
GUI's existing labels true (the checkbox says "before clipping negatives", the CSV
header says "clipped", `distribution_moments` clips internally — yet the engine
returns a signed `P_density`, negative on 251/252 traces down to −4.03, and
`P_signed_density` is an alias of it, so the overlay draws the same curve twice).
Measured: overlap +0.021 (t = 6.96), sharp +0.047, edges +0.034, broad +0.014,
mean-distance error −0.081 nm.

**Blocked** on the same class that killed the delta rule: short distances lose
0.020 overlap (t = −4.65 over 120 traces, only 41 % improving, `short_r26` 20 %),
because at 2.0–2.6 nm part of the pooled "noise" spike is genuine mass. Their mean
distance nonetheless improves 0.096 nm — the peak lands better while the shape
degrades. One real trace also moves 1.92 → 4.24 nm (`sample4_labE`; its six
sibling labs sit at 4.18–4.54 and Tikhonov says 4.67, so it is probably a fix, but
it is a reported result changing). Candidate kept at `~/deer_benchmark/s5_t0/deer_nomax.py`.
Any revival needs a short-r-safe projection and its own gate — it is a change to
what P(r) *means*, not a bug fix.

### Ported and committed

`deer.py` is shared by all five repos and `deer_analysis.py` by ITC/NIOCH/NIOCH_Q
(lead: ITC); both were mirrored byte-identically this session and `sync_check.py` is
clean. NIOCH/NIOCH_Q had also fallen ~200 lines behind ITC on `deer_analysis.py`
(the S3/S4 round), which forced the pre-t0 change to be hand-ported onto their older
text; that lag was then closed separately, so the EPR control centre is fully in
sync again.

Two limits on what any of this has actually been proven against:

* the **zero-time** change has no real-data validation and cannot get any from the
  current corpus — the 28 ring-test traces sit well below the noise gate, so the new
  path never fires on them. It will first act on genuinely noisy measurements.
* the **echo-top** fix does fire on real data (4 of the 28 traces carried the
  artifact), and it is the one change this session that makes a fit residual
  slightly *worse* by design.

## Session 2026-08-02 — a parabolic echo-top head for TIKHONOV (paused, unfinished)

Prompted by a suggestion from the user's colleague: *noise in both Mellin and
Tikhonov — surprisingly more in Tikhonov — can be strongly suppressed by fitting
the initial section of the curve with a parabola.* Round 1 ran; round 2 was stopped
part-way, to be redone on a faster machine. **Nothing here is in `deer.py`.** All
artefacts live in `~/deer_benchmark/s6_parab/`.

### Half of it already ships — on the Mellin side only

The suggestion is exactly what the Mellin δ-split does. `mellin_signal_spectrum(...,
parabolic=True)` does not use the data on [0, δ] at all; it integrates the analytic
parabola in closed form, `int_0^delta (F0 + b T^2) T^(s-1) dT = F0 delta^s/s +
b delta^(s+2)/(s+2)`, and δ is already noise-adaptive (floor/cap 0.09/0.12 → ~0.13/0.16
as `sig_e/lambda` grows), for the stated reason that a wider parabola kills the
short-r spike *at source*. **The Tikhonov path has no equivalent** — which matches
the colleague's observation that the headroom is bigger there.

### The honest window, from the physics (`validity.py`)

K(0, r) = 1 and K is even, so F(t) = 1 − (2/5)⟨ω²⟩t² + O(t⁴), ω = 2π·ν_dd/r³. Widest
window where a parabola stays within 1 % of the NOISELESS catalogue form factor:

| shape class | pinned parabola | + quartic term |
|---|---|---|
| long / broad (4.5–5.0 nm) | 220–330 ns | ≥ 400 ns |
| typical (3.0–4.0 nm) | 65–130 ns | 120–245 ns |
| short r (2.0 nm) | **18 ns** | 34 ns |

At 10 ns sampling a typical head spans only ~7–13 points, but they are the
highest-leverage points in the inversion and the head costs 1–2 parameters.

### Round 1 — 756 traces × 21 variants (`sweep.py` → `sweep.json`)

s5 shape catalogue (21 shapes × 3 conditions × 4 noise levels × 3 reps), r grid
coarsened to 128 points, joint background cached per trace, head applied to F before
`l_curve`/`tikhonov_nnls`. Two results, both sharp:

**1. Pinning F(0) = 1 is what hurts.** Every pinned variant loses: `pin2_50` −0.0055
overlap (t = −7.0), and the level-driven pinned rules — the direct analogue of the
Mellin δ rule — sit at −0.004 (t ≈ −6). Spurious mass below 2.5 nm *rises*, 0.140 →
0.151. At high noise the normalization anchor is itself wrong by more than the noise
on any single sample, and a pinned head welds the whole echo top to that wrong anchor.

**2. Freeing the constant (a + b·t²) flips the sign, and the gain grows with noise:**

| σ | base overlap | best free head | Δ overlap | t | win % |
|---|---|---|---|---|---|
| 0.0025 | 0.9589 | free2_80 | −0.0132 | −2.3 | 44 |
| 0.005 | 0.9272 | free2_80 | −0.0108 | −2.9 | 53 |
| 0.01 | 0.8853 | free2_80 | −0.0024 | −0.8 | 57 |
| 0.02 | 0.8495 | free2_80 | **+0.0033** | +1.6 | 63 |
| 0.04 | 0.7575 | free2_120 | **+0.0119** | +2.7 | 58 |
| 0.06 | 0.7001 | free2_180 | **+0.0213** | +1.9 | 67 |

By class at σ ≥ 0.02: EDGY +0.0149 (t = 6.9, 76 % win), SHARP +0.0145 (t = 5.1),
broad/other +0.0057. Per shape, `free2_120` helps on **20 of 21 shapes**; the single
loser is the one the table above predicts — `short_r20` −0.205 at 0 % win, a 120 ns
head on an 18 ns honest window (`short_r26` +0.047, `gauss_broad_short` +0.022).

### The two design rules that fall out

* **δ must be level-driven, not constant** — the F(δ)/F(0) rule already auto-shrank to
  31 ns on the short-r shapes against 65 ns on typical ones, which is exactly the
  r-gating `short_r20` needs.
* **The head must be noise-gated** — below σ ≈ 0.01 it costs real resolution
  (−0.013 at σ = 0.0025). Gate on the same `sig_e/lambda` the Mellin δ rule uses.

Note the free constant may be doing two jobs at once: denoising the head AND
re-estimating the echo top (a better estimator than `_echo_top`'s ±5-sample vertex,
which is what the pinned anchor comes from). Round 2 records the fitted constant `a`
so the two can be separated — worth knowing, because if it is mostly the echo-top
re-estimate then the cheaper fix is to `_echo_top` itself, not a new head.

### Where it stopped

`sweep2.py` got ~1/756 traces in and was **killed** — 15 s per trace on 4 cores is
~30 min a round here. Resumed 2026-08-03 on a faster box; see the next section. The
two design rules stated above did **not** survive that round — read on before
building on them.

## Session 2026-08-03 — the head, finished: δ from curvature, not from a crossing

Rounds 2–4 of the parabolic head, run on a second machine (`fel@172.16.16.1`,
6-core i5-9400F, ~4–5× this one: 13 min for a 756-trace × 13-variant round against
~30 min here). Still **nothing in `deer.py`**; artefacts in `~/deer_benchmark/s6_parab/`.

### Round 2 reversed one of round 1's two design rules

Round 1 proposed (a) δ must be level-driven and (b) the head must be noise-gated to
fire only at *high* noise. Round 2 (`sweep2.json`, 756 × 13) shows those two are
**incompatible**: the level-driven head only wins at *low* noise.

| σ | `fl75` level-driven | `f2_100` fixed δ |
|---|---|---|
| 0.0025 | **+0.0015** (t 2.0) | −0.0250 |
| 0.005 | **+0.0019** (t 4.8) | −0.0212 |
| 0.01 | **+0.0036** (t 5.6) | −0.0111 |
| 0.02 | −0.0006 | −0.0028 |
| 0.04 | **−0.0107** (t −6.1) | +0.0107 |
| 0.06 | −0.0106 | **+0.0182** (t 2.9) |

**Mechanism: the raw-crossing rule is anti-adaptive.** `delta_from_level` reads the
first sample where F drops below `level`·F(0), so a noise excursion trips it early
and δ *shrinks* as noise rises — `fl85` picks 82 ns at σ = 0.0025 but 51 ns at
σ = 0.04, narrowing the window exactly when a wide denoising window is wanted. At
σ ≥ 0.04 it also *adds* spurious short-r mass (`lo_mass` 0.204 → 0.221).

**The dominant axis is shape, not noise.** SHARP `f4_250` +0.0144 (t 5.7) and EDGY
`f4_250` +0.0141 (t 6.1) are the largest gains available anywhere — and the same
setting is −0.2835 on SHORT. A wide fixed head is simultaneously the best and the
most dangerous option; the level rule was only ever the thing protecting short r.

**Q2 — "is it just the echo-top re-estimate?" — answered NO** (`gate.py`). This was
round 1's explicit open question, with the note that if the free constant were
mostly re-estimating the echo top then the cheap fix is `_echo_top`, not a head.
For the level family mean |a−1| ≈ 0.025–0.035 and **corr(Δov, |a−1|) = −0.04…−0.09**,
i.e. no relationship — the gain is genuine denoising. For the fixed-δ family
corr = −0.49…−0.80 and Δov in the large-|a−1| half is −0.012…−0.118, so a large free
constant is a *failure marker* (a wide window forcing a wrong constant), not a source
of gain. On the 28 real traces a ∈ [0.985, 1.001] — nothing to re-estimate on clean
data. `_echo_top` is not the cheap substitute.

### Round 3 — `delta_from_curvature`, and the fix that made it work

The honest window scales as r³ (ω ∝ r⁻³; `validity.py`: 18 ns at 2.0 nm, 65–130 at
3–4, 220–330 at 4.5–5). The level rule is a *proxy* for that scaling computed on
noisy F, which is why it inverts. `delta_from_curvature` instead takes δ from the
least-squares curvature of the window — δ = √((1−level)·a/−b) — iterated to a fixed
point, so b is a fit over many points rather than one sample.

Two bugs found getting there, both instructive and both fixed:

* **Seeding from the raw crossing** put the noise dependence straight back in.
  Iterate from the *wide* end instead.
* **Seeding from `cap`** runs past the first dipolar minimum, where a parabola fit
  returns nonsense curvature and δ sticks at the cap — `short_r20` at σ = 0.06 went
  to overlap **0.005**. Fixed with `first_min_time()` (smoothed first local minimum
  of F) as the upper bound: past there is not echo top by definition.
* A fixed 30 ns floor holds only **2** samples at `hard2`'s 12.6 ns sampling, below
  `parab_head`'s `n_min`, so the head silently no-opped. The floor is now
  sample-count-driven (`n_min`-th sample), which also fixed the one real trace
  (`sample1_labC`, dt = 16 ns) whose head never fired.

`cv60` then came out positive in **every** class and at **every** σ — the first
variant to do so (ALL +0.0046, t 6.6; SHORT +0.0082 where fixed δ is −0.28). Two
knobs also died: the quartic is worse than order-2 everywhere, and `cap` is inert
because the first-minimum bound always binds first.

### Round 4 — the level series, run down until it turned over

Round 3 never turned over (cv90 +0.0013 < cv80 < cv70 < cv60 +0.0046), so round 4
extended it to 0.05, where the limit is δ = the first-minimum bound itself.

| | cv60 | **cv50** | cv40 | cv30 | cv20 | cv5 |
|---|---|---|---|---|---|---|
| ALL | +0.0046 | **+0.0053** (t 6.8) | +0.0040 | +0.0024 | −0.0018 | −0.0129 |
| SHARP | +0.0055 | +0.0060 | +0.0074 | **+0.0082** | +0.0054 | −0.0042 |
| EDGY | +0.0059 | +0.0081 | **+0.0094** | +0.0093 | +0.0062 | −0.0033 |
| SHORT | +0.0082 | +0.0107 | +0.0079 | +0.0102 | **+0.0123** | +0.0070 |
| broad | **+0.0023** | +0.0019 | −0.0015 | −0.0064 | −0.0141 | −0.0287 |

Per-class optima genuinely differ — broad wants a narrow head, short/sharp a wide
one — but **`cv50` is the best single setting that never loses**, and `lo_mass` falls
0.1404 → 0.1292, so it is not buying overlap by smearing. No noise gate is needed:
`cv50` is positive at every σ, which retires round 1's rule (b) rather than
implementing it.

### NR = 256 production re-check — conclusions transfer, and cv60 catches cv50

`sweep256.json`, 756 × 7 at full r resolution. Every round-4 conclusion holds, and
the two leaders converge:

| | base | cv60 | cv50 | cv40 | cv30 | f2_150 | f4_250 |
|---|---|---|---|---|---|---|---|
| ALL | 0.8563 | **+0.0050** (t 7.3) | **+0.0052** (t 7.0) | +0.0044 | +0.0024 | −0.0278 | −0.0370 |
| SHARP | 0.7963 | +0.0064 | +0.0068 | +0.0081 | **+0.0086** | +0.0153 | +0.0165 |
| EDGY | 0.8596 | +0.0071 | +0.0087 | **+0.0097** | +0.0090 | +0.0147 | +0.0167 |
| SHORT | 0.8927 | +0.0076 | +0.0092 | +0.0095 | **+0.0107** | −0.2553 | −0.3203 |
| broad | 0.8761 | **+0.0023** | +0.0014 | −0.0017 | −0.0068 | +0.0052 | +0.0040 |

At NR = 128 cv50 led cv60 (+0.0053 vs +0.0046); at production resolution they are a
statistical tie and cv60 is the better of the two on broad shapes. Taken with the
real-data result below, **cv60 is the recommendation, not the NR=128 winner.**

### Real data (28 YopO traces) — the honest limit of the whole idea

`real.py` with the curvature rule. Samples 1–3 (2.2–5.5 nm) are clean: |dpeak| ≤ one
grid step, |dmean| ≤ 0.06 nm, dRMS ≈ 0 or negative. **The sample4 group (5.9–7.35 nm)
degrades**: at cv60 dRMS +0.0003…+0.0027 and dmean +0.10…+0.22 nm; at cv50 worse,
including one −0.457 nm peak jump (a mode switch on a multimodal P(r)).

Two explanations were tested and **both refuted**:

* *|a−1| flags it.* No — `valve.py` on `sweep4.json` shows that for cv50 the
  |a−1| > 0.05 group gains **+0.0145**, i.e. it is where the gain lives; vetoing it
  collapses cv50 to +0.0005. The valve works only for the FIXED-δ family (turns
  `f2_150` from −0.0248 into +0.0008), which is Q2 restated, not a new diagnostic.
* *Those traces exceed their r_max.* No — `tmax_check.py`: all 28 sit inside
  r_max ≈ 5·(t_max/2)^(1/3) (sample4 6.99–7.35 nm against 7.83–8.22).

**So it is a real, physical limit.** At long r the echo-top curvature *is* the
distance measurement — ν_dd(7 nm) ≈ 0.15 MHz, one dipolar period ≈ 6.6 µs, so a
200 ns head is ~3 % of a period and fitting that curvature from noisy data adds
error rather than removing it. At short/typical r the echo top is over-sampled
relative to the information it carries, so the parabola denoises. The synthetic
catalogue says the same thing: broad/other is the weakest class and goes negative
as δ widens (cv30 −0.0068 at NR = 256).

The first-minimum bound does not protect against this — at long r it is far out, so
δ grows to 180–270 ns exactly where it should shrink.

### Correction to the bench notes

**NR = 256 costs 4.3× NR = 128, not the ~29× the s6_parab README claimed** (measured
1.95 vs 0.45 s per trace-variant). The production re-check is a ~1.5 h 7-variant
round on 6 cores, not an overnight job. README corrected. Also: `cap` is NOT inert
as round 3 concluded — it binds on 5 of 7 real 5 nm traces (δ = 350 ns), it is only
the synthetic catalogue where the first-minimum bound always wins first.

### What is left

1. ~~Fit the noise gate from `rel`~~ — retired: the curvature rule needs no gate,
   it is positive at every σ.
2. ~~NR = 256 re-check~~ — done, conclusions transfer.
3. ~~`real.py` with the winner~~ — done, and it found the long-r limitation above.
4. **A distance-scale guard is the open problem, and it blocks a `deer.py` patch.**
   The head must not fire (or must shrink hard) when the echo-top curvature is the
   measurement rather than redundant detail. Candidates: gate on an estimated mean r
   from a cheap first-pass inversion; require ≥ 1 full dipolar period inside t_max
   with margin; or cap δ as a fraction of the first-minimum time rather than
   bounding at it. Acceptance must include the sample4 group going to dRMS ≤ 0.
5. ~~The same free-constant question for the Mellin `parabolic` term~~ — done, see
   below. Also not worth shipping, and for a more interesting reason than the head.

### The Mellin `F0` pinning — measured, real, and deliberately left alone

`mellin_signal_spectrum` pins the [0, δ] analytic term at `F0 = 1.0` and fits only
the curvature (`b = Σ T²(F − F0)/Σ T⁴`) — the same pinned parametrization the
Tikhonov bench measured as its costliest choice. Mellin's window is *wider* than the
heads tested there (δ 90–160 ns, fit out to `F = 0.80·f0`), so it had more room to
act. Bench in `~/deer_benchmark/s7_mellin_f0/`.

**The pin is measurably wrong** (`probe.py`, 28 real traces). A free constant lands
systematically *below* 1 — mean −0.0121, median −0.0127, **25 of 28 negative**, i.e.
bias, not scatter — and pinning therefore forces the curvature steep: |b| is 6.2 %
too large in the median and **18 % worst case**. Note the shipped code already
computes `f0 = Fp[0]` from the data (0.982–1.013 on real traces) but uses it only to
pick the fit window, then pins the fit itself to the nominal 1.0.

**Both "the window is too wide" readings are refuted** (`sweep_f0.py`, 756 × 6 at
NR = 256 against the s5 catalogue). If a < 1 were quartic droop being absorbed, a
T⁴ term or a narrower window would fix it. Neither does: `quart` −0.0014 (t −6.2),
`narrow` (0.95) and `narrow90` both −0.0002.

**CORRECTION (same session).** The first version of this section was measured with
the Mellin cutoff pinned at 30. `deer_invert_mellin`'s signature default is
`tau_max=30.0`, **not** `None`, and the auto (`'penalty'`) selector only runs when it
is `None` — which is what the GUI passes when "auto" is ticked. The harness omitted
the argument, so the whole sweep ran at a fixed cutoff the oracle puts at 6–9. Base
overlap was therefore 0.638 rather than **0.8116**, and the claim in the first
version that 0.638 reflected "the engine's known noise sensitivity" was wrong.
Everything below is the re-run with `tau_max=None` (`sweep_f0_auto.json`).

**Anyone benchmarking this engine must pass `tau_max=None` explicitly.** Omitting it
silently disables auto-selection and costs ~0.17 mean overlap.

**Freeing the constant does capture something real — and pays for it on SHORT:**

| | free | quart | narrow |
|---|---|---|---|
| ALL | **+0.0035** (t 4.1, 69 % win) | −0.0019 | −0.0004 |
| SHARP | +0.0052 (t 4.7, 72 %) | −0.0012 | −0.0002 |
| EDGY | +0.0065 (t 4.9, 74 %) | −0.0021 | −0.0001 |
| **SHORT** | **−0.0122 (t −3.0)** | −0.0053 | +0.0001 |

By noise: +0.0021 / +0.0019 / +0.0042 / +0.0012 / +0.0082 / +0.0040 at
σ = 0.0025…0.06 — positive everywhere. `|dmean|` improves in every class
(ALL 0.1442 → 0.1336) and overall `lo_mass` **improves** 0.1830 → 0.1747.

**The mechanism claimed in the first version does not survive.** At the pinned
cutoff, freeing the constant inflated short-r mass by 11 %, which supported "the pin
is load-bearing as an implicit short-r regularizer". With the correct cutoff that
effect is gone: overall `lo_mass` *falls*, and on SHORT it moves only
0.6675 → 0.6736 (+0.9 %). The SHORT overlap loss is real but is not a short-r-mass
mechanism, and remains unexplained.

**Both "the window is too wide" readings stay refuted** — `quart` −0.0019 and
`narrow`/`narrow90` −0.0004/−0.0003, unchanged in sign from the first run.

**Status: not shipped, but the case is now closer than the first version implied.**
+0.0035 overall (t = 4.1) with better mean-r and less short-r mass is a real gain;
the blocker is the −0.0122 on SHORT (14 % of the catalogue), whose cause is not
understood. Freeing the constant *and* diagnosing the SHORT regression is a genuine
open item rather than a closed "do not fix it".

### SHIPPED — `deer_invert_mellin(tau_max=...)` now defaults to `None` (auto)

The one change from this whole line of work that was worth making. `tau_max` **is**
the Mellin regularization knob — Φ(τ) → 0 at high |τ|, so the truncation sets how
much amplified noise reaches P(r), exactly as α does in Tikhonov. The signature
pinned it at **30.0** while `auto_taumax = tau_max is None`, so the documented,
data-driven 'penalty' selector was off unless a caller opted in — even though the
GUI ships with its Auto box `setChecked(True)`. The library default contradicted the
GUI's own default.

Measured over 756 catalogue traces, pinned 30 vs auto: overlap **0.6383 vs 0.8116**
(Δ −0.1733, t = −46.4), winning on **0.9 %** of traces, roughness 0.620 vs 0.015
(41×), spurious short-r mass 0.5295 vs 0.1830. Worse at *every* noise level,
including the cleanest (−0.0221 at σ = 0.0025). The auto cutoff adapts as intended —
τ ≈ 12–22 on clean traces down to 6 on noisy ones.

Note this **removes** a hard-coded constant rather than adding one, which is why it
was shipped where the Wiener filter below was not. `deer_analysis.py` is the only
in-tree caller and always passes `tau_max` explicitly, so GUI behaviour is unchanged;
the change protects scripts, `epr_auto` and benchmarks. Side effect to know about:
`n_tau = _ntau_for(tau_max)` runs only in the auto branch, so default callers now
also get the adaptive τ-grid instead of a fixed `n_tau = 601`.

Synced byte-identical across all five repos (`deer.py` md5 `a089e260cf`).
P(r) comparison figures: `~/deer_benchmark/s7_mellin_f0/pr_{easy,hard}.png`.

### NOT shipped — the Wiener inverse filter, measured and rejected

`wiener` (default 0) is implemented but unreachable: nothing in the tree, GUI
included, ever sets it. Swept properly (`wien.py`, 7 strengths × 756 traces, gate
evaluated post hoc since the gate only *chooses* between the filtered and plain run).

The best setting is **0.25 gated at `rel = sig_e/λ > 0.08`**, not the docstring's
0.12: +0.0100 overall (t 10.0), +0.0242 at σ = 0.04, +0.0521 at σ = 0.06, bit-identical
below the gate, `lo_mass` 0.1830 → 0.1686, and positive in every shape class
(SHORT +0.0156, the short-r spike it exists to suppress). The optimum is a diagonal
ridge — stronger filters need a higher gate — and 0.25 is the robust point (flat at
+0.0100 across gates 0.03/0.05/0.08, still +0.0090 with no gate at all, where 0.50
collapses to +0.0069 blanket and 1.00 goes negative).

**Rejected anyway, for three reasons:**

1. *The gain sits where the answer is not trustworthy.* It is inactive wherever
   Mellin is doing well (σ ≤ 0.01: Δ = +0.0002 or exactly 0) and only engages where
   it is already failing (0.694 → 0.719, 0.603 → 0.655). It turns bad answers into
   less bad ones. On the 28 real traces (`rel` ≤ 0.0301) it never fires at all.
2. *Per-trace instability.* When it fires it still loses on 24 % of traces, worst
   −0.156 overlap, and at σ = 0.02 it wins on only 63 % of the traces it touches.
   One analyses one sample, not 756, with no way to tell which side one landed on.
3. *It would compromise what the engine is for.* Mellin's value is "no Tikhonov, no
   NNLS, no L-curve — the only regularizing knob is `delta` together with `tau_max`",
   both *derived* from the data. A tuned strength plus a tuned gate are two constants
   fitted to a synthetic catalogue, and tuning Mellin toward Tikhonov's smoothness
   destroys the independence that makes a Mellin-vs-Tikhonov disagreement diagnostic.

Recorded so nobody re-derives it; the docstring's 0.12 figure is superseded by a
properly swept 0.25 that is still not worth using.

## The Tikhonov echo-top bump on `gauss_broad` is a REGRESSION — **RESOLVED 2026-08-04**

**Answer, for anyone reading only this far: the culprit is `a64098e`'s
`_crop_pre_zero`, not its zero-time fixes, and the fix is in `deer.py` (uncommitted).
Jump to the 2026-08-04 session below.** The lead as it stood on 2026-08-03 follows,
kept because two of its guesses were wrong in instructive ways.


**User report, 2026-08-03: a bump / kink in the Tikhonov fit near t = 0 on
`gauss_broad`, and "there was no such bump for Tikhonov earlier". Mellin is clean.
The short-r taper shipped this session did NOT remove it.** Treat the regression
claim as the primary lead — the work below diagnosed a *mechanism* that produces
this signature, but did not establish that it is the same thing the user is seeing,
and the taper not fixing it is evidence that it is not.

### Reproduction

```bash
cd ~/deer_benchmark/s7_mellin_f0
SLUG=gauss_broad SIGMA=0.04 CONDS=hard,hard2 python3 t0diag.py   # -> t0diag_*.png
python3 t0_cause.py        # same trace at fitted / true / +-1 sample zero time
python3 t0_ab.py           # A/B two git revisions of deer.py side by side
cd ~/deer_benchmark/s8_tik_taper && python3 bisect_bump.py       # WHEN it appeared
```
`bisect_bump.py` walks the deer.py revisions and reports, per revision, the largest
positive step of `F_fit` inside the first 300 ns (0 = clean monotone decay, which is
what a broad single Gaussian must give), the sub-2.5 nm mass, and the |t0| error.
**Start here** — it answers "which commit" directly.

### What is already known

* **The signature is a spurious sub-2 nm peak.** Small r oscillates fastest in the
  kernel, so it distorts precisely the first ~100 ns: too-steep echo-top decay plus
  a kink. `hard`/rep1 at σ = 0.04 shows it clearly.
* **On that trace it is caused by the ZERO TIME, not the inversion.** The estimator
  returns 154.7 ns against a true 120 ns (+35 ns ≈ 3.5 samples). Feed the same data
  the true t0 and the artefact vanishes outright: short-r mass 0.2319 → **0.0002**,
  overlap 0.6222 → **0.8538**. On `hard`/rep0 (t0 off by only 8 ns) the residual
  junk is genuine noise instead — so it is not one cause across all traces.
* **Suspects are the three 2026-07-31 zero-time commits** (`51f0df6` noise-aware
  `_parabolic_zero_time`, `5c557de` centroid-above-noise-gate + pre-t0 display,
  `b013457` Mellin forward-fit peak), since `fit_zero_time` is shared by both
  engines. A/B `84d1f03` vs `5200009` on this case is **mixed, not uniformly bad**:
  rep1 worse (lo_mass 0.065 → 0.232), rep0 better (0.252 → 0.207), rep2 unchanged —
  and note rep1's t0 error *improved* (+50 → +35 ns) while its P(r) got worse,
  because the joint background re-fits too (λ 0.220 vs 0.244). The landscape is
  non-monotone in t0; do not assume "better t0 ⇒ better P(r)".
* **Nothing from 2026-08-03 caused it.** The only code change that day was
  `deer_invert_mellin`'s `tau_max` default (Mellin-only), plus the short-r taper
  added at the end of the session — and the user still sees the bump with it.

### Ruled out

* Not the parabolic echo-top head — that was never shipped (see 2026-08-02/03).
* Not the short-r taper — it postdates the report and does not fix it.
* Not a Mellin problem: Mellin is clean because it has BOTH a τ cutoff (which
  truncates the high-τ spectrum where short-r leakage lives) and `taper_short`.

### The open question the taper result forces

The taper suppresses sub-2 nm density and measurably helps the catalogue
(+0.0066 excl. `short_r20`, t 11.6) — yet the reported bump survives it. So either
the offending mass sits **above** 2 nm (where the taper weight is exactly 1.0 and
cannot act), or the bump is not short-r mass at all. Check the P(r) that accompanies
the user's bump before assuming the mechanism above: if the spurious mass is at
2–3 nm the whole short-r framing is wrong and the cause is elsewhere (candidates:
the joint background's λ, or `_crop_pre_zero` / the pre-t0 display change in
`5c557de`).

### Bisect result (ran 2026-08-03) — culprit is `a64098e`, and the metric is wrong

`gauss_broad`, σ = 0.04, hard + hard2, 3 reps, averaged:

| rev | date | lo_mass | \|t0 err\| ns | overlap |
|---|---|---|---|---|
| `a351f0a` | Jun 20 | **0.0546** | 17.0 | **0.8382** |
| **`a64098e`** | **Jul 23 — S1, "negative time, negative lambda, zero-time"** | **0.1079** | **30.2** | **0.7826** |
| `f6768ed`…`6ecab18` | Jul 23–31 | 0.1079 | 30.2 | 0.7826 |
| `51f0df6` | Jul 31 | 0.0734 | 22.6 | 0.8167 |
| `5c557de`…`5200009` | Jul 31–Aug 3 | 0.0973 | 15.1 | 0.8051 |
| HEAD (+ taper) | Aug 3 | 0.0686 | 15.1 | 0.8236 |

**`a64098e` is where it regressed** — spurious short-r mass doubled and overlap fell
0.838 → 0.783 in one commit, an S1 *zero-time* fix. The Jul-31 work recovered the t0
error (30.2 → 15.1 ns) but not `lo_mass`, which is still above the June level. This
matches the user's "there was no such bump earlier": earlier means before 23 July,
NOT before this session. **Start by reading a64098e's zero-time hunk.**

**But the bump metric in `bisect_bump.py` is WRONG and must be redefined first.**
`bump_max` is negative at *every* revision, i.e. `F_fit` never actually rises in the
first 300 ns — yet the kink is plainly visible in `t0diag_gauss_broad_0.04.png`
(hard/rep1, ~80 ns). So the artefact is a **shoulder — a curvature sign change —
not a rise**, and a first-difference test cannot see it. Use a second-derivative /
inflection test (or fit a monotone convex reference and measure the residual), or
the bisect will keep reporting "no bump" while the plot shows one.

### Acceptance

The redefined shoulder metric is ≈ 0 on `gauss_broad` at σ = 0.04 across reps;
`lo_mass` returns to about the June level (~0.055) on that case; and whatever fix
lands does not regress the 756-trace catalogue
(`~/deer_benchmark/s8_tik_taper/sweep_taper.py`, `s6_parab/summarize.py`).

### State of the short-r taper

Implemented in `deer_invert_joint` (`taper_short=True`, `fit_rmin_abs=2.0`,
`fit_rmin_width=0.5`) plus a shared `_short_r_taper` helper that Mellin's inline
copy was refactored onto. Benchmarked **+0.0051** overall, **+0.0066** excluding the
one 2.0 nm shape (t 11.6, 81 % of traces, worst −0.025), rising with noise. It does
**NOT** fix the reported bump, so it was left UNCOMMITTED and the tree reverted to
what is pushed — a regression hunt should not carry an unrelated behaviour change to
the same function. The full implementation and its benchmark live in
`~/deer_benchmark/s8_tik_taper/` (`taper.py`, `sweep_taper.json`, `summ.py`,
`post20_check.py`); re-apply from there if it is wanted after the bump is fixed.

## Session 2026-08-04 — the bump is the pre-zero CROP; fixed in `deer.py` (uncommitted)

Artefacts in `~/deer_benchmark/s9_t0_crop/`. Fable was available this session and was
consulted on the inverse-theory side; its parity argument is the spine of what follows.

### First, the metric — the old one could not see the artefact at all

`s8_tik_taper/bisect_bump.py` scored the largest positive FIRST DIFFERENCE of `F_fit`
in the head, which is negative at every revision. The artefact is a CURVATURE sign
change, not a rise. `metrics.py`:

    shoulder = max(0, max d2F_fit/dt2 on (0, w]) / max |d2F_true/dt2| on (0, w]

with `w` = 0.85 × the window over which the NOISELESS truth is still concave, so the
score is 0 for a clean concave head and free of the trace's amplitude and decay rate.

### Re-bisect with it — same culprit, now measurable

| rev | shoulder | lo_mass | \|t0 err\| ns | ov |
|---|---|---|---|---|
| `a351f0a` Jun 20 | 0.96 | 0.0546 | 17.0 | 0.8382 |
| **`a64098e` Jul 23** | **2.17** | 0.1080 | 30.2 | 0.7826 |
| `51f0df6` Jul 31 | 1.25 | 0.0734 | 22.6 | 0.8167 |
| `5c557de`…HEAD | 1.91 | 0.0973 | 15.1 | 0.8051 |

Note `5c557de`: the t0 error IMPROVES 22.6 → 15.1 ns while shoulder and `lo_mass` get
worse. "Better t0 ⇒ better P(r)" stays false, as the 2026-08-03 note warned.

### Which half of `a64098e` — the crop, not the zero time

2×2 at HEAD, `gauss_broad`, σ = 0.04, hard + hard2, 3 reps, NR = 256:

| variant | \|t0err\| | shoulder | lo_mass | ov |
|---|---|---|---|---|
| base (crop, fitted t0) | 15.1 | 1.91 | 0.0973 | 0.8051 |
| nocrop (same t0) | 15.1 | 1.39 | 0.0617 | 0.8422 |
| oracle (true t0, crop) | 0 | 0.71 | 0.0454 | 0.8617 |
| oracle + nocrop | 0 | 0.59 | 0.0435 | 0.8724 |
| June estimator + HEAD code | 17.0 | 2.12 | 0.0974 | 0.8040 |

Re-bisecting with the crop disabled at EVERY revision settles it: HEAD then scores
0.0617 / 0.8422 against June's 0.0546 / **0.8382** — i.e. **with the crop gone HEAD is
no longer a regression at all**, it is better than June. The crop is the whole of the
residual regression.

One correction to the above, though: `a64098e` did damage through BOTH its changes.
Crop-disabled it still doubles `lo_mass` (0.055 → 0.129), purely because its
zero-time fixes pushed the error 17 → 30 ns on this case. The July-31 commits then
repaired the estimator to 15.1 ns, better than June's 17.0. So "the estimator is
exonerated" is true at HEAD and false at `a64098e`.

### The mechanism

Every `K(·,r)` is even, so ANY model form factor has `F'(0) = 0` exactly — this is
parity, not non-negativity; a signed or complex P(r) would be just as constrained. A
t0 late by D leaves the retained data as `F_true(t + D)`, whose slope at 0 is
`−(4/5)⟨ω²⟩D`. **On a symmetric window an odd error is orthogonal to the entire even
model space: variance only, zero bias.** Cropping to `t ≥ 0` destroys that
orthogonality, and the only basis direction that can supply a non-zero initial slope
is the short-r end. Predicted spurious mass `m ≈ (r_s/⟨r⟩)⁶·ω_s·D` = 0.044 at 2.5 nm
against 0.052 measured (0.097 − 0.045) — the mechanism is not just plausible, it is
the right size.

**Confirmed with no noise at all** (`dsweep.py`, a KNOWN offset D injected on top of
the true t0, 4 shapes, σ = 0):

| D (ns) | crop ON — shoulder / lo_mass / ov | crop OFF — shoulder / lo_mass / ov |
|---|---|---|
| 0 | 0.00 / 0.239 / 0.704 | 0.00 / 0.238 / 0.693 |
| +15 | 0.00 / 0.285 / 0.741 | 0.00 / 0.224 / 0.909 |
| +30 | 0.01 / 0.316 / 0.666 | 0.00 / 0.166 / 0.823 |
| +45 | 0.12 / 0.340 / 0.548 | 0.00 / 0.076 / 0.727 |
| +60 | 0.26 / 0.137 / 0.417 | 0.00 / 0.017 / 0.651 |

Short-r mass grows LINEARLY in D with the crop on (≈ 0.0022/ns over D = 0…45, the
predicted scaling) and the shoulder appears with it. With the pre-zero samples kept
the shoulder is **exactly 0.00 at every offset from −60 to +60 ns** and short-r mass
FALLS as D grows, because the mirrored samples absorb the shift. There is no noise
anywhere in that table: the artefact is manufactured by the crop plus a shift.

Two corollaries that check out and are worth keeping:

* **A better residual search cannot be the fix.** The dipolar part of a σ = 0.04
  trace barely knows D: Fisher bound σ_D ≈ 30 ns, the same size as the error itself.
  The shipped echo-top estimator is already well past that bound (mean \|err\| 6.8 ns
  over the catalogue) because it uses the echo SHAPE, which the dipolar likelihood
  knows nothing about.
* **Mellin is immune for a reason, and it is not a Mellin property.** It crops too,
  but its δ-split replaces the head with an EVEN analytic parabola — the parity fix,
  already shipped on one engine only. That is the whole explanation of "Mellin is
  clean, Tikhonov is not".

### S1's premise for the crop does not survive a mirror test

S1 justified `_crop_pre_zero` as "the samples below t0 are the echo RISING EDGE, which
the model cannot reproduce". `evenness.py` tests it: RMS of `V(−t) − V(+t)` over the
pre-zero span in units of `√2·σ_tail`, so **1.0 = consistent with pure noise**.

* Synthetic s5: 0.53–1.31 — even by construction, which is exactly why the catalogue
  **cannot** decide this question on its own (S1's own methodological note).
* Real YopO ring test: median ≈ 1.4, **19/28 below 2.0**, only 7 above 3.0.

The 0.58 "droop" S1 read as an instrumental rise is the dipolar decay of a
short-distance sample. S1's own skeptics had already failed to reproduce the headline
5.0 → 2.7 nm and measured ≤ 0.02 nm on real traces; that reproduces at HEAD (0.009 nm
mean, 0.026 max). And the statistic PREDICTS where keeping hurts: on the 7 traces
above 3σ the V-residual degrades 44 % if the pre-zero samples are kept, on the 21
below, 4 %.

### SHIPPED (uncommitted) — `pre_zero='even'` on the two Tikhonov entry points

`_crop_pre_zero(t, V, policy='crop'|'even', tol=3.0)`. Under `'even'` it walks outward
from t = 0 and keeps the contiguous pre-zero run whose mirror residual stays inside
`tol·√2·σ`, dropping the rest — a rising edge, when there is one, sits at the far end.
σ comes from the module's existing `_tail_noise`; NaN (unmeasurable) falls back to
cropping. Kept samples go in as ordinary rows at their own negative t, which is what
the kernel already expects and what shipped before `a64098e`.

`deer_invert(..., pre_zero='even')` and `deer_invert_joint(..., pre_zero='even')` —
**Tikhonov only.** Mellin integrates on a log-T grid and `_gauss_mc`'s
`_pake_transform` assumes uniform sampling, so both keep the unconditional crop, as
does `deer_validate`. `fit_zero_time`'s internal inversions pin `pre_zero='crop'`:
its residual objective needs a fixed sample set, or it becomes a staircase in the
offset it is searching over.

**Do NOT fold.** Averaging the mirrored sample into its positive twin looks equivalent
and is better on synthetic (`lo_mass` 0.052 vs 0.062), but its interpolation onto the
coarse real grids (16–24 ns) moves reported peaks by up to 0.46 nm. Measured on the
28 real traces, vs today's crop:

| policy | \|Δpeak\| mean / max | rmsV ratio mean / worst | traces > 1.2× |
|---|---|---|---|
| keep (unconditional) | 0.009 / 0.261 | 1.141 / 1.883 | 7/28 |
| fold (unconditional) | 0.028 / 0.457 | 1.081 / 2.021 | 3/28 |
| even + fold | 0.021 / 0.457 | 1.063 / 1.959 | 2/28 |
| **even + keep (shipped)** | **0.000 / 0.000** | **1.012 / 1.087** | **0/28** |

Verified with the shipped code (which uses the module's own `_tail_noise`, not the
bench prototype's diff-based one): it keeps 74 % of the pre-zero samples across the
ring test, rejects all of them on 4 traces, and moves no reported peak at all.

### Catalogue result — 756 traces, 21 shapes, NR = 128

| | ov | Δ | t | win % | shoulder | lo_mass |
|---|---|---|---|---|---|---|
| base | 0.8526 | — | | | 0.338 | 0.1404 |
| **keep** | 0.8608 | **+0.0082** | **7.6** | 65 | 0.221 | 0.1338 |
| oracle t0 | 0.8583 | +0.0056 | 4.8 | 53 | 0.198 | 0.1370 |

Positive at EVERY noise level (+0.0010 at σ = 0.0025 rising monotonically to +0.0183
at 0.06) and in EVERY shape class (SHORT +0.0162 / 73 % win, EDGY +0.0077,
SHARP +0.0071, broad +0.0054). Nothing regresses. NR = 256 on six shapes agrees:
+0.0198 (t 4.5), positive on 6/6. **It is worth more than a perfect zero time.**

### Refuted along the way

* **Guard band** (drop `t < 80 ns`): −0.286 overlap, `lo_mass` 0.43. The head is the
  only place short-r mass is OBSERVABLE — `K(80 ns, 2 nm)` is already small — so
  removing it makes that mass free. Ranked second-safest a priori; measured, it is the
  worst thing on the list.
* **Unpenalized dF/dt nuisance column** (±J so NNLS can take it signed, to give the
  ramp a home other than short r): −0.019 overlap, shoulder 1.91 → 5.2, and the fitted
  coefficient does not track the true D.
* **Symmetry-based t0 estimator**: 400 ns errors. A decaying trace is symmetric about
  EVERY point in its flat tail, so the raw criterion has no localizing power.
  Normalizing by the even variation and seeding at the echo maximum makes it converge
  but it is still worse than what ships (mean \|err\| 11.7 vs 6.8 ns; 22.7 vs 11.4 at
  σ = 0.04). The shipped parabola/centroid stays.

### Acceptance, scored honestly

The 2026-08-03 bar was "shoulder ≈ 0 on `gauss_broad` at σ = 0.04; `lo_mass` back to
the June ~0.055; no catalogue regression".

* `lo_mass` 0.0973 → 0.0617 vs June's 0.0546 — essentially met.
* catalogue — met and then some: +0.0082 (t 7.6), no class or noise level negative.
* shoulder 1.91 → 1.39 vs June's 0.96 — **NOT met, and "≈ 0" was never reachable**:
  any t0 error produces some shoulder, and the June revision itself scores 0.96. The
  bar should have been "back to the June level", and on that it is close but short.

**The fix is partial by construction.** It recovers ~2/3 of the average loss; on the
worst trace (t0 +35 ns) overlap goes 0.622 → 0.708 against the oracle's 0.854; and it
does nothing at all for a trace with no pre-zero samples — trimmed, pre-cropped, or
already starting at t0. Closing the rest needs parity imposed on the MODEL head, i.e.
the shelved `cv60` parabolic head from `s6_parab`, which is the Tikhonov analogue of
what Mellin already ships and is blocked on its long-r guard. **That is now the
natural next item, and the parity framing is a new argument for it that the
2026-08-02/03 rounds did not have.**

### The cv60 head re-examined under the parity argument — a real defect, half a fix

Same session, after the crop fix. `head_parity.py` (algebra, no inversion),
`headfit.py`, `head_bench.py` + `head_summ.py` (756 traces), `head_real.py` (28 YopO).

**cv60 is built the one way that leaks.** `parab_head` fits `a + b t^2` on the
ONE-SIDED window `[0, delta]`, and there the odd part of a zero-time error is not
orthogonal to the even basis. Projecting `t` onto span{1, t²} with uniform weight
gives `t ~ 3d/16 + (15/16d) t²`, so

    b_hat = b (1 + 15 D / (8 delta))

a curvature bias LINEAR in the zero-time error — and `b = (2/5)<w²>` with `w ∝ r⁻³`,
so it is a distance bias. Measured on noiseless catalogue traces, `b_hat(D)/b_hat(0)`
over D = ±40 ns: `gauss_narrow` **0.083 → 1.48** (17×), `gauss_broad` 0.653 → 1.217,
`gauss_broad_long` 0.822 → 1.11. The prediction tracks the measurement.

**The obvious repair fails, and its failure explains an s6 result.** Adding an odd
term to the fit and discarding it does NOT work: on `[0, delta]`, `t` is not
orthogonal to `t⁴` either, so a shift and F's quartic term are confounded — the
odd-augmented fit returns `D_hat = 33 ns` on a trace with zero shift. That confound
is almost certainly why round 3 found "the quartic is worse than order-2 everywhere".

**What works is pair-averaging**, and it is only possible now: fit the parabola to
the even part `G(u) = [F(u) + F(-u)]/2`, which cancels the odd term identically
rather than relying on a discrete design the sampling grid may not respect. It needs
the pre-zero samples that `_crop_pre_zero` was discarding.

**Catalogue, 756 traces, on top of `pre_zero='even'`:**

| | Δ ov | t | win % | shoulder | LONG/broad |
|---|---|---|---|---|---|
| `head_1s` (s6's) | +0.0028 | 2.9 | 55 | 0.212 | −0.0019 |
| `head_pair` | **+0.0035** | **4.7** | 60 | **0.124** | **+0.0003** |

(`base` shoulder 0.224. Against the OLD baseline `head_1s` scores +0.0046, t 6.6 —
reproducing s6's published +0.0050, which validates the harness.)

**The head is worth less than s6 measured.** Its standalone +0.0046 becomes
+0.0028…+0.0035 once the crop fix is in, so roughly **40 % of what round 2 attributed
to denoising was parity restoration** — now supplied by the crop policy, more cheaply
and without the curvature bias. Round 2's `gate.py` could not have caught this: it
tested the gain against `|a−1|`, and parity restoration is uncorrelated with the
echo-top anchor just as denoising is.

**Real data — halved, not cleared.** Mean-distance shift vs the new baseline:

| | sample1 | sample2 | sample3 | sample4 (5.9–7.35 nm) | d_rms sample4 |
|---|---|---|---|---|---|
| `head_1s` | +0.004 | +0.014 | +0.024 | **+0.148** (max 0.198) | +0.00106 |
| `head_pair` | +0.003 | +0.009 | +0.008 | **+0.072** (max 0.141) | **+0.00020** |

`head_1s` reproduces s6's long-r regression (+0.10…+0.22 nm) exactly. Pair-averaging
halves it, cuts the residual harm 5×, and removes the peak instability outright —
s6's −0.457 nm mode switch on `sample2_labE` is gone and `d_peak` is 0.000 in every
group. **But s6's acceptance was sample4 dRMS ≤ 0 and this gives +0.00020, so the
head still does NOT pass.** The parity defect was a real and substantial part of the
long-r problem, not all of it; the remainder is the physical limit already named — at
7 nm one dipolar period is ~6.6 µs, so a 200–300 ns head is a few percent of a period
and the echo-top curvature IS the measurement.

**Status: SHIPPED (uncommitted at the time of writing, then committed) as
`deer_invert_joint(echo_head=True)`, default OFF.** The guard below clears s6's
acceptance. `head_pair` is the construction that ships, not `head_1s`.

### The guard — and the blocker was mis-framed as a distance problem

It is a **breadth** problem. The sample4 traces report peaks at 6.99-7.35 nm, but the
distance implied by their own echo-top curvature is **3.3 nm**: `<w^2> ~ r^-6` is
dominated by the shortest component present, so a broad P(r) has an echo top that
looks short-r however long its tail is. This is why the three distance-scale
candidates all fail to separate the group at all:

| group | delta/t_max | t_max/delta | first min missing | r_eff |
|---|---|---|---|---|
| sample1 (2.4 nm) | 0.014 | 86 | 0/7 | 2.3 |
| sample2 (3.6 nm) | 0.031 | 34 | 0/7 | 3.5 |
| sample3 (5.0 nm) | 0.035 | 46 | 0/7 | 4.6 |
| **sample4** | **0.026** | **40** | **0/7** | **3.3** |

sample4 sits BETWEEN sample2 and sample3 on every one. Note also that cv60's delta
rule is scale-free by construction — `delta = sqrt((1-level) a / -b)` with
`b = -(2/5)<w^2>` gives `delta ~ 1/w_rms`, so `delta*w_rms ~ 1` at every distance and
no guard built on that product can discriminate.

**What works: `r_mean/r_eff`** — the mean distance from a first-pass inversion against
`r_eff = (2 pi nu_dd / w_rms)^(1/3)` from the head's own curvature. It is 1 for a
single distance and grows with breadth. Real traces: sample1 1.07-1.15, sample2
1.02-1.08, sample3 1.07-1.23, **sample4 1.27-1.47**. Threshold **1.25**; a failed head
fit (`nan`) also gates off, which is the conservative direction.

**Catalogue, 756 traces** (`g_ratio125` = guard at 1.25):

| | ov | Δ | t | head on | SHORT | LONG/broad |
|---|---|---|---|---|---|---|
| `head` unguarded | 0.8642 | +0.0035 | 4.7 | 100 % | +0.0058 | +0.0003 |
| **`g_ratio125`** | 0.8640 | **+0.0034** | **4.9** | 73 % | +0.0054 | **+0.0015** |
| `g_ratio115` | 0.8629 | +0.0023 | 4.2 | 60 % | +0.0033 | +0.0005 |
| `g_resid` | 0.8623 | +0.0017 | 3.4 | 40 % | +0.0054 | −0.0010 |

The guard is free: it keeps the whole gain while switching the head off on 27 % of
traces, and it IMPROVES long/broad (+0.0003 → +0.0015) — where it fires, the head was
not helping.

**Real traces — ACCEPTANCE MET.** `g_ratio125` gates off all 7 sample4 traces, so that
group reproduces the baseline exactly: **d_rms +0.00000, d_mean +0.000, d_peak 0.000**,
against the unguarded head's +0.00013 / +0.072 nm. sample1-3 keep the head (5/7, 6/7,
5/7) and are unchanged. s6's bar — sample4 dRMS ≤ 0 — is cleared for the first time.

**Refuted on the way:**

* **`Q = 14 c / (5 b^2)`**, the breadth moment from a pair-averaged QUARTIC fit
  (`K = 1 - (2/5)w^2 t^2 + (2/35)w^4 t^4`, so `<w^2> = -5b/2`, `<w^4> = 35c/2`). It is
  the theoretically clean diagnostic — exactly 1 for a single distance, needs no
  inversion, and is only well posed at all because pair-averaging removes the odd
  term. It behaves on noiseless catalogue traces (1.07-2.41, correctly ordered) and is
  **useless on real data**: 1054.8, 203.7, −6.26, nan. The quartic coefficient is not
  determined from a noisy 150-350 ns window.
* **Residual selection** (run both, keep whichever fits V better). It satisfies a
  residual criterion by construction but residual is not accuracy: +0.0017 on the
  catalogue against +0.0034, NEGATIVE on long/broad, and on real traces it switches
  the head off almost everywhere (2/28 keep it).

### As shipped — and the port bug that nearly went out with it

`deer.py`: `_first_min_time`, `_head_delta` (the curvature rule), `_pair_fit`,
`_even_head`, `_r_from_curvature`, `_echo_head_solve`, wired into
`deer_invert_joint(echo_head=False, head_level=0.60, head_cap=0.35,
head_ratio_max=1.25)`. The result carries an `echo_head` dict (applied / delta /
r_eff / r_ratio). The unheaded solution `l_curve` already computed is reused for the
guard, so the second regularization scan is paid only when the head actually fires.
GUI: a "Parabolic echo-top head (guarded)" checkbox on the Tikhonov tab, gated to the
joint engine. Default OFF -- the gain is real but it costs a second scan and it moves
every reported distance, so it is a per-session choice, not a silent change.

Measured through the SHIPPED path, 756 traces: **+0.0033 (t 5.6)**, head applied on
66 %, SHORT +0.0057, LONG/broad +0.0016, and only sigma = 0.0025 marginally negative
(−0.0005, t −0.5). Real ring test: sample4 head off 7/7 -> **d_rms +0.00000,
d_mean +0.000**; sample1-3 keep the head (5/7 each) and are unchanged.

**The port bug, worth knowing about.** The bench took `r_eff` for the guard from the
quadratic coefficient of the **quartic** pair fit; the first port used the two-term
fit's. Over a window wide enough to denoise, the `(2/35)w^4 t^4` term is not
negligible and biases a two-term `b`, so `r_eff` came out too large, the ratio too
small, and the guard fired on only **3 of the 7** traces it exists for. The catalogue
number was **+0.0034 either way** and did not notice; only the real traces did. The
replacement parabola stays at order 2 (two-parameter denoising is the point) while the
diagnostic reads order 4 (it wants an accurate `<w^2>`) -- the two are deliberately
different, and `_pair_fit(order=)` is the seam.

**Two honest caveats on the guard.** The threshold sits in a narrow gap — the highest
kept real trace is 1.227 and the lowest gated is 1.270 — so 1.25 is a constant fitted
to a 7-trace separation, not derived. And the firing rate is noise-dependent (head on
75 % at σ = 0.02, 39 % at 0.04, 35 % at 0.06) because noise inflates both the
inversion's spread and the head's `b`: `r_ratio` is therefore part breadth test, part
noise gate, and only the breadth half was derived. Cost is one extra inversion.

Two implementation traps for whoever picks this up, both hit here:

* **s6's `delta_from_curvature` / `first_min_time` assume a cropped trace.** With
  pre-zero samples present they scan from the first sample, call a "first minimum"
  inside the rising side, and return a NEGATIVE delta — the head then silently
  no-ops and every variant looks identical to the baseline. Pass them `t >= 0` only.
* **The pair fit's window must also bound the REPLACEMENT.** `h` is capped by the
  available pre-zero span; applying a parabola fitted over 120 ns out to a 322 ns
  delta is extrapolation, and it cost −0.0131 on long/broad — the exact class the
  construction exists to rescue — until the replacement window was clipped to `h`.

### The residual bump was the REGULARIZATION OPERATOR's free ends

User report after the crop fix: a small bump remains on `gauss_broad` at σ = 0.04, and
raising the minimum distance removes it. That observation is the diagnostic, and the
answer is not r_min.

`regularization_matrix(n, 2)` was the plain (n−2, n) second difference, so `P[0]` and
`P[-1]` appear in ONE row where an interior point appears in three. Edge mass is ~3×
under-penalized and a spike sitting exactly at the grid edge is the cheapest roughness
the fit can buy. **The artefact tracks the BOUNDARY, not any distance** — sweeping
r_min on `gauss_broad`, the edge amplitude `P[0]/max(P)` falls 0.173 → 0.115 as r_min
goes 1.5 → 1.75 and then climbs back to 0.232 at 2.25 as mass re-accumulates against
the new edge. Raising r_min only moves the problem.

`regularization_matrix(n, order, include_edges=True)` adds the two rows `[-2, 1, ...]`
and `[..., 1, -2]`, i.e. P treated as zero just outside the grid, so the boundary
carries the interior's curvature penalty. Threaded as `reg_edges=True` (**the new
default**) through `deer_invert` and `deer_invert_joint` only — Mellin, the
multi-Gaussian and `joint_background`'s coarse internal fit are untouched.

**Catalogue, 756 traces: +0.0046 (t 5.1, 59 % win)**, edge amplitude 0.089 → 0.017,
shoulder 0.224 → 0.090. Positive at EVERY noise level and growing with it (+0.0006 at
σ 0.0025, +0.0125 at 0.04, +0.0161 at 0.06). By class SHORT +0.0179 (t 4.4),
LONG/broad +0.0039, SHARP +0.0010, other +0.0018, EDGY −0.0002 (neutral). Only 3 of 21
shapes negative — `rectangle` −0.0039, `gauss_narrow` −0.0021, `hyperbola` −0.0010;
`short_r20` gains **+0.0351** at 75 % win. On `gauss_broad` it beats moving the grid:
at r_min = 1.5 it recovers the peak to 3.96 nm (true 4.00) against the plain
operator's 3.61, and against 3.93 for plain-with-r_min-2.0.

Real ring test: **no peak moves at all** (|Δpeak| 0.000), Δmean +0.001 nm, ΔrmsV
+1e-6 — those distributions sit well inside the grid, so there is little edge mass to
remove and the change is safely inert there.

**When it is WRONG:** a distribution with genuine mass at the grid boundary. Measured:
`short_r20` (true 2.03 nm) recovers its peak at 2.02 nm on a grid starting at 1.5 nm,
but at 2.19 nm on one starting at 2.0 — closing the edge forces P → 0 exactly where
the data says otherwise. The lesson is to keep r_min generous and let the operator do
the work, not to clip the grid.

**A correction to this session's own reporting.** `lo_mass` was the headline artefact
metric throughout, and a substantial part of it was this operator effect rather than
short-r physics. The crop fix's +0.0082 is unaffected (measured plain-against-plain),
but the ABSOLUTE short-r mass levels quoted earlier were inflated by the free edges.

**And it reprices the head again.** `echo_head` is now worth **+0.0016 (t 3.2)**, down
from +0.0033: +0.0046 standalone → +0.0033 once `pre_zero` kept the mirrored samples →
+0.0016 once `reg_edges` closed the ends. All three suppress the same edge/short-r
pile-up, and the head was substantially compensating for the other two.

### Sampling-resolution floor — WARNED, not clamped

Separate defect, found while chasing the above, NOT fixed. The kernel's fastest
component is `2ω` (the argument `a(1−3cos²θ)` spans [−2a, a]), so it aliases below

    r_alias = (4 · nu_dd · dt)^(1/3)

= 1.28 nm at 10 ns sampling but **1.88 nm at 32 ns**. `default_r_axis` hardcodes
`rmin=1.5` with no reference to the trace's sampling, and **7 of the 28 real ring-test
traces** (dt 20–32 ns) therefore get a grid extending into aliased territory, where
columns the data cannot distinguish are free for the fit to exploit. The synthetic
catalogue at 10–12.6 ns has a floor of 1.28–1.38 nm, so it is legal there and the
catalogue cannot see this.

**Measured** on coarse-sampled synthetic traces (`alias_bench.py`, 756 traces per dt,
with `reg_edges` already on so the free-edge effect is not in the way): clamping r_min
to `r_alias` is worth **+0.0058 (t 2.6, 73 % win) at dt = 24 ns** and +0.0049 (t 1.2)
at 32 ns, and is exactly a no-op at 8 and 16 ns where `r_alias` < 1.5 — which is a
useful sanity check on the harness. Sub-alias mass in the unclamped runs is 0.009
(24 ns) and 0.020 (32 ns).

Splitting by shape settles the design question: at 32 ns the gain is **+0.0090
(t 3.9, the strongest signal in the whole alias study) on non-short shapes but
−0.0123 on the SHORT class** — clamping to 1.88 nm clips a genuinely 2.0 nm
distribution. So a clamp would trade one bias for another on exactly the samples that
most need short distances.

**Shipped as a WARNING, not a clamp** — the grid is the user's, a clamp would damage
real short-distance samples (above), and only the 24 ns row is significant overall. `alias_r_min(t)` is public,
`_warn_alias` raises a RuntimeWarning from both Tikhonov engines (precedent:
`background_fit`'s degenerate-lambda warning), the result dict carries `r_alias`, and
the GUI shows a red "r min below the N nm sampling limit" line in the info panel that
clears when r_min is raised.

**One probe that did NOT work**, recorded so it is not repeated: a column-coherence
test (how well the best OTHER kernel column reproduces the one at 1.5 nm) gave 0.52 at
24 ns and 0.46 at 32 ns, i.e. NOT degenerate — but the comparison set differed per row,
so the numbers do not separate the hypotheses and nothing should be concluded from
them. The end-to-end clamp test is the evidence.

### Before this ports anywhere

**PORTED 2026-08-04.** The four-session backlog went out with this round: `deer.py`
lifted ITC → plain and fanned to NIOCH / NIOCH_Q / Cryomech (all five now md5
`7ea0d590bd`), `deer_analysis.py` ITC → NIOCH / NIOCH_Q via `--sync-cc` (md5
`ebdc115462`). `sync_check.py` reports the DEER files in sync everywhere; the only
remaining drift is `Sibir_1.py`, which is pre-existing and untouched. Each fork was
smoke-tested after the copy (import + joint inversion + `r_alias`).

Note `--sync` would ALSO have carried `Sibir_1.py` plain → every fork, so the port was
done surgically (`--lift` for the one file, then explicit copies) rather than with the
bulk distributor.

**`deer.py` and `deer_analysis.py` must ship together** — see below.

**The GUI needed a matching fix, and it would have broken without it.** All three
engine paths did `res['t'] = x[t_us >= 0] * tf`, i.e. they rebuilt the display axis
from the assumption that the engine drops every `t < 0`. With `pre_zero='even'` the
Tikhonov result has MORE rows than that, so the axis would have mismatched every
curve. The axis is now derived from the engine's own array
(`res['t'] = t_eng + t0_disp*tf`, algebraically identical to the old expression
whenever the engine did crop), and `_pre_zero` takes `t_eng` so it extends the
display below the engine's FIRST sample rather than below zero — otherwise it would
have re-extrapolated samples the engine had just fitted, and its `V_norm`/`vpos`
alignment would have slipped. Verified headless: array lengths agree and the
reconstructed axis is exact for 0 / 5 / 20 pre-t0 samples on both engines. A real
GUI run on a Bruker trace is still wanted before this is committed.

### Bench note

The `fel` box was silently thrashing — 6 worker processes × 6 OpenBLAS threads on 6
cores, load average 35, a 6-shard round making no progress in 60 minutes. Pinning
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1` finished the same round
in ~6 minutes. **Always pin the thread count when sharding on that box**; the
per-process CPU readout looks like a healthy 100 % either way.

## Known tensions between the recent short-r work (read before adding another)

Four shipped mechanisms now attack the same artefact — spurious short-r / grid-edge
mass — and they were each justified against a baseline that lacked the others. The
overlap is measured, not hypothetical: `echo_head` fell **+0.0046 → +0.0033 → +0.0016**
as `pre_zero` and `reg_edges` landed under it. **Anything new aimed at short-r mass
must be measured against all four, not against the historical baseline**, or it will
book a gain that is already being paid for elsewhere.

1. **The Wiener rejection argues against `echo_head`.** S7 rejected the Wiener filter
   partly on principle: tuning one engine toward the other "destroys the independence
   that makes a Mellin-vs-Tikhonov disagreement diagnostic", and objected to two
   constants fitted to a synthetic catalogue. `echo_head` IS the Tikhonov analogue of
   Mellin's δ-split, with two fitted constants (`head_level` 0.60,
   `head_ratio_max` 1.25) — the same convergence with the sign reversed. It is
   opt-in and default-off, which is the mitigating difference, but by S7's own
   standard it faced a lower bar than it should have.

2. **The two engines now fit DIFFERENT DATA on the same trace.** `pre_zero='even'` is
   Tikhonov-only (Mellin integrates on a log-T grid, `_gauss_mc` assumes uniform
   sampling), so on a trace with 15 pre-t₀ samples the Tikhonov engines see 161 points
   and Mellin/gauss 146. Cross-engine disagreement was supposed to diagnose METHOD;
   part of it is now the input. This undercuts the S6 cross-engine item and should be
   stated wherever the two are compared.

3. **`reg_edges` and the alias warning give opposite advice.** `reg_edges`: keep r_min
   generous and let the operator work, because closing the edge is wrong when the truth
   sits at the boundary. The alias warning: raise r_min to ~1.88 nm on a 32 ns trace.
   For a coarse-sampled sample with a genuinely short distance these conflict, and the
   conflict is real — clamping costs −0.0123 on the SHORT class at 32 ns. **Resolution
   for now: on coarse traces prefer raising r_min ONLY when no short distance is
   expected; otherwise accept the alias warning and keep the grid.** A principled rule
   (e.g. raise r_min but disable `reg_edges` when clamped) is unmeasured.

4. **`fit_zero_time` defaults balance a trade-off that shifted.** `xcheck` is off partly
   because "a slightly-late t0 compensates a Mellin forward bias" — but the estimator is
   shared, and Tikhonov's t0 sensitivity dropped materially with `pre_zero`. The
   default has not been re-derived since.

5. **CHECKED and clear:** `echo_head`'s guard threshold was fitted under the plain
   operator and its `r_mean` input now comes from a `reg_edges` inversion, so it could
   have drifted. Re-run on the 28 real traces under the shipped code: sample4 still
   gates off 7/7 with d_rms +0.00000 and sample1-3 still keep the head 5/7 each. The
   calibration survived.

Also note: roadmap sessions BEFORE 2026-08-04 quote absolute `lo_mass` figures measured
with the free-edge operator. They are internally consistent but not comparable with
anything measured after `reg_edges`.

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
