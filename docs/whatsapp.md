# WhatsApp test number

1. In [Meta for Developers](https://developers.facebook.com/), create an app with the WhatsApp business messaging use case, associate a business portfolio, and open WhatsApp → API Setup. Use Meta's test number; do not migrate a personal number. Copy the access token and **phone number ID** (not the displayed phone number or WABA ID). Get the app secret from the app settings.
2. In API Setup → To / Manage phone number list, add and verify the demo recipients. Plan for the test number's five-recipient allowance; confirm the limit displayed in your account. Put the same international numbers, digits only, in `WA_ALLOWED`.
3. Set these names in `/etc/verified-asset.env` using your deployment's secret handling. No credentials belong in Git:

   ```dotenv
   WA_TOKEN=
   WA_PHONE_ID=
   WA_APP_SECRET=
   WA_VERIFY_TOKEN=
   WA_ALLOWED=
   WA_GRAPH_VERSION=
   ```

   The first four are required; otherwise both webhook routes return 404. Choose a random verification token. `WA_GRAPH_VERSION` is optional (default `v24.0`); select a supported version from your Meta dashboard. Omit `WA_ALLOWED` to allow any sender; an explicitly empty value allows nobody. Existing `MODEL_API_KEY`, `SPEND_CAP_USD`, `SPEND_DAILY_USD` and `CHECKS_PER_LISTING_PER_DAY` settings still apply. Refresh the temporary Meta access token before rehearsals.
4. When deployment is authorized, restart the service with that environment. Configure callback URL `https://verified.adwentech.com/wa/webhook` and the matching verify token. Subscribe the WhatsApp Business Account object's **messages** field (inbound messages and delivery statuses). Ensure the app is subscribed to the test WABA; API Setup/Configuration normally handles this. Delivery-status notifications are acknowledged without a reply. The reverse proxy must preserve the public HTTPS origin so report and seller links use the correct host.
5. From an allowed phone, send a description. Write the returned capture code on paper and send front, side and detail images in order. Include the paper in the front image. Text or a photo caption supplies the description. After three photos, expect verdicts and the public report URL, followed by a separate private editing link. Send a new image captioned `side`, `detail` or `front` to replace that view; the previous report becomes invalid. Send `new` for another item.
6. From another allowed phone, send the public `/r/{token}` link. Expect its current state, verdicts and suggested questions without another model call. Paste the link into WhatsApp and Messenger to inspect the preview. Verify revocation/expiry by opening the report: messaging clients can retain older previews despite the card's 60-second cache header.

Only text replies are sent, within 24 hours of the incoming message timestamp; no templates or outbound campaigns. Each sender gets 20 listing starts and 20 check attempts per UTC day, persisted in SQLite. Model extraction also uses the web suggestion limiter. Messages are deduplicated in SQLite and each sender is processed under a file lock. Photos are sorted by message timestamp (ties keep receipt order) as the initial three arrive. Later photos require an explicit replacement caption.

`BackgroundTasks` is intentionally small: it is not a durable queue. A process crash after HTTP acknowledgement can lose unfinished work; a claimed message ID is not retried automatically. A failed outbound send records only `wa_send_failed`; open the private listing or send a new message to retry. Keep the service running during the demo. Test with `uv run pytest -q`; HTTP is injected through `app.state.wa_transport`, with no real network or API key.

## API references checked on 2026-10-28

- [Meta webhook verification/signature reference](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/) and [callback acknowledgement](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/types/webhookCallbackFunction/): GET challenge, raw-body HMAC-SHA256 and fast acknowledgement. These SDK references are older; they are not evidence of a new 2026 API revision.
- Meta's official Postman collection: [retrieve media URL](https://www.postman.com/meta/whatsapp-business-platform/request/ptjyi84/retrieve-media-url), [send text](https://www.postman.com/meta/whatsapp-business-platform/request/8gvd47s/send-text-message). Download media using the returned HTTPS URL with bearer authentication. The adapter restricts download hosts and does not follow redirects carrying credentials.
- Current documentation entry points: [getting started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview), [text messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/text-messages), [media](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media). These developer pages returned HTTP 429 during implementation; confirm dashboard setup, supported Graph version, actual download host, permissions and five-recipient allowance in the authenticated account before the live rehearsal.
