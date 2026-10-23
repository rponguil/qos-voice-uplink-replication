"""Confirmatory analysis, analysis plan v2 §2 (+ the zero-throughput rule for H5, fixed after the plan was frozen and before H5 was computed) and the verification sample (§7).
Outputs in results/: H1.csv, CNEG.csv, H2.csv, H3.csv, H3_residuos.csv, H4.csv, H4_suelo.csv, H5.csv, CPOS.csv, E4a.csv,
celdas.csv (per-cell medians), VERIFICACION_MUESTRA.json, numbers.json, CONFIRMATORIO.txt (plain tables, no interpretation)."""
import csv, glob, json, math, os, sys
from collections import defaultdict
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import stats_lib as S
RES = os.path.join(HERE, "..", "results"); CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
SEED_CELL, SEED_H3, B = 20261020, 20261021, 10000

rows = [r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"]
T = lambda x: x == "True"
fnum = lambda x: float(x) if x not in ("", "None") else None
for r in rows:
    r["Li"] = int(r["L"]); r["p99f"] = float(r["p99"]); r["repi"] = int(r["rep"])
EMI = lambda L: 3.02 if L == 500000 else 2.00
Ts = lambda L, frame=1514: frame * 8 / L * 1000.0
Tvoz = lambda L: 214 * 8 / L * 1000.0
Tr = lambda m, calls=1: 214 * 8 / (calls * 85.6e3 * (1 + m)) * 1000.0
LOW = []   # plain-text report
P = LOW.append


def wcsv(name, recs):
    if not recs:
        return
    keys = list(dict.fromkeys(k for r in recs for k in r))
    with open(os.path.join(RES, name), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(recs)


def fmt(x, n=3):
    return "" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))


# ---------- floors (median p99 per platform and L)
floor = {}
for r in rows:
    if T(r["floor"]):
        floor.setdefault((r["platform"], r["Li"]), []).append(r["p99f"])
floor = {k: float(np.median(v)) for k, v in floor.items()}

# ---------- index: (block, rep) -> {(platform, policy): row}
idx = defaultdict(dict)
for r in rows:
    if not T(r["floor"]):
        idx[(r["block"], r["repi"])][(r["platform"], r["policy"])] = r


def paired(filt, a, b, var="p99f"):
    """Per cell group (block without rep): list of (rep, val_a, val_b, row_a, row_b) for rows passing filt; a,b=(platform,policy)."""
    out = defaultdict(list)
    for (blk, rep), d in idx.items():
        if a in d and b in d and filt(d[a]):
            out[blk].append((rep, d[a][var] if var in d[a] else None, d[b][var] if var in d[b] else None, d[a], d[b]))
    return {k: sorted(v) for k, v in out.items()}


def tost_family(groups, low_high, label_fn, fam):
    recs = []
    for blk, v in groups.items():
        d = np.array([x[1] - x[2] for x in v]); lo, hi = low_high(v[0][3])
        t = S.tost_paired(d, lo, hi)
        recs.append(dict(family=fam, cell=label_fn(v[0][3]), block=blk, n=len(d), mean_d=t["mean"], ci90_lo=t["ci90"][0], ci90_hi=t["ci90"][1],
                         median_d=float(np.median(d)), boot95_median=S.boot_ci(d, B=B, seed=SEED_CELL), margin=hi, p_low=t["p_low"],
                         p_high=t["p_high"], p_tost=t["p"]))
    adj = S.holm([r["p_tost"] for r in recs])
    for r, a in zip(recs, adj):
        r["p_holm"] = a; r["equivalent"] = a < 0.05
    return recs


lab = lambda r: f"{r['exp']} L={r['Li']//1000}k k={r['k']}" + (f" m={r['m']}" if float(r["m"]) != 0.2 else "") + \
    (f" frame={r['frame']}" if r["frame"] != "1514" else "") + (f" calls={r['calls']}" if r["calls"] != "1" else "")
