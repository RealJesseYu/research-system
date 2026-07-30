"""The structural elasticity identified WITHIN LTPP SPS projects (project fixed\neffects, where thickness was varied experimentally). The paper reports 4.98 (m16),\n3.654 (m12) and 0.4711 (m15) for this.

Self-contained: the LTPP SDR-39 column slice this number needs is embedded below
as a gzip+base64 CSV literal. No network, no other files. Deterministic.
Source table: runs/study-20260730T034915Z-m16/workspace/ltpp_sdr39_segments.csv
(copied read-only; runs/ is append-only evidence and is never written to).
"""
import base64, csv, gzip, io
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

DATA = "H4sIAAAAAAAC/32VTW7bQAyF9znLZDD8HfIS3fQAQREYjYsgCewgvX6fLVkWUDAbwdBHvhnykfLPH+38cX76OL3/OTx/tr9Pr+94vBzb8+Ht/KBdnBs9DmrqKjFHH62djr9fPh+kG8fChOckuTBxGzylUzu+fR5OX79eoTE8Cg3vPr3Un7IyljE8qcuNWTetNUdqwZDnXjLiKo97hje91iphQRC6MUUNXLJJN2RsPtGYDRFpySZ5wdCWOs0hyeMCyaYpLLFGOZMDkndLouuINdB5mMCHRrCJeXS9x+X1jqvghtfTsvsm8h+0HmjKCrcL3EvA5MgClczJ9zaEaw15eA3FSqhdcaECoh9ZnomfA3AZ9DmDMYao18J67ltK6MYS5YL28t2X6IO0YN6jzCPC0RXkHon7PCKAYLReHHTs3t4/vFRfg2xo4uaervsQ6kZ805lsaCJsU7k0YAvCPg+MuC9BaVh9BAk20vaHBfq0BN3gfc0jmsa1v5EQkH0HZlYsOptUEOWoVtCwJlFD1FyyYTWLMk9x1XmFcEyGu2A8tjy1KJh3xnDY8p3DDmmOHrvpkA2S5RS+7xg2f1bMO6H8Eo6p30GvID5tw7/JrM9EZpYQNktdJYaxVk38P5ldd9Mt2XO/uJIl/AdWaGxl+AYAAA=="


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
projs = sorted({r["sps_project"] for r in rs})
P = np.zeros((len(rs), len(projs)))
for i, r in enumerate(rs):
    P[i, projs.index(r["sps_project"])] = 1.0
X = np.column_stack([P, np.log10(_col(rs, "SN") + 1.0)])
b, _sigma = _fit_aft(X, lo, hi)
metrics["b_sn_within_sps_project"] = round(float(b[len(projs)]), 4)
metrics["n_projects"] = len(projs)
print(metrics)
