#!/usr/bin/env python3
"""Generate the esp32c3-recovery KiCad project (schematic + project symbol library).

Run from anywhere:  python3 hardware/esp32c3-recovery/tools/gen.py
Then check with:    hardware/esp32c3-recovery/tools/check.sh

All coordinates are in mm on the 1.27 mm schematic grid (parts on 2.54).
"""
import json
import os
import uuid

import kilib
from sexp import Q, dump, find, findall

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ_DIR = os.path.dirname(HERE)
NAME = "esp32c3-recovery"
LIBNAME = "esp32c3_recovery"
LIBFILE = os.path.join(PROJ_DIR, LIBNAME + ".kicad_sym")
NS = uuid.UUID("6b1f0b52-6d0e-4a55-9a43-1f1b2b2e5c3a")
ROOT_UUID = str(uuid.uuid5(NS, "root-sheet"))
_uid_count = {}


def uid(key):
    n = _uid_count.get(key, 0)
    _uid_count[key] = n + 1
    return Q(str(uuid.uuid5(NS, f"{key}#{n}")))


def f(v):
    return round(float(v), 4)


def font(size=1.27, bold=False, italic=False):
    out = ["font", ["size", size, size]]
    if bold:
        out.append(["bold", "yes"])
    if italic:
        out.append(["italic", "yes"])
    return out


def effects(size=1.27, justify=None, hide=False, bold=False, italic=False):
    e = ["effects", font(size, bold, italic)]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


# --------------------------------------------------------------------------
# Custom symbol helpers (kept for project symbols; none are needed at present)
# --------------------------------------------------------------------------

def _prop(key, val, x, y, hide=False, angle=0, justify=None):
    p = ["property", Q(key), Q(val), ["at", f(x), f(y), angle],
         ["show_name", "no"], ["do_not_autoplace", "no"]]
    if hide:
        p.append(["hide", "yes"])
    p.append(effects(justify=justify))
    return p


def _pin(etype, x, y, angle, name, number, length=5.08):
    return ["pin", etype, "line", ["at", f(x), f(y), angle], ["length", length],
            ["name", Q(name), effects()], ["number", Q(number), effects()]]


def _rect(x1, y1, x2, y2):
    return ["rectangle", ["start", f(x1), f(y1)], ["end", f(x2), f(y2)],
            ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]


def _custom(name, ref, value, desc, keywords, body, pins, ref_xy, val_xy, fp="", ds=""):
    return ["symbol", Q(name),
            ["pin_names", ["offset", 1.016]],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"],
            _prop("Reference", ref, *ref_xy, justify="left"),
            _prop("Value", value, *val_xy, justify="left"),
            _prop("Footprint", fp, 0, 0, hide=True),
            _prop("Datasheet", ds, 0, 0, hide=True),
            _prop("Description", desc, 0, 0, hide=True),
            _prop("ki_keywords", keywords, 0, 0, hide=True),
            ["symbol", Q(name + "_0_1"), body],
            ["symbol", Q(name + "_1_1")] + pins,
            ["embedded_fonts", "no"]]


def write_project_lib():
    lib = ["kicad_symbol_lib", ["version", 20251024], ["generator", Q("esp32c3_recovery_gen")],
           ["generator_version", Q("10.0")]]
    with open(LIBFILE, "w") as fh:
        fh.write(dump(lib) + "\n")


# --------------------------------------------------------------------------
# Sheet model
# --------------------------------------------------------------------------

