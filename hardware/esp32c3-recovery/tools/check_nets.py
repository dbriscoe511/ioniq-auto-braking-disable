#!/usr/bin/env python3
"""Compare the exported KiCad netlist against the intended connectivity.

ERC passes on a miswired divider, so this is the real wiring test.
"""
import sys

from sexp import find, findall, parse

EXPECTED = {
    "VBAT_IN (tap -> fuse)": {"J1.1", "F1.1"},
    "VBAT_F": {"F1.2", "D1.1", "C1.1", "U1.1"},
    "5V_REG": {"U1.3", "C2.1", "D2.2", "U3.3", "C5.1"},
    "+5V": {"D2.1", "C3.1", "U4.3", "D4.1"},
    "VBUS": {"D4.2", "J6.A4", "J6.A9", "J6.B4", "J6.B9", "TP1.1"},
    "+3V3": {"U4.2", "C7.1", "C8.1", "C10.1", "U2.1", "U3.5", "R6.1", "C6.1",
             "R8.1", "R9.1", "R10.1", "R11.1"},
    "EN": {"U2.2", "R8.2", "C9.1", "SW2.1"},
    "IO9_BOOT": {"U2.8", "R9.2", "SW1.1"},
    "IO8_STRAP": {"U2.7", "R10.2"},
    "IO2_STRAP": {"U2.16", "R11.2"},
    "USB_DN (GPIO18)": {"U2.13", "J6.A7", "J6.B7", "TP2.1"},
    "USB_DP (GPIO19)": {"U2.14", "J6.A6", "J6.B6", "TP3.1"},
    "CC1": {"J6.A5", "R12.1"},
    "CC2": {"J6.B5", "R13.1"},
    "U0TXD": {"U2.12", "TP5.1"},
    "U0RXD": {"U2.11", "TP6.1"},
    "CAN_S (GPIO5)": {"U2.4", "U3.8", "R6.2"},
    "CAN_TX (GPIO6)": {"U2.5", "U3.1"},
    "CAN_RX (GPIO7)": {"U2.6", "U3.4"},
    "GND": {"J5.1", "D1.2", "C1.2", "U1.2", "C2.2", "C3.2", "U2.9", "U2.19", "R5.2", "C4.2",
            "U3.2", "C5.2", "C6.2", "R2.2", "Q1.2", "D3.1", "U4.1", "C7.2", "C8.2", "C9.2",
            "C10.2", "SW1.2", "SW2.2", "R12.2", "R13.2", "J6.A1", "J6.A12", "J6.B1", "J6.B12",
            "J6.SH", "TP4.1"},
    "CANH": {"J2.1", "U3.7"},
    "CANL": {"J3.1", "U3.6"},
    "BTN": {"J4.1", "R4.1", "R3.1"},
    "BTN_SENSE (GPIO3)": {"R4.2", "R5.1", "C4.1", "U2.15"},
    "BTN_DRIVE (GPIO10)": {"U2.10", "R1.1"},
    "Q1 base": {"R1.2", "R2.1", "Q1.1"},
    "Q1 collector": {"Q1.3", "R3.2"},
    "LED (GPIO1)": {"U2.17", "R7.1"},
    "LED anode": {"R7.2", "D3.2"},
}


def main(path):
    net = parse(open(path).read())
    got = {}
    for n in findall(find(net, "nets"), "net"):
        nodes = {f"{find(x, 'ref')[1]}.{find(x, 'pin')[1]}" for x in findall(n, "node")}
        nodes = {x for x in nodes if not x.startswith("#")}
        if nodes:
            got[str(find(n, "name")[1])] = nodes
    want = {frozenset(v): k for k, v in EXPECTED.items()}
    ok = True
    matched = set()
    for name, nodes in sorted(got.items()):
        key = frozenset(nodes)
        if key in want:
            matched.add(key)
        elif len(nodes) == 1:
            pass  # single unconnected pin (no-connect flagged), checked below
        else:
            ok = False
            print(f"UNEXPECTED net {name}: {sorted(nodes)}")
    for key, label in want.items():
        if key not in matched:
            ok = False
            print(f"MISSING net {label}: {sorted(key)}")
    singles = sorted(next(iter(v)) for v in got.values() if len(v) == 1)
    print("single-pin nets:", singles)
    print("NETLIST OK" if ok else "NETLIST MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
