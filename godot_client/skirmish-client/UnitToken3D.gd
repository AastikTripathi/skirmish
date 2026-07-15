extends Node3D
class_name UnitToken3D

var unit_id:  String     = ""
var side:     String     = "North"
var type:     String     = "infantry"
var symbol:   String     = "I"
var faces:    Dictionary = {}
var stranded: bool       = false
var is_dying: bool       = false
var _pending_faces: Dictionary = {}  # applied after roll anim

var cube_mesh:  MeshInstance3D
var top_cap:    MeshInstance3D   # slightly lighter top-face cap
var body:       StaticBody3D
var mat:        StandardMaterial3D
var top_mat:    StandardMaterial3D

const CUBE_SIZE: float = 0.74
const HALF:      float = CUBE_SIZE * 0.5 + 0.014

var face_labels: Dictionary = {}

const FACE_NORMALS = {
	"top":   Vector3( 0,  1,  0),
	"front": Vector3( 0,  0,  1),
	"back":  Vector3( 0,  0, -1),
	"right": Vector3( 1,  0,  0),
	"left":  Vector3(-1,  0,  0),
}

# Muted, premium colour palette
const NORTH_COLOR = Color(0.18, 0.35, 0.78)   # deep steel-blue
const NORTH_TOP   = Color(0.30, 0.50, 0.92)
const SOUTH_COLOR = Color(0.72, 0.12, 0.12)   # deep crimson
const SOUTH_TOP   = Color(0.88, 0.28, 0.22)
const STRAND_COLOR= Color(0.32, 0.32, 0.35, 0.50)

func setup(data: Dictionary) -> void:
	unit_id = data.get("id", "")
	side    = data.get("side", "North")
	type    = data.get("type", "infantry")
	_build_nodes()
	update_state(data, false)

func _build_nodes() -> void:
	# ── Main cube (unshaded for consistent colour regardless of view angle) ──
	cube_mesh      = MeshInstance3D.new()
	var bm         = BoxMesh.new()
	bm.size        = Vector3(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE)
	cube_mesh.mesh = bm
	mat                 = StandardMaterial3D.new()
	mat.shading_mode    = BaseMaterial3D.SHADING_MODE_UNSHADED
	_apply_material()
	cube_mesh.material_override = mat
	add_child(cube_mesh)

	# ── Top-face cap: thin slightly-lighter slab so top is always distinct ──
	top_cap      = MeshInstance3D.new()
	var tm       = BoxMesh.new()
	tm.size      = Vector3(CUBE_SIZE - 0.04, 0.03, CUBE_SIZE - 0.04)
	top_cap.mesh = tm
	top_mat      = StandardMaterial3D.new()
	top_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	top_cap.material_override = top_mat
	top_cap.position = Vector3(0, CUBE_SIZE * 0.5 + 0.015, 0)
	add_child(top_cap)
	_update_top_cap()

	# ── Physics body ────────────────────────────────────────────────────────
	body     = StaticBody3D.new()
	var col  = CollisionShape3D.new()
	var box  = BoxShape3D.new()
	box.size = Vector3(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE)
	col.shape = box
	body.add_child(col)
	add_child(body)

	# ── Face labels ──────────────────────────────────────────────────────────
	var face_cfg = {
		"top":   [Vector3(0, CUBE_SIZE * 0.5 + 0.06,  0),    Vector3(-90, 0, 0)],
		"front": [Vector3(0, 0,  CUBE_SIZE * 0.5 + 0.04),   Vector3(  0, 0, 0)],
		"back":  [Vector3(0, 0, -(CUBE_SIZE * 0.5 + 0.04)),  Vector3(  0, 180, 0)],
		"right": [Vector3( CUBE_SIZE * 0.5 + 0.04, 0, 0),   Vector3(  0, -90, 0)],
		"left":  [Vector3(-(CUBE_SIZE * 0.5 + 0.04), 0, 0), Vector3(  0,  90, 0)],
	}
	for key in face_cfg:
		var cfg = face_cfg[key]
		var lbl              = Label3D.new()
		lbl.font_size        = 80
		lbl.pixel_size       = 0.006
		lbl.outline_size     = 10
		lbl.double_sided     = false    # only render toward camera
		lbl.no_depth_test    = false    # cube geometry occludes back labels
		lbl.billboard        = BaseMaterial3D.BILLBOARD_DISABLED
		lbl.position         = cfg[0]
		lbl.rotation_degrees = cfg[1]
		add_child(lbl)
		face_labels[key] = lbl

	_refresh_label_colors()
	position.y = CUBE_SIZE * 0.5 + 0.04

