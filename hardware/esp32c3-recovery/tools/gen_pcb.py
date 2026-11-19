#!/usr/bin/env python3
"""Generate the esp32c3-recovery PCB (2 layers, all SMD on top, JLC Economic PCBA).

Stages (tools/pcb.sh runs them in order):
  place   build the unrouted board from out/netlist.net and export out/pcb/board.dsn
  finish  import the Freerouting session, add ground pours and silkscreen, save
  fab     write JLC outputs to out/jlc/ (gerbers + drill zip, BOM, CPL)

Placement lives in PLACE below; edit it, not the .kicad_pcb.
"""
import csv
import json
import math
import os
import re
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexp import find, findall, parse  # noqa: E402

PROJ = os.path.dirname(HERE)
NAME = "esp32c3-recovery"
PCB = os.path.join(PROJ, NAME + ".kicad_pcb")
NETLIST = os.path.join(PROJ, "out", "netlist.net")
WORK = os.path.join(PROJ, "out", "pcb")
FPLIB = os.path.join(PROJ, "esp32c3_recovery.pretty")
SYSFP = "/usr/share/kicad/footprints"

MM = pcbnew.FromMM

# Board outline (mm). Origin at (X0, Y0) so the page coordinates stay readable.
X0, Y0 = 100.0, 100.0
# Hammond 1551K (80 x 40 x 20 mm ABS box) "maximum P.C. board size": 74 x 34 mm
# with 6.25 mm notches at two opposite corners for the lid-screw posts, and two
# 2.5 mm holes over the box's PCB bosses (#2 self-tapping screws). Here the
# outline is 0.25 mm inside Hammond's maximum on every side; the holes stay on
# the bosses. Board coordinates = Hammond's drawing minus 0.25 mm.
W, H = 73.5, 33.5
NOTCH = 6.25                                     # top-right and bottom-left
OUTLINE = [(0, 0), (W - NOTCH, 0), (W - NOTCH, NOTCH), (W, NOTCH), (W, H),
           (NOTCH, H), (NOTCH, H - NOTCH), (0, H - NOTCH)]
R_OUT, R_IN = 1.0, 3.0     # corner radii: convex corners, and the two notch corners
#                            (R3 is the radius on Hammond's maximum-board drawing)


def on_board(x, y, m=0.0):
    """Point inside the notched outline with margin m."""
    if not (m < x < W - m and m < y < H - m):
        return False
    if x > W - NOTCH - m and y < NOTCH + m:
        return False
    return not (x < NOTCH + m and y > H - NOTCH - m)


# ref: (x, y, rotation_deg) relative to the board's top-left corner.
# U2 (ESP32-C3-WROOM-02, 18 x 20 mm, JLC-placed) lies on its side with the
# antenna end at the left edge, so the footprint's own antenna keep-out (5 mm
# round the antenna) falls on the left 6.3 mm of the board and off the edge.
# Rotated 90: footprint (lx, ly) -> board (MOD_X + ly, MOD_Y - lx): pins 10-18
# (IO10..IO0) run along the top, 1-9 (3V3, EN, IO4..IO9, GND) along the bottom.
MOD_ROT = 90
MOD_X, MOD_Y = 13.4, 16.75          # footprint origin
MOD_LY = (-13.1, 6.9)               # module body along its length (antenna end first)


def mod_rect(lx1, ly1, lx2, ly2):
    """Footprint-local rectangle of U2 -> board rectangle (x1, y1, x2, y2)."""
    xs = (MOD_X + ly1, MOD_X + ly2)
    ys = (MOD_Y - lx1, MOD_Y - lx2)
    return min(xs), min(ys), max(xs), max(ys)


