extends Node3D
class_name UnitToken3D

var unit_id:  String     = ""
var side:     String     = "North"
var type:     String     = "infantry"
var symbol:   String     = "I"
var faces:    Dictionary = {}
var stranded: bool       = false
var is_dying: bool       = false
var _pending_faces: Dictionary = {}

var cube_mesh:  MeshInstance3D
var top_cap:    MeshInstance3D
var body:       StaticBody3D
var mat:        StandardMaterial3D
var top_mat:    StandardMaterial3D

const CUBE_SIZE: float = 0.74

var face_labels: Dictionary = {}
var shield_node: MeshInstance3D = null

const FACE_NORMALS = {
	"top":   Vector3( 0,  1,  0),
	"front": Vector3( 0,  0,  1),
	"back":  Vector3( 0,  0, -1),
	"right": Vector3( 1,  0,  0),
	"left":  Vector3(-1,  0,  0),
}

# Rich, deep, premium tactile colors for the stone body blocks
const NORTH_COLOR = Color(0.15, 0.28, 0.65)   # Deep mineral blue
const SOUTH_COLOR = Color(0.70, 0.12, 0.12)   # Dark crimson jasper
const STRAND_COLOR= Color(0.28, 0.28, 0.30)

func setup(data: Dictionary) -> void:
	unit_id = data.get("id", "")
	side    = data.get("side", "North")
	type    = data.get("type", "infantry")
	_build_nodes()
	update_state(data, false)


	
func _build_nodes() -> void:
	# ── Main Cube Body ──
	cube_mesh = MeshInstance3D.new()
	var bm = BoxMesh.new()
	bm.size = Vector3(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE)
	cube_mesh.mesh = bm

	mat = StandardMaterial3D.new()
	_apply_material()
	cube_mesh.material_override = mat
	add_child(cube_mesh)

	# ── Top-Face Cap ──
	top_cap = MeshInstance3D.new()
	var tm = BoxMesh.new()
	tm.size = Vector3(CUBE_SIZE - 0.01, 0.01, CUBE_SIZE - 0.01)
	top_cap.mesh = tm
	top_mat = StandardMaterial3D.new()
	top_cap.position = Vector3(0, CUBE_SIZE * 0.5 + 0.002, 0)
	cube_mesh.add_child(top_cap)
	_update_top_cap()

	# ── Physics Body ──
	body = StaticBody3D.new()
	var col = CollisionShape3D.new()
	var box = BoxShape3D.new()
	box.size = Vector3(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE)
	col.shape = box
	body.add_child(col)
	add_child(body)

	# ── Face Labels (Restored position inside build workflow) ──
	var face_cfg = {
		"top":   [Vector3(0, CUBE_SIZE * 0.5 + 0.015,  0),   Vector3(-90, 0, 0)],
		"front": [Vector3(0, 0,  CUBE_SIZE * 0.5 + 0.005),   Vector3(  0, 0, 0)],
		"back":  [Vector3(0, 0, -(CUBE_SIZE * 0.5 + 0.005)),  Vector3(  0, 180, 0)],
		"right": [Vector3( CUBE_SIZE * 0.5 + 0.005, 0, 0),   Vector3(  0,  90, 0)],
		"left":  [Vector3(-(CUBE_SIZE * 0.5 + 0.005), 0, 0), Vector3(  0, -90, 0)],
	}
	for key in face_cfg:
		var cfg = face_cfg[key]
		
		if key == "top":
			var mesh_inst = MeshInstance3D.new()
			var geo_text_mesh = TextMesh.new()
			geo_text_mesh.font_size = 200
			geo_text_mesh.pixel_size = 0.004
			geo_text_mesh.depth = 0.001
			geo_text_mesh.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			geo_text_mesh.vertical_alignment = VERTICAL_ALIGNMENT_CENTER 
			mesh_inst.mesh = geo_text_mesh
	
			var txt_mat = StandardMaterial3D.new()
			txt_mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
			txt_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
			mesh_inst.material_override = txt_mat
	
			mesh_inst.position = cfg[0]
			mesh_inst.rotation_degrees = cfg[1]
			cube_mesh.add_child(mesh_inst)
			face_labels[key] = mesh_inst
		else:
			var lbl = Label3D.new()
			lbl.font_size = 84
			lbl.pixel_size = 0.0055
			lbl.outline_size = 0  
			lbl.double_sided = false
			lbl.no_depth_test = false
			lbl.billboard = BaseMaterial3D.BILLBOARD_DISABLED
			lbl.texture_filter = StandardMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
			lbl.shaded = false
			
			lbl.position = cfg[0]
			lbl.rotation_degrees = cfg[1]
			cube_mesh.add_child(lbl)
			face_labels[key] = lbl
			
	_refresh_label_colors()
	
	# Restores correct vector height baseline so block isn't sunken into the field matrix
	position.y = CUBE_SIZE * 0.5


