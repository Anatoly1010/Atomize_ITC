# S3 — Mellin transform core · COMPLETE (verified, fixes applied)

Run `wf_080dd2f1-054` — 26 agents, 2.36 M tokens, ~5 h, 0 errors. Structure as S1:
3 blind derivers + 2 code reviewers concurrently, then a reconciler that saw both,
then 2 adversarial skeptics per bug/risk (default stance REFUTED).

**7 confirmed, 3 plausible, 0 refuted, 11 notes.** All 7 confirmed are fixed, plus
one plausible and three notes as documentation.

> The plan called S3 *the riskiest math in the stack*: a bespoke analytic engine
> with no external implementation anywhere to check against, so every prior
> validation of it was self-consistency. That framing held up — the panel was the
> only reference available, and it is what found the one wrong number.

---

## Headline

**The transform itself is correct.** The Mellin pair, the reflected argument, the
inverse prefactor, the conjugation and the w→r Jacobian all survive an independent
three-way derivation and a convention-sensitivity sweep. That was the nightmare
case for this session and it is ruled out.

**The defects are in the layer around it** — an absolute-time clamp that collapses
short distances, one magic constant that is 0.92 % wrong, a correction that
silently switches itself off, a noise estimator that returns a 12× inflated value
on short traces, and two documented guarantees that are false.

The single largest is **S3-1**: `mellin_delta`'s floor is an absolute 90 ns,
independent of the trace's own decay scale, so for r₀ ≲ 2.5 nm it hands most of the
first dipolar oscillation to a single parabola. Measured overlap at r₀ = 1.6 nm:
**0.166**. After the fix: **0.678**.

---

## The blind-derivation panel

Three agents derived the Mellin core from first principles with no sight of the
code (verified from the transcripts: no repo-touching tool calls). They agreed
**unanimously, to 12 significant figures**, on every structural quantity:

| Quantity | Panel | Code |
|---|---|---|
| Forward relation | Ṽ(s) = Φ(s)·P(1−s) — density image **reflected** | same ✓ |
| Inverse | p(w) = (1/2π)·w^(−1/2)·∫ P(½+iτ) e^(−iτ ln w) dτ | same ✓ |
| Jacobian | f(r) = p(w)·\|dw/dr\| = p(w)·3w/r | same ✓ |
| Φ(1/3) | 2.97279973485 | — |
| Φ(2/3) | 1.45315224347 | — |
| Φ(1) | π/(2√3) = 0.906899682117 (exact) | — |
| Φ(4/3) | 0.578964762827 | — |
| Strip of convergence | 0 < Re s < 1 for the J-form; to 3/2 only by continuation | header says 3/2 ✗ |

and on the four moment constants:

| n | s | panel, g_e = 2.0023193 | panel, g = 2 | code (before) |
|---|---|---|---|---|
| 1 | 1/3 | **4.31510** | 4.31843 | 4.35466 ✗ |
| 2 | 2/3 | 3.06169 | 3.06642 | 3.06158 ✓ |
| 3 | 1 | 2.77353 | 2.77997 | 2.77339 ✓ |
| 4 | 4/3 | 2.57011 | 2.57806 | 2.56993 ✓ |

The panel **split once**, on the moment-error quadrature end weight — deriver 1 put
full weight on the interior and half only at the last point; derivers 2 and 3 used a
true composite trapezoid with half weight at *both* ends. Derivers 2/3 are right
(the analytic δ-split already supplies ∫₀^T₁, so T₁ is a left endpoint and carries
dt/2), and the code's own rule matches them to 1.2e-4. Recorded because a panel
split is itself a signal the quantity is subtle — see note N10.

### Confirmed correct — do not re-derive in S4–S6

- **The whole inversion chain**, by convention-sensitivity sweep on a noiseless
  3.0/0.20 nm case. Recovered area with **no** normalization applied = 0.9837,
  i.e. prefactor × Jacobian × conjugation are jointly right to 1.6 %. Every
  alternative breaks it loudly: no conjugation → area 8.15e-5; Jacobian r^−3 →
  2.984; r^−5 → 0.322; w without the 2π → mean 1.65 nm instead of 2.99; prefactor
  1/π → 1.967.
- **Core round trip**, noiseless, τ_max = 30: (2.50, 0.150) → (2.479, 0.212);
  (3.00, 0.200) → (2.989, 0.225); (4.00, 0.300) → (3.989, 0.339).
- **`I(s)` for n = 2, 3, 4** — correct to their own 6-digit rounding, and they match
  the **g_e** column, not the `g = 2` the comment claimed.
