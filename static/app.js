/**
 * Fathom Batch Downloader - Frontend JavaScript
 */

// DOM Elements
const elements = {
    // Config
    apiKeyInput: document.getElementById('api-key'),
    downloadDirInput: document.getElementById('download-dir'),
    browseDirBtn: document.getElementById('browse-dir-btn'),
    saveConfigBtn: document.getElementById('save-config-btn'),
    loadMeetingsBtn: document.getElementById('load-meetings-btn'),
    configStatus: document.getElementById('config-status'),
    googleAuthBtn: document.getElementById('google-auth-btn'),
    googleAuthStatus: document.getElementById('google-auth-status'),
    
    // Meetings
    meetingsSection: document.getElementById('meetings-section'),
    meetingsTable: document.getElementById('meetings-table'),
    meetingsTbody: document.getElementById('meetings-tbody'),
    selectAllCheckbox: document.getElementById('select-all-checkbox'),
    selectAllBtn: document.getElementById('select-all-btn'),
    selectNoneBtn: document.getElementById('select-none-btn'),
    selectedCount: document.getElementById('selected-count'),
    noMeetings: document.getElementById('no-meetings'),
    
    // Search
    searchInput: document.getElementById('search-input'),
    clearSearchBtn: document.getElementById('clear-search-btn'),
    filterStats: document.getElementById('filter-stats'),
    
    // Download
    downloadSection: document.getElementById('download-section'),
    downloadBtn: document.getElementById('download-btn'),
    optVideo: document.getElementById('opt-video'),
    optTranscript: document.getElementById('opt-transcript'),
    optSummary: document.getElementById('opt-summary'),
    optActionItems: document.getElementById('opt-action-items'),
    
    // Progress
    progressOverlay: document.getElementById('progress-overlay'),
    progressBar: document.getElementById('progress-bar'),
    progressText: document.getElementById('progress-text'),
    progressLog: document.getElementById('progress-log')
};

// State
let meetings = [];
let selectedMeetingIds = new Set();

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    setupEventListeners();
});

function setupEventListeners() {
    // Config buttons
    elements.saveConfigBtn.addEventListener('click', saveConfig);
    elements.loadMeetingsBtn.addEventListener('click', loadMeetings);
    elements.googleAuthBtn.addEventListener('click', authenticateWithGoogle);
    elements.browseDirBtn.addEventListener('click', resetDownloadDir);
    
    // Selection buttons
    elements.selectAllBtn.addEventListener('click', selectAll);
    elements.selectNoneBtn.addEventListener('click', selectNone);
    elements.selectAllCheckbox.addEventListener('change', toggleSelectAll);
    
    // Search
    elements.searchInput.addEventListener('input', debounce(applySearchFilter, 300));
    elements.clearSearchBtn.addEventListener('click', clearSearch);
    
    // Download button
    elements.downloadBtn.addEventListener('click', startDownload);
}

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Boolean Search Parser
function parseBooleanSearch(query) {
    /**
     * Parse a boolean search query
     * Supports: AND, OR, NOT operators
     * Examples:
     *   "standup AND team" - must contain both
     *   "review OR retro" - must contain either
     *   "meeting NOT cancelled" - must contain meeting, must NOT contain cancelled
     *   "team standup" - implicit AND (must contain both)
     */
    query = query.trim();
    if (!query) return null;
    
    // Tokenize: split by operators while preserving them
    const tokens = query.split(/\s+(AND|OR|NOT)\s+/i);
    
    if (tokens.length === 1) {
        // Simple search - implicit AND for multiple words
        const words = tokens[0].toLowerCase().split(/\s+/).filter(w => w.length > 0);
        return { type: 'AND', terms: words.map(w => ({ type: 'TERM', value: w })) };
    }
    
    // Parse tokens with operators
    const ast = { type: 'AND', terms: [] };
    let currentOp = 'AND';
    let notNext = false;
    
    for (let i = 0; i < tokens.length; i++) {
        const token = tokens[i].trim();
        if (!token) continue;
        
        const upperToken = token.toUpperCase();
        
        if (upperToken === 'AND') {
            currentOp = 'AND';
        } else if (upperToken === 'OR') {
            currentOp = 'OR';
        } else if (upperToken === 'NOT') {
            notNext = true;
        } else {
            // It's a term - may contain multiple words
            const words = token.toLowerCase().split(/\s+/).filter(w => w.length > 0);
            for (const word of words) {
                const term = { type: notNext ? 'NOT' : 'TERM', value: word, op: currentOp };
                ast.terms.push(term);
                notNext = false;
            }
        }
    }
    
    return ast;
}

