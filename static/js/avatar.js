/* ============================================================
   Avatar Module - Live2D Integration + Multi-Avatar Support
   
   Features:
   - Multiple avatar selection (3 avatars)
   - Dynamic avatar switching without page refresh
   - Idle animations (blinking, breathing)
   - Speaking animation (mouth movement synced to TTS)
   - Tap interaction
   - Thinking/speaking state indicators
   
   Required CDN scripts (loaded in index.html BEFORE this file):
   1. pixi.js v6.5.10         → sets window.PIXI
   2. live2d.min.js           → Cubism 2.1 runtime
   3. cubism2.min.js          → pixi-live2d-display Cubism2 bundle
   ============================================================ */

const AvatarManager = {
    app: null,      // PixiJS Application
    model: null,    // Current Live2D model instance
    isLoaded: false,
    isThinking: false,
    isSpeaking: false,

    // Speaking animation state
    _speakingTicker: null,
    _speakingTime: 0,

    // Current avatar ID
    currentAvatarId: 'shizuku',

    // ============================================================
    // AVATAR REGISTRY
    // Add new avatars here. Each entry defines the model URL,
    // display name, scale, and motion/parameter mappings.
    // ============================================================
    avatars: {
        shizuku: {
            id: 'shizuku',
            name: 'Female Concierge',
            emoji: '👩',
            modelUrl: 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json',
            scale: 0.6,
            idleMotion: 'idle',
            tapMotion: 'tap_body',
            mouthParam: 'PARAM_MOUTH_OPEN_Y',
        },
        koharu: {
            id: 'koharu',
            name: 'Male Concierge',
            emoji: '👨',
            modelUrl: 'https://cdn.jsdelivr.net/npm/live2d-widget-model-koharu/assets/koharu.model.json',
            scale: 0.55,
            idleMotion: 'idle',
            tapMotion: '',  // Koharu uses unnamed motion group
            mouthParam: 'PARAM_MOUTH_OPEN_Y',
        },
        hijiki: {
            id: 'hijiki',
            name: 'AI Assistant',
            emoji: '🤖',
            modelUrl: 'https://cdn.jsdelivr.net/npm/live2d-widget-model-hijiki/assets/hijiki.model.json',
            scale: 0.55,
            idleMotion: 'idle',
            tapMotion: '',  // Hijiki uses unnamed motion group
            mouthParam: 'PARAM_MOUTH_OPEN_Y',
        },
    },

    // --- General config ---
    config: {
        canvasId: 'avatar-canvas',
        speaking: {
            speed: 8,
            maxOpen: 0.7,
            minOpen: 0.1,
            randomness: 0.3,
        },
    },

    // ============================================================
    // init() - Entry point
    // ============================================================
    async init() {
        console.log('[Avatar] === Initialization Start ===');

        // --- Dependency checks ---
        if (typeof PIXI === 'undefined') {
            this.showFallback('PixiJS library failed to load from CDN.');
            return;
        }
        console.log('[Avatar] ✓ PIXI loaded, version:', PIXI.VERSION);

        if (typeof window.PIXI === 'undefined') window.PIXI = PIXI;

        if (typeof Live2D === 'undefined' && typeof window.Live2D === 'undefined') {
            this.showFallback('Live2D Cubism2 runtime failed to load.');
            return;
        }
        console.log('[Avatar] ✓ Live2D Cubism2 runtime loaded');

        if (!PIXI.live2d || !PIXI.live2d.Live2DModel) {
            this.showFallback('pixi-live2d-display plugin failed to register.');
            return;
        }
        console.log('[Avatar] ✓ PIXI.live2d.Live2DModel available');

        // --- Create PixiJS Application ---
        try {
            const canvas = document.getElementById(this.config.canvasId);
            if (!canvas) throw new Error('Canvas #' + this.config.canvasId + ' not found.');

            this.app = new PIXI.Application({
                view: canvas,
                autoStart: true,
                resizeTo: window,
                backgroundAlpha: 0,
                antialias: true,
            });
            console.log('[Avatar] ✓ PixiJS Application created');

            // Load the default avatar
            await this.loadAvatar(this.currentAvatarId);

            window.addEventListener('resize', () => this.positionModel());
            console.log('[Avatar] === Initialization Complete ===');
        } catch (error) {
            console.error('[Avatar] Init error:', error);
            this.showFallback(error.message || String(error));
        }
    },

    // ============================================================
    // switchAvatar(avatarId) - Switch to a different avatar
    // Called by the avatar selector UI.
    // ============================================================
    async switchAvatar(avatarId) {
        if (!this.avatars[avatarId]) {
            console.error('[Avatar] Unknown avatar ID:', avatarId);
            return;
        }

        if (avatarId === this.currentAvatarId && this.isLoaded) {
            console.log('[Avatar] Already using this avatar');
            return;
        }

        console.log('[Avatar] Switching to:', avatarId);

        // Stop speaking animation if active
        this.stopSpeaking();

        // Unload current model
        this.unloadModel();

        // Load new avatar
        this.currentAvatarId = avatarId;
        await this.loadAvatar(avatarId);

        // Update selector UI
        this._updateSelectorUI(avatarId);

        console.log('[Avatar] ✓ Switched to:', this.avatars[avatarId].name);
    },

    // ============================================================
    // loadAvatar(avatarId) - Load a specific avatar model
    // ============================================================
    async loadAvatar(avatarId) {
        const avatarDef = this.avatars[avatarId];
        if (!avatarDef) throw new Error('Avatar not found: ' + avatarId);

        console.log('[Avatar] Loading:', avatarDef.name, '(' + avatarId + ')');

        try {
            this.model = await PIXI.live2d.Live2DModel.from(avatarDef.modelUrl);
            if (!this.model) throw new Error('Model load returned null');

            this.app.stage.addChild(this.model);
            this.positionModel();
            this.startIdleMotion();

            // Click interaction
            this.model.interactive = true;
            this.model.buttonMode = true;
            this.model.on('pointerdown', () => this.onTap());

            this.isLoaded = true;
            console.log('[Avatar] ✓ Avatar loaded:', avatarDef.name);
        } catch (error) {
            console.error('[Avatar] Failed to load avatar:', error);
            this.isLoaded = false;
            this.showFallback('Failed to load avatar: ' + avatarDef.name);
        }
    },

    // ============================================================
    // unloadModel() - Remove current model from stage
    // ============================================================
    unloadModel() {
        if (this.model) {
            this.model.removeAllListeners();
            this.app.stage.removeChild(this.model);
            this.model.destroy();
            this.model = null;
            this.isLoaded = false;
            console.log('[Avatar] Previous model unloaded');
        }
    },

    // ============================================================
    // positionModel()
    // ============================================================
    positionModel() {
        if (!this.model || !this.app) return;

        const avatarDef = this.avatars[this.currentAvatarId];
        const screenW = this.app.screen.width;
        const screenH = this.app.screen.height;
        const targetH = screenH * (avatarDef ? avatarDef.scale : 0.6);
        const scale = targetH / this.model.height;

        this.model.scale.set(scale);
        this.model.x = (screenW - this.model.width * scale) / 2;
        this.model.y = (screenH - this.model.height * scale) / 2 - screenH * 0.05;
    },

    // ============================================================
    // startIdleMotion()
    // ============================================================
    startIdleMotion() {
        if (!this.model) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        if (!avatarDef || !avatarDef.idleMotion) return;

        try {
            const mm = this.model.internalModel.motionManager;
            mm.startRandomMotion(avatarDef.idleMotion, PIXI.live2d.MotionPriority.IDLE);
            console.log('[Avatar] ✓ Idle motion started');
        } catch (e) {
            console.warn('[Avatar] Idle motion failed (non-fatal):', e.message);
        }
    },

    // ============================================================
    // onTap()
    // ============================================================
    onTap() {
        if (!this.model) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        if (!avatarDef || !avatarDef.tapMotion) return;

        try {
            const mm = this.model.internalModel.motionManager;
            mm.startRandomMotion(avatarDef.tapMotion, PIXI.live2d.MotionPriority.NORMAL);
            console.log('[Avatar] Tap reaction');
        } catch (e) {
            console.warn('[Avatar] Tap motion failed:', e.message);
        }
    },

    // ============================================================
    // SPEAKING ANIMATION
    // ============================================================
    startSpeaking() {
        if (!this.model || !this.app) return;
        if (this.isSpeaking) return;

        this.isSpeaking = true;
        this._speakingTime = 0;
        console.log('[Avatar] 🗣️ Speaking animation started');

        this._speakingTicker = (delta) => this._animateMouth(delta);
        this.app.ticker.add(this._speakingTicker);
    },

    stopSpeaking() {
        if (!this.isSpeaking) return;
        this.isSpeaking = false;

        if (this._speakingTicker && this.app) {
            this.app.ticker.remove(this._speakingTicker);
            this._speakingTicker = null;
        }
        this._setMouthOpen(0);
        console.log('[Avatar] 🗣️ Speaking animation stopped');
    },

    _animateMouth(delta) {
        if (!this.model || !this.isSpeaking) return;
        const cfg = this.config.speaking;

        this._speakingTime += delta * 0.016667;

        const primary = Math.sin(this._speakingTime * cfg.speed * 2 * Math.PI);
        const secondary = Math.sin(this._speakingTime * cfg.speed * 1.3 * 2 * Math.PI) * 0.3;
        const tertiary = Math.sin(this._speakingTime * cfg.speed * 3.7 * 2 * Math.PI) * 0.15;
        const jitter = (Math.random() - 0.5) * cfg.randomness * 0.5;

        let mouthValue = (primary + secondary + tertiary + jitter + 1) / 2;
        mouthValue = cfg.minOpen + mouthValue * (cfg.maxOpen - cfg.minOpen);
        mouthValue = Math.max(0, Math.min(1, mouthValue));

        this._setMouthOpen(mouthValue);
    },

    _setMouthOpen(value) {
        if (!this.model) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        const paramId = avatarDef ? avatarDef.mouthParam : 'PARAM_MOUTH_OPEN_Y';

        try {
            const coreModel = this.model.internalModel.coreModel;
            if (coreModel.setParamFloat) {
                coreModel.setParamFloat(paramId, value);
            } else if (coreModel.setParameterValueById) {
                coreModel.setParameterValueById(paramId, value);
            }
        } catch (e) { /* silent */ }
    },

    // ============================================================
    // setThinking()
    // ============================================================
    setThinking(thinking) {
        this.isThinking = thinking;
        const status = document.getElementById('avatar-status');
        if (thinking) {
            status.innerHTML = '<span class="status-dot"></span> Thinking...';
            status.classList.add('visible');
        } else {
            if (!this.isSpeaking) status.classList.remove('visible');
        }
    },

    // ============================================================
    // _updateSelectorUI() - Highlight the active avatar in selector
    // ============================================================
    _updateSelectorUI(avatarId) {
        document.querySelectorAll('.avatar-option').forEach((el) => {
            el.classList.toggle('active', el.dataset.avatar === avatarId);
        });
    },

    // ============================================================
    // getAvatarList() - Returns array of available avatars
    // ============================================================
    getAvatarList() {
        return Object.values(this.avatars);
    },

    // ============================================================
    // showFallback()
    // ============================================================
    showFallback(errorDetail) {
        const container = document.getElementById('avatar-container');
        container.innerHTML = `
            <div style="
                display:flex; flex-direction:column; align-items:center;
                justify-content:center; height:100%;
                color:#a0a0b8; text-align:center; padding:20px;
            ">
                <div style="font-size:4rem; margin-bottom:16px;">🤖</div>
                <p style="font-size:1.1rem; margin-bottom:8px;">AI Concierge</p>
                <p style="font-size:0.85rem; opacity:0.6;">
                    Avatar could not load. Chat still works below!
                </p>
                <p style="font-size:0.75rem; opacity:0.4; margin-top:8px; max-width:400px;">
                    Debug: ${errorDetail || 'Unknown error'}
                </p>
            </div>
        `;
    }
};
