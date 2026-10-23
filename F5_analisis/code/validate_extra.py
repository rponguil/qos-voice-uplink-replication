"""Extra validation (after VALIDACION.txt): (a) TOST on true-zero paired data with known SD; (b) coverage of both H3 CIs
over 200 synthetic realizations; (c) SE of the mean-of-shuffled-d check. Appends to results/VALIDACION.txt"""
import os, sys, csv
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import stats_lib as S
RES = os.path.join(HERE, "..", "results"); out = []; P = out.append
rng = np.random.default_rng(20261025)
P("\n4. EXTRA CHECKS (seed 20261025)")
# (a) TOST power with true difference 0, SD 2.03, n 17, margin 2.00 -> expected ~0.83 (P3b), and size at the margin
eq = np.mean([S.tost_paired(rng.normal(0, 2.03, 17), -2.0, 2.0)["p"] < 0.01 for _ in range(4000)])
eq05 = np.mean([S.tost_paired(rng.normal(0, 2.03, 17), -2.0, 2.0)["p"] < 0.05 for _ in range(4000)])
size = np.mean([S.tost_paired(rng.normal(2.0, 2.03, 17), -2.0, 2.0)["p"] < 0.05 for _ in range(4000)])
P(f"  (a) TOST, true d=0, SD 2.03, n=17, margin +-2: equivalence at alpha 0.01 {eq:.3f} (P3b power 0.831); at 0.05 {eq05:.3f}; "
  f"true d = margin: rejection rate {size:.3f} (should be <= 0.05)")
# (c) shuffled-d mean: SE over 200 shuffles
rows = [r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"]
by = {}
for r in rows:
    if r["exp"] == "E1" and r["platform"] == "IOU" and r["k"] == "3" and r["policy"] in ("CBWFQ", "LLQ"):
        by.setdefault(r["L"], {})[(r["policy"], r["rep"])] = float(r["p99"])
for L in sorted(by, key=int):
    d = np.array([by[L][("CBWFQ", str(i))] - by[L][("LLQ", str(i))] for i in range(1, 18)])
    se = np.sqrt(np.mean(d ** 2)) / np.sqrt(17) / np.sqrt(200)
    P(f"  (c) L={int(L)//1000}k: |d| rms {np.sqrt(np.mean(d**2)):.1f} ms -> SE of the mean over 200 shuffles {se:.2f} ms "
      f"(shuffled d has spread ~|d|, so TOST +-EMI cannot declare equivalence: the expectation 'high' does not apply here)")
# (b) coverage of H3 CIs, 200 realizations, 500 bootstrap each
cells = sorted({(int(r["L"]), float(r["m"])) for r in rows if r["platform"] == "IOU" and r["k"] == "3" and r["policy"] == "CBWFQ"
                and ((r["exp"] == "E1" and float(r["m"]) == 0.2) or r["exp"] == "E1R")})
for aa, bb, lab in ((1.0, 2.0, "p99 CBWFQ"), (0.0, 2.0, "Delta")):
    cov = {"within": [0, 0], "cluster": [0, 0]}
    for rep in range(200):
        X, y, g = [], [], []
        for ci, (L, m) in enumerate(cells):
            Ts = 1514 * 8 / L * 1000; Tr = 214 * 8 / (85.6e3 * (1 + m)) * 1000
            for _ in range(17):
                X.append([Ts, Tr, 1.0]); y.append(aa * Ts + bb * Tr + 1.0 + rng.normal(0, 1.3)); g.append(ci)
        X, y, g = np.array(X), np.array(y), np.array(g); grp = [np.where(g == c)[0] for c in range(len(cells))]
        bw, bc = [], []
        for _ in range(500):
            idx = np.concatenate([rng.choice(ix, len(ix)) for ix in grp]); bw.append(S.ols(X[idx], y[idx]))
            cc = rng.integers(0, len(cells), len(cells)); idx = np.concatenate([grp[c] for c in cc]); bc.append(S.ols(X[idx], y[idx]))
        for name, bs in (("within", bw), ("cluster", bc)):
            q = np.quantile(bs, [.025, .975], axis=0)
            cov[name][0] += q[0, 0] <= aa <= q[1, 0]; cov[name][1] += q[0, 1] <= bb <= q[1, 1]
    P(f"  (b) H3 {lab}: coverage of the 95 % CI over 200 realizations: within-cell a {cov['within'][0]/200:.3f} b {cov['within'][1]/200:.3f} | "
      f"cluster a {cov['cluster'][0]/200:.3f} b {cov['cluster'][1]/200:.3f}")
open(os.path.join(RES, "VALIDACION.txt"), "a").write("\n".join(out) + "\n"); print("\n".join(out))
