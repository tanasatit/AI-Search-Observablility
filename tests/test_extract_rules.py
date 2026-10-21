"""Regression tests for the failure classes found by the gold benchmark (python -m aiso.benchmark).
Each test names the class it protects. Entities come from config.example.json (coffee shops in Asok)."""
import unittest

from _support import EXAMPLE_CONFIG
from aiso.entities import entity_cited, find_mentions, load_config
from aiso.extract import extract

_, ENTS, _ = load_config(EXAMPLE_CONFIG)
BY = {e.name: e for e in ENTS}
T, BEAN, WORK, NANG, SLOW = (e.name for e in ENTS)


def flags(answer, citations=None):
    return extract({"answer": answer, "citations": citations or []}, ENTS)


def rec(answer):
    return {n for n, f in flags(answer).items() if f["recommended"]}


def mentioned(answer):
    return {n for n, f in flags(answer).items() if f["mentioned"]}


class WordBoundaryTest(unittest.TestCase):
    """Latin names used to match inside longer words once spaces were stripped."""

    def test_longer_words_are_not_mentions(self):
        for text in ["Network Brewery is the best craft beer spot", "Green Bean Laboratory is ideal for geeks",
                     "Bean Labs in Chiang Mai is recommended", "Slow Drip Studios is great for photos",
                     "Work & Brewery sells craft beer", "Baan Suan Cafeteria is a canteen",
                     "Network & Brew is a coworking cafe"]:
            with self.subTest(text=text):
                self.assertEqual(mentioned(text), set())

    def test_real_variants_still_match(self):
        for text, name in [("Bean-Lab", BEAN), ("BEANLAB", BEAN), ("bean lab's flat white", BEAN),
                           ("Work&Brew", WORK), ("work and brew", WORK), ("Baan Suan Cafe.", T),
                           ("ที่Bean Lab", BEAN), ("Slow Drip Studio’s pour-over", SLOW)]:
            with self.subTest(text=text):
                self.assertIn(name, mentioned(text))

    def test_find_mentions_uses_same_rule(self):
        self.assertEqual(find_mentions("Network Brewery", ENTS), set())


class ThaiSpellingTest(unittest.TestCase):
    def test_missing_tone_marks_and_thanthakhat(self):
        self.assertIn(T, mentioned("บ้านสวนคาเฟ แนะนำมุมสวน"))   # คาเฟ่ without ่
        self.assertIn(BEAN, mentioned("บีนแลบ เปิดตี 1"))        # แล็บ without ็
        self.assertIn(T, mentioned("บ้านสวน คาเฟ่ เหมาะกับนัดคุย"))  # extra space

    def test_zero_width_chars(self):
        self.assertIn(T, mentioned("แนะนำ บ้านสวน​คาเฟ่"))

    @unittest.expectedFailure
    def test_known_limit_unlisted_spelling(self):
        # แลป is a different final consonant: add it as an alias in config.json
        self.assertIn(BEAN, mentioned("บีนแลป เปิดตี 1"))

    @unittest.expectedFailure
    def test_known_limit_thai_has_no_word_boundary(self):
        # "ร้านบ้านสวนผัก" is a different shop but contains the alias "ร้านบ้านสวน"
        self.assertNotIn(T, mentioned("ร้านบ้านสวนผักออร์แกนิคที่ลาดพร้าว"))


