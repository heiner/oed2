#!/usr/bin/env python3
"""Scan the unidentified region after the QT lexicon for a flat table_B —
a sequence of u32-BE byte offsets that increase monotonically and span
a small range (since they should be offsets into the ~130 MB Section B
or a similar bounded region).
"""
import struct

DAT = '/Volumes/OED2/OED2.DAT'
START = 0xa4cf000        # right after QT lexicon block_data
END   = 0x104c8000       # next known list anchor (Etymology)
SECTION_B_LEN = 0x07c50f00  # ~130 MB

CHUNK = 1 << 20          # 1 MB
WINDOW = 0x10000         # check 64 KB windows


def is_monotone_u32be(data, max_descents=2):
    """Are 4-byte u32-BE values in `data` monotonically increasing
    (allowing up to `max_descents` exceptions)?"""
    n = len(data) // 4
    if n < 32:
        return False, 0, 0, 0
    vals = struct.unpack(f'>{n}I', data[:n*4])
    descents = 0
    last = vals[0]
    for v in vals[1:]:
        if v < last:
            descents += 1
            if descents > max_descents:
                return False, last, vals[0], vals[-1]
        last = v
    return True, descents, vals[0], vals[-1]


def main():
    with open(DAT, 'rb') as f:
        f.seek(START)
        # Sweep through the region in WINDOW-sized chunks
        candidates = []
        offset = START
        while offset < END:
            f.seek(offset)
            data = f.read(WINDOW)
            if len(data) < WINDOW:
                break
            mono, desc_or_first, first_v, last_v = is_monotone_u32be(data)
            if mono:
                candidates.append((offset, desc_or_first, first_v, last_v))
            offset += WINDOW

    print(f'Found {len(candidates)} 64KB-windows that look monotonic u32-BE.')
    if candidates:
        # Group consecutive windows
        runs = []
        prev_off = None
        cur_run = []
        for off, _desc, first_v, last_v in candidates:
            if prev_off is None or off == prev_off + WINDOW:
                cur_run.append((off, first_v, last_v))
            else:
                if cur_run:
                    runs.append(cur_run)
                cur_run = [(off, first_v, last_v)]
            prev_off = off
        if cur_run:
            runs.append(cur_run)

        for run in runs[:20]:
            start = run[0][0]
            end_off = run[-1][0] + WINDOW
            length = end_off - start
            first = run[0][1]
            last = run[-1][2]
            print(f'  {start:#10x}..{end_off:#10x}  ({length:#x} bytes = {length/(1<<20):.1f} MB)  '
                  f'values {first:#x}..{last:#x}')

    # Even with no monotone windows, look for repeating pattern of u32 BE
    # values in [0, SECTION_B_LEN). Count u32 hits.
    print()
    print('Now scanning for windows where most u32-BE values land in [0, SECTION_B_LEN):')
    with open(DAT, 'rb') as f:
        offset = START
        best = []
        while offset < END:
            f.seek(offset)
            data = f.read(WINDOW)
            if len(data) < WINDOW:
                break
            n = len(data) // 4
            vals = struct.unpack(f'>{n}I', data[:n*4])
            in_range = sum(1 for v in vals if 0 <= v < SECTION_B_LEN)
            frac = in_range / n
            if frac > 0.9:
                best.append((offset, frac, vals[0], vals[-1]))
            offset += WINDOW

    if best:
        # Group consecutive
        for off, frac, first, last in best[:30]:
            print(f'  {off:#10x}: {frac*100:.1f}% u32-BE in section_B range; first={first:#x} last={last:#x}')


if __name__ == '__main__':
    main()
