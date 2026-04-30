#!/usr/bin/env python3
"""Extract OED.EXE SGML entity rendering clues from the Win16 code.

This is a static helper, not a complete emulator.  It recognizes the
simple code shapes used by the OED entity renderer:

* `push len; mov ax,<data-string>; ...; call strcmp-like helper`
* direct stores into the renderer's output-byte and style-byte buffers
* the small single-character jump table at segment 1 offset 0x3e0c
"""

from __future__ import annotations

import argparse
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ne_inspect import NEFile


COMPARE_RE = re.compile(rb'\x6a(?P<length>.)\xb8(?P<offset>..)\x8c\xda\x52\x50')

STRING_ROUTINES = (
    ('combining', 0x41c4, 0x43ac),
    ('greek', 0x43ac, 0x71e0),
    ('latin', 0x71e0, 0x9f58),
)

SINGLE_CHAR_ROUTINE = ('single', 0x3e0c, 0x41c4)
SINGLE_CHAR_TABLE = 0x4112
SINGLE_CHAR_FIRST = 0x27
SINGLE_CHAR_COUNT = 0x54
SINGLE_CHAR_DEFAULT = 0x40e5
RTF_PLAIN_COMMAND = 0x2145
RTF_STYLE_TABLE = 0x3c96
RTF_STYLE_ROWS = 16
RTF_STYLE_ROW_BYTES = 8
RTF_FONT_COMMANDS = {
    1: 0x2191,
    2: 0x216b,
    3: 0x2166,
    4: 0x214d,
    5: 0x2161,
    6: 0x2157,
    7: 0x215c,
    8: 0x2152,
    11: 0x2175,
    12: 0x2170,
    13: 0x217a,
    14: 0x217f,
    15: 0x2185,
    16: 0x218b,
}
RTF_FORMAT_COMMANDS = {
    0x10: 0x2196,
    0x20: 0x219a,
    0x30: 0x219e,
    0x50: 0x21a4,
    0x60: 0x21aa,
}
RTF_COLOR_COMMANDS = {
    (0x00, 0x00, 0x00): 0x21b0,
    (0xff, 0x00, 0x00): 0x21b6,
    (0xff, 0xff, 0x00): 0x21bc,
    (0x00, 0xff, 0x00): 0x21c2,
    (0xff, 0x00, 0xff): 0x21c8,
    (0x00, 0x00, 0xff): 0x21ce,
    (0x00, 0xff, 0xff): 0x21d4,
    (0xff, 0xff, 0xff): 0x21da,
    (0x80, 0x00, 0x00): 0x21e0,
    (0x80, 0x80, 0x00): 0x21e6,
    (0x00, 0x80, 0x00): 0x21ed,
    (0x80, 0x00, 0x80): 0x21f4,
    (0x00, 0x00, 0x80): 0x21fb,
    (0x00, 0x80, 0x80): 0x2202,
    (0x80, 0x80, 0x80): 0x2209,
    (0xc0, 0xc0, 0xc0): 0x2210,
    (0x40, 0x40, 0x40): 0x2217,
}


@dataclass(frozen=True)
class EntityMapping:
    routine: str
    code_offset: int
    data_offset: int | None
    entity: str
    out: tuple[int | None, ...]
    style: tuple[int | None, ...]

    @property
    def out_hex(self) -> str:
        return bytes_hex(self.out)

    @property
    def style_hex(self) -> str:
        return bytes_hex(self.style)


@dataclass(frozen=True)
class RTFStyle:
    value: int
    row_index: int
    row: tuple[int, ...]
    font_id: int | None
    font: str | None
    format: str | None
    color: str | None
    commands: tuple[str, ...]
    note: str = ''

    @property
    def command_text(self) -> str:
        return ''.join(self.commands)

    @property
    def command_summary(self) -> str:
        return ' '.join(command.strip() for command in self.commands)


def parse_int(text: str) -> int:
    return int(text, 0)


def bytes_hex(values: tuple[int | None, ...]) -> str:
    last = -1
    for i, value in enumerate(values):
        if value is not None:
            last = i
    if last < 0:
        return '-'
    return ' '.join(
        '..' if value is None else f'{value:02x}'
        for value in values[:last + 1]
    )


def printable_entity_name(raw: bytes) -> bool:
    if not raw or len(raw) > 40:
        return False
    return all(32 <= b < 127 for b in raw)


