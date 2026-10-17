import unittest
from pathlib import Path
from sqlbench.plans import PlanError, analyze_plan, compare_plans

ROOT = Path(__file__).resolve().parent.parent
SCAN = (ROOT / "examples/sample-scan.sqlplan").read_text(encoding="utf-8")
SEEK = (ROOT / "examples/sample-seek.sqlplan").read_text(encoding="utf-8")


class PlanAnalyzerTests(unittest.TestCase):
    def test_scan_metrics_and_warnings(self):
        report = analyze_plan(SCAN)
        self.assertEqual(report["format"], "sqlserver-showplan")
        self.assertEqual(report["statement_count"], 1)
        self.assertEqual(report["operator_counts"], {"Table Scan": 1})
        self.assertEqual(report["estimated_statement_cost_total"], 1.824)
        self.assertEqual(len(report["missing_indexes"]), 1)
        self.assertEqual(report["missing_indexes"][0]["columns"]["EQUALITY"], ["[Status]"])
        self.assertEqual({f["code"] for f in report["findings"]}, {"scans", "spills", "index_hints"})

    def test_seek_and_comparison(self):
        report = analyze_plan(SEEK)
        self.assertEqual(report["operator_counts"], {"Index Seek": 1})
        self.assertEqual(len(report["missing_indexes"]), 0)
        pair = compare_plans(SCAN, SEEK)
        self.assertTrue(pair["comparison"]["same_statement_hashes"])
        self.assertLess(pair["comparison"]["estimated_cost_delta_percent"], 0)
        self.assertIn("does not demonstrate", pair["comparison"]["caveat"].lower())

    def test_rejects_non_showplan_root(self):
        with self.assertRaises(PlanError):
            analyze_plan("<other/>")

    def test_rejects_invalid_xml(self):
        with self.assertRaises(PlanError):
            analyze_plan("<ShowPlanXML><RelOp></ShowPlanXML>")

    def test_rejects_doctype_and_entities(self):
        for xml in ['<!DOCTYPE p [<!ENTITY a "X">]><ShowPlanXML>&a;</ShowPlanXML>',
                    '<!ENTITY foo "bar"><ShowPlanXML></ShowPlanXML>']:
            with self.subTest(xml=xml):
                with self.assertRaises(PlanError):
                    analyze_plan(xml)

    def test_rejects_overlarge_plan(self):
        with self.assertRaises(PlanError):
            analyze_plan("<ShowPlanXML>" + " " * (2 * 1024 * 1024) + "</ShowPlanXML>")

    def test_never_includes_full_sql_literals(self):
        doc = SCAN.replace("'paid'", "'PRIVATE-SAMPLE-TOKEN'")
        report = analyze_plan(doc)
        self.assertNotIn("PRIVATE-SAMPLE-TOKEN", str(report))
        self.assertEqual(len(report["statements"][0]["query_sha256"]), 64)

    def test_rejects_empty_input(self):
        for source in ("", None, [], b"bad"):
            with self.subTest(source=source):
                with self.assertRaises(PlanError):
                    analyze_plan(source)

    def test_real_row_counts_aggregated(self):
        xml = '''<ShowPlanXML><StmtSimple StatementText="s" StatementSubTreeCost="1">
          <RelOp PhysicalOp="Index Seek" EstimatedTotalSubtreeCost="0.1">
          <RunTimeCountersPerThread ActualRows="9"/><RunTimeCountersPerThread ActualRows="3"/>
          </RelOp></StmtSimple></ShowPlanXML>'''
        self.assertEqual(analyze_plan(xml)["top_operators"][0]["actual_rows"], 12)


if __name__ == "__main__":
    unittest.main()