class Sheet:
    def __init__(self):
        self.lib = {}           # lib_id -> flattened symbol
        self.symbols = []       # instance nodes
        self.segments = []      # [(x1,y1,x2,y2)]
        self.items = []         # labels, text, no_connects, rectangles
        self.pins = {}          # "REF.pin" -> (x, y)
        self.pin_pts = []
        self.pwr_n = 0
        self.flg_n = 0

    # -- symbols ----------------------------------------------------------
    def _libsym(self, lib_id):
        if lib_id not in self.lib:
            if lib_id.startswith(LIBNAME + ":"):
                sym = kilib.load(lib_id, LIBFILE)
            else:
                sym = kilib.load(lib_id)
            self.lib[lib_id] = sym
        return self.lib[lib_id]

    def place(self, lib_id, ref, value, x, y, rot=0, ref_at=None, val_at=None,
              fields=None, hide_value=False, extra_hidden=None, just=None, fa=None, dnp=False):
        """Place a symbol. ref_at / val_at are offsets (dx, dy) from the origin
        for centred, horizontal field text (or None to hide)."""
        sym = self._libsym(lib_id)
        pins = kilib.pins(sym)
        is_power = ref.startswith("#")
        fa = rot % 180 if fa is None else fa  # field angle that keeps text horizontal
        node = ["symbol", ["lib_id", Q(lib_id)], ["at", f(x), f(y), rot], ["unit", 1],
                ["exclude_from_sim", "no"], ["in_bom", "no" if is_power else "yes"],
                ["on_board", "no" if is_power else "yes"], ["dnp", "yes" if dnp else "no"],
                ["uuid", uid("sym:" + ref)]]
        props = {str(p[1]): str(p[2]) for p in findall(sym, "property")}
        props["Reference"] = ref
        props["Value"] = value
        props.update(fields or {})
        order = ["Reference", "Value", "Footprint", "Datasheet", "Description"] + \
            [k for k in (fields or {}) if k not in ("Reference", "Value", "Footprint",
                                                     "Datasheet", "Description")]
        for k in order:
            if k.startswith("ki_"):
                continue
            hide = True
            px, py = x, y
            if k == "Reference" and ref_at is not None and not is_power:
                hide = False
                px, py = x + ref_at[0], y + ref_at[1]
            if k == "Value" and val_at is not None and not hide_value:
                hide = False
                px, py = x + val_at[0], y + val_at[1]
            p = ["property", Q(k), Q(props.get(k, "")), ["at", f(px), f(py), fa]]
            if hide:
                p.append(["hide", "yes"])
            p.append(effects(justify=just if (k in ("Reference", "Value") and just) else None))
            node.append(p)
        for num in sorted(pins, key=lambda s: (len(s), s)):
            node.append(["pin", Q(num), ["uuid", uid(f"pin:{ref}:{num}")]])
        node.append(["instances", ["project", Q(NAME),
                                   ["path", Q("/" + ROOT_UUID), ["reference", Q(ref)], ["unit", 1]]]])
        self.symbols.append(node)
        for num, (_n, px, py, _a, _t) in pins.items():
            pt = kilib.xform(px, py, x, y, rot)
            self.pins[f"{ref}.{num}"] = pt
            self.pin_pts.append(pt)
        return {num: self.pins[f"{ref}.{num}"] for num in pins}

    def place_by_pin(self, lib_id, ref, value, pin, at, rot=0, **kw):
        """Place so that `pin` lands exactly on `at`."""
        sym = self._libsym(lib_id)
        _n, px, py, _a, _t = kilib.pins(sym)[pin]
        ox, oy = kilib.xform(px, py, 0, 0, rot)
        return self.place(lib_id, ref, value, f(at[0] - ox), f(at[1] - oy), rot, **kw)

    def power(self, lib_id, x, y, rot=0, show=True, val_at=None, just=None):
        if lib_id == "power:PWR_FLAG":
            self.flg_n += 1
            ref = f"#FLG0{self.flg_n}"
        else:
            self.pwr_n += 1
            ref = f"#PWR0{self.pwr_n:02d}"
        value = lib_id.split(":")[1]
        # value text sits beyond the symbol body, away from the pin
        off = val_at or {"power:GND": (0, 3.81), "power:PWR_FLAG": (0, -3.81)}.get(lib_id, (0, -3.81))
        return self.place(lib_id, ref, value, x, y, rot, val_at=off if show else None,
                          just=just)

    # -- wiring -----------------------------------------------------------
    def wire(self, *pts):
        pts = [p if isinstance(p, tuple) else self.pins[p] for p in pts]
        for a, b in zip(pts, pts[1:]):
            assert a[0] == b[0] or a[1] == b[1], f"non-orthogonal wire {a}->{b}"
            if a != b:
                self.segments.append((f(a[0]), f(a[1]), f(b[0]), f(b[1])))

    def label(self, text, at, angle=0, justify="left bottom"):
        at = at if isinstance(at, tuple) else self.pins[at]
        if justify.startswith("right"):
            angle = 180  # how KiCad stores a label whose text extends to the left
        self.items.append(["label", Q(text), ["at", f(at[0]), f(at[1]), angle],
                           effects(justify=justify),
                           ["uuid", uid("label:" + text)]])

    def no_connect(self, pin):
        at = self.pins[pin]
        self.items.append(["no_connect", ["at", f(at[0]), f(at[1])], ["uuid", uid("nc:" + pin)]])

    def text(self, s, x, y, size=1.27, bold=False, italic=False, justify="left bottom"):
        self.items.append(["text", Q(s), ["exclude_from_sim", "no"], ["at", f(x), f(y), 0],
                           effects(size, justify, bold=bold, italic=italic), ["uuid", uid("text")]])

    def note(self, s, x, y, w, h, size=1.27):
        self.items.append(["text_box", Q(s), ["exclude_from_sim", "no"], ["at", f(x), f(y), 0],
                           ["size", f(w), f(h)], ["margins", 1.27, 1.27, 1.27, 1.27],
                           ["stroke", ["width", 0.1524], ["type", "solid"]],
                           ["fill", ["type", "none"]], effects(size, "left top"),
                           ["uuid", uid("note")]])

    def block(self, title, x1, y1, x2, y2):
        self.items.append(["rectangle", ["start", f(x1), f(y1)], ["end", f(x2), f(y2)],
                           ["stroke", ["width", 0.1524], ["type", "dash"]], ["fill", ["type", "none"]],
                           ["uuid", uid("rect")]])
        self.text(title, x1 + 1.27, y1 - 1.27, size=1.778, bold=True)

    # -- output -----------------------------------------------------------
    def _split_segments(self):
        """Split wires wherever another wire end or a pin touches their interior,
        so every connection is an endpoint; return junction points."""
        pts = set(self.pin_pts)
        for s in self.segments:
            pts.add((s[0], s[1]))
            pts.add((s[2], s[3]))
        out = []
        for (x1, y1, x2, y2) in self.segments:
            cuts = [(x1, y1), (x2, y2)]
            for (px, py) in pts:
                if x1 == x2 == px and min(y1, y2) < py < max(y1, y2):
                    cuts.append((px, py))
                elif y1 == y2 == py and min(x1, x2) < px < max(x1, x2):
                    cuts.append((px, py))
            cuts.sort()
            out += [(a[0], a[1], b[0], b[1]) for a, b in zip(cuts, cuts[1:])]
        self.segments = out
        degree = {}
        for (x1, y1, x2, y2) in out:
            for p in ((x1, y1), (x2, y2)):
                degree[p] = degree.get(p, 0) + 1
        for p in self.pin_pts:
            if p in degree:
                degree[p] += 1
        return sorted(p for p, d in degree.items() if d >= 3)

    def write(self, path, title_block):
        junctions = self._split_segments()
        sch = ["kicad_sch", ["version", 20260306], ["generator", Q("eeschema")],
               ["generator_version", Q("10.0")], ["uuid", Q(ROOT_UUID)], ["paper", Q("A3")],
               title_block, ["lib_symbols"] + [self.lib[k] for k in sorted(self.lib)]]
        for p in junctions:
            sch.append(["junction", ["at", p[0], p[1]], ["diameter", 0], ["color", 0, 0, 0, 0],
                        ["uuid", uid("junction")]])
        for (x1, y1, x2, y2) in self.segments:
            sch.append(["wire", ["pts", ["xy", x1, y1], ["xy", x2, y2]],
                        ["stroke", ["width", 0], ["type", "default"]], ["uuid", uid("wire")]])
        sch += self.items
        sch += self.symbols
        sch.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
        sch.append(["embedded_fonts", "no"])
        with open(path, "w") as fh:
            fh.write(dump(sch) + "\n")