IOU = lambda p: ("IOU", p)

# ========== H1
g = paired(lambda r: r["exp"] == "E1" and r["k"] == "1", IOU("CBWFQ"), IOU("LLQ"))
h1 = tost_family(g, lambda r: (-EMI(r["Li"]), EMI(r["Li"])), lab, "H1 E1 k=1")
for rec in h1:
    L = int(rec["cell"].split("L=")[1].split("k")[0]) * 1000
    v = g[rec["block"]]
    rec["p99_CBWFQ_median"] = float(np.median([x[1] for x in v])); rec["p99_LLQ_median"] = float(np.median([x[2] for x in v]))
    rec["LLQ_bound_Ts_Tvoz_floor"] = Ts(L) + Tvoz(L) + floor[("IOU", L)]
    rec["exempt_cell"] = T(v[0][3]["shaper_exempt"])
h1.sort(key=lambda r: int(r["cell"].split("L=")[1].split("k")[0]))
# ========== CNEG
cneg = []
for k in ("1", "3"):
    g = paired(lambda r, k=k: r["exp"] == "CNEG" and r["k"] == k, IOU("CBWFQ"), IOU("LLQ"))
    f_ = tost_family(g, lambda r: (-EMI(r["Li"]), EMI(r["Li"])), lab, f"CNEG k={k}")
    cneg += sorted(f_, key=lambda r: int(r["cell"].split("L=")[1].split("k")[0]))

# ========== H2
h2 = []
for fam, filt in (("H2 E1 k=2", lambda r: r["exp"] == "E1" and r["k"] == "2"),
                  ("H2 E1 k=3", lambda r: r["exp"] == "E1" and r["k"] == "3"),
                  ("H2 E2 k=3", lambda r: r["exp"] == "E2")):
    g = paired(filt, IOU("CBWFQ"), IOU("LLQ")); recs = []
    for blk, v in g.items():
        d = np.array([x[1] - x[2] for x in v]); a = [x[1] for x in v]; b = [x[2] for x in v]
        recs.append(dict(family=fam, cell=lab(v[0][3]), block=blk, n=len(d), mean_delta=float(d.mean()), median_delta=float(np.median(d)),
                         boot95_median=S.boot_ci(d, B=B, seed=SEED_CELL), cliff_delta=S.cliff_delta(a, b),
                         p_signperm=S.signperm_exact(d, "greater"), p_wilcoxon=S.wilcoxon(d, "greater")))
    for r, aj in zip(recs, S.holm([r["p_signperm"] for r in recs])):
        r["p_holm"] = aj; r["delta_positive"] = aj < 0.05
    for r, aj in zip(recs, S.holm([r["p_wilcoxon"] for r in recs])):
        r["p_wilcoxon_holm"] = aj
    h2 += sorted(recs, key=lambda r: (r["cell"]))

# ========== H3 (k = 3; E1 m=0.2 + E1-R; IOU)
h3cells = sorted({(r["Li"], float(r["m"])) for r in rows if r["platform"] == "IOU" and r["k"] == "3" and r["policy"] == "CBWFQ"
                  and ((r["exp"] == "E1" and float(r["m"]) == 0.2) or r["exp"] == "E1R")})
