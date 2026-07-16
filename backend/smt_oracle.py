

# import sys
# from z3 import *


# class SmtTacticalOracle:
#     def __init__(self, cols=10, rows=10):
#         self.cols = cols
#         self.rows = rows

#         # Flat profile enum mapping
#         self.PROFILE_CODES = {
#             "infantry": 0,
#             "cavalry": 1,
#             "artillery": 2,
#             "relay": 3,
#             "mine": 4,
#             "shield": 5
#         }

#     def verify_action_safety(self, units: list, side: str, proposed_action: dict) -> bool:
#         """
#         Uses an SMT solver to strictly prove if a proposed move/transform commitment
#         guarantees an immediate, unacceptably high-risk vulnerability.
#         Returns True if the action is mathematically guaranteed to be a trap (Veto Action).
#         """
#         if proposed_action.get("action_type") != "move":
#             return False

#         solver = Solver()
#         act_uid = proposed_action["unitId"]
#         target_x = proposed_action["x"]
#         target_y = proposed_action["y"]
#         transform_to = proposed_action.get("transform_to")

#         Target_X = Int('target_x')
#         Target_Y = Int('target_y')
#         Target_Profile = Int('target_profile')

#         solver.add(Target_X == target_x)
#         solver.add(Target_Y == target_y)

#         current_unit = next((u for u in units if u["id"] == act_uid), None)
#         if not current_unit:
#             return False

#         final_profile_str = transform_to if transform_to else current_unit["type"].lower()
#         final_profile_code = self.PROFILE_CODES.get(final_profile_str, 0)
#         solver.add(Target_Profile == final_profile_code)

#         # Constraint 1: The Glass-Cannon Cavalry Proximity Check
#         enemy_side = "North" if side == "South" else "South"
#         enemy_units = [u for u in units if u.get("side") == enemy_side]

#         for enemy in enemy_units:
#             ex, ey = enemy["x"], enemy["y"]
#             is_adjacent = And(Abs(Target_X - ex) <= 1, Abs(Target_Y - ey) <= 1)
#             is_cavalry = (Target_Profile == 1)
#             solver.add(Not(And(is_cavalry, is_adjacent)))

#         # Constraint 2: Border Encroachment Grid Limits
#         solver.add(Target_X >= 0, Target_X < self.cols)
#         solver.add(Target_Y >= 0, Target_Y < self.rows)

#         if solver.check() == unsat:
#             print(
#                 f"🛑 [SMT Oracle] VETO: Action for Unit {act_uid} to ({target_x}, {target_y}) as [{final_profile_str}] is a high-risk trap.",
#                 file=sys.stderr)
#             return True
#         return False

#     # ── ADVANCED GENERATIVE METHODS TO LEVERAGE Z3 EXTENSIVELY ──

#     def solve_geometric_fork(self, units: list, side: str, act_uid: str, allowed_moves: list) -> dict:
#         """
#         Asks Z3 to find a legal coordinate tile from allowed_moves that sets up a
#         simultaneous multi-target threat (fork) against two distinct enemy units.
#         Returns a target action modifier dictionary if sat, else None.
#         """
#         current_unit = next((u for u in units if u["id"] == act_uid), None)
#         if not current_unit or not allowed_moves:
#             return None

#         # Build ranges based on profile mappings
#         u_type = current_unit["type"].lower()
#         u_range = 3 if u_type == "artillery" else 1

#         enemy_side = "North" if side == "South" else "South"
#         enemies = [e for e in units if e["side"] == enemy_side and e.get("symbol") != "S"]

#         # We need at least 2 targetable units to execute a geometric fork calculation
#         if len(enemies) < 2:
#             return None

#         s = Solver()
#         Fork_X = Int('fork_x')
#         Fork_Y = Int('fork_y')

#         # Constraint 1: The fork coordinate MUST exist within our pre-calculated legal movement array
#         legal_move_conditions = [And(Fork_X == m["x"], Fork_Y == m["y"]) for m in allowed_moves]
#         s.add(Or(*legal_move_conditions))

#         # Constraint 2: Check vector configurations targeting enemy pairs simultaneously
#         fork_scenarios = []
#         for i in range(len(enemies)):
#             for j in range(i + 1, len(enemies)):
#                 e1, e2 = enemies[i], enemies[j]

#                 # Model true directional vector paths (8 cardinal/diagonal lanes)
#                 # DX and DY variables measure spatial separation along coordinate lanes
#                 dx1, dy1 = e1["x"] - Fork_X, e1["y"] - Fork_Y
#                 dx2, dy2 = e2["x"] - Fork_X, e2["y"] - Fork_Y

#                 # Alignment mapping rules: component values must match or zero out completely
#                 aligned_e1 = Or(dx1 == 0, dy1 == 0, Abs(dx1) == Abs(dy1))
#                 in_range_e1 = And(Abs(dx1) <= u_range, Abs(dy1) <= u_range)

