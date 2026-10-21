"""จับชื่อธุรกิจในคำตอบ (รองรับไทย/อังกฤษ)
Entity resolution: normalize names, find mentions, check citations, discover unknown names.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")
PUNCT = re.compile(r"[\s\-_.,:;!?'\"“”‘’()\[\]{}/\\|*#@&+–—]+")


def norm(s: str) -> str:
    """lowercase, drop spaces/punctuation/zero-width chars. 'Baan Suan Café' -> 'baansuancafé'"""
    s = unicodedata.normalize("NFC", s or "")
    s = ZERO_WIDTH.sub("", s).lower()
    return PUNCT.sub("", s)


# ตัวอักษรไทยที่เป็นแค่ "เครื่องหมาย": ไม้ไต่คู้ วรรณยุกต์ ทัณฑฆาต ฯลฯ (คนสะกดตกหล่นบ่อย: คาเฟ่/คาเฟ, แล็บ/แลบ)
TH_MARKS = "\u0e47-\u0e4e"
TH_RANGE = re.compile("[\u0e00-\u0e7f]")
SEP = r"[\s\-_.,:;!?'\"“”‘’()\[\]{}/\\|*#@&+–—]*"
LATIN = "a-z0-9\u00c0-\u024f"


def clean(text: str) -> str:
    """NFC + drop zero-width chars + curly apostrophe -> ' (ความยาวคงที่ต่อตัวอักษร เพื่อให้ offset ใช้ต่อได้)"""
    return ZERO_WIDTH.sub("", unicodedata.normalize("NFC", text or "")).replace("’", "'")


def _alias_pattern(alias):
    """Latin alias -> match whole words only ("Bean Lab" is not inside "Bean Labs" or "Green Bean Laboratory",
    "Work & Brew" is not inside "Network Brewery"); spaces/punctuation between words are optional.
    Thai alias (no word boundaries in Thai) -> substring, ignoring spaces, tone marks and thanthakhat."""
    if len(norm(alias)) < 2:
        return None
    if TH_RANGE.search(alias):
        chars = [c for c in norm(alias) if not "\u0e47" <= c <= "\u0e4e"]
        marks = "[" + TH_MARKS + "]*"
        body = (marks + SEP).join(re.escape(c) for c in chars) + marks
        return re.compile(body, re.I)
    words = re.findall(r"[^\W_]+", alias)
    return re.compile(f"(?<![{LATIN}])" + SEP.join(re.escape(w) for w in words) + f"(?![{LATIN}])", re.I)


@dataclass
class Entity:
    name: str
    role: str  # "target" | "competitor"
    aliases: list = field(default_factory=list)
    domains: list = field(default_factory=list)
    _cache: tuple = field(default=None, init=False, repr=False, compare=False)

    def keys(self):
        ks = {norm(x) for x in [self.name, *self.aliases]}
        return {k for k in ks if len(k) >= 2}

    def patterns(self):
        sig = (self.name, *self.aliases)
        if self._cache is None or self._cache[0] != sig:
            pats = [_alias_pattern(a) for a in sig]
            self._cache = (sig, [p for p in pats if p])
        return self._cache[1]

    def spans(self, text):
        """[(start, end)] of every mention in `text` (pass text through clean() first for stable offsets)"""
        return sorted(m.span() for p in self.patterns() for m in p.finditer(text or ""))


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    ents = [Entity(cfg["target"]["name"], "target",
                   cfg["target"].get("aliases", []), cfg["target"].get("domains", []))]
    for c in cfg.get("competitors", []):
        ents.append(Entity(c["name"], "competitor", c.get("aliases", []), c.get("domains", [])))
    queries = cfg["queries"]
    if not queries:
        raise SystemExit("config ไม่มี queries")
    return cfg, ents, queries


def find_mentions(text, entities):
    t = clean(text)
    return {e.name for e in entities if e.spans(t)}


def entity_in(text, entity):
    return bool(entity.spans(clean(text)))


DOMAIN_TITLE = re.compile(r"^(?:https?://)?(?:www\.)?([\w-]+(?:\.[\w-]+)+)(?:\s*[›»/].*)?$")


def _domain_in(domain, blob):
    """domain must start at a label boundary and not run on into another label:
    'beanlab.co' matches 'www.beanlab.co/menu' but not 'notbeanlab.co' or 'beanlab.com'"""
    return re.search(f"(?<![a-z0-9-]){re.escape(domain.lower())}(?![a-z0-9-])", blob) is not None


def entity_cited(entity, citations):
    """A citation counts when it is the entity's own site/page: its domain appears in the url or title, or its
    title / url path names the entity (a Facebook, Wongnai or Maps page). A domain-only title (Gemini redirects)
    is matched on the domain alone, unless the entity has no domains configured."""
    doms = [d for d in entity.domains if d]
    for c in citations or []:
        url, title = unquote(c.get("url", "") or ""), clean(c.get("title", "") or "")
        if any(_domain_in(d, f"{url} {title}".lower()) for d in doms):
            return True
        dt = DOMAIN_TITLE.match(title.strip())
        if dt:
            if not doms and dt.group(1).split(".")[0].lower().replace("-", "") in entity.keys():
                return True
        elif entity.spans(title):
            return True
        u = urlparse(url)
        if entity.spans(clean(u.path + " " + u.query)):
            return True
    return False


LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$", re.M)
BOLD = re.compile(r"\*\*(.+?)\*\*")
SPLIT_AT = re.compile(r"\s+[–—\-:]\s+|[:(（]")


def discover_names(text):
    """Pull candidate business names from bold text and list items,
    so you can spot competitors you haven't added to config yet.
    Returns {normalized: display}. Noisy by design: a human reviews it."""
    found = {}
    for m in BOLD.finditer(text or ""):
        name = m.group(1).strip()
        if 1 < len(name) <= 40:
            found.setdefault(norm(name), name)
    for m in LIST_ITEM.finditer(text or ""):
        head = SPLIT_AT.split(m.group(1).replace("**", ""), maxsplit=1)[0].strip()
        if 1 < len(head) <= 40:
            found.setdefault(norm(head), head)
    return {k: v for k, v in found.items() if k}
