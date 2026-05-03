# Quotation Text full-text search — RE notes

Working notes on the OED2 "Quotation Text Search" feature (a.k.a.
"Search the Whole Dictionary"). The lexicon and index are identified;
the posting-list decoder is the remaining missing piece.

## Identified DAT structures

| Offset | Role |
|---|---|
| `0x0a08b000` | QT lexicon (`0x0ffa` block list, 1,413,525 unique terms; markers run from `\x03ag` upward) |
| `0x0a4cf000` | QT table_A copy — header `[837, 755, 2511, 7422]`, identical to word-list table_A |
| `0x0a4d3000` | Small auxiliary `0x0ffa` list (1 block of 0x400 bytes) — purpose TBD |
| `0x0a4d7000` | Candidate QT table_B — 8-byte records `(u32 BE count, u32 BE offset_into_section_b)`, sequentially-increasing offsets, frequent zero-rows |
| `0x18ce0000` | "High-bit body/index stream" — far ptr stored at context +0x60/+0x62 |
| `0x0243b100..0x0a08c000` | **Section B**: ~130 MB of varint-encoded posting lists (one per QT term) |
| `0x1584f800`, `0x15b83800`, `0x16079800` | `late-c/d/e` sparse `0xfb0f` indexes; logical_total = 2,435,558 ≈ total quotation count; bridge quotation_id → article body offset |

## OED.EXE call map

### Search-mode UI dispatcher

`seg4:0x9c80` is a multi-mode handler used by the "Quotation Search" dialog:

| Mode (`[bp-0x4]`) | Action | Title string |
|---|---|---|
| 0 | open work1 (`0x12dee800`) | "Work Titles" |
| 1 | open work2 (`0x131e8800`) | "Work Titles" |
| 2 | open Cited2 (`0x13a1b000`) + Etymology lexicon (`0x104c8000` / table_A `0x105c7000`) | "Etymology Words" |
| 3 | open QT lexicon (`0x0a08b000`) | **"Quotation Text"** (string at data `0x395f`) |
| 4 | (Date/Author/Work — TBD) | — |

The QT path (`seg4:0x9d4d`):
1. Reuse word-list table_A (call `seg5:0x4260` with `-1, -1` placeholders).
2. Call `seg5:0x2aea` with control = `0x0a08b000`.
3. Link via `seg5:0x2b98`, init buffer via `seg5:0x4f3a`.
4. Set list type code = `0x301`.

### Search executor

After list opening, the dispatcher runs at `seg4:0x5e0a`:
- Loads table_B from search-request `[bp-0x12]+0x16/0x18`.
- Indexes a 5-entry mode lookup table at `data+0x987e + idx*2`.
- Calls `seg4:0x5648` (search executor) with `(0, 0x4f, table_B_far, mode_lookup_val)`.

`seg4:0x5648` allocates a 5-byte+ buffer via `seg7:0xa457`, then drives an iterative read loop via `XWI321TE.#15` and `XWI321TE.#20` (text-buffer routines) — this is **result text streaming**, not the index decoder itself.

### Lookup primitives in `seg5`

| Routine | Role |
|---|---|
| `seg5:0x2aea` | open control_0ffa list |
| `seg5:0x4260` | open table_A |
| `seg5:0x2b98` | link table_A ↔ control |
| `seg5:0x4f3a` | init 0x20-byte working buffer |
| `seg5:0x528c` | **exact-key lookup wrapper** — returns ordinal |
| `seg5:0x53bc` | marker-block selector |
| `seg5:0x54ee` | scan-forward within block |
| `seg5:0x6502` | setter: stores high-bit-stream far ptr (e.g. `0x18ce0000`) at context+0x60/0x62 |
| `seg5:0x3db8` | thunk → calls `seg5:0x3494` (deeper) |
| `seg5:0x3494` | **0x268-byte search-state allocator + list opener.** Allocates state, locks via `XWI321.#155`, encodes query via `seg7:0x6dc6`, sets up working buffers, validates magic = `0x0ffa` via repeated `seg5:0x3de4` reads. *Not* the posting-list decoder itself — sets up a search-state then dispatches further |
| `seg5:0x3de4` | **read_u16_BE(stream)** — calls `seg7:0x68a0` with N=2, reassembles as u16 BE |
| `seg5:0x3e18` | **read_u32_BE(stream)** — calls `seg7:0x68a0` with N=4, reassembles as u32 BE |
| `seg5:0x8ebc` | "read N bytes at offset" — buffered DAT reader |

