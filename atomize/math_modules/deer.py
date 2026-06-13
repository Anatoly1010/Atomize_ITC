#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEER / PDS distance-distribution analysis (math core).

Pulsed-dipolar spectroscopy traces (DEER/PELDOR, and the closely related
RIDME / DQC / SIFTER) share one model: a background-corrected form factor F(t)
is the integral over the distance distribution P(r) of an orientation-averaged
dipolar kernel,

    F(t) = \\int K(t, r) P(r) dr ,
    K(t, r) = \\int_0^1 cos[(1 - 3 xi^2) w(r) t] dxi ,

with the dipolar angular frequency w(r) = 2*pi * NU_DD / r^3 (rad/us, r in nm,
t in us). The kernel integral has a closed form in Fresnel integrals, so K is
built without a per-orientation loop.

Recovering P(r) from F(t) is a Fredholm equation of the first kind (ill-posed);
this module solves it with Tikhonov regularization + non-negativity (NNLS), the
regularization weight chosen at the L-curve corner. A model-free analytic
Mellin-transform inversion (Matveeva/Maryasov, doi 10.1039/C7CP04059H) is
planned as a second engine.

Conventions: t in microseconds, r in nanometres. P is handled internally as
discrete probability masses (sum = 1); the matching density P(r) = masses / dr
is returned for plotting.

