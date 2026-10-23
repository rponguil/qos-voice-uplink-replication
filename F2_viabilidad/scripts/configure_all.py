"""Idempotent addressing of the whole F2 lab (run after every start). Platform IOU selected at the end."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import f2lib as f

def sh(n, c):
    f.dx(n, c)

for n, ip, gw in [("CW-VOZ", "192.168.10.11/24", "192.168.10.1"), ("CW-DAT", "192.168.10.12/24", "192.168.10.1"),
                  ("RES-1", "192.168.20.11/24", "192.168.20.1")]:
    sh(n, f"ip addr flush dev eth0; ip addr add {ip} dev eth0; ip link set eth0 up; ip route replace default via {gw}; "
          "ethtool -K eth0 gso off gro off tso off 2>/dev/null; true")   # no GSO/GRO bursts at the endpoints
sh("LXR", "sysctl -qw net.ipv4.ip_forward=1; ip link set eth0 up; "
          "ip link add link eth0 name eth0.10 type vlan id 10 2>/dev/null; ip link add link eth0 name eth0.20 type vlan id 20 2>/dev/null; "
          "ip addr flush dev eth0.10; ip addr add 192.168.10.2/24 dev eth0.10; ip link set eth0.10 up; "
          "ip addr flush dev eth0.20; ip addr add 192.168.20.2/24 dev eth0.20; ip link set eth0.20 up; "
          "ip addr flush dev eth1; ip addr add 10.0.2.1/30 dev eth1; ip link set eth1 up; ip route replace default via 10.0.2.2; "
          "ethtool -K eth0 gso off gro off tso off 2>/dev/null; ethtool -K eth1 gso off gro off tso off 2>/dev/null; true")
sh("MODEM", "sysctl -qw net.ipv4.ip_forward=1 net.ipv4.conf.all.rp_filter=0; "
            "ip addr flush dev eth0; ip addr add 10.0.1.2/30 dev eth0; ip link set eth0 up; "
            "ip addr flush dev eth1; ip addr add 10.0.2.2/30 dev eth1; ip link set eth1 up; "
            "ip addr flush dev eth2; ip addr add 203.0.113.1/30 dev eth2; ip link set eth2 up; "
            "(ip link show eth3 >/dev/null 2>&1 && ip addr flush dev eth3 && ip addr add 10.0.3.2/30 dev eth3 && ip link set eth3 up) ; "
            "(ip link show eth4 >/dev/null 2>&1 && ip addr flush dev eth4 && ip addr add 10.0.4.2/30 dev eth4 && ip link set eth4 up) ; "
            "for i in eth0 eth1 eth2 eth3 eth4; do ethtool -K $i gso off gro off tso off 2>/dev/null; done; true")
sh("SINK", "ip addr flush dev eth0; ip addr add 203.0.113.2/30 dev eth0; ip link set eth0 up; ip route replace default via 203.0.113.1; "
           "ip link set eth1 down 2>/dev/null; ethtool -K eth0 gso off gro off tso off 2>/dev/null; true")
f.configure(["interface Ethernet0/1", "ip address 10.0.1.1 255.255.255.252", "exit",
             "no ip route 0.0.0.0 0.0.0.0 10.0.1.2", "ip route 0.0.0.0 0.0.0.0 10.0.1.2"])
f.router().cmd("write memory", timeout=30)
f.set_line(None)
f.set_platform("IOU")
t = time.time()
while time.time() - t < 150 and " 1 received" not in f.dx("RES-1", "ping -c 1 -W 1 203.0.113.2", check=False):
    time.sleep(3)
for p in ("IOU", "LXR"):
    f.set_platform(p)
    print(p, [f.dx(n, "ping -c 2 -W 1 -s 1472 203.0.113.2 | grep -o '[0-9]* received'", check=False).strip()
              for n in ("CW-VOZ", "CW-DAT", "RES-1")])
f.set_platform("IOU")
