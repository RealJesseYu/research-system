"""THE DECISIVE COMPARATOR: the same 10-fold held-out-section CV, for a model with\nNO PREDICTORS - it fits one constant and predicts it. Anything the replacement's\nstructure is worth has to show up as a gap between this and the number above.

Self-contained: the LTPP SDR-39 column slice this number needs is embedded below
as a gzip+base64 CSV literal. No network, no other files. Deterministic.
Source table: runs/study-20260730T034915Z-m16/workspace/ltpp_sdr39_segments.csv
(copied read-only; runs/ is append-only evidence and is never written to).
"""
import base64, csv, gzip, io
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

DATA = "H4sIAAAAAAAC/12XzY4kuQ2E7/ssiYL4J4pPYxjYiwEfDOwC+/r+SGV7p9wYTHeqUhIZjAiyfv/PH//6x7//+cefz1/z6zf52I7z8N/StI+wsLbII7rNZX3yt/UJVh7JWr7t4yzYkmdr7GI3j9siHq88PxvMNZ88Vtvqs1nwFf7IMTXNj3JH2LbnbFHL+hRvnFJ7zE4ciU/MltULwTVJWCzIiq+FKPleIAniPBwla08qkiaPn/Dy4Br9mJxHREorJzCTvR9ZVUT/OezgTXKvKBM2kJ8YO6xAh+R10FB94hjp6SzkBg7zJOD30HB/iD9SzmdNcrIfFTGWSI5bCOGxslhLJ/Rz1n52GkdxhH6WHuI6e7HlxZQbHtWs1DOol1s9WcfsVqG2GFti2VSBcyjIo+aunoNGUIQguZUT95Zd5HpWpbOBQOQIRalDQSfunX1khkfdokQAOUis7XLjTq/HCbIM+IgyM56zRNfyocpZCeDEts+ljrHhOL9igozacAcyHRn8wwhalu5znLTIogvk3LfO3JB9o4T68ZoTy0FfNkTqG+SjGvrA6bQ1uKR1BRf8PfsCJY1LZVLVOdL37jRzydFZ4OjHiASC1z3zmD+Q5HDm5hlk0cwSoYA1K6tMWYFvNnnoTuKuLD0+iTZ/CGMf1TVxeyPzyzOVO187oIQDlRPHUFEdeu9DMc6tn8O7KuhdwxDfHMBxsGiKtdEX9d9s2ZdCebJ1ulHdvAGF4JSsBIuRpRacMoCo2oN+UaonVmIJ8wLSUnb4spNEDWewiUfJe7sPyVTaLOZnz5aUZrIH+c0LB2TnhTR9gTj6OE/E3dBxez7N7hMjp4JPj8I8NDjVcHT1TFoIpTVqki1afiZotQZqrR/OVcIIYA3e7wNhNXI8Wi/FeL0jQnLrkhLZETOBlw9wxYfPwSP0VuLs5iByNYfmI2iKa1SKo6c2pp21S0D8kZKndrnZFHKrg8MSNKawd7xExUZzUdUzZ4oFnmANzzVAr/r1efcdvzznSvl6X/3rfeMCtGmieh12F7i3GmrNC7hi1/JgeTpAYwg4rEYC9gBDhqfViJ7XIFElcFR97XVrtSkNSgLtURI6nWKnc+lAaa2Lhao9YtLcdoXRvNbXZVoafA61B5kw3w9uSh8asakSRuwwmyBcYe3fj1A0//dI2nSUBy5B69uLCv8uarf9wtI+urEd/l3Xw37gOK+te/3mPIrNNXwOMkdheED4WgPTkkg6aAKOzoYzGXEixLkdFCq2nbMnJoPotkKLOD8ehLMUzpoLLIdB9EN6aLr7GlVIseG0Xd8jSx2l4hHmAxqvYs3HUofT3X2oJRFctkGyXx4zwQAebHltmL+nzdH5brvZyyEHzeQFxXoGwCpUu1MO/QJnRgHqfslCe8YXXNfAHkK/EkTTdZj3aTPfC3SWrwVX+V6gd/UMAFtuKQHU/35uHvD5geCUdk3Hs+5GOKvdMYPKwAzQh311UWmXpqtS2jaj3YwHNfhwe0N0bdM7iNvcFerZ7rSvFzBvAMzSS6c2I9xJFj9hFwc9bQ5MS+eOEDRDoKNJgtA1vPCLPk3qqqYdb3dLut0GI2sCVsSbBu4B4xaczdttcI92ci29Xk/P7yiQTN3pYOckGnk99HiimANBL1LeExo6xmbnBjFqQePEc17v6f3Ws+HluPcII0lXE58QZHV9TbfbbQ109B5Q1kbigxSU1m4NdY5NEAwkhwUEnzH1TLdWmvVs+fZVnJxy/IxWhIll4cuSiIA1egB2stsqr7iZIAHiUCaZO2KwA7g7rk0zAFv3PUd0/Zi0lDj9VZ61hcG8+ulHpB3fCyn1teCBnL8WmC2+FpiQ7GuBQeH/DmW++D6jyf29ALurJfgWDcn34ILbxbm8gClUnZbi/hMHGms4w9/WVwRW3aquxGgph8lcr/fhqfAKf9d1WyMS7O8C0KouT4qZkSodtXultJGcLBh/Z91qg1/gz1RZoyC6Su2eW2aDzwS422AvLZiT0SQzIUlcVuAskYj6kh1daD/fbg0nuJDbmLev7wSNvINmzn+nWgTJpr1U3iGm56LVs9UNqUcBduCVqDxmBOkpP6N+xu+UZvdi5gxfd2SH1/gtlSdsm68SmJMDdNkdjcT7GwtzHh3z+tmq6Hkr/CUnPah5QwNiOm6XxQLYQoUZNjkDp2bae/i2UKQ/45SNqhiisdXRXTL40BeYAc8dLJnhYBbTpkrj91+EDY3Y0Q0AAA=="


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
y = np.log10(_col(rs, "w_last"))
X = np.ones((len(rs), 1))
metrics["null_cv_sd_heldout_section"] = round(_cv_sd(X, y), 4)
print(metrics)