func set_shielded(is_shielded: bool) -> void:
	if is_shielded and shield_node == null:
		# Create the exoskeleton shell
		shield_node = MeshInstance3D.new()
		var box = BoxMesh.new()
		box.size = Vector3(1.15, 1.15, 1.15) # Slightly larger than the unit
		shield_node.mesh = box
		
		# Force Field Material
		var mat = StandardMaterial3D.new()
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.albedo_color = Color(0.2, 0.6, 1.0, 0.3) # Semi-transparent blue
		mat.emission_enabled = true
		mat.emission = Color(0.0, 0.5, 1.0)
		mat.emission_energy_multiplier = 2.0
		# Makes the edges glow brighter
		mat.proximity_fade_enabled = true 
		
		shield_node.material_override = mat
		add_child(shield_node)
		
		# Pulse animation
		var tw = create_tween().set_loops()
		tw.tween_property(shield_node, "scale", Vector3(1.05, 1.05, 1.05), 1.0)
		tw.tween_property(shield_node, "scale", Vector3(1.0, 1.0, 1.0), 1.0)
		
	elif not is_shielded and shield_node != null:
		shield_node.queue_free()
		shield_node = null
		
				
	# ── Face Labels (Top uses geometric TextMesh for isolated neon glow; sides use standard text) ──
	var face_cfg = {
		"top":   [Vector3(0, CUBE_SIZE * 0.5 + 0.015,  0),   Vector3(-90, 0, 0)],
		"front": [Vector3(0, 0,  CUBE_SIZE * 0.5 + 0.005),   Vector3(  0, 0, 0)],
		"back":  [Vector3(0, 0, -(CUBE_SIZE * 0.5 + 0.005)),  Vector3(  0, 180, 0)],
		"right": [Vector3( CUBE_SIZE * 0.5 + 0.005, 0, 0),   Vector3(  0,  90, 0)],
		"left":  [Vector3(-(CUBE_SIZE * 0.5 + 0.005), 0, 0), Vector3(  0, -90, 0)],
	}
	for key in face_cfg:
		var cfg = face_cfg[key]
		
		if key == "top":
			var mesh_inst = MeshInstance3D.new()
			var geo_text_mesh = TextMesh.new()
			geo_text_mesh.font_size = 200
			geo_text_mesh.pixel_size = 0.004
			geo_text_mesh.depth = 0.001
			geo_text_mesh.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
			geo_text_mesh.vertical_alignment = VERTICAL_ALIGNMENT_CENTER 
			mesh_inst.mesh = geo_text_mesh
	
			var txt_mat = StandardMaterial3D.new()
			txt_mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
			txt_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
			mesh_inst.material_override = txt_mat
	
			mesh_inst.position = cfg[0]
			mesh_inst.rotation_degrees = cfg[1]
			cube_mesh.add_child(mesh_inst)
			face_labels[key] = mesh_inst
		else:
			# --- SIDE FACES: STABLE STANDARD LABELS ---
			var lbl = Label3D.new()
			lbl.font_size = 84
			lbl.pixel_size = 0.0055
			lbl.outline_size = 0  
			lbl.double_sided = false
			lbl.no_depth_test = false
			lbl.billboard = BaseMaterial3D.BILLBOARD_DISABLED
			lbl.texture_filter = StandardMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
			lbl.shaded = false
			
			
			lbl.position = cfg[0]
			lbl.rotation_degrees = cfg[1]
			cube_mesh.add_child(lbl)
			face_labels[key] = lbl
	_refresh_label_colors()
	position.y = CUBE_SIZE * 0.5
	
	

				
				
