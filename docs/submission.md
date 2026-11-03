# Submission draft — Verified Asset

## Name

Verified Asset. <!-- fuente: README.md -->

## One-liner

Check the claims before you make the trip: photo evidence for second-hand listings. <!-- fuente: README.md; app/adjudicate.py -->

## Problem and impact

A bargain sofa is less of a bargain after a wasted trip. Marketplace lists **430 million items every month worldwide**, according to Meta's July 24, 2026 announcement. For local pickup, the buyer has to judge the description before travelling: Facebook Purchase Protection covers eligible purchases with shipping and Facebook checkout; in-person pickup is excluded. <!-- fuente: https://about.fb.com/news/2026/07/connecting-real-people-on-facebook/; https://www.facebook.com/help/228307904608701 -->

The trust gap is concrete. In FloorFound's April 2022 survey of **more than 600 U.S. consumers**, **59%** said they sometimes or often bought furniture on Facebook Marketplace, but only **27%** trusted its item descriptions. Verified Asset gives buyers a way to inspect the evidence before arranging pickup, and sellers a way to show which claims their photos support. <!-- fuente: https://www.prnewswire.com/news-releases/new-consumer-survey-from-floorfound-reveals-shoppers-are-turning-to-resale-as-inflation-shifts-shopping-habits-301524330.html; app/reports.py; README.md -->

Seller, launched in July 2026, and Meta AI in Marketplace draft listings from photos. Facebook Verified checks the person, not the item. Verified Asset asks the reverse question: **which statements in the listing do the photos actually support?** Each claim gets a verdict, a reason and, when needed, a request for more evidence. Sellers share a public report link in their existing conversation; buyers open it without an account. <!-- fuente: https://about.fb.com/news/2026/07/introducing-seller-app-facebook-marketplace/; https://about.fb.com/news/2026/03/facebook-marketplace-new-meta-ai-tools-make-selling-faster-and-easier/; https://about.fb.com/news/2026/07/connecting-real-people-on-facebook/; app/adjudicate.py; app/main.py; app/reports.py -->

## What it does

Sellers choose Furniture, Phones & tablets, Electronics & gaming, Clothing & shoes, or Kitchen & home, then tap fixed attribute suggestions or write their own claims. The catalogue requests the relevant front, side or detail photos. Sellers place the listing's code on paper in the front photo, run the check, review reasons and requests for missing evidence, and create a public report link. Buyers open that link without signing up and see the checked claims, photos, outcomes and current report validity. <!-- fuente: app/catalog.py; app/static/attributes.js; app/main.py; app/templates/listing.html; app/templates/report.html -->

A free sample replays recorded Muse Spark observations of a dining set while running the rules and report lifecycle in the app. It starts without the close-up, so the first check shows Spark's recorded request for it; adding the close-up and checking again shows the contradiction. A seller's own photo check uses the configured observer, and report creation requires a successful check. <!-- fuente: app/main.py:create_sample,run_check,issue; app/observe.py:ReplayObserver -->

## Use of Meta AI tooling

- **Muse Spark 1.3 observes blindly.** It receives individual photos, neutral subject nouns and a structured observation schema, not the seller's claim sentences or expected values. Python rules decide the outcomes. The separate drafting step reads seller text or video frames to prepare editable claims. <!-- fuente: app/observe.py:observation_prompt,SparkObserver; app/catalog.py:count_subjects; app/adjudicate.py -->
- **SAM 3.1 locates evidence.** On eligible live checks with count subjects, it supplies a second count and boxes defects found by Spark. Count disagreement makes a count claim inconclusive. Damage boxes appear on the seller's page; public reports retain the written evidence. Spark observations remain available when optional SAM enrichment fails. <!-- fuente: app/main.py:run_check,sam_marks; app/segment.py:enrich; app/adjudicate.py -->
- **Muse Glimmer 30B is the local evaluation comparator.** The recorded results use the same blind-observation approach and direct-judgment comparison; the hosted pipeline uses Spark. <!-- fuente: eval/run.py; eval/results/muse-glimmer-30b.md; app/observe.py:observer_from_env -->
- **Spark asks for the photo it needs.** When a rule can't decide, Spark looks at the seller's existing photos and plans the one shot that would settle it, with the area marked on their photo; a single instruction covers every claim the same photo can settle. It receives neutral tasks ("see every chair fully"), never the claimed values, and it decides nothing: the seller retakes, and the next blind check and the rules decide. In a live run with the close-up missing, it asked for "near right tabletop corner and edge closely from above"; the new photo turned "No scratches or stains" from can't tell into contradicted (peeling on the tabletop edge). <!-- fuente: app/adjudicate.py:shot_needs; app/observe.py:plan_prompt,plan_shots; app/main.py:attach_shots -->
- **Spark also helps draft.** “Suggest claims” extracts editable rows from seller text. “Film it instead” sends still frames selected in the browser, drafts a listing and selects photos; the seller reviews the draft before the blind check. Video drafts propose counts and colours, never a no-damage claim. <!-- fuente: app/observe.py:extraction_prompt,draft_prompt; app/static/film.js; app/main.py -->

