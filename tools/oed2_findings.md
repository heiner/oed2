# OED2.DAT — findings

Static analysis of `OED2.DAT` (635,400,192 bytes, dated 1992-05-27)
from the OED Second Edition CD-ROM. All findings derived from
read-only inspection; no Wine, no execution.

## ISO contents

The CD-ROM image currently contains only:

```
/OED2.DAT   635,400,192 bytes   1992-05-27
/SETUP.EXE      991,265 bytes   1996-05-31
```

`SETUP.EXE` is a Windows 3.x NE executable and appears to be a Wise /
QuickWin installer stub.  The actual viewer files are probably packed in
the installer or otherwise generated during installation; they are not
plain files in the ISO root.

## Installed original reader

The original Win 3.1 program has now been installed under `oeddos/`.
The useful installed files are:

```
oeddos/OED.EXE        NE Win16 executable; contains OED reader/search code
oeddos/XWI321.DLL     XVT runtime/UI library
oeddos/XWI321TE.DLL   XVT text/edit library
oeddos/OED.HLP        Windows help
```

`OED.EXE`, not the `XWI321` DLLs, owns the OED data-file paths and
OED-specific search strings.  Useful string hits include:

```
%c:\oed2.dat
CD-ROM not found
Failure in opening oed files
Cannot initialize data files
Searching the whole Dictionary
```

`tools/ne_inspect.py` was added as a small NE-format inspector:

```
python3 tools/ne_inspect.py oeddos/OED.EXE info
python3 tools/ne_inspect.py oeddos/OED.EXE segments
python3 tools/ne_inspect.py oeddos/OED.EXE names
python3 tools/ne_inspect.py oeddos/OED.EXE xrefs --file-offset 420701
python3 tools/ne_inspect.py oeddos/OED.EXE disasm 4 0x1a20 --count 80
python3 tools/ne_inspect.py oeddos/OED.EXE dat-pairs --segment 4
python3 tools/ne_inspect.py oeddos/OED.EXE calls --segment 4 --target 0x2aea --context 40
python3 tools/ne_inspect.py oeddos/OED.EXE procs --segment 6 --start 0x1c00 --end 0x2100
python3 tools/ne_inspect.py oeddos/OED.EXE extract 4 /tmp/oed_seg4.bin
ndisasm -b 16 -o 0x1700 -e 0x1700 /tmp/oed_seg4.bin | head -220
```

Important NE facts for `OED.EXE`:

  - 9 segments total: 7 code segments, one placeholder-ish data segment,
    and segment 9 as the main data segment.
  - Segment 9 contains the OED strings above.
  - The `%c:\oed2.dat` and `Failure in opening oed files` data offsets
    have code references in segment 4.
  - Segment 4 offset `0x1700` is the current best target for the original
    data-file initialization routine.

The segment-4 `0x1700` routine:

  - allocates a main context of `0xa0` bytes;
  - tries to build/open `%c:\oed2.dat`, scanning drive letters from
    `c` through `z`;
  - stores two opened DAT file handles/pointers in the context
    (`context+0x76/0x78` and `context+0x12/0x14`);
  - allocates/reads several structures from fixed OED2.DAT offsets.

Constants seen directly in the original code:

| Win16 pair | Absolute offset | Notes |
|---|---:|---|
| `0x1670:0x1000` | `0x16701000` | pre-body control area just before the first framed body block |
| `0x155b:0x2800` | `0x155b2800` | sparse zero-heavy late control/index block |
| `0x1551:0x2800` | `0x15512800` | sparse zero-heavy late control/index block |
| `0x18ce:0x0000` | `0x18ce0000` | dense high-bit body/index stream |
| `0x143f:0x3000` | `0x143f3000` | low/high mixed control block |
| `0x145f:0xe800` | `0x145fe800` | table-like control block |
| `0x1541:0x6000` | `0x15416000` | used if `title.lst` cannot be opened |
| `0x1460:0x2800` | `0x14602800` | companion table for the word/POS/date lists |

This is a major validation of the earlier file-only work: the original
reader hard-codes offsets in the same late-data neighbourhood that our
body-block and pre-body table probes identified.

The disassembly now exposes a repeated "list" loader pattern.  The
reader sets a list id, loads three DAT ranges, then associates that range
with an in-program list title.  `tools/oed2_reader.py origmap` records
the current extracted map and samples each referenced region:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT origmap
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT origmap --contains list
```

Original-reader list anchors found so far:

| Reader list | Id | DAT anchors |
|---|---:|---|
| Word List | `0x0100` | `0x145fe800`, `0x14602800`, `0x143f3000` |
| Part of Speech Word List | `0x0100` | reuses the Word List anchors |
| First Date Word List | `0x0100` | reuses the Word List anchors |
| Phrase List | `0x0101` | `0x14ac9800`, `0x14acd800`, `0x1499f000` |
| Variant Form List | `0x0102` | `0x14e15800`, `0x14e19800`, `0x14c18800` |
| Greek List | `0x0103` | `0x15053800`, `0x15054800`, `0x14fdb800` |
| Phonetics List | `0x0104` | `0x152e9800`, `0x152ec000`, `0x25bb1000` |
| Cited Forms | `0x0202` / `0x0203` | `0x13b08000`, `0x13a1b000`, `0x13d01000`, `0x13cff800` |
| Work Titles | `0x0201` | `0x12dee800`, `0x131e8800` |

The executable now corroborates the three-anchor interpretation at the
routine level.  Segment 4 offset `0x2a0a` is the repeated list-open
wrapper used by the UI list commands.  Its argument order is:

```
context, list_id, 0, control_0ffa, table_B, table_A
```

Inside that wrapper:

  - `table_A` is opened through the helper reached by far-call target
    `0x4260` and stored at `context+0x6e/0x70`;
  - `control_0ffa` is opened through the helper reached by target
    `0x2aea` and stored at `context+0x06/0x08`;
  - target `0x2b98` links the opened table-A object to the opened
    control/list object;
  - target `0x4f3a` initializes a 0x20-sized working buffer on the
    opened control/list object;
  - `table_B` is not opened there as a structured object; its DAT
    pointer is stored directly at `context+0x16/0x18`, matching the
    Python reader's current "ordinal -> table-B row -> body logical
    offset" model.

Segment 4's startup path primes the default word list with the same
pieces: it opens word `control_0ffa` at `0x143f3000`, opens word
`table_A` at `0x145fe800`, links them, initializes the 0x20 buffer, and
stores word `table_B` as `0x14602800` at `context+0x82/0x84`.

The `0x0ffa` signature recurs at several third-anchor/control blocks
(`0x143f3000`, `0x1499f000`, `0x14c18800`, `0x14fdb800`,
`0x25bb1000`, and the cited-form/work-title indexes).  The `0xfb0f`
signature marks another original-reader index family at
`0x15512800`, `0x155b2800`, `0x15713800`, `0x15776000`,
`0x1584f800`, `0x15b83800`, and `0x16079800`.  The corresponding
table-B anchors often begin with small big-endian-looking longs and
sparse zeros.  This looks like a family of related list/index formats
rather than article body storage.

The `0x0ffa` blocks are now partially decoded.  They are a big-endian
relative of the PC-Wörterbuch `Lista` structure:

```
>HHHHHHH header:
  magic            0x0ffa
  version          number of 0x800 pages before block data
  block_count
  block_size       observed 0x800
  max_key_bytes    allocated current-key/display-key buffer length
  fragment_bytes   NUL-terminated fragment table length
  marker_bytes     LF-terminated per-block marker table length