- **The δ-split analytic term** ∫₀^δ (F₀ + bT²)T^(s−1) dT = F₀δ^s/s + bδ^(s+2)/(s+2).
- **`moment_error_apriori`'s S weight** — the (1/2)² on i = 1 is load-bearing (using
  1 instead raises √S by 12.6 % at n = 1).
- **`distribution_moments`' skew** formula γ = (M₃ − 3M₁σ² − M₁³)/σ³.
- **`_tail_noise`'s (1 − 1/w)** moving-average variance correction.
- **`residual_whiteness`'s ACF/DW definitions** and the ci95 band for *raw* white
  noise — measured false-alarm rate 4.5 / 4.6 / 4.6 / 5.7 % at N = 50 / 100 / 200 /
  500 over 4000 draws each.

---

## CONFIRMED (7 raw → 6 unique)

### S3-1. `mellin_delta`'s absolute 90 ns floor collapses r ≲ 2.5 nm · bug · FIXED

`mellin_delta` clamped δ to the absolute window [0.09, 0.12] µs regardless of dt,
trace length or distance range. Because the raw F-level crossing is below 90 ns for
every r₀ ≲ 3.5 nm, the "adaptive" F(δ) estimate the docstring advertises was
inoperative for essentially every trace — δ was a constant. The [0, δ] segment is
then modelled by a single parabola F₀ + bT², and at short distance the form factor
has already gone through most of its first oscillation inside 90 ns, so that model
is grossly wrong: measured against fine quadrature of the exact segment integral,
25.1 % relative error at r₀ = 2.0 nm (fitted curvature b = −210 against a true
−754), 3.1 % at 2.5 nm, 0.19 % at 4.0 nm.

The floor and cap were, per the docstring, tuned on the synthetic benchmark — but
every distribution in that benchmark has its peak between 3.0 and 4.3 nm, exactly
the regime where the clamp is harmless.

**Fix** — a new `floor_ratio = 2.0`: the floor may raise δ to at most 2× the trace's
own raw crossing. Above ~3 nm the raw crossing already exceeds floor/2, so the
clamp binds exactly as before and the tuned regime is **bit-identical**; below it
the floor lets go. Measured, auto-δ, overlap vs truth:

| r₀ (nm) | 1.6 | 1.8 | 2.0 | 2.2 | 2.5 | 3.0 | 3.5 | 4.0 | 4.5 | 5.0 |
|---|---|---|---|---|---|---|---|---|---|---|
| before | 0.166 | 0.465 | 0.763 | 0.917 | 0.950 | 0.986 | 0.978 | 0.802 | 0.648 | 0.553 |
| after | **0.678** | **0.841** | **0.908** | 0.955 | 0.985 | 0.986 | 0.978 | 0.802 | 0.648 | 0.553 |

and with noise (12 realisations, λ = 0.4): r₀ = 2.0 nm goes 0.755 → 0.874 at
σ = 0.005, 0.615 → 0.730 at σ = 0.02, 0.416 → 0.601 at σ = 0.04. Everything at
r₀ ≥ 3.0 nm is unchanged to ±0.005.

### S3-2. `_MELLIN_I_S[1] = 4.35466` is 0.92 % too high · bug · FIXED

Found independently by the moments reviewer, by the blind reconciler, and by me
before the panel returned — three routes, same number. The constants must equal
I(s) = Φ(s)/(2π·ν_dd)^s. With the panel's Φ(1/3) = 2.972800 that is **4.31512**;
the stored 4.35466 corresponds to Φ(1/3) = 3.00006, i.e. Φ(1/3) taken as **3
exactly** (Φ(1/3) = 3 gives I = 4.354578, within 2e-5 of the stored value).

No convention rescues it: 4.35466 implies ν_dd = 50.6354 MHz·nm³, which is neither
the g_e value (52.0410) nor the g = 2 value (51.9205) nor the file's own NU_DD.
The other three entries are self-consistent and each implies ν_dd = 52.0437.

**Consequence is confined**: `I(s)` is consumed only by `moment_error_apriori`,
which returns an error bar, not a moment. Every displayed ME₁ was low by 0.908 %.
`moment_error_apriori(0.04, 24 ns, 231, n=1)` now returns **0.041091 nm** (was
0.040718); n = 2, 3, 4 are untouched.

**Fix** — `_MELLIN_I_S[1] = 4.31512`, and the comment's "for g=2" corrected (it was
never the g = 2 set; see note N7).

### S3-3. Parabolic echo-top term silently dropped below 3 samples · risk · FIXED

