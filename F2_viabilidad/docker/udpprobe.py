#!/usr/bin/env python3
"""Timestamped UDP probe flows (sender and receiver).

All GNS3 Docker nodes run on the same host kernel, so CLOCK_REALTIME is shared:
one-way delay = kernel receive timestamp - send timestamp carried in the payload.

Payload header (big endian): flow_id u16, seq u32, send_ns u64, then zero padding.

send: udpprobe.py send DST PORT --flow 1 --size 172 --interval 0.020 --count 1500 --dscp 46 --out send.csv
recv: udpprobe.py recv PORT --out recv.csv --duration 120 --idle 5
"""
import argparse, socket, struct, time, sys

HDR = struct.Struct("!HIQ")
SO_TIMESTAMPNS = getattr(socket, "SO_TIMESTAMPNS", 35)


def send(a):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, a.dscp << 2)
    pad = b"\x00" * max(0, a.size - HDR.size)
    out = open(a.out, "w") if a.out else None
    if out:
        out.write("flow,seq,send_ns\n")
    t0 = time.monotonic() + 0.05
    for seq in range(a.count):
        target = t0 + seq * a.interval
        while True:
            d = target - time.monotonic()
            if d <= 0:
                break
            time.sleep(d if d > 0.002 else 0)
        ns = time.time_ns()
        s.sendto(HDR.pack(a.flow, seq, ns) + pad, (a.dst, a.port))
        if out:
            out.write(f"{a.flow},{seq},{ns}\n")
    if out:
        out.close()


def recv(a):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    s.bind(("0.0.0.0", a.port))
    s.settimeout(1.0)
    out = open(a.out, "w")
    out.write("flow,seq,send_ns,recv_ns,len\n")
    t_start = time.monotonic()
    end = t_start + a.duration
    n, last = 0, None
    while time.monotonic() < end:
        if (a.idle and last is not None and time.monotonic() - last > a.idle
                and time.monotonic() - t_start >= a.min_duration):   # never stop on idle before the sender has finished
            break
        try:
            data, anc, _, _ = s.recvmsg(65535, 64)
        except socket.timeout:
            continue
        last = time.monotonic()
        rns = None
        for lvl, typ, cd in anc:
            if lvl == socket.SOL_SOCKET and typ == SO_TIMESTAMPNS:
                sec, nsec = struct.unpack("qq", cd[:16])
                rns = sec * 1_000_000_000 + nsec
        if rns is None:
            rns = time.time_ns()
        if len(data) < HDR.size:
            continue
        f, q, sns = HDR.unpack_from(data)
        out.write(f"{f},{q},{sns},{rns},{len(data)}\n")
        n += 1
    out.close()
    print(f"received {n}", file=sys.stderr)


p = argparse.ArgumentParser()
sp = p.add_subparsers(dest="cmd", required=True)
ps = sp.add_parser("send")
ps.add_argument("dst"); ps.add_argument("port", type=int)
ps.add_argument("--flow", type=int, default=1)
ps.add_argument("--size", type=int, default=172)  # G.711 20 ms: 160 B voice + 12 B RTP
ps.add_argument("--interval", type=float, default=0.020)
ps.add_argument("--count", type=int, default=1500)
ps.add_argument("--dscp", type=int, default=46)
ps.add_argument("--out")
pr = sp.add_parser("recv")
pr.add_argument("port", type=int)
pr.add_argument("--out", required=True)
pr.add_argument("--duration", type=float, default=60, help="hard cap (s)")
pr.add_argument("--idle", type=float, default=0, help="stop after this many s without packets (0 = off)")
pr.add_argument("--min-duration", type=float, default=0, help="idle stop only after this many s (sender run length)")
a = p.parse_args()
send(a) if a.cmd == "send" else recv(a)
