/**
 * 9-Cat H2H Draft Board — builder.
 *
 * Implements docs/references/fantasy-basketball-draft-playbook.md as a live
 * spreadsheet. Every value a player is judged on is a formula in a cell, not a
 * number this script computed: the board has to be auditable on draft day.
 *
 * Pairs with Data.gs, which supplies `PLAYERS` (provider data, not committed).
 *
 * Entry point: buildDraftBoard()
 */

// ---------------------------------------------------------------- constants

var POOL_ROWS = 200;   // players carried on the board
var HDR = 2;           // rows 1-2 are the block header and the column header
var R0 = HDR + 1;      // first data row
var RN = HDR + POOL_ROWS;

var COLOR = {
  identity: '#37474F',
  raw:      '#1F5673',
  impact:   '#26706E',
  z:        '#43518A',
  g:        '#6A4C93',
  value:    '#1B6B4A',
  avail:    '#8A6116',
  market:   '#8C3B2B',
  punt:     '#7A2E52',
  notes:    '#546E7A',

  headerText: '#FFFFFF',
  inputBg:    '#FFF8E1',
  inputText:  '#1155CC',
  band:       '#F5F7F9',
  muted:      '#9AA0A6',
  rule:       '#D0D7DE',

  bad:  '#E67C73',
  mid:  '#FFFFFF',
  good: '#57BB8A',

  flagBg:   '#FCE8E6',
  flagText: '#C5221F',
  haircut:  '#FFF3D6',
  drafted:  '#EDEFF1'
};

// Board column map. Keep in sync with the header definitions below.
var B = {
  seed: 1, player: 2, team: 3, pos: 4, inPool: 5,
  gp: 6, mpg: 7, fgm: 8, fga: 9, fgp: 10, ftm: 11, fta: 12, ftp: 13,
  tpm: 14, pts: 15, reb: 16, ast: 17, stl: 18, blk: 19, to: 20,
  ifg: 21, ift: 22,
  zfg: 23, zft: 24, z3: 25, zpts: 26, zreb: 27, zast: 28, zstl: 29, zblk: 30, zto: 31, ztot: 32,
  gfg: 33, gft: 34, g3: 35, gpts: 36, greb: 37, gast: 38, gstl: 39, gblk: 40, gto: 41, gtot: 42,
  vor: 43, vorRank: 44,
  gp1: 45, gp2: 46, gp3: 47, myGp: 48, gpCheck: 49, adj: 50, adjRank: 51,
  adp: 52, xrank: 53, gap: 54,
  pFt: 55, pFg: 56, pAst: 57, p3: 58, pBlk: 59,
  pFgReb: 60, pAstStl: 61, pPtsFt: 62, pTriple: 63,
  rFt: 64, rFg: 65, rAst: 66, r3: 67, rBlk: 68,
  rFgReb: 69, rAstStl: 70, rPtsFt: 71, rTriple: 72,
  notes: 73
};
var B_LAST = B.notes;

// Nine builds: the five canonical single punts, then four named groupings.
// Published guides converge on FT%, FG%, AST and 3PM as the four most common
// single punts, with BLK a well-documented mid-draft pivot; the board carried
// only two of the four before. BLK+FG% is deliberately absent — the punt-blocks
// literature treats FG% as a category that build must PROTECT, so pairing them
// is self-defeating. See ADR-0010.
//
// Pool means and SDs are deliberately NOT recomputed for a build (playbook 6b).
// That matches how Basketball Monster and Hashtag Basketball behave, which
// matters: a build ranking is only useful if it predicts what your leaguemates
// see on their own screens.
var PUNTS = [
  { key: 'pFt',     rank: 'rFt',     label: 'Punt FT%',       drop: ['gft'] },
  { key: 'pFg',     rank: 'rFg',     label: 'Punt FG%',       drop: ['gfg'] },
  { key: 'pAst',    rank: 'rAst',    label: 'Punt AST',       drop: ['gast'] },
  { key: 'p3',      rank: 'r3',      label: 'Punt 3PM',       drop: ['g3'] },
  { key: 'pBlk',    rank: 'rBlk',    label: 'Punt BLK',       drop: ['gblk'] },
  { key: 'pFgReb',  rank: 'rFgReb',  label: 'Punt FG%+REB',   drop: ['gfg', 'greb'] },
  { key: 'pAstStl', rank: 'rAstStl', label: 'Punt AST+STL',   drop: ['gast', 'gstl'] },
  { key: 'pPtsFt',  rank: 'rPtsFt',  label: 'Punt PTS+FT%',   drop: ['gpts', 'gft'] },
  { key: 'pTriple', rank: 'rTriple', label: 'Punt FG/FT/TO',  drop: ['gfg', 'gft', 'gto'] }
];

/** Settings named range holding a build's replacement level. */
function replName(key) { return 'REPL_' + key.toUpperCase(); }

/** A build's raw punt G-score for row r: G total, less the discounted drops. */
function puntScoreExpr(punt, r) {
  var e = '$' + a1col(B.gtot) + r;
  for (var d = 0; d < punt.drop.length; d++) {
    e += '-(1-PUNT_WEIGHT)*$' + a1col(B[punt.drop[d]]) + r;
  }
  return e;
}

// ------------------------------------------------------------------ helpers

function a1col(n) {
  var s = '';
  while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = (n - m - 1) / 26; }
  return s;
}
function colRange(sheetName, col) {
  return sheetName + '!$' + a1col(col) + '$' + R0 + ':$' + a1col(col) + '$' + RN;
}
/** A fresh sheet is 26 x 1000. Grow it before writing past that. */
function ensureGrid(sh, cols, rows) {
  if (cols && sh.getMaxColumns() < cols) sh.insertColumnsAfter(sh.getMaxColumns(), cols - sh.getMaxColumns());
  if (rows && sh.getMaxRows() < rows) sh.insertRowsAfter(sh.getMaxRows(), rows - sh.getMaxRows());
  return sh;
}
function sheetByName(ss, name, cols, rows) {
  var sh = ss.getSheetByName(name);
  if (sh) {
    sh.clear();
    sh.clearConditionalFormatRules();
    sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).clearDataValidations();
    detachBandings(sh);
  }
  else { sh = ss.insertSheet(name); }
  return ensureGrid(sh, cols, rows);
}
function detachBandings(sh) {
  var bs = sh.getBandings();
  for (var i = 0; i < bs.length; i++) bs[i].remove();
}

/** Paint a merged block header across [c1..c2]. Defaults to row 1. */
function blockHeader(sh, c1, c2, label, color, row) {
  var r = sh.getRange(row || 1, c1, 1, c2 - c1 + 1);
  if (c2 > c1) r.merge();
  r.setValue(label)
   .setBackground(color).setFontColor(COLOR.headerText)
   .setFontWeight('bold').setFontSize(9)
   .setHorizontalAlignment('center').setVerticalAlignment('middle');
}

/** Mark a column as hand-editable: pale fill, blue text. */
function markInput(sh, col, width) {
  sh.getRange(R0, col, POOL_ROWS, 1)
    .setBackground(COLOR.inputBg).setFontColor(COLOR.inputText);
  if (width) sh.setColumnWidth(col, width);
}

function addColorScale(sh, ranges, low, mid, high) {
  var rules = sh.getConditionalFormatRules();
  rules.push(SpreadsheetApp.newConditionalFormatRule()
    .setGradientMinpointWithValue(low, SpreadsheetApp.InterpolationType.NUMBER, String(-2.5))
    .setGradientMidpointWithValue(mid, SpreadsheetApp.InterpolationType.NUMBER, '0')
    .setGradientMaxpointWithValue(high, SpreadsheetApp.InterpolationType.NUMBER, String(2.5))
    .setRanges(ranges).build());
  sh.setConditionalFormatRules(rules);
}
function addRule(sh, rule) {
  var rules = sh.getConditionalFormatRules();
  rules.push(rule);
  sh.setConditionalFormatRules(rules);
}

// ------------------------------------------------------------- entry point

function buildDraftBoard() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.setSpreadsheetTimeZone(ss.getSpreadsheetTimeZone());

  if (typeof PLAYERS === 'undefined') {
    throw new Error('Data.gs is missing — PLAYERS is not defined.');
  }
  if (PLAYERS.length !== POOL_ROWS) {
    throw new Error('Expected ' + POOL_ROWS + ' players, Data.gs has ' + PLAYERS.length);
  }

  var board    = sheetByName(ss, 'Board', B_LAST, RN);
  var settings = sheetByName(ss, 'Settings', 10, 75);
  var draft    = sheetByName(ss, 'Draft Board', D_LAST, RN);
  var punts    = sheetByName(ss, 'Punts', PUNTS.length * 6, 60);
  var tracker  = sheetByName(ss, 'Category Tracker', 8, 60);
  var readme   = sheetByName(ss, 'README', 2, 60);

  writeBoardData(board);
  writeSettingsSkeleton(settings);
  defineNames(ss);
  writeBoardFormulas(board);
  writeSettingsFormulas(settings);
  SpreadsheetApp.flush();

  formatSettings(settings);
  formatBoard(board);
  buildDraftTab(ss, draft, board);
  buildPuntsTab(punts);
  buildTrackerTab(tracker);
  buildReadme(readme);

  ss.setActiveSheet(draft);
  reorderTabs(ss, ['Draft Board', 'Board', 'Punts', 'Category Tracker', 'Settings', 'README']);

  var extra = ss.getSheetByName('Sheet1');
  if (extra) ss.deleteSheet(extra);

  SpreadsheetApp.flush();
  SpreadsheetApp.getActiveSpreadsheet().toast('Draft board built.', 'Done', 5);
}

/**
 * Verification aid: writes the live formula text of representative cells into
 * the build-log cell, so the sheet can be audited without trusting the UI.
 */
function dumpFormulas() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var b = ss.getSheetByName('Board'), d = ss.getSheetByName('Draft Board');
  var picks = [
    ['Board z FG%',  b.getRange(3, B.zfg).getFormula()],
    ['Board z 3PM',  b.getRange(3, B.z3).getFormula()],
    ['Board z PTS',  b.getRange(3, B.zpts).getFormula()],
    ['Board z TO',   b.getRange(3, B.zto).getFormula()],
    ['Board Z TOTAL',b.getRange(3, B.ztot).getFormula()],
    ['Board g PTS',  b.getRange(3, B.gpts).getFormula()],
    ['Board g STL',  b.getRange(3, B.gstl).getFormula()],
    ['Board AdjRank',b.getRange(3, B.adjRank).getFormula()],
    ['DB Drop',      d.getRange(4, D.drop).getFormula()],
    ['DB LocalMed',  d.getRange(4, D.med).getFormula()],
    ['DB Tier',      d.getRange(4, D.tier).getFormula()]
  ];
  var txt = picks.map(function (p) { return p[0] + ' -> ' + p[1]; }).join('  ;;  ');
  ss.getSheetByName('Settings').getRange(63, 1).setNumberFormat('@').setValue(txt);
  SpreadsheetApp.flush();
  return txt;
}

/** Record progress where it survives a thrown exception. */
function _note(msg) {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Settings');
  if (!sh) return;
  sh.getRange(60, 1).setNumberFormat('@').setValue('BUILD LOG');
  sh.getRange(61, 1).setNumberFormat('@').setValue(String(msg).slice(0, 480));
  SpreadsheetApp.flush();
}
function _guard(label, fn) {
  try {
    var detail = fn();
    _note(label + ': OK' + (detail ? ' — ' + detail : ''));
  }
  catch (e) {
    _note(label + ' FAILED: ' + e.message + ' || ' + String(e.stack || '').split('\n').slice(0, 3).join(' >> '));
    throw e;
  }
}

// ------------------------------------------------------- refreshing the data

// Board columns fed by the export, paired with their index in a PLAYERS row.
// In Pool (column 5) is a formula and is deliberately absent, as is everything
// downstream of it.
var REFRESH_MAP = [
  [B.seed, 0], [B.player, 1], [B.team, 2], [B.pos, 3],
  [B.gp, 5], [B.mpg, 6],
  [B.fgm, 7], [B.fga, 8], [B.fgp, 9],
  [B.ftm, 10], [B.fta, 11], [B.ftp, 12],
  [B.tpm, 13], [B.pts, 14], [B.reb, 15], [B.ast, 16],
  [B.stl, 17], [B.blk, 18], [B.to, 19],
  [B.adp, 4]
];

// Columns you fill in by hand. A refresh must never overwrite these.
var HAND_COLS = [B.gp1, B.gp2, B.gp3, B.myGp, B.xrank, B.notes];

function sameCell(a, b) {
  var aBlank = (a === '' || a === null || a === undefined);
  var bBlank = (b === '' || b === null || b === undefined);
  if (aBlank || bBlank) return aBlank && bBlank;
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-9;
  return String(a) === String(b);
}

function boardHeaders(board) {
  var h = board.getRange(2, 1, 1, B_LAST).getValues()[0];
  return h.map(function (x) { return String(x).replace(/\n/g, ' ').trim(); });
}

/**
 * Bring a new export onto the board, changing as little as possible.
 *
 * Only cells whose value actually moved are written. Formulas, formatting, and
 * every hand-edited column are left alone, and everything downstream
 * recalculates on its own because it is all live formulas. Safe to run as often
 * as there is new data.
 */
