/* Verified Asset content script.
   Runs on www.facebook.com so Marketplace's client-side navigations still reach an item page.
   The panel is created only on /marketplace/item/<id>, and removed when that page is left.
   Nothing is uploaded here. A published report token is fetched; title and description are
   placed in a new-tab URL only after the user clicks "Create evidence report". */
(function () {
  "use strict";

  if (!globalThis.VACore) return;
  if (globalThis.__VA_CONTENT_STARTED) return;
  globalThis.__VA_CONTENT_STARTED = true;

  var SCRIPT_SRC = document.currentScript ? document.currentScript.src : "";
  var DISCLAIMER = "Independent demo · not affiliated with Meta";
  var EMPTY = "No evidence report for this listing";
  var STALE = "This report no longer matches the listing";
  var LABELS = {
    supported: "Supported",
    contradicted: "Contradicted",
    inconclusive: "Inconclusive",
  };
  var DESCRIPTION_LABELS = {
    description: 1,
    "descripción": 1,
    "descrição": 1,
    descricao: 1,
    beschreibung: 1,
    descrizione: 1,
    omschrijving: 1,
    beskrivelse: 1,
    opis: 1,
  };
  var PRICE =
    /(?:US\$|CA\$|A\$|\$|€|£)\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\s?(?:USD|EUR|GBP)\b/;

  var generation = 0;
  var current = null;
  var cssCache = "";
  var stopObserve = function () {};

  function isTestPage() {
    if (location.hostname === "www.facebook.com") return false;
    return document.documentElement.dataset.vaTest === "1";
  }

  function testQuery() {
    return new URLSearchParams(location.search);
  }

  function pageKey() {
    if (isTestPage()) return "test:" + location.pathname + location.search;
    return VACore.facebookItemKey(location.href);
  }

  function sourceUrl() {
    return location.origin + location.pathname + location.search;
  }

  function getBase() {
    if (isTestPage()) {
      var fromQuery = testQuery().get("base");
      var fromDom = fromQuery || document.documentElement.dataset.vaBase;
      if (fromDom) return VACore.normalizeBase(fromDom);
    }
    return new Promise(function (resolve) {
      try {
        if (globalThis.chrome && chrome.storage && chrome.storage.sync) {
          chrome.storage.sync.get({ baseUrl: VACore.DEFAULT_BASE }, function (stored) {
            try {
              resolve(VACore.normalizeBase((stored && stored.baseUrl) || VACore.DEFAULT_BASE));
            } catch (err) {
              resolve(VACore.DEFAULT_BASE);
            }
          });
          return;
        }
      } catch (err) {
        /* Fall through to the default when storage is unavailable (local fixture). */
      }
      resolve(VACore.DEFAULT_BASE);
    });
  }

  function skipNode(node) {
    var el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el || !el.closest) return false;
    return !!el.closest("#verified-asset-root, #va-debug, #how");
  }

  function cleanDescription(text) {
    return String(text || "")
      .replace(/\s+/g, " ")
      .replace(/\b(see more|see less|ver más|ver menos|mostrar más|show more|show less)\s*$/i, "")
      .trim();
  }

  function nextText(el) {
    var sibling = el.nextElementSibling;
    if (sibling && !skipNode(sibling) && (sibling.innerText || "").trim().length >= 20) {
      return sibling.innerText;
    }
    var parentNext = el.parentElement && el.parentElement.nextElementSibling;
    if (parentNext && !skipNode(parentNext) && (parentNext.innerText || "").trim().length >= 20) {
      return parentNext.innerText;
    }
    return "";
  }

  /* Facebook's class names change. Prefer stable hooks, then visible text. */
  function findTitle(doc) {
    var og = doc.querySelector('meta[property="og:title"]');
    var fromMeta = og ? (og.getAttribute("content") || "").trim() : "";
    var cleaned = fromMeta.replace(/\s*\|\s*Facebook(?:\s+Marketplace)?\s*$/i, "").trim();
    if (cleaned && !/^facebook$/i.test(cleaned)) return cleaned;
    var heading = doc.querySelector("h1, [role='heading'][aria-level='1']");
    if (heading && !skipNode(heading) && heading.innerText) return heading.innerText.trim();
    return "";
  }

  function findPrice(doc) {
    var meta = doc.querySelector(
      'meta[property="product:price:amount"], meta[property="og:price:amount"]'
    );
    if (meta && meta.content) return meta.content.trim();
    var heading = doc.querySelector("h1");
    var scope = heading && heading.parentElement;
    for (var depth = 0; scope && depth < 3; depth += 1) {
      if (scope === doc.body) break;
      var match = (scope.innerText || "").match(PRICE);
      if (match) return match[0].trim();
      scope = scope.parentElement;
    }
    return "";
  }

  function findDescription(doc) {
    var nodes = doc.querySelectorAll("h2, h3, h4, span, div, strong, dt, p");
    for (var i = 0; i < nodes.length; i += 1) {
      var el = nodes[i];
      if (skipNode(el)) continue;
      var label = (el.textContent || "").trim().toLowerCase().replace(/:$/, "");
      if (!DESCRIPTION_LABELS[label]) continue;
      if ((el.textContent || "").trim().length > label.length + 2) continue;
      var block = nextText(el);
      if (block) return cleanDescription(block);
    }
    var best = "";
    var autos = doc.querySelectorAll('[dir="auto"]');
    for (var j = 0; j < autos.length; j += 1) {
      var auto = autos[j];
      if (skipNode(auto) || auto.querySelector("[dir='auto']")) continue;
      var text = cleanDescription(auto.innerText || "");
      if (text.length > best.length && text.length <= 8000) best = text;
    }
    if (best.length >= 40) return best;
    var ogd = doc.querySelector('meta[property="og:description"]');
    var ogText = ogd ? (ogd.getAttribute("content") || "").trim() : "";
    if (ogText && !/log in or sign up|facebook marketplace is a/i.test(ogText)) {
      return cleanDescription(ogText);
    }
    return "";
  }

  function extractListing(selection) {
    if (selection) {
      return {
        title: findTitle(document),
        description: cleanDescription(selection),
        price: findPrice(document),
      };
    }
    return {
      title: findTitle(document),
      description: findDescription(document),
      price: findPrice(document),
    };
  }

  function collectBlobs(description) {
    var blobs = [description];
    var ogd = document.querySelector('meta[property="og:description"]');
    if (ogd && ogd.getAttribute("content")) blobs.push(ogd.getAttribute("content"));
    var anchors = document.querySelectorAll("a[href]");
    for (var i = 0; i < anchors.length; i += 1) {
      if (skipNode(anchors[i])) continue;
      var parts = VACore.blobsFromLink(
        anchors[i].getAttribute("href"),
        anchors[i].textContent || "",
        location.href
      );
      blobs.push.apply(blobs, parts);
    }
    return blobs;
  }

  function canMessageExtension() {
    return !!(
      globalThis.chrome &&
      chrome.runtime &&
      chrome.runtime.id &&
      chrome.runtime.sendMessage
    );
  }

  function fetchReport(url) {
    if (isTestPage() && testQuery().has("mock")) {
      if (testQuery().has("fail")) return Promise.reject(new Error("mock failure"));
      var mockUrl = document.body.dataset.vaMock || "mock-report.json";
      return fetch(mockUrl, { cache: "no-store" }).then(function (res) {
        if (!res.ok) throw new Error("The mock report could not be loaded.");
        return res.json().then(function (data) {
          var state = testQuery().get("state");
          if (state && state !== "active") {
            data = { state: state, url: data.url, title: data.title };
          }
          return VACore.parseReport(data);
        });
      });
    }
    if (canMessageExtension()) {
      return chrome.runtime.sendMessage({ type: "va-fetch-report", url: url }).then(function (reply) {
        if (!reply || !reply.ok) {
          throw new Error((reply && reply.error) || "The report could not be loaded.");
        }
        return VACore.parseReport(JSON.parse(reply.body));
      });
    }
    return fetch(url, { credentials: "omit", cache: "no-store" }).then(function (res) {
      if (!res.ok) throw new Error("The report could not be loaded.");
      return res.json().then(VACore.parseReport);
    });
  }

  function cssHref() {
    if (globalThis.chrome && chrome.runtime && chrome.runtime.getURL) {
      return chrome.runtime.getURL("panel.css");
    }
    if (SCRIPT_SRC) return new URL("panel.css", SCRIPT_SRC).href;
    return "panel.css";
  }

  function loadPanelCss() {
    if (cssCache) return Promise.resolve(cssCache);
    return fetch(cssHref(), { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) throw new Error("css");
        return res.text();
      })
      .then(function (text) {
        cssCache = text;
        return text;
      })
      .catch(function () {
        cssCache =
          ".va-panel{display:block;background:#fff;color:#142018;font:13px/1.4 sans-serif;padding:12px}" +
          ".va-disclaimer{font-size:12px}";
        return cssCache;
      });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function pinHost(host) {
    var styles = {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      width: "min(320px, calc(100vw - 24px))",
      "z-index": "2147483647",
      margin: "0",
      padding: "0",
      border: "0",
      background: "transparent",
      display: "block",
      "pointer-events": "auto",
    };
    Object.keys(styles).forEach(function (key) {
      host.style.setProperty(key, styles[key], "important");
    });
  }

  function readSelection(host) {
    var sel = window.getSelection && window.getSelection();
    if (!sel || sel.isCollapsed) return "";
    var node = sel.anchorNode;
    var root = node && node.getRootNode && node.getRootNode();
    if (root instanceof ShadowRoot && root.host === host) return "";
    if (node && host.contains(node)) return "";
    return String(sel).replace(/\s+/g, " ").trim().slice(0, 8000);
  }

  function formatDate(iso) {
    var date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(date);
  }

  function issuedLine(report) {
    var issued = formatDate(report.issued_at);
    var until = formatDate(report.expires_at);
    if (issued && until) return "Issued " + issued + ", until " + until + ".";
    if (issued) return "Issued " + issued + ".";
    return "";
  }

  function openHref(session) {
    var token = session.token;
    var reported = session.report && session.report.url;
    if (reported && VACore.isReportPageUrl(session.base, reported, token)) return reported;
    if (!token) return "";
    return VACore.normalizeBase(session.base) + "/r/" + token;
  }

  function createHref(session) {
    return VACore.newReportUrl(session.base, {
      title: session.extracted.title,
      description: session.extracted.description,
      source: sourceUrl(),
    });
  }

  function stop(event) {
    event.stopPropagation();
  }

  function publishDebug(host) {
    if (!isTestPage() || !document.body) return;
    var pre = document.getElementById("va-debug");
    if (!pre) {
      pre = document.createElement("pre");
      pre.id = "va-debug";
      document.body.appendChild(pre);
    }
    var shadow = host.shadowRoot;
    var payload = {
      title: current && current.extracted.title,
      price: current && current.extracted.price,
      description: current && current.extracted.description,
      token: current && current.token,
      disclaimer: shadow.querySelector(".va-disclaimer")
        ? shadow.querySelector(".va-disclaimer").textContent
        : "",
      headline: shadow.querySelector(".va-headline, .va-empty")
        ? shadow.querySelector(".va-headline, .va-empty").textContent
        : "",
      banner: shadow.querySelector(".va-banner")
        ? shadow.querySelector(".va-banner").textContent
        : "",
      chips: Array.prototype.map.call(shadow.querySelectorAll(".va-chip"), function (node) {
        return node.textContent;
      }),
      asks: Array.prototype.map.call(shadow.querySelectorAll(".va-ask"), function (node) {
        return node.textContent;
      }),
      details: Array.prototype.map.call(shadow.querySelectorAll(".va-detail"), function (node) {
        return node.textContent;
      }),
      meta: shadow.querySelector(".va-meta") ? shadow.querySelector(".va-meta").textContent : "",
      status: shadow.querySelector(".va-status") ? shadow.querySelector(".va-status").textContent : "",
      note: shadow.querySelector(".va-note") ? shadow.querySelector(".va-note").textContent : "",
      expanded: shadow.querySelector(".va-hide")
        ? shadow.querySelector(".va-hide").getAttribute("aria-expanded")
        : "",
      actions: Array.prototype.map.call(shadow.querySelectorAll("a, button"), function (node) {
        return node.textContent.trim();
      }),
      createHref: shadow.querySelector("a.va-create") ? shadow.querySelector("a.va-create").href : "",
      openHref: shadow.querySelector("a.va-open") ? shadow.querySelector("a.va-open").href : "",
    };
    var serialized = JSON.stringify(payload);
    if (pre.textContent !== serialized) pre.textContent = serialized;
    globalThis.__VA_STATE = payload;
  }

  function addLink(parent, className, href, text) {
    var link = el("a", className, text);
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.referrerPolicy = "no-referrer";
    parent.appendChild(link);
    return link;
  }

  function addCreate(parent, session) {
    addLink(parent, "va-btn va-btn-secondary va-create", createHref(session), "Create evidence report");
  }

  function addCopy(parent, session) {
    var button = el("button", "va-btn va-copy", "Copy message for the seller");
    button.type = "button";
    button.addEventListener("click", function () {
      var message = VACore.sellerMessage(session.base, sourceUrl());
      var settled = false;
      var done = function (copied) {
        if (settled) return;
        settled = true;
        session.notice = copied
          ? "Copied."
          : "Could not copy. Select the message below and copy it yourself.";
        session.revealMessage = copied ? "" : message;
        render(session);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        setTimeout(function () {
          done(false); // a clipboard permission that never answers
        }, 1500);
        navigator.clipboard.writeText(message).then(
          function () {
            done(true);
          },
          function () {
            done(false);
          }
        );
      } else {
        done(false);
      }
    });
    parent.appendChild(button);
  }

  function addSelection(parent, session) {
    var button = el("button", "va-textbtn", "Use selected text as description");
    button.type = "button";
    button.addEventListener("click", function () {
      var text = readSelection(session.host);
      if (!text) {
        session.notice = "Highlight the description on the page, then use this button again.";
        render(session);
        return;
      }
      session.selection = text;
      session.notice = "Using the text you selected (" + Array.from(text).length + " characters).";
      session.fetchedFor = null;
      refresh(session, session.gen);
    });
    parent.appendChild(button);
  }

  function addNotice(parent, session) {
    if (session.notice) parent.appendChild(el("p", "va-note", session.notice));
    if (session.revealMessage) {
      var box = el("textarea", "va-message");
      box.readOnly = true;
      box.rows = 4;
      box.value = session.revealMessage;
      parent.appendChild(box);
    }
  }

  function render(session) {
    var host = session.host;
    var shadow = host.shadowRoot;
    shadow.textContent = "";
    var style = el("style");
    style.textContent = session.css;
    var panel = el("section", "va-panel");
    panel.lang = "en";
    panel.setAttribute("aria-label", "Verified Asset");
    var head = el("div", "va-head");
    var brand = el("div", "va-brand");
    brand.appendChild(el("p", "va-name", "Verified Asset"));
    brand.appendChild(el("p", "va-disclaimer", DISCLAIMER));
    var toggle = el("button", "va-hide", session.collapsed ? "Show" : "Hide");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", session.collapsed ? "false" : "true");
    toggle.addEventListener("click", function () {
      session.collapsed = !session.collapsed;
      render(session);
    });
    head.appendChild(brand);
    head.appendChild(toggle);
    panel.appendChild(head);

    var body = el("div", "va-body");
    if (session.collapsed) body.hidden = true;

    if (session.extracted.title || session.extracted.price) {
      var listing = el("p", "va-listing");
      if (session.extracted.title) {
        listing.appendChild(el("span", "va-listing-title", session.extracted.title));
      }
      if (session.extracted.price) listing.appendChild(el("span", "va-price", session.extracted.price));
      body.appendChild(listing);
    }

    if (session.loading) {
      body.appendChild(el("h2", "va-headline", "Looking for an evidence report…"));
    } else if (session.error) {
      body.appendChild(el("p", "va-status", session.error));
      var retry = el("button", "va-btn", "Try again");
      retry.type = "button";
      retry.addEventListener("click", function () {
        session.fetchedFor = null;
        session.error = "";
        refresh(session, session.gen);
      });
      var actions = el("div", "va-actions");
      actions.appendChild(retry);
      var href = openHref(session);
      if (href) addLink(actions, "va-link va-open", href, "Open full report");
      addCreate(actions, session);
      body.appendChild(actions);
    } else if (session.report && session.report.state !== "active") {
      body.appendChild(el("h2", "va-headline", session.report.title || "Evidence report"));
      body.appendChild(el("p", "va-banner", STALE));
      var inactiveActions = el("div", "va-actions");
      var inactiveHref = openHref(session);
      if (inactiveHref) addLink(inactiveActions, "va-link va-open", inactiveHref, "Open full report");
      addCopy(inactiveActions, session);
      addCreate(inactiveActions, session);
      addSelection(inactiveActions, session);
      addNotice(inactiveActions, session);
      body.appendChild(inactiveActions);
    } else if (session.report && session.report.state === "active") {
      var summary = VACore.countLine(session.report.verdicts);
      body.appendChild(el("h2", "va-headline", summary.line));
      var when = issuedLine(session.report);
      if (when) body.appendChild(el("p", "va-meta", when));
      session.report.verdicts.forEach(function (verdict) {
        if (!verdict || typeof verdict !== "object") return;
        var row = el("article", "va-row");
        var top = el("div", "va-rowtop");
        var claim = el("p", "va-claim", verdict.claim || "Untitled claim");
        claim.dir = "auto";
        var label = LABELS[verdict.status] || "Unknown";
        var chip = el(
          "span",
          "va-chip" + (LABELS[verdict.status] ? " va-chip-" + verdict.status : ""),
          label
        );
        top.appendChild(claim);
        top.appendChild(chip);
        row.appendChild(top);
        if (verdict.detail) {
          var detail = el("p", "va-detail", verdict.detail);
          detail.dir = "auto";
          row.appendChild(detail);
        }
        if (verdict.status === "inconclusive" && verdict.request) {
          var ask = el("p", "va-ask", "Ask the seller for: " + verdict.request);
          ask.dir = "auto";
          row.appendChild(ask);
        }
        body.appendChild(row);
      });
      var activeActions = el("div", "va-actions");
      var activeHref = openHref(session);
      if (activeHref) addLink(activeActions, "va-link va-open", activeHref, "Open full report");
      addCreate(activeActions, session);
      addSelection(activeActions, session);
      addNotice(activeActions, session);
      body.appendChild(activeActions);
    } else {
      body.appendChild(el("h2", "va-empty", EMPTY));
      if (!session.extracted.description) {
        body.appendChild(
          el(
            "p",
            "va-status",
            "No description was found. Highlight it on the page, then use the button below."
          )
        );
      }
      var emptyActions = el("div", "va-actions");
      addCopy(emptyActions, session);
      addCreate(emptyActions, session);
      addSelection(emptyActions, session);
      var again = el("button", "va-textbtn", "Check this page again");
      again.type = "button";
      again.addEventListener("click", function () {
        session.fetchedFor = null;
        refresh(session, session.gen);
      });
      emptyActions.appendChild(again);
      addNotice(emptyActions, session);
      body.appendChild(emptyActions);
    }

    panel.appendChild(body);
    shadow.appendChild(style);
    shadow.appendChild(panel);
    publishDebug(host);
  }

  function refresh(session, gen) {
    if (gen !== generation) return Promise.resolve();
    var extracted = extractListing(session.selection);
    session.extracted = extracted;
    var token = null;
    if (!(isTestPage() && testQuery().has("noreport"))) {
      token = VACore.findToken(session.base, collectBlobs(extracted.description));
    }
    session.token = token;
    if (!token) {
      session.loading = false;
      session.report = null;
      session.error = "";
      session.fetchedFor = null;
      render(session);
      return Promise.resolve();
    }
    if (session.fetchedFor === token && (session.report || session.error)) {
      render(session);
      return Promise.resolve();
    }
    session.loading = true;
    session.error = "";
    render(session);
    var apiUrl;
    try {
      apiUrl = VACore.reportApiUrl(session.base, token);
    } catch (err) {
      session.loading = false;
      session.error = "The report link was found, but it could not be loaded.";
      session.fetchedFor = token;
      render(session);
      return Promise.resolve();
    }
    return fetchReport(apiUrl).then(
      function (report) {
        if (gen !== generation) return;
        session.report = report;
        session.error = "";
        session.loading = false;
        session.fetchedFor = token;
        render(session);
      },
      function () {
        if (gen !== generation) return;
        session.report = null;
        session.loading = false;
        session.error = "The report link was found, but it could not be loaded.";
        session.fetchedFor = token;
        render(session);
      }
    );
  }

  function ourMutation(record) {
    var node = record.target;
    return skipNode(node);
  }

  function startObserver(session) {
    stopObserve();
    if (!document.body) return;
    var timer = 0;
    var gen = session.gen;
    var observer = new MutationObserver(function (records) {
      if (records.every(ourMutation)) return;
      clearTimeout(timer);
      timer = setTimeout(function () {
        if (gen !== generation || !current) return;
        refresh(current, gen);
      }, 300);
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
    var kill = setTimeout(function () {
      observer.disconnect();
    }, 45000);
    stopObserve = function () {
      clearTimeout(timer);
      clearTimeout(kill);
      observer.disconnect();
      stopObserve = function () {};
    };
  }

  function removePanel() {
    generation += 1;
    stopObserve();
    var existing = document.getElementById("verified-asset-root");
    if (existing) existing.remove();
    current = null;
  }

  function mount(key) {
    var gen = generation;
    var pending;
    try {
      pending = Promise.resolve(getBase());
    } catch (err) {
      pending = Promise.resolve(VACore.DEFAULT_BASE);
    }
    pending.then(function (base) {
      if (gen !== generation) return;
      return loadPanelCss().then(function (css) {
        if (gen !== generation) return;
        var host = document.createElement("div");
        host.id = "verified-asset-root";
        pinHost(host);
        host.addEventListener("click", stop);
        host.addEventListener("mousedown", stop);
        host.addEventListener("pointerdown", stop);
        host.addEventListener("keydown", stop);
        var shadow = host.attachShadow({ mode: "open" });
        var session = {
          key: key,
          gen: gen,
          base: base,
          css: css,
          host: host,
          collapsed: false,
          selection: null,
          notice: "",
          revealMessage: "",
          loading: true,
          error: "",
          token: null,
          report: null,
          fetchedFor: null,
          extracted: { title: "", description: "", price: "" },
        };
        current = session;
        shadow.appendChild(el("style"));
        document.documentElement.appendChild(host);
        startObserver(session);
        return refresh(session, gen);
      });
    });
  }

  function sync() {
    var key = pageKey();
    if (!key) {
      if (current || document.getElementById("verified-asset-root")) removePanel();
      return;
    }
    if (current && current.key === key && document.getElementById("verified-asset-root")) return;
    removePanel();
    mount(key);
  }

  function installUrlWatch() {
    if (globalThis.__VA_URL_WATCH) return;
    globalThis.__VA_URL_WATCH = true;
    var last = location.href;
    var fire = function () {
      var changed = location.href !== last;
      last = location.href;
      var key = pageKey();
      var host = document.getElementById("verified-asset-root");
      if (!changed && (!key || (current && host))) return;
      try {
        sync();
      } catch (err) {
        /* A panel error must not break the page's own navigation. */
      }
    };
    ["pushState", "replaceState"].forEach(function (name) {
      var original = history[name];
      if (typeof original !== "function") return;
      history[name] = function () {
        var result = original.apply(this, arguments);
        try {
          fire();
        } catch (err) {
          /* ignore */
        }
        return result;
      };
    });
    window.addEventListener("popstate", fire);
    window.addEventListener("pageshow", fire);
    if (window.navigation && typeof window.navigation.addEventListener === "function") {
      window.navigation.addEventListener("navigatesuccess", fire);
    }
    window.setInterval(fire, 1000);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible" || !current) return;
      refresh(current, current.gen);
    });
    if (globalThis.chrome && chrome.storage && chrome.storage.onChanged) {
      chrome.storage.onChanged.addListener(function (changes, area) {
        if (area === "sync" && changes.baseUrl) {
          removePanel();
          sync();
        }
      });
    }
  }

  function boot() {
    installUrlWatch();
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", sync, { once: true });
    } else {
      sync();
    }
  }

  boot();
})();
