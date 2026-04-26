const EquipmentLabelGenerator = (() => {
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

    const FONT_EQUIP = 'bold 36px Arial, sans-serif';
    const FONT_NAME = '24px Arial, sans-serif';
    const FONT_SERIAL = '14px Arial, sans-serif';
    const LINE_HEIGHT_EQUIP = 42;
    const LINE_HEIGHT_NAME = 30;
    const LINE_HEIGHT_SERIAL = 20;

    measure.font = FONT_NAME;
    const nameLines = wrapText(measure, data.toolName || '', MAX_TEXT_WIDTH);

    const lines = [];
    lines.push({ text: data.equipmentNumber || '', font: FONT_EQUIP, height: LINE_HEIGHT_EQUIP });
    for (const nl of nameLines) {
      lines.push({ text: nl, font: FONT_NAME, height: LINE_HEIGHT_NAME });
    }
    if (data.serialNumber) {
      lines.push({ text: data.serialNumber, font: FONT_SERIAL, height: LINE_HEIGHT_SERIAL });
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
