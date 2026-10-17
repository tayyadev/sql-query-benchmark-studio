# Verification notes — v0.1.0

Automated test suite (Python stdlib `unittest`):

- SQL Server ShowPlan XML parsing, missing-index and spill diagnostics, limits and entity/DTD rejection.
- Sample plan comparison and non-disclosure of statement SQL literals in API output.
- SQLite synthetic fixture determinism, read-only authorization, benchmark correctness, resource limits, comparison fingerprints and optional explicit read-only file mode.
- Advanced SQL query examples (window functions, ranking, recursion, anti-join and totals).
- Loopback local HTTP endpoints, JSON headers, content limits, cross-origin and Host restrictions, static file allowlist.

Browser HTML/CSS/JavaScript was visually smoke-tested in headless Chromium with simulated API responses generated from the actual benchmark/plan engines, covering the benchmark and plan report interactions. Browser-to-loopback network requests could not be exercised in the restricted build environment; HTTP endpoints were tested independently at the protocol level. Complete installation QA on Windows and testing against real exported SQL Server plans remain for release validation.

Run:

```bash
python -m unittest discover -s tests -v
python -m compileall -q sqlbench
node --check web/app.js
```
