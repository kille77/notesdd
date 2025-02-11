from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import os
import sqlite3
import uuid

# Get the directory where the script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback_secret_key")
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")  # Folder to store uploaded images
socketio = SocketIO(app, cors_allowed_origins="*")  # Allow all origins for Socket.IO

# Ensure the uploads folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Database setup
DB_FILE = os.path.join(BASE_DIR, "notes.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Allows access by column name
    return conn

# Create notes table
def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                color TEXT DEFAULT '#fff3cd',
                image TEXT DEFAULT NULL
            )
        """)
        conn.commit()

init_db()  # Ensure database is initialized

# Load notes from database
def load_notes():
    try:
        with get_db_connection() as conn:
            notes = conn.execute("SELECT * FROM notes").fetchall()
            return [dict(note) for note in notes]
    except Exception as e:
        print(f"Error loading notes: {e}")
        return []

# Save a new note to database
def save_note(note):
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO notes (id, text, color, image) VALUES (?, ?, ?, ?)",
                         (note["id"], note["text"], note["color"], note.get("image")))
            conn.commit()
    except Exception as e:
        print(f"Error saving note: {e}")

# Update a note in the database
def update_note(note_id, updated_note):
    try:
        with get_db_connection() as conn:
            conn.execute("UPDATE notes SET text = ?, color = ?, image = ? WHERE id = ?",
                         (updated_note.get("text"), updated_note.get("color"), updated_note.get("image"), note_id))
            conn.commit()
    except Exception as e:
        print(f"Error updating note: {e}")

# Delete a note from database
def delete_note(note_id):
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            conn.commit()
    except Exception as e:
        print(f"Error deleting note: {e}")

# Home route
@app.route("/")
def home():
    return render_template("index.html")

# API to get all notes
@app.route("/api/notes", methods=["GET"])
def get_notes():
    notes = load_notes()
    return jsonify(notes)

# Image upload route
@app.route("/upload-image", methods=["POST"])
def upload_image():
    try:
        if "image" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["image"]
        note_id = request.form.get("noteId")

        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Validate file type
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif"}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({"success": False, "message": "Invalid file type"}), 400

        # Save the file with a unique name
        filename = f"{note_id}_{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # Update the note with image path
        image_path = f"/uploads/{filename}"
        update_note(note_id, {"image": image_path})

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
        note = {"id": str(uuid.uuid4()), **data}
        save_note(note)
        emit("update_notes", load_notes(), broadcast=True)
    except Exception as e:
        emit("error", {"message": "Could not save note", "error": str(e)})

# WebSocket event for updating a note
@socketio.on("update_note")
def handle_update_note(data):
    try:
        note_id = data.get("id")
        updated_note = data.get("note")
        update_note(note_id, updated_note)
        emit("update_notes", load_notes(), broadcast=True)
    except Exception as e:
        emit("error", {"message": "Could not update note", "error": str(e)})

# WebSocket event for deleting a note
@socketio.on("delete_note")
def handle_delete_note(note_id):
    try:
        delete_note(note_id)
        emit("update_notes", load_notes(), broadcast=True)
    except Exception as e:
        emit("error", {"message": "Could not delete note", "error": str(e)})

# **Don't use `socketio.run()` in production!**
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
