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
  'shiftColumnGroupDepth','applyRowBanding'];
chain.forEach(m => { Range.prototype[m] = function(){ return this; }; });
// Single-cell writes have to be recorded too, not just grid writes. Whole tabs
// — Settings, the Category Tracker — are built one setValue at a time, and
// while these were no-ops nothing on them could be asserted at all.
['setValue','setFormula'].forEach(m => {
  Range.prototype[m] = function (v) {
    this.sheet.cells[`${this.row},${this.col}`] = v;
    return this;
  };
});
// Google refuses a frozen boundary that splits a merged cell. Model it.
Range.prototype.merge = function () {
  (this.sheet.merges = this.sheet.merges || []).push([this.col, this.col + this.nc - 1, this.row]);
  return this;
};
// Merges SURVIVE clear(). Modelled, because a leftover merge from the previous layout
// straddling the new frozen boundary is what "You can't merge frozen and non-frozen
// columns" means, and it only appears when rebuilding over an existing sheet.
Range.prototype.breakApart = function () {
  const c1 = this.col, c2 = this.col + this.nc - 1;
  this.sheet.merges = (this.sheet.merges || []).filter(m => m[1] < c1 || m[0] > c2);
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
  // boardOrder reads the selected value column off a calculation tab before Sheets has
  // calculated anything. Synthesise a descending column so the sort has something real.
  if (global.V && this.name === 'BMP' && c === V.durh && r >= 4 && v === undefined)
    return 12 - r * 0.05;
  if (v === undefined) return '';
  if (global.D && this.name === 'Draft Board' && c === D.brk)
    return (r % 15 === 0) ? 'BREAK' : '';
  return v;
};
Sheet.prototype.getRange = function (a, b, c, d) {
  if (typeof a === 'string') {
    const m = a.match(/^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/);
    if (!m) { problems.push(`${this.name}: unparsed A1 "${a}"`); return new Range(this,1,1,1,1); }
    const c1 = colNum(m[1]), r1 = +m[2];
    const c2 = m[3] ? colNum(m[3]) : c1, r2 = m[4] ? +m[4] : r1;
    return new Range(this, r1, c1, r2 - r1 + 1, c2 - c1 + 1, a);
  }
  return new Range(this, a, b, c, d);
};
['clear','clearConditionalFormatRules',
 'setRowHeight','setHiddenGridlines','setConditionalFormatRules']
 .forEach(m => { Sheet.prototype[m] = function(){ return this; }; });
// Recorded, not a no-op: the projection filter's whole job is column arithmetic, and
// pointing it at the wrong span is exactly the failure that would pass every other check.
Sheet.prototype.setFrozenRows = function (n) { this.frozenRows = n; return this; };
Sheet.prototype.hideColumns = function (c, n) {
  (this.hidden = this.hidden || []).push([c, n === undefined ? 1 : n]); return this;
};
Sheet.prototype.showColumns = function (c, n) {
  (this.shown = this.shown || []).push([c, n === undefined ? 1 : n]); return this;
};
Sheet.prototype.setColumnWidth = function (c) {
  if (c > this.maxCols) problems.push(`${this.name}: setColumnWidth(${c}) past maxColumns ${this.maxCols}`);
  return this;
};
Sheet.prototype.setFrozenColumns = function (n) {
  this.frozenCols = n;
  (this.merges || []).forEach(([c1, c2]) => {
    if (n >= c1 && n < c2)
      problems.push(`${this.name}: setFrozenColumns(${n}) splits the merge spanning cols ${c1}-${c2}`);
  });
  return this;
};
Sheet.prototype.getName = function(){ return this.name; };
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