## Technical depth and execution

The closed claim catalogue binds each type to required views. Deterministic rules produce supported, contradicted or inconclusive outcomes with reasons and targeted evidence requests. `part_no_damage` checks visible evidence about a named part; `label_text` compares transcribed text. Missing or unusable required views cannot support a claim. Uncheckable properties remain inconclusive. <!-- fuente: app/catalog.py; app/adjudicate.py; tests/test_attributes.py; tests/test_adjudicate.py -->

A SHA-256 digest binds the report payload to the listing version, checked photo hashes, check and rules version. Saving a text edit in Verified Asset invalidates earlier reports; old links show their terminal state. Replacing a photo requires another check before a new report can be issued, while an already-issued report remains tied to its original photos. Reports can be withdrawn and expire after 30 days. <!-- fuente: app/reports.py; app/store.py; app/main.py:issue; docs/demo-guide.md; tests/test_store.py; tests/test_app.py -->

The paper code is a signal against reused photos when read in a usable image. <!-- fuente: README.md; app/adjudicate.py:capture_code_seen; app/reports.py -->

Paid calls use persistent spend reservations and accounting, photo/prompt caches, and a per-listing paid-check quota. Defaults are $2 per day, $10 total and 5 paid checks per listing per UTC day. One recorded local app run took 6.508 seconds and $0.0345 for three dining-set photos with Spark and SAM; a repeat on the same photos used the cache and no API calls. <!-- fuente: app/observe.py:SpendGuard,listing_check,shared_guard; app/store.py; app/segment.py; eval/results/live-check.md -->

### Evaluation and ablation

On **12 labelled synthetic furniture cases**, blind observation plus rules scored **12/12 with zero false reassurances**, versus **9/12 with two false reassurances** when Spark was shown the claim and asked to judge directly. Glimmer produced the same aggregate split. A false reassurance means “supported” when it should not be. Labels were fixed before the first run. The blind evaluation did not include SAM. <!-- fuente: eval/cases.json; eval/run.py; eval/results/muse-spark-1.3.md; eval/results/muse-glimmer-30b.md; README.md -->

## Prior work and event contribution

Before kickoff, we had a Python research prototype (scripts, notebooks and notes) and product planning in a separate private repository. None of the prototype code or history is in this repository; the first commit imported planning documents derived from it. This repository began with commit `8b471c9` on October 27, 2026 at 19:49:30 (UTC−5), after the October 26 noon kickoff. See [provenance](provenance.md) for the full record and who did what. <!-- fuente: git log --reverse (8b471c9, 2026-10-27T19:49:30-05:00); docs/provenance.md; README.md:What existed before the hackathon -->

## Limits

- **Photos, not guarantees.** We do not prove ownership, authenticity, function, full condition or seller trustworthiness. The paper code is a reuse signal; it does not establish possession, capture time or an unedited image. <!-- fuente: app/reports.py:LIMITS; README.md; app/adjudicate.py:capture_code_seen -->
- **Report scope.** Edits outside Verified Asset cannot be detected. A report digest binds evidence within the app; it is not external certification or proof of server honesty. <!-- fuente: app/reports.py; app/store.py; app/main.py -->
- **Evaluation scope.** The 12 synthetic furniture cases are a design sanity check; differing prompts prevent a clean causal ablation. Other categories and the new part/label rules have no recorded visual evaluation. Their software tests check rule behavior. <!-- fuente: README.md; eval/run.py; eval/cases.json; tests/test_attributes.py -->
- **Impact and operating cost.** Reductions in wasted trips or fraud have not been measured. The recorded runtime and cost describe one local run; billed cost can exceed spend reservations. <!-- fuente: README.md; eval/results/live-check.md; app/observe.py:SpendGuard -->

## Links

- Demo: https://verified.adwentech.com <!-- fuente: README.md -->
- Repository: https://github.com/cpu-16/verified-asset <!-- fuente: README.md; .git/config (origin) -->
- Video: _link added when published_
- Non-furniture example: https://verified.adwentech.com/r/KD4jm0QEXOQQ_Fg3LKueng — **contradicted**, “crack (phone screen)”. <!-- fuente: app/main.py:report_page -->

## Video script — 3:00

