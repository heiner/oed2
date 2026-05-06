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
2. The fact that `seg5:0x3de4` and `seg5:0x3e18` are simple BE u16/u32 readers strongly suggests *headers* are byte-aligned with u16/u32 fields. The *payload*, however, is not simple varints — empirically tested both LSB-first and MSB-first continuation-bit varints on posting lists at `Section_B + 0x7daec` (count=1710) and at `0x18ce0000 + 0x7daec` (alternative anchor); both decoders bail out after ~22-48 deltas and very few of the cumulative IDs land in the valid quotation-id range [0, 2,435,558]. So the payload is a **custom compressed format** — very likely a Huffman / canonical-Huffman bit stream similar to the body decoder (`seg5:0x28c2` builds canonical-Huffman range rows; the posting decoder probably uses a sibling routine).
3. The 8-byte-record interpretation of `0xa4d7000` as a flat lexicon table_B is **wrong**. Empirical scan of the first 1 MB shows: 30.7% records look "valid" (small count, in-Section-B offset), 24.4% are zeros, 44.9% have garbage values; offsets are *not* monotone (24,423 descents in the first 99k non-zero rows). The region either uses variable-length records, is a different type of table altogether, or 0xa4d7000 simply isn't where the QT table_B lives. Need to find the real table_B by tracing OED.EXE's lookup path further.
3. `seg7:0x68a0` is the stream-read primitive. Find all callers in `seg5`/`seg6` to enumerate everything that reads from a stream — the posting decoder is one of them.
4. `seg5:0x528c` full scope — see how the post-lookup ordinal is consumed; specifically watch the path from `[es:bx+0x18]/[es:bx+0x1a]` (table_B internal pointer at list-object +0x18).
5. Find where `0x18ce0000` is loaded into a search context — currently observed only at startup (`seg4:0x1b68`); the QT path may set up a different stream pointer.
6. The `late-c/d/e` page format: each 4096-byte page has 186 slots × 11 u16-LE entries with 11 bits per logical entry. Could be a B-tree level (delta-encoded pointers) or a packed signature; needs `seg7:0x3bb4`'s sibling routines analysed.
7. **Find the QT table_B properly.** `0xa4d7000` is *not* it (see point 3 above). Candidate strategies:
   (a) Set a breakpoint in DOSBox at `seg5:0x528c`'s return and watch which DAT region the caller reads with the ordinal as offset.
   (b) Search for routines that take an ordinal argument and multiply by 8 (`shl ordinal, 3`) before adding a DAT base — that's the natural shape of an ordinal-indexed table_B reader.
   (c) Look at `seg5:0xe727`'s code path further to see what's done with the stored ordinals at `obj+0x44+i*8` — that's where ordinal → posting list happens.

## Search engine call graph (continued)

The QT search engine is far more complex than a single ordinal→posting
list lookup. Sketch of the call chain:

```
caller (multiple — one per search mode)
  ↓ pushes (state, count, table_base_far)
seg5:0x7e3e    QT-mode dispatcher
                — checks state.+0x51 == 3 (mode = Quotation Text)
                — checks state.+0x54/0x56 == 0
                — forwards args to seg5:0xab22
  ↓
seg5:0xab22    search scan
                — sanity checks state.+0x40 (count) < 16
                — calls seg5:0xa3e4 (stream setup)
                — initialises slot at state.+0x44 + count*8
                — calls seg5:0xa1a8 (stream read) → stores at slot+0x46
                — loops i in [0, count_arg):
                    record = u32 BE at table_base[i*4]
                    position = record + state.base32 (state.+0x2c/0x2e)
                    seg5:0xa1c2(stream, position)  ← match check
                    if non-zero: store and exit
  ↓
seg5:0xa1c2    match-test at position
                — index = state.+0x20 (compound-query slot)
                — reads 16-byte record at state.+0x24 + index*16
                — gates on record.+0xe (a flag)
                — calls near 0xa2d4 (deeper logic)
                — calls seg6:0xaa twice with state buffers (cached stream read)
  ↓
seg6:0xaa      cached 4-byte stream reader
                — buffer object {size, pos, data_far_ptr, stream_far_ptr}
                — first call: stream-read 4 bytes via seg7:0x6a20
                — subsequent: append to local cache buffer
  ↓
seg7:0x6a20    underlying stream read primitive
```