All heavy routines need scipy (the `math` extra: pip install -e .[math]); scipy
is imported lazily so importing this module never fails on a minimal install.
"""

import numpy as np

# scipy is an optional dependency (pip install -e .[math]) and slow to import
# (~0.6 s on Windows). Probe availability cheaply -- find_spec does NOT import
# scipy -- and defer the real import to _require_scipy(), so importing this
# module stays numpy-only and GUIs that embed it start fast.
import importlib.util
SCIPY_AVAILABLE = importlib.util.find_spec('scipy') is not None
fresnel = nnls = curve_fit = None

# Perpendicular dipolar frequency constant: nu_perp = NU_DD / r^3 [MHz], r in nm
# (g = 2.0023). w(r) = 2*pi*nu_perp is then in rad/us for t in us.
NU_DD = 52.04  # MHz nm^3


def _require_scipy():
    """Lazily import scipy on first use and bind the symbols this module needs.
    Every scipy-using function calls this first, so the module-level fresnel /
    nnls / curve_fit globals are guaranteed populated before they are read."""
    global fresnel, nnls, curve_fit
    if not SCIPY_AVAILABLE:
        raise RuntimeError('DEER analysis requires scipy (pip install -e .[math]).')
    if fresnel is None:
        from scipy.special import fresnel as _fresnel
        from scipy.optimize import nnls as _nnls, curve_fit as _curve_fit
        fresnel, nnls, curve_fit = _fresnel, _nnls, _curve_fit


# --------------------------------------------------------------------------- #
#  Dipolar kernel
# --------------------------------------------------------------------------- #
def dipolar_frequency(r, nu_dd=NU_DD):
    """Perpendicular dipolar frequency nu_perp(r) = nu_dd / r^3 [MHz], r in nm."""
    r = np.asarray(r, dtype=float)
    return nu_dd/r**3


def dipolar_kernel(t, r, nu_dd=NU_DD):
    """Orientation-averaged DEER kernel K[t, r] (no background, no modulation).

    `t` in us, `r` in nm. Returns shape (len(t), len(r)) with K(0, r) = 1,
    evaluated in closed form via Fresnel integrals:

        K(t, r) = sqrt(pi / (6 a)) [cos(a) C(z) + sin(a) S(z)],
        a = w(r) |t|,  z = sqrt(6 a / pi),  w(r) = 2*pi*nu_dd / r^3 .

    The a -> 0 limit is K = 1 (set explicitly to avoid 0/0).
    """
    _require_scipy()
    t = np.asarray(t, dtype=float).reshape(-1, 1)     # (nt, 1)
    r = np.asarray(r, dtype=float).reshape(1, -1)     # (1, nr)
    w = 2*np.pi*nu_dd/r**3                             # (1, nr) rad/us
    a = np.abs(w*t)                                    # (nt, nr) >= 0
    z = np.sqrt(6*a/np.pi)
    S, C = fresnel(z)                                  # scipy returns (S, C)
    with np.errstate(divide='ignore', invalid='ignore'):
        K = np.sqrt(np.pi/(6*a))*(np.cos(a)*C + np.sin(a)*S)
    K[a == 0] = 1.0
    return K


# --------------------------------------------------------------------------- #
#  Background correction
# --------------------------------------------------------------------------- #
def _bg_model(t, A, k, d):
    return A*np.exp(-(k*np.abs(t))**(d/3.0))


def background_fit(t, V, bg_start, bg_end=None, dim=3.0, fit_dim=False):
    """Fit the intermolecular background on the window bg_start <= t (<= bg_end)
    and return the background-corrected form factor.

    `V` is normalized so V(t=0) = 1. The tail window is fit to
    (1 - lambda) * exp(-(k|t|)^(d/3)); the modulation depth lambda = 1 - A. The
    full-trace background is B(t) = exp(-(k|t|)^(d/3)) and the form factor

        F(t) = (V(t)/B(t) - (1 - lambda)) / lambda .

    Only the fit window is bounded by [bg_start, bg_end]; B(t) and F(t) are still
    evaluated over the whole trace. `bg_end=None` uses everything past bg_start
    (the default). `dim` is the fractal background dimension (3 = homogeneous 3D);
    set `fit_dim=True` to float it. Returns a dict with lambda, k, dim, A, B,
    form_factor, t, bg_start, bg_end, mask.
    """
    _require_scipy()
    t = np.asarray(t, dtype=float)
    V = np.asarray(V, dtype=float)
    V = V/V[int(np.argmin(np.abs(t)))]                 # normalize at t = 0
    mask = t >= bg_start
    if bg_end is not None:
        mask = mask & (t <= bg_end)
    if mask.sum() < 4:
        raise ValueError('Background region has too few points; widen [bg_start, bg_end].')
    tt, vv = t[mask], V[mask]
    a0 = float(np.clip(vv[0], 0.05, 1.0))
    if fit_dim:
        popt, _ = curve_fit(_bg_model, tt, vv, p0=[a0, 0.1, dim],
                            bounds=([0.0, 0.0, 1.0], [1.5, np.inf, 6.0]),
                            maxfev=10000)
        A, k, d = popt
    else:
        f = lambda tx, A, k: _bg_model(tx, A, k, dim)
        popt, _ = curve_fit(f, tt, vv, p0=[a0, 0.1],
                            bounds=([0.0, 0.0], [1.5, np.inf]), maxfev=10000)
        A, k = popt
        d = dim
    lam = 1.0 - A
    B = np.exp(-(k*np.abs(t))**(d/3.0))
    if abs(lam) < 1e-6:
        lam = 1e-6
    F = (V/B - (1 - lam))/lam
    return {'lambda': lam, 'k': float(k), 'dim': float(d), 'A': float(A),
            'B': B, 'form_factor': F, 'V_norm': V, 't': t,
            'bg_start': float(bg_start),
            'bg_end': (None if bg_end is None else float(bg_end)), 'mask': mask}


# --------------------------------------------------------------------------- #
#  Tikhonov regularization + non-negativity
# --------------------------------------------------------------------------- #
def regularization_matrix(n, order=2):
    """Discrete derivative operator L for Tikhonov smoothing (default 2nd order)."""
    if order == 0:
        return np.eye(n)
    if order == 1:
        L = np.zeros((n - 1, n))
        idx = np.arange(n - 1)
        L[idx, idx] = -1.0
        L[idx, idx + 1] = 1.0
        return L
    L = np.zeros((n - 2, n))            # second order (curvature)
    idx = np.arange(n - 2)
    L[idx, idx] = 1.0
    L[idx, idx + 1] = -2.0
    L[idx, idx + 2] = 1.0
    return L


def tikhonov_nnls(K, F, alpha, L=None):
    """Non-negative Tikhonov solution of K P = F.

    Minimizes ||K P - F||^2 + alpha^2 ||L P||^2 subject to P >= 0 by solving the
    augmented NNLS problem [[K]; [alpha L]] P = [F; 0]. Returns P (masses, >= 0).
    """
    _require_scipy()
    K = np.asarray(K, float)
    F = np.asarray(F, float)
    if L is None:
        L = regularization_matrix(K.shape[1], 2)
    A = np.vstack([K, alpha*L])
    b = np.concatenate([F, np.zeros(L.shape[0])])
    P, _ = nnls(A, b)
    return P


def _menger(x1, y1, x2, y2, x3, y3):
    """Signed Menger curvature of three points (L-curve corner detector)."""
    a2 = (x2 - x1)**2 + (y2 - y1)**2
    b2 = (x3 - x2)**2 + (y3 - y2)**2
    c2 = (x3 - x1)**2 + (y3 - y1)**2
    twice_area = (x2 - x1)*(y3 - y1) - (x3 - x1)*(y2 - y1)
    denom = np.sqrt(a2*b2*c2)
    return 0.0 if denom == 0 else 2*twice_area/denom


def l_curve(K, F, alphas, L=None, method='gcv'):
    """Regularization scan over `alphas`: for each one solve the NNLS-Tikhonov
    problem and record the residual norm rho, the roughness norm eta, the Menger
    L-curve curvature, and the GCV score.

    The optimal alpha is chosen by `method`:
      'gcv'       -- minimum of the generalized cross-validation score (default).
                     Robust for DEER, whose L-curve is nearly vertical (the
                     residual stays at the noise floor across decades of alpha),
                     so the classic L-corner is ill-defined and tends to pick a
                     tiny alpha => spiky P(r).
      'curvature' -- classic maximum-Menger-curvature L-corner.

    GCV uses the (unconstrained) Tikhonov influence-matrix trace as the effective
    degrees of freedom paired with the NNLS residual -- the standard DEER GCV
    approximation.

    Returns dict: alphas, rho, eta, curvature, gcv, alpha_opt, index, method,
    P (the solution at the chosen alpha).
    """
    _require_scipy()
    K = np.asarray(K, float)
    F = np.asarray(F, float)
    if L is None:
        L = regularization_matrix(K.shape[1], 2)
    alphas = np.asarray(alphas, float)
    n = len(F)
    KtK = K.T@K
    LtL = L.T@L
    rho = np.empty(len(alphas))
    eta = np.empty(len(alphas))
    gcv = np.empty(len(alphas))
    Ps = []
    for i, al in enumerate(alphas):
        P = tikhonov_nnls(K, F, al, L)
        Ps.append(P)
        rho[i] = np.linalg.norm(K@P - F)
        eta[i] = np.linalg.norm(L@P)
        try:                                          # effective d.o.f. (hat trace)
            dof = float(np.trace(K@np.linalg.solve(KtK + (al**2)*LtL, K.T)))
        except np.linalg.LinAlgError:
            dof = 0.0
        denom = n - dof
        gcv[i] = n*rho[i]**2/denom**2 if abs(denom) > 1e-9 else np.inf
    x = np.log(rho + 1e-300)
    y = np.log(eta + 1e-300)
    kappa = np.zeros(len(alphas))
    for i in range(1, len(alphas) - 1):
        kappa[i] = _menger(x[i - 1], y[i - 1], x[i], y[i], x[i + 1], y[i + 1])
    if method == 'curvature':
        idx = int(np.argmax(kappa)) if len(alphas) > 2 else len(alphas)//2
    else:                                             # 'gcv' (default)
        idx = int(np.argmin(gcv))
    return {'alphas': alphas, 'rho': rho, 'eta': eta, 'curvature': kappa,
            'gcv': gcv, 'alpha_opt': float(alphas[idx]), 'index': idx,
            'method': method, 'P': Ps[idx]}


# --------------------------------------------------------------------------- #
#  Full pipeline + forward simulation
# --------------------------------------------------------------------------- #
def default_r_axis(rmin=1.5, rmax=8.0, n=200):
    """Default distance grid (nm)."""
    return np.linspace(rmin, rmax, int(n))


def _normalize_masses(P):
    s = float(np.sum(P))
    return P/s if s > 0 else P


def tikhonov_ci(K, F, alpha, P, L=None, dr=1.0, z=1.96):
    """Covariance-based confidence band on the regularized P(r) — the asymptotic
    (curvature) CI DeerLab shows by default.

    For the linear Tikhonov estimator P = (KᵀK + α²LᵀL)⁻¹ Kᵀ F, the noise on the
    form factor propagates as cov(P) = σ² M Mᵀ with M = (KᵀK + α²LᵀL)⁻¹ Kᵀ and σ²
    estimated from the fit residuals (effective dof = N − tr(K M)). Returns
    (lower, upper) at confidence z (default 95%) on the same density scale as
    P/sum(P)/dr, clipped at 0. The non-negativity constraint is not propagated, so
    the band is a slightly conservative linear approximation (as in DeerLab's
    moment-based CI)."""
    K = np.asarray(K, float)
    F = np.asarray(F, float)
    P = np.asarray(P, float)
    n = K.shape[1]
    if L is None:
        L = regularization_matrix(n, 2)
    G = K.T @ K + (alpha**2)*(L.T @ L)
    try:
        Ginv = np.linalg.inv(G)
    except np.linalg.LinAlgError:
        Ginv = np.linalg.pinv(G)
    M = Ginv @ K.T
    resid = F - K @ P
    dof = max(float(K.shape[0]) - float(np.trace(K @ M)), 1.0)
    sigma2 = float(np.sum(resid**2)/dof)
    std = np.sqrt(np.maximum(sigma2*np.einsum('ij,ij->i', M, M), 0.0))
    scale = 1.0/((float(np.sum(P)) or 1.0)*dr)         # masses -> density
    dens = P*scale
    band = z*std*scale
    return np.maximum(dens - band, 0.0), dens + band


def deer_invert(t, V, r=None, bg_start=None, bg_end=None, dim=3.0, fit_dim=False,
                alpha=None, alphas=None, reg_order=2, nu_dd=NU_DD,
                scan_lcurve=True, method='gcv', engine='sequential',
                alpha_factor=1.0):
    """Full DEER pipeline: background-correct V(t), build the kernel, invert to
    P(r) by Tikhonov + NNLS. When `alpha` is not supplied it is chosen
    automatically by `method` ('gcv' default, or 'curvature' for the classic
    L-corner) -- see `l_curve`.

    `alpha_factor` scales the auto-selected alpha (ignored when an explicit
    `alpha` is given). GCV/AIC tend to under-regularize the near-vertical DEER
    L-curve, leaving noise spikes in P(r); a factor > 1 (e.g. 2-4) reproduces
    the heavier hand-picked L-corner regularization the DeerAnalysis ring-test
    labs used to get smooth distributions (Schiemann et al., JACS 2021).

    `engine` selects how the background is handled:
      'sequential' -- fit the background on the tail window, divide it out, then
                       invert the form factor (this function; fast, the default).
      'joint'      -- fit background + modulation depth together with P(r) in one
                       separable-NLLS pass (`deer_invert_joint`; DeerLab-style,
                       more robust on short/shallow backgrounds).

    `t` in us, `r` in nm. With `scan_lcurve` (default) the regularization scan is
    always computed for display, even when an explicit `alpha` is given. Returns a dict:
    t, r, form_factor F(t), F_fit = K P, residuals, P (raw masses), P_norm
    (masses, sum = 1), P_density (P_norm / dr, integrates to 1), kernel, alpha,
    l_curve (when scanned), background result, lambda / k / dim, and engine.
    """
    if engine == 'joint':
        return deer_invert_joint(t, V, r=r, bg_start=bg_start, bg_end=bg_end,
                                 dim=dim, fit_dim=fit_dim, alpha=alpha,
                                 alphas=alphas, reg_order=reg_order, nu_dd=nu_dd,
                                 method=method, scan_lcurve=scan_lcurve,
                                 alpha_factor=alpha_factor)
    _require_scipy()
    t = np.asarray(t, float)
    V = np.asarray(V, float)
    r = default_r_axis() if r is None else np.asarray(r, float)
    if bg_start is None:
        bg_start = t[0] + 0.5*(t[-1] - t[0])
    bg = background_fit(t, V, bg_start, bg_end=bg_end, dim=dim, fit_dim=fit_dim)
    F = bg['form_factor']
    K = dipolar_kernel(t, r, nu_dd=nu_dd)
    L = regularization_matrix(len(r), reg_order)
    if alphas is None:
        # wide grid (1e-4 .. 1e3): GCV needs room above the old 1e1 ceiling to
        # find its true minimum, which for well-separated peaks sits at alpha~1e2.
        alphas = np.logspace(-4, 3, 36)
    lc = l_curve(K, F, alphas, L, method=method) if (scan_lcurve or alpha is None) else None
    if alpha is None:
        alpha = lc['alpha_opt']*float(alpha_factor)
        P = lc['P'] if alpha_factor == 1.0 else tikhonov_nnls(K, F, alpha, L)
    else:
        P = tikhonov_nnls(K, F, alpha, L)
    F_fit = K@P
    P_norm = _normalize_masses(P)
    dr = float(r[1] - r[0]) if len(r) > 1 else 1.0
    P_density = P_norm/dr
    P_lower, P_upper = tikhonov_ci(K, F, alpha, P, L=L, dr=dr)
    return {'t': t, 'r': r, 'form_factor': F, 'F_fit': F_fit,
            'residuals': F - F_fit, 'P': P, 'P_norm': P_norm,
            'P_density': P_density, 'P_lower': P_lower, 'P_upper': P_upper,
            'kernel': K, 'alpha': float(alpha),
            'l_curve': lc, 'background': bg, 'lambda': bg['lambda'],
            'k': bg['k'], 'dim': bg['dim'], 'engine': 'sequential'}


def deer_invert_joint(t, V, r=None, bg_start=None, bg_end=None, dim=3.0,
                      fit_dim=False, alpha=None, alphas=None, reg_order=2,
                      nu_dd=NU_DD, method='gcv', scan_lcurve=True,
                      alpha_factor=1.0):
    """DEER inversion with a *joint* (separable-NLLS / variable-projection) fit of
    the background and modulation depth together with the regularized non-negative
    P(r) -- the strategy DeerLab uses. More robust than the sequential
    'fit background, then invert' pipeline (`deer_invert`) on real traces with
    short or shallow backgrounds, where the tail fit and the inversion are coupled.

    Model:  V(t) = B(t) * [ (1 - lam) + lam * (K P)(t) ],  B(t) = exp(-(k|t|)^(d/3)).

    The background decay rate (k, and d when `fit_dim`) is the only nonlinear
    unknown. For each trial rate the modulation depth lam is *pinned* to the mean
    baseline of V/B over the background window [bg_start, bg_end] (where the
    intramolecular form factor has decayed and V ~ (1-lam) B), and the non-negative
    regularized P(r) follows from K P = (V/B - (1-lam))/lam. The rate is chosen to
    minimize the whole-trace residual ||V - B[(1-lam)+lam KP]||.

    Pinning lam to the baseline is essential: with lam free the fit is degenerate
    (a near-flat background plus extra long-r P(r) mass reproduces V equally well)
    and collapses to k -> 0; the baseline constraint removes that direction and
    recovers the correct, deeper background -- matching DeerLab's joint fit.
    `bg_start`/`bg_end` therefore set the baseline window. Same return dict as
    `deer_invert`, with engine='joint'.
    """
    _require_scipy()
    from scipy.optimize import least_squares, minimize_scalar
    t = np.asarray(t, float)
    V = np.asarray(V, float)
    r = default_r_axis() if r is None else np.asarray(r, float)
    V = V/V[int(np.argmin(np.abs(t)))]            # normalize V(0) = 1
    K = dipolar_kernel(t, r, nu_dd=nu_dd)
    L = regularization_matrix(len(r), reg_order)
    if alphas is None:
        alphas = np.logspace(-4, 3, 24)

    if bg_start is None:
        bg_start = t[0] + 0.6*(t[-1] - t[0])      # bias into the decayed tail
    hi = bg_end if (bg_end is not None and bg_end > bg_start) else float(t.max())
    mask = (t >= bg_start) & (t <= hi)
    if int(mask.sum()) < 3:
        mask = t >= bg_start

    bg0 = background_fit(t, V, bg_start, bg_end=bg_end, dim=dim, fit_dim=fit_dim)
    k0, d0 = bg0['k'], bg0['dim']

    def lam_of(B):
        return min(max(1.0 - float(np.mean((V/B)[mask])), 0.02), 0.95)

    def solve_P(k, d, al):
        B = np.exp(-(k*np.abs(t))**(d/3.0))
        lam = lam_of(B)
        F = (V/B - (1 - lam))/lam
        return B, lam, F, tikhonov_nnls(K, F, al, L)

    # select alpha once on the seed background; F is normalized (F(0)=1) so the
    # regularization weight is stable across the rate search
    B0 = np.exp(-(k0*np.abs(t))**(d0/3.0))
    lam0 = lam_of(B0)
    F0 = (V/B0 - (1 - lam0))/lam0
    lc = (l_curve(K, F0, alphas, L, method=method)
          if (scan_lcurve or alpha is None) else None)
    alpha_use = float(alpha) if alpha is not None else lc['alpha_opt']*float(alpha_factor)

    def vss(k, d):                                # whole-trace V-space residual SS
        B, lam, F, P = solve_P(k, d, alpha_use)
        return float(np.sum((V - B*((1 - lam) + lam*(K@P)))**2))

    kref = max(float(k0), 1e-4)
    if fit_dim:
        def resid(theta):
            k = abs(theta[0]); d = min(max(theta[1], 1.0), 6.0)
            B, lam, F, P = solve_P(k, d, alpha_use)
            return V - B*((1 - lam) + lam*(K@P))
        try:
            sol = least_squares(resid, [kref, d0],
                                bounds=([0.0, 1.0], [np.inf, 6.0]), max_nfev=200)
            k = abs(sol.x[0]); d = min(max(sol.x[1], 1.0), 6.0)
        except Exception:
            k, d = kref, d0
    else:
        d = d0
        try:
            sol = minimize_scalar(lambda lk: vss(np.exp(lk), d),
                                  bounds=(np.log(kref/100.0), np.log(kref*100.0)),
                                  method='bounded', options={'xatol': 3e-2})
            k = float(np.exp(sol.x))
        except Exception:
            k = kref

    # final solution at the fitted background (alpha from the seed selection is
    # reused: F is normalized to F(0)=1, so the weight transfers across the rate
    # search — re-scanning here only adds a costly GCV pass for no gain)
    B = np.exp(-(k*np.abs(t))**(d/3.0))
    lam = lam_of(B)
    F = (V/B - (1 - lam))/lam
    P_masses = tikhonov_nnls(K, F, alpha_use, L)
    P_norm = _normalize_masses(P_masses)
    dr = float(r[1] - r[0]) if len(r) > 1 else 1.0
    F_fit = K@P_norm
    P_lower, P_upper = tikhonov_ci(K, F, alpha_use, P_masses, L=L, dr=dr)
    bg = {'lambda': lam, 'k': float(k), 'dim': float(d), 'A': float(1 - lam),
          'B': B, 'form_factor': F, 'V_norm': V, 't': t,
          'bg_start': float(bg_start),
          'bg_end': (None if bg_end is None else float(bg_end)),
          'mask': mask}
    return {'t': t, 'r': r, 'form_factor': F, 'F_fit': F_fit,
            'residuals': F - F_fit, 'P': P_masses, 'P_norm': P_norm,
            'P_density': P_norm/dr, 'P_lower': P_lower, 'P_upper': P_upper,
            'kernel': K, 'alpha': float(alpha_use),
            'l_curve': lc, 'background': bg, 'lambda': lam,
            'k': float(k), 'dim': float(d), 'engine': 'joint'}


# --------------------------------------------------------------------------- #
#  Zero-time (reference-time) fitting
# --------------------------------------------------------------------------- #
def fit_zero_time(t, V, bg_start=None, bg_end=None, n_grid=16, search_frac=0.15,
                  refine=True, **kwargs):
    """Find the zero-time t0 (the dipolar reference time) that best aligns the
    kernel with the data, by minimizing the V-space reconstruction residual.

    DEER is sensitive to where t = 0 of the dipolar evolution sits: an error of
    even a few tens of ns misaligns the kernel, broadens P(r) and biases the mean
    distance long. DeerLab fits this `reftime` by default; this is the equivalent
    for the engines here. A candidate offset s shifts both the time axis and the
    (data-anchored) background window, so only the kernel alignment changes; the
    residual ‖V - V_fit‖ is smooth with a single minimum in s, so a coarse grid
    over the first `search_frac` of the trace plus a parabolic refine pins it down
    in ~`n_grid` inversions.

    t, V, bg_start, bg_end are in the kernel time unit (µs). `kwargs` pass through
    to `deer_invert` (r, dim, fit_dim, alpha, alpha_factor, ...). Returns the
    optimal t0 in the same units as `t`.

    For speed the search uses a fixed-alpha *sequential* inversion at each offset:
    t0 is set by the shape of the residual, not by the engine or the exact
    regularization, so this avoids a per-offset GCV scan and the slower joint
    background fit. The caller runs its chosen engine once at the returned t0.
    """
    t = np.asarray(t, float)
    V = np.asarray(V, float)
    span = float(t[-1] - t[0]) or 1.0
    grid = np.linspace(float(t[0]), float(t[0]) + search_frac*span,
                       int(max(3, n_grid)))

    # fast, fixed-alpha sequential inversion for the search, on a capped distance
    # grid (t0 is set by the residual shape, not the P(r) resolution)
    opts = dict(kwargs)
    opts['engine'] = 'sequential'
    opts['scan_lcurve'] = False
    opts.pop('alpha_factor', None)
    rr = opts.get('r')
    if rr is not None and len(np.asarray(rr)) > 100:
        rr = np.asarray(rr, float)
        opts['r'] = np.linspace(rr[0], rr[-1], 100)
    if opts.get('alpha') is None:                 # select alpha once, then hold it
        s0 = float(grid[len(grid)//2])
        try:
            res0 = deer_invert(t - s0, V,
                               bg_start=(None if bg_start is None else bg_start - s0),
                               bg_end=(None if bg_end is None else bg_end - s0),
                               **opts)
            opts['alpha'] = float(res0['alpha'])
        except Exception:
            opts['alpha'] = None

    def resid_at(s):
        try:
            res = deer_invert(t - s, V,
                              bg_start=(None if bg_start is None else bg_start - s),
                              bg_end=(None if bg_end is None else bg_end - s),
                              **opts)
        except Exception:
            return np.inf
        bg = res['background']
        lam = res['lambda']
        v_fit = bg['B']*((1 - lam) + lam*res['F_fit'])
        return float(np.sqrt(np.mean((bg['V_norm'] - v_fit)**2)))

    rs = np.array([resid_at(s) for s in grid])
    i = int(np.argmin(rs))
    t0 = float(grid[i])
    # parabolic refine through the grid minimum and its two neighbours
    if refine and 0 < i < len(grid) - 1 and np.all(np.isfinite(rs[i-1:i+2])):
        y0, y1, y2 = rs[i-1], rs[i], rs[i+1]
        denom = y0 - 2*y1 + y2
        if denom > 0:
            t0 = float(grid[i] + 0.5*(y0 - y2)/denom*(grid[1] - grid[0]))
    return t0


# --------------------------------------------------------------------------- #
#  Validation (DeerAnalysis-style ensemble averaging)
# --------------------------------------------------------------------------- #
def _bg_start_grid(t, center, span_frac=0.075, n=9):
    """Default background-start sweep: n points spanning +/- span_frac of the
    trace length around `center`, clipped to a sensible interior window."""
    t = np.asarray(t, float)
    t0, t1 = float(t.min()), float(t.max())
    span = t1 - t0
    if center is None:
        center = t0 + 0.5*span
    half = span_frac*span
    lo = max(center - half, t0 + 0.1*span)
    hi = min(center + half, t1 - 0.05*span)
    if hi <= lo:
        return np.array([float(np.clip(center, t0 + 0.1*span, t1 - 0.05*span))])
    return np.linspace(lo, hi, int(n))


def deer_validate(t, V, r=None, bg_start=None, bg_starts=None, bg_end=None,
                  dim=3.0, fit_dim=False, alpha=None, alpha_factor=1.0,
                  reg_order=2, nu_dd=NU_DD, method='gcv', engine='sequential',
                  noise=0.0, n_noise=0, seed=0, percentiles=(5, 95)):
    """DeerAnalysis-style validation: hold the regularization fixed, re-run the
    inversion over a grid of background-start times (and optionally added-noise
    realizations), collect the ensemble of P(r), and return the consensus P(r)
    with a percentile band. Averaging over the trials suppresses the noise-driven
    spikes a single GCV inversion leaves in P(r), giving a smooth distribution
    plus an honest uncertainty band -- the procedure behind the smooth, banded
    distributions of Fig. 4 in Schiemann et al., JACS 2021 (10.1021/jacs.1c07371).

    `bg_starts` is the explicit sweep of background-start times; when None a
    9-point grid spanning +/- 7.5% of the trace around `bg_start` (or the trace
    midpoint) is used. alpha is selected once on the central trace (honouring
    `alpha`/`alpha_factor`) and then held fixed for every trial -- validation
    probes background/noise sensitivity, not the regularization choice. With
    `noise` > 0 and `n_noise` > 0, each background-start trial is additionally
    repeated with `n_noise` Gaussian-noise realizations of std `noise` added to V
    (estimate `noise` from the trace residual). All trials share the grid `r`.

    Returns a dict: r, P_density (the ensemble *median* -- the robust consensus
    curve, always bracketed by the band), P_mean (ensemble mean, exposed for
    reference), P_lower, P_upper (the `percentiles` band), ensemble
    (n_trials x len(r) densities), n_trials, bg_starts, alpha (the fixed value),
    peak (consensus-curve peak r), r_mean (its first moment), and base = the
    single inversion at the central bg_start (its form factor / fit / residuals
    for display).
    """
    _require_scipy()
    t = np.asarray(t, float)
    V = np.asarray(V, float)
    r = default_r_axis() if r is None else np.asarray(r, float)
    if bg_starts is None:
        bg_starts = _bg_start_grid(t, bg_start)
    bg_starts = np.atleast_1d(np.asarray(bg_starts, float))
    reps = max(int(n_noise), 0) if noise > 0 else 0
    rng = np.random.default_rng(seed)
    dr = float(r[1] - r[0]) if len(r) > 1 else 1.0
    bs_mid = float(bg_starts[len(bg_starts)//2])
    af_mid = float(alpha_factor)

    # Pick alpha ONCE on the central background, then hold it fixed across every
    # trial (DeerAnalysis-style validation tests background-start / noise
    # sensitivity, not the regularization choice). Holding alpha fixed also drops
    # the per-trial L-curve scan -- the costly part -- so validation stays fast.
    base = deer_invert(t, V, r=r, bg_start=bs_mid, bg_end=bg_end, dim=dim,
                       fit_dim=fit_dim, alpha=alpha, alphas=None,
                       reg_order=reg_order, nu_dd=nu_dd, method=method,
                       engine=engine, alpha_factor=af_mid)
    alpha_fixed = float(base['alpha'])

    def _invert(Vx, bs):
        return deer_invert(t, Vx, r=r, bg_start=bs, bg_end=bg_end, dim=dim,
                           fit_dim=fit_dim, alpha=alpha_fixed, scan_lcurve=False,
                           reg_order=reg_order, nu_dd=nu_dd, method=method,
                           engine=engine)

    ensemble = []
    for bs in bg_starts:
        trials = [V] + [V + noise*rng.standard_normal(V.shape)
                        for _ in range(reps)]
        for Vx in trials:
            try:
                ensemble.append(_invert(Vx, bs)['P_density'])
            except Exception:
                continue
    if not ensemble:
        raise RuntimeError('DEER validation produced no successful trials.')
    ens = np.vstack(ensemble)
    P_mean = ens.mean(axis=0)
    P_median = np.median(ens, axis=0)
    lo, hi = percentiles
    P_lower = np.percentile(ens, lo, axis=0)
    P_upper = np.percentile(ens, hi, axis=0)
    P_mass = _normalize_masses(P_median*dr)
    return {'r': r, 'P_density': P_median, 'P_mean': P_mean,
            'P_lower': P_lower, 'P_upper': P_upper, 'ensemble': ens,
            'n_trials': ens.shape[0], 'bg_starts': bg_starts,
            'alpha': alpha_fixed,
            'peak': float(r[int(np.argmax(P_median))]),
            'r_mean': float(np.sum(r*P_mass)), 'base': base,
            'percentiles': tuple(percentiles), 'engine': engine}


def simulate(t, r, P, lam=0.3, k=0.05, dim=3.0, nu_dd=NU_DD, noise=0.0, seed=None):
    """Forward-simulate a DEER trace from a distance distribution P(r).

    V(t) = [(1 - lam) + lam * (K P_masses)] * exp(-(k|t|)^(d/3)) (+ Gaussian
    noise). `t` in us, `r` in nm. Returns V(t) with V(0) = 1 (noise aside).
    """
    _require_scipy()
    t = np.asarray(t, float)
    r = np.asarray(r, float)
    Pn = _normalize_masses(np.asarray(P, float))
    form = dipolar_kernel(t, r, nu_dd=nu_dd)@Pn
    B = np.exp(-(k*np.abs(t))**(dim/3.0))
    V = ((1 - lam) + lam*form)*B
    if noise > 0:
        rng = np.random.default_rng(seed)
        V = V + noise*rng.standard_normal(V.shape)
    return V


# --------------------------------------------------------------------------- #
#  Headless self-test: synthetic round-trip
# --------------------------------------------------------------------------- #
if __name__ == '__main__':
    if not SCIPY_AVAILABLE:
        raise SystemExit('scipy not available; install with pip install -e .[math]')
    r = default_r_axis(2.0, 6.0, 200)
    r0, sig = 3.5, 0.25
    P_true = np.exp(-0.5*((r - r0)/sig)**2)             # density (un-normalized)
    t = np.linspace(0.0, 2.5, 256)                      # us
    V = simulate(t, r, P_true, lam=0.35, k=0.10, dim=3.0, noise=0.01, seed=1)

    res = deer_invert(t, V, r=r, bg_start=1.0)
    F, Ff = res['form_factor'], res['F_fit']
    ss_res = float(np.sum((F - Ff)**2))
    ss_tot = float(np.sum((F - F.mean())**2))
    r2 = 1 - ss_res/ss_tot
    r_peak = r[int(np.argmax(res['P_density']))]
    # first moment of the recovered distribution
    r_mean = float(np.sum(res['r']*res['P_norm']))

    print(f'recovered lambda = {res["lambda"]:.3f}  (true 0.350)')
    print(f'recovered k      = {res["k"]:.3f}  (true 0.100)')
    print(f'alpha (L-corner) = {res["alpha"]:.4g}')
    print(f'form-factor fit R^2 = {r2:.4f}')
    print(f'P(r) peak  = {r_peak:.3f} nm  (true {r0:.3f})')
    print(f'P(r) mean  = {r_mean:.3f} nm')
    ok = (abs(r_peak - r0) < 0.3) and (r2 > 0.95) and (abs(res['lambda'] - 0.35) < 0.1)

    # alpha_factor: heavier regularization must smooth (lower roughness ||L P||)
    Lr = regularization_matrix(len(r), 2)
    res_h = deer_invert(t, V, r=r, bg_start=1.0, alpha_factor=4.0)
    rough = lambda d: float(np.linalg.norm(Lr@d['P_norm']))
    print(f'alpha x1 = {res["alpha"]:.4g}  roughness {rough(res):.4g}')
    print(f'alpha x4 = {res_h["alpha"]:.4g}  roughness {rough(res_h):.4g}')
    smoother = (res_h['alpha'] > res['alpha']) and (rough(res_h) < rough(res))

    # validation ensemble: smooth mean curve + band that brackets it
    val = deer_validate(t, V, r=r, bg_start=1.0, noise=0.01, n_noise=3, seed=2)
    band_ok = (np.all(val['P_lower'] <= val['P_density'] + 1e-12) and
               np.all(val['P_density'] <= val['P_upper'] + 1e-12))
    print(f'validation: {val["n_trials"]} trials, peak {val["peak"]:.3f} nm, '
          f'mean {val["r_mean"]:.3f} nm, band_ok {band_ok}')
    print('SELF-TEST:', 'PASS' if (ok and smoother and band_ok and
          abs(val['peak'] - r0) < 0.3) else 'FAIL')