h3_out, h3_res = {}, []
rng = np.random.default_rng(SEED_H3)
for model in ("p99_CBWFQ", "Delta"):
    X, y, gi = [], [], []
    for ci, (L, m) in enumerate(h3cells):
        exp = "E1" if m == 0.2 else "E1R"
        g = paired(lambda r, L=L, m=m, exp=exp: r["exp"] == exp and r["k"] == "3" and r["Li"] == L and float(r["m"]) == m, IOU("CBWFQ"), IOU("LLQ"))
        assert len(g) == 1, (L, m, len(g))
        for rep, a, b, *_ in list(g.values())[0]:
            X.append([Ts(L), Tr(m), 1.0]); y.append(a if model == "p99_CBWFQ" else a - b); gi.append(ci)
    X, y, gi = np.array(X), np.array(y), np.array(gi); grp = [np.where(gi == c)[0] for c in range(len(h3cells))]
    beta = S.ols(X, y); yhat = X @ beta; rss_lin = float(np.sum((y - yhat) ** 2))
    means = np.array([y[ix].mean() for ix in grp]); rss_means = float(sum(np.sum((y[ix] - y[ix].mean()) ** 2) for ix in grp))
    N, G = len(y), len(h3cells); Fv = ((rss_lin - rss_means) / (G - 3)) / (rss_means / (N - G))
    from scipy import stats as SS
    p_lof = float(1 - SS.f.cdf(Fv, G - 3, N - G)); r2 = 1 - rss_lin / float(np.sum((y - y.mean()) ** 2))
    bw, bc = np.empty((B, 3)), np.empty((B, 3))
    for i in range(B):
        ix = np.concatenate([rng.choice(g_, len(g_)) for g_ in grp]); bw[i] = S.ols(X[ix], y[ix])
        cc = rng.integers(0, G, G); ix = np.concatenate([grp[c] for c in cc]); bc[i] = S.ols(X[ix], y[ix])
    qw = np.quantile(bw, [.025, .975], axis=0); qc = np.quantile(bc, [.025, .975], axis=0)
    ref = (1.0, 2.0) if model == "p99_CBWFQ" else (0.0, 2.0)
    h3_out[model] = dict(n=N, cells=G, a=float(beta[0]), b=float(beta[1]), c=float(beta[2]), R2=r2,
                         a_ci_within=qw[:, 0].tolist(), b_ci_within=qw[:, 1].tolist(), c_ci_within=qw[:, 2].tolist(),
                         a_ci_cluster=qc[:, 0].tolist(), b_ci_cluster=qc[:, 1].tolist(), c_ci_cluster=qc[:, 2].tolist(),
                         ref_a=ref[0], ref_b=ref[1], ref_a_in_cluster_ci=bool(qc[0, 0] <= ref[0] <= qc[1, 0]),
                         ref_b_in_cluster_ci=bool(qc[0, 1] <= ref[1] <= qc[1, 1]), lack_of_fit_F=Fv, lack_of_fit_df=(G - 3, N - G), lack_of_fit_p=p_lof)
    for ci, (L, m) in enumerate(h3cells):
        pred = float(np.array([Ts(L), Tr(m), 1.0]) @ beta)
        h3_res.append(dict(model=model, L=L, m=m, T_s=Ts(L), T_r=Tr(m), cell_mean=float(means[ci]), predicted=pred, residual=float(means[ci] - pred)))

# ========== H4
h4, h4fl = [], []
for fam, filt in [(f"H4 E1 k={k}", (lambda r, k=k: r["exp"] == "E1" and r["k"] == k and r["Li"] <= 5000000)) for k in ("1", "2", "3")] + \
                 [("H4 E2 k=3", lambda r: r["exp"] == "E2")]:
    recs = []
    for X_ in ("FQC", "CAKE"):
        g = paired(filt, ("LXR", X_), IOU("LLQ"))
        for blk, v in g.items():
            d = np.array([x[1] - x[2] for x in v]); L = v[0][3]["Li"]; t = S.tost_paired(d, -EMI(L), EMI(L))
            recs.append(dict(family=fam, policy=X_, cell=lab(v[0][3]), block=blk, n=len(d), mean_d=t["mean"], median_d=float(np.median(d)),
                             boot95_median=S.boot_ci(d, B=B, seed=SEED_CELL), margin=EMI(L), p_tost=t["p"],
                             p_signperm_two_sided_descriptive=S.signperm_exact(d, "two-sided")))
    for r, aj in zip(recs, S.holm([r["p_tost"] for r in recs])):
        r["p_holm"] = aj; r["comparable"] = aj < 0.05
    h4 += sorted(recs, key=lambda r: (r["policy"], r["cell"]))
