import unittest
from pathlib import Path
from sqlbench.benchmark import benchmark_query, create_demo_db

ROOT = Path(__file__).resolve().parent.parent / 'examples' / 'patterns'


class AdvancedSqlTests(unittest.TestCase):
    def test_patterns_are_bounded_and_readonly(self):
        for file in sorted(ROOT.glob('*.sql')):
            with self.subTest(query=file.name):
                report = benchmark_query(file.read_text(encoding='utf-8'),
                                         iterations=3, warmups=0)
                self.assertTrue(report['results_consistent'])
                self.assertLess(report['row_count'], 25000)

    def test_running_total_matches_independent_total(self):
        db = create_demo_db()
        try:
            sql = (ROOT / 'running_revenue.sql').read_text(encoding='utf-8')
            result = db.execute(sql).fetchall()
            total = db.execute("SELECT SUM(total_cents) FROM orders WHERE status='paid'").fetchone()[0]
            self.assertEqual(result[-1][2], total)
            self.assertEqual(len(result), 365)
        finally:
            db.close()

    def test_ranked_groups_cap_at_three_per_segment(self):
        db = create_demo_db()
        try:
            sql = (ROOT / 'top_customers_by_segment.sql').read_text(encoding='utf-8')
            rows = db.execute(sql).fetchall()
            segments = {}
            for segment, identifier, name, spend in rows:
                segments.setdefault(segment, []).append(spend)
            self.assertEqual(len(segments), 4)
            for amounts in segments.values():
                self.assertLessEqual(len(amounts), 3)
                self.assertEqual(amounts, sorted(amounts, reverse=True))
        finally:
            db.close()

    def test_calendar_has_31_days(self):
        db = create_demo_db()
        try:
            values = db.execute((ROOT / 'recursive_calendar.sql').read_text()).fetchall()
            self.assertEqual(len(values), 31)
            self.assertEqual(values[0][0], 0)
            self.assertEqual(values[-1][0], 30)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
