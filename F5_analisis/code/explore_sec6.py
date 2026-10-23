"""EXPLORATORY, analysis plan v2 §6 (+ §5.8 MOS sensitivity): L*, m*, rho and D_sin, FIFO-C vs FIFO-L, E4(b), E4(d), MOS.
Output: results/EXPLORATORIO_SEC6.txt, results/expl_mos_celdas.csv, results/expl_mos_sens.csv"""
import csv, math, os, sys
from collections import defaultdict
import numpy as np
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C, load_runs as LR
RES = os.path.join(HERE, "..", "results"); CAMP = LR.CAMP
out = []; P = out.append
P("EXPLORATORY ANALYSIS (analysis plan v2 §6) — not confirmatory. Tables only. Times in ms.")
main = C.prep([r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"])
cells = defaultdict(list)
for r in main:
    cells[r["cell"]].append(r)
arr = lambda cid: np.array([x["p99f"] for x in cells[cid]])
floor = {}
for r in main:
    if r["floor"] == "True":
        floor.setdefault((r["platform"], r["Li"]), []).append(r["p99f"])
floor = {k: float(np.median(v)) for k, v in floor.items()}
LS = (500000, 1000000, 2000000, 3000000, 5000000); BUD = (20.0, 50.0, 100.0)


def boot_med(x, B, rng):
    return np.median(x[rng.integers(0, len(x), (B, len(x)))], axis=1)


def crossing(xs, ys, b, logf):
    """First x where y drops to/below b (y decreasing along x), interpolated in logf(x); None if never; 'below' if already at x0."""
    if ys[0] <= b:
        return "below"
    for i in range(1, len(xs)):
        if ys[i] <= b:
            f0, f1 = logf(xs[i - 1]), logf(xs[i]); t = (ys[i - 1] - b) / (ys[i - 1] - ys[i])
            return f0 + t * (f1 - f0)
    return None


# ---------- 1. L* (E1 IOU CBWFQ, per k)
P("\n1. FRONTIER L*: L where the median p99 of CBWFQ (E1, IOU) falls to the budget, interpolated in log L; 95% bootstrap CI (10000, seed 20261020)")
rng = np.random.default_rng(20261020)
for k in ("1", "2", "3"):
    meds = [float(np.median(arr(f"E1_IOU_CBWFQ_L{L//1000}k_k{k}_m0.2_c1_f1514"))) for L in LS]
    P(f"  k={k}: median p99 by L {dict(zip([L//1000 for L in LS], [round(m, 1) for m in meds]))}")
    bs = np.array([boot_med(arr(f"E1_IOU_CBWFQ_L{L//1000}k_k{k}_m0.2_c1_f1514"), 10000, rng) for L in LS])   # 5 x B
    for b in BUD:
        c = crossing(LS, meds, b, math.log)
        if c is None:
            P(f"    budget {b:.0f}: no crossing in 0.5-5 Mbit/s (p99 > budget at every L)")
        elif c == "below":
            P(f"    budget {b:.0f}: already below at 0.5 Mbit/s")
        else:
            cs = [crossing(LS, bs[:, i], b, math.log) for i in range(bs.shape[1])]
            num = [math.exp(x) for x in cs if isinstance(x, float)]
            P(f"    budget {b:.0f}: L* = {math.exp(c)/1e6:.2f} Mbit/s, CI95 [{np.quantile(num, .025)/1e6:.2f}, {np.quantile(num, .975)/1e6:.2f}] "
              f"({len(num)}/{len(cs)} resamples cross)")

# ---------- 2. m*(L) (k=3, IOU CBWFQ, m in {0.2, 0.5, 1, 3})
P("\n2. MINIMUM OVER-RESERVATION m*(L): CBWFQ median p99 (k=3) falls to the budget, interpolated in log(1+m); censored '> 3' if never")
MS = (0.2, 0.5, 1.0, 3.0)
cid = lambda L, m: f"E1_IOU_CBWFQ_L{L//1000}k_k3_m0.2_c1_f1514" if m == 0.2 else f"E1R_IOU_CBWFQ_L{L//1000}k_k3_m{m:g}_c1_f1514"
for L in LS:
    ms = [m for m in MS if cid(L, m) in cells]
    meds = [float(np.median(arr(cid(L, m)))) for m in ms]
    bs = np.array([boot_med(arr(cid(L, m)), 10000, rng) for m in ms])
    txt = []
    for b in BUD:
        c = crossing(ms, meds, b, lambda m: math.log1p(m))
        if c is None:
            txt.append(f"{b:.0f} ms: m* > {ms[-1]:g}")
        elif c == "below":
            txt.append(f"{b:.0f} ms: m* <= 0.2")
        else:
            cs = [crossing(ms, bs[:, i], b, lambda m: math.log1p(m)) for i in range(bs.shape[1])]
            num = [math.expm1(x) for x in cs if isinstance(x, float)]; nn = sum(1 for x in cs if x is None)
            txt.append(f"{b:.0f} ms: m* = {math.expm1(c):.2f} [CI95 {np.quantile(num, .025):.2f}, {np.quantile(num, .975):.2f}; {nn} resamples > {ms[-1]:g}]")
    P(f"  L={L//1000}k  medians {dict(zip(ms, [round(x, 1) for x in meds]))}  |  " + "; ".join(txt))

# ---------- 3. rho and D_sin (negative control complement)
P("\n3. NEGATIVE-CONTROL COMPLEMENT: D_sin = mean paired (CBWFQ - LLQ) unmarked; D_con = same in E1 marked; rho = D_sin / D_con; "
  "95% percentile bootstrap (10000, seed 20261014; reps resampled separately in each cell)")
idx = C.index(main); rng2 = np.random.default_rng(20261014)
for k in ("1", "3"):
    for L in LS:
        gu = list(C.paired(idx, lambda r, L=L, k=k: r["exp"] == "CNEG" and r["k"] == k and r["Li"] == L, C.IOU("CBWFQ"), C.IOU("LLQ")).values())[0]
        gm = list(C.paired(idx, lambda r, L=L, k=k: r["exp"] == "E1" and r["k"] == k and r["Li"] == L, C.IOU("CBWFQ"), C.IOU("LLQ")).values())[0]
        du = np.array([x[1] - x[2] for x in gu]); dm = np.array([x[1] - x[2] for x in gm])
        bu = du[rng2.integers(0, len(du), (10000, len(du)))].mean(1); bm = dm[rng2.integers(0, len(dm), (10000, len(dm)))].mean(1)
        rho = bu / bm
        P(f"  k={k} L={L//1000:>4}k  D_sin {du.mean():+8.3f} [{np.quantile(bu,.025):+.3f},{np.quantile(bu,.975):+.3f}]  D_con {dm.mean():+8.3f}  "
          f"rho {du.mean()/dm.mean():+.4f} [{np.quantile(rho,.025):+.4f},{np.quantile(rho,.975):+.4f}]")

# ---------- 4. FIFO-C vs FIFO-L (paired by block), E1 k in {1, 3}
P("\n4. FIFO-C (IOU) vs FIFO-L (LXR), E1, paired by block: d = p99 FIFO-C - p99 FIFO-L")
for k in ("1", "3"):
    for L in LS:
        g = list(C.paired(idx, lambda r, L=L, k=k: r["exp"] == "E1" and r["k"] == k and r["Li"] == L, C.IOU("FIFO"), ("LXR", "FIFO")).values())[0]
        d = np.array([x[1] - x[2] for x in g]); lo, hi = np.quantile(boot_med(d, 10000, rng), [.025, .975])
        P(f"  k={k} L={L//1000:>4}k  median FIFO-C {np.median([x[1] for x in g]):8.1f}  FIFO-L {np.median([x[2] for x in g]):8.1f}  "
          f"median d {np.median(d):+8.1f} [{lo:+.1f},{hi:+.1f}]")

# ---------- 5. E4(b) c7200 vs IOU at 1 Mbit/s
P("\n5. E4(b): c7200 vs IOU at 1 Mbit/s (difference of medians c7200 - IOU, 95% bootstrap CI; excess over own floor)")
for k in ("1", "3"):
    for pol in ("CBWFQ", "LLQ"):
        a = arr(f"E4b_C7200_{pol}_L1000k_k{k}_m0.2_c1_f1514"); b = arr(f"E1_IOU_{pol}_L1000k_k{k}_m0.2_c1_f1514")
        bs = boot_med(a, 10000, rng) - boot_med(b, 10000, rng)
        P(f"  k={k} {pol:5s} c7200 {np.median(a):7.2f} IOU {np.median(b):7.2f} diff {np.median(a)-np.median(b):+6.2f} [{np.quantile(bs,.025):+.2f},{np.quantile(bs,.975):+.2f}] | "
          f"excess over floor c7200 {np.median(a)-floor[('C7200',1000000)]:6.2f} IOU {np.median(b)-floor[('IOU',1000000)]:6.2f}")
for k in ("1", "3"):
    dc = np.median(arr(f"E4b_C7200_CBWFQ_L1000k_k{k}_m0.2_c1_f1514")) - np.median(arr(f"E4b_C7200_LLQ_L1000k_k{k}_m0.2_c1_f1514"))
    di = np.median(arr(f"E1_IOU_CBWFQ_L1000k_k{k}_m0.2_c1_f1514")) - np.median(arr(f"E1_IOU_LLQ_L1000k_k{k}_m0.2_c1_f1514"))
    P(f"  k={k} median CBWFQ - median LLQ: c7200 {dc:.2f}  IOU {di:.2f}")

# ---------- 6. E4(d)
P("\n6. E4(d): bank values (median over 17 runs) next to the published figures (Q004 hardware; Q005 = same scenario in GNS3; Q034 qualitative)")
fn = lambda x: float(x) if x not in ("", "None") else float("nan")
for sc in ("Q004", "Q034"):
    for pol in ("FIFO", "CBWFQ", "LLQ"):
        cc = [c for c in cells if c.startswith(f"E4d_IOU_{pol}_") and c.endswith(sc)][0]; v = cells[cc]
        gp = np.median([fn(x["gp_res"] if sc == "Q004" else x["gp_data"]) for x in v]) / 1e3
        P(f"  {sc} {pol:5s} probe0 ({'video' if sc == 'Q004' else 'voice'}): p99 {np.median([x['p99f'] for x in v]):8.1f} ms, loss {100*np.median([float(x['loss_w']) for x in v]):5.1f} %; "
          f"FTP goodput {gp:6.1f} kbit/s")
P("  published: Q004 (hardware) LLQ -> FTP 0 kbit/s, video loss 8 %; Q005 (GNS3, same scenario) LLQ -> FTP 209 kbit/s, video loss 48 %; "
  "Q034 (hardware, 480 kbit/s): CBWFQ vs LLQ differences described as small (no figure). Source: Luca et al. (2016).")

# ---------- 7. MOS (G.107 / G.113), main case + §5.8 sensitivity
P("\n7. MOS (E-model G.107, G.711 per G.113; protocol §9). Main case: B = 60 ms, T_resto = 100 ms, Bpl = 4.3")


def mos_run(run, dur):
    d = os.path.join(CAMP, run)
    snd = list(csv.DictReader(open(f"{d}/send_0.csv"))); rcv = {r["seq"]: r for r in csv.DictReader(open(f"{d}/recv_0.csv"))}
    t0 = min(int(r["send_ns"]) for r in snd)
    win = [r for r in snd if 20e9 <= int(r["send_ns"]) - t0 < dur * 1e9]
    dl = np.array([(int(rcv[r["seq"]]["recv_ns"]) - int(r["send_ns"])) / 1e6 for r in win if r["seq"] in rcv])
    res = {}
    for B in (40.0, 60.0, 100.0):
        for Tre in (50.0, 100.0, 150.0):
            for Bpl in (4.3, 25.1):
                dmin = dl.min(); late = int(np.sum(dl > dmin + B)); Ppl = 100.0 * ((len(win) - len(dl)) + late) / len(win)
                Ta = dmin + B + Tre
                if Ta > 100:
                    X = math.log(Ta / 100) / math.log(2)
                    Idd = 25 * ((1 + X ** 6) ** (1 / 6) - 3 * (1 + (X / 3) ** 6) ** (1 / 6) + 2)
                else:
                    Idd = 0.0
                Ie = 0 + (95 - 0) * Ppl / (Ppl / 1 + Bpl); R = 93.2 - Idd - Ie
                M = 1.0 if R < 0 else 4.5 if R > 100 else 1 + 0.035 * R + R * (R - 60) * (100 - R) * 7e-6
                res[(B, Tre, Bpl)] = M
    return res


# sanity checks from protocol §9
X = lambda Ta: math.log(Ta / 100) / math.log(2)
Iddf = lambda Ta: 25 * ((1 + X(Ta) ** 6) ** (1 / 6) - 3 * (1 + (X(Ta) / 3) ** 6) ** (1 / 6) + 2)
P(f"  sanity: Idd(150) {Iddf(150):.2f} (protocol 0.16), Idd(200) {Iddf(200):.2f} (3.0), Idd(300) {Iddf(300):.2f} (14.8); "
  f"Ie-eff(1 %, Bpl 4.3) {95*1/(1+4.3):.2f} (17.9)")
runs = [(r["run"], int(r["dur"]), r["cell"]) for r in main if r["floor"] != "True" and r["probe0_kind"] == "voice"]
with ProcessPoolExecutor(8) as ex:
    mres = list(ex.map(mos_run, [x[0] for x in runs], [x[1] for x in runs], chunksize=20))
bycell = defaultdict(list)
for (rid, _, cid), m in zip(runs, mres):
    bycell[cid].append(m)
keys = list(mres[0].keys())
with open(os.path.join(RES, "expl_mos_sens.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["cell", "B", "T_resto", "Bpl", "MOS_median"])
    for cid, v in sorted(bycell.items()):
        for k_ in keys:
            w.writerow([cid, *k_, round(float(np.median([m[k_] for m in v])), 3)])
with open(os.path.join(RES, "expl_mos_celdas.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["cell", "MOS_median_main", "MOS_min_over_sensitivity", "MOS_max_over_sensitivity"])
    for cid, v in sorted(bycell.items()):
        meds = [float(np.median([m[k_] for m in v])) for k_ in keys]
        w.writerow([cid, round(float(np.median([m[(60.0, 100.0, 4.3)] for m in v])), 3), round(min(meds), 3), round(max(meds), 3)])
P("  E1 k=3, median MOS per policy and L (main case) [range over the 18 sensitivity combinations]:")
for L in (500000, 1000000, 2000000, 3000000, 5000000, 10000000):
    row = []
    for pl, po in (("IOU", "FIFO"), ("IOU", "CBWFQ"), ("IOU", "LLQ"), ("LXR", "FIFO"), ("LXR", "FQC"), ("LXR", "CAKE")):
        cid = f"E1_{pl}_{po}_L{L//1000}k_k3_m0.2_c1_f1514"
        if cid in bycell:
            v = bycell[cid]; meds = [float(np.median([m[k_] for m in v])) for k_ in keys]
            row.append(f"{po if pl == 'IOU' or po != 'FIFO' else 'FIFO-L'}{'-C' if (pl, po) == ('IOU', 'FIFO') else ''} {np.median([m[(60.0,100.0,4.3)] for m in v]):.2f} [{min(meds):.2f}-{max(meds):.2f}]")
    P(f"    L={L//1000:>5}k  " + "  ".join(row))
open(os.path.join(RES, "EXPLORATORIO_SEC6.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
