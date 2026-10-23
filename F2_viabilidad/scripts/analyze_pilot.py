"""Apply the frozen P3a rules (protocol §10) to the pilot -> candidate P3b values.
Only applies the rules; where a rule is ambiguous it reports the alternatives for the authors to decide.
usage: python3 analyze_pilot.py [pilot_dir]
"""
import csv, glob, json, math, os, statistics as st, sys
from collections import defaultdict

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "F4_campana", "pilot")
runs = []
for d in sorted(glob.glob(os.path.join(D, "*_r[0-9][0-9]"))):
    try:
        m = json.load(open(d + "/meta.json")); s = json.load(open(d + "/summary.json"))
    except Exception:
        continue
    runs.append((d, m, s))
print(f"valid runs: {len(runs)}  invalid dirs: {len(glob.glob(os.path.join(D, '_invalid', '*')))}")


def owd(d, t_from, t_to=None):
    rows = list(csv.DictReader(open(d + "/recv_0.csv")))
    sends = [int(r["send_ns"]) for r in csv.DictReader(open(d + "/send_0.csv"))]
    t0 = min(sends)
    x = [(int(r["send_ns"]) - t0) / 1e9 for r in rows]
    y = [(int(r["recv_ns"]) - int(r["send_ns"])) / 1e6 for r in rows]
    return [b for a, b in zip(x, y) if a >= t_from and (t_to is None or a < t_to)]


def p99(v):
    v = sorted(v); return v[min(len(v) - 1, int(round(.99 * (len(v) - 1))))] if v else float("nan")


# ---- floors: amplitude of the p99 across runs, per (platform, L)
floor = defaultdict(list)
for d, m, s in runs:
    c = m["cell"]
    if c["floor"]:
        floor[(c["platform"], c["L"])].append(s["probe0"]["p99"])
amp = {k: (max(v) - min(v)) for k, v in floor.items()}
print("\nFLOOR p99 amplitude (ms) [platform, L]:")
for k in sorted(floor):
    print(f"  {k}: n={len(floor[k])} p99 median {st.median(floor[k]):.3f} amp {amp[k]:.3f}")

# ---- competition cells
cells = defaultdict(list)
for d, m, s in runs:
    c = m["cell"]
    if not c["floor"]:
        cells[c["id"]].append((d, m, s))

# EMI: max(2 ms, 10 % p99 LLQ at that L) -> alternatives by k
print("\nEMI = max(2 ms, 0.1 * median p99 of LLQ in the base cell: k = 3, m = 0.2, 1 call); k = 1 shown for reference:")
emi = {}
for cid, R in cells.items():
    c = R[0][1]["cell"]
    if c["policy"] == "LLQ" and c["exp"] == "E1" and c["platform"] == "IOU":
        med = st.median(r[2]["probe0"]["p99"] for r in R)
        emi[(c["L"], c["k"])] = max(2.0, 0.1 * med)
        print(f"  L={c['L']} k={c['k']}: median p99 LLQ {med:.2f} -> EMI {emi[(c['L'], c['k'])]:.2f} ms")
print("  NOTE: at 10 Mbit/s there is no LLQ (Cisco arms up to 5 Mbit/s): the EMI rule has no base cell there -> the authors decide.")

# ---- n per cell: two-sided, power 0.80, alpha 0.05 (Holm worst case reported too), noisiest cell SD
def n_needed(sd, delta, alpha=0.05, power=0.80):
    z = st.NormalDist().inv_cdf
    if sd == 0:
        return 2
    n = 2 * ((z(1 - alpha / 2) + z(power)) * sd / delta) ** 2   # two-sample, per group
    return math.ceil(n)
sds = {cid: st.stdev([r[2]["probe0"]["p99"] for r in R]) for cid, R in cells.items() if len(R) >= 2}
noisy = max(sds, key=sds.get) if sds else None
print("\nSD of p99 between runs per cell (ms):")
for cid in sorted(sds, key=sds.get, reverse=True):
    print(f"  {sds[cid]:7.3f}  {cid}")
if noisy:
    for k_, e in sorted(emi.items()):
        for a in (0.05, 0.05 / 6):
            print(f"  n for EMI {e:.2f} ms (L={k_[0]}, k={k_[1]}), SD {sds[noisy]:.3f} (noisiest: {noisy[:40]}), alpha {a:.4f}: {n_needed(sds[noisy], e, a)}")

