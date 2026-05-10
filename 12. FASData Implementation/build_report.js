/**
 * FASData Utilization Report — DOCX Builder
 * Reads report_data.json + chart PNGs and produces a formatted Word document.
 *
 * Usage: node build_report.js
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat
} = require("docx");

const ASSETS = path.join(__dirname, "report_assets");
const data = JSON.parse(fs.readFileSync(path.join(ASSETS, "report_data.json"), "utf8"));

// ── Helpers ──────────────────────────────────────────────────────────────────

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

function headerCell(text, widthDxa) {
  return new TableCell({
    borders,
    width: { size: widthDxa, type: WidthType.DXA },
    shading: { fill: "1B3A5C", type: ShadingType.CLEAR },
    margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })]
    })]
  });
}

function dataCell(text, widthDxa, opts = {}) {
  const { bold, color, align, fill } = opts;
  return new TableCell({
    borders,
    width: { size: widthDxa, type: WidthType.DXA },
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({
      alignment: align || AlignmentType.CENTER,
      children: [new TextRun({
        text: String(text),
        bold: bold || false,
        color: color || "333333",
        font: "Arial",
        size: 20
      })]
    })]
  });
}

function statusColor(status) {
  switch (status) {
    case "GREEN":  return { text: "2E7D32", fill: "E8F5E9" };
    case "YELLOW": return { text: "F57F17", fill: "FFF8E1" };
    case "RED":    return { text: "C62828", fill: "FFEBEE" };
    case "OFFLINE": return { text: "757575", fill: "F5F5F5" };
    default:       return { text: "757575", fill: "F5F5F5" };
  }
}

function statusLabel(status) {
  switch (status) {
    case "GREEN":  return "\u2705 On Target";
    case "YELLOW": return "\u26A0\uFE0F Below Target";
    case "RED":    return "\u274C Critical";
    case "OFFLINE": return "\u2014 Offline";
    default:       return "\u2014";
  }
}

// ── Format dates nicely ─────────────────────────────────────────────────────

const startParts = data.date_start.split("-");
const endParts = data.date_end.split("-");
const startDate = new Date(startParts[0], startParts[1] - 1, startParts[2]);
const endDate = new Date(endParts[0], endParts[1] - 1, endParts[2]);
const dateOpts = { weekday: "short", month: "short", day: "numeric", year: "numeric" };
const prettyStart = startDate.toLocaleDateString("en-US", dateOpts);
const prettyEnd = endDate.toLocaleDateString("en-US", dateOpts);
const dateRange = `${prettyStart} — ${prettyEnd}`;

// ── Build sections ──────────────────────────────────────────────────────────

const children = [];

// Title block
children.push(new Paragraph({ spacing: { after: 80 }, children: [] }));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 40 },
  children: [new TextRun({ text: "TRAXIS MANUFACTURING", font: "Arial", size: 22, color: "777777", bold: true })]
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 80 },
  children: [new TextRun({ text: "Machine Utilization Report", font: "Arial", size: 40, bold: true, color: "1B3A5C" })]
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 200 },
  children: [new TextRun({ text: dateRange, font: "Arial", size: 24, color: "555555" })]
}));

// Divider line
children.push(new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: "1B3A5C" } },
  spacing: { after: 300 },
  children: []
}));

// ── Executive Summary ───────────────────────────────────────────────────────

children.push(new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun("Executive Summary")]
}));

const summaryText = `During the reporting period (${data.num_days} working days), ` +
  `${data.active_machine_count} of ${data.total_machine_count} monitored CNC machines were active. ` +
  `The shop achieved an average utilization of ${data.shop_avg_utilization}% across active machines ` +
  `(based on actual cutting time — spindle warmup and air spinning are excluded). ` +
  `Machines logged ${data.total_hours_cutting || 0} cutting hours and ${((data.total_hours_running || 0) - (data.total_hours_cutting || 0)).toFixed(1)} spindle-only hours ` +
  `out of ${data.total_hours_available} available hours during shift time (${data.shift_hours}).`;

children.push(new Paragraph({
  spacing: { after: 120 },
  children: [new TextRun({ text: summaryText, font: "Arial", size: 22, color: "333333" })]
}));

// Key metrics summary table (compact)
const col1W = 2400;
const col2W = 1300;
const col3W = 2400;
const col4W = 1300;
const metricsW = col1W + col2W + col3W + col4W;

children.push(new Paragraph({ spacing: { before: 120, after: 120 }, children: [] }));
children.push(new Table({
  width: { size: metricsW, type: WidthType.DXA },
  columnWidths: [col1W, col2W, col3W, col4W],
  rows: [
    new TableRow({ children: [
      dataCell("Shop Utilization:", col1W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`${data.shop_avg_utilization}%`, col2W, { bold: true, color: "1B3A5C" }),
      dataCell("Active Machines:", col3W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`${data.active_machine_count} of ${data.total_machine_count}`, col4W, { bold: true, color: "1B3A5C" }),
    ]}),
    new TableRow({ children: [
      dataCell("Hours Cutting:", col1W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`${data.total_hours_cutting || 0}h`, col2W, { bold: true, color: "1B3A5C" }),
      dataCell("Hours Running:", col3W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`${data.total_hours_running}h`, col4W, { bold: true, color: "1B3A5C" }),
    ]}),
    new TableRow({ children: [
      dataCell("Hours Available:", col1W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`${data.total_hours_available}h`, col2W, { bold: true, color: "1B3A5C" }),
      dataCell("Active Machines:", col3W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`${data.active_machine_count} of ${data.total_machine_count}`, col4W, { bold: true, color: "1B3A5C" }),
    ]}),
    new TableRow({ children: [
      dataCell("Green Target:", col1W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`\u2265 ${data.green_threshold}%`, col2W),
      dataCell("Warning Below:", col3W, { bold: true, align: AlignmentType.RIGHT }),
      dataCell(`< ${data.yellow_threshold}%`, col4W),
    ]}),
  ]
}));

// ── Utilization Bar Chart ───────────────────────────────────────────────────

children.push(new Paragraph({ spacing: { before: 300 }, children: [new PageBreak()] }));

children.push(new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun("Utilization by Machine")]
}));

const barImg = fs.readFileSync(path.join(ASSETS, "utilization_bar.png"));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 200 },
  children: [new ImageRun({
    type: "png",
    data: barImg,
    transformation: { width: 580, height: 326 },
    altText: { title: "Utilization Bar Chart", description: "Bar chart showing utilization percentage per machine", name: "utilization_bar" }
  })]
}));

// ── Detailed Machine Table ──────────────────────────────────────────────────

children.push(new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun("Detailed Breakdown")]
}));

const tw = 9360; // full content width
const cw = [700, 1300, 1100, 1100, 1100, 1100, 1100, 1750]; // ID, Name, Cutting%, Spindle%, Total%, HrsRun, HrsAvail, Status

const machineIds = Object.keys(data.machines).sort();
const tableRows = [
  new TableRow({ children: [
    headerCell("ID", cw[0]),
    headerCell("Machine", cw[1]),
    headerCell("Cutting", cw[2]),
    headerCell("Spindle", cw[3]),
    headerCell("Total", cw[4]),
    headerCell("Running", cw[5]),
    headerCell("Available", cw[6]),
    headerCell("Status", cw[7]),
  ]})
];

for (const mid of machineIds) {
  const m = data.machines[mid];
  const sc = statusColor(m.status);
  tableRows.push(new TableRow({ children: [
    dataCell(mid, cw[0], { bold: true }),
    dataCell(m.name, cw[1], { align: AlignmentType.LEFT }),
    dataCell(`${m.cutting_pct || 0}%`, cw[2], { bold: true, color: "1565C0" }),
    dataCell(`${m.spindle_only_pct || 0}%`, cw[3], { color: "90CAF9" }),
    dataCell(`${m.utilization_pct}%`, cw[4], { bold: true, color: sc.text }),
    dataCell(`${m.hours_running}h`, cw[5]),
    dataCell(`${m.hours_available}h`, cw[6]),
    dataCell(statusLabel(m.status), cw[7], { fill: sc.fill, color: sc.text }),
  ]}));
}

children.push(new Table({
  width: { size: tw, type: WidthType.DXA },
  columnWidths: cw,
  rows: tableRows,
}));

// ── Daily Trend Chart ───────────────────────────────────────────────────────

const trendPath = path.join(ASSETS, "utilization_trend.png");
if (fs.existsSync(trendPath)) {
  children.push(new Paragraph({ spacing: { before: 300 }, children: [new PageBreak()] }));

  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun("Daily Utilization Trend")]
  }));

  const trendImg = fs.readFileSync(trendPath);
  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new ImageRun({
      type: "png",
      data: trendImg,
      transformation: { width: 580, height: 326 },
      altText: { title: "Daily Trend", description: "Line chart showing daily utilization trend per machine", name: "utilization_trend" }
    })]
  }));

  // Daily data table
  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun("Daily Figures")]
  }));

  const days = Object.keys(data.daily).sort();
  const activeMachines = machineIds.filter(m => data.machines[m].status !== "OFFLINE" && data.machines[m].status !== "NO DATA");
  const dcw0 = 1600; // date column
  const dcwMachine = Math.floor((tw - dcw0) / activeMachines.length);
  const dailyColWidths = [dcw0, ...activeMachines.map(() => dcwMachine)];

  const dailyRows = [
    new TableRow({ children: [
      headerCell("Date", dcw0),
      ...activeMachines.map(mid => headerCell(mid, dcwMachine))
    ]})
  ];

  for (const day of days) {
    const dayDate = new Date(day + "T12:00:00");
    const dayLabel = dayDate.toLocaleDateString("en-US", { weekday: "short", month: "numeric", day: "numeric" });
    dailyRows.push(new TableRow({ children: [
      dataCell(dayLabel, dcw0, { bold: true }),
      ...activeMachines.map(mid => {
        const dayData = data.daily[day][mid];
        // Handle both old format (number) and new format (object with running/cutting)
        const val = typeof dayData === "object" ? (dayData.running || 0) : (dayData || 0);
        const cutVal = typeof dayData === "object" ? (dayData.cutting || 0) : null;
        const sc = statusColor(
          val >= data.green_threshold ? "GREEN" : val >= data.yellow_threshold ? "YELLOW" : "RED"
        );
        const label = cutVal !== null ? `${cutVal}% / ${val}%` : `${val}%`;
        return dataCell(label, dcwMachine, { color: sc.text, fill: sc.fill });
      })
    ]}));
  }

  children.push(new Table({
    width: { size: tw, type: WidthType.DXA },
    columnWidths: dailyColWidths,
    rows: dailyRows,
  }));
}

// ── Hours Breakdown Chart ───────────────────────────────────────────────────

const hoursPath = path.join(ASSETS, "hours_breakdown.png");
if (fs.existsSync(hoursPath)) {
  children.push(new Paragraph({ spacing: { before: 300 }, children: [new PageBreak()] }));

  children.push(new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun("Running vs. Idle Hours")]
  }));

  const hoursImg = fs.readFileSync(hoursPath);
  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new ImageRun({
      type: "png",
      data: hoursImg,
      transformation: { width: 580, height: 290 },
      altText: { title: "Hours Breakdown", description: "Stacked bar showing running vs idle hours", name: "hours_breakdown" }
    })]
  }));
}

// ── Notes & Methodology ─────────────────────────────────────────────────────

children.push(new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun("Notes & Methodology")]
}));

const notes = [
  `Data collected via FOCAS2 protocol, polling each machine every 60 seconds from collector PC (WrkStationC).`,
  `Utilization is defined as the percentage of shift-hour samples where the machine spindle speed > 0 or run status = STRT/MSTR.`,
  `Shift hours: ${data.shift_hours}, Monday through Friday.`,
  `M3 (FANUC Mill 3) is currently offline due to a failed Ethernet adapter. A USB-to-Ethernet replacement is on order.`,
  `Machines M4, M5, and M7 (Robodrills) are not yet connected to the monitoring network.`,
  `M1 (Haas Classic) uses a proprietary protocol and is not FOCAS-compatible.`,
];

for (const note of notes) {
  children.push(new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text: note, font: "Arial", size: 20, color: "555555" })]
  }));
}

// ── Build Document ──────────────────────────────────────────────────────────

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "1B3A5C" },
        paragraph: { spacing: { before: 300, after: 160 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E5984" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 }
      },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [
            new TextRun({ text: "Traxis Manufacturing — FASData Utilization Report", font: "Arial", size: 16, color: "999999" })
          ]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: "Page ", font: "Arial", size: 16, color: "999999" }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" }),
            new TextRun({ text: "  |  Generated " + new Date().toLocaleDateString("en-US"), font: "Arial", size: 16, color: "999999" }),
          ]
        })]
      })
    },
    children
  }]
});

// ── Write File ──────────────────────────────────────────────────────────────

Packer.toBuffer(doc).then(buffer => {
  const outPath = path.join(__dirname, "FASData_Utilization_Report.docx");
  fs.writeFileSync(outPath, buffer);
  console.log(`✓ Report saved: ${outPath}`);
});
