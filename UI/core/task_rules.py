"""
core/task_rules.py – 🤖 Automatisch OHNE KI: ist das Foto ein Quiz / eine Frage?

Standard seit v1.0.6 (tr_classify = "rules"): spart bei jedem Foto einen KI-Aufruf
(beim lokalen Bild-LLM einen ganzen Bild-Durchlauf). Nur Textregeln, kostet ~nichts.

Punkte sammeln statt einer einzigen Bedingung – ab MIN_SCORE Punkten = Quiz:
    Zeile endet mit ? / か / 吗 …          +2
    Fragewort am Zeilenanfang (wer, what …) +1
    ≥ 2 Antwort-Optionen (A) B) 1. ① …)    +2
    Lücke (___, □, （　）)                  +3
    ○ / 〇 (Japan: richtig/falsch)          +1
    Wort wie Quiz / Rätsel / 問題            +1
    ≥ 2 kurze Zeilen nach der Frage         +1  (sehen aus wie Antworten)
Außerdem muss es nach Quiz AUSSEHEN: ≥ 3 Zeilen, Antwort-Optionen oder eine Lücke.
„Kontext erklären“ (Witz, Meme) erkennen Regeln nicht zuverlässig → nur von Hand.

Gleiche Regeln im Dienst: daemon/src/tr/rules.rs (Tests in beiden mit gleichen Beispielen).
"""

import re

MIN_SCORE = 3

QUESTION_ENDS = ("?", "？", "か", "か。", "吗", "吗。", "까", "까?")
BLANKS = ("___", "＿＿", "□", "（　）", "(  )", "( )")
YES_NO_MARKS = ("○", "〇")
QUIZ_WORDS = ("quiz", "rätsel", "riddle", "trivia", "question", "frage", "énigme", "devinette",
              "問題", "クイズ", "问题", "퀴즈")
# Erstes Wort einer Zeile (klein, ohne ¿ ¡)
QUESTION_WORDS = {
    # Deutsch
    "wer", "was", "wo", "wann", "warum", "wieso", "weshalb", "wie", "welche", "welcher", "welches",
    "welchen", "wem", "wen", "wessen", "woher", "wohin", "womit",
    # Englisch
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    # Französisch
    "quel", "quelle", "quels", "quelles", "qui", "où", "quand", "pourquoi", "comment", "combien",
    # Spanisch / Italienisch / Portugiesisch
    "qué", "cuál", "cuáles", "quién", "dónde", "cuándo", "cómo", "cuánto", "cuántos",
    "cosa", "quale", "quali", "chi", "dove", "perché", "quanto", "qual", "quem", "onde",
}
# Fragewörter in Sprachen ohne Leerzeichen – zählen nur in einer Frage-Zeile
CJK_QUESTION = ("何", "どれ", "どこ", "誰", "なぜ", "いつ", "どの", "什么", "哪", "谁", "为什么",
                "무엇", "어디", "누구", "왜", "어느")
# Antwort-Option: "A) …", "b. …", "1) …", "２．…", "① …", "Ⓐ …"
OPTION = re.compile(r"^\s*(?:[A-Da-d]|[1-9]|[１-９])\s*[).:\]．、）]\s*\S|^\s*[①-⑨Ⓐ-Ⓓ]\s*\S")
_WORD = re.compile(r"[^\W\d_]+")
SHORT_ANSWER_WORDS = 4
SHORT_ANSWER_CHARS = 30


def _lines(text: str) -> list[str]:
    return [t.strip() for t in text.splitlines() if t.strip()]


def _first_word(line: str) -> str:
    m = _WORD.match(line.lstrip("¿¡\"'„“«( ").lower())
    return m.group(0) if m else ""


def _is_question(line: str) -> bool:
    return line.endswith(QUESTION_ENDS)


def _looks_like_answer(line: str) -> bool:
    """Kurze Zeile ohne Satzende – so sehen Antwort-Knöpfe aus."""
    return (len(line) <= SHORT_ANSWER_CHARS and len(line.split()) <= SHORT_ANSWER_WORDS
            and not line.endswith((".", "!", "?", "。", "！", "？", ":", "：")))


def quiz_score(text: str) -> int:
    """Punkte für „Quiz / Frage“ (0 = sieht nicht danach aus, siehe Kopf der Datei)."""
    lines = _lines(text)
    if not lines:
        return 0
    low = text.lower()
    questions = [i for i, line in enumerate(lines) if _is_question(line)]
    options = sum(1 for line in lines if OPTION.match(line))
    blank = any(b in text for b in BLANKS)

    score = 0
    if questions:
        score += 2
    if (any(_first_word(line) in QUESTION_WORDS for line in lines)
            or any(w in lines[i] for i in questions for w in CJK_QUESTION)):
        score += 1
    if options >= 2:
        score += 2
    if blank:
        score += 3
    if any(m in text for m in YES_NO_MARKS):
        score += 1
    if any(w in low for w in QUIZ_WORDS):
        score += 1
    if questions and sum(1 for line in lines[questions[0] + 1:] if _looks_like_answer(line)) >= 2:
        score += 1

    shape = len(lines) >= 3 or options >= 2 or blank
    return score if shape else 0


def looks_like_quiz(text: str) -> bool:
    return quiz_score(text) >= MIN_SCORE
