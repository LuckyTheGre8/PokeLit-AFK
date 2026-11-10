"""PokéLit Real-Time Spatial AI Navigation Engine.

Implements real-time Computer Vision Potential Field navigation:
1. Threat Repulsion & Dynamic Kiting:
   - Scans 8 radial sectors around the player (35px to 160px).
   - Detects enemy swarms, bosses (e.g. Nidoking/Venusaur/Gengar), and hazard zones.
   - Computes repulsive vector away from high-threat sectors + tangential kiting force
     to gracefully circle around enemies while firing auto-weapons.
2. XP Gem Magnetic Attraction:
   - Identifies shining XP gems (gold, blue, green diamonds) across the playfield.
   - Computes an attractive pull vector towards dense gem clusters to vacuum up experience.
3. Rift Goal Integration:
   - When a rift portal or compass arrow is active, incorporates a strong goal attractor
     so the character navigates to the rift while dodging enemy swarms in its path.
4. Wall / Boundary Buffer:
   - Soft repulsive forces from screen boundaries to prevent getting cornered.
5. Quantization:
   - Quantizes the combined vector into optimal 8-direction keys: W, A, S, D, and diagonals.
   - Runs in ~1.5 ms per frame for ultra-low latency 60 FPS responsiveness.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
import cv2
import numpy as np
from level_detector import RiftDetector


@dataclass
class SpatialNavResult:
    """Output of spatial navigation frame evaluation."""
    direction_keys: list[str] = field(default_factory=list)
    heading_angle_deg: float = 0.0
    mode: str = "patrol"  # "kiting_evasion", "gem_hunting", "rift_push", "patrol", "unstuck_escape"
    threat_density: dict[str, float] = field(default_factory=dict)
    max_threat_percent: float = 0.0
    gems_detected: int = 0
    vector: tuple[float, float] = (0.0, 0.0)


class TerrainMotionTracker:
    """Tracks background terrain displacement via phase correlation to detect obstacle pinning."""

    def __init__(self, sample_box: tuple[int, int, int, int] = (350, 478, 650, 778), check_interval: float = 0.25) -> None:
        self.y1, self.y2, self.x1, self.x2 = sample_box
        self.check_interval = check_interval
        self.prev_crop: np.ndarray | None = None
        self.last_check_time: float = 0.0
        self.stuck_start_time: float | None = None
        self.is_stuck: bool = False
        self.unstuck_until_time: float = 0.0
        self.unstuck_heading_deg: float = 0.0
        self.unstuck_keys: list[str] = []
        self.escape_attempt: int = 0
        self.last_commanded_keys: list[str] = []
        self.same_keys_start_time: float = 0.0

    def reset(self) -> None:
        self.prev_crop = None
        self.last_check_time = 0.0
        self.stuck_start_time = None
        self.is_stuck = False
        self.unstuck_until_time = 0.0
        self.unstuck_keys = []
        self.escape_attempt = 0
        self.same_keys_start_time = 0.0
        self.last_commanded_keys = []

    def update(
        self,
        norm: np.ndarray,
        last_heading_deg: float,
        commanded_keys: list[str],
        now: float,
    ) -> tuple[bool, list[str], float]:
        """Detect if character is pinned against an obstacle or wall."""
        # 1. Anti-pinning timeout: same direction held continuously without change
        if commanded_keys == self.last_commanded_keys and commanded_keys:
            if self.same_keys_start_time == 0.0:
                self.same_keys_start_time = now
            elif now - self.same_keys_start_time >= 3.2 and not self.is_stuck:
                self._trigger_escape(last_heading_deg, now)
        else:
            self.last_commanded_keys = list(commanded_keys)
            self.same_keys_start_time = now

        # 2. Active escape maneuver execution window
        if self.is_stuck and now < self.unstuck_until_time:
            return True, self.unstuck_keys, self.unstuck_heading_deg

        # 3. Terrain patch displacement via sub-pixel phase correlation
        patch = norm[self.y1:self.y2, self.x1:self.x2]
        crop = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(np.float32)

        if now - self.last_check_time >= self.check_interval:
            if self.prev_crop is not None:
                shift, resp = cv2.phaseCorrelate(self.prev_crop, crop)
                disp = float(np.hypot(shift[0], shift[1]))

                if resp >= 0.30:
                    if disp < 2.0 and commanded_keys:
                        if self.stuck_start_time is None:
                            self.stuck_start_time = now
                        elif now - self.stuck_start_time >= 0.65:
                            self._trigger_escape(last_heading_deg, now)
                    else:
                        self.stuck_start_time = None
                        if now >= self.unstuck_until_time:
                            self.is_stuck = False
                            self.escape_attempt = 0

            self.prev_crop = crop.copy()
            self.last_check_time = now

        return self.is_stuck, self.unstuck_keys, self.unstuck_heading_deg

    def _trigger_escape(self, last_heading_deg: float, now: float) -> None:
        self.is_stuck = True
        self.unstuck_until_time = now + 0.65
        # Cycle through perpendicular slides: +90° right, -90° left, +135° reverse-angle
        if self.escape_attempt % 3 == 0:
            esc_deg = (last_heading_deg + 90.0) % 360.0
        elif self.escape_attempt % 3 == 1:
            esc_deg = (last_heading_deg - 90.0) % 360.0
        else:
            esc_deg = (last_heading_deg + 135.0) % 360.0
        if esc_deg > 180.0:
            esc_deg -= 360.0
        self.unstuck_heading_deg = round(esc_deg, 1)
        self.unstuck_keys = self._angle_to_keys(esc_deg)
        self.escape_attempt += 1
        self.stuck_start_time = None
        self.same_keys_start_time = now

    def _angle_to_keys(self, angle: float) -> list[str]:
        if -22.5 <= angle < 22.5: return ["d"]
        elif 22.5 <= angle < 67.5: return ["s", "d"]
        elif 67.5 <= angle < 112.5: return ["s"]
        elif 112.5 <= angle < 157.5: return ["s", "a"]
        elif angle >= 157.5 or angle < -157.5: return ["a"]
        elif -157.5 <= angle < -112.5: return ["w", "a"]
        elif -112.5 <= angle < -67.5: return ["w"]
        elif -67.5 <= angle < -22.5: return ["w", "d"]
        return ["d"]


class SpatialNavigator:
    """Real-time CV vector field navigator for PokéLit."""

    def __init__(
        self,
        gem_weight: float = 1.2,
        threat_weight: float = 2.4,
        kite_weight: float = 0.9,
        rift_weight: float = 2.0,
        danger_threshold: float = 12.0,
    ) -> None:
        self.gem_weight = gem_weight
        self.threat_weight = threat_weight
        self.kite_weight = kite_weight
        self.rift_weight = rift_weight
        self.danger_threshold = danger_threshold
        self.rift_detector = RiftDetector()

        # Sector unit vectors: (vx, vy)
        self.sector_vectors = {
            "d": np.array([1.0, 0.0], dtype=np.float32),
            "sd": np.array([0.7071, 0.7071], dtype=np.float32),
            "s": np.array([0.0, 1.0], dtype=np.float32),
            "sa": np.array([-0.7071, 0.7071], dtype=np.float32),
            "a": np.array([-1.0, 0.0], dtype=np.float32),
            "wa": np.array([-0.7071, -0.7071], dtype=np.float32),
            "w": np.array([0.0, -1.0], dtype=np.float32),
            "wd": np.array([0.7071, -0.7071], dtype=np.float32),
        }

        # Sector angle boundaries: (key, angle_min, angle_max)
        self.sector_defs = [
            ("d", -22.5, 22.5),
            ("sd", 22.5, 67.5),
            ("s", 67.5, 112.5),
            ("sa", 112.5, 157.5),
            ("a", 157.5, 180.0),
            ("wa", -157.5, -112.5),
            ("w", -112.5, -67.5),
            ("wd", -67.5, -22.5),
        ]

        # Pre-allocate coordinates for 320x320 danger zone crop (around player center)
        crop_size = 320
        self.crop_r = crop_size // 2
        cy, cx = self.crop_r, self.crop_r
        Y, X = np.ogrid[:crop_size, :crop_size]
        self.crop_dist = np.hypot(X - cx, Y - cy)
        self.crop_angle = np.degrees(np.arctan2(Y - cy, X - cx))
        self.danger_mask = (self.crop_dist >= 35) & (self.crop_dist <= 155)

        # Pre-compute sector masks on danger zone crop
        self.sector_masks = []
        for k, a_min, a_max in self.sector_defs:
            if k == "a":
                m = ((self.crop_angle >= 157.5) | (self.crop_angle <= -157.5)) & self.danger_mask
            else:
                m = (self.crop_angle >= a_min) & (self.crop_angle < a_max) & self.danger_mask
            tot = max(1, int(np.sum(m)))
            self.sector_masks.append((k, m, tot))

        self.last_valid_keys: list[str] = ["d"]
        self.smoothed_vector = np.array([1.0, 0.0], dtype=np.float32)
        self.initialized = False
        self.patrol_start_time = time.monotonic()
        self.smoothing_alpha = 0.50
        self.motion_tracker = TerrainMotionTracker()

    def reset(self) -> None:
        """Reset internal momentum smoothing and patrol timing."""
        self.smoothed_vector = np.array([1.0, 0.0], dtype=np.float32)
        self.initialized = False
        self.patrol_start_time = time.monotonic()
        self.last_valid_keys = ["d"]
        self.motion_tracker.reset()

    def find_portal(self, norm: np.ndarray) -> tuple[bool, list[str], float, tuple[int, int] | None]:
        """Detect physical rift portal directly on normalized frame."""
        h, w = norm.shape[:2]
        v_all = np.max(norm, axis=2)
        if (v_all < 15).sum() / (w * h) > 0.18:
            return False, [], 0.0, None

        ui = np.ones((h, w), dtype=bool)
        ui[:80, :] = False
        ui[:220, :320] = False
        ui[610:, :] = False

        b, g, r = cv2.split(norm)
        bgr_purp = (b.astype(int) > g.astype(int) + 16) & (r.astype(int) > g.astype(int) + 8)
        hsv = cv2.cvtColor(norm, cv2.COLOR_BGR2HSV)
        hsv_purp = (hsv[:, :, 0] >= 115) & (hsv[:, :, 0] <= 170) & (hsv[:, :, 1] >= 35) & (hsv[:, :, 2] >= 35)
        mask = bgr_purp & hsv_purp & ui

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8) * 255)
        best_portal = None
        best_score = 0.0

        for i in range(1, num_labels):
            px, py, pw, ph, area = stats[i]
            if 800 <= area <= 25000 and pw >= 30 and ph >= 45:
                pad = 12
                sub = norm[max(0, py - pad) : min(h, py + ph + pad), max(0, px - pad) : min(w, px + pw + pad)]
                dark_px = int((np.max(sub, axis=2) < 45).sum())
                ar = ph / float(pw)
                if dark_px >= 200 and (0.7 <= ar <= 3.2):
                    score = area + dark_px * 2.0
                    if score > best_score:
                        best_score = score
                        best_portal = (int(centroids[i][0]), int(centroids[i][1]))

        if best_portal:
            cx, cy = best_portal
            ang = float(np.degrees(np.arctan2(cy - h // 2, cx - w // 2)))
            keys = self._angle_to_keys(ang)
            return True, keys, round(ang, 1), (cx, cy)

        return False, [], 0.0, None

    def analyze(
        self,
        frame: np.ndarray,
        rift_direction_keys: list[str] | None = None,
    ) -> SpatialNavResult:
        """Calculate the real-time AI steering vector from current frame."""
        h, w = frame.shape[:2]
        if w == 0 or h == 0:
            return SpatialNavResult(direction_keys=["d"])

        target_w = 1024
        target_h = int(h * (target_w / w))
        norm = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)

        player_cx = target_w // 2
        player_cy = target_h // 2

        # ---------------------------------------------------------
        # 0. Autonomous Live Rift Detection (Portal Tear, Dynamic Compass Arrow, Banner)
        # ---------------------------------------------------------
        # Always evaluate the fresh camera frame directly on every tick for real-time tracking!
        live_rift = self.rift_detector.detect(norm)
        if live_rift.is_active and live_rift.direction_keys:
            active_rift_keys = live_rift.direction_keys
            active_rift_angle = live_rift.angle_deg
            active_rift_mode = live_rift.mode
            active_rift_pt = live_rift.target_point
        elif rift_direction_keys:
            # Fallback to external IPC signal only if live vision was momentarily obscured
            active_rift_keys = rift_direction_keys
            active_rift_angle = None
            active_rift_mode = "ipc_fallback"
            active_rift_pt = None
        else:
            active_rift_keys = None
            active_rift_angle = None
            active_rift_mode = None
            active_rift_pt = None

        # ---------------------------------------------------------
        # 1. Threat Detection & Sector Density in Danger Zone
        # ---------------------------------------------------------
        y1 = max(0, player_cy - self.crop_r)
        y2 = min(target_h, player_cy + self.crop_r)
        x1 = max(0, player_cx - self.crop_r)
        x2 = min(target_w, player_cx + self.crop_r)

        crop = norm[y1:y2, x1:x2]
        threat_density: dict[str, float] = {}
        F_threat_repulsion = np.zeros(2, dtype=np.float32)

        if crop.shape[0] == 320 and crop.shape[1] == 320:
            b, g, r = cv2.split(crop)
            # Grass / stone background has strong green dominance
            is_bg = (g.astype(int) > r.astype(int) + 15) & (g.astype(int) > b.astype(int) + 15)
            # Exclude player's purple/pink range aura ring (radius ~145px)
            is_aura = (r.astype(int) > 130) & (b.astype(int) > 110) & (g.astype(int) < 120) & (abs(self.crop_dist - 145) < 9)
            is_threat = self.danger_mask & (~is_bg) & (~is_aura)

            for k, s_mask, tot in self.sector_masks:
                threat_px = int(np.sum(is_threat & s_mask))
                pct = (threat_px / tot) * 100.0
                threat_density[k] = round(pct, 1)

                if pct > self.danger_threshold:
                    weight = (pct - self.danger_threshold) / 100.0
                    # Repulsion pushes in OPPOSITE direction of threat sector
                    F_threat_repulsion -= self.sector_vectors[k] * weight

        max_threat = max(threat_density.values()) if threat_density else 0.0

        # Swarm Encirclement Escape: if surrounded on all sides, repulsion cancels out.
        # Break out immediately through the sector with the lowest enemy density!
        threat_mag = float(np.linalg.norm(F_threat_repulsion))
        if max_threat >= self.danger_threshold and threat_mag < 0.20 and threat_density:
            safest_k = min(threat_density.keys(), key=lambda k: threat_density[k])
            if safest_k in self.sector_vectors:
                F_threat_repulsion = self.sector_vectors[safest_k] * 2.2

        # Kiting tangential force: rotate repulsion 90 degrees to circle around mobs
        F_kite = np.array([-F_threat_repulsion[1], F_threat_repulsion[0]], dtype=np.float32)

        # ---------------------------------------------------------
        # 2. XP Gem Magnetic Attraction (Dominant Cluster Targeting)
        # ---------------------------------------------------------
        play_y1, play_y2 = 190, 600
        play_x1, play_x2 = 100, 924
        playfield = norm[play_y1:play_y2, play_x1:play_x2]

        # Amber / Gold gems condition
        gold_mask = (
            (playfield[:, :, 2] > 160)
            & (playfield[:, :, 1] > 140)
            & (playfield[:, :, 0] < 140)
            & (playfield[:, :, 2] > playfield[:, :, 0] + 35)
        )
        # Blue / Cyan gems condition
        blue_mask = (
            (playfield[:, :, 0] > 170)
            & (playfield[:, :, 1] > 150)
            & (playfield[:, :, 2] < 140)
            & (playfield[:, :, 0] > playfield[:, :, 2] + 40)
        )
        combined_gems = (gold_mask | blue_mask).astype(np.uint8) * 255

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(combined_gems)
        valid_gems = []

        for i in range(1, num_labels):
            area = stats[i][4]
            if 4 <= area <= 220:
                gx = play_x1 + centroids[i][0]
                gy = play_y1 + centroids[i][1]
                dx = gx - player_cx
                dy = gy - player_cy
                dist = float(np.hypot(dx, dy))
                if 25.0 <= dist <= 260.0:
                    valid_gems.append((gx, gy, dist, dx, dy))

        gems_found = len(valid_gems)
        F_gems = np.zeros(2, dtype=np.float32)

        if valid_gems:
            # Sort by distance to find primary target gem
            valid_gems.sort(key=lambda g: g[2])
            primary = valid_gems[0]
            # Cluster nearby gems within 100px of primary gem to pull through the densest pocket
            cluster = [g for g in valid_gems if np.hypot(g[0] - primary[0], g[1] - primary[1]) <= 100.0]
            cluster_cx = float(np.mean([g[0] for g in cluster]))
            cluster_cy = float(np.mean([g[1] for g in cluster]))
            cdx = cluster_cx - player_cx
            cdy = cluster_cy - player_cy
            cdist = float(np.hypot(cdx, cdy))
            if cdist > 1.0:
                cluster_u = np.array([cdx / cdist, cdy / cdist], dtype=np.float32)
                # Strong unified directional pull toward cluster centroid - ZERO force cancellation!
                F_gems = cluster_u * min(2.5, 1.0 + len(cluster) * 0.2)

        # ---------------------------------------------------------
        # 3. Rift Goal Vector (Dynamic Continuous Compass Angle)
        # ---------------------------------------------------------
        F_rift = np.zeros(2, dtype=np.float32)
        if active_rift_angle is not None:
            rad = math.radians(active_rift_angle)
            F_rift = np.array([math.cos(rad), math.sin(rad)], dtype=np.float32)
        elif active_rift_keys:
            for rk in active_rift_keys:
                if rk in self.sector_vectors:
                    F_rift += self.sector_vectors[rk]
            norm_r = np.linalg.norm(F_rift)
            if norm_r > 0:
                F_rift /= norm_r

        # ---------------------------------------------------------
        # 4. Boundary Cushion
        # ---------------------------------------------------------
        F_bounds = np.zeros(2, dtype=np.float32)
        if player_cy < 220:
            F_bounds[1] += 0.8
        elif player_cy > 560:
            F_bounds[1] -= 0.8
        if player_cx < 160:
            F_bounds[0] += 0.8
        elif player_cx > 864:
            F_bounds[0] -= 0.8

        # ---------------------------------------------------------
        # 5. Composite Potential Field Vector
        # ---------------------------------------------------------
        mode = "patrol"
        F_total = np.zeros(2, dtype=np.float32)

        if active_rift_keys:
            # TOP PRIORITY: Pure direct push into Rift Portal / along dynamic compass arrow!
            mode = "rift_push"
            F_total = F_rift * 5.0
        elif max_threat >= self.danger_threshold:
            # Enemy swarm / boss proximity -> Evasion and Kiting
            mode = "kiting_evasion"
            F_total += F_threat_repulsion * self.threat_weight
            F_total += F_kite * self.kite_weight
            F_total += F_gems * 0.15
            F_total += F_bounds * 0.8
        elif gems_found > 0:
            # Field is safe and gems are present -> Vacuum XP gems
            mode = "gem_hunting"
            F_total += F_gems * self.gem_weight
            F_total += F_bounds * 0.5
        else:
            # Clear field -> continuous sweeping figure-8 patrol around the arena (7s period)
            mode = "patrol"
            elapsed = time.monotonic() - self.patrol_start_time
            omega = 2.0 * math.pi / 7.0
            patrol_vec = np.array([math.cos(omega * elapsed), math.sin(2.0 * omega * elapsed) * 0.75], dtype=np.float32)
            F_total = patrol_vec * 1.0 + F_bounds * 0.5

        # Apply exponential moving average (EMA) smoothing
        total_mag = float(np.linalg.norm(F_total))
        if total_mag > 0.01:
            u_target = F_total / total_mag
            if not self.initialized:
                self.smoothed_vector = u_target.copy()
                self.initialized = True
            elif mode == "rift_push":
                # Instant responsive tracking to dynamic rift compass arrow / portal tear (no lag)
                self.smoothed_vector = u_target.copy()
            else:
                self.smoothed_vector = (self.smoothing_alpha * u_target) + ((1.0 - self.smoothing_alpha) * self.smoothed_vector)
            s_norm = float(np.linalg.norm(self.smoothed_vector))
            if s_norm > 0:
                self.smoothed_vector /= s_norm

        # Quantize vector into 8 directions
        angle_deg = float(np.degrees(np.arctan2(self.smoothed_vector[1], self.smoothed_vector[0])))
        keys = self._angle_to_keys(angle_deg)
        self.last_valid_keys = keys

        # Check real-time terrain motion tracker for obstacle pinning & automatic slide
        now = time.monotonic()
        is_stuck, unstuck_keys, unstuck_angle = self.motion_tracker.update(
            norm,
            last_heading_deg=angle_deg,
            commanded_keys=keys,
            now=now,
        )

        if is_stuck and unstuck_keys:
            mode = "unstuck_escape"
            keys = unstuck_keys
            angle_deg = unstuck_angle

        return SpatialNavResult(
            direction_keys=keys,
            heading_angle_deg=round(angle_deg, 1),
            mode=mode,
            threat_density=threat_density,
            max_threat_percent=round(max_threat, 1),
            gems_detected=gems_found,
            vector=(round(float(self.smoothed_vector[0]), 3), round(float(self.smoothed_vector[1]), 3)),
        )

    def _angle_to_keys(self, angle: float) -> list[str]:
        """Convert degree angle into 8-direction WASD keystrokes."""
        if -22.5 <= angle < 22.5:
            return ["d"]
        elif 22.5 <= angle < 67.5:
            return ["s", "d"]
        elif 67.5 <= angle < 112.5:
            return ["s"]
        elif 112.5 <= angle < 157.5:
            return ["s", "a"]
        elif angle >= 157.5 or angle < -157.5:
            return ["a"]
        elif -157.5 <= angle < -112.5:
            return ["w", "a"]
        elif -112.5 <= angle < -67.5:
            return ["w"]
        elif -67.5 <= angle < -22.5:
            return ["w", "d"]
        return ["d"]
