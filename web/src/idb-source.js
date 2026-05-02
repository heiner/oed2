const PAGE_SIZE = 0x10000;

export class IDBCachedRangeSource {
  constructor(underlying, { dbName = "oed2-iso-cache", storeName = "pages" } = {}) {
    this.underlying = underlying;
    this.dbName = dbName;
    this.storeName = storeName;
    this.dbPromise = null;
  }

  get size() {
    return this.underlying.size;
  }

  async openDb() {
    if (this.dbPromise) return this.dbPromise;
    this.dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(this.dbName, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.dbPromise;
  }

  async readPages(startPage, endPage) {
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, "readonly");
      const store = tx.objectStore(this.storeName);
      const result = new Map();
      const total = endPage - startPage + 1;
      if (total <= 0) {
        resolve(result);
        return;
      }
      let pending = total;
      for (let p = startPage; p <= endPage; p += 1) {
        const key = p;
        const req = store.get(key);
        req.onsuccess = () => {
          if (req.result) result.set(key, req.result);
          pending -= 1;
          if (pending === 0) resolve(result);
        };
        req.onerror = () => reject(req.error);
      }
    });
  }

  async writePages(pages) {
    if (pages.size === 0) return;
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(this.storeName, "readwrite");
      const store = tx.objectStore(this.storeName);
      for (const [page, data] of pages) store.put(data, page);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  }

  async read(offset, length) {
    if (length <= 0) return new Uint8Array();
    const startPage = Math.floor(offset / PAGE_SIZE);
    const endPage = Math.floor((offset + length - 1) / PAGE_SIZE);
    const cached = await this.readPages(startPage, endPage);

    const runs = [];
    let runStart = -1;
    for (let p = startPage; p <= endPage; p += 1) {
      if (cached.has(p)) {
        if (runStart >= 0) {
          runs.push([runStart, p - 1]);
          runStart = -1;
        }
      } else if (runStart < 0) {
        runStart = p;
      }
    }
    if (runStart >= 0) runs.push([runStart, endPage]);

    for (const [a, b] of runs) {
      const fetchOffset = a * PAGE_SIZE;
      let fetchLength = (b - a + 1) * PAGE_SIZE;
      if (this.underlying.size !== null && this.underlying.size !== undefined) {
        fetchLength = Math.min(fetchLength, this.underlying.size - fetchOffset);
      }
      if (fetchLength <= 0) continue;
      const data = await this.underlying.read(fetchOffset, fetchLength);
      const fresh = new Map();
      for (let p = a; p <= b; p += 1) {
        const pageOffset = (p - a) * PAGE_SIZE;
        if (pageOffset >= data.length) break;
        const pageEnd = Math.min(pageOffset + PAGE_SIZE, data.length);
        const slice = data.slice(pageOffset, pageEnd);
        fresh.set(p, slice);
        cached.set(p, slice);
      }
      try {
        await this.writePages(fresh);
      } catch (error) {
        console.warn("IDB cache write failed", error);
      }
    }

    const out = new Uint8Array(length);
    let written = 0;
    for (let p = startPage; p <= endPage; p += 1) {
      const page = cached.get(p);
      if (!page) continue;
      const pageStart = p * PAGE_SIZE;
      const from = Math.max(0, offset - pageStart);
      const to = Math.min(page.length, offset + length - pageStart);
      if (to > from) {
        out.set(page.subarray(from, to), written);
        written += to - from;
      }
    }
    return out;
  }
}

export async function clearIsoCache(dbName = "oed2-iso-cache") {
  return new Promise((resolve, reject) => {
    const req = indexedDB.deleteDatabase(dbName);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
    req.onblocked = () => resolve();
  });
}
