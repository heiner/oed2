import {
  BlobRangeSource,
  HttpRangeSource,
  OED2Reader,
  bodyGeometrySummary,
  normalizeSearch,
  renderArticleRecordsHtml,
} from "./oed2.js";

const state = {
  reader: null,
  sourceLabel: "",
  lookupToken: 0,
  selectedIndex: null,
  selectedLabel: "",
  selectedAnnotation: "",
  selectedTargetLogical: null,
  pendingSelectedIndex: null,
  pushUrlOnNextWrite: false,
};

const els = {
  datUrl: document.querySelector("#dat-url"),
  datFile: document.querySelector("#dat-file"),
  connect: document.querySelector("#connect"),
  query: document.querySelector("#query"),
  status: document.querySelector("#status"),
  metrics: document.querySelector("#metrics"),
  results: document.querySelector("#results"),
  articlePane: document.querySelector(".article-pane"),
  articleTitle: document.querySelector("#article-title"),
  articleMeta: document.querySelector("#article-meta"),
  article: document.querySelector("#article"),
};

function setStatus(text, tone = "") {
  els.status.textContent = text;
  els.status.dataset.tone = tone;
}

function setMetrics(text) {
  els.metrics.textContent = text;
}

function clearSelection(clearArticle = false) {
  state.selectedIndex = null;
  state.selectedLabel = "";
  state.selectedAnnotation = "";
  state.selectedTargetLogical = null;
  if (clearArticle) {
    els.articleTitle.textContent = "No article selected";
    els.articleMeta.textContent = "";
    els.article.innerHTML = "";
  }
}

function debounce(fn, delay) {
  let timer = 0;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

function parseUrlState() {
  const params = new URLSearchParams(window.location.search);
  const indexText = params.get("index");
  return {
    dat: params.get("dat") ?? "",
    query: params.get("q") ?? "",
    index: indexText !== null && /^\d+$/.test(indexText) ? Number(indexText) : null,
  };
}

function writeUrlState() {
  const params = new URLSearchParams();
  const dat = els.datUrl.value.trim() || "/OED2.DAT";
  const query = els.query.value.trim();
  params.set("dat", dat);
  if (query) params.set("q", query);
  if (state.selectedIndex !== null) params.set("index", String(state.selectedIndex));
  if (state.selectedLabel) params.set("word", state.selectedLabel);
  if (state.selectedAnnotation) params.set("annotation", state.selectedAnnotation);
  if (state.selectedTargetLogical !== null) {
    params.set("target", state.selectedTargetLogical.toString(16));
  }
  const url = `${window.location.pathname}?${params.toString()}`;
  if (state.pushUrlOnNextWrite) {
    state.pushUrlOnNextWrite = false;
    window.history.pushState(null, "", url);
  } else {
    window.history.replaceState(null, "", url);
  }
}

function lookupUrlFor(query) {
  const params = new URLSearchParams();
  params.set("dat", els.datUrl.value.trim() || "/OED2.DAT");
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
  state.reader = null;
  state.pushUrlOnNextWrite = false;
  clearSelection(true);
  els.results.innerHTML = "";

  const file = els.datFile.files?.[0] ?? null;
  const url = els.datUrl.value.trim() || "/OED2.DAT";
  const source = file ? new BlobRangeSource(file) : new HttpRangeSource(url);
  state.sourceLabel = file ? file.name : url;
  const reader = new OED2Reader(source);

  setStatus("Opening data source...");
  const started = performance.now();
  try {
    const [control, list] = await Promise.all([
      reader.readBodyControl(),
      reader.readOedList("word"),
    ]);
    state.reader = reader;
    const elapsed = Math.round(performance.now() - started);
    setStatus(`Ready: ${state.sourceLabel}`, "ok");
    setMetrics(
      `${list.totalEntries.toLocaleString()} word rows; ` +
        `${bodyGeometrySummary(control)}; opened in ${elapsed} ms`,
    );
    if (els.query.value.trim()) void runLookup({ selectFirst: true });
    else writeUrlState();
  } catch (error) {
    setStatus(error.message, "error");
    setMetrics("");
  }
}

function renderResults(results) {
  els.results.innerHTML = "";
  if (!results.length) {
    const empty = document.createElement("li");
    empty.className = "empty-row";
    empty.textContent = "No matches";
    els.results.append(empty);
    return;
  }

  for (const result of results) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-button";
    button.dataset.index = String(result.index);
    if (state.selectedIndex === result.index) button.classList.add("active");

    const label = document.createElement("span");
    label.className = "result-label";
    label.textContent = result.label || "(blank)";
    if (result.annotation) {
      const annotation = document.createElement("span");
      annotation.className = "result-annotation";
      annotation.textContent = ` ${result.annotation}`;
      label.append(annotation);
    }
    const meta = document.createElement("span");
    meta.className = "result-meta";
    meta.textContent = `#${result.index.toLocaleString()}`;

    button.append(label, meta);
    button.addEventListener("click", () => {
      void selectResult(result.index, result.label, true, result.annotation);
    });
    item.append(button);
    els.results.append(item);
  }
}

function scrollArticleToTarget(target) {
  if (!target || !els.articlePane) return;
  const paneRect = els.articlePane.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const top = els.articlePane.scrollTop + targetRect.top - paneRect.top - 76;
  els.articlePane.scrollTo({ top: Math.max(0, top), behavior: "auto" });
}

