"""Unified Launcher: Runs random_movement.py and perk_selector.py in Window-Targeted Mode."""

from __future__ import annotations

import argparse
import sys
import threading
import time

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
    args = parser.parse_args()

    if args.choice:
        perk_selector.selector.strategy = args.choice

    hwnd = find_target_window("pokelit")
    pattern_str = " -> ".join(k.upper() for k in random_movement.KEYS) + " -> " + random_movement.KEYS[0].upper()

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
    print(f"Movement:         {pattern_str} ({random_movement.MIN_SECONDS}s-{random_movement.MAX_SECONDS}s)")
    print(f"Perk Strategy:    [{perk_selector.selector.strategy.upper()}] (Presses 1, 2, or 3)")
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
