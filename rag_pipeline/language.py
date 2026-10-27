"""
language.py
A small marker-based language detector for English, French and Cameroonian Pidgin.

HOW IT WORKS (plain words)
    Each language has a list of "marker" words: words that are common in that
    language.  We count how many markers of each language appear in the
    sentence, and the language with the highest score wins.

    Pidgin is special.  Most Pidgin words look like English words, so a normal
    count would label Pidgin sentences as English.  To avoid that, Pidgin
    markers are worth MORE points than English markers: 4 points for a
    distinctive word (wetin, dey, abeg, ...) and 2 points for a particle that
    can also be an ordinary short word (na, dem, don, ...).

    The detector only decides the language when the user has not chosen one.
    Once the user picks a language in the header, that choice is final.
"""

import re

PIDGIN_STRONG_WEIGHT = 4.0   # distinctive Pidgin words that no English sentence contains
PIDGIN_WEAK_WEIGHT = 2.0     # Pidgin particles that are also short, common words elsewhere
FRENCH_ACCENT_POINTS = 1.0
DEFAULT_LANGUAGE = "en"

# Common function words.  Words that exist in BOTH English and French (for
# example "a", "on", "me", "son", "pour" is French only) are left out.
ENGLISH_MARKERS = {
    "the", "is", "are", "was", "were", "what", "how", "why", "when", "where",
    "do", "does", "did", "my", "your", "you", "i", "we", "they", "to", "of",
    "and", "in", "for", "with", "can", "should", "would", "this", "that",
    "it", "not", "have", "has", "been", "from", "someone", "about", "if",
    "me", "will", "an", "or", "be", "who", "which", "there", "need", "keep",
}

FRENCH_MARKERS = {
    "le", "la", "les", "un", "une", "des", "est", "sont", "et", "ou", "que",
    "qui", "quoi", "pour", "dans", "avec", "sur", "mon", "ma", "mes", "je",
    "tu", "il", "nous", "vous", "comment", "pourquoi", "quel", "quelle",
    "quels", "quand", "ce", "cette", "ces", "pas", "du", "au", "aux", "ne",
    "suis", "ai", "ont", "mot", "passe", "faire", "dois", "peux", "puis",
    "mon", "votre", "vos", "ton", "par", "sans", "plus", "très", "tres",
    "c", "d", "l", "qu", "j", "n", "s",
}

# Distinctive Pidgin words (spelling varies, so common variants are listed).
# STRONG markers almost never appear in English or French text.
PIDGIN_STRONG = {
    "wetin", "weti", "dey", "abeg", "wey", "sef", "sabi", "una", "wuna",
    "pikin", "wahala", "palava", "oga", "comot", "howfa", "kontri", "waka",
    "sotey", "njangi", "massa", "bobo",
}
# WEAK markers are Pidgin particles that can also be ordinary short words.
PIDGIN_WEAK = {
    "dem", "na", "wan", "don", "nko", "shey", "chop", "dis", "dat", "dia",
    "di", "yi", "wen", "bifo", "tok", "wat",
}

# Phrases checked on the whole sentence (very strong Pidgin signals).  They are
# matched as whole words, so "i wan" does NOT match the English "i want".
PIDGIN_PHRASES = (
    "no fit", "i no", "e don", "make i", "make we", "how i go", "wetin i",
    "no be", "i dey", "dem dey", "dem don", "dey try", "no dey", "dey ask",
    "i wan", "wetin make", "e dey", "una go",
)

_WORD = re.compile(r"[a-zà-ÿ']+")
_ACCENTS = re.compile(r"[àâäçéèêëîïôöùûüÿœæ]")


def score_languages(text: str) -> dict:
    """Return the marker score of each language for a piece of text."""
    low = (text or "").lower()
    words = _WORD.findall(low)

    # Pieces for French/English: "l'ordinateur" -> "l", "ordinateur"
    pieces = []
    for w in words:
        pieces.extend(p for p in w.split("'") if p)

    english = sum(1 for p in pieces if p in ENGLISH_MARKERS)
    french = sum(1 for p in pieces if p in FRENCH_MARKERS)
    french += FRENCH_ACCENT_POINTS * len(_ACCENTS.findall(low))

    sentence = " " + " ".join(words) + " "
    pidgin = (PIDGIN_STRONG_WEIGHT * sum(1 for w in words if w in PIDGIN_STRONG)
              + PIDGIN_WEAK_WEIGHT * sum(1 for w in words if w in PIDGIN_WEAK)
              + PIDGIN_STRONG_WEIGHT * sum(1 for ph in PIDGIN_PHRASES if f" {ph} " in sentence))

    return {"en": float(english), "fr": float(french), "pidgin": float(pidgin)}


def detect_language(text: str) -> str:
    """Return "en", "fr" or "pidgin".  Ties and empty input give English."""
    scores = score_languages(text)
    best = max(scores.values())
    if best <= 0:
        return DEFAULT_LANGUAGE
    # Priority on ties: pidgin, then french, then english.
    for lang in ("pidgin", "fr", "en"):
        if scores[lang] == best:
            return lang
    return DEFAULT_LANGUAGE
