/**
 * QR Code Scanner using browser camera API + jsQR library.
 * Works on all browsers (Safari, DuckDuckGo, Chrome, Firefox).
 * Decodes proshop:// URL scheme and routes to appropriate view.
 */

const Scanner = {
  stream: null,
  videoEl: null,
  canvas: null,
  ctx: null,
  scanning: false,
  animationFrame: null,

  async start(videoElement) {
    this.videoEl = videoElement;
    this.canvas = document.createElement('canvas');
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      this.videoEl.srcObject = this.stream;
      await this.videoEl.play();
      this.scanning = true;
      this._scan();
      return true;
    } catch (err) {
      console.error('Camera access denied:', err);
      return false;
    }
  },

  stop() {
    this.scanning = false;
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.videoEl) {
      this.videoEl.srcObject = null;
    }
  },

  _scan() {
    if (!this.scanning) return;

    if (this.videoEl.readyState === this.videoEl.HAVE_ENOUGH_DATA) {
      this.canvas.width = this.videoEl.videoWidth;
      this.canvas.height = this.videoEl.videoHeight;
      this.ctx.drawImage(this.videoEl, 0, 0);

      const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);

      // Use jsQR (works on all browsers including Safari, DuckDuckGo)
      if (typeof jsQR !== 'undefined') {
        const code = jsQR(imageData.data, imageData.width, imageData.height, {
          inversionAttempts: 'dontInvert',
        });
        if (code && code.data) {
          this._handleResult(code.data);
          return;
        }
      }
    }

    this.animationFrame = requestAnimationFrame(() => this._scan());
  },

  _handleResult(data) {
    this.scanning = false; // Pause scanning after detecting

    // Parse proshop:// URL scheme
    const match = data.match(/^proshop:\/\/(wo|part|op)\/(.+)$/);
    if (match) {
      const [, type, value] = match;
      if (type === 'wo') {
        App.showWorkOrderDetail(value);
      } else if (type === 'part') {
        App.showPartDetail(value);
      } else if (type === 'op') {
        const [woNum, opNum] = value.split('/');
        App.showWorkOrderDetail(woNum);
      }
    } else if (/^\d{2}-\d{4}$/.test(data)) {
      // WO number pattern
      App.showWorkOrderDetail(data);
    } else if (/traxismfg\.adionsystems\.com/i.test(data)) {
      // ProShop URL — route to in-app view
      this._handleProShopUrl(data);
    } else if (/^https?:\/\//i.test(data)) {
      // External URL — open it directly
      window.open(data, '_blank', 'noopener');
      App.showScanResult(data);
    } else {
      // Show the raw scanned text
      App.showScanResult(data);
    }
  },

  _handleProShopUrl(url) {
    // Extract WO number: /procnc/workorders/YEAR/WO-NUMBER or just WO pattern in URL
    const woMatch = url.match(/(\d{2}-\d{4})/);
    // Extract part number: /procnc/parts/PREFIX/PART-NUMBER or /procnc/ots/PREFIX/PART-NUMBER
    const partMatch = url.match(/\/procnc\/(?:parts|ots)\/[^/]+\/([^/$?]+)/);

    if (partMatch) {
      App.showPartDetail(partMatch[1]);
    } else if (woMatch) {
      App.showWorkOrderDetail(woMatch[1]);
    } else {
      // Can't parse — show with open button
      App.showScanResult(data);
    }
  },

  parseProShopUrl(url) {
    const match = url.match(/^proshop:\/\/(wo|part|op)\/(.+)$/);
    if (!match) return null;
    return { type: match[1], value: match[2] };
  }
};