# excess over own-platform floor (all policies, E1/E2 incl. 10 Mbit/s) + FQC active flows + CAKE voice share
cellrows = defaultdict(list)
for r in rows:
    if not T(r["floor"]):
        cellrows[r["cell"]].append(r)


def fqc_flows(run):
    f = os.path.join(CAMP, run, "fqc_flows.txt")
    if not os.path.exists(f):
        return None
    v = []
    for line in open(f):
        p = line.split()
        if len(p) >= 5 and p[1] == "new_flows_len":
            v.append(int(p[2]) + int(p[4]))
    return float(np.median(v)) if v else None


for cid, v in sorted(cellrows.items()):
    r0 = v[0]
    if r0["exp"] not in ("E1", "E2"):
        continue
    med = float(np.median([x["p99f"] for x in v])); fl = floor.get((r0["platform"], r0["Li"]))
    rec = dict(cell=cid, exp=r0["exp"], platform=r0["platform"], policy=r0["policy"], L=r0["Li"], k=r0["k"], calls=r0["calls"], frame=r0["frame"],
               p99_median=med, floor_median=fl, excess_over_floor=(med - fl) if fl is not None else None)
    if r0["policy"] == "FQC":
        fv = [fqc_flows(x["run"]) for x in v]; fv = [x for x in fv if x is not None]
        rec["fqc_active_flows_median"] = float(np.median(fv)) if fv else None
    if r0["policy"] == "CAKE":
        rec["voice_rate_over_25pctR"] = (int(r0["calls"]) * 85.6e3) / (0.25 * float(r0["R"]))
    h4fl.append(rec)

# ========== H5 (E3, voice within reservation)
h5 = []
for L in (1000000, 5000000):
    for role in ("data", "res"):
        g = paired(lambda r, L=L: r["exp"] == "E3" and r["Li"] == L and r["voice_over"] in ("", "None"), IOU("LLQ"), IOU("CBWFQ"), var=f"gp_{role}")
        assert len(g) == 1
        v = list(g.values())[0]
        ok, starved = [], 0
        for rep, a, b, ra, rb in v:
            a, b = fnum(a), fnum(b)
            if not a or not b or T(ra.get(f"hambre_{role}", "False")) or T(rb.get(f"hambre_{role}", "False")):
                starved += 1; continue
            ok.append(math.log(a / b))
        rec = dict(family="H5 E3", L=L, flow=role, n_pairs=len(v), starved_pairs=starved)
        if starved > 2:
            rec.update(evaluable=False)
        else:
            t = S.tost_paired(np.array(ok), math.log(0.95), math.log(1.05))
            rec.update(evaluable=True, n_used=len(ok), mean_log_ratio=t["mean"], ratio_geomean=math.exp(t["mean"]),
                       ci90_ratio=(math.exp(t["ci90"][0]), math.exp(t["ci90"][1])), p_tost=t["p"])
        h5.append(rec)
ev = [r for r in h5 if r.get("evaluable")]
for r, aj in zip(ev, S.holm([r["p_tost"] for r in ev])):
    r["p_holm"] = aj; r["equivalent_within_5pct"] = aj < 0.05
h5_over = []
for L in (1000000, 5000000):
    for role in ("data", "res"):
        g = paired(lambda r, L=L: r["exp"] == "E3" and r["Li"] == L and r["voice_over"] not in ("", "None"), IOU("LLQ"), IOU("CBWFQ"), var=f"gp_{role}")
        v = list(g.values())[0]; lr = [math.log(fnum(a) / fnum(b)) for _, a, b, *_ in v if fnum(a) and fnum(b)]
        h5_over.append(dict(L=L, flow=role, voice="1.5 x B_v", n=len(lr), ratio_geomean=math.exp(np.mean(lr)) if lr else None,
                            ci95_ratio=tuple(math.exp(x) for x in S.mean_ci(lr)) if len(lr) > 2 else None))
