"""Reusable test functions (same definitions as confirm.py, analysis plan v2 §2) for sensitivity and exploratory runs.
Every function takes a list of run rows (dicts from runs.csv) and returns records with the decision of each test.
core.py must reproduce confirm.py exactly on the main rows (checked in sens.py)."""
import math
from collections import defaultdict
import numpy as np
import stats_lib as S

T = lambda x: x is True or x == "True"
fnum = lambda x: float(x) if x not in ("", "None", None) else None
EMI = lambda L: 3.02 if L == 500000 else 2.00
Ts = lambda L, frame=1514: frame * 8 / L * 1000.0
Tvoz = lambda L: 214 * 8 / L * 1000.0
Tr = lambda m, calls=1: 214 * 8 / (calls * 85.6e3 * (1 + m)) * 1000.0
SEED_CELL, SEED_H3 = 20261020, 20261021


def prep(rows):
    for r in rows:
        r["Li"] = int(r["L"]); r["p99f"] = float(r["p99"]); r["repi"] = int(r["rep"])
    return rows


def index(rows):
    idx = defaultdict(dict)
    for r in rows:
        if not T(r["floor"]):
            idx[(r["block"], r["repi"])][(r["platform"], r["policy"])] = r
    return idx


def paired(idx, filt, a, b, var="p99f"):
    out = defaultdict(list)
    for (blk, rep), d in idx.items():
        if a in d and b in d and filt(d[a]):
            out[blk].append((rep, d[a].get(var), d[b].get(var), d[a], d[b]))
    return {k: sorted(v, key=lambda x: x[0]) for k, v in out.items()}


def lab(r):
    return f"{r['exp']} L={r['Li']//1000}k k={r['k']}" + (f" m={r['m']}" if float(r["m"]) != 0.2 else "") + \
        (f" frame={r['frame']}" if r["frame"] != "1514" else "") + (f" calls={r['calls']}" if r["calls"] != "1" else "")


IOU = lambda p: ("IOU", p)


def _tost_family(groups, fam, pair_filter=None, boot=True):
    recs = []
    for blk, v in groups.items():
        if pair_filter:
            v = [x for x in v if pair_filter(x)]
        if len(v) < 3:
            continue
        d = np.array([x[1] - x[2] for x in v]); L = v[0][3]["Li"]; t = S.tost_paired(d, -EMI(L), EMI(L))
        rec = dict(family=fam, cell=lab(v[0][3]), L=L, n=len(d), mean_d=t["mean"], ci90_lo=t["ci90"][0], ci90_hi=t["ci90"][1],
                   median_d=float(np.median(d)), margin=EMI(L), p_tost=t["p"])
        if boot:
            rec["boot95_median"] = S.boot_ci(d, B=10000, seed=SEED_CELL)
        recs.append(rec)
    for r, a in zip(recs, S.holm([r["p_tost"] for r in recs])):
        r["p_holm"] = a; r["decision"] = "equivalent" if a < 0.05 else "not equivalent"
    return sorted(recs, key=lambda r: (r["L"], r["cell"]))


def h1(idx, Ls=None, pair_filter=None, boot=True):
    g = paired(idx, lambda r: r["exp"] == "E1" and r["k"] == "1" and (Ls is None or r["Li"] in Ls), IOU("CBWFQ"), IOU("LLQ"))
    return _tost_family(g, "H1 E1 k=1", pair_filter, boot)


def cneg(idx, Ls=None, pair_filter=None, boot=True):
    out = []
    for k in ("1", "3"):
        g = paired(idx, lambda r, k=k: r["exp"] == "CNEG" and r["k"] == k and (Ls is None or r["Li"] in Ls), IOU("CBWFQ"), IOU("LLQ"))
        out += _tost_family(g, f"CNEG k={k}", pair_filter, boot)
    return out


def h2(idx, Ls=None, pair_filter=None, boot=True):
    out = []
    for fam, filt in (("H2 E1 k=2", lambda r: r["exp"] == "E1" and r["k"] == "2"), ("H2 E1 k=3", lambda r: r["exp"] == "E1" and r["k"] == "3"),
                      ("H2 E2 k=3", lambda r: r["exp"] == "E2")):
        g = paired(idx, lambda r, filt=filt: filt(r) and (Ls is None or r["Li"] in Ls), IOU("CBWFQ"), IOU("LLQ")); recs = []
        for blk, v in g.items():
            if pair_filter:
                v = [x for x in v if pair_filter(x)]
            if len(v) < 3:
                continue
            d = np.array([x[1] - x[2] for x in v])
            rec = dict(family=fam, cell=lab(v[0][3]), L=v[0][3]["Li"], n=len(d), mean_delta=float(d.mean()), median_delta=float(np.median(d)),
                       cliff_delta=S.cliff_delta([x[1] for x in v], [x[2] for x in v]),
                       p_signperm=S.signperm_exact(d, "greater") if len(d) <= 20 else None, p_wilcoxon=S.wilcoxon(d, "greater"))
            if boot:
                rec["boot95_median"] = S.boot_ci(d, B=10000, seed=SEED_CELL)
            recs.append(rec)
        for r, a in zip(recs, S.holm([r["p_signperm"] for r in recs])):
            r["p_holm"] = a; r["decision"] = "Delta>0" if a < 0.05 else "not shown"
        out += sorted(recs, key=lambda r: r["cell"])
    return out


