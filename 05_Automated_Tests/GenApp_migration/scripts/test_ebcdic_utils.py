"""
test_ebcdic_utils.py
-----------------------
Unit tests for EBCDIC text decoding, COMP-3 packed-decimal unpacking,
COMP binary unpacking, and zoned-decimal (DISPLAY numeric) unpacking.
Pure logic, no database required:

    cd scripts
    pytest test_ebcdic_utils.py -v
"""
from decimal import Decimal

import pytest

from ebcdic_utils import (
    decode_ebcdic_text, unpack_comp3, unpack_comp, unpack_zoned_display, decode_field,
)


# ---------------------------------------------------------------------------
# EBCDIC text
# ---------------------------------------------------------------------------
def test_decode_ebcdic_text_roundtrip_cp037():
    raw = "HELLO".encode("cp037")
    assert decode_ebcdic_text(raw) == "HELLO"


def test_decode_ebcdic_text_trims_trailing_spaces_only():
    raw = "  HELLO   ".encode("cp037")
    # COBOL space-pads on the right; leading spaces are meaningful data
    # and must NOT be stripped, only trailing.
    assert decode_ebcdic_text(raw) == "  HELLO"


def test_decode_ebcdic_text_accepts_ascii_codec_for_pretranscoded_files():
    raw = "PLAIN TEXT".encode("ascii")
    assert decode_ebcdic_text(raw, codec="ascii") == "PLAIN TEXT"


# ---------------------------------------------------------------------------
# COMP-3 packed decimal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value,decimals", [
    (Decimal("123"), 0),
    (Decimal("-123"), 0),
    (Decimal("0"), 0),
    (Decimal("1234.56"), 2),
    (Decimal("-1234.56"), 2),
])
def test_unpack_comp3_roundtrip(value, decimals):
    """Pack a value by hand (matching IBM's packed-decimal byte layout:
    2 BCD digits/byte, sign nibble C=+/D=- in the last nibble) and
    confirm unpack_comp3 recovers exactly the original value."""
    scaled = int(abs(value) * (10 ** decimals))
    digits = str(scaled)
    if len(digits) % 2 == 0:
        digits = "0" + digits
    sign_nibble = 0xD if value < 0 else 0xC
    nibbles = [int(d) for d in digits] + [sign_nibble]
    raw = bytearray()
    for i in range(0, len(nibbles) - 1, 2):
        raw.append((nibbles[i] << 4) | nibbles[i + 1])
    assert unpack_comp3(bytes(raw), decimals) == value


def test_unpack_comp3_rejects_invalid_bcd_nibble():
    # 0xFA has a high nibble of 0xF, which is not a valid BCD digit (0-9)
    with pytest.raises(ValueError):
        unpack_comp3(b"\xfa\x1c", 0)


# ---------------------------------------------------------------------------
# COMP binary
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("length,signed,py_value", [
    (2, True, -100),
    (2, False, 100),
    (4, True, -100000),
    (4, False, 100000),
    (8, True, -5_000_000_000),
])
def test_unpack_comp_roundtrip(length, signed, py_value):
    import struct
    fmt_map = {(2, True): ">h", (2, False): ">H", (4, True): ">i",
               (4, False): ">I", (8, True): ">q", (8, False): ">Q"}
    raw = struct.pack(fmt_map[(length, signed)], py_value)
    assert unpack_comp(raw, decimals=0, signed=signed) == Decimal(py_value)


def test_unpack_comp_applies_implied_decimal_scale():
    import struct
    raw = struct.pack(">h", 12345)
    assert unpack_comp(raw, decimals=2, signed=True) == Decimal("123.45")


# ---------------------------------------------------------------------------
# Zoned decimal (DISPLAY numeric)
# ---------------------------------------------------------------------------
def test_unpack_zoned_display_unsigned_ascii():
    raw = "0000000123".encode("ascii")
    assert unpack_zoned_display(raw, decimals=0, signed=False, codec="ascii") == Decimal("123")


def test_unpack_zoned_display_signed_positive_overpunch_cp037():
    # EBCDIC sign-overpunch: last byte's zone nibble encodes sign+digit.
    # 'C' in the ZONED_SIGN_POSITIVE map represents digit 3, positive.
    raw = "12".encode("cp037") + "C".encode("cp037")
    value = unpack_zoned_display(raw, decimals=0, signed=True, codec="cp037")
    assert value == Decimal("123")  # positive


def test_unpack_zoned_display_signed_negative_overpunch_cp037():
    # 'L' = negative overpunch for digit 3 (ZONED_SIGN_NEGATIVE)
    raw = "12".encode("cp037") + "L".encode("cp037")
    value = unpack_zoned_display(raw, decimals=0, signed=True, codec="cp037")
    assert value == Decimal("-123")


# ---------------------------------------------------------------------------
# decode_field dispatch
# ---------------------------------------------------------------------------
class _FakeField:
    """Minimal stand-in for copybook_parser.Field, just the attributes
    decode_field actually reads."""
    def __init__(self, pic, usage="DISPLAY", decimals=0, signed=False):
        self.pic = pic
        self.usage = usage
        self.decimals = decimals
        self.signed = signed


def test_decode_field_dispatches_text_for_pic_x():
    f = _FakeField("X(05)")
    assert decode_field("HELLO".encode("ascii"), f, codec="ascii") == "HELLO"


def test_decode_field_dispatches_zoned_for_pic_9_display():
    f = _FakeField("9(03)")
    assert decode_field("042".encode("ascii"), f, codec="ascii") == Decimal("42")


def test_decode_field_dispatches_comp3_regardless_of_codec():
    # COMP-3 is pure binary - codec must be irrelevant to the result
    f = _FakeField("S9(03)", usage="COMP-3", decimals=0)
    raw = bytes([0x12, 0x3C])  # packed "123", positive
    assert decode_field(raw, f, codec="ascii") == Decimal("123")
    assert decode_field(raw, f, codec="cp037") == Decimal("123")
