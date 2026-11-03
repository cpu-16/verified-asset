import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createContext, runInContext } from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const context = createContext({
  console,
  URL,
  URLSearchParams,
  encodeURIComponent,
  decodeURIComponent,
});
runInContext(readFileSync(resolve(root, "core.js"), "utf8"), context, { filename: "core.js" });
const VA = context.VACore;
const BASE = "https://verified.adwentech.com";
const TOKEN = "dGVzdC1yZXBvcnQtaWQx";
const ITEM = "https://www.facebook.com/marketplace/item/123456789/";

test("normalizes the base URL and rejects unsafe forms", () => {
  assert.equal(VA.normalizeBase("https://verified.adwentech.com/"), BASE);
  assert.equal(VA.normalizeBase("http://localhost:8000"), "http://localhost:8000");
  assert.equal(VA.normalizeBase("https://example.com/demo/"), "https://example.com/demo");
  assert.throws(() => VA.normalizeBase("javascript:alert(1)"));
  assert.throws(() => VA.normalizeBase("https://user:pass@verified.adwentech.com"));
  assert.throws(() => VA.normalizeBase("https://verified.adwentech.com/?q=1"));
});

test("permission patterns omit the port", () => {
  assert.equal(VA.permissionPattern("http://localhost:8000"), "http://localhost/*");
  assert.equal(VA.permissionPattern("http://127.0.0.1:8000/app"), "http://127.0.0.1/*");
  assert.equal(VA.permissionPattern(BASE), "https://verified.adwentech.com/*");
});

test("finds a urlsafe report token and ignores lookalikes", () => {
  const url = BASE + "/r/" + TOKEN;
  assert.equal(VA.findToken(BASE, ["see " + url + "."]), TOKEN);
  assert.equal(VA.findToken(BASE.toUpperCase(), [url]), TOKEN);
  assert.equal(VA.findToken(BASE, [BASE + "/r/" + "a".repeat(15)]), null);
  assert.equal(VA.findToken(BASE, [BASE + "/r/" + "a".repeat(16)]), "a".repeat(16));
  assert.equal(VA.findToken(BASE, [BASE + "/r/" + "a".repeat(64)]), "a".repeat(64));
  assert.equal(VA.findToken(BASE, [BASE + "/r/" + "a".repeat(65)]), null);
  assert.equal(VA.findToken(BASE, ["https://example.com/r/" + TOKEN]), null);
  assert.equal(VA.findToken(BASE, [BASE + "/r/not+url+safe+token"]), null);
});

test("unwraps a Facebook redirect link", () => {
  const url = BASE + "/r/" + TOKEN;
  const href = "https://l.facebook.com/l.php?u=" + encodeURIComponent(url) + "&h=abc";
  assert.equal(VA.findToken(BASE, VA.blobsFromLink(href, "Seller link", ITEM)), TOKEN);
});

test("builds the seller message and the create-report URL", () => {
  assert.equal(
    VA.sellerMessage(BASE + "/", ITEM),
    "Hi! Before I come to see it, could you create a free evidence report for this item? " +
      BASE +
      "/new?source=" +
      encodeURIComponent(ITEM)
  );
  const created = new URL(
    VA.newReportUrl(BASE, {
      title: "Oak writing desk",
      description: "á".repeat(2001),
      source: ITEM,
    })
  );
  assert.equal(created.origin + created.pathname, BASE + "/new");
  assert.equal(created.searchParams.get("title"), "Oak writing desk");
  assert.equal(Array.from(created.searchParams.get("description")).length, 2000);
  assert.equal(created.searchParams.get("source"), ITEM);
});

test("recognizes Marketplace item ids and report payloads", () => {
  assert.equal(VA.facebookItemKey(ITEM + "?ref=search"), "123456789");
  assert.equal(VA.facebookItemKey("https://www.facebook.com/marketplace/"), null);
  assert.equal(VA.facebookItemKey("https://m.facebook.com/marketplace/item/123456789/"), null);
  const line = VA.countLine([
    { status: "supported" },
    { status: "supported" },
    { status: "contradicted" },
    { status: "inconclusive" },
    { status: "other" },
  ]);
  assert.equal(line.line, "2 supported · 1 contradicted · 1 inconclusive");
  const active = VA.parseReport({ state: "active", verdicts: [], title: "Desk" });
  assert.equal(active.state, "active");
  assert.equal(VA.parseReport({ state: "revoked", url: "https://x", title: "Desk" }).state, "revoked");
  assert.throws(() => VA.parseReport({ state: "deleted" }));
  assert.throws(() => VA.parseReport({ state: "active" }));
  const api = VA.reportApiUrl(BASE, TOKEN);
  assert.equal(api, BASE + "/api/r/" + TOKEN);
  assert.equal(VA.assertReportApiUrl(api), api);
  assert.throws(() => VA.assertReportApiUrl(BASE + "/new"));
  assert.equal(VA.isReportPageUrl(BASE, BASE + "/r/" + TOKEN, TOKEN), true);
  assert.equal(VA.isReportPageUrl(BASE, "https://evil.example/r/" + TOKEN, TOKEN), false);
});

