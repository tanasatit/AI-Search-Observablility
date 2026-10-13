import unittest

import _support  # noqa: F401
from aiso.collect import should_stop


class ShouldStopBoundsTest(unittest.TestCase):
    def test_below_min_never_stops(self):
        # even a perfectly unanimous result keeps going until min repeats
        self.assertFalse(should_stop({"A": [1, 1]}, 2, 3, 10, 0.2))
        self.assertFalse(should_stop({"A": []}, 0, 3, 10, 0.2))

    def test_at_or_above_max_always_stops(self):
        borderline = {"A": [1, 0] * 5}
        self.assertTrue(should_stop(borderline, 10, 3, 10, 0.2))
        self.assertTrue(should_stop(borderline, 11, 3, 10, 0.2))
        self.assertTrue(should_stop(borderline, 10, 3, 10, 0.2, rule="ci"))


class DecisionRuleTest(unittest.TestCase):
    def test_four_of_four_stops_at_four(self):
        self.assertTrue(should_stop({"A": [1, 1, 1, 1]}, 4, 3, 10, 0.2))

    def test_three_of_three_does_not_stop(self):
        # Wilson lower bound for 3/3 is ~0.44, still below the 0.5 threshold
        self.assertFalse(should_stop({"A": [1, 1, 1]}, 3, 3, 10, 0.2))

    def test_zero_of_four_stops(self):
        # upper bound for 0/4 is ~0.49 < 0.5: we know it is "usually not mentioned"
        self.assertTrue(should_stop({"A": [0, 0, 0, 0]}, 4, 3, 10, 0.2))
        self.assertFalse(should_stop({"A": [0, 0, 0]}, 3, 3, 10, 0.2))

    def test_every_entity_must_be_decided(self):
        ind = {"A": [1, 1, 1, 1], "B": [0, 0, 0, 0], "C": [1, 0, 1, 0]}
        self.assertFalse(should_stop(ind, 4, 3, 10, 0.2))
        del ind["C"]
        self.assertTrue(should_stop(ind, 4, 3, 10, 0.2))

    def test_threshold_is_configurable(self):
        # 4/4 has lower bound ~0.51: decided against 0.5, not against 0.6
        self.assertTrue(should_stop({"A": [1] * 4}, 4, 3, 10, 0.2, threshold=0.5))
        self.assertFalse(should_stop({"A": [1] * 4}, 4, 3, 10, 0.2, threshold=0.6))

    def test_no_tracked_entities_stops_at_min(self):
        self.assertTrue(should_stop({}, 3, 3, 10, 0.2))


class CiRuleTest(unittest.TestCase):
    def test_wide_interval_keeps_going(self):
        # 5/10 half-width ~0.263
        self.assertFalse(should_stop({"A": [1, 0] * 5}, 10, 3, 20, 0.2, rule="ci"))

    def test_margin_controls_stopping(self):
        self.assertTrue(should_stop({"A": [1, 0] * 5}, 10, 3, 20, 0.3, rule="ci"))

    def test_unanimous_results_are_not_width_checked(self):
        # Existing behaviour: only 0 < k < n is width-checked, so all-in / all-out stop at min.
        self.assertTrue(should_stop({"A": [1, 1, 1]}, 3, 3, 20, 0.05, rule="ci"))
        self.assertTrue(should_stop({"A": [0, 0, 0]}, 3, 3, 20, 0.05, rule="ci"))

    def test_every_entity_must_be_narrow(self):
        ind = {"A": [1] * 3, "B": [1, 0, 1]}
        self.assertFalse(should_stop(ind, 3, 3, 20, 0.2, rule="ci"))


if __name__ == "__main__":
    unittest.main()
