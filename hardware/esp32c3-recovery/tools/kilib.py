"""Load symbols from KiCad libraries, flattening derived (extends) symbols."""
import copy
import math
import os

from sexp import Q, find, findall, parse

STOCK = "/usr/share/kicad/symbols"
_cache = {}


def _load_file(path):
    if path not in _cache:
        with open(path) as f:
            _cache[path] = parse(f.read())
    return _cache[path]


def _raw(lib_path, name):
    for s in findall(_load_file(lib_path), "symbol"):
        if s[1] == name:
            return s
    raise KeyError(f"{name} not in {lib_path}")


def _rename_units(node, old, new):
    for c in node:
        if isinstance(c, list) and c and c[0] == "symbol" and c[1].startswith(old + "_"):
            c[1] = Q(new + c[1][len(old):])


def load(lib_id, lib_path=None):
    """Return a flattened copy of a symbol, named with its full lib_id."""
    nick, name = lib_id.split(":")
    lib_path = lib_path or os.path.join(STOCK, nick + ".kicad_sym")
    sym = copy.deepcopy(_raw(lib_path, name))
    ext = find(sym, "extends")
    if ext:
        parent = load(f"{nick}:{ext[1]}", lib_path)
        pname = ext[1]
        # parent body with the child's properties
        props = {p[1]: p for p in findall(sym, "property")}
        body = []
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property" and c[1] in props:
                body.append(props.pop(c[1]))
            else:
                body.append(c)
        # child-only properties go right after the parent's property block
        last = max(i for i, c in enumerate(body) if isinstance(c, list) and c[0] == "property")
        body[last + 1:last + 1] = list(props.values())
        sym = ["symbol", Q(name)] + body
        _rename_units(sym, f"{nick}:{pname}", name)
        _rename_units(sym, pname, name)
    sym[1] = Q(lib_id)
    return sym


def pins(sym):
    """{number: (name, x, y, angle, etype)} in library (Y-up) coordinates."""
    out = {}

    def walk(n):
        for c in n:
            if isinstance(c, list) and c:
                if c[0] == "pin":
                    at = find(c, "at")
                    out[str(find(c, "number")[1])] = (
                        str(find(c, "name")[1]), float(at[1]), float(at[2]),
                        float(at[3]) if len(at) > 3 else 0.0, c[1])
                elif c[0] == "symbol":
                    walk(c)
    walk(sym)
    return out


def xform(px, py, x0, y0, rot):
    """Library point -> sheet point for a symbol at (x0, y0) rotated rot deg (CCW)."""
    sx, sy = px, -py
    t = math.radians(rot)
    c, s = round(math.cos(t)), round(math.sin(t))
    return (round(x0 + sx * c + sy * s, 4), round(y0 - sx * s + sy * c, 4))
