from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import copy, random, uvicorn
from engine import GameEngine
import asyncio  # Needed for step-by-step delay pacing
from ai import WarGameAI

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = GameEngine()

# In-memory storage tracking independent active rooms
rooms = {}


def rotate_cube_faces(faces: dict, dx: int, dy: int) -> dict:
    new_faces = faces.copy()
    if dx > 0 and dy == 0:  # East
        new_faces["top"] = faces["left"]
        new_faces["bottom"] = faces["right"]
        new_faces["left"] = faces["bottom"]
        new_faces["right"] = faces["top"]
    elif dx < 0 and dy == 0:  # West
        new_faces["top"] = faces["right"]
        new_faces["bottom"] = faces["left"]
        new_faces["left"] = faces["top"]
        new_faces["right"] = faces["bottom"]
    elif dx == 0 and dy > 0:  # South
        new_faces["top"] = faces["back"]
        new_faces["bottom"] = faces["front"]
        new_faces["front"] = faces["top"]
        new_faces["back"] = faces["bottom"]
    elif dx == 0 and dy < 0:  # North
        new_faces["top"] = faces["front"]
        new_faces["bottom"] = faces["back"]
        new_faces["front"] = faces["bottom"]
        new_faces["back"] = faces["top"]
    elif dx != 0 or dy != 0:  # Diagonal (Two-step roll: first horizontal, then vertical)
        new_faces = rotate_cube_faces(faces, dx, 0)
        new_faces = rotate_cube_faces(new_faces, 0, dy)
    return new_faces


def get_initial_state():
    return {
        "mines": [],
        "awaiting_lazarus_choice": None,
        "units": [
            # === NORTH FORCES (17 Units Total) ===
            {"id": "n-inf-1", "side": "North", "type": "Infantry", "symbol": "I", "x": 4, "y": 4},
            {"id": "n-inf-2", "side": "North", "type": "Infantry", "symbol": "I", "x": 6, "y": 4},
            {"id": "n-inf-3", "side": "North", "type": "Infantry", "symbol": "I", "x": 8, "y": 4},
            {"id": "n-inf-4", "side": "North", "type": "Infantry", "symbol": "I", "x": 10, "y": 4},
            {"id": "n-inf-5", "side": "North", "type": "Infantry", "symbol": "I", "x": 12, "y": 4},
            {"id": "n-inf-6", "side": "North", "type": "Infantry", "symbol": "I", "x": 14, "y": 4},
            {"id": "n-inf-7", "side": "North", "type": "Infantry", "symbol": "I", "x": 16, "y": 4},
            {"id": "n-inf-8", "side": "North", "type": "Infantry", "symbol": "I", "x": 18, "y": 4},
            {"id": "n-inf-9", "side": "North", "type": "Infantry", "symbol": "I", "x": 20, "y": 4},

            {"id": "n-cav-1", "side": "North", "type": "Cavalry", "symbol": "C", "x": 3, "y": 3},
            {"id": "n-cav-2", "side": "North", "type": "Cavalry", "symbol": "C", "x": 7, "y": 3},
            {"id": "n-cav-3", "side": "North", "type": "Cavalry", "symbol": "C", "x": 17, "y": 3},
            {"id": "n-cav-4", "side": "North", "type": "Cavalry", "symbol": "C", "x": 21, "y": 3},

            {"id": "n-art-1", "side": "North", "type": "Artillery", "symbol": "A", "x": 11, "y": 2},
            {"id": "n-art-2", "side": "North", "type": "Artillery", "symbol": "A", "x": 13, "y": 2},

            # FIXED: y coordinates changed from 1 to 0
            {"id": "n-rel-1", "side": "North", "type": "Relay", "symbol": "R", "x": 10, "y": 0},
            {"id": "n-rel-2", "side": "North", "type": "Relay", "symbol": "R", "x": 14, "y": 0},

            # === SOUTH FORCES (17 Units Total) ===
            {"id": "s-inf-1", "side": "South", "type": "Infantry", "symbol": "I", "x": 4, "y": 15},
            {"id": "s-inf-2", "side": "South", "type": "Infantry", "symbol": "I", "x": 6, "y": 15},
            {"id": "s-inf-3", "side": "South", "type": "Infantry", "symbol": "I", "x": 8, "y": 15},
            {"id": "s-inf-4", "side": "South", "type": "Infantry", "symbol": "I", "x": 10, "y": 15},
            {"id": "s-inf-5", "side": "South", "type": "Infantry", "symbol": "I", "x": 12, "y": 15},
            {"id": "s-inf-6", "side": "South", "type": "Infantry", "symbol": "I", "x": 14, "y": 15},
            {"id": "s-inf-7", "side": "South", "type": "Infantry", "symbol": "I", "x": 16, "y": 15},
            {"id": "s-inf-8", "side": "South", "type": "Infantry", "symbol": "I", "x": 18, "y": 15},
            {"id": "s-inf-9", "side": "South", "type": "Infantry", "symbol": "I", "x": 20, "y": 15},

            {"id": "s-cav-1", "side": "South", "type": "Cavalry", "symbol": "C", "x": 3, "y": 16},
            {"id": "s-cav-2", "side": "South", "type": "Cavalry", "symbol": "C", "x": 7, "y": 16},
            {"id": "s-cav-3", "side": "South", "type": "Cavalry", "symbol": "C", "x": 17, "y": 16},
            {"id": "s-cav-4", "side": "South", "type": "Cavalry", "symbol": "C", "x": 21, "y": 16},

            {"id": "s-art-1", "side": "South", "type": "Artillery", "symbol": "A", "x": 11, "y": 17},
            {"id": "s-art-2", "side": "South", "type": "Artillery", "symbol": "A", "x": 13, "y": 17},

            # FIXED: y coordinates changed from 18 to 19
            {"id": "s-rel-1", "side": "South", "type": "Relay", "symbol": "R", "x": 10, "y": 19},
            {"id": "s-rel-2", "side": "South", "type": "Relay", "symbol": "R", "x": 14, "y": 19}
        ],
        "turn": "North",
        "moves_left": 5,
        "moved_units_this_turn": [],
        "attack_executed_this_turn": False,
        "last_combat": None
    }


