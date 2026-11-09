# PokéLit AFK Bot: Targeted Background Movement, Modals & Rift Navigation

A complete bot system for **PokéLit** that targets **ONLY** the specific game window, allowing you to use your laptop in the foreground while the bot plays in the background.

---

## Capabilities

### 1. Movement & Rift Navigation
- **Normal Gameplay**: Automatic W -> A -> S -> D clockwise movement with randomized durations.
- **Rift Portal Navigation**:
  - Automatically detects:
    1. **Physical Purple Rift Portal Tear**: When the portal is nearby on screen, it steers directly towards the portal center.
    2. **Directional Purple Arrow Indicator & Label**: When the portal is far/off-screen, steers in the arrow's heading.
    3. **"A RIFT HAS OPENED!" Banner**: Immediate notification trigger.
  - Abandons random movement and calculates the exact 8-direction steering vector (e.g., `['s', 'a']`, `['d']`, etc.) from the character in the center towards the rift.
  - Guides the character directly into the rift portal.
  - Once inside the rift (portal and indicator disappear), seamlessly resumes normal random movement loop!

### 2. Modals & Perk Selection
- **Level-Up Screen ("Choose a reward")**: 3 options -> Taps 1, 2, or 3 (configured strategy, default `1`).
- **Item Window (Pickup)**: 2 options -> Always taps **`2`** (`Equip [Item]`).
- **Item Window (Change / Swap / Lock)**: 3 options -> Always taps **`3`** (`Lock [Item]`).
- **Modal Priority**: If a modal appears while steering towards a rift, movement is paused, the choice is selected, and rift navigation resumes immediately upon modal dismissal.

### 3. Background Window Isolation
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
