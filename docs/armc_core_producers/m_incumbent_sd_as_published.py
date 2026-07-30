"""AASHTO-93 exactly as published (zero fitted parameters) in the observed-dPSI ESAL\ndomain: the residual sd of log10(predicted/observed). Its median bias travels too,\nsince a pure shift does not change an sd and the two must not be conflated.

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
mu = np.asarray(_log10W18(_col(rs, "SN"), _col(rs, "mr_face_psi"),
                          _col(rs, "dpsi_last")), float)
r = mu - np.log10(_col(rs, "w_last"))
metrics["incumbent_sd_as_published"] = round(float(np.std(r, ddof=1)), 4)
metrics["incumbent_median_bias_log10"] = round(float(np.median(r)), 4)
print(metrics)
