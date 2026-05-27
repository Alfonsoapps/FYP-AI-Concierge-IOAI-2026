/* ============================================================
   Voice Module - Speech-to-Text (Web Speech API)
   
   Manages microphone input with proper state handling to prevent:
   - Overlapping listening sessions
   - Stuck listening states
   - Conflicts with TTS playback
   - Rapid-click issues
   
   State machine: IDLE → LISTENING → PROCESSING → IDLE
   ============================================================ */

const VoiceManager = {
    recognition: null,
    isListening: false,
    isSupported: false,
    _isProcessing: false,  // True while sending transcript (prevents re-entry)
    _restartBlocked: false, // Prevents rapid restart

    elements: { micBtn: null },

    // ============================================================
    // init()
    // ============================================================
    init() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.warn('[Voice] Speech Recognition not supported.');
            this.isSupported = false;
            this._hideMicButton();
            return;
        }

        this.isSupported = true;
        this.recognition = new SpeechRecognition();
        this.recognition.lang = 'en-US';
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 1;

        this.recognition.onstart = () => this._onStart();
        this.recognition.onresult = (e) => this._onResult(e);
        this.recognition.onerror = (e) => this._onError(e);
        this.recognition.onend = () => this._onEnd();

        this.elements.micBtn = document.getElementById('mic-btn');
        if (this.elements.micBtn) {
            this.elements.micBtn.addEventListener('click', () => this.toggle());
        }

        console.log('[Voice] ✓ Initialized');
    },

    // ============================================================
    // toggle() - Main interaction point
    // ============================================================
    toggle() {
        // Prevent rapid double-clicks
        if (this._restartBlocked) return;

        if (this.isListening) {
            this.stop();
        } else {
            this.start();
        }
    },

    // ============================================================
    // start() - Begin listening
    // ============================================================
    start() {
        if (!this.isSupported || !this.recognition) return;
        if (this.isListening || this._isProcessing) return;

        // Stop any playing TTS first (prevents mic picking up speaker audio)
        if (typeof ChatManager !== 'undefined') {
            ChatManager.stopSpeech();
        }

        // Brief cooldown to prevent rapid restart issues
        this._restartBlocked = true;
        setTimeout(() => { this._restartBlocked = false; }, 300);

        try {
            this.recognition.start();
            console.log('[Voice] 🎤 Starting...');
        } catch (e) {
            console.warn('[Voice] Start failed:', e.message);
            this._resetState();
        }
    },

    // ============================================================
    // stop() - Stop listening gracefully
    // ============================================================
    stop() {
        if (!this.recognition) return;

        try {
            this.recognition.stop();
        } catch (e) { /* already stopped */ }

        console.log('[Voice] 🎤 Stop requested');
    },

    // ============================================================
    // abort() - Force-stop listening immediately (for interruptions)
    // ============================================================
    abort() {
        if (!this.recognition) return;

        try {
            this.recognition.abort();
        } catch (e) { /* already stopped */ }

        this._resetState();
        console.log('[Voice] 🎤 Aborted');
    },

    // ============================================================
    // EVENT HANDLERS
    // ============================================================
    _onStart() {
        this.isListening = true;
        this._isProcessing = false;
        this._setListeningUI(true);

        // Notify avatar
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.setListening(true);
        }

        // Show status
        const status = document.getElementById('avatar-status');
        if (status) {
            status.innerHTML = '<span class="status-dot listening"></span> Listening...';
            status.classList.add('visible');
        }

        console.log('[Voice] 🎤 Listening active');
    },

    _onResult(event) {
        const resultIndex = event.results.length - 1;
        const result = event.results[resultIndex];
        const transcript = result[0].transcript.trim();

        if (!transcript) return;

        // Show interim results in input
        const input = document.getElementById('chat-input');
        if (input) input.value = transcript;

        // Final result — send it
        if (result.isFinal) {
            console.log('[Voice] ✓ Final:', transcript);
            this._isProcessing = true;
            this._sendTranscript(transcript);
        }
    },

    _onError(event) {
        const error = event.error;
        console.warn('[Voice] Error:', error);

        switch (error) {
            case 'not-allowed':
            case 'service-not-allowed':
                this._showError('Microphone access denied. Please allow permission.');
                break;
            case 'no-speech':
                // Normal — user just didn't say anything
                break;
            case 'audio-capture':
                this._showError('No microphone found.');
                break;
            case 'network':
                this._showError('Network error during recognition.');
                break;
            case 'aborted':
                // Intentional abort — no error to show
                break;
        }
    },

    _onEnd() {
        const wasListening = this.isListening;
        this._resetState();

        // Notify avatar
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.setListening(false);
        }

        // Hide status only if nothing else is showing
        if (!ChatManager.isSpeaking && !ChatManager.isWaiting) {
            const status = document.getElementById('avatar-status');
            if (status) status.classList.remove('visible');
        }

        if (wasListening) {
            console.log('[Voice] 🎤 Session ended cleanly');
        }
    },

    // ============================================================
    // _sendTranscript() - Send to chat pipeline
    // ============================================================
    _sendTranscript(text) {
        if (!text || !text.trim()) return;

        const input = document.getElementById('chat-input');
        if (input) input.value = text;

        if (typeof ChatManager !== 'undefined') {
            ChatManager.sendMessage();
        }
    },

    // ============================================================
    // _resetState() - Clean reset of all voice state
    // ============================================================
    _resetState() {
        this.isListening = false;
        this._isProcessing = false;
        this._setListeningUI(false);
    },

    // ============================================================
    // UI HELPERS
    // ============================================================
    _setListeningUI(listening) {
        const btn = this.elements.micBtn;
        if (!btn) return;
        btn.classList.toggle('listening', listening);
        btn.setAttribute('aria-label', listening ? 'Stop listening' : 'Start voice input');
    },

    _hideMicButton() {
        const btn = document.getElementById('mic-btn');
        if (btn) btn.style.display = 'none';
    },

    _showError(message) {
        if (typeof ChatManager !== 'undefined') {
            ChatManager.showResponse(message, true);
        }
    },
};