class CitationTest(unittest.TestCase):
    def cited(self, name, url, title=""):
        return entity_cited(BY[name], [{"url": url, "title": title}])

    def test_domain_must_not_run_into_another_label(self):
        self.assertFalse(self.cited(BEAN, "https://www.notbeanlab.co/", "notbeanlab.co"))
        self.assertFalse(self.cited(BEAN, "https://www.beanlab.com/", "beanlab.com"))
        self.assertFalse(self.cited(WORK, "https://www.networkandbrew.com/", "Network & Brew"))

    def test_subdomain_and_breadcrumb_titles(self):
        self.assertTrue(self.cited(BEAN, "https://blog.beanlab.co/beans", "Beans"))
        self.assertTrue(self.cited(WORK, "https://vertexaisearch.cloud.google.com/r/1", "workandbrew.com › locations › asok"))
        self.assertTrue(self.cited(BEAN, "https://vertexaisearch.cloud.google.com/r/2", "BEANLAB.CO"))

    def test_social_and_map_pages_found_by_name(self):
        self.assertTrue(self.cited(BEAN, "https://www.facebook.com/beanlab.asok", "Bean Lab - Home | Facebook"))
        self.assertTrue(self.cited(BEAN, "https://www.google.com/maps/place/Bean+Lab+Asok", ""))
        self.assertTrue(self.cited(WORK, "https://www.tripadvisor.com/Reviews-Work_Brew-Bangkok.html", ""))

    def test_percent_encoded_thai_url(self):
        url = "https://www.wongnai.com/restaurants/1-%E0%B8%9A%E0%B9%89%E0%B8%B2%E0%B8%99%E0%B8%AA%E0%B8%A7%E0%B8%99%E0%B8%84%E0%B8%B2%E0%B9%80%E0%B8%9F%E0%B9%88"
        self.assertTrue(self.cited(T, url, "Wongnai"))

    def test_domain_only_title_for_entity_without_domains(self):
        # นั่งชิลล์คอฟฟี่ has no domains in config: a Gemini title "nangchillcoffee.com" still counts
        self.assertTrue(self.cited(NANG, "https://vertexaisearch.cloud.google.com/r/3", "nangchillcoffee.com"))

    def test_domain_only_title_of_other_site_does_not_match_by_name(self):
        self.assertFalse(self.cited(BEAN, "https://www.beanlab.com/", "beanlab.com"))

    def test_generic_titles_do_not_match(self):
        for title in ["10 ร้านกาแฟนั่งทำงาน อโศก | Wongnai", "THE BEST Cafes in Asok - Tripadvisor", "+2", ""]:
            self.assertFalse(any(self.cited(n, "https://vertexaisearch.cloud.google.com/r/4", title) for n in BY))


class NegationTest(unittest.TestCase):
    def test_negated_markers_do_not_recommend(self):
        for text in ["I can't recommend Work & Brew; the wifi drops.", "I wouldn't recommend Baan Suan Cafe for meetings.",
                     "Baan Suan Cafe isn't the best choice for work.", "Work & Brew is far from ideal for calls.",
                     "Bean Lab is no longer recommended because it closed.", "Bean Lab is not good for working.",
                     "Some say Slow Drip Studio is not worth recommending.",
                     "บ้านสวนคาเฟ่ไม่ใช่ตัวเลือกที่ดีสำหรับประชุม", "บ้านสวนคาเฟ่ ไม่ค่อยเหมาะกับนั่งทำงาน",
                     "Work & Brew ไม่ใช่ร้านที่ดีที่สุดสำหรับนั่งทำงาน", "บ้านสวนคาเฟ่ ไม่ได้แนะนำเรื่องความเงียบ"]:
            with self.subTest(text=text):
                self.assertEqual(rec(text), set())

    def test_not_only_is_not_a_negation(self):
        self.assertEqual(rec("Bean Lab is not only the best for meetings but also cheap."), {BEAN})

    def test_negative_part_does_not_hide_positive_part(self):
        self.assertEqual(rec("Work & Brew isn't recommended for groups, but it's ideal for solo work."), {WORK})
        self.assertEqual(rec("Slow Drip Studio ไม่เหมาะกับกลุ่มใหญ่ แต่เหมาะกับนั่งคนเดียว"), {SLOW})

    def test_uncertainty_is_not_a_recommendation(self):
        for text in ["It's unclear whether Bean Lab is good for meetings.", "ไม่มีข้อมูลว่า Work & Brew เหมาะกับการประชุมหรือไม่",
                     "Neither Bean Lab nor Work & Brew is recommended for quiet work.",
                     "None of Bean Lab, Work & Brew or Baan Suan Cafe is ideal for quiet calls."]:
            with self.subTest(text=text):
                self.assertEqual(rec(text), set())

    @unittest.expectedFailure
    def test_known_limit_sarcasm(self):
        self.assertEqual(rec("Oh sure, Work & Brew is the 'best' place if you love noise."), set())


