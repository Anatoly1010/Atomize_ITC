# S2 — Tikhonov + NNLS · INTERIM (review done, verification pending)

> **Nothing below the fold is verified.** Stage 1 (six independent reviewers) is
> complete; stage 2 (2 adversarial skeptics per finding, default stance REFUTED)
> has **not** run. S1 refuted findings that looked solid at this same stage, so
> treat every claim here as a *hypothesis with a reproduction attached*, not a
> defect. The one exception is the GUI axis regression, which was reproduced and
> fixed in-session — see below.

| | |
|---|---|
| Stage 1 run | `wf_789813f0-a0b` — 6 reviewers, ~2.9 M tokens, 3 h 20 min |
| Raw output | `~/deer_benchmark/s2_review_findings.json` (findings, coverage, numbers) |
| Stage 2 script | `~/deer_benchmark/s2_verify.js` — run instructions in its header |
| Findings | 38 raw → **15 unique bug/risk** after file:line merge, + 17 notes |

## Resuming — stage 2

`resumeFromRunId` is same-session only, so the verification stage is a standalone
workflow that takes the findings through `args`:

```bash
python3 -c "import json;print(json.dumps(json.load(open('/home/anatoly/deer_benchmark/s2_review_findings.json'))['to_verify']))"
```

then `Workflow({ scriptPath: '~/deer_benchmark/s2_verify.js', args: <that array> })`
— pass the actual JSON array, not a string. **14** findings × 2 skeptics = 28
agents; at this machine's concurrency cap of 2 (4 cores) budget several hours.

The queue holds 14, not 15: the GUI axis regression was fixed in-session and moved
to `fixed_in_session` in the JSON, so it is not re-verified. Its downstream finding
(ME1 `nan`, `deer_analysis.py:2368`) **is** still in the queue and must be judged
against the fixed code.

Findings merged from several reviewers carry `corroborated_by`. The skeptic prompt
is told explicitly that agreement is **not** a pass — the reviewers read the same
code and can share a premise.

---

## Fixed in-session: the GUI axis regression (introduced by S1)

Not a stage-1 hypothesis — reproduced directly, mechanism confirmed in the source,
and it was **live breakage in the fix S1 shipped on 2026-07-23**.

S1 added `_crop_pre_zero` (deer.py:312) so the engines drop `t < 0` samples. But
all three engine tabs then did `res['t'] = x * tf` — restoring the **full,
uncropped** acquisition axis over the engine's shortened result arrays:

```
sample1_labA: 354 input samples → engine returns 338 → res['t'] set back to 354
plot/export:  ValueError ... size 354 ... size 338
```

**All 28** real YopO traces carry pre-t₀ samples (4 to 40 of them; median ~13), so
the DEER window raised on every trace in the benchmark set. Fixed at
`deer_analysis.py:1844` (Tikhonov), `:1924` (Mellin), `:2012` (Multi-Gaussian) by
cropping the display axis with the engine's own condition:

```python
res['t'] = x[t_us >= 0] * tf
```

`t_us >= 0` rather than `x >= t0_disp` so the mask is bit-identical to the crop
`_crop_pre_zero` applies.

Verified by driving the GUI's exact transform (`fit_zero_time` → `t_us` →
`deer_invert`) over all 28 traces: `len(res['t'])` now equals
`len(form_factor) == len(F_fit) == len(residuals)` on **28/28**, where the old line
gave the full input length every time.

Two consequences reported by the reviewers should be re-checked once verification
runs, since both were downstream of this and may now be fixed or may be separate:
the ME1 error bar reading `nan` (`deer_analysis.py:2368`, an `IndexError` swallowed
at :2373) and the reliability bands using `ptp` of the uncropped axis (`:2503`).

---

## Unverified findings (15)

`x N` = how many of the six independent reviewers landed on that line.

### bug (9)

| | file:line | claim | reproduced number |
|---|---|---|---|
| 1 | `deer.py:629` **x3** | `deer_invert_joint` reports `F_fit`/`residuals` from `P_norm`, not the solved `P` | real labC: rms 0.001848 vs 0.001604 (−13 %), DW 1.493 vs 1.675. On a truth outside the r grid: R² reported **−1.90**, correct **+0.26** |
| 2 | `deer_analysis.py:1845` **x2** | GUI overwrites `res['t']` with the uncropped axis | **FIXED above** |
| 3 | `deer.py:547` | `alpha_factor` 2–4× — the docstring's own recommendation — collapses CI coverage | nominal 95 % → **19.1 %** on support, 0/100 at the true mode |
| 4 | `deer.py:452` | docstring claims the band is conservative; it under-covers at every mode | bimodal @ noise 0.005: 74.8 % support, 34 % modal, 0 % simultaneous; needs 2.5× width. **Worse as data get cleaner** |
| 5 | `deer.py:614` | joint engine (GUI default) biases mean r on strong backgrounds | r₀ 3.5 nm, k 0.40: joint mean **4.78 nm** (+1.28), λ 0.636 vs true 0.35; sequential 3.495 nm, λ 0.332 |
| 6 | `deer.py:358` | `tikhonov_nnls` lets scipy `nnls` raise 'Maximum iterations' and abort | deterministic 3/3 at the **default** r n=200, engine='joint' |
| 7 | `deer_analysis.py:2368` | ME1 error bar silently `nan` on every real trace | GUI `nan` vs correct 0.00217 nm (downstream of the axis bug) |
| 8 | `deer.py:443` | `tikhonov_ci` is a bias-blind sampling band | 64 % coverage; **0/120** at `alpha_factor` 3, bias −0.1596 vs reported half-band 1.96×0.0245 |
| 9 | `deer.py:630` | joint CI ignores background/λ variance | reported std 0.0431 vs actual scatter 0.3197 nm⁻¹ — **7.4× too narrow** |

