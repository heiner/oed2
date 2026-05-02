import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { homedir } from "node:os";
import { extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const root = resolve(here);
const repo = resolve(root, "..");
const port = Number(process.env.PORT ?? 8765);
const host = process.env.HOST ?? "127.0.0.1";

const isoCandidates = [
  process.env.OED2_ISO,
  resolve(homedir(), "Downloads", "Oxford English Dictionary (Second Edition).iso"),
  resolve(repo, "Oxford English Dictionary (Second Edition).iso"),
].filter(Boolean);

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".iso": "application/octet-stream",
  ".png": "image/png",
};

function safePath(urlPath) {
  let pathname = decodeURIComponent(urlPath);
  if (pathname === "/") pathname = "/index.html";
  if (pathname === "/OED2.iso") {
    const iso = isoCandidates.find((candidate) => existsSync(candidate));
    return iso ? resolve(iso) : null;
  }
  const resolved = resolve(join(root, pathname));
  if (resolved !== root && !resolved.startsWith(root + sep)) return null;
  return resolved;
}

function sendRange(req, res, file, stat) {
  const total = stat.size;
  const range = req.headers.range;
  const type = mimeTypes[extname(file)] ?? "application/octet-stream";
  res.setHeader("Accept-Ranges", "bytes");
  res.setHeader("Content-Type", type);

  if (!range) {
    res.writeHead(200, { "Content-Length": total });
    if (req.method === "HEAD") return res.end();
    createReadStream(file).pipe(res);
    return;
  }

  const match = range.match(/^bytes=(\d+)-(\d*)$/);
  if (!match) {
    res.writeHead(416, { "Content-Range": `bytes */${total}` });
    res.end();
    return;
  }
  const start = Number(match[1]);
  const end = match[2] ? Number(match[2]) : total - 1;
  if (start >= total || end < start) {
    res.writeHead(416, { "Content-Range": `bytes */${total}` });
    res.end();
    return;
  }
  const last = Math.min(end, total - 1);
  res.writeHead(206, {
    "Content-Length": last - start + 1,
    "Content-Range": `bytes ${start}-${last}/${total}`,
  });
  if (req.method === "HEAD") return res.end();
  createReadStream(file, { start, end: last }).pipe(res);
}

const server = createServer((req, res) => {
  try {
    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
    const file = safePath(url.pathname);
    if (!file || !existsSync(file)) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found\n");
      return;
    }
    const stat = statSync(file);
    if (!stat.isFile()) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Not found\n");
      return;
    }
    sendRange(req, res, file, stat);
  } catch (error) {
    res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`${error.message}\n`);
  }
});

server.listen(port, host, () => {
  console.log(`OED2 static server on http://${host}:${port}/`);
  console.log("Range requests enabled; OED decoding still happens in the browser.");
});
