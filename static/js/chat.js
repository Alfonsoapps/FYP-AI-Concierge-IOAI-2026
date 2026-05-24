/* ============================================================
   Chat Module - Handles user input, AI responses, and TTS playback
   
   This module manages:
   - Sending messages to the FastAPI backend (/chat endpoint)
   - Displaying AI responses in the floating bubble
   - Requesting and playing Text-to-Speech audio (/tts endpoint)
   - Managing chat history
   - Connecting responses to the avatar state
   ============================================================ */

const ChatManager = {
    // Chat history stored in memory
    history: [],
    
    // DOM element references (set during init)
    elements: {
        input: null,
        sendBtn: null,
        responseBubble: null,
        responseText: null,
        chatHistory: null,
        historyToggle: null,
    },

    // State
    isWaiting: false,   // True while waiting for AI response
    isSpeaking: false,  // True while TTS audio is playing

    // Audio player for TTS (reused across responses)
    audioPlayer: null,

    // ============================================================
    // INITIALIZATION
    // ============================================================
    init() {
        // Get DOM references
        this.elements.input = document.getElementById('chat-input');
        this.elements.sendBtn = document.getElementById('send-btn');
        this.elements.responseBubble = document.getElementById('response-bubble');
        this.elements.responseText = document.getElementById('response-text');
        this.elements.chatHistory = document.getElementById('chat-history');
        this.elements.historyToggle = document.getElementById('history-toggle');

        // Create a reusable Audio element for TTS playback
        this.audioPlayer = new Audio();
        this.audioPlayer.addEventListener('play', () => this.onSpeechStart());
        this.audioPlayer.addEventListener('ended', () => this.onSpeechEnd());
        this.audioPlayer.addEventListener('error', (e) => this.onSpeechError(e));

        // Event listeners
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Toggle chat history panel
        this.elements.historyToggle.addEventListener('click', () => {
            this.elements.chatHistory.classList.toggle('visible');
        });

        console.log('[Chat] Initialized with TTS support');
    },

    // ============================================================
    // SEND MESSAGE
    // Sends user message → gets AI response → plays TTS
    // ============================================================
    async sendMessage() {
        const message = this.elements.input.value.trim();
        if (!message || this.isWaiting) return;

        // Clear input
        this.elements.input.value = '';

        // Stop any currently playing speech
        this.stopSpeech();

        // Add user message to history
        this.addToHistory('user', message);

        // Show typing indicator
        this.showTypingIndicator();

        // Tell avatar we're thinking
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.setThinking(true);
        }

        // Disable input
        this.setWaiting(true);

        try {
            // --- Step 1: Get AI response ---
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Request failed (${response.status})`);
            }

            const data = await response.json();
            const reply = data.reply;

            // Display the text response
            this.showResponse(reply);
            this.addToHistory('bot', reply);

            // Tell avatar we got a response
            if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
                AvatarManager.setThinking(false);
            }

            // --- Step 2: Request TTS and play audio ---
            // This runs in the background (non-blocking)
            this.speakResponse(reply);

        } catch (error) {
            console.error('[Chat] Error:', error);
            this.showResponse(`Sorry, something went wrong: ${error.message}`, true);

            if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
                AvatarManager.setThinking(false);
            }
        }

        // Re-enable input
        this.setWaiting(false);
    },

    // ============================================================
    // TEXT-TO-SPEECH
    // Requests audio from /tts endpoint and plays it
    // ============================================================
    async speakResponse(text) {
        console.log('[Chat] Requesting TTS for response...');

        try {
            // Request speech audio from the backend
            const response = await fetch('/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.detail || `TTS request failed (${response.status})`);
            }

            // Get the audio as a blob
            const audioBlob = await response.blob();

            // Create a URL for the audio blob and play it
            const audioUrl = URL.createObjectURL(audioBlob);

            // Stop any previous audio
            this.stopSpeech();

            // Play the new audio
            this.audioPlayer.src = audioUrl;
            this.audioPlayer.play().catch((e) => {
                // Browser may block autoplay if user hasn't interacted yet
                console.warn('[Chat] Audio autoplay blocked:', e.message);
                console.warn('[Chat] User interaction required for first audio play.');
            });

            console.log('[Chat] TTS audio playing');

        } catch (error) {
            // TTS failure is non-fatal — the text response is already displayed
            console.warn('[Chat] TTS failed (non-fatal):', error.message);
        }
    },

    // ============================================================
    // SPEECH PLAYBACK EVENTS
    // ============================================================
    onSpeechStart() {
        this.isSpeaking = true;

        // Start avatar speaking animation
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.startSpeaking();
        }

        // Show speaking indicator
        const status = document.getElementById('avatar-status');
        if (status) {
            status.innerHTML = '<span class="status-dot speaking"></span> Speaking...';
            status.classList.add('visible');
        }
        console.log('[Chat] Speech started → avatar speaking');
    },

    onSpeechEnd() {
        this.isSpeaking = false;

        // Stop avatar speaking animation (returns to idle)
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.stopSpeaking();
        }

        // Hide the speaking indicator
        const status = document.getElementById('avatar-status');
        if (status) {
            status.classList.remove('visible');
        }

        // Clean up the blob URL to free memory
        if (this.audioPlayer.src.startsWith('blob:')) {
            URL.revokeObjectURL(this.audioPlayer.src);
        }
        console.log('[Chat] Speech ended → avatar idle');
    },

    onSpeechError(event) {
        this.isSpeaking = false;

        // Stop avatar speaking animation on error too
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.stopSpeaking();
        }

        const status = document.getElementById('avatar-status');
        if (status) {
            status.classList.remove('visible');
        }
        console.warn('[Chat] Audio playback error:', event);
    },

    // ============================================================
    // STOP SPEECH
    // Stops any currently playing audio
    // ============================================================
    stopSpeech() {
        if (this.audioPlayer && !this.audioPlayer.paused) {
            this.audioPlayer.pause();
            this.audioPlayer.currentTime = 0;
        }
        this.isSpeaking = false;

        // Stop avatar speaking animation
        if (typeof AvatarManager !== 'undefined' && AvatarManager.isLoaded) {
            AvatarManager.stopSpeaking();
        }
    },

    // ============================================================
    // DISPLAY RESPONSE
    // ============================================================
    showResponse(text, isError = false) {
        const bubble = this.elements.responseBubble;
        const textEl = this.elements.responseText;

        textEl.textContent = text;
        textEl.style.color = isError ? '#ef4444' : 'var(--text-primary)';
        bubble.classList.add('visible');
    },

    // ============================================================
    // TYPING INDICATOR
    // ============================================================
    showTypingIndicator() {
        const bubble = this.elements.responseBubble;
        const textEl = this.elements.responseText;

        textEl.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;
        bubble.classList.add('visible');
    },

    // ============================================================
    // CHAT HISTORY
    // ============================================================
    addToHistory(role, text) {
        this.history.push({ role, text, timestamp: Date.now() });

        const historyEl = this.elements.chatHistory;
        const msgEl = document.createElement('div');
        msgEl.className = `history-message ${role}`;
        
        const displayText = text.length > 200 ? text.substring(0, 200) + '...' : text;
        msgEl.textContent = displayText;
        
        historyEl.appendChild(msgEl);
        historyEl.scrollTop = historyEl.scrollHeight;
    },

    // ============================================================
    // UI STATE
    // ============================================================
    setWaiting(waiting) {
        this.isWaiting = waiting;
        this.elements.input.disabled = waiting;
        this.elements.sendBtn.disabled = waiting;
        
        if (waiting) {
            this.elements.input.placeholder = 'Waiting for response...';
        } else {
            this.elements.input.placeholder = 'Ask me anything about IOAI 2027...';
        }
    }
};
