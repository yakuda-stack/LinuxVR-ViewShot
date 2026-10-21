//! 🤖 Automatisch OHNE KI: ist das Foto ein Quiz / eine Frage?
//! Genau wie UI/core/task_rules.py (gleiche Punkte, gleiche Test-Beispiele).
//! Standard seit v1.0.6 (tr_classify = "rules"): spart bei jedem Foto einen KI-Aufruf.

use regex::Regex;
use std::sync::OnceLock;

pub const MIN_SCORE: u32 = 3;

const QUESTION_ENDS: &[&str] = &["?", "？", "か", "か。", "吗", "吗。", "까", "까?"];
const BLANKS: &[&str] = &["___", "＿＿", "□", "（　）", "(  )", "( )"];
const YES_NO_MARKS: &[&str] = &["○", "〇"];
const QUIZ_WORDS: &[&str] = &[
    "quiz", "rätsel", "riddle", "trivia", "question", "frage", "énigme", "devinette", "問題", "クイズ", "问题", "퀴즈",
];
const QUESTION_WORDS: &[&str] = &[
    // Deutsch
    "wer", "was", "wo", "wann", "warum", "wieso", "weshalb", "wie", "welche", "welcher", "welches",
    "welchen", "wem", "wen", "wessen", "woher", "wohin", "womit",
    // Englisch
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    // Französisch
    "quel", "quelle", "quels", "quelles", "qui", "où", "quand", "pourquoi", "comment", "combien",
    // Spanisch / Italienisch / Portugiesisch
    "qué", "cuál", "cuáles", "quién", "dónde", "cuándo", "cómo", "cuánto", "cuántos",
    "cosa", "quale", "quali", "chi", "dove", "perché", "quanto", "qual", "quem", "onde",
];
const CJK_QUESTION: &[&str] = &[
    "何", "どれ", "どこ", "誰", "なぜ", "いつ", "どの", "什么", "哪", "谁", "为什么", "무엇", "어디", "누구", "왜", "어느",
];
const SHORT_ANSWER_WORDS: usize = 4;
const SHORT_ANSWER_CHARS: usize = 30;

fn option_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"^\s*(?:[A-Da-d]|[1-9]|[１-９])\s*[).:\]．、）]\s*\S|^\s*[①-⑨Ⓐ-Ⓓ]\s*\S").unwrap()
    })
}

fn lines(text: &str) -> Vec<String> {
    crate::ocr::splitlines(text).into_iter().map(|t| t.trim().to_string()).filter(|t| !t.is_empty()).collect()
}

fn first_word(line: &str) -> String {
    let rest = line.trim_start_matches(|c: char| "¿¡\"'„“«( ".contains(c));
    rest.chars().take_while(|c| c.is_alphabetic()).collect::<String>().to_lowercase()
}

fn is_question(line: &str) -> bool {
    QUESTION_ENDS.iter().any(|e| line.ends_with(e))
}

/// Kurze Zeile ohne Satzende – so sehen Antwort-Knöpfe aus
fn looks_like_answer(line: &str) -> bool {
    line.chars().count() <= SHORT_ANSWER_CHARS
        && line.split_whitespace().count() <= SHORT_ANSWER_WORDS
        && ![".", "!", "?", "。", "！", "？", ":", "："].iter().any(|e| line.ends_with(e))
}

/// Punkte für „Quiz / Frage“ (0 = sieht nicht danach aus) – siehe UI/core/task_rules.py
pub fn quiz_score(text: &str) -> u32 {
    let lines = lines(text);
    if lines.is_empty() {
        return 0;
    }
    let low = text.to_lowercase();
    let questions: Vec<usize> = (0..lines.len()).filter(|&i| is_question(&lines[i])).collect();
    let options = lines.iter().filter(|l| option_re().is_match(l)).count();
    let blank = BLANKS.iter().any(|b| text.contains(b));

    let mut score = 0;
    if !questions.is_empty() {
        score += 2;
    }
    if lines.iter().any(|l| QUESTION_WORDS.contains(&first_word(l).as_str()))
        || questions.iter().any(|&i| CJK_QUESTION.iter().any(|w| lines[i].contains(w)))
    {
        score += 1;
    }
    if options >= 2 {
        score += 2;
    }
    if blank {
        score += 3;
    }
    if YES_NO_MARKS.iter().any(|m| text.contains(m)) {
        score += 1;
    }
    if QUIZ_WORDS.iter().any(|w| low.contains(w)) {
        score += 1;
    }
    if let Some(&q) = questions.first() {
        if lines[q + 1..].iter().filter(|l| looks_like_answer(l)).count() >= 2 {
            score += 1;
        }
    }
    let shape = lines.len() >= 3 || options >= 2 || blank;
    if shape { score } else { 0 }
}

pub fn looks_like_quiz(text: &str) -> bool {
    quiz_score(text) >= MIN_SCORE
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Gleiche Beispiele wie tests/test_core.py (test_task_rules)
    #[test]
    fn same_scores_as_app() {
        let cases: [(&str, u32); 9] = [
            ("Welches Tier?\nHund\nKatze", 4),
            ("Willkommen\nim Hotel", 0),
            ("Hello? Is anyone there?\nI heard something.\nLet's go.", 2),
            ("Capital of France?\nA) Paris\nB) Rome\nC) Berlin", 5),
            ("The sky is ___.", 3),
            ("Rules:\n1. No running\n2. No food\n3. Have fun", 2),
            ("Where is the exit?\nFollow the signs", 0),
            ("問題：日本の首都は？\nA. 東京\nB. 大阪", 6),
            ("これは何ですか？\nりんご\nみかん\nぶどう", 4),
        ];
        for (text, score) in cases {
            assert_eq!(quiz_score(text), score, "{text:?}");
        }
    }
}
