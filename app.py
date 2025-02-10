from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import os
import json
import uuid

# Get the directory where the script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback_secret_key")
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")  # Folder to store uploaded images
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow all origins for Socket.IO

# Ensure the uploads folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# File to store notes (in the same directory as the script)
NOTES_FILE = os.path.join(BASE_DIR, "notes.json")

# Ensure all notes have an ID
def ensure_note_ids(notes):
    for note in notes:
        if "id" not in note:
            note["id"] = str(uuid.uuid4())  # Generate a unique ID
    return notes

# Load notes from file
def load_notes():
    try:
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, "r") as file:
                notes = json.load(file)
                return ensure_note_ids(notes)
        return []
    except Exception as e:
        print(f"Error loading notes: {e}")
        return []

# Save notes to file
def save_notes(notes):
    try:
        with open(NOTES_FILE, "w") as file:
            json.dump(notes, file)
    except Exception as e:
        print(f"Error saving notes: {e}")

# Home route
@app.route("/")
def home():
    return render_template("index.html")

# API to get all notes
@app.route("/api/notes", methods=["GET"])
def get_notes():
    notes = load_notes()
    return jsonify(notes)

# Route to handle image uploads
@app.route("/upload-image", methods=["POST"])
def upload_image():
    try:
        if "image" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["image"]
        note_id = request.form.get("noteId")

        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Save the file
        filename = f"{note_id}_{file.filename}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Return the file path
        image_path = f"/uploads/{filename}"
        return jsonify({"success": True, "imagePath": image_path})
    except Exception as e:
        print(f"Error uploading image: {e}")
        return jsonify({"success": False, "message": "Internal server error"}), 500

# Serve uploaded images statically
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# WebSocket event for adding a note
@socketio.on("add_note")
def handle_add_note(data):
    try:
        print("Received new note data:", data)  # Debugging
        notes = load_notes()
        note = {"id": str(uuid.uuid4()), **data}  # Ensure a unique ID
        notes.append(note)
        save_notes(notes)
        emit("update_notes", notes, broadcast=True)
    except Exception as e:
        print(f"Error adding note: {e}")

# WebSocket event for updating a note
@socketio.on("update_note")
def handle_update_note(data):
    notes = load_notes()
    note_id = data.get("id")
    updated_note = data.get("note")

    for i, note in enumerate(notes):
        if "id" in note and note["id"] == note_id:
            notes[i] = {**note, **updated_note}
            save_notes(notes)
            emit("update_notes", notes, broadcast=True)
            break

# WebSocket event for deleting a note
@socketio.on("delete_note")
def handle_delete_note(note_id):
    notes = load_notes()
    notes = [note for note in notes if "id" in note and note["id"] != note_id]
    save_notes(notes)
    emit("update_notes", notes, broadcast=True)

# WebSocket event for reordering notes
@socketio.on("reorder_notes")
def handle_reorder_notes(new_notes):
    try:
        save_notes(new_notes)
        emit("update_notes", new_notes, broadcast=True)
    except Exception as e:
        print(f"Error reordering notes: {e}")

# **Don't use `socketio.run()` in production!**
if __name__ == "__main__":
    # For development, use socketio.run (DO NOT use in production)
    # socketio.run(app, host="0.0.0.0", port=5000, debug=True)
    pass
