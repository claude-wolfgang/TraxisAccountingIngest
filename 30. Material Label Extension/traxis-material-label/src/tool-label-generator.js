const ToolLabelGenerator = (() => {
  const HEIGHT = 128;
  const MARGIN = 6;
  const QR_SIZE = HEIGHT - MARGIN * 2;
  const MAX_TEXT_WIDTH = 400;

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

  function generate(data) {
    const qr = qrcode(0, 'M');
    qr.addData(data.url);
    qr.make();

    const moduleCount = qr.getModuleCount();
    const cellSize = Math.floor(QR_SIZE / moduleCount);
    const qrPixels = cellSize * moduleCount;

    const textLeft = MARGIN + qrPixels + MARGIN;

    const measure = document.createElement('canvas').getContext('2d');

    const FONT_TOOL = 'bold 30px Arial, sans-serif';
    const FONT_DESC = '20px Arial, sans-serif';
    const FONT_LOC = '14px Arial, sans-serif';
    const LINE_HEIGHT_TOOL = 36;
    const LINE_HEIGHT_DESC = 26;
    const LINE_HEIGHT_LOC = 18;

    measure.font = FONT_DESC;
    const descLines = wrapText(measure, data.description || '', MAX_TEXT_WIDTH);

    const lines = [];
    lines.push({ text: data.toolNumber || '', font: FONT_TOOL, height: LINE_HEIGHT_TOOL });
    for (const dl of descLines) {
      lines.push({ text: dl, font: FONT_DESC, height: LINE_HEIGHT_DESC });
    }
    if (data.location) {
      lines.push({ text: data.location, font: FONT_LOC, height: LINE_HEIGHT_LOC });
    }

    let maxTextWidth = 0;
    for (const line of lines) {
      measure.font = line.font;
      const w = measure.measureText(line.text).width;
      if (w > maxTextWidth) maxTextWidth = w;
    }

    const totalWidth = textLeft + Math.ceil(maxTextWidth) + MARGIN;

    const canvas = document.createElement('canvas');
    canvas.width = totalWidth;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, totalWidth, HEIGHT);

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

    ctx.fillStyle = '#000000';
    ctx.textBaseline = 'top';

    const totalTextHeight = lines.reduce((sum, l) => sum + l.height, 0);
    let y = Math.max(MARGIN, Math.floor((HEIGHT - totalTextHeight) / 2));

    for (const line of lines) {
      ctx.font = line.font;
      ctx.fillText(line.text, textLeft, y);
      y += line.height;
    }

    const dataUrl = canvas.toDataURL('image/png');
    return dataUrl.replace(/^data:image\/png;base64,/, '');
  }

  return { generate };
})();
