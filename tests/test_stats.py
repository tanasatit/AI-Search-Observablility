import unittest

import _support  # noqa: F401  (puts the repo root on sys.path)
from aiso.stats import (half_width, jaccard, mean_pairwise_jaccard, required_n,
                        variance_decomposition, wilson)


class WilsonTest(unittest.TestCase):
    def test_no_data_is_uninformative(self):
        self.assertEqual(wilson(0, 0), (0.0, 0.0, 1.0))

    def test_half(self):
        p, lo, hi = wilson(5, 10)
        self.assertAlmostEqual(p, 0.5)
        self.assertAlmostEqual(lo, 0.237, places=3)
        self.assertAlmostEqual(hi, 0.763, places=3)

    def test_symmetric_around_half(self):
        _, lo, hi = wilson(5, 10)
        self.assertAlmostEqual(lo + hi, 1.0)

    def test_all_hits(self):
        p, lo, hi = wilson(10, 10)
        self.assertEqual(p, 1.0)
        self.assertAlmostEqual(lo, 0.722, places=3)
        self.assertEqual(hi, 1.0)

    def test_no_hits(self):
        p, lo, hi = wilson(0, 10)
        self.assertEqual(p, 0.0)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.278, places=3)

    def test_small_samples(self):
        self.assertAlmostEqual(wilson(3, 3)[1], 0.438, places=3)
        self.assertAlmostEqual(wilson(4, 4)[1], 0.510, places=3)

    def test_bounds_always_in_unit_interval_and_contain_estimate(self):
        for n in range(1, 41):
            for k in range(n + 1):
                p, lo, hi = wilson(k, n)
                with self.subTest(k=k, n=n):
                    self.assertGreaterEqual(lo, 0.0)
                    self.assertLessEqual(hi, 1.0)
                    self.assertLessEqual(lo, p + 1e-12)
                    self.assertGreaterEqual(hi, p - 1e-12)

    def test_interval_narrows_with_n(self):
        widths = [half_width(n // 2, n) for n in (4, 10, 40, 100)]
        self.assertEqual(widths, sorted(widths, reverse=True))


class HalfWidthTest(unittest.TestCase):
    def test_matches_wilson(self):
        _, lo, hi = wilson(5, 10)
        self.assertAlmostEqual(half_width(5, 10), (hi - lo) / 2)
        self.assertAlmostEqual(half_width(5, 10), 0.263, places=3)

    def test_no_data(self):
        self.assertEqual(half_width(0, 0), 0.5)


class JaccardTest(unittest.TestCase):
    def test_both_empty(self):
        self.assertEqual(jaccard([], set()), 1.0)

    def test_one_empty(self):
        self.assertEqual(jaccard({"a"}, set()), 0.0)

    def test_identical_and_partial(self):
        self.assertEqual(jaccard({"a", "b"}, ["b", "a", "a"]), 1.0)
        self.assertAlmostEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)

    def test_mean_pairwise_needs_two_sets(self):
        self.assertIsNone(mean_pairwise_jaccard([]))
        self.assertIsNone(mean_pairwise_jaccard([{"a"}]))
        self.assertIsNone(mean_pairwise_jaccard(iter([{"a"}])))

    def test_mean_pairwise(self):
        self.assertEqual(mean_pairwise_jaccard([{"a"}, {"a"}, {"a"}]), 1.0)
        # pairs: (ab,ab)=1, (ab,c)=0, (ab,c)=0 -> 1/3
        self.assertAlmostEqual(mean_pairwise_jaccard([{"a", "b"}, {"a", "b"}, {"c"}]), 1 / 3)
        # accepts a generator
        self.assertEqual(mean_pairwise_jaccard(s for s in [{"x"}, {"y"}]), 0.0)


class RequiredNTest(unittest.TestCase):
    def test_extremes_use_half(self):
        expected = required_n(0.5, 0.1)
        self.assertEqual(expected, 97)  # ceil(1.96^2 * 0.25 / 0.01) = ceil(96.04)
        self.assertEqual(required_n(0.0, 0.1), expected)
        self.assertEqual(required_n(1.0, 0.1), expected)

    def test_skewed_p_needs_fewer(self):
        self.assertLess(required_n(0.1, 0.1), required_n(0.5, 0.1))
        self.assertEqual(required_n(0.1, 0.1), 35)  # ceil(3.8416 * 0.09 / 0.01) = ceil(34.57)

    def test_at_least_one(self):
        self.assertEqual(required_n(0.5, 10), 1)


class VarianceDecompositionTest(unittest.TestCase):
    def test_needs_two_non_empty_sessions(self):
        self.assertIsNone(variance_decomposition({}))
        self.assertIsNone(variance_decomposition({"d1": [1, 0, 1]}))
        self.assertIsNone(variance_decomposition({"d1": [1, 0], "d2": []}))

    def test_sessions_agree(self):
        out = variance_decomposition({"d1": [1, 0, 1, 0], "d2": [0, 1, 0, 1]})
        self.assertEqual(out["between"], 0.0)
        self.assertAlmostEqual(out["within"], 0.25)
        self.assertEqual(out["share_between"], 0.0)
        self.assertEqual(out["sessions"], 2)

    def test_pure_drift(self):
        out = variance_decomposition({"d1": [1, 1, 1], "d2": [0, 0, 0]})
        self.assertEqual(out["within"], 0.0)
        self.assertAlmostEqual(out["between"], 0.25)
        self.assertEqual(out["share_between"], 1.0)

    def test_no_variance_at_all(self):
        out = variance_decomposition({"d1": [1, 1], "d2": [1, 1]})
        self.assertEqual(out["share_between"], 0.0)


if __name__ == "__main__":
    unittest.main()
