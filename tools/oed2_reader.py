#!/usr/bin/env python3
"""
First-pass reader for OED2.DAT.

This is not a complete Oxford viewer.  It reads the structural pieces we
currently understand:

* the 66-entry file header
* the Section-D body block stream
* executable-derived body record materialization

The body format is SGML markup split into small logical records.  The
Win16 reader stores payload fragments separated by high-bit marker bytes
and an aux canonical-Huffman stream of fragment ids; symbol 0 in each
block is the observed record delimiter.

Examples:
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT info
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT blocks --limit 5
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT find abandon
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT dump --block 0
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT aux --block 0
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyrec --list word --index 8 --count 20
    python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT dump --offset 0x16721000
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import os
import re
import struct
import sys
import unicodedata
from collections import Counter, deque
from dataclasses import dataclass
from typing import Iterable, Iterator


HEADER_LONGS = 66
HEADER_BYTES = HEADER_LONGS * 4

SECTION_A_START = 0x00000000
SECTION_B_START = 0x0243B100
SECTION_C_START = 0x0A08C000
SECTION_D_START = 0x0B01CE00
EOF_EXPECTED = 0x25DF7000

BODY_BLOCK_STRIDE = 0x8000
BODY_BLOCK_RESIDUE = 0x1000
BODY_HEADER_BYTES = 16

BODY_LEN_MIN = 0x1D00
BODY_LEN_MAX = 0x2000
BODY_AUX_MIN = 0x0300
BODY_AUX_MAX = 0x0500
BODY_AUX_PREFIX_WORDS = 64
BODY_CONTROL_OFFSET = 0x16701000
BODY_CONTROL_WORDS = 9

CANDIDATE_FRAGMENT_TABLE_START = 0x165BE800
CANDIDATE_FRAGMENT_TABLE_END = 0x1667078A
CANDIDATE_FRAGMENT_STREAM_START = 0x16670802
CANDIDATE_FRAGMENT_RECORD_SIZE = 5

ORIGINAL_READER_OFFSETS = (
    ('init/body control', 0x16701000, 'opened during startup, just before framed body blocks'),
    ('late dense stream', 0x18CE0000, 'startup input to the late/body reader'),
    ('startup control A', 0x155B2800, 'zero-heavy startup control/index block'),
    ('startup control B', 0x15512800, 'zero-heavy startup control/index block'),
    ('title fallback', 0x15416000, 'used if title.lst is unavailable'),
    ('word-list control', 0x143F3000, 'shared by Word/POS/First Date lists'),
    ('word-list table A', 0x145FE800, 'shared by Word/POS/First Date lists'),
    ('word-list table B', 0x14602800, 'shared by Word/POS/First Date lists'),
    ('phrase-list control', 0x1499F000, 'Phrase List'),
    ('phrase-list table A', 0x14AC9800, 'Phrase List'),
    ('phrase-list table B', 0x14ACD800, 'Phrase List'),
    ('variant-list control', 0x14C18800, 'Variant Form List'),
    ('variant-list table A', 0x14E15800, 'Variant Form List'),
    ('variant-list table B', 0x14E19800, 'Variant Form List'),
    ('greek-list control', 0x14FDB800, 'Greek List'),
    ('greek-list table A', 0x15053800, 'Greek List'),
    ('greek-list table B', 0x15054800, 'Greek List'),
    ('phonetics control', 0x25BB1000, 'Phonetics List'),
    ('phonetics table A', 0x152E9800, 'Phonetics List'),
    ('phonetics table B', 0x152EC000, 'Phonetics List'),
    ('cited-form table', 0x13D01000, 'Cited Forms'),
    ('cited-form index', 0x13CFF800, 'Cited Forms'),
    ('cited-form table 2', 0x13B08000, 'Cited Forms'),
    ('cited-form index 2', 0x13A1B000, 'Cited Forms'),
    ('work-title table', 0x12DEE800, 'Work Titles'),
    ('work-title index', 0x131E8800, 'Work Titles'),
    ('section-c anchor', 0x0A08B000, 'plain guideword/index neighbourhood'),
    ('late index A', 0x15713800, 'hard-coded by original reader'),
    ('late index B', 0x15776000, 'hard-coded by original reader'),
    ('late index C', 0x1584F800, 'hard-coded by original reader'),
    ('late index D', 0x15B83800, 'hard-coded by original reader'),
    ('late index E', 0x16079800, 'hard-coded by original reader'),
    ('earlier index A', 0x110D9800, 'hard-coded by original reader'),
    ('earlier index B', 0x10F66800, 'hard-coded by original reader'),
)

OED_LISTS = {
    'word': (0x143F3000, 'Word List / POS Word List / First Date Word List'),
    'phrase': (0x1499F000, 'Phrase List'),
    'variant': (0x14C18800, 'Variant Form List'),
    'greek': (0x14FDB800, 'Greek List'),
    'phonetics': (0x25BB1000, 'Phonetics List'),
    'cited1': (0x13CFF800, 'Cited Forms small index'),
    'cited2': (0x13A1B000, 'Cited Forms main index'),
    'work1': (0x12DEE800, 'Work Titles small index'),
    'work2': (0x131E8800, 'Work Titles main index'),
}

OED_LIST_TABLES = {
    'word': (0x145FE800, 0x14602800),
    'phrase': (0x14AC9800, 0x14ACD800),
    'variant': (0x14E15800, 0x14E19800),
    'greek': (0x15053800, 0x15054800),
    'phonetics': (0x152E9800, 0x152EC000),
    'cited1': (0x13D01000, None),
    'cited2': (0x13B08000, None),
    'work1': (None, None),
    'work2': (None, None),
}

OED_SPARSE_INDEXES = {
    'startup-a': (0x155B2800, 'startup sparse index A'),
    'startup-b': (0x15512800, 'startup sparse index B'),
    'late-a': (0x15713800, 'late sparse index A'),
    'late-b': (0x15776000, 'late sparse index B'),
    'late-c': (0x1584F800, 'late sparse index C'),
    'late-d': (0x15B83800, 'late sparse index D'),
    'late-e': (0x16079800, 'late sparse index E'),
}

TAG_RE = re.compile(rb'<[/A-Za-z][A-Za-z0-9/]*')
ENTRY_START_RE = re.compile(rb'^<e(?:\s|>)')
ENTITY_REF_RE = re.compile(r'&[A-Za-z0-9]+\.?')
TEXT_SCORE_PATTERNS = (
    ' the ', ' of ', ' and ', ' to ', ' in ', ' that ', ' with ',
    '</', '<q', '<hw', '<w>', '<lc>', '<qt>', 'ing', 'ion', 'ed', 'er',
)

ENTITY_SUFFIX_MARKS = {
    'acu': '\u0301',
    'grave': '\u0300',
    'circ': '\u0302',
    'tilde': '\u0303',
    'uml': '\u0308',
    'mac': '\u0304',
    'breve': '\u0306',
    'hacek': '\u030c',
    'dot': '\u0307',
    'dotab': '\u0307',
    'ced': '\u0327',
    'hook': '\u0309',
    'ang': '\u030a',
}
ENTITY_NAME_UNICODE = {
    'Alpha': '\u0391',
    'Beta': '\u0392',
    'Gamma': '\u0393',
    'Delta': '\u0394',
    'Epsilon': '\u0395',
    'Zeta': '\u0396',
    'Eta': '\u0397',
    'Theta': '\u0398',
    'Iota': '\u0399',
    'Kappa': '\u039a',
    'Lambda': '\u039b',
    'Mu': '\u039c',
    'Nu': '\u039d',
    'Xi': '\u039e',
    'Omicron': '\u039f',
    'Pi': '\u03a0',
    'Rho': '\u03a1',
    'Sigma': '\u03a3',
    'Tau': '\u03a4',
    'Upsilon': '\u03a5',
    'Phi': '\u03a6',
    'Chi': '\u03a7',
    'Psi': '\u03a8',
    'Omega': '\u03a9',
    'alpha': '\u03b1',
    'beta': '\u03b2',
    'gamma': '\u03b3',
    'delta': '\u03b4',
    'epsilon': '\u03b5',
    'zeta': '\u03b6',
    'eta': '\u03b7',
    'theta': '\u03b8',
    'iota': '\u03b9',
    'kappa': '\u03ba',
    'lambda': '\u03bb',
    'mu': '\u03bc',
    'nu': '\u03bd',
    'xi': '\u03be',
    'omicron': '\u03bf',
    'pi': '\u03c0',
    'rho': '\u03c1',
    'sigma': '\u03c3',
    'Csigma': '\u03c2',
    'tau': '\u03c4',
    'upsilon': '\u03c5',
    'phi': '\u03c6',
    'chi': '\u03c7',
    'psi': '\u03c8',
    'omega': '\u03c9',
    'th': '\u00fe',
    'Th': '\u00de',
    'edh': '\u00f0',
    'Edh': '\u00d0',
    'ae': '\u00e6',
    'Ae': '\u00c6',
    'oe': '\u0153',
    'Oe': '\u0152',
    'ygh': '\u021d',
    'Ygh': '\u021c',
    'schwa': '\u0259',
    'longs': '\u017f',
    'eszett': '\u00df',
    'wyn': '\u01bf',
    'oq': '\u2018',
    'cq': '\u2019',
    'oqq': '\u201c',
    'cqq': '\u201d',
    'osb': '[',
    'csb': ']',
    'en': '\u2013',
    'em': '\u2014',
    'emem': '\u2e3a',
    'dd': '..',
    'ddd': '...',
    'es': ' ',
    'ts': ' ',
    'amp': '&',
    'and': 'and',
    'lt': '<',
    'gt': '>',
    'times': '\u00d7',
    'sect': '\u00a7',
    'page': '\u00b6',
    'para': '\u00b6',
    'dag': '\u2020',
    'ddag': '\u2021',
    'deg': '\u00b0',
    'min': '\u2212',
    'pm': '\u00b1',
    'cent': '\u00a2',
    'dollar': '$',
    'pstlg': '\u00a3',
    'dubh': '~',
    'swing': '~',
    'vb': '|',
    'at': '@',
    'sqrt': '\u221a',
    'infin': '\u221e',
    'ident': '\u2261',
    'prop': '\u221d',
    'elem': '\u2208',
    'union': '\u222a',
    'integ': '\u222b',
    'le': '\u2264',
    'ge': '\u2265',
    'neq': '\u2260',
    'div': '\u00f7',
    'logicor': '\u2228',
    'logicand': '\u2227',
    'rar': '\u2192',
    'ang': '\u2220',
    'flat': '\u266d',
    'natural': '\u266e',
    'sharp': '\u266f',
    'male': '\u2642',
    'female': '\u2640',
    'tri': '\u25b3',
    'square': '\u25a1',
    'star': '\u2606',
    'a': 'a',
    'c': 'c',
}
HEADGROUP_OPEN_TAGS = (b'<hw', b'<hm>', b'<ps>')
HEADGROUP_CLOSE_TAGS = (b'</hw', b'</hm>', b'</ps>')
HEADGROUP_END_TAG = b'</hg>'
PHONETIC_MULTI_REPLACEMENTS = (
    # Observed in `<ph>"&bsIt</ph>` and `<ph>"&bs@lju:t</ph>`.
    # In the article stream this compact token represents the visible
    # /æbs/ cluster, not a normal SGML entity.
    ('&bs', 'æbs'),
    ('@U', 'əʊ'),
    ('i:', 'iː'),
    ('u:', 'uː'),
    ('A:', 'ɑː'),
    ('O:', 'ɔː'),
    ('3:', 'ɜː'),
)
PHONETIC_CHAR_REPLACEMENTS = {
    '"': 'ˈ',
    "'": 'ˌ',
    '@': 'ə',
    'I': 'ɪ',
    'U': 'ʊ',
    'E': 'ɛ',
    'A': 'ɑ',
    'O': 'ɒ',
    'V': 'ʌ',
    'N': 'ŋ',
    'S': 'ʃ',
    'Z': 'ʒ',
    'T': 'θ',
    'D': 'ð',
}
ANSI_RESET = '\x1b[0m'
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')
SGML_ANSI_STYLES = {
    'hw': '\x1b[1;34m',
    'hm': '\x1b[1;34m',
    'ph': '\x1b[36m',
    'ps': '\x1b[3;35m',
    'cf': '\x1b[3m',
    'vf': '\x1b[3m',
    'vd': '\x1b[3m',
    've': '\x1b[3m',
    'vfl': '\x1b[3m',
    'la': '\x1b[35m',
    'bl': '\x1b[35m',
    'pt': '\x1b[35m',
    'q': '\x1b[32m',
    'qt': '\x1b[32m',
    'qd': '\x1b[2m',
    'a': '\x1b[32m',
    'w': '\x1b[3;32m',
    'bib': '\x1b[32m',
    'lc': '\x1b[2m',
    'x': '\x1b[36m',
    'xr': '\x1b[36m',
    'xs': '\x1b[36m',
    'gr': '\x1b[33m',
    'gk': '\x1b[33m',
}


def parse_int(text: str) -> int:
    return int(text, 0)


def printable(c: int) -> str:
    if c in (9, 10, 13) or 32 <= c < 127:
        return chr(c)
    return '.'


def normalize_highbit(buf: bytes) -> str:
    """Lossy readable view: clear bit 7 on high bytes."""
    return ''.join(printable(b & 0x7f if b >= 0x80 else b) for b in buf)


def marked_highbit(buf: bytes) -> str:
    """Readable view that marks bytes whose high bit was set."""
    out: list[str] = []
    for b in buf:
        c = b & 0x7f if b >= 0x80 else b
        ch = printable(c)
        out.append(f'{{{ch}}}' if b >= 0x80 else ch)
    return ''.join(out)


def hexdump(buf: bytes, start: int) -> str:
    lines = []
    for i in range(0, len(buf), 16):
        chunk = buf[i:i + 16]
        hx = ' '.join(f'{b:02x}' for b in chunk)
        asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{start + i:08x}: {hx:<47}  {asc}')
    return '\n'.join(lines)


def highbit_normalized_byte(b: int) -> int:
    return b & 0x7f if b >= 0x80 else b


def normalized_record_text(buf: bytes) -> str:
    return ''.join(printable(highbit_normalized_byte(b)) for b in buf)


def raw_record_text(buf: bytes) -> str:
    return ''.join(printable(b) for b in buf)


def marked_bytes(buf: bytes) -> str:
    out: list[str] = []
    for b in buf:
        if 32 <= b < 127:
            out.append(chr(b))
        elif b == 0x0a:
            out.append('\\n')
        else:
            out.append(f'<{b:02x}>')
    return ''.join(out)


def is_entry_start_record(data: bytes) -> bool:
    return ENTRY_START_RE.match(data) is not None


def sgml_plainish_text(data: bytes) -> str:
    text = re.sub(rb'<[^>]*>', b'', data)
    text = re.sub(rb'\s+', b' ', text).strip()
    return normalized_record_text(text)


def entity_bytes_preview(buf: bytes) -> str | None:
    if any(b < 0x20 and b not in (0x09, 0x0a, 0x0d) for b in buf):
        return None
    return buf.decode('cp1252', 'replace')


def load_exe_entity_map(exe_path: str, routines: set[str] | None = None):
    from oed2_exe_entities import extract_entities

    out = {}
    for mapping in extract_entities(exe_path):
        if routines is not None and mapping.routine not in routines:
            continue
        out[mapping.entity] = mapping
        if mapping.entity.endswith('.'):
            out.setdefault(mapping.entity[:-1], mapping)
    return out


def load_exe_rtf_styles(exe_path: str):
    from oed2_exe_entities import rtf_styles_for_exe

    return rtf_styles_for_exe(exe_path)


def entity_name_unicode(entity: str) -> str | None:
    name = entity[1:] if entity.startswith('&') else entity
    name = name[:-1] if name.endswith('.') else name
    mapped = ENTITY_NAME_UNICODE.get(name)
    if mapped is not None:
        return mapped
    for suffix, mark in sorted(ENTITY_SUFFIX_MARKS.items(),
                               key=lambda item: len(item[0]),
                               reverse=True):
        if name.endswith(suffix) and len(name) > len(suffix):
            base = name[:-len(suffix)]
            if len(base) == 1 and base.isalpha():
                return unicodedata.normalize('NFC', base + mark)
    return None


def entity_mapping_vectors(mapping) -> tuple[bytes, bytes]:
    last = -1
    for values in (mapping.out, mapping.style):
        for i, value in enumerate(values):
            if value is not None:
                last = max(last, i)
    if last < 0:
        return b'', b''
    out = bytes(
        0 if mapping.out[i] is None else mapping.out[i]
        for i in range(last + 1)
    )
    style = bytes(
        0 if mapping.style[i] is None else mapping.style[i]
        for i in range(last + 1)
    )
    return out, style


def entity_mapping_preview(mapping) -> str | None:
    named = entity_name_unicode(mapping.entity)
    if named is not None:
        return named
    out, _style = entity_mapping_vectors(mapping)
    if any(value not in (None, 0) for value in mapping.style):
        return None
    return entity_bytes_preview(out)


def style_rtf_summary(style: bytes, rtf_styles) -> str:
    if not rtf_styles:
        return ''
    values = [value for value in style if value]
    if not values:
        return ''
    unique_values: list[int] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    parts: list[str] = []
    for value in unique_values:
        decoded = rtf_styles.get(value)
        if decoded is None:
            parts.append(f'{value:02x}:?')
            continue
        summary = decoded.command_summary
        if decoded.note:
            summary += f' ({decoded.note})'
        if len(unique_values) == 1:
            parts.append(summary)
        else:
            parts.append(f'{value:02x}:{summary}')
    return ' | '.join(parts)


def load_exe_entity_previews(exe_path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for mapping in load_exe_entity_map(exe_path).values():
        last = -1
        for i, value in enumerate(mapping.out):
            if value is not None:
                last = i
        if last < 0:
            continue
        preview = entity_mapping_preview(mapping)
        if preview is None:
            continue
        out[mapping.entity] = preview
        if mapping.entity.endswith('.'):
            out.setdefault(mapping.entity[:-1], preview)
    return out


def sgml_renderish_text(data: bytes, entity_previews: dict[str, str]) -> str:
    rendered = sgml_visible_text(data)

    def replace_entity(match: re.Match[str]) -> str:
        token = match.group(0)
        return (
            entity_previews.get(token)
            or entity_previews.get(token + '.')
            or token
        )

    rendered = re.sub(r'&[A-Za-z0-9]+\.?', replace_entity, rendered)
    rendered = re.sub(r'\s+', ' ', rendered).strip()
    return rendered


def decode_phonetic_text(text: str) -> str:
    for source, replacement in PHONETIC_MULTI_REPLACEMENTS:
        text = text.replace(source, replacement)
    return ''.join(PHONETIC_CHAR_REPLACEMENTS.get(ch, ch) for ch in text)


def sgml_visible_text(data: bytes) -> str:
    """Strip SGML while preserving a few display-level tag effects.

    This is intentionally smaller than the real renderer.  It implements
    behaviour we have direct evidence for in the original output:
    pronunciation brackets, phonetic-font transliteration, and bracketed
    etymology.
    """
    source = ''.join(
        chr(highbit_normalized_byte(b))
        for b in data
    )
    out: list[str] = []
    pos = 0
    while pos < len(source):
        if source.startswith('<ph>', pos):
            end = source.find('</ph>', pos)
            if end >= 0:
                out.append(decode_phonetic_text(source[pos + 4:end]))
                pos = end + len('</ph>')
                continue
        ch = source[pos]
        if ch == '<':
            end = source.find('>', pos)
            if end < 0:
                pos += 1
                continue
            tag = source[pos:end + 1].lower()
            if tag.startswith('<pr'):
                out.append('(')
            elif tag.startswith('</pr'):
                out.append(')')
            elif tag.startswith('<etym'):
                out.append('[')
            elif tag.startswith('</etym'):
                out.append('] ')
            pos = end + 1
            continue
        out.append(ch)
        pos += 1
    return ''.join(out)


def sgml_tag_name(tag: str) -> tuple[str, bool]:
    body = tag[1:-1].strip().lower()
    closing = body.startswith('/')
    if closing:
        body = body[1:].lstrip()
    if body.endswith('/'):
        body = body[:-1].rstrip()
    if not body:
        return '', closing
    return body.split(None, 1)[0], closing


def ansi_reapply_stack(style_stack: list[str]) -> str:
    return ANSI_RESET + ''.join(SGML_ANSI_STYLES[name]
                                for name in style_stack)


def entity_token_preview(token: str, entity_map) -> str:
    mapping = entity_map.get(token) or entity_map.get(token + '.')
    if mapping is None:
        return token
    preview = entity_mapping_preview(mapping)
    return token if preview is None else preview


def sgml_terminal_renderish_text(data: bytes, entity_map) -> str:
    """Render a rough terminal view with ANSI styling for common SGML tags."""
    source = ''.join(
        chr(highbit_normalized_byte(b))
        for b in data
    )
    out: list[str] = []
    style_stack: list[str] = []
    last_space = True

    def emit_text(text: str) -> None:
        nonlocal last_space
        for ch in text:
            if ch.isspace():
                if not last_space:
                    out.append(' ')
                    last_space = True
                continue
            out.append(ch)
            last_space = False

    pos = 0
    while pos < len(source):
        if source.startswith('<ph>', pos):
            end = source.find('</ph>', pos)
            if end >= 0:
                out.append(SGML_ANSI_STYLES['ph'])
                emit_text(decode_phonetic_text(source[pos + 4:end]))
                out.append(ansi_reapply_stack(style_stack))
                pos = end + len('</ph>')
                continue
        ch = source[pos]
        if ch == '<':
            end = source.find('>', pos)
            if end < 0:
                pos += 1
                continue
            tag = source[pos:end + 1]
            name, closing = sgml_tag_name(tag)
            if name == 'pr':
                emit_text(')' if closing else '(')
            elif name == 'etym':
                emit_text('] ' if closing else '[')
            elif name in SGML_ANSI_STYLES:
                if closing:
                    for i in range(len(style_stack) - 1, -1, -1):
                        if style_stack[i] == name:
                            del style_stack[i]
                            out.append(ansi_reapply_stack(style_stack))
                            break
                else:
                    style_stack.append(name)
                    out.append(SGML_ANSI_STYLES[name])
            pos = end + 1
            continue
        if ch == '&':
            match = ENTITY_REF_RE.match(source, pos)
            if match is not None:
                emit_text(entity_token_preview(match.group(0), entity_map))
                pos = match.end()
                continue
        emit_text(ch)
        pos += 1
    if style_stack:
        out.append(ANSI_RESET)
    return ''.join(out).strip()


def ansi_visible_truncate(text: str, limit: int) -> str:
    if limit < 0:
        return text
    out: list[str] = []
    visible = 0
    pos = 0
    while pos < len(text) and visible < limit:
        if text[pos] == '\x1b':
            match = ANSI_RE.match(text, pos)
            if match is not None:
                out.append(match.group(0))
                pos = match.end()
                continue
        out.append(text[pos])
        visible += 1
        pos += 1
    preview = ''.join(out)
    if '\x1b[' in preview:
        preview += ANSI_RESET
    return preview


def append_text_atoms(atoms: list[RenderAtom], text: str) -> None:
    for ch in text:
        try:
            raw = ch.encode('cp1252')
        except UnicodeEncodeError:
            raw = b'?'
        atoms.append(RenderAtom(ch, raw, b'\x00' * len(raw), ch))


def sgml_render_atoms(data: bytes, entity_map) -> list[RenderAtom]:
    rendered = sgml_visible_text(data)
    atoms: list[RenderAtom] = []
    pos = 0
    for match in ENTITY_REF_RE.finditer(rendered):
        append_text_atoms(atoms, rendered[pos:match.start()])
        token = match.group(0)
        mapping = entity_map.get(token) or entity_map.get(token + '.')
        if mapping is None:
            raw = token.encode('ascii', 'replace')
            atoms.append(RenderAtom(token, raw, b'\x00' * len(raw), token))
        else:
            out, style = entity_mapping_vectors(mapping)
            preview = entity_mapping_preview(mapping)
            if preview is None:
                preview = token
            atoms.append(RenderAtom(token, out, style, preview))
        pos = match.end()
    append_text_atoms(atoms, rendered[pos:])
    return atoms


def find_tag_end(data: bytes, pos: int) -> int:
    end = data.find(b'>', pos)
    return len(data) if end < 0 else end + 1


def append_entity_preview(out: list[str], token: str, entity_map) -> None:
    mapping = entity_map.get(token) or entity_map.get(token + '.')
    if mapping is None:
        name = token[1:] if token.startswith('&') else token
        name = name[:-1] if name.endswith('.') else name
        out.append(f'<{name}>')
        return
    preview = entity_mapping_preview(mapping)
    if preview is None:
        out.append(token)
    else:
        out.append(preview)


def sgml_headgroup_text(data: bytes, entity_map) -> str:
    """Approximate the `seg1:ce44` head-group text extractor.

    The original routine copies text only while inside `<hw`, `<hm>`, or
    `<ps>` regions, skips SGML tags, ends at `</hg>`, translates Latin
    entity references through the entity renderer, and maps ASCII
    apostrophe to CP1252 right quote.
    """
    source = bytes(highbit_normalized_byte(b) for b in data)
    out: list[str] = []
    pos = 0
    inside = False
    while pos < len(source):
        if source.startswith(HEADGROUP_END_TAG, pos):
            break
        byte = source[pos]
        if byte == ord('<'):
            tag_end = find_tag_end(source, pos)
            if source.startswith(HEADGROUP_OPEN_TAGS, pos):
                inside = True
            elif source.startswith(HEADGROUP_CLOSE_TAGS, pos):
                if out and out[-1] != ' ':
                    out.append(' ')
                inside = False
            pos = tag_end
            continue
        if not inside:
            pos += 1
            continue
        if byte == ord('&'):
            match = ENTITY_REF_RE.match(
                source[pos:].decode('ascii', 'ignore')
            )
            if match is not None:
                token = match.group(0)
                append_entity_preview(out, token, entity_map)
                pos += len(token)
                continue
        if byte == ord("'"):
            out.append('\u2019')
        elif byte in (0x0a, 0x0d, 0x09):
            out.append(' ')
        else:
            out.append(chr(byte) if 32 <= byte < 127 else '.')
        pos += 1
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def render_atoms_preview(atoms: list[RenderAtom]) -> str:
    text = ''.join(atom.preview for atom in atoms)
    return re.sub(r'\s+', ' ', text).strip()


def sgml_entity_refs(data: bytes) -> Counter[str]:
    text = re.sub(rb'<[^>]*>', b'', data)
    rendered = normalized_record_text(text)
    return Counter(ENTITY_REF_RE.findall(rendered))


def parse_nul_fragments(area: bytes) -> list[bytes]:
    fragments: list[bytes] = []
    pos = 0
    while pos < len(area):
        end = area.find(b'\x00', pos)
        if end < 0 or end == pos:
            break
        fragments.append(area[pos:end])
        pos = end + 1
    while len(fragments) < 256:
        fragments.append(b'')
    return fragments[:256]


def parse_lf_markers(area: bytes, count: int) -> list[bytes]:
    markers: list[bytes] = []
    pos = 0
    while pos < len(area) and len(markers) < count:
        end = area.find(b'\x0a', pos)
        if end < 0:
            break
        markers.append(area[pos:end])
        pos = end + 1
    while len(markers) < count:
        markers.append(b'')
    return markers[:count]


def short_profile(buf: bytes) -> tuple[int, int, int, str]:
    printable_count = sum(32 <= b < 127 for b in buf)
    high_count = sum(b >= 0x80 for b in buf)
    zero_count = buf.count(0)
    text = normalize_highbit(buf[:48])
    return printable_count, high_count, zero_count, text


def table_magic(buf: bytes) -> str:
    if buf.startswith(b'\x0f\xfa'):
        return '0ffa'
    if buf.startswith(b'\xfb\x0f'):
        return 'fb0f'
    if len(buf) >= 4 and struct.unpack_from('>I', buf)[0] < 0x100000:
        return 'be-u32-ish'
    return ''


def packed20le_pair(buf: bytes) -> tuple[int, int]:
    if len(buf) != 5:
        raise ValueError('packed20le_pair requires exactly 5 bytes')
    value = int.from_bytes(buf, 'little')
    return value & 0xfffff, value >> 20


def u24le_u16le_record(buf: bytes) -> tuple[int, int]:
    if len(buf) != 5:
        raise ValueError('u24le_u16le_record requires exactly 5 bytes')
    left = buf[0] | (buf[1] << 8) | (buf[2] << 16)
    right = struct.unpack_from('<H', buf, 3)[0]
    return left, right


def monotonic_pair_rate(pairs: list[tuple[int, int]]) -> float:
    if len(pairs) < 2:
        return 0.0
    ordered = sum(pairs[i] >= pairs[i - 1] for i in range(1, len(pairs)))
    return ordered / (len(pairs) - 1)


def sorted_bucket_pair_rate(pairs: list[tuple[int, int]]) -> float:
    """Rate for records sorted by right field, then left field."""
    if len(pairs) < 2:
        return 0.0
    ordered = sum(
        (pairs[i][1], pairs[i][0]) >= (pairs[i - 1][1], pairs[i - 1][0])
        for i in range(1, len(pairs))
    )
    return ordered / (len(pairs) - 1)


def pack_bits(data: bytes, start_bit: int, end_bit: int,
              lsb_first: bool = False) -> bytes:
    out: list[int] = []
    acc = 0
    used = 0
    for bit_pos in range(start_bit, end_bit):
        byte = data[bit_pos // 8]
        if lsb_first:
            bit = (byte >> (bit_pos % 8)) & 1
        else:
            bit = (byte >> (7 - (bit_pos % 8))) & 1
        acc = (acc << 1) | bit
        used += 1
        if used == 8:
            out.append(acc)
            acc = 0
            used = 0
    if used:
        out.append(acc << (8 - used))
    return bytes(out)


def text_score(text: str) -> int:
    return sum(text.count(pattern) * len(pattern)
               for pattern in TEXT_SCORE_PATTERNS)


def body_quality_score(text: str) -> int:
    """Heuristic score for candidate materialized article text."""
    score = text_score(text)
    score += 8 * text.count('<q')
    score += 8 * text.count('</q')
    score += 10 * text.count('<hw')
    score += 6 * text.count('<lc')
    score += 6 * text.count('</lc')
    score += 5 * text.count('<w')
    score += 5 * text.count('</w')
    score += 4 * text.count('<a')
    score += 4 * text.count('</a')
    score += 3 * text.count('&')
    # Penalize common artifacts produced by incorrect recursive copies.
    score -= 10 * text.count('>>')
    score -= 8 * text.count('<<')
    score -= 5 * text.count('><>')
    return score


def base36_value(text: str) -> int | None:
    value = 0
    for ch in text:
        if '0' <= ch <= '9':
            digit = ord(ch) - ord('0')
        elif 'a' <= ch <= 'z':
            digit = ord(ch) - ord('a') + 10
        else:
            return None
        value = value * 36 + digit
    return value


def parse_tablea_text_map(raw: bytes, start: int,
                          limit: int | None = None) -> list['TableAMapRecord']:
    """Parse the printable Table-A text-map run.

    The visible grammar has two forms: simple single-character records
    like ``aA00`` and SGML/entity records like ``&Aacu.A1i``.  The final
    two characters are a base-36-looking rank code; the middle text is
    the normalized collation/display spelling.
    """
    end = len(raw) if limit is None else min(len(raw), start + limit)
    records: list[TableAMapRecord] = []
    pos = start
    while pos < end:
        b = raw[pos]
        if b == 0 or b < 32 or b >= 127:
            break
        rel = pos - start
        if b == ord('&'):
            dot = raw.find(b'.', pos, end)
            if dot < 0:
                break
            name_end = dot + 1
            tail = name_end
            while tail < end and (
                ord('A') <= raw[tail] <= ord('Z')
                or ord('a') <= raw[tail] <= ord('z')
            ):
                tail += 1
            if tail + 2 > end:
                break
            source = raw[pos:name_end].decode('ascii', 'replace')
            normalized = raw[name_end:tail].decode('ascii', 'replace')
            code = raw[tail:tail + 2].decode('ascii', 'replace')
            records.append(TableAMapRecord(
                source, normalized, code, base36_value(code), rel,
            ))
            pos = tail + 2
            continue
        if pos + 4 > end:
            break
        source = chr(raw[pos])
        normalized = chr(raw[pos + 1])
        code = raw[pos + 2:pos + 4].decode('ascii', 'replace')
        records.append(TableAMapRecord(
            source, normalized, code, base36_value(code), rel,
        ))
        pos += 4
    return records


def find_tablea_text_start(raw: bytes) -> int:
    best: tuple[int, int, int] | None = None
    best_offset = 0
    starters = b'&ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    for pos, b in enumerate(raw):
        if b not in starters:
            continue
        records = parse_tablea_text_map(raw, pos, 2048)
        valid = sum(1 for record in records if record.code_value is not None)
        if valid < 8:
            continue
        first_zero = 1 if records[0].code_value == 0 else 0
        score = (first_zero, valid, -pos)
        if best is None or score > best:
            best = score
            best_offset = pos
    return best_offset


@dataclass(frozen=True)
class HeaderEntry:
    index: int
    offset: int

    @property
    def page(self) -> int:
        return self.offset >> 16

    @property
    def page_offset(self) -> int:
        return self.offset & 0xffff


@dataclass(frozen=True)
class BodyBlock:
    index: int
    file_offset: int
    logical_offset: int
    logical_length: int
    stored_length: int
    aux_count: int

    @property
    def payload_offset(self) -> int:
        return self.file_offset + BODY_HEADER_BYTES

    @property
    def payload_end(self) -> int:
        return self.payload_offset + self.stored_length

    @property
    def aux_control_offset(self) -> int:
        return self.payload_end

    @property
    def aux_stream_offset(self) -> int:
        return self.aux_control_offset + 0x80


@dataclass(frozen=True)
class BodyControl:
    offset: int
    magic_or_checksum: int
    stride: int
    block_count: int
    logical_total: int
    logical_block_size: int
    aux_class_count: int
    repeated_stride: int
    tail_or_index_bytes: int
    prefix_word_bytes: int

    @property
    def first_block_offset(self) -> int:
        return self.offset + self.stride

    @property
    def end_offset(self) -> int:
        return self.first_block_offset + self.block_count * self.stride


@dataclass(frozen=True)
class AuxControl:
    code_length_count: int
    length_counts: tuple[int, ...]
    raw_longs: tuple[int, ...]

    @property
    def symbol_count(self) -> int:
        return sum(self.length_counts)

    @property
    def kraft_units(self) -> int:
        # 32-bit fixed point representation of sum(count[len] * 2^-len).
        return sum(
            count * (1 << (32 - bits))
            for bits, count in enumerate(self.length_counts, start=1)
        )


@dataclass(frozen=True)
class AuxStream:
    prefix_values: tuple[int, ...]
    compressed: bytes

    @property
    def prefix_bytes(self) -> int:
        return len(self.prefix_values) * 4


@dataclass(frozen=True)
class BodyRecord:
    logical_offset: int
    block: BodyBlock
    window_index: int
    window_start_logical: int
    bit_start: int
    bit_end: int
    sentinel_symbol: int
    skipped_symbols: int
    fragment_ids: tuple[int, ...]
    data: bytes
    terminated: bool


@dataclass(frozen=True)
class BodyArticle:
    logical_offset: int
    end_logical_offset: int | None
    records: tuple[BodyRecord, ...]
    data: bytes
    stop_reason: str


@dataclass(frozen=True)
class BodySeekState:
    logical_offset: int
    window_index: int
    window_start_logical: int
    window_bit_start: int
    skipped_symbols: int


@dataclass(frozen=True)
class RenderAtom:
    source: str
    out: bytes
    style: bytes
    preview: str

    @property
    def out_hex(self) -> str:
        return self.out.hex(' ') if self.out else '-'

    @property
    def style_hex(self) -> str:
        return self.style.hex(' ') if self.style else '-'


@dataclass(frozen=True)
class OEDListHeader:
    magic: int
    version: int
    block_count: int
    block_size: int
    max_key_bytes: int
    fragment_bytes: int
    marker_bytes: int


@dataclass(frozen=True)
class SparseIndexHeader:
    name: str
    description: str
    offset: int
    magic: int
    block_size: int
    fanout_or_levels: int
    logical_total: int

    @property
    def first_page_offset(self) -> int:
        return self.offset + self.block_size

    @property
    def page_logical_span(self) -> int:
        """Logical range covered by one loaded data page.

        Segment 7 around 0x3cce computes ``(block_size / 2) / fanout``
        using integer division, then shifts left by four.  Adjacent known
        0xffb anchors confirm this derived span.
        """
        words_per_bucket = (self.block_size // 2) // self.fanout_or_levels
        return words_per_bucket << 4

    @property
    def data_page_count(self) -> int:
        span = self.page_logical_span
        if span <= 0:
            return 0
        return (self.logical_total + span - 1) // span

    @property
    def end_offset(self) -> int:
        return self.offset + (self.data_page_count + 1) * self.block_size


@dataclass
class OEDListControl:
    name: str
    description: str
    offset: int
    header: OEDListHeader
    fragments: list[bytes]
    cumulative_deltas: list[int]
    count_base: int
    first_fragment_skip: bytes
    markers: list[bytes]
    path: str

    @property
    def block_data_offset(self) -> int:
        return self.offset + self.header.version * self.header.block_size

    @property
    def block_data_end(self) -> int:
        return self.block_data_offset + (
            self.header.block_count * self.header.block_size
        )

    @property
    def total_entries(self) -> int:
        return sum(self.entries_in_block(i)
                   for i in range(self.header.block_count))

    def start_index_for_block(self, index: int) -> int:
        return sum(self.entries_in_block(i) for i in range(index))

    def entry_counts(self) -> list[int]:
        return [self.entries_in_block(i)
                for i in range(self.header.block_count)]

    def entries_in_block(self, index: int) -> int:
        if index == 0:
            return self.cumulative_deltas[0]
        return (
            self.cumulative_deltas[index]
            - self.cumulative_deltas[index - 1]
            + self.count_base
        )

    def decode_block(self, index: int, limit: int | None = None) -> list[bytes]:
        if not 0 <= index < self.header.block_count:
            raise IndexError(index)
        count = self.entries_in_block(index)
        if count < 0:
            raise ValueError(f'negative entry count in block {index}: {count}')
        if limit is not None:
            count = min(count, limit)

        base = self.block_data_offset + index * self.header.block_size
        with open(self.path, 'rb') as f:
            f.seek(base)
            block = f.read(self.header.block_size)
        if len(block) != self.header.block_size:
            raise ValueError(f'short list block at 0x{base:x}')

        full_count = self.entries_in_block(index)
        nibble_bytes = (full_count + 1) // 2
        frag_ptr = nibble_bytes
        if frag_ptr >= len(block):
            return []

        cur_frag = self.fragments[block[frag_ptr]]
        frag_ptr += 1
        cur_pos = self.first_fragment_skip[index]
        prev = bytearray(self.markers[index])
        words: list[bytes] = []

        for i in range(count):
            shared_byte = block[i >> 1]
            shared = (shared_byte >> 4) if (i & 1) == 0 else (shared_byte & 0x0f)
            cur = bytearray(prev[:shared])
            while True:
                while cur_pos >= len(cur_frag):
                    if frag_ptr >= len(block):
                        words.append(bytes(cur))
                        return words
                    cur_frag = self.fragments[block[frag_ptr]]
                    frag_ptr += 1
                    cur_pos = 0
                b = cur_frag[cur_pos]
                cur_pos += 1
                if b == 0x0a:
                    break
                cur.append(b)
            words.append(bytes(cur))
            prev = cur
        return words


@dataclass(frozen=True)
class OEDListLookupResult:
    key: bytes
    marker_block: int
    index: int | None
    entry: bytes | None
    blocks_read: int
    entries_scanned: int
    reason: str


def oedlist_marker_block(control: OEDListControl, key: bytes) -> int:
    """Block choice from OED.EXE seg5:53bc."""
    lo = 0
    hi = control.header.block_count - 1
    selected = 0
    while hi > selected:
        mid = (selected + hi + 1) // 2
        marker = control.markers[mid]
        if key == marker:
            hi = mid
            selected = mid
        elif key < marker:
            hi = mid - 1
        else:
            selected = mid
    return selected


def oedlist_original_lookup(control: OEDListControl, key: bytes,
                            scan_limit: int | None = None,
                            require_exact: bool = True) -> OEDListLookupResult:
    """Exact lookup shape from seg5:528c/53bc/54ee.

    This intentionally uses the original marker guide and forward scan,
    rather than a Python-wide binary search over decoded entries.
    """
    block_index = oedlist_marker_block(control, key)
    blocks_read = 0
    entries_scanned = 0
    global_start = control.start_index_for_block(block_index)
    key_len = len(key)

    while block_index < control.header.block_count:
        entries = control.decode_block(block_index)
        blocks_read += 1
        for local_index, entry in enumerate(entries):
            if scan_limit is not None and entries_scanned >= scan_limit:
                return OEDListLookupResult(
                    key, oedlist_marker_block(control, key), None, None,
                    blocks_read, entries_scanned, 'scan-limit',
                )
            entries_scanned += 1
            if len(entry) >= key_len and entry[:key_len] == key:
                index = global_start + local_index
                if entry == key:
                    return OEDListLookupResult(
                        key, oedlist_marker_block(control, key), index, entry,
                        blocks_read, entries_scanned, 'exact',
                    )
                if not require_exact:
                    return OEDListLookupResult(
                        key, oedlist_marker_block(control, key), index, entry,
                        blocks_read, entries_scanned, 'prefix',
                    )
                return OEDListLookupResult(
                    key, oedlist_marker_block(control, key), None, entry,
                    blocks_read, entries_scanned, 'prefix-only',
                )
        block_index += 1
        global_start += len(entries)

    return OEDListLookupResult(
        key, oedlist_marker_block(control, key), None, None,
        blocks_read, entries_scanned, 'eof',
    )


@dataclass(frozen=True)
class TableAMapRecord:
    source: str
    normalized: str
    code_text: str
    code_value: int | None
    offset: int


@dataclass(frozen=True)
class TableAStructRecord:
    index: int
    source: bytes
    primary: bytes
    secondary: bytes
    offsets: tuple[int, int, int, int]


@dataclass(frozen=True)
class TableAStruct:
    header: tuple[int, int, int, int]
    offsets: tuple[int, ...]
    index_map: tuple[int, ...]
    pool: bytes

    @property
    def record_count(self) -> int:
        return self.header[0]

    @property
    def entity_count(self) -> int:
        return self.header[1]

    def record(self, index: int) -> TableAStructRecord:
        if not 0 <= index < self.record_count:
            raise IndexError(index)
        pos = index * 3
        a, b, c, d = self.offsets[pos:pos + 4]
        return TableAStructRecord(
            index=index,
            source=self.pool[a:b],
            primary=self.pool[b:c],
            secondary=self.pool[c:d],
            offsets=(a, b, c, d),
        )

    def direct_record_index(self, byte: int) -> int | None:
        if not 0 <= byte < 0x100:
            raise ValueError(byte)
        value = self.index_map[byte]
        return None if value == 0xffff else value

    def direct_record(self, byte: int) -> TableAStructRecord | None:
        index = self.direct_record_index(byte)
        return None if index is None else self.record(index)

    def find_entity_record_index(self, token: bytes) -> int | None:
        """Mirror the EXE's entity-name binary search.

        ``seg5:4688`` searches the index-map window beginning at 0x100.
        Each entry points to a record whose source slice is compared with
        the input through the terminating dot.
        """
        lo = 0x100
        hi = 0x100 + self.entity_count
        while lo < hi:
            mid = (lo + hi) // 2
            record_index = self.index_map[mid]
            record = self.record(record_index)
            cmp = compare_entity_token(token, record.source)
            if cmp < 0:
                hi = mid
            elif cmp > 0:
                lo = mid + 1
            else:
                return record_index
        return None

    def find_source_record_index(self, token: bytes) -> int | None:
        if token.startswith(b'&'):
            return self.find_entity_record_index(token)
        if len(token) == 1:
            return self.direct_record_index(token[0])
        for index in range(self.record_count):
            if self.record(index).source == token:
                return index
        return None


def parse_tablea_struct(raw: bytes) -> TableAStruct:
    if len(raw) < 8:
        raise ValueError('short Table-A data')
    header = struct.unpack_from('>4H', raw, 0)
    record_count, entity_count, offset_count, pool_size = header
    if offset_count != record_count * 3:
        raise ValueError(
            f'unexpected Table-A offset count {offset_count}; '
            f'wanted {record_count * 3}'
        )
    pos = 8
    offsets_end = pos + (offset_count + 1) * 2
    index_count = entity_count + 0x100
    index_end = offsets_end + index_count * 2
    pool_end = index_end + pool_size
    if len(raw) < pool_end:
        raise ValueError(
            f'short Table-A data: need 0x{pool_end:x}, got 0x{len(raw):x}'
        )
    offsets = struct.unpack_from(f'>{offset_count + 1}H', raw, pos)
    index_map = struct.unpack_from(f'>{index_count}H', raw, offsets_end)
    pool = raw[index_end:pool_end]
    if not 0 <= offsets[-1] <= pool_size:
        raise ValueError(
            f'Table-A pool sentinel is {offsets[-1]}, outside pool {pool_size}'
        )
    return TableAStruct(
        header=header,
        offsets=offsets,
        index_map=index_map,
        pool=pool,
    )


def compare_entity_token(left: bytes, right: bytes) -> int:
    """Compare entity names the way ``seg5:45fc`` does.

    The routine walks byte-for-byte and stops with equality only after a
    matching dot.  Otherwise it returns the unsigned byte difference at
    the first mismatch.
    """
    pos = 0
    while True:
        lb = left[pos] if pos < len(left) else 0
        rb = right[pos] if pos < len(right) else 0
        if lb != rb:
            return lb - rb
        if lb == ord('.'):
            return 0
        pos += 1


def tablea_rank_value(text: bytes) -> int | None:
    if len(text) != 2:
        return None
    value = 0
    for b in text:
        if ord('0') <= b <= ord('9'):
            digit = b - ord('0')
        elif ord('a') <= b <= ord('z'):
            digit = b - ord('a') + 10
        else:
            return None
        value = value * 36 + digit
    return value


def tablea_rank_code_value(first: int, second: int) -> int:
    """Inverse of the EXE's two-byte rank code reader at seg5:463e."""
    def one(byte: int) -> int:
        cls = tablea_exe_char_class(byte)
        return byte - 0x57 if cls & 0x02 else byte - 0x30

    return 36 * one(first) + one(second)


