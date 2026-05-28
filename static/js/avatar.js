/* ============================================================
   Avatar Module - Live2D Integration + Conversational Realism
   
   Features:
   - Multiple avatar selection (3 avatars)
   - Dynamic avatar switching without page refresh
   - Smooth speaking animation with natural mouth movement
   - Subtle breathing and head sway for lifelike presence
   - Smooth transitions between idle/speaking/listening states
   - Tap interaction
   
   Required CDN scripts (loaded in index.html BEFORE this file):
   1. pixi.js v6.5.10         → sets window.PIXI
   2. live2d.min.js           → Cubism 2.1 runtime
   3. cubism2.min.js          → pixi-live2d-display Cubism2 bundle
   ============================================================ */

const AvatarManager = {
    app: null,
    model: null,
    isLoaded: false,
    isThinking: false,
    isSpeaking: false,
    isListening: false,

    // Animation state
    _animTicker: null,       // Single ticker for ALL animations
    _time: 0,               // Global elapsed time (seconds)
    _mouthTarget: 0,        // Target mouth value (smoothed toward)
    _mouthCurrent: 0,       // Current mouth value (smoothly interpolated)
    _speakingIntensity: 0,  // 0→1 fade-in when speaking starts

    // Current avatar ID
    currentAvatarId: 'shizuku',

    // ============================================================
    // AVATAR REGISTRY
    // ============================================================
    avatars: {
        shizuku: {
            id: 'shizuku',
            name: 'Female Concierge',
            emoji: '👩',
            modelUrl: 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json',
            scale: 1.55,
            idleMotion: 'idle',
            tapMotion: 'tap_body',
            mouthParam: 'PARAM_MOUTH_OPEN_Y',
            angleXParam: 'PARAM_ANGLE_X',
            angleYParam: 'PARAM_ANGLE_Y',
            bodyAngleXParam: 'PARAM_BODY_ANGLE_X',
            breathParam: 'PARAM_BREATH',
        },
        koharu: {
            id: 'koharu',
            name: 'Male Concierge',
            emoji: '👨',
            modelUrl: 'https://cdn.jsdelivr.net/npm/live2d-widget-model-koharu/assets/koharu.model.json',
            scale: 1.45,
            idleMotion: 'idle',
            tapMotion: '',
            mouthParam: 'PARAM_MOUTH_OPEN_Y',
            angleXParam: 'PARAM_ANGLE_X',
            angleYParam: 'PARAM_ANGLE_Y',
            bodyAngleXParam: 'PARAM_BODY_ANGLE_X',
            breathParam: 'PARAM_BREATH',
        },
        hijiki: {
            id: 'hijiki',
            name: 'AI Assistant',
            emoji: '🤖',
            modelUrl: 'https://cdn.jsdelivr.net/npm/live2d-widget-model-hijiki/assets/hijiki.model.json',
            scale: 1.45,
            idleMotion: 'idle',
            tapMotion: '',
            mouthParam: 'PARAM_MOUTH_OPEN_Y',
            angleXParam: 'PARAM_ANGLE_X',
            angleYParam: 'PARAM_ANGLE_Y',
            bodyAngleXParam: 'PARAM_BODY_ANGLE_X',
            breathParam: 'PARAM_BREATH',
        },
    },

    // --- Animation config ---
    config: {
        canvasId: 'avatar-canvas',

        // Mouth animation (speaking)
        mouth: {
            speed: 7,           // Base oscillation speed
            maxOpen: 0.65,      // Maximum mouth opening
            minOpen: 0.08,      // Minimum while speaking
            smoothing: 0.15,    // How fast mouth follows target (0-1, lower = smoother)
            fadeSpeed: 3.0,     // How fast speaking fades in/out (seconds⁻¹)
        },

        // Breathing (subtle body movement)
        breathing: {
            speed: 0.4,         // Breaths per second (slow, natural)
            intensity: 0.5,     // How pronounced (0-1)
        },

        // Head sway (subtle idle movement)
        headSway: {
            speedX: 0.15,       // Horizontal sway speed
            speedY: 0.12,       // Vertical nod speed
            intensityX: 3.0,    // Degrees of horizontal sway
            intensityY: 2.0,    // Degrees of vertical nod
            speakingMultiplier: 1.4, // Slightly more movement when speaking
        },

        // Body sway
        bodySway: {
            speed: 0.08,
            intensity: 1.5,
        },
    },

    // ============================================================
    // init()
    // ============================================================
    async init() {
        console.log('[Avatar] === Initialization Start ===');

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

        try {
            const canvas = document.getElementById(this.config.canvasId);
            if (!canvas) throw new Error('Canvas #' + this.config.canvasId + ' not found.');

            this.app = new PIXI.Application({
                view: canvas,
                autoStart: true,
                resizeTo: document.getElementById('avatar-container'),
                backgroundAlpha: 0,
                antialias: true,
            });
            console.log('[Avatar] ✓ PixiJS Application created');

            await this.loadAvatar(this.currentAvatarId);
            this._startAnimationLoop();
            window.addEventListener('resize', () => this.positionModel());

            console.log('[Avatar] === Initialization Complete ===');
        } catch (error) {
            console.error('[Avatar] Init error:', error);
            this.showFallback(error.message || String(error));
        }
    },

    // ============================================================
    // ANIMATION LOOP
    // Single ticker handles ALL animations (breathing, sway, mouth)
    // This is more efficient than multiple tickers.
    // ============================================================
    _startAnimationLoop() {
        if (this._animTicker) return;

        this._animTicker = (delta) => {
            // delta is in frames (~1 at 60fps), convert to seconds
            const dt = delta / 60;
            this._time += dt;
            this._updateAnimations(dt);
        };

        this.app.ticker.add(this._animTicker);
        console.log('[Avatar] ✓ Animation loop started');
    },

    _updateAnimations(dt) {
        if (!this.model) return;

        const cfg = this.config;
        const t = this._time;

        // --- Speaking intensity fade (smooth transition) ---
        const targetIntensity = this.isSpeaking ? 1.0 : 0.0;
        this._speakingIntensity += (targetIntensity - this._speakingIntensity) * Math.min(1, cfg.mouth.fadeSpeed * dt);

        // --- Mouth animation ---
        if (this._speakingIntensity > 0.01) {
            this._updateMouth(t, dt);
        } else if (this._mouthCurrent > 0.001) {
            // Smoothly close mouth when not speaking
            this._mouthCurrent *= 0.85;
            if (this._mouthCurrent < 0.001) this._mouthCurrent = 0;
            this._setParam('mouth', this._mouthCurrent);
        }

        // --- Breathing ---
        this._updateBreathing(t);

        // --- Head sway ---
        this._updateHeadSway(t);

        // --- Body sway ---
        this._updateBodySway(t);
    },

    // ============================================================
    // MOUTH ANIMATION (improved smoothness)
    // Uses layered oscillators with smooth interpolation
    // ============================================================
    _updateMouth(t, dt) {
        const cfg = this.config.mouth;
        const intensity = this._speakingIntensity;

        // Generate target mouth position using layered waves
        const speed = cfg.speed;
        const wave1 = Math.sin(t * speed * 2.0 * Math.PI) * 0.4;
        const wave2 = Math.sin(t * speed * 1.37 * 2.0 * Math.PI) * 0.25;
        const wave3 = Math.sin(t * speed * 2.71 * 2.0 * Math.PI) * 0.15;
        const wave4 = Math.sin(t * speed * 0.53 * 2.0 * Math.PI) * 0.2; // Slow envelope

        // Combine and normalize to 0-1
        let raw = (wave1 + wave2 + wave3 + wave4 + 1.0) / 2.0;

        // Map to configured range
        this._mouthTarget = cfg.minOpen + raw * (cfg.maxOpen - cfg.minOpen);

        // Smooth interpolation (prevents jittery movement)
        this._mouthCurrent += (this._mouthTarget - this._mouthCurrent) * cfg.smoothing;

        // Apply speaking intensity (fades in/out smoothly)
        const finalMouth = this._mouthCurrent * intensity;
        this._setParam('mouth', finalMouth);
    },

    // ============================================================
    // BREATHING (subtle, continuous)
    // ============================================================
    _updateBreathing(t) {
        const cfg = this.config.breathing;
        // Slow sine wave for natural breathing rhythm
        const breath = (Math.sin(t * cfg.speed * 2 * Math.PI) + 1) / 2;
        this._setParam('breath', breath * cfg.intensity);
    },

    // ============================================================
    // HEAD SWAY (subtle idle movement, more active when speaking)
    // ============================================================
    _updateHeadSway(t) {
        const cfg = this.config.headSway;
        const mult = this.isSpeaking ? cfg.speakingMultiplier : 1.0;

        // Layered slow oscillations for natural feel
        const swayX = (
            Math.sin(t * cfg.speedX * 2 * Math.PI) * 0.6 +
            Math.sin(t * cfg.speedX * 1.7 * 2 * Math.PI) * 0.4
        ) * cfg.intensityX * mult;

        const swayY = (
            Math.sin(t * cfg.speedY * 2 * Math.PI) * 0.7 +
            Math.sin(t * cfg.speedY * 2.3 * 2 * Math.PI) * 0.3
        ) * cfg.intensityY * mult;

        this._setParam('angleX', swayX);
        this._setParam('angleY', swayY);
    },

    // ============================================================
    // BODY SWAY (very subtle, slower than head)
    // ============================================================
    _updateBodySway(t) {
        const cfg = this.config.bodySway;
        const sway = Math.sin(t * cfg.speed * 2 * Math.PI) * cfg.intensity;
        this._setParam('bodyAngleX', sway);
    },

    // ============================================================
    // _setParam() - Set a Live2D parameter by logical name
    // Maps logical names to model-specific parameter IDs
    // ============================================================
    _setParam(logicalName, value) {
        if (!this.model) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        if (!avatarDef) return;

        // Map logical name to parameter ID
        const paramMap = {
            mouth: avatarDef.mouthParam,
            angleX: avatarDef.angleXParam,
            angleY: avatarDef.angleYParam,
            bodyAngleX: avatarDef.bodyAngleXParam,
            breath: avatarDef.breathParam,
        };

        const paramId = paramMap[logicalName];
        if (!paramId) return;

        try {
            const coreModel = this.model.internalModel.coreModel;
            if (coreModel.setParamFloat) {
                coreModel.setParamFloat(paramId, value);
            }
        } catch (e) { /* silent - param may not exist on all models */ }
    },

    // ============================================================
    // STATE TRANSITIONS
    // ============================================================
    startSpeaking() {
        if (!this.model || !this.app) return;
        if (this.isSpeaking) return;
        this.isSpeaking = true;
        console.log('[Avatar] 🗣️ → Speaking state');
    },

    stopSpeaking() {
        if (!this.isSpeaking) return;
        this.isSpeaking = false;
        // Mouth closes smoothly via the animation loop (no abrupt reset)
        console.log('[Avatar] 🗣️ → Idle state');
    },

    setListening(listening) {
        this.isListening = listening;
        console.log('[Avatar]', listening ? '🎤 → Listening state' : '🎤 → End listening');
    },

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
    // AVATAR SWITCHING (smooth fade transition)
    // ============================================================
    async switchAvatar(avatarId) {
        if (!this.avatars[avatarId]) {
            console.error('[Avatar] Unknown avatar ID:', avatarId);
            return;
        }
        if (avatarId === this.currentAvatarId && this.isLoaded) return;

        console.log('[Avatar] 🔄 Switching to:', avatarId);

        // Stop any active states
        this.stopSpeaking();
        this._speakingIntensity = 0;
        this._mouthCurrent = 0;

        // Fade out current avatar
        const container = document.getElementById('avatar-container');
        if (container) container.style.opacity = '0';

        // Show loading state on selector
        this._updateSelectorUI(avatarId, true);

        // Brief delay for fade-out to complete
        await new Promise(r => setTimeout(r, 200));

        // Unload and load
        this.unloadModel();
        this.currentAvatarId = avatarId;

        try {
            await this.loadAvatar(avatarId);

            // Fade in new avatar
            if (container) {
                container.style.transition = 'opacity 0.4s ease';
                container.style.opacity = '1';
            }

            this._updateSelectorUI(avatarId, false);
            console.log('[Avatar] ✓ Switched to:', this.avatars[avatarId].name);
        } catch (e) {
            // Restore visibility even on error
            if (container) container.style.opacity = '1';
            this._updateSelectorUI(avatarId, false);
        }
    },

    async loadAvatar(avatarId) {
        const avatarDef = this.avatars[avatarId];
        if (!avatarDef) throw new Error('Avatar not found: ' + avatarId);

        console.log('[Avatar] Loading:', avatarDef.name);
        try {
            this.model = await PIXI.live2d.Live2DModel.from(avatarDef.modelUrl);
            if (!this.model) throw new Error('Model load returned null');

            // Set initial opacity to 0 (will be faded in by container)
            this.model.alpha = 1;
            this.app.stage.addChild(this.model);
            this.positionModel();
            this.startIdleMotion();

            this.model.interactive = true;
            this.model.buttonMode = true;
            this.model.on('pointerdown', () => this.onTap());

            this.isLoaded = true;
            console.log('[Avatar] ✓ Avatar loaded:', avatarDef.name);
        } catch (error) {
            console.error('[Avatar] Failed to load:', error);
            this.isLoaded = false;
            this.showFallback('Failed to load avatar: ' + avatarDef.name);
        }
    },

    unloadModel() {
        if (this.model) {
            this.model.removeAllListeners();
            this.app.stage.removeChild(this.model);
            this.model.destroy();
            this.model = null;
            this.isLoaded = false;
        }
    },

    positionModel() {
        if (!this.model || !this.app) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        const screenW = this.app.screen.width;
        const screenH = this.app.screen.height;

        // Scale to fill ~90% of container height
        // Using a large multiplier so avatar dominates the right side
        const scaleFactor = avatarDef ? avatarDef.scale : 1.4;
        const targetH = screenH * scaleFactor;
        const scale = targetH / this.model.height;

        this.model.scale.set(scale);

        // Center horizontally
        const modelW = this.model.width * scale;
        this.model.x = (screenW - modelW) / 2;

        // Position: push upward so face is in upper third
        // The model's anchor is top-left, so we offset to get face near top
        const modelH = this.model.height * scale;
        this.model.y = (screenH - modelH) * 0.3;
    },

    startIdleMotion() {
        if (!this.model) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        if (!avatarDef || !avatarDef.idleMotion) return;
        try {
            const mm = this.model.internalModel.motionManager;
            mm.startRandomMotion(avatarDef.idleMotion, PIXI.live2d.MotionPriority.IDLE);
        } catch (e) { /* non-fatal */ }
    },

    onTap() {
        if (!this.model) return;
        const avatarDef = this.avatars[this.currentAvatarId];
        if (!avatarDef || !avatarDef.tapMotion) return;
        try {
            const mm = this.model.internalModel.motionManager;
            mm.startRandomMotion(avatarDef.tapMotion, PIXI.live2d.MotionPriority.NORMAL);
        } catch (e) { /* non-fatal */ }
    },

    _updateSelectorUI(avatarId, isLoading) {
        document.querySelectorAll('.avatar-option').forEach((el) => {
            const isActive = el.dataset.avatar === avatarId;
            el.classList.toggle('active', isActive);
            el.classList.toggle('loading', isActive && isLoading);
            el.disabled = isLoading;
        });
    },

    getAvatarList() {
        return Object.values(this.avatars);
    },

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
