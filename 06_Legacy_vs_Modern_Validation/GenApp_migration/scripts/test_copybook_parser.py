"""
test_copybook_parser.py
--------------------------
Unit tests for the COBOL copybook parser. Pure logic, no database
required - run these on their own for fast feedback while editing
copybook_parser.py:

    cd scripts
    pytest test_copybook_parser.py -v
"""
from copybook_parser import parse_copybook, flatten, record_length


def test_pic_x_length_and_offset():
    cpy = """
       01  REC.
           05  FIELD-A                PIC X(10).
           05  FIELD-B                PIC X(05).
    """
    roots = parse_copybook(cpy)
    leaves = flatten(roots)
    assert [f.name for f in leaves] == ["FIELD-A", "FIELD-B"]
    assert leaves[0].offset == 0 and leaves[0].length == 10
    assert leaves[1].offset == 10 and leaves[1].length == 5
    assert record_length(roots) == 15


def test_pic_9_zoned_decimal_length():
    cpy = """
       01  REC.
           05  CUST-NUM               PIC 9(10).
    """
    roots = parse_copybook(cpy)
    leaf = flatten(roots)[0]
    assert leaf.usage == "DISPLAY"
    assert leaf.length == 10  # one byte per digit, zoned decimal
    assert leaf.digits == 10
    assert leaf.decimals == 0


def test_comp3_packed_decimal_length_formula():
    # bytes = floor((digits+decimals)/2) + 1
    cases = [
        ("PIC S9(03) COMP-3", 2),     # 3 digits -> floor(3/2)+1 = 2 bytes
        ("PIC S9(09)V99 COMP-3", 6),  # 9+2=11 digits -> floor(11/2)+1 = 6 bytes
        ("PIC S9(01) COMP-3", 1),      # 1 digit -> floor(1/2)+1 = 1 byte
    ]
    for pic_clause, expected_bytes in cases:
        cpy = f"       01  REC.\n           05  AMT {pic_clause}.\n"
        roots = parse_copybook(cpy)
        leaf = flatten(roots)[0]
        assert leaf.usage == "COMP-3"
        assert leaf.length == expected_bytes, f"{pic_clause}: expected {expected_bytes}, got {leaf.length}"


def test_comp_binary_length_bands():
    # IBM Enterprise COBOL: 1-4 digits->2 bytes, 5-9->4 bytes, 10-18->8 bytes
    cases = [
        ("PIC 9(04) COMP", 2),
        ("PIC 9(09) COMP", 4),
        ("PIC 9(18) COMP", 8),
        ("PIC S9(04) COMP", 2),
    ]
    for pic_clause, expected_bytes in cases:
        cpy = f"       01  REC.\n           05  CNT {pic_clause}.\n"
        roots = parse_copybook(cpy)
        leaf = flatten(roots)[0]
        assert leaf.usage == "COMP"
        assert leaf.length == expected_bytes, f"{pic_clause}: expected {expected_bytes}, got {leaf.length}"


def test_occurs_fixed_advances_offset_by_full_span():
    cpy = """
       01  REC.
           05  KEY-FIELD               PIC X(05).
           05  ITEM OCCURS 3 TIMES.
               10  ITEM-CODE            PIC X(04).
           05  TRAILER                 PIC X(02).
    """
    roots = parse_copybook(cpy)
    root = roots[0]
    occurs_field = next(f for f in root.children if f.name == "ITEM")
    trailer = next(f for f in root.children if f.name == "TRAILER")
    assert occurs_field.occurs_max == 3
    assert occurs_field.length == 4  # one occurrence's length
    # trailer must start after key(5) + 3*item(4) = 5 + 12 = 17
    assert trailer.offset == 17
    assert record_length(roots) == 19


def test_occurs_depending_on_parses_driver_field():
    cpy = """
       01  REC.
           05  RETRY-COUNT              PIC 9(01).
           05  RETRY-DETAIL OCCURS 5 TIMES
                                DEPENDING ON RETRY-COUNT.
               10  RETRY-CODE            PIC X(02).
    """
    roots = parse_copybook(cpy)
    root = roots[0]
    occurs_field = next(f for f in root.children if f.name == "RETRY-DETAIL")
    assert occurs_field.occurs_max == 5
    assert occurs_field.occurs_depending_on == "RETRY-COUNT"