function refreshData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Refresh', function () {
    if (typeof PLAYERS === 'undefined') {
      throw new Error('Data.gs is missing — PLAYERS is not defined.');
    }
    var board = ss.getSheetByName('Board');
    if (!board) throw new Error('No Board sheet yet. Run a full build first.');
    if (PLAYERS.length !== POOL_ROWS) {
      throw new Error('Data.gs holds ' + PLAYERS.length + ' players but the board is built for ' +
                      POOL_ROWS + '. Use "Full rebuild" instead.');
    }

    var oldNames = board.getRange(R0, B.player, POOL_ROWS, 1).getValues()
                        .map(function (r) { return r[0]; });
    var newNames = PLAYERS.map(function (d) { return d[1]; });

    var sameOrder = true;
    for (var i = 0; i < POOL_ROWS; i++) {
      if (oldNames[i] !== newNames[i]) { sameOrder = false; break; }
    }

    var report = sameOrder
      ? refreshInPlace(board)
      : refreshWithReorder(ss, board, oldNames, newNames);

    SpreadsheetApp.flush();
    ss.toast(report, 'Refresh', 12);
    return report;
  });
}

/**
 * Same players in the same rows — the ordinary case. Write only the cells that
 * differ, and nothing else on the sheet.
 */
function refreshInPlace(board) {
  var head = boardHeaders(board);
  var touched = [], total = 0;

  for (var m = 0; m < REFRESH_MAP.length; m++) {
    var col = REFRESH_MAP[m][0], idx = REFRESH_MAP[m][1];
    var cur = board.getRange(R0, col, POOL_ROWS, 1).getValues();

    // Group the differing rows into contiguous runs so each run is one write.
    var runs = [], open = null, n = 0;
    for (var i = 0; i < POOL_ROWS; i++) {
      if (sameCell(cur[i][0], PLAYERS[i][idx])) { open = null; continue; }
      n++;
      if (open) open.vals.push([PLAYERS[i][idx]]);
      else { open = { start: R0 + i, vals: [[PLAYERS[i][idx]]] }; runs.push(open); }
    }
    if (!n) continue;

    for (var r = 0; r < runs.length; r++) {
      board.getRange(runs[r].start, col, runs[r].vals.length, 1).setValues(runs[r].vals);
    }
    total += n;
    touched.push(head[col - 1] + ' ' + n);
  }

  if (!total) return 'Refresh: no change. 200 players matched, nothing to write.';
  return 'Refresh: ' + total + ' cells updated across ' + touched.length + ' columns (' +
         touched.join(', ') + '). Same 200 players, so hand edits and the Draft Board ' +
         'were left alone. Re-sort the Draft Board when you want the new order.';
}

/**
 * The roster itself changed, so rows have to move. Hand-edited columns are
 * captured by player name and put back afterwards; anyone new starts blank.
 */
function refreshWithReorder(ss, board, oldNames, newNames) {
  var head = boardHeaders(board);

  // Capture hand edits, keyed by player.
  var vals = {}, forms = {};
  HAND_COLS.forEach(function (c) {
    var rng = board.getRange(R0, c, POOL_ROWS, 1);
    vals[c] = rng.getValues();
    forms[c] = rng.getFormulas();
  });
  var hand = {};
  for (var i = 0; i < POOL_ROWS; i++) {
    if (!oldNames[i]) continue;
    var rec = {};
    HAND_COLS.forEach(function (c) {
      if (c === B.myGp) {
        // Only counts as an override once it no longer holds its seeding formula.
        if (!forms[c][i][0] && vals[c][i][0] !== '') rec[c] = vals[c][i][0];
      } else if (vals[c][i][0] !== '') {
        rec[c] = vals[c][i][0];
      }
    });
    hand[oldNames[i]] = rec;
  }

  // Write the export's columns wholesale — every row may now hold a different player.
  REFRESH_MAP.forEach(function (pair) {
    var out = PLAYERS.map(function (d) { return [d[pair[1]]]; });
    board.getRange(R0, pair[0], POOL_ROWS, 1).setValues(out);
  });

  // Rewrite the derived columns, which re-seeds My GP Est from the new projection.
  writeBoardFormulas(board);

  // Put the hand edits back where the player still exists, blank where he does not.
  var restored = 0;
  HAND_COLS.forEach(function (c) {
    if (c === B.myGp) return;                       // handled below, formula-aware
    var out = [];
    for (var i = 0; i < POOL_ROWS; i++) {
      var rec = hand[newNames[i]];
      var v = (rec && rec[c] !== undefined) ? rec[c] : '';
      if (v !== '') restored++;
      out.push([v]);
    }
    board.getRange(R0, c, POOL_ROWS, 1).setValues(out);
  });
  for (var j = 0; j < POOL_ROWS; j++) {
    var rec2 = hand[newNames[j]];
    if (rec2 && rec2[B.myGp] !== undefined) {
      board.getRange(R0 + j, B.myGp).setValue(rec2[B.myGp]);
      restored++;
    }
  }

  SpreadsheetApp.flush();
  buildDraftTab(ss, ensureGrid(ss.getSheetByName('Draft Board'), D_LAST, RN), board);

  var oldSet = {}, newSet = {};
  oldNames.forEach(function (n) { if (n) oldSet[n] = 1; });
  newNames.forEach(function (n) { newSet[n] = 1; });
  var added = newNames.filter(function (n) { return !oldSet[n]; });
  var dropped = oldNames.filter(function (n) { return n && !newSet[n]; });

  var settings = ss.getSheetByName('Settings');
  if (settings) {
    settings.getRange(64, 1).setNumberFormat('@')
      .setValue(added.length ? 'Added: ' + added.join(', ') : 'Added: none');
    settings.getRange(65, 1).setNumberFormat('@')
      .setValue(dropped.length ? 'Dropped: ' + dropped.join(', ') : 'Dropped: none');
  }

  return 'Refresh: roster changed, so rows were rewritten. ' + added.length + ' added, ' +
         dropped.length + ' dropped, ' + restored + ' hand-edited values carried over. ' +
         'Draft Board rebuilt because row positions moved. Names listed below.';
}

/** Step 1: rebuild Settings only. Board data is untouched. */
function step1_Settings() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Settings', function () {
    var sh = sheetByName(ss, 'Settings', 10, 75);
    writeSettingsSkeleton(sh);
    writeSettingsFormulas(sh);
    formatSettings(sh);
  });
}

/** Reformat the Board in place. Data and formulas are untouched. */
function step1b_FormatBoard() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Format Board', function () {
    var sh = ss.getSheetByName('Board');
    sh.clearConditionalFormatRules();
    detachBandings(sh);
    formatBoard(ensureGrid(sh, B_LAST, RN));
  });
}

/** Step 2 of the build: the draft-day tab. Board must already exist. */
function step2_DraftBoard() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Draft Board', function () {
    buildDraftTab(ss, sheetByName(ss, 'Draft Board', D_LAST, RN), ss.getSheetByName('Board'));
  });
}

/** Step 3: the supporting tabs, then tidy the tab order. */
function step3_Rest() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Punts',   function () { buildPuntsTab(sheetByName(ss, 'Punts', PUNTS.length * 6, 60)); });
  _guard('Tracker', function () { buildTrackerTab(sheetByName(ss, 'Category Tracker', 8, 60)); });
  _guard('README',  function () { buildReadme(sheetByName(ss, 'README', 2, 60)); });
  _guard('Tidy', function () {
    reorderTabs(ss, ['Draft Board', 'Board', 'Punts', 'Category Tracker', 'Settings', 'README']);
    var extra = ss.getSheetByName('Sheet1');
    if (extra) ss.deleteSheet(extra);
  });
}

function reorderTabs(ss, order) {
  for (var i = 0; i < order.length; i++) {
    var sh = ss.getSheetByName(order[i]);
    if (sh) { ss.setActiveSheet(sh); ss.moveActiveSheet(i + 1); }
  }
}

// ---------------------------------------------------------------- the Board

function writeBoardData(sh) {
  var head = [];
  head[B.seed] = 'Seed\nRank'; head[B.player] = 'Player'; head[B.team] = 'Team';
  head[B.pos] = 'Pos'; head[B.inPool] = 'In\nPool';
  head[B.gp] = 'GP'; head[B.mpg] = 'MPG';
  head[B.fgm] = 'FGM'; head[B.fga] = 'FGA'; head[B.fgp] = 'FG%';
  head[B.ftm] = 'FTM'; head[B.fta] = 'FTA'; head[B.ftp] = 'FT%';
  head[B.tpm] = '3PM'; head[B.pts] = 'PTS'; head[B.reb] = 'REB'; head[B.ast] = 'AST';
  head[B.stl] = 'STL'; head[B.blk] = 'BLK'; head[B.to] = 'TO';
  head[B.ifg] = 'FG\nImpact'; head[B.ift] = 'FT\nImpact';
  head[B.zfg] = 'z FG%'; head[B.zft] = 'z FT%'; head[B.z3] = 'z 3PM'; head[B.zpts] = 'z PTS';
  head[B.zreb] = 'z REB'; head[B.zast] = 'z AST'; head[B.zstl] = 'z STL'; head[B.zblk] = 'z BLK';
  head[B.zto] = 'z TO'; head[B.ztot] = 'Z\nTOTAL';
  head[B.gfg] = 'g FG%'; head[B.gft] = 'g FT%'; head[B.g3] = 'g 3PM'; head[B.gpts] = 'g PTS';
  head[B.greb] = 'g REB'; head[B.gast] = 'g AST'; head[B.gstl] = 'g STL'; head[B.gblk] = 'g BLK';
  head[B.gto] = 'g TO'; head[B.gtot] = 'G\nTOTAL';
  head[B.vor] = 'VOR'; head[B.vorRank] = 'Rank\n(VOR)';
  head[B.gp1] = 'GP\nY-1'; head[B.gp2] = 'GP\nY-2'; head[B.gp3] = 'GP\nY-3';
  head[B.myGp] = 'My GP\nEst'; head[B.gpCheck] = 'GP\nFlag';
  head[B.adj] = 'ADJUSTED\nVALUE'; head[B.adjRank] = 'Adj\nRank';
  head[B.adp] = 'ADP'; head[B.xrank] = 'XRank'; head[B.gap] = 'GAP';
  for (var i = 0; i < PUNTS.length; i++) {
    head[B[PUNTS[i].key]] = PUNTS[i].label.replace('Punt ', 'P:\n');
    head[B[PUNTS[i].rank]] = '#\n' + PUNTS[i].label.replace('Punt ', '');
  }
  head[B.notes] = 'Notes';

  var row = [];
  for (var c = 1; c <= B_LAST; c++) row.push(head[c] || '');
  // '3PM' would otherwise be parsed as 3:00 PM.
  sh.getRange(2, 1, 1, B_LAST).setNumberFormat('@').setValues([row]);

  // Raw values only. Everything derived is a formula, written separately.
  var vals = [];
  for (var p = 0; p < PLAYERS.length; p++) {
    var d = PLAYERS[p], r = [];
    for (var k = 1; k <= B_LAST; k++) r.push('');
    r[B.seed - 1] = d[0]; r[B.player - 1] = d[1]; r[B.team - 1] = d[2]; r[B.pos - 1] = d[3];
    r[B.adp - 1] = d[4];
    r[B.gp - 1] = d[5];  r[B.mpg - 1] = d[6];
    r[B.fgm - 1] = d[7]; r[B.fga - 1] = d[8];  r[B.fgp - 1] = d[9];
    r[B.ftm - 1] = d[10]; r[B.fta - 1] = d[11]; r[B.ftp - 1] = d[12];
    r[B.tpm - 1] = d[13]; r[B.pts - 1] = d[14]; r[B.reb - 1] = d[15]; r[B.ast - 1] = d[16];
    r[B.stl - 1] = d[17]; r[B.blk - 1] = d[18]; r[B.to - 1] = d[19];
    vals.push(r);
  }
  sh.getRange(R0, 1, vals.length, B_LAST).setValues(vals);
}

