"""Diagnostic: R-BORDE with one ingress interface per VLAN (no trunk).
SW port 0 -> access VLAN 10 (R-BORDE e0/0); new SW port 6 -> access VLAN 20 (R-BORDE e0/2). LXR/IOSV keep their trunks.
Stops all nodes, rewires, starts; then run configure_all.py and this script with --router to reconfigure R-BORDE."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g
pid = g.project("QoS_F2_viabilidad")["project_id"]
if "--router" not in sys.argv:
    g.post(f"/projects/{pid}/nodes/stop"); time.sleep(3)
    N = g.nodes(pid); sw = N["SW"]
    pm = [p for p in sw["properties"]["ports_mapping"] if p["port_number"] != 0]
    pm += [{"name": "Ethernet0", "port_number": 0, "type": "access", "vlan": 10},
           {"name": "Ethernet6", "port_number": 6, "type": "access", "vlan": 20}]
    saved = []
    for l in g.get(f"/projects/{pid}/links"):
        if any(x["node_id"] == sw["node_id"] for x in l["nodes"]):
            saved.append([{k: x[k] for k in ("node_id", "adapter_number", "port_number")} for x in l["nodes"]])
            g.delete(f"/projects/{pid}/links/{l['link_id']}")
    g.put(f"/projects/{pid}/nodes/{sw['node_id']}", {"properties": {"ports_mapping": sorted(pm, key=lambda p: p["port_number"])}})
    for ends in saved:
        g.post(f"/projects/{pid}/links", {"nodes": ends})
    g.post(f"/projects/{pid}/links", {"nodes": [{"node_id": sw["node_id"], "adapter_number": 0, "port_number": 6},
                                                {"node_id": N["R-BORDE"]["node_id"], "adapter_number": 0, "port_number": 2}]})
    g.post(f"/projects/{pid}/nodes/start"); time.sleep(5)
    print({n: v["status"] for n, v in g.nodes(pid).items()}, len(g.get(f"/projects/{pid}/links")), "links")
else:
    import f2lib as f
    f.configure(["no interface Ethernet0/0.10", "no interface Ethernet0/0.20",
                 "interface Ethernet0/0", "description VLAN10-COWORKING (access)", "ip address 192.168.10.1 255.255.255.0", "no keepalive", "no shutdown",
                 "interface Ethernet0/2", "description VLAN20-RESIDENCIAL (access)", "ip address 192.168.20.1 255.255.255.0", "no keepalive", "no shutdown"])
    print(f.show("show ip interface brief | include Ethernet"))
