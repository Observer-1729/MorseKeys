"""
Native Windows low-level keyboard hook for MorseKeys.

Only VK_PRIOR (Page Up) and VK_NEXT (Page Down) are handled here.
All other keyboard events are immediately passed to Windows.

The hook uses WH_KEYBOARD_LL via user32.dll, so no third-party package is
required. The callback is deliberately small: it updates state and places
application events into a Queue; decoding and file I/O happen elsewhere.
"""

from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes
from typing import Optional

if ctypes.sizeof(ctypes.c_void_p) == 8:
    LRESULT = ctypes.c_ssize_t
else:
    LRESULT = ctypes.c_long

WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

WH_KEYBOARD_LL = 13

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22   # Page Down

LLKHF_INJECTED = 0x10

HC_ACTION = 0

# Messages used to wake/stop the hook thread.
WM_QUIT = 0x0012


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    WPARAM,
    LPARAM,
)


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


class KeyboardDetector:
    """
    Detect Page Up/Page Down globally and implement the Morse mode state
    machine described by the MorseKeys specification.

    Events placed on event_queue:
      ("mode", True)
      ("mode", False, raw_morse)
      ("status", message)
      ("error", message)
    """

    def __init__(
        self,
        event_queue: "queue.Queue[tuple]",
        combo_seconds: float = 0.4,
        morse_threshold_seconds: float = 0.4,
    ) -> None:
        self.event_queue = event_queue
        self.combo_seconds = combo_seconds
        self.morse_threshold_seconds = morse_threshold_seconds

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._hook = None
        self._hook_proc = HOOKPROC(self._keyboard_proc)

        self._mode_on = False
        self._morse = []

        # State is accessed by the hook thread and combo timer, so protect it.
        self._lock = threading.RLock()

        # First physical keydown time for each Morse key.
        self._down_time: dict[int, float] = {}

        # True after both keys have gone down and a 0.4s combination timer
        # has been started.
        self._combo_active = False
        self._combo_triggered = False
        self._combo_timer: Optional[threading.Timer] = None

        # When a mode toggle happens, Windows may already have received the
        # Page Up/Page Down keydown events while Morse was OFF. We send
        # synthetic key-up events immediately, then consume the real key-ups.
        self._consume_keyup: set[int] = set()

        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        self._user32.SetWindowsHookExW.restype = wintypes.HANDLE

        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        self._user32.CallNextHookEx.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            WPARAM,
            LPARAM,
        ]
        self._user32.CallNextHookEx.restype = LRESULT

        self._user32.GetMessageW.argtypes = [
            ctypes.POINTER(MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._user32.GetMessageW.restype = ctypes.c_int

        self._user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        self._user32.TranslateMessage.restype = wintypes.BOOL

        self._user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
        self._user32.DispatchMessageW.restype = LRESULT

        self._user32.PostThreadMessageW.argtypes = [
            wintypes.DWORD,
            wintypes.UINT,
            WPARAM,
            LPARAM,
        ]
        self._user32.PostThreadMessageW.restype = wintypes.BOOL

        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        self._user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        self._user32.SendInput.restype = wintypes.UINT

    @property
    def running(self) -> bool:
        return self._running

    @property
    def mode_on(self) -> bool:
        with self._lock:
            return self._mode_on

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._hook_thread,
            name="MorseKeysKeyboardHook",
            daemon=True,
        )
        self._thread.start()

    def wait_for_activity(self, timeout: float = 0.1) -> None:
        # The method exists to keep main.py independent of implementation
        # details. The hook itself owns the Windows message loop.
        time.sleep(timeout)

    def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        with self._lock:
            timer = self._combo_timer
            self._combo_timer = None

        if timer is not None:
            timer.cancel()

        if self._thread_id is not None:
            self._user32.PostThreadMessageW(
                self._thread_id,
                WM_QUIT,
                0,
                0,
            )

        if self._thread is not None:
            self._thread.join(timeout=2.0)

        self._thread = None
        self._thread_id = None

    def _hook_thread(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()

        module_handle = self._kernel32.GetModuleHandleW(None)
        if not module_handle:
            self.event_queue.put(
                ("error", f"GetModuleHandleW failed: {ctypes.get_last_error()}")
            )
            self._running = False
            return

        hook = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_proc,
            module_handle,
            0,
        )

        if not hook:
            error = ctypes.get_last_error()
            self.event_queue.put(
                ("error", f"SetWindowsHookExW failed with error {error}.")
            )
            self._running = False
            return

        self._hook = hook
        self.event_queue.put(("status", "Global keyboard hook installed."))

        msg = MSG()

        try:
            while self._running:
                result = self._user32.GetMessageW(
                    ctypes.byref(msg),
                    None,
                    0,
                    0,
                )

                if result == -1:
                    self.event_queue.put(
                        ("error", f"GetMessageW failed: {ctypes.get_last_error()}")
                    )
                    break

                if result == 0:
                    break

                self._user32.TranslateMessage(ctypes.byref(msg))
                self._user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._hook:
                self._user32.UnhookWindowsHookEx(self._hook)
                self._hook = None

            self._running = False
            self.event_queue.put(("status", "Global keyboard hook removed."))

    def _keyboard_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return self._user32.CallNextHookEx(
                self._hook, n_code, w_param, l_param
            )

        data = ctypes.cast(
            l_param,
            ctypes.POINTER(KBDLLHOOKSTRUCT),
        ).contents

        vk = int(data.vkCode)

        if vk not in (VK_PRIOR, VK_NEXT):
            return self._user32.CallNextHookEx(
                self._hook, n_code, w_param, l_param
            )

        # Ignore our own synthetic key-up events.
        if data.flags & LLKHF_INJECTED:
            return self._user32.CallNextHookEx(
                self._hook, n_code, w_param, l_param
            )

        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = w_param in (WM_KEYUP, WM_SYSKEYUP)

        if not (is_down or is_up):
            return self._user32.CallNextHookEx(
                self._hook, n_code, w_param, l_param
            )

        if is_down:
            suppress = self._handle_key_down(vk)
        else:
            suppress = self._handle_key_up(vk)

        if suppress:
            # A non-zero return prevents this Page Up/Page Down event from
            # reaching the target application and the rest of the hook chain.
            return 1

        return self._user32.CallNextHookEx(
            self._hook, n_code, w_param, l_param
        )

    def _handle_key_down(self, vk: int) -> bool:
        now = time.monotonic()

        with self._lock:
            # Ignore auto-repeat. Only the first physical DOWN starts timing.
            if vk in self._down_time:
                return self._mode_on or vk in self._consume_keyup

            self._down_time[vk] = now

            # A second keydown creates a fresh "both held" interval.
            if (
                VK_PRIOR in self._down_time
                and VK_NEXT in self._down_time
                and not self._combo_active
            ):
                self._combo_active = True
                self._combo_triggered = False

                timer = threading.Timer(
                    self.combo_seconds,
                    self._combo_timeout,
                )
                timer.daemon = True
                self._combo_timer = timer
                timer.start()

            # While Morse mode is ON, only Page Up/Page Down are suppressed.
            return self._mode_on

    def _handle_key_up(self, vk: int) -> bool:
        now = time.monotonic()

        with self._lock:
            start = self._down_time.pop(vk, None)
            was_consumed = vk in self._consume_keyup

            if was_consumed:
                self._consume_keyup.discard(vk)

            if start is None:
                # A key-up without a tracked key-down should never become
                # Morse input.
                suppress = was_consumed or self._mode_on
            elif self._combo_triggered:
                # Toggle combinations are never Morse characters.
                suppress = True
            elif self._mode_on:
                duration = now - start
                self._append_morse_for_key(vk, duration)
                suppress = True
            else:
                # Morse OFF: Windows receives the event normally.
                suppress = False

            # The combination is eligible again only after BOTH keys are up.
            if (
                VK_PRIOR not in self._down_time
                and VK_NEXT not in self._down_time
            ):
                self._reset_combo_state()

            return suppress

    def _append_morse_for_key(self, vk: int, duration: float) -> None:
        # This method is called with _lock held.
        if duration < self.morse_threshold_seconds:
            symbol = "." if vk == VK_PRIOR else " "
        else:
            symbol = "-" if vk == VK_PRIOR else "   "

        self._morse.append(symbol)

    def _combo_timeout(self) -> None:
        """
        Runs after both keys have been continuously held for combo_seconds.

        It toggles the mode exactly once. Both keys are marked so their real
        physical key-up events are consumed and never become Morse symbols.
        """
        with self._lock:
            self._combo_timer = None

            if not self._running:
                return

            if (
                VK_PRIOR not in self._down_time
                or VK_NEXT not in self._down_time
                or self._combo_triggered
            ):
                return

            self._combo_triggered = True
            self._consume_keyup.update((VK_PRIOR, VK_NEXT))

            if self._mode_on:
                raw_morse = "".join(self._morse)
                self._morse.clear()
                self._mode_on = False
                event = ("mode", False, raw_morse)
            else:
                self._morse.clear()
                self._mode_on = True
                event = ("mode", True)

            # Because the OFF->ON transition happens after Windows may have
            # received the original key-downs, send synthetic key-ups now.
            # This prevents Windows from believing Page Up/Page Down remain
            # physically held. Injected events are ignored by our hook.
            self._send_key_up(VK_PRIOR)
            self._send_key_up(VK_NEXT)

            self.event_queue.put(event)

    def _reset_combo_state(self) -> None:
        # Called with _lock held.
        self._combo_active = False
        self._combo_triggered = False

        timer = self._combo_timer
        self._combo_timer = None

        if timer is not None:
            timer.cancel()

    def _send_key_up(self, vk: int) -> None:
        """
        Send a synthetic key-up to Windows.

        INPUT is represented locally to avoid external packages.
        """
        KEYEVENTF_KEYUP = 0x0002
        INPUT_KEYBOARD = 1

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [
                ("type", wintypes.DWORD),
                ("u", INPUT_UNION),
            ]

        inp = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=vk,
                wScan=0,
                dwFlags=KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            ),
        )

        self._user32.SendInput(
            1,
            ctypes.byref(inp),
            ctypes.sizeof(INPUT),
        )
