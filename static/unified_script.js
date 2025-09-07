// Get base URL from the window global set by the template
const BASE_URL = window.BASE_URL || '';

// Initialize Socket.IO connection with proper path handling
let socket;
function initializeSocket() {
    if (typeof io !== 'undefined') {
        const socketPath = BASE_URL ? `${BASE_URL}/socket.io` : '/socket.io';
        socket = io({
            path: socketPath
        });
    } else {
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
const downloadForm = document.getElementById('downloadForm');
const downloadBtn = document.getElementById('downloadBtn');
const refreshBtn = document.getElementById('refreshBtn');
const searchInput = document.getElementById('searchInput');
const loadingIndicator = document.getElementById('loadingIndicator');
const modelsContainer = document.getElementById('modelsContainer');
const logContainer = document.getElementById('logContainer');
const logOutput = document.getElementById('logOutput');
const clearLogBtn = document.getElementById('clearLogBtn');

// Modal elements
const deleteModal = document.getElementById('deleteModal');
const deleteModelName = document.getElementById('deleteModelName');
const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');

// State
let isDownloading = false;
let allModels = [];
let currentModelToDelete = null;
const logs = [];

// Helper function to build URLs
function buildURL(path) {
    const cleanPath = path.replace(/^\/+/, '');
    return BASE_URL ? `${BASE_URL}/${cleanPath}` : `/${cleanPath}`;
}

// ASCII Progress Bar Function
function createASCIIProgress(progress, width = 30) {
    const filled = Math.round((progress / 100) * width);
    const empty = width - filled;
    const bar = '█'.repeat(filled) + '░'.repeat(empty);
    return `[${bar}] ${Math.round(progress)}%`;
}

// Console logging functions
function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `[${timestamp}] ${message}`;
    logs.push(logEntry);
    logOutput.textContent = logs.join('\n');
    logOutput.scrollTop = logOutput.scrollHeight;
    logContainer.classList.remove('hidden');
}

function addProgressLog(message, progress = null) {
    const timestamp = new Date().toLocaleTimeString();
    let logEntry = `[${timestamp}] ${message}`;
    if (progress !== null) {
        logEntry += ` ${createASCIIProgress(progress)}`;
    }
    
    // Replace last line if it's a progress update
    if (logs.length > 0 && logs[logs.length - 1].includes('█')) {
        logs[logs.length - 1] = logEntry;
    } else {
        logs.push(logEntry);
    }
    
    logOutput.textContent = logs.join('\n');
    logOutput.scrollTop = logOutput.scrollHeight;
}

// Download functions
function resetDownloadUI() {
    isDownloading = false;
    downloadBtn.disabled = false;
    downloadBtn.textContent = 'Start Download';
}

function startDownloadUI() {
    isDownloading = true;
    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Downloading...';
    addLog('🚀 ===== DOWNLOAD STARTED =====', 'info');
}

// Model Manager functions
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
                <p>Download some models first using the form above.</p>
            </div>
        `;
        return;
    }

    const modelsHTML = models.map(createModelHTML).join('');
    modelsContainer.innerHTML = modelsHTML;
}

async function loadModels() {
    showLoading();
    addLog('🔍 Loading models...', 'info');
    try {
        const response = await fetch(buildURL('api/models'));
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const models = await response.json();
        allModels = models;
        renderModels(models);
        hideLoading();
        addLog(`✅ Loaded ${models.length} models`, 'success');
    } catch (error) {
        hideLoading();
        showError(`Failed to load models: ${error.message}`);
        addLog(`❌ Failed to load models: ${error.message}`, 'error');
        console.error('Error loading models:', error);
    }
}

async function updateModel(repoId) {
    try {
        addLog(`🔄 ===== UPDATE STARTED: ${repoId} =====`, 'info');
        const response = await fetch(buildURL('api/models/update'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_id: repoId })
        });
        
        const result = await response.json();
        if (response.ok) {
            addLog(`✅ Update started for ${repoId}`, 'success');
        } else {
            addLog(`❌ Update failed: ${result.error}`, 'error');
        }
    } catch (error) {
        addLog(`❌ Error updating model: ${error.message}`, 'error');
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
        addLog(`🗑️ ===== DELETE STARTED: ${currentModelToDelete.name} =====`, 'info');
        const response = await fetch(buildURL('api/models/delete'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentModelToDelete.path })
        });
        
        const result = await response.json();
        if (response.ok) {
            addLog(`✅ Model deleted: ${currentModelToDelete.name}`, 'success');
            addLog(`===== DELETE COMPLETED =====`, 'success');
            hideDeleteModal();
            loadModels(); // Refresh the list
        } else {
            addLog(`❌ Delete failed: ${result.error}`, 'error');
        }
    } catch (error) {
        addLog(`❌ Error deleting model: ${error.message}`, 'error');
    }
}

// Form submission handler
downloadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isDownloading) return;

    const formData = new FormData(downloadForm);
    const data = {
        repo_id: formData.get('repoId').trim(),
        quant_pattern: formData.get('quantPattern').trim()
    };

    if (!data.repo_id) {
        alert('Please enter a repository ID');
        return;
    }

    if (!data.repo_id.includes('/')) {
        alert('Repository ID should be in format: username/model-name');
        return;
    }

    try {
        startDownloadUI();
        const response = await fetch(buildURL('download'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Download failed');

        addLog(`📋 Download request sent for: ${data.repo_id}`, 'info');
        if (data.quant_pattern) addLog(`🔍 Pattern filter: ${data.quant_pattern}`, 'info');

    } catch (error) {
        addLog(`❌ Error: ${error.message}`, 'error');
        resetDownloadUI();
    }
});

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

// Clear log button handler
clearLogBtn.addEventListener('click', () => {
    logs.length = 0;
    logOutput.textContent = 'Ready...';
});

// Socket.IO event handlers
socket.on('connect', () => addLog('🔌 Connected to server', 'info'));
socket.on('disconnect', () => {
    addLog('🔌 Disconnected from server', 'info');
    if (isDownloading) {
        addLog('❌ Connection lost during download', 'error');
        addLog('===== DOWNLOAD FAILED =====', 'error');
        resetDownloadUI();
    }
});

socket.on('download_progress', (data) => {
    const { progress, status, message } = data;
    
    if (status === 'completed') {
        addLog(`✅ ${message}`, 'success');
        addLog('===== DOWNLOAD COMPLETED =====', 'success');
        setTimeout(() => {
            resetDownloadUI();
            loadModels(); // Refresh models list
        }, 2000);
    } else if (status === 'error') {
        addLog(`❌ ${message}`, 'error');
        addLog('===== DOWNLOAD FAILED =====', 'error');
        resetDownloadUI();
    } else if (status === 'downloading') {
        if (progress !== undefined) {
            addProgressLog(`🔥 ${message}`, progress);
        } else {
            addLog(`🔥 ${message}`, 'info');
        }
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hideDeleteModal();
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        loadModels();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (!isDownloading) downloadForm.dispatchEvent(new Event('submit'));
    }
});

// Form input validation
document.getElementById('repoId').addEventListener('input', (e) => {
    const value = e.target.value;
    const isValid = value.includes('/') && value.trim().length > 0;
    e.target.style.borderColor = (!value || isValid) ? '#ddd' : '#dc3545';
});

// Load models on page load
window.addEventListener('load', () => {
    loadModels();
    addLog('🚀 Application ready', 'info');
});