if sds:
    exp_cells = {cid: v for cid, v in sds.items() if not cid.startswith("CNEG")}
    nz = max(exp_cells, key=exp_cells.get)
    print(f"  [information, not the rule] noisiest cell excluding the negative controls: {nz[:45]} SD {exp_cells[nz]:.3f} ms -> "
          + ", ".join(f"n(EMI {e:.2f}) = {max(10, n_needed(exp_cells[nz], e, 0.05 / 6))}" for e in sorted(set(emi.values()))))

# ---- warm-up: smallest multiple of 5 s after which 5-s window medians change <= floor amplitude
print("\nWARM-UP (per run: first multiple of 5 s after which consecutive 5-s medians differ <= floor amp):")
wu = []
for cid, R in cells.items():
    for d, m, s in R:
        c = m["cell"]; a = amp.get((c["platform"], c["L"]))
        if a is None:
            continue
        meds = []
        for t in range(0, c["dur"] - 5, 5):
            v = owd(d, t, t + 5)
            meds.append(st.median(v) if v else float("nan"))
        w = None
        for i in range(len(meds) - 1):
            if all(abs(meds[j + 1] - meds[j]) <= a for j in range(i, len(meds) - 1)):
                w = 5 * i; break
        wu.append((w if w is not None else c["dur"], cid))
if wu:
    print(f"  max over runs: {max(wu)[0]} s ({max(wu)[1][:50]}); distribution: {sorted(set(x for x, _ in wu))}")

# ---- duration rule computed with fixed warm-ups (information only; the frozen warm-up rule is above)
for Wfix in (5, 10, 20):
    worstf = []
    for cid, R in cells.items():
        e = emi.get((R[0][1]["cell"]["L"], 3)) or 2.0
        diffs = [abs(p99(owd(d, Wfix, Wfix + 40)) - p99(owd(d, Wfix))) for d, m, s_ in R if m["cell"]["dur"] >= 120]
        if diffs:
            worstf.append((st.median(diffs), max(diffs), e, cid))
    over = [w for w in worstf if w[0] > w[2]]
    print(f"[information] warm-up {Wfix} s: cells where median |p99(40 s) - p99(120 s)| > EMI: {len(over)}/{len(worstf)} "
          + "; ".join(f"{c_[:40]} {m_:.2f}>{e_:.2f}" for m_, mx_, e_, c_ in over[:6]))

# ---- duration: p99 over 40 s vs 120 s (after warm-up)
W = max(wu)[0] if wu else 5
print(f"\nDURATION (warm-up {W} s): |p99(40 s) - p99(120 s)| vs EMI")
worst = []
for cid, R in cells.items():
    diffs = []
    for d, m, s in R:
        if m["cell"]["dur"] < 120:
            continue
        diffs.append(abs(p99(owd(d, W, W + 40)) - p99(owd(d, W))))
    if diffs:
        worst.append((st.median(diffs), max(diffs), cid))
for md, mx, cid in sorted(worst, reverse=True)[:8]:
    print(f"  median {md:.3f} max {mx:.3f} ms  {cid[:55]}")

# ---- modem queue threshold, host load threshold, double path, run time
mb = [s.get("modem", {}).get("backlog_max_bytes") or 0 for d, m, s in runs]
print(f"\nMODEM queue: max observed {max(mb)} B -> threshold {max(mb) + 1514} B")
ld = [m.get("load1", 0) for d, m, s in runs] + [max(m.get("loadavg_end", [0])[0], m.get("loadavg_start", [0])[0]) for d, m, s in runs]
print(f"HOST load (1 min): max {max(ld):.2f} -> threshold {1.5 * max(ld):.2f}")
dp = [abs(m["voice_owd_capture_path"]["p99"] - s["probe0"]["p99"]) for d, m, s in runs if m.get("voice_owd_capture_path")]
print(f"DOUBLE PATH: max |p99 diff| {max(dp):.4f} ms over {len(dp)} runs")
wt = defaultdict(list)
for d, m, s in runs:
    wt[m["cell"]["dur"]].append(m.get("wall_s", 0))
