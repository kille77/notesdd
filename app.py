from flask import Flask, render_template, request, jsonify, send_from_directory
 from flask_socketio import SocketIO, emit
 import os
 import sqlite3
 import json
 import uuid
 
 # Get the directory where the script is located
 @@ -15,67 +15,35 @@
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
         with get_db_connection() as conn:
             notes = conn.execute("SELECT * FROM notes").fetchall()
             return [dict(note) for note in notes]
         if os.path.exists(NOTES_FILE):
             with open(NOTES_FILE, "r") as file:
                 notes = json.load(file)
                 return ensure_note_ids(notes)
         return []
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
 # Save notes to file
 def save_notes(notes):
     try:
         with get_db_connection() as conn:
             conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
             conn.commit()
         with open(NOTES_FILE, "w") as file:
             json.dump(notes, file)
     except Exception as e:
         print(f"Error deleting note: {e}")
         print(f"Error saving notes: {e}")
 
 # Home route
 @app.route("/")
 @@ -88,7 +56,7 @@ def get_notes():
     notes = load_notes()
     return jsonify(notes)
 
 # Image upload route
 # Route to handle image uploads
 @app.route("/upload-image", methods=["POST"])
 def upload_image():
     try:
 @@ -101,21 +69,13 @@ def upload_image():
         if file.filename == "":
             return jsonify({"success": False, "message": "No file selected"}), 400
 
         # Validate file type
         allowed_extensions = {".jpg", ".jpeg", ".png", ".gif"}
         ext = os.path.splitext(file.filename)[1].lower()
         if ext not in allowed_extensions:
             return jsonify({"success": False, "message": "Invalid file type"}), 400
 
         # Save the file with a unique name
         filename = f"{note_id}_{uuid.uuid4().hex}{ext}"
         # Save the file
         filename = f"{note_id}_{file.filename}"
         filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
         file.save(filepath)
 
         # Update the note with image path
         # Return the file path
         image_path = f"/uploads/{filename}"
         update_note(note_id, {"image": image_path})
 
         return jsonify({"success": True, "imagePath": image_path})
     except Exception as e:
         print(f"Error uploading image: {e}")
 @@ -130,32 +90,48 @@ def uploaded_file(filename):
 @socketio.on("add_note")
 def handle_add_note(data):
     try:
         note = {"id": str(uuid.uuid4()), **data}
         save_note(note)
         emit("update_notes", load_notes(), broadcast=True)
         print("Received new note data:", data)  # Debugging
         notes = load_notes()
         note = {"id": str(uuid.uuid4()), **data}  # Ensure a unique ID
         notes.append(note)
         save_notes(notes)
         emit("update_notes", notes, broadcast=True)
     except Exception as e:
         emit("error", {"message": "Could not save note", "error": str(e)})
         print(f"Error adding note: {e}")
 
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
         delete_note(note_id)
         emit("update_notes", load_notes(), broadcast=True)
         save_notes(new_notes)
         emit("update_notes", new_notes, broadcast=True)
     except Exception as e:
         emit("error", {"message": "Could not delete note", "error": str(e)})
         print(f"Error reordering notes: {e}")
 
 # **Don't use `socketio.run()` in production!**
 if __name__ == "__main__":
     socketio.run(app, host="0.0.0.0", port=5000, debug=True)
     # For development, use socketio.run (DO NOT use in production)
     # socketio.run(app, host="0.0.0.0", port=5000, debug=True)
     pass