The correction was guarded by `count_nonzero(msk) >= 3` on a window set by the
`fit_level = 0.80` crossing. When the sampling step is coarse enough that the window
holds only two positive samples, the whole term was dropped **with no message** and
the code reverted to the constant-F split — the very model the docstring says the
parabola exists to remove. The fallback is an order of magnitude worse (constant-F
error 10.0 % at r₀ = 3.0 nm and 29.1 % at 2.5 nm, versus 0.47 % / 3.1 % with the
parabola), and the trigger is purely the acquisition step: at r₀ = 3.0 nm, dt = 32 ns
gave overlap 0.9681 and dt = 40 ns gave 0.8488. A 6 µs / 101-point trace — a
completely standard long-distance acquisition — landed on the wrong side.

**Fix** — the window is widened to always hold at least three positive samples
(`msk = Tp <= max(wfit, delta, Tp[2])`). Verified: the parabola is now ON at
dt = 32, 40, 48 and 60 ns, where before it switched off at 40.

### S3-4. The "conservative bound" guarantee is false · risk · FIXED (documentation)

The docstring asserted that "the empirical std of M1 from a full Tikhonov / Mellin
inversion sits at or below this bound … so ME_1 is a conservative a priori error
bar", and the GUI repeated it verbatim as a tooltip on all three info panels.
Monte-Carlo with the real engines (200 realisations per case, ε = 0.04, dt = 24 ns)
measures std(M1)/ME₁ = 0.97 (3.0 nm σ 0.15, NT = 231), 1.31 (4.0/0.50), 1.63
(5.0/0.20 on NT = 60), **2.64** (5.5/0.30 on NT = 40). Including bias — which is
what an error bar on a reported distance must cover — RMSE/ME₁ runs 1.45 to 41.8.
The bound is noise-only by construction, so it is *smallest exactly where the answer
is worst*.

**Fix** — the guarantee is removed from the docstring and from `MOMENTS_TOOLTIP`,
replaced by what was measured: ME₁ is a **noise floor**, it carries no resolution or
regularization-bias term, and the real scatter can exceed it.

### S3-5. Displayed mean and width/skew came from two different densities · risk · FIXED

`distribution_moments` clips negatives before normalizing — correct and documented
for proper distribution moments. But the GUI took `width` and `skew` from it while
computing the `mean` on the same row from the **unclipped signed** density, which
for the Mellin engine is explicitly signed. The two numbers on one line described
two different distributions, and the ±ME₁ attached to the mean was the error of
neither. Measured gap on a 3.0/0.15 nm case: signed mean 3.0023 vs clipped 3.0711,
**1.7× the ME₁ printed beside it**; on a broad 4.0/0.50 case, 0.261 nm = 6.4× ME₁.
The same mismatch went to the summary CSV.

**Fix** — mean, width and skew all now come from `distribution_moments`, in both the
info panel and `_trace_stats`, and the tooltip says they are moments of the
non-negative part of P(r).

### S3-6. `_tail_noise` returned a ~12× inflated σ for 12–28 samples · FIXED

`hi = n - w` exists specifically to drop the zero-padded right edge of the
`mode='same'` convolution, but the guard `resid[lo:hi] if hi - lo >= 4 else
resid[lo:]` put that edge straight back whenever the window was short — which is
every n in [12, 28]. At the padded edge the boxcar divides a partial sum by w, so
the residual is a fraction of the signal's DC level, not noise. Measured on
y = 0.7 + N(0, 0.01): 0.1224 at n = 12 through 0.1080 at n = 28, i.e. **10.8–12.5×**
the true 0.0100. σ_e feeds δ, the Wiener filter, the Monte-Carlo band amplitude and
the GUI's ε for ME₁.

**Fix** — and my first attempt at it was wrong, worth recording: the suggested
`resid[hi-4:hi]` slides into the **left** padded edge, which `mode='same'` also
creates and which the finding did not mention (it left n = 12 at 0.092). The
committed fix excludes **both** edges and pulls the window back toward the middle
rather than into the padding. Measured over 500 realisations: n ≥ 18 now returns
0.0086–0.0100 against a true 0.0100; n ≤ 16 returns 0.0 honestly (too few clean
points to measure); n ≥ 32 is unchanged by construction.

---

## PLAUSIBLE (3) — one skeptic refuted each

### `du = 0.02` log-T grid aliases short-r modulation on long traces · note

