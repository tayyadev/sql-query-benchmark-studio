import sqlite3
import tempfile
import unittest
from pathlib import Path
from sqlbench.benchmark import (BenchmarkError, DEMO_QUERY, DEMO_QUERY_COMPARISON,
    benchmark_query, compare_queries, create_demo_db, open_sqlite_readonly)


class BenchmarkTests(unittest.TestCase):
    def test_deterministic_seed_counts(self):
        db = create_demo_db()
        try:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM customers').fetchone()[0], 2000)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 12000)
        finally:
            db.close()

    def test_benchmark_summary_and_plan(self):
        result = benchmark_query(DEMO_QUERY, iterations=3, warmups=1)
        self.assertEqual(result['row_count'], 4)
        self.assertEqual(len(result['timings_ms']), 3)
        self.assertGreater(result['p95_ms'], 0)
        self.assertTrue(result['results_consistent'])
        self.assertTrue(result['query_plan'])
        self.assertEqual(result['dataset'], 'synthetic')

    def test_two_queries_same_results(self):
        result = compare_queries(DEMO_QUERY, DEMO_QUERY_COMPARISON, iterations=3, warmups=0)
        self.assertTrue(result['comparison']['same_results_in_demo'])
        self.assertTrue(result['before']['result_fingerprint'])

    def test_comparison_detects_different_results(self):
        result = compare_queries('SELECT COUNT(*) FROM customers',
                                 'SELECT COUNT(*) FROM orders', iterations=3, warmups=0)
        self.assertFalse(result['comparison']['same_results_in_demo'])

    def test_disallow_mutations(self):
        sqls = ['DELETE FROM orders', 'DROP TABLE orders',
                'WITH a AS (SELECT 1) UPDATE orders SET total_cents=1',
                'SELECT 1; DELETE FROM orders;', 'PRAGMA database_list']
        for sql in sqls:
            with self.subTest(sql=sql):
                with self.assertRaises(BenchmarkError):
                    benchmark_query(sql, iterations=3, warmups=0)

    def test_disallow_dangerous_functions_and_row_explosion(self):
        for sql in ['SELECT randomblob(10000000)',
                    'SELECT * FROM customers a CROSS JOIN customers b LIMIT 30000']:
            with self.subTest(sql=sql):
                with self.assertRaises(BenchmarkError):
                    benchmark_query(sql, iterations=3, warmups=0)

    def test_limits_input(self):
        for params in [{'iterations': 2}, {'iterations': 21}, {'warmups': 6},
                       {'iterations': True}, {'warmups': '2'}]:
            with self.subTest(params=params):
                with self.assertRaises(BenchmarkError):
                    benchmark_query('SELECT 1', **params)

    def test_readonly_file_cannot_update(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'test.db'
            db = sqlite3.connect(target)
            db.execute('CREATE TABLE t(v INTEGER)')
            db.execute('INSERT INTO t VALUES (1)')
            db.commit()
            db.close()
            ro = open_sqlite_readonly(target)
            try:
                result = benchmark_query('SELECT v FROM t', iterations=3, warmups=0, db=ro)
                self.assertEqual(result['row_count'], 1)
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute('INSERT INTO t VALUES (2)')
            finally:
                ro.close()
            verify = sqlite3.connect(target)
            self.assertEqual(verify.execute('SELECT COUNT(*) FROM t').fetchone()[0], 1)
            verify.close()

    def test_invalid_sql_reports_error(self):
        with self.assertRaises(BenchmarkError):
            benchmark_query('SELECT FROM customers', iterations=3, warmups=0)


if __name__ == '__main__':
    unittest.main()
