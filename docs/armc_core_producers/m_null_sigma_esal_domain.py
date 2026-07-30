"""THE NULL in the ESAL domain: a constant-only interval-censored fit, no predictors\nat all. Whatever the replacement beats, it must beat this first.

Self-contained: the LTPP SDR-39 column slice this number needs is embedded below
as a gzip+base64 CSV literal. No network, no other files. Deterministic.
Source table: runs/study-20260730T034915Z-m16/workspace/ltpp_sdr39_segments.csv
(copied read-only; runs/ is append-only evidence and is never written to).
"""
import base64, csv, gzip, io
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

DATA = "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"


def _rows():
    return list(csv.DictReader(io.StringIO(
        gzip.decompress(base64.b64decode(DATA)).decode())))


def _col(rs, k):
    return np.array([np.nan if r[k] == "" else float(r[k]) for r in rs])


def _log10W18(SN, MR, dPSI, ZR=0.0, S0=0.45):
    SN = np.asarray(SN, float); MR = np.asarray(MR, float)
    dPSI = np.asarray(dPSI, float)
    B = 0.40 + 1094.0 / (SN + 1.0) ** 5.19
    return (ZR * S0 + 9.36 * np.log10(SN + 1.0) - 0.20
            + np.log10(dPSI / 2.7) / B + 2.32 * np.log10(MR) - 8.07)


def _bounds(w_lo, w_hi, cens):
    lo = np.where(np.asarray(cens) == "left", -np.inf,
                  np.log10(np.maximum(np.asarray(w_lo, float), 1.0)))
    hi = np.array([np.inf if (c == "right" or not np.isfinite(h)) else np.log10(h)
                   for c, h in zip(cens, np.asarray(w_hi, float))])
    return lo, hi


def _loglik(mu, sigma, lo, hi):
    z_hi = np.where(np.isfinite(hi), (hi - mu) / sigma, np.inf)
    z_lo = np.where(np.isfinite(lo), (lo - mu) / sigma, -np.inf)
    return np.log(np.clip(norm.cdf(z_hi) - norm.cdf(z_lo), 1e-300, None))


def _fit_aft(X, lo, hi, fix_beta=None):
    if fix_beta is not None:
        mu = np.asarray(X, float)
        r = minimize(lambda p: -_loglik(mu, np.exp(p[0]), lo, hi).sum(),
                     [np.log(0.5)], method="Nelder-Mead",
                     options=dict(xatol=1e-10, fatol=1e-10, maxiter=20000))
        return None, float(np.exp(r.x[0]))
    k = X.shape[1]
    mid = np.where(np.isfinite(hi), hi, lo)
    beta0, *_ = np.linalg.lstsq(X, mid, rcond=None)
    p0 = np.concatenate([beta0, [np.log(0.5)]])
    f = lambda p: -_loglik(X @ p[:k], np.exp(p[k]), lo, hi).sum()
    r = minimize(f, p0, method="Nelder-Mead",
                 options=dict(maxiter=200000, maxfev=200000, xatol=1e-9, fatol=1e-9))
    r = minimize(f, r.x, method="Nelder-Mead",
                 options=dict(maxiter=200000, maxfev=200000, xatol=1e-10, fatol=1e-10))
    return r.x[:k], float(np.exp(r.x[k]))


def _ols(X, y):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b


def _cv_sd(X, y, seed=7, K=10):
    """10-fold held-out-SECTION CV residual sd. Deterministic: fixed seed."""
    n = len(y)
    o = np.random.default_rng(seed).permutation(n)
    res = []
    for i in range(K):
        te = np.zeros(n, bool); te[o[i::K]] = True
        res.append(y[te] - X[te] @ _ols(X[~te], y[~te]))
    return float(np.std(np.concatenate(res), ddof=1))


metrics = {}

rs = _rows()
lo, hi = _bounds(_col(rs, "w_lo"), _col(rs, "w_hi"), [r["cens"] for r in rs])
_beta, sigma = _fit_aft(np.ones((len(rs), 1)), lo, hi)
metrics["null_constant_only_sigma_esal_domain"] = round(sigma, 4)
print(metrics)
