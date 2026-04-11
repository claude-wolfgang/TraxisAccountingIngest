/**
 * Part Counter — Camera-based part counting using Claude Vision.
 * Captures a frame from the camera, sends to backend, overlays count.
 */

const Counter = {
  stream: null,
  videoEl: null,
  canvas: null,
  ctx: null,
  autoInterval: null,
  counting: false,

  async start(videoElement) {
    this.videoEl = videoElement;
    this.canvas = document.createElement('canvas');
    this.ctx = this.canvas.getContext('2d');

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      this.videoEl.srcObject = this.stream;
      await this.videoEl.play();
      return true;
    } catch (err) {
      console.error('Camera access denied:', err);
      return false;
    }
  },

  stop() {
    this.stopAuto();
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.videoEl) {
      this.videoEl.srcObject = null;
    }
  },

  captureFrame() {
    if (!this.videoEl || this.videoEl.readyState < this.videoEl.HAVE_ENOUGH_DATA) {
      return null;
    }
    // Cap at 1280x720 for reasonable payload size
    const w = Math.min(this.videoEl.videoWidth, 1280);
    const h = Math.min(this.videoEl.videoHeight, 720);
    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx.drawImage(this.videoEl, 0, 0, w, h);
    // JPEG at 0.8 quality → ~150KB base64
    return this.canvas.toDataURL('image/jpeg', 0.8);
  },

  async count() {
    if (this.counting) return;
    this.counting = true;

    const overlay = document.getElementById('count-overlay');
    const countBtn = document.getElementById('count-btn');
    if (countBtn) countBtn.disabled = true;

    // Show spinner
    if (overlay) {
      overlay.className = 'count-overlay visible counting';
      overlay.innerHTML = '<div class="count-spinner"></div>';
    }

    const frame = this.captureFrame();
    if (!frame) {
      if (overlay) {
        overlay.className = 'count-overlay visible error';
        overlay.innerHTML = '<div class="count-number">?</div><div class="count-label">Camera not ready</div>';
      }
      this.counting = false;
      if (countBtn) countBtn.disabled = false;
      return;
    }

    const contextInput = document.getElementById('count-context');
    const context = contextInput ? contextInput.value.trim() : '';

    try {
      const result = await API.countParts(frame, context);

      if (overlay) {
        if (result.error) {
          overlay.className = 'count-overlay visible error';
          overlay.innerHTML = `<div class="count-number">!</div><div class="count-label">${result.error}</div>`;
        } else {
          const confClass = result.confidence || 'low';
          overlay.className = `count-overlay visible ${confClass}`;
          overlay.innerHTML = `
            <div class="count-number">${result.count}</div>
            <div class="count-label">${result.description || 'parts counted'}</div>
            <div class="count-confidence">${confClass} confidence</div>
          `;
        }
      }
    } catch (err) {
      if (overlay) {
        overlay.className = 'count-overlay visible error';
        overlay.innerHTML = `<div class="count-number">!</div><div class="count-label">${err.message}</div>`;
      }
    }

    this.counting = false;
    if (countBtn) countBtn.disabled = false;
  },

  startAuto() {
    if (this.autoInterval) return;
    this.count(); // Count immediately
    this.autoInterval = setInterval(() => this.count(), 5000);
  },

  stopAuto() {
    if (this.autoInterval) {
      clearInterval(this.autoInterval);
      this.autoInterval = null;
    }
  },

  isAutoRunning() {
    return this.autoInterval !== null;
  },
};
