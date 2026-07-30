"""THE NULL in the YEARS domain - the domain the paper's headline rule and its\nsigma = 0.3585 live in. A constant-only fit, no predictors at all.

Self-contained: the LTPP SDR-39 column slice this number needs is embedded below
as a gzip+base64 CSV literal. No network, no other files. Deterministic.
Source table: runs/study-20260730T034915Z-m16/workspace/ltpp_sdr39_segments.csv
(copied read-only; runs/ is append-only evidence and is never written to).
"""
import base64, csv, gzip, io
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

DATA = "H4sIAAAAAAAC/8VX0aodNwx8z7csxpIlS/qaUMJtc+GSQnrp93fsPWctb0hIoLQvufGx15almdH4/ePbn8f7x8+vx6eXL399IC5kysfx9fWPz+8folSWfkQJUjpev7y/fP37t7f7qtuwFzWz70z+2rAVCqNrWItqs4MIf7umeKRUaf5cZ0VJrgC4F3du1yZUqPZrLWNP7vIcemEZJ9RS3fo6wUunbmvVPprR/PJoRBIRa9K4GnLdnWXLtVeXg3pp1dqa0CIWV24Q8EFRpHE/3l5+fx85aY4gCetaS98xFevkKcfYJw9bk5Q7YeppyBQH+1mltaWWjsOuZVzEWQ9uyNN+FaltldNK7/VKR2vFTPV2oZmweaH5gxXv2OG84QhuFXbMN0aSiM95xv6yKo10t0hFQzLj8BNR6yY4QHkB0LFfu0qEe2rYKqACLfWaHRlXooTlYPc0W3vlHK2VquLpdhUBC60fgFx+LkDS69ocqY0mLUfigDxSYuKJqSwndZ+fWeHqtJhaY9UDVOiRal83eJ7xBH668CXS28AX4JSOFHCYNQ5RBJxzCwCbOm49CXf93BC6yiGAOUfa5hw/Tt9HtnF2ps6BcreVOiTEoj1CHTgkThdLmUTKui1cALtLuwZVmmxsSFQB2JgpFxjYkEk4Nl83mcBEpjWXuhUnfaTSzv8Da+637wbg6Ql4BC7W+oGwNHrKFXbTANMQggfrxrgWgDP+AuZJBAC10GpJWQdTn/K7lhHSuigKNBGB13p+nI+pUdu4FRC/fw9B0rExahzbF90t0sZRe2yaBNlBKkFZyzI8+xHC9e59u455yz1HGyozCu+5cYFE5kBOI0C99gzC8HYJ2L8zArK8ak/6luk19IAyiFkhrbgH5QIKhFUTC352NBqYhSR9QLo38Zm5DfsGWaAR3TAI1ZdIsoRPSd0vcm1IansckPyVkcm8deeBYxHPIGigF2gW2jlXXajluygtDRuqWwcmIGZskvtjFSgANoOoJqhAAqH5x7hyyxAKcKdxOmUqabIJOVQs5tUIQLu+XItBQUxPMm1kRChh82Rm452+dVVncJM7pbTMSIZ2s+jWyHMQgxS8QnyoItmjTlFMU68CNqOnThzadETW0C7SEY8fVjU7cJRRNVi0nzhrd0JjiHC+xyTvisCaZec3OzfKSZqZ2U8ndmWaQ+2/G9GPh3qCC/mrfVfX6eUgf1NurgkrDRUM/Mu8LZ+m42lNN/YNnLr0xD4++8xJXDjkujAASGTojOV+atIDA6fJGMqbazyLivo4RdvEcjbwJKqy8cHb/EhaFnY46M4+rNu8095x+rzkRO3WCjj13OFbF6iGIaPek4n7xiQWXOfhEUGVCqXqd+bVyYPRoeWWXiC/PlVwiNUALPiILhgbcwXdC5c29NntspCY5WARXJgkkZC+UgYVDfg/v70sEJRWuZuZYVDOAg+tXRXFEdlFDtFLssPDRExznxGnLUkTyXKD/+9oWBvf3olT/UdfjPy489HLCaQBnCJ3bKWV3IGL5Q+xtXVb7hiFiLp824ABa0JY4FGRrVCt3x2iZfWY4t4zU4dsDdM7IKYeG/QyiUB9VPuWkEGZSptriiqcwq/7E1nwQARIq248shNgQ/ShL2sCyl93t4zg0TM3N6pKT41w3oxCnC+NOdnibBQLfiHZADsemtP2+N5xwUqfXnbXirqROaa5TC3J09uYGCiOwk315k5qErjHDx7PpwAEkQggg61n2tq9nwYJyZ0vomviH1fzOPcREQAA"


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
_beta, sigma = _fit_aft(np.ones((len(rs), 1)), lo, hi)
metrics["null_constant_only_sigma_years_domain"] = round(sigma, 4)
print(metrics)