func _refresh_label_colors() -> void:
	var team_glow = Color(0.4, 0.8, 1.0) if side == "North" else Color(1.0, 0.4, 0.3)
	
	for key in face_labels:
		var node = face_labels[key]
		if not node: continue
		
		if key == "top" and node is MeshInstance3D:
			var txt_mat = node.material_override as StandardMaterial3D
			if not txt_mat: continue
	
			if stranded:
				txt_mat.albedo_color = Color(0.2, 0.2, 0.2)
				txt_mat.emission_enabled = false
			else:
				txt_mat.albedo_color = Color.WHITE
				txt_mat.emission_enabled = true
				txt_mat.emission = team_glow
				txt_mat.emission_energy_multiplier = 12.0
		
		elif key != "top" and node is Label3D:
			if stranded:
				node.modulate = Color(0.15, 0.15, 0.16)
			else:
				node.modulate = Color(0.12, 0.10, 0.10)
				
				


		
#func update_facing(cam_world_pos: Vector3) -> void:
	#var to_cam = (cam_world_pos - global_position).normalized()
	#for key in face_labels:
		#var dot = FACE_NORMALS[key].dot(to_cam)
		#var node = face_labels[key] as Node3D # Generic cast allows both types
		#if not node: continue
		#
		## Simulates a natural horizon falloff view check
		#node.visible = (dot > 0.05)
		
func update_facing(cam_world_pos: Vector3) -> void:
	var to_cam = (cam_world_pos - global_position).normalized()
	for key in face_labels:
		var node = face_labels[key] as Node3D # Generic cast allows both types
		if not node: continue
		
		# Transform the static local normal into global space using the block's current 3D basis
		var local_normal = FACE_NORMALS[key]
		var global_normal = global_transform.basis * local_normal
		
		var dot = global_normal.dot(to_cam)
		
		# Simulates a natural horizon falloff view check
		node.visible = (dot > 0.05)




func _apply_material() -> void:
	var stone_base = load("res://polished_stone.tres")
	if stone_base:
		mat = stone_base.duplicate()
		mat.uv1_triplanar = true
		mat.uv1_scale = Vector3(1.2, 1.2, 1.2)
	else:
		mat = StandardMaterial3D.new()
	
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	mat.metallic = 0.0
	
	if stranded:
		# --- SPECTRUM DEACTIVATED GLASS EFFECT ---
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.albedo_color = Color(0.15, 0.22, 0.35, 0.35) # Smoky translucent blue-gray tint
		#mat.roughness = 0.12
		mat.roughness = 0.38
		mat.clearcoat_enabled = true
		mat.clearcoat = 0.5
		mat.clearcoat_roughness = 0.15                             # Shiny, clear frosted appearance
		
		# Allow internal light glow transmission scattering
		mat.subsurface_scattering_enabled = true
		mat.subsurface_scattering_strength = 0.75
		mat.subsurface_scattering_transmittance_color = Color(0.25, 0.6, 1.0)
	else:
		# --- STANDARD SOLID ACTIVE RESIN ---
		mat.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED
		mat.roughness = 0.52                             # Satin finish for matte light scatter
		mat.subsurface_scattering_enabled = true
		mat.subsurface_scattering_strength = 0.20
		
		if side == "North":
			mat.albedo_color = Color(0.12, 0.22, 0.55)
			mat.subsurface_scattering_transmittance_color = Color(0.3, 0.5, 0.9)
		else:
			mat.albedo_color = Color(0.55, 0.08, 0.08)
			mat.subsurface_scattering_transmittance_color = Color(0.9, 0.3, 0.3)
			
			
