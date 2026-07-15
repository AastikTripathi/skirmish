extends Node2D
class_name UnitToken

# Unit variables
var unit_id: String = ""
var side: String = "North" # "North" or "South"
var type: String = "infantry"
var symbol: String = "I"
var faces: Dictionary = {}

# Layout dimensions
const CELL_WIDTH: float = 128.0
const CELL_HEIGHT: float = 64.0
const CUBE_HEIGHT: float = 40.0 # Height of the cube extrusion

# Drawing fonts
var font: Font = ThemeDB.fallback_font

# Visual state tracking
var is_moving: bool = false
var roll_rotation: float = 0.0
var roll_scale_y: float = 1.0

func setup(data: Dictionary) -> void:
	unit_id = data.get("id", "")
	side = data.get("side", "North")
	update_state(data, false) # Initial setup without animation

func update_state(data: Dictionary, animate: bool = true) -> void:
	type = data.get("type", "infantry")
	symbol = data.get("symbol", "I")
	faces = data.get("faces", {"top": symbol, "bottom": "S", "front": "C", "back": "R", "left": "M", "right": "A"})
	
	var grid_pos = Vector2i(data.get("x", 0), data.get("y", 0))
	var target_pixel_pos = grid_to_isometric(grid_pos)
	
	if animate and position != target_pixel_pos:
		animate_move_and_roll(target_pixel_pos)
	else:
		position = target_pixel_pos
		queue_redraw()

func grid_to_isometric(grid_pos: Vector2i) -> Vector2:
	var iso_x = (grid_pos.x - grid_pos.y) * (CELL_WIDTH / 2.0)
	var iso_y = (grid_pos.x + grid_pos.y) * (CELL_HEIGHT / 2.0)
	return Vector2(iso_x, iso_y)

func animate_move_and_roll(target_pos: Vector2) -> void:
	if is_moving:
		return
	is_moving = true
	
	# Determine direction of roll
	var dir_vector = (target_pos - position).normalized()
	
	var tween = create_tween().set_parallel(true)
	
	# 1. Slide position to target
	tween.tween_property(self, "position", target_pos, 0.5)\
		.set_trans(Tween.TRANS_QUAD)\
		.set_ease(Tween.EASE_OUT)
		
	# 2. Roll/Tumble animation (squish and rotate)
	roll_rotation = 0.0
	var target_rotation = PI / 2.0 if dir_vector.x > 0 else -PI / 2.0
	
	tween.tween_property(self, "roll_rotation", target_rotation, 0.5)\
		.set_trans(Tween.TRANS_QUAD)\
		.set_ease(Tween.EASE_OUT)
		
	# Quick bounce/compress on Y scale to show impact of rolling
	roll_scale_y = 1.0
	var scale_tween = create_tween().set_sequence(true)
	scale_tween.tween_property(self, "roll_scale_y", 0.7, 0.25)
	scale_tween.tween_property(self, "roll_scale_y", 1.0, 0.25)
	
	await tween.finished
	
	# Reset animations and redraw flat
	roll_rotation = 0.0
	is_moving = false
	queue_redraw()

func _draw() -> void:
	# Define base colors depending on Player Side
	var primary_color: Color
	if side == "North":
		primary_color = Color(0.2, 0.6, 1.0) # Sleek blue
	else:
		primary_color = Color(1.0, 0.3, 0.3) # Hot red/orange
		
	# Shading colors for 3D faces
	var color_top = primary_color.lightened(0.2)
	var color_right = primary_color.darkened(0.1)
	var color_left = primary_color.darkened(0.3)
	
	# Draw shadow on the ground
	draw_ellipse(Vector2.ZERO, CELL_WIDTH / 3.0, CELL_HEIGHT / 4.0, Color(0, 0, 0, 0.3))
	
	# Apply animations using canvas transforms
	draw_set_transform(Vector2.ZERO, roll_rotation, Vector2(1.0, roll_scale_y))
	
	# Height offset to lift the cube above the ground
	var offset = Vector2(0, -15)
	
	# Visually construct the 3D isometric cube
	# 1. Top face points (Diamond)
	var top_pts = PackedVector2Array([
		offset + Vector2(0, -CELL_HEIGHT / 3.0 - CUBE_HEIGHT),
		offset + Vector2(CELL_WIDTH / 4.0, -CUBE_HEIGHT),
		offset + Vector2(0, CELL_HEIGHT / 3.0 - CUBE_HEIGHT),
		offset + Vector2(-CELL_WIDTH / 4.0, -CUBE_HEIGHT)
	])
	
	# 2. Left face points
	var left_pts = PackedVector2Array([
		top_pts[3],
		top_pts[2],
		top_pts[2] + Vector2(0, CUBE_HEIGHT),
		top_pts[3] + Vector2(0, CUBE_HEIGHT)
	])
	
	# 3. Right face points
	var right_pts = PackedVector2Array([
		top_pts[2],
		top_pts[1],
		top_pts[1] + Vector2(0, CUBE_HEIGHT),
		top_pts[2] + Vector2(0, CUBE_HEIGHT)
	])
	
	# Draw the 3D faces
	draw_polygon(top_pts, PackedColorArray([color_top]))
	draw_polygon(left_pts, PackedColorArray([color_left]))
	draw_polygon(right_pts, PackedColorArray([color_right]))
	
	# Draw outline highlight lines to make details pop
	var outline_color = Color(1, 1, 1, 0.4)
	draw_polyline(PackedVector2Array([top_pts[0], top_pts[1], top_pts[2], top_pts[3], top_pts[0]]), outline_color, 1.5)
	draw_line(top_pts[2], top_pts[2] + Vector2(0, CUBE_HEIGHT), outline_color, 1.5)
	draw_line(top_pts[1], top_pts[1] + Vector2(0, CUBE_HEIGHT), outline_color, 1.5)
	draw_line(top_pts[3], top_pts[3] + Vector2(0, CUBE_HEIGHT), outline_color, 1.5)
	
	# Draw letters on faces
	var top_symbol = faces.get("top", symbol)
	var left_symbol = faces.get("left", "I")
	var right_symbol = faces.get("right", "A")
	
	# Top Face Text
	draw_string(font, top_pts[2] - Vector2(5, 8), top_symbol, HORIZONTAL_ALIGNMENT_CENTER, -1, 16, Color.BLACK)
	# Left Face Text
	draw_string(font, left_pts[1] + Vector2(-15, -10), left_symbol, HORIZONTAL_ALIGNMENT_CENTER, -1, 12, Color.WHITE)
	# Right Face Text
	draw_string(font, right_pts[0] + Vector2(10, -10), right_symbol, HORIZONTAL_ALIGNMENT_CENTER, -1, 12, Color.WHITE)

# Helper function to draw circular shadows
func draw_ellipse(center: Vector2, rx: float, ry: float, color: Color) -> void:
	var points = PackedVector2Array()
	var steps = 16
	for i in range(steps):
		var phi = i * 2 * PI / steps
		points.append(center + Vector2(cos(phi) * rx, sin(phi) * ry))
	draw_polygon(points, PackedColorArray([color]))
