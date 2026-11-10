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

import ctypes
import json
import os
import random
import threading
import time
from pathlib import Path

# Ensure Windows DPI awareness so all Win32 APIs, GetClientRect, ClientToScreen, and PyAutoGUI use physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
from pynput import keyboard

from window_stream import WindowCapture, WindowInput, find_target_window
from level_detector import ScreenGrabber
from spatial_navigator import SpatialNavigator, SpatialNavResult

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
        "min_hold_seconds": 0.8,
        "max_hold_seconds": 2.2,
        "repeat_interval_seconds": 0.035,
        "switch_breather_seconds": 0.02,
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

SPATIAL_CFG = CONFIG.get("spatial_ai", {})
SPATIAL_ENABLED = SPATIAL_CFG.get("enabled", True)
GEM_WEIGHT = float(SPATIAL_CFG.get("gem_weight", 1.2))
THREAT_WEIGHT = float(SPATIAL_CFG.get("threat_weight", 2.4))
KITE_WEIGHT = float(SPATIAL_CFG.get("kite_weight", 0.9))
DANGER_THRESHOLD = float(SPATIAL_CFG.get("danger_threshold", 12.0))

spatial_nav = SpatialNavigator(
    gem_weight=GEM_WEIGHT,
    threat_weight=THREAT_WEIGHT,
    kite_weight=KITE_WEIGHT,
    danger_threshold=DANGER_THRESHOLD,
)

kb = keyboard.Controller()

running = threading.Event()
shutdown = threading.Event()
lock = threading.Lock()
worker_thread: threading.Thread | None = None
active_win_input: WindowInput | None = None
active_cap: WindowCapture | ScreenGrabber | None = None