function writeBoardFormulas(sh) {
  var f = [];
  for (var i = 0; i < POOL_ROWS; i++) {
    var r = R0 + i;
    var row = {};

    // Every reference below is derived from the B map. Written as literal
    // letters they drift the moment a column is inserted, and drift silently:
    // the formula still computes, against the wrong data. That has bitten this
    // file twice.
    function bc(col) { return '$' + a1col(col) + r; }

    // Pool membership. Seed rank breaks the circularity (see README); MIN_GP
    // keeps a small-sample line from distorting the means and SDs.
    row[B.inPool] = '=IF(AND(' + bc(B.seed) + '<=Q,' + bc(B.gp) + '>=MIN_GP),1,0)';

    // Percentages are volume-weighted. A bare rate is silently wrong.
    row[B.ifg] = '=(' + bc(B.fga) + '/POOL_AVG_FGA)*(' + bc(B.fgp) + '-POOL_FG_PCT)';
    row[B.ift] = '=(' + bc(B.fta) + '/POOL_AVG_FTA)*(' + bc(B.ftp) + '-POOL_FT_PCT)';

    row[B.zfg] = '=' + bc(B.ifg) + '/SD_FG_IMPACT';
    row[B.zft] = '=' + bc(B.ift) + '/SD_FT_IMPACT';
    var zmap = [[B.z3, B.tpm, 'MEAN_3PM', 'SD_3PM'], [B.zpts, B.pts, 'MEAN_PTS', 'SD_PTS'],
                [B.zreb, B.reb, 'MEAN_REB', 'SD_REB'], [B.zast, B.ast, 'MEAN_AST', 'SD_AST'],
                [B.zstl, B.stl, 'MEAN_STL', 'SD_STL'], [B.zblk, B.blk, 'MEAN_BLK', 'SD_BLK']];
    for (var z = 0; z < zmap.length; z++) {
      row[zmap[z][0]] = '=(' + bc(zmap[z][1]) + '-' + zmap[z][2] + ')/' + zmap[z][3];
    }
    // Turnovers count against, so that one subtraction runs the other way.
    row[B.zto]  = '=(MEAN_TO-' + bc(B.to) + ')/SD_TO';
    row[B.ztot] = '=SUM(' + bc(B.zfg) + ':' + bc(B.zto) + ')';

    // G-score = z discounted by how noisy the category is week to week.
    var gmap = [[B.gfg, B.zfg, 'MULT_FG'], [B.gft, B.zft, 'MULT_FT'], [B.g3, B.z3, 'MULT_3PM'],
                [B.gpts, B.zpts, 'MULT_PTS'], [B.greb, B.zreb, 'MULT_REB'],
                [B.gast, B.zast, 'MULT_AST'], [B.gstl, B.zstl, 'MULT_STL'],
                [B.gblk, B.zblk, 'MULT_BLK'], [B.gto, B.zto, 'MULT_TO']];
    for (var g = 0; g < gmap.length; g++) {
      row[gmap[g][0]] = '=' + bc(gmap[g][1]) + '*' + gmap[g][2];
    }
    row[B.gtot] = '=SUM(' + bc(B.gfg) + ':' + bc(B.gto) + ')';

    row[B.vor] = '=' + bc(B.gtot) + '-REPLACEMENT';
    row[B.vorRank] = '=RANK(' + bc(B.vor) + ',B_VOR)';

    // Seeded from the projection, then hand-edited. Section 6a.
    row[B.myGp] = '=' + bc(B.gp);
    row[B.gpCheck] = '=IF(' + bc(B.myGp) + '="","",IF(ABS(' + bc(B.gp) + '-' + bc(B.myGp) +
                     ')>10,"CHECK",""))';
    // Scales VOR, never the G-score: a negative score times a fraction rises.
    // Availability may only ever discount. Below replacement VOR is negative,
    // and a negative times GP/72 moves TOWARD zero — i.e. up the board — which
    // would rank the less available of two equal players higher. The board
    // carries 200 rows against a pool of 156, so those rows exist.
    row[B.adj] = '=IF(' + bc(B.myGp) + '="","",LET(v,' + bc(B.vor) +
                 ',v*IF(v<0,1,' + bc(B.myGp) + '/GP_DIVISOR)))';
    row[B.adjRank] = '=RANK(' + bc(B.adj) + ',B_ADJ)';

    // Blank ADP means no market read. Zero would read as "fairly priced".
    row[B.gap] = '=IF(' + bc(B.adp) + '="","",' + bc(B.adp) + '-' + bc(B.adjRank) + ')';

    // A punt column is the same quantity as ADJUSTED VALUE, computed inside the
    // build: value over that build's own replacement level, then discounted for
    // availability with the same floor. Ranking a raw G-score would reintroduce
    // both defects the main board avoids — a fragile player would outrank a
    // durable one below replacement, and the punt lists would be ordered partly
    // by who misses games.
    for (var q = 0; q < PUNTS.length; q++) {
      row[B[PUNTS[q].key]] =
        '=IF(' + bc(B.myGp) + '="","",LET(v,' + puntScoreExpr(PUNTS[q], r) + '-' +
        replName(PUNTS[q].key) + ',v*IF(v<0,1,' + bc(B.myGp) + '/GP_DIVISOR)))';
      var pc = a1col(B[PUNTS[q].key]);
      row[B[PUNTS[q].rank]] = '=RANK($' + pc + r + ',$' + pc + '$' + R0 + ':$' + pc + '$' + RN + ')';
    }

    var line = [];
    for (var c = 1; c <= B_LAST; c++) line.push(row[c] === undefined ? '' : row[c]);
    f.push(line);
  }

  // One write per contiguous formula block, so we do not clobber the raw values.
  writeBlock(sh, f, B.inPool, B.inPool);
  writeBlock(sh, f, B.ifg, B.vorRank);
  writeBlock(sh, f, B.myGp, B.adjRank);
  writeBlock(sh, f, B.gap, B.gap);
  writeBlock(sh, f, B.pFt, B.rTriple);
}

function writeBlock(sh, grid, c1, c2) {
  var w = c2 - c1 + 1, out = [];
  for (var i = 0; i < grid.length; i++) out.push(grid[i].slice(c1 - 1, c2));
  sh.getRange(R0, c1, out.length, w).setFormulas(out);
}

// -------------------------------------------------------------- the Settings

function writeSettingsSkeleton(sh) {
  sh.getRange('A1').setValue('Draft Board — Settings')
    .setFontSize(15).setFontWeight('bold').setFontColor(COLOR.identity);
  sh.getRange('A2').setValue(
    'Every constant the board uses lives here. Change a value and the whole sheet recalculates. ' +
    'Yellow cells are yours to edit.');

  var league = [
    ['LEAGUE', ''],
    ['Teams', 12],
    ['Roster spots', 13],
    ['Pool size (Q)', '=B4*B5'],
    ['GP divisor', 72],
    ['Min GP for pool', 25],
    ['Tier multiplier', 2],
    ['Scoring format', 'Head-to-Head Categories'],
    ['Punt weight', 0.25]
  ];
  // Only the label columns need forcing to text ('3PM' would become 3:00 PM).
  sh.getRange(1, 1, 75, 1).setNumberFormat('@');   // column A labels
  sh.getRange(1, 4, 20, 1).setNumberFormat('@');   // column D multiplier labels
  sh.getRange(3, 1, league.length, 2).setValues(league);

  var mult = [
    ['G-SCORE MULTIPLIERS', ''],
    ['FG%', 0.75], ['FT%', 0.77], ['3PM', 0.96], ['PTS', 0.87], ['REB', 0.92],
    ['AST', 1.00], ['STL', 0.59], ['BLK', 0.91], ['TO', 0.83]
  ];
  sh.getRange(3, 4, mult.length, 2).setValues(mult);
  sh.getRange(13, 4).setValue('Steals are the headline: half-weight, because the week-to-week noise swamps the edge.')
    .setFontSize(8).setFontColor(COLOR.muted).setFontStyle('italic');
  sh.getRange(14, 4).setValue(
    'Source: Rosenof, arXiv 2307.02188 Table 8, 2022-23 season, normalised to AST = 1.00. ' +
    'The ordering is reliable; the second decimal is not, least of all on FG% and FT%, whose ' +
    'reported variances carry one significant figure. Re-derive from weekly logs in Phase 4.')
    .setFontSize(8).setFontColor(COLOR.muted).setFontStyle('italic').setWrap(true);

  sh.getRange(12, 1).setValue('POOL STATISTICS').setFontWeight('bold');
  sh.getRange(13, 1, 1, 3).setValues([['Category', 'Mean', 'SD']]);
  sh.getRange(14, 1, 7, 1).setValues([['3PM'], ['PTS'], ['REB'], ['AST'], ['STL'], ['BLK'], ['TO']]);

  sh.getRange(22, 1).setValue('POOL CONSTANTS').setFontWeight('bold');
  sh.getRange(23, 1, 8, 1).setValues([
    ['Aggregate FG%'], ['Aggregate FT%'], ['Average FGA'], ['Average FTA'],
    ['SD of FG impact'], ['SD of FT impact'], ['Replacement G-score'], ['Pool average GP']
  ]);

  sh.getRange(32, 1).setValue('SANITY CHECKS').setFontWeight('bold');
  sh.getRange(33, 1, 6, 1).setValues([
    ['Players in pool'], ['Pool shortfall'], ['Z-total across pool'], ['Per-game check'],
    ['GP spread test'], ['ADP coverage']
  ]);

  // Diagnostic only. The board standardises the percentage categories by the SD
  // of the volume-weighted impact column; Rosenof's Table 5(b) defines its sigma
  // over the raw rate instead. Which is intended is unresolved, so both are
  // printed and neither is acted on. Do not change SD_FG_IMPACT without reading
  // the ratio here first.
  sh.getRange(40, 1).setValue('PERCENTAGE DIAGNOSTICS').setFontWeight('bold');
  sh.getRange(41, 1, 4, 1).setValues([
    ['SD of FG% rate'], ['SD of FT% rate'], ['FG ratio impact/rate'], ['FT ratio impact/rate']
  ]);

  // One replacement level per build, so a punt column can be a value over
  // replacement rather than a raw score. Without these the GP adjustment would
  // rank a fragile player above a durable one below replacement.
  sh.getRange(46, 1).setValue('PUNT REPLACEMENT LEVELS').setFontWeight('bold');
  var pr = [];
  for (var pi = 0; pi < PUNTS.length; pi++) pr.push([PUNTS[pi].label]);
  sh.getRange(47, 1, pr.length, 1).setValues(pr);

  sh.getRange(67, 1).setValue('TRACKER THRESHOLDS').setFontWeight('bold');
  sh.getRange(68, 1, 3, 1).setValues([
    ['FG% band'], ['FT% band'], ['Counting band']
  ]);
  sh.getRange(68, 2, 3, 1).setValues([[0.005], [0.010], [0.08]]);
  sh.getRange(68, 2, 2, 1).setNumberFormat('0.0000');
  sh.getRange(70, 2).setNumberFormat('0%');
  sh.getRange(68, 2, 3, 1).setBackground(COLOR.inputBg).setFontColor(COLOR.inputText);
  sh.getRange(71, 1).setValue(
    'The rate bands are in rate units, the counting band is a share of the benchmark. They were ' +
    'one number, 8% of the benchmark, applied to all nine rows — which on a rate means ~3.8 points ' +
    'of FG%, a margin no team ever posts, so those two rows read EVEN forever. These three are ' +
    'starting guesses and want calibrating against a season of real standings.')
    .setFontSize(8).setFontColor(COLOR.muted).setWrap(true);

  sh.getRange(57, 1).setValue('ADP source').setFontWeight('bold');
  sh.getRange(57, 2).setValue('Hashtag Basketball export — NOT Yahoo')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText);
  sh.getRange(58, 1).setValue(
    'The playbook wants Yahoo ADP, because that is the room you are drafting in. This is the ' +
    'export provider\'s own aggregate. Read GAP as "cheap somewhere", not "cheap in my league".')
    .setFontSize(8).setFontColor(COLOR.muted).setWrap(true);

  sh.getRange(3, 7).setValue('LEGEND').setFontWeight('bold');
  sh.getRange(4, 7).setValue('You edit this').setBackground(COLOR.inputBg).setFontColor(COLOR.inputText);
  sh.getRange(5, 7).setValue('Formula — leave alone');
  sh.getRange(6, 7).setValue('CHECK / warning').setBackground(COLOR.flagBg).setFontColor(COLOR.flagText);
  sh.getRange(7, 7).setValue('Generic GP haircut').setBackground(COLOR.haircut);
}

function writeSettingsFormulas(sh) {
  var cats = [['3PM', 'B_3PM'], ['PTS', 'B_PTS'], ['REB', 'B_REB'], ['AST', 'B_AST'],
              ['STL', 'B_STL'], ['BLK', 'B_BLK'], ['TO', 'B_TO']];
  var stats = [];
  for (var i = 0; i < cats.length; i++) {
    stats.push(['=AVERAGEIF(B_POOL,1,' + cats[i][1] + ')',
                '=STDEV(FILTER(' + cats[i][1] + ',B_POOL=1))']);
  }
  sh.getRange(14, 2, stats.length, 2).setFormulas(stats);

  // Aggregate, not the average of the percentages — that is the trap.
  sh.getRange(23, 2, 8, 1).setFormulas([
    ['=SUM(FILTER(B_FGM,B_POOL=1))/SUM(FILTER(B_FGA,B_POOL=1))'],
    ['=SUM(FILTER(B_FTM,B_POOL=1))/SUM(FILTER(B_FTA,B_POOL=1))'],
    ['=AVERAGEIF(B_POOL,1,B_FGA)'],
    ['=AVERAGEIF(B_POOL,1,B_FTA)'],
    ['=STDEV(FILTER(B_IFG,B_POOL=1))'],
    ['=STDEV(FILTER(B_IFT,B_POOL=1))'],
    ['=LARGE(B_GTOT,Q)'],
    ['=AVERAGEIF(B_POOL,1,B_GP)']
  ]);

  sh.getRange(33, 2, 6, 1).setFormulas([
    ['=COUNTIF(B_POOL,1)'],
    ['=LET(short,Q-COUNTIF(B_POOL,1),IF(short=0,"0 — pool is exactly Q",' +
      'short&" seeded players fall below MIN_GP and sit out the means"))'],
    ['=ROUND(SUMPRODUCT(B_ZTOT,B_POOL),3)'],
    ['=IF(AVERAGEIF(B_POOL,1,B_PTS)>100,"SEASON TOTALS — the GP adjustment would double-count. Stop.","Per-game. Safe to apply the GP ratio.")'],
    ['=LET(inband,COUNTIFS(B_GP,">=68",B_GP,"<=74",B_POOL,1)/COUNTIF(B_POOL,1),' +
      'IF(inband>0.55,"Mostly a generic haircut ("&TEXT(inband,"0%")&" sit in 68-74). Override heavily.",' +
      '"Modelled per player ("&TEXT(inband,"0%")&" in 68-74). Lean on it."))'],
    ['=COUNT(B_ADP)&" of "&COUNTA(B_PLAYER)&" have ADP — the rest show a blank Gap, not a zero"']
  ]);

  sh.getRange(41, 2, 4, 1).setFormulas([
    ['=STDEV(FILTER(B_FGP,B_POOL=1))'],
    ['=STDEV(FILTER(B_FTP,B_POOL=1))'],
    ['=SD_FG_IMPACT/B41'],
    ['=SD_FT_IMPACT/B42']
  ]);
  sh.getRange(41, 2, 2, 1).setNumberFormat('0.0000');
  sh.getRange(43, 2, 2, 1).setNumberFormat('0.000');

  // LARGE over an array expression, so no materialised column is needed.
  var repl = [];
  for (var pi = 0; pi < PUNTS.length; pi++) {
    var e = 'B_GTOT';
    for (var d = 0; d < PUNTS[pi].drop.length; d++) {
      e += '-(1-PUNT_WEIGHT)*B_' + PUNTS[pi].drop[d].toUpperCase();
    }
    // ARRAYFORMULA is load-bearing. Without it Sheets does not array-evaluate an
    // arithmetic expression passed as a function argument, so LARGE receives a
    // single value, n=Q overflows it, and every build's replacement level comes
    // back #NUM! — which then propagates into all nine punt columns.
    repl.push(['=LARGE(ARRAYFORMULA(' + e + '),Q)']);
  }
  sh.getRange(47, 2, repl.length, 1).setFormulas(repl);
  sh.getRange(47, 2, repl.length, 1).setNumberFormat('0.0000');
}

