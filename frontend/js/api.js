const API = 'http://localhost:8000';

// API Fetch helper
async function api(path, opts = {}) {
    const r = await fetch(API + path, {
        headers: {
            'Content-Type': 'application/json'
        },
        ...opts
    });
    if (!r.ok) {
        const e = await r.json().catch(() => ({
            detail: 'Error'
        }));
        throw new Error(e.detail || 'Error');
    }
    return r.json();
}

// Data loaders
async function loadProjects() {
    try {
        const projects = await api('/projects');
        const {
            selectedProject
        } = gs();
        let patch = {
            projects
        };
        if (selectedProject) {
            const updated = projects.find(p => p.id === selectedProject.id);
            if (updated) patch.selectedProject = updated;
        }
        setState(patch);
    } catch (e) {
        console.error('Failed to load projects:', e);
    }
}

async function loadFiles() {
    const {
        selectedProject,
        fileFilter,
        filePage
    } = gs();
    if (!selectedProject) return;
    try {
        const q = fileFilter === 'all' ? '' : `&status=${fileFilter}`;
        const r = await api(`/projects/${selectedProject.id}/files?page=${filePage}&per_page=60${q}`);
        setState({
            files: r.files,
            fileTotal: r.total
        });
    } catch (e) {
        console.error('Failed to load files:', e);
    }
}

async function loadFileStats() {
    const {
        selectedProject
    } = gs();
    if (!selectedProject) return;
    try {
        setState({
            fileStats: await api(`/projects/${selectedProject.id}/files/stats`)
        });
    } catch (e) {
        console.error('Failed to load file stats:', e);
    }
}

async function loadTrash() {
    const {
        selectedProject
    } = gs();
    if (!selectedProject) return;
    try {
        setState({
            trashItems: await api(`/projects/${selectedProject.id}/trash`)
        });
    } catch (e) {
        console.error('Failed to load trash:', e);
    }
}

async function checkBackend() {
    try {
        await api('/health');
        setState({
            connected: true
        });
    } catch (e) {
        setState({
            connected: false
        });
    }
}
