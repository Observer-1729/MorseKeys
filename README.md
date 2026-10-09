# MorseKeys

MorseKeys is a small Windows Python application that turns **Page Up** and
**Page Down** into a Morse-code input device while leaving the rest of the
keyboard available to the active application.

## What it does

### Morse OFF

- Page Up behaves normally.
- Page Down behaves normally.
- Every other key behaves normally.

Hold **Page Up + Page Down for at least 0.4 seconds** to enter Morse mode.

### Morse ON

Only Page Up and Page Down are intercepted by MorseKeys.

- Page Up < 0.4 s → `.`
- Page Up >= 0.4 s → `-`
- Page Down < 0.4 s → one space (letter separator)
- Page Down >= 0.4 s → three spaces (word separator)

All other keys continue to reach Windows/the active application normally,
including Ctrl, Shift, Alt, Windows, letters, numbers, Enter, Space,
Backspace, etc.

Hold **Page Up + Page Down for at least 0.4 seconds** again to finish the
Morse session.

The completed Morse string is decoded and saved as:

```text
D:\Morse_Text\text1.txt
D:\Morse_Text\text2.txt
D:\Morse_Text\text3.txt
...
```

Existing files are never overwritten.

## Project structure

```text
MorseKeys/
├── main.py
├── keyboard_detection.py
├── Morse_Conversion.py
├── test_morse_conversion.py
├── requirements.txt
├── run.bat
└── README.md
```

## Requirements

- Windows 10/11
- Python 3.9+
- No third-party Python packages are required.

The keyboard hook uses the Windows `WH_KEYBOARD_LL` API through `ctypes`.

## Run

MorseKeys is designed to run silently in the background. No terminal needs to
remain open.

Double-click `run.bat`.

The application stays running in the background while you use applications
such as Notepad. There is no status or explanatory console logging.


## Important Windows behavior

MorseKeys uses a native low-level keyboard hook and returns a non-zero value
only for Page Up/Page Down events that it is actively consuming. Other
keyboard events are passed through with `CallNextHookEx`.

The hook callback is intentionally kept short. It only updates keyboard
state and puts mode-change events into a queue; decoding and file I/O are
performed outside the hook.

The Microsoft documentation for `WH_KEYBOARD_LL` notes that the hook callback
should complete quickly and that returning a non-zero value prevents the
event
from being passed to the target window procedure.

## Known behavior of the activation gesture

When Morse mode is OFF, the first 0.4 seconds of the Page Up + Page Down
activation gesture are still normal Windows keyboard input. Once both keys
have been held for the full threshold, MorseKeys takes ownership of the keys
and sends synthetic key-up events to prevent Windows from seeing them as
stuck.

This is intentional: deciding that a simultaneous hold is a mode switch
requires waiting for the 0.4-second threshold.

## Future work

The planned End-key networking/communication mode is intentionally not
implemented yet.

## Silent background operation

MorseKeys does not open or keep a terminal window. The hook and Morse processing continue in the background.
