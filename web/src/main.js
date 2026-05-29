import {
  OED2Reader,
  normalizeSearch,
  renderArticleRecordsHtml,
} from "./oed2.js";
import { IDBPageStore } from "./idb-store.js";
import { IDBSource } from "./idb-source.js";
import { PrefixCompletionStore } from "./prefix-cache.js";
import { IsoDownloader, PAGE_SIZE, DAT_OFFSET_IN_ISO } from "./iso-downloader.js";

const ARCHIVE_ISO_URL =
  "https://archive.org/download/oxford-english-dictionary-second-edition/Oxford%20English%20Dictionary%20%28Second%20Edition%29.iso";

// On localhost, hit the dev server's /OED2.iso passthrough so we don't pull
// 635 MB from archive.org every test cycle.
const ISO_URL =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "/OED2.iso"
    : ARCHIVE_ISO_URL;

const state = {
  reader: null,
  store: new IDBPageStore(),
  lookupToken: 0,
  loadToken: 0,
  selectedIndex: null,
  pushUrlOnNextWrite: false,
  suggestions: [],
  suggestionFocus: -1,
  prefixCache: new PrefixCompletionStore(),
  download: null, // { abort, promise }
  manifest: null,
};

state.prefixCache.load();

const els = {
  app: document.querySelector("#app"),
  brand: document.querySelector("#brand"),
  query: document.querySelector("#query"),
  suggestions: document.querySelector("#suggestions"),
  status: document.querySelector("#status"),
  searchZone: document.querySelector(".search-zone"),
  articleZone: document.querySelector(".article-zone"),
  articleTitle: document.querySelector("#article-title"),
  articleMeta: document.querySelector("#article-meta"),
  article: document.querySelector("#article"),
  offlineButton: document.querySelector("#offline-button"),
};

function setMode(mode) {
  els.app.dataset.mode = mode;
}

function getMode() {
  return els.app.dataset.mode;
}

function setHasArticle(value) {
  if (value) els.app.dataset.hasArticle = "true";
  else delete els.app.dataset.hasArticle;
}

function setStatus(text, tone = "") {
  els.status.textContent = text;
  els.status.dataset.tone = tone;
}

function clearArticle() {
  state.selectedIndex = null;
  els.articleTitle.textContent = "";
  els.articleMeta.textContent = "";
  els.article.innerHTML = "";
  setHasArticle(false);
}

function hideSuggestions() {
  els.suggestions.hidden = true;
  els.suggestions.innerHTML = "";
  state.suggestions = [];
  state.suggestionFocus = -1;
  els.query.removeAttribute("aria-activedescendant");
}

function debounce(fn, delay) {
  let timer = 0;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

function appendStyledSuffix(target, text) {
  const match = text.match(/^(.*?)\s*(\d+)\s*$/);
  const ps = document.createElement("span");
  ps.className = "tag-ps";
  if (match) {
    ps.textContent = match[1];
    const hm = document.createElement("span");
    hm.className = "tag-hm";
    hm.textContent = match[2];
    ps.append(hm);
  } else {
    ps.textContent = text;
  }
  target.append(ps);
}

function appendSuggestionContent(target, result) {
  const head = result.listLabel || result.label || "(blank)";
  target.append(head);
  let suffix = result.annotation || "";
  if (!suffix && result.label && result.label !== head) {
    if (result.label.toLowerCase().startsWith(head.toLowerCase())) {
      suffix = result.label.slice(head.length).trim();
    }
  }
  if (suffix) {
    target.append(" ");
    appendStyledSuffix(target, suffix);
  }
}

function parseUrlState() {
  const params = new URLSearchParams(window.location.search);
  const indexText = params.get("index");
  return {
    query: params.get("q") ?? "",
    index: indexText !== null && /^\d+$/.test(indexText) ? Number(indexText) : null,
  };
}

function writeUrlState() {
  const params = new URLSearchParams();
  const query = els.query.value.trim();
  if (query) params.set("q", query);
  if (getMode() === "article" && state.selectedIndex !== null) {
    params.set("index", String(state.selectedIndex));
  }
  const queryString = params.toString();
  const url = queryString
    ? `${window.location.pathname}?${queryString}`
    : window.location.pathname;
  if (state.pushUrlOnNextWrite) {
    state.pushUrlOnNextWrite = false;
    window.history.pushState(null, "", url);
  } else {
    window.history.replaceState(null, "", url);
  }
}

function lookupUrlFor(query) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  return `${window.location.pathname}?${params.toString()}`;
}

