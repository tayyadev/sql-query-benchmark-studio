"""CLI entrypoint; no installed dependencies required."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmark import BenchmarkError, benchmark_query, compare_queries, open_sqlite_readonly
from .plans import PlanError, analyze_plan, compare_plans
from .server import start_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sqlbench", description="KTNS SQL Benchmark Studio")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inspect = sub.add_parser("plan", help="Inspect a local SQL Server .sqlplan file")
    inspect.add_argument("file", type=Path)
    compare = sub.add_parser("compare-plans", help="Compare two ShowPlan XML files")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    bench = sub.add_parser("benchmark", help="Benchmark SELECT on synthetic or explicit read-only SQLite")
    bench.add_argument("sql_file", type=Path)
    bench.add_argument("--database", type=Path, help="Explicitly selected local SQLite file, read-only")
    bench.add_argument("--iterations", type=int, default=7)
    bench.add_argument("--warmups", type=int, default=2)
    pair = sub.add_parser("compare-sql", help="Compare read-only SQL queries on synthetic dataset")
    pair.add_argument("before", type=Path)
    pair.add_argument("after", type=Path)
    pair.add_argument("--iterations", type=int, default=7)
    pair.add_argument("--warmups", type=int, default=2)
    serve = sub.add_parser("serve", help="Run browser UI bound to 127.0.0.1 only")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "serve":
            server = start_server(args.port)
            print(f"KTNS SQL Benchmark Studio: http://127.0.0.1:{server.server_port}")
            try:
                server.serve_forever(poll_interval=.1)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        if args.cmd == "plan":
            result = analyze_plan(args.file.read_bytes())
        elif args.cmd == "compare-plans":
            result = compare_plans(args.before.read_bytes(), args.after.read_bytes())
        elif args.cmd == "benchmark":
            sql = args.sql_file.read_text(encoding="utf-8")
            if args.database:
                db = open_sqlite_readonly(args.database)
                try:
                    result = benchmark_query(sql, iterations=args.iterations, warmups=args.warmups, db=db)
                finally:
                    db.close()
            else:
                result = benchmark_query(sql, iterations=args.iterations, warmups=args.warmups)
        else:
            result = compare_queries(args.before.read_text(encoding="utf-8"),
                                     args.after.read_text(encoding="utf-8"),
                                     iterations=args.iterations, warmups=args.warmups)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