function formatSettings(sh) {
  sh.setColumnWidth(1, 175); sh.setColumnWidth(2, 105); sh.setColumnWidth(3, 105);
  sh.setColumnWidth(4, 90); sh.setColumnWidth(5, 80); sh.setColumnWidth(6, 24);
  sh.setColumnWidth(7, 200);

  [[3, 1], [12, 1], [22, 1], [32, 1], [3, 4], [3, 7]].forEach(function (p) {
    sh.getRange(p[0], p[1], 1, 2).setBackground(COLOR.identity)
      .setFontColor(COLOR.headerText).setFontWeight('bold').setFontSize(9);
  });

  // B6 is =B4*B5, so it is deliberately not tinted: yellow means you may type here.
  [4, 5, 7, 8, 9, 10, 11].forEach(function (r) {
    sh.getRange(r, 2).setBackground(COLOR.inputBg).setFontColor(COLOR.inputText);
  });
  sh.getRange(4, 5, 9, 1).setBackground(COLOR.inputBg).setFontColor(COLOR.inputText)
    .setNumberFormat('0.00');
  sh.getRange(6, 2).setNumberFormat('0');       // pool size
  sh.getRange(9, 2).setNumberFormat('0.0');     // tier multiplier

  sh.getRange(10, 2).setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(['Head-to-Head Categories', 'Head-to-Head One Win'], true).build());
  sh.getRange(11, 2).setNumberFormat('0.00');

  sh.getRange(14, 2, 7, 2).setNumberFormat('0.000');
  sh.getRange(23, 2, 2, 1).setNumberFormat('0.0000');
  sh.getRange(25, 2, 4, 1).setNumberFormat('0.0000');
  sh.getRange(29, 2).setNumberFormat('0.0000');
  sh.getRange(30, 2).setNumberFormat('0.0');
  sh.getRange(33, 2).setNumberFormat('0');
  sh.getRange(34, 2).setNumberFormat('0.000');
  sh.getRange(13, 1, 1, 3).setFontWeight('bold').setBackground(COLOR.band);

  for (var sr = 35; sr <= 37; sr++) sh.getRange(sr, 2, 1, 4).merge();
  sh.getRange(35, 2, 3, 4).setWrap(true).setFontSize(9).setVerticalAlignment('middle');
  sh.setColumnWidth(2, 105);

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('SEASON TOTALS')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(35, 2)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('generic haircut')
    .setBackground(COLOR.haircut)
    .setRanges([sh.getRange(36, 2)]).build());

  sh.getRange('A2').setFontColor(COLOR.muted).setFontSize(9);
  sh.setHiddenGridlines(true);
}

// ----------------------------------------------------------- named ranges

function defineNames(ss) {
  var s = 'Settings';
  var names = {
    TEAMS: s + '!$B$4', ROSTER: s + '!$B$5', Q: s + '!$B$6',
    GP_DIVISOR: s + '!$B$7', MIN_GP: s + '!$B$8', TIER_MULT: s + '!$B$9', SCORING: s + '!$B$10',
    PUNT_WEIGHT: s + '!$B$11',
    MULT_FG: s + '!$E$4', MULT_FT: s + '!$E$5', MULT_3PM: s + '!$E$6', MULT_PTS: s + '!$E$7',
    MULT_REB: s + '!$E$8', MULT_AST: s + '!$E$9', MULT_STL: s + '!$E$10',
    MULT_BLK: s + '!$E$11', MULT_TO: s + '!$E$12',
    MEAN_3PM: s + '!$B$14', MEAN_PTS: s + '!$B$15', MEAN_REB: s + '!$B$16', MEAN_AST: s + '!$B$17',
    MEAN_STL: s + '!$B$18', MEAN_BLK: s + '!$B$19', MEAN_TO: s + '!$B$20',
    SD_3PM: s + '!$C$14', SD_PTS: s + '!$C$15', SD_REB: s + '!$C$16', SD_AST: s + '!$C$17',
    SD_STL: s + '!$C$18', SD_BLK: s + '!$C$19', SD_TO: s + '!$C$20',
    POOL_FG_PCT: s + '!$B$23', POOL_FT_PCT: s + '!$B$24',
    POOL_AVG_FGA: s + '!$B$25', POOL_AVG_FTA: s + '!$B$26',
    SD_FG_IMPACT: s + '!$B$27', SD_FT_IMPACT: s + '!$B$28',
    REPLACEMENT: s + '!$B$29', POOL_AVG_GP: s + '!$B$30',
    SD_FG_RATE: s + '!$B$41', SD_FT_RATE: s + '!$B$42',
    TRACK_FG_BAND: s + '!$B$68', TRACK_FT_BAND: s + '!$B$69', TRACK_COUNT_BAND: s + '!$B$70',

    B_POOL: colRange('Board', B.inPool), B_PLAYER: colRange('Board', B.player),
    B_GP: colRange('Board', B.gp),
    B_FGM: colRange('Board', B.fgm), B_FGA: colRange('Board', B.fga),
    B_FTM: colRange('Board', B.ftm), B_FTA: colRange('Board', B.fta),
    B_3PM: colRange('Board', B.tpm), B_PTS: colRange('Board', B.pts),
    B_REB: colRange('Board', B.reb), B_AST: colRange('Board', B.ast),
    B_STL: colRange('Board', B.stl), B_BLK: colRange('Board', B.blk),
    B_TO: colRange('Board', B.to),
    B_IFG: colRange('Board', B.ifg), B_IFT: colRange('Board', B.ift),
    B_ZTOT: colRange('Board', B.ztot), B_GTOT: colRange('Board', B.gtot),
    B_VOR: colRange('Board', B.vor), B_ADJ: colRange('Board', B.adj),
    B_ADJRANK: colRange('Board', B.adjRank),
    B_FGP: colRange('Board', B.fgp), B_FTP: colRange('Board', B.ftp),
    B_ADP: colRange('Board', B.adp)
  };

  // The nine g-score columns, so a punt replacement level can be computed as
  // LARGE() over an array expression instead of a materialised column.
  var gcols = ['gfg', 'gft', 'g3', 'gpts', 'greb', 'gast', 'gstl', 'gblk', 'gto'];
  for (var gi = 0; gi < gcols.length; gi++) {
    names['B_' + gcols[gi].toUpperCase()] = colRange('Board', B[gcols[gi]]);
  }
  // One replacement level per build, laid out from row 47 down.
  for (var qi = 0; qi < PUNTS.length; qi++) {
    names[replName(PUNTS[qi].key)] = s + '!$B$' + (47 + qi);
  }
  var existing = ss.getNamedRanges();
  for (var i = 0; i < existing.length; i++) {
    if (names[existing[i].getName()]) existing[i].remove();
  }
  for (var n in names) ss.setNamedRange(n, ss.getRange(names[n]));
}

// ------------------------------------------------------------ Board format

function formatBoard(sh) {
  var blocks = [
    [B.seed, B.inPool, 'IDENTITY', COLOR.identity],
    [B.gp, B.to, 'RAW PROJECTION  (per game)', COLOR.raw],
    [B.ifg, B.ift, 'IMPACT', COLOR.impact],
    [B.zfg, B.ztot, 'Z-SCORES', COLOR.z],
    [B.gfg, B.gtot, 'G-SCORES  (z × volatility multiplier)', COLOR.g],
    [B.vor, B.vorRank, 'VALUE', COLOR.value],
    [B.gp1, B.adjRank, 'AVAILABILITY', COLOR.avail],
    [B.adp, B.gap, 'MARKET', COLOR.market],
    [B.pFt, B.rTriple, 'PUNT BUILDS', COLOR.punt],
    [B.notes, B.notes, '', COLOR.notes]
  ];
  blocks.forEach(function (b) {
    blockHeader(sh, b[0], b[1], b[2], b[3]);
    sh.getRange(2, b[0], 1, b[1] - b[0] + 1)
      .setBackground(b[3]).setFontColor(COLOR.headerText)
      .setFontWeight('bold').setFontSize(9).setWrap(true)
      .setHorizontalAlignment('center').setVerticalAlignment('middle');
  });

  sh.setFrozenRows(HDR);
  sh.setFrozenColumns(B.inPool);   // block boundary; a freeze cannot split a merge
  sh.setRowHeight(1, 22);
  sh.setRowHeight(2, 36);

  for (var c = 1; c <= B_LAST; c++) sh.setColumnWidth(c, 52);
  sh.setColumnWidth(B.seed, 46);
  sh.setColumnWidth(B.player, 170);
  sh.setColumnWidth(B.team, 48);
  sh.setColumnWidth(B.pos, 74);
  sh.setColumnWidth(B.inPool, 40);
  sh.setColumnWidth(B.ztot, 62); sh.setColumnWidth(B.gtot, 62);
  sh.setColumnWidth(B.adj, 74); sh.setColumnWidth(B.gap, 56);
  sh.setColumnWidth(B.notes, 260);

  var data = sh.getRange(R0, 1, POOL_ROWS, B_LAST);
  data.setFontSize(10).setVerticalAlignment('middle');
  sh.getRange(R0, B.player, POOL_ROWS, 1).setFontWeight('bold');
  sh.getRange(R0, 1, POOL_ROWS, B.inPool).setHorizontalAlignment('left');
  sh.getRange(R0, B.seed, POOL_ROWS, 1).setHorizontalAlignment('center');
  sh.getRange(R0, B.inPool, POOL_ROWS, 1).setHorizontalAlignment('center');

  // Number formats
  sh.getRange(R0, B.gp, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, B.mpg, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, B.fgm, POOL_ROWS, 2).setNumberFormat('0.0');
  sh.getRange(R0, B.fgp, POOL_ROWS, 1).setNumberFormat('0.000');
  sh.getRange(R0, B.ftm, POOL_ROWS, 2).setNumberFormat('0.0');
  sh.getRange(R0, B.ftp, POOL_ROWS, 1).setNumberFormat('0.000');
  sh.getRange(R0, B.tpm, POOL_ROWS, B.to - B.tpm + 1).setNumberFormat('0.0');
  sh.getRange(R0, B.ifg, POOL_ROWS, 2).setNumberFormat('0.0000');
  sh.getRange(R0, B.zfg, POOL_ROWS, B.gtot - B.zfg + 1).setNumberFormat('+0.00;−0.00;0.00');
  sh.getRange(R0, B.vor, POOL_ROWS, 1).setNumberFormat('0.00');
  sh.getRange(R0, B.vorRank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, B.gp1, POOL_ROWS, 4).setNumberFormat('0');
  sh.getRange(R0, B.adj, POOL_ROWS, 1).setNumberFormat('0.000').setFontWeight('bold');
  sh.getRange(R0, B.adjRank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, B.adp, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, B.xrank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, B.gap, POOL_ROWS, 1).setNumberFormat('+0;−0;0').setFontWeight('bold');
  sh.getRange(R0, B.pFt, POOL_ROWS, PUNTS.length).setNumberFormat('+0.00;−0.00;0.00');
  sh.getRange(R0, B.rFt, POOL_ROWS, PUNTS.length).setNumberFormat('0');

  // Hand-edited columns
  [B.gp1, B.gp2, B.gp3, B.myGp, B.xrank, B.notes].forEach(function (c) { markInput(sh, c); });

  // Separators between blocks
  blocks.forEach(function (b) {
    sh.getRange(1, b[0], RN, 1).setBorder(null, true, null, null, null, null,
      COLOR.rule, SpreadsheetApp.BorderStyle.SOLID);
  });

  addColorScale(sh, [sh.getRange(R0, B.zfg, POOL_ROWS, B.ztot - B.zfg + 1),
                     sh.getRange(R0, B.gfg, POOL_ROWS, B.gtot - B.gfg + 1)],
                COLOR.bad, COLOR.mid, COLOR.good);

  // Non-pool rows: muted, so the replacement-level line is visible
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + a1col(B.inPool) + R0 + '=0')
    .setFontColor(COLOR.muted)
    .setRanges([sh.getRange(R0, B.seed, POOL_ROWS, B.pos)]).build());

  // The projection has no player-level opinion inside the generic band
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=AND($' + a1col(B.gp) + R0 + '>=68,$' +
                          a1col(B.gp) + R0 + '<=74)')
    .setBackground(COLOR.haircut)
    .setRanges([sh.getRange(R0, B.gp, POOL_ROWS, 1)]).build());

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo('CHECK')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(R0, B.gpCheck, POOL_ROWS, 1)]).build());

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .setGradientMinpointWithValue(COLOR.bad, SpreadsheetApp.InterpolationType.NUMBER, '-40')
    .setGradientMidpointWithValue(COLOR.mid, SpreadsheetApp.InterpolationType.NUMBER, '0')
    .setGradientMaxpointWithValue(COLOR.good, SpreadsheetApp.InterpolationType.NUMBER, '40')
    .setRanges([sh.getRange(R0, B.gap, POOL_ROWS, 1)]).build());

  // Collapse the wide score blocks so the sheet opens readable
  // Banding is added last so the specific rules above win where they overlap.
  // Row banding without touching the input fills
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ISEVEN(ROW())')
    .setBackground(COLOR.band)
    .setRanges([sh.getRange(R0, 1, POOL_ROWS, B.to)]).build());

  resetColumnGroups(sh, B_LAST);
  groupAndCollapse(sh, B.zfg, B.ztot);
  groupAndCollapse(sh, B.gfg, B.gblk);
  groupAndCollapse(sh, B.rFt, B.rTriple);

  sh.getRange(R0, 1, POOL_ROWS, B_LAST).setBorder(null, null, null, null, null, true,
    COLOR.rule, SpreadsheetApp.BorderStyle.SOLID);
}