def tablea_exe_char_class(byte: int) -> int:
    """Bits from OED.EXE data table 0x7395 needed by seg5:4688."""
    if ord('A') <= byte <= ord('Z'):
        return 0x01
    if ord('a') <= byte <= ord('z'):
        return 0x02
    if ord('0') <= byte <= ord('9'):
        return 0x84
    if byte in b'\t\n\r()':
        return 0x28
    if byte == ord(' '):
        return 0x48
    if 0x20 <= byte < 0x7f:
        return 0x10
    return 0x00


def tablea_copy_primary(table: TableAStruct, record_index: int,
                        out: bytearray) -> None:
    record = table.record(record_index)
    out.extend(record.primary)


def tablea_copy_secondary(table: TableAStruct, record_index: int,
                          out: bytearray) -> None:
    record = table.record(record_index)
    out.extend(record.secondary)


def tablea_find_entity_and_dot(table: TableAStruct, data: bytes,
                               pos: int) -> tuple[int | None, int]:
    dot = data.find(b'.', pos + 1)
    if dot < 0:
        return None, len(data)
    return table.find_entity_record_index(data[pos:dot + 1]), dot


def encode_tablea_exe(table: TableAStruct, text: str,
                      mode: int = 0x0100, mode_hi: int = 0) -> bytes:
    """Encode a query with the OED.EXE seg5:4688 control flow.

    The word-list mode treats the first two bytes as a POS/list prefix and
    appends them to the secondary stream before processing the visible text.
    """
    data = text.encode('latin-1', 'replace')
    primary = bytearray()
    secondary = bytearray()
    pos = 0
    lower_marker = 0x03
    upper_marker = 0x02

    if mode == 0x0100 and mode_hi == 0 and data:
        secondary.append(data[0])
        pos = 1
        if pos < len(data):
            secondary.append(data[pos])
            pos += 1

    while pos < len(data) and data[pos] != 0:
        b = data[pos]

        # The branch at 0x4750 handles tag-like text by adding only
        # secondary weights until NUL.  It matters for phrase/Greek probes.
        if b in (ord('('), ord('<')):
            balanced_paren = False
            if b == ord('('):
                close = data.find(b')', pos + 1)
                balanced_paren = close >= 0
            if not balanced_paren:
                while pos < len(data) and data[pos] != 0:
                    b = data[pos]
                    record_index: int | None
                    if b == ord('&'):
                        record_index, dot = tablea_find_entity_and_dot(
                            table, data, pos,
                        )
                        pos = dot
                    else:
                        record_index = table.direct_record_index(b)
                    if record_index is not None:
                        tablea_copy_secondary(table, record_index, secondary)
                    if pos >= len(data) or data[pos] == 0:
                        break
                    pos += 1
                continue

        if b == ord('&'):
            record_index, dot = tablea_find_entity_and_dot(table, data, pos)
            pos = dot
            if record_index is not None:
                tablea_copy_primary(table, record_index, primary)
                tablea_copy_secondary(table, record_index, secondary)
            if pos >= len(data) or data[pos] == 0:
                continue
            pos += 1
            continue

        cls = tablea_exe_char_class(b)
        if (cls & 0x03) and not (mode in (0x0103, 0x0104) and mode_hi == 0):
            if cls & 0x01:
                primary.append(b)
                secondary.append(upper_marker)
            else:
                primary.append((b - 0x20) & 0xff)
                secondary.append(lower_marker)
            pos += 1
            continue

        record_index = table.direct_record_index(b)
        if record_index is not None:
            tablea_copy_primary(table, record_index, primary)
            tablea_copy_secondary(table, record_index, secondary)
        pos += 1

    primary.append(lower_marker)
    primary.extend(secondary)
    return bytes(primary)