def h3(idx, B=10000, seed=SEED_H3):
    cells = sorted({(r["Li"], float(r["m"])) for d in idx.values() for (pl, po), r in d.items()
                    if pl == "IOU" and po == "CBWFQ" and r["k"] == "3" and ((r["exp"] == "E1" and float(r["m"]) == 0.2) or r["exp"] == "E1R")})
    rng = np.random.default_rng(seed); out = {}
    for model in ("p99_CBWFQ", "Delta"):
        X, y, gi = [], [], []
        for ci, (L, m) in enumerate(cells):
            exp = "E1" if m == 0.2 else "E1R"
            g = paired(idx, lambda r, L=L, m=m, exp=exp: r["exp"] == exp and r["k"] == "3" and r["Li"] == L and float(r["m"]) == m, IOU("CBWFQ"), IOU("LLQ"))
            for rep, a, b, *_ in list(g.values())[0]:
                X.append([Ts(L), Tr(m), 1.0]); y.append(a if model == "p99_CBWFQ" else a - b); gi.append(ci)
        X, y, gi = np.array(X), np.array(y), np.array(gi); grp = [np.where(gi == c)[0] for c in range(len(cells))]
        beta = S.ols(X, y); bc = np.empty((B, 3))
        bw = np.empty((B, 3))
        for i in range(B):
            ix = np.concatenate([rng.choice(g_, len(g_)) for g_ in grp]); bw[i] = S.ols(X[ix], y[ix])
            cc = rng.integers(0, len(cells), len(cells)); ix = np.concatenate([grp[c] for c in cc]); bc[i] = S.ols(X[ix], y[ix])
        qc = np.quantile(bc, [.025, .975], axis=0); ref = (1.0, 2.0) if model == "p99_CBWFQ" else (0.0, 2.0)
        out[model] = dict(n=len(y), a=float(beta[0]), b=float(beta[1]), c=float(beta[2]), a_ci_cluster=qc[:, 0].tolist(), b_ci_cluster=qc[:, 1].tolist(),
                          decision=("reference in cluster CI" if (qc[0, 0] <= ref[0] <= qc[1, 0] and qc[0, 1] <= ref[1] <= qc[1, 1])
                                    else "reference outside cluster CI"))
    return out


def h4(idx, pair_filter=None, boot=True):
    out = []
    for fam, filt in [(f"H4 E1 k={k}", (lambda r, k=k: r["exp"] == "E1" and r["k"] == k and r["Li"] <= 5000000)) for k in ("1", "2", "3")] + \
                     [("H4 E2 k=3", lambda r: r["exp"] == "E2")]:
        recs = []
        for X_ in ("FQC", "CAKE"):
            g = paired(idx, filt, ("LXR", X_), IOU("LLQ"))
            for blk, v in g.items():
                if pair_filter:
                    v = [x for x in v if pair_filter(x)]
                if len(v) < 3:
                    continue
                d = np.array([x[1] - x[2] for x in v]); L = v[0][3]["Li"]; t = S.tost_paired(d, -EMI(L), EMI(L))
                rec = dict(family=fam, policy=X_, cell=lab(v[0][3]), L=L, n=len(d), mean_d=t["mean"], median_d=float(np.median(d)), margin=EMI(L), p_tost=t["p"])
                if boot:
                    rec["boot95_median"] = S.boot_ci(d, B=10000, seed=SEED_CELL)
                recs.append(rec)
        for r, a in zip(recs, S.holm([r["p_tost"] for r in recs])):
            r["p_holm"] = a; r["decision"] = "comparable" if a < 0.05 else "not comparable"
        out += sorted(recs, key=lambda r: (r["policy"], r["cell"]))
    return out


def h5(idx):
    recs = []
    for L in (1000000, 5000000):
        for role in ("data", "res"):
            g = paired(idx, lambda r, L=L: r["exp"] == "E3" and r["Li"] == L and r["voice_over"] in ("", "None"), IOU("LLQ"), IOU("CBWFQ"), var=f"gp_{role}")
            if not g:
                continue
            v = list(g.values())[0]; ok, starved = [], 0
            for rep, a, b, ra, rb in v:
                a, b = fnum(a), fnum(b)
                if not a or not b or T(ra.get(f"hambre_{role}")) or T(rb.get(f"hambre_{role}")):
                    starved += 1; continue
                ok.append(math.log(a / b))
            rec = dict(family="H5 E3", L=L, flow=role, n_pairs=len(v), starved_pairs=starved)
            if starved > 2 or len(ok) < 3:
                rec.update(evaluable=False, p_tost=None)
            else:
                t = S.tost_paired(np.array(ok), math.log(0.95), math.log(1.05))
                rec.update(evaluable=True, n_used=len(ok), ratio_geomean=math.exp(t["mean"]), p_tost=t["p"])
            recs.append(rec)
    ev = [r for r in recs if r["evaluable"]]
    for r, a in zip(ev, S.holm([r["p_tost"] for r in ev])):
        r["p_holm"] = a; r["decision"] = "equivalent" if a < 0.05 else "not equivalent"
    for r in recs:
        r.setdefault("decision", "not evaluable")
    return recs


def all_tests(rows, boot=False, B_h3=10000, Ls=None, pair_filter=None):
    idx = index(rows)
    return dict(H1=h1(idx, Ls, pair_filter, boot), CNEG=cneg(idx, Ls, pair_filter, boot), H2=h2(idx, Ls, pair_filter, boot),
                H3=h3(idx, B=B_h3), H4=h4(idx, pair_filter, boot), H5=h5(idx))


def shaper_exempt():
    """SHAPER_EXEMPT read from campaign.py without importing it (importing needs the GNS3 server)."""
    import ast, os
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "F2_viabilidad", "scripts", "campaign.py")
    for node in ast.parse(open(src).read()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SHAPER_EXEMPT" for t in node.targets):
            ns = {}
            exec(compile(ast.Module([node], []), src, "exec"), ns)
            return ns["SHAPER_EXEMPT"]
    raise RuntimeError("SHAPER_EXEMPT not found in campaign.py")
