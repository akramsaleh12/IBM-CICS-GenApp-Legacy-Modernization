"""
ebcdic_utils.py
----------------
Low-level byte-decoding routines for mainframe VSAM extracts:
  - EBCDIC (cp037 / cp500) -> UTF-8 text decoding for PIC X fields
  - COMP-3 packed-decimal unpacking for PIC S9(n)V9(m) COMP-3 fields
  - COMP / COMP-4 big-endian binary integer unpacking
  - Zoned-decimal (DISPLAY numeric, PIC 9(n)) unpacking, including the
    EBCDIC sign-overpunch convention for signed DISPLAY fields

Python's built-in 'cp037' codec (US/Canada EBCDIC) covers the character
set used by most US mainframe shops. For other regions, swap EBCDIC_CODEC
below (e.g. 'cp500' for International EBCDIC, 'cp1140' for Euro-enabled).
"""
from decimal import Decimal
import struct

EBCDIC_CODEC = "cp037"

# EBCDIC zoned-decimal sign overpunch map: the zone nibble of the LAST byte
# of a DISPLAY signed numeric field encodes the sign digit + sign.
# Positive: {, A-I map to 0-9 ; Negative: } J-R map to 0-9
ZONED_SIGN_POSITIVE = {"{": 0, "A": 1, "B": 2, "C": 3, "D": 4,
                        "E": 5, "F": 6, "G": 7, "H": 8, "I": 9}
ZONED_SIGN_NEGATIVE = {"}": 0, "J": 1, "K": 2, "L": 3, "M": 4,
                        "N": 5, "O": 6, "P": 7, "Q": 8, "R": 9}


def decode_ebcdic_text(raw: bytes, codec: str = EBCDIC_CODEC) -> str:
    """Decode raw text bytes (PIC X field) to a UTF-8 Python str,
    right-trimmed of trailing spaces (COBOL space-pads alphanumerics).
    codec defaults to EBCDIC (cp037) for genuine mainframe binary
    extracts, but accepts 'ascii'/'utf-8'/'latin-1' etc. for shops that
    hand off already-transcoded flat files (common when the extract
    passed through FTP in text mode, or was produced by a workbench
    tool rather than IDCAMS REPRO)."""
    return raw.decode(codec, errors="replace").rstrip()


def unpack_comp3(raw: bytes, decimals: int) -> Decimal:
    """Unpack IBM packed-decimal (COMP-3) bytes into a Decimal.
    Each byte holds two BCD digits except the last, whose low nibble is
    the sign (C/F = positive, D = negative, B = unsigned positive)."""
    digits = []
    for b in raw[:-1]:
        digits.append((b >> 4) & 0x0F)
        digits.append(b & 0x0F)
    last = raw[-1]
    digits.append((last >> 4) & 0x0F)
    sign_nibble = last & 0x0F

    for d in digits:
        if d > 9:
            raise ValueError(f"Invalid packed-decimal digit nibble: {d:#x}")

    value_str = "".join(str(d) for d in digits) or "0"
    value = Decimal(value_str)
    if decimals:
        value = value / (Decimal(10) ** decimals)
    if sign_nibble in (0x0D, 0x0B):  # D = negative, B = unsigned-negative (rare)
        value = -value
    return value


def unpack_comp(raw: bytes, decimals: int = 0, signed: bool = True) -> Decimal:
    """Unpack IBM COMP / COMP-4 (big-endian binary) integer bytes into a
    Decimal, applying the implied decimal scale (PIC 9(n)V9(m))."""
    length = len(raw)
    fmt_map_signed = {2: ">h", 4: ">i", 8: ">q"}
    fmt_map_unsigned = {2: ">H", 4: ">I", 8: ">Q"}
    fmt = (fmt_map_signed if signed else fmt_map_unsigned).get(length)
    if not fmt:
        raise ValueError(f"Unsupported COMP length: {length} bytes")
    (int_value,) = struct.unpack(fmt, raw)
    value = Decimal(int_value)
    if decimals:
        value = value / (Decimal(10) ** decimals)
    return value


def unpack_zoned_display(raw: bytes, decimals: int, signed: bool, codec: str = EBCDIC_CODEC) -> Decimal:
    """Unpack a DISPLAY-usage numeric field (PIC 9(n) or PIC S9(n)) stored
    as zoned decimal, honoring sign-overpunch on the final byte when the
    field is signed and codec is an EBCDIC codepage. For unsigned fields
    on a plain-text (ASCII/UTF-8) extract, this is just "parse the digits"."""
    text = raw.decode(codec, errors="replace")
    if not signed:
        digits = "".join(ch for ch in text if ch.isdigit()) or "0"
        value = Decimal(digits)
    else:
        body, last_char = text[:-1], text[-1]
        digits_body = "".join(ch for ch in body if ch.isdigit())
        if last_char in ZONED_SIGN_POSITIVE:
            last_digit = ZONED_SIGN_POSITIVE[last_char]
            sign = 1
        elif last_char in ZONED_SIGN_NEGATIVE:
            last_digit = ZONED_SIGN_NEGATIVE[last_char]
            sign = -1
        elif last_char.isdigit():
            last_digit = int(last_char)
            sign = 1
        else:
            last_digit = 0
            sign = 1
        digits = (digits_body + str(last_digit)) or "0"
        value = Decimal(digits) * sign
    if decimals:
        value = value / (Decimal(10) ** decimals)
    return value


def decode_field(raw: bytes, field, codec: str = EBCDIC_CODEC) -> object:
    """Dispatch decoding based on a copybook_parser.Field's usage/PIC.
    Returns a str for alphanumeric fields, Decimal for numeric fields.
    codec applies only to DISPLAY-usage text/zoned-decimal fields -
    COMP-3 and COMP are pure binary and have no text encoding."""
    pic = (field.pic or "").upper()
    if field.usage == "COMP-3":
        return unpack_comp3(raw, field.decimals)
    if field.usage == "COMP":
        return unpack_comp(raw, field.decimals, signed=field.signed)
    if "X" in pic:
        return decode_ebcdic_text(raw, codec)
    if "9" in pic:
        return unpack_zoned_display(raw, field.decimals, field.signed, codec)
    # Fallback: treat as text
    return decode_ebcdic_text(raw, codec)