def c_string(data: bytes, offset: int) -> bytes:
    if offset < 0 or offset >= len(data):
        return b''
    end = data.find(b'\x00', offset)
    if end < 0:
        end = len(data)
    return data[offset:end]


def c_text(data: bytes, offset: int) -> str:
    return c_string(data, offset).decode('latin1', 'replace')


def exe_segments(exe_path: str) -> tuple[bytes, bytes]:
    ne = NEFile(exe_path)
    segments = {seg.index: seg for seg in ne.segments()}
    code = ne.segment_data(segments[1])
    data = ne.segment_data(segments[ne.auto_data_segment])
    return code, data


def exe_data_segment(exe_path: str) -> bytes:
    _code, data = exe_segments(exe_path)
    return data


def read_rtf_style_rows(data: bytes) -> tuple[tuple[int, ...], ...]:
    rows: list[tuple[int, ...]] = []
    for index in range(RTF_STYLE_ROWS):
        start = RTF_STYLE_TABLE + index * RTF_STYLE_ROW_BYTES
        row = tuple(data[start:start + RTF_STYLE_ROW_BYTES])
        if len(row) != RTF_STYLE_ROW_BYTES:
            raise ValueError(
                f'short RTF style row {index} at data offset 0x{start:x}'
            )
        rows.append(row)
    return tuple(rows)


def rtf_style_for_byte(data: bytes, value: int) -> RTFStyle:
    value &= 0xff
    rows = read_rtf_style_rows(data)
    row_index = value & 0x0f
    row = rows[row_index]
    base_font = row[1] or 2
    high = value & 0xf0
    style_kind = high if high else row[2]

    # seg2:00ca folds row-default bold/italic with an explicit high-nibble
    # italic/bold override into the combined bold-italic command.
    if row[2] == 0x20 and high == 0x10:
        style_kind = 0x30
    elif row[2] == 0x10 and high == 0x20:
        style_kind = 0x30

    font_id: int | None = base_font
    note = ''
    if style_kind == 0x70:
        font_id = 5
    elif style_kind == 0x80:
        font_id = 6
    elif style_kind == 0x90:
        note = 'dynamic-font-helper-0x90'
        font_id = None
    elif style_kind == 0xd0:
        font_id = 8 if base_font == 0x0c else 4
    elif style_kind == 0xe0:
        font_id = 7
    elif style_kind == 0xf0:
        note = 'dynamic-font-helper-0xf0'
        font_id = None

    commands: list[str] = [c_text(data, RTF_PLAIN_COMMAND)]
    font = None
    if font_id is not None:
        font_offset = RTF_FONT_COMMANDS.get(font_id)
        if font_offset is None:
            note = append_note(note, f'unknown-font-{font_id}')
        else:
            font = c_text(data, font_offset)
            commands.append(font)

    fmt = None
    format_offset = RTF_FORMAT_COMMANDS.get(style_kind)
    if format_offset is not None:
        fmt = c_text(data, format_offset)
        commands.append(fmt)

    color = None
    color_key = (row[4], row[5], row[6])
    color_offset = RTF_COLOR_COMMANDS.get(color_key)
    if color_offset is None:
        note = append_note(
            note, f'unknown-color-{color_key[0]:02x}{color_key[1]:02x}'
            f'{color_key[2]:02x}',
        )
    else:
        color = c_text(data, color_offset)
        commands.append(color)

    return RTFStyle(
        value=value,
        row_index=row_index,
        row=row,
        font_id=font_id,
        font=font,
        format=fmt,
        color=color,
        commands=tuple(commands),
        note=note,
    )


def append_note(current: str, addition: str) -> str:
    return addition if not current else f'{current};{addition}'


def rtf_styles_for_exe(exe_path: str) -> dict[int, RTFStyle]:
    data = exe_data_segment(exe_path)
    return {value: rtf_style_for_byte(data, value) for value in range(256)}


