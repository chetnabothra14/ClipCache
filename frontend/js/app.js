// ── State ────────────────────────────────────────────────────────────────────
let _state = {
  page: 'dashboard', projects: [], connected: null,
  selectedProject: null, showNewProject: false, showAnalyze: false,
  files: [], fileTotal: 0, filePage: 1, fileFilter: 'all',
  fileStats: {}, trashItems: [], scanProgress: null,
  analyzing: false, analysisProgress: null, selected: new Set(),
  toast: null, projectTab: 'files',
  // Analysis
  adType: 'video_with_audio', analyzeFpsMode: 'adaptive',
  // Preview
  previewFile: null, previewIndex: null
};

let _renderQueued = false;
const _listeners = [];

function setState(patch) {
    _state = {
        ..._state,
        ...patch
    };
    if (_renderQueued) return;
    _renderQueued = true;
    requestAnimationFrame(() => {
        _renderQueued = false;
        const root = document.getElementById('root');
        const el = App();
        root.innerHTML = '';
        root.appendChild(el);
    });
}

function gs() {
    return _state;
}

// ── Toast Helper ──────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
    setState({
        toast: {
            msg,
            type
        }
    });
    setTimeout(() => setState({
        toast: null
    }), 3500);
}

// ── Polling Management ────────────────────────────────────────────────────────
let scanPoll = null,
    analysisPoll = null;

function startScanPoll(pid) {
    if (scanPoll) clearInterval(scanPoll);
    scanPoll = setInterval(async () => {
        try {
            const p = await api(`/projects/${pid}/scan/progress`);
            setState({
                scanProgress: p
            });
            if (p.status === 'complete' || p.status === 'error') {
                clearInterval(scanPoll);
                scanPoll = null;
                setState({
                    scanProgress: null
                });
                loadFileStats();
                loadFiles();
                loadProjects();
                showToast('Scan complete! Files indexed.');
            }
        } catch (e) {}
    }, 300);
}

function startAnalysisPoll(pid) {
    if (analysisPoll) clearInterval(analysisPoll);
    let _lastPct = -1; // track last rendered integer percent to skip redundant re-renders
    analysisPoll = setInterval(async () => {
        try {
            const s = await api(`/projects/${pid}/analyze/status`);
            if (s.analysis_status === 'complete') {
                clearInterval(analysisPoll);
                analysisPoll = null;
                _lastPct = -1;
                setState({
                    analyzing: false,
                    analysisProgress: null
                });
                // Load stats immediately, then reload again after a short delay
                // as a safety net in case the backend hasn't fully committed yet
                await loadFileStats();
                await loadFiles();
                await loadProjects();
                showToast('Analysis complete! Review your results.');
                // Secondary reload after 500ms to ensure all DB writes are visible
                setTimeout(async () => {
                    await loadFileStats();
                    await loadFiles();
                    await loadProjects();
                }, 500);
            } else if (s.analysis_status === 'error') {
                clearInterval(analysisPoll);
                analysisPoll = null;
                _lastPct = -1;
                setState({
                    analyzing: false,
                    analysisProgress: null
                });
                showToast('Analysis failed. Check CMD window.', 'warn');
            } else {
                // Only re-render when the displayed integer percent actually changes
                // This prevents 3 different numbers flashing per second from float noise
                const newPct = Math.floor(s.percent || 0);
                if (newPct !== _lastPct || s.status !== (gs().analysisProgress || {}).status) {
                    _lastPct = newPct;
                    // Normalize percent to integer before storing so the UI shows a stable number
                    s.percent = newPct;
                    setState({ analysisProgress: s });
                }
            }
        } catch (e) {}
    }, 1000);
}

// ── Preview Navigation ────────────────────────────────────────────────────────
function openPreview(file, index) {
    setState({
        previewFile: file,
        previewIndex: index
    });
}

function closePreview() {
    setState({
        previewFile: null,
        previewIndex: null
    });
}

function previewNav(dir) {
    const {
        files,
        previewIndex
    } = gs();
    const newIdx = previewIndex + dir;
    if (newIdx < 0 || newIdx >= files.length) return false;
    setState({
        previewFile: files[newIdx],
        previewIndex: newIdx
    });
    return true;
}

// ── Keyboard Listeners ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
    if (!gs().previewFile) return;
    if (e.key === 'Escape') closePreview();
    if (e.key === 'ArrowRight') previewNav(1);
    if (e.key === 'ArrowLeft') previewNav(-1);
});

// ── Boot ──────────────────────────────────────────────────────────────────────
function boot() {
    checkBackend();
    loadProjects();
    setInterval(checkBackend, 10000);
    
    // Initial render
    const root = document.getElementById('root');
    if (root) {
        root.innerHTML = '';
        root.appendChild(App());
    }
}

// Start immediately
boot();