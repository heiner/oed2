import assert from "node:assert/strict";
import { open } from "node:fs/promises";
import { OED2Reader, renderArticleHtml, renderArticleRecordsHtml } from "./src/oed2.js";

const datPath = process.argv[2] ?? "/Volumes/OED2/OED2.DAT";

class NodeFileSource {
  constructor(handle) {
    this.handle = handle;
  }

  async read(offset, length) {
    const buffer = Buffer.alloc(length);
    const { bytesRead } = await this.handle.read(buffer, 0, length, offset);
    if (bytesRead !== length) {
      throw new Error(`Short read at 0x${offset.toString(16)}`);
    }
    return new Uint8Array(buffer.buffer, buffer.byteOffset, bytesRead);
  }
}

const handle = await open(datPath, "r");
const resultText = (result) => (
  `${result.index}:${result.annotation ? `${result.label} ${result.annotation}` : result.label}`
);

try {
  const reader = new OED2Reader(new NodeFileSource(handle));
  const control = await reader.readBodyControl();
  const list = await reader.readOedList("word");
  assert.equal(control.blockCount, 7829);
  assert.equal(list.totalEntries, 473257);
  console.log(`body blocks=${control.blockCount} word rows=${list.totalEntries}`);

  const absolute = await reader.headgroupAtOrdinal(1000);
  assert.equal(absolute.label, "absolute a.");
  console.log(`word[1000] ${absolute.label} logical=0x${absolute.logical.toString(16)}`);

  const results = await reader.lookup("absolute", 8);
  assert.deepEqual(
    results.map(resultText),
    [
      "1000:absolute a.",
      "1001:absolute address",
      "1002:absolute altitude",
      "1003:absolute ceiling",
      "1004:absolute error",
      "1005:absolute humidity",
      "1006:absolutely adv.",
      "1007:absolute magnitude",
    ],
  );
  console.log(results.map(resultText).join("\n"));

  const screw = await reader.lookup("screw", 12);
  assert.deepEqual(screw.slice(0, 4).map(resultText), [
    "349080:screw n. 1",
    "349081:screw n. 2",
    "349082:screw n. 3",
    "349083:screw v.",
  ]);
  const screwball = await reader.lookup("screwball", 4);
  assert.deepEqual(screwball.slice(0, 3).map(resultText), [
    "349091:screwball n.",
    "349092:screwball a.",
    "349093:screwballism",
  ]);

  const article = await reader.decodeArticleAtOrdinal(1000);
  const text = renderArticleHtml(article.data)
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/\u00a0/g, " ")
    .replace(/\u2060/g, "")
    .slice(0, 160);
  assert.match(text, /^absolute /);
  console.log(text);

  const fucking = await reader.lookup("fucking", 8);
  assert.deepEqual(fucking.map((result) => `${result.index}:${result.label}`), [
    "138207:fucking",
  ]);
  assert.equal(fucking[0].annotation, "vbl. n.");
  const fuckingArticle = await reader.decodeArticleAtOrdinal(138207);
  assert.equal(fuckingArticle.logical, 0xf19a9d);
  assert.equal(fuckingArticle.targetLogical, 0xf19d8f);
  const fuckingHtml = renderArticleRecordsHtml(fuckingArticle.records, fuckingArticle.targetLogical);
  const fuckingText = fuckingHtml.replace(/<[^>]+>/g, "");
  assert.match(fuckingHtml, /f\u028ck/);
  assert.match(fuckingHtml, /<span id="rec-f19d8f" class="record-anchor target-record"><\/span>Hence <br><span class="tag-sub">/);
  assert.doesNotMatch(fuckingHtml, /id="rec-f19a9d"/);
  assert.match(fuckingHtml, /<span class="sense-number">1\.<\/span> <span class="tag-gr">[\s\S]*?intr\.<\/span>/);
  assert.match(fuckingText, /a1503/);
  assert.match(fuckingHtml, /<span class="tag-a">[\s\S]*?Dunbar<\/span>/);
  assert.doesNotMatch(fuckingText, /&a\.1503/);

  const screwArticle = await reader.decodeArticleAtOrdinal(349080);
  const screwHtml = renderArticleRecordsHtml(screwArticle.records, screwArticle.targetLogical);
  const screwText = screwHtml.replace(/<[^>]+>/g, "");
  assert.match(screwHtml, /<a class="tag-x ref-link" href="#">[\s\S]*?Archimedean<\/a>/);
  assert.match(screwHtml, /<a class="tag-x ref-link" href="#">[\s\S]*?cochlea<\/a>/);
  assert.doesNotMatch(screwHtml, /record-anchor(?! target-record)/);
  assert.doesNotMatch(screwHtml, /difficulties\.<br>\u2060?\]/);
  assert.doesNotMatch(screwHtml, /difficulties\.\u2060?<br><span id="rec-28dc4f0"/);
  assert.match(screwHtml, /difficulties\.\u2060\]<br><span class="sense-number">I\.<\/span>/);
  assert.match(screwText, /\(\u2060mod\.F\./);
  assert.match(screwText, /difficulties\.\u2060\]/);

  const pulley = await reader.lookup("pulley", 4);
  assert.equal(resultText(pulley[0]), "310376:pulley n. 1");
  const pulleyArticle = await reader.decodeArticleAtOrdinal(310376);
  const pulleyHtml = renderArticleRecordsHtml(pulleyArticle.records, pulleyArticle.targetLogical);
  assert.doesNotMatch(pulleyHtml, /<br>\u00a0\[/);
  assert.match(pulleyHtml, /Forms: see below\.<\/span><br>\[/);
  assert.match(pulleyHtml, /<span class="tag-gk">πολίδιον<\/span>/);
  assert.match(pulleyHtml, /<span class="tag-gk">πόλος<\/span>/);

  const screen = await reader.lookup("screen", 4);
  assert.equal(resultText(screen[0]), "349011:screen n. 1");
  const screenArticle = await reader.decodeArticleAtOrdinal(349011);
  const screenHtml = renderArticleRecordsHtml(screenArticle.records, screenArticle.targetLogical);
  const screenText = screenHtml.replace(/<[^>]+>/g, "");
  assert.match(screenText, /1712 Steele Spectator No\. 336 \u204b2 They plague/);
  assert.match(screenText, /There was a draught~screen just at the door/);
  assert.doesNotMatch(screenText, /&(?:amp;)?(?:page|dubh)\./);

  const highlighted = renderArticleRecordsHtml(article.records, article.targetLogical, {
    highlightText: "s",
  });
  assert.match(highlighted, /<span class="tag-hw">[\s\S]*?<mark class="query-hit">/);
  assert.doesNotMatch(highlighted, /The <mark class="query-hit">s<\/mark>ense/);
} finally {
  await handle.close();
}
