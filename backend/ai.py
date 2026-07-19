# ai.py
import copy
import sys


class WarGameAI:
    def __init__(self, engine, side: str = "South", position_history: dict = None, turn_counter: int = 0):
        self.engine = engine
        self.side = side
        self.enemy_side = "North" if side == "South" else "South"

        self.defensive_weight = 0.5
        self._enemy_evaluator = None  # Lazy-init — avoids infinite recursion

        self.unit_values = {
            "artillery": 40,
            "cavalry": 55,
            "relay": 15,   # Relays are fragile logistics, not combat prizes
            "infantry": 20,
            "arsenal": 1000,
            "mine": 25,
            "shield": 35
        }
        self.position_history = position_history if position_history is not None else {}

        # ── INITIALIZE SMT TACTICAL ORACLE CONNECTION ──
        from smt_oracle import SmtTacticalOracle
        self.smt_oracle = SmtTacticalOracle(cols=engine.cols, rows=engine.rows)
        self.turn_counter = turn_counter
        self._distance_cache = {}  # {target_coords: {(x, y): distance}}
        self.cluster_turn_cursor = 0

        self._safety_cache = {}  # persists across calls within a turn
        self._safety_cache_turn = None  # tracks which turn the cache belongs to
        self._z3_safe_zones_cache = None
        self._z3_safe_zones_turn = None

    def _build_distance_map(self, target_y):
        from collections import deque
        dist = {}
        queue = deque()
        for x in range(self.engine.cols):
            if (x, target_y) not in self.engine.mountains:
                dist[(x, target_y)] = 0
                queue.append((x, target_y))
        while queue:
            cx, cy = queue.popleft()
            d = dist[(cx, cy)]
            for dx, dy in self.engine.directions:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.engine.cols and 0 <= ny < self.engine.rows:
                    if (nx, ny) not in self.engine.mountains and (nx, ny) not in dist:
                        dist[(nx, ny)] = d + 1
                        queue.append((nx, ny))
        return dist

    def get_path_distance_to_goal(self, x, y, target_y):
        if target_y not in self._distance_cache:
            self._distance_cache[target_y] = self._build_distance_map(target_y)
        return self._distance_cache[target_y].get((x, y), 30)

    def _build_point_distance_map(self, target_coords):
        from collections import deque
        dist = {}
        queue = deque()
        if isinstance(target_coords, tuple) and len(target_coords) == 2 and isinstance(target_coords[0], int):
            targets = [target_coords]
        else:
            targets = list(target_coords)
        for tx, ty in targets:
            if (tx, ty) not in self.engine.mountains:
                dist[(tx, ty)] = 0
                queue.append((tx, ty))
        while queue:
            cx, cy = queue.popleft()
            d = dist[(cx, cy)]
            for dx, dy in self.engine.directions:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.engine.cols and 0 <= ny < self.engine.rows:
                    if (nx, ny) not in self.engine.mountains and (nx, ny) not in dist:
                        dist[(nx, ny)] = d + 1
                        queue.append((nx, ny))
        return dist

    def get_path_distance(self, x, y, target_coords):
        key = tuple(target_coords) if isinstance(target_coords, list) else target_coords
        if key not in self._distance_cache:
            self._distance_cache[key] = self._build_point_distance_map(target_coords)
        return self._distance_cache[key].get((x, y), 99)

    @property
    def enemy_evaluator(self):
        if self._enemy_evaluator is None:
            self._enemy_evaluator = WarGameAI(self.engine, side=self.enemy_side, turn_counter=self.turn_counter)
            self._enemy_evaluator.defensive_weight = 0.0
        return self._enemy_evaluator

    def _assess_local_threats(self, units, ai_connected):
        threats = {}
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]
        ai_units = [u for u in units if u.get("side") == self.side]

        for unit in ai_units:
            u_id = unit["id"]
            ux, uy = unit["x"], unit["y"]
            u_stats = self.engine.get_stats(unit.get("type", ""))
            defense = u_stats["defense"]

            if (ux, uy) in self.engine.fortresses:
                defense += 4
            elif (ux, uy) in self.engine.passes:
                defense += 2

            contributing_defenders = set()
            for dx, dy in self.engine.directions:
                line_friendlies = []
                cx, cy = ux + dx, uy + dy
                while 0 <= cx < self.engine.cols and 0 <= cy < self.engine.rows:
                    if (cx, cy) in self.engine.mountains:
                        break
                    u = next((a for a in ai_units if a['x'] == cx and a['y'] == cy), None)
                    if u:
                        if u['id'] != u_id:
                            line_friendlies.append(u)
                        else:
                            break
                    else:
                        if line_friendlies:
                            if len(line_friendlies) >= 2:
                                for lf in line_friendlies:
                                    contributing_defenders.add(lf['id'])
                            line_friendlies = []
                    cx += dx
                    cy += dy
                if len(line_friendlies) >= 2:
                    for lf in line_friendlies:
                        contributing_defenders.add(lf['id'])

            for a in ai_units:
                if a["id"] == u_id:
                    continue
                a_stats = self.engine.get_stats(a.get("type", ""))
                if self.engine.check_line_of_sight(a["x"], a["y"], ux, uy, a_stats["range"], units):
                    contributing_defenders.add(a["id"])

            for a_id in contributing_defenders:
                a = next(x for x in ai_units if x["id"] == a_id)
                a_stats = self.engine.get_stats(a.get("type", ""))
                defense += a_stats["defense"]

            if (ux, uy) in self.engine.fortresses or (ux, uy) in self.engine.passes:
                defense *= 2

            if u_id not in ai_connected:
                defense = max(1, defense // 2)

            potential_offense = 0.0
            for enemy in enemy_units:
                e_stats = self.engine.get_stats(enemy.get("type", ""))
                reach = e_stats["speed"] + e_stats["range"]
                dist = max(abs(enemy["x"] - ux), abs(enemy["y"] - uy))
                if dist <= reach:
                    is_charge_range = dist <= e_stats["speed"] + 1
                    potential_offense += e_stats.get("charge", e_stats["offense"]) if is_charge_range else e_stats[
                        "offense"]

            threats[u_id] = potential_offense - defense

        return threats

    def _decide_local_goals(self, units: list, ai_connected: set) -> dict:
        """
        INDIVIDUAL MOTIVATION ENGINE (Stripped of Macro Directives)
        Units establish autonomous intentions entirely through local radar arrays.
        """
        goals = {}
        ai_units = [u for u in units if u.get("side") == self.side]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]
        local_threats = self._assess_local_threats(units, ai_connected)

        for unit in ai_units:
            uid = unit["id"]
            u_type = unit.get("type", "").lower()
            ux, uy = unit["x"], unit["y"]
            threat = local_threats.get(uid, 0.0)

            if u_type == "relay":
                goals[uid] = "ESCAPE" if threat > 0.0 else "SUPPORT_NET"
                continue

            # 1. Critical Preservation Check
            if threat > 6.0:
                goals[uid] = "RETREAT"
                continue

            # 2. Combat Opening Check (Solo Killshot OR Cooperative Stack opportunity)
            stats = self.engine.get_stats(unit["type"])
            has_combat_opening = False
            for target in enemy_units:
                if self.engine.check_line_of_sight(ux, uy, target["x"], target["y"], stats["range"], units):
                    combat = self.engine.calculate_combat(units, self.side, target["x"], target["y"], verbose=False)
                    if combat.get("valid"):
                        if combat["result"] in ["DESTROY", "RETREAT"]:
                            has_combat_opening = True
                            break
                        # Check if another ally is also aligned to stack force on this target
                        dx = target["x"] - ux
                        dy = target["y"] - uy
                        step_x = 1 if dx > 0 else (-1 if dx < 0 else 0)
                        step_y = 1 if dy > 0 else (-1 if dy < 0 else 0)
                        
                        other_allies_aligned = False
                        for ally in ai_units:
                            if ally["id"] == uid:
                                continue
                            ax_diff = target["x"] - ally["x"]
                            ay_diff = target["y"] - ally["y"]
                            a_step_x = 1 if ax_diff > 0 else (-1 if ax_diff < 0 else 0)
                            a_step_y = 1 if ay_diff > 0 else (-1 if ay_diff < 0 else 0)
                            # If they share the same alignment vector towards the target
                            if (a_step_x, a_step_y) == (step_x, step_y) or (a_step_x, a_step_y) == (-step_x, -step_y):
                                other_allies_aligned = True
                                break
                        
                        if other_allies_aligned:
                            has_combat_opening = True
                            break

            if has_combat_opening:
                goals[uid] = "ATTACK"
                continue

            # 3. Dynamic Positional Mapping (Determines optimal role purely based on distance)
            if enemy_units:
                closest_enemy = min(enemy_units, key=lambda e: max(abs(ux - e["x"]), abs(uy - e["y"])))
                dist_to_battle = max(abs(ux - closest_enemy["x"]), abs(uy - closest_enemy["y"]))

                if dist_to_battle <= stats["range"] + 2:
                    goals[uid] = "ATTACK_RUN"
                elif dist_to_battle > 6:
                    goals[uid] = "BLITZ_CHARGE"  # Seeking a Cavalry face roll for movement optimization
                else:
                    goals[uid] = "HOLD_FORMATION"
            else:
                goals[uid] = "TRAVEL"

        return goals

    def detect_threats(self, units: list) -> float:
        threat_score = 0.0
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]
        friendly_relays = [u for u in units if u.get("side") == self.side and "relay" in u.get("type", "").lower()]

        for relay in friendly_relays:
            for enemy in enemy_units:
                dist = max(abs(relay["x"] - enemy["x"]), abs(relay["y"] - enemy["y"]))
                if dist <= 4:
                    threat_score -= (5 - dist) * 180.0

        for ax, ay in self.engine.arsenals[self.side]:
            for enemy in enemy_units:
                dist = max(abs(enemy["x"] - ax), abs(enemy["y"] - ay))
                if dist <= 9:
                    threat_score -= (10 - dist) * 130.0

        if friendly_relays:
            connected_now = self.engine.get_connected_now(units, self.side) if hasattr(self.engine,
                                                                                       'get_connected_now') else self.engine.get_connected_units(
                units, self.side)
            for relay in friendly_relays:
                if relay["id"] not in connected_now:
                    threat_score -= 900.0

        friendly_combat = [u for u in units if u.get("side") == self.side and "relay" not in u.get("type", "").lower()]
        try:
            enemy_connected = set(self.engine.get_connected_units(units, self.enemy_side))
        except Exception:
            enemy_connected = set()

        for ally in friendly_combat:
            ally_in_danger = False
            for enemy in enemy_units:
                if enemy["id"] not in enemy_connected:
                    continue
                enemy_stats = self.engine.get_stats(enemy["type"])
                if self.engine.check_line_of_sight(enemy["x"], enemy["y"], ally["x"], ally["y"], enemy_stats["range"],
                                                   units):
                    ally_in_danger = True
                    break
            if ally_in_danger:
                ally_type = ally.get("type", "").lower()
                val = self.unit_values.get(ally_type, 20)
                threat_score -= val * 8.0

        return threat_score

    def evaluate_board(self, units: list, return_breakdown: bool = False,
                       base_enemy_connected: set = None, is_end_turn: bool = True,
                       original_units: list = None) -> dict or float:
        base_material = 0.0
        territory_score = 0.0
        role_score = 0.0
        cohesion_score = 0.0
        stacked_attack_pressure = 0.0

        ref_units = original_units if original_units is not None else units
        initial_enemy_count = sum(1 for u in ref_units if u.get("side") == self.enemy_side)
        current_enemy_count = sum(1 for u in units if u.get("side") == self.enemy_side)
        enemies_destroyed = initial_enemy_count - current_enemy_count

        # 1. Kill validation bounty remains significant but tightly bounded
        role_score += enemies_destroyed * 10000.0

        try:
            connected_north = set(self.engine.get_connected_units(units, "North"))
            connected_south = set(self.engine.get_connected_units(units, "South"))
        except Exception:
            connected_north = set()
            connected_south = set()

        ai_connected = connected_south if self.side == "South" else connected_north
        enemy_connected = connected_north if self.side == "South" else connected_south

        target_y = 0 if self.side == "South" else 19
        home_y = 19 if self.side == "South" else 0

        ai_units = [u for u in units if u.get("side") == self.side]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]

        connected_y_positions = []
        connected_count = 0

        for unit in units:
            u_side = unit.get("side")
            u_type = unit.get("type", "").lower()
            u_id = unit.get("id")
            ux, uy = unit.get("x", 0), unit.get("y", 0)
            is_connected = u_id in (ai_connected if u_side == self.side else enemy_connected)
            base_val = self.unit_values.get(u_type, 20)

            if u_side == self.side:
                # Scale material up so pieces care deeply about their own lives
                base_material += base_val * 10.0
                if is_connected:
                    connected_count += 1
                    connected_y_positions.append(uy)
                else:
                    cohesion_score -= 500.0  # Firm local penalty for being disconnected
            else:
                base_material -= base_val * 10.0
                if base_enemy_connected is not None:
                    if (u_id in base_enemy_connected) and not is_connected:
                        territory_score += 500.0
                elif not is_connected:
                    territory_score += 150.0

        territory_score += connected_count * 50.0

        # ── ARSENAL DEFENSE THREAT EVALUATOR ──
        my_arsenals = list(self.engine.arsenals[self.side])
        if my_arsenals:
            ax, ay = my_arsenals[0]
            for enemy in enemy_units:
                e_id = enemy.get("id")
                # Only care about connected enemies who are capable of moving/acting
                if enemy_connected and e_id in enemy_connected:
                    dist_to_my_base = max(abs(enemy["x"] - ax), abs(enemy["y"] - ay))
                    if dist_to_my_base <= 4:
                        # Scale the threat penalty exponentially as they get closer
                        territory_score -= (5 - dist_to_my_base) * 15000.0
                        if dist_to_my_base == 0:
                            territory_score -= 100000.0  # Core compromised penalty

        min_global_distance = 99
        for enemy in enemy_units:
            ex, ey = enemy.get("x", 0), enemy.get("y", 0)
            for ally in ai_units:
                ax, ay = ally.get("x", 0), ally.get("y", 0)
                dist = max(abs(ex - ax), abs(ey - ay))
                if dist < min_global_distance:
                    min_global_distance = dist

        # 2. Rebalanced Engagement Parameters to force stacking
        is_engagement_phase = min_global_distance <= 6
        if is_engagement_phase:
            for enemy in enemy_units:
                ex, ey = enemy.get("x", 0), enemy.get("y", 0)
                converging_friendly_count = 0
                for ally in ai_units:
                    ax, ay = ally.get("x", 0), ally.get("y", 0)
                    reach = 4 if ally.get("type", "").lower() in ["cavalry", "artillery"] else 3
                    dist_to_target = max(abs(ex - ax), abs(ey - ay))
                    if dist_to_target <= reach:
                        converging_friendly_count += 1
                    if dist_to_target == 1:
                        role_score += 800.0  # Moderate pinning bonus

                if converging_friendly_count == 2:
                    stacked_attack_pressure += 5000.0
                elif converging_friendly_count >= 3:
                    stacked_attack_pressure += 15000.0

        all_enemy_positions = [(e.get("x", 0), e.get("y", 0)) for e in enemy_units]
        local_threats = self._assess_local_threats(units, ai_connected)
        threatened_units = {uid: val for uid, val in local_threats.items() if val > 0}

        captured_enemy_arsenals = []
        for ax, ay in self.engine.arsenals[self.enemy_side]:
            if any(u["x"] == ax and u["y"] == ay and u["side"] == self.side for u in units):
                captured_enemy_arsenals.append((ax, ay))

        for unit in ai_units:
            u_id = unit.get("id")
            u_type = unit.get("type", "").lower()
            ux, uy = unit.get("x", 0), unit.get("y", 0)
            is_connected = u_id in ai_connected

            # 3. Normalized face rewards so they don't break the global scale
            if u_side == self.side:
                # Query the engine for the active stats of the current configuration
                current_stats = self.engine.get_stats(u_type)

                # If this unit is currently in an enemy's firing line or charge envelope
                if u_id in threatened_units:
                    net_danger = threatened_units[u_id]
                    if net_danger > 0:
                        # Heavy penalty if the unit is in a fragile state (like Cavalry with 2 Defense)
                        # This naturally forces the AI to prefer transforming into a Shield (26 Defense)
                        # or Infantry (6 Defense) when caught in an enemy threat zone.
                        role_score -= net_danger * 50.0
                    else:
                        # Reward the unit for successfully neutralizing the threat via high defense
                        # (e.g., a Shield or fortified position reducing net_danger to <= 0)
                        role_score += abs(net_danger) * 10.0

            if threatened_units:
                for t_id, severity in threatened_units.items():
                    if t_id == u_id:
                        continue
                    ally = next((a for a in ai_units if a["id"] == t_id), None)
                    if ally and max(abs(ux - ally["x"]), abs(uy - ally["y"])) == 1:
                        role_score += min(severity, 15) * 5.0

            if u_id in threatened_units:
                nearby_allies = sum(
                    1 for a in ai_units if a["id"] != u_id and max(abs(ux - a["x"]), abs(uy - a["y"])) <= 1)
                role_score += nearby_allies * 20.0
                role_score -= min(threatened_units[u_id], 20) * 30.0

            if u_type == "relay":
                # Relays score only for staying close to combat allies — logistics role, not advancement
                combat_allies = [a for a in ai_units if "relay" not in a.get("type", "").lower()]
                if combat_allies:
                    avg_ax = sum(a["x"] for a in combat_allies) / len(combat_allies)
                    avg_ay = sum(a["y"] for a in combat_allies) / len(combat_allies)
                    role_score += (45 - max(abs(ux - avg_ax), abs(uy - avg_ay))) * 3.0  # was 10.0

                # Relays do NOT score for proximity to enemy arsenal — that's a combat piece job
                continue

            all_enemy_arsenals = self.engine.arsenals[self.enemy_side]
            if all_enemy_arsenals:
                min_dist_to_arsenal = min(max(abs(ux - ax), abs(uy - ay)) for ax, ay in all_enemy_arsenals)
                role_score += (45 - min_dist_to_arsenal) * 15.0

            for ax, ay in captured_enemy_arsenals:
                if ux == ax and uy == ay:
                    role_score += 1000.0

            dist_to_goal = self.get_path_distance_to_goal(ux, uy, target_y)
            role_score += (20 - dist_to_goal) * 4.0

            if not is_connected:
                role_score -= 1000.0

        if connected_y_positions:
            avg_y = sum(connected_y_positions) / len(connected_y_positions)
            cohesion_score += abs(home_y - avg_y) * 5.0

        threat_score = self.detect_threats(
            units) if self._enemy_evaluator is not None or self.defensive_weight > 0 else 0.0

        # Enforce strict safety boundary caps to prevent overflow imbalances
        total_score = base_material + territory_score + role_score + cohesion_score + stacked_attack_pressure + threat_score

        if return_breakdown:
            return {
                "TOTAL": total_score,
                "Material": base_material,
                "Territory": territory_score,
                "Role_Exec": role_score,
                "Cohesion": cohesion_score,
                "Attack_Press": stacked_attack_pressure,
                "Threat_Def": threat_score
            }
        return total_score

    def _detect_behavioral_anomaly(self, uid: int) -> str or None:
        history = self.position_history.get(uid, [])
        if len(history) < 4:
            return None
        if len(set(history[-3:])) == 1:
            return "STASIS_FREEZE"
        if history[-4] == history[-2] and history[-3] == history[-1] and history[-4] != history[-3]:
            return "2_STEP_OSCILLATION"
        if len(history) >= 6:
            if history[-6] == history[-3] and history[-5] == history[-2] and history[-4] == history[-1]:
                return "3_STEP_OSCILLATION"
        return None

    def _get_loc_cells(self, units: list) -> set:
        raw = self.engine.compute_lines_of_communication(units, self.side)
        return {(c[0], c[1]) for c in raw}

    def _get_lane_target(self, unit: dict, units: list) -> tuple:
        ux = unit["x"]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]

        if ux <= 8:
            lane_enemies = [e for e in enemy_units if e["x"] <= 10]
        elif ux >= 16:
            lane_enemies = [e for e in enemy_units if e["x"] >= 14]
        else:
            lane_enemies = enemy_units

        if not lane_enemies:
            lane_enemies = enemy_units
        if not lane_enemies:
            return min(self.engine.arsenals[self.enemy_side], key=lambda a: abs(a[0] - ux) + abs(a[1] - unit["y"]))

        return min([(e["x"], e["y"]) for e in lane_enemies], key=lambda p: abs(p[0] - ux) + abs(p[1] - unit["y"]))



    def get_all_legal_moves(self, units: list, moved_this_turn: list) -> list:
        legal_actions = []
        ai_units = [u for u in units if u.get("side") == self.side]
        connected_unit_ids = self.engine.get_connected_units(units, self.side)

        for unit in ai_units:
            already_moved = unit["id"] in moved_this_turn
            if unit["id"] not in connected_unit_ids:
                continue

            unit_stats = self.engine.get_stats(unit["type"])

            # ── 1. GENERATE VALID COMBAT ACTIONS ──
            # The attack budget is GLOBAL (one attack per side per turn), not per-unit.
            # Any connected unit — even one that already moved — can use the attack if it hasn't been spent.
            for target in units:
                if target.get("side") == self.enemy_side:
                    if self.engine.check_line_of_sight(unit["x"], unit["y"], target["x"], target["y"],
                                                       unit_stats["range"], units):
                        combat = self.engine.calculate_combat(units, self.side, target["x"], target["y"], verbose=False)
                        if combat.get("valid"):
                            legal_actions.append(
                                {"action_type": "attack", "unitId": unit["id"], "x": target["x"], "y": target["y"]})

            # Units that already moved this turn cannot move again
            if already_moved:
                continue

            # ── 2. GENERATE FLAT MOVEMENTS + TRANSFORMATIONS ──
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    tx, ty = unit["x"] + dx, unit["y"] + dy
                    if 0 <= tx < self.engine.cols and 0 <= ty < self.engine.rows:
                        # is_valid, _ = self.engine.validate_move(units, unit["id"], tx, ty, moved_this_turn)

                        is_valid, _ = self.engine.validate_move(units, unit["id"], tx, ty, moved_this_turn,
                                                                self.turn_counter)
                        if is_valid:
                            # Option 1: Flat Slide (move while keeping current face/type)
                            legal_actions.append({
                                "action_type": "move",
                                "unitId": unit["id"],
                                "x": tx,
                                "y": ty,
                                "transform_to": None
                            })

                            # Option 2: Roll (move and roll the cube, changing to the face that naturally lands on top)
                            diff_x = tx - unit["x"]
                            diff_y = ty - unit["y"]
                            from server import rotate_cube_faces
                            faces = unit.get("faces", {"top": unit.get("symbol", "I"), "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "A"})
                            new_faces = rotate_cube_faces(faces, diff_x, diff_y)
                            symbol_map = {"A": "artillery", "I": "infantry", "C": "cavalry", "R": "relay", "M": "mine", "S": "shield"}
                            rolled_face = symbol_map.get(new_faces["top"], "infantry")

                            if rolled_face != unit["type"].lower():
                                legal_actions.append({
                                    "action_type": "move",
                                    "unitId": unit["id"],
                                    "x": tx,
                                    "y": ty,
                                    "transform_to": rolled_face
                                })
        return legal_actions

    def _calculate_exact_threat_map(self, units: list, side: str) -> set:
        """
        Generates a high-fidelity tactical vulnerability map by querying the
        engine's combat proxy rules for all accessible tiles within enemy reach corridors.
        """
        threatened_coords = set()
        enemy_side = "South" if side == "North" else "North"
        enemies = [u for u in units if u.get("side") == enemy_side]

        # Fetch active lines of communication to accurately simulate enemy supply verification
        try:
            connected_enemies = self.engine.get_connected_units(units, enemy_side)
        except Exception:
            connected_enemies = set()

        for enemy in enemies:
            # If an enemy unit is stranded out of supply, its movement is frozen (speed = 0)
            if enemy["id"] not in connected_enemies:
                continue

            ex, ey = enemy.get("x", 0), enemy.get("y", 0)
            e_type = enemy.get("type", "").lower()
            stats = self.engine.get_stats(e_type)

            # Maximum Operational envelope = Movement Speed budget + Weapon Fire Range
            max_reach = stats.get("speed", 1) + stats.get("range", 1)

            # Evaluate coordinates within the physical operational footprint of this enemy unit
            for dx in range(-max_reach, max_reach + 1):
                for dy in range(-max_reach, max_reach + 1):
                    tx, ty = ex + dx, ey + dy

                    # Ensure targets sit within active grid matrix boundaries
                    if 0 <= tx < self.engine.cols and 0 <= ty < self.engine.rows:
                        if (tx, ty) in threatened_coords:
                            continue

                        # Mock a hypothetical combat placement to test if the vector system clears the tile
                        # We evaluate if the enemy side can successfully score a DESTROY or RETREAT force metric
                        combat = self.engine.calculate_combat(units, enemy_side, tx, ty)
                        if combat.get("valid") and combat.get("result") in ["DESTROY", "RETREAT"]:
                            threatened_coords.add((tx, ty))

        return threatened_coords

    def calculate_cohesion_loss(self, units, unit_id, target_x, target_y):
        ghost = copy.deepcopy(units)
        u = next((unit for unit in ghost if unit['id'] == unit_id), None)
        if not u: return 0
        u['x'], u['y'] = target_x, target_y
        before = self.engine.get_connected_units(units, self.side)
        after = self.engine.get_connected_units(ghost, self.side)
        return len(before - after)


    # def _simulate_enemy_best_response(self, hypothetical_units: list) -> float:
    #     """
    #     Simulates the enemy's mindset by generating their best possible
    #     counter-action on the proposed board state and returning its score.
    #     """
    #     # ── DYNAMIC MOVE POOL ENFORCEMENT ──
    #     # Calculate exactly how many alive units the enemy side possesses in this state
    #     enemy_unit_count = sum(1 for u in hypothetical_units if u.get("side") == self.enemy_side)
    #     simulated_moves_budget = max(1, enemy_unit_count)

    #     # Create a mock state matching what the enemy sees with the dynamic budget
    #     enemy_state = {
    #         "units": hypothetical_units,
    #         "moved_units_this_turn": [],
    #         "attack_executed_this_turn": False,
    #         "moves_left": simulated_moves_budget
    #     }

    #     # Gather all legal actions the enemy could take in response
    #     # Pass the empty list so it evaluates options assuming it's the start of their simulated turn
    #     enemy_actions = self.enemy_evaluator.get_all_legal_moves(hypothetical_units, [])
    #     if not enemy_actions:
    #         return self.enemy_evaluator.evaluate_board(hypothetical_units, is_end_turn=True)

    #     best_enemy_response_score = -999999.0

    #     # Evaluate the top enemy choices to see their maximum damage potential
    #     # (Limit to a subset or look at raw values to keep runtime fast)
    #     for e_action in enemy_actions[:15]:
    #         ghost_board = copy.deepcopy(hypothetical_units)

    #         # Simulate the enemy's prospective attack or move
    #         if e_action["action_type"] == "attack":
    #             ghost_board = [u for u in ghost_board if not (u["x"] == e_action["x"] and u["y"] == e_action["y"])]
    #         elif e_action["action_type"] == "move":
    #             for u in ghost_board:
    #                 if u["id"] == e_action["unitId"]:
    #                     u["x"], u["y"] = e_action["x"], e_action["y"]

    #                     # Apply face mutations in the simulation if the action schedules one
    #                     chosen_face = e_action.get("transform_to")
    #                     if chosen_face:
    #                         u["type"] = chosen_face.lower()
    #                         if chosen_face == "artillery":
    #                             u["symbol"] = "A"
    #                         elif chosen_face == "infantry":
    #                             u["symbol"] = "I"
    #                         elif chosen_face == "cavalry":
    #                             u["symbol"] = "C"
    #                         elif chosen_face == "relay":
    #                             u["symbol"] = "R"
    #                         elif chosen_face == "mine":
    #                             u["symbol"] = "M"
    #                         elif chosen_face == "shield":
    #                             u["symbol"] = "S"
    #                     break

    #         # Score how good this state is for the enemy
    #         # A single counter-move represents an active pressure deployment step
    #         is_final_sim_state = (simulated_moves_budget == 1)
    #         enemy_score = self.enemy_evaluator.evaluate_board(ghost_board, is_end_turn=is_final_sim_state)
    #         if enemy_score > best_enemy_response_score:
    #             best_enemy_response_score = enemy_score

    #     return best_enemy_response_score



    def _simulate_enemy_best_response(self, hypothetical_units: list) -> float:
        """
        Simulates an aggressive, multi-step lookahead horizon.
        1. Finds the enemy's absolute best response to our prospective action.
        2. Simulates our OWN best aggressive follow-up action to that response.
        Allows the AI to see that taking a calculated risk now unlocks a lethal
        combination or assassination strike on the subsequent turn.

        Pre-sorting rationale:
        `get_all_legal_moves` emits actions in fixed generation order — attacks
        first, then moves in dx=-3..+3 / dy=-3..+3 / face iteration order.
        Without sorting, [:12] always picks up corner-moves (dx=-3, dy=-3 tiles)
        while missing the genuinely threatening responses buried at position 300+:
        cavalry-transforms that enable a next-turn charge (charge=7), artillery
        repositioning for range-3 coverage, or advances straight at our arsenal.
        We pre-sort by a fast danger heuristic so the slice always contains the
        most threatening possibilities.

        Transform awareness:
        The lookahead correctly applies transform_to to the ghost board (enemy
        flips to cavalry, etc.), but it only sees one half-step — the transformed
        unit positioned there, not yet attacking.  By giving cavalry/artillery
        transforms a high heuristic score we ensure those board states are always
        evaluated, so evaluate_board can price in the increased stacked_attack_
        pressure and role_score the new type confers.
        """
        enemy_unit_count = sum(1 for u in hypothetical_units if u.get("side") == self.enemy_side)
        simulated_moves_budget = max(1, enemy_unit_count)

        # Gather all legal actions the enemy could take in response
        enemy_actions = self.enemy_evaluator.get_all_legal_moves(hypothetical_units, [])
        if not enemy_actions:
            return self.enemy_evaluator.evaluate_board(hypothetical_units, is_end_turn=True)

        best_enemy_response_score = -999999.0
        worst_case_ghost_board = []

        # ── PRE-SORT: rank by fast danger heuristic BEFORE slicing to [:12] ──
        ai_side_units = [u for u in hypothetical_units if u.get("side") == self.side]
        our_arsenal_coords = list(self.engine.arsenals[self.side])

        def _danger_heuristic(ea: dict) -> float:
            if ea["action_type"] == "attack":
                # Run the real combat resolver — confirmed DESTROY is the most
                # dangerous thing the enemy can do in one action.
                combat = self.engine.calculate_combat(
                    hypothetical_units, self.enemy_side, ea["x"], ea["y"], verbose=False
                )
                if not combat.get("valid"):
                    return -1000.0                   # invalid attacks go to the very back
                if combat["result"] == "DESTROY":
                    target = next(
                        (u for u in hypothetical_units
                         if u["x"] == ea["x"] and u["y"] == ea["y"]), None
                    )
                    piece_val = self.unit_values.get(
                        target.get("type", "").lower(), 20) if target else 20
                    # Higher-value kills rank higher; so do high net-force hits
                    return 100_000.0 + piece_val * 100 + combat.get("net_force", 0) * 500
                elif combat["result"] == "RETREAT":
                    return 50_000.0 + combat.get("net_force", 0) * 200
                else:
                    return 5_000.0    # FAIL but valid — still beats random moves

            elif ea["action_type"] == "move":
                score = 0.0
                transform = ea.get("transform_to")

                # ── Transform threat scoring ──
                # Even though this lookahead only sees one half-step, a unit
                # that transforms to cavalry on a forward tile can charge us
                # next turn (charge=7); artillery gains range-3 fire (offense=5).
                # Scoring these highly ensures they always appear in the evaluated
                # pool so evaluate_board can price the resulting threat correctly.
                if transform == "cavalry":
                    score += 40_000.0   # charge threat materialises next turn
                elif transform == "artillery":
                    score += 30_000.0   # long-range fire platform
                elif transform == "infantry":
                    score += 8_000.0    # solid all-rounder upgrade

                # ── Objective pressure: closing on our arsenal ──
                if our_arsenal_coords:
                    ax, ay = our_arsenal_coords[0]
                    dist_to_base = max(abs(ea["x"] - ax), abs(ea["y"] - ay))
                    score += max(0.0, (10 - dist_to_base)) * 600.0

                # ── Attack positioning: closing on our combat units ──
                if ai_side_units:
                    min_dist = min(
                        max(abs(ea["x"] - u["x"]), abs(ea["y"] - u["y"]))
                        for u in ai_side_units
                    )
                    score += max(0.0, (8 - min_dist)) * 300.0

                return score

            return 0.0

        # Sort descending — [:12] now contains the genuinely most threatening
        # responses, not whatever dx/dy came first in generation order.
        enemy_actions_sorted = sorted(enemy_actions, key=_danger_heuristic, reverse=True)

        # Step 1: Evaluate the top dangerous enemy responses
        for e_action in enemy_actions_sorted[:30]:
            ghost_board = copy.deepcopy(hypothetical_units)

            if e_action["action_type"] == "attack":
                ghost_board = [u for u in ghost_board if not (u["x"] == e_action["x"] and u["y"] == e_action["y"])]
            elif e_action["action_type"] == "move":
                for u in ghost_board:
                    if u["id"] == e_action["unitId"]:
                        u["x"], u["y"] = e_action["x"], e_action["y"]
                        chosen_face = e_action.get("transform_to")
                        if chosen_face:
                            u["type"] = chosen_face.lower()
                            mapping = {"artillery": "A", "infantry": "I", "cavalry": "C", "relay": "R", "mine": "M", "shield": "S"}
                            if u["type"] in mapping:
                                u["symbol"] = mapping[u["type"]]
                        break

            is_final_sim_state = (simulated_moves_budget == 1)
            enemy_score = self.enemy_evaluator.evaluate_board(ghost_board, is_end_turn=is_final_sim_state)
            
            if enemy_score > best_enemy_response_score:
                best_enemy_response_score = enemy_score
                worst_case_ghost_board = ghost_board  # Capture the exact state where the enemy hurts us most

        # ── STEP 2: LOOK-AHEAD COMBINATORIAL INITIATIVE (OUR RE-COUNTER) ──
        # If the enemy response leaves an opening, check if we can string together an assassination path
        if worst_case_ghost_board:
            # Generate OUR legal options on top of the enemy's best response board state
            our_follow_up_actions = self.get_all_legal_moves(worst_case_ghost_board, [])
            
            best_our_retaliation_bonus = 0.0
            
            for our_act in our_follow_up_actions:
                # We explicitly scan for our own follow-up attacks or terminal objective breaks
                if our_act["action_type"] == "attack":
                    combat = self.engine.calculate_combat(worst_case_ghost_board, self.side, our_act["x"], our_act["y"], verbose=False)
                    if combat.get("valid") and combat["result"] == "DESTROY":
                        target_unit = next((u for u in worst_case_ghost_board if u["x"] == our_act["x"] and u["y"] == our_act["y"]), None)
                        if target_unit:
                            # Is this a vital high-value combat piece, a logistics relay, or an asset close to the goal?
                            target_type = target_unit.get("type", "").lower()
                            # Elevate the incentive of setting up this future assassination killshot
                            killshot_premium = 60000.0 if target_type in ["artillery", "relay", "cavalry"] else 25000.0
                            if killshot_premium > best_our_retaliation_bonus:
                                best_our_retaliation_bonus = killshot_premium

            # Subtract our future assassination value from the enemy's immediate score.
            # This mathematically tricks the AI into seeing that the enemy's counter-punch is nullified 
            # by the massive lethal trap we drop on them the very next move.
            best_enemy_response_score -= best_our_retaliation_bonus

        return best_enemy_response_score


    def log_enemy_defensive_safeguards(self, current_units: list):
        """
        Scans and prints an accurate structural diagnostic layout of every enemy unit's
        current defensive positioning, proxy safety, and braced vectors as they stand.
        """
        enemy_side = "North" if self.side == "South" else "South"
        enemy_units = [u for u in current_units if u.get("side") == enemy_side]

        print(f"\n========================================================")
        print(f"📡 [STATIC MATRIX SCAN] Profiling Enemy Defense & Safelines")
        print(f"========================================================")

        if not enemy_units:
            print("No enemy units detected on the grid matrix.")
            return

        for enemy in enemy_units:
            ex, ey = enemy["x"], enemy["y"]
            e_id = enemy["id"]

            # Pull actual unit type, ensuring we don't accidentally print a secondary state label
            e_type = enemy.get("type", "unknown").upper()

            # Get base defense stats
            base_def = self.engine.get_stats(enemy["type"]).get("defense", 0)

            print(f"\n🎯 Target Node: {e_id} ({e_type}) at Coord: ({ex}, {ey})")
            print(f"   ├─ Base Native Defense: {base_def}")

            # Track structural terrain defenses
            is_fortress = (ex, ey) in self.engine.fortresses
            is_pass = (ex, ey) in self.engine.passes

            if is_fortress:
                print("   ├─ Terrain Safeguard: FORTRESS (+4 Defense, x2 Stack Multiplier)")
            elif is_pass:
                print("   ├─ Terrain Safeguard: PASS (+2 Defense, x2 Stack Multiplier)")
            else:
                print("   ├─ Terrain Safeguard: OPEN GROUND (Standard)")

            print(f"   └─ Directional Brace Vectors (Where allies are physically standing):")

            # Scan all 8 directions to check where actual defensive support stacks exist
            for dx, dy in self.engine.directions:
                # We look in the direction the proxy line physically extends
                dir_label = self._get_direction_label(dx, dy)

                # Extract pure protection provided by units standing in this specific direction
                total_defense = self._extract_static_vector_defense(current_units, enemy, dx, dy)

                # Account for how open ground baseline vs terrain baseline looks
                terrain_base = (base_def + (4 if is_fortress else 2)) * 2 if (is_fortress or is_pass) else base_def

                if total_defense > terrain_base:
                    bonus = total_defense - terrain_base
                    print(
                        f"      ▪ [Line extending {dir_label}]: Total Defense={total_defense} | Proxy Support Stack = +{bonus}")
                else:
                    # If there are no allies in this direction, it retains the baseline terrain value
                    print(
                        f"      ▪ [Line extending {dir_label}]: Total Defense={total_defense} | No proxy backup in this vector")

        print(f"========================================================\n")

    def _extract_static_vector_defense(self, units: list, target_unit: dict, dx, dy) -> int:
        """
        Correctly extracts defensive values along a physical line extending in direction (dx, dy)
        behind or beside the target unit without letting terrain buffs multiply proxy numbers.
        """
        connected_defenders = self.engine.get_connected_units(units, target_unit['side'])
        if target_unit['id'] not in connected_defenders:
            return 0

        base_def = self.engine.get_stats(target_unit['type'])['defense']
        is_fortress = (target_unit['x'], target_unit['y']) in self.engine.fortresses
        is_pass = (target_unit['x'], target_unit['y']) in self.engine.passes

        # Step outward in the physical direction (dx, dy) to collect the support stack
        cx, cy = target_unit['x'] + dx, target_unit['y'] + dy
        defender_line = []

        while 0 <= cx < self.engine.cols and 0 <= cy < self.engine.rows:
            if (cx, cy) in self.engine.mountains:
                break
            u = next((unit for unit in units if unit['x'] == cx and unit['y'] == cy), None)
            if u and u['side'] == target_unit['side']:
                defender_line.append(u)
                cx += dx
                cy += dy
            else:
                # Any empty tile, mountain, or enemy blocks/breaks the contiguous brace chain
                break

        # 1. Calculate the target node's personal modified defense
            # ── FIXED LOGIC IN AI.PY ──
        target_personal_defense = base_def

        # Only allow the pass terrain type to modify stats
        if is_pass:
            target_personal_defense += 2
            total_defense = target_personal_defense * 2
        else:
            total_defense = target_personal_defense

        if not defender_line:
            return total_defense

        def_head = defender_line[0]
        if def_head['id'] in connected_defenders:
            def_head_stats = self.engine.get_stats(def_head['type'])
            def_head_dist = max(abs(def_head['x'] - target_unit['x']), abs(def_head['y'] - target_unit['y']))

            if def_head_dist <= def_head_stats['range']:
                total_defense += def_head_stats['defense']
                for back_def in defender_line[1:]:
                    if back_def['id'] in connected_defenders:
                        total_defense += self.engine.get_stats(back_def['type'])['defense']
            else:
                # Check for Artillery covering fire exception in the stack
                for idx, d_node in enumerate(defender_line):
                    if d_node['id'] in connected_defenders and "artillery" in d_node['type'].lower():
                        art_def_dist = max(abs(d_node['x'] - target_unit['x']), abs(d_node['y'] - target_unit['y']))
                        if art_def_dist <= 3:
                            total_defense += self.engine.get_stats("artillery")["defense"]
                            for back_def in defender_line[idx + 1:]:
                                if back_def['id'] in connected_defenders:
                                    total_defense += self.engine.get_stats(back_def['type'])['defense']
                            break

        return total_defense

    def _get_direction_label(self, dx, dy) -> str:
        labels = {
            (0, 1): "SOUTH", (0, -1): "NORTH", (1, 0): "EAST", (-1, 0): "WEST",
            (1, 1): "SOUTHEAST", (1, -1): "NORTHEAST", (-1, 1): "SOUTHWEST", (-1, -1): "NORTHWEST"
        }
        return labels.get((dx, dy), "UNKNOWN")



    def select_best_action(self, current_state: dict, allowed_clusters: set = None) -> dict:


        units = current_state["units"]

        # ─── INJECT THE SCANNER HERE ───
        try:
            self.log_enemy_defensive_safeguards(units)
        except Exception as e:
            print(f"⚠️ [LOG ERROR] Failed to run matrix scan layout: {e}")
        # ───────────────────────────────

        moved_this_turn = current_state["moved_units_this_turn"]
        attack_executed = current_state["attack_executed_this_turn"]

        try:
            start_north = set(self.engine.get_connected_units(units, "North"))
            start_south = set(self.engine.get_connected_units(units, "South"))
        except:
            start_north = start_south = set()
        base_enemy_connected = start_north if self.side == "South" else start_south
        base_my_connected = start_south if self.side == "South" else start_north

        target_y = 0 if self.side == "South" else 19

        last_updated = self.position_history.get("_last_updated_turn")
        if last_updated is None or last_updated != self.turn_counter:
            self.position_history["_last_updated_turn"] = self.turn_counter
            for u in units:
                if u.get("side") == self.side:
                    uid = u["id"]
                    if uid not in self.position_history:
                        self.position_history[uid] = []
                    self.position_history[uid].append((u["x"], u["y"]))
                    if len(self.position_history[uid]) > 8:
                        self.position_history[uid].pop(0)

        # Dynamic Goal Matrix Mapping
        local_goals = self._decide_local_goals(units, base_my_connected)

        enemy_side_label = "North" if self.side == "South" else "South"

        #  UPDATED SECURE VARIABLE INITIALIZATION BLOCK
        z3_safe_zones = set()  # Explicit top-level default guarantee
        if self._z3_safe_zones_turn != self.turn_counter:
            if hasattr(self.smt_oracle, 'calculate_absolute_safe_zones'):
                self._z3_safe_zones_cache = self.smt_oracle.calculate_absolute_safe_zones(units, enemy_side_label)
            else:
                self._z3_safe_zones_cache = set()
            self._z3_safe_zones_turn = self.turn_counter

        if self._z3_safe_zones_cache is not None:
            z3_safe_zones = self._z3_safe_zones_cache

        current_my_score = self.evaluate_board(units, base_enemy_connected=base_enemy_connected, original_units=units)
        if self.defensive_weight > 0:
            current_enemy_score = self.enemy_evaluator.evaluate_board(units, base_enemy_connected=base_my_connected,
                                                                      original_units=units)
            baseline_score = current_my_score - self.defensive_weight * current_enemy_score
        else:
            baseline_score = current_my_score

        best_score = baseline_score - 100.0
        best_action = {"action_type": "end_turn"}

        actions = self.get_all_legal_moves(units, moved_this_turn)
        if not actions:
            return {"action_type": "end_turn"}

        # move_actions = [a for a in actions if a["action_type"] == "move"]
        # attack_actions = [a for a in actions if a["action_type"] == "attack"]
        #
        # # --- FLAT ACTION EVALUATION POOL ---
        # candidate_actions = move_actions + attack_actions
        #
        # if not candidate_actions:
        #     return {"action_type": "end_turn"}
        #
        # diagnostic_log = {}
        # actions = candidate_actions

        move_actions = [a for a in actions if a["action_type"] == "move"]
        attack_actions = [a for a in actions if a["action_type"] == "attack"]

        # ── STEP 1: PRIORITIZE FREE ATTACKS FROM CURRENT STATIONARY CONFIGURATIONS ──
        if not attack_executed and attack_actions:
            best_stationary_attack = None
            best_stationary_score = -999999.0

            for att in attack_actions:
                # Query the symmetrical engine vector rules directly
                combat = self.engine.calculate_combat(units, self.side, att["x"], att["y"], verbose=False)
                if combat.get("valid") and combat["result"] in ["DESTROY", "RETREAT"]:
                    # Establish standalone priority weight: DESTROY beats RETREAT
                    att_score = 250000.0 + (combat["net_force"] * 1000.0 if combat["result"] == "DESTROY" else 80000.0)
                    if att_score > best_stationary_score:
                        best_stationary_score = att_score
                        best_stationary_attack = att

            # If an immediate safe execution path exists from our current spot, take it immediately!
            if best_stationary_attack:
                return best_stationary_attack

        # ── STEP 2: MOVEMENT CONFIGURATION SELECTION POOL ──
        # If no immediate free standstill attack is available, fall back to pure repositioning
        if not move_actions:
            return {"action_type": "end_turn"}

        diagnostic_log = {}
        actions = move_actions  # Safe movement processing loop execution

        ai_units = [u for u in units if u.get("side") == self.side]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]

        # ── PRE-CALCULATE THREAT MAPS AND FORK MAP PILES TO ACCELERATE RUNTIMES ──
        active_threatened_tiles = self._calculate_exact_threat_map(units, self.side)

        # unit_fork_maps = {}
        # for au in [u for u in units if u.get("side") == self.side and u["id"] not in moved_this_turn]:
        #     allowed_moves = [a for a in move_actions if a["unitId"] == au["id"]]
        #     fork_sol = self.smt_oracle.solve_geometric_fork(units, self.side, au["id"], allowed_moves)
        #     if fork_sol:
        #         unit_fork_maps[au["id"]] = (fork_sol["x"], fork_sol["y"], fork_sol["fork_bonus"])

        #  SAFEGUARDED LAYER WITH FORK SOLVER DETECTION
        unit_fork_maps = {}
        if hasattr(self.smt_oracle, 'solve_geometric_fork'):
            for au in [u for u in units if u.get("side") == self.side and u["id"] not in moved_this_turn]:
                allowed_moves = [a for a in move_actions if a["unitId"] == au["id"]]
                fork_sol = self.smt_oracle.solve_geometric_fork(units, self.side, au["id"], allowed_moves)
                if fork_sol:
                    unit_fork_maps[au["id"]] = (fork_sol["x"], fork_sol["y"], fork_sol["fork_bonus"])

        if self._safety_cache_turn != self.turn_counter:
            self._safety_cache = {}
            self._safety_cache_turn = self.turn_counter
        verified_safety_cache = self._safety_cache

        # for action in actions:

        priority_actions = sorted(
            actions, 
            key=lambda a: 0 if a["action_type"] == "attack" else 1
        )

        for action in priority_actions:
            temp = copy.deepcopy(units)
            mod = 0.0
            chosen_face = None

            z3_penalty_this_action = 0.0

            act_uid = action.get("unitId")
            dest_x, dest_y = action.get("x"), action.get("y")

            if act_uid and action["action_type"] == "move":
                history = self.position_history.get(act_uid, [])
                if len(history) >= 2:
                    recent_history = history[-3:]
                    if (dest_x, dest_y) in recent_history:
                        mod -= 180000.0

                has_stuck_unit = any(self._detect_behavioral_anomaly(u["id"]) is not None for u in ai_units)
                if has_stuck_unit:
                    acting_anomaly = self._detect_behavioral_anomaly(act_uid)
                    if not acting_anomaly:
                        mod += 15000.0

            acting_unit = next((u for u in units if u["id"] == act_uid), None)
            if not acting_unit and action["action_type"] != "end_turn":
                continue


            u_type = acting_unit.get("type", "").lower() if acting_unit else ""

            # SMT Supply Line Lock Veto
            if acting_unit and action["action_type"] == "move":
                ghost_units = copy.deepcopy(units)
                for gu in ghost_units:
                    if gu["id"] == act_uid:
                        gu["x"], gu["y"] = dest_x, dest_y
                        break

                try:
                    connected_before = self.engine.get_connected_units(units, self.side)
                    connected_after = self.engine.get_connected_units(ghost_units, self.side)

                    if len(connected_before - connected_after) > 0:
                        mod -= 500000.0
                except Exception:
                    pass

            # Direct Base Defense Reaction Layers
            if acting_unit and "relay" not in acting_unit.get("type", "").lower():
                our_arsenals = self.engine.arsenals[self.side]
                threatening_enemies = []
                for e in enemy_units:
                    for ax, ay in our_arsenals:
                        if max(abs(e["x"] - ax), abs(e["y"] - ay)) <= 6:
                            threatening_enemies.append(e)
                            break

                if threatening_enemies:
                    combat_units = [u for u in ai_units if "relay" not in u.get("type", "").lower()]
                    defenders_assigned = set()
                    for e in threatening_enemies:
                        if combat_units:
                            closest_u = min(combat_units,
                                            key=lambda cu: max(abs(cu["x"] - e["x"]), abs(cu["y"] - e["y"])))
                            defenders_assigned.add(closest_u["id"])

                    if acting_unit["id"] in defenders_assigned:
                        if action["action_type"] == "attack":
                            if any(e["x"] == dest_x and e["y"] == dest_y for e in threatening_enemies):
                                mod += 150000.0

                        elif action["action_type"] == "move":
                            try:
                                before_connected = self.engine.get_connected_units(units, self.side)
                                after_connected = self.engine.get_connected_units(temp, self.side)
                                is_self_connected = acting_unit["id"] in after_connected
                                breaks_ally_supply = len(before_connected - after_connected) > 0
                            except:
                                is_self_connected = True
                                breaks_ally_supply = False

                            if is_self_connected and not breaks_ally_supply:
                                min_dist_before = min(
                                    max(abs(acting_unit["x"] - e["x"]), abs(acting_unit["y"] - e["y"])) for e in
                                    threatening_enemies)
                                min_dist_after = min(max(abs(dest_x - e["x"]), abs(dest_y - e["y"])) for e in
                                                     threatening_enemies)
                                if min_dist_after < min_dist_before:
                                    mod += 40000.0
                                elif min_dist_after > min_dist_before:
                                    mod -= 20000.0

            # ── REFACTORED ATTACK LOGIC: LOOKAHEAD SYNERGY STACKING ──
            if action["action_type"] == "attack":
                if attack_executed: continue
                combat = self.engine.calculate_combat(temp, self.side, dest_x, dest_y, verbose=False)
                # ── INJECT THIS LOG ──

                if combat.get("valid"):
                    target_unit = next((u for u in temp if u["x"] == dest_x and u["y"] == dest_y), None)
                    is_target_cutoff = False
                    if target_unit:
                        target_connected = target_unit["id"] in self.engine.get_connected_units(temp, self.enemy_side)
                        is_target_cutoff = not target_connected
                    if combat["result"] == "DESTROY":
                        mod += 250000.0 + combat["net_force"] * 1000.0
                        if is_target_cutoff:
                            mod += 120000.0
                        if target_unit and "relay" in target_unit.get("type", "").lower():
                            # Dynamic relay kill bonus: counts how many enemy units get stranded
                            try:
                                connected_before_kill = set(self.engine.get_connected_units(temp, self.enemy_side))
                                temp_after_kill = [u for u in temp if not (u["x"] == dest_x and u["y"] == dest_y)]
                                connected_after_kill = set(self.engine.get_connected_units(temp_after_kill, self.enemy_side))
                                units_cut_off = connected_before_kill - connected_after_kill
                                # Base relay kill value + 80,000 per unit we strand
                                mod += 80000.0 + len(units_cut_off) * 80000.0
                            except:
                                mod += 200000.0  # fallback to static bonus
                        temp = [u for u in temp if not (u["x"] == dest_x and u["y"] == dest_y)]
                    elif combat["result"] == "RETREAT":
                        mod += 80000.0 + combat["net_force"] * 500.0
                        if is_target_cutoff:
                            mod += 60000.0
                    else:
                        # FAIL result: individually we don't kill/retreat the target.
                        # But we reward the projected offense to encourage cooperative stack attacks
                        # and chipping away high-defense units (like Artillery/Shields).
                        mod += combat["offense"] * 800.0  # Encourage axis pressure
                        
                        if target_unit:
                            converging_allies = []
                            for ally in [u for u in units if u["side"] == self.side]:
                                a_type = ally.get("type", "").lower()
                                a_reach = 4 if a_type in ["cavalry", "artillery"] else 3
                                dist = max(abs(dest_x - ally["x"]), abs(dest_y - ally["y"]))
                                if dist <= a_reach:
                                    converging_allies.append(ally)

                            stack_size = len(converging_allies)
                            if stack_size >= 2:
                                mod += 8000.0 * stack_size
                                if target_unit.get("type", "").lower() == "artillery":
                                    mod += 40000.0
                            else:
                                mod += 15000.0
                else:
                    mod -= 100000.0


            # ── UPGRADED MOVE LOGIC WITH STRUCTURAL VULNERABILITY MATRIX ──
            elif action["action_type"] == "move":
                is_currently_in_danger = (acting_unit["x"], acting_unit["y"]) in active_threatened_tiles

                # Check if an enemy can reach this vicinity next turn by combining their movement and attack range
                # near_enemy_reach = False
                # for e in enemy_units:
                #     e_stats = self.engine.get_stats(e.get("type", ""))
                #     max_reach = (2 if e.get("type", "").lower() == "cavalry" else 1) + e_stats.get("range", 2)
                #     if max(abs(dest_x - e["x"]), abs(dest_y - e["y"])) <= max_reach + 1:
                #         near_enemy_reach = True
                #         break

                # ── Z3 GATE: only call the oracle when an enemy can CURRENTLY
                # fire on the destination from their existing position — not from
                # any hypothetical repositioned tile.  The old logic used
                # speed+range as max_reach, which flagged nearly every mid-board
                # tile and fed the oracle constantly with pessimistic scores.
                # We still keep active_threatened_tiles (which already encodes
                # current LOS-based threats) as the primary gate.
                near_enemy_reach = False
                for e in enemy_units:
                    e_stats = self.engine.get_stats(e.get("type", ""))
                    # Strict current-position firing range only — no movement budget added
                    current_fire_range = e_stats.get("range", 2)
                    if max(abs(dest_x - e["x"]), abs(dest_y - e["y"])) <= current_fire_range:
                        # Also require rough LOS alignment (same row, col, or diagonal)
                        dx_diff = abs(dest_x - e["x"])
                        dy_diff = abs(dest_y - e["y"])
                        if dx_diff == 0 or dy_diff == 0 or dx_diff == dy_diff:
                            near_enemy_reach = True
                            break

                is_moving_into_danger = (dest_x, dest_y) in active_threatened_tiles or near_enemy_reach

                if (dest_x, dest_y) in active_threatened_tiles:
                    nearby_allies = sum(1 for a in units if
                                        a["side"] == self.side and a["id"] != act_uid and max(abs(dest_x - a["x"]),
                                                                                              abs(dest_y - a[
                                                                                                  "y"])) <= 1)
                    if nearby_allies >= 1:
                        mod += 25000.0 * nearby_allies
                    else:
                        mod -= 45000.0
                elif is_currently_in_danger and not (dest_x, dest_y) in active_threatened_tiles:
                    nearby_allies = sum(1 for a in units if a["side"] == self.side and a["id"] != act_uid and max(
                        abs(acting_unit["x"] - a["x"]), abs(acting_unit["y"] - a["y"])) <= 1)
                    if nearby_allies == 0:
                        mod += 35000.0

                enemy_arsenals = self.engine.arsenals[self.enemy_side]
                was_on_arsenal = acting_unit and (acting_unit["x"], acting_unit["y"]) in enemy_arsenals
                if was_on_arsenal:
                    ax, ay = acting_unit["x"], acting_unit["y"]
                    other_occupant = any(
                        u["id"] != act_uid and u["x"] == ax and u["y"] == ay and u["side"] == self.side for u in units)
                    if not other_occupant and (dest_x, dest_y) != (ax, ay):
                        mod -= 40000.0

                if (dest_x, dest_y) in enemy_arsenals:
                    mod += 15000.0

                # landed_on_mine = any(
                #     m["x"] == dest_x and m["y"] == dest_y for m in current_state.get("mines", []))
                # if landed_on_mine:
                #     temp = [unit for unit in temp if unit["id"] != act_uid]

                landed_on_mine = False
                # Track both existing mines and newly spawned mines in this simulation turn
                simulated_mines = list(current_state.get("mines", []))
                
                # Check if this unit is a mine starting its move, which will spawn a mine at its source coords
                is_spawning_mine_here = False
                source_x, source_y = acting_unit["x"], acting_unit["y"]
                if acting_unit and acting_unit.get("symbol") == "M":
                    is_spawning_mine_here = True
                    # Add to the simulated mines pool for this action check
                    simulated_mines.append({"x": source_x, "y": source_y, "side": self.side})

                for mine in simulated_mines:
                    if mine["x"] == dest_x and mine["y"] == dest_y:
                        landed_on_mine = True
                        break

                if landed_on_mine:
                    mod -= 800000.0
                    temp = [unit for unit in temp if unit["id"] != act_uid]

                else:
                    # Apply offensive mine-laying bonus if we successfully drop a mine near the enemy
                    if is_spawning_mine_here and source_x is not None:
                        for e in enemy_units:
                            dist_to_dropped_mine = max(abs(source_x - e["x"]), abs(source_y - e["y"]))
                            if dist_to_dropped_mine <= 3:
                                mod += 12000.0  # Tactical block bonus
                                break
                            
                    was_relay = (acting_unit.get("symbol") == "R")
                    
                    for u in temp:
                        if u.get("id") == act_uid:
                            u["x"], u["y"] = dest_x, dest_y

                            chosen_face = action.get("transform_to")
                            if chosen_face:
                                from server import rotate_cube_faces
                                dx = dest_x - source_x
                                dy = dest_y - source_y
                                faces = u.get("faces", {"top": u.get("symbol", "I"), "bottom": "A", "front": "C", "back": "R", "left": "I", "right": "A"})
                                new_faces = rotate_cube_faces(faces, dx, dy)
                                target_symbol = {"artillery": "A", "infantry": "I", "cavalry": "C",
                                                 "relay": "R", "mine": "M", "shield": "S"}[chosen_face.lower()]
                                found_face = next((k for k, v in new_faces.items() if v == target_symbol), None)
                                if found_face and found_face != "top":
                                    new_faces["top"], new_faces[found_face] = new_faces[found_face], new_faces["top"]
                                u["faces"] = new_faces
                                u["type"] = chosen_face.lower()
                                u["symbol"] = target_symbol
                            else:
                                chosen_face = u["type"].lower()
                            
                            is_losing_relay = was_relay and (chosen_face != "relay")
                            
                            # Calculate connectivity before transformation to check for supply cuts
                            connected_before = set()
                            if is_losing_relay:
                                try:
                                    connected_before = self.engine.get_connected_units(temp, self.side)
                                except:
                                    pass

                            if chosen_face:
                                u["type"] = chosen_face.lower()
                                if chosen_face == "artillery":
                                    u["symbol"] = "A"
                                elif chosen_face == "infantry":
                                    u["symbol"] = "I"
                                elif chosen_face == "cavalry":
                                    u["symbol"] = "C"
                                elif chosen_face == "relay":
                                    u["symbol"] = "R"
                                elif chosen_face == "mine":
                                    u["symbol"] = "M"
                                elif chosen_face == "shield":
                                    u["symbol"] = "S"

                                # Check connectivity after transformation
                                if is_losing_relay:
                                    try:
                                        connected_after = self.engine.get_connected_units(temp, self.side)
                                        lost_connections = len(connected_before - connected_after)
                                        if lost_connections > 0:
                                            mod -= 25000.0 * lost_connections
                                    except:
                                        pass

                                goal = local_goals.get(act_uid, "STAY")
                                if goal in ["RETREAT", "HOLD_FORMATION"] and chosen_face == "shield":
                                    mod += 400.0
                                elif goal in ["ATTACK", "ATTACK_RUN"] and chosen_face == "artillery":
                                    mod += 300.0
                                elif goal == "BLITZ_CHARGE" and chosen_face == "cavalry":
                                    mod += 250.0
                                elif chosen_face == "relay" and not was_relay:
                                    # Count-aware relay transformation policy:
                                    # A relay is valuable logistics when you have an army to supply.
                                    # It's a wasted piece when you're running low on fighters.
                                    friendly_pieces = [u for u in units if u.get("side") == self.side]
                                    friendly_count = len(friendly_pieces)
                                    existing_relays = sum(
                                        1 for u in friendly_pieces
                                        if u.get("type", "").lower() == "relay" and u["id"] != act_uid
                                    )

                                    if friendly_count <= 2:
                                        # Endgame: every piece must fight — never become a relay
                                        mod -= 20000.0
                                    elif existing_relays >= 1:
                                        # Already have a relay — don't stack more logistics
                                        mod -= 5000.0
                                    elif friendly_count >= 4 and existing_relays == 0:
                                        # 4+ pieces, no relay yet — building the first one is good strategy
                                        mod += 4000.0
                                    else:
                                        # 3 pieces, no relay — mildly discourage, not critical
                                        mod -= 1000.0

                                else:
                                    mod -= 100.0

                            if act_uid in unit_fork_maps:
                                fx, fy, f_bonus = unit_fork_maps[act_uid]
                                if dest_x == fx and dest_y == fy: mod += f_bonus

                            if (dest_x, dest_y) in z3_safe_zones:
                                goal = local_goals.get(act_uid, "STAY")
                                if goal in ["RETREAT", "HOLD_FORMATION"]: mod += 350.0


                            # if is_moving_into_danger or (dest_x, dest_y) in z3_safe_zones:
                            #     cache_key = (act_uid, dest_x, dest_y, chosen_face)
                            #     if cache_key in verified_safety_cache:
                            #         danger_score = verified_safety_cache[cache_key]
                            #     else:
                            #         acting_stats = self.engine.get_stats(u.get("type", "").lower())
                            #         target_def = acting_stats.get("defense", 5)

                            #         # Pass the chosen face into the Oracle so Z3 knows we are transforming!
                            #         danger_score = self.smt_oracle.verify_action_safety(
                            #             temp, self.side, (dest_x, dest_y), target_def, self.engine,
                            #             target_transform_type=chosen_face
                            #         )
                            #         verified_safety_cache[cache_key] = danger_score

                            #     if danger_score >= 2.0:
                            #         # Scale down the massive fear penalty so it doesn't cause stasis freezes
                            #         z3_penalty_this_action = danger_score * 1500.0
                            #         mod -= z3_penalty_this_action

                            #         # If we transformed into a defensive block, give an aggressive push incentive
                            #         if chosen_face in ["shield", "infantry"]:
                            #             mod += 2000.0  # Proactive stand bonus!

                            #         # ── CRITICAL ADDITION: STRUCTURAL DISCONNECTION LETHALITY PROOF ──
                            #         # If Z3 exposes that this unit can be destroyed next turn, check the macro operational cost
                            #         post_mortality_units = [unit for unit in temp if unit["id"] != act_uid]
                            #         try:
                            #             connected_now = self.engine.get_connected_units(temp, self.side)
                            #             connected_after_death = self.engine.get_connected_units(post_mortality_units,
                            #                                                                     self.side)


                            #             cascading_losses = len(connected_now - connected_after_death)
                            #             if cascading_losses > 0:
                            #                 mod -= 35000.0 * cascading_losses
                            #                 print(
                            #                     f"🛑 [DYNAMIC RISK] Unit={act_uid} destruction isolates {cascading_losses} units.",
                            #                     file=sys.stderr)
                            #         except:
                            #             pass



                            # ── TWO-ORACLE Z3 THREAT ASSESSMENT ──
                            # Oracle A (verify_action_safety): fast theoretical ceiling.
                            # Oracle B (compute_threat_probability): realistic probability-weighted threat.
                            # We only invoke Oracle B when Oracle A confirms the ceiling is high enough
                            # to matter — i.e. it's physically possible to be killed here.
                            if is_moving_into_danger or (dest_x, dest_y) in z3_safe_zones:
                                cache_key = (act_uid, dest_x, dest_y, chosen_face)
                                if cache_key in verified_safety_cache:
                                    danger_score, expected_offense, p_lethal = verified_safety_cache[cache_key]
                                else:
                                    acting_stats = self.engine.get_stats(u.get("type", "").lower())
                                    target_def   = acting_stats.get("defense", 5)

                                    # Oracle A — danger ceiling (Z3 Optimize / worst-case)
                                    danger_score = self.smt_oracle.verify_action_safety(
                                        temp, self.side, (dest_x, dest_y), target_def, self.engine,
                                        target_transform_type=chosen_face, mines=simulated_mines
                                    )

                                    # Oracle B — probabilistic threat (Z3 AllSAT + Real arithmetic)
                                    # Only invoked when the ceiling says lethality is physically possible.
                                    if danger_score >= 2.0:
                                        expected_offense, p_lethal = self.smt_oracle.compute_threat_probability(
                                            temp, self.side, (dest_x, dest_y), target_def, self.engine,
                                            target_transform_type=chosen_face, mines=simulated_mines
                                        )
                                    else:
                                        expected_offense, p_lethal = 0.0, 0.0

                                    verified_safety_cache[cache_key] = (danger_score, expected_offense, p_lethal)

                                if danger_score >= 2.0:
                                    # ── RISK BUFFERS (Calibrated to 0.0 to prevent suicide blunders) ──
                                    risk_absorption_buffer = 0.0

                                    # ── PROBABILITY-ADJUSTED PENALTY ──
                                    # expected_offense * p_lethal = what we realistically expect to face.
                                    # This is always ≤ danger_score (the ceiling), and often much lower:
                                    # if p_lethal = 0.10, the effective threat is 10× smaller than worst-case,
                                    # meaning a move that looked suicidal can be a calculated risk.
                                    prob_adjusted_threat = expected_offense * p_lethal
                                    excess_threat = max(0.0, prob_adjusted_threat - risk_absorption_buffer)
                                    z3_penalty_this_action = excess_threat * 100.0
                                    mod -= z3_penalty_this_action

                                    if p_lethal > 0.5:
                                        print(
                                            f"   ⚠️  [ORACLE-B] High lethal probability: "
                                            f"p_lethal={p_lethal:.2f}  E[offense]={expected_offense:.1f}  "
                                            f"ceiling={danger_score:.1f}  unit={act_uid}",
                                            file=sys.stderr
                                        )

                                    # ── CONDITIONAL PROACTIVE DEFENSE TRANSFORMS ──
                                    if p_lethal >= 0.40:
                                        if chosen_face == "shield":
                                            mod += 4000.0
                                    else:
                                        if chosen_face in ["infantry", "artillery"]:
                                            mod += 2000.0

                                    # Macro Operational Cost Lookahead (Unchanged)
                                    post_mortality_units = [unit for unit in temp if unit["id"] != act_uid]
                                    try:
                                        connected_now = self.engine.get_connected_units(temp, self.side)
                                        connected_after_death = self.engine.get_connected_units(post_mortality_units, self.side)
                                        cascading_losses = len(connected_now - connected_after_death)
                                        if cascading_losses > 0:
                                            mod -= 12000.0 * cascading_losses
                                    except:
                                        pass
                            break


                    if (dest_x, dest_y) in {(2, 4), (7, 5)}:
                        best_lazarus_symbol = "I"
                        best_lazarus_score = -999999.0
                        for test_sym in ("I", "A", "C", "R", "M", "S"):
                            for u in temp:
                                if u["id"] == act_uid:
                                    u["symbol"] = test_sym
                                    if test_sym == "I":
                                        u["type"] = "infantry"
                                    elif test_sym == "A":
                                        u["type"] = "artillery"
                                    elif test_sym == "C":
                                        u["type"] = "cavalry"
                                    elif test_sym == "R":
                                        u["type"] = "relay"
                                    elif test_sym == "M":
                                        u["type"] = "mine"
                                    elif test_sym == "S":
                                        u["type"] = "shield"
                                    break
                            try:
                                test_score = self.evaluate_board(temp, base_enemy_connected=base_enemy_connected)
                            except:
                                test_score = -50000.0
                            if test_score > best_lazarus_score:
                                best_lazarus_score = test_score
                                best_lazarus_symbol = test_sym
                        for u in temp:
                            if u["id"] == act_uid:
                                u["symbol"] = best_lazarus_symbol
                                if best_lazarus_symbol == "I":
                                    u["type"] = "infantry"
                                elif best_lazarus_symbol == "A":
                                    u["type"] = "artillery"
                                elif best_lazarus_symbol == "C":
                                    u["type"] = "cavalry"
                                elif best_lazarus_symbol == "R":
                                    u["type"] = "relay"
                                elif best_lazarus_symbol == "M":
                                    u["type"] = "mine"
                                elif best_lazarus_symbol == "S":
                                    u["type"] = "shield"
                                break

            

            try:
                enemy_connected_before_action = self.engine.get_connected_units(units, self.enemy_side)
                enemy_connected_after_action = self.engine.get_connected_units(temp, self.enemy_side)
                newly_cut_off = (base_enemy_connected & enemy_connected_before_action) - enemy_connected_after_action
                if newly_cut_off:
                    cut_off_value = 0.0
                    for target_id in newly_cut_off:
                        target_unit = next((u for u in enemy_units if u["id"] == target_id), None)
                        if target_unit:
                            target_val = self.unit_values.get(target_unit["type"].lower(), 20)
                            cut_off_value += target_val
                    mod += 8000.0 + cut_off_value * 200.0
            except Exception as e:
                pass

            try:
                before_connected = self.engine.get_connected_units(units, self.side)
                after_connected = self.engine.get_connected_units(temp, self.side)
                lost_ids = before_connected - after_connected
                if lost_ids:
                    cutoff_penalty = 0.0
                    for lost_id in lost_ids:
                        lost_unit = next((u for u in units if u["id"] == lost_id), None)
                        if lost_unit:
                            if "relay" in lost_unit.get("type", "").lower():
                                cutoff_penalty += 6000.0
                            else:
                                cutoff_penalty += 3500.0
                    mod -= cutoff_penalty
            except:
                pass

            lost = self.calculate_cohesion_loss(units, act_uid, action["x"], action["y"])
            if lost > 0:
                base_cohesion_factor = 200.0 if len(units) > 10 else 60.0
                history_here = self.position_history.get(act_uid, [])
                frozen_turns = 0
                if acting_unit and len(history_here) >= 3:
                    for pos in reversed(history_here[-6:]):
                        if pos == (acting_unit["x"], acting_unit["y"]):
                            frozen_turns += 1
                        else:
                            break
                stasis_divisor = max(0.1, 1.0 - (frozen_turns // 2) * 0.4)
                cohesion_factor = base_cohesion_factor * stasis_divisor
                mod -= (lost * cohesion_factor)

            goal = local_goals.get(act_uid, "STAY")

            if acting_unit:
                u_type = acting_unit.get("type", "").lower()

                if u_type == "relay":
                    if goal == "ESCAPE":
                        dist_enemy_before = min(
                            self.get_path_distance(acting_unit["x"], acting_unit["y"], (e["x"], e["y"])) for e in
                            enemy_units) if enemy_units else 99
                        dist_enemy_after = min(
                            self.get_path_distance(action["x"], action["y"], (e["x"], e["y"])) for e in
                            enemy_units) if enemy_units else 99
                        mod += (dist_enemy_after - dist_enemy_before) * 300.0

                        allies_adjacent = sum(1 for a in ai_units if "relay" not in a.get("type", "").lower() and max(
                            abs(action["x"] - a["x"]), abs(action["y"] - a["y"])) <= 1)
                        mod += allies_adjacent * 250.0
                    else:
                        try:
                            before_connected = self.engine.get_connected_units(units, self.side)
                            after_connected = self.engine.get_connected_units(temp, self.side)
                            newly_connected = after_connected - before_connected
                            newly_disconnected = before_connected - after_connected
                            for conn_uid in newly_connected:
                                conn_unit = next((u for u in units if u["id"] == conn_uid), None)
                                if conn_unit:
                                    # Reduced from 40k/30k — chain-building should not dominate everything
                                    mod += 15000.0 if "relay" in conn_unit.get("type", "").lower() else 10000.0
                            mod -= len(newly_disconnected) * 35000.0

                            was_connected = acting_unit["id"] in before_connected
                            is_connected_now = acting_unit["id"] in after_connected
                            if not was_connected and is_connected_now:
                                mod += 8000.0
                            elif not is_connected_now:
                                mod -= 100000.0
                        except:
                            pass

                        enemy_combat = [e for e in enemy_units if "relay" not in e.get("type", "").lower()]
                        if enemy_combat:
                            min_dist_enemy = min(
                                max(abs(action["x"] - e["x"]), abs(action["y"] - e["y"])) for e in enemy_combat)
                            if min_dist_enemy <= 1:
                                mod -= 5000.0
                            elif min_dist_enemy <= 3:
                                mod -= 1000.0

                else:
                    if goal == "RETREAT":
                        dist_enemy_before = min(
                            self.get_path_distance(acting_unit["x"], acting_unit["y"], (e["x"], e["y"])) for e in
                            enemy_units) if enemy_units else 99
                        dist_enemy_after = min(
                            self.get_path_distance(action["x"], action["y"], (e["x"], e["y"])) for e in
                            enemy_units) if enemy_units else 99
                        mod += (dist_enemy_after - dist_enemy_before) * 150.0

                        allies_adjacent = sum(1 for a in ai_units if
                                              max(abs(action["x"] - a["x"]), abs(action["y"] - a["y"])) <= 1 and a[
                                                  "id"] != act_uid)
                        mod += allies_adjacent * 100.0

                        if (action["x"], action["y"]) in self.engine.fortresses or (action["x"],
                                                                                    action["y"]) in self.engine.passes:
                            mod += 400.0

                        mod += (action["y"] - acting_unit["y"] if self.side == "South" else acting_unit["y"] - action[
                            "y"]) * 100.0

                    elif goal in ["ATTACK_RUN", "BLITZ_CHARGE"]:
                        if enemy_units:
                            target_p = self._get_lane_target(acting_unit, units)
                            dist_before = self.get_path_distance(acting_unit["x"], acting_unit["y"], target_p)
                            dist_after = self.get_path_distance(action["x"], action["y"], target_p)
                            mod += (dist_before - dist_after) * 200.0

                            # ── Fire Positioning Lookahead ──
                            # Check if moving to this tile sets up a direct attack vector on any enemy next turn
                            chosen_face = action.get("transform_to")
                            unit_stats_future = self.engine.get_stats(chosen_face if chosen_face else u_type)
                            future_range = unit_stats_future.get("range", 2)
                            
                            for e in enemy_units:
                                if self.engine.check_line_of_sight(action["x"], action["y"], e["x"], e["y"], future_range, temp):
                                    f_combat = self.engine.calculate_combat(temp, self.side, e["x"], e["y"], verbose=False)
                                    if f_combat.get("valid"):
                                        if f_combat["result"] in ["DESTROY", "RETREAT"]:
                                            mod += 45000.0   # Massive incentive to take attacking ground
                                        else:
                                            mod += f_combat["offense"] * 3000.0  # Stack build setup
                                            
                        if (action["x"], action["y"]) in self.engine.fortresses or (action["x"],
                                                                                    action["y"]) in self.engine.passes:
                            mod += 300.0

                    elif goal == "HOLD_FORMATION":
                        # ── ACTIVE tactical defense and positioning formation ──
                        if enemy_units:
                            # 1. Locate the nearest enemy target
                            closest_enemy = min(
                                enemy_units,
                                key=lambda e: max(abs(action["x"] - e["x"]), abs(action["y"] - e["y"]))
                            )
                            ex, ey = closest_enemy["x"], closest_enemy["y"]
                            dist_to_enemy = max(abs(action["x"] - ex), abs(action["y"] - ey))

                            # Maintain a solid defensive pressure distance (3-4 tiles away)
                            if dist_to_enemy in [3, 4]:
                                mod += 3000.0
                            elif dist_to_enemy < 3:
                                # Too close without an attack goal — retreat slightly or shield
                                mod -= 1000.0

                            # ── Fire Positioning Lookahead for HOLD_FORMATION ──
                            unit_stats_future = self.engine.get_stats(chosen_face if chosen_face else u_type)
                            future_range = unit_stats_future.get("range", 2)
                            
                            for e in enemy_units:
                                if self.engine.check_line_of_sight(action["x"], action["y"], e["x"], e["y"], future_range, temp):
                                    f_combat = self.engine.calculate_combat(temp, self.side, e["x"], e["y"], verbose=False)
                                    if f_combat.get("valid"):
                                        if f_combat["result"] in ["DESTROY", "RETREAT"]:
                                            mod += 45000.0
                                        else:
                                            mod += f_combat["offense"] * 3000.0

                            # 2. FLANKING SCORING: Align along the enemy's weak defensive vector
                            # Find which directions have the lowest defensive stack
                            enemy_directions = [
                                (0, 1), (0, -1), (1, 0), (-1, 0),
                                (1, 1), (1, -1), (-1, 1), (-1, -1)
                            ]
                            def_by_dir = {}
                            for dx, dy in enemy_directions:
                                def_by_dir[(dx, dy)] = self._extract_static_vector_defense(
                                    temp, closest_enemy, dx, dy
                                )
                            
                            min_def = min(def_by_dir.values()) if def_by_dir else 99
                            weak_directions = [d for d, v in def_by_dir.items() if v == min_def]

                            # Direction from our prospective tile to the enemy
                            dx_to_enemy = ex - action["x"]
                            dy_to_enemy = ey - action["y"]
                            # Normalize to unit step (-1, 0, or 1)
                            step_x = 1 if dx_to_enemy > 0 else (-1 if dx_to_enemy < 0 else 0)
                            step_y = 1 if dy_to_enemy > 0 else (-1 if dy_to_enemy < 0 else 0)

                            # If our approach vector points at their weak defensive side, give a flanking bonus
                            if (step_x, step_y) in weak_directions:
                                mod += 8000.0  # Flanking positioning incentive

                            # 3. SCREENING SCORING: Shielding high-value allies
                            # Shield and infantry units get bonuses for placing themselves adjacent to friendly relays/artillery
                            if u_type in ["shield", "infantry"]:
                                high_value_allies = [
                                    a for a in ai_units
                                    if a["id"] != act_uid and a.get("type", "").lower() in ["relay", "artillery"]
                                ]
                                for ally in high_value_allies:
                                    dist_to_ally = max(abs(action["x"] - ally["x"]), abs(action["y"] - ally["y"]))
                                    if dist_to_ally == 1:
                                        # Positioned as a protective barrier/screen
                                        mod += 12000.0

                            # 3b. RELAY INTERPOSITION: ANY combat piece blocking an enemy approach to a threatened relay
                            # The closer the enemy is to our relay, the bigger the bonus for interposing
                            if u_type not in ["relay"]:
                                threatened_relays = [
                                    r for r in ai_units
                                    if r.get("type", "").lower() == "relay" and r["id"] != act_uid
                                ]
                                for relay in threatened_relays:
                                    rx, ry = relay["x"], relay["y"]
                                    for enemy in enemy_units:
                                        ex2, ey2 = enemy["x"], enemy["y"]
                                        dist_enemy_relay = max(abs(ex2 - rx), abs(ey2 - ry))
                                        if dist_enemy_relay <= 4:
                                            # Is our action destination between the enemy and the relay?
                                            dist_us_relay_before = max(abs(acting_unit["x"] - rx), abs(acting_unit["y"] - ry))
                                            dist_us_relay_after  = max(abs(action["x"] - rx), abs(action["y"] - ry))
                                            dist_us_enemy_after  = max(abs(action["x"] - ex2), abs(action["y"] - ey2))
                                            if dist_us_relay_after < dist_us_relay_before and dist_us_enemy_after <= dist_enemy_relay:
                                                # We're moving closer to the relay AND between it and the enemy
                                                try:
                                                    # Scale bonus by how many of our units this relay supplies
                                                    connected = set(self.engine.get_connected_units(units, self.side))
                                                    dependents = len([u for u in units if u.get("side") == self.side
                                                                      and u["id"] in connected and u["id"] != relay["id"]])
                                                except:
                                                    dependents = 1
                                                urgency = (5 - dist_enemy_relay)  # 1–4, higher = more urgent
                                                mod += urgency * 3000.0 + dependents * 2000.0


                            # 4. CONVERGENCE SCORING: Forming stack-attack alliances
                            # Reward units for clustering together so they can project stack combat force
                            adjacent_allies = sum(
                                1 for a in ai_units
                                if a["id"] != act_uid and max(abs(action["x"] - a["x"]), abs(action["y"] - a["y"])) == 1
                            )
                            mod += adjacent_allies * 6000.0


                    elif goal == "TRAVEL":
                        if enemy_units:
                            travel_target = self._get_lane_target(acting_unit, units)
                            dist_before = self.get_path_distance(acting_unit["x"], acting_unit["y"], travel_target)
                            dist_after = self.get_path_distance(action["x"], action["y"], travel_target)
                            mod += (dist_before - dist_after) * 150.0

                    elif goal == "STAY":
                        dist_moved = max(abs(acting_unit["x"] - action["x"]), abs(acting_unit["y"] - action["y"]))
                        if dist_moved > 0: mod -= 200.0

            if acting_unit:
                dist_moved = max(abs(acting_unit["x"] - action["x"]), abs(acting_unit["y"] - action["y"]))
                if dist_moved <= 1: mod += 15.0

            # if action["action_type"] in ["move", "attack"]:
            #     max_enemy_counter_score = self._simulate_enemy_best_response(temp)
            #     enemy_advantage_delta = max_enemy_counter_score - baseline_score
            #     if enemy_advantage_delta > 5000.0:
            #         mod -= enemy_advantage_delta * 1.5

            if action["action_type"] in ["move", "attack"]:
                max_enemy_counter_score = self._simulate_enemy_best_response(temp)
                enemy_advantage_delta = max_enemy_counter_score - baseline_score
                counter_penalty = (enemy_advantage_delta - 5000.0) * 1.5 if enemy_advantage_delta > 5000.0 else 0.0

                if counter_penalty > 0 and z3_penalty_this_action > 0:
                    mod -= max(counter_penalty,
                               z3_penalty_this_action) - z3_penalty_this_action  # only add the excess, don't double-apply
                elif counter_penalty > 0:
                    mod -= counter_penalty

            # is_final_state = (action["action_type"] == "end_turn" or current_state.get("moves_left", 5) == 1)
            # my_breakdown = self.evaluate_board(temp, return_breakdown=True, base_enemy_connected=base_enemy_connected,
            #                                    is_end_turn=is_final_state)
            #
            # if my_breakdown["TOTAL"] + mod < best_score - 500.0:
            #     continue

            # 1. Count exactly how many of your own units are currently alive on the board
            current_alive_count = sum(1 for u in units if u.get("side") == self.side)

            # 2. Establish that as your dynamic maximum turn budget (minimum of 1)
            max_turn_capacity = max(1, current_alive_count)

            # 3. Determine if this action constitutes the final move of the turn loop
            is_final_state = (
                        action["action_type"] == "end_turn" or current_state.get("moves_left", max_turn_capacity) == 1)

            # 4. Proceed with your standard board evaluation breakdown
            my_breakdown = self.evaluate_board(temp, return_breakdown=True, base_enemy_connected=base_enemy_connected,
                                               is_end_turn=is_final_state)

            if my_breakdown["TOTAL"] + mod < best_score - 500.0:
                continue

            if self.defensive_weight > 0:
                enemy_score = self.enemy_evaluator.evaluate_board(temp, base_enemy_connected=base_my_connected,
                                                                  is_end_turn=is_final_state)
                score = (my_breakdown["TOTAL"] - self.defensive_weight * enemy_score) + mod
            else:
                score = my_breakdown["TOTAL"] + mod

            # ── PERMANENT ACTION TRACE LOGGING ──
            if act_uid:
                if act_uid not in diagnostic_log:
                    diagnostic_log[act_uid] = {"choices": []}
                
                # Fetch Z3 results from the cache if available
                cache_key = (act_uid, dest_x, dest_y, chosen_face)
                z3_ceiling, z3_exp_off, z3_p_lethal = 0.0, 0.0, 0.0
                if cache_key in verified_safety_cache:
                    z3_ceiling, z3_exp_off, z3_p_lethal = verified_safety_cache[cache_key]

                diagnostic_log[act_uid]["choices"].append({
                    "action": action,
                    "score": score,
                    "mod_applied": mod,
                    "breakdown": my_breakdown,
                    "z3_ceiling": z3_ceiling,
                    "z3_exp_off": z3_exp_off,
                    "z3_p_lethal": z3_p_lethal,
                    "z3_penalty": z3_penalty_this_action,
                    "counter_penalty": counter_penalty
                })

            if score > best_score:
                best_score = score
                best_action = action

        # ── Print the complete evaluation telemetry to stderr ──
        for uid, data in diagnostic_log.items():
            ref_unit = next((u for u in units if u["id"] == uid), None)
            if not ref_unit:
                continue
            
            print("\n" + "=" * 105, file=sys.stderr)
            print(f"📊 [AI TELEMETRY] Unit: {uid} ({ref_unit['type'].upper()}) at ({ref_unit['x']}, {ref_unit['y']})", file=sys.stderr)
            print("-" * 105, file=sys.stderr)
            print(
                f"{'PROPOSED TARGET':<18} | {'SCORE':<9} | {'ROLE':<8} | {'COHESION':<8} | {'THREATS':<8} | "
                f"{'CEILING':<7} | {'EXP_OFF':<7} | {'P_LETHAL':<8} | {'Z3_PEN':<7} | {'CTR_PEN':<7} | {'TOTAL_MOD':<9}",
                file=sys.stderr
            )
            print("-" * 105, file=sys.stderr)

            # Sort descending by score so best options are at the top
            sorted_choices = sorted(data["choices"], key=lambda c: c["score"], reverse=True)
            for choice in sorted_choices:
                act = choice["action"]
                bd = choice["breakdown"]
                tgt = f"{act['action_type'].upper()} -> ({act['x']}, {act['y']})" if act['action_type'] != 'end_turn' else "END_TURN"
                
                print(
                    f"{tgt:<18} | {choice['score']:<9.1f} | {bd['Role_Exec']:<8.1f} | {bd['Cohesion']:<8.1f} | {bd['Threat_Def']:<8.1f} | "
                    f"{choice['z3_ceiling']:<7.1f} | {choice['z3_exp_off']:<7.1f} | {choice['z3_p_lethal']:<8.2f} | "
                    f"{choice['z3_penalty']:<7.1f} | {choice['counter_penalty']:<7.1f} | {choice['mod_applied']:<9.1f}",
                    file=sys.stderr
                )
            print("=" * 105 + "\n", file=sys.stderr)


            # ─── REAL-TIME EXECUTION LIVE LOG INSERTION POINT ───
        if best_action and best_action.get("action_type") == "attack":
            # Run combat engine metrics one final time on the true, active board state
            final_combat = self.engine.calculate_combat(units, self.side, best_action["x"], best_action["y"])
            if final_combat.get("valid"):
                print(f"\n💥 [AI REAL-TIME COMBAT ENGAGEMENT]")
                print(f"   ├─ Attacking Unit ID: {best_action['unitId']}")
                print(f"   ├─ Target Coordinates: ({best_action['x']}, {best_action['y']})")
                print(f"   ├─ Engine Stated Offense: {final_combat['offense']}")
                print(f"   ├─ Engine Stated Defense: {final_combat['defense']}")
                print(f"   └─ Net Force Vector: {final_combat['net_force']} -> Result: {final_combat['result']}\n")
            # ────────────────────────────────────────────────────

        return best_action if best_action else {"action_type": "end_turn"}

