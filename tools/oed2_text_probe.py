#!/usr/bin/env python3
"""
Probe tagged-text islands inside OED2.DAT.

This is intentionally read-only.  The OED2 data is not a CompLex .AND
file, but late regions contain SGML-ish tags such as ``<hw>``, ``<x>``,
``<ps>``, and ``<qt>``.  Many printable bytes also appear with bit 7 set;
masking those bytes with 0x7f is a useful first-pass view because values
like 0xbe become ``>`` and 0xa0 becomes space.

Usage:
    python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --find abandon
    python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --offset 0x16721000
    python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --tags --start 0xb01ce00
    python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --tags
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from typing import Iterable


DEFAULT_CONTEXT = 512
TAG_RE = re.compile(rb'<[/A-Za-z][A-Za-z0-9/]*')


def parse_int(s: str) -> int:
    return int(s, 0)


def normalize_highbit(buf: bytes) -> str:
    """Return a lossy but readable view of OED2 tagged text.

    OED2 frequently stores ASCII-ish bytes with bit 7 set.  This function
    clears bit 7 for bytes >= 0x80 and keeps control bytes visible enough
    for terminal output.
    """
    out = bytearray()
    for b in buf:
        c = b & 0x7f if b >= 0x80 else b
        if c in (0x09, 0x0a, 0x0d) or 0x20 <= c < 0x7f:
            out.append(c)
        else:
            out.append(ord('.'))
    return out.decode('ascii', 'replace')


def hexdump(buf: bytes, start: int) -> str:
    lines = []
    for i in range(0, len(buf), 16):
        chunk = buf[i:i + 16]
        hx = ' '.join(f'{b:02x}' for b in chunk)
        hx = f'{hx:<47}'
        asc = ''.join(chr(b) if 0x20 <= b < 0x7f else '.' for b in chunk)
        lines.append(f'{start + i:08x}: {hx}  {asc}')
    return '\n'.join(lines)


def iter_hits(path: str, needle: bytes, start: int, end: int) -> Iterable[int]:
    chunk_size = 1024 * 1024
    overlap = max(len(needle) - 1, 0)
    with open(path, 'rb') as f:
        f.seek(start)
        base = start
        carry = b''
        while base < end:
            chunk = f.read(min(chunk_size, end - base))
            if not chunk:
                break
            data = carry + chunk
            search_to = len(data) - overlap
            pos = 0
            while True:
                hit = data.find(needle, pos, search_to)
                if hit < 0:
                    break
                yield base - len(carry) + hit
                pos = hit + 1
            carry = data[-overlap:] if overlap else b''
            base += len(chunk)


def dump_at(path: str, offset: int, context: int) -> None:
    size = os.path.getsize(path)
    start = max(0, offset - context)
    end = min(size, offset + context)
    with open(path, 'rb') as f:
        f.seek(start)
        buf = f.read(end - start)

    print(f'offset 0x{offset:x} ({offset:,}); showing 0x{start:x}..0x{end:x}')
    print('\nHex:')
    print(hexdump(buf, start))
    print('\nHigh-bit-normalized text:')
    print(normalize_highbit(buf))


def tag_summary(path: str, start: int, end: int) -> None:
    counts: Counter[bytes] = Counter()
    first: dict[bytes, int] = {}
    chunk_size = 1024 * 1024
    with open(path, 'rb') as f:
        f.seek(start)
        base = start
        carry = b''
        while base < end:
            chunk = f.read(min(chunk_size, end - base))
            if not chunk:
                break
            data = carry + chunk
            for m in TAG_RE.finditer(data):
                tag = m.group(0)
                off = base - len(carry) + m.start()
                counts[tag] += 1
                first.setdefault(tag, off)
            carry = data[-32:]
            base += len(chunk)

    for tag, count in counts.most_common(40):
        print(f'{tag.decode("ascii", "replace"):<12} {count:>8} '
              f'first=0x{first[tag]:x}')


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path')
    ap.add_argument('--find', help='ASCII byte string to locate')
    ap.add_argument('--offset', type=parse_int, help='offset to dump')
    ap.add_argument('--context', type=parse_int, default=DEFAULT_CONTEXT)
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--start', type=parse_int, default=0,
                    help='start offset for --find/--tags')
    ap.add_argument('--end', type=parse_int,
                    help='end offset for --find/--tags (default: EOF)')
    ap.add_argument('--tags', action='store_true',
                    help='summarize SGML-ish tag occurrences')
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print(f'error: {args.path} does not exist', file=sys.stderr)
        return 1

    size = os.path.getsize(args.path)
    end = args.end if args.end is not None else size
    if not 0 <= args.start <= end <= size:
        print('error: expected 0 <= --start <= --end <= file size',
              file=sys.stderr)
        return 1

    if args.tags:
        tag_summary(args.path, args.start, end)

    if args.find:
        needle = args.find.encode('ascii')
        for i, off in enumerate(iter_hits(args.path, needle,
                                          args.start, end)):
            if i >= args.limit:
                break
            print(f'{off}:0x{off:x}')

    if args.offset is not None:
        dump_at(args.path, args.offset, args.context)

    if not (args.tags or args.find or args.offset is not None):
        ap.error('choose --tags, --find, or --offset')

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
