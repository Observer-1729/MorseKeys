"""
MorseKeys - main application controller.

Windows-only.
The keyboard hook lives in keyboard_detection.py and only intercepts
Page Up / Page Down while Morse mode is active.
"""

import queue
import sys
from pathlib import Path

from keyboard_detection import KeyboardDetector
from Morse_Conversion import decode_morse

OUTPUT_DIR = Path(r"D:\Morse_Text")


def next_output_file(directory: Path) -> Path:
    """Return the first unused textN.txt path without overwriting anything."""
    directory.mkdir(parents=True, exist_ok=True)

    number = 1
    while True:
        candidate = directory / f"text{number}.txt"
        if not candidate.exists():
            return candidate
        number += 1


def save_decoded_text(text: str) -> Path:
    """Save decoded Morse text using the project's numbered-file rule."""
    output_file = next_output_file(OUTPUT_DIR)
    # UTF-8 keeps the file portable even though the current decoder returns ASCII.
    output_file.write_text(text, encoding="utf-8")
    return output_file


def process_events(events: "queue.Queue[tuple]") -> bool:
    """Process hook events silently."""
    should_run = True

    while True:
        try:
            event = events.get_nowait()
        except queue.Empty:
            break

        event_type = event[0]

        if event_type == "mode" and not event[1]:
            raw_morse = event[2]
            decoded = decode_morse(raw_morse)

            try:
                save_decoded_text(decoded)
            except OSError:
                # Silent background utility: don't open a console for errors.
                pass

        elif event_type == "error":
            should_run = False

    return should_run


def main() -> None:
    if sys.platform != "win32":
        return

    events: "queue.Queue[tuple]" = queue.Queue()

    detector = KeyboardDetector(
        event_queue=events,
        combo_seconds=0.4,
        morse_threshold_seconds=0.4,
    )

    try:
        detector.start()

        while detector.running:
            if not process_events(events):
                break
            detector.wait_for_activity(timeout=0.10)

    finally:
        detector.stop()
        process_events(events)


if __name__ == "__main__":
    main()
