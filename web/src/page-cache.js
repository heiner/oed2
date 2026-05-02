const PAGE_SIZE = 0x80000;
const MAX_PAGES = 64;

export class PageCachedSource {
  constructor(underlying, { pageSize = PAGE_SIZE, maxPages = MAX_PAGES } = {}) {
    this.underlying = underlying;
    this.pageSize = pageSize;
    this.maxPages = maxPages;
    // Map<pageIndex, Promise<Uint8Array>> — a Promise that resolves to the
    // page bytes. Stored as Promises (not raw Uint8Array) so concurrent
    // requests for the same in-flight page share one underlying fetch.
    this.cache = new Map();
  }

  get size() {
    return this.underlying.size;
  }

  ensurePages(startPage, endPage) {
    const missing = [];
    for (let p = startPage; p <= endPage; p += 1) {
      if (!this.cache.has(p)) missing.push(p);
    }
    if (missing.length === 0) return;

    const runs = [];
    let s = missing[0];
    let e = missing[0];
    for (let i = 1; i < missing.length; i += 1) {
      if (missing[i] === e + 1) {
        e = missing[i];
      } else {
        runs.push([s, e]);
        s = missing[i];
        e = missing[i];
      }
    }
    runs.push([s, e]);

    for (const [a, b] of runs) {
      const fetchOffset = a * this.pageSize;
      let fetchLength = (b - a + 1) * this.pageSize;
      const total = this.underlying.size;
      if (typeof total === "number" && total > 0) {
        fetchLength = Math.min(fetchLength, total - fetchOffset);
      }
      if (fetchLength <= 0) continue;

      const fetchPromise = this.underlying.read(fetchOffset, fetchLength);
      for (let p = a; p <= b; p += 1) {
        const localIndex = p - a;
        const pagePromise = fetchPromise.then((data) => {
          const pageOffset = localIndex * this.pageSize;
          if (pageOffset >= data.length) return new Uint8Array();
          const pageEnd = Math.min(pageOffset + this.pageSize, data.length);
          return data.slice(pageOffset, pageEnd);
        });
        this.cache.set(p, pagePromise);
        pagePromise.catch(() => {
          if (this.cache.get(p) === pagePromise) this.cache.delete(p);
        });
      }
    }
  }

  async read(offset, length) {
    if (length <= 0) return new Uint8Array();
    const startPage = Math.floor(offset / this.pageSize);
    const endPage = Math.floor((offset + length - 1) / this.pageSize);

    this.ensurePages(startPage, endPage);

    const promises = [];
    for (let p = startPage; p <= endPage; p += 1) {
      promises.push(this.cache.get(p));
    }
    const pages = await Promise.all(promises);

    const out = new Uint8Array(length);
    let written = 0;
    for (let i = 0; i < pages.length; i += 1) {
      const p = startPage + i;
      const pageData = pages[i];
      if (!pageData) continue;
      const pageStart = p * this.pageSize;
      const from = Math.max(0, offset - pageStart);
      const to = Math.min(pageData.length, offset + length - pageStart);
      if (to > from) {
        out.set(pageData.subarray(from, to), written);
        written += to - from;
      }
      // LRU touch.
      const existing = this.cache.get(p);
      if (existing) {
        this.cache.delete(p);
        this.cache.set(p, existing);
      }
    }

    while (this.cache.size > this.maxPages) {
      const oldest = this.cache.keys().next().value;
      this.cache.delete(oldest);
    }

    return out;
  }
}
