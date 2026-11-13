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
# Custom symbols (no stock KiCad symbol exists for these two breakout modules)
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


def supermini_symbol():
    # Pin numbers follow the two 8-pin headers of the common ESP32-C3 SuperMini
    # (USB at top, component side up): left 1..8 = 5V, GND, 3V3, GPIO4..GPIO0;
    # right 9..16 = GPIO5..GPIO10, GPIO20, GPIO21.
    pins = [
        _pin("power_in", -2.54, 17.78, 270, "5V", "1"),
        _pin("power_out", 2.54, 17.78, 270, "3V3", "3"),
        _pin("power_in", 0, -20.32, 90, "GND", "2"),
    ]
    left = [("GPIO0", "8"), ("GPIO1", "7"), ("GPIO2/STRAP", "6"), ("GPIO3/ADC1_3", "5"),
            ("GPIO4", "4")]
    for i, (n, num) in enumerate(left):
        pins.append(_pin("bidirectional", -22.86, 5.08 - 2.54 * i, 0, n, num))
    right = [("GPIO5", "9"), ("GPIO6", "10"), ("GPIO7", "11"), ("GPIO8/STRAP/LED", "12"),
             ("GPIO9/STRAP/BOOT", "13"), ("GPIO10", "14"), ("GPIO20/U0RXD", "15"),
             ("GPIO21/U0TXD", "16")]
    for i, (n, num) in enumerate(right):
        pins.append(_pin("bidirectional", 22.86, 10.16 - 2.54 * i, 180, n, num))
    return _custom(
        "ESP32-C3_SuperMini", "U",
        "ESP32-C3 SuperMini",
        "ESP32-C3 SuperMini module (USB-C, onboard 3.3 V LDO, LED on GPIO8). "
        "Pin numbers = header positions, left 1-8 then right 1-8; verify against the board silkscreen.",
        "ESP32 ESP32-C3 SuperMini module WiFi BLE RISC-V",
        _rect(-17.78, 12.7, 17.78, -15.24), pins, (-17.78, 15.24), (2.54, -17.78))


def canpal_symbol():
    pins = [
        _pin("power_in", 0, 15.24, 270, "Vcc", "1"),
        _pin("power_in", 0, -15.24, 90, "GND", "2"),
        _pin("input", -15.24, 2.54, 0, "SLNT", "5"),
        _pin("input", -15.24, 0, 0, "TX", "3"),
        _pin("output", -15.24, -2.54, 0, "RX", "4"),
        _pin("bidirectional", 15.24, 2.54, 180, "CANH", "6"),
        _pin("bidirectional", 15.24, 0, 180, "CANL", "7"),
    ]
    return _custom(
        "Adafruit_CAN_Pal", "U", "Adafruit CAN Pal",
        "Adafruit CAN Pal CAN transceiver breakout (TJA1051T/3), Adafruit 5708 / DigiKey 1528-5708-ND. "
        "Vcc 3-5 V (onboard 5 V boost for the transceiver). SLNT high = silent (no transmit). "
        "120R termination via onboard switch. Pin numbers are symbol-only.",
        "CAN transceiver TJA1051 breakout Adafruit",
        _rect(-10.16, 10.16, 10.16, -10.16), pins, (2.54, 12.7), (2.54, -12.7),
        ds="https://learn.adafruit.com/adafruit-can-pal")