fragment_bytes of NUL-terminated fragments
one big-endian 32-bit count-base value
block_count signed big-endian 32-bit cumulative/count deltas
block_count first-fragment-skip bytes
marker_bytes of LF-terminated block markers
padding to version * block_size
block_count fixed-size compressed blocks
```

Entry counts use the same family of formula as `.AND`, widened to signed
32-bit:

```
count[0] = cumulative[0]
count[n] = cumulative[n] - cumulative[n-1] + count_base
```

The old `Lista` nibble-prefix block decoder works after adapting the
endianness and metadata widths.  `tools/oed2_reader.py` now exposes this
as:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlist --list-names
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlist word --summary
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlist word --block 0
```

Decoded list summaries:

| List | Control | Blocks | Entries (delta-derived) | Block data range |
|---|---:|---:|---:|---|
| word | `0x143f3000` | 1039 | 473,257 | `0x143f7000..0x145fe800` |
| phrase | `0x1499f000` | 592 | 169,429 | `0x149a1800..0x14ac9800` |
| variant | `0x14c18800` | 983 | 221,640 | `0x14c1c800..0x14e08000` |
| greek | `0x14fdb800` | 236 | 40,650 | `0x14fdd800..0x15053800` |
| phonetics | `0x25bb1000` | 1155 | 152,418 | `0x25bb5800..0x25df7000` |
| cited1 | `0x13cff800` | 2 | 524 | `0x13d00000..0x13d01000` |
| cited2 | `0x13a1b000` | 470 | 228,816 | `0x13a1d000..0x13b08000` |
| work1 | `0x12dee800` | 144 | 77,050 | `0x12df0000..0x12e38000` |
| work2 | `0x131e8800` | 1078 | 237,332 | `0x131ed000..0x13408000` |

All known `0x0ffa` lists now have non-negative per-block counts under
this formula.

This is the first complete inherited-format win in OED2.DAT: a large
part of the original reader's navigation/search lists now has a concrete
parser, not just offsets and entropy bands.  The decoded entries are
still OED collation/notation keys.  `seg5:4c40` now expands the visible
text portion, including Table-A records such as the encoded space in
`ABSOLUTEADDRESS`, but the two-byte hidden prefix still needs the final
UI label map.

## Original list lookup path

The NE relocation parser now expands relocation chains.  This fixed
several misleading far-call annotations: for example, segment 4 calls
`seg3:4f70` from `seg4:2c1c` and `seg4:333c`, even though the raw
segment words in the instruction stream look unrelated before relocation
chain expansion.

The `0x0ffa` list object parse had one important off-by-four error in
the Python reader.  `seg5:3494` reads the fragment area, then a 32-bit
count base into `obj+0x250/0x252`, then the per-block 32-bit count table.
The Python reader used to treat that first count-base value as the first
table entry.  After matching the assembly order, the word list has
473,257 rows, and decoded keys are normal OED collation keys:
`ABSOLUTE<03>:a<03>...` at index 1000, `ABSOLUTELY<03>Ba<03>...` at
index 1006, etc.

`seg5:2d4c` is the exact-list wrapper:

1. lock the `0x0ffa` list object;
2. encode the caller's query through `seg5:4688` using the attached
   Table-A object;
3. call `seg5:528c` to find an exact key.

`seg5:528c` uses:

- `seg5:53bc`: choose a block with the original marker guide;
- `seg5:54ee`: scan forward until the current decoded key has the query
  as a prefix;
- `seg7:6d9c`: final exact `strcmp`.

The visible Word Look-up dialog follows a related but not identical path
in `seg3:35f8`.  In word mode it:

1. skips the two leading bytes in the source UI buffer;
2. writes default hidden bytes `0x30 0x61` (`"0a"`);
3. appends the visible query text;
4. calls `seg5:4688`;
5. copies only bytes greater than `0x03` from the encoded result back into
   the active query buffer, stopping at the first control byte;
6. calls `seg5:306c`, which performs the marker-guide block choice and
   accepts the first decoded list key with that primary prefix.

So the typed word `absolute` becomes:

```
full Table-A key: ABSOLUTE<03>0a<03><03><03><03><03><03><03><03>
UI primary key:  ABSOLUTE
```

The Python probe now mirrors both the exact helper and the UI primary
lookup without a Python-side global binary search:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT tablea word --struct --encode-exe 0aabsolute
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlookup word absolute --ui-word-primary
```

The second command chooses marker block 1 (`ABJUN`), scans 494 decoded
entries, and returns index 1000:

```
candidate=ABSOLUTE<03>:a<03><03><03><03><03><03><03><03>
display-key=:aabsolute
pointer=(803,126854) body-logical=0x0001ef86
```

`seg5:4c40` is the inverse display expander.  For word keys it copies the
two hidden bytes after the separator, then uses the secondary stream to
lowercase/uppercase primary bytes or expand Table-A records.  The Python
decoder now shows `ABSOLUTE<03>:a...` as `:aabsolute`, and
`ABSOLUTEADDRESS<03>1a...ma...` as `1aabsolute address`; the two-byte
prefix still needs the UI label map so it can be rendered as
`absolute a.`.

The second anchor in each main list family is now strongly identified as
a big-endian 8-byte pointer table.  `tools/oed2_reader.py ptrs` reads
records as:

```
>II:
  a   index/cross-index value (role still being narrowed)
  b   article-body logical offset, usually into the framed body stream
```

The summary probe scans one pointer record per decoded list entry:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT ptrs word --summary
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT ptrs phrase --summary
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT ptrs word --start 0 --count 16 --snippets
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlist word --block 0 --limit 24 --pointers
```

Current table-B evidence:

