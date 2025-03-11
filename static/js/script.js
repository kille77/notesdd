const socket = io();
let currentPageId = null;
let currentImageIndex = 0;
let currentImages = [];
let debounceTimeout;

// Toggle visibility of the "Add Note" button
function toggleAddNoteButton(visible) {
    const addNoteButton = document.querySelector(".add-note-btn");
    addNoteButton.style.display = visible ? "block" : "none";
}

// Fetch and populate pages in the dropdown
function fetchPages() {
    fetch("/api/pages")
        .then(response => response.json())
        .then(pages => {
            const pageSelect = document.getElementById("pageSelect");
            pageSelect.innerHTML = '<option value="">Select a page</option>';
            pages.forEach(page => {
                const option = document.createElement("option");
                option.value = page.id;
                option.textContent = page.name;
                pageSelect.appendChild(option);
            });
        })
        .catch(error => console.error("Error fetching pages:", error));
}

// Create a new page
function createPage() {
    const pageName = document.getElementById("pageName").value;
    if (!pageName) return alert("Page name is required");

    fetch("/api/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: pageName })
    })
        .then(response => response.json())
        .then(page => {
            // Select the new page in the dropdown
            const pageSelect = document.getElementById("pageSelect");
            pageSelect.value = page.id;

            // Update the header and title
            document.querySelector("h1").textContent = page.name;
            document.title = page.name;

            // Load the notes for the new page
            currentPageId = page.id;
            loadPageNotes();

            // Clear the input field
            document.getElementById("pageName").value = "";
        })
        .catch(error => console.error("Error creating page:", error));
}

