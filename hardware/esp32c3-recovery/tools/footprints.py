#!/usr/bin/env python3
"""Write the project footprints (no stock KiCad footprint exists for these).

ESP32-C3-WROOM-02_JLC    stock module footprint without its 0.2 mm ground-pad vias
SW_TS-1187A              5.1 mm SMD tactile switch (JLC basic C318884)
WAGO_2060-451_998-404    single-pole SMD push-in terminal (JLC-placed, C2765054)

Text-only (no pcbnew import) so gen.py can call it before ERC.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FPLIB = os.path.join(os.path.dirname(HERE), "esp32c3_recovery.pretty")


def _line(layer, x1, y1, x2, y2, w):
    return (f'  (fp_line (start {x1} {y1}) (end {x2} {y2}) (stroke (width {w}) (type solid))'
            f' (layer "{layer}"))\n')


def _rect(layer, x1, y1, x2, y2, w):
    return (f'  (fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width {w}) (type solid))'
            f' (fill no) (layer "{layer}"))\n')


MODEL_DIR = "${KIPRJMOD}/esp32c3_recovery.3dshapes"


def _model(name, dx=0.0, dy=0.0, rz=0.0):
    """KiCad 3D offsets are in the 3D frame (+Y = footprint -Y)."""
    return (f'  (model "{MODEL_DIR}/{name}.step"\n'
            f'    (offset (xyz {dx} {dy} 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 {rz})))\n')


def _head(name, descr, ref_y, val_y, attr):
    return [f'(footprint "{name}" (version 20241229) (generator "esp32c3_recovery")\n',
            '  (layer "F.Cu")\n',
            f'  (descr "{descr}")\n',
            f'  (property "Reference" "REF**" (at 0 {ref_y} 0) (layer "F.Fab")'
            ' (effects (font (size 0.6 0.6) (thickness 0.1))))\n',
            f'  (property "Value" "{name}" (at 0 {val_y} 0) (layer "F.Fab") (hide yes)'
            ' (effects (font (size 0.6 0.6) (thickness 0.1))))\n',
            f'  (attr {attr})\n']


STOCK_WROOM02 = "/usr/share/kicad/footprints/RF_Module.pretty/ESP32-C3-WROOM-02.kicad_mod"


def wroom02():
    """KiCad's stock ESP32-C3-WROOM-02 footprint minus the twelve 0.2 mm via
    pads in its ground pad (JLC's standard minimum drill is 0.3 mm). The PCB
    script puts five 0.3 mm vias there instead (gen_pcb.add_ep_vias)."""
    import re
    src = open(STOCK_WROOM02).read()
    out, n = re.subn(r'\t\(pad "19" thru_hole circle\n.*?\n\t\)\n', "", src, flags=re.S)
    assert n == 12, n
    out = out.replace('(footprint "ESP32-C3-WROOM-02"', '(footprint "ESP32-C3-WROOM-02_JLC"', 1)
    return out


def ts1187a():
    """XKB TS-1187A-B-A-B 5.1 x 5.1 mm SMD tactile switch (JLC basic C318884), pads
    from JLC's own footprint. The two top pads are one side of the switch and
    the two bottom pads the other (JLC's symbol: 1-2 joined, 3-4 joined), so
    they are numbered 1, 1, 2, 2 to match Device SW_Push pins 1 and 2."""
    out = _head("SW_TS-1187A", "TS-1187A 5.1x5.1mm SMD tactile switch, 4 pads (C318884)",
                -3.4, 3.4, "smd")
    out += [_rect("F.Fab", -2.55, -2.55, 2.55, 2.55, 0.1),
            _rect("F.CrtYd", -3.75, -2.85, 3.75, 2.85, 0.05),
            _rect("F.SilkS", -2.7, -1.2, 2.7, 1.2, 0.12),
            _model("SW_TS-1187A")]
    for num, x, y in (("1", -3.0, -1.85), ("1", 3.0, -1.85), ("2", -3.0, 1.85), ("2", 3.0, 1.85)):
        out.append(f'  (pad "{num}" smd rect (at {x} {y}) (size 1.0 0.75) (layers "F.Cu" "F.Paste" "F.Mask"))\n')
    out.append(")\n")
    return "".join(out)


def wago_2060():
    """WAGO 2060-451/998-404 per the WAGO data sheet (version 11.02.2026):
    14 mm land pattern of a 6 x 2 mm pad under the conductor entry and a
    3.5 x 2 mm pad at the back (both the same potential), 4 mm pole pitch,
    pad width 2.0 = 1.2 mm contact tail + 0.4 mm each side; plastic body
    12.7 x 3.9 mm from 0.5 mm inside the front pad (x -6.5..6.2), contact tail to
    0.4 mm inside the back pad (x 6.6). Conductor enters from -X. Stencil = pads.
    JLC/EasyEDA's own footprint (1.7 mm pads, origin ~0.6 mm off the body centre)
    differs slightly; this one follows WAGO."""
    out = _head("WAGO_2060-451_998-404",
                "WAGO 2060-451/998-404 SMD push-in CAGE CLAMP terminal, 1 pole, 4 mm pitch, "
                "conductor entry toward -X",
                0, 1, "smd")
    out += [_rect("F.Fab", -6.5, -1.95, 6.2, 1.95, 0.1),
            _line("F.Fab", -6.5, 0, -5.5, 0, 0.1),                  # entry marker
            _rect("F.CrtYd", -7.25, -1.99, 7.25, 1.99, 0.05),
            _line("F.SilkS", -0.7, -2.07, 3.2, -2.07, 0.12),
            _line("F.SilkS", -0.7, 2.07, 3.2, 2.07, 0.12),
            # EasyEDA model for C2765054: native body x 0..13.1, entry at x=0
            _model("WAGO_2060-451_998-404", -6.5, 0, 0)]
    for x, w in ((-4.0, 6.0), (5.25, 3.5)):
        out.append(f'  (pad "1" smd rect (at {x} 0) (size {w} 2.0) (layers "F.Cu" "F.Paste" "F.Mask"))\n')
    out.append(")\n")
    return "".join(out)


def write_all():
    os.makedirs(FPLIB, exist_ok=True)
    for name, text in (("ESP32-C3-WROOM-02_JLC", wroom02()), ("SW_TS-1187A", ts1187a()),
                       ("WAGO_2060-451_998-404", wago_2060())):
        with open(os.path.join(FPLIB, name + ".kicad_mod"), "w") as fh:
            fh.write(text)


if __name__ == "__main__":
    write_all()