#                 aligned_e2 = Or(dx2 == 0, dy2 == 0, Abs(dx2) == Abs(dy2))
#                 in_range_e2 = And(Abs(dx2) <= u_range, Abs(dy2) <= u_range)

#                 # Both separate enemy entities must be threatened concurrently on the target step
#                 fork_scenarios.append(And(aligned_e1, in_range_e1, aligned_e2, in_range_e2))

#         s.add(Or(*fork_scenarios))

#         if s.check() == sat:
#             m = s.model()
#             fx, fy = m[Fork_X].as_long(), m[Fork_Y].as_long()
#             print(f"🔮 [Z3 INTEL] FORK DETECTED! Unit {act_uid} can pressure multiple targets at ({fx}, {fy})",
#                   file=sys.stderr)
#             return {"x": fx, "y": fy, "fork_bonus": 800.0}

#         return None

#     def calculate_absolute_safe_zones(self, units: list, enemy_side: str) -> list:
#         """
#         Uses mathematical inversion to find all coordinate sectors that are
#         completely immune to active enemy fire paths for high-priority maneuvers.
#         Returns a list of safe (x, y) tuples.
#         """
#         enemies = [e for e in units if e["side"] == enemy_side]
#         active_threat_constraints = []

#         s = Solver()
#         Safe_X = Int('safe_x')
#         Safe_Y = Int('safe_y')

#         s.add(Safe_X >= 0, Safe_X < self.cols)
#         s.add(Safe_Y >= 0, Safe_Y < self.rows)

#         # For every enemy, map their potential ray-cast vectors mathematically into the solver
#         for e in enemies:
#             ex, ey = e["x"], e["y"]
#             e_range = 3 if e["type"].lower() == "artillery" else 1

#             # A coordinate is unsafe if it aligns with an enemy's vector fire lane within range
#             dx = Safe_X - ex
#             dy = Safe_Y - ey
#             aligned = Or(dx == 0, dy == 0, Abs(dx) == Abs(dy))
#             in_range = And(Abs(dx) <= e_range, Abs(dy) <= e_range)

#             active_threat_constraints.append(And(aligned, in_range))

#         # Invert the logic: We assert that the tile is NOT caught in any threat ray-cast paths
#         if active_threat_constraints:
#             s.add(Not(Or(*active_threat_constraints)))

#         safe_tiles = []
#         # Leverage Z3 to systematically drain the solution space and pull all verified safe coordinates
#         while s.check() == sat:
#             m = s.model()
#             sx, sy = m[Safe_X].as_long(), m[Safe_Y].as_long()
#             safe_tiles.append((sx, sy))
#             # Block this specific coordinate solution to force Z3 to solve for the remaining layout space
#             s.add(Or(Safe_X != sx, Safe_Y != sy))

#         return safe_tiles





import sys
from z3 import *

class SmtTacticalOracle:
    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows

    def verify_action_safety(self, units: list, ai_side: str, target_tile: tuple, target_defense: int, engine) -> float:
        """
        Uses Z3 Optimize to determine the worst-case next-turn offensive pressure 
        concentrated against a specific tile by an unknown combination of repositioning enemies.
        Returns: max_offense - target_defense (The raw vulnerability delta)
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

            # Get the exact reachable movement envelope from Step 1
            reachable_set = engine.get_reachable_tiles(units, e_id)
            if not reachable_set:
                continue

            # Free position tracking variables for this enemy unit
            ex = Int(f"ex_{i}")
            ey = Int(f"ey_{i}")
            enemy_vars[e_id] = (ex, ey)

            # Constraint: Enemy position MUST exist within its classical BFS reachable space
            tile_constraints = [And(ex == rx, ey == ry) for rx, ry in reachable_set]
            opt.add(Or(tile_constraints))

            # Boolean rule: True if the enemy aligns directionally and has target within line-of-sight range
            contributes = Bool(f"contrib_{i}")
            
            # Strict Directional Line-of-Sight Mapping Constraints:
            # Orthogonal adjacency offers no protection against diagonal strikes. 
            # We enforce exact vector alignment along standard directions.
            dx = tx - ex
            dy = ty - ey
            
            # Distance metric constraints based on max range bounds
            # max(abs(dx), abs(dy)) <= range
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

        # if not contributions:
        #     return 0.0

        # # Maximize: Total Aggregated Offense
        # total_offense = Sum(contributions)
        # vulnerability_delta = total_offense - target_defense

        if not contributions:
            return 0.0

        # Maximize: Total Aggregated Offense
        total_offense = Sum(contributions)
        
        # ── ADJUST DEFENSE INTEGRATION ACCORDING TO GRID GEOMETRY ──
        modified_defense = target_defense
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