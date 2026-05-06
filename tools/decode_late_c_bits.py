#!/usr/bin/env python3
"""Decode late-c with proper bit-packing: 16 entries × 11 bits per slot."""
import struct
from collections import Counter

DAT = '/Volumes/OED2/OED2.DAT'
ANCHOR = 0x1584f800
BLOCK_SIZE = 0x1000
LEVELS = 11
LOGICAL_TOTAL = 2_435_558


def read_page(idx):
    with open(DAT, 'rb') as f:
        f.seek(ANCHOR + (1 + idx) * BLOCK_SIZE)
        return f.read(BLOCK_SIZE)


def unpack_slot_bits(slot_bytes, bits_per_value, count):
    """Read `count` values, each `bits_per_value` wide, LSB-first."""
    out = []
    bit_pos = 0
    for _ in range(count):
        byte_pos = bit_pos // 8
        bit_off = bit_pos % 8
        v = 0
        for j in range(4):
            if byte_pos + j < len(slot_bytes):
                v |= slot_bytes[byte_pos + j] << (j * 8)
        v >>= bit_off
        v &= (1 << bits_per_value) - 1
        out.append(v)
        bit_pos += bits_per_value
    return out


def main():
    # Decode pages 0, 1, 100, 818 (last)
    slot_size = LEVELS * 2  # 22 bytes
    slots_per_page = BLOCK_SIZE // slot_size
    print(f'levels={LEVELS}, slot_size={slot_size}, slots_per_page={slots_per_page}')
    print(f'entries per slot = 16 (assumption), 16 × 11 bits = 176 bits = 22 bytes ✓')
    print()

    for page_idx in [0, 1, 100, 818]:
        page = read_page(page_idx)
        all_vals = []
        for s_idx in range(slots_per_page):
            slot = page[s_idx * slot_size : (s_idx + 1) * slot_size]
            vals = unpack_slot_bits(slot, 11, 16)
            all_vals.extend(vals)

        cnt = Counter(all_vals)
        n = len(all_vals)
        max_val = (1 << 11) - 1
        print(f'page {page_idx}: {n} entries, unique values: {len(cnt)}')
        print(f'  most common: {cnt.most_common(5)}')
        print(f'  value 2047 (max): {cnt.get(max_val, 0)} ({100*cnt.get(max_val, 0)/n:.1f}%)')
        print(f'  value 0:          {cnt.get(0, 0)} ({100*cnt.get(0, 0)/n:.1f}%)')
        # First 20 entries
        print(f'  first 20 entries: {all_vals[:20]}')
        print(f'  entries 16..32:  {all_vals[16:32]}')

    # Aggregate across all pages
    print()
    print('=== Aggregate across all 819 data pages ===')
    all_vals = []
    for page_idx in range(819):
        page = read_page(page_idx)
        for s_idx in range(slots_per_page):
            slot = page[s_idx * slot_size : (s_idx + 1) * slot_size]
            vals = unpack_slot_bits(slot, 11, 16)
            all_vals.extend(vals)

    cnt = Counter(all_vals)
    n = len(all_vals)
    print(f'total entries: {n}')
    print(f'unique values: {len(cnt)}')
    print(f'value 2047 count: {cnt.get(2047, 0)} ({100*cnt.get(2047, 0)/n:.2f}%)')
    print(f'value 0 count:    {cnt.get(0, 0)} ({100*cnt.get(0, 0)/n:.2f}%)')
    # Distribution histogram (in bins)
    print(f'value distribution (32 bins):')
    bin_size = 64
    bins = [0] * 32
    for v, c in cnt.items():
        bins[v // bin_size] += c
    for i, b in enumerate(bins):
        marker = '*' * min(60, b * 60 // n // 32 * 100 if n > 0 else 0)
        print(f'  [{i*bin_size:>4}..{(i+1)*bin_size-1:>4}]: {b:>10} ({100*b/n:.2f}%)')


if __name__ == '__main__':
    main()
