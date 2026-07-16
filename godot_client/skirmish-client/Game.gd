extends Node3D

# ── Nodes ─────────────────────────────────────────────────────────────────
@onready var camera:     Camera3D   = $Camera3D
@onready var board_node: Node3D     = $Board
@onready var units_node: Node3D     = $Units
@onready var status_lbl: Label      = $UI/StatusLabel
@onready var hud:        Control    = $UI/HUD

# ── Game state ─────────────────────────────────────────────────────────────
var current_state:    Dictionary = {}
var selected_unit_id: String     = ""
var unit_tokens:      Dictionary = {}   # uid → UnitToken3D
var last_combat_seen: Dictionary = {}   # track to avoid re-triggering
var mine_markers:     Dictionary = {}   # "x_y" → MeshInstance3D
var engine_pid: int = -1
var active_transformation_menu: Control = null

const COLS: int = 10
const ROWS: int = 10

# ── Camera ─────────────────────────────────────────────────────────────────
const ISO_PITCH: float  = 35.264
const ISO_DIST:  float  = 22.0
const BOARD_CTR: Vector3 = Vector3(4.5, 0.0, 4.5)
var   cam_yaw:        float = 45.0
var   cam_yaw_target: float = 45.0
var   cam_yaw_from:   float = 45.0
var   cam_yaw_t:      float = 1.0   # 0..1, 1 = done
var   cam_zoom:       float = 18.0

# ── Tile overlay meshes ────────────────────────────────────────────────────
var tile_meshes:      Dictionary = {}   # Vector2i → MeshInstance3D (base tile)
var overlay_meshes:   Dictionary = {}   # Vector2i → MeshInstance3D (overlay)

# ── Materials ──────────────────────────────────────────────────────────────
var mat_tile:     StandardMaterial3D
var mat_mountain: StandardMaterial3D
var mat_swamp:    StandardMaterial3D
var mat_select:   StandardMaterial3D
var mat_move:     StandardMaterial3D   # reachable move tiles
var mat_attack:   StandardMaterial3D   # enemy attack tiles
var mat_loc_n:    StandardMaterial3D   # North LoC
var mat_loc_s:    StandardMaterial3D   # South LoC
var mat_arsenal:  StandardMaterial3D
var mat_fortress: StandardMaterial3D
var mat_mine:     StandardMaterial3D

	
	
func _ready() -> void:
	# ── AUTOMATICALLY SPAWN PYTHON BACKEND ENGINE MODULE ──
	# Toggles extension matching your active runtime system export target
	var engine_filename = "server.exe" if OS.has_feature("windows") else "server"
	var engine_path: String = OS.get_executable_path().get_base_dir().path_join(engine_filename)
	
	if FileAccess.file_exists(engine_path):
		# Spawns the compiled server quietly without flashing a visual command terminal
		engine_pid = OS.create_process(engine_path, [])
		print("Python background engine started with PID: ", engine_pid)
	else:
		# If running in the editor directly, look locally inside your backend workspace folder
		var local_debug_path = OS.get_executable_path().get_base_dir().path_join("../../backend/dist").path_join(engine_filename)
		if FileAccess.file_exists(local_debug_path):
			engine_pid = OS.create_process(local_debug_path, [])
		else:
			push_warning("Background engine binary not spotted next to executable. Ensure it is copied over before sharing.")

	# ── Existing Ready Logic Continuations ──
	_build_materials()
	_build_board()
	_position_camera()
	_build_hud()

	NetworkManager.connected_to_server.connect(_on_connected)
	NetworkManager.disconnected_from_server.connect(_on_disconnected)
	NetworkManager.state_updated.connect(_on_state_updated)
	NetworkManager.error_received.connect(_on_error_received)
	NetworkManager.room_id     = "skirmish_room"
	NetworkManager.player_name = "GodotCommander"
	NetworkManager.player_side = "North"
	NetworkManager.vs_ai       = true
	NetworkManager.connect_to_room()
	status_lbl.text = "Connecting…"

	var env: Environment = $WorldEnvironment.environment
	env.ambient_light_source = Environment.AMBIENT_SOURCE_BG
	env.ambient_light_energy = 0.25 

	env.ssao_enabled = true
	env.ssao_radius = 0.5
	env.ssao_intensity = 2.0

	env.glow_enabled = true
	env.glow_normalized = true
	env.glow_intensity = 0.4
	env.glow_bloom = 0.15	

