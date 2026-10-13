"""เก็บคำตอบจากหน้าเว็บ/แอปจริงด้วยมือ (manual collection) เพื่อเทียบกับ API

  python -m aiso.manual --provider perplexity --repeat 0 --who TN --note "Chrome incognito, logged-out, Bangkok"
  python -m aiso.manual --provider chatgpt --queries 1,3,5-7 --repeat 1 --who PK

For each query: open the engine (see docs/run-sheet.md), ask the exact query, copy the answer,
paste it here, then type END on its own line.
  - Lines that are a URL are saved as citations. Accepted forms:
        https://example.com/page
        [1] https://example.com/page
        [1]: https://example.com/page   1. https://example.com   (2) https://example.com
    Text after the URL on the same line is kept as the citation title.
  - Type SKIP to skip a query (nothing is saved).
  - Type BLOCKED (optionally followed by a note) if you hit a login wall / CAPTCHA.
    It is saved as an error record and the session stops. Never try to bypass it.

Output: data/raw/<session>_<provider>_app_manual.jsonl (append). Records already collected in
that file for the same query + repeat are skipped unless --redo is given, so you can stop and resume.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import uuid

from .entities import load_config

PROVIDERS = ("gemini", "chatgpt", "perplexity", "aimode")

# optional marker "[1]", "[1]:", "1.", "1)", "(1)", "-", "*", then the URL, then an optional title
CITE_RE = re.compile(
    r"^\s*(?:\[\d+\]\s*:?|\(\d+\)|\d+[.)]|[-*•])?\s*<?(https?://[^\s<>]+?)>?[.,;]*(?:\s+[-–—|:]?\s*(.*?))?\s*$"
)


def parse_citation_line(line):
    """Return {"url", "title"} if the line is a citation line, else None."""
    m = CITE_RE.match(line or "")
    if not m:
        return None
    url = m.group(1)
    title = (m.group(2) or "").strip() or url
    return {"url": url, "title": title}


def split_answer(lines):
    """Split a pasted block into (answer_text, citations). Citations are de-duplicated by URL."""
    text_lines, cites, seen = [], [], set()
    for line in lines:
        c = parse_citation_line(line)
        if c is None:
            text_lines.append(line)
        elif c["url"] not in seen:
            seen.add(c["url"])
            cites.append(c)
    return "\n".join(text_lines).strip("\n"), cites


def parse_query_subset(spec, n):
    """'1,3,5-7' (1-based, as printed on the run sheet) -> sorted 0-based indices.
    Empty/None/'all' -> all n queries."""
    if spec is None or not str(spec).strip() or str(spec).strip().lower() == "all":
        return list(range(n))
    out = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                raise ValueError(f"ช่วงไม่ถูกต้อง: {part}")
            nums = range(a, b + 1)
        elif part.isdigit():
            nums = [int(part)]
        else:
            raise ValueError(f"อ่านเลข query ไม่ได้: {part!r} (ใช้รูปแบบ 1,3,5-7)")
        for k in nums:
            if not 1 <= k <= n:
                raise ValueError(f"query {k} อยู่นอกช่วง 1-{n}")
            out.add(k - 1)
    if not out:
        raise ValueError("ไม่ได้เลือก query เลย")
    return sorted(out)


def read_block(stream=None):
    """Read lines until END / SKIP / BLOCKED. Returns (lines, status, note)
    where status is "ok", "skip", "blocked" or "eof"."""
    stream = stream or sys.stdin
    lines = []
    for line in stream:
        s = line.rstrip("\n")
        cmd = s.strip()
        if cmd == "END":
            return lines, "ok", ""
        if cmd == "SKIP":
            return lines, "skip", ""
        if cmd.split(" ", 1)[0] == "BLOCKED":
            return lines, "blocked", cmd[len("BLOCKED"):].strip()
        lines.append(s)
    return lines, ("ok" if any(l.strip() for l in lines) else "eof"), ""


def already_done(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not r.get("error"):
                done.add((r.get("query_id"), r.get("repeat", 0)))
    return done


def make_record(args, qi, q, rep, answer, cites, error=None):
    rec = {"record_id": uuid.uuid4().hex[:12], "run_id": "manual", "session": args.session,
           "ts": dt.datetime.now().isoformat(timespec="seconds"),
           "provider": f"{args.provider}_app", "mode": "manual", "query_id": qi, "query": q,
           "repeat": rep, "answer": answer, "citations": cites,
           "collector": args.who, "session_note": args.note}
    if error:
        rec["error"] = error
    return rec


def build_parser():
    ap = argparse.ArgumentParser(description="เก็บคำตอบจาก AI engine ด้วยมือ (ดู docs/run-sheet.md)")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--provider", default="gemini", choices=PROVIDERS,
                    help="engine ที่ถามมือ (บันทึกเป็น <provider>_app)")
    ap.add_argument("--session", default=dt.date.today().isoformat())
    ap.add_argument("--repeat", type=int, default=0,
                    help="เลขรอบ (repeat) ที่กำลังเก็บ เริ่มที่ 0 ตาม run sheet")
    ap.add_argument("--rounds", type=int, default=1,
                    help="เก็บกี่รอบติดกันในครั้งนี้ (repeat, repeat+1, ...) ปกติ 1 — ควรกระจายรอบข้ามวัน")
    ap.add_argument("--queries", default=None, help="เลือกบาง query เช่น 1,3,5-7 (เลขตาม run sheet เริ่มที่ 1)")
    ap.add_argument("--who", default="", help="อักษรย่อผู้เก็บ เช่น TN")
    ap.add_argument("--note", "--session-note", dest="note", default="",
                    help="บันทึกสภาพแวดล้อม เช่น 'Chrome incognito, logged-out, Bangkok'")
    ap.add_argument("--redo", action="store_true", help="เก็บซ้ำแม้ query+repeat นี้มีในไฟล์แล้ว")
    ap.add_argument("--out", default="data/raw")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.repeat < 0 or args.rounds < 1:
        raise SystemExit("--repeat ต้อง >= 0 และ --rounds ต้อง >= 1")

    _, _, queries = load_config(args.config)
    try:
        picked = parse_query_subset(args.queries, len(queries))
    except ValueError as e:
        raise SystemExit(str(e))

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{args.session}_{args.provider}_app_manual.jsonl")
    done = set() if args.redo else already_done(path)
    todo = [(rep, qi) for rep in range(args.repeat, args.repeat + args.rounds) for qi in picked
            if (qi, rep) not in done]
    print(f"บันทึกที่ {path}")
    print(f"engine={args.provider}  ผู้เก็บ={args.who or '-'}  note={args.note or '-'}")
    if len(todo) < args.rounds * len(picked):
        print(f"ข้าม {args.rounds * len(picked) - len(todo)} รายการที่เก็บไปแล้ว (ใช้ --redo ถ้าจะเก็บซ้ำ)")
    print("วางคำตอบ + ลิงก์แหล่งที่มา แล้วพิมพ์ END  |  SKIP = ข้าม  |  BLOCKED <note> = เจอ login/CAPTCHA (หยุด)\n")

    saved = 0
    with open(path, "a", encoding="utf-8") as f:
        for i, (rep, qi) in enumerate(todo):
            q = queries[qi]
            print(f"\n=== [{i + 1}/{len(todo)}] Q{qi + 1} รอบ {rep}  ถาม: {q}")
            lines, status, note = read_block()
            if status == "eof":
                print("  จบ input")
                break
            if status == "skip":
                print("  ข้าม")
                continue
            if status == "blocked":
                rec = make_record(args, qi, q, rep, "", [], error=f"blocked: {note or 'login/captcha'}")
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print("  บันทึกว่าเจอ login/CAPTCHA แล้ว — หยุด session นี้ ห้ามพยายามเลี่ยง ดู docs/run-sheet.md")
                break
            text, cites = split_answer(lines)
            rec = make_record(args, qi, q, rep, text, cites)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            saved += 1
            print(f"  บันทึกแล้ว ({len(text)} ตัวอักษร, {len(cites)} แหล่งที่มา)")
    print(f"\nบันทึก {saved} คำตอบ  ต่อไป: python -m aiso.report")


if __name__ == "__main__":
    main()