| List | Table-B | Records scanned | `b` in body blocks | Sentinels |
|---|---:|---:|---:|---:|
| word | `0x14602800` | 473,257 | 473,257 | 0 |
| phrase | `0x14acd800` | 169,429 | 169,429 | 0 |
| variant | `0x14e19800` | 221,640 | 221,640 | 0 |
| greek | `0x15054800` | 40,650 | 40,650 | 0 |
| phonetics | `0x152ec000` | 152,418 | 152,418 | 0 |

For these main lists, `b` is now confirmed as a body logical offset:
after switching the body-block reader from heuristic scanning to the
original body-control header, every row lands in a body block with no
between-block misses.

The `--snippets` view deliberately labels previews as `raw~...`: it
shows bytes near the same relative position in the stored payload only.
Perfect article seeks still require the full high-bit fragment /
substitution decoder, because table-B offsets appear to point into the
decoded logical article stream rather than simply into compressed payload
bytes.

`oedlist --pointers` joins decoded list ordinals to table-B rows.  This
is the current best model of the lookup path: a list block yields compact
collation/notation keys, the entry's global ordinal selects an 8-byte
table-B row, and that row's second word seeks into the article-body
logical stream.  Early word-list rows show this directly: ordinals 8..14
map to body block 1 at logical-relative offsets `0x21d`, `0x304`,
`0xaef`, `0xdcc`, `0xf22`, and `0xfa5`.

The first anchor in each list family is now identified as a
collation/display table rather than a pointer table.  It begins with
four big-endian 16-bit words, then numeric offset/code arrays, then a
compact text map.  `tools/oed2_reader.py tablea` profiles it:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT tablea --all
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT tablea word --text
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT tablea greek --text
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT tablea word --records --record-limit 80
```

Observed table-A families:

| Lists | Table-A profile |
|---|---|
| word, phrase, cited1, cited2 | same SHA-1 prefix `b81238086c42`, header `[837, 755, 2511, 7422]` |
| variant | same header and visible text map, but differs from word in part of the numeric arrays |
| greek | Greek-specific header `[158, 97, 474, 1207]` and Greek entity map |
| phonetics | Phonetic-specific header `[592, 507, 1776, 4865]` and phonetic glyph map |

The word table's text-coded map starts with ordinary letters and then
OED entity names:

```
text-start 0x1b8e:
aA00 bB01 ... zZ0p AA0q BB0r ... ZZ1f
&Alpha.A1g &alpha.A1h &Aacu.A1i &aacu.A1k ...
```

The Greek table starts with Greek-specific entities:

```
&gAacu.A00 &gaacu.A01 &gamac.A02 &gauml.A03 ...
&alpha.A09 &Aasper.A0a &Alenis.A0b ...
```

`tablea --records` now parses this printable map into records of:

```
source-token -> normalized spelling, two-character base-36 rank code
```

Examples:

| Table | Text-map start | Parsed examples |
|---|---:|---|
| word / phrase / cited / variant | `0x1b8e` | `a -> A code 00`, `A -> A code 0q`, `&Alpha. -> A code 1g`, `&Aacu. -> A code 1i` |
| greek | `0x680` | `&gAacu. -> A code 00`, `&gaacu. -> A code 01`, `&alenis. -> A code 06` |
| phonetics | `0x13e0` | `a -> ! code 00`, `A -> " code 01`, `X -> # code 02`, `6 -> $ code 03` |

The rank codes are monotone in base-36 order (`00`, `01`, ... `0z`,
`10`, ...).  The list entries appear to store these compact rank codes
plus control bytes, not final display text.  The next table-A step is to
invert this record stream and decode list keys through it, using the
numeric arrays as the original program's acceleration layer.

This is almost certainly the missing layer that converts decoded
`oedlist` keys such as `ABJUE<03>...` into the real list strings shown
by the original program.  The remaining unknown is the exact grammar of
the table-A text records and how the preceding numeric arrays accelerate
lookup/collation.

## Body decoder in `OED.EXE` segment 5

The body materializer is now identified in segment 5:

| Routine | Role |
|---|---|
| `seg5:2542` | reads 36 bytes from `0x16701000`, byte-swaps nine LONGs, checks `0x643287ab` |
| `seg5:26a6` | constructs the body reader object and allocates the block buffer, output buffer, marker-offset table, and aux decoder helper |
| `seg5:25e8` | reads a full `0x8000` body block at `base + 0x8000 + block_index * 0x8000` |
| `seg5:2146` | loads the block containing a requested logical record offset |
| `seg5:2270` | byte-swaps block header words 2/3, clears payload marker high bits, records fragment end offsets |
| `seg5:2356` | builds the aux decoder for the current block and records the delimiter symbol |
| `seg5:28c2` | converts the 0x80-byte aux control table into canonical-Huffman range rows |
| `seg5:1f9a` | decodes the next aux symbol bit-by-bit from the current bit offset |
| `seg5:241c` | concatenates decoded payload fragments until the delimiter symbol |
| `seg5:1e3e` | random-access entry point: logical offset -> materialized body record |
| `seg5:1ce4` | sequential "next record" entry point used after a random seek |

The executable logic is:

```
block = logical_offset / body_control.logical_block_size
read full 0x8000-byte physical block
while logical_offset is not inside that block's logical range:
    read next physical block

window_span = ceil(block.logical_length / 64)
window = (logical_offset - block.logical_offset) / window_span
bit_offset = block.prefix[window]

delimiter = decode_symbol(bit_offset=0)
seek(bit_offset)
skip records until the requested logical offset
emit payload fragments until delimiter
```

This makes the table-B body pointer model much more precise: the second
word in a main list table-B row points to a body **record ordinal**, not
a raw byte offset.  Consecutive records form the SGML article stream.
Higher-level segment-1/2/4 routines call `seg5:1e3e` for the first
record, then repeatedly call `seg5:1ce4` while parsing tags and building
display/search strings.

`tools/oed2_reader.py article` now implements the current Python article
assembly model: find the enclosing entry-start record (`<e>` or
`<e ...>`), then concatenate consecutive body records until the next
entry-start record.  This distinguishes word-list pointers that already
land on entry starts from phrase-list pointers that land inside the
containing article.  The reader now has a stateful `BodyBlockDecoder`,
so article assembly mirrors the executable's `1e3e` random seek followed
by repeated `1ce4` sequential reads instead of reloading the same block
for each record.

The next display layer is in the executable rather than the DAT
compression itself.  Segment 1 contains tag/entity recognizers:
`seg1:bfb8` recognizes selected SGML tags while scanning records, and
the entity-rendering chain around `seg1:3e0c`, `seg1:41c4`, and
`seg1:43ac` maps `&...` names to output bytes plus font/style codes.
The data segment has the matching RTF/font strings: the RTF header starts
at data offset `0x1d7e`, with fonts including Symbol, Plantin OUP,
Porson Greek OUP One/Two, Arial OUP, Arial Small Caps OUP, Times New
Roman Phonetics, Monotype Hadassah, and Pi6/7/8/9OUP MT.  This strongly
suggests the exact remaining renderer should be recovered by translating
those segment-1 routines, not by inventing a generic SGML renderer.