# ────────────────────────────────────────────────────────────────────────────
# Materials
# ────────────────────────────────────────────────────────────────────────────
# Refactored material constructor inside Game.gd
func _make_mat(color: Color, alpha: float = 1.0, emit: Color = Color.BLACK, emit_e: float = 0.0) -> StandardMaterial3D:
	var m = StandardMaterial3D.new()
	m.albedo_color = Color(color.r, color.g, color.b, alpha)
	if alpha < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	
	# --- Stone Look Tweaks ---
	m.roughness = 0.85            # Rough slate/granite surface texture
	m.metallic = 0.1              # Minor natural mineral shine
	m.specular = 0.3              # Subdued reflection highlights
	
	# If you export a stone texture set from Material Maker, load it like this:
	# m.albedo_texture = preload("res://assets/textures/stone_albedo.png")
	# m.normal_enabled = true
	# m.normal_texture = preload("res://assets/textures/stone_normal.png")
	
	if emit != Color.BLACK:
		m.emission_enabled = true
		m.emission = emit
		m.emission_energy_multiplier = emit_e
	return m



func _build_materials() -> void:
	mat_tile     = _make_mat(Color(0.17, 0.23, 0.21))
	mat_mountain = _make_mat(Color(0.44, 0.40, 0.35))
	mat_swamp    = _make_mat(Color(0.20, 0.32, 0.18))
	mat_select   = _make_mat(Color(1.0, 0.88, 0.2, 0.85),  0.85, Color(1.0, 0.85, 0.0), 1.2)
	mat_move     = _make_mat(Color(0.2, 0.85, 0.5, 0.70),  0.70, Color(0.0, 0.9, 0.4), 0.5)
	mat_attack   = _make_mat(Color(1.0, 0.25, 0.25, 0.70), 0.70, Color(1.0, 0.1, 0.1), 0.5)
	mat_loc_n    = _make_mat(Color(0.20, 0.50, 1.0, 0.45),  0.45)
	mat_loc_s    = _make_mat(Color(1.0, 0.30, 0.25, 0.45),  0.45)
	mat_arsenal  = _make_mat(Color(0.85, 0.75, 0.20, 0.80), 0.80)
	mat_fortress = _make_mat(Color(0.60, 0.60, 0.70, 0.80), 0.80)
	mat_mine     = _make_mat(Color(0.90, 0.45, 0.10, 0.80), 0.80)

# ────────────────────────────────────────────────────────────────────────────
# Board
# ────────────────────────────────────────────────────────────────────────────
func _build_board() -> void:
	# Base tiles
	for x in range(COLS):
		for y in range(ROWS):
			var mi := MeshInstance3D.new()
			var bm := BoxMesh.new()
			bm.size = Vector3(0.96, 0.06, 0.96)
			mi.mesh = bm
			mi.material_override = mat_tile
			mi.position = Vector3(x, 0.0, y)
			board_node.add_child(mi)
			tile_meshes[Vector2i(x, y)] = mi

			# Overlay plane (slightly above base tile)
			var ov := MeshInstance3D.new()
			var qm := QuadMesh.new()
			qm.size = Vector2(0.94, 0.94)
			ov.mesh = qm
			ov.rotation_degrees = Vector3(-90, 0, 0)
			ov.position = Vector3(x, 0.042, y)
			ov.visible = false
			board_node.add_child(ov)
			overlay_meshes[Vector2i(x, y)] = ov

	# Grid lines
	var line_mat := _make_mat(Color(0.50, 0.65, 0.58, 0.35), 0.35)
	for x in range(COLS + 1):
		var lm := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(0.02, 0.08, float(ROWS))
		lm.mesh = bm
		lm.material_override = line_mat
		lm.position = Vector3(x - 0.5, 0.0, float(ROWS) * 0.5 - 0.5)
		board_node.add_child(lm)
	for y in range(ROWS + 1):
		var lm := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(float(COLS), 0.08, 0.02)
		lm.mesh = bm
		lm.material_override = line_mat
		lm.position = Vector3(float(COLS) * 0.5 - 0.5, 0.0, y - 0.5)
		board_node.add_child(lm)

# ────────────────────────────────────────────────────────────────────────────
# HUD
# ────────────────────────────────────────────────────────────────────────────
var lbl_turn:      Label
var lbl_moves:     Label
var lbl_selected:  Label
var btn_end_turn:  Button
var btn_undo:      Button
var btn_restart:   Button