def test_redefines_shares_offset_with_target():
    cpy = """
       01  REC.
           05  DISCRIMINATOR            PIC X(01).
           05  RAW-DATA                 PIC X(10).
           05  VARIANT-A REDEFINES RAW-DATA.
               10  FIELD-A1              PIC X(05).
               10  FIELD-A2              PIC X(05).
           05  VARIANT-B REDEFINES RAW-DATA.
               10  FIELD-B1              PIC X(10).
           05  TRAILER                  PIC X(03).
    """
    roots = parse_copybook(cpy)
    root = roots[0]
    raw_data = next(f for f in root.children if f.name == "RAW-DATA")
    variant_a = next(f for f in root.children if f.name == "VARIANT-A")
    variant_b = next(f for f in root.children if f.name == "VARIANT-B")
    trailer = next(f for f in root.children if f.name == "TRAILER")

    # all three interpretations of the same bytes start at the same offset
    assert raw_data.offset == variant_a.offset == variant_b.offset == 1

    # a REDEFINES group does NOT advance the record's byte cursor -
    # trailer must start right after RAW-DATA's 10 bytes, not after
    # RAW-DATA + VARIANT-A + VARIANT-B stacked sequentially
    assert trailer.offset == 11
    assert record_length(roots) == 14


def test_real_customer_copybook_matches_known_record_length():
    """Regression guard: this copybook was reverse-engineered from the
    real lgacvs01.cbl WRITE FILE(KSDSCUST) LENGTH(225) call and verified
    against reference/data/ksdscust.txt (225 chars/line). If this ever
    breaks, either the copybook was edited incorrectly or the parser
    regressed."""
    with open("../copybooks/derived_vsam_customer.cpy") as fh:
        roots = parse_copybook(fh.read())
    assert record_length(roots) == 225


def test_real_policy_copybook_matches_known_record_length_and_redefines():
    """Same regression guard for the policy copybook (64 bytes, verified
    against reference/data/ksdspoly.txt), including that all four
    REDEFINES variants (C/E/H/M) share the same starting offset."""
    with open("../copybooks/derived_vsam_policy.cpy") as fh:
        roots = parse_copybook(fh.read())
    assert record_length(roots) == 64

    root = roots[0]
    variants = [f for f in root.children if f.redefines == "POLICY-DATA"]
    assert len(variants) == 4
    offsets = {v.offset for v in variants}
    assert len(offsets) == 1, f"all REDEFINES variants should share one offset, got {offsets}"


def test_flatten_skips_group_items_returns_only_leaves():
    cpy = """
       01  REC.
           05  GROUP-FIELD.
               10  SUB-A                PIC X(02).
               10  SUB-B                PIC X(03).
           05  SIMPLE-FIELD             PIC 9(04).
    """
    roots = parse_copybook(cpy)
    leaves = flatten(roots)
    names = [f.name for f in leaves]
    assert "GROUP-FIELD" not in names  # groups themselves aren't leaves
    assert names == ["SUB-A", "SUB-B", "SIMPLE-FIELD"]


def test_88_level_condition_names_are_ignored():
    """88-level VALUE clauses carry no physical storage and must not
    appear as fields or affect offsets."""
    cpy = """
       01  REC.
           05  STATUS-CODE              PIC X(01).
               88  STATUS-ACTIVE         VALUE 'A'.
               88  STATUS-INACTIVE       VALUE 'I'.
           05  TRAILER                  PIC X(05).
    """
    roots = parse_copybook(cpy)
    leaves = flatten(roots)
    names = [f.name for f in leaves]
    assert "STATUS-ACTIVE" not in names
    assert "STATUS-INACTIVE" not in names
    trailer = next(f for f in leaves if f.name == "TRAILER")
    assert trailer.offset == 1  # right after the 1-byte STATUS-CODE
