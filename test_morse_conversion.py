import unittest

from Morse_Conversion import decode_morse


class MorseConversionTests(unittest.TestCase):
    def test_sos(self):
        self.assertEqual(decode_morse("... --- ..."), "SOS")

    def test_hello(self):
        self.assertEqual(
            decode_morse(".... . .-.. .-.. ---"),
            "HELLO",
        )

    def test_multiple_words(self):
        self.assertEqual(
            decode_morse(".... ..   - .... . .-. ."),
            "HI THERE",
        )

    def test_empty(self):
        self.assertEqual(decode_morse(""), "")

    def test_unknown_code(self):
        self.assertEqual(decode_morse(".... .-.-.-"), "H?")

    def test_extra_spaces(self):
        self.assertEqual(decode_morse("...  ---   ..."), "SO S")


if __name__ == "__main__":
    unittest.main()
