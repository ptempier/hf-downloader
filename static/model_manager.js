// Get base URL from the window global set by the template
const BASE_URL = window.BASE_URL || '';

// Initialize Socket.IO connection with proper path handling
let socket;
function initializeSocket() {
    if (typeof io !== 'undefined') {
        // Configure Socket.IO client with the correct path for subdirectory deployments
        const socketPath = BASE_URL ? `${BASE_URL}/socket.io` : '/socket.io';
        socket = io({
            path: socketPath
        });
    } else {
        // Fallback noop socket to avoid runtime errors when the client script is missing
        console.warn('Socket.IO client not found (io is undefined). Real-time progress will be disabled.');
        socket = {
            on: () => {},
            emit: () => {},
            disconnect: () => {}
        };
    }
}

// Initialize socket when script loads
initializeSocket();

// DOM elements
const refreshBtn = document.getElementById('refreshBtn');
const searchInput = document.getElementById('searchInput');
const loadingIndicator = document.getElementById('loadingIndicator');
const modelsContainer = document.getElementById('modelsContainer');

// Modal elements
const deleteModal = document.getElementById('deleteModal');
const deleteModelName = document.getElementById('deleteModelName');
const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');

// State
let allModels = [];
let currentModelToDelete = null;

// Helper function to build URLs
function buildURL(path) {
    // Remove leading slashes from path and ensure single slash between BASE_URL and path
    const cleanPath = path.replace(/^\/+/, '');
    return BASE_URL ? `${BASE_URL}/${cleanPath}` : `/${cleanPath}`;
}

// Utility functions
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function showLoading() {
    loadingIndicator.classList.remove('hidden');
    modelsContainer.innerHTML = '';
}

function hideLoading() {
    loadingIndicator.classList.add('hidden');
}

function showError(message) {
    modelsContainer.innerHTML = `
        <div class="error-message">
            <h3>⚠ Error</h3>
            <p>${message}</p>
            <button onclick="loadModels()" class="btn btn-primary">Try Again</button>
        </div>
    `;
}

function createFileGroupHTML(group) {
    const filesHTML = group.files.map((file, idx) => {
        return `
            <div class="file-item">
                <span class="file-name">${file.name}</span>
                <span class="file-meta">
                    <span class="file-index">${idx + 1}.</span>
                    <span class="file-size">${file.size}</span>
                    <span class="file-date">${file.date || ''}</span>
                </span>
            </div>
        `;
    }).join('');

    return `
        <div class="file-group">
            <div class="file-group-header" onclick="toggleFileGroup(this)">
                <span>${group.name} (${group.count} files - ${group.size})</span>
                <span class="toggle-icon">▶</span>
            </div>
            <div class="file-group-content">
                <div class="file-list">
                    ${filesHTML}
                </div>
            </div>
        </div>
    `;
}

function createFileItemHTML(file, idx) {
    return `
        <div class="file-item">
            <span class="file-name">${file.name}</span>
            <span class="file-meta">
                <span class="file-index">${idx + 1}.</span>
                <span class="file-size">${file.size}</span>
                <span class="file-date">${file.date || ''}</span>
            </span>
        </div>
    `;
}

function createModelHTML(model) {
    const groupsHTML = model.groups.map(createFileGroupHTML).join('');
    let individualFilesHTML = '';
    if (model.individual_files && model.individual_files.length > 0) {
        const items = model.individual_files.map((f, i) => createFileItemHTML(f, i)).join('');
        individualFilesHTML = `
            <div class="file-group">
                <div class="file-group-content expanded">
                    <div class="file-list">
                        ${items}
                    </div>
                </div>
            </div>
        `;
    }
    
    const groupsTotal = model.groups ? model.groups.reduce((s, g) => s + (g.count || 0), 0) : 0;
    const individualTotal = model.individual_files ? model.individual_files.length : 0;
    const modelFileCount = groupsTotal + individualTotal;
    
    return `
        <div class="model-card" data-model-name="${model.name.toLowerCase()}">
            <div class="model-header">
                <div class="model-info">
                    <div class="model-path">${model.path}</div>
                </div>

                    <div class="model-count">${modelFileCount} files</div>
                <div class="model-size-right">${model.total_size}</div>
                <div class="model-actions">
                    <button class="btn-icon btn-primary" onclick="updateModel('${model.name}')" title="Update Model">↻</button>
                    <button class="btn-icon btn-danger" onclick="showDeleteModal('${model.name}', '${model.path}')" title="Delete Model">🗑</button>
                </div>
            </div>
            <div class="model-files">
                ${groupsHTML}
                ${individualFilesHTML}
            </div>
        </div>
    `;
}