`tools/oed2_exe_entities.py` now statically extracts the simple entity
mapping shapes from those routines.  Current count is 451 mappings:
41 single-character mappings, 6 combining mappings, 170 Greek mappings,
and 234 Latin/symbol mappings.  Examples:

```
&aacu. -> e1
&Aacu. -> c1
&oq.   -> 91
&cq.   -> 92
&dd.   -> 2e 2e
&es.   -> 20
```

`tools/oed2_reader.py article --renderish --exe oeddos/OED.EXE` uses
that extracted table for readable previews.  This already turns the
word-list entry at ordinal 8 into normal prose with `án`, typographic
quotes, etc.  It is still only a preview: mappings that rely on style
bytes, overstrikes, or special fonts need the full renderer state.
`tools/oed2_reader.py entities` uses the same table as a coverage meter
and now reports exact output/style byte vectors: word ordinal 8 has
19/19 entity references covered by the EXE map, and word ordinal 9 has
149/149.  Overstrike vowels such as `&abreve.`, `&amac.`, and `&omac.`
are known exactly (`61 08 8f`, `61 08 8e`, `6f 08 8e`) and are
approximated as Unicode for readable previews.  Styled/custom-font
entities such as `&n.` are left visible in the preview but reported with
their exact bytes, e.g. `out=6d style=80`.

`tools/oed2_exe_entities.py styles` profiles the extracted nonzero
style bytes.  The entity routines currently expose five style patterns:
`80`, `70`, `e0`, `50`, and `70 70 70`.  The nearby data-segment RTF
table contains the font-switch strings (`\f7`, `\f5`, `\f2`, `\f3`,
`\f6`, `\f1`, `\f4`, `\f8`, `\f9`, `\f10`, `\f11`, `\f12`, `\f0`)
and the segment-2 routine at `seg2:00ca` now connects those style bytes
to the final RTF command sequence.

`seg2:00ca` appends `\plain `, chooses a font command from a style byte,
adds optional formatting (`\b`, `\i`, `\b\i`, `\up6`, `\dn6`), and then
adds a color command from the row's RGB triple.  The 16-row style table
lives at data offset `0x3c96`; each row is eight bytes:

```
00: 00 02 00 00 00 00 00 07
01: 00 02 10 00 ff 00 00 03
02: 00 02 30 00 ff 00 00 03
03: 00 02 10 00 ff 00 00 03
04: 00 02 10 00 00 80 00 00
05: 00 02 20 00 00 00 80 00
06: 00 02 00 00 00 00 00 07
07: 00 02 10 00 00 00 ff 01
08: 00 02 00 00 00 00 00 07
09: 00 0c 10 00 80 00 00 00
0a: 00 0c 40 00 80 00 00 00
0b: 00 0c 20 00 80 00 00 00
0c: 00 0c 00 00 ff 00 00 03
0d: 00 0c 00 00 80 00 00 00
0e: 00 02 00 00 00 00 00 07
0f: 00 02 00 00 00 00 00 07
```

The low nibble selects the row.  The high nibble usually supplies the
format/font override; if the high nibble is zero, the row's default
format byte is used.  Special high nibbles select custom OED fonts:
`0x70 -> \f6` (Times New Roman Phonetics), `0x80 -> \f2` (Porson Greek
OUP One), `0xd0 -> \f7` or `\f5` depending on base font, and
`0xe0 -> \f3` (Porson Greek OUP Two).  `0x90` and `0xf0` call an
additional dynamic helper that still needs translating.

Current decoded entity style patterns:

```
0x80 -> \plain \f2 \cf1
0x70 -> \plain \f6 \cf1
0xe0 -> \plain \f3 \cf1
0x50 -> \plain \f1 \up6 \cf1
```

`tools/oed2_exe_entities.py rtf-style` decodes arbitrary style bytes,
and `article --render-codes --exe oeddos/OED.EXE` now prints these RTF
commands beside styled entity atoms.

More of the higher-level SGML layer is now identified in segment 1:

| Routine | Role |
|---|---|
| `seg1:bfb8` | scans a body-record string for selected `<...>` tags and calls `seg1:b74e` on recognized tags |
| `seg1:b74e` | translates selected tags into an intermediate text buffer at data `0x8dd8` plus parallel style/control bytes through the buffer pointer at data `0x1c9e/0x1ca0` |
| `seg1:c28e` | searches neighbouring body records using `seg5:1e3e`/`seg5:1ce4` until `seg1:bfb8` finds one of those selected tags |
| `seg1:ce44` | builds a head-group display string across body records, skipping known SGML tags and invoking the Latin entity mapper at `seg1:71e0` |

The `seg1:bfb8` switch is keyed by the second character after `<` for
letters `c` through `v`.  The recognized families include `<cb`, `<db`,
`<e...`, `<n>`, `<q...`, `<s...`, `<pa...`, `<ta...`, and `<ve...`.
It is deliberately not an all-tags parser: it is a scanner for tags that
affect surrounding text extraction or style state.

`seg1:b74e` is the matching translator.  It sets the current style/control
byte at data `0x8dba` and appends text into the data `0x8dd8` buffer.
Notable branches include `<qig...>`, which recognizes embedded italic
abbreviation entities (`&ia.`, `&ib.`, `&id.`, `&ie.`, `&ig.`, `&ih.`,
`&iq.`, `&iz.`) and emits a dotted abbreviation with style bytes; and
`<s...>` branches, which expand selected subscript/section-style tags
into marked text plus spaces.  This needs a direct Python translation
before render/export can be called exact.

`seg1:ce44` is more concrete and looks like an original head-group
display text extractor.  It uses literal tag strings at data offsets:

```
0x1d2c </hg>   0x1d32 <hw    0x1d36 <hm>   0x1d3b <ps>
0x1d40 </hw    0x1d45 </hm>   0x1d4b </ps>  0x1d52 </q>
0x1d57 </et    0x1d5c </s     0x1d60 <q     0x1d63 </q>
0x1d68 </et    0x1d6d <q      0x1d70 </s
```

