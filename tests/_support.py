"""Shared helpers for the test suite (stdlib only).

Importing this module makes the repo root importable, so `import aiso` works no matter
where `python -m unittest discover -s tests` is launched from.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from aiso.entities import Entity  # noqa: E402

EXAMPLE_CONFIG = os.path.join(REPO_ROOT, "config.example.json")


def shop_entities():
    """Small Thai game-console retailer fixture used by the extraction tests."""
    return [
        Entity("Power Buy", "target", ["พาวเวอร์บาย", "PowerBuy"], ["powerbuy.co.th"]),
        Entity("Art and Gun Game", "competitor", ["อาร์ตแอนด์กัน", "ArtandGun"], ["artandgungame.com"]),
        Entity("Gamer Zone", "competitor", ["เกมเมอร์โซน"], []),
    ]