PLACE = {
    "U2": (MOD_X, MOD_Y, MOD_ROT),
    # 3.3 V: AMS1117 under the top edge, VO tab up; C7 at its output, C8 at the
    # module's 3V3 pin (bottom-left)
    "U4": (26.0, 4.9, 90),
    "C7": (21.2, 3.0, 90),
    "C8": (7.4, 28.1, 270),       # 100n right below the module's 3V3 pin (pad 1 up)
    "C10": (8.6, 31.9, 0),        # 22u bulk under it
    # power: VBAT terminal -> F1 -> D1/C1 -> U1 -> C2/D2/C3 -> U4 (top band)
    "F1": (47.7, 2.5, 180),
    "D1": (47.7, 8.0, 180),
    "C1": (42.9, 3.0, 270),
    "U1": (38.35, 7.6, 270),
    "C2": (33.1, 3.0, 90),
    "C3": (31.0, 3.0, 90),
    "D2": (32.4, 8.0, 90),
    # module support: EN RC below pin 2 (clear of the pin-exit corridor under the
    # bottom row), IO9/IO8 pull-ups beside the switches, IO2 pull-up by pin 16
    "R8": (11.4, 30.0, 90),
    "C9": (13.2, 30.0, 90),
    "R11": (10.4, 5.3, 90),
    "R9": (30.9, 12.5, 90),
    "R10": (30.9, 16.5, 90),
    "SW1": (26.4, 12.25, 0),
    "SW2": (26.4, 17.95, 0),
    # USB-C (J6, CC resistors R12/R13) at the bottom edge, D4 into +5V; test pads
    "J6": (27.5, H - 4.17, 0),    # courtyard on the edge; mouth 0.5 mm inside it
    "R12": (34.0, 26.6, 90),
    "R13": (35.6, 26.6, 90),
    "D4": (36.2, 30.4, 0),
    "TP1": (22.4, 22.1, 0),
    "TP2": (25.0, 22.1, 0),
    "TP3": (27.6, 22.1, 0),
    "TP4": (30.2, 22.1, 0),
    "TP5": (32.8, 22.1, 0),
    "TP6": (35.4, 22.1, 0),
    # CAN transceiver next to the CANH/CANL terminals
    "U3": (46.4, 17.2, 0),
    "C5": (41.4, 16.2, 90),
    "R6": (41.4, 20.0, 90),
    "C6": (43.9, 22.2, 0),
    # press sense and press drive
    "R5": (32.4, 14.7, 90),
    "C4": (34.2, 14.7, 90),
    "R4": (37.4, 14.7, 180),
    "Q1": (38.8, 22.6, 0),
    "R1": (34.4, 18.6, 90),
    "R2": (36.4, 18.6, 90),
    "R3": (42.9, 25.2, 90),
    # user LED on GPIO1 (pin 17), above the module's top-left corner
    "R7": (8.0, 5.3, 90),
    "D3": (8.0, 1.9, 270),       # anode (pad 2) down toward R7
    # Hammond 1551K PCB bosses
    "H1": (17.0 - 0.25, 2.75 - 0.25, 0),
    "H2": (57.0 - 0.25, 31.25 - 0.25, 0),
    # the other diagonal of the same 40 x 28.5 mm rectangle: bench standoffs only
    # (nothing under them in the box)
    "H3": (57.0 - 0.25, 2.75 - 0.25, 0),
    "H4": (17.0 - 0.25, 31.25 - 0.25, 0),
}
# 3D models KiCad doesn't ship, by footprint name (files in esp32c3_recovery.3dshapes/)
MODEL_OVERRIDE = {"Fuse_1812_4532Metric": "${KIPRJMOD}/esp32c3_recovery.3dshapes/Fuse_1812_4532Metric.step"}
# J1 VBAT, J2 CANH, J3 CANL, J4 BTN, J5 GND, top to bottom. Wire entry faces the
# right end wall, 7 mm in from the board edge so the wires can fan out from one
# grommet; GND is next to H2.
J_X = W - 7.0 - 7.0
for _i in range(5):
    PLACE[f"J{_i + 1}"] = (J_X, 9.0 + 4.0 * _i, 180)
