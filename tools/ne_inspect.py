#!/usr/bin/env python3
"""Inspect 16-bit Windows NE executables enough for OED reverse engineering."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass


def parse_int(text: str) -> int:
    return int(text, 0)


def cstr_table(data: bytes, start: int, end: int | None = None,
               stop_at_zero: bool = True) -> dict[int, str]:
    out: dict[int, str] = {}
    if end is None:
        end = len(data)
    pos = start
    while pos < end:
        n = data[pos]
        if n == 0:
            if stop_at_zero:
                break
            pos += 1
            continue
        if pos + 1 + n > end:
            break
        raw = data[pos + 1:pos + 1 + n]
        out[pos - start] = raw.decode('latin1', 'replace')
        pos += 1 + n
    return out


@dataclass(frozen=True)
class Segment:
    index: int
    sector: int
    file_offset: int
    file_length: int
    flags: int
    min_alloc: int

    @property
    def is_code(self) -> bool:
        return not bool(self.flags & 0x0001)

    @property
    def has_relocs(self) -> bool:
        return bool(self.flags & 0x0100)


class NEFile:
    def __init__(self, path: str):
        self.path = path
        with open(path, 'rb') as f:
            self.data = f.read()
        if self.data[:2] != b'MZ':
            raise ValueError('not an MZ executable')
        self.ne_offset = struct.unpack_from('<I', self.data, 0x3c)[0]
        if self.data[self.ne_offset:self.ne_offset + 2] != b'NE':
            raise ValueError('not an NE executable')
        self._parse_header()

    def _u8(self, off: int) -> int:
        return self.data[self.ne_offset + off]

    def _u16(self, off: int) -> int:
        return struct.unpack_from('<H', self.data, self.ne_offset + off)[0]

    def _u32(self, off: int) -> int:
        return struct.unpack_from('<I', self.data, self.ne_offset + off)[0]

    def _parse_header(self) -> None:
        self.entry_table_off = self._u16(0x04)
        self.entry_table_len = self._u16(0x06)
        self.flags = self._u16(0x0c)
        self.auto_data_segment = self._u16(0x0e)
        self.heap_size = self._u16(0x10)
        self.stack_size = self._u16(0x12)
        self.init_ss_sp = self._u32(0x14)
        self.init_cs_ip = self._u32(0x18)
        self.segment_count = self._u16(0x1c)
        self.module_ref_count = self._u16(0x1e)
        self.nonresident_name_size = self._u16(0x20)
        self.segment_table_off = self._u16(0x22)
        self.resource_table_off = self._u16(0x24)
        self.resident_name_table_off = self._u16(0x26)
        self.module_ref_table_off = self._u16(0x28)
        self.imported_name_table_off = self._u16(0x2a)
        self.nonresident_name_table_file_off = self._u32(0x2c)
        self.movable_entry_count = self._u16(0x30)
        self.alignment_shift = self._u16(0x32)
        self.resource_entry_count = self._u16(0x34)
        self.exe_type = self._u8(0x36)
        self.expected_windows_version = self._u16(0x3e)

    def segments(self) -> list[Segment]:
        out: list[Segment] = []
        table = self.ne_offset + self.segment_table_off
        for i in range(self.segment_count):
            off = table + i * 8
            sector, length, flags, min_alloc = struct.unpack_from(
                '<HHHH', self.data, off)
            if length == 0:
                length = 0x10000
            out.append(Segment(
                i + 1,
                sector,
                sector << self.alignment_shift,
                length,
                flags,
                min_alloc,
            ))
        return out

    def resident_names(self) -> dict[int, str]:
        return cstr_table(self.data, self.ne_offset + self.resident_name_table_off)

    def imported_names(self) -> dict[int, str]:
        start = self.ne_offset + self.imported_name_table_off
        end = self.nonresident_name_table_file_off
        if end <= start:
            end = len(self.data)
        return cstr_table(self.data, start, end, stop_at_zero=False)

    def module_refs(self) -> list[str]:
        names = self.imported_names()
        table = self.ne_offset + self.module_ref_table_off
        refs: list[str] = []
        for i in range(self.module_ref_count):
            name_off = struct.unpack_from('<H', self.data, table + i * 2)[0]
            refs.append(names.get(name_off, f'<name@0x{name_off:x}>'))
        return refs

    def file_offset_to_segment(self, file_offset: int) -> tuple[Segment, int] | None:
        for seg in self.segments():
            if seg.file_offset <= file_offset < seg.file_offset + seg.file_length:
                return seg, file_offset - seg.file_offset
        return None

    def relocations(self, seg: Segment) -> list[tuple[int, int, int, int, int]]:
        if not seg.has_relocs:
            return []
        table = seg.file_offset + seg.file_length
        if table + 2 > len(self.data):
            return []
        count = struct.unpack_from('<H', self.data, table)[0]
        out: list[tuple[int, int, int, int, int]] = []
        pos = table + 2
        for _ in range(count):
            if pos + 8 > len(self.data):
                break
            source_type, flags, offset, target1, target2 = struct.unpack_from(
                '<BBHHH', self.data, pos)
            out.append((source_type, flags, offset, target1, target2))
            pos += 8
        return out

    def segment_data(self, seg: Segment) -> bytes:
        return self.data[seg.file_offset:seg.file_offset + seg.file_length]

    def relocation_desc(self, reloc: tuple[int, int, int, int, int]) -> str:
        source_type, flags, _offset, target1, target2 = reloc
        modules = self.module_refs()
        names = self.imported_names()
        if flags & 0x03 == 0x01:
            module = modules[target1 - 1] if 0 < target1 <= len(modules) else '?'
            desc = f'{module}.#{target2}'
        elif flags & 0x03 == 0x02:
            module = modules[target1 - 1] if 0 < target1 <= len(modules) else '?'
            desc = f'{module}.{names.get(target2, f"name@0x{target2:x}")}'
        elif flags & 0x03 == 0x00:
            desc = f'internal seg={target1} off=0x{target2:x}'
        else:
            desc = f'osfixup {target1}:{target2}'
        return f'src=0x{source_type:02x} flags=0x{flags:02x} {desc}'

    def relocation_chain(self, seg: Segment,
                         reloc: tuple[int, int, int, int, int]) -> list[int]:
        """Return every source offset covered by an NE relocation chain."""
        _source_type, _flags, offset, _target1, _target2 = reloc
        blob = self.segment_data(seg)
        out: list[int] = []
        seen: set[int] = set()
        while 0 <= offset + 1 < len(blob) and offset not in seen:
            out.append(offset)
            seen.add(offset)
            next_offset = struct.unpack_from('<H', blob, offset)[0]
            if next_offset in (0x0000, 0xffff):
                break
            offset = next_offset
        return out

    def relocation_map(
        self, seg: Segment
    ) -> dict[int, list[tuple[int, int, int, int, int]]]:
        """Map every chained source offset to its relocation entry."""
        out: dict[int, list[tuple[int, int, int, int, int]]] = {}
        for reloc in self.relocations(seg):
            for offset in self.relocation_chain(seg, reloc):
                out.setdefault(offset, []).append(reloc)
        return out

    def ascii_strings(self, segment_index: int | None = None,
                      min_len: int = 4) -> dict[int, str]:
        """Return NUL-terminated-ish printable strings keyed by segment offset.

        If segment_index is None, offsets are file offsets.  Otherwise offsets
        are relative to that segment.  This deliberately keeps the parser simple:
        it is for reverse-engineering annotations, not resource extraction.
        """
        if segment_index is None:
            blob = self.data
            base = 0
        else:
            seg = {s.index: s for s in self.segments()}[segment_index]
            blob = self.segment_data(seg)
            base = 0
        out: dict[int, str] = {}
        pos = 0
        while pos < len(blob):
            if 32 <= blob[pos] < 127:
                start = pos
                while pos < len(blob) and 32 <= blob[pos] < 127:
                    pos += 1
                if pos - start >= min_len:
                    out[base + start] = blob[start:pos].decode('ascii')
            else:
                pos += 1
        return out


def command_info(ne: NEFile, _args: argparse.Namespace) -> None:
    print(f'file: {ne.path}')
    print(f'size: {len(ne.data)} bytes')
    print(f'NE offset: 0x{ne.ne_offset:x}')
    print(f'segments: {ne.segment_count}')
    print(f'module refs: {ne.module_ref_count}')
    print(f'alignment shift: {ne.alignment_shift}')
    print(f'auto data segment: {ne.auto_data_segment}')
    print(f'heap=0x{ne.heap_size:x} stack=0x{ne.stack_size:x}')
    print(f'init CS:IP raw=0x{ne.init_cs_ip:08x} SS:SP raw=0x{ne.init_ss_sp:08x}')
    print(f'expected Windows version: 0x{ne.expected_windows_version:04x}')


def command_segments(ne: NEFile, _args: argparse.Namespace) -> None:
    print('seg  file-off   len     flags  alloc   kind  relocs')
    for seg in ne.segments():
        kind = 'CODE' if seg.is_code else 'DATA'
        print(f'{seg.index:3d}  0x{seg.file_offset:06x}  0x{seg.file_length:04x}  '
              f'0x{seg.flags:04x}  0x{seg.min_alloc:04x}  '
              f'{kind:<4}  {len(ne.relocations(seg)):5d}')


def command_names(ne: NEFile, _args: argparse.Namespace) -> None:
    print('resident names:')
    for off, name in ne.resident_names().items():
        print(f'  0x{off:04x} {name}')
    print()
    print('module refs:')
    for i, name in enumerate(ne.module_refs(), start=1):
        print(f'  {i:2d} {name}')
    print()
    print('imported names:')
    for off, name in ne.imported_names().items():
        print(f'  0x{off:04x} {name}')


def command_map(ne: NEFile, args: argparse.Namespace) -> None:
    for off in args.offset:
        mapped = ne.file_offset_to_segment(off)
        if mapped is None:
            print(f'0x{off:x}: not in segment data')
        else:
            seg, seg_off = mapped
            print(f'0x{off:x}: segment {seg.index} + 0x{seg_off:x} '
                  f'({"CODE" if seg.is_code else "DATA"})')


def command_relocs(ne: NEFile, args: argparse.Namespace) -> None:
    for seg in ne.segments():
        if args.segment and seg.index != args.segment:
            continue
        relocs = ne.relocations(seg)
        if not relocs:
            continue
        print(f'segment {seg.index} relocs={len(relocs)}')
        shown = 0
        for reloc in relocs:
            _source_type, _flags, offset, _target1, _target2 = reloc
            chain = ne.relocation_chain(seg, reloc)
            if args.chains and len(chain) > 1:
                offsets = ','.join(f'0x{item:04x}' for item in chain)
                print(
                    f'  off=0x{offset:04x} chain=[{offsets}] '
                    f'{ne.relocation_desc(reloc)}'
                )
            else:
                print(f'  off=0x{offset:04x} {ne.relocation_desc(reloc)}')
            shown += 1
            if args.limit and shown >= args.limit:
                break


def command_extract(ne: NEFile, args: argparse.Namespace) -> None:
    segs = {seg.index: seg for seg in ne.segments()}
    seg = segs.get(args.segment)
    if seg is None:
        raise SystemExit(f'unknown segment: {args.segment}')
    data = ne.data[seg.file_offset:seg.file_offset + seg.file_length]
    with open(args.output, 'wb') as f:
        f.write(data)
    print(f'wrote {len(data)} bytes from segment {seg.index} to {args.output}')


def command_xrefs(ne: NEFile, args: argparse.Namespace) -> None:
    values: list[int] = []
    if args.data_offset:
        values.extend(args.data_offset)
    if args.file_offset:
        for off in args.file_offset:
            mapped = ne.file_offset_to_segment(off)
            if mapped is None:
                print(f'0x{off:x}: not in segment data', file=sys.stderr)
                continue
            _seg, seg_off = mapped
            values.append(seg_off)

    if not values:
        raise SystemExit('provide --data-offset or --file-offset')

    code_segments = [seg for seg in ne.segments() if seg.is_code]
    for value in values:
        pat = value.to_bytes(2, 'little')
        print(f'value 0x{value:04x}')
        hit_count = 0
        for seg in code_segments:
            blob = ne.data[seg.file_offset:seg.file_offset + seg.file_length]
            pos = 0
            while True:
                hit = blob.find(pat, pos)
                if hit < 0:
                    break
                print(f'  segment {seg.index} + 0x{hit:04x} '
                      f'(file 0x{seg.file_offset + hit:x})')
                hit_count += 1
                pos = hit + 1
                if args.limit and hit_count >= args.limit:
                    break
            if args.limit and hit_count >= args.limit:
                break
        if hit_count == 0:
            print('  no code hits')


NDISASM_RE = re.compile(r'^([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s+(.*)$')
IMM_RE = re.compile(r'\b0x([0-9A-Fa-f]{1,4})\b')
PUSH_IMM_RE = re.compile(r'^push\s+(?:word\s+)?0x([0-9A-Fa-f]{1,4})$')


def format_dat_pair(offset_word: int, segment_word: int) -> str | None:
    """Recognise the reader's common file offset spelling: seg:off -> absolute."""
    if 0 <= offset_word <= 0xffff and 0x0800 <= segment_word <= 0x25df:
        absolute = (segment_word << 16) | offset_word
        if absolute >= 0x100000:
            return f'DAT 0x{absolute:08x} ({segment_word:04x}:{offset_word:04x})'
    return None