function matchesBooleanSearch(text, ast) {
    if (!ast || !ast.terms || ast.terms.length === 0) return true;
    
    text = text.toLowerCase();
    
    let result = null;
    let currentOp = 'AND';
    
    for (const term of ast.terms) {
        const matches = text.includes(term.value);
        let termResult;
        
        if (term.type === 'NOT') {
            termResult = !matches;
        } else {
            termResult = matches;
        }
        
        // Apply operator
        const op = term.op || currentOp;
        if (result === null) {
            result = termResult;
        } else if (op === 'AND') {
            result = result && termResult;
        } else if (op === 'OR') {
            result = result || termResult;
        }
        
        currentOp = term.op || 'AND';
    }
    
    return result !== null ? result : true;
}

function applySearchFilter() {
    const query = elements.searchInput.value;
    const ast = parseBooleanSearch(query);
    
    const rows = elements.meetingsTbody.querySelectorAll('tr');
    let visibleCount = 0;
    let totalCount = rows.length;
    
    rows.forEach(row => {
        const titleCell = row.querySelector('.meeting-title');
        if (!titleCell) return;
        
        const title = titleCell.textContent;
        const matches = matchesBooleanSearch(title, ast);
        
        if (matches) {
            row.classList.remove('filtered-out');
            visibleCount++;
        } else {
            row.classList.add('filtered-out');
        }
    });
    
    // Update filter stats
    if (query.trim()) {
        elements.filterStats.textContent = `Showing ${visibleCount} of ${totalCount} meetings`;
        elements.filterStats.classList.add('has-filter');
    } else {
        elements.filterStats.textContent = '';
        elements.filterStats.classList.remove('has-filter');
    }
    
    updateSelectedCount();
}

function clearSearch() {
    elements.searchInput.value = '';
    applySearchFilter();
    elements.searchInput.focus();
}

// Config Functions
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        
        if (config.api_key) {
            elements.apiKeyInput.value = config.api_key;
            elements.loadMeetingsBtn.disabled = false;
        }
        
        if (config.download_dir) {
            elements.downloadDirInput.value = config.download_dir;
        }
        
        // Update Google auth status
        updateGoogleAuthStatus(config.google_authenticated);
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

function resetDownloadDir() {
    elements.downloadDirInput.value = '';
    elements.downloadDirInput.placeholder = './downloads (default)';
}

function updateGoogleAuthStatus(isAuthenticated) {
    if (isAuthenticated) {
        elements.googleAuthStatus.textContent = '✓ Signed in - Video downloads enabled';
        elements.googleAuthStatus.className = 'auth-status authenticated';
        elements.googleAuthBtn.textContent = '✓ Signed in with Google';
        elements.googleAuthBtn.disabled = true;
    } else {
        elements.googleAuthStatus.textContent = 'Sign in to enable video downloads';
        elements.googleAuthStatus.className = 'auth-status';
        elements.googleAuthBtn.disabled = false;
    }
}

