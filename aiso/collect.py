"""เก็บข้อมูล: ยิง query เข้า AI search แล้วบันทึกผลดิบเป็น JSONL

  python -m aiso.collect --smoke                       # เช็กว่า key ใช้ได้ (1 request)
  python -m aiso.collect --mode fixed --repeats 10     # Day 1: baseline
  python -m aiso.collect --mode adaptive               # Day 1: ประหยัด request
  python -m aiso.collect --provider mock ...           # ทดลองฟรี ไม่ต้องมี key

Every response is appended to disk immediately, so a crash loses nothing.
"""
import argparse
import datetime as dt
import json
import os
import time
import uuid

from .entities import load_config
from .extract import extract
from .providers import DEFAULT_GEMINI_MODEL, ProviderError, build_provider
from .stats import half_width, wilson


def now_iso():
    return dt.datetime.now().isoformat(timespec="seconds")


class RateLimiter:
    def __init__(self, rpm):
        self.gap = 60.0 / rpm if rpm > 0 else 0
        self.last = 0.0

    def wait(self):
        delta = time.monotonic() - self.last
        if delta < self.gap:
            time.sleep(self.gap - delta)
        self.last = time.monotonic()


class Budget:
    def __init__(self, max_requests):
        self.max = max_requests
        self.used = 0

    def take(self):
        if self.used >= self.max:
            return False
        self.used += 1
        return True


