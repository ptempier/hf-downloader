const BASE_URL = window.BASE_URL || '';

// Initialize Socket.IO
function initializeSocket() {
    if (typeof io !== 'undefined') {
        const socketPath = BASE_URL ? `${BASE_URL}/socket.io` : '/socket.io';
        return io({ path: socketPath });
    } else {
        console.warn('Socket.IO client not found.');
        return { on: () => {}, emit: () => {}, disconnect: () => {} };
    }
}

let socket = initializeSocket();

// DOM elements
const refreshBtn = document.getElementById('refreshBtn');
const searchInput = document.getElementById('searchInput');
const loadingIndicator = document.getElementById('loadingIndicator');
const modelsContainer = document.getElementById('modelsContainer');
const deleteModal = document.getElementById('deleteModal');
const deleteModelName = document.getElementById('deleteModelName');

// State
let allModels = [];
let currentModelToDelete = null;

// Utilities
const buildURL = (path) => BASE_URL ? `${BASE_URL}/${path.replace(/^\/+/, '')}` : `/${path.replace(/^\/+/, '')}`;

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

// Create HTML elements
function createFileHTML(file, idx) {
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

function createFileGroupHTML(group) {
    const filesHTML = group.files.map(createFileHTML).join('');
    return `
        <div class="file-group">
            <div class="file-group-header" onclick="toggleFileGroup(this)">
                <span>${group.name} (${group.count} files - ${group.size})</span>
                <span class="toggle-icon">▶</span>
            </div>
            <div class="file-group-content">
                <div class="file-list">${filesHTML}</div>
            </div>
        </div>
    `;
}

function createModelHTML(model) {
    const groupsHTML = model.groups.map(createFileGroupHTML).join('');
    
    let individualFilesHTML = '';
    if (model.individual_files?.length > 0) {
        const items = model.individual_files.map(createFileHTML).join('');
        individualFilesHTML = `
            <div class="file-group">
                <div class="file-group-content expanded">
                    <div class="file-list">${items}</div>
                </div>
            </div>
        `;
    }
    
    const totalFiles = (model.groups?.reduce((s, g) => s + g.count, 0) || 0) + (model.individual_files?.length || 0);
    
    return `
        <div class="model-card" data-model-name="${model.name.toLowerCase()}">
            <div class="model-header">
                <div class="model-info">
                    <div class="model-path">${model.path}</div>
                    <div class="model-count">${totalFiles} files</div>
                </div>
                <div class="model-size-right">${model.total_size}</div>
                <div class="model-actions">
                    <button class="btn-icon btn-primary" onclick="updateModel('${model.name}')" title="Update Model">↻</button>
                    <button class="btn-icon btn-danger" onclick="showDeleteModal('${model.name}', '${model.path}')" title="Delete Model">🗑</button>
                </div>
            </div>
            <div class="model-files">${groupsHTML}${individualFilesHTML}</div>
        </div>
    `;
}

// UI functions
function toggleFileGroup(header) {
    const content = header.nextElementSibling;
    const icon = header.querySelector('.toggle-icon');
    const isExpanded = content.classList.toggle('expanded');
    header.classList.toggle('expanded', isExpanded);
    icon.textContent = isExpanded ? '▼' : '▶';
}

function filterModels() {
    const query = searchInput.value.toLowerCase().trim();
    document.querySelectorAll('.model-card').forEach(card => {
        const modelName = card.dataset.modelName;
        card.style.display = (!query || modelName.includes(query)) ? 'block' : 'none';
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
    modelsContainer.innerHTML = models.map(createModelHTML).join('');
}

// API functions
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
        alert(response.ok ? `Update started for ${repoId}` : `Error: ${result.error}`);
    } catch (error) {
        alert(`Error updating model: ${error.message}`);
    }
}

// Modal functions
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
            loadModels();
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
document.getElementById('confirmDeleteBtn').addEventListener('click', confirmDelete);
document.getElementById('cancelDeleteBtn').addEventListener('click', hideDeleteModal);
document.querySelector('.close').addEventListener('click', hideDeleteModal);
deleteModal.addEventListener('click', (e) => e.target === deleteModal && hideDeleteModal());

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideDeleteModal();
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        loadModels();
    }
});

// Socket events
socket.on('connect', () => console.log('Connected to server'));
socket.on('disconnect', () => console.log('Disconnected from server'));

// Initialize
window.addEventListener('load', loadModels);