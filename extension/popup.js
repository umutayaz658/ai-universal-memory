const API_URL = "https://web-production-7e6a8.up.railway.app/api";

// DOM Elements
const screens = {
    login: document.getElementById('login-screen'),
    register: document.getElementById('register-screen'),
    main: document.getElementById('main-screen'),
    howItWorks: document.getElementById('how-it-works-screen')
};

const forms = {
    login: document.getElementById('login-form'),
    register: document.getElementById('register-form'),
    createProject: document.getElementById('create-project-form')
};

const elements = {
    status: document.getElementById('status-msg'),
    goToRegister: document.getElementById('go-to-register'),
    goToLogin: document.getElementById('go-to-login'),
    projectSelect: document.getElementById('project-select'),
    currentUser: document.getElementById('current-user'),
    logoutBtn: document.getElementById('logout-btn'),
    newProjectName: document.getElementById('new-project-name'),
    memoryList: document.getElementById('memory-list'),
    memorySearch: document.getElementById('memory-search'),
    exportReportBtn: document.getElementById('export-report-btn'),
    btnHowItWorks: document.getElementById('btn-how-it-works'),
    btnBackFromHelp: document.getElementById('btn-back-from-help')
};

function clearMemoryUI() {
    elements.memoryList.innerHTML = '';
    elements.memorySearch.value = '';
}

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', async () => {
    const { auth_token, user_username } = await chrome.storage.local.get(['auth_token', 'user_username']);

    if (auth_token) {
        showScreen('main');
        elements.currentUser.textContent = user_username || 'User';
        await loadProjects(auth_token);

        // Load memories for stored project if any
        const { selected_project_id } = await chrome.storage.local.get(['selected_project_id']);
        if (selected_project_id) {
            fetchMemories(auth_token, selected_project_id);
        }
    } else {
        showScreen('login');
    }
});

// --- EVENT LISTENERS ---

// Navigation
elements.goToRegister.addEventListener('click', () => {
    clearStatus();
    showScreen('register');
});

// Help Navigation
// 1. Main Screen Link
if (elements.btnHowItWorks) {
    elements.btnHowItWorks.addEventListener('click', (e) => {
        e.preventDefault();
        showScreen('howItWorks');
    });
}
// 2. Auth Screen Links (Class based)
document.querySelectorAll('.btn-how-it-works-link').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        showScreen('howItWorks');
    });
});

// 3. Back Button
if (elements.btnBackFromHelp) {
    elements.btnBackFromHelp.addEventListener('click', async () => {
        const { auth_token } = await chrome.storage.local.get(['auth_token']);
        if (auth_token) {
            showScreen('main');
        } else {
            showScreen('login');
        }
    });
}

elements.goToLogin.addEventListener('click', () => {
    clearStatus();
    showScreen('login');
});

// LOGIN Handler
forms.login.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    showStatus('Logging in...', 'info');

    try {
        const response = await fetch(`${API_URL}/login/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok) {
            // Save Token & User Info
            await chrome.storage.local.set({
                auth_token: data.token,
                user_username: username // Data usually doesn't return username, so we use input
            });

            showStatus('Login successful!', 'success');
            elements.currentUser.textContent = username;

            setTimeout(() => {
                clearStatus();
                showScreen('main');
                loadProjects(data.token);
            }, 800);
        } else {
            showStatus(data.error || 'Login failed. Check credentials.', 'error');
        }
    } catch (err) {
        showStatus('Network error. Is the server running?', 'error');
        console.error(err);
    }
});

// REGISTER Handler
forms.register.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('reg-username').value;
    const password = document.getElementById('reg-password').value;
    const confirmPassword = document.getElementById('reg-confirm-password').value;
    const email = document.getElementById('reg-email').value;

    if (password !== confirmPassword) {
        showStatus('Passwords do not match!', 'error');
        return;
    }

    if (!email) {
        showStatus('Email is required.', 'error');
        return;
    }

    showStatus('Creating account...', 'info');

    try {
        const response = await fetch(`${API_URL}/register/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email })
        });

        const data = await response.json();

        if (response.ok) {
            // Auto login after register
            await chrome.storage.local.set({
                auth_token: data.token,
                user_username: username
            });

            showStatus('Account created! Logging in...', 'success');
            elements.currentUser.textContent = username;

            setTimeout(() => {
                clearStatus();
                showScreen('main');
                loadProjects(data.token);
            }, 1000);
        } else {
            // Parse error dict if complex
            const msg = typeof data === 'object' ? JSON.stringify(data) : data;
            showStatus('Registration failed: ' + msg, 'error');
        }
    } catch (err) {
        showStatus('Network error during registration.', 'error');
    }
});

// CREATE PROJECT Handler
forms.createProject.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = elements.newProjectName.value.trim();
    if (!name) return;

    const { auth_token } = await chrome.storage.local.get(['auth_token']);
    if (!auth_token) return logout();

    try {
        const response = await fetch(`${API_URL}/projects/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${auth_token}`
            },
            body: JSON.stringify({ name })
        });

        if (response.ok) {
            elements.newProjectName.value = ''; // Clear input
            showStatus('Project created!', 'success');
            loadProjects(auth_token); // Refresh list
        } else {
            showStatus('Failed to create project.', 'error');
        }
    } catch (err) {
        showStatus('Error creating project.', 'error');
    }
});

