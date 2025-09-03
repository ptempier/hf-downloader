const BASE_URL = window.BASE_URL || '';

// Initialize Socket.IO
function initializeSocket() {
    if (typeof io !== 'undefined') {
        const socketPath = BASE_URL ? `${BASE_URL}/socket.io` : '/socket.io';
        return io({ path: socketPath });
    } else {
        console.warn('Socket.IO client not found. Real-time progress disabled.');
        return { on: () => {}, emit: () => {}, disconnect: () => {} };
    }
}

let socket = initializeSocket();

// DOM elements
const downloadForm = document.getElementById('downloadForm');
const downloadBtn = document.getElementById('downloadBtn');
const progressContainer = document.getElementById('progressContainer');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const statusMessage = document.getElementById('statusMessage');
const logContainer = document.getElementById('logContainer');
const logOutput = document.getElementById('logOutput');

// State
let isDownloading = false;
const logs = [];

// Utilities
const buildURL = (path) => BASE_URL ? `${BASE_URL}/${path.replace(/^\/+/, '')}` : `/${path.replace(/^\/+/, '')}`;

function addLog(message) {
    const timestamp = new Date().toLocaleTimeString();
    logs.push(`[${timestamp}] ${message}`);
    logOutput.textContent = logs.join('\n');
    logOutput.scrollTop = logOutput.scrollHeight;
    logContainer.classList.remove('hidden');
}

function updateProgress(progress, status, message = '') {
    progressFill.style.width = `${progress}%`;
    progressText.textContent = `${Math.round(progress)}%`;
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${status}`;
    
    const statusIcons = { completed: '✅', error: '❌', downloading: '🔥' };
    if (statusIcons[status]) addLog(`${statusIcons[status]} ${message}`);
}

function setDownloadState(downloading) {
    isDownloading = downloading;
    downloadBtn.disabled = downloading;
    downloadBtn.textContent = downloading ? 'Downloading...' : 'Start Download';
    progressContainer.classList.toggle('hidden', !downloading);
    if (downloading) addLog('🚀 Starting download...');
}

// Form submission
downloadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isDownloading) return;

    const formData = new FormData(downloadForm);
    const data = {
        repo_id: formData.get('repoId').trim(),
        quant_pattern: formData.get('quantPattern').trim()
    };

    if (!data.repo_id || !data.repo_id.includes('/')) {
        alert('Please enter a valid repository ID (username/model-name)');
        return;
    }

    try {
        setDownloadState(true);
        const response = await fetch(buildURL('download'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        if (!response.ok) throw new Error(result.error);

        addLog(`📋 Download request sent for: ${data.repo_id}`);
        if (data.quant_pattern) addLog(`🔍 Pattern filter: ${data.quant_pattern}`);

    } catch (error) {
        updateProgress(0, 'error', `Error: ${error.message}`);
        setDownloadState(false);
    }
});

// Socket events
socket.on('connect', () => addLog('🔌 Connected to download server'));
socket.on('disconnect', () => {
    addLog('🔌 Disconnected from server');
    if (isDownloading) {
        updateProgress(0, 'error', 'Connection lost during download');
        setDownloadState(false);
    }
});

socket.on('download_progress', (data) => {
    const { progress = 0, status, message } = data;
    updateProgress(progress, status, message);
    
    if (status === 'completed') setTimeout(() => setDownloadState(false), 3000);
    if (status === 'error') setDownloadState(false);
});

// UI handlers
document.getElementById('clearLogBtn').addEventListener('click', () => {
    logs.length = 0;
    logOutput.textContent = '';
    logContainer.classList.add('hidden');
});

document.getElementById('repoId').addEventListener('input', (e) => {
    const isValid = !e.target.value || e.target.value.includes('/');
    e.target.style.borderColor = isValid ? '#ddd' : '#dc3545';
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !isDownloading) {
        downloadForm.dispatchEvent(new Event('submit'));
    }
});

// Check status on load
window.addEventListener('load', async () => {
    try {
        const response = await fetch(buildURL('status'));
        const status = await response.json();
        if (status.status === 'downloading') {
            setDownloadState(true);
            updateProgress(status.progress, status.status, 'Download in progress...');
        }
    } catch (error) {
        // Silently fail
    }
});