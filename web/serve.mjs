import { Readable } from "node:stream";
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

const ARCHIVE_ISO_URL =
  process.env.OED2_ISO_URL ??
  "https://archive.org/download/oxford-english-dictionary-second-edition/Oxford%20English%20Dictionary%20%28Second%20Edition%29.iso";

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".iso": "application/octet-stream",
  ".png": "image/png",
};

function localIsoPath() {
  return isoCandidates.find((candidate) => existsSync(candidate)) ?? null;
}

function safePath(urlPath) {
  let pathname = decodeURIComponent(urlPath);
  if (pathname === "/") pathname = "/index.html";
  if (pathname === "/OED2.iso") return null;
  const resolved = resolve(join(root, pathname));
  if (resolved !== root && !resolved.startsWith(root + sep)) return null;
  return resolved;
}

async function proxyArchiveIso(req, res) {
  const headers = {};
  if (req.headers.range) headers.Range = req.headers.range;
  let upstream;
  try {
    upstream = await fetch(ARCHIVE_ISO_URL, { headers, redirect: "follow" });
  } catch (error) {
    res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`upstream error: ${error.message}\n`);
    return;
  }
  const passHeaders = ["content-length", "content-range", "last-modified", "etag"];
  const responseHeaders = {
    "Accept-Ranges": "bytes",
    "Content-Type": "application/octet-stream",
  };
  for (const name of passHeaders) {
    const value = upstream.headers.get(name);
    if (value !== null) responseHeaders[name.replace(/(^|-)([a-z])/g, (_, p, c) => p + c.toUpperCase())] = value;
  }
  res.writeHead(upstream.status, responseHeaders);
  if (req.method === "HEAD" || !upstream.body) {
    res.end();
    return;
  }
  Readable.fromWeb(upstream.body).pipe(res);
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

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
    if (url.pathname === "/OED2.iso") {
      const local = localIsoPath();
      if (local) {
        sendRange(req, res, local, statSync(local));
      } else {
        await proxyArchiveIso(req, res);
      }
      return;
    }
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
  const local = localIsoPath();
  console.log(`OED2 static server on http://${host}:${port}/`);
  console.log(local
    ? `Serving /OED2.iso from ${local}`
    : `No local ISO; proxying /OED2.iso from ${ARCHIVE_ISO_URL}`);
});