async function authenticateWithGoogle() {
    elements.googleAuthBtn.disabled = true;
    elements.googleAuthBtn.innerHTML = '<span class="spinner"></span> Opening browser...';
    elements.googleAuthStatus.textContent = 'A browser window will open. Please sign in with Google.';
    elements.googleAuthStatus.className = 'auth-status pending';
    
    try {
        const response = await fetch('/api/google-auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            updateGoogleAuthStatus(true);
            // Automatically load meetings if API key is configured
            if (elements.apiKeyInput.value.trim()) {
                loadMeetings();
            }
        } else {
            elements.googleAuthStatus.textContent = result.error || 'Authentication failed';
            elements.googleAuthStatus.className = 'auth-status error';
            elements.googleAuthBtn.disabled = false;
            elements.googleAuthBtn.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4"/>
                    <path d="M9.003 18c2.43 0 4.467-.806 5.956-2.18l-2.909-2.26c-.806.54-1.836.86-3.047.86-2.344 0-4.328-1.584-5.036-3.711H.96v2.332C2.44 15.983 5.485 18 9.003 18z" fill="#34A853"/>
                    <path d="M3.964 10.712c-.18-.54-.282-1.117-.282-1.71 0-.593.102-1.17.282-1.71V4.96H.957C.347 6.175 0 7.55 0 9.002c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
                    <path d="M9.003 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.464.891 11.428 0 9.002 0 5.485 0 2.44 2.017.96 4.958L3.967 7.29c.708-2.127 2.692-3.71 5.036-3.71z" fill="#EA4335"/>
                </svg>
                Try Again
            `;
        }
    } catch (error) {
        elements.googleAuthStatus.textContent = 'Failed to start authentication: ' + error.message;
        elements.googleAuthStatus.className = 'auth-status error';
        elements.googleAuthBtn.disabled = false;
    }
}

async function saveConfig() {
    const config = {
        api_key: elements.apiKeyInput.value.trim(),
        download_dir: elements.downloadDirInput.value.trim()
    };
    
    if (!config.api_key) {
        showStatus('error', 'Please enter an API key');
        return;
    }
    
    elements.saveConfigBtn.disabled = true;
    elements.saveConfigBtn.textContent = 'Saving...';
    
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showStatus('success', 'Configuration saved successfully!');
            elements.loadMeetingsBtn.disabled = false;
        } else {
            showStatus('error', result.error || 'Failed to save configuration');
        }
    } catch (error) {
        showStatus('error', 'Failed to save configuration: ' + error.message);
    } finally {
        elements.saveConfigBtn.disabled = false;
        elements.saveConfigBtn.textContent = 'Save Configuration';
    }
}

function showStatus(type, message) {
    elements.configStatus.className = `status-message ${type}`;
    elements.configStatus.textContent = message;
    
    if (type === 'success') {
        setTimeout(() => {
            elements.configStatus.className = 'status-message';
        }, 3000);
    }
}

// Meetings Functions
async function loadMeetings() {
    elements.loadMeetingsBtn.disabled = true;
    elements.loadMeetingsBtn.textContent = 'Loading...';
    
    try {
        const response = await fetch('/api/meetings');
        const data = await response.json();
        
        if (data.error) {
            showStatus('error', data.error);
            return;
        }
        
        meetings = data.meetings || [];
        renderMeetings();
        
        elements.meetingsSection.style.display = 'block';
        elements.downloadSection.style.display = 'block';
        
        if (meetings.length === 0) {
            elements.noMeetings.style.display = 'block';
            elements.meetingsTable.style.display = 'none';
        } else {
            elements.noMeetings.style.display = 'none';
            elements.meetingsTable.style.display = 'table';
        }
        
    } catch (error) {
        showStatus('error', 'Failed to load meetings: ' + error.message);
    } finally {
        elements.loadMeetingsBtn.disabled = false;
        elements.loadMeetingsBtn.textContent = 'Load Meetings';
    }
}

function renderMeetings() {
    elements.meetingsTbody.innerHTML = '';
    
    meetings.forEach(meeting => {
        const row = document.createElement('tr');
        
        const formattedDate = formatDate(meeting.date);
        const title = meeting.title || meeting.meeting_title || 'Untitled Meeting';
        const recordedBy = meeting.recorded_by || 'Unknown';
        
        row.innerHTML = `
            <td class="checkbox-col">
                <input type="checkbox" data-id="${meeting.id}" class="meeting-checkbox">
            </td>
            <td class="meeting-title">${escapeHtml(title)}</td>
            <td class="meeting-date">${formattedDate}</td>
            <td>${escapeHtml(recordedBy)}</td>
        `;
        
        const checkbox = row.querySelector('.meeting-checkbox');
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                selectedMeetingIds.add(meeting.id);
            } else {
                selectedMeetingIds.delete(meeting.id);
            }
            updateSelectedCount();
        });
        
        elements.meetingsTbody.appendChild(row);
    });
    
    updateSelectedCount();
}

function formatDate(dateStr) {
    if (!dateStr) return 'Unknown date';
    
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch {
        return dateStr;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function selectAll() {
    // Only select visible (not filtered out) meetings
    document.querySelectorAll('.meeting-checkbox').forEach(cb => {
        const row = cb.closest('tr');
        if (!row.classList.contains('filtered-out')) {
            cb.checked = true;
            const id = cb.dataset.id;
            selectedMeetingIds.add(id);
        }
    });
    updateSelectAllCheckboxState();
    updateSelectedCount();
}

function selectNone() {
    // Only deselect visible (not filtered out) meetings
    document.querySelectorAll('.meeting-checkbox').forEach(cb => {
        const row = cb.closest('tr');
        if (!row.classList.contains('filtered-out')) {
            cb.checked = false;
            const id = cb.dataset.id;
            selectedMeetingIds.delete(id);
        }
    });
    updateSelectAllCheckboxState();
    updateSelectedCount();
}

function updateSelectAllCheckboxState() {
    const visibleCheckboxes = Array.from(document.querySelectorAll('.meeting-checkbox')).filter(cb => {
        const row = cb.closest('tr');
        return !row.classList.contains('filtered-out');
    });
    const allChecked = visibleCheckboxes.length > 0 && visibleCheckboxes.every(cb => cb.checked);
    const someChecked = visibleCheckboxes.some(cb => cb.checked);
    
    elements.selectAllCheckbox.checked = allChecked;
    elements.selectAllCheckbox.indeterminate = someChecked && !allChecked;
}

function toggleSelectAll() {
    if (elements.selectAllCheckbox.checked) {
        selectAll();
    } else {
        selectNone();
    }
}

function updateSelectedCount() {
    const count = selectedMeetingIds.size;
    elements.selectedCount.textContent = `${count} selected`;
    elements.downloadBtn.disabled = count === 0;
    
    // Update header checkbox state
    if (count === 0) {
        elements.selectAllCheckbox.checked = false;
        elements.selectAllCheckbox.indeterminate = false;
    } else if (count === meetings.length) {
        elements.selectAllCheckbox.checked = true;
        elements.selectAllCheckbox.indeterminate = false;
    } else {
        elements.selectAllCheckbox.checked = false;
        elements.selectAllCheckbox.indeterminate = true;
    }
}

// Download Functions
async function startDownload() {
    if (selectedMeetingIds.size === 0) {
        return;
    }
    
    const options = {
        video: elements.optVideo.checked,
        transcript: elements.optTranscript.checked,
        summary: elements.optSummary.checked,
        action_items: elements.optActionItems.checked
    };
    
    // Check if video is selected but not authenticated with Google
    if (options.video && !elements.googleAuthBtn.disabled) {
        showStatus('warning', 'Please sign in with Google first to enable video downloads.');
        return;
    }
    
    // Show progress overlay
    elements.progressOverlay.style.display = 'flex';
    elements.progressBar.style.width = '0%';
    elements.progressText.textContent = 'Starting download...';
    elements.progressLog.innerHTML = '';
    
    try {
        // Get meeting info for selected meetings
        const selectedMeetings = meetings.filter(m => selectedMeetingIds.has(m.id));
        
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                meeting_ids: Array.from(selectedMeetingIds),
                meetings_info: selectedMeetings,
                options: options
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            logProgress('error', data.error);
            return;
        }
        
        // Connect to SSE for progress updates
        const eventSource = new EventSource(`/api/progress/${data.session_id}`);
        
        eventSource.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            
            switch (msg.type) {
                case 'progress':
                    const percent = (msg.current / msg.total) * 100;
                    elements.progressBar.style.width = `${percent}%`;
                    elements.progressText.textContent = msg.message;
                    break;
                    
                case 'status':
                    logProgress('info', msg.message);
                    break;
                    
                case 'warning':
                    logProgress('warning', msg.message);
                    break;
                    
                case 'error':
                    logProgress('error', msg.message);
                    eventSource.close();
                    break;
                    
                case 'complete':
                    elements.progressBar.style.width = '100%';
                    elements.progressText.textContent = msg.message;
                    logProgress('success', `Downloads saved to: ${msg.folder}`);
                    eventSource.close();
                    
                    // Auto-close after 3 seconds
                    setTimeout(() => {
                        elements.progressOverlay.style.display = 'none';
                    }, 3000);
                    break;
            }
        };
        
        eventSource.onerror = () => {
            logProgress('error', 'Connection lost');
            eventSource.close();
        };
        
    } catch (error) {
        logProgress('error', 'Failed to start download: ' + error.message);
    }
}

function logProgress(type, message) {
    const p = document.createElement('p');
    p.className = type;
    p.textContent = message;
    elements.progressLog.appendChild(p);
    elements.progressLog.scrollTop = elements.progressLog.scrollHeight;
}