# ── Camera facing: dim labels based on angle, top stays bright ────────────
func update_facing(cam_world_pos: Vector3) -> void:
	var to_cam = (cam_world_pos - global_position).normalized()
	for key in face_labels:
		var dot = FACE_NORMALS[key].dot(to_cam)
		var lbl: Label3D = face_labels[key]
		if dot > 0.05:
			lbl.visible   = true
			# Top face = full bright (it is the active/identity face)
			# Side faces = dimmed so eye focuses on top
			lbl.modulate.a = 1.0 if key == "top" else 0.55
		else:
			lbl.visible = false

# ── Label colours / glow ────────────────────────────────────────────
func _refresh_label_colors() -> void:
	# Glow color: bright version of the team colour for the halo outline
	var glow: Color = Color(0.55, 0.80, 1.0) if side == "North" else Color(1.0, 0.60, 0.55)
	for key in face_labels:
		var lbl: Label3D = face_labels[key]
		lbl.modulate         = Color.WHITE   # always pure white text
		lbl.outline_modulate = glow          # team-coloured glow halo
		if stranded:
			lbl.modulate         = Color(0.6, 0.6, 0.6, 0.5)
			lbl.outline_modulate = Color(0.3, 0.3, 0.3, 0.5)

# ── Material ──────────────────────────────────────────────────────────────
func _apply_material() -> void:
	if stranded:
		mat.albedo_color = STRAND_COLOR
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	elif side == "North":
		mat.albedo_color = NORTH_COLOR
		mat.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED
	else:
		mat.albedo_color = SOUTH_COLOR
		mat.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED

func _update_top_cap() -> void:
	if stranded:
		top_mat.albedo_color = Color(0.40, 0.40, 0.42, 0.5)
		top_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	elif side == "North":
		top_mat.albedo_color = NORTH_TOP
		top_mat.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED
	else:
		top_mat.albedo_color = SOUTH_TOP
		top_mat.transparency = BaseMaterial3D.TRANSPARENCY_DISABLED

func set_stranded(is_stranded: bool) -> void:
	if stranded == is_stranded: return
	stranded = is_stranded
	_apply_material()
	_update_top_cap()
	_refresh_label_colors()

# ── State update ──────────────────────────────────────────────────────────
func update_state(data: Dictionary, animate: bool = true) -> void:
	type   = data.get("type", type)
	symbol = data.get("symbol", "I")
	var new_faces = data.get("faces", {"top": symbol, "front": "C", "back": "R", "right": "A", "left": "M", "bottom": "S"})

	var tx = float(data.get("x", 0))
	var tz = float(data.get("y", 0))
	var is_moving = (abs(position.x - tx) > 0.01 or abs(position.z - tz) > 0.01)

	if animate and is_moving:
		# Store new faces — apply AFTER roll so symbol flip matches tumble end
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
		face_labels[key].text = faces.get(key, "?")
	_refresh_label_colors()

# ── Movement animation ────────────────────────────────────────────────────
func _animate_move(target: Vector3) -> void:
	# Cavalry: smooth glide only — no roll (high mobility unit)
	if type == "cavalry":
		var tw = create_tween().set_parallel(true)
		tw.tween_property(self, "position:x", target.x, 0.38).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
		tw.tween_property(self, "position:z", target.z, 0.38).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
		var hop = create_tween()
		hop.tween_property(self, "position:y", target.y + 0.4, 0.19)
		hop.tween_property(self, "position:y", target.y,       0.19).set_trans(Tween.TRANS_BOUNCE)
		await tw.finished
		_apply_pending_faces()
		return

	var dir       = Vector3(target.x - position.x, 0, target.z - position.z).normalized()
	var roll_axis = Vector3(-dir.z, 0, dir.x)
	var roll_target = cube_mesh.rotation_degrees + roll_axis * 90.0
	var tw = create_tween().set_parallel(true)
	tw.tween_property(self, "position:x", target.x, 0.40).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	tw.tween_property(self, "position:z", target.z, 0.40).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	tw.tween_property(cube_mesh, "rotation_degrees", roll_target, 0.40).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	await tw.finished
	cube_mesh.rotation_degrees = Vector3.ZERO
	_apply_pending_faces()   # symbol flip AFTER tumble lands

func _apply_pending_faces() -> void:
	if not _pending_faces.is_empty():
		faces = _pending_faces
		_pending_faces = {}
		_update_labels()

# ── Death animation ───────────────────────────────────────────────────────
func play_death() -> void:
	if is_dying: return
	is_dying = true
	# Spin and scale to zero
	var tw = create_tween().set_parallel(true)
	tw.tween_property(self, "scale", Vector3.ZERO, 0.55).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_IN)
	tw.tween_property(cube_mesh, "rotation_degrees",
		Vector3(0, 360, 180), 0.55).set_trans(Tween.TRANS_QUAD)
	await tw.finished
	queue_free()

# ── Attack animations ─────────────────────────────────────────────────────
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
