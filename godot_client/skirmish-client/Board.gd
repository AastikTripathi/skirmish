extends Node2D
class_name Board

# Dimensions of each isometric diamond cell
const CELL_WIDTH: float = 128.0
const CELL_HEIGHT: float = 64.0

# Store the active state data received from the server
var current_state: Dictionary = {}
var cols: int = 10
var rows: int = 10

# Color palette
var color_plain: Color = Color(0.15, 0.22, 0.20, 0.7)     # Deep dark teal/green
var color_mountain: Color = Color(0.35, 0.31, 0.26, 0.9)  # Slate brown/grey
var color_arsenal: Color = Color(0.9, 0.8, 0.3, 0.9)     # Bright gold
var color_fortress: Color = Color(0.7, 0.5, 0.2, 0.9)    # Bronze
var color_grid_line: Color = Color(0.3, 0.5, 0.4, 0.3)   # Subtle grid line
var color_loc_north: Color = Color(0.2, 0.6, 1.0, 0.4)   # Blue energy glow
var color_loc_south: Color = Color(1.0, 0.3, 0.3, 0.4)   # Red energy glow

# Pre-defined terrain maps matching your server constants
var mountains: Array = [
	Vector2i(9, 2), Vector2i(10, 2), Vector2i(11, 2), Vector2i(12, 2),
	Vector2i(9, 3), Vector2i(9, 4), Vector2i(9, 6), Vector2i(9, 7), Vector2i(9, 8),
	Vector2i(10, 13), Vector2i(11, 13), Vector2i(12, 13), Vector2i(13, 13), Vector2i(14, 13), Vector2i(15, 13),
	Vector2i(15, 15), Vector2i(15, 16), Vector2i(15, 17)
]
var arsenals_north: Array = [Vector2i(4, 0)]
var arsenals_south: Array = [Vector2i(5, 9)]
var fortresses: Array = [Vector2i(4, 0), Vector2i(5, 9)]

func _ready() -> void:
	# Center the board on screen
	position = Vector2(576, 150)

# Translate grid coordinates (x, y) to isometric screen coordinates
func grid_to_isometric(grid_pos: Vector2i) -> Vector2:
	var iso_x = (grid_pos.x - grid_pos.y) * (CELL_WIDTH / 2.0)
	var iso_y = (grid_pos.x + grid_pos.y) * (CELL_HEIGHT / 2.0)
	return Vector2(iso_x, iso_y)

# Keep track of active unit tokens by their ID
var unit_tokens: Dictionary = {}

# Redraw the board when state updates
func update_board(state_data: Dictionary) -> void:
	current_state = state_data
	cols = state_data.get("cols", 10)
	rows = state_data.get("rows", 10)
	
	# Update unit positions and spawn new tokens
	_sync_units(state_data.get("units", []))
	
	queue_redraw() # Tells Godot to trigger _draw() again on the next frame

func _sync_units(units_list: Array) -> void:
	var active_ids: Array = []
	
	for unit_data in units_list:
		var uid = unit_data.get("id")
		active_ids.append(uid)
		
		if unit_tokens.has(uid):
			# Unit already exists, update it (handles movement sliding & rolling animations)
			unit_tokens[uid].update_state(unit_data, true)
		else:
			# Spawn a new visual token for the unit
			var token = Node2D.new()
			token.set_script(load("res://UnitToken.gd"))
			add_child(token)
			token.setup(unit_data)
			unit_tokens[uid] = token
			
	# Remove destroyed units
	for uid in unit_tokens.keys():
		if not uid in active_ids:
			var token = unit_tokens[uid]
			unit_tokens.erase(uid)
			token.queue_free()


func _draw() -> void:
	# Draw cells row by row
	for y in range(rows):
		for x in range(cols):
			var cell = Vector2i(x, y)
			var center = grid_to_isometric(cell)
			
			# Define the 4 points of the isometric diamond
			var points = PackedVector2Array([
				center + Vector2(0, -CELL_HEIGHT / 2.0), # Top
				center + Vector2(CELL_WIDTH / 2.0, 0),  # Right
				center + Vector2(0, CELL_HEIGHT / 2.0),  # Bottom
				center + Vector2(-CELL_WIDTH / 2.0, 0)  # Left
			])
			
			# Decide cell fill color based on terrain
			var fill_color = color_plain
			if cell in mountains:
				fill_color = color_mountain
			elif cell in arsenals_north or cell in arsenals_south:
				fill_color = color_arsenal
			elif cell in fortresses:
				fill_color = color_fortress
				
			# Draw cell background
			draw_polygon(points, PackedColorArray([fill_color]))
			
			# Draw cell grid outline
			draw_polyline(PackedVector2Array([points[0], points[1], points[2], points[3], points[0]]), color_grid_line, 1.0)
