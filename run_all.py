"""Unified Launcher: Runs random_movement.py and perk_selector.py in Window-Targeted Mode."""

from __future__ import annotations

import argparse
import ctypes
import sys
import threading
import time

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

import perk_selector
import random_movement
from window_stream import find_target_window


def main():
    parser = argparse.ArgumentParser(description="PokéLit Bot: Run Movement + Perk Selector (Targeted Mode)")
    parser.add_argument(
        "--choice",
        choices=["1", "2", "3", "random", "cycle"],
        default=None,
        help="Perk choice override ('1', '2', '3', 'random', 'cycle')",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Region override (1-10 or region name, e.g. '4', 'sinnoh', 'hoenn')",
    )
    args = parser.parse_args()

    if args.choice:
        perk_selector.selector.strategy = args.choice

    if args.region:
        perk_selector.set_target_region(args.region, persist_to_config=True)
    else:
        perk_selector.prompt_region_selection(perk_selector.AR_REGION)

    hwnd = find_target_window("pokelit")
    pattern_str = " -> ".join(k.upper() for k in random_movement.KEYS) + " -> " + random_movement.KEYS[0].upper()

    cur_region_num = perk_selector.get_region_num(perk_selector.AR_REGION)
    cur_region_name = perk_selector.get_region_display_name(perk_selector.AR_REGION)

    print("==================================================")
    print("      PokéLit Full AFK Bot (Targeted Stream)      ")
    print("==================================================")
    if hwnd:
        print(f"Targeted Window:  HWND {hwnd:#x}")
        print("                  -> Input:  Only sent to PokéLit")
        print("                  -> Output: Only captures PokéLit")
        print("                  -> You can use your laptop in the foreground!")
    else:
        print("Targeted Window:  Not found (using global fallback)")
    print(f"Target Region:    [{cur_region_num}] {cur_region_name} (Loop Selection)")
    print(f"Movement:         {pattern_str} ({random_movement.MIN_SECONDS}s-{random_movement.MAX_SECONDS}s)")
    print(f"Perk Strategy:    [{perk_selector.selector.strategy.upper()}] (Presses 1, 2, or 3)")
    print(f"Rift Navigation:  {'Enabled (High Priority)' if perk_selector.RIFT_ENABLED else 'Disabled'}")
    chest_enabled = random_movement.CONFIG.get("chest_navigation", {}).get("enabled", True)
    print(f"Chest Auto-Open:  {'Enabled (6.5s Hold)' if chest_enabled else 'Disabled'}")
    print("Controls:")
    print("  [F8]  -> Start Bot (Movement + Auto Perk Selector)")
    print("  [F9]  -> Emergency Stop")
    print("  [F10] -> Quit")
    print("  [F7]  -> Test Scan (check target window detection)")
    print("==================================================")
    print("Press [F8] to start both streams!\n")

    def on_press(key: object) -> bool | None:
        if key == keyboard.Key.f8:
            random_movement.start()
            perk_selector.start()
        elif key == keyboard.Key.f9:
            print("\n[EMERGENCY STOP] F9 pressed.")
            random_movement.stop()
            perk_selector.stop()
        elif key == keyboard.Key.f10:
            print("\n[EXIT] F10 pressed; shutting down...")
            random_movement.stop()
            perk_selector.stop()
            random_movement.shutdown.set()
            perk_selector.shutdown.set()
            return False
        elif key == keyboard.Key.f7:
            perk_selector.manual_test_scan()
        return None

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()

    random_movement.stop()
    perk_selector.stop()
    print("All bot routines exited cleanly.")


if __name__ == "__main__":
    main()