**State object (size 0x268 bytes, allocated by seg5:0x3494):**

| Offset | Field |
|---|---|
| +0x08/+0x0a | high-bit stream object |
| +0x1c/+0x1e | buffer ptr |
| +0x20 | compound-query slot index |
| +0x24 | far ptr to 16-byte query records |
| +0x2c/+0x2e | base32 — added to record offsets to compute stream positions |
| +0x38/+0x3a | another stream object |
| +0x40 | accumulated count of search terms |
| +0x42 | current iter |
| +0x44 + i*8 | per-term slots (8 bytes each — 16 max) |
| +0x51 | search mode (=3 for Quotation Text) |
| +0x54..+0x56 | mode-specific gate field |

## Architectural inference

The structure shows the QT search engine implements **compound queries
with verify-after-filter:**

1. The search registers up to **16 query terms** (one per search box —
   the OED reader supports compound queries with AND/OR/NEAR
   operators).
2. For each term, candidate **positions** are loaded into a 4-byte-record
   table (somewhere upstream — possibly from the `late-c/d/e` sparse
   indexes, which would explain why those indexes have logical_total =
   2,435,558 quotations).
3. `seg5:0xab22` scans candidate positions and calls `seg5:0xa1c2`
   to verify each one. The verify step reads from the high-bit stream
   to confirm the term occurs at that position.
4. The 4-byte records are *delta offsets* added to a per-state base32
   field — consistent with delta-encoded posting lists.

This means **Section B may not be a flat "posting list per term"**. It
could be a **positional inverted index where each "posting" is a 4-byte
delta** and the late-c/d/e indexes pick the candidates. The per-list
table_B I was looking for might not exist as a flat array — it's
embedded in the search-state's 4-byte-record table that is built
dynamically from sparse-index hits.

This reframes the next investigation: instead of finding "QT table_B",
find **how the candidate list at `[bp+0xe]` is built** before
`seg5:0xab22` is called. That's where the late-c/d/e sparse indexes
get consulted. Track the call chain *upward* from `seg5:0xab22`'s
caller (`seg5:0x7e3e`).

## Candidate-list architecture (confirmed)

The 4-byte-record candidate list passed to `seg5:0xab22` is a
**null-terminated array of u32-LE values** with `0xffff_ffff` as the
sentinel. Confirmed by tracing:

```
seg4:0x4aa6   "search executor" — receives candidate table at [bp+0x6/0x8]
              if non-zero: jumps to candidate-scan path at 0x4dea
              if zero:     jumps to query-build path at 0x4d6d (calls seg6:0x573a)

seg4:0x4dea   candidate-list scan loop:
              for i in 0..1000:
                  bx = base + (i * 4)         ; via seg7:0x873a (32-bit shl by 2)
                  if [bx] == 0xffff and [bx+2] == 0xffff: break  ; sentinel
              count = i
              push (state, count, table_base)
              call seg5:0x7e3e                ; QT mode dispatcher
              ...

seg4:0x41b2   convenience wrapper — receives a single u32 [bp+0x6/0x8]
              builds a 1-element candidate list at fixed memory:
                  [0x77c6:0x9176, 0x9178] = the value
                  [0x77c6:0x917a, 0x917c] = 0xffff_ffff (sentinel)
              calls seg4:0x4aa6 with that 8-byte buffer

seg4:0x41b2 is registered as a CALLBACK via seg3:0x14b6 (window-creation),
so the values it receives come from Windows event dispatch on user actions.
```

**The candidates are u32 deltas added to `state.base32` (state.+0x2c/0x2e)**
to form stream positions. So the candidate list says "check positions
base+x1, base+x2, ..." against the high-bit stream.

For a single-keyword search the candidate list is built dynamically from
a single seed value; for compound queries it's a pre-intersected set of
candidate positions.

## Where the candidate list comes from

Three callers of `seg4:0x41b2` (the wrapper):
- `seg4:0x46e1` — feeds the wrapper as a callback, after a "Cited Forms"
  control open at 0x13b08000. Mode 0x202 (Cited Form Search).
- `seg4:0x481a`, `seg4:0x4953` — similar shape, different modes.

Three callers of `seg4:0x4aa6` (the executor):
- `seg4:0x4202`, `seg4:0x4213` — both inside the `seg4:0x41b2` wrapper.
- `seg4:0x457f` — likely a direct caller bypassing the wrapper.

