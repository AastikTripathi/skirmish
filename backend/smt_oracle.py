# import sys
# from z3 import *


# class SmtTacticalOracle:
#     def __init__(self, cols: int, rows: int):
#         self.cols = cols
#         self.rows = rows

#     # def verify_action_safety(self, units: list, ai_side: str, target_tile: tuple, target_defense: int, engine) -> float:
#     #     """
#     #     Uses Z3 Optimize to determine the worst-case next-turn offensive pressure
#     #     concentrated against a specific tile by an unknown combination of repositioning enemies.
#     #     Returns: max_offense - target_defense (The raw vulnerability delta)
#     #     """
#     #     enemy_side = "North" if ai_side == "South" else "South"
#     #     enemies = [u for u in units if u.get("side") == enemy_side]
#     #     tx, ty = target_tile
#     #
#     #     opt = Optimize()
#     #     enemy_vars = {}
#     #     contributions = []
#     #
#     #     for i, enemy in enumerate(enemies):
#     #         e_id = enemy["id"]
#     #         e_type = enemy.get("type", "").lower()
#     #         e_stats = engine.get_stats(e_type)
#     #         e_offense = e_stats.get("offense", 10)
#     #         e_range = e_stats.get("range", 2)
#     #
#     #         # Get the exact reachable movement envelope from Step 1
#     #         reachable_set = engine.get_reachable_tiles(units, e_id)
#     #         if not reachable_set:
#     #             continue
#     #
#     #         # Free position tracking variables for this enemy unit
#     #         ex = Int(f"ex_{i}")
#     #         ey = Int(f"ey_{i}")
#     #         enemy_vars[e_id] = (ex, ey)
#     #
#     #         # Constraint: Enemy position MUST exist within its classical BFS reachable space
#     #         tile_constraints = [And(ex == rx, ey == ry) for rx, ry in reachable_set]
#     #         opt.add(Or(tile_constraints))
#     #
#     #         # Boolean rule: True if the enemy aligns directionally and has target within line-of-sight range
#     #         contributes = Bool(f"contrib_{i}")
#     #
#     #         # Strict Directional Line-of-Sight Mapping Constraints:
#     #         # Orthogonal adjacency offers no protection against diagonal strikes.
#     #         # We enforce exact vector alignment along standard directions.
#     #         dx = tx - ex
#     #         dy = ty - ey
#     #
#     #         # Distance metric constraints based on max range bounds
#     #         # max(abs(dx), abs(dy)) <= range
#     #         dx_abs = If(dx >= 0, dx, -dx)
#     #         dy_abs = If(dy >= 0, dy, -dy)
#     #         max_dist = If(dx_abs >= dy_abs, dx_abs, dy_abs)
#     #
#     #         in_range = max_dist <= e_range
#     #
#     #         # Alignment: dx == 0 (vertical), dy == 0 (horizontal), or abs(dx) == abs(dy) (diagonal vectors)
#     #         aligned = Or(dx == 0, dy == 0, dx_abs == dy_abs)
#     #
#     #         # Connect the boolean to the geometric conditions
#     #         opt.add(contributes == And(in_range, aligned))
#     #
#     #         # Map contribution magnitude into the master optimization expression
#     #         contributions.append(If(contributes, e_offense, 0))
#     #
#     #     # if not contributions:
#     #     #     return 0.0
#     #
#     #     # # Maximize: Total Aggregated Offense
#     #     # total_offense = Sum(contributions)
#     #     # vulnerability_delta = total_offense - target_defense
#     #
#     #     if not contributions:
#     #         return 0.0
#     #
#     #     # Maximize: Total Aggregated Offense
#     #     total_offense = Sum(contributions)
#     #
#     #     # ── ADJUST DEFENSE INTEGRATION ACCORDING TO GRID GEOMETRY ──
#     #     modified_defense = target_defense
#     #     if hasattr(engine, 'fortresses') and target_tile in engine.fortresses:
#     #         modified_defense += 4
#     #     elif hasattr(engine, 'passes') and target_tile in engine.passes:
#     #         modified_defense += 2
#     #
#     #     if hasattr(engine, 'fortresses') and hasattr(engine, 'passes'):
#     #         if target_tile in engine.fortresses or target_tile in engine.passes:
#     #             modified_defense *= 2
#     #
#     #     vulnerability_delta = total_offense - modified_defense
#     #     opt.maximize(vulnerability_delta)
#     #
#     #     if opt.check() == sat:
#     #         m = opt.model()
#     #         worst_case_delta = m.evaluate(vulnerability_delta).as_long()
#     #         return float(worst_case_delta)
#     #
#     #     return 0.0

