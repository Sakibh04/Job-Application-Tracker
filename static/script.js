// Global variables
let jobs = [];
let sortColumn = 'created_at';
let sortOrder = 'desc';
let editingJobId = null;

// API base URL
const API_BASE = '/api';

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    checkAuth();
    loadJobs();
    loadStats();
});

// Check authentication and load user info
async function checkAuth() {
    try {
        // Try to load jobs to check if user is authenticated
        const response = await fetch(`${API_BASE}/jobs`);
        if (!response.ok) {
            // User not authenticated, redirect to landing
            window.location.href = '/';
            return;
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/';
    }
}

// Logout function
async function logout() {
    try {
        await fetch(`${API_BASE}/logout`, {
            method: 'POST'
        });
        window.location.href = '/';
    } catch (error) {
        console.error('Logout failed:', error);
        // Redirect anyway
        window.location.href = '/';
    }
}

// Setup event listeners
function setupEventListeners() {
    // Form submission
    document.getElementById('jobForm').addEventListener('submit', handleFormSubmit);
    
    // Modal click outside to close
    window.addEventListener('click', function(event) {
        const modal = document.getElementById('jobModal');
        if (event.target === modal) {
            closeModal();
        }
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(event) {
        // Escape key to close modal
        if (event.key === 'Escape') {
            closeModal();
        }
        // Ctrl/Cmd + N for new application
        if ((event.ctrlKey || event.metaKey) && event.key === 'n') {
            event.preventDefault();
            openModal();
        }
        // Ctrl/Cmd + E for export
        if ((event.ctrlKey || event.metaKey) && event.key === 'e') {
            event.preventDefault();
            exportToCSV();
        }
    });
}

// API Functions
async function apiRequest(url, options = {}) {
    const loading = document.getElementById('loading');
    loading.style.display = 'flex';
    
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                // User not authenticated, redirect to landing
                window.location.href = '/';
                return;
            }
            const error = await response.json();
            throw new Error(error.error || 'Request failed');
        }
        
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    } finally {
        loading.style.display = 'none';
    }
}