func _build_hud() -> void:
	var panel       = PanelContainer.new()
	var panel_style = StyleBoxFlat.new()
	panel_style.bg_color            = Color(0.06, 0.07, 0.10, 0.88)
	panel_style.border_color        = Color(0.25, 0.35, 0.50, 1.0)
	panel_style.set_border_width_all(2)
	panel_style.set_corner_radius_all(8)
	panel.add_theme_stylebox_override("panel", panel_style)
	panel.set_anchors_preset(Control.PRESET_TOP_LEFT)
	panel.set_offset(SIDE_LEFT,   12)
	panel.set_offset(SIDE_TOP,    12)
	panel.set_offset(SIDE_RIGHT,  260)
	panel.set_offset(SIDE_BOTTOM, 260)
	hud.add_child(panel)

	var vbox = VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 10)
	panel.add_child(vbox)

	# Title
	var title = Label.new()
	title.text = "⚔  SKIRMISH"
	title.add_theme_font_size_override("font_size", 18)
	title.add_theme_color_override("font_color", Color(1.0, 0.85, 0.3))
	vbox.add_child(title)

	vbox.add_child(HSeparator.new())

	lbl_turn = _hud_label("Turn: —")
	vbox.add_child(lbl_turn)
	lbl_moves = _hud_label("Moves left: —")
	vbox.add_child(lbl_moves)
	lbl_selected = _hud_label("Selected: none")
	lbl_selected.add_theme_color_override("font_color", Color(0.4, 1.0, 0.6))
	vbox.add_child(lbl_selected)

	vbox.add_child(HSeparator.new())

	# Legend
	var leg = Label.new()
	leg.text = "🟢 Move range\n🔴 Attack range\n🔵 N-LoC  🔴 S-LoC"
	leg.add_theme_font_size_override("font_size", 11)
	leg.add_theme_color_override("font_color", Color(0.75, 0.80, 0.88))
	vbox.add_child(leg)

	vbox.add_child(HSeparator.new())

	btn_end_turn = _hud_button("⏭  End Turn", Color(0.18, 0.55, 0.22))
	btn_end_turn.pressed.connect(_on_end_turn)
	vbox.add_child(btn_end_turn)

	btn_undo = _hud_button("↩  Undo", Color(0.30, 0.30, 0.18))
	btn_undo.pressed.connect(_on_undo)
	vbox.add_child(btn_undo)

	btn_restart = _hud_button("🔄  Restart", Color(0.35, 0.12, 0.12))
	btn_restart.pressed.connect(_on_restart)
	vbox.add_child(btn_restart)

	vbox.add_child(HSeparator.new())

	var ctrl_lbl = Label.new()
	ctrl_lbl.text = "Q / E — Rotate view\nScroll — Zoom"
	ctrl_lbl.add_theme_font_size_override("font_size", 11)
	ctrl_lbl.add_theme_color_override("font_color", Color(0.55, 0.60, 0.70))
	vbox.add_child(ctrl_lbl)

func _hud_label(txt: String) -> Label:
	var l = Label.new()
	l.text = txt
	l.add_theme_font_size_override("font_size", 13)
	return l

func _hud_button(txt: String, col: Color) -> Button:
	var b = Button.new()
	b.text = txt
	var s = StyleBoxFlat.new()
	s.bg_color = col
	s.set_corner_radius_all(5)
	s.set_content_margin_all(6)
	b.add_theme_stylebox_override("normal", s)
	b.add_theme_font_size_override("font_size", 13)
	return b

# ────────────────────────────────────────────────────────────────────────────
# Camera
# ────────────────────────────────────────────────────────────────────────────
func _cam_pos_for_yaw(yaw_deg: float) -> Vector3:
	var pitch  = deg_to_rad(ISO_PITCH)
	var yaw    = deg_to_rad(yaw_deg)
	return BOARD_CTR + Vector3(sin(yaw)*cos(pitch), sin(pitch), cos(yaw)*cos(pitch)) * ISO_DIST

func _position_camera(anim: bool = false) -> void:
	var tgt = _cam_pos_for_yaw(cam_yaw)
	if anim:
		cam_yaw_from   = cam_yaw
		cam_yaw_target = cam_yaw
		cam_yaw_t      = 0.0   # _process will drive the lerp
	else:
		camera.position = tgt
		camera.look_at(BOARD_CTR, Vector3.UP)
	
	# PERSPECTIVE FIX: Set fov instead of size
	camera.fov = cam_zoom

func _start_cam_rotate(delta_deg: float) -> void:
	cam_yaw_from   = cam_yaw
	cam_yaw_target = cam_yaw + delta_deg
	cam_yaw        = cam_yaw_target   # final value
	cam_yaw_t      = 0.0

