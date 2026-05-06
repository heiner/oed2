#!/usr/bin/env python3
"""Decode late-c sparse index pages — try multiple bit-packing schemes."""
import struct

DAT = '/Volumes/OED2/OED2.DAT'
ANCHOR = 0x1584f800
BLOCK_SIZE = 0x1000
LEVELS = 11
LOGICAL_TOTAL = 2_435_558
SPAN = (BLOCK_SIZE // 2 // LEVELS) * 16  # 2976


def read_page(idx):
    with open(DAT, 'rb') as f:
        f.seek(ANCHOR + (1 + idx) * BLOCK_SIZE)
        return f.read(BLOCK_SIZE)


def decode_u16_le(page, n=None):
    """Read page as u16-LE values."""
    n = n if n is not None else len(page) // 2
    return struct.unpack(f'<{n}H', page[:n*2])


def packed_bits(page, bits_per_value, count):
    """Read `count` little-endian bit-packed values, each `bits_per_value` wide."""
    out = []
    bit_pos = 0
    for _ in range(count):
        byte_pos = bit_pos // 8
        bit_off = bit_pos % 8
        if byte_pos >= len(page):
            break
        # Read enough bytes
        # max 32 bits read
        v = 0
        for j in range(4):
            if byte_pos + j < len(page):
                v |= page[byte_pos + j] << (j * 8)
        v >>= bit_off
        v &= (1 << bits_per_value) - 1
        out.append(v)
        bit_pos += bits_per_value
    return out


def main():
    page = read_page(0)
    print(f'Page 0 of late-c at file offset {ANCHOR + BLOCK_SIZE:#x}')
    print(f'Logical span: {SPAN} entries (logical 0..{SPAN-1})')
    print()

    # Hypothesis 1: u16-LE structure
    u16s = decode_u16_le(page)
    print(f'As u16-LE: first 24 = {[hex(v) for v in u16s[:24]]}')
    # Count occurrences of common sentinels
    sentinel_counts = {}
    for v in u16s:
        if v == 0xffff or v >= 0xf000:
            sentinel_counts[v] = sentinel_counts.get(v, 0) + 1
    print(f'Top 10 most-common u16 values: {sorted(((v,c) for c,v in [(c,v) for v,c in u16s.__class__([(v,u16s.count(v)) for v in set(u16s) if u16s.count(v) > 1])]), reverse=True)[:10] if False else "skipped"}')
    # Actually do a proper count
    from collections import Counter
    cnt = Counter(u16s)
    print(f'Unique u16 values: {len(cnt)}, most common: {cnt.most_common(8)}')
    print()

    # Hypothesis 2: 11-bit packed values, 2976 of them
    print('--- 11-bit packed (LE), first 30 values ---')
    vals = packed_bits(page, 11, 30)
    print(f'first 30: {vals}')
    print(f'min={min(vals)}, max={max(vals)}')

    print('--- 11-bit packed (LE), all 2976 values ---')
    all_vals = packed_bits(page, 11, 2976)
    print(f'count: {len(all_vals)}, min: {min(all_vals)}, max: {max(all_vals)}')
    cnt = Counter(all_vals)
    print(f'unique values: {len(cnt)}')
    print(f'most common 8: {cnt.most_common(8)}')

    # Are values monotone increasing?
    monotone_runs = 1
    last = all_vals[0]
    longest_run = 1
    cur_run = 1
    for v in all_vals[1:]:
        if v >= last:
            cur_run += 1
            longest_run = max(longest_run, cur_run)
        else:
            cur_run = 1
        last = v
    print(f'Longest monotone increasing run: {longest_run}')

    # Hypothesis 3: try as 22-byte slot, 11 u16-LE values per slot, 186 slots
    print()
    print('--- as 186 slots × 11 u16-LE ---')
    slots = []
    for i in range(186):
        slot = struct.unpack_from('<11H', page, i * 22)
        slots.append(slot)
    print(f'slot 0:   {[hex(v) for v in slots[0]]}')
    print(f'slot 1:   {[hex(v) for v in slots[1]]}')
    print(f'slot 92:  {[hex(v) for v in slots[92]]}')
    print(f'slot 185: {[hex(v) for v in slots[185]]}')

    # Hypothesis 4: 11 BE u16 per slot
    print()
    print('--- as 186 slots × 11 u16-BE ---')
    for i in [0, 1, 92, 185]:
        slot = struct.unpack_from('>11H', page, i * 22)
        print(f'slot {i:3d}: {[hex(v) for v in slot]}')


if __name__ == '__main__':
    main()
