"""Analysis plan v2 §4: code validation. Output: results/VALIDACION.txt"""
import glob, json, os, re, statistics as st, sys
from collections import defaultdict
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import load_runs as LR, stats_lib as S
PILOT = os.path.join(HERE, "..", "..", "F4_campana", "pilot"); RES = os.path.join(HERE, "..", "results")
out = []; P = out.append; problems = []

# ---------- 1. pilot reproduction (independent code path vs analyze_pilot.py / analyze_p3b.py outputs)
txt = open(os.path.join(PILOT, "ANALISIS_PILOTO.txt")).read(); txt3 = open(os.path.join(PILOT, "ANALISIS_P3b.txt")).read()
runs = []
for d in sorted(glob.glob(os.path.join(PILOT, "*_r[0-9][0-9]"))):
    m = json.load(open(d + "/meta.json")); runs.append((d, m["cell"], m["rep"]))
P("1. PILOT REPRODUCTION")
fl = defaultdict(list)
for d, c, r in runs:
    if c["floor"]:
        fl[(c["platform"], c["L"])].append(LR.voice(d, c["dur"], 5.0, c["dur"])["p99"])
for (pl, L), v in sorted(fl.items()):
    mm = re.search(rf"\('{pl}', {L}\): n=\d+ p99 median ([\d.]+) amp ([\d.]+)", txt)
    mine = (round(st.median(v), 3), round(max(v) - min(v), 3)); ref = (float(mm.group(1)), float(mm.group(2)))
    ok = all(abs(a - b) <= 0.0015 for a, b in zip(mine, ref)); problems += [] if ok else [f"floor {pl} {L}: {mine} vs {ref}"]
    P(f"  floor {pl} {L}: mine median/amp {mine} | pilot {ref} {'OK' if ok else 'DIFF'}")
llq = defaultdict(list)
for d, c, r in runs:
    if not c["floor"] and c["exp"] == "E1" and c["policy"] == "LLQ" and c["platform"] == "IOU":
        llq[(c["L"], c["k"])].append(LR.voice(d, c["dur"], 5.0, c["dur"])["p99"])
for (L, k), v in sorted(llq.items()):
    mm = re.search(rf"L={L} k={k}: median p99 LLQ ([\d.]+) -> EMI ([\d.]+)", txt)
    mine = round(st.median(v), 2); emi = max(2.0, 0.1 * st.median(v)); ref = float(mm.group(1))
    ok = abs(mine - ref) <= 0.006 and abs(round(emi, 2) - float(mm.group(2))) <= 0.006
    problems += [] if ok else [f"EMI L={L} k={k}: {mine} vs {ref}"]
    P(f"  EMI base L={L} k={k}: median p99 LLQ {mine} -> EMI {emi:.2f} | pilot {ref} -> {mm.group(2)} {'OK' if ok else 'DIFF'}")
pairs = defaultdict(lambda: defaultdict(dict))
for d, c, r in runs:
    if not c["floor"] and c["policy"] in ("CBWFQ", "LLQ"):
        pairs[(c["exp"], c["L"], c["k"], c["m"], c["marked"])][c["policy"]][r] = d
for key, pol in sorted(pairs.items()):
    reps = sorted(set(pol["CBWFQ"]) & set(pol["LLQ"]))
    sds = []
    for a, b in ((5, 45), (45, 85), (80, 120)):
        dd = [LR.voice(pol["CBWFQ"][r], 120, a, b)["p99"] - LR.voice(pol["LLQ"][r], 120, a, b)["p99"] for r in reps]
        sds.append(st.stdev(dd))
    pooled = float(np.sqrt(np.mean(np.square(sds))))
    lab = f"{key[0]:4s} L={key[1]/1e6:>4} k={key[2]} m={key[3]}"
    mm = re.search(re.escape(lab) + r".*?pooled ([\d.]+) ms", txt3)
    ok = mm and abs(pooled - float(mm.group(1))) <= 0.006
    problems += [] if ok else [f"SD {lab}: {pooled:.2f} vs {mm.group(1) if mm else None}"]
    P(f"  paired SD {lab}: mine {pooled:.2f} | P3b {mm.group(1) if mm else '?'} {'OK' if ok else 'DIFF'}")

