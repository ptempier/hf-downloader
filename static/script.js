// Get base URL from the window global set by the template
const BASE_URL = window.BASE_URL || '';

// Initialize Socket.IO connection (guard if client library didn't load)
let socket;
if (typeof io !== 'undefined') {
    socket = io(BASE_URL);
} else {
    // Fallback noop socket to avoid runtime errors when the client script is missing
    console.warn('Socket.IO client not found (io is undefined). Real-time progress will be disabled.');
    socket = {
        on: () => {},
        emit: () => {},
        disconnect: () => {}
    };
}

// DOM elements
const downloadForm = document.getElementById('downloadForm');
const downloadBtn = document.getElementById('downloadBtn');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const statusMessage = document.getElementById('statusMessage');
const logContainer = document.getElementById('logContainer');
const logOutput = document.getElementById('logOutput');
const clearLogBtn = document.getElementById('clearLogBtn');

// State
let isDownloading = false;
const logs = [];

// Helper function to build URLs
function buildURL(path) {
    return BASE_URL + '/' + path;
}

// Utility functions
function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `[${timestamp}] ${message}`;
    logs.push(logEntry);
    logOutput.textContent = logs.join('\n');
    logOutput.scrollTop = logOutput.scrollHeight;
    logContainer.classList.remove('hidden');
}

function updateProgress(progress, status, message = '') {
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${Math.round(progress)}%`;
    statusMessage.textContent = message;
    statusMessage.className = 'status-message';
    if (status === 'completed') {
        statusMessage.classList.add('success');
        addLog(`✅ ${message}`, 'success');
    } else if (status === 'error') {
        statusMessage.classList.add('error');
        addLog(`❌ ${message}`, 'error');
    } else if (status === 'downloading') {
        statusMessage.classList.add('info');
        addLog(`📥 ${message}`, 'info');
    }
}

function resetUI() {
    isDownloading = false;
    downloadBtn.disabled = false;
    downloadBtn.textContent = 'Start Download';
    progressContainer.classList.add('hidden');
    updateProgress(0, 'idle', '');
}

function startDownloadUI() {
    isDownloading = true;
    downloadBtn.disabled = true;
    downloadBtn.textContent = 'Downloading...';
    progressContainer.classList.remove('hidden');
    addLog('🚀 Starting download...', 'info');
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
        updateProgress(0, 'error', `Error: ${error.message}`);
        resetUI();
    }
});

// Socket.IO event handlers
socket.on('connect', () => addLog('🔌 Connected to download server', 'info'));
socket.on('disconnect', () => {
    addLog('🔌 Disconnected from download server', 'info');
    if (isDownloading) {
        updateProgress(0, 'error', 'Connection lost during download');
        resetUI();
    }
});

socket.on('download_progress', (data) => {
    const { progress, status, message, downloaded, total } = data;
    updateProgress(progress || 0, status, message);
    if (downloaded && total) addLog(`📊 Progress: ${downloaded}/${total} files (${Math.round(progress)}%)`, 'info');
    if (status === 'completed') setTimeout(resetUI, 3000);
    if (status === 'error') resetUI();
});

// Clear log button handler
clearLogBtn.addEventListener('click', () => {
    logs.length = 0;
    logOutput.textContent = '';
    logContainer.classList.add('hidden');
});

// Check initial status on page load
window.addEventListener('load', async () => {
    try {
        const response = await fetch(buildURL('status'));
        const status = await response.json();
        if (status.status === 'downloading') {
            startDownloadUI();
            updateProgress(status.progress, status.status, 'Download in progress...');
        }
    } catch (error) {}
});

// Form input validation and UX improvements
document.getElementById('repoId').addEventListener('input', (e) => {
    const value = e.target.value;
    const isValid = value.includes('/') && value.trim().length > 0;
    e.target.style.borderColor = (!value || isValid) ? '#ddd' : '#dc3545';
});

// Keyboard shortcuts (Ctrl/Cmd+Enter to submit)
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (!isDownloading) downloadForm.dispatchEvent(new Event('submit'));
    }
});