function hydrateReferenceLinks(root = els.article) {
  for (const link of root.querySelectorAll(".ref-link")) {
    const ref = link.textContent.replace(/\s+/g, " ").trim();
    if (!ref) continue;
    link.dataset.ref = ref;
    link.href = lookupUrlFor(ref);
    link.title = `Look up ${ref}`;
  }
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function baseOfflineState() {
  const m = state.manifest;
  if (state.download) return "downloading";
  if (!m) return "idle";
  if (m.complete) return "complete";
  if ((m.pagesStored ?? 0) > 0) return "partial";
  return "idle";
}

function updateOfflineUi(extra = {}) {
  const uiState = baseOfflineState();
  const button = els.offlineButton;
  if (uiState === "complete") {
    button.hidden = true;
    return;
  }
  button.hidden = false;
  button.dataset.state = uiState;
  if (uiState === "idle") {
    button.textContent = "Download dictionary (~635 MB)";
    button.disabled = false;
  } else if (uiState === "partial") {
    button.textContent = "Resume download";
    button.disabled = false;
  } else if (uiState === "downloading") {
    const { isoReceived = 0, isoTotal = 0 } = extra;
    if (isoTotal > 0) {
      const pct = Math.min(100, (isoReceived / isoTotal) * 100);
      button.textContent = `Downloading… ${pct.toFixed(1)}% (cancel)`;
    } else {
      button.textContent = `Downloading… ${formatBytes(isoReceived)} (cancel)`;
    }
    button.disabled = false;
  }
}

function showOfflineError(message) {
  const button = els.offlineButton;
  button.hidden = false;
  button.dataset.state = "error";
  button.textContent = message;
  button.disabled = true;
}

async function loadManifestAndDecide() {
  if (!(await state.store.ready())) {
    showOfflineError(
      "Your browser does not allow persistent storage. Try in a normal (non-private) window.",
    );
    return;
  }
  const manifest = await state.store.getManifest();
  state.manifest = manifest;
  updateOfflineUi();
  if (manifest?.complete) {
    await connectOffline();
  }
}

async function connectOffline() {
  const datSize = state.manifest?.datSize ?? 0;
  const source = new IDBSource(state.store, { pageSize: PAGE_SIZE, datSize });
  const reader = new OED2Reader(source);
  setStatus("Opening…");
  try {
    await Promise.all([reader.readBodyControl(), reader.readOedList("word")]);
    state.reader = reader;
    setStatus("");
    return true;
  } catch (error) {
    console.error(error);
    setStatus(error.message, "error");
    return false;
  }
}

async function startDownload() {
  if (state.download) return;
  if (!(await state.store.ready())) {
    showOfflineError("Persistent storage not available in this browser.");
    return;
  }
  const controller = new AbortController();
  let isoReceived = 0;
  let isoTotal = 0;
  let pagesStored = 0;
  const downloader = new IsoDownloader({
    url: ISO_URL,
    store: state.store,
    signal: controller.signal,
    onProgress: (ev) => {
      isoReceived = ev.isoReceived;
      isoTotal = ev.isoTotal;
      pagesStored = ev.pagesStored;
      updateOfflineUi({ isoReceived, isoTotal });
      // Persist partial-progress manifest periodically.
      if (ev.type !== "done") {
        state.manifest = {
          complete: false,
          bytesReceived: isoReceived,
          bytesStored: pagesStored * PAGE_SIZE,
          pagesStored,
          datSize: 0,
        };
        // Fire-and-forget — we want to persist progress but not block the
        // streaming reader on each IDB write.
        void state.store.setManifest(state.manifest);
      }
    },
  });
  state.download = { controller };
  updateOfflineUi({ isoReceived: 0, isoTotal: 0 });
  try {
    const summary = await downloader.run();
    state.manifest = {
      complete: true,
      datSize: summary.datSize,
      isoSize: isoReceived,
      pagesStored: summary.pagesStored,
      bytesStored: summary.pagesStored * PAGE_SIZE,
      completedAt: Date.now(),
    };
    await state.store.setManifest(state.manifest);
    state.download = null;
    updateOfflineUi();
    await connectOffline();
    if (els.query.value.trim()) void runLookup({ commit: false });
  } catch (error) {
    state.download = null;
    if (error?.name === "AbortError") {
      // Keep whatever was stored; show partial state.
      state.manifest = await state.store.getManifest();
      updateOfflineUi();
    } else {
      console.error(error);
      showOfflineError(`Download failed: ${error.message}. You can retry.`);
    }
  }
}

function cancelDownload() {
  if (!state.download) return;
  state.download.controller.abort();
}

async function runLookup({ commit = false } = {}) {
  const query = els.query.value.trim();
  const token = ++state.lookupToken;
  const normalized = normalizeSearch(query);

  if (!normalized) {
    hideSuggestions();
    if (!commit) {
      clearArticle();
      setMode("home");
      writeUrlState();
    }
    setStatus("");
    return;
  }

  // Try prefix cache first for 1–2 letter queries (works without a download).
  let drafts = null;
  if (normalized.length === 1 || normalized.length === 2) {
    drafts = state.prefixCache.get(normalized);
  }

  const reader = state.reader;

  if (!drafts && !reader) {
    // Offline data not available — tell the user.
    renderSuggestions([]);
    setStatus("Download the dictionary below to enable full search.", "warn");
    return;
  }

  try {
    if (!drafts) {
      drafts = await reader.lookupDrafts(query, 200);
    }
    if (token !== state.lookupToken) return;
    renderSuggestions(drafts);
    setStatus("");

    const topDraft = drafts[0];
    let previewPromise = null;
    if (!commit && topDraft && getMode() !== "article" && reader) {
      previewPromise = selectResult(topDraft, { switchToArticle: false });
    }

    let results = drafts;
    if (reader) {
      const enrichedPromise = reader.enrichLookup(drafts, 200);
      results = await enrichedPromise;
      if (token !== state.lookupToken) return;
      renderSuggestions(results);
    }

    const top = results[0];
    if (commit) {
      hideSuggestions();
      if (top && reader) {
        state.pushUrlOnNextWrite = true;
        await selectResult(top, { switchToArticle: true });
      } else if (top && !reader) {
        setStatus("Download the dictionary below to view articles.", "warn");
      } else {
        clearArticle();
        setMode("article");
        writeUrlState();
      }
    } else {
      if (previewPromise) await previewPromise;
      writeUrlState();
    }
  } catch (error) {
    if (token !== state.lookupToken) return;
    setStatus(error.message, "error");
  }
}

function renderSuggestions(results) {
  state.suggestions = results;
  state.suggestionFocus = -1;
  els.query.removeAttribute("aria-activedescendant");
  els.suggestions.innerHTML = "";

  if (!results.length) {
    if (els.query.value.trim() && document.activeElement === els.query) {
      const empty = document.createElement("li");
      empty.className = "suggestion-empty";
      empty.textContent = "No matches";
      els.suggestions.append(empty);
      els.suggestions.hidden = false;
    } else {
      els.suggestions.hidden = true;
    }
    return;
  }

  for (let i = 0; i < results.length; i += 1) {
    const result = results[i];
    const item = document.createElement("li");
    const button = document.createElement("div");
    button.className = "suggestion";
    button.id = `sugg-${i}`;
    button.setAttribute("role", "option");
    button.dataset.index = String(i);
    appendSuggestionContent(button, result);
    item.append(button);
    els.suggestions.append(item);
  }
  els.suggestions.hidden = document.activeElement !== els.query;
}

function focusSuggestion(index) {
  const items = els.suggestions.querySelectorAll(".suggestion");
  for (const item of items) item.removeAttribute("aria-selected");
  if (index < 0 || index >= items.length) {
    state.suggestionFocus = -1;
    els.query.removeAttribute("aria-activedescendant");
    return;
  }
  const target = items[index];
  target.setAttribute("aria-selected", "true");
  els.query.setAttribute("aria-activedescendant", target.id);
  target.scrollIntoView({ block: "nearest" });
  state.suggestionFocus = index;
}

function scrollArticleToTarget(target) {
  if (!target) return;
  target.scrollIntoView({ block: "start", behavior: "auto" });
}

async function selectResult(result, { switchToArticle = true } = {}) {
  const reader = state.reader;
  if (!reader) {
    setStatus("Download the dictionary below to view articles.", "warn");
    return;
  }
  const loadToken = ++state.loadToken;
  state.selectedIndex = result.index;

  if (result.labelHtml) {
    els.articleTitle.innerHTML = result.labelHtml;
  } else if (result.listLabel || result.label) {
    els.articleTitle.textContent = result.listLabel || result.label;
  } else {
    els.articleTitle.textContent = `Word #${result.index.toLocaleString()}`;
  }
  els.articleMeta.textContent = "";
  els.article.innerHTML = "";
  setHasArticle(true);

  if (switchToArticle) {
    setMode("article");
    hideSuggestions();
  }

  try {
    const article = await reader.decodeArticleAtOrdinal(result.index);
    if (loadToken !== state.loadToken) return;
    els.article.innerHTML = renderArticleRecordsHtml(article.records, article.targetLogical, {
      highlightText: result.label,
    });
    hydrateReferenceLinks();
    writeUrlState();
    if (switchToArticle && article.targetLogical !== null && article.targetLogical !== article.logical) {
      const target = document.getElementById(`rec-${article.targetLogical.toString(16)}`);
      window.requestAnimationFrame(() => scrollArticleToTarget(target));
    }
  } catch (error) {
    if (loadToken !== state.loadToken) return;
    els.articleMeta.textContent = error.message;
  }
}

function goHome({ clearQuery = false } = {}) {
  setMode("home");
  hideSuggestions();
  clearArticle();
  if (clearQuery) els.query.value = "";
  els.query.focus();
  writeUrlState();
  window.scrollTo({ top: 0 });
}

function commitToArticle() {
  if (getMode() === "article") return;
  const before = els.articleZone.getBoundingClientRect().top;
  setMode("article");
  const after = els.articleZone.getBoundingClientRect().top;
  if (before !== after) window.scrollBy(0, after - before);
  hideSuggestions();
  state.pushUrlOnNextWrite = true;
  writeUrlState();
}

const searchZoneObserver = new IntersectionObserver(
  ([entry]) => {
    if (entry.isIntersecting) return;
    if (getMode() !== "home") return;
    if (els.app.dataset.hasArticle !== "true") return;
    commitToArticle();
  },
  { threshold: 0 },
);
searchZoneObserver.observe(els.searchZone);

els.query.addEventListener("input", debounce(() => void runLookup({ commit: false }), 180));

els.query.addEventListener("focus", () => {
  if (state.suggestions.length > 0) {
    els.suggestions.hidden = false;
  } else if (els.query.value.trim()) {
    void runLookup({ commit: false });
  }
});

els.query.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    if (state.suggestionFocus >= 0) {
      const result = state.suggestions[state.suggestionFocus];
      if (result) {
        state.pushUrlOnNextWrite = true;
        void selectResult(result, { switchToArticle: true });
      }
    } else {
      void runLookup({ commit: true });
    }
  } else if (event.key === "ArrowDown") {
    if (state.suggestions.length === 0) return;
    event.preventDefault();
    const next = state.suggestionFocus + 1 >= state.suggestions.length
      ? 0
      : state.suggestionFocus + 1;
    focusSuggestion(next);
  } else if (event.key === "ArrowUp") {
    if (state.suggestions.length === 0) return;
    event.preventDefault();
    const next = state.suggestionFocus <= 0
      ? state.suggestions.length - 1
      : state.suggestionFocus - 1;
    focusSuggestion(next);
  } else if (event.key === "Escape") {
    if (!els.suggestions.hidden) {
      hideSuggestions();
    } else if (els.query.value || getMode() === "article") {
      els.query.value = "";
      goHome({ clearQuery: false });
    }
  }
});

