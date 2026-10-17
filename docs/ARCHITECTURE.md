# Architecture and technical decisions

```text
             Browser (static vanilla JS)
                  | localhost JSON
                  v
        ThreadingHTTPServer (127.0.0.1)
       /                          \
POST /api/plan*           POST /api/benchmark*
      |                              |
 XML ShowPlan parser            SQLite engine
      |                              |
 2 MiB / 20k nodes              Generated 12k order rows
 Scan, seek, spill info          Read-only authorizer
 Estimated cost stats           2.5-second per-execution limit
      |                          Rows and VM limits
      \                          /
       JSON response → dashboard & export
```

## Why these boundaries?

1. **No SQL Server credentials** required to inspect `.sqlplan` files. Actual/estimated plans can be exported from SSMS and reviewed offline.
2. **No direct production DB benchmarking** in the browser. Query execution is restricted to deterministic synthetic SQLite datasets; local file benchmarking requires a deliberate CLI argument.
3. **Meaningful comparison with caveats.** A statement subtree cost is an optimizer estimate; individual RelOp subtree costs overlap, so they must not be summed. Query timing is measured with `perf_counter_ns` and multiple repetitions. The UI labels them separately.
4. **Code safety.** A `SELECT` prefix alone is not adequate because SQLite permits `WITH... UPDATE`, functions and other behavior. SQLite authorizer, read-only mode and resource limits are layered on top.
5. **No user data ingestion by default.** Sample SQL and `.sqlplan` are invented for this portfolio. The plan API removes raw statement SQL literals from its report.

## API and data contracts

`/api/benchmark` returns `result` containing `timings_ms`, `mean_ms`, `median_ms`, `p95_ms`, `result_fingerprint`, `results_consistent`, `row_count`, and SQLite `EXPLAIN QUERY PLAN` descriptions.

`/api/plan` returns `result` containing `statements`, `operator_counts`, `top_operators`, `missing_indexes`, `findings`, and `estimated_statement_cost_total`.

Comparisons wrap independent reports in `before`, `after`, and `comparison` objects. The plan comparison computes percentage change only if baseline cost is nonzero. Query comparison checks stable observed result fingerprints but cannot prove equivalence on all data.

All routes return `{ "ok": false, "error": {"code": "...", "message": "..."} }` on errors. The API requires a local Host, local Origin (if supplied), and a custom header for POST.

## Future non-public product components

A separately developed Windows Pro edition may use a licensed build, scheduled local scans, advanced exports, workload history or multi-engine adapters. Such components should remain outside this public MIT repository until product and support requirements are validated.
