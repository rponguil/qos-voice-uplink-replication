"""Statistics used by validation and confirmatory analysis (analysis plan v2). All tests on paired differences."""
import itertools, math
import numpy as np
from scipy import stats

_SIGNS = {}


def _signs(n):
    if n not in _SIGNS:
        _SIGNS[n] = np.array(list(itertools.product((1.0, -1.0), repeat=n)))   # 2^n x n, exact enumeration
    return _SIGNS[n]


def signperm_exact(d, alternative="greater"):
    """Exact sign-permutation test on the mean of paired differences d (all 2^n sign patterns)."""
    d = np.asarray(d, float); n = len(d)
    if n > 20:
        raise ValueError("exact enumeration limited to n <= 20")
    means = _signs(n) @ d / n; obs = d.mean(); eps = 1e-12
    if alternative == "greater":
        return float(np.mean(means >= obs - eps))
    if alternative == "less":
        return float(np.mean(means <= obs + eps))
    return float(np.mean(np.abs(means) >= abs(obs) - eps))


def wilcoxon(d, alternative="greater"):
    d = np.asarray(d, float)
    if np.all(d == 0):
        return 1.0
    return float(stats.wilcoxon(d, alternative=alternative, zero_method="wilcox").pvalue)


def tost_paired(d, low, high):
    """Paired TOST with exact t: H0 mean <= low or mean >= high. p = max of the two one-sided p."""
    d = np.asarray(d, float); n = len(d); m = d.mean(); se = d.std(ddof=1) / math.sqrt(n)
    if se == 0:
        return {"p": 0.0 if low < m < high else 1.0, "mean": m, "p_low": None, "p_high": None}
    t_low = (m - low) / se; t_high = (m - high) / se
    p_low = 1 - stats.t.cdf(t_low, n - 1); p_high = stats.t.cdf(t_high, n - 1)
    return {"p": float(max(p_low, p_high)), "mean": float(m), "p_low": float(p_low), "p_high": float(p_high),
            "ci90": (float(m - stats.t.ppf(.95, n - 1) * se), float(m + stats.t.ppf(.95, n - 1) * se))}


def mean_ci(d, level=0.95):
    d = np.asarray(d, float); n = len(d); m = d.mean(); se = d.std(ddof=1) / math.sqrt(n); q = stats.t.ppf(.5 + level / 2, n - 1)
    return float(m - q * se), float(m + q * se)


def boot_ci(x, stat=np.median, B=10000, seed=0, level=0.95):
    x = np.asarray(x, float); rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(B, len(x)))
    bs = np.apply_along_axis(stat, 1, x[idx]) if stat is not np.median else np.median(x[idx], axis=1)
    a = (1 - level) / 2
    return float(np.quantile(bs, a)), float(np.quantile(bs, 1 - a))


def cliff_delta(x, y):
    x = np.asarray(x, float)[:, None]; y = np.asarray(y, float)[None, :]
    return float((np.sum(x > y) - np.sum(x < y)) / (x.size * y.size))


def holm(pvals):
    """Holm step-down adjusted p-values (same order as input)."""
    p = np.asarray(pvals, float); m = len(p); order = np.argsort(p); adj = np.empty(m); run = 0.0
    for i, j in enumerate(order):
        run = max(run, (m - i) * p[j]); adj[j] = min(1.0, run)
    return adj.tolist()


def ols(X, y):
    X = np.asarray(X, float); y = np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta
