# D-07 — Hackathon architecture and cloud-inference gate

Type: wayfinder:architecture-decision
Status: accepted direction by Jeff, 2026-10-27; execution conditional on G0/G1/G2/G3
Blocked by: G0 (Meta API eligibility, credit balance, pricing, image/data terms), G1 (measured vision quality)
Blocks: new hackathon product implementation and judge-facing model claims
Scope: October 27–November 4 hackathon increment only; production D-01–D-06 remain closed and unchanged
Architecture diagram: [docs/architecture.md](../architecture.md) (planned system, not as-built)
Decision source: Jeff's instruction to lock the Opus 5.5 judge's conditional Architecture B with sponsor cloud-inference credits.
Evidence: /tmp/verified_asset_review_result.md and /tmp/verified_asset_opus_judgment.md (host-local, not repository evidence); docs/experiments.md, scripts/review_listing.py, D-01–D-06.

## Accepted design, not a claim of existing functionality

Choose conditional **B: hosted Meta Muse Spark vision → value-blind typed observations → deterministic code adjudication → immutable versioned evidence report**. Spark is the target runtime if G0 and G1 pass; if not, fall back to A with locally hosted Muse Glimmer, preserving identical rules and clear labels for recorded observations. Never silently fail over. No three-model inference pipeline in the submission critical path. SAM 3.1 may be explored only as a timed optional counting experiment after G1 and the end-to-end path are protected.

The innovation to demonstrate is an evidence lifecycle: claim first, prescribed capture, observations obtained WITHOUT showing the model the seller's claimed value, policy-bound adjudication, targeted retake, confirmed correction/re-check, and a revocable snapshot-linked report. Model count is not an acceptance criterion.

Hackathon category is **Furniture/home goods only**, preserving D-02's Furniture + Clothing production scope and conditional personal-electronics decision. No claims of authenticity, ownership, function, age/history, material provenance, deliverability, seller trustworthiness, or comprehensive condition. This is a prototype, not a production pilot.

## Decision record (minimal Business / Data / Application / Technology architecture)

- AD-1 / Technology / model route: one perception-model adapter with served-model ID, version, context/config, prompt/schema/rules version, request outcome, token/compute usage, latency and applicable cost recorded for every check. Try hosted Muse Spark first only when G0 passes; Glimmer remains explicit local fallback and evaluation comparator. No model adjudicates. Model-side errors/invalid schema/timeouts are FAILED checks, not 'inconclusive'. No model endpoint is exposed directly to judges.
- AD-2 / Demo and security: host one small Python web application with persisted state and a judge-safe session or reset, mobile-accessible without seller invitation. Judges must see an actual working claim/report lifecycle. Use bounded **live hosted inference only if** G0/G1 pass and a per-session/global quota, access code or sample-only restriction, strict image size, concurrency and budget counter are active. Otherwise clearly label replayed observations, including model, date and version, and use live rules/lifecycle. Labels must distinguish Live, Recorded live run, Replayed. Do not imply a recorded model call is live.
- AD-3 / Data: listing version, capture session (24h), photo slot + content hash, check run, observations, adjudication, report version and event log are distinct records. Preserve prior versions for audit; never mutate issued claims. A report references the exact listing version, photos and successful check; each report version has its own unguessable URL. The old URL displays only invalidated/revoked/expired/deleted state after transition, never another version's claims. A new correction/version gets a new check or deterministic re-adjudication of unchanged source observations ONLY if claim type, subject, evidence and version binding make that safe. Retaken images require a new check. D-05's one session per report / per listing language is clarified for implementation as one active session bound to one listing, with report versions bound to that session's successful checks; pricing/report counting remains provisional.
- AD-4 / Application: an allowlisted typed-claim catalogue defines required views and highest possible outcome. Evidence from the model is restricted to *observations*, usable-view flags, counts/colour/defect details, photo slot references and uncertainty. Code alone emits supported, contradicted or inconclusive using versioned rules. Missing required views / uncertain observation -> inconclusive with reason and retake. Non-photo-checkable material, function, provenance and broad 'like new' claims never become supported. No report issued from any failed/missing claim result. Seller confirms a suggested correction; re-evaluate against correctly bound current evidence. Do not adopt 'any contradiction wins' if multiple non-independent observers are later introduced without measuring false alarms.
- AD-5 / Capture and privacy: seller supplies claims first, then guided photos. Preserve raw private seller evidence OFF cloud, off Git and off the public demo. Only personally owned, deliberately staged, consented, non-sensitive demo images may be marked **demo-cleared** for Meta cloud experiments; strip EXIF before request, disallow people, documents, identifying location, account details or client items; store hashes, not cloud-transmitted raw results, in public evidence. Document model provider processing in the demo disclosure. Before any real-user cloud product processing, require a separate privacy/consent/data-retention decision and provider-term review. D-03 raw-capture deletion 90 days after expiry/revocation/invalidation or sooner upon report deletion remains authoritative.
- AD-6 / Business and assurances: retain D-03's exact assurance and D-04 judge access. 'A material listing change invalidates' can be enforced only for *in-app* edits; external Marketplace edits cannot be detected without integration. Display the checked text/photo snapshot and comparison limits without claiming broader coverage. Administrative report lifecycle metadata (state, version, expiry, fingerprint) is allowed to make D-03's promise enforceable; do not add trust scores or badges. Sponsor credits fund development only, not a validated sustainable unit economics claim; D-06's $2.50 cash-cost ceiling and hypothetical $5 price require measurement excluding credit subsidies in the normal-case estimate.
- AD-7 / Quality and provenance: pre-register labelled observations and expected outcomes before inference; separate software tests, paired model evaluations and user feedback. Count wrong supports, missed contradictions, correct/incorrect inconclusives, schema failures, latency p95 and cost with explicit denominators. Preserve failures. Disclose reused pre-event code and model/runtime dependencies; no eligibility conclusion without organizers' rules.