#func _update_top_cap() -> void:
	## Keep base settings identical so it behaves as one unified die structure
	#top_mat = mat.duplicate()
	#
	#if not stranded:
		## Blend it slightly lighter on the top flat face if needed, 
		## or leave it uniform to perfectly resemble the reference image.
		#pass
		
		
func _update_top_cap() -> void:
	top_mat = mat.duplicate()
	
	# The top face is now identical dark stone resin, no background glowing pads
	if not stranded:
		# Match the baseline side body tint
		top_mat.albedo_color = mat.albedo_color
	else:
		top_mat.albedo_color = Color(0.2, 0.2, 0.2)
		
	top_mat.emission_enabled = false
	
	if top_cap:
		top_cap.material_override = top_mat	


func set_stranded(is_stranded: bool) -> void:
	if stranded == is_stranded: return
	stranded = is_stranded
	
	_apply_material()
	_update_top_cap()
	
	# Apply materials directly to structural mesh overrides to force runtime update updates
	if cube_mesh:
		cube_mesh.material_override = mat
	if top_cap:
		top_cap.material_override = top_mat
		
	_refresh_label_colors()
	
	# --- INTERNAL POINT LIGHT MANAGEMENT ---
	if stranded:
		# Delete it first if a duplicate node accidentally exists
		if has_node("InternalStrandLight"):
			get_node("InternalStrandLight").queue_free()
			
		var crystal_light = OmniLight3D.new()
		crystal_light.name = "InternalStrandLight"
		
		# Soft blue internal light parameters
		crystal_light.light_color = Color(0.35, 0.7, 1.0)
		crystal_light.light_energy = 2.2
		crystal_light.omni_range = 1.8
		crystal_light.shadow_enabled = false
		
		add_child(crystal_light)
	else:
		if has_node("InternalStrandLight"):
			get_node("InternalStrandLight").queue_free()

#func update_state(data: Dictionary, animate: bool = true) -> void:
	#type   = data.get("type", type)
	#symbol = data.get("symbol", "I")
	#var new_faces = data.get("faces", {"top": symbol, "front": "C", "back": "R", "right": "A", "left": "M", "bottom": "S"})
	#var tx = float(data.get("x", 0))
	#var tz = float(data.get("y", 0))
	#var is_moving = (abs(position.x - tx) > 0.01 or abs(position.z - tz) > 0.01)
#
	#if animate and is_moving:
		#_pending_faces = new_faces
		#_animate_move(Vector3(tx, position.y, tz))
	#else:
		#faces = new_faces
		#_pending_faces = {}
		#_update_labels()
		#position.x = tx
		#position.z = tz
		
# ── REPLACE WITH THIS DYNAMIC FACE OVERRIDE MATRIX ──
func update_state(data: Dictionary, animate: bool = true) -> void:
	type   = data.get("type", type)
	symbol = data.get("symbol", "I")
	var tx = float(data.get("x", 0))
	var tz = float(data.get("y", 0))
	
	# Explicit target face tracking structure checks
	var new_faces = data.get("faces", {})
	if new_faces.is_empty():
		new_faces = {"top": symbol, "front": "C", "back": "R", "right": "A", "left": "M", "bottom": "S"}
		
	var is_moving = (abs(position.x - tx) > 0.01 or abs(position.z - tz) > 0.01)

	if animate and is_moving:
		_pending_faces = new_faces
		_animate_move(Vector3(tx, position.y, tz))
	else:
		faces = new_faces
		_pending_faces = {}
		_update_labels()
		position.x = tx
		position.z = tz


	
func _update_labels() -> void:
	for key in face_labels:
		var node = face_labels[key]
		var character = faces.get(key, "?")
		
		if key == "top" and node is MeshInstance3D:
			node.mesh.text = character
		elif node is Label3D:
			node.text = character
			
	_refresh_label_colors()

