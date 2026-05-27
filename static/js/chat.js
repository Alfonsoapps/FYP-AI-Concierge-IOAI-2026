/* ============================================================
   Chat Module - Message handling, TTS playback, state management
   
   Manages the full conversation cycle:
   - User input (typed or voice)
   - AI response fetching
   - TTS audio playback
   - Avatar state coordination
   - Interruption handling
   
   State machine: IDLE → WAITING → SPEAKING → IDLE
   Interruptions are handled cleanly at any point.
   ============================================================ */

const ChatManager = {
    history: [],

    elements: {
        input: null,
        sendBtn: null,
        responseBubble: null,
        responseText: null,
        chatHistory: null,
        historyToggle: null,
    },

    // State
    isWaiting: false,
    isSpeaking: false,
    _ttsAbortController: null,  // Allows canceling in-flight TTS requests
    _currentBlobUrl: null,      // Track blob URL for cleanup

    // Audio player
    audioPlayer: null,

    // ============================================================
    // init()
    // ============================================================
    init() {
        this.elements.input = document.getElementById('chat-input');
        this.elements.sendBtn = document.getElementById('send-btn');
        this.elements.responseBubble = document.getElementById('response-bubble');
        this.elements.responseText = document.getElementById('response-text');
        this.elements.chatHistory = document.getElementById('chat-history');
        this.elements.historyToggle = document.getElementById('history-toggle');

        // Audio player with event handlers
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

        // History toggle
        this.elements.historyToggle.addEventListener('click', () => {
            this.elements.chatHistory.classList.toggle('visible');
        });

        console.log('[Chat] ✓ Initialized');
    },

    // ============================================================
    // sendMessage() - Main conversation entry point
    // Handles both typed and voice input.
    // ============================================================
    async sendMessage() {
        const message = this.elements.input.value.trim();
        if (!message) return;

        // If already waiting, ignore (prevents double-send)
        if (this.isWaiting) return;

        // Clear input immediately
        this.elements.input.value = '';

        // Interrupt any current speech/TTS
        this.interruptSpeech();

        // Stop listening if active (voice sent the message)
        if (typeof VoiceManager !== 'undefined' && VoiceManager.isListening) {
            VoiceManager.abort();
        }

        // Add to history
        this.addToHistory('user', message);

        // Show thinking state
        this.showTypingIndicator();
        this._setAvatarThinking(true);
        this.setWaiting(true);

        console.log('[Chat] → Sending:', message.substring(0, 50));

        try {
            // Fetch AI response
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

            // Display response
            this.showResponse(reply);
            this.addToHistory('bot', reply);
            this._setAvatarThinking(false);

            console.log('[Chat] ← Response received (%d chars)', reply.length);

            // Speak the response (non-blocking)
            this._speakResponse(reply);

        } catch (error) {
            console.error('[Chat] Error:', error.message);
            this.showResponse('Sorry, something went wrong: ' + error.message, true);
            this._setAvatarThinking(false);
        }

        this.setWaiting(false);
    },

    // ============================================================
    // TTS PLAYBACK
    // ============================================================
    async _speakResponse(text) {
        // Cancel any previous in-flight TTS request
        if (this._ttsAbortController) {
            this._ttsAbortController.abort();
        }
        this._ttsAbortController = new AbortController();

        try {
            const response = await fetch('/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
                signal: this._ttsAbortController.signal,
            });

            if (!response.ok) {
                throw new Error('TTS request failed');
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);

            // Clean up previous blob
            this._cleanupBlobUrl();
            this._currentBlobUrl = url;

            // Play audio
            this.audioPlayer.src = url;
            await this.audioPlayer.play();

            console.log('[Chat] 🔊 TTS playing');

        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('[Chat] TTS request canceled (interrupted)');
            } else {
                console.warn('[Chat] TTS failed (non-fatal):', error.message);
            }
        } finally {
            this._ttsAbortController = null;
        }
    },

    // ============================================================
    // AUDIO PLAYBACK EVENTS
    // ============================================================
    _onPlayStart() {
        this.isSpeaking = true;

        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.startSpeaking();
        }

        const status = document.getElementById('avatar-status');
        if (status) {
            status.innerHTML = '<span class="status-dot speaking"></span> Speaking...';
            status.classList.add('visible');
        }

        console.log('[Chat] 🔊 → Speaking state');
    },

    _onPlayEnd() {
        this._finishSpeaking();
        console.log('[Chat] 🔊 → Idle state (ended)');
    },

    _onPlayPause() {
        // Only finish if we're actually done (not just interrupted mid-play)
        if (this.audioPlayer.currentTime > 0 && !this.audioPlayer.ended) {
            // Paused mid-play (interruption)
            this._finishSpeaking();
            console.log('[Chat] 🔊 → Idle state (interrupted)');
        }
    },

    _onPlayError() {
        this._finishSpeaking();
        console.warn('[Chat] 🔊 Audio error');
    },

    _finishSpeaking() {
        this.isSpeaking = false;

        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.stopSpeaking();
        }

        // Hide status unless something else is active
        if (!this.isWaiting) {
            const status = document.getElementById('avatar-status');
            if (status) status.classList.remove('visible');
        }

        this._cleanupBlobUrl();
    },

    // ============================================================
    // INTERRUPTION HANDLING
    // Cleanly stops all speech-related activity
    // ============================================================
    interruptSpeech() {
        // Cancel in-flight TTS request
        if (this._ttsAbortController) {
            this._ttsAbortController.abort();
            this._ttsAbortController = null;
        }

        // Stop audio playback
        if (this.audioPlayer && !this.audioPlayer.paused) {
            this.audioPlayer.pause();
            this.audioPlayer.currentTime = 0;
        }

        // Reset state
        if (this.isSpeaking) {
            this.isSpeaking = false;
            if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
                AvatarManager.stopSpeaking();
            }
        }

        this._cleanupBlobUrl();
    },

    // Alias for backward compatibility
    stopSpeech() {
        this.interruptSpeech();
    },

    // ============================================================
    // MEMORY MANAGEMENT
    // ============================================================
    _cleanupBlobUrl() {
        if (this._currentBlobUrl) {
            URL.revokeObjectURL(this._currentBlobUrl);
            this._currentBlobUrl = null;
        }
    },

    // ============================================================
    // AVATAR COORDINATION
    // ============================================================
    _setAvatarThinking(thinking) {
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.setThinking(thinking);
        }
    },

    // ============================================================
    // UI METHODS
    // ============================================================
    showResponse(text, isError = false) {
        const bubble = this.elements.responseBubble;
        const textEl = this.elements.responseText;
        textEl.textContent = text;
        textEl.style.color = isError ? '#ef4444' : 'var(--text-primary)';
        bubble.classList.add('visible');
    },

    showTypingIndicator() {
        const textEl = this.elements.responseText;
        textEl.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
        this.elements.responseBubble.classList.add('visible');
    },

    addToHistory(role, text) {
        this.history.push({ role, text, timestamp: Date.now() });

        const historyEl = this.elements.chatHistory;
        const msgEl = document.createElement('div');
        msgEl.className = 'history-message ' + role;
        msgEl.textContent = text.length > 200 ? text.substring(0, 200) + '...' : text;
        historyEl.appendChild(msgEl);
        historyEl.scrollTop = historyEl.scrollHeight;
    },

    setWaiting(waiting) {
        this.isWaiting = waiting;
        this.elements.input.disabled = waiting;
        this.elements.sendBtn.disabled = waiting;
        this.elements.input.placeholder = waiting
            ? 'Waiting for response...'
            : 'Ask me anything about IOAI 2027...';
    },
};