def write_project_lib():
    lib = ["kicad_symbol_lib", ["version", 20251024], ["generator", Q("esp32c3_recovery_gen")],
           ["generator_version", Q("10.0")], supermini_symbol(), canpal_symbol()]
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
              fields=None, hide_value=False, extra_hidden=None, just=None):
        """Place a symbol. ref_at / val_at are offsets (dx, dy) from the origin
        for centred, horizontal field text (or None to hide)."""
        sym = self._libsym(lib_id)
        pins = kilib.pins(sym)
        is_power = ref.startswith("#")
        fa = rot % 180  # field angle that keeps text horizontal on screen
        node = ["symbol", ["lib_id", Q(lib_id)], ["at", f(x), f(y), rot], ["unit", 1],
                ["exclude_from_sim", "no"], ["in_bom", "no" if is_power else "yes"],
                ["on_board", "no" if is_power else "yes"], ["dnp", "no"],
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

    def power(self, lib_id, x, y, rot=0, show=True):
        if lib_id == "power:PWR_FLAG":
            self.flg_n += 1
            ref = f"#FLG0{self.flg_n}"
        else:
            self.pwr_n += 1
            ref = f"#PWR0{self.pwr_n:02d}"
        value = lib_id.split(":")[1]
        # value text sits beyond the symbol body, away from the pin
        off = {"power:GND": (0, 3.81), "power:PWR_FLAG": (0, -3.81)}.get(lib_id, (0, -3.81))
        return self.place(lib_id, ref, value, x, y, rot, val_at=off if show else None)

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
               ["generator_version", Q("10.0")], ["uuid", Q(ROOT_UUID)], ["paper", Q("A4")],
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

def build():
    s = Sheet()
    L = LIBNAME
    VB_Y = 40.64        # VBAT / +5V rail
    GND_Y = 68.58       # power-block ground bus

    # ---------------- Panel tap -----------------------------------------
    J = s.place("Connector:Conn_01x05_Pin", "J1", "Panel tap", 40.64, VB_Y + 5.08,
                ref_at=(1.27, -7.62), val_at=(1.27, 7.62),
                fields={"Description": "5-wire tap into the console switch panel (CON1 + button line)"})
    for i, t in enumerate(["CON1-1  VBAT", "CON1-8  CAN-H", "CON1-7  CAN-L",
                           "BTN line (note 1)", "CON1-16  GND"]):
        s.text(t, 36.83, VB_Y + 2.54 * i + 0.635, justify="right bottom")
    for pin, name in (("2", "CANH"), ("3", "CANL"), ("4", "BTN")):
        p = J[pin]
        s.wire(p, (p[0] + 7.62, p[1]))
        s.label(name, (p[0] + 7.62, p[1]))
    s.block("PANEL TAP", 15.24, 30.48, 60.96, 73.66)

    # ---------------- Power ----------------------------------------------
    F1 = s.place_by_pin("Device:Polyfuse", "F1", "500mA hold", "1", (68.58, VB_Y), rot=90,
                        ref_at=(0, -5.715), val_at=(0, -3.175),
                        fields={"Description": "PTC resettable fuse, ~0.5 A hold, >=30 V rating"})
    s.wire(J["1"], F1["1"])
    xn = 83.82
    D1 = s.place_by_pin("Diode:SMAJ18A", "D1", "SMAJ18A", "1", (xn, 50.8), rot=270,
                        ref_at=(-2.54, -1.27), val_at=(-2.54, 1.27), just="right")
    C1 = s.place_by_pin("Device:C", "C1", "0.33u", "1", (93.98, 50.8),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left")
    U1 = s.place("Regulator_Linear:LM7805_TO220", "U1", "LM7805", 114.3, VB_Y,
                 ref_at=(0, -6.35), val_at=(0, -3.81))
    C2 = s.place_by_pin("Device:C", "C2", "0.1u", "1", (129.54, 50.8),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left")
    D2 = s.place_by_pin("Diode:1N5819", "D2", "1N5819", "2", (137.16, VB_Y), rot=180,
                        ref_at=(0, -3.81), val_at=(0, 3.175))
    C3 = s.place_by_pin("Device:C_Polarized", "C3", "22u", "1", (152.4, 50.8),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields={"Description": "Bulk at the module 5V pin, tantalum or low-ESR electrolytic, >=10 V"})
    s.wire(F1["2"], (xn, VB_Y), D1["1"])
    s.wire((xn, VB_Y), (C1["1"][0], VB_Y), C1["1"])
    s.wire((C1["1"][0], VB_Y), U1["1"])
    s.wire(U1["3"], (C2["1"][0], VB_Y), C2["1"])
    s.wire((C2["1"][0], VB_Y), D2["2"])
    s.power("power:PWR_FLAG", 88.9, VB_Y)
    s.label("VBAT", (99.06, VB_Y))
    j5 = J["5"]
    s.wire(j5, (j5[0] + 2.54, j5[1]), (j5[0] + 2.54, GND_Y), (C3["2"][0], GND_Y))
    for p in (D1["2"], C1["2"], U1["2"], C2["2"], C3["2"]):
        s.wire(p, (p[0], GND_Y))
    s.power("power:GND", 114.3, GND_Y)
    s.power("power:PWR_FLAG", 71.12, GND_Y)
    s.block("POWER: 12 V -> 5 V", 62.23, 30.48, 166.37, 77.47)

    # ---------------- MCU -------------------------------------------------
    MX, MY = 195.58, 68.58
    U2 = s.place(f"{L}:ESP32-C3_SuperMini", "U2", "ESP32-C3 SuperMini", MX, MY,
                 ref_at=(-12.7, -15.24), val_at=(12.7, 19.05))
    s.wire(D2["1"], (C3["1"][0], VB_Y), C3["1"])
    s.wire((C3["1"][0], VB_Y), (U2["1"][0], VB_Y), U2["1"])
    s.power("power:+5V", 177.8, VB_Y)
    s.power("power:PWR_FLAG", 160.02, VB_Y)
    s.power("power:+3V3", *U2["3"])
    s.power("power:GND", *U2["2"])
    for num in ("8", "7", "6", "4", "12", "13", "15", "16"):
        s.no_connect(f"U2.{num}")
    s.block("MCU", 168.91, 30.48, 222.25, 95.25)

    # ---------------- Press sense (BTN -> GPIO3) --------------------------
    SY = 106.68
    R4 = s.place_by_pin("Device:R", "R4", "100k", "1", (130.81, SY), rot=90,
                        ref_at=(0, -2.54), val_at=(0, 2.54))
    s.wire((123.19, SY), R4["1"])
    s.label("BTN", (123.19, SY), justify="right bottom")
    nx = 144.78
    R5 = s.place_by_pin("Device:R", "R5", "27k", "1", (nx, SY + 5.08),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left")
    C4 = s.place_by_pin("Device:C", "C4", "100n", "1", (nx + 10.16, SY + 5.08),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left")
    s.wire(R4["2"], (nx, SY), R5["1"])
    s.wire((nx, SY), (C4["1"][0], SY), C4["1"])
    g = SY + 17.78
    s.wire(R5["2"], (nx, g), (C4["2"][0], g), C4["2"])
    s.power("power:GND", nx + 5.08, g)
    gp3 = U2["5"]
    s.wire((C4["1"][0], SY), (gp3[0] - 2.54, SY), (gp3[0] - 2.54, gp3[1]), gp3)
    s.block("PRESS SENSE (ADC, ~1 V threshold)", 110.49, 97.79, 166.37, 133.35)

    # ---------------- CAN -------------------------------------------------
    gp7 = U2["11"]
    CX = 251.46
    U3 = s.place_by_pin(f"{L}:Adafruit_CAN_Pal", "U3", "Adafruit CAN Pal", "4", (CX - 15.24, gp7[1]),
                        ref_at=(7.62, -12.7), val_at=(10.16, 12.7),
                        fields={"Description": "Adafruit 5708 / DigiKey 1528-5708-ND, TJA1051T/3"})
    s.wire(gp7, U3["4"])           # RX  -> GPIO7
    s.wire(U2["9"], U3["5"])       # GPIO5 -> SLNT
    s.wire(U2["10"], U3["3"])      # GPIO6 -> TX
    sl, vcc = U3["5"], U3["1"]
    rx = 228.6
    R6 = s.place_by_pin("Device:R", "R6", "10k", "2", (rx, sl[1]),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left",
                        fields={"Description": "SLNT pull-up: transceiver silent unless firmware drives GPIO5 low"})
    s.wire(R6["1"], (rx, vcc[1] - 2.54), (vcc[0], vcc[1] - 2.54), vcc)
    s.power("power:+3V3", vcc[0], vcc[1] - 2.54)
    s.power("power:GND", *U3["2"])
    for pin, name in (("6", "CANH"), ("7", "CANL")):
        p = U3[pin]
        s.wire(p, (p[0] + 7.62, p[1]))
        s.label(name, (p[0] + 7.62, p[1]))
    s.block("CAN (silent by default)", 226.06, 30.48, 284.48, 82.55)

    # ---------------- Button press output (GPIO10 -> NPN -> BTN) ----------
    gp10 = U2["14"]
    BY = 111.76
    R1 = s.place_by_pin("Device:R", "R1", "1k", "1", (233.68, BY), rot=90,
                        ref_at=(0, -2.54), val_at=(0, 2.54))
    s.wire(gp10, (gp10[0] + 5.08, gp10[1]), (gp10[0] + 5.08, BY), R1["1"])
    bx = 246.38
    Q1 = s.place_by_pin("Transistor_BJT:2N3904", "Q1", "2N3904", "2", (bx + 5.08, BY),
                        ref_at=(5.08, -1.27), val_at=(5.08, 1.27), just="left")
    R2 = s.place_by_pin("Device:R", "R2", "10k", "1", (bx, BY + 5.08),
                        ref_at=(-2.54, -1.27), val_at=(-2.54, 1.27), just="right")
    s.wire(R1["2"], (bx, BY), R2["1"])
    s.wire((bx, BY), Q1["2"])
    g = BY + 15.24
    s.wire(R2["2"], (bx, g), (Q1["1"][0], g), Q1["1"])
    s.power("power:GND", bx + 5.08, g)
    R3 = s.place_by_pin("Device:R", "R3", "200", "2", (Q1["3"][0], BY - 10.16),
                        ref_at=(2.54, -1.27), val_at=(2.54, 1.27), just="left")
    s.wire(R3["2"], Q1["3"])
    top = (R3["1"][0], R3["1"][1] - 2.54)
    s.wire(R3["1"], top, (top[0] + 12.7, top[1]))
    s.label("BTN", (top[0] + 12.7, top[1]))
    s.block("BUTTON PRESS OUTPUT", 226.06, 88.9, 284.48, 133.35)

    # ---------------- Notes ----------------------------------------------
    s.note("1. BTN = the Parking Safety button line (the \"pin 5 wire\" in the design chat). "
           "Its CON1 pin or PCB pad is NOT verified: the panel MCU may read the switch locally "
           "(docs/electronics.md). Trace the switch pads and measure idle/pressed voltage first. "
           "R3/R4/R5 assume BTN idles near VBAT (12-14.4 V) and is pulled to ~0 V when pressed; "
           "a stiff 5 V line would read ~1.06 V on GPIO3, right at the threshold.",
           15.24, 138.43, 78.74, 21.59)
    s.note("2. TX is wired (GPIO6) so the board CAN transmit, but it is silent by default: R6 "
           "pulls SLNT high (TJA1051 transmitter off) during boot/reset, and firmware drives "
           "GPIO5 high and runs TWAI listen-only. It never sends unless the firmware is changed "
           "on purpose. Hard lock: cut the GPIO5 link, tie SLNT to 3V3.\n"
           "3. Set the CAN Pal 120R termination switch OFF: the car bus is already terminated.\n"
           "4. ESP32-C3 TWAI is classic CAN only; confirm the panel bus carries no CAN FD frames.",
           96.52, 138.43, 78.74, 21.59)
    s.note("6. GPIO2/8/9 are strapping pins (GPIO8 = onboard LED): leave unconnected. GPIO10 is "
           "not a strap; R2 holds Q1 off during boot. GPIO20/21 (UART0) kept free for serial debug.\n"
           "7. VBAT is tapped on the PCB side of the panel's reverse-polarity diodes D1/D2; one "
           "common ground with the panel (CON1-16). F1 limits fault current if D1 fails short. "
           "D2 blocks USB 5 V back-feeding U1. LM7805: 35 V max input; SMAJ18A clamps ~29 V.",
           15.24, 162.56, 160.02, 11.43)
    s.note("5. R3 = 200R gives 60-70 mA if BTN is a stiff 12-14 V node; raise to 470R-1k if the "
           "measured pull-up allows. Firmware ignores GPIO3 while Q1 is on and caps press time.",
           177.8, 138.43, 106.68, 10.16)
    return s


TITLE = ["title_block",
         ["title", Q("Ioniq 5 Parking Safety auto-disable: ESP32-C3 add-on")],
         ["date", Q("2026-11-13")],
         ["rev", Q("A (draft)")],
         ["company", Q("ioniq-auto-braking-disable")],
         ["comment", 1, Q("Taps CON1 of the console switch panel PCB IP-678A")],
         ["comment", 2, Q("BTN tap point and its idle voltage are unverified, see notes")],
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
    with open(os.path.join(PROJ_DIR, "sym-lib-table"), "w") as fh:
        fh.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "%s")(type "KiCad")'
                 '(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "Project symbols: '
                 'ESP32-C3 SuperMini, Adafruit CAN Pal"))\n)\n' % (LIBNAME, LIBNAME))


if __name__ == "__main__":
    write_project_lib()
    write_project_files()
    sheet = build()
    sheet.write(os.path.join(PROJ_DIR, f"{NAME}.kicad_sch"), TITLE)
    print("wrote", PROJ_DIR)
