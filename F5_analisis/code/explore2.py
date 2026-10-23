"""EXPLORATORY: collapses vs TCP; Bc/Be/Tc applied by IOS; real queue limits; Q034 mean delay and jitter.
Output: results/EXPLORATORIO_TCP_SHAPER.txt, results/expl_colapso_tcp.csv"""
import csv, glob, json, os, re, struct, sys
from collections import defaultdict
import numpy as np
from scipy import stats as SS
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C
RES = os.path.join(HERE, "..", "results"); CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
out = []; P = out.append
P("EXPLORATORY. Tables only.")
main = C.prep([r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"])
cells = defaultdict(list)
for r in main:
    cells[r["cell"]].append(r)


def pcap_records(path):
    with open(path, "rb") as fh:
        gh = fh.read(24); mg = struct.unpack("<I", gh[:4])[0]
        end = "<" if mg in (0xa1b2c3d4, 0xa1b23c4d) else ">"
        mg = struct.unpack(end + "I", gh[:4])[0]; div = 1e9 if mg == 0xa1b23c4d else 1e6
        while True:
            h = fh.read(16)
            if len(h) < 16:
                return
            ts, tf, incl, _ = struct.unpack(end + "IIII", h); b = fh.read(incl)
            off = 14; et = struct.unpack(">H", b[12:14])[0]
            if et == 0x8100:
                et = struct.unpack(">H", b[16:18])[0]; off = 18
            if et != 0x0800:
                continue
            yield ts + tf / div, b, off


def tcp_segments(path, dport):
    """{(sport, seq): t} first occurrence of TCP data segments (payload > 0) to dport."""
    res = {}
    for t, b, off in pcap_records(path):
        if b[off + 9] != 6:
            continue
        ihl = (b[off] & 0x0F) * 4; tot = struct.unpack(">H", b[off + 2:off + 4])[0]; u = off + ihl
        sport, dp, seq = struct.unpack(">HHI", b[u:u + 8]); doff = (b[u + 12] >> 4) * 4
        if dp != dport or tot - ihl - doff <= 0:
            continue
        res.setdefault((sport, seq), t)
    return res


def voice_series(run):
    d = os.path.join(CAMP, run)
    t0 = min(int(x["send_ns"]) for x in csv.DictReader(open(f"{d}/send_0.csv")))
    v = np.array(sorted(((int(x["send_ns"]) - t0) / 1e9, (int(x["recv_ns"]) - int(x["send_ns"])) / 1e6) for x in csv.DictReader(open(f"{d}/recv_0.csv"))))
    return t0 / 1e9, v[(v[:, 0] >= 20) & (v[:, 0] < 60)]


def r_tcp(run, src_pcap, dport):
    d = os.path.join(CAMP, run); t0, v = voice_series(run)
    s = tcp_segments(f"{d}/{src_pcap}", dport); k = tcp_segments(f"{d}/sink.pcap", dport)
    pts = sorted((s[q] - t0, (k[q] - s[q]) * 1000) for q in s if q in k)
    pts = np.array([p for p in pts if 15 <= p[0] < 65])
    if len(pts) < 20:
        return None, len(pts)
    od = np.interp(v[:, 0], pts[:, 0], pts[:, 1])
    return (float(SS.pearsonr(v[:, 1], od)[0]) if np.std(od) > 0 else None), len(pts)


# ---------- 1. collapses vs TCP
corr = list(csv.DictReader(open(os.path.join(RES, "expl_colapso_correlacion.csv"))))
unexpl = [(x["cell"], int(x["rep"])) for x in corr if x["collapse"] == "True" and abs(float(x["r_res"] or 0)) < 0.5 and abs(float(x["r_video"] or 0)) < 0.5]
P(f"\n1. COLLAPSES WITHOUT RELATION TO RESIDENTIAL UDP OR VIDEO ({len(unexpl)}): voice delay vs TCP one-way delay per segment "
  "(own pcap reader: source capture vs SINK capture, first transmission of each (port, seq)), interpolated at voice send instants")
recs = []
for c in sorted({u[0] for u in unexpl}):
    m0 = json.load(open(os.path.join(CAMP, cells[c][0]["run"], "meta.json")))
    tcps = [(f["port"], "src_tcp_RES-1.pcap" if f["node"] == "RES-1" else "src_tcp_CW-DAT.pcap", "res TCP" if f["port"] == 5301 else "data TCP")
            for f in m0["flows"] if f["kind"] == "tcp"]
    for r in cells[c]:
        rec = dict(cell=c, rep=int(r["rep"]), collapse=(c, int(r["rep"])) in unexpl, loss_w=float(r["loss_w"]))
        for port, pc, lab in tcps:
            rv, n = r_tcp(r["run"], pc, port); rec[f"r_{lab}"] = rv; rec[f"n_{lab}"] = n
        recs.append(rec)
keys = list(dict.fromkeys(k for r in recs for k in r))
with open(os.path.join(RES, "expl_colapso_tcp.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(recs)
for c, rep in unexpl:
    x = next(r for r in recs if r["cell"] == c and r["rep"] == rep); others = [r for r in recs if r["cell"] == c and not r["collapse"]]
    parts = []
    for lab in ("res TCP", "data TCP"):
        if f"r_{lab}" in x:
            o = [r[f"r_{lab}"] for r in others if r.get(f"r_{lab}") is not None]
            parts.append(f"r(voice,{lab}) {x[f'r_{lab}'] if x[f'r_{lab}'] is None else round(x[f'r_{lab}'], 3)} (n seg {x[f'n_{lab}']}) "
                         f"[others median {np.median(o):.3f}, range {min(o):.3f}..{max(o):.3f}]" if o else f"r(voice,{lab}) {x[f'r_{lab}']}")
    P(f"  {c[:46]:46s} r{rep:02d} loss {x['loss_w']:.3f}: " + " | ".join(parts))

# ---------- 2. Bc, Be, Tc applied by IOS vs configured
P("\n2. SHAPER PARAMETERS APPLIED BY IOS ('show policy-map interface' after each run) vs CONFIGURED (Bc = ceil(R x 4 ms), Be = 0); Tc = Bc / CIR")
pat = re.compile(r"shape \(average\) cir (\d+), bc (\d+), be (\d+)")
for exp, pol, k in (("CPOS", "FIFO", "1"), ("E1", "LLQ", "3"), ("E1", "CBWFQ", "1")):
    for L in (500000, 1000000, 2000000, 3000000, 5000000):
        cid = f"{exp}_IOU_{pol}_L{L//1000}k_k{k}_m0.2_c1_f1514" + ("_pos" if exp == "CPOS" else "")
        vals = set()
        for r in cells[cid]:
            mm = pat.search(open(os.path.join(CAMP, r["run"], "router_post.txt")).read())
            vals.add(tuple(int(x) for x in mm.groups()) if mm else None)
        R = int(0.95 * L); bc_cfg = -(-R * 4 // 1000)
        txt = "; ".join(f"cir {v[0]} bc {v[1]} be {v[2]} -> Tc {1000*v[1]/v[0]:.2f} ms" for v in sorted(vals))
        P(f"  {cid[:40]:40s} configured cir {R} bc {bc_cfg} be 0 | applied ({len(cells[cid])} runs, {len(vals)} distinct): {txt} | "
          f"1514-B frame = {1514*8/(bc_cfg):.2f} Bc")

# ---------- 3. real queue limits
P("\n3. QUEUE LIMITS")
qc = set(); ql = set()
for r in cells["E1_IOU_FIFO_L1000k_k3_m0.2_c1_f1514"] + cells["E1_IOU_FIFO_L5000k_k3_m0.2_c1_f1514"]:
    mm = re.search(r"queue limit (\d+) packets", open(os.path.join(CAMP, r["run"], "router_post.txt")).read()); qc.add(mm.group(1) if mm else None)
for r in cells["E1_LXR_FIFO_L1000k_k3_m0.2_c1_f1514"] + cells["E1_LXR_FIFO_L5000k_k3_m0.2_c1_f1514"]:
    mm = re.search(r"pfifo 10: parent 1:10 limit (\d+)p", open(os.path.join(CAMP, r["run"], "router_post.txt")).read()); ql.add(mm.group(1) if mm else None)
P(f"  FIFO-C (IOU PARENT class-default): queue limit {qc} packets (router_post.txt, E1 k=3 at 1 and 5 Mbit/s)")
P(f"  FIFO-L (LXR HTB leaf pfifo): limit {ql} packets")
P("  IOU Ethernet0/1 tx ring (queried on the bench 17-10-2026 23:1x with the PARENT policy attached, 'show controllers Ethernet0/1'): "
  "'tx ring entries=64', 'tx_limited=1(4)' (tx ring limited to 4 with the service policy); interface output queue 0/1000 (not used under class-based queueing)")

# ---------- 5. Q034 mean delay and jitter per policy
P("\n5. Q034 (E4(d)): voice mean one-way delay and mean RFC 3550 jitter per policy (both calls; window [20, 60) s); median over 17 runs [min-max]")
import load_runs as LR
for pol in ("FIFO", "CBWFQ", "LLQ"):
    cid = f"E4d_IOU_{pol}_L500k_k0_m0.2_c1_f1514_Q034"; row = []
    for i in (0, 1):
        means, jits = [], []
        for r in cells[cid]:
            d = os.path.join(CAMP, r["run"]); snd = list(csv.DictReader(open(f"{d}/send_{i}.csv")))
            rcv = {x["seq"]: x for x in csv.DictReader(open(f"{d}/recv_{i}.csv"))}; t0 = min(int(x["send_ns"]) for x in snd)
            win = [x for x in snd if 20e9 <= int(x["send_ns"]) - t0 < 60e9 and x["seq"] in rcv]
            dl = [(int(rcv[x["seq"]]["recv_ns"]) - int(x["send_ns"])) / 1e6 for x in sorted(win, key=lambda x: int(x["seq"]))]
            J = 0.0
            for a, b in zip(dl, dl[1:]):
                J += (abs(b - a) - J) / 16
            means.append(np.mean(dl)); jits.append(J)
        row.append(f"call {i+1}: mean {np.median(means):6.2f} [{min(means):.2f}-{max(means):.2f}] ms, jitter {np.median(jits):5.2f} [{min(jits):.2f}-{max(jits):.2f}] ms")
    P(f"  {pol:5s} " + " | ".join(row))
open(os.path.join(RES, "EXPLORATORIO_TCP_SHAPER.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
