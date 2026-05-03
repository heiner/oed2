#!/usr/bin/env python3
"""Decode the late-c sparse index (0x1584f800) — 2.4M-entry index into Section B."""
import struct
from pathlib import Path

DAT = Path("/Volumes/OED2/OED2.DAT")
SEC_B = 0x0243b100
SEC_B_END = 0x0a08c000

ANCHOR = 0x1584f800
BLOCK_SIZE = 0x1000
FANOUT = 11
LOGICAL_TOTAL = 2_435_558


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
        # Header
        fh.seek(ANCHOR)
        header = fh.read(BLOCK_SIZE)
        magic, block_size, levels = struct.unpack_from("<HHH", header, 0)
        logical_total = struct.unpack_from("<I", header, 6)[0]
        print(f"magic={magic:#x} block_size={block_size:#x} levels={levels} logical_total={logical_total}")
        print(f"page span = (block_size/2/levels)*16 = {(block_size//2//levels)*16}")

        # Data pages
        page_logical_span = (block_size // 2 // levels) * 16
        data_pages = -(-logical_total // page_logical_span)
        print(f"computed: {data_pages} data pages")
        first_data_page_offset = ANCHOR + BLOCK_SIZE
        last_data_page_offset = first_data_page_offset + (data_pages - 1) * BLOCK_SIZE
        print(f"first data page at {first_data_page_offset:#x}, last at {last_data_page_offset:#x}")

        # Look at the first data page.
        for page_idx in [0, 1, 2, data_pages // 2, data_pages - 1]:
            page_off = first_data_page_offset + page_idx * BLOCK_SIZE
            fh.seek(page_off)
            page = fh.read(BLOCK_SIZE)
            print()
            print(f"--- page {page_idx} (at {page_off:#x}, logical {page_idx * page_logical_span}..{(page_idx+1)*page_logical_span - 1}) ---")
            print(hexdump(page, page_off, lines=8))

            # Hypothesis: page contains slots × levels u16-LE values per slot.
            # Try interpreting as u32-LE (file offsets) and see if they're plausible.
            u32s = struct.unpack_from(f"<{BLOCK_SIZE//4}I", page)
            in_b = sum(1 for v in u32s if SEC_B <= v < SEC_B_END)
            print(f"  u32-LE: {len(u32s)} values, {in_b} land in Section B")
            if in_b > 0:
                first_few = [v for v in u32s if SEC_B <= v < SEC_B_END][:8]
                print(f"  first few B-pointing u32-LE: {[hex(v) for v in first_few]}")

            # Try u24-LE instead (3-byte alignment)
            u24s = []
            for i in range(0, len(page) - 3, 3):
                v = page[i] | (page[i + 1] << 8) | (page[i + 2] << 16)
                u24s.append(v)
            in_b_u24 = sum(1 for v in u24s if SEC_B <= v < SEC_B_END)
            print(f"  u24-LE: {len(u24s)} values, {in_b_u24} land in Section B")

            # Try interpreting as u16 slots + a u32 base
            # i.e., slot_offset[i] = base + delta[i]
            # Find runs of monotonic u16le values
            u16s = struct.unpack_from(f"<{BLOCK_SIZE//2}H", page)
            mono_run = 0
            best_run = 0
            for i in range(1, len(u16s)):
                if u16s[i] >= u16s[i-1] and u16s[i-1] != 0:
                    mono_run += 1
                    best_run = max(best_run, mono_run)
                else:
                    mono_run = 0
            print(f"  u16-LE: longest monotone run = {best_run}")


if __name__ == "__main__":
    main()
