
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
            (5, 9)   # South Arsenal / Fort
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
            "relay": {"speed": 1, "range": 0, "offense": 0, "defense": 1},
            "mine": {"speed": 1, "range": 0, "offense": 0, "defense": 5},  # Defense increased 1 -> 5
            "shield": {"speed": 1, "range": 0, "offense": 0, "defense": 26}  # Defense increased 8 -> 26
        }

    def get_stats(self, unit_type: str) -> dict:
        u_type = unit_type.lower()
        if "infantry" in u_type: return self.unit_stats["infantry"]
        if "cavalry" in u_type: return self.unit_stats["cavalry"]
        if "artillery" in u_type: return self.unit_stats["artillery"]
        if "mine" in u_type: return self.unit_stats["mine"]
        if "shield" in u_type: return self.unit_stats["shield"]
        return self.unit_stats["relay"]

    def compute_lines_of_communication(self, units: List[Dict], side: str) -> Set[Tuple[int, int]]:
        opponent_side = "North" if side == "South" else "South"
        enemy_pos = {(u['x'], u['y']) for u in units if u['side'] == opponent_side}
        friendly_pos = {(u['x'], u['y']) for u in units if u['side'] == side}


        active_loc_cells = set()
        enemy_positions = {(u['x'], u['y']) for u in units if u['side'] != side}
        friendly_relays = {u['id']: (u['x'], u['y']) for u in units if
                           u['side'] == side and 'relay' in u['type'].lower()}

        # MODIFIED: Only queue arsenals that are NOT occupied by the enemy
        emitters_queue = [
            (ax, ay) for ax, ay in self.arsenals[side] if (ax, ay) not in enemy_pos
        ]

        # Authentic Rule: Total collapse ONLY happens if all friendly arsenals are compromised
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
                    if (tx, ty) in self.mountains: break
                    if (tx, ty) in enemy_positions: break

                    active_loc_cells.add((tx, ty))

                    for r_id, (rx, ry) in list(friendly_relays.items()):
                        if tx == rx and ty == ry and (rx, ry) not in processed_emitters:
                            emitters_queue.append((rx, ry))
                            processed_emitters.add((rx, ry))
                    tx += dx
                    ty += dy
        return active_loc_cells

    # def get_connected_units(self, units: List[Dict], side: str) -> Set[str]:
    #     active_loc = self.compute_lines_of_communication(units, side)
    #     friendly_units = [u for u in units if u['side'] == side]

    #     connected_ids = set()
    #     queue = []

    #     for u in friendly_units:
    #         if (u['x'], u['y']) in active_loc:
    #             connected_ids.add(u['id'])
    #             queue.append(u)

    #     position_to_unit = {(u['x'], u['y']): u for u in friendly_units}
    #     while queue:
    #         current_unit = queue.pop(0)
    #         cx, cy = current_unit['x'], current_unit['y']
    #         for dx, dy in self.directions:
    #             nx, ny = cx + dx, cy + dy
    #             if (nx, ny) in position_to_unit:
    #                 neighbor = position_to_unit[(nx, ny)]
    #                 if neighbor['id'] not in connected_ids:
    #                     connected_ids.add(neighbor['id'])
    #                     queue.append(neighbor)
    #     return connected_ids



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




    def get_reachable_tiles(self, units: list, unit_id: str) -> set:
        unit = next((u for u in units if u["id"] == unit_id), None)
        if not unit:
            return set()

        ux, uy = unit["x"], unit["y"]
        u_type = unit.get("type", "").lower()
        stats = self.get_stats(u_type)
        speed = stats.get("speed", 1)

        reachable = {(ux, uy)}
        queue = [(ux, uy, 0)]
        occupied = {(u["x"], u["y"]) for u in units if u["id"] != unit_id}

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

    def validate_move(self, units: List[Dict], unit_id: str, target_x: int, target_y: int, moved_ids: List[str]) -> \
            Tuple[bool, str]:
        moving_unit = next((u for u in units if u['id'] == unit_id), None)
        if not moving_unit: return False, "Unit missing."
        if unit_id in moved_ids: return False, "This unit has already altered its coordinates this turn."

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
                            
        if not path_found:
            return False, "Movement path is blocked by impassable mountains."

        return True, "Move approved."

    

    def calculate_combat(self, units: List[Dict], attacker_side: str, target_x: int, target_y: int) -> Dict:
        target_unit = next((u for u in units if u['x'] == target_x and u['y'] == target_y), None)
        if not target_unit or target_unit['side'] == attacker_side:
            return {"valid": False, "reason": "No valid enemy target located on those coordinates."}

        # Shield units are immune to all attacks
        if target_unit.get("symbol") == "S":
            return {"valid": False, "reason": "Target unit is shielded and immune to attacks."}

        total_offense = 0
        contributing_attackers = set()
        active_attack_directions = set()  # Tracks vectors execution paths: (dx, dy)

        # ── 1. DIRECTIONAL OFFENSE AXIS SCANNING ──
        # Scan 8 directions from target to find aligned unit stacks or valid single attackers
        for dx, dy in self.directions:
            cx, cy = target_x + dx, target_y + dy
            distance = 0
            blocked = False

            while 0 <= cx < self.cols and 0 <= cy < self.rows:
                if (cx, cy) in self.mountains:
                    blocked = True
                    break

                u = next((unit for unit in units if unit['x'] == cx and unit['y'] == cy), None)
                if u:
                    if u['side'] == attacker_side:
                        distance = max(abs(cx - target_x), abs(cy - target_y))
                        stats = self.get_stats(u['type'])

                        # Validate if the unit has the range to hit across this vector line
                        if distance <= stats['range']:
                            contributing_attackers.add(u['id'])
                            active_attack_directions.add((dx, dy))

                            # Synergy Stacking Check: Collect contiguous friendly units directly behind the head along the exact vector axis
                            nx, ny = cx + dx, cy + dy
                            while 0 <= nx < self.cols and 0 <= ny < self.rows:
                                u_behind = next((unit for unit in units if unit['x'] == nx and unit['y'] == ny), None)
                                if u_behind and u_behind['side'] == attacker_side:
                                    contributing_attackers.add(u_behind['id'])
                                    nx += dx
                                    ny += dy
                                else:
                                    break
                    else:
                        blocked = True
                    break
                cx += dx
                cy += dy

        connected_attackers = self.get_connected_units(units, attacker_side)
        connected_defenders = self.get_connected_units(units, target_unit['side'])

        # Sum total offense of valid connected contributing units
        has_connected_attacker = False
        for u_id in contributing_attackers:
            u = next((unit for unit in units if unit['id'] == u_id), None)
            if not u or u.get('symbol') == "S" or u['id'] not in connected_attackers:
                continue

            has_connected_attacker = True
            stats = self.get_stats(u['type'])
            is_adjacent = max(abs(u['x'] - target_x), abs(u['y'] - target_y)) == 1
            is_fortified = (target_x, target_y) in self.fortresses or (target_x, target_y) in self.passes

            if "cavalry" in u['type'].lower() and is_adjacent and not is_fortified:
                total_offense += stats['charge']
            else:
                total_offense += stats['offense']

        if not has_connected_attacker:
            return {"valid": False, "reason": "No connected friendly unit in range to attack this target."}

        # ── 2. DIRECTIONAL DEFENSE MATRIX SCANNING ──
        target_connected = target_unit['id'] in connected_defenders

        if not target_connected:
            total_defense = 0
        else:
            total_defense = self.get_stats(target_unit['type'])['defense']
            if (target_x, target_y) in self.fortresses:
                total_defense += 4
            elif (target_x, target_y) in self.passes:
                total_defense += 2

        contributing_defenders = set()

        # FIXED: Scan directly behind the defender strictly along the directional lines of active incoming attacks
        for dx, dy in active_attack_directions:
            # The support line must extend directly backward away from the origin threat vector
            cx, cy = target_x - dx, target_y - dy

            while 0 <= cx < self.cols and 0 <= cy < self.rows:
                if (cx, cy) in self.mountains:
                    break
                u = next((unit for unit in units if unit['x'] == cx and unit['y'] == cy), None)

                # Only apply support points if the piece matches the defender's side and line configuration
                if u and u['side'] == target_unit['side']:
                    contributing_defenders.add(u['id'])
                else:
                    # Broken line of defense alignment breaks the modifier chain
                    break
                cx -= dx
                cy -= dy

        # Sum directional defense support weights
        for d_id in contributing_defenders:
            u = next((unit for unit in units if unit['id'] == d_id), None)
            if not u or u['id'] not in connected_defenders:
                continue
            stats = self.get_stats(u['type'])
            total_defense += stats['defense']

        # Double entire defense if in a fortress or mountain pass grid cell
        if target_connected and ((target_x, target_y) in self.fortresses or (target_x, target_y) in self.passes):
            total_defense *= 2

        net_force = total_offense - total_defense

        if net_force >= 2:
            result = "DESTROY"
        elif net_force == 1:
            result = "RETREAT"
        else:
            result = "FAIL"

        return {
            "valid": True, "result": result, "net_force": net_force,
            "offense": total_offense, "defense": total_defense
        }
