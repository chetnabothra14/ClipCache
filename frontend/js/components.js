// ── Common UI Helpers ────────────────────────────────────────────────────────

function Badge(status) {
    const map = {
        used: ['badge badge-used', '✅ Used'],
        unused: ['badge badge-unused', '❌ Unused'],
        review: ['badge badge-review', '⚠️ Review'],
        unanalyzed: ['badge badge-unanalyzed', '· Not scanned'],
        trashed: ['badge badge-trashed', '🗑 Trashed'],
        duplicate: ['badge badge-review', '🔀 Duplicate']
    };
    const [cls, label] = map[status] || ['badge badge-unanalyzed', status];
    return h('span', {
        className: cls
    }, label);
}

function ConfBar(val) {
    const col = val >= 85 ? 'var(--success)' : val >= 55 ? 'var(--warn)' : 'var(--danger)';
    return h('div', {
        className: 'conf-bar'
    }, h('div', {
        className: 'conf-fill',
        style: {
            width: val + '%',
            background: col
        }
    }));
}

// ── File Card component ──────────────────────────────────────────────────────

function FileCard(file, index, selected, onSelect) {
    const isVid = ['.mp4', '.mov', '.avi', '.mkv', '.mxf'].includes((file.extension || '').toLowerCase());
    const isRaw = ['.raw', '.cr2', '.cr3', '.arw', '.nef', '.dng'].includes((file.extension || '').toLowerCase());

    // Thumbnail image
    let thumbContent;
    if (isVid) {
        thumbContent = [
            h('img', {
                src: `${API}/files/${file.id}/preview?thumb=1`,
                loading: 'lazy',
                alt: file.filename,
                onerror: function() {
                    this.style.display = 'none';
                    this.parentNode.innerHTML = '<div style="font-size:40px">🎬</div><div class="play-icon">▶</div>';
                }
            }),
            h('div', {
                className: 'play-icon'
            }, '▶')
        ];
    } else if (isRaw) {
        thumbContent = h('div', {
            style: {
                fontSize: 36,
                color: 'var(--warn)'
            }
        }, '📷');
    } else {
        const img = h('img', {
            src: `${API}/files/${file.id}/preview`,
            loading: 'lazy',
            alt: file.filename,
            onerror: function() {
                this.style.display = 'none';
                this.parentNode.innerHTML = '<div style="font-size:36px">🖼️</div>';
            }
        });
        thumbContent = img;
    }

    return h('div', {
            className: `file-card ${selected ? 'selected' : ''}`,
            title: `${file.filename}\n${fmtBytes(file.size_bytes)}\nConfidence: ${file.confidence || 0}%`
        },
        h('div', {
            className: 'file-thumb'
        }, ...(Array.isArray(thumbContent) ? thumbContent : [thumbContent])),
        h('div', {
            className: `status-dot dot-${file.status}`
        }),
        h('div', {
            className: 'file-select',
            onclick: e => {
                e.stopPropagation();
                onSelect(file.id);
            }
        }, selected ? '✓' : ''),
        h('div', {
            className: 'file-info',
            onclick: () => openPreview(file, index)
        },
            h('div', {
                className: 'file-name',
                title: file.filename
            }, file.filename),
            h('div', {
                className: 'file-meta'
            },
                h('span', {
                    className: 'file-size'
                }, fmtBytes(file.size_bytes)),
                file.original_id ? Badge('duplicate') : Badge(file.status)
            ),
            file.confidence > 0 ? ConfBar(file.confidence) : null
        )
    );
}

// ── Modals ───────────────────────────────────────────────────────────────────

