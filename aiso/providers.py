"""ตัวเชื่อมต่อกับ AI search แต่ละเจ้า
Provider adapters. Each returns: {answer, citations[{url,title}], usage, model, search_queries}
Zero dependencies (stdlib urllib only).
"""
import hashlib
import json
import os
import random
import urllib.error
import urllib.request


class ProviderError(Exception):
    def __init__(self, msg, retry_after=None, status=None, fatal=False):
        super().__init__(msg)
        self.retry_after = retry_after
        self.status = status
        self.fatal = fatal  # login wall / CAPTCHA: stop, never retry or bypass


class Provider:
    name = "base"

    def ask(self, query: str) -> dict:
        raise NotImplementedError


DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


class GeminiProvider(Provider):
    """Gemini, with Google Search grounding by default.
    search=False omits the google_search tool (works on the free tier) and records the
    provider as "gemini_nosearch", so the two kinds of data never mix in reports.
    The key is read from the GEMINI_API_KEY environment variable and is never printed or saved."""

    name = "gemini"
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, model=DEFAULT_GEMINI_MODEL, timeout=240, search=True):
        self.key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not self.key:
            raise SystemExit(
                "ไม่พบ GEMINI_API_KEY\n"
                "  macOS/Linux:  export GEMINI_API_KEY=...\n"
                "  Windows:      $env:GEMINI_API_KEY=\"...\"\n"
                "(ดู README ข้อ 2)"
            )
        self.model = model
        self.timeout = timeout
        self.search = search
        if not search:
            self.name = "gemini_nosearch"

    def ask(self, query):
        body = {"contents": [{"role": "user", "parts": [{"text": query}]}]}
        if self.search:
            body["tools"] = [{"google_search": {}}]
        req = urllib.request.Request(
            self.ENDPOINT.format(model=self.model),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:600]
            ra = e.headers.get("Retry-After")
            try:
                ra = float(ra) if ra else None
            except ValueError:
                ra = None
            raise ProviderError(f"HTTP {e.code}: {detail}", retry_after=ra, status=e.code)
        except urllib.error.URLError as e:
            raise ProviderError(f"network error: {e.reason}")
        except TimeoutError:
            raise ProviderError("timeout")
        return self._parse(data)

    def _parse(self, data):
        cands = data.get("candidates") or []
        if not cands:
            raise ProviderError(f"no candidates in response: {json.dumps(data, ensure_ascii=False)[:400]}")
        c = cands[0]
        parts = (c.get("content") or {}).get("parts") or []
        # Newer models also return "thinking" parts (thought: true); they are not the answer.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        gm = c.get("groundingMetadata") or {}
        cites = []
        for ch in gm.get("groundingChunks") or []:
            w = ch.get("web") or {}
            if w.get("uri") or w.get("title"):
                # Note: uri is often a Google redirect link; title usually holds the domain.
                cites.append({"url": w.get("uri", ""), "title": w.get("title", "")})
        return {
            "answer": text,
            "citations": cites,
            "usage": data.get("usageMetadata", {}),
            "model": self.model,
            "search_queries": gm.get("webSearchQueries", []),
        }


class MockProvider(Provider):
    """Fake provider for trying the whole pipeline without a key or cost.
    Has a stable 'core' of businesses plus random noise, like a real AI search."""

    name = "mock"
    EXTRA = ["กาแฟดีอโศก", "Corner Brew", "ร้านลมเย็น", "Daily Grind BKK"]
    REASONS = ["เหมาะกับการนั่งทำงาน มีปลั๊กเยอะ", "บรรยากาศเงียบ", "เปิดถึงดึก",
               "ราคาไม่แพง", "มีห้องประชุมเล็ก", "กาแฟคุณภาพดี"]

    def __init__(self, entities):
        self.names = [e.name for e in entities]
        self.target = next((e for e in entities if e.role == "target"), None)
        self.domains = {e.name: (e.domains[0] if e.domains else "") for e in entities}
        self.counter = 0

    def ask(self, query):
        self.counter += 1
        seed = int(hashlib.md5(f"{query}|{self.counter}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        picks = []
        for n in self.names + self.EXTRA:
            # per (query, business) "true" probability: mostly clear in/out, some borderline
            h = int(hashlib.md5(f"{query}|{n}".encode()).hexdigest()[:4], 16) / 0xFFFF
            p = 0.92 if h < 0.35 else (0.04 if h < 0.8 else 0.5)
            if rng.random() < p:
                picks.append(n)
        rng.shuffle(picks)
        lines = [f"สำหรับ \"{query}\" มีร้านที่น่าสนใจดังนี้:", ""]
        cites = []
        for i, n in enumerate(picks[:5], 1):
            lines.append(f"{i}. **{n}** – {rng.choice(self.REASONS)}")
            d = self.domains.get(n) or ""
            if d and rng.random() < 0.5:
                cites.append({"url": f"https://{d}/", "title": d})
        lines += ["", "ถ้าเน้นเงียบที่สุด แนะนำ " + (picks[0] if picks else "-") + " ครับ"]
        cites.append({"url": "https://www.wongnai.com/x", "title": "wongnai.com"})
        return {"answer": "\n".join(lines), "citations": cites, "usage": {},
                "model": "mock", "search_queries": [query]}


def build_provider(name, entities, model=None, search=True):
    if name == "gemini":
        return GeminiProvider(model=model or DEFAULT_GEMINI_MODEL, search=search)
    if name == "mock":
        return MockProvider(entities)
    if name == "perplexity_web":
        from .web import PerplexityWeb
        return PerplexityWeb()
    if name in ("gemini_web", "chatgpt_web", "aimode_web"):
        from .web import manual_only
        manual_only(name)
    raise SystemExit(f"unknown provider: {name} "
                     "(ใช้ได้: gemini, mock, perplexity_web | stub: gemini_web, chatgpt_web, aimode_web)")
