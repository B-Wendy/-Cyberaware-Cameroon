"""
lessons.py  —  the "lesson shelf" (kept on the SERVER).

The 10 lessons (scenario card + quiz, in English, French and Pidgin) live in
lessons.json.  They used to be written inside index.html, which meant every
visitor downloaded all the paid lessons just by opening the page.  Now the
browser only receives a lesson after the server has checked that the visitor
is allowed to see it.

This file:
    * loads and CHECKS lessons.json when the server starts (a typo in the data
      stops the server immediately instead of breaking a quiz later),
    * builds the public catalogue (titles, free/locked),
    * marks quizzes (server-side, so a score can be trusted).
"""

import json

from config import LESSONS_PATH, PASS_PERCENT

LANGS = ("en", "fr", "pidgin")
FREE_LESSONS = 2          # lessons 1 and 2 are free


class LessonDataError(Exception):
    pass


def _check_multilingual(block, fields, where):
    for field in fields:
        for lang in LANGS:
            if lang not in block.get(field, {}):
                raise LessonDataError(f"{where}: '{field}' is missing the '{lang}' text")


def _check_item(item, where):
    _check_multilingual(item, ("q", "opts", "exp"), where)
    size = len(item["opts"]["en"])
    if size < 2:
        raise LessonDataError(f"{where}: needs at least 2 options")
    for lang in LANGS:
        if len(item["opts"][lang]) != size:
            raise LessonDataError(f"{where}: '{lang}' has a different number of options")
    if not isinstance(item.get("cor"), int) or not 0 <= item["cor"] < size:
        raise LessonDataError(f"{where}: 'cor' (correct option) is not a valid option number")


def validate(lessons) -> None:
    if not isinstance(lessons, list) or len(lessons) != 10:
        raise LessonDataError("lessons.json must contain exactly 10 lessons")
    for index, lesson in enumerate(lessons):
        where = f"lesson {index}"
        if lesson.get("id") != index:
            raise LessonDataError(f"{where}: id must be {index}")
        _check_multilingual(lesson, ("name",), where)
        _check_item(lesson["sc"], f"{where} scenario")
        _check_multilingual(lesson["sc"], ("msg",), f"{where} scenario")
        if len(lesson.get("quiz", [])) != 5:
            raise LessonDataError(f"{where}: needs exactly 5 quiz questions")
        for qi, q in enumerate(lesson["quiz"]):
            _check_item(q, f"{where} question {qi}")
        want_free = index < FREE_LESSONS
        if bool(lesson.get("free")) != want_free:
            raise LessonDataError(f"{where}: 'free' must be {want_free}")


class LessonStore:
    def __init__(self, path=None):
        path = path or LESSONS_PATH
        with open(path, encoding="utf-8") as f:
            self.lessons = json.load(f)
        validate(self.lessons)

    def count(self) -> int:
        return len(self.lessons)

    def exists(self, lesson_id) -> bool:
        return isinstance(lesson_id, int) and 0 <= lesson_id < len(self.lessons)

    def is_free(self, lesson_id: int) -> bool:
        return bool(self.lessons[lesson_id]["free"])

    def catalogue(self, entitled: bool) -> list:
        """Titles and lock state only.  No scenario text, no quiz, no answers."""
        return [
            {
                "id": l["id"],
                "free": bool(l["free"]),
                "locked": (not l["free"]) and not entitled,
                "icon": l["icon"],
                "name": l["name"],
                "quiz_count": len(l["quiz"]),
            }
            for l in self.lessons
        ]

    def body(self, lesson_id: int) -> dict:
        return self.lessons[lesson_id]

    def grade(self, lesson_id: int, answers: list) -> dict:
        """Mark a quiz.  `answers` is the chosen option number per question."""
        quiz = self.lessons[lesson_id]["quiz"]
        if len(answers) != len(quiz):
            raise ValueError(f"expected {len(quiz)} answers")
        results = []
        for q, chosen in zip(quiz, answers):
            if isinstance(chosen, bool) or not isinstance(chosen, int) or not 0 <= chosen < len(q["opts"]["en"]):
                raise ValueError("an answer is not a valid option number")
            results.append(chosen == q["cor"])
        score = sum(results)
        percent = round(100 * score / len(quiz))
        return {"score": score, "total": len(quiz), "percent": percent,
                "passed": percent >= PASS_PERCENT, "correct": results}