func _process(delta: float) -> void:
	if cam_yaw_t < 1.0:
		cam_yaw_t = min(cam_yaw_t + delta / 0.35, 1.0)
		var cur_yaw = lerp(cam_yaw_from, cam_yaw_target, cam_yaw_t)
		camera.position = _cam_pos_for_yaw(cur_yaw)
		camera.look_at(BOARD_CTR, Vector3.UP)
	# Keep face labels always oriented toward camera
	for uid in unit_tokens:
		if is_instance_valid(unit_tokens[uid]):
			unit_tokens[uid].update_facing(camera.global_position)
			
			
func _notification(what: int) -> void:
	# Listens for system windows close instructions
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		if engine_pid != -1:
			OS.kill(engine_pid)
			print("Python backend process killed safely.")
		
		# Allow Godot to exit the program tree cleanly
		get_tree().quit()

# ────────────────────────────────────────────────────────────────────────────
# Input
# ────────────────────────────────────────────────────────────────────────────
func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if   event.keycode == KEY_Q:      _start_cam_rotate(-90.0)
		elif event.keycode == KEY_E:      _start_cam_rotate( 90.0)
		elif event.keycode == KEY_ESCAPE: _deselect()

	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			cam_zoom = max(20.0, cam_zoom - 2.0)
			camera.fov = cam_zoom
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			cam_zoom = min(60.0, cam_zoom + 2.0)
			camera.fov = cam_zoom
		elif event.button_index == MOUSE_BUTTON_LEFT:
			# First check unit tokens via raycasting 3D
			var space = get_world_3d().direct_space_state
			var from  = camera.project_ray_origin(event.position)
			var to    = from + camera.project_ray_normal(event.position) * 200.0
			var query = PhysicsRayQueryParameters3D.create(from, to)
			var hit   = space.intersect_ray(query)
			var cell  = Vector2i(-1, -1)
			if hit and hit.has("collider"):
				# find which unit token owns this collider
				var node = hit["collider"]
				while node and not (node is UnitToken3D):
					node = node.get_parent()
				if node is UnitToken3D:
					_handle_unit_click(node)
					return
			# Fallback: raycast to y=0 plane
			cell = _screen_to_grid(event.position)
			if cell != Vector2i(-1, -1):
				_handle_tile_click(cell)

func _screen_to_grid(screen_pos: Vector2) -> Vector2i:
	var from = camera.project_ray_origin(screen_pos)
	var dir  = camera.project_ray_normal(screen_pos)
	if abs(dir.y) < 0.001: return Vector2i(-1, -1)
	var t    = -from.y / dir.y
	var hit  = from + dir * t
	var gx   = int(round(hit.x))
	var gy   = int(round(hit.z))
	if gx >= 0 and gx < COLS and gy >= 0 and gy < ROWS:
		return Vector2i(gx, gy)
	return Vector2i(-1, -1)

#func _handle_unit_click(token: Node3D) -> void:
	#var uid = token.unit_id
	#var u   = _find_unit(uid)
	#if not u: return
	#if u.get("side") == NetworkManager.player_side:
		#selected_unit_id = uid
		#_refresh_overlays()
	#else:
		#if selected_unit_id != "":
			#NetworkManager.send_action({"action": "attack", "x": u.get("x"), "y": u.get("y")})
			#_deselect()
func _handle_unit_click(token: Node3D) -> void:
	# GUARD: Prevent clicking or selecting deactivated/stranded blocks entirely
	if token is UnitToken3D and token.stranded:
		return

	var uid = token.unit_id
	var u   = _find_unit(uid)
	if not u: return
	
	# If the clicked unit is on the player's side, select it
	if u.get("side") == NetworkManager.player_side:
		selected_unit_id = uid
		_refresh_overlays()
	# If it's an enemy unit, try to attack it with the currently selected unit
	else:
		if selected_unit_id != "":
			NetworkManager.send_action({"action": "attack", "x": u.get("x"), "y": u.get("y")})
			_deselect()
			
			

		
		
func _handle_tile_click(cell: Vector2i) -> void:
	# Is there a unit on this tile?
	var ux = -1; var uy = -1
	for u in current_state.get("units", []):
		if u.get("x") == cell.x and u.get("y") == cell.y:
			ux = u.get("x"); uy = u.get("y")
			
			# Player's own unit
			if u.get("side") == NetworkManager.player_side:
				var uid = u.get("id")
				# GUARD: Do not select this unit if its physical token is marked as stranded
				if unit_tokens.has(uid) and unit_tokens[uid].stranded:
					return
					
				selected_unit_id = uid
				_refresh_overlays()
				return
			# Enemy unit
			else:
				if selected_unit_id != "":
					NetworkManager.send_action({"action": "attack", "x": cell.x, "y": cell.y})
					_deselect()
				return
				
	# Empty tile — move
	#if selected_unit_id != "":
		#NetworkManager.send_action({"action": "move", "unitId": selected_unit_id, "x": cell.x, "y": cell.y})
		#_deselect()
	# Empty tile — move + optional face transformation
	# Empty tile — move
	if selected_unit_id != "":
		if Input.is_key_pressed(KEY_F):
			# Immediately calculate and commit the physical roll action without pausing
			_execute_immediate_transform_move(cell)
		else:
			# Execute normal flat sliding action instantly
			NetworkManager.send_action({
				"action": "move",
				"unitId": selected_unit_id,
				"x": cell.x,
				"y": cell.y,
				"transform_to": null
			})
			_deselect()