hambre_cells = defaultdict(int)
for r in rows:
    if r["tcp_hambre"]:
        hambre_cells[r["cell"]] += 1

# ========== positive control
cpos = []
for cid, v in sorted(cellrows.items(), key=lambda kv: (kv[1][0]["platform"], kv[1][0]["Li"])):
    r0 = v[0]
    if r0["exp"] != "CPOS":
        continue
    L = r0["Li"]; med = float(np.median([x["p99f"] for x in v])); fl = floor[(r0["platform"], L)]; ex = med - fl
    cpos.append(dict(cell=cid, platform=r0["platform"], L=L, p99_median=med, floor_median=fl, excess=ex, EMI=EMI(L), T_s=Ts(L),
                     excess_over_T_s=ex / Ts(L), literal_pass_excess_le_EMI=ex <= EMI(L), physical_pass_excess_le_Ts_plus_EMI=ex <= Ts(L) + EMI(L)))

# ========== E4(a)
e4a = []
for cid, v in sorted(cellrows.items()):
    r0 = v[0]
    if r0["platform"] != "IOU" or r0["exp"] not in ("E1", "E1R") or r0["policy"] not in ("CBWFQ", "LLQ"):
        continue
    L, m = r0["Li"], float(r0["m"]); p = np.array([x["p99f"] for x in v])
    if r0["policy"] == "LLQ":
        b1 = Ts(L) + Tvoz(L) + floor[("IOU", L)]; b2 = Ts(L) + Tvoz(L)
        e4a.append(dict(cell=cid, policy="LLQ", L=L, k=r0["k"], m=m, bound_main="T_s+T_voz+floor", bound_main_ms=b1, ratio_main=float(np.median(p / b1)),
                        ratio_main_ci95=S.boot_ci(p / b1, B=B, seed=SEED_CELL), bound_secondary="T_s+T_voz", ratio_secondary=float(np.median(p / b2))))
    else:
        b = 2 * Tr(m) + Ts(L)
        e4a.append(dict(cell=cid, policy="CBWFQ", L=L, k=r0["k"], m=m, bound_main="2*T_r+T_s (RFC 2212)", bound_main_ms=b, ratio_main=float(np.median(p / b)),
                        ratio_main_ci95=S.boot_ci(p / b, B=B, seed=SEED_CELL), bound_secondary="", ratio_secondary=None))

# ========== per-cell descriptives
celdas = []
for cid, v in sorted(cellrows.items()):
    p = np.array([x["p99f"] for x in v]); r0 = v[0]
    celdas.append(dict(cell=cid, n=len(p), p99_median=float(np.median(p)), p99_ci95=S.boot_ci(p, B=B, seed=SEED_CELL),
                       p50_median=float(np.median([float(x["p50"]) for x in v])), loss_w_median=float(np.median([float(x["loss_w"]) for x in v])),
                       jitter_median=float(np.median([float(x["jitter"]) for x in v])), max_median=float(np.median([float(x["max"]) for x in v])),
                       shaper_err_median=(float(np.median([fnum(x["shaper_err"]) for x in v if fnum(x["shaper_err"]) is not None]))
                                          if any(fnum(x["shaper_err"]) is not None for x in v) else None),
                       marcadas=sum(T(x["marcada"]) for x in v), tcp_hambre_runs=hambre_cells.get(cid, 0)))

