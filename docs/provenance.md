# Hackathon provenance and contribution record

Recorded October 26, 2026, following Jeff's authorization to establish the
conservative baseline recommended in the kickoff review. This records provenance;
it does not certify eligibility or establish the organizer's official start time.

## Fixed boundary

- Branch: `codex/hackathon-2026`.
- Original checkout: `codex/claim-review-prompt` at
  `a797d53b4509b57e68ee6136214a2f29a4a33e51` (October 21).
- Excluded baseline: `c9ba36a1fea920df60ae00327e283cb20b0ca8e4`.
- Annotated tag: `hackathon-baseline-2026-10-26`.
- Baseline commit time: `2026-10-26T12:42:42-05:00` (America/Bogota).

Everything at the baseline, including same-day planning, is excluded from the
claimed hackathon contribution. This deliberately avoids claiming uncertain
pre/post-kickoff work. It does not assert that all baseline material predates
kickoff. Original history and dates are preserved; no reinitialization, history
rewrite, or backdating was performed. The baseline recorded additions or
annotations across 17 Markdown paths as
excluded background, not new product implementation. Do not move or replace this tag.

The historical pause checkpoint says planning was not yet committed. That was true
when it was written; the baseline above subsequently committed it unchanged.

## Prior work disclosure

| Material | Existing before this boundary |
| --- | --- |
| October 21 prototype | Python listing review and validation, guided-checklist helper, prompts, three learning notebooks, offline tests and experiment notes |
| October 22 learning branch | PyTorch notebook/setup and intent-check documentation on `codex/pytorch-learning`, ending at `a280467b094b32db838be27722a9a3c8e2cd7097`; not imported into this branch |
| October 26 planning | Seller-first production decisions, research, handoffs, project instructions, historical proposal and documentation annotations |

Using or modifying these components later does not make the original components
new. Record the reused source and describe the actual change. Identify third-party
dependencies separately from original event work.

## Work after the boundary

Reconciled against local Git history through source snapshot
`a8b3d92e607c27bcd21338e9354b37ee4e2911a6` on October 27, 2026.
Times below are Git author and committer times (equal for these four commits),
not independently established original creation times or proof of eligibility.

| Commit | Recorded time (UTC−05:00) | Changed paths and classification | Evidence and limits |
| --- | --- | --- | --- |
| `7ee8449e7399f7cad9e7e002fea47ce46686e333` | `2026-10-26T12:45:48-05:00` | Added `LICENSE`, `docs/hackathon-provenance.md`, `docs/hackathon-kickoff-review.md`; amended `README.md`. Administrative licensing, disclosure and kickoff recommendations. | Commit diff; kickoff review cites transcript offsets, not a fresh official rule confirmation. MIT notice does not make the existing prototype new. |
| `8e3d496727d505b8e567aa66d1d1cd2c88ec1e30` | `2026-10-27T15:26:39-05:00` | Added `.scratch/verified-asset/tickets/D-07-hackathon-architecture.md`; amended `.scratch/verified-asset/map.md` and `AGENTS.md`. Architecture decision and narrow demo-photo governance. | Commit diff and D-07 AD-1–AD-7/G0–G3. Reuses excluded production decisions D-01–D-06; conditional design, not implementation or cloud-photo clearance. |
| `4f280308afa9cadf9f52a809eabb682e2fecfb27` | `2026-10-27T16:00:56-05:00` | Amended D-07 only. Recorded hosted Spark synthetic-image/schema smoke evidence. | D-07 records a 15:59 Panama test, `muse-spark-1.3`, generated geometry, exit 0, 4.62 seconds total CLI runtime and correct schema-shaped counts. This audit read the record, not the external fixture or a new model run. No furniture evaluation, token receipt or exact charge; $138 balance is Jeff-reported. G0 technical smoke PASS / overall G0 PARTIAL; G1–G3 NOT RUN. |
| `a8b3d92e607c27bcd21338e9354b37ee4e2911a6` | `2026-10-27T17:40:53-05:00` | Added `docs/architecture.md`; amended D-07 and `README.md`. Planned architecture diagram, navigation and implementation-status documentation. | Commit diff and architecture built/planned table. No end-to-end product, furniture adapter, policy engine, persisted report service or judge demo implemented. |

The baseline-to-source diff has **8 changed paths**. It is empty for `scripts/`,
`tests/`, `prompts/`, `notebooks/`, `evaluations/`, `examples/` and
`requirements.txt`: those components remain excluded prior work. Modified README,
map and AGENTS files contain baseline content; their entire contents cannot be
claimed as newly authored work. See the fresh-repository handoff (private pre-event repository)
for the file inventory, source hashes and conservative export gates.