/** Flatten every existing column group and unhide, so grouping is idempotent. */
function resetColumnGroups(sh, lastCol) {
  for (var d = 0; d < 5; d++) {
    try { sh.getRange(1, 1, 1, lastCol).shiftColumnGroupDepth(-1); }
    catch (e) { break; }
  }
  try { sh.showColumns(1, lastCol); } catch (e) {}
}

function groupAndCollapse(sh, c1, c2) {
  try {
    sh.getRange(1, c1, 1, c2 - c1 + 1).shiftColumnGroupDepth(1);
    sh.getColumnGroup(c1, 1).collapse();
  } catch (e) { /* grouping is cosmetic; never fail the build over it */ }
}

// ------------------------------------------------------------- Draft Board

var D = {
  rank: 1, tier: 2, player: 3, team: 4, pos: 5, adj: 6, vor: 7, gtot: 8,
  drop: 9, med: 10, brk: 11, projGp: 12, myGp: 13, adp: 14, xrank: 15, gap: 16,
  best: 17, posLeft: 18, drafted: 19, mine: 20, notes: 21,
  hFgm: 22, hFga: 23, hFtm: 24, hFta: 25, h3: 26, hPts: 27, hReb: 28, hAst: 29,
  hStl: 30, hBlk: 31, hTo: 32
};
var D_LAST = D.hTo;

/** Board row numbers, ordered by Adjusted Value descending. */
function boardOrder(board) {
  var adj = board.getRange(R0, B.adj, POOL_ROWS, 1).getValues();
  var idx = [];
  for (var i = 0; i < POOL_ROWS; i++) {
    var v = adj[i][0];
    idx.push({ row: R0 + i, v: (typeof v === 'number' && isFinite(v)) ? v : -1e9 });
  }
  idx.sort(function (a, b) { return b.v - a.v; });
  return idx.map(function (x) { return x.row; });
}

function buildDraftTab(ss, sh, board) {
  var order = boardOrder(board);
  var prior = readCheckState(sh);

  var head = [];
  head[D.rank] = '#'; head[D.tier] = 'TIER'; head[D.player] = 'Player';
  head[D.team] = 'Team'; head[D.pos] = 'Pos';
  head[D.adj] = 'ADJ\nVALUE'; head[D.vor] = 'VOR'; head[D.gtot] = 'G';
  head[D.drop] = 'Drop'; head[D.med] = 'Local\nmed'; head[D.brk] = 'Break';
  head[D.projGp] = 'Proj\nGP'; head[D.myGp] = 'My\nGP';
  head[D.adp] = 'ADP'; head[D.xrank] = 'XRank'; head[D.gap] = 'GAP';
  head[D.best] = 'Best build'; head[D.posLeft] = 'Left\n@pos';
  head[D.drafted] = 'Gone'; head[D.mine] = 'Mine';
  head[D.notes] = 'Notes';
  head[D.hFgm] = 'FGM'; head[D.hFga] = 'FGA'; head[D.hFtm] = 'FTM'; head[D.hFta] = 'FTA';
  head[D.h3] = '3PM'; head[D.hPts] = 'PTS'; head[D.hReb] = 'REB'; head[D.hAst] = 'AST';
  head[D.hStl] = 'STL'; head[D.hBlk] = 'BLK'; head[D.hTo] = 'TO';
  var hrow = [];
  for (var c = 1; c <= D_LAST; c++) hrow.push(head[c] || '');
  sh.getRange(2, 1, 1, D_LAST).setNumberFormat('@').setValues([hrow]);

  var f = [], names = [];
  var allNames = board.getRange(R0, B.player, POOL_ROWS, 1).getValues();
  for (var i = 0; i < order.length; i++) {
    var n = order[i], r = R0 + i, row = {};
    function ref(col) { return '=Board!$' + a1col(col) + '$' + n; }

    row[D.rank] = '=ROW()-' + HDR;
    row[D.player] = ref(B.player); row[D.team] = ref(B.team); row[D.pos] = ref(B.pos);
    row[D.adj] = ref(B.adj); row[D.vor] = ref(B.vor); row[D.gtot] = ref(B.gtot);
    row[D.projGp] = ref(B.gp); row[D.myGp] = ref(B.myGp);
    row[D.adp] = ref(B.adp); row[D.xrank] = ref(B.xrank); row[D.gap] = ref(B.gap);

    // Tiers cut where the value drop is large relative to what is normal nearby.
    // Drops shrink down the board, so a fixed threshold would give one huge blob.
    if (i === 0) {
      row[D.drop] = ''; row[D.med] = ''; row[D.brk] = ''; row[D.tier] = 1;
    } else {
      var dA = '$' + a1col(D.adj), dI = '$' + a1col(D.drop);
      var dJ = '$' + a1col(D.med), dK = '$' + a1col(D.brk), dB = '$' + a1col(D.tier);
      row[D.drop] = '=' + dA + (r - 1) + '-' + dA + r;
      // Fifteen drops centred here, clamped at both ends of the board.
      // INDEX(range,k) resolves to sheet row k+HDR, so these offsets give rows
      // r-7 through r+7. They were r-9 to r+5, which skewed the window up the
      // board where drops are larger, inflating the median and firing breaks
      // late — exactly where the curve steepens and a tier matters most.
      var back = 'ROW()-' + (HDR + 7), fwd = 'ROW()+' + (7 - HDR);
      var dropRange = dI + '$' + R0 + ':' + dI + '$' + RN;
      row[D.med]  = '=MEDIAN(INDEX(' + dropRange + ',MAX(1,' + back + '))' +
                    ':INDEX(' + dropRange + ',MIN(' + POOL_ROWS + ',' + fwd + ')))';
      row[D.brk]  = '=IF(N(' + dJ + r + ')<=0,"",IF(' + dI + r +
                    '>TIER_MULT*' + dJ + r + ',"BREAK",""))';
      row[D.tier] = '=IF(' + dK + r + '="BREAK",' + dB + (r - 1) + '+1,' + dB + (r - 1) + ')';
    }

    var pr = 'Board!$' + a1col(B.rFt) + '$' + n + ':$' + a1col(B.rTriple) + '$' + n;
    // Labels come from PUNTS so they cannot drift out of step with the columns.
    var labels = [];
    for (var pb = 0; pb < PUNTS.length; pb++) {
      labels.push('"' + PUNTS[pb].label.replace('Punt ', '') + '"');
    }
    row[D.best] = '=IF(MIN(' + pr + ')>=Board!$' + a1col(B.adjRank) + '$' + n + ',"—",' +
      'INDEX({' + labels.join(';') + '},MATCH(MIN(' + pr + '),' + pr + ',0))' +
      '&"  "&TEXT(Board!$' + a1col(B.adjRank) + '$' + n + '-MIN(' + pr + '),"+0"))';

    // Playbook step 3 is a scarcity tiebreak — "how many at his position are
    // still in my live tier" — and it had no instrument. Position stays out of
    // the valuation entirely (Rosenof §4.1.3: positional z-scores are a known
    // mistake); this only counts what is left, which is a different question.
    // Yahoo locks lineups daily here, which is the condition that makes
    // eligibility actually pay.
    // How many players still competing for a slot THIS player can fill. Both
    // sides have to be multi-eligible: a PF,C candidate counts toward centres,
    // and a PF,C subject has his centre scarcity measured too. Matching only the
    // subject's first-listed position answered a narrower question than the one
    // the column is for — turning his own eligibility into a single slot.
    var tC = a1col(D.tier), pC = a1col(D.pos), gC = a1col(D.drafted);
    function dcol(c) { return '$' + c + '$' + R0 + ':$' + c + '$' + RN; }
    row[D.posLeft] = '=IF($' + tC + r + '="","",SUMPRODUCT((' + dcol(tC) + '=$' + tC + r + ')*(' +
      dcol(gC) + '=FALSE)*REGEXMATCH(' + dcol(pC) + ',SUBSTITUTE($' + pC + r + ',",","|"))))';

    row[D.hFgm] = ref(B.fgm); row[D.hFga] = ref(B.fga);
    row[D.hFtm] = ref(B.ftm); row[D.hFta] = ref(B.fta);
    row[D.h3] = ref(B.tpm); row[D.hPts] = ref(B.pts); row[D.hReb] = ref(B.reb);
    row[D.hAst] = ref(B.ast); row[D.hStl] = ref(B.stl); row[D.hBlk] = ref(B.blk);
    row[D.hTo] = ref(B.to);

    var line = [];
    for (var c = 1; c <= D_LAST; c++) line.push(row[c] === undefined ? '' : row[c]);
    f.push(line);
    names.push(allNames[n - R0][0]);
  }

  writeGrid(sh, f, 1, D.gtot);
  writeGrid(sh, f, D.drop, D.gap);
  writeGrid(sh, f, D.best, D.posLeft);
  writeGrid(sh, f, D.hFgm, D.hTo);

  sh.getRange(R0, D.drafted, POOL_ROWS, 2).insertCheckboxes();
  restoreCheckState(sh, names, prior);
  formatDraftTab(sh);
  drawTierBreaks(sh);
}

function writeGrid(sh, grid, c1, c2) {
  var out = [];
  for (var i = 0; i < grid.length; i++) out.push(grid[i].slice(c1 - 1, c2));
  var rng = sh.getRange(R0, c1, out.length, c2 - c1 + 1);
  // Tier column mixes a literal 1 with formulas; setValues handles both.
  var hasLiteral = false;
  for (var i = 0; i < out.length; i++)
    for (var j = 0; j < out[i].length; j++)
      if (out[i][j] !== '' && String(out[i][j]).charAt(0) !== '=') hasLiteral = true;
  if (hasLiteral) rng.setValues(out); else rng.setFormulas(out);
}

function readCheckState(sh) {
  var state = {};
  try {
    if (sh.getLastRow() < R0) return state;
    var n = Math.min(POOL_ROWS, sh.getLastRow() - HDR);
    var names = sh.getRange(R0, D.player, n, 1).getValues();
    // Notes sits beside the two checkboxes and is captured with them. A re-sort
    // moves every player's row; without this the note stays put and ends up
    // beside whoever landed on that row instead.
    var span = D.notes - D.drafted + 1;
    var flags = sh.getRange(R0, D.drafted, n, span).getValues();
    for (var i = 0; i < n; i++) {
      if (names[i][0]) {
        state[names[i][0]] = [flags[i][0] === true, flags[i][1] === true, flags[i][2] || ''];
      }
    }
  } catch (e) { /* first build */ }
  return state;
}

function restoreCheckState(sh, names, prior) {
  var out = [], any = false;
  for (var i = 0; i < names.length; i++) {
    var p = prior[names[i]];
    if (p && (p[0] || p[1] || p[2])) any = true;
    out.push(p || [false, false, '']);
  }
  if (any) sh.getRange(R0, D.drafted, out.length, D.notes - D.drafted + 1).setValues(out);
}

/**
 * Draw the tier cliffs. Conditional formatting cannot set borders, and a tier
 * break has to read at a glance without parsing the tier number.
 */