When inside the selected text region, it copies literal bytes, maps
ASCII apostrophe (`0x27`) to typographic apostrophe (`0x92`), and calls
the Latin/symbol entity routine at `seg1:71e0` for `&...` references.
`tools/oed2_reader.py article --headgroup --exe oeddos/OED.EXE` and the
compact `headgroups` command now implement this path as a Python
approximation: it copies only text inside `<hw`, `<hm>`, and `<ps>`
regions, stops at `</hg>`, uses the EXE's Latin entity mappings, and
performs the same apostrophe mapping.
Early samples match the expected compact header/list shape:

```
word[8]  -> a a.1
word[9]  -> a a.2
word[10] -> a a’ a.3
word[12] -> a v.
phrase[4] (enclosed article) -> aback adv.
```

The next renderer target is to fold `seg1:b74e` tag-state output into
the full article display/export path, because `--headgroup` is only the
narrow head-group extractor rather than the complete article formatter.

## Original-output comparison: `absolute`

The original Win 3.1 program was used to display/export the word-list
entry `absolute a.`.  The copied Microsoft Write 3.0 file
`/Users/heiner/tmp/dosbox/ABSOLUTE.WRI` preserves the plain article
text, but not the font/color changes visible in the screenshot.  The
plain text confirms our body and entity decoding for the first page:

```
absolute (__________), a.
[a. mid. Fr. absolut (mod. absolu), a 14th c. latinizing of OFr. asolu, assolu:
L. absolut-um loosened, free, separate, acquitted, completed, etc.; ...
```

The screenshot adds the missing display semantics: the headword is blue
and bold, the pronunciation is a phonetic-font run inside parentheses,
the part of speech is magenta/italic, and etymological/cited-form spans
use distinct italic/font styling.

The body records for this entry start:

```
<e><hg><hw>
absolute</hw> <pr>
<ph>"&bs@lju:t</ph></pr>, <ps>
a.</ps></hg> <etym>
a.
mid.
Fr. <cf>
absolut</cf> (
```

This comparison gave us two concrete renderer improvements:

- `<pr>...</pr>` displays as parenthesized pronunciation material.
- `<ph>...</ph>` is not ordinary entity text; it is a phonetic-font run.
  For the observed tokens, `"` is primary stress, `&bs` is the compact
  `/æbs/` cluster, `@` is schwa, and `u:` is long /uː/.
- `<etym>...</etym>` displays as bracketed etymology text.

After adding those display effects, the Python preview now begins:

```
absolute (ˈæbsəljuːt), a. [a. mid. Fr. absolut (mod. absolu), ...
```

`article --color --exe oeddos/OED.EXE` now adds a provisional ANSI
terminal style layer on top of that same render-ish stream.  It colors
headwords, pronunciations, parts of speech, cited forms, labels,
quotation metadata/text, and cross-references using tag names such as
`<hw>`, `<ph>`, `<ps>`, `<cf>`, `<la>`, `<q>/<qt>/<qd>`, and `<x>/<xr>`.
This is useful for terminal inspection, but the screenshot makes clear
that full reproduction still requires translating the exact
tag-to-font/color state machine around `seg1:b74e` and the segment-2
display style routines.

The static web renderer now applies the same evidence to the browser
path.  It renders `<ph>fVk</ph>` as `fʌk`, styles
`<s4 num=1><gr>intr.</gr>` as a distinctive sense number and grammar
label, starts quotation blocks on their own lines, turns `&a.1503` into
`a1503`, styles `<a>Dunbar</a>` as an author token, and keeps subentry
lookups such as `fucking` in article context while scrolling to the
target logical record.

Example from `bodyrec 0x2095 --count 8`:

```
<e st=obs><hg><hw>
a</hw>, <ps>
a.<hm>
1</hm> (<gr>
def.
numeral</gr>)</ps></hg>. <la>
Obs.</la>
or <la>
```

Segment 6 still contains generic block-cache / stream I/O used by other
indexes.  Around offset `0x1df8`, one routine compares a requested
32-bit logical position against `context+0x1c/0x1e`, seeks via helper
calls, reads into buffers at `context+0x10/0x12`, then byte-swaps words
through helpers at `0x3678` and `0x36d6`.  Segment 6 around `0x8a6c`
initializes a global codec state at data offsets `0x8278..0x829a` and
stores two far callbacks; this is likely a generic bit/record decoder
for non-body list/index readers.

## File-level overview

```
+0x00000000  264-byte header  (66 LE LONGs, all 24-bit)
+0x00000108  zero padding
+0x00000800  side-table       ~150 entries, byte/byte structure
                              (probably collation / case-fold table)
+0x000c0000  Section A start  term index
   ...
+0x0243b100  Section B start  compressed/non-body data (~130 MB)
+0x0a08c000  Section C start  per-block control (~17 MB, fragmented)
+0x0b01ce00  Section D start  late data region; contains SGML article
                              body blocks with byte-fragment substitution
+0x25df7000  EOF
```

## Header at file start