func _deselect() -> void:
	selected_unit_id = ""
	_refresh_overlays()

func _find_unit(uid: String) -> Dictionary:
	for u in current_state.get("units", []):
		if u.get("id") == uid: return u
	return {}

# ────────────────────────────────────────────────────────────────────────────
# State update
# ────────────────────────────────────────────────────────────────────────────

func _on_state_updated(state_data: Dictionary) -> void:
	current_state = state_data
	
	# 1. Find which mines exploded in this turn before updating anything
	var exploded_mines: Array[Vector2i] = []
	var current_mine_keys: Array = []
	for mine in state_data.get("mines", []):
		current_mine_keys.append("%d_%d" % [mine.get("x", 0), mine.get("y", 0)])
	
	for key in mine_markers.keys():
		if key not in current_mine_keys:
			var parts = key.split("_")
			if parts.size() == 2:
				exploded_mines.append(Vector2i(int(parts[0]), int(parts[1])))

	# 2. Sync units and pass the exploded mines list to handle sequenced deaths
	_sync_units(state_data, exploded_mines)
	
	# 3. Sync visual mine markers on the board
	_sync_mines(state_data)
	
	_update_hud(state_data)
	_refresh_overlays()
	_play_combat_anim(state_data)
	_check_winner(state_data)

func _play_combat_anim(st: Dictionary) -> void:
	var lc = st.get("lastCombat")
	if not lc or lc == last_combat_seen: return
	last_combat_seen = lc
	var ax = lc.get("attackerX", -1)
	var ay = lc.get("attackerY", -1)
	var tx = lc.get("targetX",  -1)
	var ty = lc.get("targetY",  -1)
	var result = lc.get("result", "FAIL")
	# Find the attacker token by position (before it potentially moved)
	for uid in unit_tokens:
		var tok: UnitToken3D = unit_tokens[uid]
		if int(round(tok.position.x)) == ax and int(round(tok.position.z)) == ay:
			tok.play_ram_attack(Vector3(tx, tok.position.y, ty))
	# Shake the defender if it survived
	if result != "DESTROY":
		for uid in unit_tokens:
			var tok: UnitToken3D = unit_tokens[uid]
			if int(round(tok.position.x)) == tx and int(round(tok.position.z)) == ty:
				tok.play_hit_shake()

			
			
func _sync_units(state_data: Dictionary, exploded_mines: Array[Vector2i]) -> void:
	var seen: Array = []
	var connected_ids: Array = state_data.get("connectedUnitIds", [])
	
	# Update surviving units
	for u in state_data.get("units", []):
		var uid = u.get("id", "")
		seen.append(uid)
		if unit_tokens.has(uid):
			unit_tokens[uid].update_state(u)
		else:
			var tok = preload("res://UnitToken3D.gd").new()
			units_node.add_child(tok)
			tok.setup(u)
			unit_tokens[uid] = tok
		unit_tokens[uid].set_stranded(uid not in connected_ids)
		
	# Handle dying units with proper animation sequencing
	for uid in unit_tokens.keys():
		if uid not in seen:
			var tok = unit_tokens[uid]
			unit_tokens.erase(uid) # Remove from active tracking immediately
			
			# Check if this unit was the one that stepped on an exploded mine
			var matched_mine: Vector2i = Vector2i(-1, -1)
			for mine_pos in exploded_mines:
				# A unit triggers a mine by stepping directly onto its coordinates
				# Chebyshev distance check (adjacent/diagonal) or direct check to find the path
				var dist_x = abs(tok.position.x - mine_pos.x)
				var dist_z = abs(tok.position.z - mine_pos.y)
				if dist_x <= 2.0 and dist_z <= 2.0: # Matches movement range
					matched_mine = mine_pos
					break
			
			if matched_mine != Vector2i(-1, -1):
				# SEQUENCED MINE DEATH FLOW:
				_sequence_mine_death(tok, matched_mine)
			else:
				# Normal instant death (e.g., destroyed by combat/attacks)
				tok.play_death()
				
