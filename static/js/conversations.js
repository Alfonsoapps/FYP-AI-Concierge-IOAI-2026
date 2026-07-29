/* ============================================================
   Conversation Manager
   
   Manages multiple conversations in localStorage.
   Each conversation has an ID, title, timestamp, and messages.
   Tied to the participant's anonymous clientId.
   ============================================================ */

const ConversationManager = {
    _STORAGE_KEY: 'ioai-conversations',
    _ACTIVE_KEY: 'ioai-active-conversation',
    _MAX_CONVERSATIONS: 50,

    conversations: [],
    activeId: null,

    // ============================================================
    // INIT
    // ============================================================
    init() {
        this.conversations = this._load();
        this.activeId = localStorage.getItem(this._ACTIVE_KEY);

        // If no conversations exist, create a default one
        if (this.conversations.length === 0) {
            this.createNew(false);
        } else if (!this.activeId || !this.getById(this.activeId)) {
            this.activeId = this.conversations[0].id;
            localStorage.setItem(this._ACTIVE_KEY, this.activeId);
        }

        this._renderSidebar();
        this._bindEvents();
        console.log('[Conversations] ✓ Initialized (%d conversations)', this.conversations.length);
    },

    // ============================================================
    // CRUD
    // ============================================================
    createNew(switchTo = true) {
        const conv = {
            id: this._generateId(),
            title: 'New Conversation',
            icon: '💬',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            messages: [],
        };

        this.conversations.unshift(conv);
        this._save();

        if (switchTo) {
            this.switchTo(conv.id);
            // Clear chat UI
            if (typeof ChatManager !== 'undefined') {
                ChatManager.history = [];
                const container = ChatManager.elements.messagesContainer;
                if (container) container.innerHTML = '';
                ChatManager._addMessage('bot', 'Welcome to IOAI 2027! I\'m your friendly guide. How can I help you today?');
            }
        }

        this._renderSidebar();
        return conv;
    },

    switchTo(id) {
        const conv = this.getById(id);
        if (!conv) return;

        this.activeId = id;
        localStorage.setItem(this._ACTIVE_KEY, id);

        // Load messages into ChatManager
        if (typeof ChatManager !== 'undefined') {
            ChatManager.history = conv.messages.slice();
            const container = ChatManager.elements.messagesContainer;
            if (container) {
                container.innerHTML = '';
                if (conv.messages.length === 0) {
                    ChatManager._addMessage('bot', 'Welcome to IOAI 2027! I\'m your friendly guide. How can I help you today?');
                } else {
                    for (const msg of conv.messages) {
                        ChatManager._addMessage(msg.role, msg.text, msg.file || null);
                    }
                }
                container.scrollTop = container.scrollHeight;
            }
        }

        this._renderSidebar();
        this._closeMobileSidebar();
    },

    deleteConversation(id) {
        const idx = this.conversations.findIndex(c => c.id === id);
        if (idx === -1) return;

        this.conversations.splice(idx, 1);
        this._save();

        // If we deleted the active conversation, switch to another
        if (this.activeId === id) {
            if (this.conversations.length === 0) {
                this.createNew(true);
            } else {
                this.switchTo(this.conversations[0].id);
            }
        }

        this._renderSidebar();
    },

    clearAll() {
        this.conversations = [];
        this._save();
        this.createNew(true);
        this._renderSidebar();
    },

    getById(id) {
        return this.conversations.find(c => c.id === id) || null;
    },

    getActive() {
        return this.getById(this.activeId);
    },

    // ============================================================
    // MESSAGE TRACKING (called by ChatManager)
    // ============================================================
    addMessage(role, text, fileMeta) {
        const conv = this.getActive();
        if (!conv) return;

        const msg = {
            role,
            text,
            timestamp: new Date().toISOString(),
        };
        if (fileMeta) msg.file = fileMeta;

        conv.messages.push(msg);
        conv.updatedAt = new Date().toISOString();

        // Auto-generate title from first user message
        if (conv.title === 'New Conversation' && role === 'user') {
            const generated = this._generateTitle(text);
            conv.title = generated.title;
            conv.icon = generated.icon;
        }

        this._save();
        this._renderSidebar();
    },

    // ============================================================
    // TITLE GENERATION
    // ============================================================
    _generateTitle(message) {
        const text = message.trim().toLowerCase();
        const maxLen = 28;

        // Category detection with icons
        const categories = [
            { keywords: ['schedule', 'time', 'when', 'day 1', 'day 2', 'day 3', 'day 4', 'event', 'ceremony'], icon: '📅' },
            { keywords: ['map', 'where', 'location', 'venue', 'hall', 'room', 'building', 'direction'], icon: '🗺' },
            { keywords: ['hotel', 'accommodation', 'stay', 'check-in', 'check-out', 'room'], icon: '🏨' },
            { keywords: ['food', 'eat', 'restaurant', 'lunch', 'dinner', 'breakfast', 'meal', 'halal', 'vegetarian'], icon: '🍽' },
            { keywords: ['transport', 'bus', 'mrt', 'taxi', 'grab', 'train', 'airport'], icon: '🚆' },
            { keywords: ['document', 'pdf', 'file', 'upload', 'summarise', 'summarize', 'handbook'], icon: '📄' },
            { keywords: ['team', 'delegation', 'leader', 'group', 'participant'], icon: '👥' },
            { keywords: ['help', 'emergency', 'safety', 'medical', 'sick', 'lost'], icon: '🆘' },
        ];

        let icon = '💬';
        for (const cat of categories) {
            if (cat.keywords.some(k => text.includes(k))) {
                icon = cat.icon;
                break;
            }
        }

        // Generate a short title from the message
        let title = message.trim();

        // Remove common question starters
        title = title.replace(/^(can you |could you |please |hey |hi |hello |what is |what's |where is |where's |how do i |how can i |tell me about |i need |i want )/i, '');

        // Capitalize first letter
        title = title.charAt(0).toUpperCase() + title.slice(1);

        // Remove trailing punctuation
        title = title.replace(/[?.!]+$/, '');

        // Truncate
        if (title.length > maxLen) {
            title = title.substring(0, maxLen).trim() + '…';
        }

        return { title: title || 'New Conversation', icon };
    },

    // ============================================================
    // SIDEBAR RENDERING
    // ============================================================
    _renderSidebar() {
        const list = document.getElementById('conv-list');
        if (!list) return;

        list.innerHTML = '';

        for (const conv of this.conversations) {
            const isActive = conv.id === this.activeId;
            const item = document.createElement('div');
            item.className = 'conv-item' + (isActive ? ' active' : '');
            item.dataset.id = conv.id;

            const msgCount = conv.messages.filter(m => m.role === 'user').length;
            const timeStr = this._relativeTime(conv.updatedAt);

            item.innerHTML =
                '<div class="conv-item-main">' +
                    '<span class="conv-icon">' + (conv.icon || '💬') + '</span>' +
                    '<div class="conv-info">' +
                        '<span class="conv-title">' + this._escapeHtml(conv.title) + '</span>' +
                        '<span class="conv-meta">' + msgCount + ' message' + (msgCount !== 1 ? 's' : '') + ' · ' + timeStr + '</span>' +
                    '</div>' +
                '</div>' +
                '<button class="conv-delete" title="Delete conversation" aria-label="Delete">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>' +
                '</button>';

            list.appendChild(item);
        }
    },

    // ============================================================
    // EVENTS
    // ============================================================
    _bindEvents() {
        // New conversation button
        const newBtn = document.getElementById('conv-new-btn');
        if (newBtn) {
            newBtn.addEventListener('click', () => this.createNew(true));
        }

        // Clear all button
        const clearBtn = document.getElementById('conv-clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                if (confirm('Delete all conversations? This cannot be undone.')) {
                    this.clearAll();
                }
            });
        }

        // Conversation list (delegation)
        const list = document.getElementById('conv-list');
        if (list) {
            list.addEventListener('click', (e) => {
                const deleteBtn = e.target.closest('.conv-delete');
                const item = e.target.closest('.conv-item');

                if (deleteBtn && item) {
                    e.stopPropagation();
                    const id = item.dataset.id;
                    const conv = this.getById(id);
                    const name = conv ? conv.title : 'this conversation';
                    if (confirm('Delete "' + name + '"?')) {
                        this.deleteConversation(id);
                    }
                } else if (item) {
                    this.switchTo(item.dataset.id);
                }
            });
        }

        // Mobile toggle
        const toggle = document.getElementById('sidebar-toggle');
        const sidebar = document.getElementById('conv-sidebar');
        const overlay = document.getElementById('sidebar-overlay');

        if (toggle && sidebar) {
            toggle.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                if (overlay) overlay.classList.toggle('visible');
            });
        }

        if (overlay) {
            overlay.addEventListener('click', () => this._closeMobileSidebar());
        }
    },

    _closeMobileSidebar() {
        const sidebar = document.getElementById('conv-sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('visible');
    },

    // ============================================================
    // PERSISTENCE
    // ============================================================
    _save() {
        try {
            const trimmed = this.conversations.slice(0, this._MAX_CONVERSATIONS);
            localStorage.setItem(this._STORAGE_KEY, JSON.stringify(trimmed));
        } catch (e) {
            console.warn('[Conversations] Save failed:', e.message);
        }
    },

    _load() {
        try {
            const data = localStorage.getItem(this._STORAGE_KEY);
            if (!data) return [];
            const parsed = JSON.parse(data);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    },

    // ============================================================
    // UTILITIES
    // ============================================================
    _generateId() {
        return 'conv_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    _relativeTime(iso) {
        const now = Date.now();
        const then = new Date(iso).getTime();
        const diff = Math.floor((now - then) / 1000);

        if (diff < 60) return 'now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
        return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    },
};
