extends Node2D

@onready var board: Board = $Board

func _ready() -> void:
	print("Game screen initialized. Hooking up network signals...")
	
	# Connect to our global NetworkManager signals
	NetworkManager.connected_to_server.connect(_on_connected)
	NetworkManager.disconnected_from_server.connect(_on_disconnected)
	NetworkManager.state_updated.connect(_on_state_updated)
	NetworkManager.error_received.connect(_on_error_received)
	
	# Configure room settings (feel free to change these for testing)
	NetworkManager.room_id = "skirmish_room"
	NetworkManager.player_name = "GodotCommander"
	NetworkManager.player_side = "North"
	NetworkManager.vs_ai = true  # Set to true to play against your python ai.py
	
	# Connect to the local FastAPI backend server.py
	print("Attempting to connect to backend server...")
	NetworkManager.connect_to_room()

func _on_connected() -> void:
	print("📡 Successfully joined the battle room: ", NetworkManager.room_id)

func _on_disconnected() -> void:
	print("🔌 Lost connection to the server.")

func _on_error_received(msg: String) -> void:
	print("⚠️ Server Error: ", msg)

func _on_state_updated(state_data: Dictionary) -> void:
	print("🎮 Received State Update from Python backend!")
	if board:
		board.update_board(state_data)