// PROJECT SELECTION Handler
elements.projectSelect.addEventListener('change', async (e) => {
    const projectId = e.target.value;

    if (!projectId) {
        // User selected "No Active Project"
        await chrome.storage.local.remove(['selected_project_id', 'selected_project_name']);
        clearMemoryUI();
        showStatus('Memory Disabled 🔕', 'info');
    } else {
        // User selected a valid project
        const projectName = e.target.options[e.target.selectedIndex].text;

        await chrome.storage.local.set({
            selected_project_id: projectId,
            selected_project_name: projectName
        });
        showStatus(`✅ ${projectName} Active`, 'success');

        // Fetch memories for new project
        const { auth_token } = await chrome.storage.local.get(['auth_token']);
        fetchMemories(auth_token, projectId);
    }
});

// MEMORY SEARCH Handler (Debounce)
let searchTimeout;
elements.memorySearch.addEventListener('input', async (e) => {
    const query = e.target.value;
    clearTimeout(searchTimeout);

    searchTimeout = setTimeout(async () => {
        const { auth_token, selected_project_id } = await chrome.storage.local.get(['auth_token', 'selected_project_id']);
        if (auth_token && selected_project_id) {
            fetchMemories(auth_token, selected_project_id, query);
        }
    }, 500); // 500ms debounce
});

async function fetchMemories(token, projectId, query = "") {
    if (!projectId) {
        clearMemoryUI();
        return;
    }
    elements.memoryList.innerHTML = '<div style="text-align:center; padding:10px; color:#94a3b8;">Searching...</div>';

    try {
        const response = await fetch(`${API_URL}/memories/retrieve/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${token}`
            },
            body: JSON.stringify({ project_id: projectId, query: query || "latest" })
            // "latest" is a dummy query to fetch recent if empty. 
            // If backend strictly requires query, we might need a blank search support or distinct endpoint.
            // Using "latest" or just a common stopword might trigger 'latest' fetch if backend supports it.
            // Actually, RetrieveContextView expects a query. Let's send "." if empty to match everything or triggers latent search.
            // Actually, RetrieveContextView logic relies on vector search mostly.
            // Let's use a generic query if empty to get *something*. "summary" or "project" usually works.
        });

        const data = await response.json();
        if (response.ok) {
            renderMemories(data.results || []);
        } else {
            elements.memoryList.innerHTML = '<div style="text-align:center; color:var(--error-color);">Failed to load memories</div>';
        }
    } catch (err) {
        console.error(err);
        elements.memoryList.innerHTML = '<div style="text-align:center; color:var(--error-color);">Network Error</div>';
    }
}

function renderMemories(memories) {
    elements.memoryList.innerHTML = '';

    if (memories.length === 0) {
        elements.memoryList.innerHTML = '<div style="text-align:center; padding:10px; color:#94a3b8;">No memories found.</div>';
        return;
    }

    // Task 1.4: Client-side sorting (Newest First) just in case
    memories.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    memories.forEach(mem => {
        const card = document.createElement('div');
        card.className = 'memory-card';

        // Clean text (remove timestamp if present in raw_text)
        const textDisplay = mem.raw_text.length > 50 ? mem.raw_text.substring(0, 50) + "..." : mem.raw_text;

        card.innerHTML = `
            <div class="memory-text" title="${mem.raw_text}">${textDisplay}</div>
            <button class="delete-mem-btn" data-id="${mem.id}">🗑️</button>
        `;

        // Delete Handler
        card.querySelector('.delete-mem-btn').addEventListener('click', async (e) => {
            const btn = e.currentTarget; // use currentTarget to get button, not icon
            const memId = btn.getAttribute('data-id');
            const { auth_token, selected_project_id } = await chrome.storage.local.get(['auth_token', 'selected_project_id']);

            if (confirm("Delete this memory?")) {
                try {
                    const res = await fetch(`${API_URL}/memories/delete/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Token ${auth_token}`
                        },
                        body: JSON.stringify({ project_id: selected_project_id, memory_id: memId })
                    });

                    if (res.ok) {
                        card.remove(); // Optimistic remove
                    } else {
                        alert("Failed to delete memory");
                    }
                } catch (err) {
                    console.error(err);
                    alert("Error deleting memory");
                }
            }
        });

        elements.memoryList.appendChild(card);
    });
}
// EXPORT REPORT Handler
// EXPORT REPORT HANDLERS
const exportMenuBtn = document.getElementById('export-menu-btn');
const exportOptions = document.getElementById('export-options');
const exportMdBtn = document.getElementById('export-md');
const exportPdfBtn = document.getElementById('export-pdf');