class ClauseTest(unittest.TestCase):
    def test_contrast_between_two_businesses(self):
        self.assertEqual(rec("Bean Lab เหมาะกับงานกลุ่ม แต่ บ้านสวนคาเฟ่ ไม่เหมาะ เพราะเสียงดัง"), {BEAN})
        self.assertEqual(rec("Bean Lab is recommended, while Baan Suan Cafe is quite small."), {BEAN})
        self.assertEqual(rec("Bean Lab เหมาะกับงานกลุ่ม ส่วน Work & Brew ปลั๊กเยอะ"), {BEAN})
        self.assertEqual(rec("ถ้าต้องการเงียบ Work & Brew ไม่เหมาะ ส่วน Slow Drip Studio ดีที่สุด"), {SLOW})

    def test_concessive_opening(self):
        self.assertEqual(rec("While Bean Lab is popular, I'd recommend Work & Brew for quiet work."), {WORK})
        self.assertEqual(rec("แม้ว่า Bean Lab จะเด่นเรื่องกาแฟ แต่ Work & Brew เหมาะกับนั่งทำงานมากกว่า"), {WORK})

    def test_single_business_keeps_whole_sentence(self):
        self.assertEqual(rec("Work & Brew gets crowded after 6 pm, but it's good for groups."), {WORK})

    def test_opposite_verdicts_in_one_clause_go_to_nearest_business(self):
        self.assertEqual(rec("ไม่แนะนำให้ไป Work & Brew ช่วงเย็น คนเยอะมาก ควรไป Bean Lab มากกว่า"), {BEAN})
        self.assertEqual(rec("ผมว่า Baan Suan Cafe ไม่โอเคสำหรับทำงานเลย ลองไป Bean Lab ดีกว่า"), {BEAN})
        self.assertEqual(rec("Bean Lab is good for meetings and Work & Brew is not good for calls."), {BEAN})

    def test_shared_verdict_for_a_list(self):
        self.assertEqual(rec("แนะนำ Slow Drip Studio, Bean Lab และ Work & Brew ทั้งสามร้านมี wifi"), {SLOW, BEAN, WORK})


class ComparativeTest(unittest.TestCase):
    def test_only_the_better_one_is_recommended(self):
        for text, want in [("Bean Lab is better than Baan Suan Cafe for working.", {BEAN}),
                           ("Work & Brew ดีกว่า Bean Lab ในเรื่องปลั๊ก", {WORK}),
                           ("Slow Drip Studio is a better choice than Work & Brew if you need quiet.", {SLOW}),
                           ("Go to Bean Lab instead of Work & Brew, which is too crowded.", {BEAN}),
                           ("ถ้าจะนั่งทำงาน ผมแนะนำ Bean Lab แทน Work & Brew", {BEAN}),
                           ("Bean Lab is good for meetings; Rocket Coffee Bar is better than Bean Lab for solo work.", {BEAN})]:
            with self.subTest(text=text):
                self.assertEqual(rec(text), want)

    def test_worse_than(self):
        self.assertEqual(rec("Work & Brew is worse than Slow Drip Studio for calls, which is great for focus."), {SLOW})


class ListStructureTest(unittest.TestCase):
    def test_recommending_heading_covers_its_items(self):
        for text in ["ร้านแนะนำ 3 อันดับ:\n1. Bean Lab\n2. Work & Brew\n3. Slow Drip Studio",
                     "Top picks for working near Asok:\n1. Bean Lab\n2. Work & Brew\n3. Slow Drip Studio",
                     "Top 3 coffee shops for remote work:\n1. Bean Lab\n2. Work & Brew\n3. Slow Drip Studio",
                     "**Best cafes to work from**\n\n**1. Bean Lab** – outlets\n**2. Work & Brew** – cheap\n**3. Slow Drip Studio**",
                     "ร้านที่เหมาะกับการนั่งทำงาน:\nBean Lab มีปลั๊กเยอะ\nWork & Brew เปิดดึก\nSlow Drip Studio เงียบ"]:
            with self.subTest(text=text):
                self.assertEqual(rec(text), {BEAN, WORK, SLOW})

    def test_neutral_heading_recommends_nothing(self):
        self.assertEqual(rec("Cafes near Asok:\n1. Bean Lab\n2. Work & Brew"), set())
        self.assertEqual(rec("รวม 5 ร้านกาแฟน่านั่งทำงาน\n• Bean Lab\n• Work & Brew"), set())

    def test_negative_heading_then_positive_heading(self):
        self.assertEqual(rec("ร้านที่ไม่แนะนำ:\n- Work & Brew (เสียงดัง)\nร้านที่แนะนำ:\n- Bean Lab"), {BEAN})
        self.assertEqual(rec("Recommended:\n- Bean Lab\n- Slow Drip Studio\n\nNot recommended:\n- Work & Brew"), {BEAN, SLOW})

    def test_item_markers_beat_the_heading(self):
        self.assertEqual(rec("Here are my picks:\n- Bean Lab – recommended\n- Work & Brew – not recommended"), {BEAN})

    def test_heading_does_not_leak_into_prose(self):
        self.assertEqual(rec("I recommend checking Google Maps for hours.\nBean Lab opens at 8 am."), set())
        self.assertEqual(rec("You asked for the best cafe near Asok. Bean Lab is open until 10 pm."), set())
        self.assertEqual(rec("คุณถามหาร้านที่ดีที่สุดแถวอโศก\nBean Lab เปิดถึงสี่ทุ่ม"), set())

    def test_rank_one_and_table_rows(self):
        self.assertEqual(rec("อันดับ 1 Bean Lab\nอันดับ 2 Work & Brew"), {BEAN})
        self.assertEqual(rec("| Bean Lab | wifi แรง |\n| Slow Drip Studio | เงียบ เหมาะประชุม |"), {SLOW})
        self.assertEqual(rec("| Bean Lab | Recommended |\n| Work & Brew | Not recommended |"), {BEAN})


