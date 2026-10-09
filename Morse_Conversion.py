"""
Morse-to-English conversion for MorseKeys.

The input format follows the MorseKeys specification:
    " "   separates letters
    "   " separates words

The decoder accepts any number of spaces as separators. Unknown Morse
groups are represented by '?' so malformed input is visible rather than
silently disappearing.
"""

Morse_to_Text = {
    ".-": "A",
    "-...": "B",
    "-.-.": "C",
    "-..": "D",
    ".": "E",
    "..-.": "F",
    "--.": "G",
    "....": "H",
    "..": "I",
    ".---": "J",
    "-.-": "K",
    ".-..": "L",
    "--": "M",
    "-.": "N",
    "---": "O",
    ".--.": "P",
    "--.-": "Q",
    ".-.": "R",
    "...": "S",
    "-": "T",
    "..-": "U",
    "...-": "V",
    ".--": "W",
    "-..-": "X",
    "-.--": "Y",
    "--..": "Z",
    "-----":"0",
    ".----":"1",
    "..---":"2",
    "...--":"3",
    "....-":"4",
    ".....":"5",
    "-....":"6",
    "--...":"7",
    "---..":"8",
    "----.":"9"
}


def decode_morse(text: str) -> str:
    """
    Decode the raw MorseKeys string into uppercase ASCII English.

    Examples:
        decode_morse("... --- ...") -> "SOS"
        decode_morse(".... . .-.. .-.. ---") -> "HELLO"
    """
    if not text:
        return ""

    # The input deliberately uses one space for letters and three for words.
    # Splitting into words first preserves the distinction.
    words = text.strip().split("   ")

    decoded_words = []

    for word in words:
        letters = [part for part in word.split(" ") if part]
        decoded_letters = [
            Morse_to_Text.get(letter, "?")
            for letter in letters
        ]
        decoded_words.append("".join(decoded_letters))

    return " ".join(decoded_words)