function PreviewModal() {
    const {
        previewFile: file,
        previewIndex,
        files
    } = gs();
    if (!file) return h('div', {
        style: {
            display: 'none'
        }
    });

    const isVid = ['.mp4', '.mov', '.avi', '.mkv', '.mxf'].includes((file.extension || '').toLowerCase());
    const isRaw = ['.raw', '.cr2', '.cr3', '.arw', '.nef', '.dng'].includes((file.extension || '').toLowerCase());
    const previewUrl = `${API}/files/${file.id}/preview`;
    const matchUrl = `${API}/files/${file.id}/match-frame`;

    // Main preview content
    let mainContent;
    if (isVid) {
        mainContent = h('video', {
            controls: true,
            autoplay: true,
            src: `${API}/files/${file.id}/stream`,
            style: {
                maxWidth: '100%',
                maxHeight: 'calc(92vh - 200px)',
                borderRadius: '8px'
            }
        });
    } else if (isRaw) {
        mainContent = h('div', {
                style: {
                    textAlign: 'center',
                    color: 'var(--muted)',
                    padding: '40px'
                }
            },
            h('div', {
                style: {
                    fontSize: 64
                }
            }, '📷'),
            h('div', {
                style: {
                    fontSize: 13,
                    marginTop: 12
                }
            }, 'RAW file preview not supported in browser'),
            h('div', {
                style: {
                    fontSize: 11,
                    marginTop: 6,
                    color: 'var(--muted)'
                }
            }, 'Open the file in your editing software to view it'),
            h('a', {
                href: previewUrl,
                download: file.filename,
                style: {
                    display: 'inline-block',
                    marginTop: 16,
                    padding: '8px 16px',
                    background: 'var(--surf2)',
                    border: '1px solid var(--border)',
                    borderRadius: '8px',
                    color: 'var(--text)',
                    fontSize: 12,
                    textDecoration: 'none'
                }
            }, '⬇ Download File')
        );
    } else {
        mainContent = h('img', {
            src: previewUrl,
            alt: file.filename,
            style: {
                maxWidth: '100%',
                maxHeight: 'calc(92vh - 200px)',
                objectFit: 'contain',
                borderRadius: '8px',
                display: 'block'
            },
            onerror: function() {
                this.outerHTML = '<div style="color:var(--muted);font-size:13px;padding:40px;text-align:center">⚠️ Could not load preview</div>';
            }
        });
    }

    // Match frame section
    const matchSection = h('div', {
            className: 'preview-section'
        },
        h('div', {
            className: 'preview-section-title'
        }, 'Matched Frame in Final Ad'),
        file.status === 'used' || file.status === 'review' ?
        h('div', {},
            h('div', {
                    className: 'match-thumb'
                },
                h('img', {
                    src: matchUrl,
                    alt: 'Matched frame',
                    style: {
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover'
                    },
                    onerror: function() {
                        this.outerHTML = '<div class="no-match">⚠️ Frame not available</div>';
                    }
                })
            ),
            h('div', {
                    style: {
                        fontSize: 11,
                        color: 'var(--muted)',
                        textAlign: 'center'
                    }
                },
                file.status === 'used' ? `✅ Found in final ad at ${file.confidence}% confidence` : `⚠️ Partial match \u2014 ${file.confidence}% confidence`
            )
        ) :
        h('div', {
                className: 'match-thumb'
            },
            h('div', {
                    className: 'no-match'
                },
                file.status === 'unused' ? '❌ Not found in final ad' :
                file.status === 'unanalyzed' ? 'Run analysis first' : '\u2014'
            )
        )
    );

    return h('div', {
            className: 'overlay',
            onclick: e => {
                if (e.target.className === 'overlay') closePreview();
            }
        },
        h('div', {
                className: 'preview-modal'
            },
            // Header
            h('div', {
                    className: 'preview-header'
                },
                h('div', {
                    className: 'preview-filename',
                    title: file.filename
                }, file.filename),
                         file.original_id ? Badge('duplicate') : Badge(file.status),
                h('div', {
                        style: {
                            marginLeft: 'auto',
                            display: 'flex',
                            gap: '8px',
                            alignItems: 'center'
                        }
                    },
                    h('span', {
                        style: {
                            fontSize: 12,
                            color: 'var(--muted)',
                            fontFamily: 'monospace'
                        }
                    }, `${previewIndex + 1} / ${files.length}`),
                    h('button', {
                        className: 'modal-close',
                        style: {
                            position: 'static'
                        },
                        onclick: closePreview
                    }, '\u2715')
                )
            ),
            // Body
            h('div', {
                    className: 'preview-body'
                },
                // Main preview area
                h('div', {
                        className: 'preview-main'
                    },
                    previewIndex > 0 ? h('div', {
                        className: 'nav-arrow left',
                        onclick: () => previewNav(-1)
                    }, '\u2039') : null,
                    mainContent,
                    previewIndex < files.length - 1 ? h('div', {
                        className: 'nav-arrow right',
                        onclick: () => previewNav(1)
                    }, '\u203A') : null
                ),
                // Sidebar
                h('div', {
                        className: 'preview-sidebar'
                    },
                    // File info
                    h('div', {
                            className: 'preview-section'
                        },
                        h('div', {
                            className: 'preview-section-title'
                        }, 'File Details'),
                        ...[
                            ['Name', file.filename],
                            ['Type', file.file_type],
                            ['Size', fmtBytes(file.size_bytes)],
                            ['Extension', file.extension || '\u2014'],
                            ['Status', file.status],
                            ['Confidence', file.confidence ? file.confidence + '%' : '\u2014'],
                            file.original_id ? ['Duplicate Of', 'ID: ' + file.original_id] : null
                        ].filter(Boolean).map(([k, v]) =>
                            h('div', {
                                    className: 'meta-row'
                                },
                                h('span', {
                                    className: 'meta-key'
                                }, k),
                                h('span', {
                                    className: 'meta-val',
                                    title: v
                                }, v)
                            )
                        )
                    ),
                    // Match frame
                    matchSection,
                    // Actions
                    h('div', {
                            className: 'preview-actions'
                        },
                        file.status === 'unused' || file.status === 'review' ?
                        h('button', {
                            className: 'btn btn-danger w-full',
                            style: {
                                width: '100%',
                                justifyContent: 'center'
                            },
                            onclick: async () => {
                                const {
                                    selectedProject
                                } = gs();
                                if (!confirm(`Move "${file.filename}" to Trash?`)) return;
                                try {
                                    await api(`/projects/${selectedProject.id}/trash`, {
                                        method: 'POST',
                                        body: JSON.stringify({
                                            file_ids: [file.id]
                                        })
                                    });
                                    showToast('Moved to Trash');
                                    loadFiles();
                                    loadFileStats();
                                    loadTrash();
                                    previewNav(1) || closePreview();
                                } catch (e) {
                                    showToast(e.message, 'warn');
                                }
                            }
                        }, '\uD83D\uDDD1 Move to Trash') :
                        null,
                        file.status === 'unused' || file.status === 'review' ?
                        h('button', {
                            className: 'btn btn-success',
                            style: {
                                width: '100%',
                                justifyContent: 'center'
                            },
                            onclick: async () => {
                                try {
                                    await api(`/files/${file.id}/protect?protected=true`, {
                                        method: 'PATCH'
                                    });
                                    showToast('File protected \u2014 will never be deleted');
                                    loadFiles();
                                } catch (e) {
                                    showToast(e.message, 'warn');
                                }
                            }
                        }, '\uD83D\uDD12 Protect This File') :
                        null,
                        h('button', {
                            className: 'btn btn-secondary',
                            style: {
                                width: '100%',
                                justifyContent: 'center'
                            },
                            onclick: closePreview
                        }, 'Close')
                    )
                )
            )
        )
    );
}

function NewProjectModal() {
    // Store form values directly in _state without triggering a re-render.
    // This survives re-renders caused by checkBackend() firing every 10s.
    if (!_state._newProjectName) _state._newProjectName = '';
    if (!_state._newProjectFolder) _state._newProjectFolder = '';

    const errDiv = h('div', {
        id: 'modal-err'
    });

    // Create name input — restore any previously typed value after re-render
    const nameInput = h('input', {
        id: 'new-project-name',
        className: 'form-input',
        placeholder: 'e.g. Nike Campaign June 2025',
        oninput: e => {
            _state._newProjectName = e.target.value; // direct mutation — no re-render
        }
    });
    nameInput.value = _state._newProjectName; // restore typed text after re-render

    // Create folder input — restore any previously typed value after re-render
    const folderInput = h('input', {
        id: 'new-project-folder',
        className: 'form-input',
        placeholder: 'e.g. D:\\AdShoots\\Nike_June_2025',
        oninput: e => {
            _state._newProjectFolder = e.target.value; // direct mutation — no re-render
        }
    });
    folderInput.value = _state._newProjectFolder; // restore typed text after re-render

    function closeModal() {
        // Clear stored form values when modal is dismissed
        _state._newProjectName = '';
        _state._newProjectFolder = '';
        setState({ showNewProject: false });
    }


    const browseBtn = h('button', {
            className: 'btn btn-secondary',
            style: { flexShrink: 0, whiteSpace: 'nowrap' },
            title: 'Open folder picker',
            onclick: async function() {
                const originalHTML = this.innerHTML;
                this.innerHTML = '⏳ Opening...';
                this.disabled = true;
                try {
                    // /browse-dialog opens the native OS folder picker
                    const r = await api('/browse-dialog');
                    if (r && r.folder) {
                        _state._newProjectFolder = r.folder;
                        folderInput.value = r.folder;
                        errDiv.innerHTML = '';
                    }
                } catch (e) {
                    errDiv.innerHTML = '<div class="alert alert-warn">⚠️ ' + e.message + '</div>';
                }
                this.disabled = false;
                this.innerHTML = originalHTML;
            }
        },
        '📂 Browse'
    );

    return h('div', {
            className: 'overlay',
            onclick: e => {
                if (e.target.className === 'overlay') closeModal();
            }
        },
        h('div', {
                className: 'modal'
            },
            h('button', {
                className: 'modal-close',
                onclick: closeModal
            }, '\u2715'),
            h('div', { className: 'modal-title' }, '\uFF0B New Project'),
            h('div', { className: 'modal-sub' }, 'Create a project for an ad shoot campaign'),
            h('div', { className: 'form-group' },
                h('label', { className: 'form-label' }, 'Project Name'),
                nameInput
            ),
            h('div', { className: 'form-group' },
                h('label', { className: 'form-label' }, 'Raw Media Folder Path'),
                h('div', {
                        style: { display: 'flex', gap: '8px', alignItems: 'center' }
                    },
                    folderInput,
                    browseBtn
                ),
                h('div', { className: 'text-xs text-muted mt-2' },
                    'Paste the full path \u2014 or click Browse to pick a folder')
            ),
            errDiv,
            h('div', { className: 'form-actions' },
                h('button', {
                    className: 'btn btn-secondary',
                    onclick: closeModal
                }, 'Cancel'),
                h('button', {
                    className: 'btn btn-primary',
                    onclick: async function() {
                        const name   = (_state._newProjectName  || '').trim();
                        const folder = (_state._newProjectFolder || '').trim();
                        if (!name || !folder) {
                            errDiv.innerHTML = '<div class="alert alert-warn">Both fields required</div>';
                            return;
                        }
                        this.disabled = true;
                        this.textContent = 'Creating\u2026';
                        try {
                            const p = await api('/projects', {
                                method: 'POST',
                                body: JSON.stringify({ name, raw_folder: folder })
                            });
                            // Clear form state before navigating
                            _state._newProjectName = '';
                            _state._newProjectFolder = '';
                            await loadProjects();
                            setState({
                                showNewProject: false,
                                selectedProject: p,
                                page: 'project',
                                fileFilter: 'all',
                                filePage: 1,
                                projectTab: 'files'
                            });
                            loadFileStats();
                            loadFiles();
                            loadTrash();
                            showToast('Project created!');
                        } catch (e) {
                            errDiv.innerHTML = `<div class="alert alert-warn">\u26A0\uFE0F ${e.message}</div>`;
                            this.disabled = false;
                            this.textContent = 'Create Project';
                        }
                    }
                }, 'Create Project')
            )
        )
    );
}

