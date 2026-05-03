#!/usr/bin/env python3
"""Deeper structural probe: find framing/headers within Section B."""
import math
import struct
from pathlib import Path

DAT = Path("/Volumes/OED2/OED2.DAT")
SEC_B = 0x0243b100
SEC_B_END = 0x0a08c000


def entropy(data):
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    total = len(data)
    h = 0.0
    for c in counts:
        if c:
            p = c / total
            h -= p * math.log2(p)
    return h


def hexdump(data, base=0, width=16):
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + i:08x}  {hexs:<{width*3-1}}  {ascii}")
    return "\n".join(lines)


def main():
    with open(DAT, "rb") as fh:
        # 1. Look at the boundary regions just before and after Section B.
        print("=" * 60)
        print("BOUNDARY: bytes leading into Section B (0x243b100)")
        print("=" * 60)
        fh.seek(SEC_B - 0x80)
        print(hexdump(fh.read(0x100), SEC_B - 0x80))
        print()

        print("=" * 60)
        print("BOUNDARY: bytes leaving Section B (0xa08c000)")
        print("=" * 60)
        fh.seek(SEC_B_END - 0x80)
        print(hexdump(fh.read(0x100), SEC_B_END - 0x80))
        print()

        # 2. Find lowest-entropy 256-byte windows in the first 16 MB of Section B.
        print("=" * 60)
        print("Lowest-entropy 256-byte windows in first 16 MB of Section B")
        print("=" * 60)
        fh.seek(SEC_B)
        chunk = fh.read(16 * 1024 * 1024)
        window = 256
        scores = []
        for i in range(0, len(chunk) - window, window):
            h = entropy(chunk[i : i + window])
            scores.append((h, SEC_B + i))
        scores.sort()
        for h, off in scores[:10]:
            print(f"  off={off:#x} (B+{off-SEC_B:#x}) entropy={h:.3f}")
            fh.seek(off)
            print(hexdump(fh.read(64), off))
            print()

        # 3. Sliding-stride histograms — look for headers at strides 0x100, 0x200, 0x400.
        print("=" * 60)
        print("Strided 4-byte prefix collisions (check for repeating headers)")
        print("=" * 60)
        for stride in (0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x10000):
            fh.seek(SEC_B)
            count = min(2000, (SEC_B_END - SEC_B) // stride)
            sigs = {}
            for i in range(count):
                fh.seek(SEC_B + i * stride)
                p = fh.read(4)
                sigs[p] = sigs.get(p, 0) + 1
            top = max(sigs.values())
            unique = len(sigs)
            print(f"  stride={stride:#x}: {count} samples, {unique} unique 4-byte prefixes, top freq={top}")

        # 4. Byte-frequency over entire Section B - is it uniform or biased?
        print()
        print("=" * 60)
        print("Byte-frequency profile over first 64 MB of Section B")
        print("=" * 60)
        fh.seek(SEC_B)
        counts = [0] * 256
        total = 0
        for _ in range(0x4000):  # 0x4000 * 0x1000 = 64 MB
            buf = fh.read(0x1000)
            if not buf:
                break
            for b in buf:
                counts[b] += 1
            total += len(buf)
        # Show top 10 and bottom 10 byte values
        ranked = sorted(enumerate(counts), key=lambda x: x[1])
        print(f"  total bytes: {total:,}; expected uniform ~{total/256:.0f}")
        print("  least common byte values:")
        for b, c in ranked[:8]:
            print(f"    0x{b:02x}: {c:,}")
        print("  most common byte values:")
        for b, c in ranked[-8:]:
            print(f"    0x{b:02x}: {c:,}")


if __name__ == "__main__":
    main()
