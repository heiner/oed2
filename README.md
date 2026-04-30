# oed2

Reverse-engineering tools and notes for the Oxford English Dictionary
Second Edition CD-ROM data file, `OED2.DAT`.

The goal is to reproduce the original Windows 3.1 reader exactly enough
to decode, search, render, and eventually export dictionary articles from
the ISO data.  The current work was split out from the `pcwb2026` project
after confirming that the Oxford reader uses similar compact-index and
compressed-record ideas, but has its own data structures and executable
renderer.

## Current Status

| Component | State |
| --- | --- |
| Original installed reader / `OED.EXE` analysis | partly mapped |
| DAT hard-coded section anchors | mapped from disassembly |
| Word/phrase/variant/Greek/phonetics list controls | parsed |
| Word and phrase pointer tables | fully mapped to body offsets |
| Body block framing | parsed |
| Body aux Huffman stream | decoded |
| Body record materialization | working |
| Article assembly | working |
| Entity renderer extraction from `OED.EXE` | working for 451 entities |
| RTF style-byte decoding | partial |
| Terminal article preview | provisional ANSI styling |
| Exact Win 3.1 display/export reproduction | open |

The main working notes are in
[`tools/oed2_findings.md`](tools/oed2_findings.md).  The primary reader
and probe is [`tools/oed2_reader.py`](tools/oed2_reader.py).

## Format Overview

`OED2.DAT` is a random-access compressed database rather than a single
linear text file.  The original executable owns the format: it opens the
DAT directly, seeks to hard-coded anchors, decodes compact list indexes,
and then materializes body records from compressed body blocks.

The current lookup path is:

```
decoded list block -> global ordinal -> table-B row -> body logical offset
```

For the main article-facing lists, table-B entries are 8-byte records.
The second word points into the logical body stream.  Word and phrase
table-B coverage is currently exact: every row lands inside the decoded
body block range.

The body stream starts at `0x16709000` and is controlled by a header at
`0x16701000`.  It contains 7,829 fixed-stride frames.  Each frame has:

- a four-long big-endian block header;
- a payload area whose high-bit bytes mark fragment boundaries;
- a canonical-Huffman aux stream of fragment IDs;
- a 64-entry prefix/restart table for random access within the frame.

The aux stream is decoded from the correct prefix window.  Fragment IDs
select payload fragments, and symbol `0` is the observed body-record
delimiter.  The decoded records are SGML-like article pieces such as
`<e><hg><hw>absolute</hw> ...`.

Rendering is a second layer.  The DAT stores SGML tags and entity names;
`OED.EXE` contains the entity mappings, style bytes, font/color choices,
and RTF/display routines.  The Python tools currently implement readable
render-ish previews, headgroup extraction, entity inspection, partial RTF
style decoding, and an ANSI-colored terminal preview.

## Why This Was Good 1990s Technology

The design is tuned for CD-ROM, Win16 memory, and slow random I/O:

- Lookups avoid scanning the 606 MB data file.
- List pages and pointer rows are tiny.
- Body data is decompressed in local `0x8000`-stride frames.
- Many lookup modes can point to the same article stream without
  duplicating article text.
- SGML/entity-heavy dictionary prose compresses well with local fragment
  substitution plus Huffman coding.

For a normal lookup, the original reader should need only a few small
index reads, one 8-byte pointer-table row, and usually one `0x8000` body
frame.  Longer entries need additional adjacent body frames.  The entry
`absolute a.` fits in one body frame.

## Useful Commands

Assuming the ISO is mounted at `/Volumes/OED2` and the original executable
is available as `OED.EXE` in the repo root:

```sh
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT info
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyctl
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodycheck
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT ptrs word --summary
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT headgroups --list word --index 8 --count 12 --exe OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 1000 --renderish --exe OED.EXE
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 1000 --color --exe OED.EXE --show 800
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT article --list word --index 9 --renderish --render-codes 20 --exe OED.EXE
python3 tools/oed2_exe_entities.py OED.EXE stats
python3 tools/oed2_exe_entities.py OED.EXE styles --rtf
python3 tools/oed2_exe_entities.py OED.EXE rtf-style --style 0x80 --style 0x70 --style 0xe0 --style 0x50
```

Local binaries, ISO images, installed-reader files, and extracted data
files are ignored by git.