def ask_with_retry(provider, query, limiter, budget, attempts=4):
    """Returns (result | None, error | None). Raises SystemExit on non-retryable errors."""
    last_err = None
    for i in range(attempts):
        if not budget.take():
            return None, "budget_exhausted"
        limiter.wait()
        t0 = time.monotonic()
        try:
            res = provider.ask(query)
            res["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return res, None
        except ProviderError as e:
            last_err = str(e)
            if e.fatal:
                raise SystemExit(f"\nหยุด: {e}\nไม่ข้าม login/CAPTCHA ตามขอบเขตโปรเจกต์ — ข้อมูลที่ได้บันทึกไว้แล้ว")
            if e.status in (400, 401, 403, 404):
                raise SystemExit(f"\nหยุด: error ที่ retry ไม่ช่วย\n{e}\n"
                                 "ตรวจ key / ชื่อโมเดล (--model) / ว่าเปิดใช้ Gemini API แล้ว")
            # Two kinds of 429: "too fast" (wait and retry helps) vs "quota" (it never will).
            if e.status == 429 and "exceeded your current quota" in str(e):
                raise SystemExit(f"\nหยุด: quota หมด/ไม่มี quota สำหรับโมเดลหรือฟีเจอร์นี้ (retry ไม่ช่วย)\n{e}\n"
                                 "ถ้าใช้ google_search ใน free tier ไม่ได้ ลอง --no-search หรือเปิด billing")
            print(f"    ! {str(e)[:120]}")
            if i < attempts - 1:  # only say "retrying" if another attempt will really run
                wait = e.retry_after or min(60, 5 * (2 ** i))
                print(f"      -> รอ {wait:.0f}s แล้วลองใหม่")
                time.sleep(wait)
    return None, last_err


def should_stop(indicators, n, min_r, max_r, margin, rule="decision", threshold=0.5):
    """Adaptive stopping rule (heuristic — validate it against a fixed run; that IS the research).

    rule="decision" (default): stop when, for every tracked business, the 95% CI lies fully
        above or fully below `threshold`, i.e. we already know if it is "usually mentioned".
        Unanimous results stop after ~4-5 repeats; borderline ones run to max.
    rule="ci": stop when every business's CI half-width <= margin (needs many more repeats)."""
    if n < min_r:
        return False
    if n >= max_r:
        return True
    for ks in indicators.values():
        k = sum(ks)
        if rule == "ci":
            if 0 < k < n and half_width(k, n) > margin:
                return False
        else:
            _, lo, hi = wilson(k, n)
            if lo <= threshold <= hi:
                return False
    return True


def main():
    ap = argparse.ArgumentParser(description="AI Search Observability — collector")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--provider", default="gemini", help="gemini | mock | perplexity_web")
    ap.add_argument("--model", default=None, help=f"default {DEFAULT_GEMINI_MODEL} (เช็กชื่อล่าสุดใน Google AI Studio)")
    ap.add_argument("--no-search", action="store_true",
                    help="gemini: ไม่ใช้ Google Search grounding (บันทึกเป็น provider gemini_nosearch)")
    ap.add_argument("--mode", choices=["fixed", "adaptive"], default="fixed")
    ap.add_argument("--repeats", type=int, default=10, help="fixed mode: รอบต่อ query")
    ap.add_argument("--min", dest="min_r", type=int, default=3, help="adaptive: รอบขั้นต่ำ")
    ap.add_argument("--max", dest="max_r", type=int, default=10, help="adaptive: รอบสูงสุด")
    ap.add_argument("--stop-rule", choices=["decision", "ci"], default="decision",
                    help="adaptive: decision=หยุดเมื่อรู้ว่าติด/ไม่ติด, ci=หยุดเมื่อ CI แคบพอ")
    ap.add_argument("--threshold", type=float, default=0.5, help="adaptive decision: เส้นแบ่ง 'ติดเป็นปกติ'")
    ap.add_argument("--margin", type=float, default=0.2, help="adaptive ci: CI half-width ที่ยอมรับได้")
    ap.add_argument("--focus", choices=["all", "target"], default="all",
                    help="adaptive: ตัดสินใจหยุดจากร้านทุกร้าน หรือเฉพาะร้านเป้าหมาย")
    ap.add_argument("--rpm", type=float, default=8, help="requests ต่อนาที (กันชน free tier)")
    ap.add_argument("--max-requests", type=int, default=150, help="เพดาน request ต่อการรัน 1 ครั้ง")
    ap.add_argument("--limit-queries", type=int, default=0, help="ใช้แค่ N query แรก (0 = ทั้งหมด)")
    ap.add_argument("--session", default=dt.date.today().isoformat(), help="ป้ายวัน ใช้แยก variance รายวัน")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--smoke", action="store_true", help="ยิง 1 ครั้ง แสดงผล แล้วจบ")
    args = ap.parse_args()

    cfg, entities, queries = load_config(args.config)
    if args.limit_queries:
        queries = queries[: args.limit_queries]
    provider = build_provider(args.provider, entities, args.model, search=not args.no_search)
    limiter, budget = RateLimiter(args.rpm), Budget(1 if args.smoke else args.max_requests)

    if args.smoke:
        res, err = ask_with_retry(provider, queries[0], limiter, budget, attempts=1)
        if hasattr(provider, "close"):
            provider.close()
        if err:
            raise SystemExit(f"ล้มเหลว: {err}")
        print(f"\nQuery: {queries[0]}\n\n--- คำตอบ ---\n{res['answer']}\n")
        print(f"--- citations ({len(res['citations'])}) ---")
        for c in res["citations"]:
            print(f"  {c['title']}  {c['url'][:80]}")
        print(f"\nsearch queries ที่ AI ใช้: {res.get('search_queries')}")
        print(f"tokens: {res.get('usage')}\n\nใช้ได้แล้ว ✓ ไปต่อ README ข้อ 4")
        return

    os.makedirs(args.out, exist_ok=True)
    stamp = dt.datetime.now().strftime("%H%M%S")
    path = os.path.join(args.out, f"{args.session}_{provider.name}_{args.mode}_{stamp}.jsonl")
    run_id = uuid.uuid4().hex[:8]
    plan = args.repeats if args.mode == "fixed" else f"{args.min_r}-{args.max_r} ({args.stop_rule}, focus={args.focus})"
    print(f"run {run_id}: {len(queries)} queries × {plan} รอบ | rpm={args.rpm} | เพดาน {args.max_requests}")
    print(f"บันทึกที่ {path}\n")

    stats = {"ok": 0, "err": 0}
    per_query_n = {}
    with open(path, "a", encoding="utf-8") as f:
        for qi, q in enumerate(queries):
            indicators = {e.name: [] for e in entities}
            n = 0
            target_n = args.repeats if args.mode == "fixed" else args.max_r
            while n < target_n:
                watch = indicators if args.focus == "all" else {entities[0].name: indicators[entities[0].name]}
                # Decide on successful observations only: a failed request is not a "not mentioned".
                ok_n = len(indicators[entities[0].name])
                if args.mode == "adaptive" and should_stop(watch, ok_n, args.min_r, args.max_r, args.margin,
                                                         args.stop_rule, args.threshold):
                    break
                res, err = ask_with_retry(provider, q, limiter, budget)
                if err == "budget_exhausted":
                    print(f"\nถึงเพดาน {args.max_requests} requests แล้ว หยุดก่อน (ข้อมูลที่ได้บันทึกไว้แล้ว)")
                    break
                rec = {"record_id": uuid.uuid4().hex[:12], "run_id": run_id, "session": args.session,
                       "ts": now_iso(), "provider": provider.name, "mode": args.mode,
                       "query_id": qi, "query": q, "repeat": n}
                if err:
                    rec["error"] = err
                    stats["err"] += 1
                else:
                    rec.update(res)
                    stats["ok"] += 1
                    for name, flags in extract(rec, entities).items():
                        indicators[name].append(1 if flags["mentioned"] else 0)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                n += 1
            per_query_n[qi] = n
            tgt = entities[0].name
            k = sum(indicators[tgt])
            m = len(indicators[tgt])
            print(f"[{qi + 1}/{len(queries)}] {n} รอบ | {tgt}: {k}/{m} | {q}")
            if budget.used >= budget.max:
                break

    if hasattr(provider, "close"):
        provider.close()
    total = sum(per_query_n.values())
    print(f"\nเสร็จ: สำเร็จ {stats['ok']} | error {stats['err']} | ใช้ {budget.used} requests")
    if args.mode == "adaptive" and per_query_n:
        fixed_equiv = args.max_r * len(per_query_n)
        print(f"adaptive ใช้ {total} รอบ เทียบ fixed {fixed_equiv} รอบ "
              f"(ประหยัด {100 * (1 - total / fixed_equiv):.0f}%)")
    print("ต่อไป: python -m aiso.report")


if __name__ == "__main__":
    main()