#     def verify_action_safety(self, units: list, ai_side: str, target_tile: tuple, target_defense: int, engine,
#                              target_transform_type: str = None) -> float:
#         """
#         Uses Z3 Optimize to determine the worst-case next-turn offensive pressure
#         concentrated against a specific tile by an unknown combination of repositioning enemies.
#         Dynamically factors in transformation defense modifications.
#         Returns: max_offense - modified_defense (The raw vulnerability delta)
#         """
#         enemy_side = "North" if ai_side == "South" else "South"
#         enemies = [u for u in units if u.get("side") == enemy_side]
#         tx, ty = target_tile

#         opt = Optimize()
#         enemy_vars = {}
#         contributions = []

#         for i, enemy in enumerate(enemies):
#             e_id = enemy["id"]
#             e_type = enemy.get("type", "").lower()
#             e_stats = engine.get_stats(e_type)
#             e_offense = e_stats.get("offense", 10)
#             e_range = e_stats.get("range", 2)

#             # Get the exact reachable movement envelope
#             reachable_set = engine.get_reachable_tiles(units, e_id)
#             if not reachable_set:
#                 continue

#             # Position tracking variables for this enemy unit
#             ex = Int(f"ex_{i}")
#             ey = Int(f"ey_{i}")
#             enemy_vars[e_id] = (ex, ey)

#             # Constraint: Enemy position MUST exist within its reachable space
#             tile_constraints = [And(ex == rx, ey == ry) for rx, ry in reachable_set]
#             opt.add(Or(tile_constraints))

#             # Boolean rule: True if the enemy aligns directionally and has target within line-of-sight range
#             contributes = Bool(f"contrib_{i}")

#             dx = tx - ex
#             dy = ty - ey

#             # Distance metric constraints based on max range bounds
#             dx_abs = If(dx >= 0, dx, -dx)
#             dy_abs = If(dy >= 0, dy, -dy)
#             max_dist = If(dx_abs >= dy_abs, dx_abs, dy_abs)

#             in_range = max_dist <= e_range

#             # Alignment: dx == 0 (vertical), dy == 0 (horizontal), or abs(dx) == abs(dy) (diagonal vectors)
#             aligned = Or(dx == 0, dy == 0, dx_abs == dy_abs)

#             # Connect the boolean to the geometric conditions
#             opt.add(contributes == And(in_range, aligned))

#             # Map contribution magnitude into the master optimization expression
#             contributions.append(If(contributes, e_offense, 0))

#         if not contributions:
#             return 0.0

#         # Maximize: Total Aggregated Offense
#         total_offense = Sum(contributions)

#         # ── 1. DYNAMICALLY READ THE TRANSFORMATION STATS INSIDE Z3 EVALUATION ──
#         if target_transform_type:
#             t_stats = engine.get_stats(target_transform_type.lower())
#             modified_defense = t_stats.get("defense", target_defense)
#         else:
#             modified_defense = target_defense

#         # ── 2. ADJUST DEFENSE INTEGRATION ACCORDING TO GRID GEOMETRY ──
#         if hasattr(engine, 'fortresses') and target_tile in engine.fortresses:
#             modified_defense += 4
#         elif hasattr(engine, 'passes') and target_tile in engine.passes:
#             modified_defense += 2

#         if hasattr(engine, 'fortresses') and hasattr(engine, 'passes'):
#             if target_tile in engine.fortresses or target_tile in engine.passes:
#                 modified_defense *= 2

#         vulnerability_delta = total_offense - modified_defense
#         opt.maximize(vulnerability_delta)
import sys
from fractions import Fraction
from z3 import *