function AnalyzeModal() {
    const {
        selectedProject,
        analyzeFile,
        uploading,
        uploadProgressText,
        uploadProgressPercent
    } = gs();
    const fileInput = h('input', {
        type: 'file',
        accept: 'video/*',
        style: {
            display: 'none'
        },
        onchange: function() {
            const selFile = this.files[0];
            if (selFile) {
                setState({
                    analyzeFile: selFile
                });
            }
        }
    });
    const errDiv = h('div', {
        id: 'analyze-err'
    });
    return h('div', {
            className: 'overlay',
            onclick: e => {
                if (e.target.className === 'overlay') setState({
                    showAnalyze: false
                });
            }
        },
        h('div', {
                className: 'modal'
            },
            h('button', {
                className: 'modal-close',
                onclick: () => setState({
                    showAnalyze: false
                })
            }, '\u2715'),
            h('div', {
                className: 'modal-title'
            }, '\uD83C\uDFAC Analyze Final Ad'),
            h('div', {
                className: 'modal-sub'
            }, 'Upload the finished ad video to detect which raw files were used'),
            fileInput,
            h('div', {
                    className: 'form-group'
                },
                h('label', {
                    className: 'form-label'
                }, 'Final Ad Video'),
                h('div', {
                        className: 'upload-zone',
                        onclick: () => fileInput.click()
                    },
                    h('div', {
                        id: 'up-icon',
                        style: {
                            fontSize: 38,
                            marginBottom: 12
                        }
                    }, analyzeFile ? '\u2705' : '\uD83C\uDFAC'),
                    h('div', {
                        id: 'up-name',
                        style: {
                            fontSize: 14,
                            marginBottom: 5
                        }
                    }, analyzeFile ? analyzeFile.name : 'Click to select final ad video'),
                    h('div', {
                        id: 'up-size',
                        style: {
                            fontSize: 12,
                            color: 'var(--muted)'
                        }
                    }, analyzeFile ? fmtBytes(analyzeFile.size) + ' \u00B7 Ready' : 'MP4, MOV, AVI, MKV supported')
                )
            ),
            h('div', {
                    className: 'form-group'
                },
                h('label', {
                    className: 'form-label'
                }, 'Ad Type'),
                h('select', {
                        className: 'form-input',
                        id: 'ad-type-select',
                        value: gs().adType || 'video_with_audio',
                        style: {
                            background: 'rgba(10, 10, 10, 0.85)',
                            borderColor: 'var(--border)',
                            color: 'var(--text)'
                        },
                        onchange: e => {
                            setState({
                                adType: e.target.value
                            });
                        }
                    },
                    h('option', {
                        value: 'video_with_audio'
                    }, '🎥 Video with Audio — Music video, commercial, or motion ad'),
                    h('option', {
                        value: 'acted_ads'
                    }, '🎭 Acted Ads — Dialogue-heavy, audio is critical'),
                    h('option', {
                        value: 'product_photoshoot'
                    }, '📷 Product Photoshoot — Photos & videos (audio ignored)')
                ),
                h('div', {
                    className: 'text-xs text-muted mt-2'
                }, gs().adType === 'product_photoshoot' ? 'Uses pure image hashing (audio ignored)' : gs().adType === 'acted_ads' ? 'Prioritizes audio matching (60%) over visual (40%) - dialogue/sound is key' : 'Uses balanced audio and visual matching for optimal results')
            ),
            h('div', {
                    className: 'form-group'
                },
                h('label', {
                    className: 'form-label'
                }, 'Frame Extraction Mode'),
                h('select', {
                        className: 'form-input',
                        value: gs().analyzeFpsMode || 'adaptive',
                        style: {
                            background: 'rgba(10, 10, 10, 0.85)',
                            borderColor: 'var(--border)',
                            color: 'var(--text)'
                        },
                        onchange: e => {
                            setState({
                                analyzeFpsMode: e.target.value
                            });
                        }
                    },
                    h('option', {
                        value: 'adaptive'
                    }, 'Adaptive (Recommended) \u2014 Smart scene detection'),
                    h('option', {
                        value: 'quick'
                    }, 'Quick \u2014 2fps \u2014 Lightly edited ads'),
                    h('option', {
                        value: 'standard'
                    }, 'Standard \u2014 5fps \u2014 Moderate editing'),
                    h('option', {
                        value: 'high'
                    }, 'High Detail \u2014 10fps \u2014 Heavily edited'),
                    h('option', {
                        value: 'maximum'
                    }, 'Maximum \u2014 24fps \u2014 Flash cuts, music videos')
                )
            ),
            h('div', {
                className: 'alert alert-info'
            }, '\u2139\uFE0F Handles color grading, cropping & slow motion automatically.'),
            errDiv,
            h('div', {
                    className: 'form-actions',
                    style: {
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '16px'
                    }
                },
                uploading ? h('div', {
                    style: {
                        display: 'flex',
                        alignItems: 'center',
                        width: '100%',
                        gap: '12px'
                    }
                },
                    h('div', {
                            className: 'progress-wrap',
                            style: {
                                flex: 1,
                                margin: 0,
                                height: 16
                            }
                        },
                        h('div', {
                            className: 'progress-bar',
                            style: {
                                width: (uploadProgressPercent || 0) + '%'
                            }
                        })
                    ),
                    h('span', {
                        style: {
                            fontSize: 13,
                            fontFamily: 'monospace',
                            fontWeight: 600
                        }
                    }, (uploadProgressPercent || 0) + '%')
                ) : null,
                h('div', {
                        style: {
                            display: 'flex',
                            gap: '8px',
                            justifyContent: 'flex-end',
                            width: '100%'
                        }
                    },
                    h('button', {
                        className: 'btn btn-secondary',
                        disabled: uploading,
                        onclick: () => setState({
                            showAnalyze: false
                        })
                    }, 'Cancel'),
                    h('button', {
                        className: 'btn btn-primary',
                        disabled: uploading,
                        onclick: async function() {
                            if (!analyzeFile) {
                                errDiv.innerHTML = '<div class="alert alert-warn">Select a video file first</div>';
                                return;
                            }
                            setState({
                                uploading: true,
                                uploadProgressText: 'Starting\u2026',
                                uploadProgressPercent: 0
                            });
                            try {
                                const CHUNK_SIZE = 8 * 1024 * 1024; // 8MB chunks
                                const totalChunks = Math.ceil(analyzeFile.size / CHUNK_SIZE);
                                const fileId = Date.now().toString() + "_" + Math.floor(Math.random() * 1000);

                                for (let i = 0; i < totalChunks; i++) {
                                    const start = i * CHUNK_SIZE;
                                    const end = Math.min(start + CHUNK_SIZE, analyzeFile.size);
                                    const chunk = analyzeFile.slice(start, end);

                                    const fd = new FormData();
                                    fd.append('file_id', fileId);
                                    fd.append('chunk_index', i);
                                    fd.append('total_chunks', totalChunks);
                                    fd.append('chunk', chunk, analyzeFile.name);

                                    const r = await fetch(`${API}/projects/${selectedProject.id}/analyze/chunk`, {
                                        method: 'POST',
                                        body: fd
                                    });
                                    if (!r.ok) {
                                        const e = await r.json().catch(() => ({}));
                                        throw new Error(e.detail || 'Chunk upload failed');
                                    }

                                    const pct = Math.round(((i + 1) / totalChunks) * 100);
                                    setState({
                                        uploadProgressText: `Uploading\u2026`,
                                        uploadProgressPercent: pct
                                    });
                                }

                                setState({
                                    uploadProgressText: 'Starting Analysis\u2026'
                                });

                                const fdComplete = new FormData();
                                fdComplete.append('file_id', fileId);
                                fdComplete.append('filename', analyzeFile.name);
                                fdComplete.append('fps_mode', gs().analyzeFpsMode || 'adaptive');
                                fdComplete.append('ad_type', gs().adType || 'video_with_audio');

                                const cResp = await fetch(`${API}/projects/${selectedProject.id}/analyze/complete`, {
                                    method: 'POST',
                                    body: fdComplete
                                });
                                if (!cResp.ok) {
                                    const e = await cResp.json().catch(() => ({}));
                                    throw new Error(e.detail || 'Finalizing failed');
                                }

                                setState({
                                    showAnalyze: false,
                                    analyzing: true,
                                    uploading: false,
                                    analyzeFile: null
                                });
                                startAnalysisPoll(selectedProject.id);
                            } catch (e) {
                                errDiv.innerHTML = `<div class="alert alert-warn">\u26A0\uFE0F ${e.message}</div>`;
                                setState({
                                    uploading: false
                                });
                            }
                        }
                    }, uploading ? uploadProgressText : '\uD83D\uDE80 Start Analysis')
                )
            )
        )
    );
}

