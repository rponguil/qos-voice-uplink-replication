"""Bench topology for the paper (vector PDF + PNG), no internal title. Output: results/paper_fig0_topologia.{pdf,png}"""
import os
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
TXT, TXT2, EDGE, FILL, SURF = "#0b0b0b", "#52514e", "#8a8984", "#f3f2ee", "#ffffff"
C_TS, C_CAP, C_Q = "#2a78d6", "#eb6834", "#1baf7a"   # timestamp, capture, queue/counters markers
fig, ax = plt.subplots(figsize=(9.6, 4.9)); ax.set_xlim(0, 100); ax.set_ylim(0, 52); ax.axis("off")
fig.patch.set_facecolor(SURF)


def box(x, y, w, h, title, lines=(), dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2", fc=FILL, ec=EDGE, lw=1.1, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y + h - 1.6, title, ha="center", va="top", fontsize=8.2, color=TXT, weight="bold")
    for i, l in enumerate(lines):
        ax.text(x + w / 2, y + h - 4.4 - 2.5 * i, l, ha="center", va="top", fontsize=6.6, color=TXT2)


def arrow(x0, y0, x1, y1, dashed=False, label=None, lx=0, ly=0):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=9, lw=1.0, color=EDGE, ls="--" if dashed else "-"))
    if label:
        ax.text((x0 + x1) / 2 + lx, (y0 + y1) / 2 + ly, label, fontsize=6.2, color=TXT2, ha="center")


def mark(x, y, kind, label, dx=1.2, ha="left"):
    col = {"ts": C_TS, "cap": C_CAP, "q": C_Q}[kind]; mk = {"ts": "o", "cap": "s", "q": "D"}[kind]
    ax.plot(x, y, marker=mk, ms=6, color=col, markeredgecolor=SURF, markeredgewidth=0.8, zorder=5)
    ax.text(x + (dx if ha == "left" else -dx), y, label, fontsize=6.1, color=col, va="center", ha=ha)


# endpoints
box(1, 37, 15, 11, "CW-VOZ", ("VLAN 10", "voice G.711, EF", "(1 or 4 calls)"))
box(1, 21.5, 15, 11, "CW-DAT", ("VLAN 10", "video UDP, AF41 (k ≥ 2)", "data TCP, AF21 (k = 3)"))
box(1, 6, 15, 11, "RES-1", ("VLAN 20", "residential TCP + UDP", "unmarked (k ≥ 1)"))
mark(9.5, 36.2, "ts", "send time in payload", dx=0.9); mark(9.5, 34.6, "cap", "capture", dx=0.9)
mark(9.5, 20.7, "cap", "TCP capture", dx=0.9); mark(9.5, 5.2, "cap", "TCP capture", dx=0.9)
# switch
box(22, 19, 11, 14, "Switch", ("GNS3 Ethernet", "switch", "802.1Q trunk", "to LXR"))
for y in (42.5, 27, 11.5):
    arrow(16.3, y, 21.8, 26)
# routers
box(40, 35, 22, 14, "R-BORDE (IOU)", ("IOS 15.5(2)T", "access e0/0 (VLAN 10), e0/2 (VLAN 20)", "WAN e0/1: PARENT shape R = 0.95·L,", "Bc = R·4 ms, Be = 0; CHILD policy"))
box(40, 18.5, 22, 13, "LXR (Linux tc)", ("eth0.10 / eth0.20 (trunk)", "eth1: HTB at R + pfifo / fq_codel,", "or CAKE diffserv4 at R"))
box(40, 3, 22, 12, "C7200 (Dynamips)", ("IOS 15.3(3)XB12, no idle-PC", "E4(b) only, 1 Mbit/s", "same policy as R-BORDE"), dashed=True)
mark(58.5, 34.2, "q", "policy counters", dx=1.0); mark(58.5, 17.7, "q", "tc -s stats", dx=1.0)
arrow(33.3, 30, 39.7, 41); ax.text(27.5, 35.5, "one branch\nactive per run", fontsize=6.2, color=TXT2, ha="center"); arrow(33.3, 26, 39.7, 25); arrow(33.3, 22, 39.7, 9, dashed=True)
# modem and sink
box(68, 17, 15, 18, "MODEM", ("netem rate = L", "(0.5-10 Mbit/s)", "queue 64 packets", "backlog sampled", "every 20 ms"))
mark(75.5, 16.2, "q", "queue backlog", dx=1.0)
for y in (42, 25, 9):
    arrow(62.3, y, 67.7, 26, dashed=(y == 9))
box(88, 19.5, 11, 13, "SINK", ("203.0.113.2", "probe receiver", "iperf3 server"))
arrow(83.3, 26, 87.7, 26, label="uplink", ly=1.0)
mark(90.5, 18.2, "ts", "kernel RX time", dx=1.0); mark(90.5, 16.4, "cap", "capture", dx=1.0)
# legend + clock note
ax.plot(69, 4.2, "o", color=C_TS, ms=6); ax.text(70.3, 4.2, "timestamp (one host clock)", fontsize=6.4, color=TXT2, va="center")
ax.plot(69, 2.2, "s", color=C_CAP, ms=6); ax.text(70.3, 2.2, "packet capture (tcpdump)", fontsize=6.4, color=TXT2, va="center")
ax.plot(86, 4.2, "D", color=C_Q, ms=6); ax.text(87.3, 4.2, "queue / policy counters", fontsize=6.4, color=TXT2, va="center")
ax.text(85.4, 2.2, "single host", fontsize=6.4, color=TXT2, va="center")
fig.tight_layout(pad=0.2)
fig.savefig(os.path.join(RES, "paper_fig0_topologia.pdf"), metadata={"CreationDate": None}); fig.savefig(os.path.join(RES, "paper_fig0_topologia.png"), dpi=300)
print("ok")