if (exportMenuBtn) {
    // Toggle Menu
    exportMenuBtn.addEventListener('click', () => {
        exportOptions.classList.toggle('hidden');
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!exportMenuBtn.contains(e.target) && !exportOptions.contains(e.target)) {
            exportOptions.classList.add('hidden');
        }
    });

    // Handle Options
    exportMdBtn.addEventListener('click', () => exportProject('md'));
    exportPdfBtn.addEventListener('click', () => exportProject('pdf'));
}

async function exportProject(format) {
    const { auth_token, selected_project_id } = await chrome.storage.local.get(['auth_token', 'selected_project_id']);

    if (!selected_project_id) {
        showStatus('Please select a project first.', 'error');
        return;
    }

    // UI Feedback
    exportOptions.classList.add('hidden'); // Close menu
    const originalText = exportMenuBtn.textContent;
    exportMenuBtn.textContent = '⏳ Generating...';
    exportMenuBtn.disabled = true;
    showStatus(`Generating ${format.toUpperCase()} report...`, 'info');

    try {
        const response = await fetch(`${API_URL}/projects/export/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${auth_token}`
            },
            body: JSON.stringify({ project_id: selected_project_id, format: format })
        });

        if (response.ok) {
            // Handle File Download
            let blob;
            let extension;
            let filename;

            if (format === 'pdf') {
                blob = await response.blob();
                extension = 'pdf';
                // Try to get filename from header
                const disposition = response.headers.get('Content-Disposition');
                if (disposition && disposition.indexOf('filename=') !== -1) {
                    const matches = /filename="([^"]*)"/.exec(disposition);
                    if (matches != null && matches[1]) {
                        filename = matches[1];
                    }
                }
            } else {
                const data = await response.json();
                if (!data.report) throw new Error(data.error || 'No report data');
                blob = new Blob([data.report], { type: 'text/markdown' });
                extension = 'md';
                filename = `${(data.project_name || 'Project').replace(/[^a-z0-9]/gi, '_')}_Report.md`;
            }

            // Fallback filename
            if (!filename) filename = `Project_Report.${extension}`;

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();

            // Cleanup
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showStatus('Report downloaded!', 'success');
        } else {
            const errData = await response.json().catch(() => ({}));
            showStatus(errData.error || 'Failed to generate report.', 'error');
        }
    } catch (err) {
        console.error(err);
        showStatus('Error generating report.', 'error');
    } finally {
        exportMenuBtn.textContent = originalText;
        exportMenuBtn.disabled = false;
    }
}

// LOGOUT Handler
elements.logoutBtn.addEventListener('click', logout);

// --- HELPERS ---

async function logout() {
    await chrome.storage.local.remove(['selected_project_id', 'selected_project_name']);
    await chrome.storage.local.clear();
    clearMemoryUI();
    showScreen('login');
    showStatus('Logged out.', 'info');
}

function showScreen(screenName) {
    // Hide all
    Object.values(screens).forEach(el => el.classList.add('hidden'));
    // Show target
    screens[screenName].classList.remove('hidden');
}

function showStatus(msg, type) {
    elements.status.textContent = msg;
    elements.status.className = ''; // Reset
    elements.status.classList.add(type === 'error' ? 'status-error' : 'status-success');
    elements.status.classList.remove('hidden');
}

function clearStatus() {
    elements.status.classList.add('hidden');
    elements.status.textContent = '';
}

async function loadProjects(token) {
    elements.projectSelect.innerHTML = '<option>Loading...</option>';

    try {
        const response = await fetch(`${API_URL}/projects/`, {
            headers: {
                'Authorization': `Token ${token}`
            }
        });

        if (response.status === 401 || response.status === 403) {
            showStatus('Login expired.', 'error');
            setTimeout(logout, 1500);
            return;
        }

        const projects = await response.json();

        // 1. Add Default "None" Option
        elements.projectSelect.innerHTML = '<option value="">⛔ No Active Project (Memory Disabled)</option>';

        // Get currently selected project from storage to persist selection
        const { selected_project_id } = await chrome.storage.local.get(['selected_project_id']);

        if (projects.length === 0) {
            // No projects available, but we still keep the "None" option.
            // Maybe add a disabled option to guide them?
            const opt = document.createElement('option');
            opt.disabled = true;
            opt.text = "👇 Create a project below to start";
            elements.projectSelect.appendChild(opt);
        }

        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            if (p.id === selected_project_id) {
                opt.selected = true;
            }
            elements.projectSelect.appendChild(opt);
        });

        // Ensure "None" is selected if nothing in storage, or if stored ID is no longer valid
        if (!selected_project_id) {
            elements.projectSelect.value = "";
        } else {
            // Check if stored ID exists in list
            const exists = projects.find(p => p.id === selected_project_id);
            if (!exists) {
                elements.projectSelect.value = "";
                chrome.storage.local.remove(['selected_project_id', 'selected_project_name']);
            }
        }

    } catch (err) {
        console.error(err);
        elements.projectSelect.innerHTML = '<option disabled>Error loading projects</option>';
        showStatus('Failed to load projects.', 'error');
    }
}