test("demo mock page is labelled, unindexed, and uses the fixture report schema", () => {
  const html = readFileSync(resolve(root, "test/demo-mock.html"), "utf8");
  assert.ok(html.includes(
    "MOCK PAGE for the Meta Global AI Developer Hackathon demo. Not Facebook or Marketplace. " +
    "Not affiliated with or endorsed by Meta. No real listing, seller or person is shown."
  ));
  assert.match(html, /<title>MOCK - Verified Asset demo page<\/title>/);
  assert.match(html, /<meta\s+name="robots"\s+content="noindex"\s*\/?\s*>/i);
  assert.doesNotMatch(html, /<meta\b[^>]*\bog:/i);
  assert.doesNotMatch(html, /facebook\.com/i);
  assert.ok(html.includes("Mock page for demonstration. No real listing, seller or person."));
  const fixture = JSON.parse(readFileSync(resolve(root, "test/mock-report.json"), "utf8"));
  const demo = JSON.parse(readFileSync(resolve(root, "test/demo-mock-report.json"), "utf8"));
  assert.deepEqual(Object.keys(demo).sort(), Object.keys(fixture).sort());
  for (const key of Object.keys(fixture)) {
    assert.equal(typeof demo[key], typeof fixture[key], key);
  }
  assert.equal(VA.parseReport(demo).state, "active");
  assert.equal(demo.title, "Dining set");
  assert.equal(demo.observer, fixture.observer);
  assert.match(demo.digest, /^[a-f0-9]{64}$/);
  assert.equal(demo.url, BASE + "/r/MOCK-DEMO-NOT-A-REAL-REPORT");
  assert.equal(VA.findToken(BASE, [demo.url]), "MOCK-DEMO-NOT-A-REAL-REPORT");
  assert.deepEqual(demo.verdicts.map((row) => [row.claim, row.status]), [
    ["4 chairs", "supported"],
    ["White", "supported"],
    ["No visible damage", "contradicted"],
    ["Very strong wood", "inconclusive"],
  ]);
  for (const row of demo.verdicts) {
    assert.deepEqual(Object.keys(row).sort(), Object.keys(fixture.verdicts[0]).sort());
    for (const key of Object.keys(row)) assert.equal(typeof row[key], "string", key);
  }
  assert.match(demo.verdicts[2].detail, /close-up shows a pale scratch near the edge/);
  assert.match(demo.verdicts[3].detail, /Photos cannot show this/);
});

function decodePre(html) {
  const match = html.match(/<pre id="va-debug">([\s\S]*?)<\/pre>/);
  assert.ok(match, "debug output missing from the fixture page");
  const text = match[1]
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"');
  return JSON.parse(text);
}

function serve(dir) {
  return new Promise((resolveServer) => {
    const server = createServer((req, res) => {
      const url = new URL(req.url, "http://127.0.0.1");
      const path = resolve(dir, "." + decodeURIComponent(url.pathname));
      if (!path.startsWith(dir)) {
        res.writeHead(403);
        res.end();
        return;
      }
      try {
        const body = readFileSync(path);
        res.writeHead(200);
        res.end(body);
      } catch {
        res.writeHead(404);
        res.end();
      }
    });
    server.listen(0, "127.0.0.1", () => resolveServer(server));
  });
}

function dumpDom(url) {
  const chromium = process.env.CHROMIUM || "chromium";
  return new Promise((resolveDump, reject) => {
    const child = spawn(
      chromium,
      [
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--virtual-time-budget=8000",
        "--dump-dom",
        url,
      ],
      { stdio: ["ignore", "pipe", "pipe"] }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => {
      out += chunk;
    });
    child.stderr.on("data", (chunk) => {
      err += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) reject(new Error(err || "chromium exited " + code));
      else resolveDump(out);
    });
  });
}