async function loadJobs() {
    try {
        const params = new URLSearchParams({
            sort_by: sortColumn,
            sort_order: sortOrder
        });
        
        const statusFilter = document.getElementById('statusFilter').value;
        
        if (statusFilter) params.append('status', statusFilter);
        
        jobs = await apiRequest(`${API_BASE}/jobs?${params.toString()}`);
        renderTable();
        loadStats(); // Refresh stats when jobs are loaded
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

async function loadStats() {
    try {
        const stats = await apiRequest(`${API_BASE}/stats`);
        updateStatsDisplay(stats);
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

async function saveJob(jobData) {
    const url = editingJobId 
        ? `${API_BASE}/jobs/${editingJobId}` 
        : `${API_BASE}/jobs`;
    
    const method = editingJobId ? 'PUT' : 'POST';
    
    return await apiRequest(url, {
        method: method,
        body: JSON.stringify(jobData)
    });
}

async function deleteJobById(jobId) {
    await apiRequest(`${API_BASE}/jobs/${jobId}`, {
        method: 'DELETE'
    });
}

// Modal functions
function openModal(jobId = null) {
    const modal = document.getElementById('jobModal');
    const form = document.getElementById('jobForm');
    const title = document.getElementById('modalTitle');
    
    editingJobId = jobId;
    
    if (jobId) {
        title.textContent = 'Edit Application';
        const job = jobs.find(j => j.id === jobId);
        if (job) {
            populateForm(job);
        }
    } else {
        title.textContent = 'Add New Application';
        form.reset();
        document.getElementById('appliedDate').value = new Date().toISOString().split('T')[0];
    }
    
    modal.style.display = 'block';
    setTimeout(() => {
        document.getElementById('company').focus();
    }, 100);
}

function closeModal() {
    document.getElementById('jobModal').style.display = 'none';
    editingJobId = null;
}

function populateForm(job) {
    document.getElementById('company').value = job.company || '';
    document.getElementById('position').value = job.position || '';
    document.getElementById('status').value = job.status || 'applied';
    document.getElementById('appliedDate').value = job.applied_date || '';
    document.getElementById('jobUrl').value = job.job_url || '';
    document.getElementById('salary').value = job.salary || '';
    document.getElementById('notes').value = job.notes || '';
}

// Form submission handler
async function handleFormSubmit(e) {
    e.preventDefault();
    
    const saveButton = document.getElementById('saveButton');
    const btnText = saveButton.querySelector('.btn-text');
    const btnLoading = saveButton.querySelector('.btn-loading');
    
    // Show loading state
    saveButton.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'inline';
    
    try {
        const jobData = {
            company: document.getElementById('company').value.trim(),
            position: document.getElementById('position').value.trim(),
            status: document.getElementById('status').value,
            appliedDate: document.getElementById('appliedDate').value || null,
            jobUrl: document.getElementById('jobUrl').value.trim(),
            salary: document.getElementById('salary').value.trim(),
            notes: document.getElementById('notes').value.trim()
        };
        
        // Validation
        if (!jobData.company || !jobData.position) {
            alert('Company and Position are required fields');
            return;
        }
        
        await saveJob(jobData);
        await loadJobs();
        closeModal();
        
    } catch (error) {
        console.error('Failed to save job:', error);
        alert('Failed to save application. Please try again.');
    } finally {
        // Reset button state
        saveButton.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

// Job management functions
async function deleteJob(jobId) {
    if (!confirm('Are you sure you want to delete this application?')) {
        return;
    }
    
    try {
        await deleteJobById(jobId);
        await loadJobs();
    } catch (error) {
        console.error('Failed to delete job:', error);
        alert('Failed to delete application. Please try again.');
    }
}

// Table rendering and management
function renderTable() {
    const tbody = document.getElementById('jobTableBody');
    const emptyState = document.getElementById('emptyState');
    
    if (jobs.length === 0) {
        tbody.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    
    tbody.innerHTML = jobs.map(job => {
        return `
            <tr>
                <td>
                    <div>
                        <strong>${escapeHtml(job.company)}</strong>
                        ${job.job_url ? `<br><a href="${escapeHtml(job.job_url)}" target="_blank" style="font-size: 12px; color: #007bff;" title="View Job Posting">🔗 View Job</a>` : ''}
                    </div>
                </td>
                <td>${escapeHtml(job.position)}</td>
                <td><span class="status ${job.status}">${capitalizeFirst(job.status)}</span></td>
                <td>${formatDate(job.applied_date)}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-primary" onclick="openModal(${job.id})" title="Edit Application">
                            ✏️ Edit
                        </button>
                        <button class="btn btn-danger" onclick="deleteJob(${job.id})" title="Delete Application">
                            🗑️ Delete
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function updateStatsDisplay(stats) {
    document.getElementById('totalApps').textContent = stats.total || 0;
    document.getElementById('interviewCount').textContent = stats.byStatus?.interview || 0;
}

// Utility functions
function formatDate(dateString) {
    if (!dateString) return '';
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
    } catch {
        return dateString;
    }
}

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Sorting functionality
function sortTable(column) {
    if (sortColumn === column) {
        sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortOrder = 'asc';
    }
    
    // Update header styling
    document.querySelectorAll('th').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
    });
    
    const columnIndex = ['company', 'position', 'status', 'applied_date'].indexOf(column);
    if (columnIndex >= 0) {
        document.querySelectorAll('th')[columnIndex].classList.add(`sort-${sortOrder}`);
    }
    
    loadJobs();
}

// Filter functions
function clearFilters() {
    document.getElementById('statusFilter').value = '';
    loadJobs();
}

// CSV Export
async function exportToCSV() {
    try {
        const response = await fetch(`${API_BASE}/export/csv`);
        if (!response.ok) {
            throw new Error('Export failed');
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `job_applications_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (error) {
        console.error('Export failed:', error);
        alert('Failed to export data. Please try again.');
    }
}

// Auto-refresh stats periodically
setInterval(loadStats, 60000); // Refresh stats every minute