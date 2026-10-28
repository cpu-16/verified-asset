# Live check through the app

October 28, 2026, 03:5x UTC, on a laptop with the app running locally (`uvicorn`, one process) and a Meta API key.

The three dining-set photos in `eval/photos/` were uploaded through the seller page of two listings with the same claims (4 chairs, white, no scratches, solid oak), then each listing's check was run.

| | First listing | Second listing, same photos |
|---|---|---|
| Observer | `muse-spark-1.3 (live)` | `muse-spark-1.3 (live)` |
| Check time (`checks.latency_ms`) | 6508 ms | 4 ms (every observation from the cache) |
| Muse Spark calls | 3, one per photo, in parallel | 0 |
| SAM 3.1 calls | 4: "chair" on each photo, "peeling" on the close-up | 0 |
| Tokens (Spark) | 6,765 in, 3,769 out | 0 |
| API cost (spend ledger) | $0.0345 ($0.0245 Spark + $0.0100 SAM) | $0.00 |

Verdicts: 4 chairs supported (Spark 4, SAM 4, in the front and side photos), white supported, no scratches contradicted (peeling in the close-up, boxed by SAM), solid oak can't be checked. The paper code was read in the front photo.

The timings, tokens and costs come from the local database and `spend.json` of that run, which are not in the repository.
