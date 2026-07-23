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
| S2 Tikhonov + NNLS | next | |
| S3 Mellin transform core | not started | |
| S4 Mellin engine + joint background | not started | |
| S5 Multi-Gaussian | not started | |
| S6 Cross-engine, validation, GUI | not started | |

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

## Next session — S2: Tikhonov + NNLS

Scope, hunt list and ground truth: [REVIEW_PLAN.md](REVIEW_PLAN.md) § S2.

Prerequisites, both now met:
- DeerLab works — `~/deer_benchmark/deerlab_shim.py`, import it **before**
  `deerlab` (site-packages untouched). This is S2's main ground truth.
- S1's negative-time fix is in, so engine comparisons are no longer contaminated.

The one thing S2 should test that the existing benchmarks do **not**: **CI
coverage.** `tikhonov_ci` reports a 95 % band from covariance/curvature; nothing
checks that it actually covers 95 %. Simulate N traces at known noise and count.
A band that reads 95 % and covers 60 % is a publication hazard.
