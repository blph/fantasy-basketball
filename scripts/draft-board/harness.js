// Mock enough of the Apps Script Sheets API to execute buildDraftBoard() and
// assert the things that actually break: range/array dimension mismatches,
// writes outside the grid, and calls to methods that do not exist.
const fs = require('fs');
const problems = [];
const seen = { namedRanges: {}, sheets: {} };

const A1 = /^(?:'([^']+)'|([A-Za-z0-9 _]+))!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$/;

function colNum(s){let n=0;for(const c of s)n=n*26+(c.charCodeAt(0)-64);return n;}

function Range(sheet, row, col, nr, nc, label) {
  this.sheet = sheet; this.row = row; this.col = col;
  this.nr = nr === undefined ? 1 : nr; this.nc = nc === undefined ? 1 : nc;
  this.label = label || '';
  if (row < 1 || col < 1) problems.push(`${sheet.name}: range starts at r${row} c${col}`);
  if (col + this.nc - 1 > sheet.maxCols)
    problems.push(`${sheet.name}: range r${row} c${col}+${this.nc} runs past maxColumns ${sheet.maxCols}`);
  if (row + this.nr - 1 > sheet.maxRows)
    problems.push(`${sheet.name}: range r${row}+${this.nr} runs past maxRows ${sheet.maxRows}`);
}
const chain = ['setBackground','setFontColor','setFontWeight','setFontSize','setFontStyle',
  'setHorizontalAlignment','setVerticalAlignment','setWrap','setNumberFormat','setFontFamily',
  'setBorder','setDataValidation','insertCheckboxes','clearDataValidations','merge',
  'shiftColumnGroupDepth','setValue','setFormula','applyRowBanding'];
chain.forEach(m => { Range.prototype[m] = function(){ return this; }; });
// Google refuses a frozen boundary that splits a merged cell. Model it.
Range.prototype.merge = function () {
  (this.sheet.merges = this.sheet.merges || []).push([this.col, this.col + this.nc - 1, this.row]);
  return this;
};

Range.prototype._check = function (grid, what) {
  if (!Array.isArray(grid)) { problems.push(`${this.sheet.name}: ${what} got non-array`); return; }
  if (grid.length !== this.nr)
    problems.push(`${this.sheet.name} ${what}: ${grid.length} rows into a ${this.nr}-row range (r${this.row} c${this.col})`);
  grid.forEach((r, i) => {
    if (!Array.isArray(r)) { problems.push(`${this.sheet.name}: ${what} row ${i} not an array`); return; }
    if (r.length !== this.nc)
      problems.push(`${this.sheet.name} ${what}: row ${i} has ${r.length} cols into a ${this.nc}-col range (r${this.row} c${this.col})`);
  });
};
Range.prototype.setValues = function (g) { this._check(g, 'setValues'); this.sheet._write(this, g); return this; };
Range.prototype.setFormulas = function (g) {
  this._check(g, 'setFormulas');
  g.forEach((r,i)=>r.forEach((v,j)=>{
    if (v !== '' && String(v).charAt(0) !== '=')
      problems.push(`${this.sheet.name}: setFormulas got a non-formula "${String(v).slice(0,30)}" at r${this.row+i} c${this.col+j}`);
  }));
  this.sheet._write(this, g); return this;
};
Range.prototype.getValue = function () { return this.sheet._read(this.row, this.col); };
Range.prototype.getValues = function () {
  const out = [];
  for (let i = 0; i < this.nr; i++) {
    const r = [];
    for (let j = 0; j < this.nc; j++) r.push(this.sheet._read(this.row + i, this.col + j));
    out.push(r);
  }
  return out;
};

