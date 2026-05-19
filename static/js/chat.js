/* ============================================================
   Chat Module - Handles user input and AI responses
   
   This module manages:
   - Sending messages to the FastAPI backend (/chat endpoint)
   - Displaying AI responses in the floating bubble
   - Managing chat history
   - Connecting responses to the avatar state
   
   The chat interface is intentionally minimal and secondary
   to the avatar experience.
   ============================================================ */

// ============================================================
// CHAT MANAGER
// Encapsulates all chat logic
// ============================================================
const ChatManager = {
    // Chat history stored in memory (could be persisted to localStorage later)
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
    isWaiting: false,  // True while waiting for AI response

    // ============================================================
    // INITIALIZATION
    // Grabs DOM references and sets up event listeners
    // ============================================================
    init() {
        // Get references to DOM elements
        this.elements.input = document.getElementById('chat-input');
        this.elements.sendBtn = document.getElementById('send-btn');
        this.elements.responseBubble = document.getElementById('response-bubble');
        this.elements.responseText = document.getElementById('response-text');
        this.elements.chatHistory = document.getElementById('chat-history');
        this.elements.historyToggle = document.getElementById('history-toggle');

        // Set up event listeners
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

        console.log('[Chat] Initialized');
    },

    // ============================================================
    // SEND MESSAGE
    // Sends the user's message to the backend and handles the response
    // ============================================================
    async sendMessage() {
        // Get and validate the message
        const message = this.elements.input.value.trim();
        if (!message || this.isWaiting) return;

        // Clear the input field
        this.elements.input.value = '';

        // Add user message to history
        this.addToHistory('user', message);

        // Show typing indicator in the response bubble
        this.showTypingIndicator();

        // Tell the avatar we're waiting for a response
        if (AvatarManager.isLoaded) {
            AvatarManager.setThinking(true);
        }

        // Disable input while waiting
        this.setWaiting(true);

        try {
            // --- Send request to FastAPI backend ---
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message }),
            });

            // Handle HTTP errors
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Request failed (${response.status})`);
            }

            // Parse the JSON response
            const data = await response.json();
            const reply = data.reply;

            // Display the AI response
            this.showResponse(reply);

            // Add bot response to history
            this.addToHistory('bot', reply);

            // Tell the avatar we got a response
            if (AvatarManager.isLoaded) {
                AvatarManager.setThinking(false);
                // Future: trigger a "speaking" animation here
                // AvatarManager.setExpression('happy');
            }

        } catch (error) {
            // Show error in the response bubble
            console.error('[Chat] Error:', error);
            this.showResponse(`Sorry, something went wrong: ${error.message}`, true);

            if (AvatarManager.isLoaded) {
                AvatarManager.setThinking(false);
            }
        }

        // Re-enable input
        this.setWaiting(false);
    },

    // ============================================================
    // DISPLAY RESPONSE
    // Shows the AI's response in the floating bubble
    // ============================================================
    showResponse(text, isError = false) {
        const bubble = this.elements.responseBubble;
        const textEl = this.elements.responseText;

        // Set the response text
        textEl.textContent = text;
        textEl.style.color = isError ? '#ef4444' : 'var(--text-primary)';

        // Make the bubble visible with animation
        bubble.classList.add('visible');
    },

    // ============================================================
    // TYPING INDICATOR
    // Shows animated dots while waiting for AI response
    // ============================================================
    showTypingIndicator() {
        const bubble = this.elements.responseBubble;
        const textEl = this.elements.responseText;

        // Show typing animation
        textEl.innerHTML = `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;

        bubble.classList.add('visible');
    },

    // ============================================================
    // CHAT HISTORY
    // Manages the expandable message history panel
    // ============================================================
    addToHistory(role, text) {
        // Store in memory
        this.history.push({ role, text, timestamp: Date.now() });

        // Add to the history panel DOM
        const historyEl = this.elements.chatHistory;
        const msgEl = document.createElement('div');
        msgEl.className = `history-message ${role}`;
        
        // Truncate long messages in history view
        const displayText = text.length > 200 ? text.substring(0, 200) + '...' : text;
        msgEl.textContent = displayText;
        
        historyEl.appendChild(msgEl);

        // Auto-scroll to bottom
        historyEl.scrollTop = historyEl.scrollHeight;
    },

    // ============================================================
    // UI STATE
    // Enables/disables input while waiting for response
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
