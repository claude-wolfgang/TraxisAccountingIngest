/**
 * Label Generator — renders a 128px-tall PNG label via Canvas API.
 *
 * Layout matches P9 WO label convention:
 *   [QR 116x116] | WO 26-0120                          (bold 36px)
 *                | Stainless Steel 316 Hexagonal Bar    (24px, wraps)
 *                | 55500096                             (14px)
 *
 * 128px height / 180 DPI = 24mm tape on Brother PT-P700.
 */

const LabelGenerator = (() => {
  const HEIGHT = 128;
  const MARGIN = 6;
  const QR_SIZE = HEIGHT - MARGIN * 2; // 116px
  const MAX_TEXT_WIDTH = 400; // max width for text area before wrapping

  /**
   * Word-wrap text to fit within maxWidth at the given font.
   * Returns an array of line strings.
   */
  function wrapText(ctx, text, maxWidth) {
    const words = text.split(/\s+/);
    const lines = [];
    let current = '';

    for (const word of words) {
      const test = current ? current + ' ' + word : word;
      if (ctx.measureText(test).width > maxWidth && current) {
        lines.push(current);
        current = word;
      } else {
        current = test;
      }
    }
    if (current) lines.push(current);
    return lines;
  }

  /**
   * Generate a label as a base64-encoded PNG string (no data: prefix).
   * @param {Object} data
   * @param {string} data.woNumber   - e.g. "26-0120"
   * @param {string} data.material   - e.g. "Stainless Steel 316 Hexagonal Bar"
   * @param {string} data.partNumber - e.g. "55500096"
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

    const textLeft = MARGIN + qrPixels + MARGIN;

    // --- Build wrapped lines ---
    const measure = document.createElement('canvas').getContext('2d');

    const FONT_WO = 'bold 36px Arial, sans-serif';
    const FONT_MATERIAL = '24px Arial, sans-serif';
    const FONT_PART = '14px Arial, sans-serif';
    const LINE_HEIGHT_WO = 42;
    const LINE_HEIGHT_MATERIAL = 30;
    const LINE_HEIGHT_PART = 20;

    // Wrap material text
    measure.font = FONT_MATERIAL;
    const materialLines = wrapText(measure, data.material || 'Unknown material', MAX_TEXT_WIDTH);

    // Build final line list with fonts and heights
    const lines = [];
    lines.push({ text: `WO ${data.woNumber}`, font: FONT_WO, height: LINE_HEIGHT_WO });
    for (const ml of materialLines) {
      lines.push({ text: ml, font: FONT_MATERIAL, height: LINE_HEIGHT_MATERIAL });
    }
    if (data.partNumber) {
      lines.push({ text: data.partNumber, font: FONT_PART, height: LINE_HEIGHT_PART });
    }

    // --- Measure max width ---
    let maxTextWidth = 0;
    for (const line of lines) {
      measure.font = line.font;
      const w = measure.measureText(line.text).width;
      if (w > maxTextWidth) maxTextWidth = w;
    }

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

    // Text lines — vertically centered as a group
    ctx.fillStyle = '#000000';
    ctx.textBaseline = 'top';

    const totalTextHeight = lines.reduce((sum, l) => sum + l.height, 0);
    let y = Math.max(MARGIN, Math.floor((HEIGHT - totalTextHeight) / 2));

    for (const line of lines) {
      ctx.font = line.font;
      ctx.fillText(line.text, textLeft, y);
      y += line.height;
    }

    // Export as base64 PNG (strip the data:image/png;base64, prefix)
    const dataUrl = canvas.toDataURL('image/png');
    return dataUrl.replace(/^data:image\/png;base64,/, '');
  }

  return { generate };
})();