## Sponsor inference credits and G0 funding policy

Official organizer page: https://events.cerebralvalley.ai/e/meta-ai-developer-hackathon
Meta event: https://dev.meta.ai/events/global-hackathon

Advertised, NOT yet proven credited or eligible on Jeff's account:
- $150 Meta Model API credits per accepted participant, claim and account activation required (see docs/meta-planning-handoff.md); no assumption that the batch has arrived.
- Baseten $100, Modal $100, Fireworks $25 **for selected participants** under partner-specific terms. These are separate wallets and cannot be assumed fungible with Meta Model API Spark usage.
- Jeff says the sponsors provide cloud inference credits; this confirms the design preference, NOT receipt/available balance.

G0 must record: (1) correct event/Startup Track enrollment and eligibility, (2) Meta Billing *actual credited balance*, promotion expiry and any claim instructions, (3) Spark availability/image API, response schema, rate limits and price, (4) approved demo-only cloud-photo policy and terms, (5) one tiny non-sensitive test image request, served model, latency, usage and result, (6) application-level hard quota and maximum cash exposure. Meta alert is NOT a hard cap. Do not make a chargeable inference request just because a credit was advertised; if balance is uncredited, either await activation or seek explicit approval of a small cash test budget. Never commit keys.

## Three engineering gates (pass/fail evidence required)

- G1 / Perception by Wed Oct 28: pre-register a clear true/false colour claim, true and inflated count, missing view, real visible mark if one exists, and a deliberately poor photo; repeat 3 times where practical. After policy, zero wrong supported claims in the small test, at least two of three correct on clear true/false cases, poor-photo flagged at least two of three, valid parse after at most one retry, slow-end check time <=45 seconds. These are smoke-test gates, NOT accuracy or safety guarantees. Compare Spark against Glimmer on equal cases and report denominators. Spark promoted only if G0/G1 pass. If neither passes, narrow to count and colour or pivot transparently to an evidence-request assistant.
- G2 / Rules and lifecycle by Thu Oct 29: tests confirm missing view -> inconclusive; unprovable classes never supported; failure -> NO report; correction and retake properly re-checked; report cites exact immutable listing/photo/check versions; 30-day expiry, in-app invalidation, revoke/deletion and old-link behavior verified with fake clock. One genuinely new end-to-end run, no manual database edits.
- G3 / Judge access by Fri Oct 30: fresh browser/mobile data, under three minutes, no invitation/login: sample claim -> labelled live/replayed evidence -> issue report -> buyer opens link -> in-app edit invalidates -> revoke. Public report page contains no raw photo URL. Demo inference limited to pre-cleared samples and enforced budget/call caps.

SAM gate (NOT critical path): if access is already active and remaining time allows <=60 minutes, run >=4 preregistered included-piece counting cases with >=2 exaggerated counts and a partially occluded view. Retain only if it corrects >=1 error, causes ZERO new false decisions, adds <=10s p95, and the integration fits <=60 minutes. Otherwise publish honest negative finding and omit SAM from the shipped stack.

## Fixed delivery order and hard cuts (human capacity ~12–18 hours to Nov 1)

