#!/usr/bin/env python3
"""Decode sparse-index pages using bit-plane interleaving.

Reverse-engineered from seg7:0x3aac:
  Each slot has `levels` u16 values (bit planes).
  Entry E in the slot has value = sum_i ((slot[i] >> E) & 1) << i
  for i in [0, levels).
"""
import struct
from collections import Counter

DAT = '/Volumes/OED2/OED2.DAT'

INDEXES = [
    ('late-c', 0x1584f800, 11, 0x1000),
    ('late-d', 0x15b83800, 17, 0x1000),
    ('late-e', 0x16079800, 18, 0x1000),
]
LOGICAL_TOTAL = 2_435_558


def decode_slot(slot_u16s, entry_in_slot):
    """Extract entry value via bit-plane decoding."""
    val = 0
    mask = 1 << entry_in_slot
    for i, plane in enumerate(slot_u16s):
        if plane & mask:
            val |= 1 << i
    return val


def decode_page(page_bytes, levels):
    """Decode all 186/120/113 slots × 16 entries on a page."""
    slot_size = levels * 2
    slots_per_page = len(page_bytes) // slot_size
    out = []
    for s in range(slots_per_page):
        u16s = struct.unpack_from(f'<{levels}H', page_bytes, s * slot_size)
        for e in range(16):
            out.append(decode_slot(u16s, e))
    return out


def main():
    for name, anchor, levels, blksize in INDEXES:
        slot_size = levels * 2
        slots_per_page = blksize // slot_size
        entries_per_page = slots_per_page * 16
        # Read page 0 (data page 0, after header)
        with open(DAT, 'rb') as f:
            f.seek(anchor + blksize)
            page = f.read(blksize)
        vals = decode_page(page, levels)
        max_val = (1 << levels) - 1
        print(f'=== {name} (levels={levels}, slots/page={slots_per_page}, entries/page={entries_per_page}) ===')
        print(f'  max possible value: {max_val} (= 2^{levels} - 1)')
        cnt = Counter(vals)
        print(f'  page 0 entries: {len(vals)}')
        print(f'  unique values: {len(cnt)}')
        print(f'  first 16 entries (= slot 0): {vals[:16]}')
        print(f'  most common 8: {cnt.most_common(8)}')
        print(f'  count of max value ({max_val}): {cnt.get(max_val, 0)}')
        print(f'  count of 0: {cnt.get(0, 0)}')
        print()


if __name__ == '__main__':
    main()