#func _animate_move(target: Vector3) -> void:
	#if type == "cavalry":
		#var tw = create_tween().set_parallel(true)
		#tw.tween_property(self, "position:x", target.x, 0.38).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
		#tw.tween_property(self, "position:z", target.z, 0.38).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
		#var hop = create_tween()
		#hop.tween_property(self, "position:y", target.y + 0.4, 0.19)
		#hop.tween_property(self, "position:y", target.y,       0.19).set_trans(Tween.TRANS_BOUNCE)
		#await tw.finished
		#_apply_pending_faces()
		#return
#
#
	## ── NON-CAVALRY: HEAVY WEIGHTED AXIS ROLL ANIMATION ──
	#var start_pos = position
	#var move_vec = target - start_pos
	#var dir = move_vec.normalized()
	#
	## Determine tile dimension space buffer (Assuming typical grid step size = 1.0)
	#var tile_step = move_vec.length()
	#var slide_dist = (tile_step - CUBE_SIZE) * 0.5
	#
	## 1. THE SLIDE PHASE (Ease In-Out to the tile border edge)
	#var tw_slide = create_tween()
	#tw_slide.tween_property(self, "position", start_pos + (dir * slide_dist), 0.12)\
		#.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	#await tw_slide.finished
	#
	## 2. THE HEAVY INERTIA LIFT (Ease-In slow climb up to ~45 degrees)
	##var roll_axis = Vector3(-dir.z, 0, dir.x)
	#var roll_axis = Vector3(dir.z, 0, -dir.x)
	#var lift_target_rot = roll_axis * 42.0
	#var mid_pos = position + (dir * (CUBE_SIZE * 0.35)) + Vector3(0, CUBE_SIZE * 0.22, 0)
	#
	##var tw_lift = create_tween().set_parallel(true)
	##tw_lift.tween_property(self, "position", mid_pos, 0.24)\
		##.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	##tw_lift.tween_property(cube_mesh, "rotation_degrees", lift_target_rot, 0.24)\
		##.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	##await tw_lift.finished
	#
	#var tw_lift = create_tween().set_parallel(true)
	#tw_lift.tween_property(self, "position", mid_pos, 0.24)\
		#.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	#tw_lift.tween_property(self, "rotation_degrees", lift_target_rot, 0.24)\
		#.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	#await tw_lift.finished
	#
	### 3. THE SNAP SNAP DROP & SETTLE (Rapid drop over center of mass with a subtle bounce settle)
	##var final_rot = roll_axis * 90.0
	##var tw_drop = create_tween().set_parallel(true)
	##tw_drop.tween_property(self, "position", target, 0.14)\
		##.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	##tw_drop.tween_property(cube_mesh, "rotation_degrees", final_rot, 0.14)\
		##.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	##await tw_drop.finished
	##
	### 1. Firmly set the root token node to the target grid destination
	##position = target
	##
	### 2. CRUCIAL STEP: Wipe the mesh rotation immediately so its local axes line up with the world.
	### Because it matches global orientation instantly, faces won't mismatch or visually glitch.
	##cube_mesh.rotation_degrees = Vector3.ZERO
	#
	#var final_rot = roll_axis * 90.0
	#var tw_drop = create_tween().set_parallel(true)
	#tw_drop.tween_property(self, "position", target, 0.14)\
		#.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	#tw_drop.tween_property(self, "rotation_degrees", final_rot, 0.14)\
		#.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	#await tw_drop.finished
	#
	#position = target
	#self.rotation_degrees = Vector3.ZERO # Resets the global rotation track matrix cleanly
	#
	## 3. Apply the backend data mapping to the newly oriented faces
	#_apply_pending_faces()
	
	
	