class DiscourseTest(unittest.TestCase):
    def test_interjection_stays_with_next_sentence(self):
        self.assertEqual(rec("ห้ามพลาด! บ้านสวนคาเฟ่ ตอนเช้า"), {T})

    def test_question_needs_an_affirmative_answer(self):
        self.assertEqual(rec("Is Bean Lab good for working? Yes, it has outlets."), {BEAN})
        self.assertEqual(rec("Is Work & Brew good for working? Not really; it's too noisy."), set())

    def test_pronoun_follow_up(self):
        self.assertEqual(rec("Bean Lab opened in 2019 near the BTS.\nI recommend it for small meetings."), {BEAN})
        self.assertEqual(rec("Work & Brew is a coworking-style cafe. It's a good place for focused sessions."), {WORK})
        self.assertEqual(rec("Baan Suan Cafe closes at 5 pm. It's not ideal for late work."), set())

    def test_pronoun_needs_a_single_business_before_it(self):
        self.assertEqual(rec("Bean Lab and Work & Brew are both open late. I recommend it."), set())

    def test_pronoun_best_to_is_not_a_verdict(self):
        self.assertEqual(rec("Bean Lab is on Soi 31. It is best to arrive early."), set())

    @unittest.expectedFailure
    def test_known_limit_answer_after_comparative_question(self):
        self.assertEqual(rec("Which is better, Bean Lab or Work & Brew? Bean Lab, by a small margin."), {BEAN})


class MarkerPhraseTest(unittest.TestCase):
    def test_new_phrasings(self):
        for text, want in [("Nang Chill Coffee is a great choice for focus.", {NANG}),
                           ("I'd go with Work&Brew for a long session.", {WORK}),
                           ("ลองไป Bean Lab ดูครับ", {BEAN}),
                           ("For quiet, pick Slow Drip Studio.", {SLOW}),
                           ("Go for Work & Brew if you need outlets.", {WORK}),
                           ("Bean Lab is a solid pick for laptop work.", {BEAN}),
                           ("Top-rated cafes include Bean Lab and Work & Brew.", {BEAN, WORK}),
                           ("If quiet is the priority, Slow Drip Studio is your best bet.", {SLOW})]:
            with self.subTest(text=text):
                self.assertEqual(rec(text), want)

    def test_neutral_sentences_stay_neutral(self):
        for text in ["Cafes in Asok include Bean Lab and Work & Brew.", "Slow Drip Studio opens at 8 am.",
                     "Please pick up your order at Bean Lab.", "Work & Brew is rated 4.7 on Google Maps."]:
            with self.subTest(text=text):
                self.assertEqual(rec(text), set())


class SourceChipWithListTest(unittest.TestCase):
    def test_chips_between_items_do_not_break_a_heading(self):
        cites = [{"url": "https://www.baansuancafe.com/", "title": "baansuancafe.com"},
                 {"url": "https://www.beanlab.co/", "title": "beanlab.co"}]
        out = flags("ร้านที่เหมาะกับการนั่งทำงานแถวอโศก:\nบ้านสวนคาเฟ่ มีที่นั่งกว้าง\nbaansuancafe\nBean Lab เปิดตั้งแต่ 8 โมง\nbeanlab.co\n+2", cites)
        for name in (T, BEAN):
            self.assertEqual(out[name], {"mentioned": True, "cited": True, "recommended": True})


if __name__ == "__main__":
    unittest.main()
