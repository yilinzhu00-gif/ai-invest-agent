"""Offline regression tests for the scoring data-quality gate."""

from __future__ import annotations

import math
import unittest

import scoring

DEMO_METRICS = {
    "pe_ttm": 18.5,
    "pb": 2.3,
    "roe": 16.2,
    "net_margin": 12.5,
    "gross_margin": 38.0,
    "rev_growth": 22.0,
    "profit_growth": 28.0,
    "debt_ratio": 45.0,
    "current_ratio": 1.8,
    "ret_60d": 8.0,
    "price_vs_ma20": 3.5,
}


class EvaluateScoreQualityTests(unittest.TestCase):
    def test_single_metric_is_insufficient_and_hides_the_rating(self) -> None:
        """Removing core-dimension data must prevent a partial valuation rating."""
        evaluation = scoring.evaluate_score({"pe_ttm": 10})

        self.assertEqual(evaluation["status"], "insufficient_data")
        self.assertAlmostEqual(evaluation["coverage"], 0.12)
        self.assertIn("profit", evaluation["missing_core_dimensions"])
        self.assertIsNone(evaluation["result"])

    def test_complete_demo_metrics_have_full_coverage_and_a_result(self) -> None:
        """A complete scorecard must pass the quality gate without external services."""
        evaluation = scoring.evaluate_score(DEMO_METRICS)

        self.assertEqual(evaluation["status"], "ok")
        self.assertAlmostEqual(evaluation["coverage"], 1.0)
        self.assertEqual(evaluation["missing_core_dimensions"], [])
        self.assertEqual(evaluation["missing_metrics"], [])
        self.assertIsNotNone(evaluation["result"])

    def test_invalid_values_are_reported_and_excluded_from_coverage(self) -> None:
        """NaN, infinity, strings, and None must not be treated as score inputs."""
        metrics = DEMO_METRICS | {
            "pe_ttm": math.nan,
            "pb": math.inf,
            "roe": "not-a-number",
            "net_margin": None,
        }
        evaluation = scoring.evaluate_score(metrics)

        self.assertEqual(evaluation["status"], "insufficient_data")
        self.assertAlmostEqual(evaluation["coverage"], 0.6125)
        self.assertTrue({"pe_ttm", "pb", "roe", "net_margin"} <= set(evaluation["missing_metrics"]))
        self.assertIn("valuation", evaluation["missing_core_dimensions"])
        self.assertNotIn("profit", evaluation["missing_core_dimensions"])
        self.assertIsNone(evaluation["result"])

    def test_one_complete_core_dimension_cannot_produce_a_rating(self) -> None:
        """Coverage alone cannot substitute for evidence across core dimensions."""
        evaluation = scoring.evaluate_score({"pe_ttm": 10, "pb": 1})

        self.assertEqual(evaluation["status"], "insufficient_data")
        self.assertAlmostEqual(evaluation["coverage"], 0.20)
        self.assertIsNone(evaluation["result"])

    def test_complete_legacy_score_dimensions_remain_unchanged(self) -> None:
        """The gate must not change legacy scoring for complete existing callers."""
        result = scoring.score_stock(DEMO_METRICS)

        self.assertEqual(
            [(dimension["name"], dimension["score"]) for dimension in result["dimensions"]],
            [
                ("估值", 77.8),
                ("盈利能力", 82.2),
                ("成长性", 82.2),
                ("财务健康", 78.6),
                ("动量/技术面", 73.8),
            ],
        )
