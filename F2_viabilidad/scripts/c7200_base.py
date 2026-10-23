"""Base configuration of C7200 (Dynamips) (same options as R-BORDE: CEF, no CDP, no keepalive), via its console."""
import re, sys, time, os
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g, f2lib as f

c = g.Console(f.CONSOLE["C7200"])
t0 = time.time(); buf = ""
while time.time() - t0 < 600:                       # wait for boot
    c.s.sendall(b"\r"); buf = c._read(3.0)
    if "initial configuration dialog" in buf:
        c.s.sendall(b"no\r"); time.sleep(5); continue
    if re.search(r"[>#]\s*$", buf.strip() + " "):
        break
print("C7200 prompt after", round(time.time() - t0), "s:", buf.strip()[-40:])
c.cmd("enable"); c.cmd("terminal length 0")
f._con["C7200"] = c
cfg = ["hostname C7200", "no ip domain lookup", "ip cef", "no cdp run",
       "interface FastEthernet0/0", "no ip address", "no keepalive", "duplex full", "no shutdown",
       "interface FastEthernet0/0.10", "encapsulation dot1Q 10", "ip address 192.168.10.4 255.255.255.0",
       "interface FastEthernet0/0.20", "encapsulation dot1Q 20", "ip address 192.168.20.4 255.255.255.0",
       "interface FastEthernet1/0", "ip address 10.0.4.1 255.255.255.252", "no keepalive", "duplex full", "no shutdown",
       "interface FastEthernet1/1", "shutdown", "exit",
       "ip route 0.0.0.0 0.0.0.0 10.0.4.2",
       "line con 0", "exec-timeout 0 0", "logging synchronous"]
f.configure(cfg, name="C7200")
c.cmd("write memory", timeout=30)
print(f.show("show version | include IOS|uptime", name="C7200"))
print(f.show("show ip interface brief", name="C7200"))
