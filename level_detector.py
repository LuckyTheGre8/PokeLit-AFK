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


class MenuScreenType(str, Enum):
    NONE = "none"
    RUN_OVER = "run_over"
    MAIN_MENU = "main_menu"
    CHOOSE_REGION = "choose_region"
    SUBMENU_BACK = "submenu_back"


@dataclass
class MenuDetectionResult:
    """Result of end-of-match / menu navigation screen detection."""
    screen_type: MenuScreenType = MenuScreenType.NONE
    click_point: tuple[int, int] | None = None
    confidence: float = 0.0


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


@dataclass
class GameTimerResult:
    """Result of in-game timer detection at top center."""
    detected: bool = False
    minutes_category: int | None = None  # 0 for < 10m, 10 for >= 10m
    is_at_least_10_min: bool = False


@dataclass
class AutoVigorResult:
    """Result of Auto Level / Auto Vigor button detection and state evaluation."""
    is_present: bool = False
    is_active: bool = False  # True if button is in active state (bright yellow or active pink)
    norm_point: tuple[int, int] | None = None  # (click_x, click_y) in normalized 1024x640 frame
    confidence: float = 0.0
    theme: str = "yellow"  # "yellow" for AUTO LEVEL, "pink" for legacy AUTO VIGOR


AutoLevelResult = AutoVigorResult


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
        self.tpl_arrow_above = self._load_template("arrow_above_portal.png")

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

        # 0. Check overall screen black ratio: menus and modals have > 18% black void
        v_all = np.max(norm, axis=2)
        black_ratio = (v_all < 15).sum() / (target_w * target_h)
        scores["black_ratio"] = round(float(black_ratio), 4)
        if black_ratio > 0.18:
            return RiftResult(
                is_active=False,
                mode="none",
                direction_keys=[],
                angle_deg=None,
                target_point=None,
                confidence=0.0,
                scores=scores,
            )

        # 1. TOP PRIORITY: Physical purple rift portal tear on screen
        # Detected via color-spatial morphology: dense purple aura enclosing a dark vertical void
        ui = np.ones((target_h, target_w), dtype=bool)
        ui[:80, :] = False       # Top bar & in-game timer
        ui[:220, :320] = False   # Mewtwo card & stats
        ui[610:, :] = False      # Bottom edge task banner

        b, g, r = cv2.split(norm)
        bgr_purp = (b.astype(int) > g.astype(int) + 16) & (r.astype(int) > g.astype(int) + 8)
        hsv = cv2.cvtColor(norm, cv2.COLOR_BGR2HSV)
        hsv_purp = (hsv[:, :, 0] >= 115) & (hsv[:, :, 0] <= 170) & (hsv[:, :, 1] >= 35) & (hsv[:, :, 2] >= 35)
        mask = bgr_purp & hsv_purp & ui

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8) * 255)
        best_portal = None
        best_portal_score = 0.0

        for i in range(1, num_labels):
            px, py, pw, ph, area = stats[i]
            # Adaptive physical portal tear: detect tall vertical tears early as they enter screen (ph >= 45, pw >= 30, area >= 1200)
            if area >= 1200 and pw >= 30 and ph >= 45:
                ar = ph / float(pw)
                if 1.15 <= ar <= 3.2:
                    pad = 12
                    sub = norm[max(0, py - pad) : min(target_h, py + ph + pad), max(0, px - pad) : min(target_w, px + pw + pad)]
                    dark_px = int((np.max(sub, axis=2) < 45).sum())
                    sh, sw = sub.shape[:2]
                    cw1, cw2 = int(sw * 0.30), int(sw * 0.70)
                    ch1, ch2 = int(sh * 0.20), int(sh * 0.80)
                    center_box = sub[ch1:ch2, cw1:cw2]
                    dark_in_center = (np.max(center_box, axis=2) < 45).sum()
                    center_ratio = dark_in_center / float(max(1, (cw2 - cw1) * (ch2 - ch1)))
                    # True void core requires contiguous dark pixels in center of tear (rejects solid purple mobs)
                    if dark_px >= 250 and center_ratio >= 0.15:
                        score = area + dark_px * 2.0
                        if score > best_portal_score:
                            best_portal_score = score
                            best_portal = (int(centroids[i][0]), int(centroids[i][1]), area, dark_px)

        if best_portal:
            cx, cy, a, d = best_portal
            keys, angle = self._calc_direction((cx, cy), target_w, target_h)
            scores["portal_area"] = float(a)
            scores["portal_dark_core"] = float(d)
            return RiftResult(
                is_active=True,
                mode="portal_tear",
                direction_keys=keys,
                angle_deg=angle,
                target_point=(cx, cy),
                confidence=round(min(1.0, best_portal_score / 6000.0), 4),
                scores=scores,
            )

        # 1b. Floating Beacon Arrow above physical portal (pointing down into portal)
        play = norm[60:625, :]
        max_va = 0.0
        if self.tpl_arrow_above is not None and play.shape[0] >= self.tpl_arrow_above.shape[0] and play.shape[1] >= self.tpl_arrow_above.shape[1]:
            res_a = cv2.matchTemplate(play, self.tpl_arrow_above, cv2.TM_CCOEFF_NORMED)
            _, max_val_a, _, max_la = cv2.minMaxLoc(res_a)
            max_va = float(max_val_a)
            scores["arrow_above_portal"] = round(max_va, 4)

            if max_va >= 0.75:
                aw, ah = self.tpl_arrow_above.shape[1], self.tpl_arrow_above.shape[0]
                target_pt = (max_la[0] + aw // 2, min(target_h - 10, 60 + max_la[1] + ah // 2 + 50))
                keys, angle = self._calc_direction(target_pt, target_w, target_h)
                return RiftResult(
                    is_active=True,
                    mode="portal_tear",
                    direction_keys=keys,
                    angle_deg=angle,
                    target_point=target_pt,
                    confidence=round(max_va, 4),
                    scores=scores,
                )

        # 1c. Fallback: Template Match on portal core (if available)
        max_vp = 0.0
        if self.tpl_portal is not None and play.shape[0] >= self.tpl_portal.shape[0] and play.shape[1] >= self.tpl_portal.shape[1]:
            res_p = cv2.matchTemplate(play, self.tpl_portal, cv2.TM_CCOEFF_NORMED)
            _, max_val_p, _, max_lp = cv2.minMaxLoc(res_p)
            max_vp = float(max_val_p)
            scores["portal_core"] = round(max_vp, 4)

            if max_vp >= 0.75:
                pw, ph = self.tpl_portal.shape[1], self.tpl_portal.shape[0]
                target_pt = (max_lp[0] + pw // 2, 60 + max_lp[1] + ph // 2)
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

        # 2. Dynamic Purple Compass Arrow + RIFT label pointing towards distant portal
        max_vr = 0.0
        if self.tpl_rift_text is not None and play.shape[0] >= self.tpl_rift_text.shape[0] and play.shape[1] >= self.tpl_rift_text.shape[1]:
            res_r = cv2.matchTemplate(play, self.tpl_rift_text, cv2.TM_CCOEFF_NORMED)
            _, max_val_r, _, max_lr = cv2.minMaxLoc(res_r)
            max_vr = float(max_val_r)
            scores["rift_text"] = round(max_vr, 4)

            if max_vr >= 0.70:
                tx = max_lr[0]
                ty = 60 + max_lr[1]
                # Verify purple cluster in the vicinity (within 70-100px)
                bx1 = max(0, tx - 70)
                bx2 = min(target_w, tx + 100)
                by1 = max(0, ty - 50)
                by2 = min(target_h, ty + 70)
                sub = norm[by1:by2, bx1:bx2]
                purp = (sub[:, :, 0].astype(int) > sub[:, :, 1].astype(int) + 16) & (
                    sub[:, :, 2].astype(int) > sub[:, :, 1].astype(int) + 10
                )
                if np.sum(purp) >= 120:
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


class GameTimerDetector:
    """Extracts in-game timer state from top center of 1024x640 frame."""

    def detect(self, frame: np.ndarray) -> GameTimerResult:
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return GameTimerResult()
        target_w = 1024
        target_h = int(h * (target_w / w))
        norm = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # Timer area at top center
        roi = norm[20:70, 440:580]
        b, g, r = cv2.split(roi)
        # White text mask: immune to orange lava or dark terrain
        white = (b > 130) & (g > 130) & (r > 130) & (b.astype(int) + g.astype(int) + r.astype(int) > 480)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(white.astype(np.uint8) * 255)

        # 1. First find main timer digits: tall white glyphs (gh >= 12, area >= 25, 25 <= gx <= 120)
        digits = []
        for i in range(1, num_labels):
            gx, gy, gw, gh, area = stats[i]
            if gh >= 12 and area >= 25 and 25 <= gx <= 120:
                digits.append((gx, gy, gw, gh, area, centroids[i]))

        if not digits:
            return GameTimerResult(detected=False)

        # The timer digits share a distinct vertical center line
        med_cy = float(np.median([d[5][1] for d in digits]))

        # Filter digits to only those on the same vertical baseline as the timer (within 8px of median cy)
        digits = [d for d in digits if abs(d[5][1] - med_cy) <= 8]
        if not digits:
            return GameTimerResult(detected=False)

        # 2. Find colon between digits (must be vertically aligned with med_cy)
        colon_x = None

        # Check for pair of vertically stacked dots (e.g. the two dots of ':')
        dots = []
        for i in range(1, num_labels):
            gx, gy, gw, gh, area = stats[i]
            cx, cy = centroids[i]
            if 35 <= gx <= 90 and abs(cy - med_cy) <= 8 and gw <= 7 and gh <= 7:
                dots.append((gx, gy, gw, gh, area, (cx, cy)))

        for i in range(len(dots)):
            for j in range(i + 1, len(dots)):
                d1, d2 = dots[i], dots[j]
                if abs(d1[5][0] - d2[5][0]) <= 3 and 3 <= abs(d1[5][1] - d2[5][1]) <= 14:
                    colon_x = (d1[5][0] + d2[5][0]) / 2.0
                    break
            if colon_x is not None:
                break

        # Check for merged colon glyph (single component with gh >= 5, gw <= 7)
        if colon_x is None:
            for i in range(1, num_labels):
                gx, gy, gw, gh, area = stats[i]
                cx, cy = centroids[i]
                if 35 <= gx <= 90 and abs(cy - med_cy) <= 8 and gw <= 7 and gh >= 5:
                    colon_x = cx
                    break

        if colon_x is None:
            return GameTimerResult(detected=False)

        digits_left = [d for d in digits if d[5][0] < colon_x]
        if len(digits_left) >= 2:
            return GameTimerResult(detected=True, minutes_category=10, is_at_least_10_min=True)
        elif len(digits_left) == 1:
            return GameTimerResult(detected=True, minutes_category=0, is_at_least_10_min=False)

        return GameTimerResult(detected=False, minutes_category=None, is_at_least_10_min=False)


class AutoVigorDetector:
    """Detects the AUTO LEVEL / AUTO VIGOR button position and active/inactive state in 1024x640 frame."""

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent / "templates"
        self.templates_dir = Path(templates_dir)
        # Legacy Auto Vigor templates (pink theme)
        self.tpl_text = cv2.imread(str(self.templates_dir / "auto_vigor_text.png"))
        self.tpl_on = cv2.imread(str(self.templates_dir / "auto_vigor_on.png"))
        # Auto Level templates (yellow theme)
        self.tpl_lvl_off = cv2.imread(str(self.templates_dir / "auto_level_off.png"))
        self.tpl_lvl_on = cv2.imread(str(self.templates_dir / "auto_level_on.png"))
        self.tpl_lvl_on_w = cv2.imread(str(self.templates_dir / "auto_level_on_word.png"))

    def detect(self, frame: np.ndarray) -> AutoVigorResult:
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return AutoVigorResult()
        target_w = 1024
        target_h = int(h * (target_w / w))
        norm = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # Badges row below stat card: covers normal Mewtwo (y~162) and Mega Mewtwo (y~146)
        # and accommodates dynamic horizontal badge shifting across all builds (x: 90..440)
        roi_y1, roi_y2 = 130, 195
        roi_x1, roi_x2 = 90, 440
        roi = norm[roi_y1:roi_y2, roi_x1:roi_x2]
        if roi.shape[0] < 15 or roi.shape[1] < 50:
            return AutoVigorResult()

        # 1. Match AUTO LEVEL (yellow theme)
        s_lvl_off, l_lvl_off = 0.0, (0, 0)
        s_lvl_on, l_lvl_on = 0.0, (0, 0)
        if self.tpl_lvl_off is not None and roi.shape[0] >= self.tpl_lvl_off.shape[0] and roi.shape[1] >= self.tpl_lvl_off.shape[1]:
            res_lo = cv2.matchTemplate(roi, self.tpl_lvl_off, cv2.TM_CCOEFF_NORMED)
            _, s_lvl_off, _, l_lvl_off = cv2.minMaxLoc(res_lo)
        if self.tpl_lvl_on is not None and roi.shape[0] >= self.tpl_lvl_on.shape[0] and roi.shape[1] >= self.tpl_lvl_on.shape[1]:
            res_lon = cv2.matchTemplate(roi, self.tpl_lvl_on, cv2.TM_CCOEFF_NORMED)
            _, s_lvl_on, _, l_lvl_on = cv2.minMaxLoc(res_lon)

        # 2. Match legacy AUTO VIGOR (pink theme)
        s_vig_off, l_vig_off = 0.0, (0, 0)
        s_vig_on, l_vig_on = 0.0, (0, 0)
        if self.tpl_text is not None and roi.shape[0] >= self.tpl_text.shape[0] and roi.shape[1] >= self.tpl_text.shape[1]:
            res_vo = cv2.matchTemplate(roi, self.tpl_text, cv2.TM_CCOEFF_NORMED)
            _, s_vig_off, _, l_vig_off = cv2.minMaxLoc(res_vo)
        if self.tpl_on is not None and roi.shape[0] >= self.tpl_on.shape[0] and roi.shape[1] >= self.tpl_on.shape[1]:
            res_von = cv2.matchTemplate(roi, self.tpl_on, cv2.TM_CCOEFF_NORMED)
            _, s_vig_on, _, l_vig_on = cv2.minMaxLoc(res_von)

        best_lvl = max(float(s_lvl_off), float(s_lvl_on))
        best_vig = max(float(s_vig_off), float(s_vig_on))

        # Check Yellow Theme (AUTO LEVEL)
        if best_lvl >= 0.70 and best_lvl >= best_vig:
            if s_lvl_on > s_lvl_off and s_lvl_on >= 0.75:
                th, tw = self.tpl_lvl_on.shape[:2]
                click_x = roi_x1 + l_lvl_on[0] + tw // 2
                click_y = roi_y1 + l_lvl_on[1] + th // 2
                is_active = True
            else:
                th, tw = self.tpl_lvl_off.shape[:2]
                click_x = roi_x1 + l_lvl_off[0] + tw // 2
                click_y = roi_y1 + l_lvl_off[1] + th // 2
                # Verify bright yellow glow vs dark yellow
                pill = norm[max(0, click_y - 7) : min(target_h, click_y + 8), max(0, click_x - 30) : min(target_w, click_x + 35)]
                bright_y = int(((pill[:, :, 2] > 170) & (pill[:, :, 1] > 170) & (pill[:, :, 0] < 120)).sum())
                is_active = (bright_y >= 25) or (s_lvl_on >= 0.85)

            return AutoVigorResult(
                is_present=True,
                is_active=bool(is_active),
                norm_point=(click_x, click_y),
                confidence=round(best_lvl, 4),
                theme="yellow",
            )

        # Check Pink Theme (AUTO VIGOR)
        if best_vig >= 0.60:
            if s_vig_on > s_vig_off and s_vig_on >= 0.70:
                th, tw = self.tpl_on.shape[:2]
                click_x = roi_x1 + l_vig_on[0] + tw // 2
                click_y = roi_y1 + l_vig_on[1] + th // 2
                is_active = True
            else:
                th, tw = self.tpl_text.shape[:2]
                click_x = roi_x1 + l_vig_off[0] + tw // 2
                click_y = roi_y1 + l_vig_off[1] + th // 2

                pill_crop = norm[max(0, click_y - 6) : min(target_h, click_y + 7), max(0, click_x - 25) : min(target_w, click_x + 25)]
                b, g, r = cv2.split(pill_crop)
                pink_px = int(((r.astype(int) > 140) & (b.astype(int) > 110) & (g.astype(int) < 110) & (r.astype(int) > g.astype(int) + 40)).sum())

                right_crop = norm[max(0, click_y - 5) : min(target_h, click_y + 6), min(target_w, click_x + 18) : min(target_w, click_x + 36)]
                right_pink = 0
                if right_crop.size > 0:
                    right_pink = int(((right_crop[:, :, 2].astype(int) > 140) & (right_crop[:, :, 0].astype(int) > 110)).sum())

                is_active = (pink_px > 25) or (right_pink > 10)

            return AutoVigorResult(
                is_present=True,
                is_active=bool(is_active),
                norm_point=(click_x, click_y),
                confidence=round(best_vig, 4),
                theme="pink",
            )

        return AutoVigorResult(is_present=False, confidence=round(max(best_lvl, best_vig), 4))


AutoLevelDetector = AutoVigorDetector


class MenuNavigatorDetector:
    """Detects end-of-match Run Over screen, Main Menu Play button, and Choose Region modal."""

    def __init__(self, templates_dir: Path | str | None = None, target_region: str = "johto") -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent / "templates"
        self.templates_dir = Path(templates_dir)
        self.target_region = target_region.lower()
        if self.target_region == "jhoto":
            self.target_region = "johto"

        self.tpl_run_over = self._load_template("run_over_title.png")
        self.tpl_btn_menu = self._load_template("back_to_menu_btn.png")
        self.tpl_play = self._load_template("main_menu_play_btn.png")
        self.tpl_region = self._load_template("choose_region_title.png")
        self.tpl_kanto = self._load_template("kanto_word.png")
        self.tpl_johto = self._load_template("johto_word.png")
        self.tpl_modal_back = self._load_template("modal_back_btn.png")

    def _load_template(self, filename: str) -> np.ndarray | None:
        path = self.templates_dir / filename
        if not path.exists():
            return None
        return cv2.imread(str(path))

    def detect(self, frame: np.ndarray) -> MenuDetectionResult:
        """Analyze frame for Run Over, Main Menu, or Choose Region screens."""
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return MenuDetectionResult()
        target_w = 1024
        target_h = int(h * (target_w / w))
        norm = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # 1. "Run over" screen (Match ended -> Click "Back to menu")
        # Accommodates both short match cards (y~145) and tall match cards with IV/Gacha loot (y~37)
        val_ro, val_bm = 0.0, 0.0
        click_pt = (460, 483)

        if self.tpl_run_over is not None:
            roi_ro = norm[20:250, 420:600]
            if roi_ro.shape[0] >= self.tpl_run_over.shape[0] and roi_ro.shape[1] >= self.tpl_run_over.shape[1]:
                res_ro = cv2.matchTemplate(roi_ro, self.tpl_run_over, cv2.TM_CCOEFF_NORMED)
                val_ro = float(cv2.minMaxLoc(res_ro)[1])

        if self.tpl_btn_menu is not None:
            roi_bm = norm[400:635, 360:540]
            if roi_bm.shape[0] >= self.tpl_btn_menu.shape[0] and roi_bm.shape[1] >= self.tpl_btn_menu.shape[1]:
                res_bm = cv2.matchTemplate(roi_bm, self.tpl_btn_menu, cv2.TM_CCOEFF_NORMED)
                min_bm, max_bm, _, loc_bm = cv2.minMaxLoc(res_bm)
                val_bm = float(max_bm)
                if val_bm >= 0.70:
                    click_pt = (360 + loc_bm[0] + self.tpl_btn_menu.shape[1] // 2, 400 + loc_bm[1] + self.tpl_btn_menu.shape[0] // 2)

        if val_ro >= 0.70 or val_bm >= 0.70:
            conf = max(val_ro, val_bm)
            return MenuDetectionResult(screen_type=MenuScreenType.RUN_OVER, click_point=click_pt, confidence=round(conf, 4))

        # 2. "Choose the region" modal -> Click target region card (e.g. Johto or Kanto)
        if self.tpl_region is not None:
            roi_reg = norm[120:220, 180:440]
            if roi_reg.shape[0] >= self.tpl_region.shape[0] and roi_reg.shape[1] >= self.tpl_region.shape[1]:
                res_reg = cv2.matchTemplate(roi_reg, self.tpl_region, cv2.TM_CCOEFF_NORMED)
                val_reg = float(cv2.minMaxLoc(res_reg)[1])
                if val_reg >= 0.70:
                    region = self.target_region.lower()
                    if region in ("johto", "jhoto"):
                        click_pt = (387, 277)  # Center of Johto card
                        if self.tpl_johto is not None:
                            roi_jh = norm[180:360, 310:460]
                            if roi_jh.shape[0] >= self.tpl_johto.shape[0] and roi_jh.shape[1] >= self.tpl_johto.shape[1]:
                                res_jh = cv2.matchTemplate(roi_jh, self.tpl_johto, cv2.TM_CCOEFF_NORMED)
                                loc_jh = cv2.minMaxLoc(res_jh)[3]
                                click_pt = (310 + loc_jh[0] + self.tpl_johto.shape[1] // 2, 180 + loc_jh[1] + self.tpl_johto.shape[0] // 2)
                    else:  # default to Kanto
                        click_pt = (266, 277)  # Center of Kanto card
                        if self.tpl_kanto is not None:
                            roi_kt = norm[180:360, 180:340]
                            if roi_kt.shape[0] >= self.tpl_kanto.shape[0] and roi_kt.shape[1] >= self.tpl_kanto.shape[1]:
                                res_kt = cv2.matchTemplate(roi_kt, self.tpl_kanto, cv2.TM_CCOEFF_NORMED)
                                loc_kt = cv2.minMaxLoc(res_kt)[3]
                                click_pt = (180 + loc_kt[0] + 20, 180 + loc_kt[1] - 5)
                    return MenuDetectionResult(screen_type=MenuScreenType.CHOOSE_REGION, click_point=click_pt, confidence=round(val_reg, 4))

        # 3. Main Menu (Play button -> Click "Play")
        if self.tpl_play is not None:
            roi_pl = norm[400:560, 360:660]
            if roi_pl.shape[0] >= self.tpl_play.shape[0] and roi_pl.shape[1] >= self.tpl_play.shape[1]:
                res_pl = cv2.matchTemplate(roi_pl, self.tpl_play, cv2.TM_CCOEFF_NORMED)
                val_pl = float(cv2.minMaxLoc(res_pl)[1])
                if val_pl >= 0.70:
                    loc_pl = cv2.minMaxLoc(res_pl)[3]
                    click_pt = (360 + loc_pl[0] + self.tpl_play.shape[1] // 2, 400 + loc_pl[1] + self.tpl_play.shape[0] // 2)
                    return MenuDetectionResult(screen_type=MenuScreenType.MAIN_MENU, click_point=click_pt, confidence=round(val_pl, 4))

        # 4. Stray Sub-Menu / Modal Dialog (Gacha menu, Upgrades, etc.) -> Click "Back"
        if self.tpl_modal_back is not None:
            roi_mb = norm[140:220, 700:850]
            if roi_mb.shape[0] >= self.tpl_modal_back.shape[0] and roi_mb.shape[1] >= self.tpl_modal_back.shape[1]:
                res_mb = cv2.matchTemplate(roi_mb, self.tpl_modal_back, cv2.TM_CCOEFF_NORMED)
                val_mb = float(cv2.minMaxLoc(res_mb)[1])
                if val_mb >= 0.75:
                    loc_mb = cv2.minMaxLoc(res_mb)[3]
                    click_pt = (700 + loc_mb[0] + self.tpl_modal_back.shape[1] // 2, 140 + loc_mb[1] + self.tpl_modal_back.shape[0] // 2)
                    return MenuDetectionResult(screen_type=MenuScreenType.SUBMENU_BACK, click_point=click_pt, confidence=round(val_mb, 4))

        return MenuDetectionResult(screen_type=MenuScreenType.NONE, confidence=0.0)


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
