/* Fetches a public report from the extension process so Facebook's page CSP
   cannot block it. The only request this worker makes is GET <base>/api/r/<token>. */
importScripts("core.js");

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (!message || message.type !== "va-fetch-report") return;
  if (!sender || !sender.tab) {
    sendResponse({ ok: false, error: "Unexpected caller." });
    return;
  }
  var target;
  try {
    target = VACore.assertReportApiUrl(message.url);
  } catch (err) {
    sendResponse({ ok: false, error: err.message || "Unexpected report URL." });
    return;
  }
  fetch(target, { method: "GET", credentials: "omit", cache: "no-store", redirect: "follow" })
    .then(function (res) {
      var finalUrl;
      try {
        finalUrl = VACore.assertReportApiUrl(res.url);
      } catch (err) {
        sendResponse({ ok: false, error: "The report request was redirected somewhere unexpected." });
        return null;
      }
      if (finalUrl !== target) {
        sendResponse({ ok: false, error: "The report request was redirected somewhere unexpected." });
        return null;
      }
      return res.text().then(function (body) {
        if (body.length > 1000000) {
          sendResponse({ ok: false, error: "The report response was too large." });
          return;
        }
        sendResponse({ ok: res.ok, status: res.status, body: body });
      });
    })
    .catch(function () {
      sendResponse({ ok: false, error: "The report could not be reached." });
    });
  return true;
});

chrome.action.onClicked.addListener(function () {
  chrome.runtime.openOptionsPage();
});