function Sheet(name) {
  this.name = name; this.cells = {}; this.rules = [];
  this.maxCols = 26; this.maxRows = 1000;   // what insertSheet actually gives you
  seen.sheets[name] = this;
}
Sheet.prototype.insertColumnsAfter = function (after, n) { this.maxCols += n; return this; };
Sheet.prototype.insertRowsAfter = function (after, n) { this.maxRows += n; return this; };
Sheet.prototype._write = function (rng, g) {
  for (let i = 0; i < g.length; i++) for (let j = 0; j < g[i].length; j++)
    this.cells[`${rng.row+i},${rng.col+j}`] = g[i][j];
};
Sheet.prototype._read = function (r, c) {
  const v = this.cells[`${r},${c}`];
  if (v === undefined) return '';
  // Emulate calculation for the columns the script reads back.
  if (this.name === 'Board' && c === 50) return 12 - r * 0.05;          // Adjusted Value
  if (this.name === 'Board' && c === 51) return r - 2;                   // Adj Rank
  if (this.name === 'Draft Board' && c === 11) return (r % 15 === 0) ? 'BREAK' : '';
  return v;
};
Sheet.prototype.getRange = function (a, b, c, d) {
  if (typeof a === 'string') {
    const m = a.match(/^([A-Z]+)(\d+)$/);
    if (!m) { problems.push(`${this.name}: unparsed A1 "${a}"`); return new Range(this,1,1,1,1); }
    return new Range(this, +m[2], colNum(m[1]), 1, 1, a);
  }
  return new Range(this, a, b, c, d);
};
['clear','clearConditionalFormatRules','setFrozenRows',
 'setRowHeight','setHiddenGridlines','hideColumns','setConditionalFormatRules']
 .forEach(m => { Sheet.prototype[m] = function(){ return this; }; });
Sheet.prototype.setColumnWidth = function (c) {
  if (c > this.maxCols) problems.push(`${this.name}: setColumnWidth(${c}) past maxColumns ${this.maxCols}`);
  return this;
};
Sheet.prototype.setFrozenColumns = function (n) {
  (this.merges || []).forEach(([c1, c2]) => {
    if (n >= c1 && n < c2)
      problems.push(`${this.name}: setFrozenColumns(${n}) splits the merge spanning cols ${c1}-${c2}`);
  });
  return this;
};
Sheet.prototype.getBandings = function(){ return []; };
Sheet.prototype.getConditionalFormatRules = function(){ return this.rules; };
Sheet.prototype.setConditionalFormatRules = function(r){ this.rules = r; return this; };
Sheet.prototype.getColumnGroup = function(){ return { collapse(){} }; };
Sheet.prototype.getLastRow = function(){ return 0; };
Sheet.prototype.getMaxRows = function(){ return this.maxRows; };
Sheet.prototype.getMaxColumns = function(){ return this.maxCols; };

const ss = {
  getSheetByName: n => seen.sheets[n] || null,
  insertSheet: n => new Sheet(n),
  deleteSheet(){}, setActiveSheet(){ return this; }, moveActiveSheet(){}, toast(){},
  setSpreadsheetTimeZone(){}, getSpreadsheetTimeZone: () => 'UTC',
  getNamedRanges: () => [],
  setNamedRange(name, rng) {
    seen.namedRanges[name] = rng;
    if (!rng || !(rng instanceof Range)) problems.push(`named range ${name} is not a Range`);
  },
  getRange(a1) {
    const m = String(a1).match(A1);
    if (!m) { problems.push(`bad A1 notation for a named range: "${a1}"`); return new Range(new Sheet('?'),1,1); }
    const sheetName = m[1] || m[2];
    const sh = seen.sheets[sheetName];
    if (!sh) { problems.push(`named range points at missing sheet "${sheetName}" (${a1})`); return new Range(new Sheet('?'),1,1); }
    const c1 = colNum(m[3]), r1 = +m[4];
    const c2 = m[5] ? colNum(m[5]) : c1, r2 = m[6] ? +m[6] : r1;
    return new Range(sh, r1, c1, r2 - r1 + 1, c2 - c1 + 1, a1);
  }
};

function ruleBuilder() {
  const b = {};
  ['whenFormulaSatisfied','whenTextEqualTo','whenTextContains','setBackground','setFontColor',
   'setBold','setItalic','setStrikethrough','setUnderline','setRanges',
   'setGradientMinpointWithValue','setGradientMidpointWithValue','setGradientMaxpointWithValue']
   .forEach(m => { b[m] = () => b; });
  b.build = () => ({});
  return b;
}
global.SpreadsheetApp = {
  getActiveSpreadsheet: () => ss,
  flush(){},
  newConditionalFormatRule: ruleBuilder,
  newDataValidation: () => ({ requireValueInList: () => ({ build: () => ({}) }) }),
  InterpolationType: { NUMBER: 'NUMBER' },
  BorderStyle: { SOLID: 'SOLID', SOLID_MEDIUM: 'SOLID_MEDIUM' },
  BandingTheme: { LIGHT_GREY: 'LIGHT_GREY' },
  getUi: () => ({ createMenu: () => { const m = { addItem: () => m, addSeparator: () => m, addToUi(){} }; return m; } })
};