Current README/architecture/map/kickoff-review edits, the readiness document and
this provenance/migration handoff are **uncommitted preparation**, outside the source snapshot above. There
is no new commit SHA to cite for them. Reinspect the final diff and record the
actual resulting source commit only after an authorized commit exists; never
invent a SHA or export uncommitted working-tree bytes as that older snapshot.

No new product implementation is claimed through the audited snapshot. For each
future completed increment record the actual commit, authoring evidence, reused
components, validation and demo relevance. Record failures and recorded/demo-only
results honestly. Keep private evidence and raw image-derived text outside Git.

## Official rules and cutoff — unresolved release blocker

The public [organizer page](https://events.cerebralvalley.ai/e/meta-ai-developer-hackathon)
and [Meta page](https://dev.meta.ai/events/global-hackathon) were rechecked on
October 27. Their event dates/kickoff livestream references do **not** establish
the exact eligible coding-start instant. The public pages still describe full
rules as forthcoming before kickoff; the applicable full participant rules,
scoring rubric, exact cutoff with timezone, prior-work treatment/disclosure
requirements, accepted team/track and Gilberto's participation remain unconfirmed.
No organizer confirmation is recorded. The local conservative boundary is not a
substitute for these facts and does not automatically validate the earliest
post-boundary commit. Obtain and retain the actual rules/version and organizer
clarification before claiming compliance or finalizing an eligible-work selection.

The current organizer page advertises Fireworks $100; D-07's $25 is a historical
record of what was consulted then, not proof of any available wallet. Do not
silently rewrite that history or assume sponsor credits have been received.

## Daily commit procedure

1. Confirm the active branch and inspect `git status --short`.
2. Inspect the working diff and each untracked file. Separate new work, older
   imports, generated files and private material; do not select by file timestamp.
3. Stage exact paths or individual changed sections. Avoid blanket `git add .` or
   `git add -A`. Do not force-add ignored evidence or credentials.
4. Review `git diff --cached --stat`, `git diff --cached` and
   `git diff --cached --check`. Run checks appropriate to the change.
5. Commit a small completed increment with an accurate description. Record the
   commit in this ledger after it exists. Keep original author dates for imports.
6. Review the cumulative changes using:

```bash
git log --reverse --oneline hackathon-baseline-2026-10-26..HEAD
git diff --stat hackathon-baseline-2026-10-26 HEAD
git diff hackathon-baseline-2026-10-26 HEAD -- scripts tests prompts notebooks
```

The first two commands include documentation and licensing work. Add new application
paths to the last command when they exist. Do not present every post-baseline line
as a new product feature. These are review procedures, not an automatic eligibility
or secret-detection enforcement mechanism.

## Publication preparation and remaining checks

- The repository was verified private during the October 26 review. This work does
  not change visibility, push branches/tags, or submit an entry.
- A bounded scan examined 95 historical blob versions reachable from all locally
  available refs before the baseline commit. No private-key, GitHub-token, AWS-key,
  or quoted assigned-secret pattern matches were found. A separate scan of the
  17 baseline candidate files found no matches.
- No historical paths matched the checked evidence directories, common photo/video
  extensions, `.env`, `.pem`, or `.key` patterns. Six historical notebook versions
  had no outputs, execution counts, or cell attachments. No notebook changes were
  necessary. Embedded source text and other formats still require content review.
- This was a bounded pattern scan, not comprehensive secret or rights clearance.
  Gitleaks was not installed. Remote-only refs were not fetched or scanned.
- MIT licensing is included for repository software and associated documentation.
  Dependencies, model weights and third-party material retain their own terms.
  Source: [OSI MIT license](https://opensource.org/license/mit).
- Before public release, inspect every remote branch/tag that will become public,
  review retained content for private or third-party material, and run a complete
  secret scan across the publication history. `.gitignore` does not remove already
  tracked content from history.
- Publish through the existing feature-branch and PR workflow when authorized;
  preserve the baseline tag and keep the contribution summary visible on the
  submitted branch. Verify repository, video and demo links without authentication.
- Confirm participant rules, track, accepted teammates, exact kickoff cutoff and
  prior-work disclosure format with the organizer. Record the actual response;
  no organizer message has been sent by this task.

## Organizer clarification draft

I have an October 21–22 Python/notebook prototype and October 26 product planning.
I have preserved that history and marked all existing material as excluded from
my claimed hackathon contribution, with a baseline recorded on October 26 at
12:42:42 UTC−05:00. I intend to disclose reused components and demonstrate only
new event-built functionality. Can you confirm the exact eligible start time and
whether a baseline commit/tag plus an explicit contribution log satisfies your
prior-work disclosure requirements? How should same-day pre-kickoff planning be
reported?
