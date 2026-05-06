#!/usr/bin/env python3
"""Analyse late-c/d/e page format hypothesis: 22-byte slots of variable u16 hash signatures terminated by 0xffff."""
import struct
from collections import Counter

DAT = '/Volumes/OED2/OED2.DAT'
INDEXES = [
    ('late-c', 0x1584f800, 11, 0x1000),
    ('late-d', 0x15b83800, 17, 0x1000),
    ('late-e', 0x16079800, 18, 0x1000),
]


def main():
    for name, anchor, levels, blksize in INDEXES:
        slot_size = 2 * levels  # u16 each
        slots_per_page = blksize // slot_size
        # First 4 data pages
        with open(DAT, 'rb') as f:
            f.seek(anchor + blksize)  # skip header page
            pages = [f.read(blksize) for _ in range(4)]

        print(f'=== {name} (anchor={anchor:#x}, levels={levels}, slot={slot_size} bytes, slots/page={slots_per_page}) ===')
        # Count "real" u16s per slot across the first 4 pages
        real_counts = Counter()
        all_real_values = Counter()
        for p_idx, page in enumerate(pages):
            for s_idx in range(slots_per_page):
                slot = struct.unpack_from(f'<{levels}H', page, s_idx * slot_size)
                # Count from start until 0xffff
                real = 0
                for v in slot:
                    if v == 0xffff:
                        break
                    real += 1
                    all_real_values[v] += 1
                real_counts[real] += 1

        print(f'distribution of "real" u16s per slot (across 4 pages = {slots_per_page * 4} slots):')
        for n in sorted(real_counts):
            print(f'  {n:>3} real values: {real_counts[n]:>5} slots ({100*real_counts[n]/(slots_per_page*4):.1f}%)')
        print(f'total real values: {sum(all_real_values.values())}')
        print(f'unique real values: {len(all_real_values)}')
        # Top 5 most common
        top5 = all_real_values.most_common(5)
        print(f'top 5 most common: {top5}')
        # Histogram of low byte patterns
        print()


if __name__ == '__main__':
    main()