// ── Pages ────────────────────────────────────────────────────────────────────

function DashboardPage() {
    const {
        projects
    } = gs();
    const totalFiles = projects.reduce((s, p) => s + (p.total_files || 0), 0);
    const unusedSize = projects.reduce((s, p) => s + (p.unused_size_bytes || 0), 0);
    const analyzed = projects.filter(p => p.status === 'analyzed').length;
    return h('div', {},
        h('div', {
                className: 'stats-row'
            },
            ...[
                ['Projects', projects.length, ''],
                ['Files Indexed', totalFiles.toLocaleString(), ''],
                ['Reclaimable', fmtBytes(unusedSize), 'c-unused'],
                ['Analyzed', analyzed, 'c-used']
            ]
            .map(([l, v, c]) => h('div', {
                className: 'stat-card'
            }, h('div', {
                className: 'stat-label'
            }, l), h('div', {
                className: `stat-value ${c}`
            }, v)))
        ),
        h('div', {
                className: 'flex justify-between items-center mb-3'
            },
            h('div', {
                className: 'section-title'
            }, 'Ad Projects'),
            h('button', {
                className: 'btn btn-primary',
                onclick: () => setState({
                    showNewProject: true
                })
            }, '\uFF0B New Project')
        ),
        projects.length === 0 ?
        h('div', {
            className: 'empty'
        }, h('div', {
            className: 'empty-icon'
        }, '\uD83C\uDFAC'), h('div', {
            className: 'empty-text'
        }, 'No projects yet'), h('div', {
            className: 'empty-sub'
        }, 'Create your first project to get started'), h('button', {
            className: 'btn btn-primary',
            style: {
                marginTop: '14px'
            },
            onclick: () => setState({
                showNewProject: true
            })
        }, '\uFF0B New Project')) :
        h('table', {
                className: 'table'
            },
            h('thead', {}, h('tr', {}, ...['Project', 'Folder', 'Files', 'Status', 'Reclaimable', ''].map(t => h('th', {}, t)))),
            h('tbody', {}, ...projects.map(p => h('tr', {},
                h('td', {}, h('strong', {}, p.name), h('div', {
                    className: 'text-xs text-muted mt-2'
                }, fmtDate(p.created_at))),
                h('td', {}, h('span', {
                    className: 'tag'
                }, p.raw_folder.length > 32 ? '\u2026' + p.raw_folder.slice(-30) : p.raw_folder)),
                h('td', {}, (p.total_files || 0).toLocaleString()),
                h('td', {}, Badge(p.status === 'analyzed' ? 'used' : p.status === 'analyzing' ? 'review' : 'unanalyzed')),
                h('td', {
                    className: 'c-unused'
                }, fmtBytes(p.unused_size_bytes)),
                h('td', {},
                    h('div', {
                            style: {
                                display: 'flex',
                                gap: '6px'
                            }
                        },
                        h('button', {
                            className: 'btn btn-secondary btn-sm',
                            onclick: () => {
                                const isAnalyzing = p.status === 'analyzing';
                                setState({
                                    selectedProject: p,
                                    page: 'project',
                                    fileFilter: 'all',
                                    filePage: 1,
                                    projectTab: 'files',
                                    analyzing: isAnalyzing
                                });
                                if (isAnalyzing) startAnalysisPoll(p.id);
                                loadFileStats();
                                loadFiles();
                                loadTrash();
                            }
                        }, 'Open \u2192'),
                        h('button', {
                            className: 'btn btn-danger btn-sm',
                            onclick: async (e) => {
                                e.stopPropagation();
                                if (!confirm(`Delete project "${p.name}"?`)) return;
                                const deleteFiles = confirm(`Also PERMANENTLY DELETE all raw media files from your hard drive?\n\n\u2022 OK = Delete files from disk forever\n\u2022 Cancel = Only remove project from ClipCache (files stay on disk)`);
                                try {
                                    await api(`/projects/${p.id}?delete_files=${deleteFiles}`, {
                                        method: 'DELETE'
                                    });
                                    showToast(deleteFiles ? `Project "${p.name}" and all files deleted from disk.` : `Project "${p.name}" removed from ClipCache.`);
                                    loadProjects();
                                } catch (err) {
                                    showToast(err.message, 'warn');
                                }
                            }
                        }, '\uD83D\uDDD1')
                    )
                )
            )))
        )
    );
}

