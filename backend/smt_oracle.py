from z3 import *

class SmtTacticalOracle:
    def __init__(self, cols=10, rows=10):
        self.cols = cols
        self.rows = rows
        
        # Symbol definitions mapped to integer codes
        self.SYM_CODES = {"I": 0, "A": 1, "C": 2, "R": 3, "M": 4, "S": 5}
        self.CODE_TO_SYM = {v: k for k, v in self.SYM_CODES.items()}

    def get_symbol_code(self, symbol: str) -> int:
        return self.SYM_CODES.get(symbol, 0)

    def symbolic_rotate_cube(self, current_top, current_bottom, current_front, current_back, current_left, current_right, dx, dy):
        """
        Pure mathematical translation of rotate_cube_faces using Z3 conditional execution.
        Returns symbolic expressions for the next (top, bottom, front, back, left, right).
        """
        # East Roll (dx > 0, dy == 0)
        east_top    = current_left
        east_bottom = current_right
        east_left   = current_bottom
        east_right  = current_top
        east_front  = current_front
        east_back   = current_back

        # West Roll (dx < 0, dy == 0)
        west_top    = current_right
        west_bottom = current_left
        west_left   = current_top
        west_right  = current_bottom
        west_front  = current_front
        west_back   = current_back

        # South Roll (dx == 0, dy > 0)
        south_top    = current_back
        south_bottom = current_front
        south_front  = current_top
        south_back   = current_bottom
        south_left   = current_left
        south_right  = current_right

        # North Roll (dx == 0, dy < 0)
        north_top    = current_front
        north_bottom = current_back
        north_front  = current_bottom
        north_back   = current_top
        north_left   = current_left
        north_right  = current_right

        # Bind the vectors conditionally depending on symbolic move inputs
        next_top = If(And(dx > 0, dy == 0), east_top,
                   If(And(dx < 0, dy == 0), west_top,
                   If(And(dx == 0, dy > 0), south_top,
                   If(And(dx == 0, dy < 0), north_top, current_top))))

        next_bottom = If(And(dx > 0, dy == 0), east_bottom,
                      If(And(dx < 0, dy == 0), west_bottom,
                      If(And(dx == 0, dy > 0), south_bottom,
                      If(And(dx == 0, dy < 0), north_bottom, current_bottom))))

        next_front = If(And(dx > 0, dy == 0), east_front,
                     If(And(dx < 0, dy == 0), west_front,
                     If(And(dx == 0, dy > 0), south_front,
                     If(And(dx == 0, dy < 0), north_front, current_front))))

        next_back = If(And(dx > 0, dy == 0), east_back,
                    If(And(dx < 0, dy == 0), west_back,
                    If(And(dx == 0, dy > 0), south_back,
                    If(And(dx == 0, dy < 0), north_back, current_back))))

        next_left = If(And(dx > 0, dy == 0), east_left,
                    If(And(dx < 0, dy == 0), west_left,
                    If(And(dx == 0, dy > 0), south_left,
                    If(And(dx == 0, dy < 0), north_left, current_left))))

        next_right = If(And(dx > 0, dy == 0), east_right,
                     If(And(dx < 0, dy == 0), west_right,
                     If(And(dx == 0, dy > 0), south_right,
                     If(And(dx == 0, dy < 0), north_right, current_right))))

        return next_top, next_bottom, next_front, next_back, next_left, next_right



    

def solve_rotation_path(self, current_faces: dict, allowed_moves_budget: int, target_top_symbol: str) -> list:
        """
        Asks Z3 to find a valid sequence of grid steps (dx, dy) 
        that puts target_top_symbol on the top face.
        """
        solver = Solver()
        
        # Convert initial face strings to int codes
        t = self.get_symbol_code(current_faces.get("top", "I"))
        b = self.get_symbol_code(current_faces.get("bottom", "S"))
        f = self.get_symbol_code(current_faces.get("front", "C"))
        bk = self.get_symbol_code(current_faces.get("back", "R"))
        l = self.get_symbol_code(current_faces.get("left", "M"))
        r = self.get_symbol_code(current_faces.get("right", "A"))
        
        target_code = self.get_symbol_code(target_top_symbol)

        # Create step array variables for the path horizon
        steps_dx = [Int(f'step_{i}_dx') for i in range(allowed_moves_budget)]
        steps_dy = [Int(f'step_{i}_dy') for i in range(allowed_moves_budget)]

        # Restrict movement values to valid single grid steps
        for i in range(allowed_moves_budget):
            # Steps must be either 0, 1, or -1
            solver.add(steps_dx[i] >= -1, steps_dx[i] <= 1)
            solver.add(steps_dy[i] >= -1, steps_dy[i] <= 1)
            # Prevent diagonal combined step parsing bugs by forcing orthogonal components per sub-step
            solver.add(If(steps_dx[i] != 0, steps_dy[i] == 0, True))
            solver.add(Not(And(steps_dx[i] == 0, steps_dy[i] == 0))) # Must actually move

        # Unroll the transition function through the step horizon loop
        curr_t, curr_b, curr_f, curr_bk, curr_l, curr_r = t, b, f, bk, l, r
        for i in range(allowed_moves_budget):
            curr_t, curr_b, curr_f, curr_bk, curr_l, curr_r = self.symbolic_rotate_cube(
                curr_t, curr_b, curr_f, curr_bk, curr_l, curr_r, 
                steps_dx[i], steps_dy[i]
            )

        # Assert final target condition to check satisfiability
        solver.add(curr_t == target_code)

        if solver.check() == sat:
            m = solver.model()
            path_plan = []
            for i in range(allowed_moves_budget):
                path_plan.append({
                    "dx": m[steps_dx[i]].as_long(),
                    "dy": m[steps_dy[i]].as_long()
                })
            print(f"🔮 [SMT Oracle] Path found to activate {target_top_symbol}: {path_plan}")
            return path_plan
        
        print(f"❌ [SMT Oracle] Impossible to isolate face {target_top_symbol} within {allowed_moves_budget} steps.")
        return []