# experiment hook: PLACE_JSON='{"R6": [40.8, 20.6, 90]}' overrides entries
PLACE.update({k: tuple(v) for k, v in json.loads(os.environ.get("PLACE_JSON", "{}")).items()})
J_LABELS = {"J1": "VBAT", "J2": "CANH", "J3": "CANL", "J4": "BTN", "J5": "GND"}
# JLC's own footprint for C2765054 has its origin 0.57 mm toward the back pad
# from ours (body -7.07..5.67 vs -6.5..6.2 about the origin); the CPL reports
# that point so JLC's part lands on our pads. Likewise JLC's footprint for the
# USB-C (C165948) has its origin 1.42 mm back from ours (shell holes at
# -1.706/+2.474 mm about it vs -3.13/+1.05 mm about ours).
CPL_SHIFT = {"WAGO_2060-451_998-404": (0.57, 0.0),
             "USB_C_Receptacle_HRO_TYPE-C-31-M-12": (0.0, -1.42)}

# JLC placement rotation offsets (from JLCKicadTools' cpl_rotations_db); check the
# rest, including the WAGO terminals, in JLC's placement preview before ordering.
JLC_ROT = {"SOIC-": 270, "SOT-23": 180, "SOT-223": 180}   # SOT-23: JLC preview (2026-11-17), not the db's -90

# GND is routed at the default 0.25 mm: the pours carry the current, and thin
# ground tracks fit the corridors by the module.
POWER_NETS = ("/VBAT_F", "Net-(J1-Pin_1)", "+5V", "/5V_REG", "+3V3", "/VBUS")


def mm(v):
    return pcbnew.ToMM(v)


