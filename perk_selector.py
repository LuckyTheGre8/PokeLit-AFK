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

from level_detector import (
    AutoVigorDetector,
    AutoVigorResult,
    DetectionResult,
    GameTimerDetector,
    GameTimerResult,
    LevelUpDetector,
    MenuDetectionResult,
    MenuNavigatorDetector,
    MenuScreenType,
    ModalType,
    PerkSelector,
    RiftDetector,
    RiftResult,
    ScreenGrabber,
)
from spatial_navigator import SpatialNavigator, SpatialNavResult
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
        "auto_vigor": {
            "enabled": True,
            "trigger_minutes": 10.0,
            "use_game_timer": True,
        },
        "auto_restart": {
            "enabled": True,
            "region": "johto",
            "post_click_delay_seconds": 1.2,
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

AV_CFG = CONFIG.get("auto_vigor", {})
AV_ENABLED = AV_CFG.get("enabled", True)
AV_TRIGGER_MIN = float(AV_CFG.get("trigger_minutes", 10.0))
AV_USE_GAME_TIMER = AV_CFG.get("use_game_timer", True)

AR_CFG = CONFIG.get("auto_restart", {})
AR_ENABLED = AR_CFG.get("enabled", True)
AR_REGION = str(AR_CFG.get("region", "johto")).lower()
if AR_REGION == "jhoto":
    AR_REGION = "johto"
AR_DELAY = float(AR_CFG.get("post_click_delay_seconds", 1.2))

running = threading.Event()
shutdown = threading.Event()
lock = threading.Lock()
monitor_thread: threading.Thread | None = None

detector = LevelUpDetector(confidence_threshold=CONF_THRESH)
rift_detector = RiftDetector()
timer_detector = GameTimerDetector()
auto_vigor_detector = AutoVigorDetector()
menu_detector = MenuNavigatorDetector(target_region=AR_REGION)
spatial_nav = SpatialNavigator()

match_start_time: float = time.monotonic()
auto_vigor_active: bool = False
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


def execute_click(norm_x: int, norm_y: int) -> None:
    """Click at normalized coordinate on target window or screen with physical DPI and aspect scaling."""
    global active_hwnd, active_win_input

    if active_hwnd and active_win_input:
        rect = wintypes.RECT()
        user32.GetClientRect(active_hwnd, ctypes.byref(rect))
        cw = max(1, rect.right - rect.left)
        ch = max(1, rect.bottom - rect.top)

        # Scale uniformly matching frame normalization (target_w=1024, target_h=int(h * (1024/w)))
        scale = cw / 1024.0
        client_x = int(norm_x * scale)
        client_y = int(norm_y * scale)
        screen_x, screen_y = active_win_input.client_to_screen(client_x, client_y)

        if FOCUS_FLICK:
            prev_fg = user32.GetForegroundWindow()
            try:
                user32.SetForegroundWindow(active_hwnd)
                time.sleep(0.06)
                # Physical mouse down with 80ms hold duration for HTML5 canvas/WebGL events
                pyautogui.moveTo(screen_x, screen_y)
                time.sleep(0.02)
                pyautogui.mouseDown(screen_x, screen_y, button="left")
                time.sleep(0.08)
                pyautogui.mouseUp(screen_x, screen_y, button="left")
                # Win32 PostMessage backup
                active_win_input.click(client_x, client_y)
                time.sleep(0.08)
            finally:
                if prev_fg and prev_fg != active_hwnd:
                    user32.SetForegroundWindow(prev_fg)
        else:
            active_win_input.click(client_x, client_y)
    else:
        sw, sh = pyautogui.size()
        scale = sw / 1024.0
        screen_x = int(norm_x * scale)
        screen_y = int(norm_y * scale)
        pyautogui.moveTo(screen_x, screen_y)
        time.sleep(0.02)
        pyautogui.mouseDown(screen_x, screen_y, button="left")
        time.sleep(0.08)
        pyautogui.mouseUp(screen_x, screen_y, button="left")


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
    print(f"Rift Navigation:   {'ENABLED (Auto-steers to purple arrow/tear)' if RIFT_ENABLED else 'DISABLED'}")
    print(f"Auto Vigor:        {'ENABLED (Activates at 10:00 on timer)' if AV_ENABLED else 'DISABLED'}")
    print(f"Auto Restart:      {'ENABLED (Back to menu -> Play -> ' + AR_REGION.capitalize() + ')' if AR_ENABLED else 'DISABLED'}")
    print("Press [F9] to stop | [F7] for test scan.\n")

    modals_handled = 0
    rift_active_logged = False
    last_rift_seen_time = 0.0
    last_vigor_toggle_time = 0.0
    global auto_vigor_active
    past_10m_latched = False
    early_timer_streak = 0

    try:
        while running.is_set() and not shutdown.is_set():
            time.sleep(POLL_INTERVAL)

            if not running.is_set() or shutdown.is_set():
                break

            try:
                frame = active_cap.grab_bgr()

                # 0. Menu & Match End Navigation ("Run over" -> "Back to menu" -> "Play" -> "Kanto")
                if AR_ENABLED:
                    menu_res: MenuDetectionResult = menu_detector.detect(frame)
                    if menu_res.screen_type != MenuScreenType.NONE and menu_res.click_point:
                        set_pause(True)
                        set_rift_movement(False)

                        if menu_res.screen_type == MenuScreenType.RUN_OVER:
                            print(f"\n==================================================")
                            print(f" [RUN OVER DETECTED] Match has ended!")
                            print(f" -> Clicking 'Back to menu' button at {menu_res.click_point}...")
                            execute_click(menu_res.click_point[0], menu_res.click_point[1])
                            time.sleep(AR_DELAY)
                            print("==================================================\n")
                            continue

                        elif menu_res.screen_type == MenuScreenType.MAIN_MENU:
                            print(f"\n==================================================")
                            print(f" [MAIN MENU DETECTED]")
                            print(f" -> Clicking 'Play' (Enter dungeon) at {menu_res.click_point}...")
                            execute_click(menu_res.click_point[0], menu_res.click_point[1])
                            time.sleep(AR_DELAY)
                            print("==================================================\n")
                            continue

                        elif menu_res.screen_type == MenuScreenType.CHOOSE_REGION:
                            print(f"\n==================================================")
                            print(f" [CHOOSE REGION DETECTED]")
                            print(f" -> Selecting '{AR_REGION.capitalize()}' region at {menu_res.click_point}...")
                            execute_click(menu_res.click_point[0], menu_res.click_point[1])
                            print(f" -> Starting new match in {AR_REGION.capitalize()} (waiting 2.5s)...")
                            time.sleep(2.5)

                            # Reset match start time and Auto Vigor flag for the fresh game
                            match_start_time = time.monotonic()
                            auto_vigor_active = False
                            past_10m_latched = False
                            early_timer_streak = 0

                            set_pause(False)
                            print(f" [NEW MATCH STARTED] Movement and perk selection active!")
                            print("==================================================\n")
                            continue

                # 1. First priority: Check for Level-Up or Item Modal
                result: DetectionResult = detector.detect(frame)

                if result.is_level_up:
                    # Do NOT clear rift navigation file; only pause movement so rift heading is retained!
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

                    # Seamless Rift Continuation: re-verify rift portal/arrow BEFORE unpausing
                    if RIFT_ENABLED:
                        fresh_frame = active_cap.grab_bgr()
                        fresh_rift = rift_detector.detect(fresh_frame)
                        if fresh_rift.is_active and fresh_rift.direction_keys:
                            set_rift_movement(True, fresh_rift.direction_keys, fresh_rift.angle_deg)
                            print(f" -> Rift path preserved: Steering {fresh_rift.direction_keys} (Angle: {fresh_rift.angle_deg}°)")
                        else:
                            set_rift_movement(False)

                    set_pause(False)
                    print(" Resuming movement loop.")
                    print("==================================================\n")
                    continue

                # 2. Check Auto Vigor state:
                # Rule: For the first 10 minutes on the timer, Auto Vigor MUST BE OFF (so bot selects level-up perks 1/2/3).
                #       After 10:00 on the timer, Auto Vigor MUST BE ON (so game selects level-ups automatically).
                if AV_ENABLED:
                    is_past_10m = past_10m_latched
                    timer_is_valid = False

                    if AV_USE_GAME_TIMER:
                        t_res = timer_detector.detect(frame)
                        if t_res.detected:
                            timer_is_valid = True
                            if t_res.is_at_least_10_min:
                                past_10m_latched = True
                                is_past_10m = True
                                early_timer_streak = 0
                            else:
                                early_timer_streak += 1
                                if early_timer_streak >= 15:  # ~1.8s of consistent early timer unlatches
                                    past_10m_latched = False
                                    is_past_10m = False

                    if not is_past_10m and not timer_is_valid:
                        elapsed_min = (time.monotonic() - match_start_time) / 60.0
                        if elapsed_min >= AV_TRIGGER_MIN:
                            past_10m_latched = True
                            is_past_10m = True

                    av_res = auto_vigor_detector.detect(frame)
                    now_v = time.monotonic()
                    if av_res.is_present and (now_v - last_vigor_toggle_time >= 2.0):
                        if not is_past_10m:
                            # BEFORE 10 MINUTES: Auto Vigor MUST be OFF so the bot can choose perks
                            auto_vigor_active = False
                            if av_res.is_active:
                                last_vigor_toggle_time = now_v
                                print(f"\n==================================================")
                                print(f"[AUTO VIGOR] Timer is under 10:00, but Auto Vigor is currently ON (pink)!")
                                print(f"Turning Auto Vigor OFF so the bot selects perks according to strategy [{selector.strategy}]...")
                                set_pause(True)
                                time.sleep(0.08)
                                execute_click(av_res.norm_point[0], av_res.norm_point[1])
                                time.sleep(0.35)
                                check_frame = active_cap.grab_bgr()
                                check_av = auto_vigor_detector.detect(check_frame)
                                if not check_av.is_active:
                                    print(f"[AUTO VIGOR] Auto Vigor successfully turned OFF for early game perk selection!")
                                else:
                                    print(f"[AUTO VIGOR] Retrying click to turn OFF...")
                                    execute_click(av_res.norm_point[0], av_res.norm_point[1])
                                    time.sleep(0.35)
                                set_pause(False)
                                print(f"==================================================\n")
                        else:
                            # AT OR AFTER 10 MINUTES: Auto Vigor MUST be ON so gameplay is uninterrupted
                            if not av_res.is_active:
                                last_vigor_toggle_time = now_v
                                print(f"\n==================================================")
                                print(f"[AUTO VIGOR TRIGGERED] 10 minute mark reached! In-game timer >= 10:00.")
                                print(f"Clicking AUTO VIGOR button at normalized {av_res.norm_point} to turn ON...")
                                set_pause(True)
                                time.sleep(0.08)
                                execute_click(av_res.norm_point[0], av_res.norm_point[1])
                                time.sleep(0.35)
                                check_frame = active_cap.grab_bgr()
                                check_av = auto_vigor_detector.detect(check_frame)
                                if check_av.is_active:
                                    auto_vigor_active = True
                                    print(f"[AUTO VIGOR ENABLED] Auto Vigor successfully turned on (AUTO VIGOR ON confirmed)!")
                                    print(f"All future level-ups will now be selected automatically by the game.")
                                else:
                                    print(f"[AUTO VIGOR] Retrying click on AUTO VIGOR button to turn ON...")
                                    execute_click(av_res.norm_point[0], av_res.norm_point[1])
                                    time.sleep(0.35)
                                    check_frame2 = active_cap.grab_bgr()
                                    check_av2 = auto_vigor_detector.detect(check_frame2)
                                    if check_av2.is_active:
                                        auto_vigor_active = True
                                        print(f"[AUTO VIGOR ENABLED] Auto Vigor successfully turned on on retry!")
                                        print(f"All future level-ups will now be selected automatically by the game.")
                                set_pause(False)
                                print(f"==================================================\n")
                            else:
                                auto_vigor_active = True

                # 3. Third priority: Rift Detection & Navigation (Top Gameplay Priority)
                if RIFT_ENABLED:
                    rift_res: RiftResult = rift_detector.detect(frame)
                    if rift_res.is_active and rift_res.direction_keys:
                        last_rift_seen_time = time.monotonic()
                        if not rift_active_logged:
                            rift_active_logged = True
                            desc = "Physical Portal Tear" if rift_res.mode == "portal_tear" else ("Arrow indicator" if rift_res.mode == "rift_arrow" else "Banner")
                            print(f"[RIFT DETECTED - TOP PRIORITY] {desc} found at {rift_res.target_point} -> Steering {rift_res.direction_keys} (Angle: {rift_res.angle_deg}°)")
                        set_rift_movement(True, rift_res.direction_keys, rift_res.angle_deg)
                    else:
                        if time.monotonic() - last_rift_seen_time > 0.4:
                            if rift_active_logged:
                                rift_active_logged = False
                                print("[RIFT ENDED] Portal / Arrow cleared. Returning to normal movement.")
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
    global monitor_thread, active_cap, active_win_input, active_hwnd, match_start_time, auto_vigor_active
    with lock:
        if running.is_set():
            print("[INFO] Monitor is already running.")
            return

        match_start_time = time.monotonic()
        auto_vigor_active = False
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

        t_res = timer_detector.detect(frame)
        av_res = auto_vigor_detector.detect(frame)
        m_res = menu_detector.detect(frame)
        s_res = spatial_nav.analyze(frame)
        print(f"Game Timer: detected = {t_res.detected}, minutes_cat = {t_res.minutes_category}, is_at_least_10_min = {t_res.is_at_least_10_min}")
        print(f"Auto Vigor: present = {av_res.is_present}, is_active = {av_res.is_active}, norm_point = {av_res.norm_point}")
        print(f"Menu Screen: {m_res.screen_type.value} (conf = {m_res.confidence}, click = {m_res.click_point})")
        print(f"Spatial AI: mode = {s_res.mode}, keys = {s_res.direction_keys}, gems = {s_res.gems_detected}, max_threat = {s_res.max_threat_percent}%")

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
