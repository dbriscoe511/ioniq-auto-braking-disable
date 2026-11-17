"""Minimal S-expression reader/writer for KiCad files.

Quoted strings are parsed to ``Q`` (a str subclass); bare atoms (keywords and
numbers) stay plain ``str``. Lists are Python lists.
"""


class Q(str):
    """A quoted string atom."""


def parse(text):
    pos = 0
    n = len(text)
    stack = [[]]
    while pos < n:
        c = text[pos]
        if c in " \t\r\n":
            pos += 1
        elif c == "(":
            stack.append([])
            pos += 1
        elif c == ")":
            done = stack.pop()
            stack[-1].append(done)
            pos += 1
        elif c == '"':
            pos += 1
            buf = []
            while text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                    buf.append({"n": "\n", "t": "\t"}.get(text[pos], text[pos]))
                else:
                    buf.append(text[pos])
                pos += 1
            pos += 1
            stack[-1].append(Q("".join(buf)))
        else:
            start = pos
            while pos < n and text[pos] not in ' \t\r\n()"':
                pos += 1
            stack[-1].append(text[start:pos])
    assert len(stack) == 1
    return stack[0][0] if len(stack[0]) == 1 else stack[0]


def _atom(a):
    if isinstance(a, Q):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(a, float):
        s = f"{a:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(a)


# Short lists that read best on a single line.
_INLINE = {"at", "xy", "size", "start", "end", "mid", "center", "radius", "length",
           "offset", "width", "type", "color", "uuid", "hide", "justify", "unit",
           "reference", "lib_id", "exclude_from_sim", "in_bom", "on_board", "dnp",
           "fields_autoplaced", "page", "paper", "version", "generator",
           "generator_version", "in_pos_files", "show_name", "do_not_autoplace",
           "bold", "italic", "thickness", "embedded_fonts", "pin_names", "pin_numbers",
           "duplicate_pin_numbers_are_jumpers", "extends", "diameter", "convert", "body_style"}


def dump(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    head = node[0] if node and not isinstance(node[0], list) else None
    simple = all(not isinstance(x, list) for x in node)
    if simple and (head in _INLINE or len(node) <= 4):
        return "(" + " ".join(_atom(x) for x in node) + ")"
    if head == "pts":
        return "(pts " + " ".join(dump(x) for x in node[1:]) + ")"
    tab = "\t" * (indent + 1)
    out = ["("]
    # keep leading atoms on the opening line
    i = 0
    atoms = []
    while i < len(node) and not isinstance(node[i], list):
        atoms.append(_atom(node[i]))
        i += 1
    out.append(" ".join(atoms))
    for child in node[i:]:
        out.append("\n" + tab + dump(child, indent + 1))
    out.append("\n" + "\t" * indent + ")")
    return "".join(out)


def find(node, key):
    """First child list whose head is ``key``."""
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def findall(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]
