import {
  HttpRangeSource,
  OED2Reader,
  normalizeSearch,
  renderArticleRecordsHtml,
} from "./oed2.js";
import { PageCachedSource } from "./page-cache.js";

const ISO_URL = "https://misty-heart-2775.heiner-a97.workers.dev/";
const DAT_OFFSET_IN_ISO = 0xa800;

const state = {
  reader: null,
  lookupToken: 0,
  loadToken: 0,
  selectedIndex: null,
  pushUrlOnNextWrite: false,
  suggestions: [],
  suggestionFocus: -1,
};

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

async function connect() {
  const network = new HttpRangeSource(ISO_URL, DAT_OFFSET_IN_ISO);
  const cached = new PageCachedSource(network);
  const reader = new OED2Reader(cached);
  setStatus("Opening…");
  try {
    await Promise.all([reader.readBodyControl(), reader.readOedList("word")]);
    state.reader = reader;
    setStatus("");
    return true;
  } catch (error) {
    setStatus(error.message, "error");
    return false;
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

async function runLookup({ commit = false } = {}) {
  const reader = state.reader;
  const query = els.query.value.trim();
  const token = ++state.lookupToken;

  if (!reader) return;
  if (!normalizeSearch(query)) {
    hideSuggestions();
    if (!commit) {
      clearArticle();
      setMode("home");
      writeUrlState();
    }
    setStatus("");
    return;
  }

  try {
    const results = await reader.lookup(query, 50);
    if (token !== state.lookupToken) return;
    renderSuggestions(results);
    setStatus("");

    const top = results[0];
    if (commit) {
      hideSuggestions();
      if (top) {
        state.pushUrlOnNextWrite = true;
        await selectResult(top, { switchToArticle: true });
      } else {
        clearArticle();
        setMode("article");
        writeUrlState();
      }
    } else if (top && getMode() !== "article") {
      await selectResult(top, { switchToArticle: false });
    } else {
      writeUrlState();
    }
  } catch (error) {
    if (token !== state.lookupToken) return;
    setStatus(error.message, "error");
  }
}

function scrollArticleToTarget(target) {
  if (!target) return;
  target.scrollIntoView({ block: "start", behavior: "auto" });
}

async function selectResult(result, { switchToArticle = true } = {}) {
  const reader = state.reader;
  if (!reader) return;
  const loadToken = ++state.loadToken;
  state.selectedIndex = result.index;

  if (result.labelHtml) {
    els.articleTitle.innerHTML = result.labelHtml;
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
  } else if (els.query.value.trim() && state.reader) {
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

window.addEventListener("popstate", () => {
  state.pushUrlOnNextWrite = false;
  void hydrateFromUrl({ skipConnect: !!state.reader });
});

async function hydrateFromUrl({ skipConnect = false } = {}) {
  const urlState = parseUrlState();
  els.query.value = urlState.query;
  if (!skipConnect) {
    const ok = await connect();
    if (!ok) return;
  }
  if (urlState.index !== null) {
    setMode("article");
    const reader = state.reader;
    if (!reader) return;
    try {
      let requested = null;
      if (urlState.query) {
        const results = await reader.lookup(urlState.query, 50);
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
