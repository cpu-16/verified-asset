# Verified Asset

**Evidence reports for second-hand listings, scoped to what the photos can actually show.**

Built for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) (October 26 – November 4, 2026) by AdwenTech.

A seller states claims about an item ("oak dining table, 6 chairs, no visible scratches"), follows guided photo requests, and gets each claim checked against the photos: `supported`, `contradicted` or `inconclusive` **as photographed**. Meta models only *observe*; deterministic code decides. The result is a report bound to the exact photos and listing version that were checked, which a buyer can open without signing up.

## Status

Work in progress. See the [planned architecture](docs/architecture.md) and the [hackathon architecture decision (D-07)](docs/decisions/D-07-hackathon-architecture.md).

## What existed before the hackathon

This repository contains **only work done during the event**, starting from an empty history on October 27, 2026. Before kickoff, the team had a private research prototype (listing-review scripts, notebooks, offline tests) and product planning; none of that code or its git history is included here. The [provenance record](docs/provenance.md) lists what was excluded and why. Open-source dependencies and public datasets used later are labelled where they are used.

**Limits:** a report is not proof of ownership, authenticity, function, comprehensive condition or seller trustworthiness. This is a demo, not affiliated with Meta or Facebook Marketplace.

## License

[MIT](LICENSE). Dependencies, model weights and third-party material keep their own terms.