### Lower-level helpers in `seg6/seg7`

| Routine | Role |
|---|---|
| `seg6:0x8a6c` | codec state init: 4 × `seg7:0x974` reads, plus 2 far-callbacks; state at `data+0x827a..0x8298` |
| `seg7:0x3bb4` | open sparse `0xfb0f` index (verifies magic, reads header) |
| `seg7:0x68a0` | **stream `read(buf, N)` primitive** — args are `(buf_far, N_words, ?, stream_obj_far)`; underlying byte read from current stream position |
| `seg7:0xa457` | allocator (returns 0/0 on failure) |
| `seg7:0x6dc6` / `seg7:0x6d60` | table-A query encoders (called from `seg5:0x528c` / `seg5:0x3494`) |
| `seg7:0x7010` | **stream `seek(stream, offset, whence)`** — modes 0/1/2 = SET/CUR/END; calls `seg7:0xa01c` as the underlying seek primitive |
| `seg7:0xa01c` | low-level seek (takes a 4-byte byte from `[stream_obj+0xb]` plus a 32-bit position) |
| `seg7:0x9012` | companion routine in the stream-object family |

## Object layout — main "context" object (referenced via `[0x2af8]`)

| Offset | Field |
|---|---|
| +0x06/+0x08 | active list control_0ffa pointer |
| +0x12/+0x14 | shared context pointer |
| +0x16/+0x18 | table_B (raw DAT far ptr) |
| +0x1e/+0x20 | structured search object |
| +0x60/+0x62 | high-bit stream pointer (`0x18ce0000`) |
| +0x6e/+0x70 | table_A object handle |

## Status

**What works as a search:** lexicon decoded → ordinal known → location of posting list known (`table_B[ordinal]` → `(count, offset_in_section_b)`).

**What's missing:** the byte-format of posting lists in Section B and the per-page format of `late-c/d/e` sparse indexes.

## Next disassembly targets

1. `seg5:0x3494` ran past — the routine sets up a 0x268-byte state object and validates the list magic. The actual posting-list decoder must be downstream (called *after* the state is built and the magic is verified). Need to trace from `seg5:0x3494`'s tail forward, or find the routine that consumes the state object's `+0x6/+0x8` (control) and `+0xa/+0xc` (stream) fields together.
2. The fact that `seg5:0x3de4` and `seg5:0x3e18` are simple BE u16/u32 readers strongly suggests the posting-list format isn't bit-packed — it's *byte-aligned* with u16/u32 fields. The "high entropy" of Section B is from Huffman-encoded bytes interleaved between u16/u32 metadata. So the decoder we're looking for likely reads a u16/u32 header (count, length, etc.) and then does a byte-level Huffman / arithmetic decode for the payload.
3. `seg7:0x68a0` is the stream-read primitive. Find all callers in `seg5`/`seg6` to enumerate everything that reads from a stream — the posting decoder is one of them.
4. `seg5:0x528c` full scope — see how the post-lookup ordinal is consumed; specifically watch the path from `[es:bx+0x18]/[es:bx+0x1a]` (table_B internal pointer at list-object +0x18).
5. Find where `0x18ce0000` is loaded into a search context — currently observed only at startup (`seg4:0x1b68`); the QT path may set up a different stream pointer.
6. The `late-c/d/e` page format: each 4096-byte page has 186 slots × 11 u16-LE entries with 11 bits per logical entry. Could be a B-tree level (delta-encoded pointers) or a packed signature; needs `seg7:0x3bb4`'s sibling routines analysed.

## How to reproduce

```sh
hdiutil attach -readonly -nobrowse \
    'Oxford English Dictionary (Second Edition).iso'

# Lexicon summary
python3 tools/oed2_reader.py /Volumes/OED2/OED2.DAT oedlist qtext --summary

# Probe scripts
python3 tools/probe_section_b.py --mode overview
python3 tools/probe_section_b2.py
python3 tools/probe_fb0f.py
python3 tools/probe_late_c.py

# Disassembly probes
python3 tools/ne_inspect.py OED.EXE disasm 5 0x3494 --count 80
python3 tools/ne_inspect.py OED.EXE disasm 5 0x528c --count 80
python3 tools/ne_inspect.py OED.EXE dat-pairs --segment 4
```
