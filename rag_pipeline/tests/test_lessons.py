import copy
import json
import unittest
from collections import Counter

import tests.helpers  # noqa: F401
from config import LESSONS_PATH
from lessons import LessonDataError, LessonStore, validate


class LessonDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = LessonStore()
        with open(LESSONS_PATH, encoding="utf-8") as f:
            cls.raw = json.load(f)

    def test_ten_lessons_five_questions_each(self):
        self.assertEqual(self.store.count(), 10)
        self.assertTrue(all(len(l["quiz"]) == 5 for l in self.raw))

    def test_only_first_two_lessons_are_free(self):
        self.assertEqual([self.store.is_free(i) for i in range(10)], [True, True] + [False] * 8)

    def test_correct_answers_are_spread_across_positions(self):
        # Guards against "always pick B": no position may hold more than 40% of the answers.
        positions = Counter(q["cor"] for l in self.raw for q in l["quiz"])
        total = sum(positions.values())
        self.assertEqual(total, 50)
        self.assertGreaterEqual(len(positions), 4)
        self.assertLessEqual(max(positions.values()) / total, 0.40)

    def test_scenario_answers_are_not_all_the_same_position(self):
        self.assertGreater(len({l["sc"]["cor"] for l in self.raw}), 1)

    def test_catalogue_hides_content_and_answers(self):
        cat = self.store.catalogue(entitled=False)
        text = json.dumps(cat)
        for forbidden in ['"quiz"', '"cor"', '"sc"', '"msg"', '"exp"']:
            self.assertNotIn(forbidden, text)
        self.assertEqual([c["locked"] for c in cat], [False, False] + [True] * 8)

    def test_catalogue_unlocks_everything_when_entitled(self):
        self.assertFalse(any(c["locked"] for c in self.store.catalogue(entitled=True)))

    def test_grading_all_correct(self):
        answers = [q["cor"] for q in self.raw[0]["quiz"]]
        result = self.store.grade(0, answers)
        self.assertEqual((result["score"], result["percent"], result["passed"]), (5, 100, True))

    def test_pass_mark_is_80_percent(self):
        quiz = self.raw[0]["quiz"]
        four = [q["cor"] for q in quiz]
        four[0] = (four[0] + 1) % 4
        result = self.store.grade(0, four)
        self.assertEqual((result["score"], result["percent"], result["passed"]), (4, 80, True))
        three = list(four)
        three[1] = (three[1] + 1) % 4
        result = self.store.grade(0, three)
        self.assertEqual((result["score"], result["percent"], result["passed"]), (3, 60, False))

    def test_grading_all_wrong(self):
        answers = [(q["cor"] + 1) % len(q["opts"]["en"]) for q in self.raw[0]["quiz"]]
        self.assertEqual(self.store.grade(0, answers)["score"], 0)

    def test_grading_rejects_bad_input(self):
        for bad in ([0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 9], [0, 0, 0, 0, -1],
                    [0, 0, 0, 0, "1"], [0, 0, 0, 0, True], [0, 0, 0, 0, 1.5]):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.store.grade(0, bad)

    def test_every_lesson_has_text_in_all_three_languages(self):
        validate(self.raw)      # raises if anything is missing

    def test_validation_catches_data_mistakes(self):
        broken = copy.deepcopy(self.raw)
        broken[2]["quiz"][1]["cor"] = 7
        with self.assertRaises(LessonDataError):
            validate(broken)
        broken = copy.deepcopy(self.raw)
        del broken[4]["name"]["pidgin"]
        with self.assertRaises(LessonDataError):
            validate(broken)
        broken = copy.deepcopy(self.raw)
        broken[0]["quiz"].pop()
        with self.assertRaises(LessonDataError):
            validate(broken)
        broken = copy.deepcopy(self.raw)
        broken[5]["quiz"][0]["opts"]["fr"].pop()
        with self.assertRaises(LessonDataError):
            validate(broken)
        with self.assertRaises(LessonDataError):
            validate(self.raw[:9])


if __name__ == "__main__":
    unittest.main()
