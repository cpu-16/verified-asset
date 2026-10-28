/* Options page. The base URL is stored in chrome.storage.sync and is not sent to the server. */
(function () {
  "use strict";

  var REQUIRED = {
    "https://verified.ciberpty.com/*": true,
  };
  var form = document.querySelector("#settings");
  var input = document.querySelector("#base");
  var status = document.querySelector("#status");

  function show(message) {
    status.textContent = message;
  }

  function save(base) {
    chrome.storage.sync.set({ baseUrl: base }, function () {
      var err = chrome.runtime.lastError;
      if (err) {
        show(err.message);
        return;
      }
      input.value = base;
      show("Saved. Open a Marketplace item again to use it.");
    });
  }

  if (!globalThis.chrome || !chrome.storage || !chrome.storage.sync) {
    show("Open this page from the extension options, not as a standalone file.");
    return;
  }

  chrome.storage.sync.get({ baseUrl: VACore.DEFAULT_BASE }, function (stored) {
    input.value = stored.baseUrl || VACore.DEFAULT_BASE;
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var base;
    try {
      base = VACore.normalizeBase(input.value);
    } catch (err) {
      show(err.message);
      return;
    }
    var pattern = VACore.permissionPattern(base);
    if (REQUIRED[pattern]) {
      save(base);
      return;
    }
    /* Request permission before any await so the click still counts as a user gesture. */
    chrome.permissions.request({ origins: [pattern] }, function (granted) {
      var err = chrome.runtime.lastError;
      if (err) {
        show("Could not request permission for that site. " + err.message);
        return;
      }
      if (!granted) {
        show("Permission for that site was not granted. The base URL was not saved.");
        return;
      }
      save(base);
    });
  });
})();