function ProjectPage() {
    const {
        selectedProject,
        files,
        fileTotal,
        filePage,
        fileFilter,
        fileStats,
        trashItems,
        scanProgress,
        analyzing,
        selected,
        projectTab
    } = gs();
    const PER_PAGE = 60;
    const scanRunning = scanProgress && scanProgress.status === 'running';
    const filterCounts = {
        all: fileStats.total || 0,
        used: fileStats.used || 0,
        unused: fileStats.unused || 0,
        review: fileStats.review || 0,
        unanalyzed: fileStats.unanalyzed || 0,
        duplicates: fileStats.duplicates || 0
    };

    return h('div', {},
        // Header row
        h('div', {
                className: 'flex items-center gap-3 mb-4',
                style: {
                    flexWrap: 'wrap'
                }
            },
            h('button', {
                className: 'btn btn-secondary btn-sm',
                onclick: () => setState({
                    selectedProject: null,
                    page: 'dashboard',
                    files: [],
                    fileStats: {}
                })
            }, '\u2190 Back'),
            h('div', {},
                h('div', {
                    style: {
                        fontWeight: 700,
                        fontSize: 17
                    }
                }, selectedProject.name),
                h('div', {
                    className: 'text-xs text-muted'
                }, selectedProject.raw_folder)
            ),
            h('div', {
                    style: {
                        marginLeft: 'auto',
                        display: 'flex',
                        gap: '8px',
                        flexWrap: 'wrap'
                    }
                },
                h('button', {
                    className: 'btn btn-secondary btn-sm',
                    disabled: scanRunning,
                    onclick: async function() {
                        try {
                            await api(`/projects/${selectedProject.id}/scan`, {
                                method: 'POST'
                            });
                            startScanPoll(selectedProject.id);
                            showToast('Scan started\u2026');
                        } catch (e) {
                            showToast(e.message, 'warn');
                        }
                    }
                }, scanRunning ? '\u231B Scanning\u2026' : '\uD83D\uDD0D Scan Folder'),
                h('button', {
                    className: 'btn btn-primary btn-sm',
                    disabled: analyzing,
                    onclick: () => setState({
                        showAnalyze: true
                    })
                }, analyzing ? '\u231B Analyzing\u2026' : '\uD83C\uDFAC Analyze Final Ad'),
                selected.size > 0 ? h('button', {
                    className: 'btn btn-secondary btn-sm',
                    onclick: async () => {
                        if (!confirm(`Move ${selected.size} files to Trash?\n\nFiles can be restored within 30 days.`)) return;
                        try {
                            await api(`/projects/${selectedProject.id}/trash`, {
                                method: 'POST',
                                body: JSON.stringify({
                                    file_ids: [...selected]
                                })
                            });
                            setState({
                                selected: new Set()
                            });
                            loadFileStats();
                            loadFiles();
                            loadTrash();
                            showToast(`${selected.size} files moved to Trash`);
                        } catch (e) {
                            showToast(e.message, 'warn');
                        }
                    }
                }, `\uD83D\uDDD1 Trash ${selected.size}`) : null,
                selected.size > 0 ? h('button', {
                    className: 'btn btn-danger btn-sm',
                    onclick: async () => {
                        if (!confirm(`\u26A0\uFE0F PERMANENTLY DELETE ${selected.size} files from your hard drive?\n\nThis CANNOT be undone. The actual files will be removed from disk forever.`)) return;
                        if (!confirm(`FINAL WARNING: You are about to permanently delete ${selected.size} files. Are you absolutely sure?`)) return;
                        try {
                            // First move to trash, then immediately permanently delete
                            await api(`/projects/${selectedProject.id}/trash`, {
                                method: 'POST',
                                body: JSON.stringify({
                                    file_ids: [...selected]
                                })
                            });
                            await api('/trash/delete', {
                                method: 'DELETE',
                                body: JSON.stringify({
                                    file_ids: [...selected]
                                })
                            });
                            setState({
                                selected: new Set()
                            });
                            loadFileStats();
                            loadFiles();
                            loadTrash();
                            showToast(`${selected.size} files permanently deleted from disk`);
                        } catch (e) {
                            showToast(e.message, 'warn');
                        }
                    }
                }, ` Delete ${selected.size} permanently`) : null
            )
        ),
        // Scan progress banner
        scanRunning && scanProgress ? h('div', {
            className: 'alert alert-info mb-3'
        },
            h('div', {
                    style: {
                        flex: 1
                    }
                },
                h('div', {
                    className: 'flex justify-between'
                }, h('span', {}, 'Scanning\u2026'), h('span', {
                    style: {
                        fontFamily: 'monospace',
                        fontSize: 12
                    }
                }, scanProgress.percent + '%')),
                h('div', {
                    className: 'progress-wrap'
                }, h('div', {
                    className: 'progress-bar',
                    style: {
                        width: scanProgress.percent + '%'
                    }
                })),
                h('div', {
                    className: 'text-xs text-muted'
                }, `${scanProgress.current_file} \u00B7 ${scanProgress.processed} processed`)
            )
        ) : null,
        // Analyzing banner
        analyzing && gs().analysisProgress && gs().analysisProgress.status !== 'idle' ? h('div', {
            className: 'alert alert-info mb-3',
            style: {
                display: 'flex',
                alignItems: 'center',
                gap: '16px'
            }
        },
            h('div', {
                    style: {
                        flex: 1
                    }
                },
                h('div', {
                    className: 'flex justify-between'
                }, h('span', {}, '🎬 Analyzing\u2026'), h('span', {
                    style: {
                        fontFamily: 'monospace',
                        fontSize: 12
                    }
                }, (gs().analysisProgress.percent || 0) + '%')),
                h('div', {
                    className: 'progress-wrap'
                }, h('div', {
                    className: 'progress-bar',
                    style: {
                        width: (gs().analysisProgress.percent || 0) + '%'
                    }
                })),
                h('div', {
                    className: 'text-xs text-muted'
                }, gs().analysisProgress.phase || 
                    ((gs().analysisProgress.status === 'matching' || gs().analysisProgress.status === 'classifying') ?
                    `${gs().analysisProgress.current_file || '...'} · ${gs().analysisProgress.processed || 0} / ${gs().analysisProgress.total || 0}` :
                    `${fmtTime(gs().analysisProgress.current_time)} / ${fmtTime(gs().analysisProgress.duration)}`))
            ),
            h('button', {
                className: 'btn btn-danger btn-sm',
                style: {
                    flexShrink: 0
                },
                title: 'Stop the analysis at any time',
                onclick: async () => {
                    if (!confirm("Are you sure you want to stop the analysis? This will reset all progress.")) return;
                    try {
                        await api(`/projects/${selectedProject.id}/analyze`, {
                            method: 'DELETE'
                        });
                        if (typeof analysisPoll !== 'undefined' && analysisPoll) {
                            clearInterval(analysisPoll);
                            analysisPoll = null;
                        }
                        setState({
                            analyzing: false,
                            analysisProgress: null
                        });
                        loadFileStats();
                        loadFiles();
                        showToast("Analysis stopped.");
                    } catch (e) {
                        showToast(e.message, 'warn');
                    }
                }
            }, '🛑 Stop Analysis')
        ) : null,
        // Stats
        h('div', {
                className: 'stats-row',
                style: {
                    marginBottom: '16px'
                }
            },
            ...[
                ['Total', fileStats.total || 0, '', fmtBytes(fileStats.total_size)],
                ['Used \u2705', fileStats.used || 0, 'c-used', fmtBytes(fileStats.used_size)],
                ['Unused \u274C', fileStats.unused || 0, 'c-unused', fmtBytes(fileStats.unused_size)],
                ['Review \u26A0\uFE0F', fileStats.review || 0, 'c-review', fmtBytes(fileStats.review_size)],
                ['Reclaimable', fmtBytes(fileStats.unused_size), 'c-accent', 'can be freed']
            ]
            .map(([l, v, c, s]) => h('div', {
                className: 'stat-card'
            }, h('div', {
                className: 'stat-label'
            }, l), h('div', {
                className: `stat-value ${c}`
            }, v), s ? h('div', {
                className: 'stat-sub'
            }, s) : null))
        ),
        // Tabs
        h('div', {
                style: {
                    borderBottom: '1px solid var(--border)',
                    marginBottom: '18px',
                    display: 'flex',
                    gap: '4px'
                }
            },
            ['files', 'trash', 'duplicates'].map(t => {
                const active = projectTab === t;
                return h('button', {
                        style: {
                            padding: '8px 16px',
                            background: 'none',
                            border: 'none',
                            color: active ? 'var(--accent)' : 'var(--muted)',
                            borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                            cursor: 'pointer',
                            fontSize: 13,
                            fontWeight: 600,
                            transition: 'all .15s'
                        },
                        onclick: () => setState({
                            projectTab: t,
                            filePage: 1
                        })
                    },
                    t === 'files' ? `Files (${fileStats.total || 0})` : t === 'trash' ? `Trash (${trashItems.length})` : `🔀 Duplicates (${fileStats.duplicates || 0})`
                );
            })
        ),

        // FILES TAB
        projectTab === 'files' ? h('div', {},
            h('div', {
                    className: 'filter-bar'
                },
                ...Object.entries(filterCounts).map(([k, v]) =>
                    h('button', {
                        className: `filter-btn ${fileFilter === k ? 'active' : ''}`,
                        onclick: () => {
                            setState({
                                fileFilter: k,
                                filePage: 1
                            });
                            loadFiles();
                        }
                    }, `${k === 'all' ? 'All' : k === 'duplicates' ? '🔀 Duplicates' : k.charAt(0).toUpperCase() + k.slice(1)} ${v}`)
                ),
                fileFilter === 'unused' && files.length > 0 ? h('button', {
                    className: 'btn btn-secondary btn-sm',
                    style: {
                        marginLeft: 'auto'
                    },
                    onclick: () => {
                        setState({
                            selected: new Set(files.filter(f => f.status === 'unused').map(f => f.id))
                        });
                    }
                }, 'Select All Unused') : null
            ),
            // Tip
            (fileStats.total || 0) > 0 && (fileStats.unanalyzed || 0) === 0 && files.length > 0 ?
            h('div', {
                className: 'alert alert-info mb-3',
                style: {
                    fontSize: 12
                }
            }, '\uD83D\uDCA1 Click any file card to preview it full size. Use \u2190 \u2192 arrow keys to browse.') :
            null,
            files.length === 0 ?
            h('div', {
                className: 'empty'
            }, h('div', {
                className: 'empty-icon'
            }, '\uD83D\uDCC1'), h('div', {
                className: 'empty-text'
            }, (fileStats.total || 0) === 0 ? 'No files indexed yet' : 'No files in this filter'), h('div', {
                className: 'empty-sub'
            }, (fileStats.total || 0) === 0 ? 'Click "Scan Folder" to index your raw media' : 'Select a different filter above')) :
            h('div', {},
                h('div', {
                    className: 'file-grid'
                }, ...files.map((f, i) => FileCard(f, i, selected.has(f.id), id => {
                    const n = new Set(selected);
                    n.has(id) ? n.delete(id) : n.add(id);
                    setState({
                        selected: n
                    });
                }))),
                fileTotal > PER_PAGE ? h('div', {
                        className: 'flex justify-between items-center',
                        style: {
                            marginTop: '20px'
                        }
                    },
                    h('span', {
                        className: 'text-xs text-muted'
                    }, `Showing ${((filePage - 1) * PER_PAGE) + 1}\u2013${Math.min(filePage * PER_PAGE, fileTotal)} of ${fileTotal}`),
                    h('div', {
                            className: 'flex gap-2'
                        },
                        h('button', {
                            className: 'btn btn-secondary btn-sm',
                            disabled: filePage === 1,
                            onclick: () => {
                                setState({
                                    filePage: filePage - 1
                                });
                                loadFiles();
                            }
                        }, '\u2190 Prev'),
                        h('button', {
                            className: 'btn btn-secondary btn-sm',
                            disabled: filePage * PER_PAGE >= fileTotal,
                            onclick: () => {
                                setState({
                                    filePage: filePage + 1
                                });
                                loadFiles();
                            }
                        }, 'Next \u2192')
                    )
                ) : null
            )
        ) : null,

        // TRASH TAB
        projectTab === 'trash' ? h('div', {},
            trashItems.length === 0 ?
            h('div', {
                className: 'empty'
            }, h('div', {
                className: 'empty-icon'
            }, '\uD83D\uDDD1\uFE0F'), h('div', {
                className: 'empty-text'
            }, 'Trash is empty'), h('div', {
                className: 'empty-sub'
            }, 'Files moved to trash will appear here for 30 days')) :
            h('div', {}, ...trashItems.map(item =>
                h('div', {
                        className: 'trash-item'
                    },
                    h('div', {
                        style: {
                            fontSize: 24
                        }
                    }, item.file_type === 'video' ? '\uD83C\uDFAC' : '\uD83D\uDDBC\uFE0F'),
                    h('div', {
                            className: 'trash-info'
                        },
                        h('div', {
                            className: 'trash-name'
                        }, item.filename),
                        h('div', {
                            className: 'trash-meta'
                        }, `${fmtBytes(item.size_bytes)} \u00B7 Expires ${fmtDate(item.expires_at)}`)
                    ),
                    h('div', {
                            style: {
                                display: 'flex',
                                gap: '8px'
                            }
                        },
                        h('button', {
                            className: 'btn btn-secondary btn-sm',
                            onclick: async () => {
                                try {
                                    await api('/trash/restore', {
                                        method: 'POST',
                                        body: JSON.stringify({
                                            file_ids: [item.file_id]
                                        })
                                    });
                                    loadTrash();
                                    loadFiles();
                                    loadFileStats();
                                    showToast('File restored!');
                                } catch (e) {
                                    showToast(e.message, 'warn');
                                }
                            }
                        }, '\u21A9 Restore'),
                        h('button', {
                            className: 'btn btn-danger btn-sm',
                            onclick: async () => {
                                if (!confirm('Permanently delete? Cannot be undone.')) return;
                                try {
                                    await api('/trash/delete', {
                                        method: 'DELETE',
                                        body: JSON.stringify({
                                            file_ids: [item.file_id]
                                        })
                                    });
                                    loadTrash();
                                    loadFileStats();
                                    showToast('Permanently deleted');
                                } catch (e) {
                                    showToast(e.message, 'warn');
                                }
                            }
                        }, '\u2715 Delete')
                    )
                )
            ))
        ) : null,

        // DUPLICATES TAB
        projectTab === 'duplicates' ? h('div', {},
            h('div', {
                    className: 'filter-bar'
                },
                h('button', {
                    className: 'btn btn-primary btn-sm',
                    disabled: (fileStats.duplicates || 0) === 0,
                    onclick: async function() {
                        if (!confirm('Delete all duplicates?\n\nOnly the original files will be kept.')) return;
                        if (!confirm('Are you absolutely sure? This will delete all duplicate files.')) return;
                        this.disabled = true;
                        this.textContent = 'Deleting\u2026';
                        try {
                            const duplicateIds = files.map(f => f.id);
                            await api(`/projects/${selectedProject.id}/trash`, {
                                method: 'POST',
                                body: JSON.stringify({
                                    file_ids: duplicateIds
                                })
                            });
                            await loadFileStats();
                            await loadFiles();
                            showToast(`${files.length} duplicates moved to trash!`);
                        } catch (e) {
                            showToast(e.message, 'warn');
                        }
                        this.disabled = false;
                        this.textContent = '\uD83D\uDDD1 Delete All Duplicates';
                    }
                }, '\uD83D\uDDD1 Delete All Duplicates')
            ),
            (fileStats.duplicates || 0) === 0 ?
            h('div', {
                className: 'empty'
            }, h('div', {
                className: 'empty-icon'
            }, '\u2705'), h('div', {
                className: 'empty-text'
            }, 'No duplicates found'), h('div', {
                className: 'empty-sub'
            }, 'Click "🔀 Find Duplicates" button above to detect duplicate files')) :
            h('div', {},
                h('div', {
                    className: 'alert alert-info mb-3',
                    style: {
                        fontSize: 12
                    }
                }, `Found ${fileStats.duplicates} duplicate files. The original file (with earliest date) is kept, others can be deleted.`),
                h('div', {
                    className: 'file-grid'
                }, ...files.map((f, i) => FileCard(f, i, selected.has(f.id), id => {
                    const n = new Set(selected);
                    n.has(id) ? n.delete(id) : n.add(id);
                    setState({
                        selected: n
                    });
                })))
            )
        ) : null
    );
}

