/**
 * Label Generator — renders a 128px-tall PNG label via Canvas API.
 *
 * Layout matches P9 WO label convention:
 *   [QR 116x116] | WO 26-0120        (bold 36px)
 *                | 6061-T6 Aluminum   (18px)
 *                | PART-1234          (14px)
 *                | Qty: 5 remaining   (14px)
 *
 * 128px height / 180 DPI = 24mm tape on Brother PT-P700.
 */

const LabelGenerator = (() => {
  const HEIGHT = 128;
  const MARGIN = 6;
  const QR_SIZE = HEIGHT - MARGIN * 2; // 116px

  /**
   * Generate a label as a base64-encoded PNG string (no data: prefix).
   * @param {Object} data
   * @param {string} data.woNumber   - e.g. "26-0120"
   * @param {string} data.material   - e.g. "6061-T6 Aluminum"
   * @param {string} data.partNumber - e.g. "PART-1234"
   * @param {string} data.quantity   - e.g. "5 remaining"
   * @returns {string} base64 PNG
   */
  function generate(data) {
    // --- Build QR code ---
    const qr = qrcode(0, 'M');
    qr.addData(`proshop://wo/${data.woNumber}`);
    qr.make();

    const moduleCount = qr.getModuleCount();
    const cellSize = Math.floor(QR_SIZE / moduleCount);
    const qrPixels = cellSize * moduleCount;

    // --- Measure text to determine canvas width ---
    const measure = document.createElement('canvas').getContext('2d');

    const lines = [
      { text: `WO ${data.woNumber}`, font: 'bold 36px Arial, sans-serif' },
      { text: data.material || 'Unknown material', font: '18px Arial, sans-serif' },
      { text: data.partNumber || '', font: '14px Arial, sans-serif' },
      { text: data.quantity ? `Qty: ${data.quantity}` : '', font: '14px Arial, sans-serif' },
    ].filter(l => l.text);

    let maxTextWidth = 0;
    for (const line of lines) {
      measure.font = line.font;
      const w = measure.measureText(line.text).width;
      if (w > maxTextWidth) maxTextWidth = w;
    }

    const textLeft = MARGIN + qrPixels + MARGIN;
    const totalWidth = textLeft + Math.ceil(maxTextWidth) + MARGIN;

    // --- Draw label ---
    const canvas = document.createElement('canvas');
    canvas.width = totalWidth;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext('2d');

    // White background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, totalWidth, HEIGHT);

    // QR code
    const qrOffsetX = MARGIN;
    const qrOffsetY = MARGIN + Math.floor((QR_SIZE - qrPixels) / 2);
    ctx.fillStyle = '#000000';
    for (let row = 0; row < moduleCount; row++) {
      for (let col = 0; col < moduleCount; col++) {
        if (qr.isDark(row, col)) {
          ctx.fillRect(
            qrOffsetX + col * cellSize,
            qrOffsetY + row * cellSize,
            cellSize,
            cellSize
          );
        }
      }
    }

    // Text lines
    ctx.fillStyle = '#000000';
    ctx.textBaseline = 'top';

    // Position text lines vertically centered as a group
    const lineHeights = [42, 24, 20, 20]; // approximate line spacing
    const usedLines = lines.length;
    const totalTextHeight = lineHeights.slice(0, usedLines).reduce((a, b) => a + b, 0);
    let y = Math.max(MARGIN, Math.floor((HEIGHT - totalTextHeight) / 2));

    for (let i = 0; i < lines.length; i++) {
      ctx.font = lines[i].font;
      ctx.fillText(lines[i].text, textLeft, y);
      y += lineHeights[i];
    }

    // Export as base64 PNG (strip the data:image/png;base64, prefix)
    const dataUrl = canvas.toDataURL('image/png');
    return dataUrl.replace(/^data:image\/png;base64,/, '');
  }

  return { generate };
})();