// Real data if it happens to be here, otherwise synthetic. The test must run on
// a clean clone: this repo is public and holds no provider data.
if (fs.existsSync('Data.gs')) {
  eval(fs.readFileSync('Data.gs', 'utf8'));
} else {
  global.PLAYERS = Array.from({ length: 200 }, (_, i) => {
    const t = 1 - i / 220;                       // deterministic, no randomness
    const fga = +(6 + 12 * t).toFixed(1), fta = +(1 + 6 * t).toFixed(1);
    return [
      i + 1, 'Player ' + String(i + 1).padStart(3, '0'), 'TM' + (i % 30), 'PG,SG',
      i < 162 ? +(2 + i * 0.65).toFixed(1) : '',
      60 + (i % 21), +(20 + 16 * t).toFixed(1),
      +(fga * 0.47).toFixed(1), fga, 0.47,
      +(fta * 0.79).toFixed(1), fta, 0.79,
      +(0.6 + 2.8 * t).toFixed(1), +(6 + 22 * t).toFixed(1), +(2 + 8 * t).toFixed(1),
      +(1 + 7 * t).toFixed(1), +(0.4 + 1.1 * t).toFixed(1), +(0.2 + 1.4 * t).toFixed(1),
      +(0.8 + 2.4 * t).toFixed(1)
    ];
  });
}
eval(fs.readFileSync('Build.gs','utf8'));

try { buildDraftBoard(); }
catch (e) { problems.push('THREW: ' + e.message + '\n' + (e.stack||'').split('\n').slice(1,4).join('\n')); }

console.log('sheets built:', Object.keys(seen.sheets).join(', '));
console.log('named ranges:', Object.keys(seen.namedRanges).length);
const board = seen.sheets['Board'], draft = seen.sheets['Draft Board'];
if (board) console.log('Board cells written:', Object.keys(board.cells).length);
if (draft) console.log('Draft Board cells written:', Object.keys(draft.cells).length);
if (problems.length) {
  console.log('\n=== ' + problems.length + ' PROBLEM(S) ===');
  problems.slice(0,25).forEach(p => console.log(' - ' + p));
} else console.log('\nNo problems found.');

// ---- targeted assertions on what actually landed in the cells ----
function cell(sh, r, c){ const v = seen.sheets[sh].cells[`${r},${c}`]; return v === undefined ? '<empty>' : v; }
function L(n){let s='';while(n>0){const m=(n-1)%26;s=String.fromCharCode(65+m)+s;n=(n-m-1)/26;}return s;}
const fails = [];
function expect(what, got, want) {
  if (String(got) !== String(want)) fails.push(`${what}\n     got  ${got}\n     want ${want}`);
}
console.log('\n=== Board row 3 (first player) ===');
[['A seed',1],['B player',2],['F GP',6],['I FGA',9],['J FG%',10],['AZ ADP',52]].forEach(([n,c])=>
  console.log(`  ${n.padEnd(10)} ${L(c)}3 = ${cell('Board',3,c)}`));
[[5,'In Pool'],[21,'FG impact'],[23,'z FG%'],[31,'z TO'],[32,'Z total'],[36,'g PTS'],
 [42,'G total'],[43,'VOR'],[48,'My GP'],[50,'Adj value'],[54,'Gap'],[55,'Punt FT%'],[60,'Punt triple']]
 .forEach(([c,n])=> console.log(`  ${n.padEnd(12)} ${L(c)}3 = ${cell('Board',3,c)}`));