print("RUN TIME (wall s): " + ", ".join(f"dur {k}s -> median {st.median(v):.0f} s (n={len(v)})" for k, v in wt.items()))

# ---- negative control (pilot confirmation)
print("\nNEGATIVE CONTROL (unmarked, L=1M, k=3): median p99 per policy")
for cid, R in cells.items():
    if R[0][1]["cell"]["exp"] == "CNEG":
        print(f"  {R[0][1]['cell']['policy']}: {st.median(r[2]['probe0']['p99'] for r in R):.2f} ms (n={len(R)})")

# ---- invalid runs per cell and policy
st_p = os.path.join(D, "state.json")
if os.path.exists(st_p):
    state = json.load(open(st_p))
    print("\nINVALID RUNS (attempts set aside, with reason) per cell:")
    per_pol = defaultdict(int)
    for rid, lst in sorted(state.get("invalid", {}).items()):
        cid = rid.rsplit("_r", 1)[0]
        pol = cid.split("_")[2]
        per_pol[pol] += len(lst)
        print(f"  {len(lst)} x {rid}: " + " | ".join(r[0][:110] for r in lst))
    tot = defaultdict(int)
    for d, m, s in runs:
        tot[m["cell"]["policy"]] += 1
    print("  by policy (invalid attempts / valid runs): " + ", ".join(f"{p}: {per_pol.get(p, 0)}/{tot[p]}" for p in sorted(tot)))

# ---- flagged runs (router input losses), pre-policy loss by class, voice loss after classification
print("\nFLAGGED RUNS (router input losses > 0) per cell, and pre-policy loss by class (sent - classified):")
flag_tab = defaultdict(lambda: [0, 0])
cmp_rows = []
for cid, R in sorted(cells.items()):
    c = R[0][1]["cell"]
    fl = [r for r in R if r[1].get("marcada")]; cl = [r for r in R if not r[1].get("marcada")]
    flag_tab[(c["platform"], c["policy"], c["marked"])][0] += len(fl)
    flag_tab[(c["platform"], c["policy"], c["marked"])][1] += len(R)
    pre = defaultdict(list); vloss = []
    for d, m, s in R:
        pc = m.get("per_class") or {}
        clsd = pc.get("classified") or {}
        if not c["marked"] or "total" in clsd:     # unmarked or single-queue policy: only totals are comparable
            tot_cls = clsd.get("total") if "total" in clsd else sum(v or 0 for v in clsd.values())
            if tot_cls is not None:
                pre["total"].append(sum((pc.get("sent") or {}).values()) - tot_cls)
        else:
            for k_, v in (pc.get("sent") or {}).items():
                cv = clsd.get(k_)
                if cv is not None:
                    pre[k_].append(v - cv)
        cv = clsd.get("voz") if c["marked"] else None; rv = (pc.get("received_at_sink") or {}).get("voz")
        if cv:
            vloss.append((cv - rv) / cv)
    line = f"  {cid[:52]}: flagged {len(fl)}/{len(R)} | pre-policy loss max per class {dict((k_, max(v)) for k_, v in pre.items())}"
    if vloss:
        line += f" | voice loss after classification max {max(vloss):.4f}"
    print(line)
    if fl and cl:
        e = emi.get((c["L"], 3)) or 2.0
        dmed = st.median(r[2]["probe0"]["p99"] for r in fl) - st.median(r[2]["probe0"]["p99"] for r in cl)
        cmp_rows.append((cid, len(fl), len(cl), dmed, e))
print("  by platform/policy (flagged / runs): " + ", ".join(f"{k[0]} {k[1]}{'' if k[2] else ' unmarked'}: {v[0]}/{v[1]}" for k, v in sorted(flag_tab.items())))
print("\nFLAGGED-RUNS CHECK: median p99 flagged - clean, per cell, vs EMI (STOP if |diff| > EMI):")
stop = False
for cid, nf, nc, dmed, e in cmp_rows:
    bad = abs(dmed) > e; stop |= bad
    print(f"  {'STOP ' if bad else 'ok   '}{cid[:52]}: {nf} flagged vs {nc} clean, diff {dmed:+.2f} ms, EMI {e:.2f} ms")
print("  RESULT:", "STOP AND ASK THE AUTHORS" if stop else "no cell exceeds the EMI" if cmp_rows else "no cell has both flagged and clean runs")
