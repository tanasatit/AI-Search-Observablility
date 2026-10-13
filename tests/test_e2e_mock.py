"""End-to-end: drive aiso.collect.main() with the MockProvider, all inside temp dirs.

Never touches data/ or reports/, never calls the network, never needs GEMINI_API_KEY.
"""
import contextlib
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from _support import EXAMPLE_CONFIG
from aiso import collect
from aiso.entities import load_config
from aiso.extract import extract
from aiso.providers import MockProvider, ProviderError, build_provider


def _no_network(*_a, **_k):
    raise AssertionError("tests must not touch the network")


class _Sandbox(unittest.TestCase):
    """Temp config copied from config.example.json, temp output dir, no network, no sleeping."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiso-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.config = os.path.join(self.tmp, "config.json")
        shutil.copyfile(EXAMPLE_CONFIG, self.config)
        self.cfg, self.entities, self.queries = load_config(self.config)

        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        for p in (mock.patch.dict(os.environ, env, clear=True),
                  mock.patch("urllib.request.urlopen", _no_network),
                  mock.patch.object(collect.time, "sleep", lambda *_: None)):
            p.start()
            self.addCleanup(p.stop)

    def run_collect(self, *args):
        out = tempfile.mkdtemp(prefix="raw-", dir=self.tmp)  # one output dir per run
        argv = ["aiso.collect", "--config", self.config, "--provider", "mock", "--rpm", "0",
                "--out", out, "--session", "test", *args]
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(buf):
            collect.main()
        files = glob.glob(os.path.join(out, "*.jsonl"))
        self.assertEqual(len(files), 1, buf.getvalue())
        with open(files[0], encoding="utf-8") as f:
            return [json.loads(line) for line in f]


class MockProviderTest(_Sandbox):
    def test_build_provider_mock(self):
        p = build_provider("mock", self.entities)
        self.assertIsInstance(p, MockProvider)
        res = p.ask(self.queries[0])
        self.assertEqual(set(res), {"answer", "citations", "usage", "model", "search_queries"})
        self.assertTrue(res["answer"])

    def test_deterministic(self):
        a = build_provider("mock", self.entities)
        b = build_provider("mock", self.entities)
        for q in self.queries[:3]:
            for _ in range(3):
                self.assertEqual(a.ask(q), b.ask(q))

    def test_extract_on_mock_answers(self):
        p = build_provider("mock", self.entities)
        seen = set()
        for q in self.queries:
            out = extract(p.ask(q), self.entities)
            self.assertEqual(set(out), {e.name for e in self.entities})
            seen |= {n for n, f in out.items() if f["mentioned"]}
        self.assertTrue(seen, "mock answers should mention at least one configured shop")

    def test_gemini_without_key_exits_cleanly(self):
        with self.assertRaises(SystemExit):
            build_provider("gemini", self.entities)


class CollectEndToEndTest(_Sandbox):
    MAX = 10

    def test_fixed_vs_adaptive(self):
        fixed = self.run_collect("--mode", "fixed", "--repeats", str(self.MAX))
        adaptive = self.run_collect("--mode", "adaptive", "--min", "3", "--max", str(self.MAX))

        n_q = len(self.queries)
        self.assertEqual(len(fixed), self.MAX * n_q)
        self.assertTrue(all("error" not in r for r in fixed + adaptive))
        self.assertTrue(all(r["provider"] == "mock" and r["session"] == "test" for r in fixed))

        per_query = {}
        for r in adaptive:
            per_query[r["query_id"]] = per_query.get(r["query_id"], 0) + 1
        self.assertEqual(set(per_query), set(range(n_q)))
        self.assertTrue(all(3 <= n <= self.MAX for n in per_query.values()), per_query)
        self.assertLess(len(adaptive), len(fixed))

    def test_adaptive_focus_target_saves_more(self):
        all_ = self.run_collect("--mode", "adaptive", "--max", str(self.MAX))
        target = self.run_collect("--mode", "adaptive", "--max", str(self.MAX), "--focus", "target")
        self.assertLessEqual(len(target), len(all_))
        self.assertLess(len(target), self.MAX * len(self.queries))

    def test_adaptive_is_deterministic(self):
        strip = ("record_id", "run_id", "ts", "latency_ms")
        a = self.run_collect("--mode", "adaptive", "--limit-queries", "3")
        b = self.run_collect("--mode", "adaptive", "--limit-queries", "3")
        clean = lambda rs: [{k: v for k, v in r.items() if k not in strip} for r in rs]  # noqa: E731
        self.assertEqual(clean(a), clean(b))

    def test_max_requests_budget(self):
        recs = self.run_collect("--mode", "fixed", "--repeats", "10", "--max-requests", "7")
        self.assertEqual(len(recs), 7)

    def test_errors_are_not_counted_as_not_mentioned(self):
        """Regression: adaptive stopping used the attempt count (including failed requests)
        as n, so failures counted as 'not mentioned' and a provider that only ever errored
        was 'decided' after 4 records with zero real observations."""

        class AlwaysFails:
            name = "failing"

            def ask(self, query):
                raise ProviderError("HTTP 500: boom", status=500)

        with mock.patch.object(collect, "build_provider", lambda *a, **k: AlwaysFails()):
            out = os.path.join(self.tmp, "raw")
            argv = ["aiso.collect", "--config", self.config, "--rpm", "0", "--out", out,
                    "--mode", "adaptive", "--min", "3", "--max", "6", "--limit-queries", "1"]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                collect.main()
        (path,) = glob.glob(os.path.join(out, "*.jsonl"))
        with open(path, encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        self.assertTrue(all("error" in r for r in recs))
        self.assertEqual(len(recs), 6, "no stop decision should be made without successful data")


if __name__ == "__main__":
    unittest.main()