def generate_random_layout():
    cols = 25
    rows = 20

    mountains = {
        (9, 2), (10, 2), (11, 2), (12, 2),
        (9, 3), (9, 4),
        (9, 6), (9, 7), (9, 8),
        (10, 13), (11, 13), (12, 13), (13, 13), (14, 13), (15, 13),
        (15, 15), (15, 16), (15, 17)
    }

    def is_valid(x, y, occupied):
        if (x, y) in mountains:
            return False
        if (x, y) in occupied:
            return False
        return 0 <= x < cols and 0 <= y < rows

    occupied = set()

    # 1. Randomize Arsenals (behind or beside starting units)
    north_arsenals = set()
    while len(north_arsenals) < 2:
        ax = random.randint(1, cols - 2)
        ay = random.randint(0, 2)
        if is_valid(ax, ay, occupied):
            if not north_arsenals or all(abs(ax - ox) >= 3 for ox, oy in north_arsenals):
                north_arsenals.add((ax, ay))
                occupied.add((ax, ay))

    south_arsenals = set()
    while len(south_arsenals) < 2:
        ax = random.randint(1, cols - 2)
        ay = random.randint(17, 19)
        if is_valid(ax, ay, occupied):
            if not south_arsenals or all(abs(ax - ox) >= 3 for ox, oy in south_arsenals):
                south_arsenals.add((ax, ay))
                occupied.add((ax, ay))

    # 2. Place Relays adjacent to Arsenals (ensuring supply connection)
    directions = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
    north_relays = []
    for ax, ay in list(north_arsenals):
        placed = False
        dirs = list(directions)
        random.shuffle(dirs)
        for dx, dy in dirs:
            rx, ry = ax + dx, ay + dy
            if is_valid(rx, ry, occupied) and ry <= 3:
                north_relays.append((rx, ry))
                occupied.add((rx, ry))
                placed = True
                break
        if not placed:
            for ry in range(4):
                for rx in range(cols):
                    if is_valid(rx, ry, occupied):
                        north_relays.append((rx, ry))
                        occupied.add((rx, ry))
                        break
                if len(north_relays) == len(occupied) - 2:
                    break

    south_relays = []
    for ax, ay in list(south_arsenals):
        placed = False
        dirs = list(directions)
        random.shuffle(dirs)
        for dx, dy in dirs:
            rx, ry = ax + dx, ay + dy
            if is_valid(rx, ry, occupied) and ry >= 16:
                south_relays.append((rx, ry))
                occupied.add((rx, ry))
                placed = True
                break
        if not placed:
            for ry in range(16, 20):
                for rx in range(cols):
                    if is_valid(rx, ry, occupied):
                        south_relays.append((rx, ry))
                        occupied.add((rx, ry))
                        break
                if len(south_relays) == len(occupied) - 4:
                    break

    # Calculate starting LoC map
    def get_starting_loc(side_arsenals, side_relays):
        loc = set(side_arsenals)
        for rx, ry in side_relays:
            queue = [(rx, ry, 0)]
            visited = {(rx, ry)}
            while queue:
                cx, cy, dist = queue.pop(0)
                loc.add((cx, cy))
                if dist < 4:
                    for dx, dy in directions:
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < cols and 0 <= ny < rows and (nx, ny) not in mountains and (nx, ny) not in visited:
                            visited.add((nx, ny))
                            queue.append((nx, ny, dist + 1))
        return loc

    north_loc = get_starting_loc(north_arsenals, north_relays)
    south_loc = get_starting_loc(south_arsenals, south_relays)

    # 3. Place Combat Units (70% must start inside starting LoC)
    def place_side_units(side, starting_loc, start_y, end_y, relays):
        combat_types = (["Artillery"] * 2) + (["Cavalry"] * 4) + (["Infantry"] * 9)
        random.shuffle(combat_types)

        all_valid_cells = []
        for y in range(start_y, end_y + 1):
            for x in range(cols):
                if is_valid(x, y, occupied):
                    all_valid_cells.append((x, y))

        loc_cells = [c for c in all_valid_cells if c in starting_loc]
        
        placed_units = []
        # Place 11 units (out of 15, i.e. > 70%) on LoC cells
        num_loc_to_place = min(11, len(loc_cells))
        loc_placements = random.sample(loc_cells, num_loc_to_place)
        for c in loc_placements:
            occupied.add(c)
            placed_units.append(c)

        # Place remaining combat units anywhere valid in start zone
        remaining_count = 15 - num_loc_to_place
        remaining_valid = [c for c in all_valid_cells if c not in occupied]
        if len(remaining_valid) >= remaining_count:
            other_placements = random.sample(remaining_valid, remaining_count)
            for c in other_placements:
                occupied.add(c)
                placed_units.append(c)
        else:
            for c in remaining_valid:
                occupied.add(c)
                placed_units.append(c)

        units_list = []
        # Add Relays
        for idx, r in enumerate(relays):
            prefix = "n" if side == "North" else "s"
            units_list.append({
                "id": f"{prefix}-rel-{idx+1}",
                "side": side,
                "type": "Relay",
                "symbol": "R",
                "x": r[0],
                "y": r[1]
            })
        # Add Combat Units
        inf_cnt, cav_cnt, art_cnt = 1, 1, 1
        for idx, c in enumerate(placed_units):
            utype = combat_types[idx]
            prefix = "n" if side == "North" else "s"
            if utype == "Infantry":
                uid = f"{prefix}-inf-{inf_cnt}"
                inf_cnt += 1
                sym = "I"
            elif utype == "Cavalry":
                uid = f"{prefix}-cav-{cav_cnt}"
                cav_cnt += 1
                sym = "C"
            else:
                uid = f"{prefix}-art-{art_cnt}"
                art_cnt += 1
                sym = "A"
            units_list.append({
                "id": uid,
                "side": side,
                "type": utype,
                "symbol": sym,
                "x": c[0],
                "y": c[1]
            })
        return units_list

    north_units_list = place_side_units("North", north_loc, 0, 5, north_relays)
    south_units_list = place_side_units("South", south_loc, 14, 19, south_relays)

    all_units = north_units_list + south_units_list

    # Combined forts: standard forts + all arsenals
    fortresses = {
        (7, 1), (12, 8), (20, 7),
        (2, 12), (14, 11), (22, 14)
    }
    for a in north_arsenals:
        fortresses.add(a)
    for a in south_arsenals:
        fortresses.add(a)

    return {
        "units": all_units,
        "arsenals": {
            "North": list(north_arsenals),
            "South": list(south_arsenals)
        },
        "fortresses": list(fortresses)
    }


