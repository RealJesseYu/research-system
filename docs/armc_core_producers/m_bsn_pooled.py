"""The pooled structural elasticity d log10(life) / d log10(SN+1) against the Guide's\n9.36. The paper reports 0.3215 (m15), 1.61 (m16) and -0.532 (m12) for this.

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
SN, MR = _col(rs, "SN"), _col(rs, "mr_face_psi")
DP, y = _col(rs, "dpsi_last"), np.log10(_col(rs, "w_last"))
X = np.column_stack([np.ones(len(rs)), np.log10(SN + 1.0), np.log10(MR),
                     np.log10(DP / 2.7)])
b = _ols(X, y)
# cluster-robust (CR1) SE by state, exactly as the shipped kernel computes it
u = y - X @ b
XtXi = np.linalg.pinv(X.T @ X)
gs = np.array([r["state"] for r in rs])
meat = np.zeros((X.shape[1], X.shape[1]))
for g in np.unique(gs):
    m = gs == g
    s = X[m].T @ u[m]
    meat += np.outer(s, s)
G, n, k = len(np.unique(gs)), len(y), X.shape[1]
V = (G / (G - 1.0)) * ((n - 1.0) / (n - k)) * XtXi @ meat @ XtXi
metrics["b_sn_pooled"] = round(float(b[1]), 4)
metrics["b_sn_pooled_cluster_se"] = round(float(np.sqrt(np.diag(V))[1]), 4)
print(metrics)