class SmtTacticalOracle:
    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows

    def verify_action_safety(self, units: list, ai_side: str, target_tile: tuple, target_defense: int, engine,
                             target_transform_type: str = None, mines: list = None) -> float:
        """
        Oracle A — Danger Ceiling (Z3 Optimize / worst-case).
        Finds the theoretical maximum offense any enemy configuration can project
        onto target_tile.  Used as a fast gate: if ceiling < 2.0 the tile is
        completely safe.  When ceiling >= 2.0, compute_threat_probability is
        called for the realistic probability-weighted assessment.
        Returns: vulnerability delta (ceiling danger score).
        """
        enemy_side = "North" if ai_side == "South" else "South"
        enemies = [u for u in units if u.get("side") == enemy_side]
        tx, ty = target_tile

        opt = Optimize()
        contributions = []

        for i, enemy in enumerate(enemies):
            e_id = enemy["id"]
            e_type = enemy.get("type", "").lower()
            e_stats = engine.get_stats(e_type)
            e_offense = e_stats.get("offense", 10)
            e_range = e_stats.get("range", 2)

            reachable_set = engine.get_reachable_tiles(units, e_id, mines)
            if not reachable_set:
                continue

            ex = Int(f"ex_{i}")
            ey = Int(f"ey_{i}")

            tile_constraints = [And(ex == rx, ey == ry) for rx, ry in reachable_set]
            opt.add(Or(tile_constraints))

            contributes = Bool(f"contrib_{i}")
            dx = tx - ex
            dy = ty - ey
            dx_abs = If(dx >= 0, dx, -dx)
            dy_abs = If(dy >= 0, dy, -dy)
            max_dist = If(dx_abs >= dy_abs, dx_abs, dy_abs)
            in_range = max_dist <= e_range
            aligned = Or(dx == 0, dy == 0, dx_abs == dy_abs)
            opt.add(contributes == And(in_range, aligned))
            contributions.append(If(contributes, e_offense, 0))

        if not contributions:
            return 0.0

        total_offense = Sum(contributions)

        if target_transform_type:
            t_stats = engine.get_stats(target_transform_type.lower())
            modified_defense = t_stats.get("defense", target_defense)
        else:
            modified_defense = target_defense

        if hasattr(engine, 'fortresses') and target_tile in engine.fortresses:
            modified_defense += 4
        elif hasattr(engine, 'passes') and target_tile in engine.passes:
            modified_defense += 2
        if hasattr(engine, 'fortresses') and hasattr(engine, 'passes'):
            if target_tile in engine.fortresses or target_tile in engine.passes:
                modified_defense *= 2

        raw_net_force = total_offense - modified_defense
        vulnerability_delta = If(raw_net_force >= 2,
                                 raw_net_force,
                                 If(raw_net_force == 1, 1.0, 0.0))
        opt.maximize(vulnerability_delta)

        if opt.check() == sat:
            m = opt.model()
            return float(m.evaluate(vulnerability_delta).as_long())
        return 0.0

    def compute_threat_probability(self, units: list, ai_side: str, target_tile: tuple,
                                   target_defense: int, engine,
                                   target_transform_type: str = None, mines: list = None) -> tuple:
        """
        Oracle B — Probabilistic Threat Assessment (Z3 AllSAT + Z3 Real arithmetic).

        Phase 1 — Z3 AllSAT (model blocking):
            For each connected enemy, Z3 enumerates EVERY reachable tile from
            which they have geometrically valid firing geometry onto target_tile
            (axis alignment + weapon range).  We block each found model with
            Or(ex != fx, ey != fy) and call check() again until UNSAT.
            Termination is guaranteed because the reachable set is finite.
            engine.check_line_of_sight then filters terrain-blocked paths
            (Z3 cannot model mountains or occupied cells as obstacle constraints).

        Phase 2 — Z3 Real arithmetic (exact rationals):
            Each reachable tile receives a tactical desirability weight
            (probability the enemy moves there).  Python Fraction gives lossless
            rational representation; Z3 RatVal encodes it exactly.

              p_fire_i      = firing_weight_i / total_weight_i
              E[offense_i]  = p_fire_i × offense_i
              E[offense]    = Σ_i E[offense_i]
              p_survive     = Π_i (1 − p_lethal_solo_i)   [independence]
              p_lethal      = 1 − p_survive

            Z3 Optimize verifies E[offense] as a satisfiable Real expression
            before extracting the model value.

        Returns:
            (expected_offense: float, p_lethal: float)
            expected_offense — probability-weighted average offense on target_tile
            p_lethal         — P(at least one enemy achieves a DESTROY-level hit)
        """
        enemy_side = "North" if ai_side == "South" else "South"
        enemies = [u for u in units if u.get("side") == enemy_side]
        tx, ty = target_tile

        # ── Defense baseline (mirrors Oracle A) ──
        if target_transform_type:
            t_stats = engine.get_stats(target_transform_type.lower())
            mod_def = t_stats.get("defense", target_defense)
        else:
            mod_def = target_defense
        if hasattr(engine, "fortresses") and target_tile in engine.fortresses:
            mod_def = (mod_def + 4) * 2
        elif hasattr(engine, "passes") and target_tile in engine.passes:
            mod_def = (mod_def + 2) * 2
        destroy_threshold = mod_def + 2      # net_force >= 2 → DESTROY

        try:
            connected_enemies = engine.get_connected_units(units, enemy_side)
        except Exception:
            connected_enemies = set()

        ai_units_here = [u for u in units if u.get("side") == ai_side]
        ai_arsenals   = list(engine.arsenals[ai_side])

        def _weight(rx: int, ry: int) -> float:
            """
            Tactical desirability weight for a reachable tile.
            Higher weight → higher probability enemy moves there.
            Driven by: advance toward our arsenal + close in on our units.
            """
            w = 1.0
            if ai_arsenals:
                ax, ay = ai_arsenals[0]
                w += max(0.0, 10 - max(abs(rx - ax), abs(ry - ay))) * 0.40
            if ai_units_here:
                min_d = min(max(abs(rx - u["x"]), abs(ry - u["y"])) for u in ai_units_here)
                w += max(0.0, 8 - min_d) * 0.25
            return w

        # ──────────────────────────────────────────────────────────────────────
        # PHASE 1 — Z3 AllSAT: enumerate all firing positions per enemy
        # ──────────────────────────────────────────────────────────────────────
        per_enemy_stats = []   # [(expected_contribution, p_lethal_solo)]

        for enemy in enemies:
            if enemy["id"] not in connected_enemies:
                continue

            e_type    = enemy.get("type", "").lower()
            e_stats   = engine.get_stats(e_type)
            e_offense = e_stats.get("offense", 0)
            e_range   = e_stats.get("range", 2)
            if e_offense == 0:
                continue          # mines / shields cannot project offense

            reachable_set = list(engine.get_reachable_tiles(units, enemy["id"], mines))
            if not reachable_set:
                continue

            # Z3 integer position variables for this enemy unit
            ex = Int(f"ex_{enemy['id']}")
            ey = Int(f"ey_{enemy['id']}")

            # Geometric firing constraint
            dx_z     = tx - ex
            dy_z     = ty - ey
            dx_abs_z = If(dx_z >= 0, dx_z, -dx_z)
            dy_abs_z = If(dy_z >= 0, dy_z, -dy_z)
            max_d_z  = If(dx_abs_z >= dy_abs_z, dx_abs_z, dy_abs_z)

            fire_geom = And(
                max_d_z > 0,
                max_d_z <= e_range,
                Or(dx_z == 0, dy_z == 0, dx_abs_z == dy_abs_z)
            )

            # Hard constraint: enemy must be at one of their legally reachable tiles
            reach_cstr = Or([And(ex == rx, ey == ry) for rx, ry in reachable_set])

            # AllSAT loop: block each found model until UNSAT
            slv = Solver()
            slv.add(reach_cstr, fire_geom)

            can_fire_tiles = []
            while slv.check() == sat:
                mdl = slv.model()
                fx, fy = mdl[ex].as_long(), mdl[ey].as_long()
                # Terrain-blocking LOS delegated to the engine
                if engine.check_line_of_sight(fx, fy, tx, ty, e_range, units):
                    can_fire_tiles.append((fx, fy))
                # Block this model: force next solution to be a different tile
                slv.add(Or(ex != fx, ey != fy))

            if not can_fire_tiles:
                continue

            total_w  = sum(_weight(rx, ry) for rx, ry in reachable_set)
            firing_w = sum(_weight(rx, ry) for rx, ry in can_fire_tiles)
            if total_w <= 0:
                continue

            p_fire           = firing_w / total_w
            expected_contrib = p_fire * e_offense
            p_lethal_solo    = p_fire if e_offense >= destroy_threshold else 0.0

            per_enemy_stats.append((expected_contrib, p_lethal_solo))

        if not per_enemy_stats:
            return 0.0, 0.0

        # ──────────────────────────────────────────────────────────────────────
        # PHASE 2 — Z3 Real arithmetic: exact rational probability aggregation
        # ──────────────────────────────────────────────────────────────────────
        opt2 = Optimize()

        z_e_offense  = Real("z_e_offense")
        contrib_vars = []
        survive_prod = Fraction(1)    # Π(1 - p_lethal_solo_i), exact rational

        for idx, (exp_c, p_ls) in enumerate(per_enemy_stats):
            c_frac = Fraction(exp_c).limit_denominator(100_000)
            l_frac = Fraction(p_ls).limit_denominator(100_000)

            cv = Real(f"c_{idx}")
            opt2.add(cv == RatVal(c_frac.numerator, c_frac.denominator))
            opt2.add(cv >= 0)
            contrib_vars.append(cv)

            survive_prod *= (Fraction(1) - l_frac)

        opt2.add(z_e_offense == Sum(contrib_vars))
        opt2.maximize(z_e_offense)     # verifies constraint satisfiability

        if opt2.check() == sat:
            m_out    = opt2.model()
            e_off_z3 = m_out.evaluate(z_e_offense)

            try:
                e_off_f = e_off_z3.numerator_as_long() / e_off_z3.denominator_as_long()
            except Exception:
                e_off_f = float(e_off_z3.as_decimal(8).rstrip("?"))

            sp_frac  = survive_prod.limit_denominator(100_000)
            sp_float = sp_frac.numerator / sp_frac.denominator
            p_lethal = float(max(0.0, min(1.0, 1.0 - sp_float)))

            return float(max(0.0, e_off_f)), p_lethal

        # Z3 unexpectedly failed — fall back to pure Python arithmetic
        e_py  = sum(d[0] for d in per_enemy_stats)
        sp_py = 1.0
        for _, p_ls in per_enemy_stats:
            sp_py *= (1.0 - p_ls)
        return float(e_py), float(max(0.0, 1.0 - sp_py))