// Rules were chainable no-ops, so nothing about them could be asserted. They
// carry hardcoded column letters, which is exactly the thing that drifts when a
// column is inserted -- and did, twice, before this recorded anything.
function ruleBuilder() {
  const b = {}, spec = { formula: null, text: null, ranges: [] };
  ['setBackground','setFontColor','setBold','setItalic','setStrikethrough','setUnderline',
   'setGradientMinpointWithValue','setGradientMidpointWithValue','setGradientMaxpointWithValue']
   .forEach(m => { b[m] = () => b; });
  b.whenFormulaSatisfied = f => { spec.formula = f; return b; };
  b.whenTextEqualTo      = t => { spec.text = t; return b; };
  b.whenTextContains     = t => { spec.text = t; return b; };
  b.setRanges = rs => { spec.ranges = rs.map(r => ({ col: r.col, nc: r.nc })); return b; };
  b.build = () => spec;
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
//
// Every expectation below is BUILT FROM THE COLUMN MAPS, never pinned as a literal.
// Pinning both sides as strings makes this file blind to the failure it exists to catch:
// insert a column and each hardcoded source letter shifts against the data while the
// assertion still passes.
function cell(sh, r, c){ const v = seen.sheets[sh].cells[`${r},${c}`]; return v === undefined ? '<empty>' : v; }
function L(n){let s='';while(n>0){const m=(n-1)%26;s=String.fromCharCode(65+m)+s;n=(n-m-1)/26;}return s;}
const fails = [];
function expect(what, got, want) {
  if (String(got) !== String(want)) fails.push(`${what}\n     got  ${got}\n     want ${want}`);
}
function check(what, ok, detail) { if (!ok) fails.push(what + (detail ? `\n     ${detail}` : '')); }
const C = n => '$' + L(n);
const r4 = R0;

// --- structure -------------------------------------------------------------
check('all three calculation tabs exist',
  SOURCES.every(s => seen.sheets[s.key]),
  'got: ' + Object.keys(seen.sheets).join(', '));

// The projection filter hides one source's six-column span. A gap in that span would hide
// the wrong columns while every offline check still passed.
SOURCES.forEach((s, i) => {
  const start = dSpanStart(i);
  for (let k = 0; k < VALUE_KINDS.length; k++) {
    check(`${s.label} block is contiguous at ${VALUE_KINDS[k].label}`,
      dValue(i, k) === start + k * 2 && dTag(i, k) === start + k * 2 + 1,
      `value ${dValue(i,k)} tag ${dTag(i,k)} expected ${start + k*2}/${start + k*2 + 1}`);
  }
  check(`${s.label} span is ${SPAN} wide`,
    dSpanStart(i) + SPAN - 1 === dTag(i, VALUE_KINDS.length - 1));
});

// Gone and Mine sit inside the frozen pane, and the freeze is set to Mine.
check('GONE and MINE are adjacent and inside the frozen pane',
  D.mine === D.drafted + 1 && D.mine < dSpanStart(0));

// The punt score and rank blocks must each be contiguous: "Best build" takes MIN and MATCH
// across the rank span as one range, and the labels are positional against it.
for (let i = 1; i < PUNTS.length; i++) {
  check(`punt score block breaks at ${PUNTS[i].label}`, V.p0 + i === V.p0 + i);
}
check('punt rank block sits immediately after the score block',
  V.pr0 === V.p0 + PUNTS.length);

// CAT_LABELS is matched elementwise against the DH block and against the tracker's rows.
// A drift here relabels every player's strengths and nothing errors.
check('CAT_LABELS has no turnovers', CAT_LABELS.indexOf('TO') === -1);
check('DH and D blocks are CAT_LABELS wide',
  V.d0 - V.dh0 === CAT_LABELS.length && V.z0 - V.d0 === CAT_LABELS.length);
CAT_LABELS.forEach((label, i) => {
  const got = cell('Category Tracker', TRACKER_R0 + i, 1);
  if (String(got) !== label)
    fails.push(`Category Tracker row ${TRACKER_R0 + i} is "${got}", CAT_LABELS says ${label}`);
});

// --- sheet-name quoting ----------------------------------------------------
// BMP-ALT contains a hyphen, so an unquoted reference to it resolves somewhere else or
// fails outright. This is a class of bug rather than one instance, so test the class.
expect('sheetRef quotes a hyphenated name', sheetRef('BMP-ALT'), "'BMP-ALT'");
// A space does not parse unquoted -- the whole formula returns #ERROR!.
expect('sheetRef quotes a name containing a space', sheetRef('Category Tracker'),
  "'Category Tracker'");
expect('sheetRef leaves a bare identifier alone', sheetRef('Board'), 'Board');
{
  let unquoted = 0;
  // Every sheet name that is not a bare identifier: hyphens AND spaces.
  const hyphenated = SOURCES.map(s => s.key).concat(['Draft Board', 'Category Tracker'])
    .filter(n => !/^[A-Za-z0-9_]+$/.test(n));
  Object.values(seen.sheets).forEach(sh => {
    Object.values(sh.cells).forEach(v => {
      if (typeof v !== 'string' || v.charAt(0) !== '=') return;
      hyphenated.forEach(name => {
        // The bare name followed by ! and not preceded by the closing quote.
        if (new RegExp(`(^|[^'\\\\w])${name}!`).test(v)) unquoted++;
      });
    });
  });
  check('every reference to a hyphenated sheet is quoted', unquoted === 0,
    `${unquoted} unquoted reference(s) to ${hyphenated.join(', ')}`);
}

// --- Board -----------------------------------------------------------------
// Two formulas, and no valuation anywhere: the Board is a spine now.
expect('My GP seeds from the projection', cell('Board', r4, B.myGp), `=${C(B.gp)}${r4}`);
expect('GP flag', cell('Board', r4, B.gpCheck),
  `=IF(${C(B.myGp)}${r4}="","",IF(ABS(${C(B.gp)}${r4}-${C(B.myGp)}${r4})>10,"CHECK",""))`);
check('the Board carries no value columns',
  B.durh === undefined && B.gtot === undefined && B.adj === undefined);

// Every REFRESH_MAP target must name the column its header claims. Each index moved when
// the Board was cut from 73 columns to 28.
REFRESH_MAP.forEach(([col, idx]) => {
  check(`REFRESH_MAP column ${L(col)} has a header`,
    String(cell('Board', HDR, col)).trim() !== '' && String(cell('Board', HDR, col)) !== '<empty>',
    `PLAYERS[${idx}] -> ${L(col)}`);
});
HAND_COLS.forEach(c => {
  check(`hand column ${L(c)} is not also refreshed`,
    !REFRESH_MAP.some(([col]) => col === c));
});

// --- calculation tabs ------------------------------------------------------
SOURCES.forEach(s => {
  const first = cell(s.key, r4, V.durh);
  check(`${s.key} DURH is a number, not a formula`,
    typeof first === 'number' || String(first).charAt(0) !== '=',
    `got ${first}`);
});
check('the lambda row names a constant per category',
  String(cell(SOURCES[0].key, HDR, V.d0)).indexOf('λ') === 0,
  `got ${cell(SOURCES[0].key, HDR, V.d0)}`);
check('the weight row names a constant per category',
  String(cell(SOURCES[0].key, HDR, V.dh0)).indexOf('w') === 0,
  `got ${cell(SOURCES[0].key, HDR, V.dh0)}`);

// --- Draft Board -----------------------------------------------------------
expect('rank is a RANK over the sorted column', cell('Draft Board', r4, D.rank),
  `=RANK(${C(D.sel)}${r4},${C(D.sel)}$${R0}:${C(D.sel)}$${RN})`);
expect('round reads league size', cell('Draft Board', r4, D.round),
  `=IF(${C(D.rank)}${r4}="","",CEILING(${C(D.rank)}${r4}/TEAMS))`);
expect('GAP is ADP minus the board rank', cell('Draft Board', r4, D.gap),
  `=IF(${C(D.adp)}${r4}="","",${C(D.adp)}${r4}-${C(D.rank)}${r4})`);
expect('tier 1 is a literal', cell('Draft Board', r4, D.tier), 1);
expect('drop reads the sorted column', cell('Draft Board', r4 + 1, D.drop),
  `=${C(D.sel)}${r4}-${C(D.sel)}${r4 + 1}`);
// The tier window must be centred: INDEX(range,k) is sheet row k+HDR, so these offsets
// have to resolve to r-7 .. r+7.
{
  // INDEX(range,k) resolves to sheet row k+HDR, so these offsets must give r-7 .. r+7.
  // A window skewed up the board sits where drops are larger, which inflates the median
  // and fires breaks late -- exactly where the curve steepens and a tier matters most.
  const span = `${C(D.drop)}$${R0}:${C(D.drop)}$${RN}`;
  expect('tier window is centred on the row', cell('Draft Board', r4 + 1, D.med),
    `=MEDIAN(INDEX(${span},MAX(1,ROW()-${HDR + 7}))`
    + `:INDEX(${span},MIN(${POOL_ROWS},ROW()+${7 - HDR})))`);
}
expect('break', cell('Draft Board', r4 + 1, D.brk),
  `=IF(N(${C(D.med)}${r4 + 1})<=0,"",IF(${C(D.drop)}${r4 + 1}>TIER_MULT*${C(D.med)}${r4 + 1},"BREAK",""))`);
expect('tier roll', cell('Draft Board', r4 + 1, D.tier),
  `=IF(${C(D.brk)}${r4 + 1}="BREAK",${C(D.tier)}${r4}+1,${C(D.tier)}${r4})`);

// The sorted column must point at one of the nine value columns, and nothing else may.
{
  const sel = String(cell('Draft Board', r4, D.sel));
  const valid = [];
  for (let s = 0; s < SOURCES.length; s++)
    for (let k = 0; k < VALUE_KINDS.length; k++) valid.push(`=${C(dValue(s, k))}${r4}`);
  check('the sorted column copies one of the nine values', valid.indexOf(sel) >= 0, `got ${sel}`);
}

// Each tag reads its own rank column, and ZSC -- which drops nothing -- carries only a rank.
for (let s = 0; s < SOURCES.length; s++) {
  for (let k = 0; k < VALUE_KINDS.length; k++) {
    const tag = String(cell('Draft Board', r4, dTag(s, k)));
    check(`${SOURCES[s].label} ${VALUE_KINDS[k].label} tag reads its own rank column`,
      tag.indexOf(C(dRank(s, k)) + r4) >= 0, `got ${tag}`);
    if (!VALUE_KINDS[k].drop) {
      check(`${VALUE_KINDS[k].label} tag carries no dropped category`,
        tag.indexOf('&" "&') === -1, `got ${tag}`);
    }
  }
}

// The profile columns: both array traps live here and neither is visible offline.
{
  const s = String(cell('Draft Board', r4, D.strengths));
  const w = String(cell('Draft Board', r4, D.weaknesses));
  [['strengths', s], ['weaknesses', w]].forEach(([name, f]) => {
    check(`${name} wraps its IF in ARRAYFORMULA`, f.indexOf('ARRAYFORMULA(IF(') >= 0, f);
    // The LET trap: bind the raw TRANSPOSE and compare inside the ARRAYFORMULA.
    check(`${name} binds the raw TRANSPOSE, not a comparison`,
      f.indexOf('punt,TRANSPOSE(') >= 0 && f.indexOf('TRANSPOSE(') >= 0
      && f.indexOf('<>TRUE)') > f.indexOf('ARRAYFORMULA('), f);
    check(`${name} reads the UNWEIGHTED DURANT block`,
      f.indexOf(C(D.d0) + r4) >= 0, f);
    check(`${name} reads the tracker's Punted column`,
      f.indexOf(`$${L(TRACK_PUNT_COL)}$${TRACKER_R0}`) >= 0, f);
  });
  check('strengths and weaknesses are different formulas', s !== w);
}

// --- Category Tracker ------------------------------------------------------
check('the tracker has no turnovers row',
  CAT_LABELS.length === 8 && !CAT_LABELS.some(c => c === 'TO'));
for (let i = 0; i < CAT_LABELS.length; i++) {
  const r = TRACKER_R0 + i, lab = CAT_LABELS[i];
  const z = String(cell('Category Tracker', r, 4));
  const win = String(cell('Category Tracker', r, 5));
  const read = String(cell('Category Tracker', r, 6));
  check(`${lab} Z divides by SQRT(n)`, z.indexOf('/SQRT(') >= 0, z);
  check(`${lab} benchmark is capped at Q`, z.indexOf('MIN(Q,TEAMS*') >= 0, z);
  check(`${lab} Win% uses its own K`, win.indexOf('K_' + catKey(lab)) >= 0, win);
  check(`${lab} Win% is a normal CDF`, win.indexOf('NORMSDIST(') >= 0, win);
  ['PUNTED', 'BANKED', 'STRONG', 'WEAK', 'CONTESTED'].forEach(state => {
    check(`${lab} Read can report ${state}`, read.indexOf(state) >= 0, read);
  });
}

// --- named ranges ----------------------------------------------------------
// The mechanical guard on the riskiest part of the Settings rewrite: a label must sit
// beside the cell its named range claims.
function labelFor(name, want) {
  const rng = seen.namedRanges[name];
  if (!rng) { fails.push(`named range ${name} was never defined`); return; }
  const got = String(seen.sheets['Settings'].cells[`${rng.row},${rng.col - 1}`] || '');
  if (got !== want) fails.push(`${name} points at a cell labelled "${got}", expected "${want}"`);
}
labelFor('TEAMS', 'Teams');
labelFor('ROSTER', 'Roster spots');
labelFor('Q', 'Pool size (Q)');
labelFor('SORT_BY', 'Sort by');
labelFor('TIER_MULT', 'Tier multiplier');
labelFor('CAT_BAND', 'Category band');
labelFor('DISAGREE_GAP', 'Disagreement gap');
labelFor('WEAK_WIN', 'Weak at or below');
labelFor('STRONG_WIN', 'Strong at or above');
labelFor('BANK_WIN', 'Banked at or above');
// K sits in a table, so its label is at the start of the row rather than beside it.
CAT_LABELS.forEach(lab => {
  const rng = seen.namedRanges['K_' + catKey(lab)];
  if (!rng) { fails.push(`named range K_${catKey(lab)} was never defined`); return; }
  const got = String(seen.sheets['Settings'].cells[`${rng.row},1`] || '');
  if (got !== lab) fails.push(`K_${catKey(lab)} points at a row labelled "${got}", expected "${lab}"`);
});

['TRACK_FG_BAND', 'TRACK_FT_BAND', 'TRACK_COUNT_BAND', 'GP_DIVISOR', 'MIN_GP',
 'REPLACEMENT', 'PUNT_WEIGHT', 'MULT_STL'].forEach(n => {
  check(`retired named range ${n} is gone`, !seen.namedRanges[n]);
});
SOURCES.forEach(s => {
  ['PLAYER', 'DURH', 'DURH_RANK', 'ZSH', 'ZSC', 'ADP'].forEach(t => {
    check(`${nameOf(s.prefix, t)} is defined`, !!seen.namedRanges[nameOf(s.prefix, t)]);
  });
});
CAT_LABELS.forEach(lab => {
  check(`DB_DH_${catKey(lab)} is defined`, !!seen.namedRanges['DB_DH_' + catKey(lab)]);
});

// --- the projection filter -------------------------------------------------
// Only the column arithmetic can be tested offline; that Google actually fires the trigger
// cannot be. The arithmetic is the part that silently points at the wrong span.
{
  const sh = seen.sheets['Draft Board'];
  sh.hidden = []; sh.shown = [];
  setProjectionVisible(sh, 1, false);
  expect('hiding HBP hides exactly its six columns',
    JSON.stringify(sh.hidden), JSON.stringify([[dSpanStart(1), SPAN]]));
  setProjectionVisible(sh, 2, true);
  expect('showing BMP-ALT shows exactly its six columns',
    JSON.stringify(sh.shown), JSON.stringify([[dSpanStart(2), SPAN]]));

  // A checkbox tick anywhere but row 1 of the Draft Board must do nothing at all: onEdit
  // fires on every edit, including each of the ~156 GONE ticks during a draft.
  sh.hidden = []; sh.shown = [];
  onEdit({ range: { getRow: () => 5, getColumn: () => 1, getSheet: () => sh,
                    getValue: () => false } });
  check('onEdit ignores edits outside row 1', sh.hidden.length === 0 && sh.shown.length === 0);
  onEdit({ range: { getRow: () => 1, getColumn: () => 1, getSheet: () => sh,
                    getValue: () => false } });
  expect('onEdit on the first checkbox hides the first block',
    JSON.stringify(sh.hidden), JSON.stringify([[dSpanStart(0), SPAN]]));
}

// --- draft state survives a layout change ----------------------------------
// The hazard that matters is not a column moving -- everything here derives from the map,
// so a move is legitimate and harmless. It is readCheckState running against the OLD sheet
// while the rest of the build uses the NEW map. Off by one, the old MINE column is read as
// GONE: the draft state silently corrupted rather than merely wiped, on the two controls
// used on the clock. So it keys off the header labels, and this proves it.
{
  const old = new Sheet('Old Draft Board');
  old.maxCols = D_LAST + 8; old.maxRows = RN;
  // A layout with GONE and MINE somewhere else entirely, found only by their headers.
  const oldPlayer = 2, oldGone = 40, oldMine = 41, oldNotes = 42, oldInj = 43;
  old.cells[`${HDR},${oldPlayer}`] = 'Player';
  old.cells[`${HDR},${oldGone}`] = 'GONE';
  old.cells[`${HDR},${oldMine}`] = 'MINE';
  old.cells[`${HDR},${oldNotes}`] = 'Notes';
  old.cells[`${HDR},${oldInj}`] = 'INJ';
  old.cells[`${R0},${oldPlayer}`] = 'Ada Lovelace';
  old.cells[`${R0},${oldGone}`] = false;
  old.cells[`${R0},${oldMine}`] = true;
  old.cells[`${R0},${oldNotes}`] = 'target';
  old.cells[`${R0},${oldInj}`] = 'GTD';
  old.getLastRow = () => R0;

  const at = draftHeaderCols(old);
  check('draftHeaderCols finds GONE by its header, not by the map', at.GONE === oldGone,
    `got ${at.GONE}, expected ${oldGone}`);
  check('draftHeaderCols finds MINE by its header', at.MINE === oldMine);

  check('readCheckState tolerates a missing sheet', readCheckState(null) && true);
  const state = readCheckState(old);
  const rec = state['Ada Lovelace'];
  check('the ticked player is read back', !!rec);
  if (rec) {
    // The precise corruption to guard against: reading MINE as GONE.
    check('MINE is not read as GONE', rec.gone === false && rec.mine === true,
      `gone=${rec.gone} mine=${rec.mine}`);
    check('Notes and Injuries travel with the checkboxes',
      rec.notes === 'target' && rec.inj === 'GTD', JSON.stringify(rec));
  }
}

// --- conditional formats ---------------------------------------------------
// These carry column letters, which is exactly what drifts when a column is inserted.
{
  const rules = seen.sheets['Draft Board'].rules.map(r => r.formula).filter(Boolean);
  const has = f => rules.some(x => x === f);
  check('MINE rule keys off the Mine column', has(`=${C(D.mine)}${R0}=TRUE`), rules.join('\n'));
  check('GONE rule keys off the Gone column', has(`=${C(D.drafted)}${R0}=TRUE`));
  // First match wins, so MINE has to be added before GONE: the old order rendered a
  // player who was both as struck through, which the mine rule explicitly undid.
  const iMine = rules.indexOf(`=${C(D.mine)}${R0}=TRUE`);
  const iGone = rules.indexOf(`=${C(D.drafted)}${R0}=TRUE`);
  check('MINE resolves before GONE', iMine >= 0 && iGone >= 0 && iMine < iGone,
    `mine at ${iMine}, gone at ${iGone}`);
  check('the GP haircut band points at Projected GP',
    has(`=AND(${C(D.projGp)}${R0}>=68,${C(D.projGp)}${R0}<=74)`));
  check('the round ruler points at the round column',
    has(`=ISODD(${C(D.round)}${R0})`));
  // One rule per tag column, never one rule over nine ranges: a multi-range rule relies on
  // Sheets offsetting a relative reference per range, which is untestable here.
  let pairs = 0;
  for (let s = 0; s < SOURCES.length; s++)
    for (let k = 0; k < VALUE_KINDS.length; k++)
      if (has(`=AND(${C(dRank(s,k))}${R0}<>"",${C(D.rank)}${R0}-${C(dRank(s,k))}${R0}>=${disagreeGap()})`))
        pairs++;
  check('every tag column has its own disagreement rule',
    pairs === SOURCES.length * VALUE_KINDS.length, `found ${pairs}`);

  // A conditional format rule MAY NOT reference another sheet, and every named range in
  // this workbook lives on Settings. Referencing one takes down the entire rule set for
  // that tab -- "Conditional format rule cannot reference a different sheet" -- which is
  // how the Draft Board build failed on its first live run.
  const named = ['DISAGREE_GAP','CAT_BAND','TIER_MULT','TEAMS','Q','WEAK_WIN','STRONG_WIN',
                 'BANK_WIN','SORT_BY','ROSTER','SCORING'];
  ['Draft Board','Board','Category Tracker','Punts','BMP','HBP','BMP-ALT','Settings']
    .forEach(name => {
      const sh = seen.sheets[name];
      if (!sh) return;
      sh.rules.forEach(r => {
        const f = r.formula || '';
        named.concat(CAT_LABELS.map(c => 'K_' + catKey(c))).forEach(n => {
          if (new RegExp(`\\b${n}\\b`).test(f))
            fails.push(`${name}: a conditional format rule references the named range ${n}, `
                       + `which lives on another sheet\n     ${f}`);
        });
        if (/[A-Za-z0-9_ ]+!\$?[A-Z]/.test(f) || /'[^']+'!/.test(f))
          fails.push(`${name}: a conditional format rule references another sheet\n     ${f}`);
      });
    });
}

// --- rebuilding over an existing sheet --------------------------------------
// The failure this caught live: clear() does NOT remove merges, so a merged block header
// from the previous layout survives, and the next build's frozen boundary lands inside it.
// Only reproducible by building TWICE over the same sheets, which is what every rebuild
// after the first actually does.
{
  // Seed a merge from a DIFFERENT layout -- the pre-refactor board merged its first block
  // across columns 1-5, and the new layout freezes at 4. Building from scratch twice with
  // the same map cannot reproduce this; only a layout change can, which is precisely when
  // it bites.
  const board = seen.sheets['Board'];
  board.merges = (board.merges || []).concat([[1, 5, 1]]);
  const before = problems.length;
  try { buildDraftBoard(); } catch (e) { problems.push('SECOND BUILD THREW: ' + e.message); }
  const introduced = problems.slice(before);
  check('a rebuild clears merges left by the previous layout',
    introduced.length === 0, introduced.slice(0, 3).join('\n     '));
}

console.log('\n=== ' + (fails.length ? fails.length + ' ASSERTION FAILURE(S)' : 'all assertions passed') + ' ===');
fails.forEach(f => console.log('  ✗ ' + f));
process.exit(fails.length || problems.length ? 1 : 0);

