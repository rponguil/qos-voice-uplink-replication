"""P3b from the repeated pilot with the rules fixed before the repeated pilot.
- n: paired TOST (CBWFQ - LLQ, paired by block/rep), exact t by simulation, SD of the paired difference of the
  voice p99 in 40-s windows ([5,45], [45,85], [80,120], pooled variance), alpha = 0.01 (Holm, 5 L), power 0.80,
  over the cells with an EMI-margin test (E1, E1-R, negative control CBWFQ/LLQ; not FIFO-C). Min 10, cap 30.
- n for H5: paired TOST on TCP goodput (data AF21 and residential) per 40-s window, E1 k = 3 at 1 and 5 Mbit/s,
  delta_c = 5 % of the CBWFQ goodput.
- warm-up: smallest W in {5, 10, 20} s with median over runs of |p99[W, W+40] - p99[80, 120]| < EMI in every
  tested cell (non-overlapping windows).
- IOU floors at 1 and 2 Mbit/s: which runs widen the range, and why (load, IOU CPU, time); median and IQR.
usage: python3 analyze_p3b.py [pilot_dir]
"""
import csv, glob, json, os, re, subprocess, sys, statistics as st
from collections import defaultdict
import numpy as np

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "F4_campana", "pilot")
EMI = {500000: 3.02}
emi = lambda L: EMI.get(L, 2.00)
WINDOWS = ((5, 45), (45, 85), (80, 120))
rng = np.random.default_rng(20261011)

runs = []
for d in sorted(glob.glob(os.path.join(D, "*_r[0-9][0-9]"))):
    m = json.load(open(d + "/meta.json")); s = json.load(open(d + "/summary.json"))
    runs.append((d, m, s))


def voice(d):
    t0 = min(int(r["send_ns"]) for r in csv.DictReader(open(d + "/send_0.csv")))
    return [((int(r["send_ns"]) - t0) / 1e9, (int(r["recv_ns"]) - int(r["send_ns"])) / 1e6) for r in csv.DictReader(open(d + "/recv_0.csv"))]


def p99w(v, a, b):
    x = sorted(y for t, y in v if a <= t < b)
    return x[min(len(x) - 1, int(round(.99 * (len(x) - 1))))] if x else float("nan")


def tost_n(sd, delta, alpha, power=0.80, nmax=60, sims=20000):
    """Smallest n with power >= target for a paired TOST, true difference 0, exact t by simulation."""
    from scipy import stats
    for n in range(3, nmax + 1):
        x = rng.normal(0, sd, size=(sims, n))
        mu = x.mean(1); se = x.std(1, ddof=1) / np.sqrt(n)
        tc = stats.t.ppf(1 - alpha, n - 1)
        pw = np.mean(((mu + delta) / se > tc) & ((mu - delta) / se < -tc))
        if pw >= power:
            return n, pw
    return None, None


def key(c):
    return (c["exp"], c["platform"], c["L"], c["k"], c["m"], c["marked"])


# ---- pairs CBWFQ/LLQ by rep for the tested cells
byk = defaultdict(dict)
for d, m, s in runs:
    c = m["cell"]
    if c["floor"] or c["policy"] not in ("CBWFQ", "LLQ"):
        continue
    byk[key(c)].setdefault(c["policy"], {})[m["rep"]] = d
print("=== n for the EMI-margin tests (paired CBWFQ - LLQ, voice p99 in 40-s windows) ===")
res_n = []
for k_, pol in sorted(byk.items()):
    if "CBWFQ" not in pol or "LLQ" not in pol:
        continue
    reps = sorted(set(pol["CBWFQ"]) & set(pol["LLQ"]))
    sds = []
    for a, b in WINDOWS:
        diffs = [p99w(voice(pol["CBWFQ"][r]), a, b) - p99w(voice(pol["LLQ"][r]), a, b) for r in reps]
        sds.append(st.stdev(diffs))
    pooled = float(np.sqrt(np.mean(np.square(sds))))
    e = emi(k_[2])
    n01, pw = tost_n(pooled, e, 0.01)
    res_n.append((n01, pooled, e, k_))
    print(f"  {k_[0]:4s} L={k_[2]/1e6:>4} k={k_[3]} m={k_[4]} {'marked' if k_[5] else 'UNMARKED'}: SD windows "
          f"{[round(x, 2) for x in sds]} pooled {pooled:.2f} ms, EMI {e:.2f} -> n(alpha 0.01) = {n01} (power {pw:.3f})")
worst = max(res_n, key=lambda r: (r[0] or 999))
print(f"  -> largest n: {worst[0]} (SD {worst[1]:.2f}, cell {worst[3]})")

# ---- H5: TCP goodput per 40-s window from the SINK capture (paired CBWFQ - LLQ)
print("\n=== n for H5 (paired TOST on TCP goodput, delta_c = 5 % of CBWFQ goodput) ===")


