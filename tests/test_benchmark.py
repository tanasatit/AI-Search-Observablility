import io
import unittest
from collections import Counter

from _support import EXAMPLE_CONFIG
from aiso.benchmark import DEFAULT_GOLD, METRICS, evaluate, load_gold, prf, print_report, table
from aiso.entities import load_config
from aiso.extract import extract

_, ENTS, _ = load_config(EXAMPLE_CONFIG)
NAMES = {e.name for e in ENTS}
GOLD = load_gold(DEFAULT_GOLD)

# Targets from the project brief. Floors sit a little below the current numbers so a real regression fails the build,
# but one new hard case added to the gold set does not.
FLOORS = {"mentioned": (0.95, 0.95), "cited": (0.95, 0.95), "recommended": (0.90, 0.90)}


class GoldCorpusTest(unittest.TestCase):
    def test_size_and_ids(self):
        self.assertGreaterEqual(len(GOLD), 150)
        ids = [c["id"] for c in GOLD]
        self.assertEqual(len(ids), len(set(ids)))

    def test_labels_are_consistent(self):
        for c in GOLD:
            with self.subTest(id=c["id"]):
                for m in METRICS:
                    self.assertTrue(set(c["gold"][m]) <= NAMES, f"unknown entity in {m}")
                self.assertTrue(set(c["gold"]["recommended"]) <= set(c["gold"]["mentioned"]),
                                "recommended must also be mentioned")
                self.assertIn(c["split"], {"dev", "test", "holdout"})
                for cite in c["citations"]:
                    self.assertEqual(set(cite), {"url", "title"})

    def test_covers_required_languages_and_hard_cases(self):
        self.assertEqual({c["lang"] for c in GOLD}, {"th", "en", "mix"})
        cats = Counter(c["category"] for c in GOLD)
        for cat in ["alias", "near_miss", "competitor_only", "not_recommended", "structure", "negation", "citation",
                    "unknown"]:
            self.assertGreaterEqual(cats[cat], 5, cat)
        self.assertTrue(any("vertexaisearch" in x["url"] and "." in x["title"] for c in GOLD for x in c["citations"]),
                        "needs Google redirect urls with domain-only titles")
        self.assertTrue(any(c["gold"]["mentioned"] == [] and c["gold"]["cited"] for c in GOLD),
                        "needs cited-but-not-mentioned (source chips)")

    def test_gold_answers_are_not_trivially_one_sided(self):
        for m in METRICS:
            pos = sum(len(c["gold"][m]) for c in GOLD)
            self.assertGreater(pos, 30, m)
            self.assertLess(pos, len(GOLD) * len(NAMES) * 0.5, m)


class ExtractorAccuracyTest(unittest.TestCase):
    def check(self, cases, floors=FLOORS):
        res = evaluate(cases, ENTS)
        for metric, p, r, _f1, tp, fp, fn in table(res):
            fp_floor, fn_floor = floors[metric]
            self.assertGreaterEqual(p, fp_floor, f"{metric} precision {p:.3f}; errors: {res['errors'][:5]}")
            self.assertGreaterEqual(r, fn_floor, f"{metric} recall {r:.3f}; errors: {res['errors'][:5]}")

    def test_whole_corpus(self):
        self.check(GOLD)

    def test_each_split(self):
        for split in ("dev", "test", "holdout"):
            with self.subTest(split=split):
                # the holdout split is small, so one miss moves recall a lot: only the brief's floors apply
                self.check([c for c in GOLD if c["split"] == split],
                           {"mentioned": (0.95, 0.95), "cited": (0.95, 0.95), "recommended": (0.85, 0.85)})


class BenchmarkMechanicsTest(unittest.TestCase):
    def test_prf(self):
        for got in prf(8, 2, 2):
            self.assertAlmostEqual(got, 0.8)
        self.assertEqual(prf(0, 0, 0), (None, None, None))
        self.assertEqual(prf(0, 3, 3)[2], 0.0)

    def test_perfect_and_broken_extractors(self):
        sample = GOLD[:20]

        def oracle(record, entities):
            case = next(c for c in sample if c["answer"] == record["answer"])
            return {e.name: {m: e.name in case["gold"][m] for m in METRICS} for e in entities}

        def always_false(record, entities):
            return {e.name: {m: False for m in METRICS} for e in entities}

        self.assertEqual(evaluate(sample, ENTS, oracle)["errors"], [])
        broken = evaluate(sample, ENTS, always_false)
        self.assertTrue(broken["errors"])
        self.assertTrue(all(x["kind"] == "fn" for x in broken["errors"]))

    def test_report_prints_errors_on_request(self):
        buf = io.StringIO()
        res = evaluate(GOLD[:30], ENTS, lambda r, e: {x.name: {m: True for m in METRICS} for x in e})
        print_report(res, show_errors=True, out=lambda s="": buf.write(s + "\n"))
        out = buf.getvalue()
        self.assertIn("precision", out)
        self.assertIn("FP", out)

    def test_real_extractor_is_deterministic(self):
        a = evaluate(GOLD, ENTS, extract)["errors"]
        b = evaluate(GOLD, ENTS, extract)["errors"]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
