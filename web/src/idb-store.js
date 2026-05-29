const DB_NAME = "oed2";
const STORE_PAGES = "pages";
const STORE_META = "meta";
const DB_VERSION = 2;
const MANIFEST_KEY = "manifest";

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (event) => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_PAGES)) {
        db.createObjectStore(STORE_PAGES);
      }
      if (!db.objectStoreNames.contains(STORE_META)) {
        db.createObjectStore(STORE_META);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    req.onblocked = () => reject(new Error("indexedDB open blocked"));
  });
}

export class IDBPageStore {
  constructor() {
    this.dbPromise = openDB().catch((err) => {
      console.warn("IDB unavailable:", err);
      return null;
    });
  }

  async ready() {
    return (await this.dbPromise) !== null;
  }

  async get(pageIndex) {
    const db = await this.dbPromise;
    if (!db) return null;
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_PAGES, "readonly");
      const req = tx.objectStore(STORE_PAGES).get(pageIndex);
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => resolve(null);
    });
  }

  async put(pageIndex, bytes) {
    const db = await this.dbPromise;
    if (!db) return;
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_PAGES, "readwrite");
      tx.objectStore(STORE_PAGES).put(bytes, pageIndex);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    });
  }

  async getManifest() {
    const db = await this.dbPromise;
    if (!db) return null;
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_META, "readonly");
      const req = tx.objectStore(STORE_META).get(MANIFEST_KEY);
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => resolve(null);
    });
  }

  async setManifest(manifest) {
    const db = await this.dbPromise;
    if (!db) return;
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_META, "readwrite");
      tx.objectStore(STORE_META).put(manifest, MANIFEST_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    });
  }

  async clearAll() {
    const db = await this.dbPromise;
    if (!db) return;
    return new Promise((resolve) => {
      const tx = db.transaction([STORE_PAGES, STORE_META], "readwrite");
      tx.objectStore(STORE_PAGES).clear();
      tx.objectStore(STORE_META).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    });
  }
}
