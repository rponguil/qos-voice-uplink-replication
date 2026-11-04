"""EXPLORATORY: figures added in the second review round.
  1. E4(a) with the competing-frame time on the shaped rate, T_s = 8 * 1514 / R with R = 0.95 * L (LLQ reported with
     T_voz on L and on R), and the largest change of a ratio against the pre-registered T_s on L;
  2. extended bound 2 * T_r + (k + 1) * T_s (T_s on L) for CBWFQ, E1 and E1-R;
  3. positive control with T_s on R;
  4. E3 with voice at 1.5 * B_v: voice loss and p99;
  5. flows per fq_codel run, from meta.json;
  6. c7200 CBWFQ ratios with T_s on R.
Per-cell statistic: median over the runs of the cell of the per-run ratio p99 / bound, as in confirm.py.
Output: results/review2_numbers.json, results/EXPLORATORIO_REVIEW2.txt"""
import collections, csv, glob, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C
RES = os.path.join(HERE, "..", "results"); CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
T = lambda x: x == "True"
Ts = lambda B, frame=1514: frame * 8 / B * 1e3          # ms, B in bit/s
Tvoz = lambda B: 214 * 8 / B * 1e3
R = lambda L: 0.95 * L

rows = C.prep([r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"])
floor = collections.defaultdict(list)
for r in rows:
    if T(r["floor"]):
        floor[(r["platform"], r["Li"])].append(r["p99f"])
floor = {k: float(np.median(v)) for k, v in floor.items()}
cells = collections.defaultdict(list)
for r in rows:
    if not T(r["floor"]):
        cells[r["cell"]].append(r)
med = lambda p, b: float(np.median(np.asarray(p) / b))
rng = lambda v: [float(min(v)), float(max(v))]
out, txt = {}, []
P = txt.append

# 1. E4(a) with T_s on R
e4 = []
for c, v in sorted(cells.items()):
    r0 = v[0]
    if r0["platform"] != "IOU" or r0["exp"] not in ("E1", "E1R") or r0["policy"] not in ("CBWFQ", "LLQ"):
        continue
    L, m, k = r0["Li"], float(r0["m"]), int(r0["k"]); p = [x["p99f"] for x in v]
    if r0["policy"] == "CBWFQ":
        rec = dict(cell=c, policy="CBWFQ", k=k, L=L, m=m, ratio_Ts_L=med(p, 2 * C.Tr(m) + Ts(L)), ratio_Ts_R=med(p, 2 * C.Tr(m) + Ts(R(L))))
    else:
        fl = floor[("IOU", L)]
        rec = dict(cell=c, policy="LLQ", k=k, L=L, m=m, ratio_Ts_L=med(p, Ts(L) + Tvoz(L) + fl),
                   ratio_Ts_R_Tvoz_L=med(p, Ts(R(L)) + Tvoz(L) + fl), ratio_Ts_R_Tvoz_R=med(p, Ts(R(L)) + Tvoz(R(L)) + fl))
    e4.append(rec)
cb = [x for x in e4 if x["policy"] == "CBWFQ"]; ll = [x for x in e4 if x["policy"] == "LLQ"]
out["e4a_Ts_on_R"] = dict(
    cells=e4,
    CBWFQ_k1_L_1_to_5M=rng([x["ratio_Ts_R"] for x in cb if x["k"] == 1 and x["L"] >= 1000000]),
    CBWFQ_k1_L_0p5M=rng([x["ratio_Ts_R"] for x in cb if x["k"] == 1 and x["L"] == 500000]),
    CBWFQ_k2=rng([x["ratio_Ts_R"] for x in cb if x["k"] == 2]),
    CBWFQ_k3_E1_E1R=rng([x["ratio_Ts_R"] for x in cb if x["k"] == 3]),
    LLQ_Tvoz_on_L=rng([x["ratio_Ts_R_Tvoz_L"] for x in ll]),
    LLQ_Tvoz_on_R=rng([x["ratio_Ts_R_Tvoz_R"] for x in ll]),
    largest_drop_vs_Ts_on_L_Tvoz_on_L=float(max([x["ratio_Ts_L"] - x["ratio_Ts_R"] for x in cb] + [x["ratio_Ts_L"] - x["ratio_Ts_R_Tvoz_L"] for x in ll])),
    largest_drop_vs_Ts_on_L_Tvoz_on_R=float(max([x["ratio_Ts_L"] - x["ratio_Ts_R"] for x in cb] + [x["ratio_Ts_L"] - x["ratio_Ts_R_Tvoz_R"] for x in ll])))
o = out["e4a_Ts_on_R"]
P("1. E4(a) WITH T_s ON R = 0.95 L (median per cell of p99 / bound)")
for key in ("CBWFQ_k1_L_1_to_5M", "CBWFQ_k1_L_0p5M", "CBWFQ_k2", "CBWFQ_k3_E1_E1R", "LLQ_Tvoz_on_L", "LLQ_Tvoz_on_R"):
    P(f"  {key:22s} {o[key][0]:.3f} - {o[key][1]:.3f}")
P(f"  largest drop against T_s on L: {o['largest_drop_vs_Ts_on_L_Tvoz_on_L']:.3f} (T_voz on L), {o['largest_drop_vs_Ts_on_L_Tvoz_on_R']:.3f} (T_voz on R)")

# 2. extended bound 2 T_r + (k + 1) T_s, T_s on L
ext = []
for c, v in sorted(cells.items()):
    r0 = v[0]
    if r0["platform"] != "IOU" or r0["exp"] not in ("E1", "E1R") or r0["policy"] != "CBWFQ":
        continue
    L, m, k = r0["Li"], float(r0["m"]), int(r0["k"])
    ext.append(dict(cell=c, k=k, L=L, m=m, ratio=med([x["p99f"] for x in v], 2 * C.Tr(m) + (k + 1) * Ts(L))))
out["extended_bound"] = dict(cells=ext, L_0p5M=rng([x["ratio"] for x in ext if x["L"] == 500000]),
                             L_1M=rng([x["ratio"] for x in ext if x["L"] == 1000000]),
                             L_2_to_5M=rng([x["ratio"] for x in ext if x["L"] >= 2000000]))
o = out["extended_bound"]
P("\n2. EXTENDED BOUND 2 T_r + (k + 1) T_s (T_s on L), CBWFQ E1 + E1-R")
for key in ("L_0p5M", "L_1M", "L_2_to_5M"):
    P(f"  {key:10s} {o[key][0]:.3f} - {o[key][1]:.3f}")

# 3. positive control with T_s on R
cpos = []
for r in csv.DictReader(open(os.path.join(RES, "CPOS.csv"))):
    L = int(r["L"]); ex = float(r["excess"])
    cpos.append(dict(platform=r["platform"], L=L, excess_ms=ex, excess_over_Ts_R=ex / Ts(R(L)), excess_minus_Ts_R_ms=ex - Ts(R(L))))
out["positive_control_Ts_on_R"] = cpos
P("\n3. POSITIVE CONTROL: excess over the floor, in units of T_s on R, and minus T_s on R")
for x in cpos:
    P(f"  {x['platform']:4s} L={x['L'] / 1e6:4.1f} excess {x['excess_ms']:6.2f} ms  / T_s(R) {x['excess_over_Ts_R']:.3f}  - T_s(R) {x['excess_minus_Ts_R_ms']:6.2f} ms")

# 4. E3 with voice at 1.5 B_v
e3 = []
for c, v in sorted(cells.items()):
    if v[0]["exp"] == "E3" and "vx1.5" in c:
        e3.append(dict(cell=c, n=len(v), voice_loss_median=float(np.median([float(x["loss_w"]) for x in v])),
                       p99_median_ms=float(np.median([x["p99f"] for x in v]))))
out["e3_voice_1p5_Bv"] = e3
P("\n4. E3, VOICE AT 1.5 B_v (k = 3; median per cell)")
for x in e3:
    P(f"  {x['cell'][:44]:44s} n={x['n']} voice loss {100 * x['voice_loss_median']:5.1f} %  p99 {x['p99_median_ms']:8.1f} ms")

# 5. flows per fq_codel run
fq = collections.Counter()
for d in sorted(glob.glob(os.path.join(CAMP, "*_LXR_FQC_*"))):
    if not os.path.exists(os.path.join(d, "meta.json")) or "_invalid" in d:
        continue
    meta = json.load(open(os.path.join(d, "meta.json")))
    voice = sum(1 for f in meta["flows"] if f["kind"] == "probe" and f.get("node") == "CW-VOZ")
    other = sum(1 for f in meta["flows"] if not (f["kind"] == "probe" and f.get("node") == "CW-VOZ"))
    fq[(meta["cell"]["k"], meta["cell"].get("calls", 1), voice, other)] += 1
out["fq_codel_flows_per_run"] = [dict(k=k, calls=c, voice_flows=v, other_flows=o, runs=n) for (k, c, v, o), n in sorted(fq.items())]
P("\n5. FLOWS PER fq_codel RUN (meta.json; iperf3 control connections not counted)")
for x in out["fq_codel_flows_per_run"]:
    P(f"  k={x['k']} calls={x['calls']}: {x['voice_flows']} voice + {x['other_flows']} other flows ({x['runs']} runs)")

# 6. c7200 CBWFQ with T_s on R
c72 = []
for k in (1, 3):
    for plat, c in (("C7200", f"E4b_C7200_CBWFQ_L1000k_k{k}_m0.2_c1_f1514"), ("IOU", f"E1_IOU_CBWFQ_L1000k_k{k}_m0.2_c1_f1514")):
        p = [x["p99f"] for x in cells[c]]
        c72.append(dict(platform=plat, k=k, ratio_Ts_R=med(p, 2 * C.Tr(0.2) + Ts(R(1000000))), ratio_Ts_L=med(p, 2 * C.Tr(0.2) + Ts(1000000))))
out["c7200_Ts_on_R"] = c72
P("\n6. c7200 AND IOU, CBWFQ AT 1 Mbit/s: p99 / (2 T_r + T_s)")
for x in c72:
    P(f"  {x['platform']:5s} k={x['k']}: T_s on R {x['ratio_Ts_R']:.3f}  T_s on L {x['ratio_Ts_L']:.3f}")

json.dump(out, open(os.path.join(RES, "review2_numbers.json"), "w"), indent=1)
open(os.path.join(RES, "EXPLORATORIO_REVIEW2.txt"), "w").write("EXPLORATORY (second review round). Tables only.\n\n" + "\n".join(txt) + "\n")
print("\n".join(txt))