els.suggestions.addEventListener("click", (event) => {
  const item = event.target.closest(".suggestion");
  if (!item) return;
  const index = Number(item.dataset.index);
  const result = state.suggestions[index];
  if (!result) return;
  state.pushUrlOnNextWrite = true;
  els.query.value = result.listLabel || result.label || els.query.value;
  void selectResult(result, { switchToArticle: true });
});

els.suggestions.addEventListener("mousemove", (event) => {
  const item = event.target.closest(".suggestion");
  if (!item) return;
  const index = Number(item.dataset.index);
  if (Number.isFinite(index) && index !== state.suggestionFocus) focusSuggestion(index);
});

document.addEventListener("click", (event) => {
  if (!els.suggestions.contains(event.target) && event.target !== els.query) {
    if (!els.suggestions.hidden) els.suggestions.hidden = true;
  }
});

els.brand.addEventListener("click", (event) => {
  event.preventDefault();
  state.pushUrlOnNextWrite = true;
  goHome({ clearQuery: true });
});

els.article.addEventListener("click", (event) => {
  const link = event.target.closest(".ref-link");
  if (!link || !els.article.contains(link)) return;
  if (
    event.defaultPrevented ||
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  ) return;
  const ref = link.dataset.ref || link.textContent.replace(/\s+/g, " ").trim();
  if (!ref) return;
  event.preventDefault();
  els.query.value = ref;
  state.pushUrlOnNextWrite = true;
  void runLookup({ commit: true });
});