A step uniform in ln T is a step of T·du in real time — 40 ns at the end of a 2 µs
trace but 160 ns at the end of an 8 µs one. Resolving the fastest dipolar
oscillation needs r_min³ ≫ ν_dd·du·T_max, satisfied down to ~1.3 nm at 2 µs but
failing below ~2.0 nm at 8 µs. Measured: r₀ = 1.8 nm at T_max = 5 µs, overlap 0.689
at du = 0.02 vs 0.735 at du = 0.00125. The docstring's stated criterion
(`du < ~π/max|τ|`) covers only the post-substitution oscillation, not the signal's
own content.

**Not fixed.** It is note-severity, and it interacts with the τ_max auto-selection —
a data-driven `du` changes which τ_max the penalty selector picks, so it needs the
synthetic suite as a gate rather than a blind edit. Handed to **S4**, which owns
`deer_invert_mellin`. Note that S3-1 makes this *more* visible, since short-r
reconstructions now actually work.

### ME₁'s ε is measured where the noise is most amplified · note

Both call sites take ε from `_tail_noise` on the **last 35 %** of F, where the noise
carries the full 1/(λB(t)) amplification — while ME₁'s weight i^(−4/3) is
concentrated at the **start** (the first 10 % of points carry 75.7 % of S at
NT = 231). The result is a background-dependent inflation with nothing to do with
measurement quality: same trace quality, ME₁ spanning 0.0111 → 0.0520 (4.4×) as the
background rate goes 0.02 → 0.35.

**Not fixed**, deliberately. The direction is well argued and the docstring's own
definition (ε ~ σ_trace/λ) supports it, but the correction makes ME₁ *smaller*
while S3-4 has just established it already under-covers — and it is a change to a
displayed number on a split verdict. It belongs with the queued "a band that
deserves the name" work. Handed to **S6**.

### `residual_whiteness` demeans, so a DC pedestal reads as "white" · risk · FIXED

`e = e - e.mean()` removes exactly the systematic the diagnostic advertises: a
mis-estimated λ or a background pedestal leaves a constant offset. Measured on
c·σ + N(0, σ), n = 400: raw lag-1 autocorrelation +0.11 / +0.12 / +0.50 / +0.82 for
c = 0.2 / 0.5 / 1.0 / 2.0, while `residual_whiteness` returned `white=True` in every
one.

**Fixed additively** rather than by removing the demeaning (DW's textbook definition
does assume zero-mean regression residuals): the returned dict gains
`offset = mean(e)/std(e)`, computed before the subtraction, and the DEER window
prints `offset = ±x.xxσ` alongside DW and r₁ when |offset| > 0.25. Verified: offset
reads +0.97 and +2.09 for 1σ and 2σ pedestals that all previously read "white".

---

## Notes (11) — recorded, not acted on

- **N1 / N2 / N9 — the section header's convergence claim is wrong.** It says the
  Γ(s)cos(πs/2)·J(s) construction is "valid for 0 < Re s < 3/2"; J(s) actually
  converges only for Re s < 1 (|1−3x²| ~ 2√3|x−x₀| at the magic angle), reaching 3/2
  only by analytic continuation. The header also justifies the plain sinh grid by
  "unit modulus near u = 0" — the modulus is indeed 1 on the critical line, but the
  *phase* −2τ ln sinh u turns over ever faster as u → 0, so the trapezoid converges
  only as O(1/n_u). **Header corrected** (doc-only).
- **N8 — Φ(s) quadrature is 1st-order: 2.4e-2 relative error at τ = 30** (5.5e-2 in
  the 30–40 band, max 1.2e-1), converging 2.4e-2 → 6.0e-3 → 1.5e-3 → 3.7e-4 at
  n_u = 512 → 2048 → 8192 → 32768. **Left as is**: the effect on a recovered mean
  distance is 7.3e-5 nm at τ_max = 10 and ≤ 2.5e-5 nm beyond, far below anything the
  physics resolves. Now stated in the header instead of the false "integrates it
  accurately".
- **N7 — the `I(s)` comment said "for g=2"**; the values are the g_e/52.04 set,
  which is the right choice given NU_DD, but the wrong label invited a future "fix"
  toward the g = 2 column. **Comment corrected.**
- **N3 — δ below the first sample**: `np.interp` clamps, filling [δ, T₁] with the
  *decayed* F(T₁) instead of ~F₀, so that stretch is counted twice at the wrong
  level. Unreachable through the auto path; reachable via the GUI's manual δ, whose
  range is 0 … 1e9.
