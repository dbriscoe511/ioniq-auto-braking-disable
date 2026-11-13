#!/usr/bin/env python3
"""Compare the exported KiCad netlist against the intended connectivity.

ERC passes on a miswired divider, so this is the real wiring test.
"""
import sys

from sexp import find, findall, parse

EXPECTED = {
    "VBAT_IN (tap -> fuse)": {"J1.1", "F1.1"},
    "VBAT_F": {"F1.2", "D1.1", "C1.1", "U1.1"},
    "5V_REG": {"U1.3", "C2.1", "D2.2"},
    "+5V": {"D2.1", "C3.1", "U2.1"},
    "+3V3": {"U2.3", "U3.1", "R6.1"},
    "CAN_SLNT (GPIO5)": {"U2.9", "U3.5", "R6.2"},
    "CAN_TX (GPIO6)": {"U2.10", "U3.3"},
    "GND": {"J1.5", "D1.2", "C1.2", "U1.2", "C2.2", "C3.2", "U2.2", "R5.2", "C4.2",
            "U3.2", "R2.2", "Q1.1"},
    "CANH": {"J1.2", "U3.6"},
    "CANL": {"J1.3", "U3.7"},
    "BTN": {"J1.4", "R4.1", "R3.1"},
    "BTN_SENSE (GPIO3)": {"R4.2", "R5.1", "C4.1", "U2.5"},
    "CAN_RX (GPIO7)": {"U2.11", "U3.4"},
    "BTN_DRIVE (GPIO10)": {"U2.14", "R1.1"},
    "Q1 base": {"R1.2", "R2.1", "Q1.2"},
    "Q1 collector": {"Q1.3", "R3.2"},
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
