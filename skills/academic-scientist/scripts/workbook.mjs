// Render one literature baseline. Dependencies must come from an existing bundled runtime.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import crypto from 'node:crypto';

const [baselinePath, runtimeDir] = process.argv.slice(2);
if (!baselinePath || !runtimeDir) throw new Error('Usage: workbook.mjs baseline.json runtime-directory');
const require = createRequire(path.join(path.resolve(runtimeDir), 'package.json'));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const baselineBytes = await fs.readFile(baselinePath);
const bundle = JSON.parse(baselineBytes.toString('utf8'));
const outputDir = path.dirname(path.resolve(baselinePath));
const outputPath = path.join(outputDir, 'literature.xlsx');
const sealPath = path.join(outputDir, 'workbook-seal.json');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const exists = async file => { try { await fs.access(file); return true; } catch { return false; } };
const buildHash = hash(await fs.readFile(new URL(import.meta.url)));
if (await exists(outputPath)) {
  if (!(await exists(sealPath))) throw new Error('Existing workbook lacks a seal; preserve it and inspect interrupted output');
  const seal = JSON.parse(await fs.readFile(sealPath, 'utf8'));
  if (seal.baseline_sha256 !== hash(baselineBytes) || seal.workbook_sha256 !== hash(await fs.readFile(outputPath)))
    throw new Error('Preserve manually modified workbook; import edits and prepare a new revision');
  if (seal.builder_sha256 !== buildHash) throw new Error('Builder changed; prepare a new export version instead of overwriting');
  console.log(JSON.stringify({ path: outputPath, reused: true }));
  process.exit(0);
}

const wb = Workbook.create();
const colName = index => { let s = ''; for (let n = index + 1; n > 0; n = Math.floor((n-1)/26)) s = String.fromCharCode(65+(n-1)%26) + s; return s; };
const textValue = v => typeof v === 'string' && /^[=+@-]/.test(v) ? "'" + v : v;
const inspections = [];
for (const [index, spec] of bundle.sheets.entries()) {
  const sheet = wb.worksheets.add(spec.name);
  const values = [spec.header, ...spec.rows].map(row => row.map(textValue));
  const last = colName(spec.header.length - 1);
  const range = sheet.getRange(`A1:${last}${values.length}`);
  range.values = values;
  range.format.font = { name: 'Arial', size: 11, color: '#1F2937' };
  range.format.wrapText = true;
  range.format.verticalAlignment = 'top';
  sheet.showGridLines = false;
  sheet.getRange(`A1:${last}1`).format = { fill: '#34495E', font: { name: 'Arial', size: 11, color: '#FFFFFF', bold: true }, wrapText: true, rowHeight: 34 };
  for (const [col, width] of spec.widths.entries()) sheet.getRange(`${colName(col)}1:${colName(col)}${values.length}`).format.columnWidth = width;
  if (values.length > 1) {
    const table = sheet.tables.add(`A1:${last}${values.length}`, true, `LiteratureTable${index+1}`);
    table.showFilterButton = true;
    for (const col of spec.editable) sheet.getRange(`${colName(col)}2:${colName(col)}${values.length}`).format.fill = '#FFF4D6';
    // Long prose remains fully visible with wrapped rows. Refuse beyond Excel's display limits.
    for (let r = 1; r < values.length; r++) {
      let lines = 1;
      for (let c = 0; c < values[r].length; c++) {
        const text = String(values[r][c] ?? '');
        if (text.length > 32767) throw new Error('Cell exceeds Excel text limit; split the source assertion before exporting');
        const estimated = text.split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil([...line].reduce((n,ch) => n+(ch.charCodeAt(0)>255 ? 2 : 1),0)/(spec.widths[c]*0.85))), 0);
        lines = Math.max(lines, estimated);
      }
      const height = Math.max(28, lines * 15 + 10);
      if (height > 405) throw new Error('Row exceeds readable Excel height; split the source assertion before exporting');
      sheet.getRange(`A${r+1}:${last}${r+1}`).format.rowHeight = height;
    }
  }
  if (values.length > 12) sheet.freezePanes.freezeRows(1);
  if (spec.name === '论文总览') sheet.getRange(`D2:D${values.length}`).setNumberFormat('0');
  if (spec.name === '原文证据') sheet.getRange(`E2:E${values.length}`).setNumberFormat('0');
  if (spec.name === '平台认知') sheet.getRange(`F2:F${values.length}`).setNumberFormat('0');
  const check = await wb.inspect({kind:'table', range:`'${spec.name}'!A1:${last}${Math.min(values.length,4)}`, include:'values,formulas', tableMaxRows:4, tableMaxCols:spec.header.length, maxChars:2500});
  inspections.push({sheet:spec.name, report:check.ndjson});
  const preview = await wb.render({sheetName:spec.name, range:`A1:${last}${Math.min(values.length,5)}`, scale:1, format:'png'});
  await fs.writeFile(path.join(outputDir, `preview-${index+1}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const errors = await wb.inspect({ kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options:{useRegex:true,maxResults:50}, maxChars:4000 });
await fs.writeFile(path.join(outputDir, 'workbook-inspection.json'), JSON.stringify({sheets:inspections, formula_errors:errors.ndjson},null,2));
const output = await SpreadsheetFile.exportXlsx(wb);
const temp = path.join(outputDir, 'literature.pending.xlsx');
await output.save(temp);
const seal = { baseline_sha256:hash(baselineBytes), workbook_sha256:hash(await fs.readFile(temp)), builder_sha256:buildHash };
// Seal first: a retry after interruption can regenerate a missing XLSX without overwriting an existing file.
await fs.writeFile(sealPath, JSON.stringify(seal,null,2));
await fs.rename(temp, outputPath);
console.log(JSON.stringify({path:outputPath, sheets:bundle.sheets.length, reused:false}));