def collect_buffer_writes(blob: bytes, start: int, end: int
                          ) -> tuple[tuple[int | None, ...],
                                     tuple[int | None, ...]]:
    out: list[int | None] = [None] * 5
    style: list[int | None] = [None] * 5
    pos = start
    end = min(end, len(blob))
    while pos < end - 6:
        target: list[int | None] | None = None
        if blob[pos:pos + 3] == b'\xc4\x5e\x0a':
            target = out
        elif blob[pos:pos + 3] == b'\xc4\x5e\x0e':
            target = style

        if target is not None and blob[pos + 3:pos + 5] == b'\x26\xc6':
            mode = blob[pos + 5]
            if mode == 0x07 and pos + 6 < end:
                target[0] = blob[pos + 6]
                pos += 7
                continue
            if mode == 0x47 and pos + 7 < end:
                index = blob[pos + 6]
                if index < len(target):
                    target[index] = blob[pos + 7]
                pos += 8
                continue
        pos += 1
    return tuple(out), tuple(style)


def extract_string_routine(blob: bytes, data: bytes, routine: str,
                           start: int, end: int) -> list[EntityMapping]:
    region = blob[start:end]
    matches = []
    for match in COMPARE_RE.finditer(region):
        rel = match.start()
        after = rel + len(match.group(0))
        if b'\x9a\x42\x6e' not in region[after:after + 32]:
            continue
        length = match.group('length')[0]
        data_offset = struct.unpack('<H', match.group('offset'))[0]
        raw = c_string(data, data_offset)
        if not printable_entity_name(raw):
            continue
        # The compare length includes the trailing NUL-like terminator in
        # many cases, so accept exact or one-short readable strings.
        if len(raw) not in (length, max(0, length - 1)):
            continue
        matches.append((start + rel, data_offset, raw.decode('latin1')))

    out: list[EntityMapping] = []
    for i, (code_offset, data_offset, name) in enumerate(matches):
        block_start = code_offset + 1
        block_end = matches[i + 1][0] if i + 1 < len(matches) else end
        output, style = collect_buffer_writes(blob, block_start, block_end)
        if output == (None,) * 5 and style == (None,) * 5:
            continue
        entity = name if name.startswith('&') else f'&{name}'
        out.append(EntityMapping(
            routine, code_offset, data_offset, entity, output, style,
        ))
    return out


def extract_single_char_routine(blob: bytes) -> list[EntityMapping]:
    table = struct.unpack_from(
        f'<{SINGLE_CHAR_COUNT}H', blob, SINGLE_CHAR_TABLE,
    )
    starts = sorted(set(addr for addr in table if addr != SINGLE_CHAR_DEFAULT))
    block_end_by_start: dict[int, int] = {}
    for i, addr in enumerate(starts):
        block_end_by_start[addr] = (
            starts[i + 1] if i + 1 < len(starts) else SINGLE_CHAR_DEFAULT
        )

    out: list[EntityMapping] = []
    for i, target in enumerate(table):
        ch = chr(SINGLE_CHAR_FIRST + i)
        if target == SINGLE_CHAR_DEFAULT or target not in block_end_by_start:
            continue
        output, style = collect_buffer_writes(
            blob, target, block_end_by_start[target],
        )
        if output == (None,) * 5 and style == (None,) * 5:
            continue
        out.append(EntityMapping(
            'single', target, None, f'&{ch}.', output, style,
        ))
    return out


def extract_entities(exe_path: str) -> list[EntityMapping]:
    code, data = exe_segments(exe_path)

    mappings: list[EntityMapping] = []
    mappings.extend(extract_single_char_routine(code))
    for routine, start, end in STRING_ROUTINES:
        mappings.extend(extract_string_routine(code, data, routine, start, end))
    return mappings


def command_list(args: argparse.Namespace) -> None:
    mappings = extract_entities(args.exe)
    if args.contains:
        needle = args.contains.lower()
        mappings = [m for m in mappings if needle in m.entity.lower()]
    if args.routine:
        mappings = [m for m in mappings if m.routine == args.routine]
    if args.entity:
        wanted = {e if e.startswith('&') else f'&{e}' for e in args.entity}
        mappings = [m for m in mappings if m.entity in wanted]
    if args.limit:
        mappings = mappings[:args.limit]

    for m in mappings:
        data = '-' if m.data_offset is None else f'0x{m.data_offset:04x}'
        print(f'{m.routine:<9} code=0x{m.code_offset:04x} '
              f'data={data:<6} {m.entity:<18} '
              f'out={m.out_hex:<14} style={m.style_hex}')
    print(f'total: {len(mappings)}')


