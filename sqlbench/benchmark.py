"""Read-only, resource-bounded SQLite benchmarks on synthetic local data."""
from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

MAX_ROWS = 25_000
MAX_SECONDS = 12.0
SINGLE_SECONDS = 2.5

class BenchmarkError(ValueError):
    """Invalid query, unsafe operation or workload overrun."""

DEMO_QUERY = """SELECT c.segment, COUNT(*) AS paid_orders,
ROUND(SUM(o.total_cents) / 100.0, 2) AS revenue
FROM customers c JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'paid' GROUP BY c.segment ORDER BY revenue DESC"""
DEMO_QUERY_COMPARISON = """SELECT c.segment, COUNT(o.id) AS paid_orders,
ROUND(SUM(o.total_cents) / 100.0, 2) AS revenue
FROM customers c JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
GROUP BY c.segment ORDER BY revenue DESC"""


def create_demo_db() -> sqlite3.Connection:
    """A reproducible in-memory workload: 2k fabricated customers, 12k orders."""
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
          segment TEXT NOT NULL, region TEXT NOT NULL);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
          total_cents INTEGER NOT NULL CHECK(total_cents > 0), status TEXT NOT NULL,
          created_day INTEGER NOT NULL, FOREIGN KEY(customer_id) REFERENCES customers(id));
        CREATE INDEX idx_segment ON customers(segment);
        CREATE INDEX idx_customer_status ON orders(customer_id, status);
        CREATE INDEX idx_order_status ON orders(status);
    """)
    segments = ("Startup", "Growth", "Enterprise", "Nonprofit")
    regions = ("East", "West", "Central", "South")
    rng = random.Random(20261017)
    db.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", (
        (i, f"Demo Customer {i:04d}", segments[i % 4], regions[(i * 3) % 4])
        for i in range(1, 2001)
    ))
    db.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", (
        (i, rng.randrange(1, 2001), rng.randrange(1200, 250000),
         ("paid", "paid", "pending", "refunded")[i % 4], i % 365)
        for i in range(1, 12001)
    ))
    db.commit()
    return db


def open_sqlite_readonly(file: str | Path) -> sqlite3.Connection:
    """CLI-only: explicitly selected SQLite path, never exposed to the web API."""
    path = Path(file).expanduser().resolve(strict=True)
    if not path.is_file():
        raise BenchmarkError("Specify an existing SQLite file.")
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)


def _guard(sql: Any) -> str:
    if not isinstance(sql, str) or not (1 <= len(sql.strip()) <= 12000):
        raise BenchmarkError("SQL must contain 1–12,000 characters.")
    query = sql.strip()
    if "\x00" in query or not query.lower().startswith(("select ", "select\n", "select\t",
                                                          "with ", "with\n", "with\t")):
        raise BenchmarkError("Only SELECT or WITH queries are supported.")
    return query


def _authorize(op: int, arg1: str | None, arg2: str | None,
               db_name: str | None, source: str | None) -> int:
    del arg1, db_name, source
    if op in {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK
    if op == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() not in {
        "load_extension", "readfile", "writefile", "randomblob", "zeroblob"
    }:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _fingerprint(rows: list[tuple[Any, ...]]) -> str:
    """Order independent aggregate fingerprint, including duplicate row counts."""
    digest_sum, digest_xor = 0, 0
    for row in rows:
        data = json.dumps(row, default=str, ensure_ascii=False, allow_nan=False)
        value = int.from_bytes(hashlib.sha256(data.encode("utf-8")).digest(), "big")
        digest_sum = (digest_sum + value) % (1 << 256)
        digest_xor ^= value
    marker = f"{len(rows)}:{digest_sum:064x}:{digest_xor:064x}"
    return hashlib.sha256(marker.encode("ascii")).hexdigest()


def _once(db: sqlite3.Connection, sql: str, deadline: float) -> tuple[float, int, str]:
    db.set_progress_handler(lambda: int(time.perf_counter() > deadline), 1000)
    start = time.perf_counter_ns()
    rows: list[tuple[Any, ...]] = []
    try:
        cur = db.execute(sql)
        if cur.description is None or len(cur.description) > 64:
            raise BenchmarkError("Queries must return 1–64 columns.")
        while True:
            batch = cur.fetchmany(256)
            if not batch:
                break
            rows.extend(batch)
            if len(rows) > MAX_ROWS:
                raise BenchmarkError("Result exceeds 25,000 rows; use a tighter filter.")
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
    except sqlite3.Error as exc:
        if "interrupted" in str(exc).lower():
            raise BenchmarkError("Query interrupted after its execution time limit.") from exc
        raise BenchmarkError(f"Read-only SQLite query failed: {exc}") from exc
    finally:
        db.set_progress_handler(None, 0)
    return elapsed, len(rows), _fingerprint(rows)


def benchmark_query(sql: str, *, iterations: int = 7, warmups: int = 2,
                    db: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Measure a bounded read-only query, returning a JSON-compatible report."""
    query = _guard(sql)
    if type(iterations) is not int or not 3 <= iterations <= 20:
        raise BenchmarkError("Iterations must be an integer between 3 and 20.")
    if type(warmups) is not int or not 0 <= warmups <= 5:
        raise BenchmarkError("Warmups must be an integer between 0 and 5.")
    own = db is None
    connection = db if db is not None else create_demo_db()
    try:
        # Bound SQLite resources in addition to runtime and row-count ceilings.
        if hasattr(connection, "setlimit"):
            limits = {
                sqlite3.SQLITE_LIMIT_LENGTH: 8192,
                sqlite3.SQLITE_LIMIT_COLUMN: 64,
                sqlite3.SQLITE_LIMIT_SQL_LENGTH: 12000,
                sqlite3.SQLITE_LIMIT_EXPR_DEPTH: 100,
                sqlite3.SQLITE_LIMIT_VDBE_OP: 100_000,
                sqlite3.SQLITE_LIMIT_COMPOUND_SELECT: 30,
            }
            for category, limit in limits.items():
                connection.setlimit(category, limit)
        connection.execute("PRAGMA query_only=ON")
        connection.set_authorizer(_authorize)
        try:
            steps = connection.execute("EXPLAIN QUERY PLAN " + query).fetchall()
        except sqlite3.Error as exc:
            raise BenchmarkError(f"Could not plan query: {exc}") from exc
        begin = time.perf_counter()
        timings: list[float] = []
        fingerprints: list[str] = []
        counts: list[int] = []
        for index in range(warmups + iterations):
            deadline = min(begin + MAX_SECONDS, time.perf_counter() + SINGLE_SECONDS)
            if time.perf_counter() >= deadline:
                raise BenchmarkError("Total benchmark time budget exceeded.")
            elapsed, count, digest = _once(connection, query, deadline)
            if index >= warmups:
                timings.append(elapsed)
                fingerprints.append(digest)
                counts.append(count)
        sorted_timings = sorted(timings)
        avg = statistics.mean(timings)
        return {
            "engine": "sqlite", "dataset": "synthetic" if own else "user_supplied_readonly",
            "iterations": iterations, "warmups": warmups,
            "row_count": counts[-1], "result_fingerprint": fingerprints[-1],
            "results_consistent": len(set(fingerprints)) == 1 and len(set(counts)) == 1,
            "timings_ms": [round(t, 4) for t in timings],
            "mean_ms": round(avg, 4),
            "median_ms": round(statistics.median(timings), 4),
            "p95_ms": round(sorted_timings[math.ceil(len(timings) * .95) - 1], 4),
            "min_ms": round(min(timings), 4), "max_ms": round(max(timings), 4),
            "relative_stddev": round(statistics.pstdev(timings) / avg, 4) if avg else 0,
            "query_plan": [{"id": s[0], "parent": s[1], "detail": str(s[3])[:300]}
                           for s in steps[:100]],
            "limitations": "Local SQLite timings are hardware and cache dependent and "
                           "do not predict SQL Server speed.",
        }
    finally:
        if own:
            connection.close()
        else:
            connection.set_authorizer(None)
            connection.execute("PRAGMA query_only=OFF")


def compare_queries(before: str, after: str, *, iterations: int = 7,
                    warmups: int = 2) -> dict[str, Any]:
    left = benchmark_query(before, iterations=iterations, warmups=warmups)
    right = benchmark_query(after, iterations=iterations, warmups=warmups)
    same = (left["result_fingerprint"] == right["result_fingerprint"] and
            left["results_consistent"] and right["results_consistent"])
    old, new = left["median_ms"], right["median_ms"]
    return {
        "before": left, "after": right,
        "comparison": {
            "same_results_in_demo": same,
            "median_time_reduction_percent": round((old - new) / old * 100, 2) if old else 0,
            "caveat": "Fingerprints only compare observed results; they do not prove equivalence. "
                      "Small timing changes may be noise. SQLite != SQL Server.",
        },
    }