def check_win_condition(units: list, arsenals: dict = None) -> str | None:
    """
    Returns 'North', 'South', or None.
    Win conditions:
      1. Annihilation  — eliminate all enemy units.
      2. Full Capture  — occupy BOTH enemy arsenal tiles simultaneously.
         (Capturing one arsenal collapses enemy LoC and extends yours — but
          you still need to hold both to claim total victory or destroy the remnants.)
    """
    north_units = [u for u in units if u["side"] == "North"]
    south_units = [u for u in units if u["side"] == "South"]

    if not north_units:
        return "South"
    if not south_units:
        return "North"

    north_pos = {(u["x"], u["y"]) for u in north_units}
    south_pos = {(u["x"], u["y"]) for u in south_units}

    # Arsenal tile coordinates
    if not arsenals:
        north_arsenals = {(7, 3), (14, 1)}
        south_arsenals = {(2, 19), (22, 19)}
    else:
        north_arsenals = set(tuple(a) for a in arsenals.get("North", []))
        south_arsenals = set(tuple(a) for a in arsenals.get("South", []))

    # Full capture: you must occupy ALL enemy arsenal tiles at once
    if north_arsenals.issubset(south_pos):   # South holds both North arsenals
        return "South"
    if south_arsenals.issubset(north_pos):   # North holds both South arsenals
        return "North"

    # Deactivation win condition: if one side has active (connected) units but the other side
    # has 0 active units (all cut off/deactivated), the active side wins.
    try:
        connected_north = engine.get_connected_units(units, "North")
        connected_south = engine.get_connected_units(units, "South")
        if north_units and not connected_north and connected_south:
            return "South"
        if south_units and not connected_south and connected_north:
            return "North"
    except Exception:
        pass

    return None