### risk (6)

| | file:line | claim | reproduced number |
|---|---|---|---|
| 10 | `deer.py:544` **x2** | α grid ceiling 1e3 is in dr-dependent units and pins silently | r=[3.0,4.5] with default 200 pts: α_opt = 1000 at index **35/35**; true optimum 3981. Peak position cost 0.59 nm |
| 11 | `deer.py:422` | `method='curvature'` argmax includes the κ=0 sentinels | same trace, only `bg_start` moved: α swings 1.585e-4 ↔ 158.5 (6 decades), 17 modes ↔ 1 |
| 12 | `deer.py:469` | band diverges as α → 0 | manual α=0.1: band max 101 nm⁻¹ on a 6.4 nm⁻¹ peak; α=1e-4 (spinbox min): 5.4e5 |
| 13 | `deer.py:616` | λ pin fails on undecayed tails | Tmax 1.0 µs: joint λ 0.053 (6.6× low), overlap 0.404 vs sequential 0.632 |
| 14 | `deer_analysis.py:2503` | reliability bands use `ptp` of the acquisition axis, not dipolar t_max | edges 3.366/5.609 vs 3.314/5.523 nm |
| 15 | `deer_analysis.py:1838` | manual-α runs still pay the full 36-point scan | 119.0 s vs 3.52 s with `scan_lcurve=False` — **34×** |

17 notes are in the JSON under `notes`, carried through unverified.

---

## Numbers worth keeping regardless of the verdicts

These are measurements, not claims, and several are the first of their kind for
this code. Full tables in `s2_review_findings.json` → `per_dimension[].numbers`.

**DeerLab cross-check, 28 real YopO traces — no regression from S1.** This was the
headline risk of doing S1's fixes before S2, and it is clean:

| metric | this run | historical (pre-S1) |
|---|---|---|
| mean P(r) overlap | 0.9781 (min 0.816) | 0.978 |
| mean \|Δpeak\| | 0.0245 nm (max 0.327) | 0.024 nm |
| harness-crop vs `_crop_pre_zero` | **1.00000 overlap on all 28** | n/a |
| sum(P) ours / DeerLab | 1.0007 / 1.0007 | n/a |
| CI rel. width at peak, ours / DL | 0.318 / 1.133 — **DeerLab 3.6× wider** | n/a |

**α selection agrees with DeerLab exactly** where both use the same 36-point grid
(`sample1_labA` 0.0631, `sample2_labB` 0.01585, `sample3_labA` 1.0 — all EXACT), and
matches `dl aic` on the same grid. The GCV *functional* is therefore not the problem;
the reviewers' α findings are about the grid ceiling and the `curvature` branch.

**The regularization operator matches DeerLab up to dr².** `max|regoperator(r,2) −
L_repo/dr²| = 2.6e-11` at n=200. The classic boundary off-by-one is **absent** —
both are (n−2, n). The dr² difference means this code's α is not on DeerLab's scale
(α_repo·dr² ≈ α_DL, ratio 0.94–1.06), which is a units note, not a defect — but it
is what makes finding 10 (dr-dependent grid ceiling) plausible.

**Mass/scale bookkeeping is clean:** λ round-trip 0.1469/0.2938/0.4896 for true
0.15/0.30/0.50; `∫P_density dr = 1.0000` in all cases; sum(P) 0.975–1.003 over the
27 ring-test traces. The "invisible rescaling" S1 warned about is **not present**.

**CI coverage — the number S2 existed to produce.** Nominal 95 % throughout:

| config | support cov. | modal cov. | simultaneous |
|---|---|---|---|
| narrow, noise 0.005, sequential | 0.942 | 0.805 | 0.565 |
| narrow, noise 0.020, sequential | 0.856 | 0.400 | 0.330 |
| bimodal, noise 0.005, sequential | 0.748 | 0.340 | 0.000 |
| narrow, noise 0.010, **joint** | 0.771 | 0.180 | 0.100 |
| narrow, noise 0.010, **α×4** | 0.191 | 0.000 | 0.000 |
| DeerLab 0.14.2, narrow, noise 0.010 | 0.883 | 0.480 | 0.360 |

Two things to hold onto when reading the verdicts. DeerLab's own band under-covers
too (0.883 / 0.480) — so "narrower than nominal" is partly intrinsic to covariance
CIs on a regularized non-negative estimator, and a skeptic may reasonably refute
findings 4/8 on that basis. But this code's band is **3.6× narrower than DeerLab's**
on real data, and the α×4 collapse to 0.191 is specific to this tool's own
documented recommendation. Those are separable questions and should get separate
verdicts.

---

## For the reviewer of stage 2

- Findings 3, 4, 8, 9 are all facets of "the CI is too narrow" reached by two
  different reviewers by different routes. Expect correlated verdicts; do not read
  four confirmations as four independent defects.
- Findings 1 and 2 both trace to how a result dict's arrays relate to its axis.
  With 2 fixed, re-check 7 before accepting it.
- Finding 5 tests `k` = 0.20–0.40 /µs. The real ring-test set spans k = 0.0018–0.0457
  with decay 1.4–18.4 % over the trace — **k ≥ 0.2 is never exercised by real data
  here**, so a skeptic should press on whether the scenario is reachable.
- S1's method lessons still bind: `deer.simulate` is even in t, and
  `benchmark.py:46` pre-crops where the GUI does not.