func _sequence_mine_death(tok: UnitToken3D, mine_pos: Vector2i) -> void:
	# 1. Force the unit to run its tumbling/rolling animation to the mine tile
	await tok._animate_move(Vector3(mine_pos.x, 0.0, mine_pos.y))
	
	# 2. Spawn the vertical laser strike directly on the target tile
	_spawn_laser_beam(mine_pos.x, mine_pos.y)
	
	# 3. Play the death dissolution animation inside the beam
	tok.play_death()

			
			
func _sync_mines(state_data: Dictionary) -> void:
	var current_keys: Array = []
	for mine in state_data.get("mines", []):
		var mx = mine.get("x", 0)
		var my = mine.get("y", 0)
		var key = "%d_%d" % [mx, my]
		current_keys.append(key)
		if not mine_markers.has(key):
			mine_markers[key] = _spawn_mine_marker(mx, my)
	
	# Remove cleared mines and fire the vertical strike laser beam
	for key in mine_markers.keys():
		if key not in current_keys:
			# Parse coordinates to place the strike beam
			var parts = key.split("_")
			if parts.size() == 2:
				var mx = int(parts[0])
				var my = int(parts[1])
				_spawn_laser_beam(mx, my) # <-- Run the laser strike!
			
			mine_markers[key].queue_free()
			mine_markers.erase(key)

# Clean, dedicated laser spawner
func _spawn_laser_beam(x: int, y: int) -> void:
	var laser_script = preload("res://LaserBeam3D.gd")
	var laser = Node3D.new()
	laser.set_script(laser_script)
	
	# Position the center of the beam's base flat on the targeted tile
	laser.position = Vector3(x, 0.0, y)
	board_node.add_child(laser)

func _spawn_mine_marker(mx: int, my: int) -> Node3D:
	var root    = Node3D.new()
	root.position = Vector3(mx, 0.0, my)
	board_node.add_child(root)
	# Hazard diamond: 4-pointed star via small rotated boxes
	var haz_mat = StandardMaterial3D.new()
	haz_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	haz_mat.albedo_color = Color(0.95, 0.55, 0.05)   # warning orange
	for i in range(4):
		var mi  = MeshInstance3D.new()
		var bm  = BoxMesh.new()
		bm.size = Vector3(0.44, 0.06, 0.12)
		mi.mesh = bm
		mi.material_override = haz_mat
		mi.rotation_degrees  = Vector3(0, i * 45, 0)
		mi.position          = Vector3(0, 0.06, 0)
		root.add_child(mi)
	# Pulse scale tween
	var tw = root.create_tween().set_loops()
	tw.tween_property(root, "scale", Vector3(1.15, 1.3, 1.15), 0.6).set_trans(Tween.TRANS_SINE)
	tw.tween_property(root, "scale", Vector3(0.90, 0.8, 0.90), 0.6).set_trans(Tween.TRANS_SINE)
	return root

func _update_hud(st: Dictionary) -> void:
	var turn = st.get("turn", "?")
	lbl_turn.text  = "Turn: %s" % turn
	lbl_turn.add_theme_color_override("font_color",
		Color(0.3, 0.7, 1.0) if turn == "North" else Color(1.0, 0.4, 0.4))
	lbl_moves.text = "Moves left: %s" % str(st.get("movesLeft", "?"))
	if selected_unit_id != "":
		var u = _find_unit(selected_unit_id)
		lbl_selected.text = "Selected: %s" % u.get("id", "none")
	else:
		lbl_selected.text = "Selected: none"
	btn_undo.disabled     = not st.get("canUndo", false)
	btn_end_turn.disabled = (st.get("turn","") != NetworkManager.player_side)