// Load notes for the selected page
function loadPageNotes() {
    const pageSelect = document.getElementById("pageSelect");
    currentPageId = pageSelect.value;

    // Hide "Add Note" button if no page is selected
    toggleAddNoteButton(!!currentPageId);

    if (!currentPageId) {
        // Reset header and title to default
        document.querySelector("h1").textContent = "Sticky Notes";
        document.title = "Sticky Notes";
        renderNotes([]); // Clear the notes container
        return;
    }

    // Fetch the page details to get the page name
    fetch(`/api/pages/${currentPageId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(page => {
            // Update the header with the page name
            document.querySelector("h1").textContent = page.name;
            // Update the title tag with the page name
            document.title = page.name;
            // Fetch and render the notes for the selected page
            return fetch(`/api/pages/${currentPageId}/notes`);
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(notes => renderNotes(notes))
        .catch(error => {
            console.error("Error fetching page or notes:", error);
            alert("Failed to load page. Please try again.");
        });
}

// Delete the selected page
function deletePage() {
    const pageSelect = document.getElementById("pageSelect");
    const pageId = pageSelect.value;
    if (!pageId) return alert("No page selected");

    if (confirm("Delete this page and all its notes?")) {
        fetch(`/api/pages/${pageId}`, { method: "DELETE" })
            .then(() => {
                // Remove the deleted page from the dropdown
                const optionToRemove = pageSelect.querySelector(`option[value="${pageId}"]`);
                if (optionToRemove) {
                    optionToRemove.remove();
                }

                // Reset to default page
                pageSelect.value = "";
                currentPageId = null;
                loadPageNotes(); // This will reset the header, title, and notes
            })
            .catch(error => console.error("Error deleting page:", error));
    }
}

// Add a new note
function addNote() {
    if (!currentPageId) return alert("Please select a page first");
    socket.emit("add_note", { text: "New Note", color: "#ffff00", page_id: currentPageId });
}

// Render notes to the container
function renderNotes(notes) {
    const container = document.getElementById("notes-container");
    container.innerHTML = "";
    notes.forEach(note => {
        const noteElement = document.createElement("div");
        noteElement.className = "note";
        noteElement.style.backgroundColor = note.color;
        noteElement.innerHTML = `
            <textarea oninput="updateNote('${note.id}', this.value)">${note.text}</textarea>
            <button class="delete-btn" onclick="deleteNote('${note.id}')">×</button>
            <div class="uploaded-images-container">
                ${note.images.map(image => `
                    <img src="${image}" class="uploaded-image" onclick="openModal('${note.id}', '${image}')">
                `).join('')}
            </div>
            <input type="file" accept="image/*" multiple onchange="uploadImage('${note.id}', this.files)" class="image-upload">
            <div class="color-picker">
                <div class="color-box red" onclick="changeColor('${note.id}', 'red')"></div>
                <div class="color-box yellow" onclick="changeColor('${note.id}', 'yellow')"></div>
                <div class="color-box green" onclick="changeColor('${note.id}', 'green')"></div>
            </div>
        `;
        container.appendChild(noteElement);
    });
}

// Update a note's text with debounce
function updateNote(id, text) {
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
        socket.emit("update_note", { id, note: { text } });
    }, 500);
}

// Delete a note
function deleteNote(id) {
    if (confirm("Delete this note?")) socket.emit("delete_note", id);
}

// Upload images to a note
function uploadImage(noteId, files) {
    const formData = new FormData();
    formData.append("noteId", noteId);
    Array.from(files).forEach(file => {
        formData.append("images", file);
    });
    fetch("/upload-image", { method: "POST", body: formData })
        .then(response => {
            if (response.ok) {
                loadPageNotes();
            } else {
                response.json().then(data => alert(data.message));
            }
        })
        .catch(error => {
            console.error("Error uploading image:", error);
        });
}

// Change note color
function changeColor(noteId, color) {
    socket.emit("update_note", { id: noteId, note: { color } });
}

// Open the modal to view images
function openModal(noteId, image) {
    currentNoteId = noteId;
    currentImageIndex = 0;

    fetch(`/api/notes/${noteId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(note => {
            currentImages = note.images;
            displayImage(image);
            document.getElementById("imageModal").style.display = "flex";
        })
        .catch(error => {
            console.error("Error fetching note:", error);
            alert("Failed to fetch note. Please try again.");
        });
}

// Display the current image in the modal
function displayImage(image) {
    const modalImage = document.getElementById("modalImage");
    modalImage.src = image;

    document.querySelector(".prev-btn").disabled = currentImageIndex === 0;
    document.querySelector(".next-btn").disabled = currentImageIndex === currentImages.length - 1;
}

// Navigate between images
function navigateImages(direction) {
    currentImageIndex += direction;
    displayImage(currentImages[currentImageIndex]);
}

// Close the modal
function closeModal() {
    document.getElementById("imageModal").style.display = "none";
}

// Add event listener to close modal when clicking outside the modal content
document.getElementById("imageModal").addEventListener("click", function(event) {
    if (event.target === this) {
        closeModal();
    }
});

// Listen for page creation events
socket.on("page_created", (page) => {
    const pageSelect = document.getElementById("pageSelect");
    const option = document.createElement("option");
    option.value = page.id;
    option.textContent = page.name;
    pageSelect.appendChild(option);
});

// Listen for page deletion events
socket.on("page_deleted", (data) => {
    const pageSelect = document.getElementById("pageSelect");
    const optionToRemove = pageSelect.querySelector(`option[value="${data.id}"]`);
    if (optionToRemove) {
        optionToRemove.remove();
    }

    // If the deleted page was the currently selected page, reset to default
    if (currentPageId === data.id) {
        pageSelect.value = "";
        currentPageId = null;
        loadPageNotes(); // Reset the header, title, and notes
    }
});

// Listen for update_notes event
socket.on("update_notes", (data) => {
// Only update the notes if the page_id matches the currently selected page
if (data.page_id === currentPageId) {
renderNotes(data.notes);
}
});

// Initial fetch of pages and notes
fetchPages();

// Set the correct state for the "Add Note" button on page load
document.addEventListener("DOMContentLoaded", () => {
    const pageSelect = document.getElementById("pageSelect");
    if (pageSelect.value === "") {
        toggleAddNoteButton(false); // Hide the button if no page is selected
    }
});
