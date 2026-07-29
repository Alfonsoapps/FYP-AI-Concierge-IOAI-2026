/* ============================================================
   Chat Module - Side-by-side layout version
   
   Manages conversation in the left panel with message bubbles.
   Handles TTS playback and avatar state coordination.
   Persists conversation history (with file metadata) in localStorage.
   ============================================================ */

const ChatManager = {
    history: [],
    selectedFile: null,
    elements: {
        input: null,
        sendBtn: null,
        messagesContainer: null,
        attachBtn: null,
        fileInput: null,
        filePreview: null,
        filePreviewName: null,
        fileRemoveBtn: null,
    },

    isWaiting: false,
    isSpeaking: false,
    _ttsAbortController: null,
    _currentBlobUrl: null,
    _activityTimer: null,
    clientId: null,
    audioPlayer: null,

    // localStorage key for persisting chat history
    _HISTORY_KEY: 'ioai-chat-history',
    _MAX_HISTORY: 100,  // max messages to persist

    // ============================================================
    // init()
    // ============================================================
    init() {
        this.elements.input = document.getElementById('chat-input');
        this.elements.sendBtn = document.getElementById('send-btn');
        this.elements.messagesContainer = document.getElementById('chat-messages');

        // Keep one anonymous identifier per browser so multiple tabs from the
        // same person are counted once in the active-user metric.
        this.clientId = localStorage.getItem('ioai-user-id');
        const validClientId = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;
        if (!this.clientId || !validClientId.test(this.clientId)) {
            this.clientId = (window.crypto && window.crypto.randomUUID)
                ? window.crypto.randomUUID()
                : `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
            localStorage.setItem('ioai-user-id', this.clientId);
        }

        this._sendActivity();
        this._activityTimer = window.setInterval(
            () => this._sendActivity(),
            30000
        );
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) this._sendActivity();
        });

        // Audio player
        this.audioPlayer = new Audio();
        this.audioPlayer.addEventListener('play', () => this._onPlayStart());
        this.audioPlayer.addEventListener('ended', () => this._onPlayEnd());
        this.audioPlayer.addEventListener('pause', () => this._onPlayPause());
        this.audioPlayer.addEventListener('error', () => this._onPlayError());

        // Mobile audio unlock: play a silent audio on first user interaction
        // This "unlocks" the audio context so future programmatic plays work
        const unlockAudio = () => {
            this.audioPlayer.src = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAABhgFCnMkAAAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAABhgFCnMkAAAAAAAAAAAAAAAAA';
            this.audioPlayer.play().then(() => {
                this.audioPlayer.pause();
                this.audioPlayer.currentTime = 0;
                this.audioPlayer.src = '';
                console.log('[Chat] ✓ Mobile audio unlocked');
            }).catch(() => {});
            document.removeEventListener('touchstart', unlockAudio);
            document.removeEventListener('click', unlockAudio);
        };
        document.addEventListener('touchstart', unlockAudio, { once: true });
        document.addEventListener('click', unlockAudio, { once: true });

        // Input events
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // File attachment
        this.elements.attachBtn = document.getElementById('attach-btn');
        this.elements.fileInput = document.getElementById('file-input');
        this.elements.filePreview = document.getElementById('file-preview');
        this.elements.filePreviewName = document.getElementById('file-preview-name');
        this.elements.fileRemoveBtn = document.getElementById('file-remove-btn');

        if (this.elements.attachBtn && this.elements.fileInput) {
            this.elements.attachBtn.addEventListener('click', () => {
                this.elements.fileInput.click();
            });

            this.elements.fileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    // Validate file size client-side (10 MB)
                    if (file.size > 10 * 1024 * 1024) {
                        this._showToast('File too large. Maximum size is 10 MB.', 'error');
                        this.elements.fileInput.value = '';
                        return;
                    }
                    this.selectedFile = file;
                    this._showFilePreview(file);
                    this.elements.attachBtn.classList.add('has-file');
                    console.log('[Chat] File attached:', file.name, '(' + (file.size / 1024).toFixed(1) + ' KB)');
                }
            });

            this.elements.fileRemoveBtn.addEventListener('click', () => {
                this._removeAttachedFile();
            });
        }

        // Backward compat: hidden elements
        this.elements.responseBubble = document.getElementById('response-bubble');
        this.elements.responseText = document.getElementById('response-text');
        this.elements.chatHistory = document.getElementById('chat-history');
        this.elements.historyToggle = document.getElementById('history-toggle');

        console.log('[Chat] ✓ Initialized (side-by-side layout)');

        // Restore persisted chat history
        this._loadHistory();
    },

    // Refresh this tab's activity without inflating the query counter.
    async _sendActivity() {
        if (!this.clientId || document.hidden) return;

        try {
            await fetch('/chat/activity', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this.clientId }),
                cache: 'no-store',
                keepalive: true,
            });
        } catch (error) {
            // Analytics must never interrupt the participant's chat session.
            console.debug('[Chat] Activity heartbeat failed:', error.message);
        }
    },

    // ============================================================
    // sendMessage()
    // ============================================================
    async sendMessage() {
        const message = this.elements.input.value.trim();
        if (!message || this.isWaiting) return;

        this.elements.input.value = '';
        this.interruptSpeech();

        if (typeof VoiceManager !== 'undefined' && VoiceManager.isListening) {
            VoiceManager.abort();
        }

        // Build display text (include filename if attached)
        let displayText = message;
        const attachedFile = this.selectedFile;
        let fileMeta = null;
        if (attachedFile) {
            displayText = message; // We'll render the file badge separately
            const ext = attachedFile.name.split('.').pop().toLowerCase();
            fileMeta = {
                filename: attachedFile.name,
                fileType: ext,
                size: attachedFile.size,
                timestamp: new Date().toISOString(),
            };
        }

        // Add user message bubble (with file badge if applicable)
        this._addMessage('user', displayText, fileMeta);
        this.history.push({
            role: 'user',
            text: message,
            file: fileMeta,
            timestamp: new Date().toISOString(),
        });
        // Notify conversation manager
        if (typeof ConversationManager !== 'undefined') {
            ConversationManager.addMessage('user', message, fileMeta);
        }

        // Clear the attached file from the UI
        this._removeAttachedFile();

        // Show typing/analysis indicator
        const hasFile = !!attachedFile;
        const typingEl = hasFile ? this._addAnalysisIndicator(fileMeta) : this._addTypingIndicator();
        this._setAvatarThinking(true);
        this.setWaiting(true);

        console.log('[Chat] → Sending:', message.substring(0, 50), attachedFile ? '+ file: ' + attachedFile.name : '');

        try {
            let response;

            if (attachedFile) {
                // Use multipart/form-data endpoint when file is attached
                const formData = new FormData();
                formData.append('message', message);
                formData.append('file', attachedFile);

                // Show upload progress via XHR
                response = await this._uploadWithProgress(formData, typingEl);
            } else {
                // Standard JSON endpoint for text-only
                response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-User-ID': this.clientId,
                    },
                    body: JSON.stringify({ message: message }),
                });
            }

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || `Request failed (${response.status})`);
            }

            const data = await response.json();
            const reply = data.reply;

            // Remove typing indicator, add bot message
            typingEl.remove();
            this._addMessage('bot', reply);
            this.history.push({ role: 'bot', text: reply, timestamp: new Date().toISOString() });
            // Notify conversation manager
            if (typeof ConversationManager !== 'undefined') {
                ConversationManager.addMessage('bot', reply);
            }
            this._setAvatarThinking(false);

            if (hasFile) {
                // Don't show success toast if guardrails blocked the message
                const isBlocked = reply.includes("I'm sorry, I'm not able to help with that");
                if (!isBlocked) {
                    this._showToast('Document analysed successfully', 'success');
                }
            }

            console.log('[Chat] ← Response (%d chars)', reply.length);

            // Speak
            this._speakResponse(reply);

        } catch (error) {
            typingEl.remove();
            this._addMessage('bot', 'Sorry, something went wrong. Please try again.');
            this._showToast(error.message, 'error');
            this._setAvatarThinking(false);
            console.error('[Chat] Error:', error.message);
        }

        this.setWaiting(false);
    },

    // ============================================================
    // MESSAGE RENDERING
    // ============================================================
    _addMessage(role, text, fileMeta) {
        const container = this.elements.messagesContainer;
        const msgEl = document.createElement('div');
        msgEl.className = 'msg ' + role;

        let html = '';

        // Render file attachment badge (above message text)
        if (fileMeta && fileMeta.filename) {
            const icon = this._getFileIcon(fileMeta.fileType);
            html += '<div class="msg-file-badge">' +
                '<span class="msg-file-icon">' + icon + '</span>' +
                '<span class="msg-file-name">' + this._escapeHtml(fileMeta.filename) + '</span>' +
                '<span class="msg-file-type">' + (fileMeta.fileType || '').toUpperCase() + '</span>' +
                '</div>';
        }

        html += '<div class="msg-content">' + this._escapeHtml(text) + '</div>';
        msgEl.innerHTML = html;
        container.appendChild(msgEl);
        container.scrollTop = container.scrollHeight;
        return msgEl;
    },

    _getFileIcon(fileType) {
        const icons = {
            pdf: '📄', doc: '📝', docx: '📝', txt: '📃',
            png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', webp: '🖼️',
        };
        return icons[fileType] || '📎';
    },

    _addTypingIndicator() {
        const container = this.elements.messagesContainer;
        const msgEl = document.createElement('div');
        msgEl.className = 'msg bot';
        msgEl.innerHTML = '<div class="msg-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>';
        container.appendChild(msgEl);
        container.scrollTop = container.scrollHeight;
        return msgEl;
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    // ============================================================
    // TTS PLAYBACK
    // ============================================================
    async _speakResponse(text) {
        if (this._ttsAbortController) this._ttsAbortController.abort();
        this._ttsAbortController = new AbortController();

        try {
            const response = await fetch('/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
                signal: this._ttsAbortController.signal,
            });

            if (!response.ok) throw new Error('TTS failed');

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            this._cleanupBlobUrl();
            this._currentBlobUrl = url;

            this.audioPlayer.src = url;
            await this.audioPlayer.play();
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.warn('[Chat] TTS failed:', error.message);
            }
        } finally {
            this._ttsAbortController = null;
        }
    },

    // ============================================================
    // AUDIO EVENTS
    // ============================================================
    _onPlayStart() {
        this.isSpeaking = true;
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) AvatarManager.startSpeaking();
        const status = document.getElementById('avatar-status');
        if (status) {
            status.innerHTML = '<span class="status-dot speaking"></span> Speaking...';
            status.classList.add('visible');
        }
    },

    _onPlayEnd() { this._finishSpeaking(); },
    _onPlayPause() {
        if (this.audioPlayer.currentTime > 0 && !this.audioPlayer.ended) this._finishSpeaking();
    },
    _onPlayError() { this._finishSpeaking(); },

    _finishSpeaking() {
        this.isSpeaking = false;
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) AvatarManager.stopSpeaking();
        if (!this.isWaiting) {
            const status = document.getElementById('avatar-status');
            if (status) status.classList.remove('visible');
        }
        this._cleanupBlobUrl();
    },

    // ============================================================
    // INTERRUPTION
    // ============================================================
    interruptSpeech() {
        if (this._ttsAbortController) { this._ttsAbortController.abort(); this._ttsAbortController = null; }
        if (this.audioPlayer && !this.audioPlayer.paused) {
            this.audioPlayer.pause();
            this.audioPlayer.currentTime = 0;
        }
        if (this.isSpeaking) {
            this.isSpeaking = false;
            if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) AvatarManager.stopSpeaking();
        }
        this._cleanupBlobUrl();
    },

    stopSpeech() { this.interruptSpeech(); },

    _cleanupBlobUrl() {
        if (this._currentBlobUrl) { URL.revokeObjectURL(this._currentBlobUrl); this._currentBlobUrl = null; }
    },

    // ============================================================
    // FILE ATTACHMENT
    // ============================================================
    _removeAttachedFile() {
        this.selectedFile = null;
        if (this.elements.fileInput) this.elements.fileInput.value = '';
        if (this.elements.filePreview) this.elements.filePreview.classList.add('hidden');
        if (this.elements.attachBtn) this.elements.attachBtn.classList.remove('has-file');
        console.log('[Chat] File attachment removed');
    },

    _showFilePreview(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        const icon = this._getFileIcon(ext);
        const sizeStr = file.size < 1024 * 1024
            ? (file.size / 1024).toFixed(0) + ' KB'
            : (file.size / (1024 * 1024)).toFixed(1) + ' MB';

        const nameEl = document.getElementById('file-preview-name');
        const preview = this.elements.filePreview;

        if (nameEl) {
            nameEl.innerHTML = '<span class="fp-icon">' + icon + '</span>' +
                '<span class="fp-details">' +
                '<span class="fp-filename">' + this._escapeHtml(file.name) + '</span>' +
                '<span class="fp-meta">' + ext.toUpperCase() + ' · ' + sizeStr + '</span>' +
                '</span>';
        }
        if (preview) preview.classList.remove('hidden');
    },

    _addAnalysisIndicator(fileMeta) {
        const container = this.elements.messagesContainer;
        const msgEl = document.createElement('div');
        msgEl.className = 'msg bot';
        const icon = fileMeta ? this._getFileIcon(fileMeta.fileType) : '📄';
        const fname = fileMeta ? this._escapeHtml(fileMeta.filename) : 'document';
        msgEl.innerHTML =
            '<div class="msg-content">' +
            '<div class="analysis-indicator">' +
            '<div class="analysis-spinner"></div>' +
            '<div class="analysis-text">' +
            '<span class="analysis-title">Analysing ' + icon + ' ' + fname + '</span>' +
            '<span class="analysis-sub">Extracting content and searching knowledge base…</span>' +
            '</div>' +
            '</div>' +
            '<div class="analysis-progress"><div class="analysis-progress-bar"></div></div>' +
            '</div>';
        container.appendChild(msgEl);
        container.scrollTop = container.scrollHeight;
        return msgEl;
    },

    _uploadWithProgress(formData, indicatorEl) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const progressBar = indicatorEl.querySelector('.analysis-progress-bar');
            const analysisText = indicatorEl.querySelector('.analysis-sub');

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && progressBar) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = pct + '%';
                    if (pct >= 100 && analysisText) {
                        analysisText.textContent = 'Upload complete. AI is reading your document…';
                    }
                }
            });

            xhr.addEventListener('load', () => {
                if (progressBar) progressBar.style.width = '100%';
                if (xhr.status >= 200 && xhr.status < 300) {
                    // Wrap in a Response-like object for consistency
                    resolve({
                        ok: true,
                        status: xhr.status,
                        json: () => Promise.resolve(JSON.parse(xhr.responseText)),
                    });
                } else {
                    let detail = `Request failed (${xhr.status})`;
                    try {
                        const err = JSON.parse(xhr.responseText);
                        if (err.detail) detail = err.detail;
                    } catch (_) {}
                    resolve({ ok: false, status: xhr.status, json: () => Promise.resolve({ detail }) });
                }
            });

            xhr.addEventListener('error', () => {
                reject(new Error('Network error — could not upload file.'));
            });

            xhr.addEventListener('timeout', () => {
                reject(new Error('Upload timed out. Please try a smaller file.'));
            });

            xhr.open('POST', '/chat/upload');
            xhr.setRequestHeader('X-User-ID', this.clientId);
            xhr.timeout = 120000; // 2 minutes
            xhr.send(formData);
        });
    },

    // ============================================================
    // TOAST NOTIFICATIONS
    // ============================================================
    _showToast(message, type) {
        // type: 'success' | 'error' | 'info'
        const existing = document.querySelector('.chat-toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'chat-toast chat-toast-' + type;

        const icons = { success: '✓', error: '✕', info: 'ℹ' };
        toast.innerHTML =
            '<span class="toast-icon">' + (icons[type] || '') + '</span>' +
            '<span class="toast-text">' + this._escapeHtml(message) + '</span>';

        const panel = document.getElementById('chat-panel');
        if (panel) {
            panel.appendChild(toast);
        } else {
            document.body.appendChild(toast);
        }

        // Auto-dismiss
        setTimeout(() => {
            toast.classList.add('toast-fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    // ============================================================
    // HISTORY PERSISTENCE
    // ============================================================
    _saveHistory() {
        // History is now managed by ConversationManager — no-op here
        // (ConversationManager.addMessage is called directly)
    },

    _loadHistory() {
        // ConversationManager handles loading on init and switchTo
        // Check if ConversationManager has already loaded messages
        if (typeof ConversationManager !== 'undefined' && ConversationManager.activeId) {
            const conv = ConversationManager.getActive();
            if (conv && conv.messages.length > 0) {
                const container = this.elements.messagesContainer;
                container.innerHTML = '';
                for (const msg of conv.messages) {
                    this._addMessage(msg.role, msg.text, msg.file || null);
                }
                this.history = conv.messages.slice();
                container.scrollTop = container.scrollHeight;
                console.log('[Chat] Loaded %d messages from active conversation', conv.messages.length);
            }
        }
    },

    clearHistory() {
        this.history = [];
        const container = this.elements.messagesContainer;
        container.innerHTML = '';
        // Re-add welcome message
        this._addMessage('bot', 'Welcome to IOAI 2027! I\'m your friendly guide, here to assist you with any questions about attending this international event in Singapore.\n\nWhat would you like to know first?');
        console.log('[Chat] History cleared');
    },

    // ============================================================
    // AVATAR & UI STATE
    // ============================================================
    _setAvatarThinking(thinking) {
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) AvatarManager.setThinking(thinking);
    },

    setWaiting(waiting) {
        this.isWaiting = waiting;
        this.elements.input.disabled = waiting;
        this.elements.sendBtn.disabled = waiting;
        this.elements.input.placeholder = waiting ? 'Waiting for response...' : 'Ask me anything about IOAI 2027...';
    },

    // Backward compat methods (used by voice module)
    showResponse(text, isError) {
        this._addMessage('bot', text);
    },

    showTypingIndicator() { /* handled inline now */ },
    addToHistory(role, text) { /* handled inline now */ },
};