def vec(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


# --------------------------------------------------------------------------
# Netlist
# --------------------------------------------------------------------------

def read_netlist():
    net = parse(open(NETLIST).read())
    comps = {}
    for c in findall(find(net, "components"), "comp"):
        ref = str(find(c, "ref")[1])
        props = {str(find(p, "name")[1]): str(find(p, "value")[1])
                 for p in findall(c, "property") if find(p, "value")}
        comps[ref] = {
            "value": str(find(c, "value")[1]),
            "footprint": str(find(c, "footprint")[1]) if find(c, "footprint") else "",
            "tstamp": str(find(c, "tstamps")[1]),
            "lcsc": props.get("LCSC", ""),
            "dnp": any(str(find(p, "name")[1]) == "dnp" for p in findall(c, "property")),
            "user": {k: v for k, v in props.items()
                     if k not in ("Sheetname", "Sheetfile") and not k.startswith("ki_")},
            "descr": str(find(c, "description")[1]) if find(c, "description") else "",
            "datasheet": str(find(c, "datasheet")[1]) if find(c, "datasheet") else "",
        }
    pads = {}  # (ref, pin) -> net name
    for n in findall(find(net, "nets"), "net"):
        name = str(find(n, "name")[1])
        for node in findall(n, "node"):
            pads[(str(find(node, "ref")[1]), str(find(node, "pin")[1]))] = name
    return comps, pads


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = FPLIB if lib == "esp32c3_recovery" else os.path.join(SYSFP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    return fp


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------

def write_netclasses():
    """Default 0.25/0.2 mm, Power 0.5 mm; vias 0.6/0.3 (JLC Economic friendly)."""
    path = os.path.join(PROJ, NAME + ".kicad_pro")
    pro = json.load(open(path))
    ns = pro.setdefault("net_settings", {})
    base = {"clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3,
            "microvia_diameter": 0.3, "microvia_drill": 0.1,
            "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
            "wire_width": 6, "bus_width": 12, "line_style": 0,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "priority": 2147483647}
    ns["classes"] = [dict(base, name="Default", track_width=0.25),
                     dict(base, name="Power", track_width=0.5, priority=0)]
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": n} for n in POWER_NETS]
    ns.setdefault("meta", {"version": 4})
    # JLC: 0.3 mm copper-to-edge on a routed outline
    pro["board"].setdefault("design_settings", {}).setdefault("rules", {})["min_copper_edge_clearance"] = 0.3
    with open(path, "w") as fh:
        json.dump(pro, fh, indent=2)
        fh.write("\n")


def stage_place():
    import footprints
    footprints.write_all()
    comps, pads = read_netlist()
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(2)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    nets = {}
    for name in sorted(set(pads.values())):
        n = pcbnew.NETINFO_ITEM(b, name)
        b.Add(n)
        nets[name] = n

    for ref, c in sorted(comps.items()):
        fp = load_fp(c["footprint"])
        lib, name = c["footprint"].split(":")
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetLibDescription(c["descr"])
        fp.GetField("Description").SetText(c["descr"])
        fp.GetField("Datasheet").SetText(c["datasheet"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["tstamp"]))
        for k, v in dict(c["user"], LCSC=c["lcsc"]).items():
            fp.SetField(k, v)
            fp.GetField(k).SetVisible(False)
        x, y, r = PLACE[ref]
        if name in MODEL_OVERRIDE:
            fp.Models()[0].m_Filename = MODEL_OVERRIDE[name]
        b.Add(fp)
        fp.SetPosition(vec(X0 + x, Y0 + y))
        fp.SetOrientationDegrees(r)
        for p in fp.Pads():
            key = (ref, p.GetNumber())
            if key in pads:
                p.SetNet(nets[pads[key]])
        # The board is too dense for legible silk references; they go on the
        # fab layer (assembly drawing) and the silkscreen keeps outlines only.
        fp.Reference().SetLayer(pcbnew.F_Fab)
        fp.Reference().SetTextSize(vec(0.6, 0.6))
        fp.Reference().SetTextThickness(MM(0.1))
        fp.Reference().SetPosition(fp.GetPosition())
        fp.Value().SetVisible(False)
        fp.SetAttributes(fp.GetAttributes() & ~pcbnew.FP_EXCLUDE_FROM_BOM)
        if c["dnp"]:
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_DNP)
            # no paste on unfitted parts: shrink every stencil opening to nothing
            fp.SetLocalSolderPasteMargin(MM(-2.0))
        # solid pour connections: the regulator tab and the module's ground pad (heat)
        for p in fp.Pads():
            if (ref, p.GetNumber()) in (("U1", "2"), ("U2", "19"), ("U2", "9"), ("J6", "SH")):
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    add_keepouts(b)
    add_tab_vias(b)
    add_ep_vias(b)
    # gerbers, drill and CPL all use the board's lower-left corner as origin
    ds.SetAuxOrigin(vec(X0, Y0 + H))
    add_outline(b)

    os.makedirs(WORK, exist_ok=True)
    pcbnew.SaveBoard(PCB, b)
    write_netclasses()
    b = pcbnew.LoadBoard(PCB)
    dsn = os.path.join(WORK, "board.dsn")
    if not pcbnew.ExportSpecctraDSN(b, dsn):
        raise SystemExit("DSN export failed")
    widen_power_in_dsn(dsn)
    print("placed; DSN at", dsn)


def outline_corners():
    """Per corner of OUTLINE: (tangent-in, arc mid, tangent-out, centre, radius)."""
    n = len(OUTLINE)
    pts = []          # (tangent-in, mid, tangent-out) per corner
    for i in range(n):
        p0, p1, p2 = OUTLINE[i - 1], OUTLINE[i], OUTLINE[(i + 1) % n]
        a = (p0[0] - p1[0], p0[1] - p1[1])
        c = (p2[0] - p1[0], p2[1] - p1[1])
        la, lc = math.hypot(*a), math.hypot(*c)
        a, c = (a[0] / la, a[1] / la), (c[0] / lc, c[1] / lc)
        reflex = (a[0] * c[1] - a[1] * c[0]) > 0     # clockwise outline, y down
        r = R_IN if reflex else R_OUT
        t_in = (p1[0] + a[0] * r, p1[1] + a[1] * r)
        t_out = (p1[0] + c[0] * r, p1[1] + c[1] * r)
        ctr = (p1[0] + (a[0] + c[0]) * r, p1[1] + (a[1] + c[1]) * r)
        d = (p1[0] - ctr[0], p1[1] - ctr[1])
        k = r / math.hypot(*d)
        mid = (ctr[0] + d[0] * k, ctr[1] + d[1] * k)
        pts.append((t_in, mid, t_out, ctr, r))
    return pts


def outline_points(step=0.5):
    """The filleted outline as a closed polyline (arcs sampled)."""
    out = []
    for t_in, mid, t_out, ctr, r in outline_corners():
        a0 = math.atan2(t_in[1] - ctr[1], t_in[0] - ctr[0])
        a1 = math.atan2(t_out[1] - ctr[1], t_out[0] - ctr[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi    # the short way round
        k = max(2, int(abs(da) * r / step) + 1)
        for j in range(k + 1):
            a = a0 + da * j / k
            out.append((ctr[0] + r * math.cos(a), ctr[1] + r * math.sin(a)))
    return out


def add_outline(b):
    """Edge.Cuts: OUTLINE with every corner filleted (R_IN on the two reflex
    notch corners, R_OUT elsewhere)."""
    pts = outline_corners()
    n = len(pts)

    def shape(kind, *xy):
        e = pcbnew.PCB_SHAPE(b)
        e.SetShape(kind)
        if kind == pcbnew.SHAPE_T_ARC:
            e.SetArcGeometry(*(vec(X0 + x, Y0 + y) for x, y in xy))
        else:
            e.SetStart(vec(X0 + xy[0][0], Y0 + xy[0][1]))
            e.SetEnd(vec(X0 + xy[1][0], Y0 + xy[1][1]))
        e.SetLayer(pcbnew.Edge_Cuts)
        e.SetWidth(MM(0.1))
        b.Add(e)

    for i in range(n):
        t_in, mid, t_out = pts[i][:3]
        shape(pcbnew.SHAPE_T_ARC, t_in, mid, t_out)
        shape(pcbnew.SHAPE_T_SEGMENT, t_out, pts[(i + 1) % n][0])


def rule_area(b, name, layers, x1, y1, x2, y2, tracks, vias, fill):
    z = pcbnew.ZONE(b)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowZoneFills(fill)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        o.Append(MM(X0 + x), MM(Y0 + y))
    b.Add(z)


def rule_circle(b, name, layers, cx, cy, r, tracks, vias, fill, n=24):
    z = pcbnew.ZONE(b)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowZoneFills(fill)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    o = z.Outline()
    o.NewOutline()
    for i in range(n):
        a = 2 * math.pi * i / n
        o.Append(MM(X0 + cx + r * math.cos(a)), MM(Y0 + cy + r * math.sin(a)))
    b.Add(z)


def add_tab_vias(b):
    """3 x 3 thermal vias (0.3 mm) inside the regulator's GND tab, placed before
    routing so the autorouter keeps other nets off them."""
    tab = [p for p in b.FindFootprintByReference("U1").Pads() if p.GetNumber() == "2"][0]
    c = tab.GetBoundingBox().GetCenter()
    for dx in (-1.6, 0, 1.6):
        for dy in (-1.6, 0, 1.6):
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(c.x + MM(dx), c.y + MM(dy)))
            v.SetWidth(MM(0.6))
            v.SetDrill(MM(0.3))
            v.SetNet(tab.GetNet())
            b.Add(v)


def add_ep_vias(b):
    """Four 0.3 mm GND vias in the module's centre ground pad (pad 19, 2.9 mm
    square at footprint (0.96, 0.2)) into the bottom pour, placed before routing.
    They sit between the footprint's 3 x 3 paste dots (1.1 mm pitch), not under
    them, so solder doesn't wick down the holes."""
    fp = b.FindFootprintByReference("U2")
    ep = [p for p in fp.Pads() if p.GetNumber() == "19" and pcbnew.ToMM(p.GetSize().x) > 2][0]
    c = ep.GetPosition()
    for dx, dy in ((-0.55, -0.55), (0.55, -0.55), (-0.55, 0.55), (0.55, 0.55)):
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(c.x + MM(dx), c.y + MM(dy)))
        v.SetWidth(MM(0.6))
        v.SetDrill(MM(0.3))
        v.SetNet(ep.GetNet())
        b.Add(v)


def add_keepouts(b):
    """WROOM-02 (the footprint carries Espressif's antenna keep-out: 5 mm round
    the antenna, all layers):
    - the same keep-out again as a board rule area over the left strip, so the
      autorouter and the pours certainly see it;
    - no top-layer tracks under the module body inside the pad rows (only its
      ground pad and vias there);
    - a 0.5 mm band along every board edge (below)."""
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    x1, _, x2, _ = mod_rect(-14.0, MOD_LY[0] - 5.0, 14.0, -7.1)
    rule_area(b, "antenna", [F, B], -1.0, -1.0, x2, H + 1.0, True, True, True)
    rule_area(b, "under-module", [F], *mod_rect(-8.0, -6.6, 8.0, MOD_LY[1]), True, False, False)
    # box screw heads (#2 pan, ~4.2 mm) on H1/H2: no top tracks or vias within
    # 2.7 mm of the centre, so only the GND pour sits under a head
    for ref in ("H1", "H2"):
        x, y, _ = PLACE[ref]
        rule_circle(b, "screw-head", [F], x, y, 2.7, True, True, False)
    # 0.5 mm edge band along the filleted outline: the autorouter ignores the
    # board's edge-clearance rule
    e = 0.5
    pl = outline_points()
    for (x1, y1), (x2, y2) in zip(pl, pl[1:] + pl[:1]):
        if math.hypot(x2 - x1, y2 - y1) < 1e-6:
            continue
        rule_area(b, "edge", [F, B], min(x1, x2) - e, min(y1, y2) - e,
                  max(x1, x2) + e, max(y1, y2) + e, True, True, False)


def widen_power_in_dsn(path):
    """Freerouting reads track width from DSN net classes; make sure power nets get 0.5 mm."""
    txt = open(path).read()
    if "(class Power" in txt:
        return
    names = " ".join('"%s"' % n if not n.isalnum() else n for n in POWER_NETS)
    cls = ('    (class Power %s\n      (circuit\n        (use_via "Via[0-1]_600:300_um")\n      )\n'
           '      (rule\n        (width 500)\n        (clearance 200)\n      )\n    )\n' % names)
    i = txt.rindex("  )\n  (wiring")
    txt = txt[:i] + cls + txt[i:]
    # default signal width 0.25 mm (KiCad exports the minimum, 0.2)
    k = txt.index("(class kicad_default")
    j = txt.index("(width 200)", k)
    txt = txt[:j] + "(width 250)" + txt[j + len("(width 200)"):]
    open(path, "w").write(txt)


def zone(b, layer, net, prio=0):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(b.FindNet(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(MM(0.25))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    o = z.Outline()
    o.NewOutline()
    for x, y in OUTLINE:     # the board-edge clearance keeps the fill inside
        o.Append(MM(X0 + x), MM(Y0 + y))
    b.Add(z)
    return z


def stitch(b, pitch=2.5, clear=0.3):
    """Drop GND vias on a grid wherever they clear every other net, every pad
    and the module footprint, tying the top and bottom pours together."""
    others, pads = [], []
    for t in b.GetTracks():
        others.append(t)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            pads.append(p)
    keep_out = b.FindFootprintByReference("U2").GetBoundingBox(False)
    keep_out.Inflate(MM(0.5))
    areas = [z for z in b.Zones() if z.GetIsRuleArea()]
    # candidates: a tight ring around the regulator tab first (heat), then a grid
    grid = []
    y = 1.2
    while y < H - 1.0:
        x = 1.2
        while x < W - 1.0:
            grid.append((x, y))
            x += pitch
        y += pitch
    pts = []
    tab = [p for p in b.FindFootprintByReference("U1").Pads() if p.GetNumber() == "2"][0]
    tb = tab.GetBoundingBox()
    tx1, ty1, tx2, ty2 = (mm(tb.GetLeft()) - X0, mm(tb.GetTop()) - Y0,
                          mm(tb.GetRight()) - X0, mm(tb.GetBottom()) - Y0)
    d = 0.9
    k = 0.0
    while k <= 1.0001:
        for (x, y) in ((tx1 - d, ty1 + k * (ty2 - ty1)), (tx2 + d, ty1 + k * (ty2 - ty1)),
                       (tx1 + k * (tx2 - tx1), ty2 + d)):
            pts.append((x, y))
        k += 0.2
    pts += grid
    added = 0

    for (x, y) in pts:
        if True:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(vec(X0 + x, Y0 + y))
            v.SetWidth(MM(0.6))
            v.SetDrill(MM(0.3))
            v.SetNet(b.FindNet("GND"))
            ok = not keep_out.Contains(v.GetPosition()) and on_board(x, y, 0.8)
            if ok and any(z.GetDoNotAllowVias() and z.Outline().Collide(v.GetPosition(), MM(0.35))
                          for z in areas):
                ok = False
            if ok:
                for o in others:
                    if o.Type() == pcbnew.PCB_VIA_T and (o.GetPosition() - v.GetPosition()).EuclideanNorm() < MM(1.0):
                        ok = False
                        break
            if ok:
                for fp in b.GetFootprints():
                    if fp.GetReference().startswith("H") and fp.HitTest(v.GetPosition(), MM(3.0)):
                        ok = False
                        break
            if ok:
                vs = v.GetEffectiveShape(pcbnew.F_Cu)
                for it in others:
                    gap = MM(clear) if it.GetNetname() != "GND" else MM(0.2)
                    if it.GetEffectiveShape(it.GetLayer() if it.Type() != pcbnew.PCB_VIA_T
                                            else pcbnew.F_Cu).Collide(vs, gap):
                        ok = False
                        break
            if ok:
                for p in pads:
                    if p.GetEffectiveShape(pcbnew.F_Cu).Collide(vs, MM(clear)):
                        ok = False
                        break
            if ok:
                b.Add(v)
                others.append(v)
                added += 1
    return added


def silk_text(b, s, x, y, size=0.8, layer=pcbnew.F_SilkS, just=None):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(vec(X0 + x, Y0 + y))
    t.SetLayer(layer)
    t.SetTextSize(vec(size, size))
    t.SetTextThickness(MM(0.15))
    t.SetMirrored(layer == pcbnew.B_SilkS)
    if just == "left":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif just == "right":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    b.Add(t)
    return t


def stage_finish():
    b = pcbnew.LoadBoard(PCB)
    ses = os.path.join(WORK, "board.ses")
    if not pcbnew.ImportSpecctraSES(b, ses):
        raise SystemExit("SES import failed")
    zone(b, pcbnew.F_Cu, "GND")
    zone(b, pcbnew.B_Cu, "GND")
    n = stitch(b)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    print("stitching vias:", n)
    for ref, name in J_LABELS.items():
        x, y, _ = PLACE[ref]
        silk_text(b, name, x, y, size=1.0, layer=pcbnew.B_SilkS)      # under each terminal
        silk_text(b, name, J_X + 7.6, y, size=0.8, just="left")      # at each wire entry
    t = silk_text(b, "ANT: keep clear", 3.2, MOD_Y, size=0.8)
    t.SetTextAngleDegrees(90)
    silk_text(b, "LED", PLACE["D3"][0] - 1.4, PLACE["D3"][1], size=0.8, just="right")
    # bench labels on the back (the switch bodies and pads leave no room on top)
    for ref, name in (("SW1", "BOOT"), ("SW2", "RESET"), ("TP1", "5V"), ("TP2", "D-"),
                      ("TP3", "D+"), ("TP4", "GND"), ("TP5", "TX"), ("TP6", "RX"), ("J6", "USB")):
        x, y, _ = PLACE[ref]
        silk_text(b, name, x, y, size=0.8, layer=pcbnew.B_SilkS)
    silk_text(b, "Ioniq 5 Parking Safety auto-off", 44.0, 12.5, size=1.0, layer=pcbnew.B_SilkS)
    silk_text(b, "rev C  2026-11  Hammond 1551K", 44.0, 14.3, size=1.0, layer=pcbnew.B_SilkS)
    pcbnew.SaveBoard(PCB, b)
    print("finished", PCB)


def stage_fab():
    out = os.path.join(PROJ, "out", "jlc")
    os.makedirs(out, exist_ok=True)
    g = os.path.join(out, "gerbers")
    os.makedirs(g, exist_ok=True)
    for f in os.listdir(g):
        os.remove(os.path.join(g, f))
    layers = "F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", layers,
                    "--subtract-soldermask", "--use-drill-file-origin", "-o", g + "/", PCB], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon",
                    "--excellon-separate-th", "--drill-origin", "plot", "--generate-map", "--map-format", "gerberx2",
                    "-o", g + "/", PCB], check=True, stdout=subprocess.DEVNULL)
    with zipfile.ZipFile(os.path.join(out, NAME + "-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(g)):
            z.write(os.path.join(g, f), f)

    comps, _ = read_netlist()
    groups = {}
    for ref, c in comps.items():
        if not c["lcsc"] or c["dnp"]:
            continue
        key = (c["footprint"].split(":")[1], c["lcsc"])
        groups.setdefault(key, []).append(ref)
    with open(os.path.join(out, NAME + "-bom.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (fp, lcsc), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            refs = sorted(refs, key=lambda r: (r[0], int(re.sub(r"\D", "", r))))
            vals = {comps[r]["value"] for r in refs}
            val = vals.pop() if len(vals) == 1 else fp.split("_")[0] + " " + fp.split("_")[1]
            w.writerow([val, ",".join(refs), fp, lcsc])

    b = pcbnew.LoadBoard(PCB)
    with open(os.path.join(out, NAME + "-cpl.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
            c = comps.get(fp.GetReference(), {})
            if not c.get("lcsc") or c.get("dnp"):
                continue
            pos = fp.GetPosition()
            # JLC uses Y up from the board's lower-left corner
            fpname = fp.GetFPID().GetLibItemName().wx_str()
            if fpname in CPL_SHIFT:
                dx, dy = CPL_SHIFT[fpname]
                r = math.radians(fp.GetOrientationDegrees())   # KiCad: CCW, screen Y down
                pos = vec(mm(pos.x) + dx * math.cos(r) + dy * math.sin(r),
                          mm(pos.y) - dx * math.sin(r) + dy * math.cos(r))
            rot = fp.GetOrientationDegrees() + sum(v for k, v in JLC_ROT.items() if fpname.startswith(k))
            w.writerow([fp.GetReference(), "%.3fmm" % (mm(pos.x) - X0), "%.3fmm" % (Y0 + H - mm(pos.y)),
                        "Top", "%.1f" % (rot % 360)])
    print("JLC outputs in", out)


if __name__ == "__main__":
    {"place": stage_place, "finish": stage_finish, "fab": stage_fab}[sys.argv[1]]()