def initialize_room(room_id: str, vs_ai: bool = False, ai_vs_ai: bool = False, player_side: str = "North", layout_type: str = "skirmish_10x10"):
    if room_id not in rooms:
        rooms[room_id] = {
            "state": get_initial_state(),
            "history": [],
            "connections": [],
            "password": None,
            "vs_ai": vs_ai,
            "ai_vs_ai": ai_vs_ai, # Track if both sides are automated
            "sim_running": False,  # Flag to prevent spawning duplicate task threads
            "turn_counter": 0,
            "ai_position_history": {},
            "player_side": player_side,
            "ai_side": "South" if player_side == "North" else "North",
            "layout_type": "skirmish_10x10",
            "cols": 10,
            "rows": 10,
            "arsenals": {
                "North": {(4, 0)},
                "South": {(5, 9)}
            },
            "fortresses": {(4, 0), (5, 9)},
            "lazarus_pits": {(2, 4), (7, 5)}
        }
        rooms[room_id]["state"]["units"] = [
            # North Forces (Unique faces: I, A, C, R, M, S)
            {"id": "n-art-1", "type": "artillery", "symbol": "A", "side": "North", "x": 4, "y": 0, "faces": {"top": "A", "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "I"}},
            {"id": "n-rel-1", "type": "relay", "symbol": "R", "side": "North", "x": 4, "y": 1, "faces": {"top": "R", "bottom": "S", "front": "C", "back": "I", "left": "M", "right": "A"}},
            {"id": "n-inf-1", "type": "mine", "symbol": "M", "side": "North", "x": 3, "y": 2, "faces": {"top": "M", "bottom": "S", "front": "C", "back": "R", "left": "I", "right": "A"}},
            {"id": "n-cav-1", "type": "cavalry", "symbol": "C", "side": "North", "x": 5, "y": 2, "faces": {"top": "C", "bottom": "S", "front": "I", "back": "R", "left": "M", "right": "A"}},
            # South Forces (Unique faces: I, A, C, R, M, S)
            {"id": "s-art-1", "type": "artillery", "symbol": "A", "side": "South", "x": 5, "y": 9, "faces": {"top": "A", "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "I"}},
            {"id": "s-rel-1", "type": "relay", "symbol": "R", "side": "South", "x": 5, "y": 8, "faces": {"top": "R", "bottom": "S", "front": "C", "back": "I", "left": "M", "right": "A"}},
            {"id": "s-inf-1", "type": "mine", "symbol": "M", "side": "South", "x": 6, "y": 7, "faces": {"top": "M", "bottom": "S", "front": "C", "back": "R", "left": "I", "right": "A"}},
            {"id": "s-cav-1", "type": "cavalry", "symbol": "C", "side": "South", "x": 4, "y": 7, "faces": {"top": "C", "bottom": "S", "front": "I", "back": "R", "left": "M", "right": "A"}}
        ]


async def broadcast_room_state(room_id: str):
    room = rooms.get(room_id)
    if not room:
        return

    engine.arsenals = room.get("arsenals", engine.arsenals)
    engine.fortresses = room.get("fortresses", engine.fortresses)
    engine.cols = room.get("cols", 25)
    engine.rows = room.get("rows", 20)

    st = room["state"]
    n_loc = [[x, y] for x, y in engine.compute_lines_of_communication(st["units"], "North")]
    s_loc = [[x, y] for x, y in engine.compute_lines_of_communication(st["units"], "South")]
    connected = list(engine.get_connected_units(st["units"], "North")) + list(
        engine.get_connected_units(st["units"], "South"))

    # Build a name → side map to send to all clients
    players = {"North": None, "South": None}
    for conn in room["connections"]:
        if conn["side"] in ("North", "South"):
            players[conn["side"]] = conn["name"]

    winner = check_win_condition(st["units"], room.get("arsenals"))

    payload = {
        "units": st["units"],
        "turn": st["turn"],
        "movesLeft": st["moves_left"],
        "attackExecuted": st["attack_executed_this_turn"],
        "movedUnitsThisTurn": st["moved_units_this_turn"],
        "linesOfCommunication": {"North": n_loc, "South": s_loc},
        "connectedUnitIds": connected,
        "canUndo": len(room["history"]) > 0,
        "players": players,
        "winner": winner,
        "lastCombat": st.get("last_combat"),
        "cols": room.get("cols", 25),
        "rows": room.get("rows", 20),
        "arsenals": {
            "North": list(room.get("arsenals", {}).get("North", [])),
            "South": list(room.get("arsenals", {}).get("South", []))
        },
        "fortresses": list(room.get("fortresses", [])),
        "lazarusPits": [[x, y] for x, y in room.get("lazarus_pits", [])],
        "mines": st.get("mines", []),
        "awaitingLazarusChoice": st.get("awaiting_lazarus_choice")
    }

    for conn in room["connections"]:
        try:
            # Each client also learns their own assigned side
            personal_payload = {**payload, "yourSide": conn["side"]}
            await conn["ws"].send_json(personal_payload)
        except Exception:
            pass


def save_state_to_history(room_id: str):
    """Deep-copies current game state into the undo stack before an action alters it."""
    room = rooms[room_id]
    # Keep up to last 10 snapshots to avoid memory bloat
    if len(room["history"]) >= 10:
        room["history"].pop(0)
    room["history"].append(copy.deepcopy(room["state"]))


async def run_ai_simulation(room_id: str):
    """Automated background task running both AI agents at maximum velocity."""
    try:
        while True:
            room = rooms.get(room_id)
            if not room or not room.get("ai_vs_ai", False) or not room["connections"]:
                break

            st = room["state"]
            current_side = st["turn"]
            ai_agent = WarGameAI(engine, side=current_side, position_history=room.get("ai_position_history"),
                                 turn_counter=room.get("turn_counter", 0))

            # Process actions rapidly
            while st["turn"] == current_side and st["moves_left"] > 0:
                # Scaled down to 50ms for ultra-rapid visual automation updates
                if check_win_condition(st["units"], room.get("arsenals")):
                    return

                delay = 0.8 if room.get("layout_type") == "skirmish_10x10" else 0.05
                await asyncio.sleep(delay)

                room = rooms.get(room_id)
                if not room or not room.get("ai_vs_ai", False) or not room["connections"]:
                    return

                st = room["state"]
                print(
                    f"🧠 [AI ENGINE EVAL] Side: {current_side} | Moves Left: {st['moves_left']} | Units Active: {len(st['units'])}")

                best_act = ai_agent.select_best_action(st)
                print(
                    f"📋 [AI DECISION] Selected Action: Type='{best_act['action_type']}' | Unit='{best_act.get('unitId')}' | Target=({best_act.get('x')}, {best_act.get('y')})")

                if best_act["action_type"] == "end_turn":
                    print(f"🛑 [SIM AI TURN END] Side {current_side} explicitly chose to terminate the turn loop.")
                    break

                if best_act["action_type"] == "move":
                    u_prev_x = None
                    u_prev_y = None
                    u_symbol_before = None
                    u_side_before = None

                    for u in st["units"]:
                        if u["id"] == best_act["unitId"]:
                            u_prev_x = u["x"]
                            u_prev_y = u["y"]
                            u_symbol_before = u["symbol"]
                            u_side_before = u["side"]
                            dx = best_act["x"] - u["x"]
                            dy = best_act["y"] - u["y"]
                            u["x"], u["y"] = best_act["x"], best_act["y"]

                            # Always execute the matrix rotation layout checks
                            faces = u.get("faces",
                                          {"top": u["symbol"], "bottom": "A", "front": "C", "back": "R", "left": "I",
                                           "right": "A"})
                            new_faces = rotate_cube_faces(faces, dx, dy)
                            u["faces"] = new_faces

                            transform_target = best_act.get("transform_to")
                            if transform_target is not None:
                                u["type"] = str(transform_target).lower()
                            else:
                                # AUTOMATIC IDENTITY SYNC FALLBACK LAYER
                                if new_faces["top"] != u_symbol_before:
                                    mapping = {"A": "artillery", "I": "infantry", "C": "cavalry", "R": "relay",
                                               "M": "mine", "S": "shield"}
                                    if new_faces["top"] in mapping:
                                        u["type"] = mapping[new_faces["top"]]

                            # Map visual character representation accurately
                            if u["type"] == "artillery":
                                u["symbol"] = "A"
                            elif u["type"] == "infantry":
                                u["symbol"] = "I"
                            elif u["type"] == "cavalry":
                                u["symbol"] = "C"
                            elif u["type"] == "relay":
                                u["symbol"] = "R"
                            elif u["type"] == "mine":
                                u["symbol"] = "M"
                            elif u["type"] == "shield":
                                u["symbol"] = "S"

                            if transform_target is not None:
                                print(f"🎲 [AI ACTIVE ROLL] Unit ID={best_act['unitId']} rolled to Type: {u['type']}")
                            else:
                                print(
                                    f"🚄 [AI FLAT SLIDE] Unit ID={best_act['unitId']} slid flatly. Synced Type: {u['type']}")
                            break

                    # 1. AI vs AI Mine Spawning
                    if u_symbol_before == "M" and u_prev_x is not None:
                        st["mines"].append({"x": u_prev_x, "y": u_prev_y, "side": u_side_before})
                        print(f"💣 [AI MINE SPAWNED] at ({u_prev_x}, {u_prev_y}) by side={u_side_before}")

                    # 2. AI vs AI Mine Detonation
                    mine_triggered = None
                    for mine in st["mines"]:
                        if mine["x"] == best_act["x"] and mine["y"] == best_act["y"]:
                            mine_triggered = mine
                            break
                    if mine_triggered:
                        st["mines"].remove(mine_triggered)
                        st["units"] = [unit for unit in st["units"] if unit["id"] != best_act["unitId"]]
                        print(
                            f"💥 [AI MINE DETONATED] Unit {best_act['unitId']} vaporized at ({best_act['x']}, {best_act['y']})!")

                    st["moves_left"] -= 1
                    st["moved_units_this_turn"].append(best_act["unitId"])

                elif best_act["action_type"] == "attack":
                    tx, ty = best_act["x"], best_act["y"]
                    mover = next((u for u in st["units"] if u["id"] == best_act["unitId"]), None)
                    combat = engine.calculate_combat(st["units"], current_side, tx, ty)
                    if combat.get("valid"):
                        if combat["result"] == "DESTROY":
                            st["units"] = [u for u in st["units"] if not (u["x"] == tx and u["y"] == ty)]
                        st["last_combat"] = {
                            "attackerX": mover["x"] if mover else tx,
                            "attackerY": mover["y"] if mover else ty,
                            "targetX": tx, "targetY": ty, "result": combat["result"]
                        }
                        print(
                            f"⚔️ [SIM AI ATTACK] {current_side} Unit {best_act['unitId']} hit ({tx}, {ty}) -> {combat['result']}")
                    else:
                        print(f"❌ [SIM AI ATTACK INVALID] ({tx}, {ty}) -> {combat.get('reason')}")

                    # ENFORCE STRICT SIMULATION ACTION LOCKING
                    st["moved_units_this_turn"].append(best_act["unitId"])
                    st["attack_executed_this_turn"] = True

                await broadcast_room_state(room_id)

            # Hand over active control matrix directly to opposing instance
            room["history"].clear()
            room["turn_counter"] = room.get("turn_counter", 0) + 1
            st["turn"] = "South" if current_side == "North" else "North"
            st["moves_left"] = 5
            st["moved_units_this_turn"] = []
            st["attack_executed_this_turn"] = False
            st["last_combat"] = None
            await broadcast_room_state(room_id)

            # Brief micro-cooldown before next AI takes over
            await asyncio.sleep(0.05)
    finally:
        room = rooms.get(room_id)
        if room:
            room["sim_running"] = False


async def run_ai_turn_if_needed(room_id: str):
    room = rooms.get(room_id)
    if not room or not room.get("vs_ai", False):
        return
    st = room["state"]
    ai_side = room.get("ai_side", "South")
    player_side = room.get("player_side", "North")

    if st["turn"] == ai_side and not check_win_condition(st["units"], room.get("arsenals")):
        ai_agent = WarGameAI(engine, side=ai_side, position_history=room.get("ai_position_history"),
                             turn_counter=room.get("turn_counter", 0))

        while st["turn"] == ai_side and st["moves_left"] > 0:
            delay = 0.8
            await asyncio.sleep(delay)
            room = rooms.get(room_id)
            if not room or not room["connections"]:
                break

            print(f"🧠 [AI ENGINE EVAL] Side: {ai_side} | Moves Left: {st['moves_left']}")
            best_act = ai_agent.select_best_action(st)
            print(
                f"📋 [AI DECISION] Selected Action: Type='{best_act['action_type']}' | Unit='{best_act.get('unitId')}' | Target=({best_act.get('x')}, {best_act.get('y')})")

            if best_act["action_type"] == "end_turn":
                print(f"🛑 [AI TURN END] Agent explicitly chose to terminate the turn loop.")
                break

            if best_act["action_type"] == "move":
                u_prev_x = None
                u_prev_y = None
                u_symbol_before = None
                u_side_before = None

                for u in st["units"]:
                    if u["id"] == best_act["unitId"]:
                        u_prev_x = u["x"]
                        u_prev_y = u["y"]
                        u_symbol_before = u["symbol"]
                        u_side_before = u["side"]
                        dx = best_act["x"] - u["x"]
                        dy = best_act["y"] - u["y"]
                        u["x"], u["y"] = best_act["x"], best_act["y"]

                        # Always execute matrix rotation updates
                        faces = u.get("faces",
                                      {"top": u["symbol"], "bottom": "A", "front": "C", "back": "R", "left": "I",
                                       "right": "A"})
                        new_faces = rotate_cube_faces(faces, dx, dy)
                        u["faces"] = new_faces

                        transform_target = best_act.get("transform_to")
                        if transform_target is not None:
                            u["type"] = str(transform_target).lower()
                        else:
                            # AUTOMATIC IDENTITY SYNC FALLBACK LAYER
                            if new_faces["top"] != u_symbol_before:
                                mapping = {"A": "artillery", "I": "infantry", "C": "cavalry", "R": "relay", "M": "mine",
                                           "S": "shield"}
                                if new_faces["top"] in mapping:
                                    u["type"] = mapping[new_faces["top"]]

                        # Map visual character representation accurately
                        if u["type"] == "artillery":
                            u["symbol"] = "A"
                        elif u["type"] == "infantry":
                            u["symbol"] = "I"
                        elif u["type"] == "cavalry":
                            u["symbol"] = "C"
                        elif u["type"] == "relay":
                            u["symbol"] = "R"
                        elif u["type"] == "mine":
                            u["symbol"] = "M"
                        elif u["type"] == "shield":
                            u["symbol"] = "S"
                        break

                # 1. AI Mine Spawning
                if u_symbol_before == "M" and u_prev_x is not None:
                    st["mines"].append({"x": u_prev_x, "y": u_prev_y, "side": u_side_before})

                # 2. AI Mine Detonation
                mine_triggered = None
                for mine in st["mines"]:
                    if mine["x"] == best_act["x"] and mine["y"] == best_act["y"]:
                        mine_triggered = mine
                        break
                if mine_triggered:
                    st["mines"].remove(mine_triggered)
                    st["units"] = [unit for unit in st["units"] if unit["id"] != best_act["unitId"]]
                    print(f"💥 [MINE DETONATED] Enemy AI Unit {best_act['unitId']} vaporized!")

                st["moves_left"] -= 1
                st["moved_units_this_turn"].append(best_act["unitId"])

            elif best_act["action_type"] == "attack":
                tx, ty = best_act["x"], best_act["y"]
                mover = next((u for u in st["units"] if u["id"] == best_act["unitId"]), None)
                combat = engine.calculate_combat(st["units"], ai_side, tx, ty)
                if combat.get("valid"):
                    if combat["result"] == "DESTROY":
                        st["units"] = [u for u in st["units"] if not (u["x"] == tx and u["y"] == ty)]
                    st["last_combat"] = {
                        "attackerX": mover["x"] if mover else tx,
                        "attackerY": mover["y"] if mover else ty,
                        "targetX": tx, "targetY": ty, "result": combat["result"]
                    }
                    print(
                        f"⚔️ [AI ATTACK] Unit {best_act['unitId']} targeted ({tx}, {ty}) -> Result: {combat['result']}")
                else:
                    print(f"❌ [AI ATTACK INVALID] Targeted ({tx}, {ty}) -> Reason: {combat.get('reason')}")

                st["moved_units_this_turn"].append(best_act["unitId"])
                st["attack_executed_this_turn"] = True

            # Broadcast intermediate actions without mutating turns prematurely
            await broadcast_room_state(room_id)

            # Check win condition immediately after action to prevent unnecessary steps if game ended
            if check_win_condition(st["units"], room.get("arsenals")):
                break

        # ── FIXED: ALL MOVEMENTS COMPLETED. NOW SWITCH CONTROL TO PLAYER ──
        print(f"🔄 [TURN SWITCH] AI finished all actions. Control to {player_side}.")
        st["turn"] = player_side
        st["moves_left"] = 5
        st["moved_units_this_turn"] = []
        st["attack_executed_this_turn"] = False
        st["last_combat"] = None
        await broadcast_room_state(room_id)

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    name = websocket.query_params.get("name", "Unknown")
    password = websocket.query_params.get("password", "")
    vs_ai = websocket.query_params.get("vs_ai", "false").lower() == "true"
    ai_vs_ai = websocket.query_params.get("ai_vs_ai", "false").lower() == "true"
    player_side = websocket.query_params.get("player_side", "North")
    layout_type = "skirmish_10x10"

    await websocket.accept()
    initialize_room(room_id, vs_ai=vs_ai, ai_vs_ai=ai_vs_ai, player_side=player_side, layout_type="skirmish_10x10")

    room = rooms[room_id]

    # Forcefully evict ghost entries if running an automated or solo testing sandbox
    if room.get("vs_ai", False) or room.get("ai_vs_ai", False):
        room["connections"] = []

    # --- Password check ---
    if room["password"] is None:
        room["password"] = password
    elif room["password"] != password:
        await websocket.send_json({"type": "error", "message": "Authentication failed: incorrect password."})
        await websocket.close()
        return

    existing_conn = next((c for c in room["connections"] if c["name"] == name), None)

    if existing_conn:
        # Inherit your original side assignment and remove the stale ghost connection
        assigned_side = existing_conn["side"]
        room["connections"].remove(existing_conn)
        try:
            await existing_conn["ws"].close()
        except Exception:
            pass
    else:
        if room.get("vs_ai", False):
            assigned_side = room.get("player_side", "North")
        else:
            # Standard side assignment for a brand new player joining
            taken_sides = {conn["side"] for conn in room["connections"] if conn["side"] is not None}

            if "North" not in taken_sides:
                assigned_side = "North"
            elif "South" not in taken_sides:
                assigned_side = "South"
            else:
                # Room is full — reject the 3rd+ connection
                await websocket.send_json({
                    "type": "error",
                    "message": "Room is full. This battle already has two commanders."
                })
                await websocket.close()
                return

    conn_entry = {"ws": websocket, "name": name, "side": assigned_side if not room.get("ai_vs_ai") else "Observer"}
    room["connections"].append(conn_entry)

    await broadcast_room_state(room_id)

    # Fire up the automated sandbox task if it isn't running yet
    if room.get("ai_vs_ai", False) and not room.get("sim_running", False):
        room["sim_running"] = True
        asyncio.create_task(run_ai_simulation(room_id))

    if room.get("vs_ai", False):
        asyncio.create_task(run_ai_turn_if_needed(room_id))

    try:
        while True:
            # Ensure engine knows the current room's layout
            engine.arsenals = room.get("arsenals", engine.arsenals)
            engine.fortresses = room.get("fortresses", engine.fortresses)
            engine.cols = room.get("cols", 25)
            engine.rows = room.get("rows", 20)

            data = await websocket.receive_json()
            st = room["state"]
            action = data.get("action")

            # --- Turn Authorization ---
            # Only the player whose side matches the current turn may act.
            # Exceptions: restart is always allowed by either player.
            if action != "restart" and conn_entry["side"] != st["turn"]:
                await websocket.send_json({
                    "type": "error",
                    "message": f"It is {st['turn']}'s turn. Wait for your opponent."
                })
                continue

            # Freeze all actions (except restart) once the game has a winner
            if action != "restart" and check_win_condition(st["units"], room.get("arsenals")):
                await websocket.send_json({"type": "error", "message": "The battle is over. Restart to play again."})
                continue

            # --- Lazarus Pit Block ---
            if action != "restart" and st.get("awaiting_lazarus_choice") and action != "choose_lazarus_face":
                await websocket.send_json({"type": "error", "message": "Must resolve Lazarus Pit choice first."})
                continue

            if action == "choose_lazarus_face":
                pending = st.get("awaiting_lazarus_choice")
                if not pending or pending["side"] != conn_entry["side"]:
                    await websocket.send_json({"type": "error", "message": "No pending choice for you."})
                    continue
                unit_id = pending["unitId"]
                symbol = data.get("symbol") # 'I', 'A', 'C', 'R', 'M', or 'S'
                if symbol not in ("I", "A", "C", "R", "M", "S"):
                    await websocket.send_json({"type": "error", "message": "Invalid symbol choice."})
                    continue
                
                for u in st["units"]:
                    if u["id"] == unit_id:
                        faces = u.get("faces", {"top": u["symbol"], "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "A"})
                        found_face = None
                        for k, v in faces.items():
                            if v == symbol:
                                found_face = k
                                break
                        if found_face:
                            old_top = faces["top"]
                            faces["top"] = symbol
                            faces[found_face] = old_top
                        
                        u["faces"] = faces
                        u["symbol"] = symbol
                        if symbol == "I": u["type"] = "infantry"
                        elif symbol == "A": u["type"] = "artillery"
                        elif symbol == "C": u["type"] = "cavalry"
                        elif symbol == "R": u["type"] = "relay"
                        elif symbol == "M": u["type"] = "mine"
                        elif symbol == "S": u["type"] = "shield"
                        
                        print(f"🌟 [LAZARUS CHOICE] Unit {unit_id} reshaped to {symbol}. New faces: {faces}")
                        break
                
                st["awaiting_lazarus_choice"] = None
                await broadcast_room_state(room_id)
                continue


            if action == "move":
                if st["moves_left"] <= 0:
                    await websocket.send_json({"type": "error", "message": "No moves remaining."})
                    continue

                unit_id = data.get("unitId")
                tx, ty = data.get("x"), data.get("y")
                transform_target = data.get("transform_to")

                is_valid, reason = engine.validate_move(st["units"], unit_id, tx, ty, st["moved_units_this_turn"])
                if is_valid:
                    save_state_to_history(room_id)  # Log history frame
                    print(
                        f"[MOVE] Success: ID={unit_id} to ({tx},{ty}) in room={room_id}. History size now: {len(room['history'])}")
                    # Pre-move checks for mine creator spawning
                    u_prev_x = None
                    u_prev_y = None
                    u_symbol_before = None
                    u_side_before = None

                    for u in st["units"]:
                        if u["id"] == unit_id:
                            u_prev_x = u["x"]
                            u_prev_y = u["y"]
                            u_symbol_before = u["symbol"]
                            u_side_before = u["side"]
                            dx = tx - u["x"]
                            dy = ty - u["y"]
                            u["x"], u["y"] = tx, ty

                            if transform_target is not None:
                                faces = u.get("faces",
                                                {"top": u["symbol"], "bottom": "S", "front": "C", "back": "R",
                                                "left": "M", "right": "A"})
                                new_faces = rotate_cube_faces(faces, dx, dy)
                                u["faces"] = new_faces
                                u["symbol"] = new_faces["top"]
                                u["type"] = str(transform_target).lower()
                                print(
                                    f"🎲 [ACTIVE ROLL] Unit ID={unit_id} moved dx={dx}, dy={dy} -> Type: {u['type']}")
                            else:
                                print(f"🚄 [FLAT SLIDE] Unit ID={unit_id} slid flatly. Orientation kept.")
                            break
                    
                    # 1. Mine Spawning: If symbol before was M, spawn mine at u_prev_x, u_prev_y
                    if u_symbol_before == "M" and u_prev_x is not None:
                        st["mines"].append({"x": u_prev_x, "y": u_prev_y, "side": u_side_before})
                        print(f"💣 [MINE SPAWNED] at ({u_prev_x}, {u_prev_y}) by side={u_side_before}")
                    
                    # 2. Mine Detonation: If landed on a cell containing a mine, detonate!
                    mine_triggered = None
                    for mine in st["mines"]:
                        if mine["x"] == tx and mine["y"] == ty:
                            mine_triggered = mine
                            break
                    if mine_triggered:
                        st["mines"].remove(mine_triggered)
                        st["units"] = [unit for unit in st["units"] if unit["id"] != unit_id]
                        print(f"💥 [MINE DETONATED] at ({tx}, {ty}). Unit {unit_id} vaporized!")
                    
                    # 3. Lazarus Pit check: If unit is still alive and landed on a Lazarus Pit, trigger choice
                    unit_still_alive = any(unit["id"] == unit_id for unit in st["units"])
                    if unit_still_alive and (tx, ty) in room.get("lazarus_pits", set()):
                        st["awaiting_lazarus_choice"] = {"unitId": unit_id, "side": u_side_before}
                        print(f"🌟 [LAZARUS PIT TRIGGERED] Unit {unit_id} landed at ({tx}, {ty}). Awaiting choice from {u_side_before}")
                    
                    st["moves_left"] -= 1
                    st["moved_units_this_turn"].append(unit_id)
                    await broadcast_room_state(room_id)
                else:
                    print(f"[MOVE] Refused: ID={unit_id} to ({tx},{ty}) in room={room_id} because: {reason}")
                    await websocket.send_json({"type": "error", "message": reason})

            elif action == "attack":
                if st["attack_executed_this_turn"]:
                    await websocket.send_json({"type": "error", "message": "Attack action limit reached."})
                    continue

                tx, ty = data.get("x"), data.get("y")

                # Block attacking shielded units
                target_unit = next((u for u in st["units"] if u["x"] == tx and u["y"] == ty), None)
                if target_unit and target_unit.get("symbol") == "S":
                    await websocket.send_json({"type": "error", "message": "Target unit is shielded and immune to attacks."})
                    continue

                combat = engine.calculate_combat(st["units"], st["turn"], tx, ty)

                if combat.get("valid"):
                    save_state_to_history(room_id)  # Log history frame
                    res = combat["result"]
                    attacker_unit = next((u for u in st["units"] if u["side"] == st["turn"] and
                                          abs(u["x"] - tx) <= 3 and abs(u["y"] - ty) <= 3), None)
                    print(f"[ATTACK] Success: target=({tx},{ty}) result={res} in room={room_id}. History size now: {len(room['history'])}")
                    if res == "DESTROY":
                        st["units"] = [u for u in st["units"] if not (u["x"] == tx and u["y"] == ty)]
                        msg = "Strike Success! Unit eliminated."
                    else:
                        msg = "Attack repelled."

                    st["last_combat"] = {
                        "attackerX": attacker_unit["x"] if attacker_unit else tx,
                        "attackerY": attacker_unit["y"] if attacker_unit else ty,
                        "targetX": tx, "targetY": ty, "result": res
                    }
                    st["attack_executed_this_turn"] = True
                    await broadcast_room_state(room_id)
                else:
                    print(f"[ATTACK] Refused: target=({tx},{ty}) in room={room_id} because: {combat.get('reason')}")
                    await websocket.send_json({"type": "error", "message": combat.get("reason", "Invalid attack target.")})

            elif action == "undo":
                if room["history"]:
                    old_state = room["history"].pop()
                    print(f"[UNDO] Restoring state in room={room_id}. History size remaining: {len(room['history'])}")
                    room["state"] = old_state
                    await broadcast_room_state(room_id)
                else:
                    print(f"[UNDO] Refused in room={room_id}: history is empty")
                    await websocket.send_json({"type": "error", "message": "Nothing left to undo."})

            elif action == "restart":
                room["history"].clear()
                room["turn_counter"] = 0
                room["ai_position_history"] = {}
                room["cols"] = 10
                room["rows"] = 10
                room["arsenals"] = {
                    "North": {(4, 0)},
                    "South": {(5, 9)}
                }
                room["fortresses"] = {(4, 0), (5, 9)}
                room["lazarus_pits"] = {(2, 4), (7, 5)}
                room["state"] = {
                    "mines": [],
                    "awaiting_lazarus_choice": None,
                    "units": [
                        {"id": "n-art-1", "type": "artillery", "symbol": "A", "side": "North", "x": 4, "y": 0, "faces": {"top": "A", "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "I"}},
                        {"id": "n-rel-1", "type": "relay", "symbol": "R", "side": "North", "x": 4, "y": 1, "faces": {"top": "R", "bottom": "S", "front": "C", "back": "I", "left": "M", "right": "A"}},
                        {"id": "n-inf-1", "type": "mine", "symbol": "M", "side": "North", "x": 3, "y": 2, "faces": {"top": "M", "bottom": "S", "front": "C", "back": "R", "left": "I", "right": "A"}},
                        {"id": "n-cav-1", "type": "cavalry", "symbol": "C", "side": "North", "x": 5, "y": 2, "faces": {"top": "C", "bottom": "S", "front": "I", "back": "R", "left": "M", "right": "A"}},
                        {"id": "s-art-1", "type": "artillery", "symbol": "A", "side": "South", "x": 5, "y": 9, "faces": {"top": "A", "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "I"}},
                        {"id": "s-rel-1", "type": "relay", "symbol": "R", "side": "South", "x": 5, "y": 8, "faces": {"top": "R", "bottom": "S", "front": "C", "back": "I", "left": "M", "right": "A"}},
                        {"id": "s-inf-1", "type": "mine", "symbol": "M", "side": "South", "x": 6, "y": 7, "faces": {"top": "M", "bottom": "S", "front": "C", "back": "R", "left": "I", "right": "A"}},
                        {"id": "s-cav-1", "type": "cavalry", "symbol": "C", "side": "South", "x": 4, "y": 7, "faces": {"top": "C", "bottom": "S", "front": "I", "back": "R", "left": "M", "right": "A"}}
                    ],
                    "turn": "North",
                    "moves_left": 5,
                    "moved_units_this_turn": [],
                    "attack_executed_this_turn": False,
                    "last_combat": None
                }
                await broadcast_room_state(room_id)
                if room.get("vs_ai", False):
                    asyncio.create_task(run_ai_turn_if_needed(room_id))
                elif room.get("ai_vs_ai", False) and not room.get("sim_running", False):
                    room["sim_running"] = True
                    asyncio.create_task(run_ai_simulation(room_id))

            # elif action == "end_turn":
            #     room["history"].clear()  # Wipe undo stack when turn officially locks down
            #     next_side = "South" if st["turn"] == "North" else "North"
            #     st["turn"] = next_side
            #     st["moves_left"] = 5
            #     st["moved_units_this_turn"] = []
            #     st["attack_executed_this_turn"] = False
            #     await broadcast_room_state(room_id)

            elif action == "end_turn":
                room["history"].clear()  # Wipe undo stack when turn officially locks down
                room["turn_counter"] = room.get("turn_counter", 0) + 1
                next_side = "South" if st["turn"] == "North" else "North"
                st["turn"] = next_side
                st["moves_left"] = 5
                st["moved_units_this_turn"] = []
                st["attack_executed_this_turn"] = False
                st["last_combat"] = None

                # Broadcast the shift to South's turn immediately
                await broadcast_room_state(room_id)
                
                # --- INTERCEPT FOR AI MATCH PLAY ---
                if room.get("vs_ai", False):
                    asyncio.create_task(run_ai_turn_if_needed(room_id))

    except WebSocketDisconnect:
        room["connections"].remove(conn_entry)
        if not room["connections"]:
            del rooms[room_id]  # Clean up memory if empty
        else:
            # Notify remaining player that their opponent disconnected
            for remaining in room["connections"]:
                try:
                    await remaining["ws"].send_json({
                        "type": "error",
                        "message": f"Opponent '{name}' has disconnected."
                    })
                except Exception:
                    pass


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port
    )