function drawTierBreaks(sh) {
  SpreadsheetApp.flush();
  var span = sh.getRange(R0, 1, POOL_ROWS, D.notes);
  span.setBorder(false, null, null, null, null, false);
  var brk = sh.getRange(R0, D.brk, POOL_ROWS, 1).getValues();
  var cuts = 0;
  for (var i = 0; i < brk.length; i++) {
    if (brk[i][0] === 'BREAK') {
      sh.getRange(R0 + i, 1, 1, D.notes).setBorder(
        true, null, null, null, null, null,
        COLOR.identity, SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
      cuts++;
    }
  }
  return cuts + 1;
}

function formatDraftTab(sh) {
  var blocks = [
    [D.rank, D.pos, 'WHO', COLOR.identity],
    [D.adj, D.gtot, 'VALUE', COLOR.value],
    [D.drop, D.brk, 'TIERING', COLOR.z],
    [D.projGp, D.myGp, 'GP', COLOR.avail],
    [D.adp, D.gap, 'MARKET', COLOR.market],
    [D.best, D.best, 'BUILD', COLOR.punt],
    [D.posLeft, D.notes, 'DRAFT DAY', COLOR.identity],
    [D.hFgm, D.hTo, 'CATEGORY FEED (hidden helper)', COLOR.notes]
  ];
  blocks.forEach(function (b) {
    blockHeader(sh, b[0], b[1], b[2], b[3]);
    sh.getRange(2, b[0], 1, b[1] - b[0] + 1)
      .setBackground(b[3]).setFontColor(COLOR.headerText)
      .setFontWeight('bold').setFontSize(9).setWrap(true)
      .setHorizontalAlignment('center').setVerticalAlignment('middle');
  });

  sh.setFrozenRows(HDR);
  sh.setFrozenColumns(D.pos);      // block boundary; a freeze cannot split a merge
  sh.setRowHeight(1, 22); sh.setRowHeight(2, 34);

  sh.setColumnWidth(D.rank, 38); sh.setColumnWidth(D.tier, 44);
  sh.setColumnWidth(D.player, 175); sh.setColumnWidth(D.team, 48); sh.setColumnWidth(D.pos, 76);
  sh.setColumnWidth(D.adj, 68); sh.setColumnWidth(D.vor, 54); sh.setColumnWidth(D.gtot, 54);
  sh.setColumnWidth(D.drop, 50); sh.setColumnWidth(D.med, 50); sh.setColumnWidth(D.brk, 56);
  sh.setColumnWidth(D.projGp, 44); sh.setColumnWidth(D.myGp, 44);
  sh.setColumnWidth(D.adp, 50); sh.setColumnWidth(D.xrank, 50); sh.setColumnWidth(D.gap, 52);
  sh.setColumnWidth(D.best, 110);
  sh.setColumnWidth(D.drafted, 50); sh.setColumnWidth(D.mine, 50);
  sh.setColumnWidth(D.notes, 300);

  sh.getRange(R0, 1, POOL_ROWS, D_LAST).setFontSize(10).setVerticalAlignment('middle');
  sh.getRange(R0, D.player, POOL_ROWS, 1).setFontWeight('bold');
  sh.getRange(R0, D.rank, POOL_ROWS, 2).setHorizontalAlignment('center');
  sh.getRange(R0, D.tier, POOL_ROWS, 1).setFontWeight('bold');

  sh.getRange(R0, D.adj, POOL_ROWS, 1).setNumberFormat('0.000').setFontWeight('bold');
  sh.getRange(R0, D.vor, POOL_ROWS, 2).setNumberFormat('0.00');
  sh.getRange(R0, D.drop, POOL_ROWS, 2).setNumberFormat('0.000');
  sh.getRange(R0, D.projGp, POOL_ROWS, 2).setNumberFormat('0');
  sh.getRange(R0, D.adp, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, D.xrank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, D.gap, POOL_ROWS, 1).setNumberFormat('+0;−0;0').setFontWeight('bold');
  sh.getRange(R0, D.hFgm, POOL_ROWS, D.hTo - D.hFgm + 1).setNumberFormat('0.0');

  markInput(sh, D.notes);
  sh.getRange(R0, D.notes, POOL_ROWS, 1).setFontWeight('normal');

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .setGradientMinpointWithValue(COLOR.bad, SpreadsheetApp.InterpolationType.NUMBER, '-40')
    .setGradientMidpointWithValue(COLOR.mid, SpreadsheetApp.InterpolationType.NUMBER, '0')
    .setGradientMaxpointWithValue(COLOR.good, SpreadsheetApp.InterpolationType.NUMBER, '40')
    .setRanges([sh.getRange(R0, D.gap, POOL_ROWS, 1)]).build());

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo('BREAK')
    .setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(R0, D.brk, POOL_ROWS, 1)]).build());

  // Both key off the D map. Written as literal letters these pointed one column
  // short the moment a column was inserted ahead of them, which turned Gone
  // green and left Mine doing nothing — on the two controls used on the clock.
  // Drafted players fall away without being deleted.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + a1col(D.drafted) + R0 + '=TRUE')
    .setBackground(COLOR.drafted).setFontColor(COLOR.muted).setStrikethrough(true)
    .setRanges([sh.getRange(R0, 1, POOL_ROWS, D.notes)]).build());

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + a1col(D.mine) + R0 + '=TRUE')
    .setBackground('#E6F4EA').setFontColor('#137333').setStrikethrough(false)
    .setRanges([sh.getRange(R0, 1, POOL_ROWS, D.notes)]).build());

  // Banding last, so BREAK / drafted / mine keep their formatting.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ISEVEN(ROW())')
    .setBackground(COLOR.band)
    .setRanges([sh.getRange(R0, 1, POOL_ROWS, D.best)]).build());

  sh.getRange(R0, D.projGp, POOL_ROWS, 1).setFontColor(COLOR.muted);
  resetColumnGroups(sh, D_LAST);
  groupAndCollapse(sh, D.drop, D.med);
  groupAndCollapse(sh, D.hFgm, D.hTo);
  sh.hideColumns(D.hFgm, D.hTo - D.hFgm + 1);
}

// -------------------------------------------------------------------- Punts

