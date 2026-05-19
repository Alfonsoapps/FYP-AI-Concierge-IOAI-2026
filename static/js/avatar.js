/* ============================================================
   Avatar Module - Live2D Integration
   
   Renders a Live2D Cubism2 model (Shizuku) inside #avatar-canvas
   using PixiJS v6 + pixi-live2d-display v0.4.
   
   Required CDN scripts (loaded in index.html BEFORE this file):
   1. pixi.js v6.5.10         → sets window.PIXI
   2. live2d.min.js           → Cubism 2.1 runtime (required for .model.json)
   3. cubism2.min.js          → pixi-live2d-display Cubism2 bundle
                                 → registers PIXI.live2d namespace
   ============================================================ */

const AvatarManager = {
    app: null,      // PixiJS Application
    model: null,    // Live2D model instance
    isLoaded: false,
    isThinking: false,

    // --- Configuration ---
    config: {
        // Shizuku: free Cubism2 model from pixi-live2d-display test assets
        modelUrl: 'https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json',
        canvasId: 'avatar-canvas',
        modelScale: 0.6,  // Height relative to viewport (0.0 - 1.0)
    },

    // ============================================================
    // init() - Entry point
    // ============================================================
    async init() {
        console.log('[Avatar] === Initialization Start ===');

        // --- Dependency checks ---
        if (typeof PIXI === 'undefined') {
            console.error('[Avatar] PIXI is undefined. PixiJS did not load.');
            this.showFallback('PixiJS library failed to load from CDN.');
            return;
        }
        console.log('[Avatar] ✓ PIXI loaded, version:', PIXI.VERSION);

        // Check that window.PIXI is set (pixi-live2d-display needs this)
        if (typeof window.PIXI === 'undefined') {
            console.warn('[Avatar] window.PIXI not set, setting it now...');
            window.PIXI = PIXI;
        }

        // Check Live2D Cubism2 runtime
        if (typeof Live2D === 'undefined' && typeof window.Live2D === 'undefined') {
            console.error('[Avatar] Live2D Cubism2 runtime (live2d.min.js) not loaded.');
            this.showFallback('Live2D Cubism2 runtime failed to load. Check CDN availability.');
            return;
        }
        console.log('[Avatar] ✓ Live2D Cubism2 runtime loaded');

        // Check pixi-live2d-display plugin
        if (!PIXI.live2d) {
            console.error('[Avatar] PIXI.live2d namespace not found.');
            console.error('[Avatar] This means pixi-live2d-display did not register correctly.');
            this.showFallback('pixi-live2d-display plugin failed to register on PIXI.live2d.');
            return;
        }
        console.log('[Avatar] ✓ PIXI.live2d namespace exists');

        if (!PIXI.live2d.Live2DModel) {
            console.error('[Avatar] PIXI.live2d.Live2DModel not found.');
            this.showFallback('PIXI.live2d.Live2DModel is missing.');
            return;
        }
        console.log('[Avatar] ✓ PIXI.live2d.Live2DModel available');

        // --- Create PixiJS Application ---
        try {
            const canvas = document.getElementById(this.config.canvasId);
            if (!canvas) {
                throw new Error('Canvas #' + this.config.canvasId + ' not found in DOM.');
            }
            console.log('[Avatar] ✓ Canvas element found');

            this.app = new PIXI.Application({
                view: canvas,
                autoStart: true,
                resizeTo: window,
                backgroundAlpha: 0,
                antialias: true,
            });
            console.log('[Avatar] ✓ PixiJS Application created (' +
                this.app.screen.width + 'x' + this.app.screen.height + ')');

            // --- Load the Live2D model ---
            await this.loadModel();

            // --- Resize handler ---
            window.addEventListener('resize', () => this.positionModel());

            console.log('[Avatar] === Initialization Complete ===');
        } catch (error) {
            console.error('[Avatar] Initialization error:', error);
            this.showFallback(error.message || String(error));
        }
    },

    // ============================================================
    // loadModel() - Fetches and displays the Live2D model
    // ============================================================
    async loadModel() {
        console.log('[Avatar] Loading model from:', this.config.modelUrl);

        // Load the model (pixi-live2d-display handles fetching all assets)
        this.model = await PIXI.live2d.Live2DModel.from(this.config.modelUrl);

        if (!this.model) {
            throw new Error('Live2DModel.from() returned null');
        }
        console.log('[Avatar] ✓ Model loaded (' +
            Math.round(this.model.width) + 'x' + Math.round(this.model.height) + ')');

        // Add to stage
        this.app.stage.addChild(this.model);
        console.log('[Avatar] ✓ Model added to stage');

        // Position and scale
        this.positionModel();

        // Start idle animation
        this.startIdleMotion();

        // Click interaction
        this.model.interactive = true;
        this.model.buttonMode = true;
        this.model.on('pointerdown', () => this.onTap());

        this.isLoaded = true;
        console.log('[Avatar] ✓ Avatar is live and interactive');
    },

    // ============================================================
    // positionModel() - Centers and scales the model
    // ============================================================
    positionModel() {
        if (!this.model || !this.app) return;

        const screenW = this.app.screen.width;
        const screenH = this.app.screen.height;

        const targetH = screenH * this.config.modelScale;
        const scale = targetH / this.model.height;
        this.model.scale.set(scale);

        // Center horizontally
        this.model.x = (screenW - this.model.width * scale) / 2;

        // Center vertically, shifted up to avoid chat panel overlap
        this.model.y = (screenH - this.model.height * scale) / 2 - screenH * 0.05;
    },

    // ============================================================
    // startIdleMotion() - Starts idle animation loop
    // ============================================================
    startIdleMotion() {
        if (!this.model) return;
        try {
            const mm = this.model.internalModel.motionManager;
            // "idle" is the motion group in shizuku.model.json
            mm.startRandomMotion('idle', PIXI.live2d.MotionPriority.IDLE);
            console.log('[Avatar] ✓ Idle motion started');
        } catch (e) {
            console.warn('[Avatar] Idle motion failed (non-fatal):', e.message);
        }
    },

    // ============================================================
    // onTap() - Tap reaction animation
    // ============================================================
    onTap() {
        if (!this.model) return;
        try {
            const mm = this.model.internalModel.motionManager;
            mm.startRandomMotion('tap_body', PIXI.live2d.MotionPriority.NORMAL);
            console.log('[Avatar] Tap reaction');
        } catch (e) {
            console.warn('[Avatar] Tap motion failed:', e.message);
        }
    },

    // ============================================================
    // setThinking() - Status indicator for AI response wait
    // ============================================================
    setThinking(thinking) {
        this.isThinking = thinking;
        const status = document.getElementById('avatar-status');
        if (thinking) {
            status.innerHTML = '<span class="status-dot"></span> Thinking...';
            status.classList.add('visible');
        } else {
            status.classList.remove('visible');
        }
    },

    // ============================================================
    // Future hooks (placeholders)
    // ============================================================
    setExpression(name) { console.log('[Avatar] Expression (future):', name); },
    triggerMotion(group, index) {
        if (!this.model) return;
        this.model.internalModel.motionManager.startMotion(
            group, index || 0, PIXI.live2d.MotionPriority.FORCE
        );
    },
    startLipSync() { /* Future */ },
    stopLipSync() { /* Future */ },

    // ============================================================
    // showFallback() - Error display
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
