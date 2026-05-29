// Reads DAT bytes purely from IndexedDB (no network).
// Used after the ISO download is complete.

import { PAGE_SIZE, pageIsKept } from "./iso-downloader.js";

export class IDBSource {
  constructor(store, { pageSize = PAGE_SIZE, datSize = 0 } = {}) {
    this.store = store;
    this.pageSize = pageSize;
    this.size = datSize;
    this.pageCache = new Map(); // in-memory LRU on top of IDB
    this.maxPages = 32;
  }

  async getPage(pageIndex) {
    let cached = this.pageCache.get(pageIndex);
    if (cached) {
      // LRU touch
      this.pageCache.delete(pageIndex);
      this.pageCache.set(pageIndex, cached);
      return cached;
    }
    if (!pageIsKept(pageIndex, this.pageSize)) {
      // The page was deliberately dropped during download — should never
      // be read. Surface this loudly so we can fix the drop list.
      throw new Error(
        `Page ${pageIndex} (offset 0x${(pageIndex * this.pageSize).toString(16)}) ` +
          `was not stored locally. Either the drop range is too aggressive ` +
          `or this is a code path we don't support offline yet.`,
      );
    }
    const bytes = await this.store.get(pageIndex);
    if (!bytes) {
      throw new Error(
        `Missing page ${pageIndex} in local storage. The download may be incomplete.`,
      );
    }
    const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    this.pageCache.set(pageIndex, u8);
    while (this.pageCache.size > this.maxPages) {
      const oldest = this.pageCache.keys().next().value;
      this.pageCache.delete(oldest);
    }
    return u8;
  }

  async read(offset, length) {
    if (length <= 0) return new Uint8Array();
    const startPage = Math.floor(offset / this.pageSize);
    const endPage = Math.floor((offset + length - 1) / this.pageSize);
    const out = new Uint8Array(length);
    let written = 0;
    for (let p = startPage; p <= endPage; p += 1) {
      const pageBytes = await this.getPage(p);
      const pageStart = p * this.pageSize;
      const from = Math.max(0, offset - pageStart);
      const to = Math.min(pageBytes.length, offset + length - pageStart);
      if (to > from) {
        out.set(pageBytes.subarray(from, to), written);
        written += to - from;
      }
    }
    return out;
  }
}
