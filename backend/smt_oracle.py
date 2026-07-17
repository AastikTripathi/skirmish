import sys
from z3 import *


class SmtTacticalOracle:
    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows

    # def verify_action_safety(self, units: list, ai_side: str, target_tile: tuple, target_defense: int, engine) -> float:
    #     """
    #     Uses Z3 Optimize to determine the worst-case next-turn offensive pressure
    #     concentrated against a specific tile by an unknown combination of repositioning enemies.
    #     Returns: max_offense - target_defense (The raw vulnerability delta)
    #     """
    #     enemy_side = "North" if ai_side == "South" else "South"
    #     enemies = [u for u in units if u.get("side") == enemy_side]
    #     tx, ty = target_tile
    #
    #     opt = Optimize()
    #     enemy_vars = {}
    #     contributions = []
    #
    #     for i, enemy in enumerate(enemies):
    #         e_id = enemy["id"]
    #         e_type = enemy.get("type", "").lower()
    #         e_stats = engine.get_stats(e_type)
    #         e_offense = e_stats.get("offense", 10)
    #         e_range = e_stats.get("range", 2)
    #
    #         # Get the exact reachable movement envelope from Step 1
    #         reachable_set = engine.get_reachable_tiles(units, e_id)
    #         if not reachable_set:
    #             continue
    #
    #         # Free position tracking variables for this enemy unit
    #         ex = Int(f"ex_{i}")
    #         ey = Int(f"ey_{i}")
    #         enemy_vars[e_id] = (ex, ey)
    #
    #         # Constraint: Enemy position MUST exist within its classical BFS reachable space
    #         tile_constraints = [And(ex == rx, ey == ry) for rx, ry in reachable_set]
    #         opt.add(Or(tile_constraints))
    #
    #         # Boolean rule: True if the enemy aligns directionally and has target within line-of-sight range
    #         contributes = Bool(f"contrib_{i}")
    #
    #         # Strict Directional Line-of-Sight Mapping Constraints:
    #         # Orthogonal adjacency offers no protection against diagonal strikes.
    #         # We enforce exact vector alignment along standard directions.
    #         dx = tx - ex
    #         dy = ty - ey
    #
    #         # Distance metric constraints based on max range bounds
    #         # max(abs(dx), abs(dy)) <= range
    #         dx_abs = If(dx >= 0, dx, -dx)
    #         dy_abs = If(dy >= 0, dy, -dy)
    #         max_dist = If(dx_abs >= dy_abs, dx_abs, dy_abs)
    #
    #         in_range = max_dist <= e_range
    #
    #         # Alignment: dx == 0 (vertical), dy == 0 (horizontal), or abs(dx) == abs(dy) (diagonal vectors)
    #         aligned = Or(dx == 0, dy == 0, dx_abs == dy_abs)
    #
    #         # Connect the boolean to the geometric conditions
    #         opt.add(contributes == And(in_range, aligned))
    #
    #         # Map contribution magnitude into the master optimization expression
    #         contributions.append(If(contributes, e_offense, 0))
    #
    #     # if not contributions:
    #     #     return 0.0
    #
    #     # # Maximize: Total Aggregated Offense
    #     # total_offense = Sum(contributions)
    #     # vulnerability_delta = total_offense - target_defense
    #
    #     if not contributions:
    #         return 0.0
    #
    #     # Maximize: Total Aggregated Offense
    #     total_offense = Sum(contributions)
    #
    #     # ── ADJUST DEFENSE INTEGRATION ACCORDING TO GRID GEOMETRY ──
    #     modified_defense = target_defense
    #     if hasattr(engine, 'fortresses') and target_tile in engine.fortresses:
    #         modified_defense += 4
    #     elif hasattr(engine, 'passes') and target_tile in engine.passes:
    #         modified_defense += 2
    #
    #     if hasattr(engine, 'fortresses') and hasattr(engine, 'passes'):
    #         if target_tile in engine.fortresses or target_tile in engine.passes:
    #             modified_defense *= 2
    #
    #     vulnerability_delta = total_offense - modified_defense
    #     opt.maximize(vulnerability_delta)
    #
    #     if opt.check() == sat:
    #         m = opt.model()
    #         worst_case_delta = m.evaluate(vulnerability_delta).as_long()
    #         return float(worst_case_delta)
    #
    #     return 0.0

    def verify_action_safety(self, units: list, ai_side: str, target_tile: tuple, target_defense: int, engine,
                             target_transform_type: str = None) -> float:
        """
        Uses Z3 Optimize to determine the worst-case next-turn offensive pressure
        concentrated against a specific tile by an unknown combination of repositioning enemies.
        Dynamically factors in transformation defense modifications.
        Returns: max_offense - modified_defense (The raw vulnerability delta)
        """
        enemy_side = "North" if ai_side == "South" else "South"
        enemies = [u for u in units if u.get("side") == enemy_side]
        tx, ty = target_tile

        opt = Optimize()
        enemy_vars = {}
        contributions = []

        for i, enemy in enumerate(enemies):
            e_id = enemy["id"]
            e_type = enemy.get("type", "").lower()
            e_stats = engine.get_stats(e_type)
            e_offense = e_stats.get("offense", 10)
            e_range = e_stats.get("range", 2)

            # Get the exact reachable movement envelope
            reachable_set = engine.get_reachable_tiles(units, e_id)
            if not reachable_set:
                continue

            # Position tracking variables for this enemy unit
            ex = Int(f"ex_{i}")
            ey = Int(f"ey_{i}")
            enemy_vars[e_id] = (ex, ey)

            # Constraint: Enemy position MUST exist within its reachable space
            tile_constraints = [And(ex == rx, ey == ry) for rx, ry in reachable_set]
            opt.add(Or(tile_constraints))

            # Boolean rule: True if the enemy aligns directionally and has target within line-of-sight range
            contributes = Bool(f"contrib_{i}")

            dx = tx - ex
            dy = ty - ey

            # Distance metric constraints based on max range bounds
            dx_abs = If(dx >= 0, dx, -dx)
            dy_abs = If(dy >= 0, dy, -dy)
            max_dist = If(dx_abs >= dy_abs, dx_abs, dy_abs)

            in_range = max_dist <= e_range

            # Alignment: dx == 0 (vertical), dy == 0 (horizontal), or abs(dx) == abs(dy) (diagonal vectors)
            aligned = Or(dx == 0, dy == 0, dx_abs == dy_abs)

            # Connect the boolean to the geometric conditions
            opt.add(contributes == And(in_range, aligned))

            # Map contribution magnitude into the master optimization expression
            contributions.append(If(contributes, e_offense, 0))

        if not contributions:
            return 0.0

        # Maximize: Total Aggregated Offense
        total_offense = Sum(contributions)

        # ── 1. DYNAMICALLY READ THE TRANSFORMATION STATS INSIDE Z3 EVALUATION ──
        if target_transform_type:
            t_stats = engine.get_stats(target_transform_type.lower())
            modified_defense = t_stats.get("defense", target_defense)
        else:
            modified_defense = target_defense

        # ── 2. ADJUST DEFENSE INTEGRATION ACCORDING TO GRID GEOMETRY ──
        if hasattr(engine, 'fortresses') and target_tile in engine.fortresses:
            modified_defense += 4
        elif hasattr(engine, 'passes') and target_tile in engine.passes:
            modified_defense += 2

        if hasattr(engine, 'fortresses') and hasattr(engine, 'passes'):
            if target_tile in engine.fortresses or target_tile in engine.passes:
                modified_defense *= 2

        vulnerability_delta = total_offense - modified_defense
        opt.maximize(vulnerability_delta)

        if opt.check() == sat:
            m = opt.model()
            worst_case_delta = m.evaluate(vulnerability_delta).as_long()
            return float(worst_case_delta)

        return 0.0