function toggleFileGroup(header) {
    const content = header.nextElementSibling;
    const icon = header.querySelector('.toggle-icon');
    
    if (content.classList.contains('expanded')) {
        content.classList.remove('expanded');
        header.classList.remove('expanded');
        icon.textContent = '▶';
    } else {
        content.classList.add('expanded');
        header.classList.add('expanded');
        icon.textContent = '▼';
    }
}

function filterModels() {
    const query = searchInput.value.toLowerCase().trim();
    const modelCards = document.querySelectorAll('.model-card');
    
    modelCards.forEach(card => {
        const modelName = card.dataset.modelName;
        const isVisible = !query || modelName.includes(query);
        card.style.display = isVisible ? 'block' : 'none';
    });
}

function renderModels(models) {
    if (models.length === 0) {
        modelsContainer.innerHTML = `
            <div class="error-message">
                <h3>🔍 No Models Found</h3>
                <p>No models found in /models/ directory.</p>
                <p>Download some models first using the <a href="${BASE_URL}/">Download</a> page.</p>
            </div>
        `;
        return;
    }

    const modelsHTML = models.map(createModelHTML).join('');
    modelsContainer.innerHTML = modelsHTML;
}

async function loadModels() {
    showLoading();
    try {
        const response = await fetch(buildURL('api/models'));
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const models = await response.json();
        allModels = models;
        renderModels(models);
        hideLoading();
    } catch (error) {
        hideLoading();
        showError(`Failed to load models: ${error.message}`);
        console.error('Error loading models:', error);
    }
}

async function updateModel(repoId) {
    try {
        const response = await fetch(buildURL('api/models/update'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_id: repoId })
        });
        
        const result = await response.json();
        if (response.ok) {
            alert(`Update started for ${repoId}`);
        } else {
            alert(`Error: ${result.error}`);
        }
    } catch (error) {
        alert(`Error updating model: ${error.message}`);
    }
}

function showDeleteModal(modelName, modelPath) {
    currentModelToDelete = { name: modelName, path: modelPath };
    deleteModelName.textContent = modelName;
    deleteModal.classList.remove('hidden');
}

function hideDeleteModal() {
    deleteModal.classList.add('hidden');
    currentModelToDelete = null;
}

async function confirmDelete() {
    if (!currentModelToDelete) return;
    
    try {
        const response = await fetch(buildURL('api/models/delete'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentModelToDelete.path })
        });
        
        const result = await response.json();
        if (response.ok) {
            alert(`Model deleted: ${currentModelToDelete.name}`);
            hideDeleteModal();
            loadModels(); // Refresh the list
        } else {
            alert(`Error: ${result.error}`);
        }
    } catch (error) {
        alert(`Error deleting model: ${error.message}`);
    }
}

// Event listeners
refreshBtn.addEventListener('click', loadModels);
searchInput.addEventListener('input', filterModels);
confirmDeleteBtn.addEventListener('click', confirmDelete);
cancelDeleteBtn.addEventListener('click', hideDeleteModal);

// Modal close handlers
document.querySelector('.close').addEventListener('click', hideDeleteModal);
deleteModal.addEventListener('click', (e) => {
    if (e.target === deleteModal) hideDeleteModal();
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideDeleteModal();
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        loadModels();
    }
});

// Socket.IO event handlers for real-time updates
socket.on('connect', () => console.log('Connected to server'));
socket.on('disconnect', () => console.log('Disconnected from server'));

// Load models on page load
window.addEventListener('load', loadModels);
