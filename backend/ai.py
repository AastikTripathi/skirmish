
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
            "relay": 95,
            "infantry": 20,
            "arsenal": 1000,
            "mine": 25,
            "shield": 35
        }
        self.macro_directives = {}
        self.macro_state = "STANDARD"
        self.target_arsenal_coords = None

        # --- NEW DIAGNOSTIC SYSTEM PROPERTIES ---
        self.position_history = position_history if position_history is not None else {}
        self.turn_counter = turn_counter
        self._distance_cache = {}  # {target_y: {(x, y): distance}}
        self.cluster_turn_cursor = 0
        self.orchestration_data = {}

    # def get_path_distance_to_goal(self, x, y, target_y):
    #     """Heuristic: Manhattan distance to the target baseline."""
    #     return abs(target_y - y)

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
        """Terrain-aware distance to the target baseline, via a precomputed
        static map (mountains never move, so this only needs to be built once
        per target row and reused for the rest of the match)."""
        if target_y not in self._distance_cache:
            self._distance_cache[target_y] = self._build_distance_map(target_y)
        return self._distance_cache[target_y].get((x, y), 30)

    def _build_point_distance_map(self, target_coords):
        """Builds a terrain-aware distance map starting from target_coords (tuple (x, y) or list/tuple of tuples)."""
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
        """Terrain-aware distance to target coordinate(s), via a cached distance map."""
        key = tuple(target_coords) if isinstance(target_coords, list) else target_coords
        if key not in self._distance_cache:
            self._distance_cache[key] = self._build_point_distance_map(target_coords)
        return self._distance_cache[key].get((x, y), 99)


    @property
    def enemy_evaluator(self):
        """Lazily constructs a WarGameAI from the enemy's POV for perspective scoring."""
        if self._enemy_evaluator is None:
            self._enemy_evaluator = WarGameAI(self.engine, side=self.enemy_side, turn_counter=self.turn_counter)
            self._enemy_evaluator.defensive_weight = 0.0
        return self._enemy_evaluator

    def _analyze_theater_clusters(self, units: list) -> dict:
        """Groups units into spatial battalions for macro situational tracking."""
        sides = {"North": [], "South": []}
        for u in units:
            sides[u.get("side")].append(u)

        clusters = {"North": [], "South": []}
        for side in ["North", "South"]:
            unvisited = list(sides[side])
            while unvisited:
                current = unvisited.pop(0)
                cluster = [current]
                added = True
                while added:
                    added = False
                    to_remove = []
                    for cand in unvisited:
                        if any(max(abs(cand["x"] - c["x"]), abs(cand["y"] - c["y"])) <= 3 for c in cluster):
                            cluster.append(cand)
                            to_remove.append(cand)
                            added = True
                    # for r in to_remove:
                    #     unvisited.remove(r)
                    unvisited = [cand for cand in unvisited if cand not in to_remove]

                total_strength = sum(self.unit_values.get(u.get("type", "").lower(), 20) for u in cluster)
                cx = sum(u["x"] for u in cluster) / len(cluster)
                cy = sum(u["y"] for u in cluster) / len(cluster)

                clusters[side].append({
                    "units": cluster,
                    "strength": total_strength,
                    "center": (cx, cy)
                })
        return clusters

    def _orchestrate_tactics(self, units: list, ai_connected: set, enemy_connected: set):
        """
        GLOBAL TACTICAL ORCHESTRATOR (The Director/Coach)
        Performs strategic analysis of the board, computes team mentality,
        and partitions friendly combat forces into roles (ATTACKER, DEFENDER, REINFORCEMENT).
        """
        self.orchestration_data.clear()
        self.macro_directives.clear()
        self.target_arsenal_coords = None

        ai_units = [u for u in units if u.get("side") == self.side]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]

        # 1. Cluster Analysis
        theater = self._analyze_theater_clusters(units)
        enemy_clusters = theater[self.enemy_side]

        # 2. Identify the target coordinates (weakest cluster or cutoff instigator)
        weakest_cluster = None
        disconnected_friendly = [u for u in ai_units if u["id"] not in ai_connected]
        cutoff_instigator = None
        if disconnected_friendly and enemy_units:
            min_dist = float('inf')
            for df in disconnected_friendly:
                for e in enemy_units:
                    if "relay" in e.get("type", "").lower():
                        continue
                    dist = self.get_path_distance(e["x"], e["y"], (df["x"], df["y"]))
                    if dist < min_dist:
                        min_dist = dist
                        cutoff_instigator = e

        if cutoff_instigator:
            target_coords = (cutoff_instigator["x"], cutoff_instigator["y"])
        else:
            weakest_cluster = None
            min_weakness_val = float('inf')

            ai_combat_units = [u for u in ai_units if "relay" not in u.get("type", "").lower()]
            if ai_combat_units:
                our_cx = sum(u["x"] for u in ai_combat_units) / len(ai_combat_units)
                our_cy = sum(u["y"] for u in ai_combat_units) / len(ai_combat_units)
            else:
                our_cx, our_cy = 12.0, 10.0

            for ec in enemy_clusters:
                ec_units = ec["units"]
                ec_combat = [u for u in ec_units if "relay" not in u.get("type", "").lower()]
                if not ec_combat and len(enemy_units) > len(ec_units):
                    continue
                cx, cy = ec["center"]
                dist_to_us = self.get_path_distance(int(cx), int(cy), (int(our_cx), int(our_cy)))
                weakness_val = ec["strength"] + (dist_to_us * 15.0)
                if weakest_cluster is None or weakness_val < min_weakness_val:
                    min_weakness_val = weakness_val
                    weakest_cluster = ec

            if not weakest_cluster and enemy_clusters:
                weakest_cluster = enemy_clusters[0]

            target_coords = weakest_cluster["center"] if weakest_cluster else (12, 10)
            target_coords = (int(target_coords[0]), int(target_coords[1]))

        # 3. Prized Possession Threat Assessment
        my_arsenals = self.engine.arsenals[self.side]
        max_arsenal_threat = 0.0
        threatened_arsenals = []
        for ax, ay in my_arsenals:
            enemy_combat = [e for e in enemy_units if "relay" not in e.get("type", "").lower()]
            if enemy_combat:
                closest_enemy_dist = min(self.get_path_distance(e["x"], e["y"], (ax, ay)) for e in enemy_combat)
                if closest_enemy_dist <= 7:
                    threat_severity = 8 - closest_enemy_dist
                    max_arsenal_threat = max(max_arsenal_threat, threat_severity)
                    threatened_arsenals.append((ax, ay))

        my_relays = [u for u in ai_units if "relay" in u.get("type", "").lower()]
        threatened_relays = []
        for relay in my_relays:
            rx, ry = relay["x"], relay["y"]
            enemy_combat = [e for e in enemy_units if "relay" not in e.get("type", "").lower()]
            if enemy_combat:
                closest_enemy_dist = min(self.get_path_distance(e["x"], e["y"], (rx, ry)) for e in enemy_combat)
                if closest_enemy_dist <= 5:
                    threatened_relays.append(relay["id"])

        # 4. Determine Team Mentality
        ai_strength = sum(self.unit_values.get(u.get("type", "").lower(), 20) for u in ai_units if "relay" not in u.get("type", "").lower())
        enemy_strength = sum(self.unit_values.get(u.get("type", "").lower(), 20) for u in enemy_units if "relay" not in u.get("type", "").lower())

        if max_arsenal_threat >= 2.0 or ai_strength < enemy_strength * 0.7:
            mentality = "DEFENSIVE"
            self.macro_state = "DESPERATION_CHOKE"
        elif max_arsenal_threat == 0.0 and (ai_strength > enemy_strength * 1.2 or enemy_strength <= 100):
            mentality = "ATTACKING"
            self.macro_state = "ANNIHILATION_HUNT"
        else:
            mentality = "BALANCED"
            self.macro_state = "STANDARD"

        # Track targets for compatibility
        uncaptured_enemy_arsenals = []
        for ax, ay in self.engine.arsenals[self.enemy_side]:
            is_captured = any(u["x"] == ax and u["y"] == ay and u["side"] == self.side for u in units)
            if not is_captured:
                uncaptured_enemy_arsenals.append((ax, ay))
        if uncaptured_enemy_arsenals:
            self.target_arsenal_coords = uncaptured_enemy_arsenals[0]

        # 5. Squad Partitioning (Tactical Roles)
        enemy_arsenals = self.engine.arsenals[self.enemy_side]
        combat_units = [u for u in ai_units if "relay" not in u.get("type", "").lower()]
        
        roles = {}
        regular_combat_units = []
        
        # Explicit exception: any combat unit occupying an enemy arsenal becomes an ARSENAL_GUARD
        # and is excluded from regular squad/role overrides
        for u in combat_units:
            if (u["x"], u["y"]) in enemy_arsenals:
                roles[u["id"]] = "ARSENAL_GUARD"
                self.macro_directives[u["id"]] = "GUARD"
            else:
                regular_combat_units.append(u)

        home_coords = list(my_arsenals) if my_arsenals else [(12, 19 if self.side == "South" else 0)]
        regular_combat_units.sort(key=lambda u: min(self.get_path_distance(u["x"], u["y"], hc) for hc in home_coords))

        n_combat = len(regular_combat_units)

        if mentality == "DEFENSIVE":
            n_defenders = int(n_combat * 0.6)
        elif mentality == "ATTACKING":
            n_defenders = max(1, int(n_combat * 0.15))
        else:
            n_defenders = int(n_combat * 0.3)

        defenders = regular_combat_units[:n_defenders]
        attackers_and_others = regular_combat_units[n_defenders:]

        for u in defenders:
            roles[u["id"]] = "DEFENDER"
            self.macro_directives[u["id"]] = "SHIELD_WALL"

        for u in attackers_and_others:
            dist_to_target = self.get_path_distance(u["x"], u["y"], target_coords)
            if dist_to_target > 6:
                roles[u["id"]] = "REINFORCEMENT"
                self.macro_directives[u["id"]] = "STANDARD_MARCH"
            else:
                roles[u["id"]] = "ATTACKER"
                self.macro_directives[u["id"]] = "HUNTER_SEEKER" if mentality == "ATTACKING" else "STANDARD_MARCH"

        for relay in my_relays:
            roles[relay["id"]] = "RELAY_SUPPORT"
            self.macro_directives[relay["id"]] = "DYNAMIC_LINK"

        self.orchestration_data = {
            "mentality": mentality,
            "target_coords": target_coords,
            "roles": roles,
            "weakest_cluster": weakest_cluster,
            "threatened_arsenals": threatened_arsenals,
            "threatened_relays": threatened_relays,
            "max_arsenal_threat": max_arsenal_threat
        }

    def detect_threats(self, units: list) -> float:
        """Tracks direct proximity risks to back-line assets."""
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
            connected_now = self.engine.get_connected_now(units, self.side) if hasattr(self.engine, 'get_connected_now') else self.engine.get_connected_units(units, self.side)
            for relay in friendly_relays:
                if relay["id"] not in connected_now:
                    threat_score -= 900.0

        # Combat units danger detection: penalize combat units that are within line-of-sight & range of active enemy attackers
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
                if self.engine.check_line_of_sight(enemy["x"], enemy["y"], ally["x"], ally["y"], enemy_stats["range"], units):
                    ally_in_danger = True
                    break
            if ally_in_danger:
                ally_type = ally.get("type", "").lower()
                val = self.unit_values.get(ally_type, 20)
                threat_score -= val * 8.0  # E.g. -160 for infantry, -440 for cavalry, -320 for artillery

        # Relay downstream deactivation check
        try:
            connected_now_set = set(connected_now)
        except Exception:
            connected_now_set = set()

        for relay in friendly_relays:
            relay_in_danger = False
            for enemy in enemy_units:
                if enemy["id"] not in enemy_connected:
                    continue
                enemy_stats = self.engine.get_stats(enemy["type"])
                if self.engine.check_line_of_sight(enemy["x"], enemy["y"], relay["x"], relay["y"], enemy_stats["range"], units):
                    relay_in_danger = True
                    break

            if relay_in_danger:
                units_without_relay = [u for u in units if u["id"] != relay["id"]]
                try:
                    connected_without_relay = set(self.engine.get_connected_units(units_without_relay, self.side))
                    downstream_count = len(connected_now_set) - len(connected_without_relay) - 1
                    if downstream_count > 0:
                        # Heavy penalty per downstream unit threatened with deactivation
                        threat_score -= downstream_count * 1000.0
                except Exception:
                    pass

        return threat_score

    def _assess_local_threats(self, units, ai_connected):
        """Estimates how exposed each friendly unit is to enemy attack next turn:
        sums enemy offense within move+range reach and compares to the unit's
        effective defense (fortress/pass/support-adjusted). Positive = unit is
        likely to lose a fight if attacked as-is; negative = unit can hold."""
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
        LOCAL GOAL DECIDER (The Player Mind)
        Determines the local dynamic goal (e.g. RETREAT, ATTACK, DEFEND, TRAVEL, STAY)
        for each friendly unit based on its local threat profile and global partition role.
        """
        goals = {}
        ai_units = [u for u in units if u.get("side") == self.side]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]

        # Re-use existing local threat assessment
        local_threats = self._assess_local_threats(units, ai_connected)

        roles = self.orchestration_data.get("roles", {})
        target_coords = self.orchestration_data.get("target_coords", (12, 10))

        for unit in ai_units:
            uid = unit["id"]
            u_type = unit.get("type", "").lower()
            ux, uy = unit["x"], unit["y"]
            role = roles.get(uid, "ATTACKER")
            threat = local_threats.get(uid, 0.0)

            # Relays are handled differently
            if u_type == "relay":
                if threat > 0.0:
                    goals[uid] = "ESCAPE"
                else:
                    goals[uid] = "SUPPORT_NET"
                continue

            # Combat units
            # 1. RETREAT check: if threat is high and we are likely to be destroyed, run!
            if threat > 5.0:
                goals[uid] = "RETREAT"
                continue

            # 2. Direct ATTACK check: can we hit any enemy directly from here?
            stats = self.engine.get_stats(unit["type"])
            has_los_target = False
            for target in enemy_units:
                if self.engine.check_line_of_sight(ux, uy, target["x"], target["y"], stats["range"], units):
                    combat = self.engine.calculate_combat(units, self.side, target["x"], target["y"])
                    if combat.get("valid") and combat["result"] in ["DESTROY", "RETREAT"]:
                        has_los_target = True
                        break

            if has_los_target:
                goals[uid] = "ATTACK"
                continue

            # 3. Role-based fallback
            if role == "DEFENDER":
                goals[uid] = "DEFEND"
            elif role == "ATTACKER":
                goals[uid] = "ATTACK_RUN"
            elif role == "REINFORCEMENT":
                goals[uid] = "TRAVEL"
            else:
                goals[uid] = "STAY"

        return goals

    def _cluster_own_units(self, units):
        """Groups this side's units into spatially local factions so move
        comparisons happen within a faction, not across the whole army."""
        own = [u for u in units if u.get("side") == self.side]
        unvisited = list(own)
        cluster_map = {}
        cid = 0
        while unvisited:
            current = unvisited.pop(0)
            cluster = [current]
            added = True
            while added:
                added = False
                remaining = []
                for cand in unvisited:
                    if any(abs(cand["x"] - c["x"]) + abs(cand["y"] - c["y"]) <= 3 for c in cluster):
                        cluster.append(cand)
                        added = True
                    else:
                        remaining.append(cand)
                unvisited = remaining
            for u in cluster:
                cluster_map[u["id"]] = cid
            cid += 1
        return cluster_map

    def evaluate_board(self, units: list, return_breakdown: bool = False,
                       base_enemy_connected: set = None, is_end_turn: bool = True) -> dict or float:
        base_material = 0.0
        territory_score = 0.0
        role_score = 0.0
        cohesion_score = 0.0
        stacked_attack_pressure = 0.0

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
                base_material += base_val
                if is_connected:
                    connected_count += 1
                    connected_y_positions.append(uy)
                else:
                    cohesion_score -= 15.0
            else:
                base_material -= base_val
                if base_enemy_connected is not None:
                    if (u_id in base_enemy_connected) and not is_connected:
                        territory_score += 200.0
                elif not is_connected:
                    territory_score += 60.0

        territory_score += connected_count * 35.0

        min_global_distance = 99
        for enemy in enemy_units:
            ex, ey = enemy.get("x", 0), enemy.get("y", 0)
            for ally in ai_units:
                ax, ay = ally.get("x", 0), ally.get("y", 0)
                dist = max(abs(ex - ax), abs(ey - ay))
                if dist < min_global_distance:
                    min_global_distance = dist

        is_engagement_phase = min_global_distance <= 6
        if is_engagement_phase:
            for enemy in enemy_units:
                ex, ey = enemy.get("x", 0), enemy.get("y", 0)
                converging_friendly_count = 0
                for ally in ai_units:
                    ax, ay = ally.get("x", 0), ally.get("y", 0)
                    reach = 4 if ally.get("type", "").lower() in ["cavalry", "artillery"] else 3
                    if max(abs(ex - ax), abs(ey - ay)) <= reach:
                        converging_friendly_count += 1
                if converging_friendly_count == 1:
                    stacked_attack_pressure += 100.0
                elif converging_friendly_count == 2:
                    stacked_attack_pressure += 1500.0
                elif converging_friendly_count >= 3:
                    stacked_attack_pressure += 5000.0

        all_enemy_positions = [(e.get("x", 0), e.get("y", 0)) for e in enemy_units]

        local_threats = self._assess_local_threats(units, ai_connected)
        threatened_units = {uid: val for uid, val in local_threats.items() if val > 0}

        captured_enemy_arsenals = []
        uncaptured_enemy_arsenals = []
        for ax, ay in self.engine.arsenals[self.enemy_side]:
            if any(u["x"] == ax and u["y"] == ay and u["side"] == self.side for u in units):
                captured_enemy_arsenals.append((ax, ay))
            else:
                uncaptured_enemy_arsenals.append((ax, ay))

        for unit in ai_units:
            u_id = unit.get("id")
            u_type = unit.get("type", "").lower()
            ux, uy = unit.get("x", 0), unit.get("y", 0)
            is_connected = u_id in ai_connected
            directive = self.macro_directives.get(u_id, "STANDARD_MARCH")

            # --- REINFORCEMENT: reward standing adjacent to a threatened ally ---
            if threatened_units:
                for t_id, severity in threatened_units.items():
                    if t_id == u_id:
                        continue
                    ally = next((a for a in ai_units if a["id"] == t_id), None)
                    if ally and max(abs(ux - ally["x"]), abs(uy - ally["y"])) == 1:
                        role_score += min(severity, 15) * 25.0

            # --- SELF-PRESERVATION: if this unit itself is exposed, favor
            # positions that add friendly support rather than isolation ---
            if u_id in threatened_units:
                nearby_allies = sum(1 for a in ai_units if a["id"] != u_id and
                                    max(abs(ux - a["x"]), abs(uy - a["y"])) <= 1)
                role_score += nearby_allies * 60.0
                role_score -= min(threatened_units[u_id], 20) * 20.0

            if u_type == "relay":
                combat_allies = [a for a in ai_units if "relay" not in a.get("type", "").lower()]
                if combat_allies:
                    avg_ax = sum(a["x"] for a in combat_allies) / len(combat_allies)
                    avg_ay = sum(a["y"] for a in combat_allies) / len(combat_allies)
                    role_score += (45 - max(abs(ux - avg_ax), abs(uy - avg_ay))) * 160.0

                all_enemy_arsenals = self.engine.arsenals[self.enemy_side]
                if all_enemy_arsenals:
                    min_dist_a = min(max(abs(ux - ax), abs(uy - ay)) for ax, ay in all_enemy_arsenals)
                    role_score += (45 - min_dist_a) * 90.0
                elif all_enemy_positions:
                    min_dist_e = min(max(abs(ux - ex), abs(uy - ey)) for ex, ey in all_enemy_positions)
                    role_score += (45 - min_dist_e) * 90.0

                if is_connected:
                    role_score += 2000.0
                else:
                    role_score -= 80000.0
                continue

            all_enemy_arsenals = self.engine.arsenals[self.enemy_side]
            if all_enemy_arsenals:
                min_dist_to_arsenal = min(max(abs(ux - ax), abs(uy - ay)) for ax, ay in all_enemy_arsenals)
                role_score += (45 - min_dist_to_arsenal) * 250.0

            for ax, ay in captured_enemy_arsenals:
                if ux == ax and uy == ay:
                    has_nearby_threat = any(max(abs(ex - ax), abs(ey - ay)) <= 5 for ex, ey in all_enemy_positions)
                    if has_nearby_threat:
                        role_score += 7000.0  # Massive priority to hold captured enemy arsenals under threat
                    else:
                        role_score += 5000.0  # Keep occupying captured enemy arsenals to maintain supply line extension

            if enemy_units:
                dists = []
                for enemy in enemy_units:
                    ex, ey = enemy.get("x", 0), enemy.get("y", 0)
                    e_id = enemy.get("id")
                    is_deactivated = e_id not in enemy_connected
                    dist_to_enemy = max(abs(ux - ex), abs(uy - ey))
                    dists.append((dist_to_enemy, is_deactivated))

                min_dist, is_deactivated = min(dists, key=lambda x: x[0])
                if is_deactivated:
                    role_score += (45 - min_dist) * 350.0
                else:
                    role_score += (45 - min_dist) * 150.0

                # Support contact bonus: give additional points if next to any enemy (facilitates engagement)
                for dist_to_enemy, _ in dists:
                    if dist_to_enemy == 1:
                        role_score += 800.0

            if self.macro_state == "DESPERATION_CHOKE" and self.target_arsenal_coords:
                dist_to_target = max(abs(ux - self.target_arsenal_coords[0]), abs(uy - self.target_arsenal_coords[1]))
                role_score += (45 - dist_to_target) * 400.0

            if directive == "SHIELD_WALL":
                neighbor_allies = sum(1 for a in ai_units if max(abs(ux - a["x"]), abs(uy - a["y"])) == 1)
                role_score += neighbor_allies * 120.0

            dist_to_goal = self.get_path_distance_to_goal(ux, uy, target_y)
            role_score += (20 - dist_to_goal) * 10.0
            if is_connected:
                role_score += 1000.0
            else:
                role_score -= 60000.0

            # Formation / Cohesion stacking bonus: reward combat units that stand adjacent to other friendly combat units
            if "relay" not in u_type:
                has_adjacent_ally = any(
                    a["id"] != u_id and 
                    "relay" not in a.get("type", "").lower() and 
                    max(abs(ux - a["x"]), abs(uy - a["y"])) == 1 
                    for a in ai_units
                )
                if has_adjacent_ally:
                    role_score += 40.0

        if connected_y_positions and self.macro_state == "STANDARD":
            avg_y = sum(connected_y_positions) / len(connected_y_positions)
            cohesion_score += abs(home_y - avg_y) * 45.0

        if self.macro_state == "ANNIHILATION_HUNT":
            cohesion_score *= 0.1

        threat_score = self.detect_threats(
            units) if self._enemy_evaluator is not None or self.defensive_weight > 0 else 0.0

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

    # --- NEW ANOMALY DETECTION ENGINE ENGINE ---
    def _detect_behavioral_anomaly(self, uid: int) -> str or None:
        """Analyzes spatial updates over turns to isolate loops and deadlocks."""
        history = self.position_history.get(uid, [])
        if len(history) < 4:
            return None

        # 1. Stasis Detection (Unit has stood completely still over 3 full engine turns)
        if len(set(history[-3:])) == 1:
            return "STASIS_FREEZE"

        # 2. 2-Step Oscillation Check (A -> B -> A -> B)
        if history[-4] == history[-2] and history[-3] == history[-1] and history[-4] != history[-3]:
            return "2_STEP_OSCILLATION"

        # 3. 3-Step Oscillation Check (A -> B -> C -> A -> B -> C)
        if len(history) >= 6:
            if history[-6] == history[-3] and history[-5] == history[-2] and history[-4] == history[-1]:
                return "3_STEP_OSCILLATION"

        return None

    def _get_loc_cells(self, units: list) -> set:
        """Set of (x,y) cells on this side's active LoC network."""
        raw = self.engine.compute_lines_of_communication(units, self.side)
        return {(c[0], c[1]) for c in raw}

    def _compute_relay_expansion(self, units: list, relay_id: str, tx: int, ty: int) -> int:
        """
        Net new LoC cells gained by moving relay to (tx, ty).
        Positive = relay move opens new territory for combat units.
        Negative = relay move shrinks coverage (penalise this).
        """
        before = len(self.engine.compute_lines_of_communication(units, self.side))
        ghost = copy.deepcopy(units)
        for u in ghost:
            if u["id"] == relay_id:
                u["x"], u["y"] = tx, ty
                break
        after = len(self.engine.compute_lines_of_communication(ghost, self.side))
        return after - before

    def _get_lane_target(self, unit: dict, units: list) -> tuple:
        """
        Assigns each combat unit a lane-specific target cell.
        Board is divided into three lanes by x-coordinate:
          Left  : x <= 8   targets enemies/arsenals in the left corridor
          Center: 9-15     targets the centre mass
          Right : x >= 16  targets enemies/arsenals in the right corridor
        Falls back to the global closest enemy if the lane is empty.
        """
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
            # No enemies left — head for enemy arsenal
            arsenals = self.engine.arsenals[self.enemy_side]
            return min(arsenals, key=lambda a: abs(a[0] - ux) + abs(a[1] - unit["y"]))

        return min(
            [(e["x"], e["y"]) for e in lane_enemies],
            key=lambda p: abs(p[0] - ux) + abs(p[1] - unit["y"])
        )

    def get_all_legal_moves(self, units: list, moved_this_turn: list) -> list:
        legal_actions = []
        ai_units = [u for u in units if u.get("side") == self.side]
        connected_unit_ids = self.engine.get_connected_units(units, self.side)

        for unit in ai_units:
            if unit["id"] not in connected_unit_ids:
                continue
            if unit["id"] in moved_this_turn:
                continue

            unit_type = unit.get("type", "").lower()
            is_relay = "relay" in unit_type

            # Attack actions — only valid if this unit has direct line of sight and range to target
            unit_stats = self.engine.get_stats(unit["type"])
            for target in units:
                if target.get("side") == self.enemy_side:
                    if self.engine.check_line_of_sight(unit["x"], unit["y"], target["x"], target["y"], unit_stats["range"], units):
                        combat = self.engine.calculate_combat(units, self.side, target["x"], target["y"])
                        if combat.get("valid"):
                            legal_actions.append(
                                {"action_type": "attack", "unitId": unit["id"],
                                 "x": target["x"], "y": target["y"]})

            # Move actions
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    tx, ty = unit["x"] + dx, unit["y"] + dy
                    if 0 <= tx < 25 and 0 <= ty < 20:
                        is_valid, _ = self.engine.validate_move(units, unit["id"], tx, ty, moved_this_turn)
                        if is_valid:
                            if is_relay:
                                # Relays shape the LoC — they are unrestricted so they
                                # can push forward and open new territory.
                                legal_actions.append(
                                    {"action_type": "move", "unitId": unit["id"], "x": tx, "y": ty})
                            else:
                                # Combat units: allow any move that does NOT
                                # disconnect a currently-connected friendly unit.
                                # Frontier units can step forward (no one behind
                                # them loses connection). Units in the middle can
                                # still move sideways if cohesion is preserved.
                                # Disconnecting moves get a heavy penalty in
                                # scoring but are no longer silently dropped.
                                # Allow disconnecting moves to be evaluated; select_best_action applies cohesion/disconnection penalties dynamically
                                legal_actions.append(
                                    {"action_type": "move", "unitId": unit["id"], "x": tx, "y": ty})
        return legal_actions

    def calculate_cohesion_loss(self, units, unit_id, target_x, target_y):
        ghost = copy.deepcopy(units)
        u = next((unit for unit in ghost if unit['id'] == unit_id), None)
        if not u: return 0
        u['x'], u['y'] = target_x, target_y
        before = self.engine.get_connected_units(units, self.side)
        after = self.engine.get_connected_units(ghost, self.side)
        return len(before - after)

    def select_best_action(self, current_state: dict, allowed_clusters: set = None) -> dict:
        units = current_state["units"]
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

        # --- UPDATE TEMPORAL TRACKER KEYS (Once per turn) ---
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

        # Run the Global Tactical Orchestrator
        self._orchestrate_tactics(units, base_my_connected, base_enemy_connected)
        # Get dynamic local goals
        local_goals = self._decide_local_goals(units, base_my_connected)

        current_my_score = self.evaluate_board(units, base_enemy_connected=base_enemy_connected)
        if self.defensive_weight > 0:
            current_enemy_score = self.enemy_evaluator.evaluate_board(units, base_enemy_connected=base_my_connected)
            baseline_score = current_my_score - self.defensive_weight * current_enemy_score
        else:
            baseline_score = current_my_score

        # Initialize best_score to baseline_score minus a tolerance threshold (2000.0).
        # This allows the AI to make progress moves that have minor negative modifiers (e.g. cohesion loss,
        # leaving a defend post), while still preventing suicidal or catastrophic actions.
        best_score = baseline_score - 2000.0
        best_action = {"action_type": "end_turn"}

        actions = self.get_all_legal_moves(units, moved_this_turn)
        if not actions:
            return {"action_type": "end_turn"}

        # Separate move actions and attack actions
        move_actions = [a for a in actions if a["action_type"] == "move"]
        attack_actions = [a for a in actions if a["action_type"] == "attack"]

        # Group move actions by cluster
        unit_to_cluster = self._cluster_own_units(units)
        moves_by_cluster = {}
        for action in move_actions:
            cid = unit_to_cluster.get(action["unitId"], -1)
            if allowed_clusters is None or cid in allowed_clusters:
                moves_by_cluster.setdefault(cid, []).append(action)

        cluster_ids = sorted(moves_by_cluster.keys())
        chosen_cluster = None
        if cluster_ids:
            start = self.cluster_turn_cursor % len(cluster_ids)
            ordered_clusters = cluster_ids[start:] + cluster_ids[:start]
            chosen_cluster = ordered_clusters[0]
            candidate_actions = list(moves_by_cluster[chosen_cluster])
            self.cluster_turn_cursor = (self.cluster_turn_cursor + 1) % len(cluster_ids)
        else:
            candidate_actions = []

        # Merge ALL attacks globally into the candidate actions pool
        candidate_actions.extend(attack_actions)

        if not candidate_actions:
            return {"action_type": "end_turn"}

        diagnostic_log = {}
        actions = candidate_actions

        ai_units = [u for u in units if u.get("side") == self.side]
        enemy_units = [u for u in units if u.get("side") == self.enemy_side]

        for action in actions:
            temp = copy.deepcopy(units)
            mod = 0.0
            act_uid = action.get("unitId")

            if act_uid and action["action_type"] == "move":
                # Immediate oscillation check: moving back to any of the last 3 positions is heavily penalized
                history = self.position_history.get(act_uid, [])
                if len(history) >= 2:
                    recent_history = history[-3:]
                    if (action["x"], action["y"]) in recent_history:
                        mod -= 180000.0  # Devastating penalty for immediate loop oscillation

                has_stuck_unit = any(self._detect_behavioral_anomaly(u["id"]) is not None for u in ai_units)
                if has_stuck_unit:
                    acting_anomaly = self._detect_behavioral_anomaly(act_uid)
                    if not acting_anomaly:
                        mod += 15000.0

            acting_unit = next((u for u in units if u["id"] == act_uid), None)
            if not acting_unit and action["action_type"] != "end_turn":
                continue

            # Arsenal defense and cut-off pursuit logic
            if acting_unit and "relay" not in acting_unit.get("type", "").lower():
                our_arsenals = self.engine.arsenals[self.side]
                threatening_enemies = []
                for e in enemy_units:
                    for ax, ay in our_arsenals:
                        if max(abs(e["x"] - ax), abs(e["y"] - ay)) <= 6:
                            threatening_enemies.append(e)
                            break

                if threatening_enemies:
                    # Find closest friendly combat units to the threats to partition response
                    combat_units = [u for u in ai_units if "relay" not in u.get("type", "").lower()]
                    defenders_assigned = set()
                    for e in threatening_enemies:
                        if combat_units:
                            closest_u = min(combat_units, key=lambda cu: max(abs(cu["x"] - e["x"]), abs(cu["y"] - e["y"])))
                            defenders_assigned.add(closest_u["id"])

                    if acting_unit["id"] in defenders_assigned:
                        if action["action_type"] == "attack":
                            # If the attack is targeting one of these threatening enemies, reward it massively
                            if any(e["x"] == action["x"] and e["y"] == action["y"] for e in threatening_enemies):
                                mod += 150000.0  # Clear Arsenal Threat Kill Order!
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
                                min_dist_before = min(max(abs(acting_unit["x"] - e["x"]), abs(acting_unit["y"] - e["y"])) for e in threatening_enemies)
                                min_dist_after = min(max(abs(action["x"] - e["x"]), abs(action["y"] - e["y"])) for e in threatening_enemies)
                                if min_dist_after < min_dist_before:
                                    mod += 40000.0  # Reward moving to intercept threat
                                elif min_dist_after > min_dist_before:
                                    mod -= 20000.0  # Penalize moving away from arsenal threat

            if action["action_type"] == "attack":
                if attack_executed: continue
                combat = self.engine.calculate_combat(temp, self.side, action["x"], action["y"])
                if combat.get("valid"):
                    # Find if target unit is cut off
                    target_unit = next((u for u in temp if u["x"] == action["x"] and u["y"] == action["y"]), None)
                    is_target_cutoff = False
                    if target_unit:
                        target_connected = target_unit["id"] in self.engine.get_connected_units(temp, self.enemy_side)
                        is_target_cutoff = not target_connected
                    if combat["result"] == "DESTROY":
                        # Shoot to kill: large destroy bonus
                        mod += 15000.0 + combat["net_force"] * 100.0
                        if is_target_cutoff:
                            mod += 80000.0  # Massive priority to eliminate cut-off units!
                        if target_unit and "relay" in target_unit.get("type", "").lower():
                            mod += 150000.0  # Chess Queen priority bonus to destroy enemy Relays!
                        temp = [u for u in temp if not (u["x"] == action["x"] and u["y"] == action["y"])]
                    elif combat["result"] == "RETREAT":
                        mod += 3000.0 + combat["net_force"] * 100.0
                        if is_target_cutoff:
                            mod += 40000.0  # Moderate priority to push cut-off units back!
                        if target_unit and "relay" in target_unit.get("type", "").lower():
                            mod += 75000.0  # Moderate priority to push relays back!
                    else:
                        # Wasting an attack on a failed combat is heavily penalized
                        mod -= 100000.0

            elif action["action_type"] == "move":
                # Penalize abandoning a captured enemy arsenal unless another friendly unit is guarding it
                enemy_arsenals = self.engine.arsenals[self.enemy_side]
                was_on_arsenal = acting_unit and (acting_unit["x"], acting_unit["y"]) in enemy_arsenals
                if was_on_arsenal:
                    ax, ay = acting_unit["x"], acting_unit["y"]
                    other_occupant = any(u["id"] != act_uid and u["x"] == ax and u["y"] == ay and u["side"] == self.side for u in units)
                    if not other_occupant and (action["x"], action["y"]) != (ax, ay):
                        mod -= 40000.0  # Massive penalty for leaving an occupied enemy arsenal unprotected!

                if (action["x"], action["y"]) in enemy_arsenals:
                    mod += 15000.0  # Huge bonus to capture/occupy an enemy arsenal!

                # 1. Simulate mine detonation
                landed_on_mine = any(m["x"] == action["x"] and m["y"] == action["y"] for m in current_state.get("mines", []))
                if landed_on_mine:
                    temp = [unit for unit in temp if unit["id"] != act_uid]
                else:
                    # 2. Simulate standard movement & 3D face rotation
                    for u in temp:
                        if u.get("id") == act_uid:
                            dx = action["x"] - u["x"]
                            dy = action["y"] - u["y"]
                            u["x"], u["y"] = action["x"], action["y"]
                            if u["type"].lower() != "cavalry":
                                from server import rotate_cube_faces
                                faces = u.get("faces", {"top": u["symbol"], "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "A"})
                                new_faces = rotate_cube_faces(faces, dx, dy)
                                u["faces"] = new_faces
                                top_sym = new_faces["top"]
                                u["symbol"] = top_sym
                                if top_sym == "I": u["type"] = "infantry"
                                elif top_sym == "A": u["type"] = "artillery"
                                elif top_sym == "C": u["type"] = "cavalry"
                                elif top_sym == "R": u["type"] = "relay"
                                elif top_sym == "M": u["type"] = "mine"
                                elif top_sym == "S": u["type"] = "shield"
                            break

                    # 3. Simulate optimal Lazarus Pit choice
                    if (action["x"], action["y"]) in {(2, 4), (7, 5)}:
                        best_lazarus_symbol = "I"
                        best_lazarus_score = -999999.0
                        for test_sym in ("I", "A", "C", "R", "M", "S"):
                            for u in temp:
                                if u["id"] == act_uid:
                                    u["symbol"] = test_sym
                                    if test_sym == "I": u["type"] = "infantry"
                                    elif test_sym == "A": u["type"] = "artillery"
                                    elif test_sym == "C": u["type"] = "cavalry"
                                    elif test_sym == "R": u["type"] = "relay"
                                    elif test_sym == "M": u["type"] = "mine"
                                    elif test_sym == "S": u["type"] = "shield"
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
                                if best_lazarus_symbol == "I": u["type"] = "infantry"
                                elif best_lazarus_symbol == "A": u["type"] = "artillery"
                                elif best_lazarus_symbol == "C": u["type"] = "cavalry"
                                elif best_lazarus_symbol == "R": u["type"] = "relay"
                                elif best_lazarus_symbol == "M": u["type"] = "mine"
                                elif best_lazarus_symbol == "S": u["type"] = "shield"
                                break

                # ── DYNAMIC POTENTIAL RISK ASSESSMENT (FEAR OF CERTAIN DEATH) ──
                try:
                    enemy_potential_threat_power = 0.0
                    for e in enemy_units:
                        # Only connected enemies pose active threats
                        if e["id"] in base_enemy_connected:
                            e_type = e.get("type", "").lower()
                            if "relay" in e_type:
                                continue
                            e_stats = self.get_stats(e_type)
                            e_move = 2 if "cavalry" in e_type else 1
                            e_range = e_stats["range"]
                            # Chebyshev distance check
                            dist_to_dest = max(abs(e["x"] - action["x"]), abs(e["y"] - action["y"]))
                            if dist_to_dest <= e_move + e_range:
                                enemy_potential_threat_power += e_stats["offense"]

                    if enemy_potential_threat_power > 0:
                        friendly_potential_support_power = 0.0
                        for a in ai_units:
                            if a["id"] != act_uid and a["id"] in base_my_connected:
                                a_type = a.get("type", "").lower()
                                if "relay" in a_type:
                                    continue
                                a_stats = self.get_stats(a_type)
                                a_move = 2 if "cavalry" in a_type else 1
                                dist_to_dest = max(abs(a["x"] - action["x"]), abs(a["y"] - action["y"]))
                                if dist_to_dest <= a_move + 1:
                                    friendly_potential_support_power += a_stats["offense"]

                        acting_stats = self.get_stats(acting_unit.get("type", "").lower())
                        total_friendly_power = friendly_potential_support_power + acting_stats["offense"]

                        if friendly_potential_support_power == 0.0:
                            # Charging alone into enemy potential threat reach is suicidal
                            mod -= 50000.0

                        if enemy_potential_threat_power > total_friendly_power:
                            # Outnumbered in potential threat reach
                            mod -= (enemy_potential_threat_power - total_friendly_power) * 1200.0
                except:
                    pass

                # ── STRATEGIC SUPPLY-LINE INTERCEPTION (NON-LETHAL KILLS) ──
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

                # Cohesion loss penalty (Self/Teammate Disconnection from Supply Line)
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
                                    cutoff_penalty += 6000.0  # Devastating penalty for cutting off a relay
                                else:
                                    cutoff_penalty += 3500.0  # Heavy penalty for cutting off a combat unit
                        mod -= cutoff_penalty
                except:
                    pass

                lost = self.calculate_cohesion_loss(units, act_uid, action["x"], action["y"])
                if lost > 0:
                    base_cohesion_factor = (
                        15.0 if self.macro_state == "ANNIHILATION_HUNT" else
                        (200.0 if len(units) > 10 else 60.0)
                    )
                    if self.macro_state == "ANNIHILATION_HUNT":
                        base_cohesion_factor = 0.0

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

                # ── GOAL-SPECIFIC MODIFIERS (FIFA-STYLE INDIVIDUAL INTELLIGENCE) ──
                goal = local_goals.get(act_uid, "STAY")
                mentality = self.orchestration_data.get("mentality", "BALANCED")
                target_coords = self.orchestration_data.get("target_coords", (12, 10))

                if acting_unit:
                    u_type = acting_unit.get("type", "").lower()
                    
                    if u_type == "relay":
                        if goal == "ESCAPE":
                            # Highly threatened relay: run to safety, get next to defenders
                            dist_enemy_before = min(self.get_path_distance(acting_unit["x"], acting_unit["y"], (e["x"], e["y"])) for e in enemy_units) if enemy_units else 99
                            dist_enemy_after = min(self.get_path_distance(action["x"], action["y"], (e["x"], e["y"])) for e in enemy_units) if enemy_units else 99
                            mod += (dist_enemy_after - dist_enemy_before) * 300.0
                            
                            allies_adjacent = sum(1 for a in ai_units if "relay" not in a.get("type", "").lower() and max(abs(action["x"] - a["x"]), abs(action["y"] - a["y"])) <= 1)
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
                                        if "relay" in conn_unit.get("type", "").lower():
                                            mod += 40000.0  # Huge bonus to reconnect a friendly relay playmaker!
                                        else:
                                            mod += 30000.0  # Big bonus to reconnect combat units
                                mod -= len(newly_disconnected) * 35000.0  # Massive penalty to keep supply lines stable!

                                # Relay supply rule constraints
                                was_connected = acting_unit["id"] in before_connected
                                is_connected_now = acting_unit["id"] in after_connected
                                if not was_connected and is_connected_now:
                                    mod += 80000.0  # High priority to reconnect this Relay to the supply network!
                                elif not is_connected_now:
                                    mod -= 100000.0  # Massive penalty for the Relay staying offline or moving out of supply!
                            except:
                                pass

                            # Target positioning: stay 2-4 steps behind attackers to act as playmakers/bridges
                            attackers = [u for u in ai_units if self.orchestration_data.get("roles", {}).get(u["id"]) == "ATTACKER"]
                            if attackers:
                                avg_ax = sum(a["x"] for a in attackers) / len(attackers)
                                avg_ay = sum(a["y"] for a in attackers) / len(attackers)
                                dist_to_attackers = self.get_path_distance(action["x"], action["y"], (int(avg_ax), int(avg_ay)))
                                if 2 <= dist_to_attackers <= 3:
                                    mod += 800.0
                                else:
                                    mod += (10 - abs(dist_to_attackers - 2.5)) * 100.0

                            # Relay must NEVER commit suicide by moving next to enemy combat units
                            enemy_combat = [e for e in enemy_units if "relay" not in e.get("type", "").lower()]
                            if enemy_combat:
                                min_dist_enemy = min(max(abs(action["x"] - e["x"]), abs(action["y"] - e["y"])) for e in enemy_combat)
                                if min_dist_enemy <= 1:
                                    mod -= 5000.0
                                elif min_dist_enemy <= 3:
                                    mod -= 1000.0

                    else:
                        # Combat Units
                        if goal == "RETREAT":
                            dist_enemy_before = min(self.get_path_distance(acting_unit["x"], acting_unit["y"], (e["x"], e["y"])) for e in enemy_units) if enemy_units else 99
                            dist_enemy_after = min(self.get_path_distance(action["x"], action["y"], (e["x"], e["y"])) for e in enemy_units) if enemy_units else 99
                            mod += (dist_enemy_after - dist_enemy_before) * 150.0

                            allies_adjacent = sum(1 for a in ai_units if max(abs(action["x"] - a["x"]), abs(action["y"] - a["y"])) <= 1 and a["id"] != act_uid)
                            mod += allies_adjacent * 100.0

                            if (action["x"], action["y"]) in self.engine.fortresses or (action["x"], action["y"]) in self.engine.passes:
                                mod += 400.0

                            # Retreat towards home rows
                            mod += (action["y"] - acting_unit["y"] if self.side == "South" else acting_unit["y"] - action["y"]) * 100.0

                        elif goal == "ATTACK_RUN":
                            dist_before = self.get_path_distance(acting_unit["x"], acting_unit["y"], target_coords)
                            dist_after = self.get_path_distance(action["x"], action["y"], target_coords)
                            mod += (dist_before - dist_after) * 200.0
                            if (action["x"], action["y"]) in self.engine.fortresses or (action["x"], action["y"]) in self.engine.passes:
                                mod += 300.0

                        elif goal == "DEFEND":
                            possessions = list(self.engine.arsenals[self.side]) + [(r["x"], r["y"]) for r in ai_units if "relay" in r.get("type", "").lower()]
                            if possessions:
                                dist_before = min(self.get_path_distance(acting_unit["x"], acting_unit["y"], p) for p in possessions)
                                dist_after = min(self.get_path_distance(action["x"], action["y"], p) for p in possessions)
                                if dist_after in [1, 2]:
                                    mod += 500.0 # Shield position
                                elif dist_after < dist_before:
                                    mod += 200.0
                                if (action["x"], action["y"]) in self.engine.fortresses:
                                    mod += 300.0

                        elif goal == "TRAVEL":
                            travel_target = target_coords if mentality != "DEFENSIVE" else list(self.engine.arsenals[self.side])[0]
                            dist_before = self.get_path_distance(acting_unit["x"], acting_unit["y"], travel_target)
                            dist_after = self.get_path_distance(action["x"], action["y"], travel_target)
                            mod += (dist_before - dist_after) * 150.0

                        elif goal == "STAY":
                            dist_moved = max(abs(acting_unit["x"] - action["x"]), abs(acting_unit["y"] - action["y"]))
                            if dist_moved > 0:
                                mod -= 200.0

                if acting_unit:
                    dist_moved = max(abs(acting_unit["x"] - action["x"]), abs(acting_unit["y"] - action["y"]))
                    if dist_moved <= 1:
                        mod += 0.0 if self.macro_state in ["ANNIHILATION_HUNT", "DESPERATION_CHOKE"] else 15.0

            is_final_state = (action["action_type"] == "end_turn" or current_state.get("moves_left", 5) == 1)
            my_breakdown = self.evaluate_board(temp, return_breakdown=True, base_enemy_connected=base_enemy_connected, is_end_turn=is_final_state)

            if my_breakdown["TOTAL"] + mod < best_score - 500.0:
                continue

            if self.defensive_weight > 0:
                enemy_score = self.enemy_evaluator.evaluate_board(temp, base_enemy_connected=base_my_connected, is_end_turn=is_final_state)
                score = (my_breakdown["TOTAL"] - self.defensive_weight * enemy_score) + mod
            else:
                score = my_breakdown["TOTAL"] + mod

            anomaly_type = self._detect_behavioral_anomaly(act_uid) if act_uid else None
            if anomaly_type:
                if act_uid not in diagnostic_log:
                    diagnostic_log[act_uid] = {"anomaly": anomaly_type, "choices": []}
                diagnostic_log[act_uid]["choices"].append({
                    "action": action,
                    "score": score,
                    "mod_applied": mod,
                    "breakdown": my_breakdown
                })

                if anomaly_type == "STASIS_FREEZE":
                    u_temp = next((ut for ut in temp if ut["id"] == act_uid), None)
                    if u_temp and u_temp["x"] == acting_unit["x"] and u_temp["y"] == acting_unit["y"]:
                        score -= 200000.0
                elif anomaly_type in ["2_STEP_OSCILLATION", "3_STEP_OSCILLATION"]:
                    recent_pos = set(self.position_history.get(act_uid, [])[-4:])
                    if action["action_type"] == "move" and (action["x"], action["y"]) in recent_pos:
                        score -= 200000.0



            if score > best_score:
                best_score = score
                best_action = action

        for uid, data in diagnostic_log.items():
            ref_unit = next(u for u in units if u["id"] == uid)
            print("\n" + "=" * 80, file=sys.stderr)
            print(f"⚠️ DIAGNOSTIC ALERT: Unit ID {uid} [{ref_unit['type'].upper()}] at ({ref_unit['x']}, {ref_unit['y']}) is in state: {data['anomaly']}", file=sys.stderr)
            print(f"Macro Strategy Context: {self.macro_state}", file=sys.stderr)
            print(f"Historical Positions Tracking Queue: {self.position_history[uid]}", file=sys.stderr)
            print("-" * 80, file=sys.stderr)
            print(f"{'PROPOSED TARGET':<18} | {'FINAL SCORE':<12} | {'ROLE EVAL':<10} | {'COHESION':<10} | {'THREATS':<10} | {'MODIFIER':<10}", file=sys.stderr)
            print("-" * 80, file=sys.stderr)

            sorted_choices = sorted(data["choices"], key=lambda c: c["score"], reverse=True)
            for choice in sorted_choices:
                act = choice["action"]
                bd = choice["breakdown"]
                tgt = f"{act['action_type'].upper()} -> ({act['x']}, {act['y']})" if act['action_type'] != 'end_turn' else "END_TURN"
                print(f"{tgt:<18} | {choice['score']:<12.1f} | {bd['Role_Exec']:<10.1f} | {bd['Cohesion']:<10.1f} | {bd['Threat_Def']:<10.1f} | {choice['mod_applied']:<10.1f}", file=sys.stderr)

            if len(sorted_choices) >= 2:
                top_choice = sorted_choices[0]
                forward_choices = [c for c in sorted_choices if c['action']['action_type'] == 'move' and abs(c['action']['y'] - target_y) < abs(ref_unit['y'] - target_y)]
                if forward_choices and top_choice != forward_choices[0]:
                    f_choice = forward_choices[0]
                    print("\n💡 ROOT CAUSE ANALYSIS:", file=sys.stderr)
                    role_delta = f_choice['breakdown']['Role_Exec'] - top_choice['breakdown']['Role_Exec']
                    coh_delta = f_choice['breakdown']['Cohesion'] - top_choice['breakdown']['Cohesion']
                    loss_delta = f_choice['mod_applied'] - top_choice['mod_applied']

                    print(f"   • Forward movement was rejected in favor of {top_choice['action']['action_type'].upper()}.", file=sys.stderr)
                    if coh_delta < 0:
                        print(f"   • Cohesion Deficit: Moving forward would drop Cohesion score by {abs(coh_delta):.1f} points.", file=sys.stderr)
                    if role_delta < 0:
                        print(f"   • Role Penalty: Moving forward would lose out on {abs(role_delta):.1f} objective value points.", file=sys.stderr)
                    if loss_delta < 0:
                        print(f"   • Structural Loss: Move broke lines, triggering a penalty of {abs(loss_delta):.1f} points.", file=sys.stderr)
            print("=" * 80 + "\n", file=sys.stderr)

        # If the best action chosen is unproductive (end_turn), but there are other clusters
        # we haven't evaluated yet, recursively try the next cluster!
        if best_action and best_action["action_type"] == "end_turn" and cluster_ids:
            all_clusters = set(sorted(unit_to_cluster.values()))
            if allowed_clusters is None:
                allowed_clusters = all_clusters
            remaining_clusters = allowed_clusters - {chosen_cluster}
            if remaining_clusters:
                return self.select_best_action(current_state, allowed_clusters=remaining_clusters)

        return best_action if best_action else {"action_type": "end_turn"}