def tablea_primary_prefix(encoded: bytes) -> bytes:
    """Return the primary bytes copied by the word lookup at seg3:3737."""
    out = bytearray()
    for b in encoded:
        if b <= 0x03:
            break
        out.append(b)
    return bytes(out)


def decode_tablea_exe(table: TableAStruct, encoded: bytes,
                      mode: int = 0x0100, mode_hi: int = 0) -> bytes:
    """Expand a Table-A encoded key using the OED.EXE seg5:4c40 shape.

    Word-list keys keep a two-byte hidden class/POS prefix immediately after
    the primary separator.  The remaining secondary stream says whether each
    primary byte should be lowercased, kept uppercase, or expanded through a
    Table-A record.
    """
    separator = 0x03
    upper_marker = 0x02
    split = encoded.find(bytes([separator]))
    if split < 0:
        return encoded.rstrip(b'\x00')

    primary_pos = 0
    secondary_pos = split
    out = bytearray()

    if mode == 0x0100 and mode_hi == 0:
        if secondary_pos + 1 < len(encoded):
            out.append(encoded[secondary_pos + 1])
        if secondary_pos + 2 < len(encoded):
            out.append(encoded[secondary_pos + 2])
        secondary_pos += 2

    while secondary_pos < len(encoded) and encoded[secondary_pos] != 0:
        secondary_pos += 1
        if secondary_pos >= len(encoded):
            break
        marker = encoded[secondary_pos]

        if marker in (separator, 0):
            if primary_pos < split:
                out.append((encoded[primary_pos] + 0x20) & 0xff)
                primary_pos += 1
            if marker == 0:
                break
            continue

        if marker == upper_marker:
            if primary_pos < split:
                out.append(encoded[primary_pos])
                primary_pos += 1
            continue

        if secondary_pos + 1 >= len(encoded):
            break
        record_index = tablea_rank_code_value(
            encoded[secondary_pos], encoded[secondary_pos + 1],
        )
        secondary_pos += 1
        if 0 <= record_index < table.record_count:
            record = table.record(record_index)
            out.extend(record.source)
            primary_pos = min(split, primary_pos + len(record.primary))

    if primary_pos < split:
        out.extend(encoded[primary_pos:split])
    return bytes(out)


def encode_tablea_simple(table: TableAStruct, text: str) -> bytes:
    """Encode through Table-A records without the EXE's mode quirks.

    This intentionally mirrors the core record copy in ``seg5:4688``:
    source bytes append their primary slice to the first stream and
    their secondary slice to the second stream.  The mode-specific
    first-two-byte handling and case branches are still being decoded,
    so this command is a structural probe rather than the final lookup
    encoder.
    """
    data = text.encode('latin-1', 'replace')
    primary = bytearray()
    secondary = bytearray()
    pos = 0
    while pos < len(data):
        b = data[pos]
        record_index: int | None
        if b == ord('&'):
            dot = data.find(b'.', pos + 1)
            if dot < 0:
                record_index = None
                pos += 1
            else:
                token = data[pos:dot + 1]
                record_index = table.find_entity_record_index(token)
                pos = dot + 1
        else:
            record_index = table.direct_record_index(b)
            pos += 1
        if record_index is None:
            continue
        record = table.record(record_index)
        primary.extend(record.primary)
        secondary.extend(record.secondary)
    primary.append(0x03)
    primary.extend(secondary)
    primary.append(0x00)
    return bytes(primary)