# --------------------------------------------------------------------------
# The circuit
# --------------------------------------------------------------------------

# JLCPCB parts. "basic" and "preferred" carry no feeder-loading fee on Economic
# PCBA; plain "extended" costs a one-off fee per part type per order.
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"


def jlc(lcsc, fp, desc=None):
    out = {"Footprint": fp, "LCSC": lcsc}
    if desc:
        out["Description"] = desc
    return out




def build():
    s = Sheet()
    L = LIBNAME
    VB_Y = 40.64        # VBAT / +5V rail
    GND_Y = 68.58       # power-block ground bus

    # ---------------- Panel tap -----------------------------------------
    # One WAGO 2060 single-pole SMD spring-clamp terminal per wire: JLC places
    # them, and five of one part keeps it to a single extended-part fee.
    WAGO = jlc("C2765054", "esp32c3_recovery:WAGO_2060-451_998-404",
               "WAGO 2060-451/998-404 SMD push-in terminal, 1 pole, 0.2-0.75 mm2 (24-18 AWG), 9 A")
    J = {}
    for i, name in enumerate(["VBAT", "CANH", "CANL", "BTN", "GND"]):
        ref = f"J{i + 1}"
        J[str(i + 1)] = s.place_by_pin("Connector:Conn_01x01_Pin", ref, name, "1", (45.72, VB_Y + 2.54 * i),
                                       ref_at=(-1.27, 0.635), just="right", fields=WAGO)["1"]
    for i, t in enumerate(["CON1-1  VBAT", "CON1-8  CAN-H", "CON1-7  CAN-L",
                           "CON1-5  BTN", "CON1-16  GND"]):
        s.text(t, 34.29, VB_Y + 2.54 * i + 0.635, justify="right bottom")
    for pin, name in (("2", "CANH"), ("3", "CANL"), ("4", "BTN")):
        p = J[pin]
        s.wire(p, (p[0] + 7.62, p[1]))
        s.label(name, (p[0] + 7.62, p[1]))
    s.block("PANEL TAP", 15.24, 30.48, 60.96, 73.66)

    # ---------------- Power ----------------------------------------------
    F1 = s.place_by_pin("Device:Polyfuse", "F1", "500mA 60V", "1", (68.58, VB_Y), rot=90,
                        ref_at=(0, -5.715), val_at=(0, -3.175),
                        fields=jlc("C70113", "Fuse:Fuse_1812_4532Metric",
                                   "PTC resettable fuse mSMD050-60V, 0.5 A hold, 60 V (JLC extended)"))
    s.wire(J["1"], F1["1"])
    xn = 83.82
    D1 = s.place_by_pin("Diode:SMAJ18A", "D1", "SMBJ18A", "1", (xn, 50.8), rot=270,
                        ref_at=(-2.54, -1.27), val_at=(-2.54, 1.27), just="right",
                        fields=jlc("C19077573", "Diode_SMD:D_SMB",
                                   "600 W unidirectional TVS, 18 V standoff, 29.2 V clamp (JLC preferred)"))
    C1 = s.place_by_pin("Device:C", "C1", "1u 50V", "1", (93.98, 50.8),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C28323", C0805))
    U1 = s.place("Regulator_Linear:LM78M05_TO252", "U1", "L78M05", 114.3, VB_Y,
                 ref_at=(0, -6.35), val_at=(0, -3.81),
                 fields=jlc("C58069", "Package_TO_SOT_SMD:TO-252-2",
                            "L78M05ABDT 5 V 500 mA linear regulator, 35 V max in, DPAK"))
    C2 = s.place_by_pin("Device:C", "C2", "100n", "1", (129.54, 50.8),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C14663", C0603))
    D2 = s.place_by_pin("Device:D_Schottky", "D2", "B5819W", "2", (137.16, VB_Y), rot=180,
                        ref_at=(0, -3.81), val_at=(0, 3.175),
                        fields=jlc("C8598", "Diode_SMD:D_SOD-123",
                                   "40 V 1 A Schottky: stops USB 5 V back-feeding the regulator"))
    C3 = s.place_by_pin("Device:C", "C3", "22u 25V", "1", (152.4, 50.8),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C45783", C0805, "Bulk on +5V, at the 3.3 V regulator input"))
    s.wire(F1["2"], (xn, VB_Y), D1["1"])
    s.wire((xn, VB_Y), (C1["1"][0], VB_Y), C1["1"])
    s.wire((C1["1"][0], VB_Y), U1["1"])
    s.wire(U1["3"], (C2["1"][0], VB_Y), C2["1"])
    s.wire((C2["1"][0], VB_Y), D2["2"])
    s.power("power:PWR_FLAG", 88.9, VB_Y)
    s.label("VBAT_F", (99.06, VB_Y))
    s.label("5V_REG", (C2["1"][0], VB_Y))
    j5 = J["5"]
    s.wire(j5, (j5[0] + 2.54, j5[1]), (j5[0] + 2.54, GND_Y), (C3["2"][0], GND_Y))
    for p in (D1["2"], C1["2"], U1["2"], C2["2"], C3["2"]):
        s.wire(p, (p[0], GND_Y))
    s.power("power:GND", 106.68, GND_Y)
    s.power("power:PWR_FLAG", 71.12, GND_Y)
    s.block("POWER: 12 V -> 5 V", 62.23, 30.48, 166.37, 77.47)

    # ---------------- MCU -------------------------------------------------
    # 3.3 V from +5V (AMS1117, 1.3 V drop at ~80 mA: ~0.1 W), then the module.
    U4 = s.place("Regulator_Linear:AMS1117-3.3", "U4", "AMS1117-3.3", 179.07, VB_Y,
                 ref_at=(0, -5.08), val_at=(0, -2.54),
                 fields=jlc("C6186", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                            "AMS1117-3.3 1 A LDO, 15 V max in; fed from +5V"))
    s.wire(D2["1"], (C3["1"][0], VB_Y), C3["1"])
    s.wire((C3["1"][0], VB_Y), U4["3"])
    s.power("power:+5V", *U4["3"])
    s.power("power:PWR_FLAG", 160.02, VB_Y)
    s.power("power:GND", *U4["1"])
    MX, MY = 203.2, 73.66
    U2 = s.place("RF_Module:ESP32-C3-WROOM-02", "U2", "ESP32-C3-WROOM-02-N4", MX, MY,
                 ref_at=(10.16, -25.4), val_at=(12.7, 25.4),
                 fields=jlc("C2934560", "esp32c3_recovery:ESP32-C3-WROOM-02_JLC",
                            "ESP32-C3-WROOM-02-N4 module, 4 MB flash, PCB antenna, -40 to 85 C (JLC extended)"))
    v3 = U2["1"]
    C7 = s.place_by_pin("Device:C", "C7", "22u 25V", "1", (189.23, VB_Y),
                        ref_at=(0, 10.16), val_at=None,
                        fields=jlc("C45783", C0805, "AMS1117 output / module bulk"))
    C8 = s.place_by_pin("Device:C", "C8", "100n", "1", (194.31, VB_Y),
                        ref_at=(0, 10.16), val_at=None,
                        fields=jlc("C14663", C0603, "Module 3V3 decoupling, at pin 1"))
    C10 = s.place_by_pin("Device:C", "C10", "22u 25V", "1", (199.39, VB_Y),
                         ref_at=(0, 10.16), val_at=None,
                         fields=jlc("C45783", C0805, "Module 3V3 bulk, at pin 1 (Espressif: 10u+)"))
    s.wire(U4["2"], (C7["1"][0], VB_Y), C7["1"])
    s.wire((C7["1"][0], VB_Y), (C8["1"][0], VB_Y), C8["1"])
    s.wire((C8["1"][0], VB_Y), (C10["1"][0], VB_Y), C10["1"])
    s.wire((C10["1"][0], VB_Y), (v3[0], VB_Y), v3)
    s.power("power:+3V3", v3[0], VB_Y)
    s.power("power:GND", *C7["2"])
    s.power("power:GND", *C8["2"])
    s.power("power:GND", *C10["2"])
    s.power("power:GND", *U2["9"])
    for num in ("18", "3"):          # IO0, IO4
        s.no_connect(f"U2.{num}")
    for pin, name in (("2", "EN"), ("17", "LED"), ("16", "IO2_STRAP"), ("15", "BTN_SENSE"),
                      ("4", "CAN_S"), ("5", "CAN_TX"), ("6", "CAN_RX"), ("7", "IO8_STRAP"),
                      ("8", "IO9_BOOT"), ("10", "BTN_DRIVE"), ("13", "USB_DN"), ("14", "USB_DP")):
        p = U2[pin]
        s.wire(p, (p[0] - 12.7, p[1]))
        s.label(name, (p[0] - 12.7, p[1]))
    for pin, name in (("11", "U0RXD"), ("12", "U0TXD")):
        p = U2[pin]
        s.wire(p, (p[0] + 2.54, p[1]))
        s.label(name, (p[0] + 2.54, p[1]))
    s.block("MCU (module JLC-placed)", 168.91, 30.48, 226.06, 102.87)

    # ---------------- Press sense (BTN -> GPIO3) --------------------------
    SY = 106.68
    R4 = s.place_by_pin("Device:R", "R4", "100k", "1", (130.81, SY), rot=90,
                        ref_at=(0, -2.54), val_at=(0, 2.54), fields=jlc("C25803", R0603))
    s.wire((123.19, SY), R4["1"])
    s.label("BTN", (123.19, SY), justify="right bottom")
    nx = 144.78
    R5 = s.place_by_pin("Device:R", "R5", "27k", "1", (nx, SY + 5.08),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C22967", R0603))
    C4 = s.place_by_pin("Device:C", "C4", "100n", "1", (nx + 10.16, SY + 5.08),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C14663", C0603))
    s.wire(R4["2"], (nx, SY), R5["1"])
    s.wire((nx, SY), (C4["1"][0], SY), C4["1"])
    g = SY + 17.78
    s.wire(R5["2"], (nx, g), (C4["2"][0], g), C4["2"])
    s.power("power:GND", nx + 5.08, g)
    s.wire((C4["1"][0], SY), (C4["1"][0] + 7.62, SY))
    s.label("BTN_SENSE", (C4["1"][0] + 7.62, SY), justify="right bottom")
    s.block("PRESS SENSE (ADC, ~1 V threshold)", 110.49, 97.79, 166.37, 133.35)

    # ---------------- CAN -------------------------------------------------
    U3 = s.place("Interface_CAN_LIN:TJA1051T-3", "U3", "TJA1051T/3", 256.54, 55.88,
                 ref_at=(-2.54, -10.16), val_at=(-2.54, 10.16), just="right",
                 fields=jlc("C38695", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                            "TJA1051T/3/1J CAN transceiver (same chip as the Adafruit CAN Pal). "
                            "VCC 5 V, VIO 3.3 V logic. S high = silent (transmitter off). JLC extended."))
    for pin, name in (("1", "CAN_TX"), ("4", "CAN_RX"), ("8", "CAN_S")):
        p = U3[pin]
        s.wire(p, (p[0] - 10.16, p[1]))
        s.label(name, (p[0] - 10.16, p[1]))
    vio = U3["5"]
    s.wire(vio, (vio[0] - 5.08, vio[1]))
    s.power("power:+3V3", vio[0] - 5.08, vio[1], rot=90, val_at=(-5.08, -1.27), just="right")
    vcc = U3["3"]
    top = (vcc[0], vcc[1] - 7.62)
    C5 = s.place_by_pin("Device:C", "C5", "100n", "1", (vcc[0] + 12.7, top[1]),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C14663", C0603))
    s.wire(vcc, top, (C5["1"][0], top[1]), C5["1"])
    s.wire((vcc[0] - 7.62, top[1]), top)
    s.label("5V_REG", (vcc[0] - 7.62, top[1]))
    s.power("power:GND", *C5["2"])
    s.power("power:GND", *U3["2"])
    for pin, name in (("7", "CANH"), ("6", "CANL")):
        p = U3[pin]
        s.wire(p, (p[0] + 7.62, p[1]))
        s.label(name, (p[0] + 7.62, p[1]))
    # S pull-up and VIO decoupling
    ry = 68.58
    R6 = s.place_by_pin("Device:R", "R6", "4.7k", "1", (234.95, ry),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C23162", R0603,
                                   "S pull-up: transceiver silent unless firmware drives GPIO5 low"))
    s.power("power:+3V3", *R6["1"])
    s.wire(R6["2"], (R6["2"][0], R6["2"][1] + 2.54), (R6["2"][0] + 8.89, R6["2"][1] + 2.54))
    s.label("CAN_S", (R6["2"][0] + 8.89, R6["2"][1] + 2.54), justify="right bottom")
    C6 = s.place_by_pin("Device:C", "C6", "100n", "1", (271.78, ry),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C14663", C0603, "VIO decoupling"))
    s.power("power:+3V3", *C6["1"])
    s.power("power:GND", *C6["2"])
    s.block("CAN (silent by default)", 227.33, 30.48, 284.48, 82.55)

    # ---------------- Button press output (GPIO10 -> NPN -> BTN) ----------
    BY = 111.76
    R1 = s.place_by_pin("Device:R", "R1", "1k", "1", (233.68, BY), rot=90,
                        ref_at=(0, -2.54), val_at=(0, 2.54), fields=jlc("C21190", R0603))
    s.wire((R1["1"][0] - 5.08, BY), R1["1"])
    s.label("BTN_DRIVE", (R1["1"][0] - 5.08, BY))
    bx = 246.38
    Q1 = s.place_by_pin("Transistor_BJT:MMBT3904", "Q1", "MMBT3904", "1", (bx + 5.08, BY),
                        ref_at=(5.08, -1.27), val_at=(5.08, 1.27), just="left",
                        fields=jlc("C20526", "Package_TO_SOT_SMD:SOT-23"))
    R2 = s.place_by_pin("Device:R", "R2", "10k", "1", (bx, BY + 5.08),
                        ref_at=(-2.54, -1.27), val_at=(-2.54, 1.27), just="right",
                        fields=jlc("C25804", R0603))
    s.wire(R1["2"], (bx, BY), R2["1"])
    s.wire((bx, BY), Q1["1"])
    g = BY + 15.24
    s.wire(R2["2"], (bx, g), (Q1["2"][0], g), Q1["2"])
    s.power("power:GND", bx + 5.08, g)
    R3 = s.place_by_pin("Device:R", "R3", "200", "2", (Q1["3"][0], BY - 10.16),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C17540", "Resistor_SMD:R_0805_2012Metric",
                                   "0805 125 mW; dissipates <10 mW against the panel's ~5k pull-up"))
    s.wire(R3["2"], Q1["3"])
    top = (R3["1"][0], R3["1"][1] - 2.54)
    s.wire(R3["1"], top, (top[0] + 12.7, top[1]))
    s.label("BTN", (top[0] + 12.7, top[1]))
    s.block("BUTTON PRESS OUTPUT", 227.33, 88.9, 284.48, 133.35)

    # ---------------- User LED (GPIO1, active high) -----------------------
    LY = 109.22
    R7 = s.place_by_pin("Device:R", "R7", "1k", "1", (31.75, LY), rot=90,
                        ref_at=(0, -2.54), val_at=(0, 2.54),
                        fields=jlc("C21190", R0603, "LED current ~1.3 mA from 3.3 V"))
    s.wire((21.59, LY), R7["1"])
    s.label("LED", (21.59, LY), justify="right bottom")
    D3 = s.place_by_pin("Device:LED", "D3", "red", "2", (R7["2"][0] + 5.08, LY), rot=180,
                        ref_at=(0, -3.81), val_at=(0, 3.81),
                        fields=jlc("C2286", "LED_SMD:LED_0603_1608Metric",
                                   "KT-0603R red 0603 LED, JLC basic"))
    s.wire(R7["2"], D3["2"])
    k = D3["1"]
    s.wire(k, (k[0] + 3.81, k[1]), (k[0] + 3.81, LY + 7.62))
    s.power("power:GND", k[0] + 3.81, LY + 7.62)
    s.block("USER LED", 15.24, 97.79, 72.39, 127.0)

    # ---------------- Module support (reset, boot, strapping) ------------
    SPY = 45.72
    def pullup(ref, x, net, desc):
        r = s.place_by_pin("Device:R", ref, "10k", "1", (x, SPY), ref_at=(2.54, -1.27),
                           val_at=(2.54, 1.27), just="left", fields=jlc("C25804", R0603, desc))
        s.power("power:+3V3", *r["1"])
        node = (x, r["2"][1] + 2.54)
        s.wire(r["2"], node)
        return node
    en = pullup("R8", 304.8, "EN", "EN pull-up (with C9: power-on reset delay)")
    s.wire((en[0] - 7.62, en[1]), en)
    s.label("EN", (en[0] - 7.62, en[1]))
    C9 = s.place_by_pin("Device:C", "C9", "1u", "1", (en[0] + 12.7, en[1]),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields=jlc("C15849", C0603, "EN reset delay"))
    s.wire(en, C9["1"])
    s.power("power:GND", *C9["2"])
    SW2 = s.place_by_pin("Switch:SW_Push", "SW2", "RESET", "1", (en[0], en[1] + 5.08), rot=270,
                         ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                         fields=jlc("C318884", "esp32c3_recovery:SW_TS-1187A", "Reset (EN to GND)"))
    s.wire(en, SW2["1"])
    s.power("power:GND", *SW2["2"])
    bt = pullup("R9", 342.9, "IO9_BOOT", "IO9 (BOOT strap) pull-up")
    s.wire((bt[0] - 7.62, bt[1]), bt)
    s.label("IO9_BOOT", (bt[0] - 7.62, bt[1]))
    SW1 = s.place_by_pin("Switch:SW_Push", "SW1", "BOOT", "1", (bt[0], bt[1] + 5.08), rot=270,
                         ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                         fields=jlc("C318884", "esp32c3_recovery:SW_TS-1187A",
                                    "Hold during reset for the ROM USB/serial bootloader"))
    s.wire(bt, SW1["1"])
    s.power("power:GND", *SW1["2"])
    for ref, x, name in (("R10", 373.38, "IO8_STRAP"), ("R11", 393.7, "IO2_STRAP")):
        n = pullup(ref, x, name, f"{name.split('_')[0]} strapping pull-up")
        s.wire((n[0] - 7.62, n[1]), n)
        s.label(name, (n[0] - 7.62, n[1]))
    s.block("MODULE SUPPORT: reset, boot, strapping", 289.56, 30.48, 406.4, 88.9)

    # ---------------- USB-C and debug pads ---------------------------------
    UX, UY = 309.88, 132.08
    J6 = s.place("Connector:USB_C_Receptacle_USB2.0_16P", "J6", "USB-C", UX, UY,
                 ref_at=(0, -25.4), val_at=(0, -22.86),
                 fields=jlc("C165948", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                            "HRO TYPE-C-31-M-12, USB 2.0 device (native USB on GPIO18/19)"))
    vb = J6["A4"]
    D4 = s.place_by_pin("Device:D_Schottky", "D4", "B5819W", "2", (vb[0] + 7.62, vb[1]), rot=180,
                        ref_at=(0, -3.81), val_at=(0, 3.175),
                        fields=jlc("C8598", "Diode_SMD:D_SOD-123",
                                   "USB VBUS into +5V; blocks +5V from back-feeding the USB host"))
    s.wire(vb, (vb[0] + 2.54, vb[1]))
    s.wire((vb[0] + 2.54, vb[1]), D4["2"])
    s.wire(D4["1"], (D4["1"][0] + 5.08, vb[1]))
    s.power("power:+5V", D4["1"][0] + 5.08, vb[1])
    s.wire((vb[0] + 2.54, vb[1]), (vb[0] + 2.54, vb[1] - 5.08))
    s.label("VBUS", (vb[0] + 2.54, vb[1] - 5.08))
    for a, b, name in (("A7", "B7", "USB_DN"), ("A6", "B6", "USB_DP")):
        pa, pb = J6[a], J6[b]
        xj = pa[0] + 5.08
        s.wire(pa, (xj, pa[1]))
        s.wire(pb, (xj, pb[1]))
        s.wire((xj, pa[1]), (xj, pb[1]))
        s.wire((xj, pa[1]), (xj + 12.7, pa[1]))
        s.label(name, (xj + 12.7, pa[1]), justify="right bottom")
    for i, (cc, ref) in enumerate((("A5", "CC1"), ("B5", "CC2"))):
        p = J6[cc]
        s.wire(p, (p[0] + 15.24 + 2.54 * i, p[1]))
        s.label(ref, (p[0] + 15.24 + 2.54 * i, p[1]), justify="right bottom")
        x = round(309.88 + 17.78 * i, 2)
        r = s.place_by_pin("Device:R", f"R{12 + i}", "5.1k", "1", (x, 165.1 - 17.78),
                           ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                           fields=jlc("C23186", R0603, "USB-C CC pull-down (sink)"))
        s.wire((x, r["1"][1] - 2.54), r["1"])
        s.label(ref, (x, r["1"][1] - 2.54))
        s.power("power:GND", *r["2"])
    for pin in ("A8", "B8"):
        s.no_connect(f"J6.{pin}")
    g = J6["A1"]
    s.wire(J6["SH"], g)
    s.power("power:GND", *g)
    TPF = {"Footprint": "TestPoint:TestPoint_Pad_D1.5mm"}
    for i, (ref, name) in enumerate((("TP1", "VBUS"), ("TP2", "USB_DN"), ("TP3", "USB_DP"),
                                     ("TP4", "GND"), ("TP5", "U0TXD"), ("TP6", "U0RXD"))):
        x = round(350.52 + 10.16 * i, 2)
        tp = s.place_by_pin("Connector:TestPoint", ref, name, "1", (x, 116.84),
                            ref_at=(0, -5.08), val_at=None, fields=TPF)
        s.wire(tp["1"], (x, 121.92))
        if name == "GND":
            s.power("power:GND", x, 121.92)
        else:
            s.label(name, (x, 121.92))
    s.text("Bench flashing: 5V, D-, D+, GND on TP1-TP4\n(native USB), or J6.\n"
           "Hold BOOT, tap RESET: ROM bootloader.\nTP5/TP6: UART0 log (3.3 V).", 350.52, 132.08)
    s.block("USB-C + DEBUG PADS", 289.56, 101.6, 406.4, 172.72)

    # ---------------- Mounting holes --------------------------------------
    for i in range(4):
        s.place("Mechanical:MountingHole", f"H{i + 1}", "#2", 177.8 + 12.7 * i, 147.32,
                ref_at=(0, -3.81), val_at=None,
                fields={"Footprint": "MountingHole:MountingHole_2.5mm"})
    s.text("2.5 mm NPTH. H1/H2 on the Hammond 1551K PCB bosses (#2 x 3/16\" self-tapping); H3/H4 bench only.",
           177.8, 154.94)

    # ---------------- Notes ----------------------------------------------
    s.note("1. BTN = CON1-5, Parking Safety switch (~200R to GND in the panel), 12.2 V idle. "
           "Q1 + R3 emulate a press (in car: GPIO3 ~2.5 V released, ~0.1 V pressed).\n"
           "2. CAN is silent by default: R6 holds S high and firmware keeps it high "
           "(listen-only). No 120R termination on this board.\n"
           "3. GPIO2/8/9 are strapping pins, held high by R11/R10/R9 (BOOT pulls GPIO9 low). D3 on GPIO1 is the board LED.\n"
           "4. Every part has an LCSC field for JLC assembly.",
           15.24, 140.97, 160.02, 13.97)
    return s

TITLE = ["title_block",
         ["title", Q("Ioniq 5 Parking Safety auto-disable: ESP32-C3 add-on")],
         ["date", Q("2026-11-16")],
         ["rev", Q("C (draft)")],
         ["company", Q("ioniq-auto-braking-disable")],
         ["comment", 1, Q("Taps CON1 of the console switch panel PCB IP-678A")],
         ["comment", 2, Q("BTN = CON1-5 (Parking Safety switch line), 12.2 V idle in the car")],
         ["comment", 3, Q("Generated by tools/gen.py; edit the generator, not the sheet")]]


def write_project_files():
    pro = {
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 3},
        "boards": [],
        "sheets": [[ROOT_UUID, "Root"]],
        "text_variables": {},
    }
    pro_path = os.path.join(PROJ_DIR, f"{NAME}.kicad_pro")
    if not os.path.exists(pro_path):  # KiCad owns the project file once it has saved it
        with open(pro_path, "w") as fh:
            json.dump(pro, fh, indent=2)
            fh.write("\n")
    with open(os.path.join(PROJ_DIR, "fp-lib-table"), "w") as fh:
        fh.write('(fp_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")'
                 '(uri "${KIPRJMOD}/%s.pretty")(options "")(descr "Project footprints: '
                 'ESP32-C3-WROOM-02 (JLC drill), WAGO 2060, TS-1187A"))\n)\n' % (LIBNAME, LIBNAME))
    with open(os.path.join(PROJ_DIR, "sym-lib-table"), "w") as fh:
        fh.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")'
                 '(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "Project symbols '
                 '(none at present)"))\n)\n' % (LIBNAME, LIBNAME))


if __name__ == "__main__":
    import footprints
    footprints.write_all()
    write_project_lib()
    write_project_files()
    sheet = build()
    sheet.write(os.path.join(PROJ_DIR, f"{NAME}.kicad_sch"), TITLE)
    print("wrote", PROJ_DIR)
