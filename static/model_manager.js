// Get base URL from the window global set by the template
const BASE_URL = window.BASE_URL || '';

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
    return BASE_URL + '/' + path;
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
            <h3>❌ Error</h3>
            <p>${message}</p>
            <button onclick="loadModels()" class="btn btn-primary">Try Again</button>
        </div>
    `;
}

function createFileGroupHTML(group) {
    const filesHTML = group.files.map((file, idx) => {
        // file is an object: { name, path, size, size_bytes, mtime, date }
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
    // Render all individual (ungrouped) files inside one compact file-group
    let individualFilesHTML = '';
    if (model.individual_files && model.individual_files.length > 0) {
        const items = model.individual_files.map((f, i) => createFileItemHTML(f, i)).join('');
        // render files directly inside the file-group content; count will be shown in header
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
    
    // compute total files for the model (group counts + individual files)
    const groupsTotal = model.groups ? model.groups.reduce((s, g) => s + (g.count || 0), 0) : 0;
    const individualTotal = model.individual_files ? model.individual_files.length : 0;
    const modelFileCount = groupsTotal + individualTotal;
    return `
        <div class="model-card" data-model-name="${model.name.toLowerCase()}">
            <div class="model-header">
                <div class="model-info">
                    <div class="model-path">${model.path}</div