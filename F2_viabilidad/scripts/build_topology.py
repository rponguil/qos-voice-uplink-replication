"""Create the reduced F2 topology in GNS3 (project QoS_F2_viabilidad)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g

NAME = "QoS_F2_viabilidad"
CFG = os.path.join(os.path.dirname(__file__), "..", "configs")
IOU = "/home/ronald-ponguillo/GNS3/images/IOU/"
p = g.project(NAME) or g.post("/projects", {"name": NAME})
pid = p["project_id"]
if p["status"] != "opened":
    g.post(f"/projects/{pid}/open")
have = g.nodes(pid)

def node(name, ntype, props, x, y):
    if name in have:
        return have[name]
    return g.post(f"/projects/{pid}/nodes", {"name": name, "node_type": ntype,
                  "compute_id": "local", "x": x, "y": y, "properties": props})

R = node("R-BORDE", "iou", {"path": IOU + "i86bi-linux-l3-adventerprisek9-ms.155-2.T.bin",
         "ethernet_adapters": 1, "serial_adapters": 0, "ram": 512,
         "startup_config_content": open(f"{CFG}/R-BORDE_base.cfg").read()}, 0, 0)
# GNS3 built-in Ethernet switch (ubridge). The IOU L2 image was dropped on 2026-10-09:
# it capped forwarding at ~380 pkt/s and, after a 20 Mbit/s burst, exhausted its Big/VeryBig
# buffers and silently dropped every frame >= ~1000 B (results/hallazgo_iou_l2/).
SW = node("SW", "ethernet_switch", {"ports_mapping": [
    {"name": "Ethernet0", "port_number": 0, "type": "dot1q", "vlan": 1},
    {"name": "Ethernet1", "port_number": 1, "type": "access", "vlan": 10},
    {"name": "Ethernet2", "port_number": 2, "type": "access", "vlan": 10},
    {"name": "Ethernet3", "port_number": 3, "type": "access", "vlan": 20}]}, -250, 0)
dk = {"image": "qos-endpoint:f2", "adapters": 1, "console_type": "none",
      "start_command": "sleep infinity"}
H = {n: node(n, "docker", dk, x, y) for n, x, y in
     [("CW-VOZ", -500, -150), ("CW-DAT", -500, 0), ("RES-1", -500, 150), ("SINK", 250, 0)]}

links = [(SW, 0, 0, R, 0, 0), (H["CW-VOZ"], 0, 0, SW, 0, 1), (H["CW-DAT"], 0, 0, SW, 0, 2),
         (H["RES-1"], 0, 0, SW, 0, 3), (R, 0, 1, H["SINK"], 0, 0)]
existing = g.get(f"/projects/{pid}/links")
if not existing:
    for a, aa, ap, b, ba, bp in links:
        g.post(f"/projects/{pid}/links", {"nodes": [
            {"node_id": a["node_id"], "adapter_number": aa, "port_number": ap},
            {"node_id": b["node_id"], "adapter_number": ba, "port_number": bp}]})
# Linux router (2.10) is added afterwards by add_linux_router.py
print(pid, sorted(g.nodes(pid)), len(g.get(f"/projects/{pid}/links")), "links")
