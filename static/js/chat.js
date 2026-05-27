/* ============================================================
   Chat Module - Side-by-side layout version
   
   Manages conversation in the left panel with message bubbles.
   Handles TTS playback and avatar state coordination.
   ============================================================ */

const ChatManager = {
    history: [],
    elements: {
        input: null,
        sendBtn: null,
        messagesContainer: null,
    },

    isWaiting: false,
    isSpeaking: false,
    _ttsAbortController: null,
    _currentBlobUrl: null,
    audioPlayer: null,

    // ============================================================
    // init()
    // ============================================================
    init() {
        this.elements.input = document.getElementById('chat-input');
        this.elements.sendBtn = document.getElementById('send-btn');
        this.elements.messagesContainer = document.getElementById('chat-messages');

        // Audio player
        this.audioPlayer = new Audio();
        this.audioPlayer.addEventListener('play', () => this._onPlayStart());
        this.audioPlayer.addEventListener('ended', () => this._onPlayEnd());
        this.audioPlayer.addEventListener('pause', () => this._onPlayPause());
        this.audioPlayer.addEventListener('error', () => this._onPlayError());

        // Input events
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Backward compat: hidden elements
        this.elements.responseBubble = document.getElementById('response-bubble');
        this.elements.responseText = document.getElementById('response-text');
        this.elements.chatHistory = document.getElementById('chat-history');
        this.elements.historyToggle = document.getElementById('history-toggle');

        console.log('[Chat] ✓ Initialized (side-by-side layout)');
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

        // Add user message bubble
        this._addMessage('user', message);
        this.history.push({ role: 'user', text: message, timestamp: Date.now() });

        // Show typing indicator
        const typingEl = this._addTypingIndicator();
        this._setAvatarThinking(true);
        this.setWaiting(true);

        console.log('[Chat] → Sending:', message.substring(0, 50));

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message }),
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || `Request failed (${response.status})`);
            }

            const data = await response.json();
            const reply = data.reply;

            // Remove typing indicator, add bot message
            typingEl.remove();
            this._addMessage('bot', reply);
            this.history.push({ role: 'bot', text: reply, timestamp: Date.now() });
            this._setAvatarThinking(false);

            console.log('[Chat] ← Response (%d chars)', reply.length);

            // Speak
            this._speakResponse(reply);

        } catch (error) {
            typingEl.remove();
            this._addMessage('bot', 'Sorry, something went wrong: ' + error.message);
            this._setAvatarThinking(false);
            console.error('[Chat] Error:', error.message);
        }

        this.setWaiting(false);
    },

    // ============================================================
    // MESSAGE RENDERING
    // ============================================================
    _addMessage(role, text) {
        const container = this.elements.messagesContainer;
        const msgEl = document.createElement('div');
        msgEl.className = 'msg ' + role;
        msgEl.innerHTML = '<div class="msg-content">' + this._escapeHtml(text) + '</div>';
        container.appendChild(msgEl);
        container.scrollTop = container.scrollHeight;
        return msgEl;
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
