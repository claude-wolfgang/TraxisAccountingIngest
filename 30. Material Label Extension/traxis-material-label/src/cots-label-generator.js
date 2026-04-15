/**
 * COTS Label Generator — renders a 128px-tall, 450px-wide PNG label via Canvas.
 *
 * Layout matches P17 Python generator:
 *   [QR 116x116] | THI-219               (bold 48px)
 *                | M4 X 0.7 x 6 304SS    (28px, wraps to 2 lines)
 *                | TANGLESS THREAD INSERT
 *
 * 128px height / 180 DPI = 24mm tape on Brother PT-P700.
 * Fixed 450px width = 2.5" label.
 * Renders at 2x and downsamples for crisp text.
 */

const COTSLabelGenerator = (() => {
  const HEIGHT = 128;
  const WIDTH = 450;
  const MARGIN = 6;
  const QR_SIZE = HEIGHT - MARGIN * 2; // 116px
  const S = 2; // supersample factor

  /**
   * Word-wrap text to fit within maxWidth pixels.
   * @returns {string[]} array of lines
   */
  function wrapText(ctx, text, maxWidth) {
    const words = text.split(/\s+/);
    const lines = [];
    let current = '';
    for (const word of words) {
      const test = current ? `${current} ${word}` : word;
      if (ctx.measureText(test).width <= maxWidth) {
        current = test;
      } else {
        if (current) lines.push(current);
        current = ctx.measureText(word).width > maxWidth
          ? truncateText(ctx, word, maxWidth)
          : word;
      }
    }
    if (current) lines.push(current);
    return lines;
  }

  function truncateText(ctx, text, maxWidth) {
    while (text.length > 1) {
      text = text.slice(0, -1);
      if (ctx.measureText(text + '...').width <= maxWidth) {
        return text + '...';
      }
    }
    return text;
  }

  /**
   * Generate a COTS label as base64 PNG (no data: prefix).
   * @param {Object} data
   * @param {string} data.cotsId    - e.g. "THI-219"
   * @param {string} data.description - e.g. "M4 X 0.7 x 6 304SS TANGLESS THREAD INSERT"
   * @param {string} data.url       - full ProShop URL for QR code
   * @returns {string} base64 PNG
   */
  function generate(data) {
    // --- QR code ---
    const qr = qrcode(0, 'M');
    qr.addData(data.url);
    qr.make();

    const moduleCount = qr.getModuleCount();
    const cellSize = Math.floor((QR_SIZE * S) / moduleCount);
    const qrPixels = cellSize * moduleCount;

    // --- Hi-res canvas (2x) ---
    const canvas = document.createElement('canvas');
    canvas.width = WIDTH * S;
    canvas.height = HEIGHT * S;
    const ctx = canvas.getContext('2d');

    // White background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // QR code, vertically centered
    const qrX = MARGIN * S;
    const qrY = Math.floor((HEIGHT * S - qrPixels) / 2);
    ctx.fillStyle = '#000000';
    for (let row = 0; row < moduleCount; row++) {
      for (let col = 0; col < moduleCount; col++) {
        if (qr.isDark(row, col)) {
          ctx.fillRect(qrX + col * cellSize, qrY + row * cellSize, cellSize, cellSize);
        }
      }
    }

    // Text area
    const textX = (MARGIN + QR_SIZE + MARGIN) * S;
    const textAreaW = canvas.width - textX - MARGIN * S;
    ctx.fillStyle = '#000000';
    ctx.textBaseline = 'top';

    // COTS ID — bold 48px
    ctx.font = `bold ${48 * S}px Arial, sans-serif`;
    ctx.fillText(data.cotsId, textX, 2 * S);

    // Description — 28px, word-wrapped, max 2 lines
    ctx.font = `${28 * S}px Arial, sans-serif`;
    let descLines = wrapText(ctx, data.description || '', textAreaW);
    if (descLines.length > 2) {
      descLines = descLines.slice(0, 2);
      descLines[1] = truncateText(ctx, descLines[1], textAreaW);
    }

    let descY = 56 * S;
    const lineSpacing = 32 * S;
    for (const line of descLines) {
      ctx.fillText(line, textX, descY);
      descY += lineSpacing;
    }

    // --- Downsample to output resolution ---
    const out = document.createElement('canvas');
    out.width = WIDTH;
    out.height = HEIGHT;
    const outCtx = out.getContext('2d');
    outCtx.imageSmoothingEnabled = true;
    outCtx.imageSmoothingQuality = 'high';
    outCtx.drawImage(canvas, 0, 0, WIDTH, HEIGHT);

    const dataUrl = out.toDataURL('image/png');
    return dataUrl.replace(/^data:image\/png;base64,/, '');
  }

  return { generate };
})();
