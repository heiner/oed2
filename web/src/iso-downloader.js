// Streams the OED2 ISO from archive.org, slicing it into DAT-aligned pages
// and persisting only the pages we actually use to IndexedDB.
//
// The CORS-enabled archive.org URL does not honour Range requests, so the
// whole ISO must be transferred even on resume. We mitigate this by being
// selective about what gets stored — pages that fall entirely inside the
// known-unused Section B / QT region are simply discarded as they fly by.

export const PAGE_SIZE = 0x80000;
export const DAT_OFFSET_IN_ISO = 0xa800;

// Ranges of DAT bytes that we *don't* need to keep on disk.
// (Pages that lie entirely inside one of these ranges are skipped.)
//   0x0243b100..0x0a08c000  Section B — compressed QT posting lists (~130 MB)
//   0x0a08c000..0x0b01ce00  QT lexicon + unidentified post-QT region (~16 MB)
const DROP_RANGES = [[0x0243b100, 0x0b01ce00]];

export function pageIsKept(pageIndex, pageSize = PAGE_SIZE) {
  const start = pageIndex * pageSize;
  const end = start + pageSize;
  for (const [a, b] of DROP_RANGES) {
    if (start >= a && end <= b) return false;
  }
  return true;
}

export function countKeptPages(datSize, pageSize = PAGE_SIZE) {
  const total = Math.ceil(datSize / pageSize);
  let kept = 0;
  for (let p = 0; p < total; p += 1) {
    if (pageIsKept(p, pageSize)) kept += 1;
  }
  return kept;
}

export function estimatedStoredBytes(datSize, pageSize = PAGE_SIZE) {
  return countKeptPages(datSize, pageSize) * pageSize;
}

export class IsoDownloader {
  constructor({ url, store, onProgress, signal, pageSize = PAGE_SIZE, datOffset = DAT_OFFSET_IN_ISO }) {
    this.url = url;
    this.store = store;
    this.onProgress = onProgress;
    this.signal = signal;
    this.pageSize = pageSize;
    this.datOffset = datOffset;
  }

  async run() {
    const response = await fetch(this.url, { signal: this.signal, cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
    if (!response.body) throw new Error("Response has no body stream");
    const isoTotal = Number(response.headers.get("content-length")) || 0;

    const reader = response.body.getReader();
    const pageBuffer = new Uint8Array(this.pageSize);
    let pageIndex = 0;
    let pageFill = 0;
    let bytesToSkipHeader = this.datOffset;
    let isoReceived = 0;
    let pagesStored = 0;
    let pagesSkipped = 0;
    let lastReportedAt = 0;
    const reportEvery = 256 * 1024; // 256 KB

    const emit = (eventType = "progress", extra = {}) => {
      this.onProgress?.({
        type: eventType,
        isoReceived,
        isoTotal,
        pagesStored,
        pagesSkipped,
        ...extra,
      });
    };

    const flushPage = async () => {
      if (pageFill === 0) return;
      const keep = pageIsKept(pageIndex, this.pageSize);
      if (keep) {
        const slice = pageBuffer.slice(0, pageFill);
        await this.store.put(pageIndex, slice);
        pagesStored += 1;
      } else {
        pagesSkipped += 1;
      }
      pageIndex += 1;
      pageFill = 0;
    };

    emit("start");

    try {
      while (true) {
        if (this.signal?.aborted) throw new DOMException("Aborted", "AbortError");
        const { value, done } = await reader.read();
        if (done) break;

        let pos = 0;
        const chunk = value;

        if (bytesToSkipHeader > 0) {
          const skip = Math.min(bytesToSkipHeader, chunk.length);
          bytesToSkipHeader -= skip;
          pos += skip;
        }

        while (pos < chunk.length) {
          const want = this.pageSize - pageFill;
          const have = chunk.length - pos;
          const take = Math.min(want, have);
          // Skip the actual byte copy when the destination page will be
          // discarded — saves CPU on hundreds of MB.
          if (pageIsKept(pageIndex, this.pageSize)) {
            pageBuffer.set(chunk.subarray(pos, pos + take), pageFill);
          }
          pageFill += take;
          pos += take;
          if (pageFill === this.pageSize) {
            await flushPage();
          }
        }

        isoReceived += chunk.length;
        if (isoReceived - lastReportedAt >= reportEvery) {
          lastReportedAt = isoReceived;
          emit("progress");
        }
      }
      // Tail-end partial page (DAT typically ends mid-page).
      if (pageFill > 0) await flushPage();
    } finally {
      try {
        reader.releaseLock();
      } catch (_) {
        /* noop */
      }
    }

    emit("done", { complete: true });

    return {
      isoReceived,
      pagesStored,
      pagesSkipped,
      datSize: pageIndex * this.pageSize + pageFill,
    };
  }
}