function ReportsPage() {
    const {
        projects
    } = gs();
    return h('div', {},
        h('div', {
            className: 'section-title mb-3'
        }, 'Reports & Export'),
        projects.length === 0 ? h('div', {
            className: 'empty'
        }, h('div', {
            className: 'empty-icon'
        }, '\uD83D\uDCCA'), h('div', {
            className: 'empty-text'
        }, 'No projects yet')) :
        h('div', {}, ...projects.map(p => h('div', {
                className: 'card flex justify-between items-center'
            },
            h('div', {}, h('div', {
                style: {
                    fontWeight: 600
                }
            }, p.name), h('div', {
                className: 'text-xs text-muted mt-2'
            }, `${(p.total_files || 0).toLocaleString()} files \u00B7 ${fmtBytes(p.total_size_bytes)} \u00B7 ${fmtBytes(p.unused_size_bytes)} reclaimable`)),
            h('button', {
                className: 'btn btn-secondary btn-sm',
                onclick: () => window.open(`${API}/projects/${p.id}/report`, '_blank')
            }, '\u2B07 Export CSV')
        )))
    );
}

function SettingsPage() {
    const {
        connected
    } = gs();
    return h('div', {},
        h('div', {
            className: 'section-title mb-3'
        }, 'Settings'),
        h('div', {
                className: 'card'
            },
            h('div', {
                style: {
                    fontWeight: 600,
                    marginBottom: 12
                }
            }, 'Backend Connection'),
            h('div', {
                className: 'flex items-center gap-2'
            }, h('div', {
                className: `dot dot-${connected ? 'green' : 'red'}`
            }), h('span', {
                className: 'text-sm'
            }, connected ? `Connected to ${API}` : 'Not connected')),
            h('button', {
                className: 'btn btn-secondary btn-sm',
                style: {
                    marginTop: 12
                },
                onclick: checkBackend
            }, 'Test Connection')
        ),
        h('div', {
                className: 'card'
            },
            h('div', {
                style: {
                    fontWeight: 600,
                    marginBottom: 10
                }
            }, 'Start Command'),
            h('div', {
                    style: {
                        background: 'var(--surf3)',
                        borderRadius: 8,
                        padding: '12px',
                        fontFamily: 'monospace',
                        fontSize: 11,
                        color: 'var(--accent)',
                        lineHeight: 1.9
                    }
                },
                'cd C:\\path\\to\\framevault\\backend', h('br', {}), 'uvicorn main:app --host 0.0.0.0 --port 8000 --reload'
        
        ),
        h('div', {
                className: 'card'
            },
            h('div', {
                style: {
                    fontWeight: 600,
                    marginBottom: 8
                }
            }, 'About'),
            h('div', {
                className: 'text-sm text-muted'
            }, 'ClipCache v1.0.0 \u00B7 pHash engine \u00B7 OpenCV \u00B7 SQLite')
        )
    );
}

function Toast() {
    const {
        toast
    } = gs();
    if (!toast) return h('div', {
        style: {
            display: 'none'
        }
    });
    const bg = toast.type === 'warn' ? 'var(--warn)' : 'var(--success)';
    return h('div', {
        style: {
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            background: bg,
            color: '#0a0a0f',
            padding: '11px 18px',
            borderRadius: '10px',
            fontWeight: 600,
            fontSize: 13,
            boxShadow: '0 4px 20px rgba(0,0,0,.4)',
            zIndex: 300
        }
    }, toast.msg);
}

// ── Analysis Progress Overlay ────────────────────────────────────────────────

function AnalysisProgressOverlay() {
    const {
        analyzing,
        analysisProgress
    } = gs();
    
    if (!analyzing || !analysisProgress) {
        return h('div', { style: { display: 'none' } });
    }
    
    const status = analysisProgress.status || 'idle';
    const percent = analysisProgress.percent || 0;
    const currentFile = analysisProgress.current_file || '';
    const processed = analysisProgress.processed || 0;
    const total = analysisProgress.total || 0;
    
    let statusLabel = '';
    if (status === 'extracting') {
        statusLabel = '📽️ Extracting frames from final ad...';
    } else if (status === 'matching') {
        statusLabel = `🔍 Matching ({processed} / {total}) files...`;
    } else {
        statusLabel = '⏳ Processing...';
    }
    
    return h('div', {
            className: 'overlay',
            style: {
                background: 'rgba(0,0,0,0.8)',
                display: analyzing ? 'flex' : 'none',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 500
            }
        },
        h('div', {
                style: {
                    background: 'var(--surf1)',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '32px',
                    width: 'clamp(280px, 90vw, 500px)',
                    boxShadow: '0 20px 60px rgba(0,0,0,0.5)'
                }
            },
            h('div', {
                style: {
                    fontSize: 18,
                    fontWeight: 600,
                    marginBottom: 8,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                }
            }, '🎬 Analyzing Ad...'),
            h('div', {
                style: {
                    fontSize: 12,
                    color: 'var(--muted)',
                    marginBottom: 20
                }
            }, statusLabel.replace('{processed}', processed).replace('{total}', total)),
            
            // Progress bar
            h('div', {
                style: {
                    marginBottom: 16
                }
            },
                h('div', {
                    style: {
                        background: 'var(--surf2)',
                        height: '8px',
                        borderRadius: '4px',
                        overflow: 'hidden',
                        marginBottom: 8
                    }
                },
                    h('div', {
                        style: {
                            height: '100%',
                            width: percent + '%',
                            background: 'linear-gradient(90deg, var(--accent), #00ff00)',
                            transition: 'width 0.3s ease',
                            borderRadius: '4px'
                        }
                    })
                )
            ),
            
            // Cancel button
            h('button', {
                className: 'btn btn-secondary',
                style: {
                    width: '100%'
                },
                onclick: async () => {
                    const {
                        selectedProject
                    } = gs();
                    if (selectedProject && confirm('Stop analysis?')) {
                        try {
                            await api(`/projects/${selectedProject.id}/analyze/cancel`, {
                                method: 'POST'
                            });
                            setState({
                                analyzing: false,
                                analysisProgress: null
                            });
                            showToast('Analysis cancelled');
                        } catch (e) {
                            showToast(e.message, 'warn');
                        }
                    }
                }
            }, '⊗ Cancel')
        )
    );
}

// ── App shell ────────────────────────────────────────────────────────────────

function App() {
    // Regular dashboard
    const {
        page,
        connected,
        showNewProject,
        showAnalyze,
        selectedProject,
        previewFile
    } = gs();
    const navItems = [{
        id: 'dashboard',
        icon: '\u2B1B',
        label: 'Dashboard'
    }, {
        id: 'projects-list',
        icon: '\uD83D\uDCC1',
        label: 'Projects'
    }, {
        id: 'reports',
        icon: '\uD83D\uDCCA',
        label: 'Reports'
    }, {
        id: 'settings',
        icon: '\u2699\uFE0F',
        label: 'Settings'
    }];
    const activePage = selectedProject ? 'project' : page;

    let pageContent;
    if (activePage === 'project') pageContent = ProjectPage();
    else if (page === 'projects-list') {
        pageContent = h('div', {},
            h('div', {
                className: 'flex justify-between items-center mb-4'
            }, h('div', {
                className: 'section-title'
            }, 'All Projects'), h('button', {
                className: 'btn btn-primary btn-sm',
                onclick: () => setState({
                    showNewProject: true
                })
            }, '\uFF0B New Project')),
            ...gs().projects.map(p => h('div', {
                    className: 'card flex justify-between items-center'
                },
                h('div', {}, h('div', {
                    style: {
                        fontWeight: 600
                    }
                }, p.name), h('div', {
                    className: 'text-xs text-muted mt-2'
                }, p.raw_folder), h('div', {
                    style: {
                        marginTop: 8
                    }
                }, Badge(p.status === 'analyzed' ? 'used' : p.status === 'analyzing' ? 'review' : 'unanalyzed'))),
                h('button', {
                    className: 'btn btn-primary btn-sm',
                    onclick: () => {
                        const isAnalyzing = p.status === 'analyzing';
                        setState({
                            selectedProject: p,
                            page: 'project',
                            fileFilter: 'all',
                            filePage: 1,
                            projectTab: 'files',
                            analyzing: isAnalyzing
                        });
                        if (isAnalyzing) startAnalysisPoll(p.id);
                        loadFileStats();
                        loadFiles();
                        loadTrash();
                    }
                }, 'Open \u2192')
            ))
        );
    } else if (page === 'reports') pageContent = ReportsPage();
    else if (page === 'settings') pageContent = SettingsPage();
    else pageContent = DashboardPage();

    return h('div', {
            className: 'app'
        },
        h('div', {
                className: 'sidebar'
            },
            h('div', {
                className: 'logo'
            }, h('div', {
                className: 'logo-name'
            }, 'ClipCache'), h('div', {
                className: 'logo-sub'
            }, 'Ad Media Manager')),
            ...navItems.map(n => h('div', {
                className: `nav-item ${page === n.id && !selectedProject ? 'active' : ''}`,
                onclick: () => setState({
                    selectedProject: null,
                    page: n.id,
                    files: [],
                    fileStats: {}
                })
            }, h('span', {
                style: {
                    fontSize: 14,
                    width: 20,
                    textAlign: 'center'
                }
            }, n.icon), n.label)),
            h('div', {
                    className: 'sidebar-bottom'
                },
                h('div', {
                    className: 'flex items-center gap-2',
                    style: {
                        marginBottom: 4
                    }
                }, h('div', {
                    className: `dot dot-${connected === null ? 'yellow' : connected ? 'green' : 'red'}`
                }), h('span', {
                    className: 'version'
                }, connected === null ? 'Connecting\u2026' : connected ? 'Backend connected' : 'Backend offline')),
                h('div', {
                    className: 'version'
                }, 'v1.0.0')
            )
        ),
        h('div', {
                className: 'main'
            },
            h('div', {
                className: 'topbar'
            }, 
                h('div', { className: 'page-title' }, selectedProject ? selectedProject.name : page.charAt(0).toUpperCase() + page.replace('-list', 's').slice(1))
            ),
            h('div', {
                    className: 'content'
                },
                connected === false ? h('div', {
                    className: 'alert alert-warn mb-4'
                }, '\u26A0\uFE0F Backend offline. Run: ', h('code', {}, 'uvicorn main:app --host 0.0.0.0 --port 8000 --reload', ' in the backend folder')) : null,
                pageContent
            )
        ),
        showNewProject ? NewProjectModal() : null,
        showAnalyze ? AnalyzeModal() : null,
        previewFile ? PreviewModal() : null,
        // AnalysisProgressOverlay(),
        Toast()
    );
}
