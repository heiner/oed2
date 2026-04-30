#!/usr/bin/env python3
"""
OED2.DAT static inspector — Milestone 1 of the reverse-engineering effort.

The OED2 CD-ROM (1992, Oxford University Press, OED2.DAT inside the
ISO) ships ~606 MB of opaque binary. This script does read-only
analysis to identify the file's section boundaries and produces a
JSON map of what's where.

Usage:
    python3 tools/oed2_inspect.py /path/to/OED2.DAT [--out report.json]

Findings as of first run (2026-04, see plan file):

  * 264-byte header at file start: 66 LE LONGs, all values fit in
    24 bits (max 0xfff8 8415). Likely a directory of pointers into
    the term-index region; precise interpretation TBD.
  * Padding to 0x800.
  * 0x0800..~0x0980  diacritic side-table: (decorated, base) byte
    pairs covering the CP437 high half.
  * Section A:  0..0x243b100 (~38 MB)        low-entropy term index
  * Section B:  0x243b100..~0xa08a7c0 (~168 MB)  HIGH-entropy bodies
  * Section C:  ~168 MB..~185 MB             fragmented per-block
                                             control structures
  * Section D:  ~185 MB..end                 high-entropy bodies
                                             (likely citations or
                                             full-text inverted
                                             index)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple


HEADER_LONGS = 66
HEADER_BYTES = HEADER_LONGS * 4   # 0x108


# ---------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------
@dataclass
class HeaderEntry:
    index: int
    raw: int            # 32-bit LE LONG
    offset: int         # interpreted as a file byte offset
    page: int           # offset // 0x10000 (64 KB pages)
    page_offset: int    # offset % 0x10000


def parse_header(blob: bytes) -> List[HeaderEntry]:
    if len(blob) < HEADER_BYTES:
        raise ValueError('header too short')
    out = []
    for i in range(HEADER_LONGS):
        v = struct.unpack_from('<I', blob, i * 4)[0]
        out.append(HeaderEntry(
            index=i, raw=v,
            offset=v,
            page=v >> 16,
            page_offset=v & 0xffff,
        ))
    return out


# ---------------------------------------------------------------------
# Diacritic side-table at 0x800
# ---------------------------------------------------------------------
def extract_diacritic_table(blob: bytes, start: int = 0x800,
                             max_pairs: int = 200) -> List[Tuple[int, int]]:
    """Read repeating (decorated, base) byte pairs.

    The table runs until a region of trailing zeros / sentinel.
    Returns pairs where decorated > 0x7f (CP437 high half) and base
    is printable ASCII (0x20-0x7e) or a recognised plaintext form.
    """
    pairs: List[Tuple[int, int]] = []
    p = start
    while p + 1 < len(blob) and len(pairs) < max_pairs:
        a, b = blob[p], blob[p + 1]
        if a == 0 and b == 0:
            break
        pairs.append((a, b))
        p += 2
    return pairs


# ---------------------------------------------------------------------
# Entropy profiling
# ---------------------------------------------------------------------
def entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    c = Counter(buf)
    n = len(buf)
    return -sum((v / n) * math.log2(v / n) for v in c.values() if v)


def entropy_profile(path: str, win: int = 65536, stride: Optional[int] = None
                    ) -> List[Tuple[int, float]]:
    """Sliding-window entropy across the file. Returns (offset, ent)."""
    if stride is None:
        stride = win
    size = os.path.getsize(path)
    out: List[Tuple[int, float]] = []
    with open(path, 'rb') as f:
        for off in range(0, size, stride):
            f.seek(off)
            buf = f.read(min(win, size - off))
            out.append((off, entropy(buf)))
    return out


# ---------------------------------------------------------------------
# Section discovery
# ---------------------------------------------------------------------
@dataclass
class Section:
    start: int
    end: int
    kind: str             # 'index', 'compressed', 'mixed', 'tail'
    mean_entropy: float
    note: str = ''

    @property
    def length(self) -> int:
        return self.end - self.start


def find_sections(profile: List[Tuple[int, float]],
                  size: int) -> List[Section]:
    """Cluster consecutive bins by entropy band into sections."""
    sections: List[Section] = []
    if not profile:
        return sections

    def band(e: float) -> str:
        if e < 5.0:
            return 'index'
        if e < 7.5:
            return 'mixed'
        return 'compressed'

    cur_band = band(profile[0][1])
    cur_start = profile[0][0]
    cur_ents: List[float] = [profile[0][1]]

    for off, ent in profile[1:]:
        b = band(ent)
        if b != cur_band:
            mean = sum(cur_ents) / len(cur_ents)
            sections.append(Section(
                start=cur_start, end=off,
                kind=cur_band, mean_entropy=mean,
            ))
            cur_band = b
            cur_start = off
            cur_ents = []
        cur_ents.append(ent)

    mean = sum(cur_ents) / len(cur_ents) if cur_ents else 0.0
    sections.append(Section(
        start=cur_start, end=size,
        kind=cur_band, mean_entropy=mean,
    ))
    return sections


def merge_short(sections: List[Section], min_len: int = 1024 * 1024
                ) -> List[Section]:
    """Coalesce sub-MB sections into their neighbours.

    Avoids the false-fragmentation we see around 168-185 MB where
    per-block control headers create lots of tiny low-entropy windows.
    """
    if not sections:
        return sections
    merged = [sections[0]]
    for s in sections[1:]:
        if s.length < min_len:
            # absorb into previous, keep its kind but recompute mean
            prev = merged[-1]
            total_ents = (
                prev.mean_entropy * (prev.length / 1024)
                + s.mean_entropy * (s.length / 1024)
            )
            new_len = (prev.length + s.length) / 1024
            prev.end = s.end
            prev.mean_entropy = (total_ents / new_len) if new_len else 0
            prev.note = (prev.note + ' +absorb-frag').strip()
        else:
            merged.append(s)
    return merged


# ---------------------------------------------------------------------
# Top-level report builder
# ---------------------------------------------------------------------
def build_report(path: str, *, profile_window: int = 65536) -> dict:
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        head = f.read(0x10000)

    header = parse_header(head[:HEADER_BYTES])
    diac = extract_diacritic_table(head, 0x800)

    profile = entropy_profile(path, win=profile_window, stride=profile_window)
    sections = merge_short(find_sections(profile, size))

    return {
        'file': path,
        'file_size': size,
        'profile_window': profile_window,
        'header': {
            'long_count': HEADER_LONGS,
            'all_24bit': all(h.raw < 1 << 24 for h in header),
            'min_offset': min(h.offset for h in header),
            'max_offset': max(h.offset for h in header),
            'entries': [
                {'i': h.index, 'raw': h.raw, 'offset': h.offset,
                 'page': h.page, 'page_offset': h.page_offset}
                for h in header
            ],
        },
        'diacritic_table': {
            'start': 0x800,
            'pair_count': len(diac),
            'sample': [{'decorated': a, 'base': b,
                        'base_char': chr(b) if 0x20 <= b < 0x7f else None}
                       for a, b in diac[:20]],
        },
        'sections': [asdict(s) for s in sections],
        'section_count': len(sections),
    }


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path', help='Path to OED2.DAT')
    ap.add_argument('--out', help='JSON report output path '
                                  '(default: stdout)',
                    default=None)
    ap.add_argument('--window', type=int, default=65536,
                    help='Entropy window/stride in bytes (default 64 KB)')
    args = ap.parse_args(argv)

    if not os.path.exists(args.path):
        print(f'error: {args.path} does not exist', file=sys.stderr)
        return 1

    print(f'Analysing {args.path} ({os.path.getsize(args.path):,} bytes)…',
          file=sys.stderr)

    report = build_report(args.path, profile_window=args.window)

    print('\nSection map:', file=sys.stderr)
    print(f'{"start":>12}  {"end":>12}  {"length":>12}  {"kind":<11}  '
          f'mean ent', file=sys.stderr)
    for s in report['sections']:
        print(f'{s["start"]:>12,}  {s["end"]:>12,}  '
              f'{s["end"] - s["start"]:>12,}  {s["kind"]:<11}  '
              f'{s["mean_entropy"]:.2f}', file=sys.stderr)

    print(f'\nHeader: {HEADER_LONGS} LONGs, all 24-bit: '
          f'{report["header"]["all_24bit"]}, range '
          f'[{report["header"]["min_offset"]:,}, '
          f'{report["header"]["max_offset"]:,}]', file=sys.stderr)

    print(f'\nDiacritic table at 0x800: '
          f'{report["diacritic_table"]["pair_count"]} pairs.',
          file=sys.stderr)
    for p in report['diacritic_table']['sample'][:10]:
        bc = repr(p['base_char']) if p['base_char'] else f'0x{p["base"]:02x}'
        print(f'  0x{p["decorated"]:02x} -> {bc}', file=sys.stderr)

    out = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, 'w') as f:
            f.write(out)
        print(f'\nReport written to {args.out}', file=sys.stderr)
    else:
        print(out)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
