"""Sensitivity analyses, analysis plan v2 §5.1-5.7 (5.8 MOS goes with the exploratory MOS).
First checks that core.py reproduces confirm.py on the main rows. Output: results/SENSIBILIDAD.txt + results/sens_*.csv"""
import csv, glob, json, os, sys
from collections import defaultdict
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C, stats_lib as S, load_runs as LR
RES = os.path.join(HERE, "..", "results"); CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
out = []; P = out.append; CHANGES = []
allrows = C.prep(list(csv.DictReader(open(os.path.join(RES, "runs.csv")))))
main = [r for r in allrows if r["main"] == "True"]


def wcsv(name, recs):
    if recs:
        keys = list(dict.fromkeys(k for r in recs for k in r))
        with open(os.path.join(RES, name), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(recs)


def decisions(res):
    d = {}
    for t in ("H1", "CNEG", "H2", "H4", "H5"):
        for r in res.get(t, []):
            d[(t, r["family"], r.get("policy", ""), r.get("cell", f"L={r.get('L')} {r.get('flow','')}"))] = r["decision"]
    for mdl, o in (res.get("H3") or {}).items():
        d[("H3", mdl, "", "")] = o["decision"]
    return d


def compare(name, res, base, only=None):
    dv, db = decisions(res), decisions(base); ch = []
    for k, v in dv.items():
        if only and k[0] not in only:
            continue
        if k in db and db[k] != v:
            ch.append((k, db[k], v))
    P(f"  -> decisions compared: {sum(1 for k in dv if k in db and (not only or k[0] in only))}; changed: {len(ch)}")
    for k, a, b in ch:
        P(f"     CHANGE {k}: {a} -> {b}")
    CHANGES.extend((name, k, a, b) for k, a, b in ch)


# ---------- 0. core reproduces confirm.py
P("0. CORE vs CONFIRM (main rows)")
base = C.all_tests(main, boot=False)
conf = {t: list(csv.DictReader(open(os.path.join(RES, f"{t}.csv")))) for t in ("H1", "CNEG", "H2", "H4", "H5")}
h3c = json.load(open(os.path.join(RES, "H3.json")))
mism = 0
for t, key, dec in (("H1", "p_holm", "equivalent"), ("CNEG", "p_holm", "equivalent"), ("H2", "p_holm", "delta_positive"), ("H4", "p_holm", "comparable")):
    cm = {(r["family"], r.get("policy", ""), r["cell"]): r for r in conf[t]}
    for r in base[t]:
        c = cm[(r["family"], r.get("policy", ""), r["cell"])]
        if abs(float(c[key]) - r["p_holm"]) > 1e-12 or (c[dec] == "True") != (r["decision"] in ("equivalent", "Delta>0", "comparable")):
            mism += 1; P(f"  MISMATCH {t} {r['cell']}")
for r, c in zip(base["H5"], [x for x in conf["H5"] if x.get("evaluable") in ("True", "False")]):
    if abs(float(c["p_holm"]) - r["p_holm"]) > 1e-12:
        mism += 1; P(f"  MISMATCH H5 {r['L']} {r['flow']}")
for mdl in ("p99_CBWFQ", "Delta"):
    if abs(h3c[mdl]["a"] - base["H3"][mdl]["a"]) > 1e-9 or abs(h3c[mdl]["b"] - base["H3"][mdl]["b"]) > 1e-9 or \
            np.max(np.abs(np.array(h3c[mdl]["a_ci_cluster"]) - np.array(base["H3"][mdl]["a_ci_cluster"]))) > 1e-9:
        mism += 1; P(f"  MISMATCH H3 {mdl}")
P(f"  mismatches: {mism}")
if mism:
    open(os.path.join(RES, "SENSIBILIDAD.txt"), "w").write("\n".join(out) + "\n"); sys.exit("core does not reproduce confirm.py")

marc = lambda x: not (C.T(x[3]["marcada"]) or C.T(x[4]["marcada"]))
# ---------- 5.1 without flagged runs
P("\n5.1 WITHOUT FLAGGED RUNS (marcada) — H1, H2, CNEG")
idx = C.index(main)
r51 = dict(H1=C.h1(idx, pair_filter=marc, boot=False), CNEG=C.cneg(idx, pair_filter=marc, boot=False), H2=C.h2(idx, pair_filter=marc, boot=False))
nflag = sum(1 for r in main if C.T(r["marcada"]))
P(f"  flagged runs in main: {nflag}; pairs dropped per family: " + ", ".join(f"{t} {sum(17 - r['n'] for r in r51[t])}" for t in r51))
compare("5.1", r51, base); wcsv("sens_51_sin_marcadas.csv", [dict(test=t, **r) for t in r51 for r in r51[t]])
# ---------- 5.2 without 2 and 3 Mbit/s
P("\n5.2 WITHOUT IOU 2 AND 3 Mbit/s — H1, H2, CNEG (Holm over the remaining L)")
Ls = {500000, 1000000, 5000000}
r52 = dict(H1=C.h1(idx, Ls=Ls, boot=False), CNEG=C.cneg(idx, Ls=Ls, boot=False), H2=C.h2(idx, Ls=Ls, boot=False))
compare("5.2", r52, base); wcsv("sens_52_sin_2_3Mbps.csv", [dict(test=t, **r) for t in r52 for r in r52[t]])
# ---------- 5.3 per session
P("\n5.3 PER SESSION (E4(c))")
cells = defaultdict(lambda: {1: [], 2: []})
for r in main:
    if r["platform"] == "IOU" and r["policy"] in ("CBWFQ", "LLQ") and r["exp"] in ("E1", "E1R", "CNEG"):
        cells[r["cell"]][int(r["session"])].append(r["p99f"])
rng = np.random.default_rng(20261016); ses = []
for cid, v in sorted(cells.items()):
    a, b = np.array(v[1]), np.array(v[2]); L = int([r for r in main if r["cell"] == cid][0]["L"])
    dlt = float(np.median(b) - np.median(a))
    bs = np.median(b[rng.integers(0, len(b), (10000, len(b)))], 1) - np.median(a[rng.integers(0, len(a), (10000, len(a)))], 1)
    ses.append(dict(cell=cid, n1=len(a), n2=len(b), median_s1=float(np.median(a)), median_s2=float(np.median(b)), delta_ses=dlt,
                    ci95=(float(np.quantile(bs, .025)), float(np.quantile(bs, .975))), EMI=C.EMI(L), exceeds_EMI=abs(dlt) > C.EMI(L)))
wcsv("sens_53_delta_sesion.csv", ses)
exc = [s for s in ses if s["exceeds_EMI"]]
P(f"  tested cells: {len(ses)}; |Delta_ses| > EMI in {len(exc)}:")
for s in exc:
    P(f"     {s['cell']}: s1 {s['median_s1']:.2f} s2 {s['median_s2']:.2f} delta {s['delta_ses']:+.2f} CI95 [{s['ci95'][0]:+.2f},{s['ci95'][1]:+.2f}] EMI {s['EMI']}")
for sn in (1, 2):
    rs = [r for r in main if int(r["session"]) == sn]
    res = C.all_tests(rs, boot=False)
    P(f"  session {sn} only (n per cell {'9' if sn == 1 else '8'}):"); compare(f"5.3 s{sn}", res, base)
# ---------- 5.4 battery originals instead of their _ac
P("\n5.4 WITH THE RUNS MEASURED ON BATTERY (originals instead of _ac)")
bat_rows = [r for r in allrows if r["ac"] != "True"]
res = C.all_tests(bat_rows, boot=False); compare("5.4", res, base)
byid = {r["run"]: r for r in allrows}; pd_ = defaultdict(list)
for r in allrows:
    if r["ac"] == "True":
        o = byid[r["run"][:-3]]; pd_[o["cell"]].append(o["p99f"] - r["p99f"])
alld = [x for v in pd_.values() for x in v]
from scipy import stats as SS
P(f"  paired original - _ac p99 over {len(alld)} runs in {len(pd_)} cells: median {np.median(alld):+.3f} ms, positive {sum(x > 0 for x in alld)}, "
  f"negative {sum(x < 0 for x in alld)}, sign test p = {SS.binomtest(sum(x > 0 for x in alld), sum(x != 0 for x in alld)).pvalue:.3g}")
wcsv("sens_54_bateria_por_celda.csv", [dict(cell=c, n=len(v), median_diff=float(np.median(v)), pos=sum(x > 0 for x in v), neg=sum(x < 0 for x in v),
                                            sign_p=SS.binomtest(sum(x > 0 for x in v), max(1, sum(x != 0 for x in v))).pvalue) for c, v in sorted(pd_.items())])
# ---------- 5.5 the 12 sporadic shaper failures
P("\n5.5 SPORADIC SHAPER FAILURES: failed attempt vs accepted replacement (voice p99, same window)")
if not os.path.isdir(os.path.join(CAMP, "_invalid")):
    P("  NOT COMPUTED: needs the raw archive (F4_campana/campaign/_invalid/); sens_55_shaper_esporadico.csv left unchanged")
else:
    SHAPER_EXEMPT = C.shaper_exempt()
    st = json.load(open(os.path.join(CAMP, "state.json"))); s55 = []
    for rid, lst in st["invalid"].items():
        for ai, att in enumerate(lst):
            if any(x.startswith("shaper rate") for x in att) and not any(p in rid for p in SHAPER_EXEMPT):
                for d in sorted(glob.glob(os.path.join(CAMP, "_invalid", f"{rid}_a*"))):
                    if any(x.startswith("shaper rate") for x in open(d + "/reason.txt").read().splitlines()) and os.path.exists(d + "/send_0.csv"):
                        m = json.load(open(d + "/meta.json")); p_f = LR.voice(d, m["cell"]["dur"])["p99"]
                        p_ok = byid[rid]["p99f"]; L = m["cell"]["L"]
                        s55.append(dict(run=rid, attempt=os.path.basename(d)[-2:], p99_failed=p_f, p99_accepted=p_ok, diff=p_f - p_ok, EMI=C.EMI(L),
                                        exceeds_EMI=abs(p_f - p_ok) > C.EMI(L), shaper_err_failed=m.get("shaper_err")))
    s55 = list({(x["run"], x["attempt"]): x for x in s55}.values())
    for x in sorted(s55, key=lambda x: x["run"]):
        P(f"  {x['run'][:52]:52s} {x['attempt']} p99 failed {x['p99_failed']:8.2f} accepted {x['p99_accepted']:8.2f} diff {x['diff']:+8.2f} "
          f"(EMI {x['EMI']}) {'> EMI' if x['exceeds_EMI'] else ''} shaper_err {x['shaper_err_failed']}")
    P(f"  attempts: {len(s55)}; |diff| > EMI: {sum(x['exceeds_EMI'] for x in s55)}")
    wcsv("sens_55_shaper_esporadico.csv", s55)
# ---------- 5.6 run during the 15-10 automatic upgrade
P("\n5.6 RUN DURING THE 15-10 UPGRADE (E2 IOU LLQ 5 Mbit/s k=3 r10): H2 of that cell with and without it")
g = C.paired(idx, lambda r: r["exp"] == "E2" and r["Li"] == 5000000 and r["calls"] == "1" and r["frame"] == "1514", C.IOU("CBWFQ"), C.IOU("LLQ"))
v = list(g.values())[0]
for lab_, vv in (("with", v), ("without r10", [x for x in v if x[0] != 10])):
    d = np.array([x[1] - x[2] for x in vv])
    P(f"  {lab_}: n {len(d)} median Delta {np.median(d):.2f} p_signperm {S.signperm_exact(d, 'greater'):.3g}")
# ---------- 5.7 S and S-H against their E1 base cell
P("\n5.7 S AND S-H vs BASE E1 CELL (k=3, same L, policy): difference of medians with 95% bootstrap CI; H2 within each IOU variant")
s57 = []; rng = np.random.default_rng(20261020)
cellp = defaultdict(list)
for r in main:
    if r["floor"] != "True":
        cellp[r["cell"]].append(r)
for cid, v in sorted(cellp.items()):
    r0 = v[0]
    if r0["exp"] not in ("S", "SH"):
        continue
    basecid = f"E1_{r0['platform']}_{r0['policy']}_L{r0['Li']//1000}k_k3_m0.2_c1_f1514"
    a = np.array([x["p99f"] for x in v]); b = np.array([x["p99f"] for x in cellp[basecid]])
    bs = np.median(a[rng.integers(0, len(a), (10000, len(a)))], 1) - np.median(b[rng.integers(0, len(b), (10000, len(b)))], 1)
    s57.append(dict(cell=cid, base=basecid, median_variant=float(np.median(a)), median_base=float(np.median(b)), diff=float(np.median(a) - np.median(b)),
                    ci95=(float(np.quantile(bs, .025)), float(np.quantile(bs, .975))), EMI=C.EMI(r0["Li"])))
for x in s57:
    P(f"  {x['cell'][:52]:52s} median {x['median_variant']:8.2f} vs base {x['median_base']:8.2f}: diff {x['diff']:+7.2f} [{x['ci95'][0]:+.2f},{x['ci95'][1]:+.2f}]")
wcsv("sens_57_S_SH.csv", s57)
P("  H2 (CBWFQ vs LLQ) within each IOU S/S-H variant:")
for (blk, rep), d in []:
    pass
gS = C.paired(idx, lambda r: r["exp"] in ("S", "SH"), C.IOU("CBWFQ"), C.IOU("LLQ"))
for blk, v in sorted(gS.items()):
    d = np.array([x[1] - x[2] for x in v]); p = S.signperm_exact(d, "greater")
    basedec = [r["decision"] for r in base["H2"] if r["family"] == "H2 E1 k=3" and r["L"] == v[0][3]["Li"]][0]
    dec = "Delta>0" if p < 0.05 else "not shown"
    P(f"    {blk:40s} median Delta {np.median(d):8.2f} p_signperm {p:.3g} -> {dec} (base E1 k=3: {basedec})")
    if dec != basedec:
        CHANGES.append(("5.7", blk, basedec, dec))
P("\nCONCLUSION CHANGES (any sensitivity): " + (f"{len(CHANGES)}" if CHANGES else "none"))
for c in CHANGES:
    P(f"  {c}")
open(os.path.join(RES, "SENSIBILIDAD.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
