const CHUNK_SIZE = 0x100000;
const META_STORE = "meta";
const CHUNK_STORE = "chunks";
const META_SIZE = "size";
const META_PERSISTED = "persisted";
const META_URL = "url";

export class IDBStreamingSource {
  constructor(url, { dbName = "oed2-iso" } = {}) {
    this.url = url;
    this.dbName = dbName;
    this.size = null;
    this.bytesPersisted = 0;
    this.complete = false;
    this.dbPromise = null;
    this.startPromise = null;
    this.waiters = [];
    this.onProgress = null;
  }

  log(msg, ...rest) {
    console.log(`[idb-iso] ${msg}`, ...rest);
  }

  async openDb() {
    if (this.dbPromise) return this.dbPromise;
    this.dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(this.dbName, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(CHUNK_STORE)) db.createObjectStore(CHUNK_STORE);
        if (!db.objectStoreNames.contains(META_STORE)) db.createObjectStore(META_STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.dbPromise;
  }

  async getMeta(key) {
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(META_STORE, "readonly");
      const req = tx.objectStore(META_STORE).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async getChunk(index) {
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(CHUNK_STORE, "readonly");
      const req = tx.objectStore(CHUNK_STORE).get(index);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  }

  async writeChunkAndMeta(index, data, persistedAfter) {
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction([CHUNK_STORE, META_STORE], "readwrite");
      tx.objectStore(CHUNK_STORE).put(data, index);
      tx.objectStore(META_STORE).put(persistedAfter, META_PERSISTED);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  }

  async writeMeta(entries) {
    const db = await this.openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(META_STORE, "readwrite");
      const store = tx.objectStore(META_STORE);
      for (const [k, v] of entries) store.put(v, k);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  emitProgress() {
    if (this.onProgress) {
      this.onProgress({
        downloaded: this.bytesPersisted,
        total: this.size,
        complete: this.complete,
      });
    }
  }

  resolveWaiters() {
    const remaining = [];
    for (const w of this.waiters) {
      if (this.complete || w.endByte <= this.bytesPersisted) w.resolve();
      else remaining.push(w);
    }
    this.waiters = remaining;
  }

  rejectAllWaiters(error) {
    for (const w of this.waiters) w.reject(error);
    this.waiters = [];
  }

  async start() {
    if (this.startPromise) return this.startPromise;
    this.startPromise = (async () => {
      this.log("start: opening IDB", this.dbName);
      const persistedUrl = await this.getMeta(META_URL);
      if (persistedUrl && persistedUrl !== this.url) {
        this.log("start: URL changed, resetting cache", { was: persistedUrl, now: this.url });
        await this.reset();
      }
      const persistedSize = await this.getMeta(META_SIZE);
      const persisted = await this.getMeta(META_PERSISTED);
      if (persistedSize) this.size = persistedSize;
      if (persisted) this.bytesPersisted = persisted;
      this.log("start: meta", { size: this.size, persisted: this.bytesPersisted });
      this.emitProgress();
      if (this.size && this.bytesPersisted >= this.size) {
        this.log("start: already complete");
        this.complete = true;
        this.emitProgress();
        this.resolveWaiters();
        return;
      }
      try {
        await this.streamDownload();
      } catch (error) {
        this.log("streamDownload error", error);
        this.rejectAllWaiters(error);
        throw error;
      }
    })();
    return this.startPromise;
  }

  async reset() {
    const db = await this.openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction([CHUNK_STORE, META_STORE], "readwrite");
      tx.objectStore(CHUNK_STORE).clear();
      tx.objectStore(META_STORE).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    this.size = null;
    this.bytesPersisted = 0;
    this.complete = false;
  }

  async streamDownload() {
    this.log("fetch", this.url);
    const response = await fetch(this.url);
    this.log("fetch returned", { ok: response.ok, status: response.status });
    if (!response.ok) throw new Error(`Source returned HTTP ${response.status}`);
    const totalHeader = parseInt(response.headers.get("content-length") ?? "0", 10);
    if (totalHeader && this.size !== totalHeader) {
      this.size = totalHeader;
      await this.writeMeta([[META_SIZE, totalHeader], [META_URL, this.url]]);
    }
    this.emitProgress();

    const reader = response.body.getReader();
    let pending = new Uint8Array(CHUNK_SIZE);
    let pendingFilled = 0;
    const skipUntil = this.bytesPersisted;
    let nextChunkIndex = Math.floor(skipUntil / CHUNK_SIZE);
    let streamSeen = 0;
    this.log("stream begin", { skipUntil, firstChunkIndex: nextChunkIndex });

    let lastEmit = performance.now();

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          this.log("stream done flag");
          break;
        }
        streamSeen += value.length;

        let remaining = value;
        if (streamSeen <= skipUntil) {
          if (this.size && streamSeen >= this.size) break;
          if (performance.now() - lastEmit > 200) {
            this.emitProgress();
            lastEmit = performance.now();
          }
          continue;
        }
        if (streamSeen - value.length < skipUntil) {
          const drop = skipUntil - (streamSeen - value.length);
          remaining = value.subarray(drop);
        }

        let chunkOffset = 0;
        while (chunkOffset < remaining.length) {
          const space = CHUNK_SIZE - pendingFilled;
          const take = Math.min(space, remaining.length - chunkOffset);
          pending.set(remaining.subarray(chunkOffset, chunkOffset + take), pendingFilled);
          pendingFilled += take;
          chunkOffset += take;
          if (pendingFilled === CHUNK_SIZE) {
            const idx = nextChunkIndex;
            nextChunkIndex += 1;
            const persistedAfter = (idx + 1) * CHUNK_SIZE;
            await this.writeChunkAndMeta(idx, pending, persistedAfter);
            this.bytesPersisted = persistedAfter;
            pending = new Uint8Array(CHUNK_SIZE);
            pendingFilled = 0;
            this.resolveWaiters();
            if (performance.now() - lastEmit > 200) {
              this.emitProgress();
              lastEmit = performance.now();
            }
          }
        }
        if (this.size && streamSeen >= this.size) break;
      }
    } finally {
      try { await reader.cancel(); } catch (_) { /* ignore */ }
    }

    if (pendingFilled > 0) {
      const idx = nextChunkIndex;
      nextChunkIndex += 1;
      const data = pending.slice(0, pendingFilled);
      const persistedAfter = idx * CHUNK_SIZE + pendingFilled;
      await this.writeChunkAndMeta(idx, data, persistedAfter);
      this.bytesPersisted = persistedAfter;
    }

    this.complete = true;
    this.log("complete", { persisted: this.bytesPersisted, size: this.size, streamSeen });
    this.emitProgress();
    this.resolveWaiters();
  }

  async waitFor(endByte) {
    if (this.complete || endByte <= this.bytesPersisted) return;
    return new Promise((resolve, reject) => {
      this.waiters.push({ endByte, resolve, reject });
    });
  }

  async read(offset, length) {
    if (length <= 0) return new Uint8Array();
    const end = offset + length;
    await this.waitFor(end);

    const startChunk = Math.floor(offset / CHUNK_SIZE);
    const endChunk = Math.floor((end - 1) / CHUNK_SIZE);
    const out = new Uint8Array(length);
    let written = 0;
    for (let c = startChunk; c <= endChunk; c += 1) {
      const data = await this.getChunk(c);
      if (!data) throw new Error(`Cached chunk ${c} missing`);
      const chunkStart = c * CHUNK_SIZE;
      const from = Math.max(0, offset - chunkStart);
      const to = Math.min(data.length, end - chunkStart);
      if (to > from) {
        out.set(data.subarray(from, to), written);
        written += to - from;
      }
    }
    return out;
  }
}

export async function clearIsoCache(dbName = "oed2-iso") {
  return new Promise((resolve, reject) => {
    const req = indexedDB.deleteDatabase(dbName);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
    req.onblocked = () => resolve();
  });
}
