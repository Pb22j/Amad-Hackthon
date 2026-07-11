from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.nlu.language_detection import detect_language


class LanguageDetectionTests(unittest.TestCase):
    def test_detects_english_by_default(self) -> None:
        self.assertEqual(detect_language("Please check my portfolio"), Language.ENGLISH)

    def test_detects_arabic_characters(self) -> None:
        self.assertEqual(detect_language("راجع رصيدي من فضلك"), Language.ARABIC)

    def test_explicit_language_overrides_detection(self) -> None:
        self.assertEqual(detect_language("Please check this", explicit_language="ar"), Language.ARABIC)


if __name__ == "__main__":
    unittest.main()

