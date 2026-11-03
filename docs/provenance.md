# Provenance and contribution record

This file says what this repository contains, what existed before it, and who did what.
It is a disclosure, not a certification of eligibility: that is for the hackathon
organizers to decide.

## What this repository is

The repository's history starts on **October 27, 2026 at 19:49 (UTC−5)** with commit
`8b471c9`, after the October 26 kickoff. Every commit since is in this history, and
the commit times can be checked with `git log --reverse`.

Commit times show when something was committed. They do not by themselves prove who
wrote it or when it was first drafted.

## What existed before

| Material | Where it lives | In this repository? |
| --- | --- | --- |
| Concept and product planning (from October 21) | A separate private repository | Not as history. The first commit imported planning documents derived from it: `docs/architecture.md` and `docs/decisions/D-07-hackathon-architecture.md`. |
| Research prototype (listing-review scripts, notebooks, offline tests, experiment notes) | The same separate private repository | **No.** None of its code, notebooks, prompts or git history is included. |

The application code in `app/`, `eval/`, `extension/`, `tests/` and `deploy/` was
committed in this repository after October 27. Where the planning documents describe
a design, the code is the evidence of what was built; the documents are not.

## Who did what

- **Jeff:** concept and product decisions.
- **Gilberto:** code.

## Third-party material

Meta's Muse Spark 1.3 and SAM 3.1 are called through the Meta API. Muse Glimmer 30B
runs locally for evaluation only. Python and JavaScript dependencies keep their own
licences (see `pyproject.toml` and `uv.lock`). The repository is MIT licensed; model
weights and third-party material keep their own terms.

## Claims this repository does not make

- It does not claim the earlier prototype or the October 21–26 planning as event work.
- It does not claim that planning documents were written after kickoff.
- It does not claim a bonus-prize category on the strength of the local Glimmer
  evaluation: the hosted product runs on Muse Spark through the Meta API.
