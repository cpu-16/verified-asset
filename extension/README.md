# Verified Asset for Marketplace

A Chrome and Brave extension (Manifest V3, plain JavaScript, no build step) that brings a [Verified Asset](https://verified.ciberpty.com) evidence report onto a Facebook Marketplace item page.

It is an independent demo and is not affiliated with Meta. The panel says that on every listing.

## What it does

On `https://www.facebook.com/marketplace/item/…` the extension reads the title, description, and price in the tab. It does not run on Marketplace search or the home feed, but the script is loaded on `www.facebook.com` so it can notice when Facebook changes the URL without a full page load. Away from an item page it removes its panel and does not read the listing.

If the description or a link contains `<base>/r/<token>`, it loads the public report at `<base>/api/r/<token>` and shows one row per claim: supported, contradicted, or inconclusive. Inconclusive rows include the photo to ask the seller for. Invalidated, revoked, and expired reports show “This report no longer matches the listing” and do not show claim rows.

If no report is there, the panel can copy a message that asks the seller to create one. **Create evidence report** opens `<base>/new` in a new tab with the title, the description (at most 2,000 characters), and the item URL.

The toolbar icon opens the options page. The default server is `https://verified.ciberpty.com`. For a local demo, set `http://localhost:8000` and accept the site permission.

## Privacy

- Listing text stays in the tab until you click **Create evidence report**. That click opens a new tab; the title, description, and item URL are the query string of that tab.
- **Copy message for the seller** only writes to the clipboard.
- The only request the extension makes on its own is `GET <base>/api/r/<token>` when a report link is already on the page. The service worker performs that request so Marketplace’s page policy cannot block it, and it refuses any other path.
- The base URL is stored in `chrome.storage.sync`. It is not sent to Verified Asset.

## Load unpacked

1. Open `chrome://extensions` or `brave://extensions`.
2. Turn on Developer mode.
3. Choose **Load unpacked** and select this `extension` folder.
4. Click the toolbar icon to open settings. Leave the default base, or set `http://localhost:8000` for a server on this machine. Saving a custom base asks for permission to contact that host. `http://localhost` covers every port, including 8000.

Reload the extension after pulling changes, then reload the Marketplace tab.

## Try it without Facebook

From this folder:

```bash
node test/check.mjs
```

That checks URL parsing and opens the local fixture in headless Chromium. To look at the panel yourself:

```bash
python3 -m http.server 8765
```

Open `http://127.0.0.1:8765/test/item.html?mock=1`.

| Query | What you should see |
| --- | --- |
| `?mock=1` | Four claim rows from `test/mock-report.json` |
| `?mock=1&state=expired` | The “no longer matches” banner |
| `?mock=1&noreport=1` | No report, plus the seller message button |
| `?mock=1&notitlemeta=1` | Title taken from the page heading |
| `?mock=1&fail=1` | The load-error state |

`?mock=1` does not call the network. Without it, the fixture page calls the API with `fetch`, so that server must allow this page’s origin. The installed extension does not need that; its service worker makes the request.

The heading in the fixture is intentionally different from `og:title`, and a longer block of text sits under the real description. The debug block at the bottom of the fixture is what the checks read.

## What to confirm on a real listing

Marketplace markup is obfuscated and changes. These are the assumptions to check on a live item, while logged in:

- The listing title is in `meta[property="og:title"]`. A trailing `| Facebook` or `| Facebook Marketplace` is removed. If that tag is missing or generic, the panel uses the first `h1` or `aria-level="1"` heading.
- The description is a block next to a short label whose text is `Description` (also `Descripción`, `Descrição`, and a few other language labels). Class names are not used. If the label is missing, the longest `dir="auto"` text is used, then `og:description` when it is not a login prompt.
- Collapsed “See more” text is whatever Facebook has already put in the DOM. Text that loads only after that click is missed until **Check this page again**, or until you highlight it and use **Use selected text as description**.
- The price is `product:price:amount` / `og:price:amount` when present, otherwise the first currency amount within a few parents of the `h1`. A price written only as “Free”, or only inside a closed shadow root, is skipped.
- The report URL is recognized in the description, in link text, in `href`, and in a Facebook `l.facebook.com/l.php?u=…` wrapper. The host must match the base URL in settings. `m.facebook.com` and `web.facebook.com` are not handled.
- The item id is the first path segment of `/marketplace/item/<id>`. The panel is removed when the path is no longer an item. Client-side moves are watched via the Navigation API, `history.pushState` / `replaceState`, and a one-second check.
- A report link that appears only after the first 45 seconds, with no further DOM change while the tab is in the background, waits until you focus the tab or click **Check this page again**.