def command_disasm(ne: NEFile, args: argparse.Namespace) -> None:
    if not shutil.which('ndisasm'):
        raise SystemExit('ndisasm not found')
    segs = {seg.index: seg for seg in ne.segments()}
    seg = segs.get(args.segment)
    if seg is None:
        raise SystemExit(f'unknown segment: {args.segment}')
    start = args.start
    if start < 0 or start >= seg.file_length:
        raise SystemExit(f'start 0x{start:x} outside segment {seg.index}')

    blob = ne.segment_data(seg)
    relocs = ne.relocation_map(seg)
    data_strings = ne.ascii_strings(ne.auto_data_segment, min_len=args.string_min)
    proc = subprocess.run(
        ['ndisasm', '-b', '16', '-o', f'0x{start:x}', '-e', f'0x{start:x}', '-'],
        input=blob,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    shown = 0
    prev_push_imm: int | None = None
    for raw_line in proc.stdout.decode('latin1').splitlines():
        if shown >= args.count:
            break
        match = NDISASM_RE.match(raw_line)
        if not match:
            continue
        addr = int(match.group(1), 16)
        hexbytes = match.group(2)
        asm = match.group(3)
        insn_len = len(hexbytes) // 2
        notes: list[str] = []

        for reloc_off in range(addr, addr + max(insn_len, 1)):
            for reloc in relocs.get(reloc_off, []):
                notes.append(
                    f'reloc@+{reloc_off - addr}: {ne.relocation_desc(reloc)}'
                )

        immediates = [int(m.group(1), 16) for m in IMM_RE.finditer(asm)]
        for word in immediates:
            text = data_strings.get(word)
            if text:
                notes.append(f'data[{word:04x}]="{text[:60]}"')

        push_match = PUSH_IMM_RE.match(asm)
        if push_match and prev_push_imm is not None:
            note = format_dat_pair(int(push_match.group(1), 16), prev_push_imm)
            if note:
                notes.append(note)
        prev_push_imm = int(push_match.group(1), 16) if push_match else None

        suffix = ''
        if notes:
            suffix = ' ; ' + ' | '.join(dict.fromkeys(notes))
        print(f'{addr:04x}  {hexbytes:<18} {asm}{suffix}')
        shown += 1


def command_strings(ne: NEFile, args: argparse.Namespace) -> None:
    for off, text in ne.ascii_strings(args.segment, min_len=args.min_len).items():
        if args.contains and args.contains.lower() not in text.lower():
            continue
        print(f'0x{off:04x} {text}')


def iter_push_immediates(blob: bytes) -> list[tuple[int, int, int]]:
    """Return (offset, length, immediate) for simple 16-bit push immediates."""
    out: list[tuple[int, int, int]] = []
    pos = 0
    while pos < len(blob):
        opcode = blob[pos]
        if opcode == 0x68 and pos + 3 <= len(blob):
            out.append((pos, 3, struct.unpack_from('<H', blob, pos + 1)[0]))
            pos += 3
        elif opcode == 0x6a and pos + 2 <= len(blob):
            out.append((pos, 2, blob[pos + 1]))
            pos += 2
        else:
            pos += 1
    return out


def command_dat_pairs(ne: NEFile, args: argparse.Namespace) -> None:
    for seg in ne.segments():
        if args.segment and seg.index != args.segment:
            continue
        if not seg.is_code and not args.all_segments:
            continue
        pushes = iter_push_immediates(ne.segment_data(seg))
        by_offset = {off: (length, imm) for off, length, imm in pushes}
        last_pair_current_off: int | None = None
        for off, length, imm in pushes:
            prev = None
            prev_off = None
            # Pair only immediately consecutive push-immediate instructions.
            for prev_len in (2, 3):
                candidate = by_offset.get(off - prev_len)
                if candidate is not None and candidate[0] == prev_len:
                    prev = candidate[1]
                    prev_off = off - prev_len
                    break
            if prev_off == last_pair_current_off:
                continue
            if prev is None:
                continue
            note = format_dat_pair(imm, prev)
            if not note:
                continue
            print(f'seg {seg.index} + 0x{off:04x}: {note}')
            last_pair_current_off = off


def iter_far_calls(blob: bytes) -> list[tuple[int, int, int]]:
    """Return (offset, target_offset, raw_segment_word) for CALL FAR immediates."""
    out: list[tuple[int, int, int]] = []
    pos = 0
    while pos + 5 <= len(blob):
        if blob[pos] == 0x9a:
            target_off, raw_seg = struct.unpack_from('<HH', blob, pos + 1)
            out.append((pos, target_off, raw_seg))
            pos += 5
        else:
            pos += 1
    return out


def dat_pairs_in_window(blob: bytes, start: int, end: int) -> list[str]:
    """Return DAT-pair annotations for adjacent push immediates in a byte window."""
    pushes = iter_push_immediates(blob[start:end])
    by_offset = {off: (length, imm) for off, length, imm in pushes}
    out: list[str] = []
    last_pair_current_off: int | None = None
    for off, _length, imm in pushes:
        prev = None
        prev_off = None
        for prev_len in (2, 3):
            candidate = by_offset.get(off - prev_len)
            if candidate is not None and candidate[0] == prev_len:
                prev = candidate[1]
                prev_off = off - prev_len
                break
        if prev_off == last_pair_current_off or prev is None:
            continue
        note = format_dat_pair(imm, prev)
        if note:
            out.append(f'+0x{start + off:04x} {note}')
        last_pair_current_off = off
    return out


def command_calls(ne: NEFile, args: argparse.Namespace) -> None:
    for seg in ne.segments():
        if args.segment and seg.index != args.segment:
            continue
        if not seg.is_code:
            continue
        blob = ne.segment_data(seg)
        relocs = ne.relocation_map(seg)
        shown = 0
        for off, target_off, raw_seg in iter_far_calls(blob):
            reloc_notes: list[str] = []
            for reloc_off in (off + 1, off + 3):
                for reloc in relocs.get(reloc_off, []):
                    reloc_notes.append(f'reloc@+{reloc_off - off}: '
                                       f'{ne.relocation_desc(reloc)}')
            if args.target is not None and target_off != args.target:
                continue
            if args.internal_seg is not None:
                matched = False
                for reloc_off in (off + 1, off + 3):
                    for reloc in relocs.get(reloc_off, []):
                        _st, flags, _roff, target1, _target2 = reloc
                        if flags & 0x03 == 0x00 and target1 == args.internal_seg:
                            matched = True
                if not matched:
                    continue
            suffix = ''
            if reloc_notes:
                suffix = ' ; ' + ' | '.join(reloc_notes)
            print(f'seg {seg.index} + 0x{off:04x}: '
                  f'call far raw {raw_seg:04x}:{target_off:04x}{suffix}')
            if args.context:
                start = max(0, off - args.context)
                pairs = dat_pairs_in_window(blob, start, off)
                for pair in pairs:
                    print(f'    {pair}')
            shown += 1
            if args.limit and shown >= args.limit:
                break


def command_procs(ne: NEFile, args: argparse.Namespace) -> None:
    signatures = [
        (b'\x55\x8b\xec', 'bp-prolog'),
        (b'\x1e\x58\x90\x45\x55\x8b\xec', 'far-prolog'),
    ]
    for seg in ne.segments():
        if args.segment and seg.index != args.segment:
            continue
        if not seg.is_code:
            continue
        blob = ne.segment_data(seg)
        hits: dict[int, str] = {}
        pos = 0
        while pos + 4 <= len(blob):
            if blob[pos] == 0xc8 and blob[pos + 3] == 0x00:
                hits[pos] = f'enter locals=0x{struct.unpack_from("<H", blob, pos + 1)[0]:x}'
            pos += 1
        for sig, name in signatures:
            pos = 0
            while True:
                hit = blob.find(sig, pos)
                if hit < 0:
                    break
                hits[hit] = name
                pos = hit + 1
        count = 0
        for off in sorted(hits):
            if args.start is not None and off < args.start:
                continue
            if args.end is not None and off >= args.end:
                continue
            print(f'seg {seg.index} + 0x{off:04x}: {hits[off]}')
            count += 1
            if args.limit and count >= args.limit:
                break


def disasm_lines(ne: NEFile, seg: Segment) -> list[tuple[int, str, str]]:
    """Return ndisasm lines as (address, hexbytes, asm)."""
    if not shutil.which('ndisasm'):
        raise SystemExit('ndisasm not found')
    blob = ne.segment_data(seg)
    proc = subprocess.run(
        ['ndisasm', '-b', '16', '-o', '0x0', '-'],
        input=blob,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    out: list[tuple[int, str, str]] = []
    for raw_line in proc.stdout.decode('latin1').splitlines():
        match = NDISASM_RE.match(raw_line)
        if match:
            out.append((int(match.group(1), 16), match.group(2), match.group(3)))
    return out


def command_imms(ne: NEFile, args: argparse.Namespace) -> None:
    values = set(args.value)
    shown = 0
    for seg in ne.segments():
        if args.segment and seg.index != args.segment:
            continue
        if not seg.is_code:
            continue
        for addr, hexbytes, asm in disasm_lines(ne, seg):
            if args.start is not None and addr < args.start:
                continue
            if args.end is not None and addr >= args.end:
                continue
            immediates = {int(m.group(1), 16) for m in IMM_RE.finditer(asm)}
            if not (immediates & values):
                continue
            print(f'seg {seg.index} + 0x{addr:04x}: '
                  f'{hexbytes:<18} {asm}')
            shown += 1
            if args.limit and shown >= args.limit:
                return


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path')
    sub = ap.add_subparsers(dest='command', required=True)

    sub.add_parser('info')
    sub.add_parser('segments')
    sub.add_parser('names')

    p_map = sub.add_parser('map')
    p_map.add_argument('offset', nargs='+', type=parse_int)

    p_relocs = sub.add_parser('relocs')
    p_relocs.add_argument('--segment', type=int)
    p_relocs.add_argument('--limit', type=int, default=80)
    p_relocs.add_argument('--chains', action='store_true',
                          help='show every chained source offset')

    p_extract = sub.add_parser('extract')
    p_extract.add_argument('segment', type=int)
    p_extract.add_argument('output')

    p_xrefs = sub.add_parser('xrefs')
    p_xrefs.add_argument('--data-offset', action='append', type=parse_int)
    p_xrefs.add_argument('--file-offset', action='append', type=parse_int)
    p_xrefs.add_argument('--limit', type=int, default=80)

    p_disasm = sub.add_parser('disasm')
    p_disasm.add_argument('segment', type=int)
    p_disasm.add_argument('start', type=parse_int)
    p_disasm.add_argument('--count', type=int, default=80)
    p_disasm.add_argument('--string-min', type=int, default=4)

    p_strings = sub.add_parser('strings')
    p_strings.add_argument('--segment', type=int, default=None)
    p_strings.add_argument('--min-len', type=int, default=4)
    p_strings.add_argument('--contains')

    p_dat_pairs = sub.add_parser('dat-pairs')
    p_dat_pairs.add_argument('--segment', type=int)
    p_dat_pairs.add_argument('--all-segments', action='store_true')

    p_calls = sub.add_parser('calls')
    p_calls.add_argument('--segment', type=int)
    p_calls.add_argument('--target', type=parse_int)
    p_calls.add_argument('--internal-seg', type=int)
    p_calls.add_argument('--context', type=int, default=0,
                         help='bytes before each call to scan for DAT push pairs')
    p_calls.add_argument('--limit', type=int, default=80)

    p_procs = sub.add_parser('procs')
    p_procs.add_argument('--segment', type=int)
    p_procs.add_argument('--start', type=parse_int)
    p_procs.add_argument('--end', type=parse_int)
    p_procs.add_argument('--limit', type=int, default=120)

    p_imms = sub.add_parser('imms')
    p_imms.add_argument('value', nargs='+', type=parse_int)
    p_imms.add_argument('--segment', type=int)
    p_imms.add_argument('--start', type=parse_int)
    p_imms.add_argument('--end', type=parse_int)
    p_imms.add_argument('--limit', type=int, default=120)

    return ap


def main(argv: list[str]) -> int:
    args = build_arg_parser().parse_args(argv)
    if not os.path.exists(args.path):
        print(f'error: {args.path} does not exist', file=sys.stderr)
        return 1
    ne = NEFile(args.path)
    commands = {
        'info': command_info,
        'segments': command_segments,
        'names': command_names,
        'map': command_map,
        'relocs': command_relocs,
        'extract': command_extract,
        'xrefs': command_xrefs,
        'disasm': command_disasm,
        'strings': command_strings,
        'dat-pairs': command_dat_pairs,
        'calls': command_calls,
        'procs': command_procs,
        'imms': command_imms,
    }
    commands[args.command](ne, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
