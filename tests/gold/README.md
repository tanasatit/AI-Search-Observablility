# Gold corpus for the mentioned / cited / recommended counters

`cases.jsonl` — one JSON object per line, 209 synthetic AI-search answers (Thai, English, mixed). No network, no API
key. Entities are the ones in `config.example.json` (target `บ้านสวนคาเฟ่`; competitors Bean Lab, Work & Brew,
นั่งชิลล์คอฟฟี่, Slow Drip Studio). The answers are written to look like Gemini / Perplexity output, they are not
real model output.

```json
{"id": "g001", "split": "dev", "category": "basic", "lang": "th", "query": "...",
 "answer": "text exactly as a provider would return it (markdown, source-chip lines, ...)",
 "citations": [{"url": "https://vertexaisearch.cloud.google.com/...", "title": "beanlab.co"}],
 "gold": {"mentioned": ["Bean Lab"], "cited": ["Bean Lab"], "recommended": ["Bean Lab"]},
 "unknown_names": ["Rocket Coffee Bar"]}
```

## What the gold labels mean (decide once, apply the same way)

| label | true when | false when |
|---|---|---|
| `mentioned` | the business is named in the answer prose (any listed name/alias or an obvious spelling variant) | only a source-chip line (`beanlab.co`, `+2`) or only the citation list names it; a *different* business with a similar name ("Bean Labs", "Network Brewery") |
| `cited` | a citation is the business's own site or page: its domain in the url/title, or a page about it (Facebook, Wongnai, Maps) whose title/url names it | a listicle/other site that does not name it; a look-alike domain (`notbeanlab.co`, `beanlab.com`) |
| `recommended` | the answer endorses it: a recommending word in the same clause, a list item under a recommending heading ("แนะนำ 3 ร้าน:", "Top picks:"), the better side of "A better than B", a pronoun follow-up ("... I recommend it") | merely listed or described ("also nearby", "opens at 8"), praise without a verdict, negated ("not recommended", "ไม่เหมาะ"), the worse side of a comparison, uncertainty ("unclear whether ...") |

`recommended` must also be `mentioned`. A numbered list with a neutral heading ("Cafes near Asok:") is **not**
recommended; this is a definition choice. Change it in the README of the project report if the team decides otherwise,
and relabel the `structure` cases.

## Splits

* `dev` / `test` — written first, before any tuning. The author saw every failure of the original extractor on both, so
  `test` is *not* blind.
* `holdout` — 42 cases written afterwards with new phrasings. Its first run on the then-current rules is the nearest
  thing to an out-of-sample estimate (see the PR description for those numbers). Fixes made after that run are
  tuned on it too, so use new cases for a fresh check.

## Adding a case

1. Append one line to `cases.jsonl` (next free `id`). Label by hand from the table above, **before** running the
   benchmark.
2. Use `split: "holdout"` for cases you add to check the rules, `dev` for cases you add to drive a fix.
3. `python -m aiso.benchmark --errors` shows what the extractor gets wrong; `python -m unittest discover -s tests`
   checks the corpus is consistent and that precision/recall floors still hold.
4. If you fix a rule, add a regression test to `tests/test_extract_rules.py`.

Cases tagged as known limits (`g042`, `g061`, `g066`, `h003`, `h033`, `h035`) are kept on purpose: they are the
failures rules cannot fix without a model or per-business aliases.
