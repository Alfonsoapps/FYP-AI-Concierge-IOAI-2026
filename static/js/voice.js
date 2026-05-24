/* ============================================================
   Voice Module - Speech-to-Text using Web Speech API
   
   Allows users to speak to the AI concierge using their microphone.
   Uses the browser's built-in Web Speech API (no external services).
   
   Flow:
   1. User clicks the microphone button
   2. Browser starts listening (shows "Listening..." state)
   3. User speaks naturally
   4. Speech is converted to text
   5. Text is sent through the existing ChatManager pipeline
   6. AI responds with text + TTS audio + avatar animation
   
   Browser support:
   - Chrome, Edge, Safari (full support)
   - Firefox (partial/no support for SpeechRecognition)
   - Falls back gracefully if unsupported
   ============================================================ */

const VoiceManager = {
    // Web Speech API instance
    recognition: null,

    // State
    isListening: false,
    isSupported: false,

    // DOM references
    elements: {
        micBtn: null,
    },

    // ============================================================
    // init() - Set up speech recognition
    // ============================================================
    init() {
        // Check browser support
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.warn('[Voice] Speech Recognition not supported in this browser.');
            this.isSupported = false;
            this._hideMicButton();
            return;
        }

        this.isSupported = true;
        console.log('[Voice] ✓ Web Speech API supported');

        // Create recognition instance
        this.recognition = new SpeechRecognition();

        // --- Configuration ---
        this.recognition.lang = 'en-US';       // Language for recognition
        this.recognition.continuous = false;    // Stop after one utterance
        this.recognition.interimResults = true; // Show partial results while speaking
        this.recognition.maxAlternatives = 1;   // Only need the best result

        // --- Event handlers ---
        this.recognition.onstart = () => this._onStart();
        this.recognition.onresult = (event) => this._onResult(event);
        this.recognition.onerror = (event) => this._onError(event);
        this.recognition.onend = () => this._onEnd();

        // Get mic button reference
        this.elements.micBtn = document.getElementById('mic-btn');

        if (this.elements.micBtn) {
            this.elements.micBtn.addEventListener('click', () => this.toggle());
            console.log('[Voice] ✓ Microphone button connected');
        } else {
            console.warn('[Voice] Mic button #mic-btn not found in DOM');
        }

        console.log('[Voice] ✓ Initialized');
    },

    // ============================================================
    // toggle() - Start or stop listening
    // ============================================================
    toggle() {
        if (this.isListening) {
            this.stop();
        } else {
            this.start();
        }
    },

    // ============================================================
    // start() - Begin listening for speech
    // ============================================================
    start() {
        if (!this.isSupported || !this.recognition) {
            console.warn('[Voice] Cannot start: not supported');
            return;
        }

        if (this.isListening) return;

        // Stop any currently playing TTS audio (so it doesn't interfere)
        if (typeof ChatManager !== 'undefined') {
            ChatManager.stopSpeech();
        }

        try {
            this.recognition.start();
            console.log('[Voice] 🎤 Starting recognition...');
        } catch (e) {
            // Can happen if recognition is already started
            console.warn('[Voice] Start failed:', e.message);
        }
    },

    // ============================================================
    // stop() - Stop listening
    // ============================================================
    stop() {
        if (!this.recognition || !this.isListening) return;

        try {
            this.recognition.stop();
            console.log('[Voice] 🎤 Stopping recognition...');
        } catch (e) {
            console.warn('[Voice] Stop failed:', e.message);
        }
    },

    // ============================================================
    // INTERNAL EVENT HANDLERS
    // ============================================================

    _onStart() {
        this.isListening = true;
        console.log('[Voice] 🎤 Listening...');

        // Update UI to show listening state
        this._setListeningUI(true);

        // Show status indicator
        const status = document.getElementById('avatar-status');
        if (status) {
            status.innerHTML = '<span class="status-dot listening"></span> Listening...';
            status.classList.add('visible');
        }
    },

    _onResult(event) {
        // Get the latest result
        const resultIndex = event.results.length - 1;
        const result = event.results[resultIndex];
        const transcript = result[0].transcript.trim();

        if (!transcript) return;

        // Show interim (partial) results in the input field
        const input = document.getElementById('chat-input');
        if (input) {
            input.value = transcript;
        }

        // If this is a final result (user stopped speaking)
        if (result.isFinal) {
            console.log('[Voice] ✓ Final transcript:', transcript);

            // Send the recognized text through the chat pipeline
            this._sendTranscript(transcript);
        } else {
            console.log('[Voice] ... interim:', transcript);
        }
    },

    _onError(event) {
        console.warn('[Voice] Recognition error:', event.error);

        // Handle specific errors
        switch (event.error) {
            case 'not-allowed':
            case 'service-not-allowed':
                this._showError('Microphone access denied. Please allow microphone permission.');
                break;
            case 'no-speech':
                // User didn't say anything — not a real error
                console.log('[Voice] No speech detected');
                break;
            case 'audio-capture':
                this._showError('No microphone found. Please connect a microphone.');
                break;
            case 'network':
                this._showError('Network error during speech recognition.');
                break;
            case 'aborted':
                // User or system aborted — normal behavior
                break;
            default:
                console.warn('[Voice] Unhandled error:', event.error);
        }
    },

    _onEnd() {
        this.isListening = false;
        console.log('[Voice] 🎤 Recognition ended');

        // Reset UI
        this._setListeningUI(false);

        // Hide status indicator (unless avatar is speaking/thinking)
        const status = document.getElementById('avatar-status');
        if (status && !ChatManager.isSpeaking && !ChatManager.isWaiting) {
            status.classList.remove('visible');
        }
    },

    // ============================================================
    // _sendTranscript() - Send recognized text to the chat system
    // ============================================================
    _sendTranscript(text) {
        if (!text || !text.trim()) return;

        // Put the text in the input field and trigger send
        const input = document.getElementById('chat-input');
        if (input) {
            input.value = text;
        }

        // Use ChatManager's sendMessage (which reads from the input)
        if (typeof ChatManager !== 'undefined') {
            ChatManager.sendMessage();
        }
    },

    // ============================================================
    // UI HELPERS
    // ============================================================

    _setListeningUI(listening) {
        const btn = this.elements.micBtn;
        if (!btn) return;

        if (listening) {
            btn.classList.add('listening');
            btn.setAttribute('aria-label', 'Stop listening');
        } else {
            btn.classList.remove('listening');
            btn.setAttribute('aria-label', 'Start voice input');
        }
    },

    _hideMicButton() {
        // Hide the mic button if speech recognition isn't supported
        const btn = document.getElementById('mic-btn');
        if (btn) {
            btn.style.display = 'none';
            btn.title = 'Voice input not supported in this browser';
        }
    },

    _showError(message) {
        // Show a brief error in the response bubble
        if (typeof ChatManager !== 'undefined') {
            ChatManager.showResponse(message, true);
        }
    },
};
