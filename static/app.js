/**
 * Fathom Batch Downloader - Frontend JavaScript
 */

// DOM Elements
const elements = {
    // Config
    apiKeyInput: document.getElementById('api-key'),
    fathomEmailInput: document.getElementById('fathom-email'),
    fathomPasswordInput: document.getElementById('fathom-password'),
    saveConfigBtn: document.getElementById('save-config-btn'),
    loadMeetingsBtn: document.getElementById('load-meetings-btn'),
    configStatus: document.getElementById('config-status'),
    
    // Meetings
    meetingsSection: document.getElementById('meetings-section'),
    meetingsTable: document.getElementById('meetings-table'),
    meetingsTbody: document.getElementById('meetings-tbody'),
    selectAllCheckbox: document.getElementById('select-all-checkbox'),
    selectAllBtn: document.getElementById('select-all-btn'),
    selectNoneBtn: document.getElementById('select-none-btn'),
    selectedCount: document.getElementById('selected-count'),
    noMeetings: document.getElementById('no-meetings'),
    
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
    
    // Selection buttons
    elements.selectAllBtn.addEventListener('click', selectAll);
    elements.selectNoneBtn.addEventListener('click', selectNone);
    elements.selectAllCheckbox.addEventListener('change', toggleSelectAll);
    
    // Download button
    elements.downloadBtn.addEventListener('click', startDownload);
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
        if (config.fathom_email) {
            elements.fathomEmailInput.value = config.fathom_email;
        }
        if (config.fathom_password) {
            elements.fathomPasswordInput.value = config.fathom_password;
        }
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

async function saveConfig() {
    const config = {
        api_key: elements.apiKeyInput.value.trim(),
        fathom_email: elements.fathomEmailInput.value.trim(),
        fathom_password: elements.fathomPasswordInput.value
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
    document.querySelectorAll('.meeting-checkbox').forEach(cb => {
        cb.checked = true;
    });
    meetings.forEach(m => selectedMeetingIds.add(m.id));
    elements.selectAllCheckbox.checked = true;
    updateSelectedCount();
}

function selectNone() {
    document.querySelectorAll('.meeting-checkbox').forEach(cb => {
        cb.checked = false;
    });
    selectedMeetingIds.clear();
    elements.selectAllCheckbox.checked = false;
    updateSelectedCount();
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
    
    // Check if video is selected but no credentials
    if (options.video) {
        const email = elements.fathomEmailInput.value.trim();
        const password = elements.fathomPasswordInput.value;
        
        if (!email || !password || password === '••••••••') {
            showStatus('warning', 'Fathom email and password required for video download. Please enter them above.');
            return;
        }
    }
    
    // Show progress overlay
    elements.progressOverlay.style.display = 'flex';
    elements.progressBar.style.width = '0%';
    elements.progressText.textContent = 'Starting download...';
    elements.progressLog.innerHTML = '';
    
    try {
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                meeting_ids: Array.from(selectedMeetingIds),
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

