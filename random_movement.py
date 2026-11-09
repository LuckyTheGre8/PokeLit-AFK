"""Fixed-loop WASD movement runner with targeted window input & rift navigation.

Features:
- Normal Mode: W -> A -> S -> D clockwise loop with randomized durations (0.1s to 1.5s).
- Rift Mode: When a rift banner or arrow appears, halts random movement and steers
  character continuously towards the rift portal.
- Modal Integration: Automatically pauses while perk_selector.py selects level-ups
  or items, then resumes movement immediately.
- Window-Specific Target: Directs keystrokes ONLY to the PokéLit window (via Win32 PostMessage)
  so you can use your laptop in the foreground without WASD interfering with your work.
- Controls:
    [F8]  = Start movement loop
    [F9]  = Emergency stop (instant key release)
    [F10] = Quit
- Safety:
    PyAutoGUI mouse corner fail-safe (slam mouse to top-left corner).
    Guaranteed release of all keys on stop and exit.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path

import pyautogui
from pynput import keyboard

from window_stream import WindowInput, find_target_window

# PyAutoGUI safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
PAUSE_FILE = Path(__file__).resolve().parent / ".pause_movement"
RIFT_FILE = Path(__file__).resolve().parent / ".rift_movement"

DEFAULT_CONFIG = {
    "target_window": {
        "enabled": True,
        "title_keyword": "pokelit",
        "hwnd": None,
    },
    "movement": {
        "keys": ["w", "a", "s", "d"],
        "min_hold_seconds": 0.1,
        "max_hold_seconds": 1.5,
        "repeat_interval_seconds": 0.035,
        "switch_breather_seconds": 0.03,
    },
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                return {**DEFAULT_CONFIG, **loaded}
        except Exception:
            pass
    return DEFAULT_CONFIG


CONFIG = load_config()
KEYS = CONFIG.get("movement", {}).get("keys", ["w", "a", "s", "d"])
MIN_SECONDS = CONFIG.get("movement", {}).get("min_hold_seconds", 0.1)
MAX_SECONDS = CONFIG.get("movement", {}).get("max_hold_seconds", 1.5)
REPEAT_INTERVAL = CONFIG.get("movement", {}).get("repeat_interval_seconds", 0.035)
SWITCH_BREATHER = CONFIG.get("movement", {}).get("switch_breather_seconds", 0.03)

TARGET_CFG = CONFIG.get("target_window", {})
TARGET_ENABLED = TARGET_CFG.get("enabled", True)
TITLE_KEYWORD = TARGET_CFG.get("title_keyword", "pokelit")
MANUAL_HWND = TARGET_CFG.get("hwnd", None)

kb = keyboard.Controller()

running = threading.Event()
shutdown = threading.Event()
lock = threading.Lock()
worker_thread: threading.Thread | None = None
active_win_input: WindowInput | None = None


def resolve_window_input() -> WindowInput | None:
    """Find target window and return WindowInput controller if enabled."""
    if not TARGET_ENABLED:
        return None
    hwnd = MANUAL_HWND or find_target_window(TITLE_KEYWORD)
    if hwnd:
        return WindowInput(hwnd)
    return None


def release_all_keys() -> None:
    """Defensively release all keys on both target window and global OS."""
    global active_win_input
    for k in KEYS:
        if active_win_input:
            try:
                active_win_input.key_up(k)
            except Exception:
                pass
        try:
            kb.release(k)
        except Exception:
            pass
        try:
            pyautogui.keyUp(k)
        except Exception:
            pass


def read_rift_movement() -> tuple[list[str], float | None] | None:
    """Read active rift target direction keys if .rift_movement exists."""
    if not RIFT_FILE.exists():
        return None
    try:
        with open(RIFT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("active") and data.get("keys"):
                return data.get("keys", []), data.get("angle")
    except Exception:
        pass
    return None


def movement_loop() -> None:
    """Movement loop alternating between rift navigation and random loop."""
    global active_win_input
    pattern_str = " -> ".join(k.upper() for k in KEYS) + " -> " + KEYS[0].upper()

    if active_win_input:
        target_info = f"Window HWND: {active_win_input.hwnd:#x}"
        print(f"\n[ACTIVE] Targeted Background Movement started! ({target_info})")
    else:
        print("\n[ACTIVE] Global Movement started (Game window not locked)!")

    print(f"Normal Pattern: {pattern_str}")
    print("Press [F9] to emergency stop.\n")

    # Clean leftover flag files
    for flag in [PAUSE_FILE, RIFT_FILE]:
        if flag.exists():
            try:
                flag.unlink()
            except Exception:
                pass

    index = 0
    rift_mode_active = False

    try:
        while running.is_set() and not shutdown.is_set():
            # 1. Check if paused for modal selection (level-up or item)
            if PAUSE_FILE.exists():
                release_all_keys()
                time.sleep(0.05)
                continue

            # 2. Check for active rift navigation
            rift_info = read_rift_movement()
            if rift_info:
                rift_keys, angle = rift_info
                if not rift_mode_active:
                    rift_mode_active = True
                    release_all_keys()
                    ang_str = f" (Angle: {angle}°)" if angle is not None else ""
                    print(f"\n>>> [RIFT NAVIGATION STARTED] Arrow detected! Steering: {rift_keys}{ang_str}")

                # Hold rift direction keys for 100ms
                t_end = time.monotonic() + 0.10
                while running.is_set() and not shutdown.is_set() and time.monotonic() < t_end:
                    if PAUSE_FILE.exists() or not RIFT_FILE.exists():
                        break

                    for rk in rift_keys:
                        if active_win_input:
                            active_win_input.key_down(rk)
                        else:
                            kb.press(rk)
                            pyautogui.keyDown(rk)

                    time.sleep(REPEAT_INTERVAL)

                for rk in rift_keys:
                    if active_win_input:
                        active_win_input.key_up(rk)
                    else:
                        kb.release(rk)
                        pyautogui.keyUp(rk)

                continue

            # Transition out of rift mode if arrow/banner disappear
            if rift_mode_active:
                rift_mode_active = False
                release_all_keys()
                print("\n<<< [RIFT NAVIGATION ENDED] Arrow/banner gone! Resuming random movement loop.\n")

            # 3. Normal random movement: pick next key in sequence
            key = KEYS[index % len(KEYS)]
            index += 1

            duration = round(random.uniform(MIN_SECONDS, MAX_SECONDS), 2)
            print(f" -> [{index}] Holding [{key.upper()}] for {duration:.2f}s...")

            deadline = time.monotonic() + duration

            while running.is_set() and not shutdown.is_set() and time.monotonic() < deadline:
                # If modal appears or rift appears, break immediately
                if PAUSE_FILE.exists() or RIFT_FILE.exists():
                    release_all_keys()
                    break

                if active_win_input:
                    active_win_input.key_down(key)
                else:
                    kb.press(key)
                    pyautogui.keyDown(key)

                time.sleep(REPEAT_INTERVAL)

            # Release current key
            if active_win_input:
                active_win_input.key_up(key)
            else:
                kb.release(key)
                pyautogui.keyUp(key)

            time.sleep(SWITCH_BREATHER)

    except pyautogui.FailSafeException:
        print("\n[SAFETY] Mouse corner fail-safe triggered!")
    except Exception as exc:
        print(f"\n[ERROR] Error in movement loop: {exc}")
    finally:
        release_all_keys()
        running.clear()
        print("\n[STOPPED] Movement loop stopped. All keys released.\n")


def start() -> None:
    """Start movement worker thread."""
    global worker_thread, active_win_input
    with lock:
        if running.is_set():
            print("[INFO] Movement is already running.")
            return

        active_win_input = resolve_window_input()
        running.set()
        worker_thread = threading.Thread(target=movement_loop, daemon=True, name="MovementLoop")
        worker_thread.start()


def stop() -> None:
    """Emergency stop and immediate key release."""
    with lock:
        running.clear()
        release_all_keys()


def on_press(key: object) -> bool | None:
    """Handle global hotkey inputs."""
    if key == keyboard.Key.f8:
        start()
    elif key == keyboard.Key.f9:
        print("\n[EMERGENCY STOP] F9 pressed.")
        stop()
    elif key == keyboard.Key.f10:
        print("\n[EXIT] F10 pressed; shutting down...")
        stop()
        shutdown.set()
        return False
    return None


def main() -> None:
    target = resolve_window_input()
    print("==================================================")
    print("      PokéLit Movement Runner (WASD + Rift)       ")
    print("==================================================")
    if target:
        print(f"Targeted Window:  HWND {target.hwnd:#x} (Background Stream Active)")
        print("                  -> Keystrokes go ONLY to PokéLit!")
    else:
        print("Targeted Window:  Not locked (using global inputs)")
    print(f"Hold Interval:    {MIN_SECONDS}s to {MAX_SECONDS}s per direction")
    print("Features:")
    print("  - Random WASD clockwise movement during regular play")
    print("  - Automatic steering towards purple arrow when rift opens")
    print("  - Seamless pause/resume for level-up & item modals")
    print("Controls:")
    print("  [F8]  -> Start movement loop")
    print("  [F9]  -> Emergency stop")
    print("  [F10] -> Quit")
    print("==================================================")
    print("Ready to run alongside perk_selector.py!\n")

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

    stop()
    print("Application exited cleanly.")


if __name__ == "__main__":
    main()
