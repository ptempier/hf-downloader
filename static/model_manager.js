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
                    <div class="model-path">${model.path}</div>
                </div>
                <div style="display:flex; align-items:center; gap:0.6rem;">
                    <div class="model-count">${modelFileCount} files</div>
                    <div class="model-size-right">${model.total_size}</div>
                    <div class="model-actions">
                        <button class="btn btn-icon btn-primary" onclick="triggerUpdate('${model.name}')">
                            🔄
                        </button>
                        <button class="btn btn-icon btn-danger" onclick="showDeleteModal('${model.name}', '${model.path}')">
                            🗑️
                        </button>
                    </div>
                </div>
            </div>
            <div class="model-files">
                ${groupsHTML}
                ${individualFilesHTML}
            </div>
        </div>
    `;
}

function renderModels(models) {
    if (models.length === 0) {
        modelsContainer.innerHTML = `
            <div class="no-models">
                <h3>📁 No Models Found</h3>
                <p>No models found in /models directory.</p>
                <p><a href="http://localhost:5000" target="_blank">Download some models first</a></p>
            </div>
        `;
        return;
    }

    const modelsHTML = models.map(createModelHTML).join('');
    modelsContainer.innerHTML = modelsHTML;
}

function filterModels(searchTerm) {
    const filtered = allModels.filter(model => 
        model.name.toLowerCase().includes(searchTerm.toLowerCase())
    );
    renderModels(filtered);
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

// Modal functions
function showModal(modal) {
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function hideModal(modal) {
    modal.classList.add('hidden');
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

// Update now: directly update with same model and no quantization filter by default
function triggerUpdate(modelName) {
    // Immediately start update with empty quant pattern
    updateModel(modelName, '');
}
function showDeleteModal(modelName, modelPath) {
    deleteModelName.textContent = modelName;
    currentModelToDelete = { name: modelName, path: modelPath };
    showModal(deleteModal);
}

// API functions
async function loadModels() {
    try {
        showLoading();
        const response = await fetch('/api/models');
        
        if (!response.ok) {
            throw new Error('Failed to load models');
        }
        
        const models = await response.json();
        allModels = models;
        renderModels(models);
        
    } catch (error) {
        console.error('Error loading models:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

async function updateModel(repoId, quantPattern = '') {
    try {
        const response = await fetch('/api/models/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                repo_id: repoId,
                quant_pattern: quantPattern
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Update failed');
        }
        
    alert(`Update started for ${repoId}. This may take a while.`);
        
        // Refresh models after a short delay
        setTimeout(() => {
            loadModels();
        }, 2000);
        
    } catch (error) {
        console.error('Error updating model:', error);
        alert(`Error updating model: ${error.message}`);
    }
}

async function deleteModel(modelPath) {
    try {
        const response = await fetch('/api/models/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                path: modelPath
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.error || 'Delete failed');
        }
        
        alert(result.message);
        hideModal(deleteModal);
        loadModels(); // Refresh the models list
        
    } catch (error) {
        console.error('Error deleting model:', error);
        alert(`Error deleting model: ${error.message}`);
    }
}

// Event listeners
refreshBtn.addEventListener('click', loadModels);

searchInput.addEventListener('input', (e) => {
    filterModels(e.target.value);
});

// Modal event listeners
document.querySelectorAll('.close').forEach(closeBtn => {
    closeBtn.addEventListener('click', (e) => {
        const modal = e.target.closest('.modal');
        hideModal(modal);
    });
});

// No update modal; Update button calls triggerUpdate(modelName)

// Delete confirmation buttons
confirmDeleteBtn.addEventListener('click', () => {
    if (currentModelToDelete) {
        deleteModel(currentModelToDelete.path);
    }
});

cancelDeleteBtn.addEventListener('click', () => {
    hideModal(deleteModal);
});

// Close modal when clicking outside
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            hideModal(modal);
        }
    });
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Escape to close modals
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal:not(.hidden)').forEach(modal => {
            hideModal(modal);
        });
    }
    
    // F5 or Ctrl+R to refresh
    if (e.key === 'F5' || (e.ctrlKey && e.key === 'r')) {
        e.preventDefault();
        loadModels();
    }
    
    // Ctrl+F to focus search
    if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        searchInput.focus();
    }
});

// Global function for onclick handlers
window.toggleFileGroup = toggleFileGroup;
window.triggerUpdate = triggerUpdate;
window.showDeleteModal = showDeleteModal;

// Initialize modals as hidden on page load
window.addEventListener('DOMContentLoaded', () => {
    // Ensure all modals start hidden
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.add('hidden');
        modal.style.display = 'none';
    });
});

// Load models on page load
window.addEventListener('load', loadModels);