def goodput(d, port, a, b):
    res = subprocess.run(["tcpdump", "-tt", "-nn", "-r", d + "/sink.pcap", f"tcp dst port {port}"], capture_output=True, text=True)
    if res.returncode != 0:   # an unreadable capture is an error, not a goodput of 0
        raise RuntimeError(f"tcpdump cannot read {d}/sink.pcap: {res.stderr.strip()}")
    out = res.stdout
    ev = []
    for l in out.splitlines():
        mm = re.match(r"(\d+\.\d+) .* length (\d+)", l)
        if mm:
            ev.append((float(mm.group(1)), int(mm.group(2))))
    if not ev:
        return 0.0
    t0 = min(int(r["send_ns"]) for r in csv.DictReader(open(d + "/send_0.csv"))) / 1e9
    return sum(by for t, by in ev if a <= t - t0 < b) * 8 / (b - a)


h5 = []
for L in (1000000, 5000000):
    k_ = ("E1", "IOU", L, 3, 0.2, True)
    pol = byk.get(k_)
    if not pol:
        continue
    reps = sorted(set(pol["CBWFQ"]) & set(pol["LLQ"]))
    for name, port in (("datos", 5302), ("residencial", 5301)):
        sds, base = [], []
        for a, b in WINDOWS:
            gc = [goodput(pol["CBWFQ"][r], port, a, b) for r in reps]
            gl = [goodput(pol["LLQ"][r], port, a, b) for r in reps]
            sds.append(st.stdev([x - y for x, y in zip(gc, gl)])); base += gc
        pooled = float(np.sqrt(np.mean(np.square(sds)))); delta = 0.05 * st.mean(base)
        for alpha in (0.025, 0.01):
            n_, pw = tost_n(pooled, delta, alpha)
            h5.append((n_, name, L, alpha))
            print(f"  L={L/1e6} {name}: CBWFQ goodput {st.mean(base)/1e3:.1f} kbit/s, SD diff {pooled/1e3:.2f} kbit/s, "
                  f"delta_c {delta/1e3:.2f} kbit/s, alpha {alpha} -> n = {n_}")
n_h5 = max((x[0] or 999) for x in h5) if h5 else None
n_final = max(10, worst[0] or 999, n_h5 or 0)
print(f"\nn = max(10, n EMI tests, n H5) = {n_final}  ({'within' if n_final <= 30 else 'ABOVE'} the cap of 30)")

# ---- warm-up rule
print("\n=== warm-up: median over runs of |p99[W, W+40] - p99[80, 120]| < EMI in every tested cell ===")
tested = defaultdict(list)
for d, m, s in runs:
    c = m["cell"]
    if not c["floor"] and c["policy"] in ("CBWFQ", "LLQ"):
        tested[(c["exp"], c["policy"], c["L"], c["k"], c["m"], c["marked"])].append(d)
W_ok = None
for W in (5, 10, 20):
    worst_w = (0, None)
    bad = []
    for k_, ds in tested.items():
        med = st.median(abs(p99w(v, W, W + 40) - p99w(v, 80, 120)) for v in (voice(d) for d in ds))
        if med > worst_w[0]:
            worst_w = (med, k_)
        if med >= emi(k_[2]):
            bad.append((k_, round(med, 2)))
    print(f"  W={W:>2} s: worst median {worst_w[0]:.2f} ms ({worst_w[1]}); cells >= EMI: {bad}")
    if not bad and W_ok is None:
        W_ok = W
print(f"  -> W = {W_ok} s" if W_ok else "  -> no W satisfies the rule: STOP, the authors decide")

# ---- IOU floors at 1 and 2 Mbit/s
print("\n=== floors: median and IQR of the p99; runs that widen the range at IOU 1 and 2 Mbit/s ===")
fl = defaultdict(list)
for d, m, s in runs:
    c = m["cell"]
    if c["floor"]:
        fl[(c["platform"], c["L"])].append((s["probe0"]["p99"], s["probe0"]["max"], m.get("load1"), m.get("iou_cpu_frac"), m.get("t_start"), os.path.basename(d)))
for k_ in sorted(fl):
    p = sorted(x[0] for x in fl[k_]); q1, q3 = np.percentile(p, [25, 75])
    print(f"  {k_[0]} {k_[1]/1e6:>4} Mbit/s: median {st.median(p):.3f} IQR [{q1:.3f}, {q3:.3f}] range [{p[0]:.3f}, {p[-1]:.3f}]")
    if k_[0] == "IOU" and k_[1] in (1000000, 2000000):
        med = st.median(p)
        for x in sorted(fl[k_], key=lambda x: -x[0]):
            flag = " <-- outlier" if x[0] - med > 0.3 else ""
            print(f"      p99 {x[0]:.3f} max {x[1]:.2f} load1 {x[2]} iou_cpu {x[3]} start {x[4]} {x[5][-3:]}{flag}")
