extends Node3D

func _ready() -> void:
	# ── 1. Create the Outer Energy Beam (Transparent Glow) ──
	var outer_mesh = MeshInstance3D.new()
	var outer_cyl = CylinderMesh.new()
	outer_cyl.top_radius = 0.4
	outer_cyl.bottom_radius = 0.4
	outer_cyl.height = 30.0 # Reaches high up off-screen
	outer_mesh.mesh = outer_cyl
	
	var outer_mat = StandardMaterial3D.new()
	outer_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	outer_mat.albedo_color = Color(0.0, 0.7, 1.0, 0.4) # Glowing Cyan energy sheath
	outer_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	outer_mat.emission_enabled = true
	outer_mat.emission = Color(0.0, 0.6, 1.0)
	outer_mat.emission_energy_multiplier = 4.0
	outer_mesh.material_override = outer_mat
	
	# Center the cylinder so its base rests perfectly on the grid floor (Y=0)
	outer_mesh.position.y = 15.0 
	add_child(outer_mesh)

	# ── 2. Create the Inner Intense Core (Solid White Core) ──
	var inner_mesh = MeshInstance3D.new()
	var inner_cyl = CylinderMesh.new()
	inner_cyl.top_radius = 0.15
	inner_cyl.bottom_radius = 0.15
	inner_cyl.height = 30.0
	inner_mesh.mesh = inner_cyl
	
	var inner_mat = StandardMaterial3D.new()
	inner_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	inner_mat.albedo_color = Color(1.0, 1.0, 1.0, 1.0) # Solid hot white core
	inner_mesh.material_override = inner_mat
	inner_mesh.position.y = 15.0
	add_child(inner_mesh)

	# ── 3. Animate the Laser "Flash and Fade" ──
	# We start scale at zero on horizontal axes (X & Z)
	scale = Vector3(0.0, 1.0, 0.0)
	
	var tw = create_tween().set_parallel(false)
	
	# Fast Strike: Expand outward horizontally in a fraction of a second
	tw.tween_property(self, "scale", Vector3(1.0, 1.0, 1.0), 0.07).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	
	# Fade Out: Collapse the width back to 0 while shrinking the energy
	var fade_tw = create_tween().set_parallel(true)
	fade_tw.tween_property(self, "scale", Vector3(0.0, 1.0, 0.0), 0.25).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	fade_tw.tween_property(outer_mat, "albedo_color:a", 0.0, 0.25)
	
	# Clean up from the game tree when finished
	await fade_tw.finished
	queue_free()
