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
| Original `0x0ffa` exact-list lookup | marker/scan path ported |
| Plain typed-word lookup from `OED.EXE` | assembly path ported in Python |
| Body block framing | parsed |
| Body aux Huffman stream | decoded |
| Body record materialization | working |
| Article assembly | working |
| Entity renderer extraction from `OED.EXE` | working for 451 entities |
| RTF style-byte decoding | partial |
| Terminal article preview | provisional ANSI styling |
| Static browser lookup | marker/scan path ported |
| Exact Win 3.1 display/export reproduction | open |

The main working notes are in
[`tools/oed2_findings.md`](tools/oed2_findings.md).  The primary reader
and probe is [`tools/oed2_reader.py`](tools/oed2_reader.py).

## Format Overview

`OED2.DAT` is a random-access compressed database rather than a single
linear text file.  The original executable owns the format: it opens the
DAT directly, seeks to hard-coded anchors, decodes compact list indexes,
and then materializes body records from compressed body blocks.

The currently understood exact list path is:

```
decoded list block -> global ordinal -> table-B row -> body logical offset
```

For the main article-facing lists, table-B entries are 8-byte records.
The second word points into the logical body stream.  Word and phrase
table-B coverage is currently exact: every row lands inside the decoded
body block range.

The original Win16 list lookup is reproduced for the word-list path.  The
exact helper `seg5:2d4c` encodes a caller string with Table-A
(`seg5:4688`) and uses the `0x0ffa` marker guide plus forward scan
(`seg5:528c/53bc/54ee`).  The visible Word Look-up dialog uses a related
primary-key path in `seg3:35f8`: it prepends the default hidden bytes
`0a`, encodes the query, keeps only the primary bytes before the first
control byte, and accepts the first prefix match.  For `absolute`, that
lands on word index 1000 and table-B body logical `0x0001ef86`.

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

The body markup is SGML-shaped (element names like `<hg>`, `<hw>`, `<ps>`,
`<sub>`, entity references with a `.` terminator like `&schwa.`,
`&page.`) but no DTD was ever attempted for it: see Tompa, "What is (tagged)
text?" (1989), https://www.jstor.org/stable/43091009.  `OED.EXE` is the
authoritative source for what each entity and tag actually rendered.

## Why This Was Good 1990s Technology

The design is tuned for CD-ROM, Win16 memory, and slow random I/O:

- Lookups avoid scanning the 606 MB data file.
- List pages and pointer rows are tiny.
- Body data is decompressed in local `0x8000`-stride frames.
- Many lookup modes can point to the same article stream without
  duplicating article text.
- SGML/entity-heavy dictionary prose compresses well with local fragment
  substitution plus Huffman coding.

For a normal typed-word lookup, the reader needs the list control data,
the word Table-A encoder table, one `0x800` compressed word-list block in
the common case, one 8-byte pointer-table row per selected result, and
usually one `0x8000` body frame for the article.  Longer entries need
additional adjacent body frames.  The entry `absolute a.` fits in one
body frame.

## Static Web Lookup

The browser UI in [`web/`](web/) is a fully static frontend.  All OED
seeking and decoding happens in JavaScript in the browser; there is no
lookup API and no Python service behind it.

The frontend can read `OED2.DAT` two ways:

- HTTP byte-range requests against `/OED2.DAT`, for static hosts that
  support `Range: bytes=...`;
- a local file picker, using `Blob.slice()` for the same small random
  reads without uploading the file anywhere.

The browser lookup path now follows the Win16 word-list path: encode the
typed text with the word Table-A data, keep the UI primary key, choose a
list block with the `0x0ffa` marker guide, expand that compressed block,
and scan forward for matching primary prefixes.  It does not use a
global ordinal binary search or a backend index service.

The article renderer is still not a byte-perfect clone of the Win 3.1
display code, but it now preserves more of the original reading shape:
phonetic `V` renders as `ʌ`, sense numbers and grammar labels are styled,
quotation/date lines break out distinctly, `&a.1503` renders as `a1503`,
author tags use small caps, and subentry lookups scroll to their target
body record.

For local development, the helper below is only a range-capable static
file server.  It serves files and byte ranges; it does not perform OED
lookup or decoding:

```sh
npm run serve
```

Then open `http://127.0.0.1:8765/`.  By default the helper serves
`/OED2.DAT` from `/Volumes/OED2/OED2.DAT` when the ISO is mounted.  You
can override that with `OED2_DAT=/path/to/OED2.DAT npm run serve`, or use
the file picker in the page.

The web decoder can be checked from Node with:

```sh
npm run check:web
```

## Useful Commands

Assuming the ISO is mounted at `/Volumes/OED2` and the original executable
is available as `OED.EXE` in the repo root:

```sh
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT info
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodyctl
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT bodycheck
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT ptrs word --summary
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT tablea word --struct --encode-exe 0aabsolute
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlookup word absolute --ui-word-primary
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
