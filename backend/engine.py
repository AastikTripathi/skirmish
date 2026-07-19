# engine.py
from typing import List, Dict, Tuple, Set


class GameEngine:
    def __init__(self):
        self.cols = 10
        self.rows = 10

        # No mountains or passes in Skirmish Mode
        self.mountains = set()
        self.passes = set()

        # Strategic Fortresses (Both pure Forts and Arsenals yield defensive cover bonuses)
        self.fortresses = {
            (4, 0),  # North Arsenal / Fort
            (5, 9)  # South Arsenal / Fort
        }

        self.arsenals = {
            "North": {(4, 0)},
            "South": {(5, 9)}
        }

        self.directions = [
            (0, 1), (0, -1), (1, 0), (-1, 0),  # Orthogonal
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Diagonal
        ]

        # Official Unit Stat Catalog - Modified Cavalry, Shield, and Mine Profiles
        self.unit_stats = {
            "infantry": {"speed": 1, "range": 2, "offense": 4, "defense": 6},
            "cavalry": {"speed": 2, "range": 2, "offense": 5, "defense": 2, "charge": 7},  # Defense reduced 5 -> 2
            "artillery": {"speed": 1, "range": 3, "offense": 5, "defense": 8},
            "relay": {"speed": 1, "range": 1, "offense": 1, "defense": 1},
            "mine": {"speed": 1, "range": 1 , "offense": 0, "defense": 5},
            "shield": {"speed": 1, "range": 1, "offense": 0, "defense": 26}
        }

    def get_stats(self, unit_type: str) -> dict:
        u_type = unit_type.lower()
        if "infantry" in u_type: return self.unit_stats["infantry"]
        if "cavalry" in u_type: return self.unit_stats["cavalry"]
        if "artillery" in u_type: return self.unit_stats["artillery"]
        if "mine" in u_type: return self.unit_stats["mine"]
        if "shield" in u_type: return self.unit_stats["shield"]
        return self.unit_stats["relay"]

    # def compute_lines_of_communication(self, units: List[Dict], side: str) -> Set[Tuple[int, int]]:
    #     opponent_side = "North" if side == "South" else "South"
    #     enemy_pos = {(u['x'], u['y']) for u in units if u['side'] == opponent_side}
    #     friendly_pos = {(u['x'], u['y']) for u in units if u['side'] == side}

    #     active_loc_cells = set()
    #     enemy_positions = {(u['x'], u['y']) for u in units if u['side'] != side}
    #     friendly_relays = {u['id']: (u['x'], u['y']) for u in units if
    #                        u['side'] == side and 'relay' in u['type'].lower()}

    #     # MODIFIED: Only queue arsenals that are NOT occupied by the enemy
    #     emitters_queue = [
    #         (ax, ay) for ax, ay in self.arsenals[side] if (ax, ay) not in enemy_pos
    #     ]

    #     # Authentic Rule: Total collapse ONLY happens if all friendly arsenals are compromised
    #     if not emitters_queue:
    #         return set()
    #     processed_emitters = set(emitters_queue)

    #     for ax, ay in self.arsenals[opponent_side]:
    #         if (ax, ay) in friendly_pos and (ax, ay) not in processed_emitters:
    #             emitters_queue.append((ax, ay))
    #             processed_emitters.add((ax, ay))

    #     for ax, ay in emitters_queue:
    #         active_loc_cells.add((ax, ay))

    #     while emitters_queue:
    #         cx, cy = emitters_queue.pop(0)
    #         for dx, dy in self.directions:
    #             tx, ty = cx + dx, cy + dy
    #             while 0 <= tx < self.cols and 0 <= ty < self.rows:
    #                 if (tx, ty) in self.mountains: break
    #                 if (tx, ty) in enemy_positions: break

    #                 active_loc_cells.add((tx, ty))

    #                 for r_id, (rx, ry) in list(friendly_relays.items()):
    #                     if tx == rx and ty == ry and (rx, ry) not in processed_emitters:
    #                         emitters_queue.append((rx, ry))
    #                         processed_emitters.add((rx, ry))
    #                 tx += dx
    #                 ty += dy
    #     return active_loc_cells



    def compute_lines_of_communication(self, units: List[Dict], side: str) -> Set[Tuple[int, int]]:
        opponent_side = "North" if side == "South" else "South"
        
        # FIXED: Ensure all lookahead algorithms check the dynamic states passed into the method argument
        enemy_pos = {(u['x'], u['y']) for u in units if u['side'] == opponent_side}
        friendly_pos = {(u['x'], u['y']) for u in units if u['side'] == side}

        active_loc_cells = set()
        friendly_relays = {u['id']: (u['x'], u['y']) for u in units if
                           u['side'] == side and 'relay' in u['type'].lower()}

        # Queue arsenals that are NOT actively occupied or overwritten by an enemy asset
        emitters_queue = [
            (ax, ay) for ax, ay in self.arsenals[side] if (ax, ay) not in enemy_pos
        ]

        if not emitters_queue:
            return set()
        processed_emitters = set(emitters_queue)

        for ax, ay in self.arsenals[opponent_side]:
            if (ax, ay) in friendly_pos and (ax, ay) not in processed_emitters:
                emitters_queue.append((ax, ay))
                processed_emitters.add((ax, ay))

        for ax, ay in emitters_queue:
            active_loc_cells.add((ax, ay))

        while emitters_queue:
            cx, cy = emitters_queue.pop(0)
            for dx, dy in self.directions:
                tx, ty = cx + dx, cy + dy
                while 0 <= tx < self.cols and 0 <= ty < self.rows:
                    if (tx, ty) in self.mountains: 
                        break
                    
                    # FIXED: A supply line grid cell is covered up to the point of enemy presence.
                    # The cell containing the enemy is blocked, but your own adjacent units can safely 
                    # occupy the next cell to contest space without breaking macro connectivity maps.
                    if (tx, ty) in enemy_pos:
                        active_loc_cells.add((tx, ty)) # Include the impact tile itself
                        break

                    active_loc_cells.add((tx, ty))

                    for r_id, (rx, ry) in list(friendly_relays.items()):
                        if tx == rx and ty == ry and (rx, ry) not in processed_emitters:
                            emitters_queue.append((rx, ry))
                            processed_emitters.add((rx, ry))
                    tx += dx
                    ty += dy
        return active_loc_cells


    def get_connected_units(self, units: List[Dict], side: str) -> Set[str]:
        active_loc = self.compute_lines_of_communication(units, side)
        friendly_units = [u for u in units if u['side'] == side]

        connected_ids = set()
        queue = []

        for u in friendly_units:
            if (u['x'], u['y']) in active_loc:
                connected_ids.add(u['id'])
                queue.append(u)

        position_to_unit = {(u['x'], u['y']): u for u in friendly_units}
        while queue:
            current_unit = queue.pop(0)
            cx, cy = current_unit['x'], current_unit['y']
            for dx, dy in self.directions:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in position_to_unit:
                    neighbor = position_to_unit[(nx, ny)]
                    if neighbor['id'] not in connected_ids:
                        connected_ids.add(neighbor['id'])
                        queue.append(neighbor)
        return connected_ids

    def get_connected_now(self, units: List[Dict], side: str) -> Set[str]:
        return self.get_connected_units(units, side)

    def get_reachable_tiles(self, units: list, unit_id: str, mines: list = None) -> set:
        unit = next((u for u in units if u["id"] == unit_id), None)
        if not unit:
            return set()

        ux, uy = unit["x"], unit["y"]
        
        # Enforce supply line constraints: disconnected units have speed = 0
        try:
            connected_ids = self.get_connected_units(units, unit["side"])
            is_connected = unit_id in connected_ids
        except:
            is_connected = True # Default fallback to safety

        u_type = unit.get("type", "").lower()
        stats = self.get_stats(u_type)
        speed = stats.get("speed", 1) if is_connected else 0

        reachable = {(ux, uy)}
        queue = [(ux, uy, 0)]
        occupied = {(u["x"], u["y"]) for u in units if u["id"] != unit_id}
        
        # Add static mines to blocked/occupied tiles list
        if mines:
            for mine in mines:
                occupied.add((mine["x"], mine["y"]))

        while queue:
            cx, cy, dist = queue.pop(0)
            if dist >= speed:
                continue

            for dx, dy in self.directions:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.cols and 0 <= ny < self.rows:
                    if (nx, ny) in self.mountains or (nx, ny) in occupied:
                        continue
                    if (nx, ny) not in reachable:
                        reachable.add((nx, ny))
                        queue.append((nx, ny, dist + 1))

        return reachable

    def check_line_of_sight(self, from_x: int, from_y: int, to_x: int, to_y: int, max_range: int,
                            units: List[Dict]) -> bool:
        dx_diff = abs(to_x - from_x)
        dy_diff = abs(to_y - from_y)
        if dx_diff != 0 and dy_diff != 0 and dx_diff != dy_diff:
            return False

        distance = max(dx_diff, dy_diff)
        if distance > max_range or distance == 0:
            return False

        # Bresenham's Line Algorithm to find all cells between (from_x, from_y) and (to_x, to_y)
        x0, y0 = from_x, from_y
        x1, y1 = to_x, to_y

        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        cx, cy = x0, y0
        while True:
            # Do not check the start or end cell itself
            if (cx, cy) != (x0, y0) and (cx, cy) != (x1, y1):
                if (cx, cy) in self.mountains:
                    return False

            if cx == x1 and cy == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy

        return True

    def validate_move(self, units: List[Dict], unit_id: str, target_x: int, target_y: int, moved_ids: List[str],
                      current_turn_counter: int = 0) -> Tuple[bool, str]:
        moving_unit = next((u for u in units if u['id'] == unit_id), None)
        if not moving_unit: return False, "Unit missing."
        if unit_id in moved_ids: return False, "This unit has already altered its coordinates this turn."

        suppressed_until = moving_unit.get("suppressed_until_turn")
        if suppressed_until is not None and current_turn_counter < suppressed_until:
            return False, "Unit is suppressed from the last attack and cannot move."

        connected_units = self.get_connected_units(units, moving_unit['side'])
        if unit_id not in connected_units: return False, "Unit is stranded out of supply and frozen."
        if not (0 <= target_x < self.cols and 0 <= target_y < self.rows): return False, "Out of boundary limits."
        if (target_x, target_y) in self.mountains: return False, "Impassable mountain range."
        if any(u['x'] == target_x and u['y'] == target_y for u in units): return False, "Tile occupied."

        stats = self.get_stats(moving_unit['type'])

        # BFS Pathfinding: verify there is a path of length <= speed that does not traverse mountain range cells
        start_x, start_y = moving_unit['x'], moving_unit['y']
        queue = [(start_x, start_y, 0)]
        visited = {(start_x, start_y)}
        path_found = False

        other_unit_positions = {(u['x'], u['y']) for u in units if u['id'] != unit_id}

        while queue:
            cx, cy, dist = queue.pop(0)
            if cx == target_x and cy == target_y:
                if dist <= stats['speed']:
                    path_found = True
                    break

            if dist >= stats['speed']:
                continue

            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < self.cols and 0 <= ny < self.rows:
                        # Modified: Path cannot traverse mountain spaces or spaces occupied by other units
                        if (nx, ny) not in self.mountains and (nx, ny) not in other_unit_positions and (nx,
                                                                                                        ny) not in visited:
                            visited.add((nx, ny))
                            queue.append((nx, ny, dist + 1))

        # if not path_found:
        #     return False, "Movement path is blocked by impassable mountains."

        if not path_found:
            if (target_x, target_y) in self.mountains:
                return False, "Impassable mountain range."
            return False, "Movement path is blocked by other units or out of reach."

        return True, "Move approved."






    def calculate_combat(self, units: List[Dict], attacker_side: str, target_x: int, target_y: int, verbose: bool = True) -> Dict:
        target_unit = next((u for u in units if u['x'] == target_x and u['y'] == target_y), None)
        if not target_unit or target_unit['side'] == attacker_side:
            return {"valid": False, "reason": "No valid enemy target located on those coordinates."}

        if target_unit.get("symbol") == "S":
            return {"valid": False, "reason": "Target unit is shielded and immune to attacks."}

        connected_attackers = self.get_connected_units(units, attacker_side)
        connected_defenders = self.get_connected_units(units, target_unit['side'])

        # Strict Combat Whitelist
        COMBAT_OFFENSE_TYPES = ["artillery", "cavalry", "infantry"]

        # ── SYSTEM 1: EVALUATE INDEPENDENT AXES (LOOK UPSTREAM FOR ATTACKERS) ──
        best_axis_offense = 0
        best_axis_direction = None

        for dx, dy in self.directions:
            # We treat (dx, dy) as the impact direction vector (e.g., 0, 1 means force moving South)
            # Therefore, the attacker must be located UPSTREAM (-dx, -dy)
            cx, cy = target_x - dx, target_y - dy
            head_unit = None
            blocked_by_terrain = False

            # Phase 1: Locate the leading attacking unit upstream along this specific ray
            while 0 <= cx < self.cols and 0 <= cy < self.rows:
                if (cx, cy) in self.mountains:
                    blocked_by_terrain = True
                    break
                u = next((unit for unit in units if unit['x'] == cx and unit['y'] == cy), None)
                if u:
                    if u['side'] == attacker_side:
                        head_unit = u
                    break
                cx -= dx
                cy -= dy

            if blocked_by_terrain or not head_unit:
                continue
            if head_unit['id'] not in connected_attackers:
                continue

            head_stats = self.get_stats(head_unit['type'])
            head_dist = max(abs(head_unit['x'] - target_x), abs(head_unit['y'] - target_y))

            # Phase 2: Trace straight backwards behind the head (further upstream: -dx, -dy)
            friendly_line = [head_unit]
            nx, ny = head_unit['x'] - dx, head_unit['y'] - dy
            while 0 <= nx < self.cols and 0 <= ny < self.rows:
                if (nx, ny) in self.mountains:
                    break
                u = next((unit for unit in units if unit['x'] == nx and unit['y'] == ny), None)
                if u and u['side'] == attacker_side:
                    friendly_line.append(u)
                    nx -= dx
                    ny -= dy
                else:
                    break

            is_adjacent = head_dist == 1
            is_fortified = (target_x, target_y) in self.fortresses or (target_x, target_y) in self.passes
            axis_offense = 0

            if head_dist <= head_stats['range']:
                if "cavalry" in head_unit['type'].lower() and is_adjacent and not is_fortified:
                    axis_offense += head_stats['charge']
                else:
                    if head_unit['type'].lower() in COMBAT_OFFENSE_TYPES:
                        axis_offense += head_stats['offense']

                for back_unit in friendly_line[1:]:
                    if back_unit['id'] in connected_attackers:
                        if back_unit['type'].lower() in COMBAT_OFFENSE_TYPES:
                            axis_offense += self.get_stats(back_unit['type'])['offense']
            else:
                for idx, u_node in enumerate(friendly_line):
                    if u_node['id'] in connected_attackers and "artillery" in u_node['type'].lower():
                        art_dist = max(abs(u_node['x'] - target_x), abs(u_node['y'] - target_y))
                        if art_dist <= 3:
                            axis_offense += self.get_stats("artillery")["offense"]
                            for back_unit in friendly_line[idx + 1:]:
                                if back_unit['id'] in connected_attackers:
                                    if back_unit['type'].lower() in COMBAT_OFFENSE_TYPES:
                                        axis_offense += self.get_stats(back_unit['type'])['offense']
                            break

            if axis_offense > best_axis_offense:
                best_axis_offense = axis_offense
                best_axis_direction = (dx, dy)

        if best_axis_offense == 0:
            return {"valid": False, "reason": "No valid connected unit configuration can project force."}

        total_offense = best_axis_offense

        # ── SYSTEM 2: DEFENSIVE STACK VERIFICATION (LOOK DOWNSTREAM FOR DEFENDERS) ──
        target_connected = target_unit['id'] in connected_defenders
        total_defense = 0

        if target_connected:
            base_def = self.get_stats(target_unit['type'])['defense']
            is_fortress = (target_x, target_y) in self.fortresses
            is_pass = (target_x, target_y) in self.passes

            if is_fortress:
                total_defense = (base_def + 4) * 2
            elif is_pass:
                total_defense = (base_def + 2) * 2
            else:
                total_defense = base_def

            dx, dy = best_axis_direction
            
            # Step downstream (+ direction of attack vector) to find the tile directly behind the target
            cx, cy = target_x + dx, target_y + dy
            
            # Strict Adjacency Check
            if 0 <= cx < self.cols and 0 <= cy < self.rows and (cx, cy) not in self.mountains:
                first_backup = next((unit for unit in units if unit['x'] == cx and unit['y'] == cy), None)
                
                if first_backup and first_backup['side'] == target_unit['side'] and first_backup['id'] in connected_defenders:
                    defender_line = []
                    # Whitelist check for the first backing unit before building the chain
                    if first_backup['type'].lower() in COMBAT_OFFENSE_TYPES:
                        defender_line.append(first_backup)
                    
                    nx, ny = cx + dx, cy + dy
                    
                    # Trace the unbroken chain further downstream
                    while 0 <= nx < self.cols and 0 <= ny < self.rows:
                        if (nx, ny) in self.mountains:
                            break
                        u = next((unit for unit in units if unit['x'] == nx and unit['y'] == ny), None)
                        if u and u['side'] == target_unit['side'] and u['id'] in connected_defenders:
                            if u['type'].lower() in COMBAT_OFFENSE_TYPES:
                                defender_line.append(u)
                            nx += dx
                            ny += dy
                        else:
                            break
                    
                    # Accumulate scores for verified whitelisted units in the strict unbroken chain
                    for defender_piece in defender_line:
                        total_defense += self.get_stats(defender_piece['type'])['defense']

        # ── SYSTEM 3: RESOLUTION CALCULATOR ──
        net_force = total_offense - total_defense
        if net_force >= 2:
            result = "DESTROY"
        elif net_force == 1:
            result = "RETREAT"
        else:
            result = "FAIL"

        if verbose:
            print(f"\n⚡ [ENGINE RESOLUTION MATRIX]")
            print(f"   ├─ Action Trigger: Side '{attacker_side}' attacking target at ({target_x}, {target_y})")
            print(f"   ├─ Vector Axis: Direction Vector dx={best_axis_direction[0]}, dy={best_axis_direction[1]}")
            print(f"   ├─ Final Offense Calculation: {total_offense}")
            print(f"   ├─ Final Defense Calculation: {total_defense}")
            print(f"   └─ Output Force Evaluation: Net={net_force} Result={result}\n")


        return {
            "valid": True, "result": result, "net_force": net_force,
            "offense": total_offense, "defense": total_defense
        }