async function runLookup({ selectFirst = false } = {}) {
  const reader = state.reader;
  const query = els.query.value.trim();
  const token = ++state.lookupToken;

  if (!reader) {
    setStatus("Connect OED2.DAT first", "error");
    return;
  }
  if (!normalizeSearch(query)) {
    clearSelection(true);
    els.results.innerHTML = "";
    setStatus(`Ready: ${state.sourceLabel}`, "ok");
    writeUrlState();
    return;
  }

  const started = performance.now();
  let lastProbe = "";
  setStatus(`Looking up "${query}"...`);
  try {
    const results = await reader.lookup(query, 48, ({ blockIndex, blocksRead, entriesScanned, marker }) => {
      lastProbe =
        `block ${blockIndex.toLocaleString()} (${blocksRead.toLocaleString()} read), ` +
        `${entriesScanned.toLocaleString()} keys scanned` +
        (marker ? `, marker ${marker}` : "");
      setStatus(lastProbe);
    });
    if (token !== state.lookupToken) return;
    renderResults(results);
    const elapsed = Math.round(performance.now() - started);
    setStatus(
      `${results.length.toLocaleString()} matches in ${elapsed} ms` +
        (lastProbe ? `; ${lastProbe}` : ""),
      "ok",
    );
    const requestedIndex = state.pendingSelectedIndex;
    state.pendingSelectedIndex = null;
    const requested = requestedIndex === null
      ? null
      : results.find((result) => result.index === requestedIndex);
    const selected = requested ?? (selectFirst ? results[0] : null);
    if (selected) {
      await selectResult(selected.index, selected.label, true, selected.annotation);
    } else {
      const currentStillVisible = (
        state.selectedIndex !== null &&
        results.some((result) => result.index === state.selectedIndex)
      );
      if (!currentStillVisible) clearSelection(true);
      renderResults(results);
      writeUrlState();
    }
  } catch (error) {
    if (token !== state.lookupToken) return;
    setStatus(error.message, "error");
  }
}

async function selectResult(index, fallbackLabel = "", updateActive = true, annotation = "") {
  const reader = state.reader;
  if (!reader) return;
  state.selectedIndex = index;
  state.selectedLabel = fallbackLabel || "";
  state.selectedAnnotation = annotation || "";
  state.selectedTargetLogical = null;
  if (updateActive) {
    for (const button of document.querySelectorAll(".result-button")) {
      button.classList.toggle("active", Number(button.dataset.index) === index);
    }
  }
  const title = annotation ? `${fallbackLabel} ${annotation}` : fallbackLabel;
  els.articleTitle.textContent = title || `Word #${index.toLocaleString()}`;
  els.articleMeta.textContent = "Loading article...";
  els.article.innerHTML = "";

  const started = performance.now();
  try {
    const article = await reader.decodeArticleAtOrdinal(index);
    const elapsed = Math.round(performance.now() - started);
    state.selectedTargetLogical = article.targetLogical;
    els.articleTitle.textContent = title || `Word #${index.toLocaleString()}`;
    els.articleMeta.textContent =
      `#${index.toLocaleString()} · ${article.recordCount.toLocaleString()} records · ` +
      `${article.data.length.toLocaleString()} bytes · ` +
      `${elapsed} ms`;
    els.article.innerHTML = renderArticleRecordsHtml(article.records, article.targetLogical, {
      highlightText: fallbackLabel,
    });
    hydrateReferenceLinks();
    writeUrlState();
    if (article.targetLogical !== null && article.targetLogical !== article.logical) {
      const target = document.getElementById(`rec-${article.targetLogical.toString(16)}`);
      window.requestAnimationFrame(() => scrollArticleToTarget(target));
    }
  } catch (error) {
    els.articleMeta.textContent = error.message;
  }
}

els.connect.addEventListener("click", () => void connect());
els.datFile.addEventListener("change", () => void connect());
els.datUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") void connect();
});
els.query.addEventListener("input", debounce(() => void runLookup({ selectFirst: false }), 180));
els.query.addEventListener("keydown", (event) => {
  if (event.key === "Enter") void runLookup({ selectFirst: true });
});
els.article.addEventListener("click", (event) => {
  const link = event.target.closest(".ref-link");
  if (!link || !els.article.contains(link)) return;
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  const ref = link.dataset.ref || link.textContent.replace(/\s+/g, " ").trim();
  if (!ref) return;
  event.preventDefault();
  els.query.value = ref;
  state.pendingSelectedIndex = null;
  state.pushUrlOnNextWrite = true;
  void runLookup({ selectFirst: true });
});

window.addEventListener("popstate", () => {
  const urlState = parseUrlState();
  state.pushUrlOnNextWrite = false;
  if (urlState.dat) els.datUrl.value = urlState.dat;
  els.query.value = urlState.query;
  state.pendingSelectedIndex = urlState.index;
  void connect();
});

const initialUrlState = parseUrlState();
if (initialUrlState.dat) els.datUrl.value = initialUrlState.dat;
if (initialUrlState.query) els.query.value = initialUrlState.query;
state.pendingSelectedIndex = initialUrlState.index;

void connect();
