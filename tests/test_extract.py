import unittest

from _support import shop_entities
from aiso.extract import answer_text, extract, is_source_chip, sentences

CITES = [
    {"url": "https://www.powerbuy.co.th/th/ps5", "title": "PS5 | Power Buy"},
    {"url": "https://artandgungame.com/", "title": "artandgungame.com"},
]


class SourceChipTest(unittest.TestCase):
    DOMAINS = ["powerbuy.co.th", "artandgungame.com"]

    def test_chips(self):
        for line in ["powerbuy.co", "artandgungame", "  ArtAndGunGame  ", "+2", "+12"]:
            with self.subTest(line=line):
                self.assertTrue(is_source_chip(line, self.DOMAINS))

    def test_not_chips(self):
        for line in ["", "   ", "+", "+x", "powerbuy มีของ", "shopee.co.th", "1. Power Buy"]:
            with self.subTest(line=line):
                self.assertFalse(is_source_chip(line, self.DOMAINS))


class AnswerTextTest(unittest.TestCase):
    def test_strips_chips_keeps_real_lines(self):
        answer = "\n".join([
            "ร้านขายเครื่องเกมแนะนำ:",
            "Gamer Zone มี PS5 ราคาดี",
            "powerbuy.co",
            "artandgungame",
            "+2",
            "สรุป: ไปที่ Gamer Zone",
        ])
        out = answer_text({"answer": answer, "citations": CITES})
        self.assertEqual(out.split("\n"), [
            "ร้านขายเครื่องเกมแนะนำ:",
            "Gamer Zone มี PS5 ราคาดี",
            "สรุป: ไปที่ Gamer Zone",
        ])

    def test_no_citations_returns_text_unchanged(self):
        answer = "powerbuy.co\n+2"
        self.assertEqual(answer_text({"answer": answer, "citations": []}), answer)
        self.assertEqual(answer_text({"answer": answer}), answer)

    def test_does_not_mutate_record(self):
        rec = {"answer": "x\n+2", "citations": CITES}
        answer_text(rec)
        self.assertEqual(rec["answer"], "x\n+2")

    def test_missing_answer(self):
        self.assertEqual(answer_text({"citations": CITES}), "")


class SentencesTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(sentences("A. B!\nC  D"), ["A.", "B!", "C", "D"])
        self.assertEqual(sentences(""), [])
        self.assertEqual(sentences(None), [])


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.ents = shop_entities()

    def test_flags(self):
        rec = {
            "answer": "แนะนำ Power Buy สำหรับ PS5 ของแท้\nGamer Zone ก็มีขายเหมือนกัน",
            "citations": [{"url": "https://www.powerbuy.co.th/", "title": "Power Buy"}],
        }
        out = extract(rec, self.ents)
        self.assertEqual(out["Power Buy"], {"mentioned": True, "cited": True, "recommended": True})
        self.assertEqual(out["Gamer Zone"], {"mentioned": True, "cited": False, "recommended": False})
        self.assertEqual(out["Art and Gun Game"], {"mentioned": False, "cited": False, "recommended": False})

    def test_recommendation_is_per_sentence(self):
        rec = {"answer": "Gamer Zone เปิดถึงสองทุ่ม. ร้านที่ดีที่สุดคือ Power Buy.", "citations": []}
        out = extract(rec, self.ents)
        self.assertFalse(out["Gamer Zone"]["recommended"])
        self.assertTrue(out["Power Buy"]["recommended"])

    def test_english_marker(self):
        rec = {"answer": "I recommend ArtandGun for retro consoles.", "citations": []}
        self.assertTrue(extract(rec, self.ents)["Art and Gun Game"]["recommended"])

    def test_negation_blocks_recommended(self):
        rec = {"answer": "ไม่แนะนำ Gamer Zone เพราะของไม่แท้", "citations": []}
        flags = extract(rec, self.ents)["Gamer Zone"]
        self.assertTrue(flags["mentioned"])
        self.assertFalse(flags["recommended"])

    def test_negated_sentence_does_not_hide_a_positive_one(self):
        rec = {"answer": "ไม่แนะนำ Gamer Zone ช่วงลดราคา\nแต่โดยรวม Gamer Zone เหมาะกับมือใหม่", "citations": []}
        self.assertTrue(extract(rec, self.ents)["Gamer Zone"]["recommended"])

    def test_source_chip_only_is_cited_not_mentioned(self):
        rec = {
            "answer": "ร้านที่มี PS5 พร้อมส่ง:\nGamer Zone แนะนำเลย\nartandgungame\n+1",
            "citations": CITES,
        }
        out = extract(rec, self.ents)
        art = out["Art and Gun Game"]
        self.assertFalse(art["mentioned"])
        self.assertFalse(art["recommended"])
        self.assertTrue(art["cited"])
        # Power Buy is also only a citation here (no chip, no mention)
        self.assertEqual(out["Power Buy"], {"mentioned": False, "cited": True, "recommended": False})
        self.assertTrue(out["Gamer Zone"]["recommended"])

    def test_empty_record(self):
        out = extract({}, self.ents)
        for flags in out.values():
            self.assertEqual(flags, {"mentioned": False, "cited": False, "recommended": False})


if __name__ == "__main__":
    unittest.main()
