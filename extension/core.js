/* Verified Asset — pure helpers shared by the content script, options page, and service worker.
   No DOM access. Listing text never leaves this file; callers decide what to do with it. */
(function (root) {
  "use strict";

  var DEFAULT_BASE = "https://verified.ciberpty.com";
  var TOKEN = "[A-Za-z0-9_-]{16,64}";
  var STATES = { active: 1, invalidated: 1, revoked: 1, expired: 1 };

  function escapeRegex(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function normalizeBase(input) {
    var raw = String(input == null ? "" : input).trim();
    var url;
    try {
      url = new URL(raw);
    } catch (err) {
      throw new Error("Enter a full URL, including http:// or https://.");
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      throw new Error("Use an http or https URL.");
    }
    if (url.username || url.password) {
      throw new Error("Remove the username and password from the URL.");
    }
    if (url.search || url.hash) {
      throw new Error("Remove the query and hash from the base URL.");
    }
    var path = url.pathname.replace(/\/+$/, "");
    if (path === "/") path = "";
    return url.origin + path;
  }

  /* Host permission pattern. Port is omitted so one grant covers :8000 and friends. */
  function permissionPattern(base) {
    var url = new URL(normalizeBase(base));
    var host = url.hostname;
    if (host.indexOf(":") !== -1) host = "[" + host + "]";
    return url.protocol + "//" + host + "/*";
  }

  function truncate(value, max) {
    var chars = Array.from(String(value || ""));
    if (chars.length <= max) return chars.join("");
    return chars.slice(0, max).join("");
  }

  function encodeQuery(pairs) {
    return pairs
      .map(function (pair) {
        return encodeURIComponent(pair[0]) + "=" + encodeURIComponent(pair[1]);
      })
      .join("&");
  }

  function newReportUrl(base, fields) {
    var title = truncate(fields && fields.title, 300);
    var description = truncate(fields && fields.description, 2000);
    var source = fields && fields.source ? String(fields.source) : "";
    var pairs = [];
    if (title) pairs.push(["title", title]);
    if (description) pairs.push(["description", description]);
    pairs.push(["source", source]);
    return normalizeBase(base) + "/new?" + encodeQuery(pairs);
  }

  function sellerMessage(base, itemUrl) {
    var link = normalizeBase(base) + "/new?source=" + encodeURIComponent(itemUrl || "");
    return "Hi! Before I come to see it, could you create a free evidence report for this item? " + link;
  }

  function reportApiUrl(base, token) {
    if (!new RegExp("^" + TOKEN + "$").test(token || "")) {
      throw new Error("That report token is not valid.");
    }
    return normalizeBase(base) + "/api/r/" + token;
  }

  function findToken(base, blobs) {
    var canonical;
    try {
      canonical = normalizeBase(base);
    } catch (err) {
      return null;
    }
    var finder = new RegExp(escapeRegex(canonical) + "/r/(" + TOKEN + ")(?![A-Za-z0-9_-])");
    var hostSwap = new RegExp(escapeRegex(canonical), "ig");
    for (var i = 0; i < (blobs || []).length; i += 1) {
      if (!blobs[i]) continue;
      var text = String(blobs[i]);
      var normalized = text.replace(hostSwap, canonical);
      var match = normalized.match(finder);
      if (match) return match[1];
    }
    return null;
  }

  /* Facebook often wraps outbound hrefs as l.facebook.com/l.php?u=<encoded>. */
  function blobsFromLink(href, text, baseHref) {
    var blobs = [];
    if (text) blobs.push(text);
    if (!href) return blobs;
    blobs.push(href);
    try {
      var url = new URL(href, baseHref || "https://www.facebook.com/");
      blobs.push(url.href);
      var wrapped = url.searchParams.get("u");
      if (wrapped) blobs.push(wrapped);
    } catch (err) {
      /* Ignore unparseable hrefs; the raw string was already included. */
    }
    return blobs;
  }

  function facebookItemKey(href) {
    var url;
    try {
      url = new URL(href);
    } catch (err) {
      return null;
    }
    if (url.hostname !== "www.facebook.com") return null;
    var match = url.pathname.match(/^\/marketplace\/item\/([^/]+)/);
    if (!match || !match[1]) return null;
    return match[1];
  }

  function countLine(verdicts) {
    var counts = { supported: 0, contradicted: 0, inconclusive: 0 };
    var list = verdicts || [];
    for (var i = 0; i < list.length; i += 1) {
      var status = list[i] && list[i].status;
      if (Object.prototype.hasOwnProperty.call(counts, status)) counts[status] += 1;
    }
    return {
      counts: counts,
      line:
        counts.supported +
        " supported · " +
        counts.contradicted +
        " contradicted · " +
        counts.inconclusive +
        " inconclusive",
    };
  }

  function parseReport(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error("Unexpected report response.");
    }
    if (!STATES[data.state]) throw new Error("Unexpected report state.");
    if (data.state === "active" && !Array.isArray(data.verdicts)) {
      throw new Error("Unexpected report response.");
    }
    return data;
  }

  function assertReportApiUrl(input) {
    var url = new URL(input);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      throw new Error("Unexpected report URL.");
    }
    if (url.username || url.password || url.search || url.hash) {
      throw new Error("Unexpected report URL.");
    }
    if (!new RegExp("/api/r/" + TOKEN + "$").test(url.pathname)) {
      throw new Error("Unexpected report URL.");
    }
    return url.origin + url.pathname;
  }

  function isReportPageUrl(base, url, token) {
    return findToken(base, [url]) === token;
  }

  root.VACore = {
    DEFAULT_BASE: DEFAULT_BASE,
    normalizeBase: normalizeBase,
    permissionPattern: permissionPattern,
    truncate: truncate,
    newReportUrl: newReportUrl,
    sellerMessage: sellerMessage,
    reportApiUrl: reportApiUrl,
    findToken: findToken,
    blobsFromLink: blobsFromLink,
    facebookItemKey: facebookItemKey,
    countLine: countLine,
    parseReport: parseReport,
    assertReportApiUrl: assertReportApiUrl,
    isReportPageUrl: isReportPageUrl,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
