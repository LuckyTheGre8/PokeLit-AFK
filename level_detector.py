"""PokéLit In-Game Modal & Rift Navigation Engine.

Features:
1. Level-Up Perk Modal ("Choose a reward" - 3 options: 1, 2, or 3)
   -> Selects configured perk strategy (default: 1)
2. Item Pickup Modal ("An item!" - 2 options: 1: Don't equip, 2: Equip Item)
   -> Always selects 2
3. Item Change / Swap / Lock Modal ("An item!" - 3 options: 1: Keep, 2: Switch, 3: Lock)
   -> Always selects 3
4. Rift Detection & Steering:
   - Physical Purple Rift Portal Tear (on-screen tear with dark core).
   - Purple Arrow Indicator + "RIFT" label (pointing towards off-screen portal).
   - "A RIFT HAS OPENED!" announcement banner.
   - Calculates 8-direction vector from player center to portal/arrow.
   - Disables random controls and steers directly towards the rift.
   - Once inside the rift room (portal/arrow/banner gone), resumes random movement!

Designed for PokéLit running in Chrome/Brave across all resolutions (1024x640 up to 2560x1600).
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

# Ensure Windows DPI awareness so captures reflect physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

try:
    user32 = ctypes.windll.user32
    hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
except Exception:
    pass


class ModalType(str, Enum):
    NONE = "none"
    LEVEL_UP = "level_up"
    ITEM = "item"


@dataclass
class DetectionResult:
    """Result of in-game modal detection check."""
    is_level_up: bool
    confidence: float
    modal_type: ModalType = ModalType.NONE
    recommended_choice: str = "1"
    option_count: int = 0
    scores: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class RiftResult:
    """Result of rift portal detection and navigation vector calculation."""
    is_active: bool
    mode: str = "none"  # "portal_tear", "rift_arrow", "banner_only", or "none"
    direction_keys: list[str] = field(default_factory=list)
    angle_deg: float | None = None
    target_point: tuple[int, int] | None = None
    confidence: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


class ScreenGrabber:
    """Fast screen capture using mss."""

    def __init__(self) -> None:
        import mss
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]  # Primary monitor

    def grab_bgr(self) -> np.ndarray:
        raw = self.sct.grab(self.monitor)
        return np.array(raw, dtype=np.uint8)[:, :, :3]


class LevelUpDetector:
    """Multi-scale template matching detector for PokéLit game modals."""

    def __init__(
        self,
        templates_dir: Path | str | None = None,
        confidence_threshold: float = 0.78,
    ) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent / "templates"
        self.templates_dir = Path(templates_dir)
        self.confidence_threshold = confidence_threshold

        # Level-Up templates
        self.tpl_choose = self._load_template("choose_reward.png")
        self.tpl_level = self._load_template("level_word.png")
        self.tpl_reroll = self._load_template("reroll_word.png")

        # Item Modal templates
        self.tpl_an_item = self._load_template("an_item.png")
        self.tpl_equip_sub = self._load_template("equip_subtitle.png")
        self.tpl_dont_equip = self._load_template("dont_equip.png")
        self.tpl_lock_word = self._load_template("lock_word.png")

        # Multi-scale ratios to handle browser scaling / zoom levels
        self.scales = [0.90, 1.0, 1.10]

    def _load_template(self, filename: str) -> np.ndarray | None:
        path = self.templates_dir / filename
        if not path.exists():
            return None
        return cv2.imread(str(path))

    def _match_best_scale(self, roi: np.ndarray, tpl: np.ndarray | None) -> tuple[float, tuple[int, int]]:
        if tpl is None or roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]:
            return 0.0, (0, 0)
        best_val = 0.0
        best_loc = (0, 0)
        for scale in self.scales:
            t = tpl if scale == 1.0 else cv2.resize(tpl, (0, 0), fx=scale, fy=scale)
            if roi.shape[0] >= t.shape[0] and roi.shape[1] >= t.shape[1]:
                res = cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val > best_val:
                    best_val = float(max_val)
                    best_loc = max_loc
        return round(best_val, 4), best_loc

    def detect(self, frame: np.ndarray) -> DetectionResult:
        """Analyze a frame and detect whether Level-Up or Item modal is open."""
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return DetectionResult(is_level_up=False, confidence=0.0)

        target_w = 1024
        target_h = int(h * (target_w / w))
        norm_frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # Crop central ROI: y: [15%, 85%], x: [30%, 70%]
        y1, y2 = int(target_h * 0.15), int(target_h * 0.85)
        x1, x2 = int(target_w * 0.30), int(target_w * 0.70)
        roi = norm_frame[y1:y2, x1:x2]

        scores: dict[str, float] = {}

        # 1. Check Level-Up Modal
        score_choose, _ = self._match_best_scale(roi, self.tpl_choose)
        score_level, _ = self._match_best_scale(roi, self.tpl_level)
        score_reroll, _ = self._match_best_scale(roi, self.tpl_reroll)

        scores["choose_reward"] = score_choose
        scores["level_word"] = score_level
        scores["reroll_word"] = score_reroll

        is_lvl = (score_choose >= self.confidence_threshold) or (
            score_level >= self.confidence_threshold and score_reroll >= 0.70
        )

        if is_lvl:
            conf = max(score_choose, (score_level + score_reroll) / 2.0)
            return DetectionResult(
                is_level_up=True,
                confidence=round(conf, 4),
                modal_type=ModalType.LEVEL_UP,
                recommended_choice="1",
                option_count=3,
                scores=scores,
            )

        # 2. Check Item Modal
        score_an_item, loc_item = self._match_best_scale(roi, self.tpl_an_item)
        score_equip_sub, _ = self._match_best_scale(roi, self.tpl_equip_sub)
        score_dont_equip, _ = self._match_best_scale(roi, self.tpl_dont_equip)
        score_lock, _ = self._match_best_scale(roi, self.tpl_lock_word)

        scores["an_item"] = score_an_item
        scores["equip_subtitle"] = score_equip_sub
        scores["dont_equip"] = score_dont_equip
        scores["lock_word"] = score_lock

        is_item = (score_an_item >= self.confidence_threshold) or (
            score_equip_sub >= self.confidence_threshold
        ) or (score_dont_equip >= self.confidence_threshold)

        if is_item:
            conf = max(score_an_item, score_equip_sub, score_dont_equip)
            has_3_options = (score_lock >= self.confidence_threshold) or (loc_item[1] < 115 and loc_item[1] > 0)
            opt_count = 3 if has_3_options else 2

            # Rule: 2 options -> always select 2; 3 options -> always select 3
            recommended_choice = "3" if opt_count == 3 else "2"

            return DetectionResult(
                is_level_up=True,
                confidence=round(conf, 4),
                modal_type=ModalType.ITEM,
                recommended_choice=recommended_choice,
                option_count=opt_count,
                scores=scores,
            )

        # No modal detected
        max_noise = max(scores.values()) if scores else 0.0
        return DetectionResult(
            is_level_up=False,
            confidence=round(max_noise, 4),
            modal_type=ModalType.NONE,
            option_count=0,
            scores=scores,
        )


class RiftDetector:
    """Detects physical purple rift portal, announcement banner, and directional compass arrow."""

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent / "templates"
        self.templates_dir = Path(templates_dir)

        self.tpl_banner = self._load_template("rift_banner_text.png")
        self.tpl_rift_text = self._load_template("rift_text_clean.png")
        self.tpl_portal = self._load_template("portal_core.png")

    def _load_template(self, filename: str) -> np.ndarray | None:
        path = self.templates_dir / filename
        if not path.exists():
            return None
        return cv2.imread(str(path))

    def detect(self, frame: np.ndarray) -> RiftResult:
        """Detect purple rift portal/arrow and calculate steering keys from player center."""
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return RiftResult(is_active=False)

        target_w = 1024
        target_h = int(h * (target_w / w))
        norm = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

        scores: dict[str, float] = {}

        # 1. Highest Priority: Physical purple rift portal tear on screen
        play = norm[80:605, :]
        max_vp = 0.0
        if self.tpl_portal is not None and play.shape[0] >= self.tpl_portal.shape[0] and play.shape[1] >= self.tpl_portal.shape[1]:
            res_p = cv2.matchTemplate(play, self.tpl_portal, cv2.TM_CCOEFF_NORMED)
            _, max_val_p, _, max_lp = cv2.minMaxLoc(res_p)
            max_vp = float(max_val_p)
            scores["portal_core"] = round(max_vp, 4)

            if max_vp >= 0.75:
                pw, ph = self.tpl_portal.shape[1], self.tpl_portal.shape[0]
                target_pt = (max_lp[0] + pw // 2, 80 + max_lp[1] + ph // 2)
                keys, angle = self._calc_direction(target_pt, target_w, target_h)
                return RiftResult(
                    is_active=True,
                    mode="portal_tear",
                    direction_keys=keys,
                    angle_deg=angle,
                    target_point=target_pt,
                    confidence=round(max_vp, 4),
                    scores=scores,
                )

        # 2. Purple directional compass arrow + RIFT label pointing towards distant portal
        max_vr = 0.0
        if self.tpl_rift_text is not None and play.shape[0] >= self.tpl_rift_text.shape[0] and play.shape[1] >= self.tpl_rift_text.shape[1]:
            res_r = cv2.matchTemplate(play, self.tpl_rift_text, cv2.TM_CCOEFF_NORMED)
            _, max_val_r, _, max_lr = cv2.minMaxLoc(res_r)
            max_vr = float(max_val_r)
            scores["rift_text"] = round(max_vr, 4)

            if max_vr >= 0.72:
                tx = max_lr[0]
                ty = 80 + max_lr[1]
                # Verify purple cluster in the vicinity (within 80px)
                bx1 = max(0, tx - 60)
                bx2 = min(target_w, tx + 90)
                by1 = max(0, ty - 40)
                by2 = min(target_h, ty + 60)
                sub = norm[by1:by2, bx1:bx2]
                purp = (sub[:, :, 0].astype(int) > sub[:, :, 1].astype(int) + 18) & (
                    sub[:, :, 2].astype(int) > sub[:, :, 1].astype(int) + 10
                )
                if np.sum(purp) >= 80:
                    y_idx, x_idx = np.where(purp)
                    target_pt = (bx1 + int(np.mean(x_idx)), by1 + int(np.mean(y_idx)))
                    keys, angle = self._calc_direction(target_pt, target_w, target_h)
                    return RiftResult(
                        is_active=True,
                        mode="rift_arrow",
                        direction_keys=keys,
                        angle_deg=angle,
                        target_point=target_pt,
                        confidence=round(max_vr, 4),
                        scores=scores,
                    )

        # 3. Announcement Banner ("A RIFT HAS OPENED!")
        max_vb = 0.0
        if self.tpl_banner is not None:
            roi_banner = norm[95:185, 380:645]
            if roi_banner.shape[0] >= self.tpl_banner.shape[0] and roi_banner.shape[1] >= self.tpl_banner.shape[1]:
                res_b = cv2.matchTemplate(roi_banner, self.tpl_banner, cv2.TM_CCOEFF_NORMED)
                _, max_val_b, _, _ = cv2.minMaxLoc(res_b)
                max_vb = float(max_val_b)
                scores["banner"] = round(max_vb, 4)
                if max_vb >= 0.75:
                    return RiftResult(
                        is_active=True,
                        mode="banner_only",
                        direction_keys=["s"],
                        angle_deg=90.0,
                        target_point=(target_w // 2, target_h),
                        confidence=round(max_vb, 4),
                        scores=scores,
                    )

        return RiftResult(
            is_active=False,
            mode="none",
            direction_keys=[],
            angle_deg=None,
            target_point=None,
            confidence=round(max(max_vp, max_vr, max_vb), 4),
            scores=scores,
        )

    def _calc_direction(self, target_pt: tuple[int, int], w: int, h: int) -> tuple[list[str], float]:
        cx, cy = w // 2, h // 2
        dx = target_pt[0] - cx
        dy = target_pt[1] - cy
        angle = math.degrees(math.atan2(dy, dx))

        if -22.5 <= angle < 22.5:
            return ["d"], round(angle, 1)
        elif 22.5 <= angle < 67.5:
            return ["s", "d"], round(angle, 1)
        elif 67.5 <= angle < 112.5:
            return ["s"], round(angle, 1)
        elif 112.5 <= angle < 157.5:
            return ["s", "a"], round(angle, 1)
        elif angle >= 157.5 or angle < -157.5:
            return ["a"], round(angle, 1)
        elif -157.5 <= angle < -112.5:
            return ["w", "a"], round(angle, 1)
        elif -112.5 <= angle < -67.5:
            return ["w"], round(angle, 1)
        elif -67.5 <= angle < -22.5:
            return ["w", "d"], round(angle, 1)

        return ["d"], round(angle, 1)


class PerkSelector:
    """Handles option choices for Level-Up (1,2,3), Item 2-opt (select 2), and Item 3-opt (select 3)."""

    def __init__(
        self,
        strategy: Literal["1", "2", "3", "random", "cycle"] = "1",
        key_hold_seconds: float = 0.08,
        priority_list: list[str] | None = None,
        item_choice_2: str = "2",
        item_choice_3: str = "3",
    ) -> None:
        from pynput import keyboard
        import pyautogui

        self.strategy = strategy
        self.key_hold_seconds = key_hold_seconds
        self.priority_list = priority_list or []
        self.item_choice_2 = item_choice_2
        self.item_choice_3 = item_choice_3
        self.cycle_index = 0
        self.kb = keyboard.Controller()
        self.pyautogui = pyautogui

    def decide_choice(self, modal_type: ModalType = ModalType.LEVEL_UP, option_count: int = 3) -> str:
        """Determine key to press based on modal type and option count."""
        if modal_type == ModalType.ITEM:
            if option_count == 3:
                return self.item_choice_3
            return self.item_choice_2

        strat = str(self.strategy).lower()
        if strat in ("1", "2", "3"):
            return strat
        elif strat == "random":
            return random.choice(["1", "2", "3"])
        elif strat == "cycle":
            keys = ["1", "2", "3"]
            choice = keys[self.cycle_index % 3]
            self.cycle_index += 1
            return choice

        return "1"

    def tap_choice(self, key_str: str) -> None:
        """Reliably press and release key 1, 2, or 3."""
        if key_str not in ("1", "2", "3"):
            key_str = "1"

        self.kb.press(key_str)
        self.pyautogui.keyDown(key_str)
        time.sleep(self.key_hold_seconds)
        self.kb.release(key_str)
        self.pyautogui.keyUp(key_str)
