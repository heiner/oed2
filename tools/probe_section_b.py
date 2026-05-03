#!/usr/bin/env python3
"""Quick structural probe of Section B (0x243b100..0xa08c000)."""
import argparse
import re
import struct
from collections import Counter
from pathlib import Path

DAT = Path("/Volumes/OED2/OED2.DAT")
SEC_B = 0x0243b100
SEC_B_END = 0x0a08c000


def hexdump(data, width=16, base=0):
    out = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{base + i:08x}  {hexs:<{width*3-1}}  {ascii}")
    return "\n".join(out)


def block_signature_scan(fh, start, end, step=0x8000):
    """Look for repeating headers at fixed strides."""
    seen = Counter()
    fh.seek(start)
    pos = start
    while pos + 16 < end:
        fh.seek(pos)
        first16 = fh.read(16)
        # First 4 bytes as a "signature" — most-frequent prefix tells us framing.
        seen[first16[:4]] += 1
        pos += step
    return seen


def entropy_window(data):
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    total = len(data) or 1
    import math
    h = 0.0
    for c in counts:
        if c:
            p = c / total
            h -= p * math.log2(p)
    return h


def find_tag_offsets(fh, start, end, tag, limit=20):
    fh.seek(start)
    chunk_size = 1 << 22  # 4 MB chunks
    offsets = []
    pos = start
    pat = re.compile(re.escape(tag.encode()))
    leftover = b""
    while pos < end and len(offsets) < limit:
        fh.seek(pos)
        chunk = fh.read(min(chunk_size, end - pos))
        for m in pat.finditer(leftover + chunk):
            real = pos - len(leftover) + m.start()
            offsets.append(real)
            if len(offsets) >= limit:
                break
        leftover = chunk[-len(tag) :]
        pos += chunk_size
    return offsets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="overview")
    ap.add_argument("--at", type=lambda s: int(s, 0), default=SEC_B)
    ap.add_argument("--len", type=lambda s: int(s, 0), default=256)
    ap.add_argument("--tag", default="<qd")
    args = ap.parse_args()

    with open(DAT, "rb") as fh:
        if args.mode == "overview":
            # Sample headers at three points: start, +1MB, +10MB, +50MB, +100MB
            for off in [SEC_B, SEC_B + 0x100000, SEC_B + 0xa00000, SEC_B + 0x3200000, SEC_B + 0x6400000]:
                fh.seek(off)
                buf = fh.read(64)
                print(f"--- {off:#x} (Section B + {off - SEC_B:#x}) ---")
                print(hexdump(buf, 16, off))
                print(f"entropy of first 64KB: {entropy_window(fh.read(0x10000)):.3f}")
                print()
            print("--- block-prefix histogram at stride 0x800 (first 1024 strides from start) ---")
            sigs = block_signature_scan(fh, SEC_B, SEC_B + 1024 * 0x800, step=0x800)
            for sig, count in sigs.most_common(8):
                print(f"  {sig.hex()}  x {count}")
            print("--- block-prefix histogram at stride 0x8000 (first 1024 strides) ---")
            sigs = block_signature_scan(fh, SEC_B, SEC_B + 1024 * 0x8000, step=0x8000)
            for sig, count in sigs.most_common(8):
                print(f"  {sig.hex()}  x {count}")
        elif args.mode == "dump":
            fh.seek(args.at)
            buf = fh.read(args.len)
            print(hexdump(buf, 16, args.at))
        elif args.mode == "find":
            offs = find_tag_offsets(fh, SEC_B, SEC_B_END, args.tag, limit=8)
            print(f"first 8 occurrences of {args.tag!r} in Section B:")
            for off in offs:
                fh.seek(max(SEC_B, off - 32))
                ctx = fh.read(96)
                print(f"--- {off:#x} (Section B + {off - SEC_B:#x}) ---")
                print(hexdump(ctx, 16, max(SEC_B, off - 32)))
                print()


if __name__ == "__main__":
    main()
