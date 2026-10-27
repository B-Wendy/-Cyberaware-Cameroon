import unittest

from tests.helpers import ROOT  # noqa: F401  (sets up paths)
from language import detect_language

# Thirty labelled inputs: ten per language.  Several Pidgin inputs are
# deliberately "ambiguous": most of their words are ordinary English.
LABELLED = [
    # English
    ("How do I recognise a phishing SMS?", "en"),
    ("What makes a strong password?", "en"),
    ("My Facebook account was hacked, what should I do?", "en"),
    ("How can I report a cybercrime to CIRT?", "en"),
    ("Is it safe to use public wifi at the cafe?", "en"),
    ("Someone is asking me for my Mobile Money PIN", "en"),
    ("I want to change the password on my email", "en"),
    ("Should I pay if my files are locked by ransomware?", "en"),
    ("Tell me about two factor authentication", "en"),
    ("Why do scammers send messages about prizes?", "en"),
    # French
    ("Comment reconnaître un SMS de phishing ?", "fr"),
    ("Qu'est-ce qu'un mot de passe robuste ?", "fr"),
    ("Mon compte Facebook a été piraté, que faire ?", "fr"),
    ("Comment signaler une cybercriminalité au CIRT ?", "fr"),
    ("Est-ce dangereux d'utiliser le wifi public ?", "fr"),
    ("Quelqu'un me demande mon code PIN Mobile Money", "fr"),
    ("Je veux changer le mot de passe de ma messagerie", "fr"),
    ("Dois-je payer si mes fichiers sont bloqués ?", "fr"),
    ("Parlez-moi de l'authentification à deux facteurs", "fr"),
    ("Pourquoi les escrocs envoient des messages sur des cadeaux ?", "fr"),
    # Pidgin (the last four are the "ambiguous" ones: mostly English words)
    ("Wetin I go do if dem hack my Facebook?", "pidgin"),
    ("How I go know say na scam SMS?", "pidgin"),
    ("Abeg tell me how to protect my Mobile Money", "pidgin"),
    ("Dem don send me message say my account don block", "pidgin"),
    ("Wetin make password strong?", "pidgin"),
    ("I no sabi how to report cybercrime", "pidgin"),
    ("My account don hack, make I change di password", "pidgin"),
    ("How I go put two factor for my WhatsApp?", "pidgin"),
    ("Person wan chop my money for Mobile Money, wetin I go do", "pidgin"),
    ("Dem dey ask me for my PIN, na true say e dey safe?", "pidgin"),
]


class LanguageDetectorTests(unittest.TestCase):
    def test_exactly_thirty_inputs_ten_per_language(self):
        self.assertEqual(len(LABELLED), 30)
        for lang in ("en", "fr", "pidgin"):
            self.assertEqual(sum(1 for _t, l in LABELLED if l == lang), 10)

    def test_each_labelled_input(self):
        wrong = [(t, want, detect_language(t)) for t, want in LABELLED if detect_language(t) != want]
        self.assertEqual(wrong, [], f"misclassified: {wrong}")

    def test_empty_and_unknown_default_to_english(self):
        self.assertEqual(detect_language(""), "en")
        self.assertEqual(detect_language("zzzz qqqq"), "en")

    def test_pidgin_markers_outweigh_english_overlap(self):
        # Mostly English words, but one distinctive Pidgin particle pair.
        self.assertEqual(detect_language("my phone dey show say I don win money"), "pidgin")


if __name__ == "__main__":
    unittest.main()
