#!/usr/bin/env python3
"""Check that the project-library symbols embedded in the sheet match the
project .kicad_sym exactly (kicad-cli ERC does not reliably flag this)."""
import sys

from sexp import dump, find, findall, parse

sch = parse(open(sys.argv[1]).read())
lib = parse(open(sys.argv[2]).read())
nick = sys.argv[3]
emb = {str(s[1]): s for s in findall(find(sch, "lib_symbols"), "symbol")}
bad = 0
for s in findall(lib, "symbol"):
    key = f"{nick}:{s[1]}"
    e = emb.get(key)
    if e is None:
        continue
    e = [e[0], s[1]] + e[2:]
    if dump(e) != dump(s):
        bad += 1
        print("MISMATCH", key)
print("LIB OK" if not bad else "LIB MISMATCH")
sys.exit(1 if bad else 0)