66 little-endian 32-bit values, every value's MSB is `0x00`, i.e.
they fit in 24 bits. Range: `[524,288 .. 16,305,939]` — i.e. all
pointers into the first ~16 MB of the file.

  - The values are **not** monotonic, so this isn't a sorted block
    directory.
  - 66 unique values; no obvious "(offset, length) pairs" pattern
    (sums don't add up cleanly to file size).
  - Best guess: a fixed-size lookup table indexed by something —
    initial letter? part-of-speech? entry class? — with each entry
    pointing to the start of a sub-region inside the term index.

This needs Milestone-2 work to interpret. Keeping it as raw data
in the section map for now.

## Side table at 0x800

193 byte-pairs starting at file offset `0x800`. The first ~30 byte-
pairs are filler (`(0x20, 0x20)`, `(0xa0, 0xa0)`); real entries
begin around `0x830` with patterns like `(0xb0, '0')`, `(0xa1, …)`,
`(0xa2, '"')`, `(0xa3, '#')`. The structure is consistent with a
**256-entry character classification / collation table** mapping
each input byte to a sort class or canonical-form analog. Same role
as the .AND format's `\x01`-marker stream, just realised as a side
table instead of an inline encoding.

Will be needed when the term index renderer is implemented
(Milestone 2).

## Section map (entropy-banded)

Section boundaries identified by sliding-window entropy (64 KB
window) over the whole file, then merged sub-MB neighbours.

| Section | Range (bytes) | Length | Mean entropy | Hypothesised role |
|---|---|---|---|---|
| **A** | 0 .. 0x243b100 | ~38 MB | 3.5 – 5.3 | **Term index.** Low entropy + structured byte distribution; same shape as the .AND `Lista` only at much larger scale. The 66-LONG header points exclusively into this region. |
| **B** | 0x243b100 .. ~0xa08a7c0 | ~130 MB | **7.87** | **Unknown compressed/index data, probably not article bodies.** It has very low OED tag density compared with Section D. |
| **C** | ~168 MB .. ~185 MB | ~17 MB | 5.27 (with frequent jumps to 0.4–7.9) | **Per-block control / meta table.** Fragmented profile — many tiny low-entropy windows interleaved with brief high-entropy ones. Same shape as `.AND` Story's meta subfile (ordinal→bit-offset lookup) but bigger; may contain Huffman freq tables for each compressed block. |
| **D** | ~185 MB .. EOF | ~450 MB | 7.5 – 7.9 | **Late data region containing article bodies.** Contains the overwhelming majority of SGML-like OED tags (`<hw>`, `<qt>`, `<etym>`, `<xr>`, `</x> <ps`) plus headword text. The clearly framed body-block stream found so far begins at `0x16709000`. |

## Milestone 2: SGML + byte fragment substitution

The body-text format appears to be SGML-like markup with byte-level
fragment substitution.  Plain ASCII tags survive in large numbers,
especially in Section D from about `0x16709000` onward.  Example hits:

```
rg -aob '</x> <ps' /Volumes/OED2/OED2.DAT | head
376510837:</x> <ps
376542095:</x> <ps
376544233:</x> <ps
376575468:</x> <ps
376575812:</x> <ps
```

At `0x16721000`, a 16-byte big-endian-looking block header is followed
by SGML-ish OED article markup:

```
0x16721000  00 00 5b 68  00 00 1e 78  00 00 11 e4  00 00 03 fe
0x16721010  8a 6f 66 a0  74 68 65 a0  f3 2e a0 e5  74 6f a0 f4
...
0x16721740  ... 61 62 61 6e 64 6f 6e 3c 2f 78 3e 20 3c 70 73 be
             ... "abandon</x> <ps" ...
```

Many printable bytes appear with bit 7 set.  A useful first-pass
normalizer is `byte & 0x7f`, which turns values such as `0xbe` into
`>` and `0xa0` into a space.  This does not fully decode the text,
because the high-bit bytes likely carry token-boundary or fragment
substitution information, but it exposes tags and headword-like
fragments well enough for scanning.

`tools/oed2_text_probe.py` was added for this work:

```
python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --find '</x> <ps'
python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --offset 0x16721000
python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --tags
python3 tools/oed2_text_probe.py /Volumes/OED2/OED2.DAT --tags \
    --start 0xb01ce00
```

`tools/oed2_reader.py` is the first structured reader.  It parses the
66-LONG file header and the currently identified Section-D body-block
stream:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT info
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyctl
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodycheck
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT blocks --limit 8
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT find abandon
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT dump --block 3
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT aux --block 3
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyrec --list word --index 8 --count 24
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyrec 0x2095 --join-records 24
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 8 --plainish
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list phrase --index 0 --plainish
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 8 --count 12 --headgroup --exe oeddos/OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT headgroups --list word --index 8 --count 12 --exe oeddos/OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 8 --renderish --exe oeddos/OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 1000 --color --exe oeddos/OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 9 --renderish --render-codes 20 --exe oeddos/OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT entities --list word --index 8 --count 2 --exe oeddos/OED.EXE
python3 tools/oed2_exe_entities.py oeddos/OED.EXE stats
python3 tools/oed2_exe_entities.py oeddos/OED.EXE styles --rtf
python3 tools/oed2_exe_entities.py oeddos/OED.EXE rtf-style --style 0x80 --style 0x70 --style 0xe0 --style 0x50
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5-profile
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5-runs
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5 --offset 0x16640000
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bitrange 0
```

Current body-block findings:

  - The original reader opens a body-control header at `0x16701000`.
    Its big-endian LONG fields are currently parsed as:
    `magic/checksum=0x643287ab`, `stride=0x8000`,
    `block_count=0x1e95`, `logical_total=0x03a3b4b8`,
    `logical_block_size=0x1e78`, `aux_class_count=0x40`,
    repeated stride `0x8000`, `tail/index bytes=0x898`, and
    `prefix_word_bytes=0x100`.
  - Body blocks start at `0x16709000`, one stride after the control
    header, and end exactly at `0x25bb1000`, which is the phonetics-list
    control anchor.
  - There are `7,829` body blocks.
  - Each starts with four big-endian LONGs:
    `(logical_offset, logical_length, stored_length, aux_count)`.
  - `logical_length` is usually `0x1e78`; some blocks differ, and the
    final tail block has logical length `0x08de`.
  - `stored_length` is usually around `0x1100..0x1300`, and the payload
    immediately follows the 16-byte header.
  - `aux_count` exactly equals the number of high-bit bytes in the
    payload, at least across the first 100 checked blocks.
  - The payload is followed by a 0x80-byte aux control area.  Its first
    LONG is the number of canonical-Huffman code-length classes; the
    following count values sum to `aux_count` and satisfy Kraft exactly.
  - After the 0x80-byte aux control area is a fixed 64-LONG big-endian
    prefix table.  The disassembled reader uses this table as bit offsets
    for 64 logical windows inside the block, not as byte-class streams.
  - The compressed aux bitstream encodes fragment ids.  At block load
    time the reader scans the payload, clears bit 7 on every high-bit
    marker byte, and stores the offset immediately after each marker.
    Fragment id `n` copies bytes from marker-offset `n` to marker-offset
    `n+1`.
  - The first decoded aux symbol in each block is the record delimiter
    symbol; in all sampled blocks so far it is `0`.  A body logical
    offset is a record ordinal.  To materialize a record, seek to the
    nearest logical-window prefix, skip delimiter symbols until the
    requested ordinal, then concatenate decoded fragment ids until the
    next delimiter.
  - `oed2_reader.py bodyrec` implements this executable-derived decoder
    and now returns clean SGML body records.
  - `oed2_reader.py bodycheck` validates the entire stream: all 7,829
    blocks have `aux_count == high-bit payload byte count`, all prefix
    tables are monotone, every delimiter symbol is `0`, and logical
    offsets are continuous.  Total high-bit markers / aux symbols:
    8,011,012.
  - `oed2_reader.py aux` now shows logical windows and sample decoded
    records for a body block.

For block `0x16721000`, the aux code-length counts are:

```
[0, 1, 0, 0, 0, 0, 8, 41, 69, 146, 284, 443, 23, 5, 2]
```

They sum to `1022`, matching the payload high-bit byte count, and their
fixed-point Kraft sum is exactly `0x100000000`.

For the same block, the 64-entry aux prefix table starts:

```
[0x2, 0xd45, 0x1bb2, 0x2836, 0x36f6, 0x444c, 0x50d1, 0x5ee0, ...]
```

The old interpretation of those 64 prefix values as streams keyed by
`payload_byte & 0x3f` was wrong.  The apparent fit came from the prefix
table's monotone shape and from the fact that the symbol count equals
the number of high-bit payload markers; the executable resolves the
ambiguity.

Historical body-probe notes, now superseded by the segment-5 decoder:

The following probes are retained for audit trail only.  They were useful
before the executable resolved the prefix-table semantics, but they are
not the current body model.

  - Treating the data after the 0x80 control area as one linear Huffman
    stream overreads the 64-LONG prefix table and produces an artificial
    run of zeros.
  - Treating aux symbols as direct replacement characters or simple
    pointers into the high-bit marker list does not make the normalized
    SGML prose cleaner.
  - Treating nonzero aux symbols as LZ-style back-references with zero as
    literal also fails to improve readability.  The symbols may still be
    references, but not in that simple form.
  - Treating each aux symbol as a direct record number in the candidate
    pre-body table at `0x16600000` yields structured records, but not
    readable fragments.

Experimental recursive marker expansion (obsolete):

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT substprobe --block 3
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodytrie --scan --count 12 --root-zero
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodytrie --scan --count 12 --consume reverse --shift 1 --root-zero
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodydist --scan --count 20 --formula i-s-1 --formula i-s+1
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodydist --scan --scope class --count 12 --formula-range=-8:8
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyfit --count 20 --consume forward --consume reverse --formula i-s-1 --formula i-s+1
```

This treats decoded aux symbols as references to high-bit payload
markers, maps canonical ranks through several candidate marker orders,
and recursively expands `marker := marker-char + referenced-marker`.
It is **not** the final decoder.  The payload-order variant is a useful
near miss for block 3, producing length `7748` versus logical length
`7800`, but the text is still visibly wrong.  That points to a missing
symbol-order/permutation layer or an external mapping table, not to a
simple "rank equals payload marker index" rule.

`bodytrie` is the reproducible version of this experiment.  Under the
direct payload-order parent model (`consume=forward`, `shift=0`,
`root-zero`), the first dozen blocks compare as follows:

| Block | Stored | Logical | Trie total | Diff |
|---:|---:|---:|---:|---:|
| 0 | 4,284 | 7,800 | 7,998 | +198 |
| 1 | 4,420 | 7,800 | 9,089 | +1,289 |
| 2 | 4,544 | 7,800 | 6,750 | -1,050 |
| 3 | 4,580 | 7,800 | 7,752 | -48 |
| 4 | 4,772 | 7,800 | 7,948 | +148 |
| 5 | 4,588 | 7,800 | 8,229 | +429 |
| 8 | 4,580 | 7,800 | 8,119 | +319 |
| 9 | 4,536 | 7,800 | 7,720 | -80 |
| 10 | 4,680 | 7,800 | 7,584 | -216 |

The near misses are useful because they validate the broad shape:
aux symbols behave like references into a per-block high-bit marker
dictionary, and each marker contributes a visible low-7-bit byte plus
some referenced suffix/prefix.  The misses are inconsistent enough to
rule out the naive graph as the final algorithm.

`bodydist` was the strongest pre-disassembly materialization probe.  It
treats an aux symbol as an LZ-style distance from the current high-bit
marker rather than as an absolute marker id.  The two closest simple
formulas are:

```
parent = current_marker_index - aux_symbol - 1
parent = current_marker_index - aux_symbol + 1
```

On the first 20 body blocks these formulas often land within a few
hundred bytes of the exact `0x1e78` decoded logical length; block 0 with
`i-s-1` gives `7761` vs `7800`, and block 7 with `i-s+1` gives `7837`
vs `7800`.  Over the first 200 blocks, forward consume with `i-s+1`
currently has the best simple length fit (average absolute error about
242 bytes, 60/200 blocks within 100 bytes).  The materialized prose was
still wrong; the later segment-5 decoder explained why, by showing that
aux symbols are direct payload fragment ids separated into logical
records by a delimiter symbol.

`bodyfit` compares candidate body materializers by decoded-length error
and a rough SGML/text quality score.  On the first 20 blocks, the
distance models beat the older absolute-parent probes on length fit,
while `char-parent` order currently scores slightly better than
`parent-char` on the text heuristic.  The heuristic is intentionally
weak because incorrect expansions can preserve many literal SGML tags;
use it to rank probes, not to declare success.

A fixed root-alphabet variant was also tested: references before marker
0 contributing one literal byte instead of empty text made the length
fit much worse.  That argues against a simple LZ78 dictionary with a
256-entry literal root table, at least under the current symbol order.

When the 64-prefix table was still being misread as
`payload_byte & 0x3f` streams, a class-local distance/rank variant was
also tested.  It is a useful negative result in the audit trail, but the
premise is now known to be wrong.

Under the obsolete payload-order interpretation, aux symbols appeared
reference-like:

  - `symbol == 0` is very frequent (roughly 260-280 times per ~1024
    high-bit markers).
  - Around 80% of symbols are numerically less than the current marker
    index if interpreted in payload order.
  - Direct marker-index dereferencing does not preserve the visible
    low-7-bit character, so the symbols are not just "copy this prior
    marker's character".

The original executable also has a separate high-bit display/entity
routine in segment 1 around `0x3a1c`/`0x3b92`.  It maps high bytes
through an internal entity-name table and emits `_` or `&name.` forms.
That routine is likely relevant after body record materialization, but
it is not the body substitution decoder itself: it handles
already-materialized bytes for rendering/search text.

## Sparse `0xffb` indexes

The sparse index family opened by the original reader at `0x155b2800`,
`0x15512800`, and the later `0x157...` anchors uses little-endian magic
`0x0ffb`, unlike the big-endian `0x0ffa` Lista-relative main lists.
`tools/oed2_reader.py sparse` now parses the common 10-byte header:

```
u16 magic          0x0ffb
u16 block_size     usually 0x0800 or 0x1000
u16 fanout/levels  observed 11, 17, 18, 24
u32 logical_total
```

The executable routine around segment 7 `0x3bb4` derives a page
coverage value as:

```
page_logical_span = ((block_size / 2) / fanout_or_levels) * 16
data_pages = ceil(logical_total / page_logical_span)
derived_end = anchor + (1 + data_pages) * block_size
```

The first data page starts exactly one `block_size` after the header
anchor.  This formula is now independently validated by adjacent sparse
anchors: six of the seven known sparse indexes end exactly at the next
known sparse anchor.

Sample profiles:

| Name | Offset | Block size | Fanout/levels | Logical total | Span | Data pages | Derived end |
|---|---:|---:|---:|---:|---:|---:|---:|
| startup-b | `0x15512800` | `0x800` | 11 | 473,257 | 1,488 | 319 | `0x155b2800` |
| startup-a | `0x155b2800` | `0x800` | 24 | 473,258 | 672 | 705 | `0x15713800` |
| late-a | `0x15713800` | `0x800` | 11 | 291,588 | 1,488 | 196 | `0x15776000` |
| late-b | `0x15776000` | `0x800` | 24 | 291,589 | 672 | 434 | `0x1584f800` |
| late-c | `0x1584f800` | `0x1000` | 11 | 2,435,558 | 2,976 | 819 | `0x15b83800` |
| late-d | `0x15b83800` | `0x1000` | 17 | 2,435,558 | 1,920 | 1,269 | `0x16079800` |
| late-e | `0x16079800` | `0x1000` | 18 | 2,435,558 | 1,808 | 1,348 | `0x165be800` |

The `late-e` derived end at `0x165be800` is particularly useful because
it lands exactly at the start of the candidate pre-body codebook table.
The page semantics are not decoded yet; some first pages are sparse word
tables while others are dense high-entropy pages.

## Candidate pre-body codebook / range table

The area immediately before the body blocks is now clearly more
structured than a loose printable blob.  The 5-byte record table starts
at `0x165be800`, exactly where the final known `0xffb` sparse index
ends.  The sorted records run to `0x1667078a`; a 120-byte trailer follows
before a denser stream begins at `0x16670802`.

The table is best viewed as records of:

```
u24le left
u16le right
```

The whole sorted range has 145,794 records and is perfectly ordered by
`(right, left)`:

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5 --count 8 --show 8
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5-runs --limit 8
```

Example first records:

| Index | File offset | u24 | u16 |
|---:|---:|---:|---:|
| 0 | `0x165be800` | `0x060016` | `0x0001` |
| 1 | `0x165be805` | `0x020022` | `0x0002` |
| 2 | `0x165be80a` | `0x0b0027` | `0x0002` |
| 3 | `0x165be80f` | `0x03002b` | `0x0004` |

The previous two-20-bit interpretation was an artefact of the old
misaligned start.  The `u24/u16` ordering is much stronger and should be
the basis for the next decoding attempts.

```
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5-profile
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT table5-runs
```

Current `table5-runs` output:

```
table range: 0x165be800..0x1667078a
records: 145794; monotone runs: 1
run  records              count   file-off     first(u24,u16)      last(u24,u16)
  0       0..145793  145794  0x165be800  (060016,0001)  (9f00af,900a)
```

This looks like a directory or range map into a later compressed stream,
not final text fragments.  The next decoding step is likely another
table lookup or codebook layer.

## Section C / pre-body index anchors

Section C is not only opaque control data.  It contains sparse
dictionary/index anchors in plain upper-case form.  Examples:

```
0x0a08d800  GOSPELG, GOVERNORGENERALI, ... HACKTHORNS ...
0x0a08e000  ... OVERc, OXFO, OZONIZER ...
0x12def600  ... ONR, OXFORD, PARKMAN@F ...
```

These are not article bodies, but they are likely reader navigation or
search-index guidewords.  They support the earlier point that Section B
is not the body region and that the late pre-body area includes several
different index/codebook structures before the framed article blocks.

Tag-density comparison strongly supports Section D, not Section B, as
the article-body region:

| Pattern | Section B count | Section D count |
|---|---:|---:|
| `<hw` | 2 | 20,385 |
| `<x` | 1,891 | 119,874 |
| `</x> <ps` | 0 | 12,630 |
| `<qt` | 9 | 126,211 |
| `<q` | 1,656 | 507,790 |
| `<s4` | 6 | 32,739 |
| `<etym` | 0 | 20,204 |
| `<xr` | 8 | 52,087 |

Literal string probes show the same split: `abandon`, `Oxford`, and
`dictionary` all appear in Section D, while Section B has no hits for
those terms in raw form.

Top raw tag counts from the first run include:

| Tag | Count |
|---|---:|
| `<w` | 179,859 |
| `<q` | 168,303 |
| `<qd` | 161,156 |
| `</qd` | 158,243 |
| `</qt` | 154,958 |
| `</q` | 147,384 |
| `</w` | 126,970 |
| `<qt` | 126,212 |
| `<lc` | 125,916 |
| `</lc` | 120,855 |

The regex is deliberately broad, so counts may include false positives
from binary/compressed spans.  Still, the concentration of real OED tags
near `0x16709000+` is strong enough to make this region the next best
target.

## Confirmed differences from `.AND`

  - **No matches** for `.AND` magic numbers (`0x0FFA` Lista,
    `0x76232828` Story, `0x00112233` Meta) anywhere in the first
    2 MB. OED2.DAT is its own format, not a CompLex `.AND` variant.
  - The 264-byte header is a **per-file directory of 66 pointers**,
    where `.AND` has only 4 LONGs (TOC) + a separate per-section
    Book header. So the OED's directory is much richer.
  - **Side table at 0x800** vs. `.AND`'s inline `\x01`-marker
    stream — different solution to the same collation problem.

## Likely shared with `.AND`

  - Section D's article bodies look like SGML markup with byte-level
    fragment substitution.  This resembles the `.AND` design at the
    engineering level: keep the text structurally marked up, then replace
    frequent byte fragments or suffixes with compact single-byte forms.
  - Section A's entropy band (3.5–5.3) matches the `Lista`
    fragment-stream profile almost exactly — strong hint that the
    term index is structurally very similar to `.AND`'s, just at
    50× the entry count.

## Current open questions

  1. Translate the SGML/entity renderer from `OED.EXE`, especially
     `seg1:3e0c`, `seg1:41c4`, and `seg1:43ac`, so `&...` names map to
     the same output bytes and font/style codes as Win 3.1.
  2. Finish the word-list hidden-prefix label map so `:aabsolute` and
     related keys render with the exact original POS/class suffixes.
  3. Decode the `0xffb` sparse index family around `0x15512800` and
     `0x155b2800`; headers/page geometry are parsed, page semantics are
     still open.
  4. Explain Section B.  Its entropy is high, but it lacks article-tag
     density.  It is probably search/index data rather than bodies.
  5. Explain the first 32-bit word in table-B rows and the duplicate /
     multi-row semantics across word, Greek, and phonetics lists.
  6. Revisit the 66-LONG file header and the side table at `0x800` after
     the remaining list/search indexes are understood.

## Reproducing

```sh
hdiutil attach -readonly -nobrowse \
    'Oxford English Dictionary (Second Edition).iso'
python3 tools/oed2_inspect.py /Volumes/OED2/OED2.DAT \
    --out tools/oed2_section_map.json
hdiutil detach /Volumes/OED2
```