expect('In Pool',   cell('Board',3,5),  '=IF(AND($A3<=Q,$F3>=MIN_GP),1,0)');
expect('FG impact', cell('Board',3,21), '=($I3/POOL_AVG_FGA)*($J3-POOL_FG_PCT)');
expect('z FG%',     cell('Board',3,23), '=$U3/SD_FG_IMPACT');
expect('z TO flip', cell('Board',3,31), '=(MEAN_TO-$T3)/SD_TO');
expect('Z total',   cell('Board',3,32), '=SUM($W3:$AE3)');
expect('g PTS',     cell('Board',3,36), '=$Z3*MULT_PTS');
expect('G total',   cell('Board',3,42), '=SUM($AG3:$AO3)');
expect('VOR',       cell('Board',3,43), '=$AP3-REPLACEMENT');
expect('Adj value', cell('Board',3,50), '=IF($AV3="","",$AQ3*$AV3/GP_DIVISOR)');
expect('Gap blank', cell('Board',3,54), '=IF($AZ3="","",$AZ3-$AY3)');
expect('Punt FT%',  cell('Board',3,55), '=$AP3-$AH3');
expect('Punt triple',cell('Board',3,60),'=$AP3-$AG3-$AH3-$AO3');

// The nine z-scores summed by Z total must be exactly the nine z columns.
const zc = [23,24,25,26,27,28,29,30,31];
zc.forEach(c => { if (String(cell('Board',3,c)).charAt(0) !== '=') fails.push(`z col ${L(c)} is not a formula`); });
if (L(zc[0]) !== 'W' || L(zc[8]) !== 'AE') fails.push('z block is not W:AE');
if (L(33) !== 'AG' || L(41) !== 'AO') fails.push('g block is not AG:AO');

console.log('\n=== named ranges the formulas depend on ===');
['Q','MIN_GP','GP_DIVISOR','TIER_MULT','MULT_PTS','MULT_STL','MEAN_TO','SD_TO',
 'POOL_FG_PCT','POOL_AVG_FGA','SD_FG_IMPACT','REPLACEMENT','B_POOL','B_GTOT','B_ADJ']
 .forEach(n => { const r = seen.namedRanges[n];
   console.log(`  ${n.padEnd(14)} -> ${r.sheet.name}!${L(r.col)}${r.row}${r.nr>1?':'+L(r.col+r.nc-1)+(r.row+r.nr-1):''}`); });

// Settings labels must sit beside the cells the named ranges claim.
const S = seen.sheets['Settings'];
function labelFor(n){ const r = seen.namedRanges[n]; return S.cells[`${r.row},${r.col-1}`] ?? S.cells[`${r.row},1`]; }
expect('Q label',          labelFor('Q'),          'Pool size (Q)');
expect('MIN_GP label',     labelFor('MIN_GP'),     'Min GP for pool');
expect('TIER_MULT label',  labelFor('TIER_MULT'),  'Tier multiplier');
expect('GP_DIVISOR label', labelFor('GP_DIVISOR'), 'GP divisor');
expect('MULT_STL label',   labelFor('MULT_STL'),   'STL');
expect('MULT_PTS label',   labelFor('MULT_PTS'),   'PTS');
expect('MEAN_TO label',    labelFor('MEAN_TO'),    'TO');
expect('REPLACEMENT lbl',  labelFor('REPLACEMENT'),'Replacement G-score');
expect('POOL_FG_PCT lbl',  labelFor('POOL_FG_PCT'),'Aggregate FG%');

// Draft Board must be sorted by the mocked Adjusted Value, descending.
const d3 = cell('Draft Board',3,3), d4 = cell('Draft Board',4,3);
console.log(`\n=== Draft Board ===\n  C3 = ${d3}\n  C4 = ${d4}\n  I4 (drop) = ${cell('Draft Board',4,9)}\n  J4 (local median) = ${cell('Draft Board',4,10)}\n  K4 (break) = ${cell('Draft Board',4,11)}\n  B4 (tier) = ${cell('Draft Board',4,2)}\n  B3 (tier 1, by hand) = ${cell('Draft Board',3,2)}`);
expect('tier 1 literal', cell('Draft Board',3,2), 1);
expect('drop', cell('Draft Board',4,9), '=$F3-$F4');
expect('break', cell('Draft Board',4,11), '=IF(N($J4)<=0,"",IF($I4>TIER_MULT*$J4,"BREAK",""))');
expect('tier roll', cell('Draft Board',4,2), '=IF($K4="BREAK",$B3+1,$B3)');

console.log('\n=== ' + (fails.length ? fails.length + ' ASSERTION FAILURE(S)' : 'all assertions passed') + ' ===');
fails.forEach(f => console.log('  ✗ ' + f));
process.exit(fails.length || problems.length ? 1 : 0);