# ========== verification sample (§7)
samp = json.load(open(os.path.join(HERE, "..", "MUESTRA_VERIFICACION.json")))
byrun = {r["run"]: r for r in rows}
ver = {"p99_runs": {rid: byrun[rid]["p99f"] for rid in samp["p99_runs"]},
       "H2_E1_k3_1M": next(r for r in h2 if r["family"] == "H2 E1 k=3" and "L=1000k" in r["cell"]),
       "H2_E1_k3_5M": next(r for r in h2 if r["family"] == "H2 E1 k=3" and "L=5000k" in r["cell"]),
       "H1_1M": next(r for r in h1 if "L=1000k" in r["cell"]), "H3_p99_CBWFQ": h3_out["p99_CBWFQ"]}

# ========== write
wcsv("H1.csv", h1); wcsv("CNEG.csv", cneg); wcsv("H2.csv", h2); wcsv("H3_residuos.csv", h3_res); wcsv("H4.csv", h4); wcsv("H4_suelo.csv", h4fl)
wcsv("H5.csv", h5 + h5_over); wcsv("CPOS.csv", cpos); wcsv("E4a.csv", e4a); wcsv("celdas.csv", celdas)
json.dump(h3_out, open(os.path.join(RES, "H3.json"), "w"), indent=1)
json.dump(ver, open(os.path.join(RES, "VERIFICACION_MUESTRA.json"), "w"), indent=1, default=str)
numbers = {"H1": h1, "CNEG": cneg, "H2": h2, "H3": h3_out, "H4": h4, "H5": h5, "H5_over": h5_over, "CPOS": cpos, "floors": {f"{k[0]}_{k[1]}": v for k, v in floor.items()}}
json.dump(numbers, open(os.path.join(RES, "numbers.json"), "w"), indent=1, default=str)

# plain report
P("CONFIRMATORY RESULTS (analysis plan v2), tables only. Times in ms. p_holm within family.")
P("\nH1 (E1 IOU k=1; d = p99 CBWFQ - p99 LLQ; TOST +-EMI)")
for r in h1:
    P(f"  {r['cell']:16s} n={r['n']} mean d {r['mean_d']:+8.3f} [90% {r['ci90_lo']:+.3f},{r['ci90_hi']:+.3f}] median {r['median_d']:+8.3f} margin {r['margin']:.2f} "
      f"p_tost {r['p_tost']:.4g} p_holm {r['p_holm']:.4g} equiv {r['equivalent']} | p99 CBWFQ {r['p99_CBWFQ_median']:.2f} LLQ {r['p99_LLQ_median']:.2f} "
      f"bound {r['LLQ_bound_Ts_Tvoz_floor']:.2f}{' [exempt cell]' if r['exempt_cell'] else ''}")
P("\nNegative control (unmarked; d = CBWFQ - LLQ; TOST +-EMI)")
for r in cneg:
    P(f"  {r['family']:9s} {r['cell']:18s} mean d {r['mean_d']:+8.3f} [90% {r['ci90_lo']:+.3f},{r['ci90_hi']:+.3f}] p_tost {r['p_tost']:.4g} p_holm {r['p_holm']:.4g} equiv {r['equivalent']}")
P("\nH2 (Delta = p99 CBWFQ - p99 LLQ; exact sign permutation, one-sided; Wilcoxon check)")
for r in h2:
    P(f"  {r['family']:9s} {r['cell']:34s} median Delta {r['median_delta']:8.2f} [95% {r['boot95_median'][0]:.2f},{r['boot95_median'][1]:.2f}] "
      f"Cliff {r['cliff_delta']:+.2f} p_perm {r['p_signperm']:.3g} p_holm {r['p_holm']:.3g} (Wilcoxon holm {r['p_wilcoxon_holm']:.3g}) Delta>0 {r['delta_positive']}")
