#!/usr/bin/env python3
"""Inspect the 0xfb0f / sparse-index family and look for Section B refs."""
import struct
from pathlib import Path

DAT = Path("/Volumes/OED2/OED2.DAT")
SEC_B = 0x0243b100
SEC_B_END = 0x0a08c000

# From findings doc — sparse-index anchors with the 0xfb0f/0xffb signature.
ANCHORS = [
    0x15512800,
    0x155b2800,
    0x15713800,
    0x15776000,
    0x1584f800,
    0x15b83800,
    0x16079800,
]


def hexdump(data, base=0, width=16, lines=4):
    out = []
    for i in range(0, min(len(data), lines * width), width):
        chunk = data[i : i + width]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"{base + i:08x}  {hexs:<{width*3-1}}  {ascii}")
    return "\n".join(out)


def main():
    with open(DAT, "rb") as fh:
        for anchor in ANCHORS:
            print("=" * 60)
            print(f"anchor {anchor:#x}")
            print("=" * 60)
            fh.seek(anchor)
            head = fh.read(64)
            print(hexdump(head, anchor, lines=4))
            # Try header-as-u16-be: magic, ver, blocks, blocksize, ...
            magic, ver, blocks, blocksize = struct.unpack(">HHHH", head[:8])
            print(f"  u16be header: magic={magic:#06x} ver={ver} blocks={blocks} blocksize={blocksize:#x}")
            # u32 BE / LE pairs
            longs_be = struct.unpack(">8I", head[:32])
            longs_le = struct.unpack("<8I", head[:32])
            print(f"  u32 BE: {[hex(x) for x in longs_be]}")
            print(f"  u32 LE: {[hex(x) for x in longs_le]}")
            print()

    # For each anchor, scan its first MB for any u32 LE/BE landing in Section B.
    print("=" * 60)
    print("Looking for Section-B references inside each anchor's first 1 MB")
    print("=" * 60)
    for anchor in ANCHORS:
        with open(DAT, "rb") as fh:
            fh.seek(anchor)
            buf = fh.read(0x100000)
        b_hits_le = []
        b_hits_be = []
        for i in range(0, len(buf) - 4, 4):
            v_le = struct.unpack_from("<I", buf, i)[0]
            v_be = struct.unpack_from(">I", buf, i)[0]
            if SEC_B <= v_le < SEC_B_END:
                b_hits_le.append((i, v_le))
            if SEC_B <= v_be < SEC_B_END:
                b_hits_be.append((i, v_be))
        print(f"  {anchor:#x}: aligned LE hits={len(b_hits_le)} BE hits={len(b_hits_be)}")
        if b_hits_le[:3]:
            print(f"    sample LE: " + ", ".join(f"+{i:#x}->{v:#x}" for i, v in b_hits_le[:3]))
        if b_hits_be[:3]:
            print(f"    sample BE: " + ", ".join(f"+{i:#x}->{v:#x}" for i, v in b_hits_be[:3]))


if __name__ == "__main__":
    main()
