extends Node

# Signal emitted when we successfully connect to the server
signal connected_to_server
# Signal emitted when connection fails or closes
signal disconnected_from_server
# Signal emitted when we receive a new state update from the server
signal state_updated(state_data)
# Signal emitted when we receive an error message from the server
signal error_received(message)

var socket: WebSocketPeer = WebSocketPeer.new()
var websocket_connected: bool = false

# Configuration settings
var server_url: String = "ws://localhost:8000/ws/"
var room_id: String = "skirmish_room"
var player_name: String = "GodotPlayer"
var room_password: String = ""
var vs_ai: bool = false
var ai_vs_ai: bool = true
var player_side: String = "North"

func _ready() -> void:
	# Keep this node running even when game is paused
	process_mode = Node.PROCESS_MODE_ALWAYS

func connect_to_room() -> void:
	# Format the query parameters for room auth & settings
	var url_params = "?name=%s&password=%s&vs_ai=%s&ai_vs_ai=%s&player_side=%s" % [
		player_name.uri_encode(),
		room_password.uri_encode(),
		"true" if vs_ai else "false",
		"true" if ai_vs_ai else "false",
		player_side
	]
	var full_url = server_url + room_id + url_params
	print("Connecting to: ", full_url)
	
	socket.close() # Close any existing connection first
	websocket_connected = false
	
	var err = socket.connect_to_url(full_url)
	if err != OK:
		print("Failed to initialize connection: ", err)
		emit_signal("disconnected_from_server")

func _process(_delta: float) -> void:
	socket.poll()
	var state = socket.get_ready_state()
	
	if state == WebSocketPeer.STATE_OPEN:
		if not websocket_connected:
			websocket_connected = true
			print("Connected to WebSocket server!")
			emit_signal("connected_to_server")
		
		# Read all available packets
		while socket.get_available_packet_count() > 0:
			var packet = socket.get_packet()
			var json_string = packet.get_string_from_utf8()
			_handle_message(json_string)
			
	elif state == WebSocketPeer.STATE_CLOSED:
		if websocket_connected:
			websocket_connected = false
			var code = socket.get_close_code()
			var reason = socket.get_close_reason()
			print("Disconnected: Code %d, Reason: %s" % [code, reason])
			emit_signal("disconnected_from_server")

# Send an action payload to the server
func send_action(payload: Dictionary) -> void:
	if socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		var json_string = JSON.stringify(payload)
		socket.send_text(json_string)
		print("Sent action: ", payload)
	else:
		print("Cannot send action: Socket is not open.")

# Process incoming JSON messages
func _handle_message(json_string: String) -> void:
	var json = JSON.new()
	var parse_err = json.parse(json_string)
	if parse_err != OK:
		print("Failed to parse JSON: ", json_string)
		return
		
	var data = json.get_data()
	if not data is Dictionary:
		return
		
	# Check message type
	var msg_type = data.get("type", "")
	if msg_type == "error":
		var message = data.get("message", "Unknown error")
		print("Server Error: ", message)
		emit_signal("error_received", message)
	else:
		# If it's a state update, it won't have a "type" but contains "units", "turn", etc.
		emit_signal("state_updated", data)
