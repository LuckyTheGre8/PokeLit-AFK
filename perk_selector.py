"""PokéLit Level-Up, Item Modal & Rift Navigator (Window-Targeted).

Runs alongside random_movement.py:
- Output Stream: Captures ONLY the target PokéLit window via Win32 PrintWindow.
- Automated Responsibilities:
    1. Level-Up Screen ("Choose a reward") -> Taps 1, 2, or 3 (configured strategy)
    2. Item Screen (2 Options) -> Always taps 2 (Equips item)
    3. Item Screen (3 Options) -> Always taps 3 (Locks item)
    4. Rift Detection & Steering -> Detects purple banner / arrow, calculates
       8-direction vector from player center, steers towards the rift, and
       resumes random movement when arrow/banner disappear.
- Input Stream: Sends choice keys directly to the target window.
- Controls:
    [F8]  = Start monitoring
    [F9]  = Stop monitoring
    [F10] = Quit
    [F7]  = Manual Test Scan (captures target window now and logs state)
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
import threading
import time
from pathlib import Path

import pyautogui
from pynput import keyboard

from level_detector import DetectionResult, LevelUpDetector, ModalType, PerkSelector, RiftDetector, RiftResult, ScreenGrabber
from window_stream import WindowCapture, WindowInput, find_target_window

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

user32 = ctypes.windll.user32

PAUSE_FILE = Path(__file__).resolve().parent / ".pause_movement"
RIFT_FILE = Path(__file__).resolve().parent / ".rift_movement"
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"


def load_config() -> dict:
    defaults = {
        "target_window": {
            "enabled": True,
            "title_keyword": "pokelit",
            "hwnd": None,
            "focus_flick_on_select": True,
        },
        "level_up": {
            "confidence_threshold": 0.78,
            "choice_strategy": "1",
            "key_press_hold_seconds": 0.08,
            "post_detection_settle_seconds": 0.25,
            "post_selection_wait_seconds": 0.4,
            "max_selection_wait_seconds": 2.0,
            "poll_interval_seconds": 0.12,
            "priority_list": [],
        },
        "item_window": {
            "choice_2_options": "2",
            "choice_3_options": "3",
        },
        "rift_navigation": {
            "enabled": True,
            "confidence_threshold": 0.75,
        },
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**defaults, **data}
        except Exception:
            pass
    return defaults


CONFIG = load_config()
TARGET_CFG = CONFIG.get("target_window", {})
TARGET_ENABLED = TARGET_CFG.get("enabled", True)
TITLE_KEYWORD = TARGET_CFG.get("title_keyword", "pokelit")
MANUAL_HWND = TARGET_CFG.get("hwnd", None)
FOCUS_FLICK = TARGET_CFG.get("focus_flick_on_select", True)

LVL_CFG = CONFIG.get("level_up", {})
CONF_THRESH = LVL_CFG.get("confidence_threshold", 0.78)
CHOICE_STRAT = LVL_CFG.get("choice_strategy", "1")
KEY_HOLD_SEC = LVL_CFG.get("key_press_hold_seconds", 0.08)
SETTLE_SEC = LVL_CFG.get("post_detection_settle_seconds", 0.25)
POST_WAIT = LVL_CFG.get("post_selection_wait_seconds", 0.4)
MAX_WAIT = LVL_CFG.get("max_selection_wait_seconds", 2.0)
POLL_INTERVAL = LVL_CFG.get("poll_interval_seconds", 0.12)
PRIORITY_LIST = LVL_CFG.get("priority_list", [])

ITEM_CFG = CONFIG.get("item_window", {})
ITEM_CHOICE_2 = ITEM_CFG.get("choice_2_options", "2")
ITEM_CHOICE_3 = ITEM_CFG.get("choice_3_options", "3")

RIFT_CFG = CONFIG.get("rift_navigation", {})
RIFT_ENABLED = RIFT_CFG.get("enabled", True)

running = threading.Event()
shutdown = threading.Event()
lock = threading.Lock()
monitor_thread: threading.Thread | None = None

detector = LevelUpDetector(confidence_threshold=CONF_THRESH)
rift_detector = RiftDetector()
selector = PerkSelector(
    strategy=CHOICE_STRAT,
    key_hold_seconds=KEY_HOLD_SEC,
    priority_list=PRIORITY_LIST,
    item_choice_2=ITEM_CHOICE_2,
    item_choice_3=ITEM_CHOICE_3,
)

active_cap: WindowCapture | ScreenGrabber | None = None
active_win_input: WindowInput | None = None
active_hwnd: int | None = None


def resolve_capture_and_input() -> tuple[WindowCapture | ScreenGrabber, WindowInput | None, int | None]:
    """Resolve target window stream; fallback to full screen if disabled or not found."""
    if TARGET_ENABLED:
        hwnd = MANUAL_HWND or find_target_window(TITLE_KEYWORD)
        if hwnd:
            try:
                cap = WindowCapture(hwnd)
                _ = cap.grab_bgr()
                inp = WindowInput(hwnd)
                return cap, inp, hwnd
            except Exception as exc:
                print(f"[WARN] Failed to lock to window {hwnd:#x} ({exc}); falling back to screen.")

    return ScreenGrabber(), None, None


def set_pause(active: bool) -> None:
    """Create or remove the pause signal file for random_movement.py."""
    try:
        if active:
            PAUSE_FILE.touch(exist_ok=True)
        else:
            if PAUSE_FILE.exists():
                PAUSE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def set_rift_movement(active: bool, keys: list[str] | None = None, angle: float | None = None) -> None:
    """Write or clear the active rift navigation steering keys."""
    try:
        if active and keys:
            data = json.dumps({"active": True, "keys": keys, "angle": angle})
            temp_file = RIFT_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(data)
            temp_file.replace(RIFT_FILE)
        else:
            if RIFT_FILE.exists():
                RIFT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def execute_choice(choice: str) -> None:
    """Execute selection specifically on target window or global fallback."""
    global active_hwnd, active_win_input

    if active_hwnd and active_win_input:
        if FOCUS_FLICK:
            prev_fg = user32.GetForegroundWindow()
            try:
                user32.SetForegroundWindow(active_hwnd)
                time.sleep(0.04)
                active_win_input.tap(choice, hold_duration=KEY_HOLD_SEC)
                selector.tap_choice(choice)
            finally:
                if prev_fg and prev_fg != active_hwnd:
                    user32.SetForegroundWindow(prev_fg)
        else:
            active_win_input.tap(choice, hold_duration=KEY_HOLD_SEC)
    else:
        selector.tap_choice(choice)


def monitor_loop() -> None:
    """Background screen monitoring loop for modals and rift navigation."""
    global active_cap, active_win_input, active_hwnd

    if isinstance(active_cap, WindowCapture) and active_hwnd:
        print(f"\n[ACTIVE] Vision monitor targeting window HWND: {active_hwnd:#x}")
        print("         -> Capturing ONLY the game window in background.")
    else:
        print("\n[ACTIVE] Vision monitor active on full screen.")

    print(f"Level-Up Strategy: Option [{selector.strategy.upper()}] (taps 1, 2, or 3)")
    print(f"Item Strategy:     2-Options -> [{selector.item_choice_2}] | 3-Options -> [{selector.item_choice_3}]")
    print(f"Rift Navigation:   {'ENABLED (Auto-steers to purple arrow)' if RIFT_ENABLED else 'DISABLED'}")
    print("Press [F9] to stop | [F7] for test scan.\n")

    modals_handled = 0
    rift_active_logged = False

    try:
        while running.is_set() and not shutdown.is_set():
            time.sleep(POLL_INTERVAL)

            if not running.is_set() or shutdown.is_set():
                break

            try:
                frame = active_cap.grab_bgr()

                # 1. First priority: Check for Level-Up or Item Modal
                result: DetectionResult = detector.detect(frame)

                if result.is_level_up:
                    # Clear rift navigation while modal is active
                    set_rift_movement(False)
                    set_pause(True)

                    modals_handled += 1
                    modal_label = "LEVEL-UP" if result.modal_type == ModalType.LEVEL_UP else "ITEM WINDOW"
                    print(f"\n==================================================")
                    print(f" [{modal_label} DETECTED #{modals_handled}]")
                    print(f" Type: {result.modal_type.value} | Options: {result.option_count} | Confidence: {result.confidence:.3f}")
                    print(f" Pausing movement...")

                    time.sleep(SETTLE_SEC)

                    choice = selector.decide_choice(result.modal_type, result.option_count)
                    if result.modal_type == ModalType.ITEM:
                        action_desc = f"Item Modal ({result.option_count} options -> selecting [{choice}])"
                    else:
                        action_desc = f"Selecting perk [{choice}]"
                    print(f" -> {action_desc} (Tapping key [{choice}])...")
                    execute_choice(choice)

                    dismissed = False
                    start_wait = time.monotonic()
                    while time.monotonic() - start_wait < MAX_WAIT:
                        time.sleep(0.12)
                        check_frame = active_cap.grab_bgr()
                        if not detector.detect(check_frame).is_level_up:
                            dismissed = True
                            break
                        if time.monotonic() - start_wait > 0.5:
                            execute_choice(choice)

                    if dismissed:
                        elapsed = time.monotonic() - start_wait
                        print(f" -> Modal dismissed successfully ({elapsed:.2f}s).")
                    else:
                        print(" -> [WARN] Modal dismissal wait timed out.")

                    time.sleep(POST_WAIT)
                    set_pause(False)
                    print(" Resuming movement loop.")
                    print("==================================================\n")
                    continue

                # 2. Second priority: Rift Detection & Navigation
                if RIFT_ENABLED:
                    rift_res: RiftResult = rift_detector.detect(frame)
                    if rift_res.is_active and rift_res.direction_keys:
                        if not rift_active_logged:
                            rift_active_logged = True
                            desc = "Physical Portal Tear" if rift_res.mode == "portal_tear" else ("Arrow indicator" if rift_res.mode == "rift_arrow" else "Banner")
                            print(f"[RIFT DETECTED] {desc} found at {rift_res.target_point} -> Steering {rift_res.direction_keys} (Angle: {rift_res.angle_deg}°)")
                        set_rift_movement(True, rift_res.direction_keys, rift_res.angle_deg)
                    else:
                        if rift_active_logged:
                            rift_active_logged = False
                            print("[RIFT ENDED] Portal / Arrow cleared. Returning to random movement.")
                        set_rift_movement(False)

            except Exception as exc:
                print(f"[WARN] Detection error: {exc}")
                time.sleep(0.2)

    finally:
        set_pause(False)
        set_rift_movement(False)
        running.clear()
        print("\n[STOPPED] Vision monitor stopped.\n")


def start() -> None:
    """Start monitor thread."""
    global monitor_thread, active_cap, active_win_input, active_hwnd
    with lock:
        if running.is_set():
            print("[INFO] Monitor is already running.")
            return

        active_cap, active_win_input, active_hwnd = resolve_capture_and_input()
        running.set()
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True, name="ModalMonitorThread")
        monitor_thread.start()


def stop() -> None:
    """Stop monitor thread and clear pause/rift files."""
    with lock:
        running.clear()
        set_pause(False)
        set_rift_movement(False)


def manual_test_scan() -> None:
    """Hotkey [F7] test scan: inspects modals and rift status."""
    global active_cap, active_hwnd
    print("\n--- [MANUAL TEST SCAN (F7)] ---")
    try:
        cap, _, hwnd = resolve_capture_and_input()
        frame = cap.grab_bgr()
        res = detector.detect(frame)
        rift_res = rift_detector.detect(frame)

        target_name = f"Window {hwnd:#x}" if hwnd else "Full Screen"
        print(f"Source: {target_name} ({frame.shape[1]}x{frame.shape[0]})")
        print(f"Modal Detected: {res.modal_type.value} (is_active = {res.is_level_up}, options = {res.option_count})")
        if res.is_level_up:
            choice = selector.decide_choice(res.modal_type, res.option_count)
            print(f"  -> Recommended Choice: [{choice}]")

        print(f"Rift Status: active = {rift_res.is_active} (mode = {rift_res.mode}, scores = {rift_res.scores})")
        if rift_res.is_active:
            print(f"  -> Steering Keys: {rift_res.direction_keys} (Angle: {rift_res.angle_deg}°, Target: {rift_res.target_point})")

        print("-------------------------------\n")
    except Exception as exc:
        print(f"[ERROR] Test scan failed: {exc}\n")


def on_press(key: object) -> bool | None:
    """Global hotkey handler."""
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
    elif key == keyboard.Key.f7:
        manual_test_scan()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="PokéLit Level-Up, Item & Rift Option Selector")
    parser.add_argument(
        "--choice",
        choices=["1", "2", "3", "random", "cycle"],
        default=None,
        help="Perk choice override ('1', '2', '3', 'random', 'cycle')",
    )
    args = parser.parse_args()

    if args.choice:
        selector.strategy = args.choice

    set_pause(False)
    set_rift_movement(False)
    _, _, hwnd = resolve_capture_and_input()

    print("==================================================")
    print("   PokéLit Vision Monitor (Modals + Rift Portal)  ")
    print("==================================================")
    if hwnd:
        print(f"Targeted Window:  HWND {hwnd:#x} (Background Stream Locked)")
    else:
        print("Targeted Window:  Not locked (using desktop capture)")
    print(f"Level-Up Choice:  Option [{selector.strategy.upper()}] (taps 1, 2, or 3)")
    print(f"Item 2-Options:   Option [{selector.item_choice_2}] (always selects 2)")
    print(f"Item 3-Options:   Option [{selector.item_choice_3}] (always selects 3)")
    print(f"Rift Navigation:  {'Enabled (Auto-moves to purple arrow)' if RIFT_ENABLED else 'Disabled'}")
    print("Controls:")
    print("  [F8]  -> Start monitoring")
    print("  [F9]  -> Stop monitoring")
    print("  [F10] -> Quit")
    print("  [F7]  -> Test Scan (check target window right now)")
    print("==================================================")
    print("You can keep PokéLit in the background and use your laptop freely.\n")

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

    stop()
    print("Vision monitor exited cleanly.")


if __name__ == "__main__":
    main()
