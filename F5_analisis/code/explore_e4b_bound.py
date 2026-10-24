"""EXPLORATORY, analysis plan v2 §6.5: CBWFQ on the c7200 (E4(b), 1 Mbit/s, k = 1 and 3) against the RFC 2212 bound 2*T_r + T_s,
with the same method as E4(a) in confirm.py (median of the per-run ratio measured/bound, 95 % bootstrap CI, same seed and B),
next to the IOU ratios of E4a.csv and the bound constants quoted in the paper.
Output: results/E4b_cota.csv, results/numbers_e4b.json"""
import csv, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C, stats_lib as S
RES = os.path.join(HERE, "..", "results")
B = 10000
Ts = lambda L: 1514 * 8 / L * 1e3                       # ms
Tr = lambda m, calls=1: 214 * 8 / (calls * 85.6e3 * (1 + m)) * 1e3   # ms
bound = lambda L, m: 2 * Tr(m) + Ts(L)

main = C.prep([r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"])
out = []
for k in ("1", "3"):
    cid = f"E4b_C7200_CBWFQ_L1000k_k{k}_m0.2_c1_f1514"
    p = np.array([r["p99f"] for r in main if r["cell"] == cid])
    assert len(p) == 17, (cid, len(p))
    b = bound(1000000, 0.2)
    out.append(dict(cell=cid, platform="C7200", k=int(k), n=len(p), p99_median=float(np.median(p)), bound_ms=b,
                    ratio_median=float(np.median(p / b)), ratio_ci95=S.boot_ci(p / b, B=B, seed=C.SEED_CELL)))
iou = {r["cell"]: r for r in csv.DictReader(open(os.path.join(RES, "E4a.csv")))}
for k in ("1", "2", "3"):
    r = iou[f"E1_IOU_CBWFQ_L1000k_k{k}_m0.2_c1_f1514"]
    lo, hi = (float(x) for x in r["ratio_main_ci95"].strip("()").split(","))
    out.append(dict(cell=r["cell"], platform="IOU", k=int(k), n=17, p99_median=None, bound_ms=float(r["bound_main_ms"]),
                    ratio_median=float(r["ratio_main"]), ratio_ci95=(lo, hi)))
with open(os.path.join(RES, "E4b_cota.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
nums = dict(E4b_bound=out, bound_constants_ms=dict(two_T_r_m02=2 * Tr(0.2), bound_L500k=bound(500000, 0.2), bound_L1000k=bound(1000000, 0.2),
                                                   bound_L5000k=bound(5000000, 0.2)))
json.dump(nums, open(os.path.join(RES, "numbers_e4b.json"), "w"), indent=1)
print("EXPLORATORY E4(b): CBWFQ p99 / (2*T_r + T_s), 1 Mbit/s, m = 0.2, one call; median of per-run ratio [95 % bootstrap CI]")
for r in out:
    print(f"  {r['platform']:5s} k={r['k']}  bound {r['bound_ms']:.2f} ms  ratio {r['ratio_median']:.3f} [{r['ratio_ci95'][0]:.3f}, {r['ratio_ci95'][1]:.3f}]"
          + (f"  p99 median {r['p99_median']:.2f} ms" if r["p99_median"] is not None else ""))
print("  bound constants (ms):", {k: round(v, 2) for k, v in nums["bound_constants_ms"].items()})
