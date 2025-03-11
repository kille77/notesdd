import os
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
import eventlet
eventlet.monkey_patch()

# Flask app initialization
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "fallback_secret_key")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///notes.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# File upload configuration
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB limit

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database, socket.io, and Flask-Migrate
db = SQLAlchemy(app)
migrate = Migrate(app, db)  # Initialize Flask-Migrate
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# Database Models
class Page(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)  # Name of the page
    notes = db.relationship("Note", backref="page", lazy=True)  # One-to-many relationship with notes

class Note(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    text = db.Column(db.Text, nullable=False, default="New Note")
    color = db.Column(db.String(20), default="#ffff00")
    images = db.Column(db.Text, nullable=True)  # Store image paths as a comma-separated string
    page_id = db.Column(db.String(36), db.ForeignKey("page.id"), nullable=False)  # Foreign key to associate with a page

# Create database tables (this should only be needed when you first create the tables)
with app.app_context():
    db.create_all()

# Utility function to check allowed file extensions
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Home route
@app.route("/")
def home():
    return render_template("index.html")

# API to create a new page
@app.route("/api/pages", methods=["POST"])
def create_page():
    data = request.get_json()
    page = Page(name=data.get("name"))
    db.session.add(page)
    db.session.commit()

    # Emit a WebSocket event to all clients
    socketio.emit("page_created", {"id": page.id, "name": page.name}, namespace="/")

    return jsonify({"id": page.id, "name": page.name}), 201

# API to get all pages
@app.route("/api/pages", methods=["GET"])
def get_pages():
    pages = Page.query.all()
    return jsonify([{"id": page.id, "name": page.name} for page in pages])

# API to delete a page
@app.route("/api/pages/<page_id>", methods=["DELETE"])
def delete_page(page_id):
    page = db.session.get(Page, page_id)
    if not page:
        return jsonify({"error": "Page not found"}), 404

    # Delete associated notes and their images
    for note in page.notes:
        if note.images:
            image_paths = note.images.split(',')
            for image_path in image_paths:
                filename = os.path.basename(image_path)
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
        db.session.delete(note)

    db.session.delete(page)
    db.session.commit()

    # Emit a WebSocket event to all clients
    socketio.emit("page_deleted", {"id": page_id}, namespace="/")

    return jsonify({"success": True})

# API to get a specific note by ID
@app.route("/api/notes/<note_id>", methods=["GET"])
def get_note_by_id(note_id):
    note = db.session.get(Note, note_id)  # Fetch the note by ID
    if note:
        return jsonify({
            "id": note.id,
            "text": note.text,
            "color": note.color,
            "images": note.images.split(',') if note.images else []  # Split the image paths into a list
        })
    else:
        return jsonify({"error": "Note not found"}), 404
    
    # API to get a specific page by ID
@app.route("/api/pages/<page_id>", methods=["GET"])
def get_page_by_id(page_id):
    page = db.session.get(Page, page_id)  # Fetch the page by ID
    if page:
        return jsonify({
            "id": page.id,
            "name": page.name
        })
    else:
        return jsonify({"error": "Page not found"}), 404

# API to get notes for a specific page
@app.route("/api/pages/<page_id>/notes", methods=["GET"])
def get_notes_for_page(page_id):
    notes = Note.query.filter_by(page_id=page_id).all()
    return jsonify([{
        "id": note.id,
        "text": note.text,
        "color": note.color,
        "images": note.images.split(',') if note.images else []
    } for note in notes])

# API to upload images
@app.route("/upload-image", methods=["POST"])
def upload_image():
    if "images" not in request.files:
        return jsonify({"success": False, "message": "No files uploaded"}), 400

    files = request.files.getlist("images")
    note_id = request.form.get("noteId")

    # Get the note
    note = db.session.get(Note, note_id)
    if not note:
        return jsonify({"success": False, "message": "Note not found"}), 404

    # Allow unlimited images, just track them
    existing_images = note.images.split(',') if note.images else []

    # Validate files
    filenames = []
    for file in files:
        if file.filename == "" or not allowed_file(file.filename):
            return jsonify({"success": False, "message": "Invalid file type"}), 400

        filename = secure_filename(f"{note_id}_{uuid.uuid4().hex}_{file.filename}")
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        filenames.append(f"/uploads/{filename}")

    # Append new image paths to the existing list of images
    if note.images:
        note.images += "," + ",".join(filenames)
    else:
        note.images = ",".join(filenames)
    
    db.session.commit()

    # Emit the updated notes for the specific page
    socketio.emit("update_notes", {"page_id": note.page_id, "notes": get_notes_for_page(note.page_id).json}, namespace="/")

    return jsonify({"success": True, "imagePaths": filenames})

# Serve uploaded images
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# WebSocket event handlers
@socketio.on("add_note")
def handle_add_note(data):
    try:
        page_id = data.get("page_id")
        if not page_id:
            return jsonify({"error": "Page ID is required"}), 400

        note = Note(text=data.get("text", "New Note"), color=data.get("color", "#fff3cd"), page_id=page_id)
        db.session.add(note)
        db.session.commit()

        # Emit the updated notes for the specific page
        socketio.emit("update_notes", {"page_id": page_id, "notes": get_notes_for_page(page_id).json}, namespace="/")
    except Exception as e:
        print(f"Error adding note: {e}")

@socketio.on("update_note")
def handle_update_note(data):
    try:
        note = db.session.get(Note, data.get("id"))
        if note:
            note.text = data["note"].get("text", note.text)
            note.color = data["note"].get("color", note.color)
            db.session.commit()

            # Emit the updated notes for the specific page
            socketio.emit("update_notes", {"page_id": note.page_id, "notes": get_notes_for_page(note.page_id).json}, namespace="/")
    except Exception as e:
        print(f"Error updating note: {e}")

@socketio.on("delete_note")
def handle_delete_note(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note:
            # Delete associated images
            if note.images:
                image_paths = note.images.split(',')
                for image_path in image_paths:
                    filename = os.path.basename(image_path)
                    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)

            page_id = note.page_id  # Store the page_id before deleting the note
            db.session.delete(note)
            db.session.commit()

            # Emit the updated notes for the specific page
            socketio.emit("update_notes", {"page_id": page_id, "notes": get_notes_for_page(page_id).json}, namespace="/")
        else:
            print(f"Note with ID {note_id} not found.")
    except Exception as e:
        print(f"Error deleting note: {e}")

# Run the app (for production)
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    socketio.run(app, host=host, port=port)