P("\nH3 (k=3, E1+E1-R, 19 cells; OLS; CI within cells / cluster)")
for mdl, o in h3_out.items():
    P(f"  {mdl}: a={o['a']:.3f} within[{o['a_ci_within'][0]:.3f},{o['a_ci_within'][1]:.3f}] cluster[{o['a_ci_cluster'][0]:.3f},{o['a_ci_cluster'][1]:.3f}] (ref {o['ref_a']}, in cluster CI: {o['ref_a_in_cluster_ci']}); "
      f"b={o['b']:.3f} within[{o['b_ci_within'][0]:.3f},{o['b_ci_within'][1]:.3f}] cluster[{o['b_ci_cluster'][0]:.3f},{o['b_ci_cluster'][1]:.3f}] (ref {o['ref_b']}, in cluster CI: {o['ref_b_in_cluster_ci']}); "
      f"c={o['c']:.3f}; R2={o['R2']:.3f}; lack-of-fit F({o['lack_of_fit_df'][0]},{o['lack_of_fit_df'][1]})={o['lack_of_fit_F']:.2f} p={o['lack_of_fit_p']:.3g}")
P("  residuals per cell: results/H3_residuos.csv")
P("\nH4 (d = p99 X - p99 LLQ; TOST +-EMI decides 'comparable'; sign permutation two-sided descriptive)")
for r in h4:
    P(f"  {r['family']:9s} {r['policy']:4s} {r['cell']:34s} median d {r['median_d']:+8.2f} mean {r['mean_d']:+8.2f} p_tost {r['p_tost']:.3g} p_holm {r['p_holm']:.3g} "
      f"comparable {r['comparable']} | p_perm2 {r['p_signperm_two_sided_descriptive']:.3g}")
P("  excess over own-platform floor, FQC active flows, CAKE voice share: results/H4_suelo.csv")
P("\nH5 (E3; ln(goodput LLQ / CBWFQ); TOST [ln .95, ln 1.05]; zero goodput or hambre -> pair out, >2 -> not evaluable)")
for r in h5:
    if r.get("evaluable"):
        P(f"  L={r['L']//1000}k {r['flow']:4s} pairs {r['n_pairs']} starved {r['starved_pairs']} ratio {r['ratio_geomean']:.4f} [90% {r['ci90_ratio'][0]:.4f},{r['ci90_ratio'][1]:.4f}] "
          f"p_tost {r['p_tost']:.3g} p_holm {r['p_holm']:.3g} equiv {r['equivalent_within_5pct']}")
    else:
        P(f"  L={r['L']//1000}k {r['flow']:4s} pairs {r['n_pairs']} starved {r['starved_pairs']} -> NOT EVALUABLE")
for r in h5_over:
    P(f"  voice 1.5xB_v (descriptive) L={r['L']//1000}k {r['flow']:4s} ratio {fmt(r['ratio_geomean'],4)} 95% {r['ci95_ratio']}")
P(f"  tcp_hambre runs per cell (main analysis): {dict(hambre_cells)}")
P("\nPositive control (excess = median p99 CPOS - median floor of its platform and L)")
for r in cpos:
    P(f"  {r['platform']:4s} L={r['L']//1000}k p99 {r['p99_median']:.2f} floor {r['floor_median']:.2f} excess {r['excess']:.2f} = {r['excess_over_T_s']:.2f} T_s | "
      f"literal (<= EMI) {r['literal_pass_excess_le_EMI']} | physical (<= T_s+EMI = {r['T_s']+r['EMI']:.2f}) {r['physical_pass_excess_le_Ts_plus_EMI']}")
P("\nE4(a) (median of per-run ratio measured/bound, 95% bootstrap CI)")
for r in e4a:
    P(f"  {r['cell'][:44]:44s} {r['policy']:5s} bound {r['bound_main']:20s} {r['bound_main_ms']:7.2f} ratio {r['ratio_main']:.3f} [{r['ratio_main_ci95'][0]:.3f},{r['ratio_main_ci95'][1]:.3f}]"
      + (f" | without floor {r['ratio_secondary']:.3f}" if r["ratio_secondary"] else ""))
open(os.path.join(RES, "CONFIRMATORIO.txt"), "w").write("\n".join(LOW) + "\n")
print("\n".join(LOW))