- **N4 — `ci95 = 1.96/√N` is the raw-data band.** Correct for raw white noise
  (verified above), but applied to residuals of a fitted regularized model whose
  null distribution differs: measured acf1 on *correct* Mellin fits has mean −0.062,
  so `white` over-flags on the anti-correlated side. Now stated in the docstring.
- **N5 — ME₁ end conventions.** The code gives the last point full trapezoid weight
  and stops at i = NT−1; a true composite trapezoid differs by 1.2e-4 relative at
  n = 1. Harmless; recorded so S4–S6 do not re-derive it.
- **N6 — `_tail_noise` returning 0.0 silently disables the Monte-Carlo band**
  (`deer_invert_mellin` gates it on `sig_e > 0`), with no warning and no log line.
  The S3-6 fix makes 0.0 *more* reachable on very short traces, so this is now
  documented in the docstring — but the caller still does not announce it.
  **Handed to S4.**
- **N10 — the panel split on the moment-error end weight** (see above).
- **N11** duplicates the ME₁-ε plausible finding.

---

## Deliberately not changed

- **`I(s)` for n = 2, 3, 4.** Each is off by −4.8e-5 to −9.5e-5 relative (they imply
  ν_dd = 52.0437 where the file uses 52.04). Below the rounding of the 6 digits
  stored and far below any experimental resolution; changing them would move
  historical numbers for no physical gain. Same reasoning S1 applied to NU_DD.
- **Computing `_MELLIN_I_S` from `NU_DD` at import.** Tempting — it would stop the
  two drifting apart — but n = 3 and n = 4 need the analytic continuation of a
  divergent integral (via ₂F₁), which is a lot of machinery to run at import for
  four constants. The corrected values are in the table above and the definition is
  now in the comment.
- **The `du` and ME₁-ε plausible findings** — reasons under PLAUSIBLE above.
- **`joint_background` and `deer_invert_mellin`** — out of scope by the plan; S4
  owns them.

---

## Regression evidence

- **Fix-by-fix verification**: each of the six fixes reproduces the failure it
  targets before, and does not after — tables above.
- **Synthetic gate for S3-1**, the only fix that moves numbers on normal data:
  large wins at r₀ ≤ 2.5 nm (up to +0.512 overlap), **bit-identical at r₀ ≥ 3.0 nm**
  across four noise levels. The one negative is −0.018 at r₀ = 2.5 nm / σ = 0.04,
  within the scatter of 12 realisations.
- **`_tail_noise` over 500 realisations** at 12 lengths: unchanged for n ≥ 32,
  inflation gone for 18 ≤ n ≤ 28, honest 0.0 below.
- **GUI smoke run, offscreen, per the S1 lesson** — Mellin engine with `fit_t0` on,
  over all 28 real ring-test traces: **28/28 complete**, `len(res['t']) ==
  len(form_factor)` on every one, `mean`/`width` finite on every one, info panel
  renders. The δ spinbox reads 0.09 on real data, i.e. the floor still binds there —
  confirming directly that S3-1 does not touch the real-trace regime.
- **DeerLab cross-check re-run post-fix** (`~/deer_benchmark/batch.py`, 28/28
  traces): mean P(r) overlap **0.978** (min 0.816), mean |Δpeak| **0.024 nm** (max
  0.327), mean |Δλ| vs the labs' own values **0.0259**. Identical to the S2
  post-fix baseline and to the historical figures — none of the S3 fixes moved the
  sequential/Tikhonov result, as expected since none of them is on that path.
- **All four engines end-to-end** on a 4.0 nm trace with background and noise:
  sequential 3.978 / joint 4.178 / mellin 4.054 / gauss 4.002 nm, all with matching
  `t` and `form_factor` lengths; `deer_validate` runs.

---

## Carried forward

- **To S4** (`deer_invert_mellin` + `joint_background`): the `du` aliasing finding;
  N6 (a zero noise level silently disabling the MC band); N3 (manual δ below the
  first sample). Plus everything S2 already handed over — the `joint_background`
  collapse guard above all.
- **To S6**: the ME₁-ε placement, with the queued CI work.
- **The port is now three sessions deep.** `deer.py` is byte-identical across plain
  / NIOCH / NIOCH_Q / Cryomech while ITC carries S1 + S2 + S3; `deer_analysis.py`
  exists only in ITC / NIOCH / NIOCH_Q. Port together, and run
  `~/atomize_sync/sync_check.py` first.
- **`sympy` and `mpmath` were not installed** on this machine, though S1's and S2's
  environment blocks both claimed they were. Installed this session (sympy 1.14.0,
  mpmath 1.3.0). S3 depended on them heavily; a future session should not assume
  the claim without checking.