1. Tue Oct 27 (2–2.5h): G0 sponsor balance/terms and small test; write D-07; prepare metadata-free owned test photos and labelled claim set; commit answers before testing.
2. Wed Oct 28 (2.5–3h): perception adapter and rule layer; G1; no model-count additions until G1 passes. Fix only critical model-output failures.
3. Thu Oct 29 (2.5–3h): smallest seller flow, capture, adjudication, corrected draft/recheck, immutable report; G2.
4. Fri Oct 30 (2.5–3h): report lifecycle, hosted judge demo, strict quota/access, independent browser check; G3.
5. Sat Oct 31 (2–3h): held-out negative-heavy cases (aim 12–16 with clear denominators), model-only vs observation+rules, log failures and basic performance/cost.
6. Sun Nov 1 (1.5–2.5h): freeze scope, README claims, provenance ledger, 3-minute video draft, prepublication checklist. Leave 2–3h on Nov 2–3 for final video and submission if available.

Hard cuts: SAM, 2nd model in critical runtime, clothing UI, dynamic natural-language claim splitting, styling, elaborate per-judge sandboxes, secondary physical item, fancy comparators. Never cut evidence/rules separation, honesty labels, check failures, report version binding, invalidation/revocation or held-out counts.

## Status, authority and next actions

The **design decision is locked**, not the provider's runtime fitness or cloud-credit availability. No implementation, credit spend or publicity is authorized by this document alone. D-01–D-06 retain their original final status; the limited hackathon-scope clarifications above do not silently amend their commercial/privacy commitments.

Immediate actions:
1. Verify Meta Model API credits actually appear in account billing and confirm participant/partner eligibility and demo-photo processing terms.
2. Perform G0 with one deliberately staged, scrubbed, non-sensitive image after the credited balance and cap are verified; record technical facts only.
3. Pre-register furniture claims and outcomes, execute G1, then hand the measured choice B or A to the implementation agent.

Execution state as of 2026-10-27: **G0 model smoke PASS / overall G0 PARTIAL** (billing balance reported by Jeff, not independently read; application hard spending counter not yet built; provider retention and demo-photo processing review not complete). **G1 = NOT RUN; G2 = NOT RUN; G3 = NOT RUN.** Change these only with test evidence.

## G0 observed evidence — October 27, 2026, 15:59 Panama

- Jeff reports **$138 promotional credits remaining** in his Meta account before this smoke request. His report confirms account funding direction; the agent did not retrieve a post-call billing receipt or token-usage breakdown.
- Meta's published Model API documents specify endpoint `https://api.meta.ai/v1`, model `muse-spark-1.3`, image input in user content, and JSON schema constrained output. Standard-mode pricing as consulted October 27: $1.25 / million input tokens and $4.25 / million output tokens, discounted cached input; exact per-image-equivalent token count was not recorded. Standard mode is documented as not used to train Meta models; this **does not** establish a complete retention agreement for real-user photos. Docs: https://dev.meta.ai/docs/overview ; https://dev.meta.ai/docs/cookbook/vision-input ; https://dev.meta.ai/docs/structured-output ; https://dev.meta.ai/docs/pricing-rate-limits .
- Environment: installed Muse Code CLI 1.4.13 with previously saved Meta credentials (no key read into output), `muse exec --provider meta --model muse-spark-1.3 --contributor-mode off --reasoning-effort low --preset empty --max-model-steps 1 --disable-shell --disable-write --disable-web-tools --no-session-log`, plus prescribed image and JSON schema. No subagents, remote workspace tool calls, or private photos.
- Safe fixture outside repo: `/tmp/verified_asset_g0_shapes.png` (generated geometry: 3 blue squares, 1 red circle, white field) and `/tmp/verified_asset_g0_schema.json`. This is **NOT** an evaluation of furniture recognition or seller claim support.
- Result: process exit 0 in **4.62 seconds total CLI runtime** and exact JSON response `{"blue_squares":3,"red_circles":1,"usable":true}`. The one response correctly counted fixture shapes and satisfied schema. No inference token receipt was captured and therefore the exact dollar charge is unknown; don't subtract an invented value from the promotional balance.
- **G0 technical findings:** saved credentials work; a hosted Spark image call succeeds; constrained JSON response and low latency succeed on synthetic shapes. G0 remains PARTIAL because user billing was not independently read, full provider terms for demo-photo use were not reviewed and an enforceable app-level quota/cost meter has not been implemented.
- **Billing caution:** Meta documents that an alert is **not** a hard spending cap: https://dev.meta.ai/help/billing/spend-limit-alert . No paid G1 runs are authorized until a bounded experiment budget and metadata-scrubbed owned images are ready.