| Time | On screen (actual app routes) | Spoken narration |
|---|---|---|
| 0:00–0:15 | `/`, with a prior-work disclosure caption. | “Before kickoff we had a research prototype and product notes, in a separate repo that isn't part of this entry. The app you're about to see is what we built this week.” <!-- fuente: docs/provenance.md; README.md --> |
| 0:15–0:30 | `/`: title, then click **Try the sample** (`POST /sample`), landing on `/l/{listing_id}?k={seller_key}`. | “Will that sofa match the listing when you arrive? Check the claims before making the trip. This free sample replays recorded Spark observations; the rules run now.” <!-- fuente: README.md; app/main.py:create_sample,run_check --> |
| 0:30–0:45 | Sample seller page: **Check my claims**, verdicts, then **Create report link** → `/r/{token}`. Keep this public tab open. | “Spark describes photos without the claimed values. Code decides: supported, contradicted, or inconclusive. Four chairs are supported; no scratches is contradicted; solid oak cannot be settled from photos.” <!-- fuente: app/main.py; app/adjudicate.py; eval/results/muse-spark-1.3.md --> |
| 0:45–1:00 | `/new`: choose Furniture; add **Chairs = 4** and **No visible damage**; continue to `/l/{listing_id}?k={seller_key}`. Show front photo with this listing's paper code and side photo; leave detail empty. | “For a photo check, choose a category and attributes. Each claim requests its evidence. Put this listing's code on paper in the front photo to help spot reused images.” <!-- fuente: app/catalog.py; app/main.py; README.md --> |
| 1:00–1:15 | Same seller page: run check with front and side uploaded; highlight the no-damage verdict and request for the missing detail photo. | “The close-up is missing. The damage claim stays inconclusive, with a request for that photo. Missing evidence must not become reassurance.” <!-- fuente: app/adjudicate.py:_views,_inconclusive; app/templates/listing.html --> |
| 1:15–1:35 | Upload the detail photo via `/l/{listing_id}/photo`, run check via `/l/{listing_id}/check`, show **contradicted** and the SAM box over visible damage on the seller page. | “Now add the close-up and check again. Spark observes the damage; SAM locates it in this box. The rule contradicts the no-damage claim. SAM also checks counts; disagreement means inconclusive.” <!-- fuente: app/main.py:run_check,sam_marks; app/segment.py; app/adjudicate.py --> |
| 1:35–1:50 | Return to sample seller tab; edit count and sentence to six, save via `/l/{listing_id}/edit`; reload the original `/r/{token}`. | “The report binds the listing version and photo hashes. Editing the listing here invalidates the old link. Buyers see that it is no longer valid.” <!-- fuente: app/reports.py; app/store.py; app/main.py; docs/demo-guide.md --> |
| 1:50–2:10 | `/new`: choose **Phones & tablets**, tap **Screen has no visible damage**. Then open `/r/KD4jm0QEXOQQ_Fg3LKueng`. Show phone and screen verdict. | “Now try a phone. Choose the screen claim and open this report: contradicted, with “crack (phone screen)” as the evidence. The report connects the claim to the visible damage.” <!-- fuente: app/catalog.py; app/adjudicate.py --> |
| 2:10–2:30 | `/#evaluation`: comparison chart; caption “Furniture only · Synthetic photos · No SAM in this evaluation”. | “On twelve synthetic furniture cases, Spark plus rules got twelve right, versus nine for direct judgment, with zero versus two false reassurances. Local Muse Glimmer had the same split.” <!-- fuente: eval/results/muse-spark-1.3.md; eval/results/muse-glimmer-30b.md; eval/run.py; README.md --> |
| 2:30–2:45 | From the completed photo-check seller tab, create a new report (`POST /l/{listing_id}/report`) → active `/r/{token}`: open **Is this report genuine?** and **Technical details**; caption “Cached observations · Persistent spend caps · Paid-check quotas”. | “Photo hashes and version binding make the evidence traceable. Caching, persistent spending limits and paid-check quotas bound API use. A failed check cannot issue a report.” <!-- fuente: app/templates/report.html; app/reports.py; app/observe.py; app/main.py:issue --> |
| 2:45–3:00 | `/#limits`, ending on demo and repository URLs. | “Read the limits alongside the evidence. Then open the sample, inspect a claim, and see what happens when the listing changes. Check before you make the trip.” <!-- fuente: app/reports.py; README.md; eval/cases.json --> |

### Recording notes (not spoken)

Plan the edit for 3:00 using the time windows above. They cover Impact (30%), Meta AI Tooling (25%), Technical Depth & Execution (20%) and Demo (25%). The first spoken line discloses prior work.

Use placeholders only for generated listing IDs, seller keys and report tokens; the route patterns are implemented. Hide the private seller key in the recording. Prepare owned demo photos with the new listing's paper code, including a visible defect, and retain a clean sample tab for the invalidation scene. Do not expect SAM boxes from the replay sample or on a public report. Rehearse the fresh-photo missing-view/contradiction/SAM sequence before recording and caption what actually happens. If model waits are trimmed, caption “wait shortened”; if showing a previous run, caption “recorded live run”. Do not call cached or replayed inference a fresh model call. <!-- fuente: app/main.py; app/observe.py; app/segment.py; docs/demo-guide.md; eval/results/live-check.md -->