def command_stats(args: argparse.Namespace) -> None:
    mappings = extract_entities(args.exe)
    by_routine: dict[str, int] = {}
    for mapping in mappings:
        by_routine[mapping.routine] = by_routine.get(mapping.routine, 0) + 1
    print(f'exe: {Path(args.exe)}')
    print(f'total mappings: {len(mappings)}')
    for routine, count in sorted(by_routine.items()):
        print(f'  {routine:<9} {count}')
    multi = sum(1 for m in mappings if sum(v is not None for v in m.out) > 1)
    styled = sum(1 for m in mappings if any(v is not None for v in m.style))
    print(f'multi-byte outputs: {multi}')
    print(f'style-byte outputs: {styled}')


def command_styles(args: argparse.Namespace) -> None:
    mappings = extract_entities(args.exe)
    rtf_styles = rtf_styles_for_exe(args.exe) if args.rtf else None
    styles: Counter[tuple[int, ...]] = Counter()
    examples: dict[tuple[int, ...], list[EntityMapping]] = defaultdict(list)
    for mapping in mappings:
        style = tuple(value for value in mapping.style
                      if value not in (None, 0))
        if not style:
            continue
        styles[style] += 1
        if len(examples[style]) < args.examples:
            examples[style].append(mapping)

    print(f'style patterns: {len(styles)}')
    for style, count in styles.most_common():
        style_hex = ' '.join(f'{value:02x}' for value in style)
        suffix = ''
        if rtf_styles is not None:
            decoded = [rtf_styles[value].command_summary for value in style]
            suffix = '  rtf=' + ' | '.join(decoded)
        print(f'{count:4d} style={style_hex}{suffix}')
        for mapping in examples[style]:
            print(f'     {mapping.routine:<9} {mapping.entity:<18} '
                  f'out={mapping.out_hex:<12} style={mapping.style_hex}')


def command_rtf_style(args: argparse.Namespace) -> None:
    data = exe_data_segment(args.exe)
    rows = read_rtf_style_rows(data)
    if args.rows:
        print('RTF style rows at data offset 0x3c96:')
        for i, row in enumerate(rows):
            row_hex = ' '.join(f'{value:02x}' for value in row)
            print(f'  row {i:02x}: {row_hex}')
        if not args.style and not args.all:
            return

    styles = list(args.style or [])
    if args.all:
        styles.extend(range(256))
    if not styles:
        styles = [0x00, 0x50, 0x70, 0x80, 0xd0, 0xe0]

    for value in styles:
        decoded = rtf_style_for_byte(data, value)
        row_hex = ' '.join(f'{byte:02x}' for byte in decoded.row)
        font = '-' if decoded.font is None else decoded.font.strip()
        fmt = '-' if decoded.format is None else decoded.format.strip()
        color = '-' if decoded.color is None else decoded.color.strip()
        note = f' note={decoded.note}' if decoded.note else ''
        print(
            f'style=0x{decoded.value:02x} row={decoded.row_index:02x} '
            f'row-bytes={row_hex} font-id={decoded.font_id or "-"} '
            f'font={font} format={fmt} color={color} '
            f'rtf={decoded.command_summary}{note}'
        )


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('exe')
    sub = ap.add_subparsers(dest='command', required=True)

    p_list = sub.add_parser('list')
    p_list.add_argument('--contains')
    p_list.add_argument('--routine',
                        choices=['single', 'combining', 'greek', 'latin'])
    p_list.add_argument('--entity', action='append')
    p_list.add_argument('--limit', type=parse_int, default=0)

    sub.add_parser('stats')
    p_styles = sub.add_parser('styles')
    p_styles.add_argument('--examples', type=int, default=8)
    p_styles.add_argument('--rtf', action='store_true',
                          help='append the EXE-derived RTF command sequence')

    p_rtf_style = sub.add_parser('rtf-style')
    p_rtf_style.add_argument('--style', type=parse_int, action='append',
                             help='decode one style byte; may be repeated')
    p_rtf_style.add_argument('--all', action='store_true',
                             help='decode all 256 possible style bytes')
    p_rtf_style.add_argument('--rows', action='store_true',
                             help='also print the raw 16-row style table')
    return ap


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    if args.command == 'list':
        command_list(args)
    elif args.command == 'stats':
        command_stats(args)
    elif args.command == 'styles':
        command_styles(args)
    elif args.command == 'rtf-style':
        command_rtf_style(args)
    else:
        raise SystemExit(f'unknown command: {args.command}')


if __name__ == '__main__':
    main()
