"""ตัวเก็บข้อมูลจากหน้าเว็บ AI search ฟรี ผ่าน Playwright (เบราว์เซอร์จริง)
Browser adapters for the free web versions. Same return shape as providers.py:
{answer, citations[{url,title}], usage, model, search_queries}

Rules (proposal section 4): low volume, fresh logged-out context per query,
never bypass a CAPTCHA or login wall. If one appears we stop and collect that engine
by hand instead (python -m aiso.manual).

Needs:  uv pip install playwright && python -m playwright install chromium
"""
import time
from urllib.parse import urlparse

from .providers import Provider, ProviderError

LOGIN_WALL = ["Sign up and repeat your request", "ลงทะเบียนและส่งคำขอของคุณอีกครั้ง"]
CHALLENGE = ["Just a moment", "Verify you are human", "captcha"]


class PerplexityWeb(Provider):
    """perplexity.ai, logged out. Types the query into the home-page box like a person would
    (the ?q= deep link is login-walled for logged-out users)."""

    name = "perplexity_web"
    HOME = "https://www.perplexity.ai/"

    def __init__(self, headless=False, timeout=120, locale="th-TH"):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SystemExit("ต้องติดตั้ง playwright ก่อน:\n"
                             "  uv pip install playwright && python -m playwright install chromium")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self.timeout = timeout
        self.locale = locale

    def close(self):
        self._browser.close()
        self._pw.stop()

    def ask(self, query):
        ctx = self._browser.new_context(locale=self.locale)  # fresh cookies every query
        try:
            pg = ctx.new_page()
            pg.goto(self.HOME, timeout=60000)
            self._check_blocked(pg)
            pg.wait_for_selector("#ask-input", timeout=30000)
            pg.click("#ask-input")
            pg.keyboard.type(query, delay=30)
            pg.keyboard.press("Enter")
            answer, cites = self._wait_answer(pg)
        except ProviderError:
            raise
        except Exception as e:  # layout change, timeout, network
            raise ProviderError(f"perplexity_web: {type(e).__name__}: {str(e)[:200]}")
        finally:
            ctx.close()
        return {"answer": answer, "citations": cites, "usage": {},
                "model": "perplexity-web-free", "search_queries": []}

    def _check_blocked(self, pg):
        title = (pg.title() or "").lower()
        if any(c.lower() in title for c in CHALLENGE):
            raise ProviderError("perplexity_web: bot challenge shown — not bypassing; collect manually",
                                fatal=True)

    def _read(self, pg):
        # Main answer = the longest .prose block; read only that, never the whole page
        # (the sidebar can show unrelated history).
        return pg.evaluate("""() => {
          const ps = [...document.querySelectorAll('.prose')];
          if (!ps.length) return {text: '', links: []};
          const main = ps.reduce((a, b) => (b.innerText.length > a.innerText.length ? b : a));
          const scope = main.closest('main') || document;
          const links = [...main.querySelectorAll('a[href^="http"]'), ...scope.querySelectorAll('a.inline-flex[href^="http"]')]
            .map(a => a.href).filter(h => !h.includes('perplexity.ai'));
          return {text: main.innerText, links: [...new Set(links)]};
        }""")

    def _wait_answer(self, pg):
        deadline = time.monotonic() + self.timeout
        last, stable, got = -1, 0, {"text": "", "links": []}
        while time.monotonic() < deadline:
            time.sleep(1)
            try:
                got = self._read(pg)
            except Exception:  # page navigated mid-read; try again
                continue
            if any(w in got["text"] for w in LOGIN_WALL):
                raise ProviderError("perplexity_web: login wall — not bypassing; collect manually", fatal=True)
            n = len(got["text"])
            stable = stable + 1 if n == last else 0
            last = n
            if n > 200 and stable >= 5:  # streaming finished
                break
        else:
            raise ProviderError("perplexity_web: answer did not finish in time")
        cites = [{"url": h, "title": urlparse(h).netloc} for h in got["links"]]
        return got["text"], cites


STUBS = {
    "gemini_web": "ต้อง login Google; ใช้ Gemini API เป็นตัวแทนไปก่อน",
    "chatgpt_web": "มีหน้า login/challenge บ่อย และต้องตรวจ ToS ก่อน",
    "aimode_web": "Google Search มี bot detection และ ToS ห้าม automated queries",
}


def manual_only(name):
    """Engines we do not automate yet: tell the user how to collect them by hand."""
    raise SystemExit(f"{name}: ยังไม่ทำ automation ({STUBS[name]})\n"
                     f"เก็บด้วยมือแทน:  python -m aiso.manual --provider {name.replace('_web', '')}")
