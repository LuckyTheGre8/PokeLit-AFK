# PokéLit AFK Bot: Targeted Background Movement, Modals & Rift Navigation

A complete bot system for **PokéLit** that targets **ONLY** the specific game window, allowing you to use your laptop in the foreground while the bot plays in the background.

---

## Capabilities

### 1. Real-Time Spatial AI Navigation & Kiting
- **Spatial Potential Field AI**:
  - **Dynamic Swarm Avoidance**: Scans 8 radial danger sectors around the character ($r \in [35, 160]\text{px}$) to detect incoming enemy hordes and bosses (e.g. Nidoking, Venusaur, Gengar). Computes a repulsive vector away from danger.
  - **Pro-Player Kiting & Strafing**: Applies tangential rotational force to gracefully circle around enemy mobs while automatic abilities fire into the cluster.
  - **XP Gem Vacuum**: Detects shining amber, gold, blue, and green diamond XP gems across the playfield and pulls the character towards dense clusters.
  - **Dominant Gem Clustering**: Groups gems within 100px of the primary nearest gem, preventing force vector cancellation (local minima) that previously froze characters between opposite gems.
  - **Terrain Motion Tracking (Anti-Pinning)**: Employs sub-pixel phase correlation (`cv2.phaseCorrelate`) on background terrain patches to detect physical stalling (< 2.0px displacement over 0.65s).
  - **Autonomous Obstacle Escape Slides**: When blocked by rocks, trees, or terrain corners, automatically initiates orthogonal ($\pm 90^\circ$ or $135^\circ$) sliding vectors to navigate smoothly around obstacles.
  - **Swarm Encirclement Breakout**: When surrounded on all sides and threat vectors cancel out, immediately locates and charges through the lowest-threat corridor.
  - **Opposing Key Lockout & Ghost Flush**: Forcefully releases opposing keys (e.g. `s` when `w` is pressed) and flushes stale browser key states every 1.5s, eliminating browser net-zero velocity freeze.
  - **Boundary Cushion**: Repels from screen edges to avoid getting cornered against walls.
  - **Fallback**: If disabled in `config.json`, seamlessly falls back to classic clockwise WASD movement.
- **Top Priority Rift Portal Navigation**:
  - **Dynamic Compass Arrow Tracking**: Continuously monitors the rotating purple compass arrow and distance text across the screen perimeter. As your character moves across the terrain and the relative position of the rift shifts, the bot recalculates the steering vector on every single camera frame (30 FPS), smoothly turning along the rotating arrow without ever locking into stale headings!
  - **On-Screen Physical Portal Tear Detection**: Morphology parser requiring tall vertical tear geometry ($ph \ge 85\text{px}, pw \ge 45\text{px}, \text{AR} \in [1.25, 2.8]$), contiguous dark void core, and dense electric violet perimeter aura. Distinguishes genuine rift portals from purple enemy mobs (such as Nidoking and Nidorino on the Ash Volcano map) with zero false positives.
  - **100% Top Priority Plunge**: When a rift is active (arrow or portal tear), the AI completely abandons enemy kiting and random movement to plunge directly and uninterrupted into the portal coordinates.
  - **Autonomous 30 FPS Frame-Level Tracking**: Evaluated directly on the live camera stream with sub-millisecond latency.
  - **Inside the Rift Realm**: Once the portal is entered and the player teleports to the secret dimension, the bot switches to XP gem harvesting and kiting.

### 2. Modals, Perk Selection & Auto Vigor
- **Level-Up Screen ("Choose a reward")**: 3 options -> Taps 1, 2, or 3 (configured strategy, default `1`).
- **Item Window (Pickup)**: 2 options -> Always taps **`2`** (`Equip [Item]`).
- **Item Window (Change / Swap / Lock)**: 3 options -> Always taps **`3`** (`Lock [Item]`).
- **Seamless Rift Path Preservation**: If a level-up or item modal appears while moving towards the rift, movement is paused without losing the rift heading. The choice is selected, rift position is re-verified, and navigation resumes directly towards the rift without ever dropping into random movement!
- **Auto Vigor at 10 Minutes**:
  - For the first 10 minutes of match time (or until `10:00` on the in-game timer), the bot selects your level-up perks.
  - At 10 minutes, the bot automatically locates and clicks the **AUTO VIGOR** button below the stats card.
  - From 10:00 onwards, the game applies all subsequent level-ups automatically in the background, keeping movement towards rifts completely uninterrupted!

### 3. Automatic Match Restart Loop (Infinite AFK)
- **"Run over" Screen**: When a match concludes, the bot detects the summary card and clicks **`Back to menu`**.
- **Main Menu**: Detects the main lobby with Mewtwo and clicks **`Play`** (`Enter the dungeon`).
- **Region Selection**: Detects the region modal and selects **`Kanto`**.
- **Seamless Match Initialization**: Resets timers and Auto Vigor, resumes WASD movement, and plays the new game automatically.

### 4. Background Window Isolation
- **Output Stream**: Captures strictly from the PokéLit window handle via Win32 `PrintWindow`. You can cover the game with any other application.
- **Input Stream**: Posts keystrokes directly to the PokéLit window via Win32 `PostMessage`. Does not pollute your active apps or keyboard focus.

---

## How to Run

### Two Separate Windows:
```powershell
# Terminal 1:
python .\random_movement.py

# Terminal 2:
python .\perk_selector.py
```

### Single Command:
```powershell
python .\run_all.py
```

Press **`[F8]`** to begin!

---

## Controls

| Hotkey | Action |
|---|---|
| **`[F8]`** | Start Bot |
| **`[F9]`** | Emergency Stop |
| **`[F10]`** | Quit |
| **`[F7]`** | Test Scan (inspects current window for modals and rift status) |
| **Mouse Corner** | Top-left screen corner fail-safe abort |
