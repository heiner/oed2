#!/usr/bin/env python3
"""Find pointers into Section B (0x243b100..0xa08c000) from anywhere earlier.

We scan the first 16 MB byte-by-byte and look at every 4-byte window
interpreted as both LE and BE, counting how many fall into Section B's
byte range. We also bin by 0x100000 (1 MB) so we can find clusters.
"""
import struct
from collections import Counter
from pathlib import Path

DAT = Path("/Volumes/OED2/OED2.DAT")
SEC_B = 0x0243b100
SEC_B_END = 0x0a08c000


def main():
    # Read the first 16 MB into memory.
    with open(DAT, "rb") as fh:
        buf = fh.read(16 * 1024 * 1024)

    print(f"scanning {len(buf):,} bytes for u32 values in [{SEC_B:#x}, {SEC_B_END:#x})")

    le_hits = []
    be_hits = []
    for i in range(0, len(buf) - 4, 1):
        v_le = struct.unpack_from("<I", buf, i)[0]
        v_be = struct.unpack_from(">I", buf, i)[0]
        if SEC_B <= v_le < SEC_B_END:
            le_hits.append((i, v_le))
        if SEC_B <= v_be < SEC_B_END:
            be_hits.append((i, v_be))

    print(f"LE u32 hits: {len(le_hits)}")
    print(f"BE u32 hits: {len(be_hits)}")

    # Bin by 1MB-of-source location.
    print("\n--- LE clusters by 256 KB ---")
    bins = Counter()
    for src, _ in le_hits:
        bins[src // 0x40000] += 1
    for b, c in sorted(bins.items()):
        if c >= 4:
            print(f"  source {b * 0x40000:#08x}..{(b+1)*0x40000:#08x}  hits={c}")

    print("\n--- BE clusters by 256 KB ---")
    bins = Counter()
    for src, _ in be_hits:
        bins[src // 0x40000] += 1
    for b, c in sorted(bins.items()):
        if c >= 4:
            print(f"  source {b * 0x40000:#08x}..{(b+1)*0x40000:#08x}  hits={c}")

    # The strongest clusters: look at densest source bin and dump its hits.
    if be_hits:
        be_bin = Counter(src // 0x40000 for src, _ in be_hits).most_common(1)[0][0]
        print(f"\n--- densest BE bin source [{be_bin*0x40000:#x}..{(be_bin+1)*0x40000:#x}] ---")
        bin_hits = [(s, v) for s, v in be_hits if s // 0x40000 == be_bin]
        # Look for stride pattern within the bin
        stride_counter = Counter()
        for i in range(1, min(64, len(bin_hits))):
            stride = bin_hits[i][0] - bin_hits[i-1][0]
            stride_counter[stride] += 1
        print(f"  hit count: {len(bin_hits)}")
        print(f"  most common BE-hit strides in this bin: {stride_counter.most_common(5)}")
        # Sample first 10 hits
        for s, v in bin_hits[:10]:
            print(f"  src={s:#08x} -> dst={v:#08x} (B+{v - SEC_B:#x})")

    if le_hits:
        le_bin = Counter(src // 0x40000 for src, _ in le_hits).most_common(1)[0][0]
        print(f"\n--- densest LE bin source [{le_bin*0x40000:#x}..{(le_bin+1)*0x40000:#x}] ---")
        bin_hits = [(s, v) for s, v in le_hits if s // 0x40000 == le_bin]
        stride_counter = Counter()
        for i in range(1, min(64, len(bin_hits))):
            stride = bin_hits[i][0] - bin_hits[i-1][0]
            stride_counter[stride] += 1
        print(f"  hit count: {len(bin_hits)}")
        print(f"  most common LE-hit strides in this bin: {stride_counter.most_common(5)}")
        for s, v in bin_hits[:10]:
            print(f"  src={s:#08x} -> dst={v:#08x} (B+{v - SEC_B:#x})")


if __name__ == "__main__":
    main()
