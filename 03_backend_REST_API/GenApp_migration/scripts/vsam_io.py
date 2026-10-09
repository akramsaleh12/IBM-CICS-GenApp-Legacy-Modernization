"""
vsam_io.py
-----------
Shared record-reading logic for the VSAM loaders.

Real mainframe VSAM extracts (IDCAMS REPRO to a sequential dataset,
FTP'd BINARY) are TRUE fixed-width: record N+1 starts immediately at
byte (N+1)*record_length, with no delimiter at all - RECFM=FB has no
concept of a newline. Reading such a file in fixed-size chunks is
correct and required.

Convenience sample/test files (like reference/data/ksdscust.txt) are
often prepared as ordinary newline-delimited text instead, because
that is what text editors, git, and `head`/`wc` can work with. This
reader auto-detects which shape the input file has and reads
accordingly, so the same loader script works against a real binary
mainframe extract AND a human-readable sample fixture.
"""
import sys


def read_records(data_path: str, rec_len: int):
    with open(data_path, "rb") as fh:
        data = fh.read()

    if b"\n" in data[: rec_len * 2 + 2]:
        # Newline-delimited text mode: one record per line
        lines = data.split(b"\n")
        for i, line in enumerate(lines):
            line = line.rstrip(b"\r")
            if not line:
                continue
            if len(line) != rec_len:
                print(f"WARNING: line {i + 1} is {len(line)} bytes, expected {rec_len} - "
                      f"{'padding' if len(line) < rec_len else 'truncating'}", file=sys.stderr)
                line = line.ljust(rec_len)[:rec_len]
            yield line
        return

    # True fixed-width binary mode: no delimiters, read in rec_len chunks
    pos = 0
    total = len(data)
    while pos < total:
        chunk = data[pos: pos + rec_len]
        if len(chunk) < rec_len:
            print(f"WARNING: truncated final record ({len(chunk)} of {rec_len} bytes) - skipped",
                  file=sys.stderr)
            return
        yield chunk
        pos += rec_len
