const PAGE_SIZE = 0x80000;
const MAX_PAGES = 64;

export class PageCachedSource {
  constructor(underlying, { pageSize = PAGE_SIZE, maxPages = MAX_PAGES, persistentStore = null } = {}) {
    this.underlying = underlying;
    this.pageSize = pageSize;
    this.maxPages = maxPages;
    this.store = persistentStore;
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
    const resolvers = new Map();
    for (let p = startPage; p <= endPage; p += 1) {
      if (this.cache.has(p)) continue;
      let resolve;
      let reject;
      const promise = new Promise((res, rej) => {
        resolve = res;
        reject = rej;
      });
      this.cache.set(p, promise);
      promise.catch(() => {
        if (this.cache.get(p) === promise) this.cache.delete(p);
      });
      resolvers.set(p, { resolve, reject });
      missing.push(p);
    }
    if (missing.length === 0) return;

    void this.fillPages(missing, resolvers);
  }

  async fillPages(missing, resolvers) {
    let needNetwork = missing;

    if (this.store) {
      const lookups = await Promise.all(missing.map((p) => this.store.get(p)));
      const remaining = [];
      for (let i = 0; i < missing.length; i += 1) {
        const p = missing[i];
        const hit = lookups[i];
        if (hit && hit.byteLength !== undefined) {
          const bytes = hit instanceof Uint8Array ? hit : new Uint8Array(hit);
          resolvers.get(p).resolve(bytes);
        } else {
          remaining.push(p);
        }
      }
      needNetwork = remaining;
    }

    if (needNetwork.length === 0) return;

    const runs = [];
    let s = needNetwork[0];
    let e = needNetwork[0];
    for (let i = 1; i < needNetwork.length; i += 1) {
      if (needNetwork[i] === e + 1) {
        e = needNetwork[i];
      } else {
        runs.push([s, e]);
        s = needNetwork[i];
        e = needNetwork[i];
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
      if (fetchLength <= 0) {
        for (let p = a; p <= b; p += 1) resolvers.get(p)?.resolve(new Uint8Array());
        continue;
      }

      this.underlying.read(fetchOffset, fetchLength).then(
        (data) => {
          for (let p = a; p <= b; p += 1) {
            const localIndex = p - a;
            const pageOffset = localIndex * this.pageSize;
            if (pageOffset >= data.length) {
              resolvers.get(p)?.resolve(new Uint8Array());
              continue;
            }
            const pageEnd = Math.min(pageOffset + this.pageSize, data.length);
            const pageBytes = data.slice(pageOffset, pageEnd);
            resolvers.get(p)?.resolve(pageBytes);
            if (this.store) void this.store.put(p, pageBytes);
          }
        },
        (err) => {
          for (let p = a; p <= b; p += 1) resolvers.get(p)?.reject(err);
        },
      );
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