class OED2Reader:
    def __init__(self, path: str):
        self.path = path
        self.size = os.path.getsize(path)
        self._blocks: list[BodyBlock] | None = None

    def header_entries(self) -> list[HeaderEntry]:
        with open(self.path, 'rb') as f:
            blob = f.read(HEADER_BYTES)
        if len(blob) != HEADER_BYTES:
            raise ValueError('file too small for OED2 header')
        return [
            HeaderEntry(i, struct.unpack_from('<I', blob, i * 4)[0])
            for i in range(HEADER_LONGS)
        ]

    def body_blocks(self) -> list[BodyBlock]:
        if self._blocks is None:
            self._blocks = list(self._scan_body_blocks())
        return self._blocks

    def read_body_control(self) -> BodyControl:
        with open(self.path, 'rb') as f:
            f.seek(BODY_CONTROL_OFFSET)
            raw = f.read(BODY_CONTROL_WORDS * 4)
        if len(raw) != BODY_CONTROL_WORDS * 4:
            raise ValueError('short body control header')
        words = struct.unpack(f'>{BODY_CONTROL_WORDS}I', raw)
        return BodyControl(BODY_CONTROL_OFFSET, *words)

    def _scan_body_blocks(self) -> Iterator[BodyBlock]:
        try:
            control = self.read_body_control()
        except ValueError:
            control = None
        if (
            control is not None
            and control.stride == BODY_BLOCK_STRIDE
            and control.repeated_stride == BODY_BLOCK_STRIDE
            and control.aux_class_count == BODY_AUX_PREFIX_WORDS
        ):
            yield from self._scan_body_blocks_from_control(control)
            return

        first = self._first_body_candidate()
        idx = 0
        with open(self.path, 'rb') as f:
            for off in range(first, self.size - BODY_HEADER_BYTES,
                             BODY_BLOCK_STRIDE):
                f.seek(off)
                h = f.read(BODY_HEADER_BYTES)
                if len(h) != BODY_HEADER_BYTES:
                    break
                logical, length, stored, aux = struct.unpack('>IIII', h)
                if not self._looks_like_body_header(length, stored, aux):
                    continue
                if off + BODY_HEADER_BYTES + stored > self.size:
                    continue
                yield BodyBlock(idx, off, logical, length, stored, aux)
                idx += 1

    def _scan_body_blocks_from_control(self,
                                       control: BodyControl) -> Iterator[BodyBlock]:
        with open(self.path, 'rb') as f:
            for idx in range(control.block_count):
                off = control.first_block_offset + idx * control.stride
                f.seek(off)
                h = f.read(BODY_HEADER_BYTES)
                if len(h) != BODY_HEADER_BYTES:
                    break
                logical, length, stored, aux = struct.unpack('>IIII', h)
                if (
                    length <= 0
                    or stored <= 0
                    or stored >= control.stride - BODY_HEADER_BYTES
                    or aux <= 0
                    or aux >= control.stride
                ):
                    raise ValueError(
                        f'bad body block header at 0x{off:x}: '
                        f'logical=0x{logical:x} length=0x{length:x} '
                        f'stored=0x{stored:x} aux=0x{aux:x}'
                    )
                yield BodyBlock(idx, off, logical, length, stored, aux)

    def _first_body_candidate(self) -> int:
        base = ((SECTION_D_START + BODY_BLOCK_STRIDE - 1)
                // BODY_BLOCK_STRIDE * BODY_BLOCK_STRIDE)
        residue = base % BODY_BLOCK_STRIDE
        if residue <= BODY_BLOCK_RESIDUE:
            return base + (BODY_BLOCK_RESIDUE - residue)
        return base + (BODY_BLOCK_STRIDE - residue) + BODY_BLOCK_RESIDUE

    @staticmethod
    def _looks_like_body_header(length: int, stored: int, aux: int) -> bool:
        return (
            BODY_LEN_MIN <= length <= BODY_LEN_MAX
            and 0 < stored < BODY_BLOCK_STRIDE - BODY_HEADER_BYTES
            and BODY_AUX_MIN <= aux <= BODY_AUX_MAX
        )

    def block_for_logical_offset(self, logical_offset: int) -> BodyBlock:
        blocks = self.body_blocks()
        starts = [b.logical_offset for b in blocks]
        i = bisect.bisect_right(starts, logical_offset) - 1
        if i < 0:
            raise ValueError(f'logical offset 0x{logical_offset:x} '
                             'is before the first body block')
        block = blocks[i]
        if logical_offset >= block.logical_offset + block.logical_length:
            raise ValueError(f'logical offset 0x{logical_offset:x} '
                             'falls between body blocks')
        return block

    def body_logical_range(self) -> tuple[int, int]:
        blocks = self.body_blocks()
        if not blocks:
            raise ValueError('no body blocks found')
        first = blocks[0]
        last = blocks[-1]
        return first.logical_offset, last.logical_offset + last.logical_length

    def read_payload(self, block: BodyBlock) -> bytes:
        with open(self.path, 'rb') as f:
            f.seek(block.payload_offset)
            return f.read(block.stored_length)

    def read_aux_control(self, block: BodyBlock) -> AuxControl:
        with open(self.path, 'rb') as f:
            f.seek(block.aux_control_offset)
            data = f.read(0x80)
        if len(data) != 0x80:
            raise ValueError('short aux control block')
        longs = tuple(struct.unpack('>32I', data))
        n = longs[0]
        if n > 31:
            raise ValueError(f'implausible aux code-length count: {n}')
        return AuxControl(n, tuple(longs[1:1 + n]), longs)

    def read_aux_stream_raw(self, block: BodyBlock) -> bytes:
        with open(self.path, 'rb') as f:
            f.seek(block.aux_stream_offset)
            return f.read(block.file_offset + BODY_BLOCK_STRIDE
                          - block.aux_stream_offset)

    def read_aux_stream(self, block: BodyBlock) -> AuxStream:
        raw = self.read_aux_stream_raw(block)
        # The original reader treats this as a fixed 64-entry table of
        # bit offsets into the following canonical-Huffman stream.  The
        # entries are selected by logical-window number, not by payload
        # byte class.
        prefix_words = min(BODY_AUX_PREFIX_WORDS, len(raw) // 4)
        prefix = tuple(
            struct.unpack_from('>I', raw, i * 4)[0]
            for i in range(prefix_words)
        )
        return AuxStream(prefix, raw[prefix_words * 4:])

    def body_fragment_table(self, block: BodyBlock) -> tuple[bytes, list[int]]:
        """Return payload with marker bits cleared plus fragment end offsets.

        Segment 5's loader scans the stored payload, clears bit 7 on every
        marker byte in-place, and records the offset immediately after each
        marker.  Fragment id N copies bytes offsets[N]:offsets[N + 1].
        """
        payload = bytearray(self.read_payload(block))
        offsets = [0]
        for pos, byte in enumerate(payload):
            if byte >= 0x80:
                payload[pos] = byte & 0x7f
                offsets.append(pos + 1)
        return bytes(payload), offsets

    def body_window_span(self, block: BodyBlock) -> int:
        control = self.read_body_control()
        return (
            block.logical_length + control.aux_class_count - 1
        ) // control.aux_class_count

    def body_block_decoder(self, block: BodyBlock) -> BodyBlockDecoder:
        return BodyBlockDecoder(self, block)

    def decode_body_record(self, logical_offset: int,
                           max_fragments: int = 8192) -> BodyRecord:
        """Materialize one body record using the OED.EXE segment-5 algorithm."""
        block = self.block_for_logical_offset(logical_offset)
        decoder = self.body_block_decoder(block)
        decoder.seek(logical_offset)
        return decoder.next_record(max_fragments=max_fragments)

    def iter_body_records(self, logical_offset: int,
                          max_fragments: int = 8192
                          ) -> Iterator[BodyRecord]:
        blocks = self.body_blocks()
        starts = [b.logical_offset for b in blocks]
        block_index = bisect.bisect_right(starts, logical_offset) - 1
        if block_index < 0:
            raise ValueError(f'logical offset 0x{logical_offset:x} '
                             'is before the first body block')
        current = logical_offset
        while block_index < len(blocks):
            block = blocks[block_index]
            block_end = block.logical_offset + block.logical_length
            if current < block.logical_offset:
                current = block.logical_offset
            if current >= block_end:
                block_index += 1
                continue
            decoder = self.body_block_decoder(block)
            decoder.seek(current)
            while current < block_end:
                record = decoder.next_record(max_fragments=max_fragments)
                yield record
                current += 1
                if not record.terminated:
                    return
            block_index += 1

    def decode_body_article(self, logical_offset: int,
                            max_records: int = 5000,
                            max_fragments: int = 8192) -> BodyArticle:
        records: list[BodyRecord] = []
        pieces: list[bytes] = []
        body_lo, body_hi = self.body_logical_range()
        current = logical_offset
        stop_reason = 'max-records'
        end_logical: int | None = None

        if not body_lo <= current < body_hi:
            raise ValueError(f'logical offset 0x{logical_offset:x} '
                             'is outside the body stream')

        for record in self.iter_body_records(current,
                                             max_fragments=max_fragments):
            if len(records) >= max_records:
                break
            if records and is_entry_start_record(record.data):
                stop_reason = 'next-entry'
                end_logical = record.logical_offset
                break
            records.append(record)
            pieces.append(record.data)
            if not record.terminated:
                stop_reason = 'unterminated-record'
                end_logical = record.logical_offset
                break
            current = record.logical_offset + 1
            if current >= body_hi:
                stop_reason = 'end-of-body'
                end_logical = body_hi
                break

        return BodyArticle(
            logical_offset=logical_offset,
            end_logical_offset=end_logical,
            records=tuple(records),
            data=b''.join(pieces),
            stop_reason=stop_reason,
        )

    def find_body_entry_start(self, logical_offset: int,
                              search_back: int = 12000) -> int:
        body_lo, _body_hi = self.body_logical_range()
        stop = max(body_lo, logical_offset - search_back)
        latest: int | None = None
        for record in self.iter_body_records(stop):
            if is_entry_start_record(record.data):
                latest = record.logical_offset
            if record.logical_offset >= logical_offset:
                break
        if latest is not None:
            return latest
        raise ValueError(
            f'no enclosing <e> record found within {search_back} records '
            f'before 0x{logical_offset:x}'
        )

    def decode_aux_symbols(self, block: BodyBlock,
                           limit: int | None = None,
                           consume: str = 'forward') -> list[int]:
        """Legacy probe for the rejected byte-class aux interpretation.

        The executable-derived decoder is :meth:`decode_body_record`.
        This method remains only so older exploratory commands still run.
        """
        if consume not in ('forward', 'reverse'):
            raise ValueError(f'unknown aux consume order: {consume}')
        payload = self.read_payload(block)
        high_bytes = [b for b in payload if b >= 0x80]
        wanted = len(high_bytes) if limit is None else min(limit,
                                                           len(high_bytes))
        group_counts = Counter(b & 0x3f for b in high_bytes)
        control = self.read_aux_control(block)
        stream = self.read_aux_stream(block)
        streams: dict[int, deque[int]] = {}
        for group, count in group_counts.items():
            streams[group] = deque(decode_canonical_symbols_from_bit(
                stream.compressed,
                control.length_counts,
                stream.prefix_values[group],
                count,
            ))
            if consume == 'reverse':
                streams[group] = deque(reversed(streams[group]))

        out: list[int] = []
        for b in high_bytes:
            group = b & 0x3f
            if not streams[group]:
                break
            out.append(streams[group].popleft())
            if len(out) >= wanted:
                break
        return out

    def read_at_file_offset(self, offset: int, size: int) -> bytes:
        with open(self.path, 'rb') as f:
            f.seek(offset)
            return f.read(size)

    def read_oed_list(self, name: str) -> OEDListControl:
        if name not in OED_LISTS:
            known = ', '.join(sorted(OED_LISTS))
            raise ValueError(f'unknown OED list {name!r}; known: {known}')
        offset, description = OED_LISTS[name]
        with open(self.path, 'rb') as f:
            f.seek(offset)
            header_raw = f.read(14)
            if len(header_raw) != 14:
                raise ValueError(f'short OED list header at 0x{offset:x}')
            header = OEDListHeader(*struct.unpack('>7H', header_raw))
            if header.magic != 0x0FFA:
                raise ValueError(
                    f'bad OED list magic at 0x{offset:x}: 0x{header.magic:04x}'
                )

            f.seek(offset + 14)
            fragment_area = f.read(header.fragment_bytes)
            fragments = parse_nul_fragments(fragment_area)

            extra_raw = f.read(4)
            if len(extra_raw) != 4:
                raise ValueError(f'short OED list extra table at 0x{offset:x}')
            count_base = struct.unpack('>I', extra_raw)[0]
            cumulative_deltas = [
                struct.unpack('>i', f.read(4))[0]
                for _ in range(header.block_count)
            ]
            first_fragment_skip = f.read(header.block_count)
            marker_area = f.read(header.marker_bytes)
            markers = parse_lf_markers(marker_area, header.block_count)

        return OEDListControl(
            name=name,
            description=description,
            offset=offset,
            header=header,
            fragments=fragments,
            cumulative_deltas=cumulative_deltas,
            count_base=count_base,
            first_fragment_skip=first_fragment_skip,
            markers=markers,
            path=self.path,
        )

    def read_oed_pointer_records(self, name: str, start: int,
                                 count: int) -> list[tuple[int, int]]:
        if name not in OED_LIST_TABLES:
            known = ', '.join(sorted(OED_LIST_TABLES))
            raise ValueError(f'unknown OED list table {name!r}; known: {known}')
        _table_a, table_b = OED_LIST_TABLES[name]
        if table_b is None:
            raise ValueError(f'no table-B pointer anchor recorded for {name!r}')
        with open(self.path, 'rb') as f:
            f.seek(table_b + start * 8)
            raw = f.read(count * 8)
        out: list[tuple[int, int]] = []
        for pos in range(0, len(raw) - 7, 8):
            out.append(struct.unpack_from('>II', raw, pos))
        return out

    def read_sparse_header(self, name: str) -> SparseIndexHeader:
        if name not in OED_SPARSE_INDEXES:
            known = ', '.join(sorted(OED_SPARSE_INDEXES))
            raise ValueError(f'unknown sparse index {name!r}; known: {known}')
        offset, description = OED_SPARSE_INDEXES[name]
        raw = self.read_at_file_offset(offset, 10)
        if len(raw) != 10:
            raise ValueError(f'short sparse header at 0x{offset:x}')
        magic, block_size, fanout, logical_total = struct.unpack('<HHHI', raw)
        if magic != 0x0FFB:
            raise ValueError(
                f'bad sparse magic at 0x{offset:x}: 0x{magic:04x}'
            )
        return SparseIndexHeader(
            name, description, offset, magic, block_size, fanout, logical_total,
        )

    def iter_payload_hits(self, needle: bytes) -> Iterable[tuple[BodyBlock, int]]:
        for block in self.body_blocks():
            payload = self.read_payload(block)
            pos = 0
            while True:
                hit = payload.find(needle, pos)
                if hit < 0:
                    break
                yield block, hit
                pos = hit + 1

    def tag_counts(self, limit: int = 30) -> list[tuple[bytes, int]]:
        counts: dict[bytes, int] = {}
        for block in self.body_blocks():
            payload = self.read_payload(block)
            for m in TAG_RE.finditer(payload):
                tag = m.group(0)
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def build_canonical_decode_table(length_counts: tuple[int, ...]
                                 ) -> dict[tuple[int, int], int]:
    code = 0
    symbol = 0
    out: dict[tuple[int, int], int] = {}
    for bits, count in enumerate(length_counts, start=1):
        for _ in range(count):
            out[(bits, code)] = symbol
            symbol += 1
            code += 1
        code <<= 1
    return out


def decode_canonical_symbols(data: bytes, length_counts: tuple[int, ...],
                             limit: int) -> list[int]:
    return decode_canonical_symbols_from_bit(data, length_counts, 0, limit)


def decode_canonical_symbols_from_bit(data: bytes,
                                      length_counts: tuple[int, ...],
                                      bit_offset: int,
                                      limit: int) -> list[int]:
    table = build_canonical_decode_table(length_counts)
    out: list[int] = []
    acc = 0
    bits = 0
    for bit_pos in range(bit_offset, len(data) * 8):
        byte = data[bit_pos // 8]
        shift = 7 - (bit_pos % 8)
        acc = (acc << 1) | ((byte >> shift) & 1)
        bits += 1
        symbol = table.get((bits, acc))
        if symbol is not None:
            out.append(symbol)
            acc = 0
            bits = 0
            if len(out) >= limit:
                return out
    return out


class CanonicalBitDecoder:
    def __init__(self, data: bytes, length_counts: tuple[int, ...],
                 bit_offset: int = 0, end_bit: int | None = None):
        self.data = data
        self.table = build_canonical_decode_table(length_counts)
        self.max_bits = len(length_counts)
        self.bit_offset = bit_offset
        self.end_bit = len(data) * 8 if end_bit is None else min(end_bit,
                                                                  len(data) * 8)

    def seek(self, bit_offset: int) -> None:
        if bit_offset < 0 or bit_offset > self.end_bit:
            raise ValueError(f'bit offset out of range: {bit_offset}')
        self.bit_offset = bit_offset

    def next_symbol(self) -> int:
        acc = 0
        for bits in range(1, self.max_bits + 1):
            if self.bit_offset >= self.end_bit:
                return -1
            byte = self.data[self.bit_offset // 8]
            shift = 7 - (self.bit_offset % 8)
            acc = (acc << 1) | ((byte >> shift) & 1)
            self.bit_offset += 1
            symbol = self.table.get((bits, acc))
            if symbol is not None:
                return symbol
        return -1


class BodyBlockDecoder:
    def __init__(self, reader: OED2Reader, block: BodyBlock):
        self.block = block
        self.payload, self.fragment_offsets = reader.body_fragment_table(block)
        if len(self.fragment_offsets) - 1 != block.aux_count:
            raise ValueError(
                f'block {block.index} marker count mismatch: '
                f'{len(self.fragment_offsets) - 1} != {block.aux_count}'
            )
        aux_control = reader.read_aux_control(block)
        aux_stream = reader.read_aux_stream(block)
        self.prefix_values = aux_stream.prefix_values
        self.decoder = CanonicalBitDecoder(
            aux_stream.compressed, aux_control.length_counts,
        )
        self.sentinel_symbol = self.decoder.next_symbol()
        if self.sentinel_symbol < 0:
            raise ValueError(f'block {block.index} has no delimiter symbol')
        self.window_span = reader.body_window_span(block)
        self.seek_state: BodySeekState | None = None
        self.current_logical = block.logical_offset
        self.symbols_since_window_start = 0

    def seek(self, logical_offset: int) -> BodySeekState:
        if not (
            self.block.logical_offset
            <= logical_offset
            < self.block.logical_offset + self.block.logical_length
        ):
            raise ValueError(
                f'logical offset 0x{logical_offset:x} is outside block '
                f'{self.block.index}'
            )
        rel = logical_offset - self.block.logical_offset
        window = rel // self.window_span
        if window >= len(self.prefix_values):
            raise ValueError(
                f'logical offset 0x{logical_offset:x} selects window {window}, '
                f'but block has {len(self.prefix_values)} prefixes'
            )
        bit_start = self.prefix_values[window]
        self.decoder.seek(bit_start)
        window_start = self.block.logical_offset + window * self.window_span
        current = window_start
        skipped = 0
        while current < logical_offset:
            symbol = self.decoder.next_symbol()
            if symbol < 0:
                raise ValueError(
                    f'ran out of aux symbols before logical '
                    f'0x{logical_offset:x}'
                )
            skipped += 1
            if symbol == self.sentinel_symbol:
                current += 1

        state = BodySeekState(
            logical_offset=logical_offset,
            window_index=window,
            window_start_logical=window_start,
            window_bit_start=bit_start,
            skipped_symbols=skipped,
        )
        self.seek_state = state
        self.current_logical = logical_offset
        self.symbols_since_window_start = skipped
        return state

    def next_record(self, max_fragments: int = 8192) -> BodyRecord:
        if self.seek_state is None:
            self.seek(self.block.logical_offset)
        assert self.seek_state is not None
        window = (
            self.current_logical - self.block.logical_offset
        ) // self.window_span
        if window != self.seek_state.window_index:
            window_start = self.block.logical_offset + window * self.window_span
            bit_start = self.prefix_values[window]
            if self.decoder.bit_offset != bit_start:
                raise ValueError(
                    f'block {self.block.index} sequential bit offset '
                    f'{self.decoder.bit_offset} does not match prefix '
                    f'{bit_start} for window {window}'
                )
            self.seek_state = BodySeekState(
                logical_offset=self.current_logical,
                window_index=window,
                window_start_logical=window_start,
                window_bit_start=bit_start,
                skipped_symbols=0,
            )
            self.symbols_since_window_start = 0
        state = self.seek_state
        skipped = self.symbols_since_window_start
        out = bytearray()
        fragment_ids: list[int] = []
        terminated = False
        for _ in range(max_fragments):
            symbol = self.decoder.next_symbol()
            if symbol < 0:
                break
            self.symbols_since_window_start += 1
            if symbol == self.sentinel_symbol:
                terminated = True
                break
            if not 0 <= symbol < len(self.fragment_offsets) - 1:
                raise ValueError(
                    f'block {self.block.index} decoded invalid fragment id '
                    f'{symbol}; valid range is 0..{len(self.fragment_offsets) - 2}'
                )
            lo = self.fragment_offsets[symbol]
            hi = self.fragment_offsets[symbol + 1]
            out.extend(self.payload[lo:hi])
            fragment_ids.append(symbol)

        record = BodyRecord(
            logical_offset=self.current_logical,
            block=self.block,
            window_index=state.window_index,
            window_start_logical=state.window_start_logical,
            bit_start=state.window_bit_start,
            bit_end=self.decoder.bit_offset,
            sentinel_symbol=self.sentinel_symbol,
            skipped_symbols=skipped,
            fragment_ids=tuple(fragment_ids),
            data=bytes(out),
            terminated=terminated,
        )
        self.current_logical += 1
        return record


def command_info(reader: OED2Reader, _args: argparse.Namespace) -> None:
    entries = reader.header_entries()
    blocks = reader.body_blocks()
    print(f'file: {reader.path}')
    print(f'size: {reader.size:,} bytes (0x{reader.size:x})')
    print()
    print('sections:')
    print(f'  A term/index-ish:      0x{SECTION_A_START:08x}..0x{SECTION_B_START:08x}')
    print(f'  B unknown compressed:  0x{SECTION_B_START:08x}..0x{SECTION_C_START:08x}')
    print(f'  C control/meta-ish:    0x{SECTION_C_START:08x}..0x{SECTION_D_START:08x}')
    print(f'  D article bodies:      0x{SECTION_D_START:08x}..0x{reader.size:08x}')
    print()
    print(f'header entries: {len(entries)}')
    print(f'  min=0x{min(e.offset for e in entries):x} '
          f'max=0x{max(e.offset for e in entries):x}')
    print()
    print(f'body blocks: {len(blocks)}')
    if blocks:
        first, last = blocks[0], blocks[-1]
        print(f'  first: #{first.index} file=0x{first.file_offset:x} '
              f'logical=0x{first.logical_offset:x}')
        print(f'  last:  #{last.index} file=0x{last.file_offset:x} '
              f'logical=0x{last.logical_offset:x}')


def command_bodyctl(reader: OED2Reader, _args: argparse.Namespace) -> None:
    control = reader.read_body_control()
    print(f'body control at 0x{control.offset:08x}')
    print(f'  magic/checksum:      0x{control.magic_or_checksum:08x}')
    print(f'  stride:              0x{control.stride:04x}')
    print(f'  block count:         {control.block_count} (0x{control.block_count:x})')
    print(f'  logical total:       0x{control.logical_total:x}')
    print(f'  logical block size:  0x{control.logical_block_size:x}')
    print(f'  aux class count:     {control.aux_class_count}')
    print(f'  repeated stride:     0x{control.repeated_stride:04x}')
    print(f'  tail/index bytes:    0x{control.tail_or_index_bytes:x}')
    print(f'  prefix word bytes:   0x{control.prefix_word_bytes:x}')
    print(f'  first block:         0x{control.first_block_offset:08x}')
    print(f'  stream end:          0x{control.end_offset:08x}')


def command_header(reader: OED2Reader, _args: argparse.Namespace) -> None:
    for e in reader.header_entries():
        print(f'{e.index:02d} 0x{e.offset:06x} '
              f'page={e.page:03d} page_off=0x{e.page_offset:04x}')


def command_origmap(reader: OED2Reader, args: argparse.Namespace) -> None:
    print('label                 offset      magic       p/h/z   sample')
    with open(reader.path, 'rb') as f:
        for label, offset, note in ORIGINAL_READER_OFFSETS:
            if args.contains and args.contains.lower() not in (
                f'{label} {note}'.lower()
            ):
                continue
            if offset >= reader.size:
                print(f'{label:<21} 0x{offset:08x} outside file  {note}')
                continue
            f.seek(offset)
            buf = f.read(args.size)
            printable_count, high_count, zero_count, text = short_profile(buf)
            text = ''.join(ch if 32 <= ord(ch) < 127 else '.' for ch in text)
            magic = table_magic(buf)
            print(f'{label:<21} 0x{offset:08x} {magic:<10} '
                  f'{printable_count:02d}/{high_count:02d}/{zero_count:02d}  '
                  f'{buf[:8].hex(" "):<23} {text}')
            if args.notes:
                print(f'  {note}')


def command_oedlist(reader: OED2Reader, args: argparse.Namespace) -> None:
    if args.list_names:
        for name, (offset, description) in sorted(OED_LISTS.items()):
            print(f'{name:<10} 0x{offset:08x} {description}')
        return

    control = reader.read_oed_list(args.name)
    h = control.header
    print(f'{control.name}: {control.description}')
    print(f'  control=0x{control.offset:08x}')
    print(f'  magic=0x{h.magic:04x} version={h.version} '
          f'blocks={h.block_count} block_size=0x{h.block_size:x}')
    print(f'  max_key_bytes={h.max_key_bytes} fragments={h.fragment_bytes} '
          f'markers={h.marker_bytes} count_base={control.count_base}')
    print(f'  block_data=0x{control.block_data_offset:08x}'
          f'..0x{control.block_data_end:08x}')
    counts = control.entry_counts()
    negative_counts = sum(1 for count in counts if count < 0)
    total_note = f'{control.total_entries}'
    if negative_counts:
        total_note += f' ({negative_counts} negative delta-derived blocks)'
    print(f'  total_entries~{total_note}')
    if args.summary:
        print(f'  entries/block min={min(counts)} max={max(counts)} '
              f'first={counts[:8]}')
        print('  first markers:')
        for i, marker in enumerate(control.markers[:8]):
            print(f'    {i:4d}: {marked_bytes(marker)}')
        return

    block = args.block
    entries = control.decode_block(block, limit=args.limit)
    print(f'  decoded block {block} entries={len(entries)} '
          f'of {control.entries_in_block(block)}')
    pointers: list[tuple[int, int]] = []
    global_start = control.start_index_for_block(block)
    if args.pointers:
        _table_a, table_b = OED_LIST_TABLES.get(control.name, (None, None))
        if table_b is None:
            raise SystemExit(f'no table-B pointer anchor recorded for {control.name!r}')
        pointers = reader.read_oed_pointer_records(
            control.name, global_start, len(entries)
        )
    for i, entry in enumerate(entries):
        entry_text = marked_bytes(entry)
        if args.hex:
            entry_text += f'  hex={entry.hex(" ")}'
        if pointers:
            left, right = pointers[i]
            try:
                target = reader.block_for_logical_offset(right)
            except ValueError:
                note = ' outside-body'
            else:
                rel = right - target.logical_offset
                note = f' block={target.index} rel=0x{rel:x}'
            print(f'{global_start + i:8d} {entry_text} ptr=({left},{right}){note}')
        else:
            print(f'{i:5d} {entry_text}')


def command_bodycheck(reader: OED2Reader, args: argparse.Namespace) -> None:
    blocks = reader.body_blocks()
    bad_aux: list[tuple[int, int, int, int]] = []
    bad_prefix: list[tuple[int, int, str]] = []
    bad_delimiter: list[tuple[int, int, int]] = []
    bad_logical: list[tuple[int, int, int]] = []
    total_high = 0
    total_aux = 0
    prev_end: int | None = None
    for block in blocks:
        payload = reader.read_payload(block)
        high = sum(1 for b in payload if b >= 0x80)
        total_high += high
        total_aux += block.aux_count
        if high != block.aux_count:
            bad_aux.append((block.index, block.file_offset, high, block.aux_count))

        stream = reader.read_aux_stream(block)
        prefix = stream.prefix_values
        if len(prefix) != BODY_AUX_PREFIX_WORDS:
            bad_prefix.append((block.index, block.file_offset, 'short-prefix'))
        elif any(prefix[i] > prefix[i + 1] for i in range(len(prefix) - 1)):
            bad_prefix.append((block.index, block.file_offset, 'nonmonotone'))
        control = reader.read_aux_control(block)
        delimiter = CanonicalBitDecoder(
            stream.compressed, control.length_counts,
        ).next_symbol()
        if delimiter != 0:
            bad_delimiter.append((block.index, block.file_offset, delimiter))

        if prev_end is not None and block.logical_offset != prev_end:
            bad_logical.append((block.index, prev_end, block.logical_offset))
        prev_end = block.logical_offset + block.logical_length

    print(f'body blocks: {len(blocks)}')
    print(f'total high-bit payload markers: {total_high}')
    print(f'total aux symbols declared:     {total_aux}')
    print(f'aux-count mismatches:           {len(bad_aux)}')
    print(f'prefix-table issues:            {len(bad_prefix)}')
    print(f'delimiter-symbol issues:        {len(bad_delimiter)}')
    print(f'logical-continuity gaps:         {len(bad_logical)}')
    if args.samples:
        for label, rows in (
            ('aux mismatch', bad_aux),
            ('prefix issue', bad_prefix),
            ('delimiter issue', bad_delimiter),
            ('logical gap', bad_logical),
        ):
            if rows:
                print(label + ':')
                for row in rows[:args.samples]:
                    print(f'  {row}')


def command_ptrs(reader: OED2Reader, args: argparse.Namespace) -> None:
    table_a, table_b = OED_LIST_TABLES[args.name]
    count = args.count
    if count is None:
        count = reader.read_oed_list(args.name).total_entries if args.summary else 32
    records = reader.read_oed_pointer_records(args.name, args.start, count)
    print(f'{args.name}: tableA={table_a and f"0x{table_a:08x}"} '
          f'tableB=0x{table_b:08x}')
    if args.summary:
        blocks = reader.body_blocks()
        starts = [b.logical_offset for b in blocks]
        body_lo, body_hi = reader.body_logical_range()
        body_hits = 0
        sentinel_right = 0
        between_body_blocks = 0
        left_nonzero = 0
        left_monotone = 0
        right_monotone = 0
        duplicate_records = 0
        prev_left: int | None = None
        prev_right: int | None = None
        prev_record: tuple[int, int] | None = None
        invalid_samples: list[tuple[int, int, int, str]] = []
        left_values: list[int] = []
        right_values: list[int] = []
        for i, (left, right) in enumerate(records, start=args.start):
            left_values.append(left)
            right_values.append(right)
            if left:
                left_nonzero += 1
            if right == 0xffffffff:
                sentinel_right += 1
            if prev_left is not None and left >= prev_left:
                left_monotone += 1
            if prev_right is not None and right >= prev_right:
                right_monotone += 1
            if prev_record == (left, right):
                duplicate_records += 1
            prev_left = left
            prev_right = right
            prev_record = (left, right)

            reason = ''
            if not body_lo <= right < body_hi:
                reason = 'outside-body-logical-range'
            else:
                block_index = bisect.bisect_right(starts, right) - 1
                block = blocks[block_index] if block_index >= 0 else None
                if (
                    block is None
                    or right >= block.logical_offset + block.logical_length
                ):
                    between_body_blocks += 1
                    reason = 'between-body-blocks'
                else:
                    body_hits += 1
            if reason and len(invalid_samples) < 8:
                invalid_samples.append((i, left, right, reason))

        transitions = max(0, len(records) - 1)
        print(f'  scanned records: {len(records)} from index {args.start}')
        print(f'  body logical range: 0x{body_lo:x}..0x{body_hi:x}')
        print(f'  b in body blocks: {body_hits} / {len(records)}')
        print(f'  b between body blocks: {between_body_blocks}')
        print(f'  b sentinels 0xffffffff: {sentinel_right}')
        print(f'  a nonzero: {left_nonzero} / {len(records)}')
        if records:
            print(f'  a min/max: {min(left_values)} / {max(left_values)}')
            print(f'  b min/max: {min(right_values)} / {max(right_values)}')
        print(f'  a nondecreasing adjacent pairs: '
              f'{left_monotone} / {transitions}')
        print(f'  b nondecreasing adjacent pairs: '
              f'{right_monotone} / {transitions}')
        print(f'  duplicate adjacent records: {duplicate_records}')
        if invalid_samples:
            print('  invalid/sentinel samples:')
            for i, left, right, reason in invalid_samples:
                print(f'    {i:8d} a={left:10d} b=0x{right:08x} {reason}')
        return

    for i, (left, right) in enumerate(records, start=args.start):
        note = ''
        if args.snippets:
            try:
                record = reader.decode_body_record(right)
            except ValueError:
                note = ' outside-body-logical-range'
            else:
                block = record.block
                rel = right - block.logical_offset
                snippet = normalized_record_text(record.data).replace('\n', ' ')
                note = (
                    f' block={block.index} logical_rel=0x{rel:x} '
                    f'frags={len(record.fragment_ids)} '
                    f'body={snippet[:args.snippet_chars]!r}'
                )
        print(f'{i:8d}  a={left:10d}  b={right:10d}  '
              f'b_hex=0x{right:08x}{note}')


def command_tablea(reader: OED2Reader, args: argparse.Namespace) -> None:
    names = sorted(OED_LIST_TABLES) if args.all else [args.name]
    for name in names:
        table_a, _table_b = OED_LIST_TABLES[name]
        if table_a is None:
            print(f'{name}: no table-A anchor recorded')
            continue
        raw = reader.read_at_file_offset(table_a, args.size)
        if len(raw) < 2:
            print(f'{name}: short read at 0x{table_a:08x}')
            continue
        vals = list(struct.unpack(f'>{len(raw) // 2}H', raw[:len(raw) & ~1]))
        nz = [i for i, value in enumerate(vals) if value]
        last_nz = nz[-1] if nz else None
        print(f'{name}: tableA=0x{table_a:08x} size=0x{len(raw):x} '
              f'sha1={hashlib.sha1(raw).hexdigest()[:12]}')
        print(f'  header_words={vals[:4]}')
        print(f'  nonzero_words={len(nz)} last_nonzero_index={last_nz} '
              f'last_value={vals[last_nz] if last_nz is not None else None}')
        if args.words:
            start = min(max(0, args.start), len(vals))
            stop = min(len(vals), start + args.words)
            shown = ' '.join(f'{value:04x}' for value in vals[start:stop])
            print(f'  words[{start}:{stop}] {shown}')
        table_struct: TableAStruct | None = None
        if (args.struct or args.record_indexes or args.map_bytes
                or args.encode or args.encode_exe or args.decode_exe_hex):
            try:
                table_struct = parse_tablea_struct(raw)
            except ValueError as exc:
                print(f'  structured parse failed: {exc}')
            else:
                index_samples = [
                    table_struct.index_map[i]
                    for i in range(min(16, len(table_struct.index_map)))
                ]
                print(
                    f'  struct records={table_struct.record_count} '
                    f'entities={table_struct.entity_count} '
                    f'pool=0x{len(table_struct.pool):x} '
                    f'index_map={len(table_struct.index_map)}'
                )
                print(
                    f'  struct offsets[0:8] '
                    f'{" ".join(f"{v:04x}" for v in table_struct.offsets[:8])}'
                )
                print(
                    f'  struct index[0:16] '
                    f'{" ".join(f"{v:04x}" for v in index_samples)}'
                )
        if table_struct is not None and args.record_indexes:
            for index in args.record_indexes:
                try:
                    record = table_struct.record(index)
                except IndexError:
                    print(f'  record[{index}] out of range')
                    continue
                rank = tablea_rank_value(record.secondary)
                rank_text = '?' if rank is None else str(rank)
                print(
                    f'  record[{index:4d}] '
                    f'off={record.offsets[0]:04x}/{record.offsets[1]:04x}/'
                    f'{record.offsets[2]:04x}/{record.offsets[3]:04x} '
                    f'source={marked_bytes(record.source)!r} '
                    f'primary={marked_bytes(record.primary)!r} '
                    f'secondary={marked_bytes(record.secondary)!r} '
                    f'rank={rank_text}'
                )
        if table_struct is not None and args.map_bytes:
            for item in args.map_bytes:
                if len(item) == 1:
                    byte = ord(item)
                else:
                    byte = parse_int(item)
                try:
                    record_index = table_struct.direct_record_index(byte)
                except ValueError:
                    print(f'  map[{item!r}] invalid byte')
                    continue
                if record_index is None:
                    print(f'  map[{item!r}] -> ffff')
                    continue
                record = table_struct.record(record_index)
                print(
                    f'  map[{item!r}/0x{byte:02x}] -> record {record_index}: '
                    f'{marked_bytes(record.source)!r} -> '
                    f'{marked_bytes(record.primary)!r} + '
                    f'{marked_bytes(record.secondary)!r}'
                )
        if table_struct is not None and args.encode:
            for text in args.encode:
                encoded = encode_tablea_simple(table_struct, text)
                print(
                    f'  encode-simple {text!r}: '
                    f'{marked_bytes(encoded)}  hex={encoded.hex(" ")}'
                )
        if table_struct is not None and args.encode_exe:
            for text in args.encode_exe:
                encoded = encode_tablea_exe(
                    table_struct, text, args.mode, args.mode_hi,
                )
                print(
                    f'  encode-exe {text!r}: '
                    f'{marked_bytes(encoded)}  hex={encoded.hex(" ")}'
                )
        if table_struct is not None and args.decode_exe_hex:
            for text in args.decode_exe_hex:
                encoded = bytes.fromhex(text)
                decoded = decode_tablea_exe(
                    table_struct, encoded, args.mode, args.mode_hi,
                )
                print(
                    f'  decode-exe {text!r}: '
                    f'{marked_bytes(decoded)}  hex={decoded.hex(" ")}'
                )
        if args.text:
            if args.text_start is None:
                text_start = find_tablea_text_start(raw)
            else:
                text_start = min(max(0, args.text_start), len(raw))
            text = ''.join(printable(b) for b in raw[
                text_start:text_start + args.text_bytes
            ])
            print(f'  text[0x{text_start:x}:0x{text_start + len(text):x}] '
                  f'{text!r}')
        if args.records:
            if args.text_start is None:
                text_start = find_tablea_text_start(raw)
            else:
                text_start = min(max(0, args.text_start), len(raw))
            records = parse_tablea_text_map(raw, text_start, args.text_bytes)
            print(f'  records parsed={len(records)} '
                  f'from text_start=0x{text_start:x}')
            for i, record in enumerate(records[:args.record_limit]):
                code_value = (
                    '?' if record.code_value is None
                    else str(record.code_value)
                )
                print(f'    {i:4d} +0x{record.offset:04x} '
                      f'{record.source!r} -> {record.normalized!r} '
                      f'code={record.code_text} ({code_value})')


def command_sparse(reader: OED2Reader, args: argparse.Namespace) -> None:
    names = (
        [
            name for name, (_offset, _description)
            in sorted(OED_SPARSE_INDEXES.items(), key=lambda item: item[1][0])
        ]
        if args.all else [args.name]
    )
    known_offsets = sorted(offset for offset, _desc in OED_SPARSE_INDEXES.values())
    for name in names:
        header = reader.read_sparse_header(name)
        next_known = next(
            (off for off in known_offsets if off > header.offset),
            BODY_CONTROL_OFFSET if BODY_CONTROL_OFFSET > header.offset else None,
        )
        print(f'{name}: {header.description}')
        print(f'  offset=0x{header.offset:x} magic=0x{header.magic:04x}')
        print(f'  block_size=0x{header.block_size:x} '
              f'fanout/levels={header.fanout_or_levels} '
              f'logical_total=0x{header.logical_total:x} '
              f'({header.logical_total})')
        print(f'  first_page=0x{header.first_page_offset:x} '
              f'page_logical_span={header.page_logical_span} '
              f'data_pages={header.data_page_count} '
              f'derived_end=0x{header.end_offset:x}')
        if next_known is not None:
            gap = next_known - header.end_offset
            print(f'  next_known=0x{next_known:x} gap_after_derived=0x{gap:x}')
        for page in range(args.pages):
            page_off = header.first_page_offset + page * header.block_size
            raw = reader.read_at_file_offset(page_off, header.block_size)
            words = [
                struct.unpack_from('<H', raw, i)[0]
                for i in range(0, len(raw) - 1, 2)
            ]
            longs = [
                struct.unpack_from('<I', raw, i)[0]
                for i in range(0, len(raw) - 3, 4)
            ]
            preview_words = ' '.join(f'{w:04x}' for w in words[:args.words])
            preview_longs = ' '.join(f'{x:08x}' for x in longs[:args.longs])
            print(f'  page {page:3d} off=0x{page_off:x} '
                  f'nonzero_words={sum(1 for w in words if w):4d}/{len(words)} '
                  f'nonzero_longs={sum(1 for x in longs if x):4d}/{len(longs)}')
            print(f'    u16le: {preview_words}')
            print(f'    u32le: {preview_longs}')
        print()


def command_blocks(reader: OED2Reader, args: argparse.Namespace) -> None:
    blocks = reader.body_blocks()
    stop = min(len(blocks), args.limit) if args.limit else len(blocks)
    for block in blocks[:stop]:
        print(f'{block.index:5d} file=0x{block.file_offset:08x} '
              f'logical=0x{block.logical_offset:08x} '
              f'len=0x{block.logical_length:04x} '
              f'stored=0x{block.stored_length:04x} '
              f'aux=0x{block.aux_count:04x}')
    if stop < len(blocks):
        print(f'... {len(blocks) - stop} more')


def block_from_args(reader: OED2Reader, args: argparse.Namespace) -> BodyBlock:
    if args.block is not None:
        blocks = reader.body_blocks()
        if not 0 <= args.block < len(blocks):
            raise SystemExit(f'block index out of range: {args.block}')
        return blocks[args.block]
    if args.offset is not None:
        blocks = {b.file_offset: b for b in reader.body_blocks()}
        if args.offset in blocks:
            return blocks[args.offset]
        raise SystemExit(f'no body block starts at file offset 0x{args.offset:x}')
    if args.logical is not None:
        return reader.block_for_logical_offset(args.logical)
    raise SystemExit('choose --block, --offset, or --logical')


def command_dump(reader: OED2Reader, args: argparse.Namespace) -> None:
    block = block_from_args(reader, args)
    payload = reader.read_payload(block)
    start = max(0, args.payload_offset)
    end = min(len(payload), start + args.size)
    chunk = payload[start:end]

    print(f'block #{block.index} file=0x{block.file_offset:x} '
          f'logical=0x{block.logical_offset:x} '
          f'len=0x{block.logical_length:x} stored=0x{block.stored_length:x} '
          f'aux=0x{block.aux_count:x}')
    print(f'payload slice 0x{start:x}..0x{end:x}')
    if args.mode in ('hex', 'both'):
        print('\nHex:')
        print(hexdump(chunk, block.payload_offset + start))
    if args.mode in ('text', 'both'):
        print('\nText:')
        text = marked_highbit(chunk) if args.mark_highbit else normalize_highbit(chunk)
        print(text)


def command_aux(reader: OED2Reader, args: argparse.Namespace) -> None:
    block = block_from_args(reader, args)
    payload, fragment_offsets = reader.body_fragment_table(block)
    control = reader.read_aux_control(block)
    stream = reader.read_aux_stream(block)
    decoder = CanonicalBitDecoder(stream.compressed, control.length_counts)
    sentinel = decoder.next_symbol()
    window_span = reader.body_window_span(block)

    print(f'block #{block.index} file=0x{block.file_offset:x} '
          f'logical=0x{block.logical_offset:x}')
    print(f'payload high-bit bytes: {len(fragment_offsets) - 1} '
          f'(header aux_count={block.aux_count})')
    print(f'aux control offset: 0x{block.aux_control_offset:x}')
    print(f'aux stream offset:  0x{block.aux_stream_offset:x}')
    print(f'aux prefix words:   {len(stream.prefix_values)} '
          f'(0x{stream.prefix_bytes:x} bytes)')
    if stream.prefix_values:
        preview = [f'0x{x:x}' for x in stream.prefix_values[:8]]
    print(f'aux prefix first:   {preview}')
    print('aux prefix use:     prefix[logical-window] gives bit offset')
    print(f'logical window span: {window_span}')
    print(f'delimiter symbol:   {sentinel}')
    print(f'compressed bytes:   {len(stream.compressed)}')
    print(f'code-length classes: {control.code_length_count}')
    print(f'length counts: {list(control.length_counts)}')
    print(f'symbol count: {control.symbol_count}')
    print(f'kraft units: 0x{control.kraft_units:08x}')
    print()
    print('prefix windows:')
    for window, bit_start in enumerate(stream.prefix_values[:args.limit]):
        logical = block.logical_offset + window * window_span
        if logical >= block.logical_offset + block.logical_length:
            break
        record = reader.decode_body_record(logical)
        text = normalized_record_text(record.data).replace('\n', ' ')
        next_bit = (
            stream.prefix_values[window + 1]
            if window + 1 < len(stream.prefix_values)
            else len(stream.compressed) * 8
        )
        print(f'{window:4d} logical=0x{logical:08x} '
              f'bit={bit_start:7d}..{next_bit:<7d} '
              f'first-frags={len(record.fragment_ids):3d} '
              f'{text[:80]!r}')

    print()
    print('first payload fragments:')
    for fragment_id in range(min(args.limit, len(fragment_offsets) - 1)):
        lo = fragment_offsets[fragment_id]
        hi = fragment_offsets[fragment_id + 1]
        text = normalized_record_text(payload[lo:hi]).replace('\n', ' ')
        print(f'{fragment_id:4d} payload=0x{lo:04x}..0x{hi:04x} '
              f'{text[:80]!r}')


def command_classes(reader: OED2Reader, args: argparse.Namespace) -> None:
    block = block_from_args(reader, args)
    payload = reader.read_payload(block)
    control = reader.read_aux_control(block)
    stream = reader.read_aux_stream(block)

    class_counts = Counter(b & 0x3f for b in payload if b >= 0x80)
    print('legacy probe: OED.EXE uses the 64 prefix values as logical '
          'window starts, not payload byte classes.')
    print(f'block #{block.index} file=0x{block.file_offset:x} '
          f'logical=0x{block.logical_offset:x}')
    print(f'class count: {len(class_counts)}; high-bit markers: '
          f'{sum(class_counts.values())}')
    print('class  char  count  bit_start  next_start  decoded  top_symbols')
    for group, count in class_counts.most_common(args.limit):
        bit_start = stream.prefix_values[group]
        next_start = (
            stream.prefix_values[group + 1]
            if group < len(stream.prefix_values) - 1
            else len(stream.compressed) * 8
        )
        symbols = decode_canonical_symbols_from_bit(
            stream.compressed,
            control.length_counts,
            bit_start,
            count,
        )
        top = ','.join(f'{sym}:{n}' for sym, n in
                       Counter(symbols).most_common(5))
        print(f'0x{group:02x}   {printable(group)!r:>4}  {count:5d}  '
              f'{bit_start:9d}  {next_start:10d}  '
              f'{len(symbols):7d}  {top}')


def command_table5(reader: OED2Reader, args: argparse.Namespace) -> None:
    size = args.width * args.count
    data = reader.read_at_file_offset(args.offset, size)
    records = [
        data[i:i + args.width]
        for i in range(0, len(data) - args.width + 1, args.width)
    ]

    print(f'candidate table slice: 0x{args.offset:x}..'
          f'0x{args.offset + len(data):x}')
    print(f'width={args.width} records={len(records)}')
    if (args.offset - CANDIDATE_FRAGMENT_TABLE_START) % args.width:
        print('note: offset is not aligned to the candidate table start')
    print()
    print('column  printable  high-bit  unique  top-bytes')
    for col in range(args.width):
        values = [r[col] for r in records if len(r) > col]
        printable_count = sum(32 <= highbit_normalized_byte(b) < 127
                              for b in values)
        high_count = sum(b >= 0x80 for b in values)
        top = ' '.join(f'{b:02x}:{n}' for b, n in
                       Counter(values).most_common(6))
        print(f'{col:6d}  {printable_count / len(values):9.3f}  '
              f'{high_count / len(values):8.3f}  '
              f'{len(set(values)):6d}  {top}')

    print()
    pairs = [packed20le_pair(r) for r in records if len(r) == 5]
    u24_pairs = [u24le_u16le_record(r) for r in records if len(r) == 5]
    if pairs:
        pair_rate = monotonic_pair_rate(pairs)
        print(f'packed 20-bit LE pair monotonic rate: {pair_rate:.3f}')
    if u24_pairs:
        bucket_rate = sorted_bucket_pair_rate(u24_pairs)
        print(f'u24le/u16le bucket-sort rate: {bucket_rate:.3f}')
        print()

    print('index       file-off   bytes             u24      u16    lo20    hi20    raw       norm')
    start_index = (args.offset - CANDIDATE_FRAGMENT_TABLE_START) // args.width
    for i, rec in enumerate(records[:args.show]):
        off = args.offset + i * args.width
        idx = start_index + i
        hx = ' '.join(f'{b:02x}' for b in rec)
        if len(rec) == 5:
            lo20, hi20 = packed20le_pair(rec)
            u24, u16 = u24le_u16le_record(rec)
            fields = f'{u24:7x} {u16:6x}  {lo20:6x}  {hi20:6x}'
        else:
            fields = '      -      -       -       -'
        print(f'{idx:7d}  0x{off:08x}  {hx:<16}  {fields}  '
              f'{raw_record_text(rec)!r:<9} {normalized_record_text(rec)!r}')


def command_table5_profile(reader: OED2Reader,
                           args: argparse.Namespace) -> None:
    print('offset      printable  high-bit  records  le20-pair-monotone  u24/u16-sort')
    offset = args.start
    while offset < args.end:
        data = reader.read_at_file_offset(offset, min(args.chunk,
                                                      args.end - offset))
        if not data:
            break
        record_bytes = (
            len(data) // CANDIDATE_FRAGMENT_RECORD_SIZE
            * CANDIDATE_FRAGMENT_RECORD_SIZE
        )
        data = data[:record_bytes]
        records = [
            data[i:i + CANDIDATE_FRAGMENT_RECORD_SIZE]
            for i in range(0,
                           record_bytes,
                           CANDIDATE_FRAGMENT_RECORD_SIZE)
        ]
        if not records:
            break
        pairs = [packed20le_pair(r) for r in records]
        u24_pairs = [u24le_u16le_record(r) for r in records]
        printable_count = sum(32 <= highbit_normalized_byte(b) < 127
                              for b in data)
        high_count = sum(b >= 0x80 for b in data)
        print(f'0x{offset:08x}  {printable_count / len(data):9.3f}  '
              f'{high_count / len(data):8.3f}  {len(records):7d}  '
              f'{monotonic_pair_rate(pairs):18.3f}  '
              f'u24/u16-sort={sorted_bucket_pair_rate(u24_pairs):.3f}')
        offset += record_bytes


def command_table5_runs(reader: OED2Reader, args: argparse.Namespace) -> None:
    size = args.end - args.start
    data = reader.read_at_file_offset(args.start, size)
    record_bytes = (
        len(data) // CANDIDATE_FRAGMENT_RECORD_SIZE
        * CANDIDATE_FRAGMENT_RECORD_SIZE
    )
    records = [
        data[i:i + CANDIDATE_FRAGMENT_RECORD_SIZE]
        for i in range(0, record_bytes, CANDIDATE_FRAGMENT_RECORD_SIZE)
    ]
    pairs = [u24le_u16le_record(r) for r in records]
    if not pairs:
        return

    runs: list[tuple[int, int]] = []
    run_start = 0
    for i in range(1, len(pairs)):
        if (pairs[i][1], pairs[i][0]) < (pairs[i - 1][1], pairs[i - 1][0]):
            runs.append((run_start, i))
            run_start = i
    runs.append((run_start, len(pairs)))

    print(f'table range: 0x{args.start:x}..0x{args.start + record_bytes:x}')
    print(f'records: {len(records)}; monotone runs: {len(runs)}')
    print('run  records              count   file-off     first(u24,u16)      last(u24,u16)')
    for run_index, (start_idx, end_idx) in enumerate(runs[:args.limit]):
        first = pairs[start_idx]
        last = pairs[end_idx - 1]
        off = args.start + start_idx * CANDIDATE_FRAGMENT_RECORD_SIZE
        print(f'{run_index:3d}  {start_idx:6d}..{end_idx - 1:<6d}  '
              f'{end_idx - start_idx:6d}  0x{off:08x}  '
              f'({first[0]:06x},{first[1]:04x})  '
              f'({last[0]:06x},{last[1]:04x})')


def command_bitrange(reader: OED2Reader, args: argparse.Namespace) -> None:
    rec_offset = args.table_offset + args.index * CANDIDATE_FRAGMENT_RECORD_SIZE
    rec = reader.read_at_file_offset(rec_offset, CANDIDATE_FRAGMENT_RECORD_SIZE)
    if len(rec) != CANDIDATE_FRAGMENT_RECORD_SIZE:
        raise SystemExit('short table record')
    lo20, hi20 = packed20le_pair(rec)
    start_bit, end_bit = sorted((lo20, hi20))
    bit_count = end_bit - start_bit
    byte_count = (end_bit + 7) // 8
    stream = reader.read_at_file_offset(args.stream_offset, byte_count)
    msb = pack_bits(stream, start_bit, end_bit, lsb_first=False)
    lsb = pack_bits(stream, start_bit, end_bit, lsb_first=True)

    hx = ' '.join(f'{b:02x}' for b in rec)
    print(f'index={args.index} record_offset=0x{rec_offset:x}')
    print(f'record bytes: {hx}')
    print(f'lo20=0x{lo20:x} hi20=0x{hi20:x} bits={bit_count}')
    print(f'stream base: 0x{args.stream_offset:x}')
    for name, buf in (('msb-packed', msb), ('lsb-packed', lsb)):
        sample = buf[:args.limit]
        print()
        print(name)
        print(hexdump(sample, args.stream_offset + start_bit // 8))
        print(normalized_record_text(sample))


def command_auxmap(reader: OED2Reader, args: argparse.Namespace) -> None:
    block = block_from_args(reader, args)
    payload = reader.read_payload(block)
    high_positions = [i for i, b in enumerate(payload) if b >= 0x80]
    symbols = reader.decode_aux_symbols(block, args.limit)

    print('legacy probe: this uses the old byte-class aux-symbol model; '
          'bodyrec is the executable-derived decoder.')
    print(f'block #{block.index} file=0x{block.file_offset:x} '
          f'logical=0x{block.logical_offset:x}')
    print(f'table base=0x{args.table_offset:x} width={args.width}')
    print('marker  payload  class char aux_sym  table-off   bytes             norm       context')
    with open(reader.path, 'rb') as f:
        for marker_index, pos in enumerate(high_positions[:len(symbols)]):
            b = payload[pos]
            group = b & 0x3f
            sym = symbols[marker_index]
            rec_off = args.table_offset + sym * args.width
            f.seek(rec_off)
            rec = f.read(args.width)
            context = normalize_highbit(payload[max(0, pos - 10):pos + 11])
            hx = ' '.join(f'{x:02x}' for x in rec)
            print(f'{marker_index:6d}  0x{pos:04x}  '
                  f'0x{group:02x} {printable(group)!r:>4} '
                  f'{sym:7d}  0x{rec_off:08x}  {hx:<16}  '
                  f'{normalized_record_text(rec)!r:<9} {context}')


def marker_order(markers: list[tuple[int, int, int, int]],
                 order: str) -> list[int]:
    """Return marker indexes in a candidate canonical-symbol order.

    Each marker tuple is ``(marker_index, raw_byte, ascii_byte, class)``.
    The true OED2 reader likely maps decoded canonical ranks through a
    deterministic order.  These candidates are probes, not assertions.
    """
    reverse = order.endswith('-rev')
    base_order = order[:-4] if reverse else order
    if base_order == 'payload':
        rows = markers
    elif base_order == 'raw':
        rows = sorted(markers, key=lambda t: (t[1], t[0]))
    elif base_order == 'char':
        rows = sorted(markers, key=lambda t: (t[2], t[0]))
    elif base_order == 'class':
        rows = sorted(markers, key=lambda t: (t[3], t[0]))
    else:
        raise ValueError(f'unknown marker order: {order}')
    if reverse:
        rows = list(reversed(rows))
    return [row[0] for row in rows]


def candidate_recursive_expansion(payload: bytes, symbols: list[int],
                                  order: str) -> str:
    high_bytes = [b for b in payload if b >= 0x80]
    markers = [
        (i, b, highbit_normalized_byte(b), b & 0x3f)
        for i, b in enumerate(high_bytes)
    ]
    rank_to_marker = marker_order(markers, order)
    mapped = [
        rank_to_marker[s] if 0 <= s < len(rank_to_marker) else 0
        for s in symbols
    ]
    chars = [m[2] for m in markers]

    memo: dict[int, str] = {}
    visiting: set[int] = set()

    def expand_marker(index: int) -> str:
        # Treat marker zero as a terminal for this experiment.  This is
        # one of the behaviours suggested by the high frequency of symbol
        # zero, but it is not yet known to be the production algorithm.
        if index == 0 or index >= len(mapped):
            return ''
        if index in memo:
            return memo[index]
        if index in visiting:
            return ''
        visiting.add(index)
        ch = printable(chars[index])
        text = ch + expand_marker(mapped[index])
        visiting.remove(index)
        # Guard against pathological cycles while keeping enough text to
        # inspect fragment-like expansions.
        memo[index] = text[:128]
        return memo[index]

    out: list[str] = []
    marker_index = 0
    for b in payload:
        if b >= 0x80:
            out.append(expand_marker(marker_index))
            marker_index += 1
        else:
            out.append(printable(b))
    return ''.join(out)


def distance_parent_symbols(symbols: list[int], formula: str) -> list[int]:
    shift_match = re.fullmatch(r'i-s([+-]\d+)?', formula)
    if shift_match:
        shift = int(shift_match.group(1) or '0')
        return [i - symbol + shift for i, symbol in enumerate(symbols)]
    if formula == 'i-s-1':
        return [i - symbol - 1 for i, symbol in enumerate(symbols)]
    if formula == 'i-s':
        return [i - symbol for i, symbol in enumerate(symbols)]
    if formula == 'i-s+1':
        return [i - symbol + 1 for i, symbol in enumerate(symbols)]
    if formula == 'symbol':
        return symbols
    raise ValueError(f'unknown distance formula: {formula}')


def class_distance_parent_symbols(payload: bytes, symbols: list[int],
                                  formula: str) -> list[int]:
    """Legacy distance probe for the rejected byte-class aux model."""
    shift_match = re.fullmatch(r'i-s([+-]\d+)?', formula)
    if shift_match:
        mode = 'distance'
        shift = int(shift_match.group(1) or '0')
    elif formula == 'symbol':
        mode = 'absolute'
        shift = 0
    else:
        raise ValueError(f'unknown class-distance formula: {formula}')

    high_bytes = [b for b in payload if b >= 0x80]
    class_to_globals: dict[int, list[int]] = {}
    local_indexes: list[int] = []
    for global_index, b in enumerate(high_bytes):
        group = b & 0x3f
        rows = class_to_globals.setdefault(group, [])
        local_indexes.append(len(rows))
        rows.append(global_index)

    parents: list[int] = []
    for global_index, (b, symbol) in enumerate(zip(high_bytes, symbols)):
        group = b & 0x3f
        if mode == 'distance':
            parent_local = local_indexes[global_index] - symbol + shift
        else:
            parent_local = symbol
        rows = class_to_globals[group]
        if 0 <= parent_local < len(rows):
            parents.append(rows[parent_local])
        else:
            parents.append(-1)
    return parents


def candidate_distance_expansion(payload: bytes, symbols: list[int],
                                 formula: str = 'i-s-1',
                                 order: str = 'parent-char') -> str:
    """Experimental LZ-style high-bit expansion.

    The strongest current body hypothesis is that aux symbols are
    distances to a prior high-bit marker, not absolute marker indexes.
    This function materializes that hypothesis for inspection.
    """
    if order not in ('parent-char', 'char-parent'):
        raise ValueError(f'unknown distance expansion order: {order}')
    high_bytes = [b for b in payload if b >= 0x80]
    parents = distance_parent_symbols(symbols, formula)
    chars = [highbit_normalized_byte(b) for b in high_bytes]
    memo: dict[int, str] = {}
    visiting: set[int] = set()

    def expand_marker(index: int) -> str:
        if index < 0 or index >= len(parents):
            return ''
        if index in memo:
            return memo[index]
        if index in visiting:
            return ''
        visiting.add(index)
        ch = printable(chars[index])
        parent_text = expand_marker(parents[index])
        text = (
            parent_text + ch
            if order == 'parent-char'
            else ch + parent_text
        )
        visiting.remove(index)
        memo[index] = text[:256]
        return memo[index]

    out: list[str] = []
    marker_index = 0
    for b in payload:
        if b >= 0x80:
            out.append(expand_marker(marker_index))
            marker_index += 1
        else:
            out.append(printable(b))
    return ''.join(out)


def candidate_class_distance_expansion(payload: bytes, symbols: list[int],
                                       formula: str = 'i-s-1',
                                       order: str = 'parent-char') -> str:
    if order not in ('parent-char', 'char-parent'):
        raise ValueError(f'unknown distance expansion order: {order}')
    high_bytes = [b for b in payload if b >= 0x80]
    parents = class_distance_parent_symbols(payload, symbols, formula)
    chars = [highbit_normalized_byte(b) for b in high_bytes]
    memo: dict[int, str] = {}
    visiting: set[int] = set()

    def expand_marker(index: int) -> str:
        if index < 0 or index >= len(parents):
            return ''
        if index in memo:
            return memo[index]
        if index in visiting:
            return ''
        visiting.add(index)
        ch = printable(chars[index])
        parent_text = expand_marker(parents[index])
        text = (
            parent_text + ch
            if order == 'parent-char'
            else ch + parent_text
        )
        visiting.remove(index)
        memo[index] = text[:256]
        return memo[index]

    out: list[str] = []
    marker_index = 0
    for b in payload:
        if b >= 0x80:
            out.append(expand_marker(marker_index))
            marker_index += 1
        else:
            out.append(printable(b))
    return ''.join(out)


def trie_expansion_lengths(parent: list[int], root_zero: bool = True,
                           max_depth: int = 4096) -> list[int]:
    """Experimental high-bit marker graph lengths.

    This models each high-bit marker as one visible low-7-bit byte plus
    a referenced parent marker.  It is a probe for the OED body
    substitution layer, not a confirmed production decoder.
    """
    memo: dict[int, int] = {}
    visiting: set[int] = set()
    n = len(parent)

    def length(index: int, depth: int = 0) -> int:
        if index < 0 or index >= n:
            return 0
        if root_zero and parent[index] == 0:
            return 1
        if index in memo:
            return memo[index]
        if index in visiting or depth >= max_depth:
            return 0
        visiting.add(index)
        value = 1 + length(parent[index], depth + 1)
        visiting.remove(index)
        memo[index] = value
        return value

    return [length(i) for i in range(n)]


def command_bodytrie(reader: OED2Reader, args: argparse.Namespace) -> None:
    blocks = reader.body_blocks()
    indices = (
        range(args.start_block, min(len(blocks), args.start_block + args.count))
        if args.scan
        else [block_from_args(reader, args).index]
    )
    shifts = args.shift if args.shift is not None else [0]
    print('block stored logical high consume shift root0 total diff '
          'avg_len zeros gt_current')
    for index in indices:
        block = blocks[index]
        payload = reader.read_payload(block)
        high_bytes = [b for b in payload if b >= 0x80]
        symbols = reader.decode_aux_symbols(block, consume=args.consume)
        if len(symbols) != len(high_bytes):
            print(f'{index:5d} short-symbols decoded={len(symbols)} '
                  f'high={len(high_bytes)}')
            continue
        for shift in shifts:
            parent = [symbol + shift for symbol in symbols]
            lengths = trie_expansion_lengths(parent, root_zero=args.root_zero)
            total = block.stored_length + sum(length - 1 for length in lengths)
            avg = sum(lengths) / len(lengths) if lengths else 0.0
            gt_current = sum(p > i for i, p in enumerate(parent))
            print(f'{index:5d} {block.stored_length:6d} '
                  f'{block.logical_length:7d} {len(high_bytes):4d} '
                  f'{args.consume:<7} {shift:5d} {int(args.root_zero):5d} '
                  f'{total:5d} {total - block.logical_length:5d} '
                  f'{avg:7.3f} {symbols.count(0):5d} {gt_current:10d}')


def command_bodydist(reader: OED2Reader, args: argparse.Namespace) -> None:
    blocks = reader.body_blocks()
    indices = (
        range(args.start_block, min(len(blocks), args.start_block + args.count))
        if args.scan
        else [block_from_args(reader, args).index]
    )
    formulas = expand_formula_args(args.formula, args.formula_range, ['i-s-1'])
    if args.scan:
        print('block stored logical high scope  formula  total diff avg_len')
    for index in indices:
        block = blocks[index]
        payload = reader.read_payload(block)
        symbols = reader.decode_aux_symbols(block, consume=args.consume)
        if len(symbols) != sum(1 for b in payload if b >= 0x80):
            print(f'{index:5d} short-symbols decoded={len(symbols)}')
            continue
        for formula in formulas:
            if args.scope == 'global':
                parents = distance_parent_symbols(symbols, formula)
            elif args.scope == 'class':
                parents = class_distance_parent_symbols(payload, symbols, formula)
            else:
                raise ValueError(f'unknown bodydist scope: {args.scope}')
            lengths = trie_expansion_lengths(parents, root_zero=False)
            total = block.stored_length + sum(length - 1 for length in lengths)
            avg = sum(lengths) / len(lengths) if lengths else 0.0
            if args.scan:
                print(f'{index:5d} {block.stored_length:6d} '
                      f'{block.logical_length:7d} {len(symbols):4d} '
                      f'{args.scope:<6} {formula:<7} {total:5d} '
                      f'{total - block.logical_length:5d} {avg:7.3f}')
            else:
                print(f'block #{block.index} file=0x{block.file_offset:x} '
                      f'logical=0x{block.logical_offset:x}')
                print(f'scope={args.scope} formula={formula} '
                      f'consume={args.consume} '
                      f'stored={block.stored_length} '
                      f'expanded={total} logical={block.logical_length} '
                      f'diff={total - block.logical_length}')
                if args.scope == 'global':
                    text = candidate_distance_expansion(
                        payload, symbols, formula, args.order,
                    )
                else:
                    text = candidate_class_distance_expansion(
                        payload, symbols, formula, args.order,
                    )
                if args.show:
                    print(text[:args.show].replace('\n', '\\n'))


def command_bodyfit(reader: OED2Reader, args: argparse.Namespace) -> None:
    blocks = reader.body_blocks()
    indices = range(args.start_block, min(len(blocks), args.start_block + args.count))
    candidates: list[tuple[str, str, str, str]] = []
    consumes = args.consume or ['forward']
    formulas = expand_formula_args(args.formula, args.formula_range,
                                   ['i-s-1', 'i-s+1'])
    distance_orders = args.distance_order or ['parent-char', 'char-parent']
    recursive_orders = args.recursive_order or ['payload']
    for consume in consumes:
        for formula in formulas:
            for order in distance_orders:
                candidates.append(('dist', consume, formula, order))
                candidates.append(('classdist', consume, formula, order))
    for order in recursive_orders:
        candidates.append(('recursive', 'forward', order, 'char-parent'))
    candidates = list(dict.fromkeys(candidates))

    print('candidate                          avg_abs  mean_diff  best  '
          'worst  within100  avg_quality')
    for kind, consume, formula, order in candidates:
        diffs: list[int] = []
        qualities: list[int] = []
        for index in indices:
            block = blocks[index]
            payload = reader.read_payload(block)
            symbols = reader.decode_aux_symbols(block, consume=consume)
            if kind == 'dist':
                parents = distance_parent_symbols(symbols, formula)
                lengths = trie_expansion_lengths(parents, root_zero=False)
                text = candidate_distance_expansion(payload, symbols, formula, order)
            elif kind == 'classdist':
                parents = class_distance_parent_symbols(payload, symbols, formula)
                lengths = trie_expansion_lengths(parents, root_zero=False)
                text = candidate_class_distance_expansion(
                    payload, symbols, formula, order,
                )
            else:
                mapped_order = formula
                # recursive candidates predate consume variants.
                text = candidate_recursive_expansion(payload, symbols, mapped_order)
                lengths = None
            if lengths is None:
                total = len(text)
            else:
                total = block.stored_length + sum(length - 1 for length in lengths)
            diffs.append(total - block.logical_length)
            qualities.append(body_quality_score(text[:args.quality_bytes]))

        avg_abs = sum(abs(diff) for diff in diffs) / len(diffs)
        mean_diff = sum(diffs) / len(diffs)
        within100 = sum(abs(diff) <= 100 for diff in diffs)
        avg_quality = sum(qualities) / len(qualities)
        if kind in ('dist', 'classdist'):
            name = f'dist/{consume}/{formula}/{order}'
            if kind == 'classdist':
                name = f'classdist/{consume}/{formula}/{order}'
        else:
            name = f'recursive/{formula}'
        print(f'{name:<34} {avg_abs:7.1f} {mean_diff:10.1f} '
              f'{min(diffs):5d} {max(diffs):6d} {within100:10d} '
              f'{avg_quality:11.1f}')


def expand_formula_args(formulas: list[str] | None,
                        ranges: list[str] | None,
                        default: list[str]) -> list[str]:
    out = list(formulas or default)
    for spec in ranges or []:
        match = re.fullmatch(r'(-?\d+):(-?\d+)', spec)
        if not match:
            raise ValueError(f'bad formula range {spec!r}; use START:END')
        start, end = (int(match.group(1)), int(match.group(2)))
        step = 1 if end >= start else -1
        for shift in range(start, end + step, step):
            if shift < 0:
                out.append(f'i-s{shift}')
            elif shift > 0:
                out.append(f'i-s+{shift}')
            else:
                out.append('i-s')
    return list(dict.fromkeys(out))


def command_substprobe(reader: OED2Reader, args: argparse.Namespace) -> None:
    block = block_from_args(reader, args)
    payload = reader.read_payload(block)
    symbols = reader.decode_aux_symbols(block)
    orders = (args.order if args.order else
              ['payload', 'payload-rev', 'raw', 'raw-rev',
               'class', 'class-rev', 'char', 'char-rev'])

    print(f'block #{block.index} file=0x{block.file_offset:x} '
          f'logical=0x{block.logical_offset:x}')
    print(f'stored={block.stored_length} logical={block.logical_length} '
          f'high-bit={len(symbols)}')
    print()
    for order in orders:
        text = candidate_recursive_expansion(payload, symbols, order)
        print(f'order={order:<11} len={len(text):5d} '
              f'diff={len(text) - block.logical_length:6d} '
              f'score={text_score(text):5d}')
        if args.show:
            sample = text[:args.show].replace('\n', '\\n')
            print(sample)
            print()


def command_oedlookup(reader: OED2Reader, args: argparse.Namespace) -> None:
    control = reader.read_oed_list(args.name)
    require_exact = True
    full_encoded: bytes | None = None
    table: TableAStruct | None = None
    if args.raw_hex:
        key = bytes.fromhex(args.text)
        source = 'raw hex'
    else:
        query = args.text
        if args.ui_word_primary:
            if args.name != 'word':
                raise SystemExit('--ui-word-primary is only valid for word')
            query = '0a' + query
            require_exact = False
        elif args.ui_word_prefix and args.name == 'word':
            query = '0a' + query
        table_a, _table_b = OED_LIST_TABLES[args.name]
        if table_a is None:
            raise SystemExit(f'no table-A anchor recorded for {args.name!r}')
        table = parse_tablea_struct(reader.read_at_file_offset(table_a, 0x4000))
        full_encoded = encode_tablea_exe(table, query, args.mode, args.mode_hi)
        key = (
            tablea_primary_prefix(full_encoded)
            if args.ui_word_primary else full_encoded
        )
        source = repr(query)

    result = oedlist_original_lookup(
        control, key, args.scan_limit, require_exact=require_exact,
    )
    marker = control.markers[result.marker_block]
    print(f'{args.name}: source={source}')
    if full_encoded is not None and full_encoded != key:
        print(f'  full-encoded={marked_bytes(full_encoded)}')
        print(f'  full-hex={full_encoded.hex(" ")}')
    print(f'  encoded={marked_bytes(key)}')
    print(f'  hex={key.hex(" ")}')
    print(
        f'  marker-block={result.marker_block} '
        f'marker={marked_bytes(marker)}'
    )
    print(
        f'  result={result.reason} blocks_read={result.blocks_read} '
        f'entries_scanned={result.entries_scanned}'
    )
    if result.entry is not None:
        print(f'  candidate={marked_bytes(result.entry)}')
        if table is not None:
            display = decode_tablea_exe(
                table, result.entry, args.mode, args.mode_hi,
            )
            print(f'  display-key={marked_bytes(display)}')
    if result.index is not None:
        print(f'  index={result.index}')
        _table_a, table_b = OED_LIST_TABLES[args.name]
        if table_b is not None:
            left, right = reader.read_oed_pointer_records(
                args.name, result.index, 1,
            )[0]
            print(f'  pointer=({left},{right}) body-logical=0x{right:08x}')


def command_bodyrec(reader: OED2Reader, args: argparse.Namespace) -> None:
    targets: list[tuple[str, int]] = []
    if args.list_name is not None:
        if args.index is None:
            raise SystemExit('--index is required with --list')
        records = reader.read_oed_pointer_records(
            args.list_name, args.index, args.count,
        )
        for i, (_left, right) in enumerate(records, start=args.index):
            targets.append((f'{args.list_name}[{i}]', right))
    else:
        if args.logical is None:
            raise SystemExit('provide a logical offset or use --list/--index')
        for i in range(args.count):
            targets.append((f'0x{args.logical + i:x}', args.logical + i))

    for label, logical in targets:
        if args.join_records:
            pieces: list[bytes] = []
            decoded = 0
            for rel in range(args.join_records):
                try:
                    record = reader.decode_body_record(
                        logical + rel, max_fragments=args.max_fragments,
                    )
                except ValueError as exc:
                    print(f'{label}: logical=0x{logical + rel:x} '
                          f'decode-error: {exc}')
                    break
                pieces.append(record.data)
                decoded += 1
            text = normalized_record_text(b''.join(pieces))
            if not args.keep_newlines:
                text = text.replace('\n', ' ')
            print(f'{label}: logical=0x{logical:08x} '
                  f'joined-records={decoded} bytes={sum(map(len, pieces))}')
            print(text[:args.show])
            print()
            continue

        try:
            record = reader.decode_body_record(
                logical, max_fragments=args.max_fragments,
            )
        except ValueError as exc:
            print(f'{label}: logical=0x{logical:x} decode-error: {exc}')
            continue
        block = record.block
        text = normalized_record_text(record.data)
        if not args.keep_newlines:
            text = text.replace('\n', ' ')
        print(f'{label}: logical=0x{logical:08x} block={block.index} '
              f'rel=0x{logical - block.logical_offset:x} '
              f'window={record.window_index} '
              f'bit={record.bit_start}->{record.bit_end} '
              f'sentinel={record.sentinel_symbol} '
              f'skipped={record.skipped_symbols} '
              f'frags={len(record.fragment_ids)} '
              f'bytes={len(record.data)} '
              f'terminated={int(record.terminated)}')
        print(text[:args.show])
        if args.fragments:
            preview = ' '.join(str(x) for x in
                               record.fragment_ids[:args.fragments])
            print(f'fragments: {preview}')
        print()


def collect_article_targets(reader: OED2Reader, args: argparse.Namespace
                            ) -> list[tuple[str, int]]:
    targets: list[tuple[str, int]] = []
    if args.list_name is not None:
        if args.index is None:
            raise SystemExit('--index is required with --list')
        records = reader.read_oed_pointer_records(
            args.list_name, args.index, args.count,
        )
        for i, (_left, right) in enumerate(records, start=args.index):
            targets.append((f'{args.list_name}[{i}]', right))
    else:
        if args.logical is None:
            raise SystemExit('provide a logical offset or use --list/--index')
        logical = (
            args.logical
            if args.no_enclosing
            else reader.find_body_entry_start(args.logical, args.anchor_search)
        )
        for i in range(args.count):
            targets.append((f'article[{i}]', logical))
            article = reader.decode_body_article(
                logical,
                max_records=args.max_records,
                max_fragments=args.max_fragments,
            )
            if article.end_logical_offset is None:
                break
            logical = article.end_logical_offset
    return targets


def command_article(reader: OED2Reader, args: argparse.Namespace) -> None:
    use_renderish = args.renderish or args.color
    entity_map = None
    rtf_styles = None
    if use_renderish or args.render_codes or args.headgroup:
        if (use_renderish or args.render_codes) and not args.exe:
            raise SystemExit('--renderish/--color/--render-codes requires '
                             '--exe OED.EXE')
        routines = {'latin'} if args.headgroup else None
        entity_map = load_exe_entity_map(args.exe, routines) if args.exe else {}
        if args.render_codes and args.exe:
            rtf_styles = load_exe_rtf_styles(args.exe)

    for label, logical in collect_article_targets(reader, args):
        target_logical = logical
        if not args.no_enclosing:
            try:
                logical = reader.find_body_entry_start(
                    logical, args.anchor_search,
                )
            except ValueError as exc:
                print(f'{label}: logical=0x{target_logical:x} '
                      f'anchor-error: {exc}')
                continue
        try:
            article = reader.decode_body_article(
                logical,
                max_records=args.max_records,
                max_fragments=args.max_fragments,
            )
        except ValueError as exc:
            print(f'{label}: logical=0x{logical:x} decode-error: {exc}')
            continue

        end = (
            'unknown' if article.end_logical_offset is None
            else f'0x{article.end_logical_offset:08x}'
        )
        print(f'{label}: logical=0x{logical:08x} end={end} '
              f'records={len(article.records)} bytes={len(article.data)} '
              f'stop={article.stop_reason}')
        if logical != target_logical:
            print(f'  target logical=0x{target_logical:08x} '
                  f'enclosed by 0x{logical:08x}')
        if args.records:
            for record in article.records[:args.records]:
                text = normalized_record_text(record.data)
                if not args.keep_newlines:
                    text = text.replace('\n', ' ')
                print(f'  0x{record.logical_offset:08x}: {text[:args.show_record]}')
            if len(article.records) > args.records:
                print(f'  ... {len(article.records) - args.records} more records')
        else:
            if args.headgroup:
                assert entity_map is not None
                text = sgml_headgroup_text(article.data, entity_map)
            elif use_renderish:
                assert entity_map is not None
                if args.color:
                    text = sgml_terminal_renderish_text(article.data, entity_map)
                else:
                    atoms = sgml_render_atoms(article.data, entity_map)
                    text = render_atoms_preview(atoms)
            elif args.plainish:
                text = sgml_plainish_text(article.data)
            else:
                text = normalized_record_text(article.data)
                if not args.keep_newlines:
                    text = text.replace('\n', ' ')
            if args.color:
                print(ansi_visible_truncate(text, args.show))
            else:
                print(text[:args.show])
            if args.render_codes:
                assert entity_map is not None
                atoms = sgml_render_atoms(article.data, entity_map)
                shown = 0
                for atom in atoms:
                    if len(atom.source) == 1 and atom.source == atom.preview:
                        continue
                    suffix = ''
                    rtf = style_rtf_summary(atom.style, rtf_styles)
                    if rtf:
                        suffix = f' rtf={rtf}'
                    print(f'  {atom.source:<16} out={atom.out_hex:<12} '
                          f'style={atom.style_hex:<12} '
                          f'{atom.preview}{suffix}')
                    shown += 1
                    if shown >= args.render_codes:
                        break
        print()


def command_entities(reader: OED2Reader, args: argparse.Namespace) -> None:
    entity_map = load_exe_entity_map(args.exe) if args.exe else None
    rtf_styles = load_exe_rtf_styles(args.exe) if args.exe else None
    combined: Counter[str] = Counter()
    for label, logical in collect_article_targets(reader, args):
        target_logical = logical
        if not args.no_enclosing:
            try:
                logical = reader.find_body_entry_start(
                    logical, args.anchor_search,
                )
            except ValueError as exc:
                print(f'{label}: logical=0x{target_logical:x} '
                      f'anchor-error: {exc}')
                continue
        try:
            article = reader.decode_body_article(
                logical,
                max_records=args.max_records,
                max_fragments=args.max_fragments,
            )
        except ValueError as exc:
            print(f'{label}: logical=0x{logical:x} decode-error: {exc}')
            continue

        counts = sgml_entity_refs(article.data)
        combined.update(counts)
        known = 0
        if entity_map is not None:
            known = sum(
                count for token, count in counts.items()
                if token in entity_map or token + '.' in entity_map
            )
        unknown = sum(counts.values()) - known
        suffix = ''
        if entity_map is not None:
            suffix = f' known={known} unknown={unknown}'
        print(f'{label}: logical=0x{logical:08x} '
              f'entities={sum(counts.values())} unique={len(counts)}{suffix}')
        for token, count in counts.most_common(args.limit):
            preview = ''
            if entity_map is not None:
                mapping = entity_map.get(token) or entity_map.get(token + '.')
                if mapping is not None:
                    value = entity_mapping_preview(mapping)
                    out, style = entity_mapping_vectors(mapping)
                    value_note = value if value is not None else '<styled>'
                    preview = (f' -> {value_note} '
                               f'out={out.hex(" ") or "-"} '
                               f'style={style.hex(" ") or "-"}')
                    rtf = style_rtf_summary(style, rtf_styles)
                    if rtf:
                        preview += f' rtf={rtf}'
                else:
                    preview = ' -> ?'
            print(f'  {count:5d} {token}{preview}')
        print()

    if args.count > 1:
        print(f'combined: entities={sum(combined.values())} '
              f'unique={len(combined)}')
        for token, count in combined.most_common(args.limit):
            print(f'  {count:5d} {token}')


def command_headgroups(reader: OED2Reader, args: argparse.Namespace) -> None:
    entity_map = load_exe_entity_map(args.exe, {'latin'}) if args.exe else {}
    for label, logical in collect_article_targets(reader, args):
        target_logical = logical
        if not args.no_enclosing:
            try:
                logical = reader.find_body_entry_start(
                    logical, args.anchor_search,
                )
            except ValueError as exc:
                print(f'{label}\t0x{target_logical:08x}\tanchor-error: {exc}')
                continue
        try:
            article = reader.decode_body_article(
                logical,
                max_records=args.max_records,
                max_fragments=args.max_fragments,
            )
        except ValueError as exc:
            print(f'{label}\t0x{logical:08x}\tdecode-error: {exc}')
            continue
        text = sgml_headgroup_text(article.data, entity_map)
        target = (
            '' if logical == target_logical
            else f'\ttarget=0x{target_logical:08x}'
        )
        print(f'{label}\t0x{logical:08x}\t{text}{target}')


def command_find(reader: OED2Reader, args: argparse.Namespace) -> None:
    needle = args.text.encode('ascii')
    count = 0
    for block, pos in reader.iter_payload_hits(needle):
        payload = reader.read_payload(block)
        start = max(0, pos - args.context)
        end = min(len(payload), pos + len(needle) + args.context)
        snippet = normalize_highbit(payload[start:end]).replace('\n', ' ')
        print(f'block={block.index} file=0x{block.file_offset:x} '
              f'payload=0x{pos:x} logical~0x{block.logical_offset + pos:x}')
        print(snippet)
        print()
        count += 1
        if count >= args.limit:
            break
    if count == 0:
        print('no hits')


def command_tags(reader: OED2Reader, args: argparse.Namespace) -> None:
    for tag, count in reader.tag_counts(args.limit):
        print(f'{tag.decode("ascii", "replace"):<12} {count:>8}')


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path')
    sub = ap.add_subparsers(dest='command', required=True)

    sub.add_parser('info')
    sub.add_parser('header')
    sub.add_parser('bodyctl')

    p_origmap = sub.add_parser('origmap')
    p_origmap.add_argument('--size', type=parse_int, default=64)
    p_origmap.add_argument('--contains')
    p_origmap.add_argument('--notes', action='store_true')

    p_oedlist = sub.add_parser('oedlist')
    p_oedlist.add_argument('name', nargs='?', default='word')
    p_oedlist.add_argument('--list-names', action='store_true')
    p_oedlist.add_argument('--summary', action='store_true')
    p_oedlist.add_argument('--block', type=int, default=0)
    p_oedlist.add_argument('--limit', type=int, default=40)
    p_oedlist.add_argument('--pointers', action='store_true')
    p_oedlist.add_argument('--hex', action='store_true',
                           help='show raw decoded key bytes')

    p_oedlookup = sub.add_parser('oedlookup')
    p_oedlookup.add_argument('name', choices=sorted(OED_LIST_TABLES))
    p_oedlookup.add_argument('text')
    p_oedlookup.add_argument('--raw-hex', action='store_true',
                             help='treat text as a hex-encoded raw key')
    p_oedlookup.add_argument('--ui-word-prefix', action='store_true',
                             help='prepend the default 0a word prefix before encoding')
    p_oedlookup.add_argument('--ui-word-primary', action='store_true',
                             help='mimic seg3:35f8 word lookup: prepend 0a, keep primary bytes, prefix-match')
    p_oedlookup.add_argument('--mode', type=parse_int, default=0x0100)
    p_oedlookup.add_argument('--mode-hi', type=parse_int, default=0)
    p_oedlookup.add_argument('--scan-limit', type=int,
                             help='diagnostic cap on the original forward scan')

    p_ptrs = sub.add_parser('ptrs')
    p_ptrs.add_argument('name', choices=sorted(OED_LIST_TABLES))
    p_ptrs.add_argument('--start', type=int, default=0)
    p_ptrs.add_argument('--count', type=int)
    p_ptrs.add_argument('--summary', action='store_true')
    p_ptrs.add_argument('--snippets', action='store_true')
    p_ptrs.add_argument('--context', type=parse_int, default=60)
    p_ptrs.add_argument('--snippet-chars', type=int, default=100)

    p_tablea = sub.add_parser('tablea')
    p_tablea.add_argument('name', nargs='?', default='word',
                          choices=sorted(OED_LIST_TABLES))
    p_tablea.add_argument('--all', action='store_true')
    p_tablea.add_argument('--size', type=parse_int, default=0x4000)
    p_tablea.add_argument('--start', type=int, default=0)
    p_tablea.add_argument('--words', type=int, default=32)
    p_tablea.add_argument('--text', action='store_true')
    p_tablea.add_argument('--text-start', type=parse_int)
    p_tablea.add_argument('--text-bytes', type=parse_int, default=240)
    p_tablea.add_argument('--records', action='store_true')
    p_tablea.add_argument('--record-limit', type=int, default=40)
    p_tablea.add_argument('--struct', action='store_true',
                          help='parse using the EXE-derived offset arrays')
    p_tablea.add_argument('--record-indexes', type=int, nargs='*',
                          help='dump structured Table-A records by index')
    p_tablea.add_argument('--map-bytes', nargs='*',
                          help='show direct byte to Table-A record mappings')
    p_tablea.add_argument('--encode', nargs='*',
                          help='encode strings through the simple Table-A record copier')
    p_tablea.add_argument('--encode-exe', nargs='*',
                          help='encode strings through seg5:4688 rules')
    p_tablea.add_argument('--decode-exe-hex', nargs='*',
                          help='decode hex keys through seg5:4c40 rules')
    p_tablea.add_argument('--mode', type=parse_int, default=0x0100,
                          help='seg5:4688 mode word, default word list')
    p_tablea.add_argument('--mode-hi', type=parse_int, default=0)

    p_sparse = sub.add_parser('sparse')
    p_sparse.add_argument('name', nargs='?', default='startup-a',
                          choices=sorted(OED_SPARSE_INDEXES))
    p_sparse.add_argument('--all', action='store_true')
    p_sparse.add_argument('--pages', type=int, default=2)
    p_sparse.add_argument('--words', type=int, default=16)
    p_sparse.add_argument('--longs', type=int, default=8)

    p_blocks = sub.add_parser('blocks')
    p_blocks.add_argument('--limit', type=int, default=20)

    p_bodycheck = sub.add_parser('bodycheck')
    p_bodycheck.add_argument('--samples', type=int, default=8)

    p_dump = sub.add_parser('dump')
    p_dump.add_argument('--block', type=int)
    p_dump.add_argument('--offset', type=parse_int)
    p_dump.add_argument('--logical', type=parse_int)
    p_dump.add_argument('--payload-offset', type=parse_int, default=0)
    p_dump.add_argument('--size', type=parse_int, default=512)
    p_dump.add_argument('--mode', choices=('hex', 'text', 'both'),
                        default='both')
    p_dump.add_argument('--mark-highbit', action='store_true')

    p_aux = sub.add_parser('aux')
    p_aux.add_argument('--block', type=int)
    p_aux.add_argument('--offset', type=parse_int)
    p_aux.add_argument('--logical', type=parse_int)
    p_aux.add_argument('--limit', type=int, default=40)

    p_classes = sub.add_parser('classes')
    p_classes.add_argument('--block', type=int)
    p_classes.add_argument('--offset', type=parse_int)
    p_classes.add_argument('--logical', type=parse_int)
    p_classes.add_argument('--limit', type=int, default=20)

    p_table5 = sub.add_parser('table5')
    p_table5.add_argument('--offset', type=parse_int,
                          default=CANDIDATE_FRAGMENT_TABLE_START)
    p_table5.add_argument('--width', type=parse_int,
                          default=CANDIDATE_FRAGMENT_RECORD_SIZE)
    p_table5.add_argument('--count', type=parse_int, default=64)
    p_table5.add_argument('--show', type=int, default=32)

    p_table5_profile = sub.add_parser('table5-profile')
    p_table5_profile.add_argument('--start', type=parse_int,
                                  default=CANDIDATE_FRAGMENT_TABLE_START)
    p_table5_profile.add_argument('--end', type=parse_int,
                                  default=CANDIDATE_FRAGMENT_TABLE_END)
    p_table5_profile.add_argument('--chunk', type=parse_int,
                                  default=0x10000)

    p_table5_runs = sub.add_parser('table5-runs')
    p_table5_runs.add_argument('--start', type=parse_int,
                               default=CANDIDATE_FRAGMENT_TABLE_START)
    p_table5_runs.add_argument('--end', type=parse_int,
                               default=CANDIDATE_FRAGMENT_TABLE_END)
    p_table5_runs.add_argument('--limit', type=int, default=40)

    p_bitrange = sub.add_parser('bitrange')
    p_bitrange.add_argument('index', type=parse_int)
    p_bitrange.add_argument('--table-offset', type=parse_int,
                            default=CANDIDATE_FRAGMENT_TABLE_START)
    p_bitrange.add_argument('--stream-offset', type=parse_int,
                            default=CANDIDATE_FRAGMENT_STREAM_START)
    p_bitrange.add_argument('--limit', type=int, default=96)

    p_auxmap = sub.add_parser('auxmap')
    p_auxmap.add_argument('--block', type=int)
    p_auxmap.add_argument('--offset', type=parse_int)
    p_auxmap.add_argument('--logical', type=parse_int)
    p_auxmap.add_argument('--limit', type=int, default=40)
    p_auxmap.add_argument('--table-offset', type=parse_int,
                          default=CANDIDATE_FRAGMENT_TABLE_START)
    p_auxmap.add_argument('--width', type=parse_int,
                          default=CANDIDATE_FRAGMENT_RECORD_SIZE)

    p_substprobe = sub.add_parser('substprobe')
    p_substprobe.add_argument('--block', type=int)
    p_substprobe.add_argument('--offset', type=parse_int)
    p_substprobe.add_argument('--logical', type=parse_int)
    p_substprobe.add_argument('--order', action='append',
                              choices=('payload', 'payload-rev', 'raw',
                                       'raw-rev', 'char', 'char-rev',
                                       'class', 'class-rev'))
    p_substprobe.add_argument('--show', type=int, default=500)

    p_bodytrie = sub.add_parser('bodytrie')
    p_bodytrie.add_argument('--block', type=int)
    p_bodytrie.add_argument('--offset', type=parse_int)
    p_bodytrie.add_argument('--logical', type=parse_int)
    p_bodytrie.add_argument('--consume', choices=('forward', 'reverse'),
                            default='forward')
    p_bodytrie.add_argument('--shift', type=int, action='append',
                            default=None)
    p_bodytrie.add_argument('--root-zero', action='store_true')
    p_bodytrie.add_argument('--scan', action='store_true')
    p_bodytrie.add_argument('--start-block', type=int, default=0)
    p_bodytrie.add_argument('--count', type=int, default=12)

    p_bodydist = sub.add_parser('bodydist')
    p_bodydist.add_argument('--block', type=int)
    p_bodydist.add_argument('--offset', type=parse_int)
    p_bodydist.add_argument('--logical', type=parse_int)
    p_bodydist.add_argument('--consume', choices=('forward', 'reverse'),
                            default='forward')
    p_bodydist.add_argument('--scope', choices=('global', 'class'),
                            default='global')
    p_bodydist.add_argument('--formula', action='append')
    p_bodydist.add_argument('--formula-range', action='append',
                            help='inclusive shift range, e.g. -6:6 for i-s+k')
    p_bodydist.add_argument('--order', choices=('parent-char', 'char-parent'),
                            default='parent-char')
    p_bodydist.add_argument('--scan', action='store_true')
    p_bodydist.add_argument('--start-block', type=int, default=0)
    p_bodydist.add_argument('--count', type=int, default=12)
    p_bodydist.add_argument('--show', type=parse_int, default=0)

    p_bodyfit = sub.add_parser('bodyfit')
    p_bodyfit.add_argument('--start-block', type=int, default=0)
    p_bodyfit.add_argument('--count', type=int, default=20)
    p_bodyfit.add_argument('--consume', action='append',
                           choices=('forward', 'reverse'),
                           default=None)
    p_bodyfit.add_argument('--formula', action='append', default=None)
    p_bodyfit.add_argument('--formula-range', action='append', default=None,
                           help='inclusive shift range, e.g. -6:6 for i-s+k')
    p_bodyfit.add_argument('--distance-order', action='append',
                           choices=('parent-char', 'char-parent'),
                           default=None)
    p_bodyfit.add_argument('--recursive-order', action='append',
                           choices=('payload', 'payload-rev', 'raw', 'raw-rev',
                                    'class', 'class-rev', 'char', 'char-rev'),
                           default=None)
    p_bodyfit.add_argument('--quality-bytes', type=parse_int, default=1800)

    p_bodyrec = sub.add_parser('bodyrec')
    p_bodyrec.add_argument('logical', type=parse_int, nargs='?')
    p_bodyrec.add_argument('--list', dest='list_name',
                           choices=sorted(OED_LIST_TABLES))
    p_bodyrec.add_argument('--index', type=int)
    p_bodyrec.add_argument('--count', type=int, default=1)
    p_bodyrec.add_argument('--show', type=parse_int, default=600)
    p_bodyrec.add_argument('--max-fragments', type=int, default=8192)
    p_bodyrec.add_argument('--fragments', type=int, default=0)
    p_bodyrec.add_argument('--join-records', type=int, default=0,
                           help='join this many consecutive body records '
                           'from each selected logical offset')
    p_bodyrec.add_argument('--keep-newlines', action='store_true')

    p_article = sub.add_parser('article')
    p_article.add_argument('logical', type=parse_int, nargs='?')
    p_article.add_argument('--list', dest='list_name',
                           choices=sorted(OED_LIST_TABLES))
    p_article.add_argument('--index', type=int)
    p_article.add_argument('--count', type=int, default=1)
    p_article.add_argument('--show', type=parse_int, default=4000)
    p_article.add_argument('--show-record', type=parse_int, default=160)
    p_article.add_argument('--records', type=int, default=0,
                           help='show this many component body records')
    p_article.add_argument('--max-records', type=int, default=12000)
    p_article.add_argument('--max-fragments', type=int, default=8192)
    p_article.add_argument('--anchor-search', type=int, default=12000,
                           help='records to scan backward for enclosing <e>')
    p_article.add_argument('--no-enclosing', action='store_true',
                           help='start exactly at the supplied logical record')
    p_article.add_argument('--plainish', action='store_true',
                           help='strip SGML tags for a rough preview')
    p_article.add_argument('--renderish', action='store_true',
                           help='strip SGML tags and replace known entities '
                           'using mappings extracted from OED.EXE')
    p_article.add_argument('--color', action='store_true',
                           help='emit ANSI colors for --renderish output '
                           '(implies --renderish)')
    p_article.add_argument('--headgroup', action='store_true',
                           help='approximate the original seg1:ce44 '
                           'headword/headgroup text extractor')
    p_article.add_argument('--render-codes', type=int, default=0,
                           help='show this many non-literal renderer atoms '
                           'with exact output/style bytes')
    p_article.add_argument('--exe',
                           help='path to OED.EXE for entity/render metadata')
    p_article.add_argument('--keep-newlines', action='store_true')

    p_entities = sub.add_parser('entities')
    p_entities.add_argument('logical', type=parse_int, nargs='?')
    p_entities.add_argument('--list', dest='list_name',
                            choices=sorted(OED_LIST_TABLES))
    p_entities.add_argument('--index', type=int)
    p_entities.add_argument('--count', type=int, default=1)
    p_entities.add_argument('--limit', type=int, default=40)
    p_entities.add_argument('--max-records', type=int, default=12000)
    p_entities.add_argument('--max-fragments', type=int, default=8192)
    p_entities.add_argument('--anchor-search', type=int, default=12000,
                            help='records to scan backward for enclosing <e>')
    p_entities.add_argument('--no-enclosing', action='store_true',
                            help='start exactly at the supplied logical record')
    p_entities.add_argument('--exe',
                            help='path to OED.EXE for known/unknown coverage')

    p_headgroups = sub.add_parser('headgroups')
    p_headgroups.add_argument('logical', type=parse_int, nargs='?')
    p_headgroups.add_argument('--list', dest='list_name',
                              choices=sorted(OED_LIST_TABLES))
    p_headgroups.add_argument('--index', type=int)
    p_headgroups.add_argument('--count', type=int, default=12)
    p_headgroups.add_argument('--max-records', type=int, default=12000)
    p_headgroups.add_argument('--max-fragments', type=int, default=8192)
    p_headgroups.add_argument('--anchor-search', type=int, default=12000,
                              help='records to scan backward for enclosing <e>')
    p_headgroups.add_argument('--no-enclosing', action='store_true',
                              help='start exactly at the supplied logical record')
    p_headgroups.add_argument('--exe',
                              help='path to OED.EXE for Latin entity mappings')

    p_find = sub.add_parser('find')
    p_find.add_argument('text')
    p_find.add_argument('--limit', type=int, default=10)
    p_find.add_argument('--context', type=parse_int, default=160)

    p_tags = sub.add_parser('tags')
    p_tags.add_argument('--limit', type=int, default=30)

    return ap


def main(argv: list[str]) -> int:
    args = build_arg_parser().parse_args(argv)
    if not os.path.exists(args.path):
        print(f'error: {args.path} does not exist', file=sys.stderr)
        return 1

    reader = OED2Reader(args.path)
    commands = {
        'info': command_info,
        'header': command_header,
        'bodyctl': command_bodyctl,
        'origmap': command_origmap,
        'oedlist': command_oedlist,
        'oedlookup': command_oedlookup,
        'ptrs': command_ptrs,
        'tablea': command_tablea,
        'sparse': command_sparse,
        'blocks': command_blocks,
        'bodycheck': command_bodycheck,
        'dump': command_dump,
        'aux': command_aux,
        'classes': command_classes,
        'table5': command_table5,
        'table5-profile': command_table5_profile,
        'table5-runs': command_table5_runs,
        'bitrange': command_bitrange,
        'auxmap': command_auxmap,
        'substprobe': command_substprobe,
        'bodytrie': command_bodytrie,
        'bodydist': command_bodydist,
        'bodyfit': command_bodyfit,
        'bodyrec': command_bodyrec,
        'article': command_article,
        'entities': command_entities,
        'headgroups': command_headgroups,
        'find': command_find,
        'tags': command_tags,
    }
    commands[args.command](reader, args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
