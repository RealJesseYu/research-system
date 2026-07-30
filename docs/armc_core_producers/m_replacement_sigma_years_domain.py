"""The replacement's own regressors in the YEARS domain, against the null above.\nThe paper reports sigma = 0.3585 here and calls it a fitted replacement for S0.

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
lo, hi = _bounds(_col(rs, "t_lo"), _col(rs, "t_hi"), [r["cens"] for r in rs])
SN, MR = _col(rs, "SN"), _col(rs, "mr_face_psi")
X = np.column_stack([np.ones(len(rs)), np.log10(SN + 1.0), np.log10(MR)])
_beta, sigma = _fit_aft(X, lo, hi)
metrics["replacement_sigma_years_domain"] = round(sigma, 4)
print(metrics)
