"""AASHTO-93's residual sigma from the interval-censored likelihood for life to a\n1.0-PSI serviceability loss, face-value measured Mr. m16 reported 1.4624.

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
mu = _log10W18(_col(rs, "SN"), _col(rs, "mr_face_psi"), 1.0)
_, sigma = _fit_aft(mu, lo, hi, fix_beta=np.array([1.0]))
metrics["incumbent_sigma_interval_censored_dpsi1"] = round(sigma, 4)
print(metrics)
