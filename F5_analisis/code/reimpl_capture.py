"""EXPLORATORY §6.8: voice p99 and RFC 3550 jitter recomputed from the packet captures with independent code
(own pcap reader; no tcpdump, no campaign code). Output: results/REIMPLEMENTACION_CAPTURAS.txt"""
import csv, os, struct, sys
import numpy as np
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, "..", "results")
CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")


def read_pcap(path, dport=5001):
    """{seq: t} for UDP packets to dport whose payload flow id (first 2 bytes) is 100. Handles us and ns pcap, Ethernet + optional 802.1Q."""
    out = {}
    with open(path, "rb") as fh:
        gh = fh.read(24); magic = struct.unpack("<I", gh[:4])[0]
        if magic in (0xa1b2c3d4, 0xa1b23c4d):
            end = "<"
        else:
            end = ">"; magic = struct.unpack(">I", gh[:4])[0]
        div = 1e9 if magic == 0xa1b23c4d else 1e6
        while True:
            h = fh.read(16)
            if len(h) < 16:
                break
            ts, tf, incl, _ = struct.unpack(end + "IIII", h); b = fh.read(incl)
            off = 14; et = struct.unpack(">H", b[12:14])[0]
            if et == 0x8100:
                et = struct.unpack(">H", b[16:18])[0]; off = 18
            if et != 0x0800 or b[off + 9] != 17:
                continue
            ihl = (b[off] & 0x0F) * 4; u = off + ihl
            if struct.unpack(">H", b[u + 2:u + 4])[0] != dport:
                continue
            pl = b[u + 8:u + 14]
            if len(pl) < 6 or struct.unpack(">H", pl[:2])[0] != 100:
                continue
            out[struct.unpack(">I", pl[2:6])[0]] = ts + tf / div
    return out


def one(args):
    run, dur, p99_csv, jit_csv = args
    d = os.path.join(CAMP, run)
    try:
        s = read_pcap(f"{d}/src_voice.pcap"); r = read_pcap(f"{d}/sink.pcap")
    except Exception as e:
        return (run, None, None, p99_csv, jit_csv, repr(e))
    if not s:
        return (run, None, None, p99_csv, jit_csv, "no voice in capture")
    t0 = min(s.values()); seqs = sorted(q for q, t in s.items() if 20 <= t - t0 < dur and q in r)
    dl = np.array([(r[q] - s[q]) * 1000 for q in seqs]); ds = np.sort(dl)
    p99 = ds[min(len(ds) - 1, int(round(.99 * (len(ds) - 1))))]
    J = 0.0
    for i in range(1, len(dl)):
        J += (abs(dl[i] - dl[i - 1]) - J) / 16
    return (run, float(p99), J, p99_csv, jit_csv, None)


if __name__ == "__main__":
    rows = [r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True" and r["probe0_kind"] == "voice"]
    with ProcessPoolExecutor(8) as ex:
        res = list(ex.map(one, [(r["run"], int(r["dur"]), float(r["p99"]), float(r["jitter"])) for r in rows], chunksize=10))
    ok = [x for x in res if x[1] is not None]; bad = [x for x in res if x[1] is None]
    dp = np.array([abs(x[1] - x[3]) for x in ok]); dj = np.array([abs(x[2] - x[4]) for x in ok])
    lines = ["EXPLORATORY §6.8 — reimplementation from captures (own pcap reader) vs per-packet CSV of the probe",
             f"runs with voice: {len(rows)}; parsed: {len(ok)}; failed: {len(bad)} {bad[:3]}",
             f"p99: max |diff| {dp.max():.4f} ms, median {np.median(dp):.4f}, > 0.1 ms: {int(np.sum(dp > 0.1))}",
             f"jitter RFC 3550: max |diff| {dj.max():.4f} ms, median {np.median(dj):.4f}, > 0.1 ms: {int(np.sum(dj > 0.1))}",
             "worst p99: " + str(sorted(((round(a, 4), x[0]) for a, x in zip(dp, ok)), reverse=True)[:3]),
             "worst jitter: " + str(sorted(((round(a, 4), x[0]) for a, x in zip(dj, ok)), reverse=True)[:3])]
    open(os.path.join(RES, "REIMPLEMENTACION_CAPTURAS.txt"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