# ── FIX: DEFAULT TO FLAT SLIDE FOR ALL PIECES ──
func _animate_move(target: Vector3) -> void:
	# Check if the incoming state change actually demands a face transformation change
	var is_transforming = !_pending_faces.is_empty() and _pending_faces.get("top") != faces.get("top")
	
	if is_transforming:
		# ── OPTIONAL USER-TRIGGERED PHYSICAL AXIS ROLL ──
		var start_pos = position
		var move_vec = target - start_pos
		var dir = move_vec.normalized()
		var tile_step = move_vec.length()
		var slide_dist = (tile_step - CUBE_SIZE) * 0.5
		
		# 1. Slide to the edge
		var tw_slide = create_tween()
		tw_slide.tween_property(self, "position", start_pos + (dir * slide_dist), 0.12)\
			.set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
		await tw_slide.finished
		
		# 2. Lift and tilt
		var roll_axis = Vector3(dir.z, 0, -dir.x)
		var lift_target_rot = roll_axis * 42.0
		var mid_pos = position + (dir * (CUBE_SIZE * 0.35)) + Vector3(0, CUBE_SIZE * 0.22, 0)
		
		var tw_lift = create_tween().set_parallel(true)
		tw_lift.tween_property(self, "position", mid_pos, 0.24)\
			.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		tw_lift.tween_property(self, "rotation_degrees", lift_target_rot, 0.24)\
			.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
		await tw_lift.finished
		
		# 3. Drop and settle
		var final_rot = roll_axis * 90.0
		var tw_drop = create_tween().set_parallel(true)
		tw_drop.tween_property(self, "position", target, 0.14)\
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
		tw_drop.tween_property(self, "rotation_degrees", final_rot, 0.14)\
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
		await tw_drop.finished
		
		position = target
		self.rotation_degrees = Vector3.ZERO
	else:
		# ── CAVALRY STYLE FLAT SLIDE ROUTINE (THE DEFAULT BEHAVIOR) ──
		var tw = create_tween().set_parallel(true)
		tw.tween_property(self, "position:x", target.x, 0.38).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
		tw.tween_property(self, "position:z", target.z, 0.38).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
		
		# Give it a tiny, satisfying micro-hop to sell the slide kinetics
		var hop = create_tween()
		hop.tween_property(self, "position:y", target.y + 0.15, 0.19)
		hop.tween_property(self, "position:y", target.y,       0.19).set_trans(Tween.TRANS_BOUNCE)
		await tw.finished
		
	_apply_pending_faces()

#func _apply_pending_faces() -> void:
	#if not _pending_faces.is_empty():
		#faces = _pending_faces
		#_pending_faces = {}
		#_update_labels()
		
func _apply_pending_faces() -> void:
	if not _pending_faces.is_empty():
		print("--- DEBUG MOVE END ---")
		print("Old Faces Matrix: ", faces)
		print("Incoming Server Faces Matrix: ", _pending_faces)
		faces = _pending_faces
		_pending_faces = {}
		_update_labels()

func play_death() -> void:
	if is_dying: return
	is_dying = true
	var tw = create_tween().set_parallel(true)
	tw.tween_property(self, "scale", Vector3.ZERO, 0.55).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN)
	tw.tween_property(cube_mesh, "rotation_degrees", Vector3(0, 360, 180), 0.55).set_trans(Tween.TRANS_QUAD)
	await tw.finished
	queue_free()

func play_ram_attack(target_world_pos: Vector3) -> void:
	var origin = position
	var lunge  = origin + (target_world_pos - origin).normalized() * 0.42
	var tw = create_tween()
	tw.tween_property(self, "position", lunge,  0.13).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "position", origin, 0.20).set_trans(Tween.TRANS_BOUNCE)

func play_hit_shake() -> void:
	var o = position
	var tw = create_tween()
	for i in range(4):
		var s = 0.07 * (1.0 - i * 0.22)
		tw.tween_property(self, "position", o + Vector3(s, 0, 0), 0.04)
		tw.tween_property(self, "position", o - Vector3(s, 0, 0), 0.04)
	tw.tween_property(self, "position", o, 0.04)