The "Cited Form" / "Etymology" / "Quotation Text" search modes all funnel
through `seg4:0x4aa6` with mode-specific candidate lists. The candidate
generation happens in code paths *before* the callback is registered
— in the dialog setup and the user-input handlers.

## Streams identified by base offset

| Anchor | Role | Header? | Notes |
|---|---|---|---|
| `0x18ce0000` | "high-bit body/index stream" — stored at startup in main context+0x60/0x62 | **No header** at the boundary (bytes before and after equally high-entropy) — this is a *byte offset into* a larger compressed region, not a start-of-section | Used widely by `seg6:0xaa` cached reads |
| `0x1b690000`, `0x1c300000`, `0x1c6f0000` | Other unknown DAT pointers from `seg4` dat-pairs | High-entropy bytes, no headers | Likely more streams for other modes |

The fact that `0x18ce0000` has no boundary structure means the search
engine treats large compressed regions as opaque streams accessed via
seek+read primitives, with the actual structural information living in
tables and indexes elsewhere (the lexicon, the sparse indexes, and
per-search-state caches).

## late-c/d/e page format (decoded)

The three sparse `0xfb0f` indexes use a uniform bit-packing scheme:

- Each page is `block_size` (= 0x1000 = 4096) bytes.
- Pages are organised as **slots of `levels * 2` bytes**.
- Each slot holds **16 logical entries**, each `levels` bits wide,
  bit-packed LSB-first.
- 16 × `levels` bits = `levels * 2` bytes exactly fills the slot — no padding.

| Index | Levels | Slot size | Slots/page | Entries/page | Value range |
|---|---:|---:|---:|---:|---:|
| late-c | 11 | 22 B | 186 | 2,976 | 0..2047 |
| late-d | 17 | 34 B | 120 | 1,920 | 0..131,071 |
| late-e | 18 | 36 B | 113 | 1,808 | 0..262,143 |

For each, total entries across all data pages just slightly exceeds
`logical_total = 2,435,558` — the last page is padded.

Empirically over the full 819 data pages of late-c (2,437,344 entries):

- Distribution is **roughly uniform 0..2046** (3-5% per 64-wide bin)
- **Value 2047** is a clear outlier at **13.73% of entries** — almost
  certainly a "no-data" / "always-no-match" sentinel
- Last page is 60% value `0` — that's the padding region beyond
  logical_total

This is the signature of a **bloom-filter-like signature file** where
each quotation gets a fixed-width hash value. The three indexes
combine for very low false-positive rate:

```
combined FP rate ≈ 1 / (2048 × 131072 × 262144) ≈ 1.4e-13
```

The verify-after-filter architecture in `seg5:0xab22` makes sense
here: late-c/d/e quickly cull all 2.4M candidates down to a tiny set,
which then gets verified by reading the actual quotation text via
the high-bit stream.

## Open questions about the hash

- What hash function maps a query term → (h_c, h_d, h_e)?
- Are h_c, h_d, h_e three separate hashes, or three different bit-extracts
  of the same hash?
- Is the hash defined over the term's encoded form (via `seg7:0x6dc6`
  table-A encoding) or the raw text?
- What does sentinel 2047 mean exactly — is it "always-no-match" or
  "always-yes-match" or "this quotation has no indexed terms"?

## Empirical results

Picked first non-zero record from suspected table_B at `0xa4d7000`:
`(count=1710, offset=0x7daec)`. Tried decoding the byte stream at two
candidate anchors using both LSB-first and MSB-first continuation-bit
varints:

| Anchor + offset | Decoder | Bytes consumed | Decoded deltas | Valid IDs (in [0, 2.4M]) |
|---|---|---:|---:|---:|
| Section B + 0x7daec | LSB-first | 79 | 48 | 4 |
| Section B + 0x7daec | MSB-first | 79 | 48 | 11 |
| 0x18ce0000 + 0x7daec | LSB-first | 41 | 22 | 6 |
| 0x18ce0000 + 0x7daec | MSB-first | 41 | 22 | 6 |

Result is far below the expected 1710 entries → **not simple varints**. The
payload format is a custom compressed code (likely canonical-Huffman per
the body-decoder family at `seg5:0x28c2`).

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