function buildPuntsTab(sh) {
  sh.getRange('A1').setValue('Punt builds — who each build gets at a discount')
    .setFontSize(14).setFontWeight('bold').setFontColor(COLOR.punt);
  // Yahoo's own names. The old test read "Most Categories", which is ESPN's word
  // for what Yahoo calls One Win — and once the dropdown was corrected to Yahoo's
  // wording that branch could never fire, so the tab always gave the same advice.
  sh.getRange('A2').setFormula(
    '=IF(SCORING="Head-to-Head One Win",' +
    '"One Win: the week resolves to a single result, so once you have won five categories a sixth adds nothing — punting pays. Aim to win six or seven, not exactly five.",' +
    '"Head-to-Head Categories: every category is settled separately every week, so abandoning three is expensive — soft-punt at most, and stay balanced.")')
    .setFontColor(COLOR.muted).setFontSize(10);
  sh.getRange('A3').setValue(
    'Sorted by Punt Gap = ADP − rank inside that build. A big positive number means the room prices him ' +
    'normally and this build values him far higher. Learn the top ten of each before draft day; a build ' +
    'rank is not a licence to reach.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(3, 1, 1, 12).merge();
  sh.setRowHeight(3, 30);

  var top = 40;
  for (var i = 0; i < PUNTS.length; i++) {
    var c0 = 1 + i * 6;                       // 5 columns + a gutter
    var pc = a1col(B[PUNTS[i].key]);
    var rc = a1col(B[PUNTS[i].rank]);
    var adpc = a1col(B.adp);

    blockHeader(sh, c0, c0 + 4, PUNTS[i].label.toUpperCase(), COLOR.punt, 4);
    sh.getRange(5, c0, 1, 5).setNumberFormat('@').setValues([['#', 'Player', 'Score', 'ADP', 'GAP']])
      .setBackground(COLOR.punt).setFontColor(COLOR.headerText)
      .setFontWeight('bold').setFontSize(9).setHorizontalAlignment('center');

    // A player with no ADP is one the market has not priced — a role change, a
    // returning injury, a rookie whose situation just moved. Those are exactly
    // the names a build most wants cheap, and they used to be FILTERed off the
    // tab entirely. They have no Gap, so they sort last on a sentinel rather
    // than being deleted; the Gap cell stays blank, never zero.
    function bcol(c) { return 'Board!$' + c + '$' + R0 + ':$' + c + '$' + RN; }
    var gapExpr = 'IF(' + bcol(adpc) + '="","",' + bcol(adpc) + '-' + bcol(rc) + ')';
    var sortKey = 'IF(' + bcol(adpc) + '="",-1E9,' + bcol(adpc) + '-' + bcol(rc) + ')';
    var arr = '{' + bcol(rc) + ',' + bcol('B') + ',' + bcol(pc) + ',' +
              bcol(adpc) + ',' + gapExpr + ',' + sortKey + '}';
    sh.getRange(6, c0).setFormula(
      '=ARRAY_CONSTRAIN(SORT(FILTER(' + arr + ',' + bcol(rc) + '<>""),6,FALSE),' + top + ',5)');

    sh.setColumnWidth(c0, 34);
    sh.setColumnWidth(c0 + 1, 150);
    sh.setColumnWidth(c0 + 2, 52);
    sh.setColumnWidth(c0 + 3, 48);
    sh.setColumnWidth(c0 + 4, 48);
    sh.setColumnWidth(c0 + 5, 18);

    sh.getRange(6, c0, top, 1).setNumberFormat('0');
    sh.getRange(6, c0 + 2, top, 1).setNumberFormat('+0.00;−0.00;0.00');
    sh.getRange(6, c0 + 3, top, 1).setNumberFormat('0.0');
    sh.getRange(6, c0 + 4, top, 1).setNumberFormat('+0;−0;0').setFontWeight('bold');

    addRule(sh, SpreadsheetApp.newConditionalFormatRule()
      .setGradientMinpointWithValue(COLOR.mid, SpreadsheetApp.InterpolationType.NUMBER, '0')
      .setGradientMaxpointWithValue(COLOR.good, SpreadsheetApp.InterpolationType.NUMBER, '60')
      .setRanges([sh.getRange(6, c0 + 4, top, 1)]).build());
    addRule(sh, SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=ISEVEN(ROW())')
      .setBackground(COLOR.band)
      .setRanges([sh.getRange(6, c0, top, 5)]).build());
  }
  sh.setFrozenRows(5);
  sh.getRange(6, 1, top, 36).setFontSize(10);
  sh.setHiddenGridlines(true);
}

// -------------------------------------------------------- Category Tracker

function buildTrackerTab(sh) {
  sh.getRange('A1').setValue('Category tracker')
    .setFontSize(14).setFontWeight('bold').setFontColor(COLOR.value);
  sh.getRange('A2').setValue(
    'Tick "Mine" on the Draft Board and this fills in. Benchmark is what an average team from the pool ' +
    'would post over the same number of players, so the comparison holds at any roster size.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(2, 1, 1, 6).merge();
  sh.setRowHeight(2, 28);

  var DB = "'Draft Board'!";
  /** A Draft Board column as an absolute A1 range, keyed off the D map. */
  function dbCol(col) {
    var L = a1col(col);
    return DB + '$' + L + '$' + R0 + ':$' + L + '$' + RN;
  }
  function sumMine(col) {
    return 'SUMIF(' + dbCol(D.mine) + ',TRUE,' + dbCol(col) + ')';
  }
  var count = 'COUNTIF(' + dbCol(D.mine) + ',TRUE)';

  sh.getRange(4, 1).setValue('Players on my roster').setFontWeight('bold');
  sh.getRange(4, 2).setFormula('=' + count).setNumberFormat('0');

  sh.getRange(6, 1, 1, 6).setValues([['Category', 'My team', 'Average team', 'Edge', 'Read', 'Punted']])
    .setBackground(COLOR.value).setFontColor(COLOR.headerText).setFontWeight('bold').setFontSize(9);

  // The benchmark is what an average team holds RIGHT NOW, not what an average
  // pool member is worth. After round k every manager holds k players and those
  // 12k are the top 12k of the pool, not a random sample of it. Benchmarking
  // against all 156 makes the target far too low early — every counting row
  // reads STRONG through round 10 — and only becomes correct at a full roster.
  // Basketball Monster ships both and says its drafted-so-far summary "carries
  // the more weight throughout the draft"; this is that one.
  var drafted = 'B_ADJRANK<=TEAMS*' + count;
  function benchCount(range) {
    return '=IF(' + count + '=0,"",AVERAGE(FILTER(' + range + ',' + drafted + '))*' + count + ')';
  }
  function benchRate(makes, atts) {
    return '=IF(' + count + '=0,"",SUM(FILTER(' + makes + ',' + drafted + '))' +
           '/SUM(FILTER(' + atts + ',' + drafted + ')))';
  }

  // FG% and FT% are aggregates of makes over attempts, never an average of rates.
  var rows = [
    ['FG%', '=IF(' + count + '=0,"",' + sumMine(D.hFgm) + '/' + sumMine(D.hFga) + ')',
      benchRate('B_FGM', 'B_FGA'), '0.000'],
    ['FT%', '=IF(' + count + '=0,"",' + sumMine(D.hFtm) + '/' + sumMine(D.hFta) + ')',
      benchRate('B_FTM', 'B_FTA'), '0.000'],
    ['3PM', '=IF(' + count + '=0,"",' + sumMine(D.h3) + ')', benchCount('B_3PM'), '0.0'],
    ['PTS', '=IF(' + count + '=0,"",' + sumMine(D.hPts) + ')', benchCount('B_PTS'), '0.0'],
    ['REB', '=IF(' + count + '=0,"",' + sumMine(D.hReb) + ')', benchCount('B_REB'), '0.0'],
    ['AST', '=IF(' + count + '=0,"",' + sumMine(D.hAst) + ')', benchCount('B_AST'), '0.0'],
    ['STL', '=IF(' + count + '=0,"",' + sumMine(D.hStl) + ')', benchCount('B_STL'), '0.0'],
    ['BLK', '=IF(' + count + '=0,"",' + sumMine(D.hBlk) + ')', benchCount('B_BLK'), '0.0'],
    ['TO',  '=IF(' + count + '=0,"",' + sumMine(D.hTo) + ')',  benchCount('B_TO'),  '0.0']
  ];

  for (var i = 0; i < rows.length; i++) {
    var r = 7 + i;
    sh.getRange(r, 1).setNumberFormat('@').setValue(rows[i][0]).setFontWeight('bold');
    sh.getRange(r, 2).setFormula(rows[i][1]).setNumberFormat(rows[i][3]);
    sh.getRange(r, 3).setFormula(rows[i][2]).setNumberFormat(rows[i][3]);
    // Turnovers count against, so the sign flips on that row alone.
    var edge = (rows[i][0] === 'TO')
      ? '=IF($B' + r + '="","",$C' + r + '-$B' + r + ')'
      : '=IF($B' + r + '="","",$B' + r + '-$C' + r + ')';
    // A rate edge lives in the third decimal; one decimal hides STRONG vs EVEN.
    var isRate = (rows[i][0] === 'FG%' || rows[i][0] === 'FT%');
    sh.getRange(r, 4).setFormula(edge)
      .setNumberFormat(isRate ? '+0.000;−0.000;0.000' : '+0.0;−0.0;0.0');
    // A rate row's band is an absolute margin in rate units; a counting row's is
    // a share of its benchmark. One shared 8%-of-benchmark rule made STRONG and
    // WEAK unreachable on FG% and FT%, so the two categories where a 9-cat
    // roster most often quietly falls apart were the two it could not see.
    var band = (rows[i][0] === 'FG%') ? 'TRACK_FG_BAND'
             : (rows[i][0] === 'FT%') ? 'TRACK_FT_BAND'
             : 'ABS($C' + r + ')*TRACK_COUNT_BAND';
    sh.getRange(r, 5).setFormula(
      '=IF($F' + r + '=TRUE,"PUNTED",IF($B' + r + '="","",' +
      'IF($D' + r + '>' + band + ',"STRONG",IF($D' + r + '<-' + band + ',"WEAK","EVEN"))))');
  }

  // A punted category is conceded on purpose. Without a way to say so the tab
  // keeps reporting it live and keeps advising you to spend a pick fixing it.
  sh.getRange(7, 6, 9, 1).insertCheckboxes();
  sh.getRange(16, 1).setValue(
    'Tick Punted to concede a category: it stops counting toward what you still need. Read the ' +
    'rest as a steer on where the next pick goes — spend it on an EVEN category, not a STRONG one.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(16, 1, 1, 6).merge();
  sh.setRowHeight(16, 30);

  sh.getRange(17, 1).setValue(
    'Aim for roughly 60% in your live categories, not 90%. Winning a category 60–30 pays the same as ' +
    '46–45, so every point of margin past "win" is wasted capital. Spend it on an EVEN category instead.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(17, 1, 1, 5).merge();
  sh.setRowHeight(17, 32);

  sh.getRange(19, 1).setValue('MY ROSTER').setFontWeight('bold')
    .setBackground(COLOR.identity).setFontColor(COLOR.headerText);
  sh.getRange(19, 1, 1, 3).merge();
  sh.getRange(20, 1, 1, 3).setValues([['#', 'Player', 'Pos']])
    .setFontWeight('bold').setBackground(COLOR.band);
  sh.getRange(21, 1).setFormula(
    '=IFERROR(SORT(FILTER({' + dbCol(D.rank) + ',' + dbCol(D.player) + ',' +
    dbCol(D.pos) + '},' + dbCol(D.mine) + '=TRUE),1,TRUE),"Nothing ticked yet")');

  sh.setColumnWidth(1, 120); sh.setColumnWidth(2, 110); sh.setColumnWidth(3, 120);
  sh.setColumnWidth(4, 80); sh.setColumnWidth(5, 90); sh.setColumnWidth(6, 64);
  sh.getRange(6, 1, 11, 6).setFontSize(10);

  addRule(sh, SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo('STRONG')
    .setBackground('#E6F4EA').setFontColor('#137333').setBold(true)
    .setRanges([sh.getRange(7, 5, 9, 1)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo('WEAK')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(7, 5, 9, 1)]).build());
  sh.setHiddenGridlines(true);
}

// ------------------------------------------------------------------ README

// Section banners, found by label rather than by row number. Inserting a row
// used to silently shift every hardcoded index and paint a blank line.
var README_SECTIONS = [
  'HOW TO USE IT',
  'THE TWO THINGS THAT ARE NOT AUTOMATIC',
  'COLOURS',
  'CHEAT SHEET — WHAT EVERY NUMBER ON THIS SHEET MEANS',
  'THINGS WORTH KNOWING'
];
var README_STEPS = [
  'THE POOL — what every number is measured against',
  'STEP 1 — SCORE EVERY CATEGORY  (z)',
  'STEP 2 — DISCOUNT FOR WEEKLY NOISE  (g)',
  'STEP 3 — TURN IT INTO VALUE',
  'STEP 4 — ADJUST FOR GAMES PLAYED',
  'STEP 5 — COMPARE AGAINST THE ROOM',
  'STEP 6 — CUT THE TIERS',
  'STEP 7 — PUNT BUILDS',
  'THE CATEGORY TRACKER'
];

function readmeRowOf(L, label) {
  for (var i = 0; i < L.length; i++) if (L[i][0] === label) return i + 1;
  return 0;
}

// The README tab's content, hoisted to the top level so export_readme.js can
// generate the markdown copy in docs/ from the same source the sheet uses.
// [name, formula, what it actually means]. Formulas lead with a space so
// Sheets stores them as text instead of trying to evaluate them.
var README_ROWS = [
  ['9-Cat H2H Draft Board', '', ''],
  ['Built from docs/references/fantasy-basketball-draft-playbook.md. Every number is a live formula — click any cell and read it.', '', ''],
  ['', '', ''],

  ['HOW TO USE IT', '', ''],
  ['Draft Board', '', 'The tab you use on the clock. Sorted by Adjusted Value. Tick Gone as players come off the board, Mine for your own picks.'],
  ['Board', '', 'The audit. One row per player, every intermediate number visible. Collapse the z and g blocks with the +/− above the columns.'],
  ['Punts', '', 'Nine builds, each showing who it gets at a discount. Homework before draft day, not reading material during it.'],
  ['Category Tracker', '', 'Fills itself from the Mine checkboxes.'],
  ['Settings', '', 'Every constant. Change one and the whole board recalculates.'],
  ['', '', ''],

  ['THE TWO THINGS THAT ARE NOT AUTOMATIC', '', ''],
  ['Re-seed the pool', '', 'The pool is "the top 156 by value", but you need values to know who those are. Seed Rank breaks that circle. Once the board settles, run  Draft Board ▸ Re-seed pool from current ranks,  then rebuild. Twice is enough — the set stops changing.'],
  ['Re-sort the board', '', 'Row order is deliberately static so nothing moves under you mid-draft. After editing GP estimates, run  Draft Board ▸ Rebuild & re-sort.  Your checkboxes survive it.'],
  ['', '', ''],

  ['COLOURS', '', ''],
  ['Pale yellow + blue text', '', 'You type here. Everything else is a formula.'],
  ['Red → white → green', '', 'Z and G scores, centred on the pool average.'],
  ['Green GAP', '', 'The room rates him lower than you do. Target.'],
  ['Red GAP', '', 'The room rates him higher than you do. Let him go.'],
  ['Amber GP cell', '', 'Projected GP sits in 68–74, the generic-haircut band. The projection has no opinion about this player; yours is worth more.'],
  ['Thick line across a row', '', 'A tier break. Waiting past it costs you something real.'],
  ['', '', ''],

  ['CHEAT SHEET — WHAT EVERY NUMBER ON THIS SHEET MEANS', '', ''],
  ['', '', 'Read top to bottom and it walks one player from his raw stat line all the way to his final rank. Left column is the name as it appears on the sheet, middle is the actual formula, right is what it is doing in plain English.'],
  ['', '', ''],

  ['THE POOL — what every number is measured against', '', ''],
  ['Q   (pool size)', ' =Teams × Roster spots', '12 × 13 = 156. The number of players who will actually get drafted. Every average and spread on this sheet is worked out across those 156 and nobody else. Measure against all 500 NBA players instead and almost everyone looks above average, which tells you nothing.'],
  ['In Pool', ' =IF(AND(Seed Rank<=Q, GP>=MIN_GP), 1, 0)', '1 if this player counts toward the averages, 0 if he does not. Keeps deep bench players and tiny injury-shortened samples from dragging the averages around. They still appear on the board — they just do not get a vote on what "average" means.'],
  ['Mean   (one per category)', ' =AVERAGEIF(In Pool, 1, that category)', 'What a typical drafted player does in that category. This is the line everyone is measured against.'],
  ['SD   (one per category)', ' =STDEV(FILTER(category, In Pool = 1))', 'Standard deviation — how spread out that category is across the pool. Points range over tens, steals over fractions, so each category needs its own yardstick before you can compare them.'],
  ['Aggregate FG%  /  FT%', ' =SUM(pool FGM) / SUM(pool FGA)', 'The pool\'s real shooting percentage: total makes divided by total attempts. Not the average of everyone\'s percentage — that would count a 3-shot night the same as an 18-shot night and give you the wrong number to compare against.'],
  ['Average FGA  /  FTA', ' =AVERAGEIF(In Pool, 1, FGA)', 'How many shots a typical drafted player takes. Used to work out whether a player\'s shooting percentage actually moves your team or barely registers.'],
  ['SD of FG impact  /  FT impact', ' =STDEV(FILTER(FG impact, In Pool = 1))', 'The spread of the shooting-impact numbers below, so those can be put on the same scale as every other category.'],
  ['REPLACEMENT', ' =LARGE(G TOTAL, Q)', 'The G-score of the 156th best player — the last man who gets drafted at all. This becomes the zero point for value: anyone below him is someone you could have off waivers for nothing.'],
  ['Punt replacement levels', ' =LARGE(that build\'s scores, Q)', 'The same zero point, worked out again inside each punt build. A build changes who the last drafted player is, so it needs its own line. Without these a punt column would be a raw score rather than a value, and the games-played step below would run backwards on it.'],
  ['Pool shortfall', ' =Q − COUNTIF(In Pool, 1)', 'How many of the top 156 seeds fell below MIN_GP and sat out the averages. Normally 0. If it is not, the pool is smaller than Q and this tells you by how much — the count is legitimately below 156, not broken.'],
  ['', '', ''],

  ['STEP 1 — SCORE EVERY CATEGORY  (z)', '', ''],
  ['FG impact', ' =(FGA / POOL_AVG_FGA) × (FG% − POOL_FG_PCT)', 'How much this player actually moves your team\'s field goal percentage. Two parts: how far above or below the pool average he shoots, multiplied by how many shots he takes relative to a normal player. Someone shooting 60% on 3 attempts barely registers; 60% on 18 attempts is a real edge. Using the raw percentage on its own is the single most common way to get a 9-cat board wrong.'],
  ['FT impact', ' =(FTA / POOL_AVG_FTA) × (FT% − POOL_FT_PCT)', 'Exactly the same idea for free throws, weighted by attempts.'],
  ['z FG%', ' =FG impact / SD_FG_IMPACT', 'The shooting impact above, converted onto the same scale as every other category so it can be added to them.'],
  ['z FT%', ' =FT impact / SD_FT_IMPACT', 'Same for free throws.'],
  ['z 3PM, PTS, REB, AST, STL, BLK', ' =(player − pool mean) / pool SD', 'How good he is at that one category, in a single number. Zero means exactly average for a drafted player. +1 means better than roughly five out of every six of them; −1 means worse. Dividing by the spread is the trick that lets you add rebounds and steals together even though 10 rebounds and 2 steals are nothing alike.'],
  ['z TO', ' =(pool mean − player) / pool SD', 'Turnovers, with the subtraction turned around. Turnovers count against you, so fewer is better — flipping it means a careful player scores positive like he does everywhere else on the sheet, and the nine scores can simply be added up.'],
  ['Z TOTAL', ' =SUM(the nine z-scores)', 'All nine categories added together. One number for the whole player. This is the classic fantasy basketball ranking, and it is the input to the next step rather than the final answer.'],
  ['', '', ''],

  ['STEP 2 — DISCOUNT FOR WEEKLY NOISE  (g)', '', ''],
  ['g FG%, FT%, 3PM, PTS, REB, AST, STL, BLK, TO', ' =that z-score × its multiplier', 'The same score, knocked down by how much that category swings from week to week. In head-to-head you play one opponent for one week, so what matters is not the season average — it is whether your edge actually shows up in the seven days that count. Steals bounce around so violently that a big steals advantage frequently loses anyway, so they count 0.59. Assists are steady week to week and count the full 1.00. The multipliers live on the Settings tab.'],
  ['G TOTAL', ' =SUM(the nine g-scores)', 'The nine discounted scores added up. This is the honest measure of a player, and everything below is built on it. The headline effect versus Z TOTAL: steals specialists fall, steady producers rise.'],
  ['', '', ''],

  ['STEP 3 — TURN IT INTO VALUE', '', ''],
  ['VOR', ' =G TOTAL − REPLACEMENT', 'Value Over Replacement. A G TOTAL of zero means "an average drafted player", which leaves half the board sitting in negative numbers and is awkward to reason about. Subtracting the replacement player re-bases everything so zero is the worst player still worth drafting. Now the number answers the question you actually care about on the clock: how much better is this guy than whoever I could take instead?'],
  ['Rank (VOR)', ' =RANK(VOR, all VOR)', 'Where he sits on pure talent, before games played is considered.'],
  ['', '', ''],

  ['STEP 4 — ADJUST FOR GAMES PLAYED', '', ''],
  ['My GP Est', ' =Projected GP    (then edited by hand)', 'How many games you personally expect him to play. Starts as a copy of the projection. Change it where you know something the projection does not — a player back from injury, an ageing star on load management. Edit the fifteen or thirty you have a real opinion about, not all 200.'],
  ['GP Flag', ' =IF(ABS(Projected GP − My GP Est) > 10, "CHECK", "")', 'Says CHECK when your estimate disagrees with the projection by more than ten games. Not an error — just a nudge to confirm you meant it.'],
  ['ADJUSTED VALUE', ' =VOR × My GP Est / GP_DIVISOR   (never scaled up when VOR is negative)', 'The column the board is actually sorted by, and the closest thing here to a final answer. It is VOR scaled by how much the player is available. A brilliant player who suits up 55 times contributes less across a season than a merely good one who plays 78, and the draft room is consistently bad at pricing that. Two guards on it. It scales VOR and never the G-score, because multiplying a negative score by a fraction would push a bad player up the board. And below replacement, where VOR is already negative, the scaling is switched off entirely — otherwise the same thing happens again among the last forty names, ranking the player who misses more games higher. Availability may discount a player; it may never promote one. Worth knowing why the shape is a straight line: if you replace an injured player with someone off waivers, his value over replacement for the games he misses is exactly zero, so the expected season total really is VOR × games ÷ 72. It is not an approximation.'],
  ['Adj Rank', ' =RANK(Adjusted Value, all Adjusted Value)', 'Your final ranking, 1 to 200. This is the number the Draft Board is ordered by.'],
  ['', '', ''],

  ['STEP 5 — COMPARE AGAINST THE ROOM', '', ''],
  ['ADP', ' (typed in, not calculated)', 'Average Draft Position — where this player actually comes off the board in real drafts. Tells you when you can have him, not how good he is.'],
  ['GAP', ' =IF(ADP = "", "", ADP − Adj Rank)', 'Your opinion minus the room\'s. +25 means he typically goes 25 picks later than you rate him, so you can wait a round and still get him — or take him now as a bargain. Negative means the room likes him more than you do, so let someone else pay. Blank means no ADP exists for him, which is not the same as being fairly priced.'],
  ['', '', ''],

  ['STEP 6 — CUT THE TIERS', '', ''],
  ['Drop', ' =Adjusted Value above − Adjusted Value here', 'How much value you give up by taking this player instead of the one directly above him.'],
  ['Local median', ' =MEDIAN(the fifteen drops centred on this row — seven above, seven below)', 'The normal size of a drop around here. This matters because drops shrink as you go down the board: a gap that is a canyon at pick 120 is completely routine at pick 5. Judging every drop against a single fixed number would give you five tiers at the top and one enormous blob at the bottom.'],
  ['Break', ' =IF(Drop > TIER_MULT × Local median, "BREAK", "")', 'Fires when the drop into this player is much bigger than what is normal for that part of the board. That is a real cliff, and it is where a tier line gets drawn.'],
  ['Tier', ' =IF(Break = "BREAK", Tier above + 1, Tier above)', 'A group of players you would be roughly equally happy with. Inside a tier you can afford to wait, because the next name down is just as good. Between tiers waiting costs you something real. This is what turns 200 names into about a dozen actual decisions.'],
  ['', '', ''],

  ['STEP 7 — PUNT BUILDS', '', ''],
  ['Punt FT%   (and the other eight)', ' =(G TOTAL − 75% of g FT% − that build\'s replacement) × availability', 'The entire board re-valued as if you are barely competing in that category. If you decide you are not chasing free throw percentage, terrible free throw shooters stop being penalised for it and immediately get cheap. The reordering is dramatic rather than marginal — Giannis is around 25th on a normal board and 2nd on a punt-FT% board. Two things this does that a plain subtraction does not. It keeps a quarter of the punted category rather than deleting it, because you will still win that category in some weeks by accident and those weeks are free — which also stops the build rating a genuinely awful free throw shooter identically to a merely neutral one. And it goes through the build\'s own replacement level and the same games-played discount as the main board, so a punt list is not quietly sorted by who misses games. Set Punt weight to 0 on Settings to get the old hard-punt behaviour back.'],
  ['Punt rank', ' =RANK(that punt column)', 'Where the player sits inside that build.'],
  ['Punt Gap', ' =ADP − rank inside that build', 'The bargain measure for a build. A big positive number means the room prices him normally while this particular build values him far higher. The top of each list on the Punts tab is who that build gets at a discount. Players with no ADP have no Gap and sit at the bottom of each list rather than being hidden — an unpriced player is often exactly the one a build wants cheap.'],
  ['Best build', ' =the punt column that ranks him highest, and by how much', 'A shortcut. Reads "AST+STL +21", meaning a punt assists-and-steals build rates him 21 places higher than the standard board does. A dash means no build helps him — he is simply good everywhere.'],
  ['', '', ''],

  ['THE CATEGORY TRACKER', '', ''],
  ['My team   (counting stats)', ' =SUMIF(Mine, TRUE, that stat)', 'Adds up the category across every player you have ticked as Mine.'],
  ['My team   (FG% and FT%)', ' =SUMIF(Mine,TRUE,FGM) / SUMIF(Mine,TRUE,FGA)', 'Your roster\'s real shooting percentage — total makes over total attempts again, never the average of the individual percentages.'],
  ['Average team', ' =mean of the top (Teams × my player count) by Adj Rank, × my player count', 'What an average team actually holds right now. After five rounds every manager has five players and those sixty are the best sixty on the board, not sixty players drawn at random from all 156 — so the benchmark has to move with the draft. Measuring against the whole pool instead makes the target far too low early and reads STRONG on everything through about round ten, which is precisely when you need it to tell you something.'],
  ['Edge', ' =My team − Average team', 'How far ahead or behind average you are in that category. Reversed on the turnovers row, because there fewer is better.'],
  ['Read', ' =STRONG / EVEN / WEAK, or PUNTED if you tick the box', 'The quick verdict. Each row has its own threshold, on Settings: FG% and FT% in rate points, the seven counting categories as a share of the benchmark. They used to share one 8%-of-benchmark rule, which on a percentage means about four points of team FG% — a margin no team ever posts, so those two rows read EVEN no matter what you drafted. Aim for roughly 60% win rate in the categories you are contesting, not 90% — winning a category 60–30 pays exactly the same as winning it 46–45, so margin beyond a win is wasted. Spend your next pick on an EVEN category, not a STRONG one.'],
  ['', '', ''],

  ['THINGS WORTH KNOWING', '', ''],
  ['Steals', '', 'Worth about half what the raw z-score claims. The week-to-week noise swamps the edge.'],
  ['Games played', '', 'The most under-priced variable on the board. Kept in its own column on purpose — never folded into the projection, so you can see talent and availability separately.'],
  ['MPG', '', 'Carried for context and deliberately not valued. Minutes are the best single predictor of production, which is exactly why folding them in would double-count: a per-game projection already is the minutes. Use the column to sanity-check a line that looks wrong — big counting stats on small minutes is usually a projection worth overriding, not a bargain.'],
  ['Tier 1', '', 'Written as a literal rather than computed. The fifteen-row window is truncated at the very top of the board, so the formula has nothing useful to say there.'],
  ['Tier multiplier', '', 'Ships at 2.0, the playbook\'s own suggestion. It shipped at 4.0 for a while, chosen to hit a target number of tiers — which turned out to be the wrong thing to measure. What matters is the size of a tier where you are actually picking, and at 4.0 one tier ran from pick 25 to pick 70: forty-six players the board called interchangeable, across rounds three to six. At 2.0 the worst tier in the top 100 is twelve. The total count is higher and that is fine; a tier you cannot act on is not worth counting. Tune it on Settings.'],
  ['Blank GAP', '', 'Some players have no ADP. Blank, not zero — a zero would read as "fairly priced", which is a different claim entirely.'],
  ['ADP source', '', "Hashtag's, not Yahoo. Yahoo ADP is the room you are actually drafting in, and the two do not agree — Yahoo skews toward established names. Read GAP as \"cheap somewhere\", not \"cheap in my league\"."],
  ['Scoring format', '', 'Head-to-Head Categories: all nine categories are settled separately every week, so a week ends 6-3. That is Yahoo\'s name for it; ESPN calls the same thing Each Category. It is not the format where the week resolves to a single win, which Yahoo calls One Win. The difference decides how hard to punt — conceding a category here costs a loss every single week, so soft-punt at most and stay broad.'],
  ['Left @pos', '', 'How many players at his primary position are still un-Gone in his tier. The scarcity tiebreak: between two players you rate the same, take the one whose position is running out. Position is deliberately kept out of the valuation itself — a rebound counts the same whoever grabs it — so this only counts what is left.'],
  ['Punt weight', '', 'What a punted category still counts for, on Settings. Ships at 0.25. Set it to 0 for a hard punt, which is what this board did before and what most public tools still do.'],
  ['G-score multipliers', '', 'From Rosenof (arXiv 2307.02188, Table 8), computed on the 2022-23 season. The ordering is solid and the steals discount is robust; the second decimal is not, least of all on FG% and FT%.']
];

function buildReadme(sh) {
  var L = README_ROWS;

  // Plain text throughout: the formula column starts with '=' and must not run.
  sh.getRange(1, 1, L.length, 3).setNumberFormat('@').setValues(L);

  sh.setColumnWidth(1, 175); sh.setColumnWidth(2, 335); sh.setColumnWidth(3, 560);
  sh.getRange(1, 1, L.length, 3).setVerticalAlignment('top');
  sh.getRange(1, 2, L.length, 2).setWrap(true);
  sh.getRange(1, 1, L.length, 1).setFontWeight('bold').setWrap(true);
  sh.getRange(1, 2, L.length, 1).setFontFamily('Roboto Mono').setFontSize(9)
    .setFontColor(COLOR.z);
  sh.getRange(1, 3, L.length, 1).setFontSize(10);
  sh.getRange(1, 1).setFontSize(18).setFontColor(COLOR.identity);
  sh.getRange(2, 1).setFontColor(COLOR.muted).setFontSize(10).setFontWeight('normal');
  sh.getRange(2, 1, 1, 3).merge();

  README_SECTIONS.forEach(function (label) {
    var r = readmeRowOf(L, label);
    if (!r) return;
    sh.getRange(r, 1, 1, 3).merge().setBackground(COLOR.identity)
      .setFontColor(COLOR.headerText).setFontWeight('bold').setFontSize(11);
  });
  README_STEPS.forEach(function (label) {
    var r = readmeRowOf(L, label);
    if (!r) return;
    sh.getRange(r, 1, 1, 3).merge().setBackground(COLOR.band)
      .setFontColor(COLOR.identity).setFontWeight('bold').setFontSize(10)
      .setBorder(true, null, null, null, null, null,
                 COLOR.identity, SpreadsheetApp.BorderStyle.SOLID);
  });

  var swatch = readmeRowOf(L, 'Pale yellow + blue text');
  if (swatch) sh.getRange(swatch, 3).setBackground(COLOR.inputBg).setFontColor(COLOR.inputText);

  sh.setHiddenGridlines(true);
  sh.setFrozenRows(2);
}

// ------------------------------------------------------------------- menu

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Draft Board')
    .addItem('Refresh data (new export, keeps your edits)', 'refreshData')
    .addSeparator()
    .addItem('Rebuild & re-sort', 'rebuildAndResort')
    .addItem('Re-seed pool from current ranks', 'reseedPool')
    .addSeparator()
    .addItem('Full rebuild (from Data.gs)', 'buildDraftBoard')
    .addSeparator()
    .addItem('Step 1 — Settings only', 'step1_Settings')
    .addItem('Step 1b — Reformat Board', 'step1b_FormatBoard')
    .addItem('Step 2 — Draft Board only', 'step2_DraftBoard')
    .addItem('Step 3 — Punts, Tracker, README', 'step3_Rest')
    .addToUi();
}

/** Re-sort the draft board against current Adjusted Values, keeping checkboxes. */
function rebuildAndResort() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  SpreadsheetApp.flush();
  var draft = ss.getSheetByName('Draft Board');
  draft.clearConditionalFormatRules();
  detachBandings(draft);
  buildDraftTab(ss, ensureGrid(draft, D_LAST, RN), ss.getSheetByName('Board'));
  SpreadsheetApp.flush();
  ss.toast('Re-sorted. Checkbox state kept.', 'Draft Board', 5);
}

/**
 * One iteration of the pool. Copies current Adj Rank into Seed Rank, so
 * membership reflects the values the board just produced. Run it twice.
 */
function reseedPool() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var board = ss.getSheetByName('Board');
  SpreadsheetApp.flush();
  var ranks = board.getRange(R0, B.adjRank, POOL_ROWS, 1).getValues();
  for (var i = 0; i < ranks.length; i++) {
    if (typeof ranks[i][0] !== 'number') {
      ss.toast('Adj Rank is not fully calculated — nothing changed.', 'Re-seed', 6);
      return;
    }
  }
  board.getRange(R0, B.seed, POOL_ROWS, 1).setValues(ranks);
  SpreadsheetApp.flush();
  var moved = ss.getSheetByName('Settings').getRange(33, 2).getValue();
  ss.toast('Pool re-seeded. ' + moved + ' players in pool. Run again to confirm it has settled.',
           'Re-seed', 8);
}