def resolve_capture_and_input() -> tuple[WindowCapture | ScreenGrabber | None, WindowInput | None]:
    """Find target window and return (WindowCapture, WindowInput) if enabled."""
    if not TARGET_ENABLED:
        return ScreenGrabber(), None
    hwnd = MANUAL_HWND or find_target_window(TITLE_KEYWORD)
    if hwnd:
        try:
            cap = WindowCapture(hwnd)
            inp = WindowInput(hwnd)
            return cap, inp
        except Exception:
            pass
    return ScreenGrabber(), None


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
    """Movement loop alternating between real-time Spatial AI navigation and classic loop."""
    global active_win_input, active_cap
    pattern_str = " -> ".join(k.upper() for k in KEYS) + " -> " + KEYS[0].upper()

    if active_win_input:
        target_info = f"Window HWND: {active_win_input.hwnd:#x}"
        print(f"\n[ACTIVE] Targeted Background Movement started! ({target_info})")
    else:
        print("\n[ACTIVE] Global Movement started (Game window not locked)!")

    if SPATIAL_ENABLED and active_cap:
        print("Movement Mode:    AI SPATIAL NAVIGATION (Dynamic Kiting & Gem Harvesting)")
    else:
        print(f"Movement Mode:    CLASSIC WASD LOOP ({pattern_str})")
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
    last_rift_time = 0.0
    last_mode = ""
    last_mode_log_time = 0.0
    last_key_flush_time = 0.0
    active_keys_held: set[str] = set()
    opposing_keys = {"w": "s", "s": "w", "a": "d", "d": "a"}

    try:
        while running.is_set() and not shutdown.is_set():
            # 1. Check if paused for modal selection (level-up or item)
            if PAUSE_FILE.exists():
                if active_keys_held:
                    release_all_keys()
                    active_keys_held.clear()
                last_rift_time = time.monotonic()  # Freeze rift grace window during modal pause
                time.sleep(0.05)
                continue

            # 2. Check for active rift navigation signal
            rift_info = read_rift_movement()
            rift_keys = rift_info[0] if rift_info else None
            if rift_keys:
                last_rift_time = time.monotonic()

            # 3. Real-Time Spatial AI Navigation (Continuous Fluid Movement)
            if SPATIAL_ENABLED and active_cap:
                try:
                    frame = active_cap.grab_bgr()
                    res: SpatialNavResult = spatial_nav.analyze(frame, rift_direction_keys=rift_keys)
                    target_keys = set(res.direction_keys)

                    if res.mode == "rift_push":
                        last_rift_time = time.monotonic()

                    now = time.monotonic()
                    if res.mode != last_mode or (now - last_mode_log_time > 8.0):
                        last_mode = res.mode
                        last_mode_log_time = now
                        if res.mode == "kiting_evasion":
                            print(f"[AI KITING] Threat: {res.max_threat_percent}% -> Kiting: {res.direction_keys} (Heading: {res.heading_angle_deg}°)")
                        elif res.mode == "gem_hunting":
                            print(f"[AI GEMS] Vacuuming {res.gems_detected} XP gems -> Steering: {res.direction_keys} (Heading: {res.heading_angle_deg}°)")
                        elif res.mode == "rift_push":
                            print(f"[AI RIFT - TOP PRIORITY] Dynamically tracking Rift Arrow / Portal: {res.direction_keys} (Heading: {res.heading_angle_deg}°)")
                        elif res.mode == "unstuck_escape":
                            print(f"[AI UNSTUCK] Obstacle detected! Sliding {res.direction_keys} (Heading: {res.heading_angle_deg}°) to bypass obstacle")
                        elif res.mode == "patrol":
                            print(f"[AI PATROL] Field clear -> Cruising: {res.direction_keys}")

                    # Release keys no longer part of target direction, PLUS any opposing keys
                    to_release = active_keys_held - target_keys
                    for tk in target_keys:
                        opp = opposing_keys.get(tk)
                        if opp:
                            to_release.add(opp)

                    # Periodic hygiene flush: ensure no stale ghost keys are held in background
                    if now - last_key_flush_time > 1.5:
                        last_key_flush_time = now
                        for non_k in set(KEYS) - target_keys:
                            to_release.add(non_k)

                    for k in to_release:
                        if active_win_input:
                            active_win_input.key_up(k)
                        else:
                            kb.release(k)
                            pyautogui.keyUp(k)
                        active_keys_held.discard(k)

                    # Press newly added direction keys
                    to_press = target_keys - active_keys_held
                    for k in to_press:
                        if active_win_input:
                            active_win_input.key_down(k, is_repeat=False)
                        else:
                            kb.press(k)
                            pyautogui.keyDown(k)

                    # Maintain continuous hold via typematic repeat pulse (with is_repeat flag)
                    for k in target_keys:
                        if active_win_input:
                            active_win_input.key_down(k, is_repeat=True)

                    active_keys_held = set(target_keys)
                    time.sleep(REPEAT_INTERVAL)
                    continue
                except Exception:
                    pass

            # Release spatial keys if falling through to classic mode
            if active_keys_held:
                release_all_keys()
                active_keys_held.clear()

            # 4. Fallback: Classic Movement Loop
            if rift_info:
                target_fallback_keys = set(rift_keys or [])
                if not rift_mode_active:
                    rift_mode_active = True
                    release_all_keys()
                    ang_str = f" (Angle: {rift_info[1]}°)" if rift_info[1] is not None else ""
                    print(f"\n>>> [RIFT NAVIGATION STARTED] Arrow/Portal detected! Steering: {rift_keys}{ang_str}")

                t_end = time.monotonic() + 0.10
                while running.is_set() and not shutdown.is_set() and time.monotonic() < t_end:
                    if PAUSE_FILE.exists() or not RIFT_FILE.exists():
                        break

                    # Re-read rift info dynamically so heading updates if arrow rotates
                    fresh_rift = read_rift_movement()
                    if fresh_rift and fresh_rift[0]:
                        new_keys = set(fresh_rift[0])
                        # Release keys no longer in target
                        for old_k in target_fallback_keys - new_keys:
                            if active_win_input:
                                active_win_input.key_up(old_k)
                            else:
                                kb.release(old_k)
                                pyautogui.keyUp(old_k)
                        target_fallback_keys = new_keys

                    for rk in target_fallback_keys:
                        if active_win_input:
                            active_win_input.key_down(rk)
                        else:
                            kb.press(rk)
                            pyautogui.keyDown(rk)

                    time.sleep(REPEAT_INTERVAL)

                continue

            if rift_mode_active:
                if time.monotonic() - last_rift_time < 0.6:
                    time.sleep(0.04)
                    continue

                rift_mode_active = False
                release_all_keys()
                print("\n<<< [RIFT NAVIGATION ENDED] Portal / Arrow cleared. Resuming random movement loop.\n")

            key = KEYS[index % len(KEYS)]
            index += 1

            duration = round(random.uniform(MIN_SECONDS, MAX_SECONDS), 2)
            print(f" -> [{index}] Holding [{key.upper()}] for {duration:.2f}s...")

            deadline = time.monotonic() + duration

            while running.is_set() and not shutdown.is_set() and time.monotonic() < deadline:
                if PAUSE_FILE.exists() or RIFT_FILE.exists():
                    release_all_keys()
                    break

                if active_win_input:
                    active_win_input.key_down(key)
                else:
                    kb.press(key)
                    pyautogui.keyDown(key)

                time.sleep(REPEAT_INTERVAL)

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
        active_keys_held.clear()
        release_all_keys()
        running.clear()
        print("\n[STOPPED] Movement loop stopped. All keys released.\n")


def start() -> None:
    """Start movement worker thread."""
    global worker_thread, active_win_input, active_cap
    with lock:
        if running.is_set():
            print("[INFO] Movement is already running.")
            return

        active_cap, active_win_input = resolve_capture_and_input()
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
    cap, target = resolve_capture_and_input()
    print("==================================================")
    print("     PokéLit AI Movement Runner (Spatial AI)      ")
    print("==================================================")
    if target:
        print(f"Targeted Window:  HWND {target.hwnd:#x} (Background Stream Active)")
        print("                  -> Keystrokes go ONLY to PokéLit!")
    else:
        print("Targeted Window:  Not locked (using global inputs)")
    print(f"Spatial AI Nav:   {'ENABLED (Enemy Kiting & Gem Harvesting)' if SPATIAL_ENABLED else 'DISABLED'}")
    print(f"Hold Interval:    {MIN_SECONDS}s to {MAX_SECONDS}s per direction")
    print("Controls:         [F8] Start | [F9] Emergency Stop | [F10] Quit")
    print("==================================================\n")
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