# ────────────────────────────────────────────────────────────────────────────
# Overlay rendering (LoC, move tiles, attack tiles, special tiles)
# ────────────────────────────────────────────────────────────────────────────
func _refresh_overlays() -> void:
	# Hide all overlays first
	for cell in overlay_meshes:
		overlay_meshes[cell].visible = false

	var st = current_state

	# ── Lines of Communication ──────────────────────────────────────────────
	var loc = st.get("linesOfCommunication", {})
	for xy in loc.get("North", []):
		_set_overlay(Vector2i(xy[0], xy[1]), mat_loc_n)
	for xy in loc.get("South", []):
		_set_overlay(Vector2i(xy[0], xy[1]), mat_loc_s)

	# ── Arsenals, Fortresses, Mines ─────────────────────────────────────────
	for xy in st.get("arsenals", {}).get("North", []):
		_set_overlay(Vector2i(xy[0], xy[1]), mat_arsenal)
	for xy in st.get("arsenals", {}).get("South", []):
		_set_overlay(Vector2i(xy[0], xy[1]), mat_arsenal)
	for xy in st.get("fortresses", []):
		_set_overlay(Vector2i(xy[0], xy[1]), mat_fortress)
	for mine in st.get("mines", []):
		_set_overlay(Vector2i(mine.get("x",0), mine.get("y",0)), mat_mine)

	# ── Base tile terrain ───────────────────────────────────────────────────
	for cell in tile_meshes:
		tile_meshes[cell].material_override = mat_tile

	# ── Move / Attack range for selected unit ───────────────────────────────
	if selected_unit_id != "":
		var sel_unit = _find_unit(selected_unit_id)
		if sel_unit:
			_set_overlay(Vector2i(sel_unit.get("x"), sel_unit.get("y")), mat_select)
			_compute_and_show_range(sel_unit)

func _set_overlay(cell: Vector2i, mat: StandardMaterial3D) -> void:
	if overlay_meshes.has(cell):
		overlay_meshes[cell].material_override = mat
		overlay_meshes[cell].visible = true

func _compute_and_show_range(sel: Dictionary) -> void:
	# BFS reachable tiles (mirrors engine logic client-side)
	var unit_type = sel.get("type", "infantry")
	var speed_map = {"infantry": 1, "cavalry": 2, "artillery": 1, "relay": 1, "mine": 1, "shield": 1}
	var range_map = {"infantry": 2, "cavalry": 2, "artillery": 3, "relay": 0, "mine": 0, "shield": 0}
	var speed = speed_map.get(unit_type, 1)
	var atk_range = range_map.get(unit_type, 1)

	var sx = sel.get("x", 0)
	var sy = sel.get("y", 0)
	var occupied: Dictionary = {}
	for u in current_state.get("units", []):
		occupied[Vector2i(u.get("x"), u.get("y"))] = u.get("side")

	# BFS for move range
	var moved_ids = current_state.get("movedUnitsThisTurn", [])
	var already_moved = sel.get("id","") in moved_ids

	if not already_moved:
		var queue = [[sx, sy, 0]]
		var visited = {Vector2i(sx, sy): true}
		while not queue.is_empty():
			var cur = queue.pop_front()
			var cx = cur[0]; var cy = cur[1]; var dist = cur[2]
			if dist > 0:
				var c = Vector2i(cx, cy)
				if not occupied.has(c):
					_set_overlay(c, mat_move)
			if dist >= speed: continue
			for dx in [-1, 0, 1]:
				for dy in [-1, 0, 1]:
					if dx == 0 and dy == 0: continue
					var nx = cx + dx; var ny = cy + dy
					var nc = Vector2i(nx, ny)
					if nx >= 0 and nx < COLS and ny >= 0 and ny < ROWS and not visited.has(nc):
						visited[nc] = true
						queue.append([nx, ny, dist + 1])

	# Attack range (Chebyshev = diagonal allowed)
	if atk_range > 0:
		for dx in range(-atk_range, atk_range + 1):
			for dy in range(-atk_range, atk_range + 1):
				if dx == 0 and dy == 0: continue
				var c = Vector2i(sx + dx, sy + dy)
				if c.x >= 0 and c.x < COLS and c.y >= 0 and c.y < ROWS:
					if occupied.has(c) and occupied[c] != sel.get("side"):
						_set_overlay(c, mat_attack)

	# Selection tile on top
	_set_overlay(Vector2i(sx, sy), mat_select)

# ────────────────────────────────────────────────────────────────────────────
# HUD Buttons
# ────────────────────────────────────────────────────────────────────────────
func _on_end_turn() -> void:
	NetworkManager.send_action({"action": "end_turn"})
	_deselect()

func _on_undo() -> void:
	NetworkManager.send_action({"action": "undo"})
	_deselect()

func _on_restart() -> void:
	NetworkManager.send_action({"action": "restart"})
	_deselect()

# ── Network ────────────────────────────────────────────────────────────────
func _on_connected() -> void:
	status_lbl.text = "✅ Connected — North side  |  Q/E rotate  |  Scroll zoom"

func _on_disconnected() -> void:
	status_lbl.text = "❌ Disconnected"

func _on_error_received(msg: String) -> void:
	status_lbl.text = "⚠️ " + msg

# ── Victory screen ───────────────────────────────────────────────────────────
var _winner_shown: String = ""
var _victory_panel: Control = null

