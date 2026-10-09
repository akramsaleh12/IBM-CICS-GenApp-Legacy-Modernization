"""
copybook_parser.py
-------------------
Parses IBM COBOL copybooks (fixed-format, columns 7-72) into a structured
field model that downstream tools (ddl_generator.py, vsam_loader.py) use to:
  - compute byte offsets/lengths for fixed-width VSAM record extracts
  - know which fields are COMP-3 (packed decimal), COMP/COMP-4 (binary),
    or DISPLAY (PIC X / PIC 9)
  - resolve OCCURS (fixed and DEPENDING ON) into repeating groups
  - resolve REDEFINES into alternate interpretations of the same bytes

This does NOT execute COBOL. It is a structural parser sufficient for
data-migration purposes (byte layout + type inference), not a compiler.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


COMMENT_PREFIX = "*"
PIC_RE = re.compile(r"PIC(?:TURE)?\s+([9XASVZ\d\(\)\+\-\.\,]+)", re.IGNORECASE)
LEVEL_NAME_RE = re.compile(r"^(\d+)\s+([A-Z0-9\-]+)", re.IGNORECASE)
OCCURS_FIXED_RE = re.compile(r"OCCURS\s+(\d+)\s+TIMES", re.IGNORECASE)
OCCURS_DEPENDING_RE = re.compile(
    r"OCCURS\s+(\d+)\s+TO\s+(\d+)\s+TIMES\s+DEPENDING\s+ON\s+([A-Z0-9\-]+)",
    re.IGNORECASE,
)
OCCURS_DEPENDING_SIMPLE_RE = re.compile(
    r"OCCURS\s+(\d+)\s+TIMES\s+DEPENDING\s+ON\s+([A-Z0-9\-]+)", re.IGNORECASE
)
REDEFINES_RE = re.compile(r"REDEFINES\s+([A-Z0-9\-]+)", re.IGNORECASE)
COMP3_RE = re.compile(r"COMP-3|COMPUTATIONAL-3|PACKED-DECIMAL", re.IGNORECASE)
COMP_RE = re.compile(r"COMP-4|COMPUTATIONAL-4|COMP\b|COMPUTATIONAL\b", re.IGNORECASE)


@dataclass
class Field:
    level: int
    name: str
    pic: Optional[str] = None
    usage: str = "DISPLAY"          # DISPLAY | COMP-3 | COMP
    occurs_min: int = 1
    occurs_max: int = 1
    occurs_depending_on: Optional[str] = None
    redefines: Optional[str] = None
    children: List["Field"] = field(default_factory=list)
    parent: Optional["Field"] = None

    # computed at layout time
    offset: int = 0          # byte offset within record (of ONE occurrence)
    length: int = 0          # byte length of ONE occurrence (physical storage)
    digits: int = 0          # total digits for numeric PIC
    decimals: int = 0        # digits right of implied decimal point
    signed: bool = False
    is_group: bool = False

    def path(self) -> str:
        chain = []
        n = self
        while n is not None:
            chain.append(n.name)
            n = n.parent
        return ".".join(reversed(chain))


def _clean_lines(text: str) -> List[str]:
    """Strip COBOL comment lines/sequence area, join continued statements."""
    lines = []
    for raw in text.splitlines():
        # Columns 1-6 = sequence number area, column 7 = indicator (* = comment)
        line = raw
        if len(line) >= 7 and line[6] == COMMENT_PREFIX:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        lines.append(stripped)

    # Join into full statements ending in '.'
    joined = " ".join(lines)
    statements = [s.strip() for s in joined.split(".") if s.strip()]
    return statements


def _parse_pic_digits(pic: str):
    """Return (total_digits, decimal_digits, signed) from a PIC clause like
    S9(09)V99 or 9(4) or X(20)."""
    signed = pic.upper().startswith("S")
    # Expand repetition syntax e.g. 9(09) -> 9999999999... not needed; count via regex
    int_digits = 0
    dec_digits = 0
    # split on V (implied decimal point)
    parts = pic.upper().split("V")
    int_part = parts[0]
    dec_part = parts[1] if len(parts) > 1 else ""

    def count_9s(segment: str) -> int:
        total = 0
        for m in re.finditer(r"9(\((\d+)\))?", segment):
            total += int(m.group(2)) if m.group(2) else 1
        return total

    int_digits = count_9s(int_part)
    dec_digits = count_9s(dec_part)
    return int_digits, dec_digits, signed


def _pic_display_length(pic: str, digits: int, decimals: int) -> int:
    """Byte length if stored as DISPLAY (zoned) - one byte per digit/char,
    sign is a zone overpunch (no extra byte)."""
    if pic.upper().find("X") >= 0:
        # PIC X(n)
        m = re.search(r"X\((\d+)\)", pic.upper())
        if m:
            return int(m.group(1))
        return pic.upper().count("X")
    return digits + decimals


def _comp3_length(digits: int) -> int:
    """Packed decimal storage: 2 digits per byte + 1 nibble for sign,
    rounded up. Formula: floor(digits/2) + 1."""
    return (digits // 2) + 1


def _comp_length(digits: int) -> int:
    """Binary (COMP/COMP-4) storage length per IBM Enterprise COBOL rules:
    1-4 digits -> 2 bytes (halfword)
    5-9 digits -> 4 bytes (fullword)
    10-18 digits -> 8 bytes (doubleword)"""
    if digits <= 4:
        return 2
    if digits <= 9:
        return 4
    return 8


def parse_copybook(text: str) -> List[Field]:
    """Parse copybook text into a flat token list, then build a tree based
    on level numbers. Returns the list of top-level (01) Field nodes."""
    statements = _clean_lines(text)
    flat: List[Field] = []

    for stmt in statements:
        m = LEVEL_NAME_RE.match(stmt)
        if not m:
            continue
        level = int(m.group(1))
        if level == 88:
            continue  # condition-names (VALUE clauses) - not physical storage
        name = m.group(2).upper()

        f = Field(level=level, name=name)

        pic_m = PIC_RE.search(stmt)
        if pic_m:
            f.pic = pic_m.group(1)

        if COMP3_RE.search(stmt):
            f.usage = "COMP-3"
        elif COMP_RE.search(stmt):
            f.usage = "COMP"

        redef_m = REDEFINES_RE.search(stmt)
        if redef_m:
            f.redefines = redef_m.group(1).upper()

        dep_m = OCCURS_DEPENDING_RE.search(stmt)
        if dep_m:
            f.occurs_min, f.occurs_max = int(dep_m.group(1)), int(dep_m.group(2))
            f.occurs_depending_on = dep_m.group(3).upper()
        else:
            dep2_m = OCCURS_DEPENDING_SIMPLE_RE.search(stmt)
            if dep2_m:
                f.occurs_max = int(dep2_m.group(1))
                f.occurs_min = 0
                f.occurs_depending_on = dep2_m.group(2).upper()
            else:
                fixed_m = OCCURS_FIXED_RE.search(stmt)
                if fixed_m:
                    f.occurs_min = f.occurs_max = int(fixed_m.group(1))

        if f.pic:
            digits, decimals, signed = _parse_pic_digits(f.pic)
            f.digits, f.decimals, f.signed = digits, decimals, signed
            if f.usage == "COMP-3":
                f.length = _comp3_length(digits + decimals)
            elif f.usage == "COMP":
                f.length = _comp_length(digits + decimals)
            else:
                f.length = _pic_display_length(f.pic, digits, decimals)
        else:
            f.is_group = True  # group item, length computed from children

        flat.append(f)

    # Build tree using a level stack
    roots: List[Field] = []
    stack: List[Field] = []
    for f in flat:
        while stack and stack[-1].level >= f.level:
            stack.pop()
        if stack:
            f.parent = stack[-1]
            stack[-1].children.append(f)
            stack[-1].is_group = True
        else:
            roots.append(f)
        stack.append(f)

    _compute_offsets(roots)
    return roots


def _compute_offsets(nodes: List[Field], base_offset: int = 0) -> int:
    """Recursively compute byte offsets. REDEFINES fields share the offset
    of the field they redefine (same base_offset, do not advance cursor)."""
    offset = base_offset
    named_offsets = {}
    for node in nodes:
        if node.redefines:
            # REDEFINES reuses the offset of the redefined sibling
            node.offset = named_offsets.get(node.redefines, offset)
        else:
            node.offset = offset

        if node.children:
            child_end = _compute_offsets(node.children, node.offset)
            node.length = child_end - node.offset
        # else: leaf length already computed from PIC/usage

        occurs_factor = node.occurs_max if node.occurs_max else 1
        span = node.length * occurs_factor

        named_offsets[node.name] = node.offset
        if not node.redefines:
            offset = node.offset + span
    return offset


def flatten(nodes: List[Field]) -> List[Field]:
    """Return all leaf (elementary, non-group) fields in a flat list,
    depth-first, in physical order."""
    out = []
    for n in nodes:
        if n.children:
            out.extend(flatten(n.children))
        else:
            out.append(n)
    return out


def record_length(nodes: List[Field]) -> int:
    """Total physical record length in bytes (max offset of any non-redefining
    top-level field's end, i.e. the layout cursor after compute_offsets)."""
    end = 0
    for n in nodes:
        if n.redefines:
            continue
        occurs_factor = n.occurs_max if n.occurs_max else 1
        end = max(end, n.offset + n.length * occurs_factor)
    return end


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../copybooks/CVCUS01Y.cpy"
    with open(path) as fh:
        tree = parse_copybook(fh.read())
    for leaf in flatten(tree):
        print(f"{leaf.path():45s} off={leaf.offset:4d} len={leaf.length:4d} "
              f"usage={leaf.usage:8s} pic={leaf.pic} occurs={leaf.occurs_min}-{leaf.occurs_max} "
              f"redefines={leaf.redefines}")
    print(f"\nTotal record length: {record_length(tree)} bytes")
