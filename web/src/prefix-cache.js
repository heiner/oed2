export class PrefixCompletionStore {
  constructor() {
    this.data = null;
    this.loadPromise = null;
  }

  async load(url = "./prefix-completions.json") {
    if (this.loadPromise) return this.loadPromise;
    this.loadPromise = (async () => {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`prefix-completions: ${res.status}`);
        this.data = await res.json();
      } catch (err) {
        console.warn("prefix completions unavailable:", err);
      }
    })();
    return this.loadPromise;
  }

  get(prefix) {
    if (!this.data) return null;
    const entries = this.data[prefix];
    if (!entries) return null;
    return entries.map((e) => ({
      index: e[0],
      listLabel: e[1],
      annotation: e[2] ?? "",
      label: e[1],
    }));
  }
}