func _check_winner(st: Dictionary) -> void:
	var winner = st.get("winner", "")
	if not winner or winner == _winner_shown:
		return
	_winner_shown = winner
	_show_victory(winner)

func _show_victory(winner: String) -> void:
	if _victory_panel:
		_victory_panel.queue_free()

	var overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	hud.add_child(overlay)
	_victory_panel = overlay

	# Dim background
	var bg = ColorRect.new()
	bg.color = Color(0, 0, 0, 0.72)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(bg)

	# Centre card
	var card = PanelContainer.new()
	var cs   = StyleBoxFlat.new()
	cs.bg_color           = Color(0.07, 0.08, 0.12, 0.97)
	cs.border_color       = Color(1.0, 0.82, 0.2, 1.0)
	cs.set_border_width_all(3)
	cs.set_corner_radius_all(14)
	card.add_theme_stylebox_override("panel", cs)
	card.set_anchors_preset(Control.PRESET_CENTER)
	card.set_offset(SIDE_LEFT,   -200)
	card.set_offset(SIDE_TOP,    -140)
	card.set_offset(SIDE_RIGHT,   200)
	card.set_offset(SIDE_BOTTOM,  140)
	overlay.add_child(card)

	var vb = VBoxContainer.new()
	vb.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_theme_constant_override("separation", 18)
	card.add_child(vb)

	var crown = Label.new()
	crown.text = "🎖️  VICTORY"
	crown.add_theme_font_size_override("font_size", 28)
	crown.add_theme_color_override("font_color", Color(1.0, 0.85, 0.25))
	crown.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(crown)

	var win_lbl = Label.new()
	var is_north = (winner == "North")
	win_lbl.text = "%s wins the battle!" % winner
	win_lbl.add_theme_font_size_override("font_size", 20)
	win_lbl.add_theme_color_override("font_color",
		Color(0.45, 0.70, 1.0) if is_north else Color(1.0, 0.45, 0.45))
	win_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(win_lbl)

	vb.add_child(HSeparator.new())

	var rb = Button.new()
	rb.text = "🔄  Play Again"
	rb.add_theme_font_size_override("font_size", 16)
	var rbs = StyleBoxFlat.new()
	rbs.bg_color = Color(0.18, 0.55, 0.22)
	rbs.set_corner_radius_all(8)
	rbs.set_content_margin_all(10)
	rb.add_theme_stylebox_override("normal", rbs)
	rb.pressed.connect(func():
		_winner_shown = ""
		overlay.queue_free()
		NetworkManager.send_action({"action": "restart"}))
	vb.add_child(rb)
	
	
	
	


# ── INSTANT TACTICAL DISPATCH ENGINE: NO MENUS ──
func _execute_immediate_transform_move(cell: Vector2i) -> void:
	var sel_unit = _find_unit(selected_unit_id)
	var token: UnitToken3D = unit_tokens.get(selected_unit_id)
	if not sel_unit or not token:
		return
		
	# Instantly project rotation axis metrics using displacement distance delta
	var dx = cell.x - int(sel_unit.get("x", 0))
	var dy = cell.y - int(sel_unit.get("y", 0))
	var predicted_face_symbol = _calculate_top_face_after_roll(token.faces, dx, dy)
	
	var symbol_to_type = {
		"I": "infantry", "C": "cavalry", "A": "artillery", 
		"R": "relay", "M": "mine", "S": "shield"
	}
	var predicted_type = symbol_to_type.get(predicted_face_symbol, "infantry")
	
	# Transmit packet instantly down the socket pipeline
	NetworkManager.send_action({
		"action": "move",
		"unitId": selected_unit_id,
		"x": cell.x,
		"y": cell.y,
		"transform_to": predicted_type
	})
	
	_deselect()



# ── GEOMETRIC CUBE ORIENTATION SIMULATOR ──
func _calculate_top_face_after_roll(current_faces: Dictionary, dx: int, dy: int) -> String:
	var fallback = current_faces.get("top", "I")
	if dx == 0 and dy == 0:
		return fallback
		
	# Moving Right (+X): Left face tumbles to Top
	if dx > 0 and abs(dx) >= abs(dy):
		return current_faces.get("left", "M")
	# Moving Left (-X): Right face tumbles to Top
	elif dx < 0 and abs(dx) >= abs(dy):
		return current_faces.get("right", "A")
	# Moving Down (+Y): Back face tumbles to Top
	elif dy > 0 and abs(dy) > abs(dx):
		return current_faces.get("back", "R")
	# Moving Up (-Y): Front face tumbles to Top
	elif dy < 0 and abs(dy) > abs(dx):
		return current_faces.get("front", "C")
		
	return fallback
