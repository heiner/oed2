import { open, mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { OED2Reader, normalizeSearch } from "./src/oed2.js";

const datPath = process.argv[2] ?? "/Volumes/OED2/OED2.DAT";
const outPath = process.argv[3] ?? "web/prefix-completions.json";
const ENTRIES_PER_PREFIX = parseInt(process.env.LIMIT ?? "100", 10);
const ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";

class NodeFileSource {
  constructor(handle) {
    this.handle = handle;
  }
  async read(offset, length) {
    const buffer = Buffer.alloc(length);
    const { bytesRead } = await this.handle.read(buffer, 0, length, offset);
    if (bytesRead !== length) throw new Error(`Short read at 0x${offset.toString(16)}`);
    return new Uint8Array(buffer.buffer, buffer.byteOffset, bytesRead);
  }
}

const handle = await open(datPath, "r");
try {
  const reader = new OED2Reader(new NodeFileSource(handle));
  await reader.readBodyControl();
  await reader.readOedList("word");

  const out = {};
  let totalEntries = 0;

  const prefixes = [];
  for (const a of ALPHABET) prefixes.push(a);
  for (const a of ALPHABET) for (const b of ALPHABET) prefixes.push(a + b);

  for (const prefix of prefixes) {
    if (normalizeSearch(prefix) !== prefix) continue;
    const drafts = await reader.lookupDrafts(prefix, ENTRIES_PER_PREFIX);
    if (drafts.length === 0) continue;
    out[prefix] = drafts.map((d) =>
      d.annotation ? [d.index, d.listLabel, d.annotation] : [d.index, d.listLabel],
    );
    totalEntries += drafts.length;
  }

  await mkdir(dirname(outPath), { recursive: true });
  const json = JSON.stringify(out);
  await writeFile(outPath, json);
  console.log(`wrote ${outPath}: ${json.length.toLocaleString()} bytes, ${Object.keys(out).length} prefixes, ${totalEntries.toLocaleString()} entries`);
} finally {
  await handle.close();
}