test("demo mock page renders the Dining set report through the content script", async () => {
  const server = await serve(root);
  const { port } = server.address();
  try {
    const html = await dumpDom("http://127.0.0.1:" + port + "/test/demo-mock.html?mock=1");
    const active = decodePre(html);
    assert.equal(active.title, "Dining set");
    assert.equal(active.price, "$120");
    assert.match(active.description, /sample evidence report/);
    assert.equal(active.token, "MOCK-DEMO-NOT-A-REAL-REPORT");
    assert.equal(active.headline, "2 supported · 1 contradicted · 1 inconclusive");
    assert.deepEqual(active.chips, ["Supported", "Supported", "Contradicted", "Inconclusive"]);
    assert.match(active.details[2], /close-up shows a pale scratch near the edge/);
    assert.equal(active.details[3], "Photos cannot show this.");
    assert.equal(active.openHref, BASE + "/r/MOCK-DEMO-NOT-A-REAL-REPORT");
    assert.equal(active.status, "");
  } finally {
    await new Promise((done) => server.close(done));
  }
});

test("fixture page renders the report, the empty state, and the fallbacks", async () => {
  const server = await serve(root);
  const { port } = server.address();
  const open = (query) => dumpDom("http://127.0.0.1:" + port + "/test/item.html" + query);
  try {
    const active = decodePre(await open("?mock=1"));
    assert.equal(active.title, "Oak writing desk");
    assert.equal(active.price, "$180");
    assert.match(active.description, /Solid oak writing desk/);
    assert.equal(active.description.includes("Great seller"), false);
    assert.equal(active.meta, "Issued Oct 27, 2026, until Nov 26, 2026.");
    assert.equal(active.token, TOKEN);
    assert.equal(active.disclaimer, "Independent demo · not affiliated with Meta");
    assert.equal(active.headline, "1 supported · 1 contradicted · 2 inconclusive");
    assert.equal(active.banner, "");
    assert.deepEqual(active.chips, ["Inconclusive", "Supported", "Contradicted", "Inconclusive"]);
    assert.deepEqual(active.asks, ["Ask the seller for: a photo of the chair next to the desk"]);
    assert.match(active.details[2], /pale scratch/);
    assert.equal(active.actions.includes("Copy message for the seller"), false);
    assert.equal(active.actions.includes("Create evidence report"), true);
    assert.equal(active.actions.includes("Open full report"), true);
    assert.equal(active.openHref, BASE + "/r/" + TOKEN);
    const created = new URL(active.createHref);
    assert.equal(created.searchParams.get("title"), "Oak writing desk");
    assert.match(created.searchParams.get("description"), /Solid oak writing desk/);
    assert.match(created.searchParams.get("source"), /\/test\/item\.html/);

    const empty = decodePre(await open("?mock=1&noreport=1"));
    assert.equal(empty.token, null);
    assert.equal(empty.headline, "No evidence report for this listing");
    assert.equal(empty.actions.includes("Copy message for the seller"), true);
    assert.equal(empty.chips.length, 0);

    const expired = decodePre(await open("?mock=1&state=expired"));
    assert.equal(expired.banner, "This report no longer matches the listing");
    assert.equal(expired.headline, "Oak writing desk");
    assert.equal(expired.chips.length, 0);
    assert.equal(expired.actions.includes("Open full report"), true);

    const revoked = decodePre(await open("?mock=1&state=revoked"));
    assert.equal(revoked.banner, "This report no longer matches the listing");

    const heading = decodePre(await open("?mock=1&notitlemeta=1"));
    assert.equal(heading.title, "Desk heading in the page");

    const hidden = decodePre(await open("?mock=1&click=hide"));
    assert.equal(hidden.expanded, "false");
    assert.equal(hidden.disclaimer, "Independent demo · not affiliated with Meta");
    assert.equal(hidden.headline, "1 supported · 1 contradicted · 2 inconclusive");
    assert.equal(hidden.actions.includes("Show"), true);

    const copied = decodePre(await open("?mock=1&noreport=1&click=copy"));
    assert.equal(
      copied.note === "Copied." || copied.note.startsWith("Could not copy."),
      true
    );

    const failed = decodePre(await open("?mock=1&fail=1"));
    assert.equal(failed.status, "The report link was found, but it could not be loaded.");
    assert.equal(failed.actions.includes("Try again"), true);
    assert.equal(failed.token, TOKEN);
  } finally {
    await new Promise((done) => server.close(done));
  }
});
