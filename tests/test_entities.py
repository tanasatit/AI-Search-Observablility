import json
import os
import tempfile
import unittest

from _support import EXAMPLE_CONFIG, shop_entities
from aiso.entities import (Entity, discover_names, entity_cited, entity_in, find_mentions,
                           load_config, norm)


class NormTest(unittest.TestCase):
    def test_english(self):
        self.assertEqual(norm("Art & Gun  Game!"), "artgungame")
        self.assertEqual(norm("Power-Buy (Central)"), "powerbuycentral")

    def test_thai_keeps_letters_and_marks(self):
        self.assertEqual(norm("พาวเวอร์ บาย"), "พาวเวอร์บาย")
        self.assertEqual(norm("ร้าน “เกมเมอร์โซน”"), "ร้านเกมเมอร์โซน")

    def test_zero_width_chars_removed(self):
        self.assertEqual(norm("Power​Buy"), "powerbuy")
        self.assertEqual(norm("พาวเวอร์‌บาย﻿"), "พาวเวอร์บาย")

    def test_unicode_normalized(self):
        self.assertEqual(norm("Café"), norm("Café"))

    def test_none_and_empty(self):
        self.assertEqual(norm(None), "")
        self.assertEqual(norm(" - . "), "")

    def test_entity_keys_drop_too_short(self):
        e = Entity("Power Buy", "target", ["P", "", "พาวเวอร์บาย"], [])
        self.assertEqual(e.keys(), {"powerbuy", "พาวเวอร์บาย"})


class MentionTest(unittest.TestCase):
    def setUp(self):
        self.ents = shop_entities()

    def test_find_by_name_and_alias(self):
        text = "ลองไปที่ พาวเวอร์บาย หรือ Art-and-Gun Game ก็ได้"
        self.assertEqual(find_mentions(text, self.ents), {"Power Buy", "Art and Gun Game"})

    def test_case_and_spacing_insensitive(self):
        self.assertEqual(find_mentions("POWERBUY มีของ", self.ents), {"Power Buy"})
        self.assertEqual(find_mentions("ร้าน เกมเมอร์ โซน", self.ents), {"Gamer Zone"})

    def test_no_mentions(self):
        self.assertEqual(find_mentions("ไม่มีร้านไหนเลย", self.ents), set())
        self.assertEqual(find_mentions("", self.ents), set())

    def test_entity_in(self):
        self.assertTrue(entity_in("ArtandGun shop", self.ents[1]))
        self.assertFalse(entity_in("Art shop", self.ents[1]))


class CitedTest(unittest.TestCase):
    def setUp(self):
        self.power, self.art, self.zone = shop_entities()

    def test_by_domain_substring_in_url(self):
        cites = [{"url": "https://www.powerbuy.co.th/th/ps5", "title": "PS5 console"}]
        self.assertTrue(entity_cited(self.power, cites))
        self.assertFalse(entity_cited(self.art, cites))

    def test_by_domain_in_title(self):
        # Gemini: url is a redirect, title holds the domain
        cites = [{"url": "https://vertexaisearch.cloud.google.com/redirect/abc", "title": "artandgungame.com"}]
        self.assertTrue(entity_cited(self.art, cites))

    def test_by_name_in_title_without_domains(self):
        cites = [{"url": "https://facebook.com/somepage", "title": "เกมเมอร์โซน - Facebook"}]
        self.assertTrue(entity_cited(self.zone, cites))

    def test_empty(self):
        self.assertFalse(entity_cited(self.power, None))
        self.assertFalse(entity_cited(self.power, []))
        self.assertFalse(entity_cited(self.zone, [{"url": "https://x.com"}]))


class DiscoverNamesTest(unittest.TestCase):
    def test_bold_and_list_items(self):
        text = "\n".join([
            "ร้านที่น่าสนใจ:",
            "1. **Power Buy** – มี PS5 ครบ",
            "2. Gamer Zone: ราคาดี",
            "- เกมเมอร์ช็อป (สาขาสยาม)",
            "ลองดู **Neo Games** ด้วย",
            "ประโยคธรรมดาไม่ใช่รายการ",
        ])
        found = discover_names(text)
        self.assertEqual(found.get("powerbuy"), "Power Buy")
        self.assertEqual(found.get("gamerzone"), "Gamer Zone")
        self.assertEqual(found.get("เกมเมอร์ช็อป"), "เกมเมอร์ช็อป")
        self.assertEqual(found.get("neogames"), "Neo Games")
        self.assertNotIn(norm("ประโยคธรรมดาไม่ใช่รายการ"), found)

    def test_empty_and_too_long(self):
        self.assertEqual(discover_names(""), {})
        self.assertEqual(discover_names(None), {})
        self.assertEqual(discover_names("**" + "x" * 41 + "**"), {})


class LoadConfigTest(unittest.TestCase):
    def test_example_config(self):
        cfg, ents, queries = load_config(EXAMPLE_CONFIG)
        self.assertEqual(ents[0].role, "target")
        self.assertTrue(all(e.role == "competitor" for e in ents[1:]))
        self.assertEqual(len(ents), 1 + len(cfg["competitors"]))
        self.assertEqual(queries, cfg["queries"])

    def test_empty_queries_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"target": {"name": "X"}, "queries": []}, f)
            with self.assertRaises(SystemExit):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