els.offlineButton?.addEventListener("click", () => {
  if (state.download) {
    cancelDownload();
  } else {
    void startDownload();
  }
});

window.addEventListener("beforeunload", (event) => {
  if (state.download) {
    event.preventDefault();
    event.returnValue =
      "A dictionary download is in progress. Leaving will pause it; you can resume later.";
    return event.returnValue;
  }
});

window.addEventListener("popstate", () => {
  state.pushUrlOnNextWrite = false;
  void hydrateFromUrl();
});

async function hydrateFromUrl() {
  const urlState = parseUrlState();
  els.query.value = urlState.query;
  await loadManifestAndDecide();
  if (urlState.index !== null) {
    setMode("article");
    const reader = state.reader;
    if (!reader) {
      setStatus("Download the dictionary below to view articles.", "warn");
      return;
    }
    try {
      let requested = null;
      if (urlState.query) {
        const results = await reader.lookup(urlState.query, 200);
        requested = results.find((r) => r.index === urlState.index) ?? null;
      }
      if (!requested) {
        const headgroup = await reader.headgroupAtOrdinal(urlState.index);
        requested = {
          ...headgroup,
          listLabel: headgroup.label,
          label: headgroup.label,
          annotation: "",
        };
      }
      hideSuggestions();
      await selectResult(requested, { switchToArticle: true });
    } catch (error) {
      setStatus(error.message, "error");
    }
  } else if (urlState.query) {
    setMode("home");
    void runLookup({ commit: false });
  } else {
    setMode("home");
    hideSuggestions();
    clearArticle();
  }
  if (getMode() === "home") els.query.focus();
}

void hydrateFromUrl();
