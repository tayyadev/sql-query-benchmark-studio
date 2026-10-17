# Security and scope

## Usage boundary

KTNS SQL Benchmark Studio v0.1 is a **local desktop-style developer tool**, not a hosted multi-tenant service. The web interface listens on `127.0.0.1` only and has **no authentication system**. Do not expose its port on a public network or put it behind a reverse proxy. Run it under a non-privileged operating-system account.

No remote SQL Server connection exists. The plan parser works on locally supplied XML. The benchmark engine uses a fabricated in-memory SQLite database by default; only the CLI allows explicit use of a local SQLite database opened `mode=ro`.

## Defensive controls

- Reject SQL statements outside `SELECT` / `WITH` and enforce SQLite's authorizer to deny writes, PRAGMA, ATTACH, transaction and extension operations. A textual prefix check alone is not the security boundary.
- Set `PRAGMA query_only=ON` and SQLite limits (maximum SQL length, value length, columns, expression depth, virtual machine operations and compound SELECTs).
- Interrupt long-running queries using a SQLite progress callback, cap total runs, row counts and concurrent heavy jobs.
- Do not allow the browser API to supply arbitrary file paths or directly connect to databases.
- Require JSON content type, a custom request header, valid loopback Host and matching local Origin (when present); disallow cross-origin traffic via no CORS permission. These are mitigation layers, not general-purpose authentication.
- Allowlist exactly four static file routes to prevent directory traversal.
- Cap JSON POST payloads; reject DTD and entity declarations before parsing XML; cap XML size and node count.
- Do not serialize original SQL statement text from plan documents in JSON reports; emit a SHA-256 digest instead. The local input text remains in the user's browser while the tool is running.
- Render untrusted user-provided messages as text in the UI, not as HTML.
- No telemetry, external JS libraries, third-party web fonts, or default external API connections.

## Known limits

These controls reduce risk but **do not create a hostile-code sandbox**. SQLite expressions may still consume resources within configured ceilings, and a malicious local user could interfere with their own process. Large plans can be CPU-intensive. Use the tool locally only, with authorized inputs and limited privilege.

Query fingerprints can show matching outputs on the *observed dataset*, but cannot establish full SQL semantic equivalence. Timing differences may be caused by caches, CPU scheduling, or data distributions. SQL Server plan costs are relative estimates, not milliseconds or guaranteed speedups.

Reproducible benchmark results require comparable system load, runtime configuration and datasets; never act on one timing run alone.

## Reporting issues

Open a GitHub issue without attaching credentials, business SQL literals, customer details, or confidential plans. If the issue could reveal a vulnerability, contact the repository owner privately instead of publicly posting an exploit.
