"""python -m unittest discover -s tests   (no network, stdlib only)"""
import csv
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from aiso import manual, runsheet
from aiso.manual import parse_citation_line, parse_query_subset, read_block, split_answer

def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CitationLineTests(unittest.TestCase):
    def test_bare_url(self):
        self.assertEqual(parse_citation_line("https://a.com/x"), {"url": "https://a.com/x", "title": "https://a.com/x"})

    def test_bracket_number(self):
        for line in ("[1] https://a.com/x", "[12]: https://a.com/x", "  [3]https://a.com/x"):
            self.assertEqual(parse_citation_line(line)["url"], "https://a.com/x", line)

    def test_other_list_markers(self):
        for line in ("1. https://a.com/x", "2) https://a.com/x", "(4) https://a.com/x",
                     "- https://a.com/x", "* https://a.com/x", "<https://a.com/x>"):
            self.assertEqual(parse_citation_line(line)["url"], "https://a.com/x", line)

    def test_title_after_url(self):
        c = parse_citation_line("[2] https://shop.co.th/ps5 - ร้านเกมไทย PS5")
        self.assertEqual(c, {"url": "https://shop.co.th/ps5", "title": "ร้านเกมไทย PS5"})

    def test_trailing_punctuation_stripped_but_parens_kept(self):
        self.assertEqual(parse_citation_line("https://a.com/x.")["url"], "https://a.com/x")
        self.assertEqual(parse_citation_line("https://en.wikipedia.org/wiki/A_(b)")["url"],
                         "https://en.wikipedia.org/wiki/A_(b)")

    def test_http_scheme(self):
        self.assertEqual(parse_citation_line("http://a.com")["url"], "http://a.com")

    def test_non_citation_lines(self):
        for line in ("ร้านแนะนำคือ https://a.com", "[1] ร้าน A", "", "hello", "1. PS5 ราคาดี", "ftp://a.com"):
            self.assertIsNone(parse_citation_line(line), line)

    def test_split_answer_dedupes(self):
        text, cites = split_answer(["ร้าน A ดีที่สุด", "", "[1] https://a.com", "[2] https://b.com Title B",
                                    "https://a.com"])
        self.assertEqual(text, "ร้าน A ดีที่สุด")
        self.assertEqual([c["url"] for c in cites], ["https://a.com", "https://b.com"])
        self.assertEqual(cites[1]["title"], "Title B")


class QuerySubsetTests(unittest.TestCase):
    def test_all(self):
        for spec in (None, "", "all", " ALL "):
            self.assertEqual(parse_query_subset(spec, 4), [0, 1, 2, 3])

    def test_list_and_ranges(self):
        self.assertEqual(parse_query_subset("1,3,5", 10), [0, 2, 4])
        self.assertEqual(parse_query_subset("5-7, 1", 10), [0, 4, 5, 6])
        self.assertEqual(parse_query_subset("3,3,2-3,", 5), [1, 2])

    def test_errors(self):
        for spec in ("0", "11", "a", "3-1", "1-11", ",", "1;2"):
            with self.assertRaises(ValueError, msg=spec):
                parse_query_subset(spec, 10)


class ReadBlockTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(read_block(io.StringIO("a\nb\nEND\nrest\n")), (["a", "b"], "ok", ""))
        self.assertEqual(read_block(io.StringIO("SKIP\n"))[1], "skip")
        self.assertEqual(read_block(io.StringIO("BLOCKED captcha on chatgpt\n")), ([], "blocked", "captcha on chatgpt"))
        self.assertEqual(read_block(io.StringIO(""))[1], "eof")


class ManualCliTests(unittest.TestCase):
    def run_manual(self, argv, stdin):
        with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(io.StringIO()):
            manual.main(argv)

    def test_records_and_resume(self):
        cfg = os.path.join(ROOT, "config.example.json")
        with tempfile.TemporaryDirectory() as d:
            base = ["--config", cfg, "--provider", "perplexity", "--session", "2026-10-13", "--out", d,
                    "--queries", "1,3", "--repeat", "2", "--who", "TN", "--note", "incognito, Bangkok"]
            self.run_manual(base, "answer one\n[1] https://a.com A\nEND\nSKIP\n")
            path = os.path.join(d, "2026-10-13_perplexity_app_manual.jsonl")
            recs = load_jsonl(path)
            self.assertEqual(len(recs), 1)
            r = recs[0]
            self.assertEqual((r["provider"], r["mode"], r["query_id"], r["repeat"]), ("perplexity_app", "manual", 0, 2))
            self.assertEqual((r["collector"], r["session_note"]), ("TN", "incognito, Bangkok"))
            self.assertEqual(r["citations"], [{"url": "https://a.com", "title": "A"}])
            self.assertEqual(r["answer"], "answer one")
            # resume: Q1 already done, so only Q3 is asked; BLOCKED writes an error record and stops
            self.run_manual(base, "BLOCKED login wall\n")
            recs = load_jsonl(path)
            self.assertEqual(len(recs), 2)
            self.assertEqual(recs[1]["query_id"], 2)
            self.assertTrue(recs[1]["error"].startswith("blocked"))

    def test_provider_choices(self):
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                manual.build_parser().parse_args(["--provider", "bing"])


class RunsheetTests(unittest.TestCase):
    def test_rows_and_csv(self):
        rows = runsheet.build_rows(["q a", "q|b"], ["perplexity", "chatgpt"], 2)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0], {"engine": "perplexity", "repeat": 0, "q_no": 1, "query": "q a"})
        parsed = list(csv.DictReader(io.StringIO(runsheet.render_csv(rows))))
        self.assertEqual(len(parsed), 8)
        self.assertEqual(parsed[1]["query"], "q|b")
        md = runsheet.render_markdown(rows, ["perplexity", "chatgpt"], 2, ["q a", "q|b"], "x.json")
        self.assertIn("q\\|b", md)
        self.assertEqual(sum(l.startswith("| ☐ |") for l in md.splitlines()), 8)

    def test_engines(self):
        self.assertEqual(runsheet.parse_engines("all"), list(manual.PROVIDERS))
        self.assertEqual(runsheet.parse_engines("chatgpt, aimode,chatgpt"), ["chatgpt", "aimode"])
        with self.assertRaises(ValueError):
            runsheet.parse_engines("bing")

    def test_main_writes_files_with_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            prefix = os.path.join(d, "sub", "rs")
            cwd = os.getcwd()
            os.chdir(ROOT)  # no config.json in repo -> falls back to config.example.json
            try:
                with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                    runsheet.main(["--repeats", "2", "--engines", "aimode", "--queries", "1-3", "--out", prefix])
            finally:
                os.chdir(cwd)
            with open(prefix + ".csv", encoding="utf-8-sig") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 6)
            self.assertTrue(os.path.exists(prefix + ".md"))


if __name__ == "__main__":
    unittest.main()