# ---------- 2. shuffled labels, E1 IOU k = 3 (campaign data; labels permuted within pair = random sign flip of d)
import csv
rows = [r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"]
P("\n2. SHUFFLED LABELS (E1 IOU k=3, CBWFQ/LLQ swapped at random within each pair; 200 shuffles; seed 20261022)")
by = defaultdict(dict)
for r in rows:
    if r["exp"] == "E1" and r["platform"] == "IOU" and r["k"] == "3" and r["policy"] in ("CBWFQ", "LLQ"):
        by[r["L"]][(r["policy"], r["rep"])] = float(r["p99"])
EMI = lambda L: 3.02 if int(L) == 500000 else 2.00
rng = np.random.default_rng(20261022)
for L in sorted(by, key=int):
    d = np.array([by[L][("CBWFQ", str(i))] - by[L][("LLQ", str(i))] for i in range(1, 18)])
    p_h2, eq, ci0, means = [], 0, 0, []
    for _ in range(200):
        ds = d * rng.choice([1.0, -1.0], size=len(d))
        p_h2.append(S.signperm_exact(ds, "greater"))
        t = S.tost_paired(ds, -EMI(L), EMI(L)); eq += t["p"] < 0.05
        lo, hi = S.mean_ci(ds); ci0 += lo <= 0 <= hi; means.append(ds.mean())
    P(f"  L={int(L)//1000}k: H2 frac p<0.05 {np.mean(np.array(p_h2) < 0.05):.3f} | TOST: mean of d over shuffles {np.mean(means):+.3f} ms, "
      f"95% CI contains 0 in {ci0/200:.3f}, equivalence declared in {eq/200:.3f}")
    if not (0.0 <= np.mean(np.array(p_h2) < 0.05) <= 0.12):
        problems.append(f"shuffle H2 L={L}")

# ---------- 3. synthetic H3 (a=1, b=2, c=1 ms; real T_s, T_r of the 19 cells; 17 reps; noise SD 1.3 ms)
P("\n3. SYNTHETIC H3 (seed 20261023)")
cells = sorted({(int(r["L"]), float(r["m"])) for r in rows if r["platform"] == "IOU" and r["k"] == "3" and r["policy"] == "CBWFQ"
                and ((r["exp"] == "E1" and float(r["m"]) == 0.2) or r["exp"] == "E1R")})
P(f"  cells: {len(cells)}")
rng = np.random.default_rng(20261023)
for (aa, bb, label) in ((1.0, 2.0, "p99 CBWFQ"), (0.0, 2.0, "Delta")):
    X, y, g = [], [], []
    for ci, (L, m) in enumerate(cells):
        Ts = 1514 * 8 / L * 1000; Tr = 214 * 8 / (85.6e3 * (1 + m)) * 1000
        for _ in range(17):
            X.append([Ts, Tr, 1.0]); y.append(aa * Ts + bb * Tr + 1.0 + rng.normal(0, 1.3)); g.append(ci)
    X, y, g = np.array(X), np.array(y), np.array(g)
    beta = S.ols(X, y)
    bs_w, bs_c = [], []
    for _ in range(2000):   # within-cell and cluster bootstrap
        idx = np.concatenate([rng.choice(np.where(g == c)[0], 17) for c in range(len(cells))]); bs_w.append(S.ols(X[idx], y[idx]))
        cc = rng.integers(0, len(cells), len(cells)); idx = np.concatenate([np.where(g == c)[0] for c in cc]); bs_c.append(S.ols(X[idx], y[idx]))
    qw = np.quantile(bs_w, [.025, .975], axis=0); qc = np.quantile(bs_c, [.025, .975], axis=0)
    okw = qw[0, 0] <= aa <= qw[1, 0] and qw[0, 1] <= bb <= qw[1, 1]; okc = qc[0, 0] <= aa <= qc[1, 0] and qc[0, 1] <= bb <= qc[1, 1]
    P(f"  {label}: true a={aa} b={bb} -> a={beta[0]:.3f} b={beta[1]:.3f} c={beta[2]:.3f}; CI within a[{qw[0,0]:.3f},{qw[1,0]:.3f}] b[{qw[0,1]:.3f},{qw[1,1]:.3f}] "
      f"| CI cluster a[{qc[0,0]:.3f},{qc[1,0]:.3f}] b[{qc[0,1]:.3f},{qc[1,1]:.3f}] -> contain truth: {okw}/{okc}")
    if not (okw and okc):
        problems.append(f"synthetic H3 {label}")
P("\nPROBLEMS: " + ("; ".join(problems) if problems else "none"))
open(os.path.join(RES, "VALIDACION.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
