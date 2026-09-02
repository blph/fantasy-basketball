/**
 * 9-Cat H2H Draft Board — 2026-27
 *
 * Builds the whole workbook: the Draft Board you sit in front of on the clock, three
 * calculation tabs, the punt builds, the Category Tracker, Settings and the README.
 *
 * WHERE THE NUMBERS COME FROM. Every value a player is judged on is computed in Python
 * (scripts/draft-board/build_data.py, over the engine in scripts/bbm/bbm_reference.py) and
 * arrives here in Data.gs as a number. ADR-0016 records why: DURANT H2H needs a pool
 * iterated to a fixed point, and Sheets cannot express a fixed point without a circular
 * reference. What stays a live formula is everything that has to react during a draft —
 * rank, tier, round, GAP, the category profile, Left @pos, and the Category Tracker.
 *
 * So: changing a weight on Settings does NOT recalculate the board. Re-run the pipeline.
 * Those cells are grey rather than input-yellow for exactly that reason.
 *
 * THREE PROJECTIONS, THREE VALUES (ADR-0014, ADR-0015). BMP and BMP-ALT are Basketball
 * Monster's two sources; HBP is Hashtag Basketball and supplies the board's 200 rows,
 * team, position and ADP. Each carries DURH, ZSH and ZSC. DURH on BMP is the default.
 *
 * NOTHING SCALES BY GAMES PLAYED (ADR-0017). The GP columns are context, not a multiplier.
 *
 * This file is SOURCE. The sheet runs a separate bound copy named Code.gs, and editing
 * this changes nothing in Google until that copy is replaced. See
 * docs/draft-board/build-and-maintenance.md.
 */

var TRACKER_TAB = 'Category Tracker';
var TRACKER_R0 = 7;    // first category row on the tracker, in CAT_LABELS order

var POOL_ROWS = 200;   // players carried on the board
// Row 1 is the control strip (sort dropdown, projection toggles), row 2 the merged block
// headers, row 3 the column headers. This was 2 before the control strip existed, and
// every external read range moved with it: see build-and-maintenance.md.
var HDR = 3;
var R0 = HDR + 1;      // first data row
var RN = HDR + POOL_ROWS;

var COLOR = {
  identity: '#37474F',
  raw:      '#1F5673',
  impact:   '#26706E',
  z:        '#43518A',
  transform:'#6A4C93',
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
  faint:      '#BDC1C6',
  rule:       '#D0D7DE',
  ruleGroup:  '#8A94A0',
  chrome:     '#E3E7EB',

  bad:  '#E67C73',
  mid:  '#FFFFFF',
  good: '#57BB8A',

  // A divergent pair for "the projections disagree". Deliberately differs in LIGHTNESS as
  // well as hue, because the bad/good pair above sits at nearly identical lightness and is
  // the classic red-green failure case.
  posBg: '#CDE9D8', posText: '#0B5D33',
  negBg: '#FBE9E7', negText: '#8C3B2B',

  flagBg:   '#FCE8E6',
  flagText: '#C5221F',
  // Was #FFF3D6, four hex points from inputBg — two meanings, one swatch. "You may type
  // here" and "the projection is guessing" have to be distinguishable at 9pt.
  warnBg:   '#FFECC7',
  warnText: '#7A5B00',
  drafted:  '#EDEFF1',
  mineBg:   '#E6F4EA',
  mineText: '#137333',
  active:   '#FFFDF6',

  srcBmp: '#334E7A', srcBmpOff: '#8B99B4', srcBmpBand: '#EDF1F8',
  srcHbp: '#1F5F63', srcHbpOff: '#82A3A5', srcHbpBand: '#EAF3F3',
  srcAlt: '#54427C', srcAltOff: '#9C93B5', srcAltBand: '#F1EDF7'
};

/**
 * The three projection sources, in board order. `prefix` keys the D map and the named
 * ranges; a named range cannot contain a hyphen, which is why BMP-ALT is `alt`.
 */
var SOURCES = [
  { key: 'BMP',     prefix: 'bmp', label: 'BMP',
    head: COLOR.srcBmp, off: COLOR.srcBmpOff, band: COLOR.srcBmpBand },
  { key: 'HBP',     prefix: 'hbp', label: 'HBP',
    head: COLOR.srcHbp, off: COLOR.srcHbpOff, band: COLOR.srcHbpBand },
  { key: 'BMP-ALT', prefix: 'alt', label: 'BMP-ALT',
    head: COLOR.srcAlt, off: COLOR.srcAltOff, band: COLOR.srcAltBand }
];

/**
 * The three values, in board order. ZSC drops nothing, so it has no dropped-category tag
 * and its tag column carries only the rank.
 */
var VALUE_KINDS = [
  { key: 'Durh', label: 'DURH', v: 'durh', rank: 'durhRank', drop: 'durhDrop' },
  { key: 'Zsh',  label: 'ZSH',  v: 'zsh',  rank: 'zshRank',  drop: 'zshDrop'  },
  { key: 'Zsc',  label: 'ZSC',  v: 'zsc',  rank: 'zscRank',  drop: null       }
];

/**
 * The eight categories the board displays, in the order Python emits them.
 *
 * Turnovers are absent on purpose: DURANT H2H weights them zero, so a DH turnover column
 * is identically 0.0 for every player and can neither clear a band nor move a total.
 *
 * This order is load-bearing three times over — the tracker's rows, the Punted checkbox
 * range, and the Category profile's label array are all matched against it positionally.
 * Keep it in step with board_values.CAT_LABELS; the harness asserts both ends.
 */
var CAT_LABELS = ['FG%', 'FT%', '3PM', 'PTS', 'REB', 'AST', 'STL', 'BLK'];

/** The nine builds the board ships (ADR-0010). Keys match PUNT_VALUES in Data.gs. */
var PUNTS = [
  { key: 'pFt',     label: 'Punt FT%'      },
  { key: 'pFg',     label: 'Punt FG%'      },
  { key: 'pAst',    label: 'Punt AST'      },
  { key: 'p3',      label: 'Punt 3PM'      },
  { key: 'pBlk',    label: 'Punt BLK'      },
  { key: 'pFgReb',  label: 'Punt FG%+REB'  },
  { key: 'pAstStl', label: 'Punt AST+STL'  },
  { key: 'pPtsFt',  label: 'Punt PTS+FT%'  },
  { key: 'pTriple', label: 'Punt FG/FT/TO' }
];

/**
 * Board — the spine. Identity, the HBP raw line, availability, market, and every column
 * you edit by hand. Nothing derived lives here any more, which is what keeps `Refresh
 * data` writing to exactly one tab.
 */
var B = {
  seed: 1, player: 2, team: 3, pos: 4,
  gp: 5, mpg: 6,
  fgm: 7, fga: 8, fgp: 9, ftm: 10, fta: 11, ftp: 12,
  tpm: 13, pts: 14, reb: 15, ast: 16, stl: 17, blk: 18, to: 19,
  gp1: 20, gp2: 21, gp3: 22, myGp: 23, gpCheck: 24,
  adp: 25, xrank: 26,
  injuries: 27, notes: 28
};
var B_LAST = B.notes;

/**
 * A calculation tab. One map, three identical sheets. Every cell is a number written by
 * the pipeline — there is not one formula on these tabs.
 */
var V = (function () {
  var m = { player: 1, poolD: 2, gp: 3, mpg: 4,
            fgm: 5, fga: 6, ftm: 7, fta: 8,
            tpm: 9, pts: 10, reb: 11, ast: 12, stl: 13, blk: 14, to: 15, adp: 16 };
  var c = 17;
  m.durh = c++; m.durhRank = c++; m.durhDrop = c++;
  m.zsh  = c++; m.zshRank  = c++; m.zshDrop  = c++;
  m.zsc  = c++; m.zscRank  = c++;
  m.dh0 = c; c += CAT_LABELS.length;      // DURANT H2H, weighted — what the tracker sums
  m.d0  = c; c += CAT_LABELS.length;      // DURANT, unweighted — what the profile bands
  m.z0  = c; c += CAT_LABELS.length;      // plain z, audit only
  // Punt builds. Populated on BMP only (ADR-0010 ships nine builds for the default
  // projection); blank on the other two, so the map stays uniform across all three tabs.
  // Both blocks are contiguous because the Draft Board's "Best build" takes MIN and MATCH
  // across the rank span as a single range.
  m.p0 = c; c += PUNTS.length;
  m.pr0 = c; c += PUNTS.length;
  m.last = c - 1;
  return m;
})();
var V_LAST = V.last;

/**
 * Draft Board. The 18 value columns are generated from SOURCES x VALUE_KINDS rather than
 * typed out: the projection filter hides one source's six-column span, and a gap in that
 * span would hide the wrong columns while every offline check still passed.
 */
var D = (function () {
  var m = { rank: 1, tier: 2, round: 3, player: 4, team: 5, pos: 6, inj: 7 };
  // Gone and Mine live inside the frozen pane. They are the only two cells written during
  // a draft, and at the right-hand edge they scrolled off the moment any value column was
  // in view.
  m.drafted = 8; m.mine = 9;
  var c = 10;
  for (var s = 0; s < SOURCES.length; s++) {
    for (var k = 0; k < VALUE_KINDS.length; k++) {
      m[SOURCES[s].prefix + VALUE_KINDS[k].key] = c++;
      m[SOURCES[s].prefix + VALUE_KINDS[k].key + 'Tag'] = c++;
    }
  }
  // The value the board is currently sorted by, copied from the selected calculation
  // column at build time. Rank, drop, median, break and tier all read this one column, so
  // changing the sort repoints one formula rather than five families of them.
  m.sel = c++;
  m.drop = c++; m.med = c++; m.brk = c++;
  m.projGp = c++; m.myGp = c++; m.gpFlag = c++;
  m.adp = c++; m.xrank = c++; m.gap = c++;
  m.best = c++;
  // Split from one 240px string: strengths are scanned when the tracker says a category
  // is contested, and weaknesses can carry a pale fill so damage reads without being read.
  m.strengths = c++; m.weaknesses = c++;
  m.posLeft = c++; m.notes = c++;
  // Hidden feed. The tracker and the profile read these rather than reaching across to a
  // calculation tab, so they follow whichever projection is selected.
  m.hFgm = c++; m.hFga = c++; m.hFtm = c++; m.hFta = c++;
  m.h3 = c++; m.hPts = c++; m.hReb = c++; m.hAst = c++; m.hStl = c++; m.hBlk = c++;
  m.dh0 = c; c += CAT_LABELS.length;
  m.d0 = c; c += CAT_LABELS.length;
  // Nine numeric ranks, one per value column, so the "projections disagree" highlight can
  // compare against the board's own rank. Computing RANK() inside a conditional format
  // would evaluate a 200-cell aggregate 200 times per rule.
  m.rank0 = c; c += SOURCES.length * VALUE_KINDS.length;
  // The board's own alignment guard: the player name read from the SAME calculation row
  // this row's hidden block reads. Settings compares the column against `Player` and says
  // MISALIGNED if they ever differ. A half-finished build once left this whole block in
  // the previous sort's order while the visible columns held the new one, and nothing --
  // not the sheet, not the harness, not verify.py -- said a word.
  m.rowCheck = c++;
  m.last = c - 1;
  return m;
})();
var D_LAST = D.last;

/** Which Draft Board column holds this source's value / tag for this kind. */
function dValue(si, ki) { return D[SOURCES[si].prefix + VALUE_KINDS[ki].key]; }
function dTag(si, ki)   { return D[SOURCES[si].prefix + VALUE_KINDS[ki].key + 'Tag']; }
function dRank(si, ki)  { return D.rank0 + si * VALUE_KINDS.length + ki; }
/** The first column of a source's six-column block — what the projection filter hides. */
function dSpanStart(si) { return dValue(si, 0); }
var SPAN = VALUE_KINDS.length * 2;

// ------------------------------------------------------------------ helpers

function a1col(n) {
  var s = '';
  while (n > 0) { var m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = (n - m - 1) / 26; }
  return s;
}

/**
 * A sheet name as it must appear inside a formula.
 *
 * Quote anything that is not a bare identifier. TWO separate live failures come from
 * getting this wrong, and neither is visible offline:
 *
 *   `BMP-ALT`          a hyphen reads as subtraction, so the reference resolves elsewhere
 *                      or fails outright
 *   `Category Tracker` a SPACE does not parse at all -- the whole formula returns #ERROR!
 *
 * A space is the one that bites, because a name with a space looks harmless. Only
 * letters, digits and underscores may go unquoted.
 */
function sheetRef(name) {
  return /^[A-Za-z0-9_]+$/.test(name) ? name : "'" + String(name).replace(/'/g, "''") + "'";
}
function cellRef(sheetName, col, row) {
  return sheetRef(sheetName) + '!$' + a1col(col) + '$' + row;
}
function colRange(sheetName, col) {
  return sheetRef(sheetName) + '!$' + a1col(col) + '$' + R0 + ':$' + a1col(col) + '$' + RN;
}

/**
 * The same column, as a STRING that Sheets will never rewrite.
 *
 * Only for the Settings sanity checks, and only because Sheets rewrites both of the
 * obvious alternatives out from under them:
 *
 *   - A named range dies when its tab is recreated. `sheetByName` deletes and recreates
 *     every tab it builds, so a full rebuild turned B_PLAYER into #REF! inside the
 *     formulas that used it -- which is how the "Names line up across tabs" guard came to
 *     be reading `COUNTA(#REF!)` and reporting nothing at all.
 *   - An A1 reference shifts when a column is inserted at or before it. Settings is built
 *     before the Draft Board, so a reference to the board's LAST column is written one
 *     past the end of the grid; growing the grid to fit then slid it one further, and the
 *     alignment check spent its first build pointing at an empty column.
 *
 * A string is not a reference, so neither happens. The cost is that the formula no longer
 * follows a column that moves -- which is what we want: the map is the authority on where
 * the column is, and the next build rewrites the formula from it.
 */
function colIndirect(sheetName, col) {
  return 'INDIRECT("' + sheetRef(sheetName).replace(/"/g, '""')
       + '!R' + R0 + 'C' + col + ':R' + RN + 'C' + col + '",FALSE)';
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
    // Unfreeze and unmerge FIRST, before anything else touches the sheet.
    //
    // `clear()` does not remove merges. A merged block header left over from the PREVIOUS
    // layout survives the wipe, and the moment the new layout freezes at a different
    // column Google throws "You can't merge frozen and non-frozen columns" -- from
    // setFrozenColumns, with the rebuild already half-written and the tab unusable. This
    // is exactly how the first live deploy of the refactor failed.
    //
    // Dropping the freeze before breaking the merges matters too: a merge that currently
    // spans the frozen boundary cannot be broken while the freeze is still in place.
    sh.setFrozenRows(0);
    sh.setFrozenColumns(0);
    sh.getRange(1, 1, sh.getMaxRows(), sh.getMaxColumns()).breakApart();
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

/** Paint a merged block header across [c1..c2]. Defaults to the block-header row. */
function blockHeader(sh, c1, c2, label, color, row) {
  var r = sh.getRange(row || HDR - 1, c1, 1, c2 - c1 + 1);
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

function addRule(sh, rule) {
  var rules = sh.getConditionalFormatRules();
  rules.push(rule);
  sh.setConditionalFormatRules(rules);
}
function gradient(sh, ranges, lo, hi, low, mid, high) {
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .setGradientMinpointWithValue(low || COLOR.bad, SpreadsheetApp.InterpolationType.NUMBER, String(lo))
    .setGradientMidpointWithValue(mid || COLOR.mid, SpreadsheetApp.InterpolationType.NUMBER, '0')
    .setGradientMaxpointWithValue(high || COLOR.good, SpreadsheetApp.InterpolationType.NUMBER, String(hi))
    .setRanges(ranges).build());
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

/** Guard against Data.gs being absent or the wrong shape, with one message per cause. */
function requireData() {
  if (typeof PLAYERS === 'undefined' || typeof VALUES === 'undefined') {
    throw new Error('Data.gs is missing or stale — run scripts/draft-board/build_data.py '
                    + 'and paste the result in. PLAYERS and VALUES must both exist.');
  }
  if (PLAYERS.length !== POOL_ROWS) {
    throw new Error('Data.gs holds ' + PLAYERS.length + ' players; the board is built for '
                    + POOL_ROWS + '.');
  }
  for (var i = 0; i < SOURCES.length; i++) {
    var key = SOURCES[i].key;
    if (!VALUES[key]) throw new Error('Data.gs has no VALUES for ' + key + '.');
    if (VALUES[key].length !== POOL_ROWS) {
      throw new Error(key + ': ' + VALUES[key].length + ' value rows against '
                      + POOL_ROWS + ' players. Row i must be the same player in both.');
    }
  }
}

/** Which value the board is sorted by, as [sourceIndex, kindIndex]. */
function selectedSort(ss) {
  var chosen = '';
  try { chosen = String(ss.getRangeByName('SORT_BY').getValue() || ''); } catch (e) {}
  for (var s = 0; s < SOURCES.length; s++) {
    for (var k = 0; k < VALUE_KINDS.length; k++) {
      if (chosen === sortLabel(s, k)) return [s, k];
    }
  }
  return [0, 0];   // BMP - DURH
}
function sortLabel(si, ki) { return SOURCES[si].label + ' · ' + VALUE_KINDS[ki].label; }
function allSortLabels() {
  var out = [];
  for (var s = 0; s < SOURCES.length; s++)
    for (var k = 0; k < VALUE_KINDS.length; k++) out.push(sortLabel(s, k));
  return out;
}

// ------------------------------------------------------------- entry point

function buildDraftBoard() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  requireData();

  var board    = sheetByName(ss, 'Board', B_LAST, RN);
  var calcs = [];
  for (var i = 0; i < SOURCES.length; i++) {
    calcs.push(sheetByName(ss, SOURCES[i].key, V_LAST, RN));
  }
  var settings = sheetByName(ss, 'Settings', 10, 90);
  // Captured before the wipe -- see buildDraftTab.
  var priorDraft = readCheckState(ss.getSheetByName('Draft Board'));
  var draft    = sheetByName(ss, 'Draft Board', D_LAST, RN);
  var punts    = sheetByName(ss, 'Punts', PUNTS.length * 6, 60);
  var tracker  = sheetByName(ss, TRACKER_TAB, 8, 60);
  var readme   = sheetByName(ss, 'README', 3, 70);

  _guard('Board',    function () { writeBoardData(board); writeBoardFormulas(board); });
  _guard('Calc',     function () {
    for (var i = 0; i < SOURCES.length; i++) writeCalcSheet(calcs[i], i);
  });
  _guard('Settings', function () { writeSettingsSkeleton(settings); });
  _guard('Names',    function () { defineNames(ss); });
  SpreadsheetApp.flush();
  _guard('Format',   function () {
    formatSettings(settings);
    formatBoard(board);
    for (var i = 0; i < SOURCES.length; i++) formatCalcSheet(calcs[i], i);
  });
  _guard('Draft',    function () { buildDraftTab(ss, draft, board, priorDraft); });
  _guard('Punts',    function () { buildPuntsTab(punts); });
  _guard('Tracker',  function () { buildTrackerTab(tracker); });
  _guard('README',   function () { buildReadme(readme); });
  _guard('Tidy', function () {
    var order = ['Draft Board'];
    for (var i = 0; i < SOURCES.length; i++) order.push(SOURCES[i].key);
    order = order.concat(['Board', 'Punts', TRACKER_TAB, 'Settings', 'README']);
    reorderTabs(ss, order);
    var extra = ss.getSheetByName('Sheet1');
    if (extra) ss.deleteSheet(extra);
  });
}

/**
 * Write a one-line outcome to Settings. The execution log does not survive a thrown
 * exception; this cell does, which is the only way to find out where a timed-out build
 * stopped.
 */
function _note(msg) {
  try {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Settings');
    if (!sh) return;
    sh.getRange(NOTE_ROW, 1).setValue('BUILD LOG').setFontWeight('bold');
    sh.getRange(NOTE_ROW + 1, 1).setValue(msg);
  } catch (e) { /* never let logging break the build */ }
}
function _guard(step, fn) {
  try { var out = fn(); _note(step + ': ok'); return out; }
  catch (e) { _note(step + ': FAILED — ' + e.message); throw e; }
}

function reorderTabs(ss, order) {
  for (var i = 0; i < order.length; i++) {
    var sh = ss.getSheetByName(order[i]);
    if (sh) { ss.setActiveSheet(sh); ss.moveActiveSheet(i + 1); }
  }
}

// ---------------------------------------------------------------- the Board

/**
 * Board columns fed by the export, paired with their index in a PLAYERS row.
 * Hand-edited columns are deliberately absent; a refresh must never touch them.
 */
var REFRESH_MAP = [
  [B.seed, 0], [B.player, 1], [B.team, 2], [B.pos, 3],
  [B.gp, 5], [B.mpg, 6],
  [B.fgm, 7], [B.fga, 8], [B.fgp, 9],
  [B.ftm, 10], [B.fta, 11], [B.ftp, 12],
  [B.tpm, 13], [B.pts, 14], [B.reb, 15], [B.ast, 16],
  [B.stl, 17], [B.blk, 18], [B.to, 19],
  [B.adp, 4]
];

/** Columns you fill in by hand. A refresh must never overwrite these. */
var HAND_COLS = [B.gp1, B.gp2, B.gp3, B.myGp, B.xrank, B.injuries, B.notes];

function writeBoardData(sh) {
  var head = [];
  for (var c = 1; c <= B_LAST; c++) head[c] = '';
  head[B.seed] = 'HBP\n#'; head[B.player] = 'Player'; head[B.team] = 'Tm'; head[B.pos] = 'Pos';
  head[B.gp] = 'GP'; head[B.mpg] = 'MPG';
  head[B.fgm] = 'FGM'; head[B.fga] = 'FGA'; head[B.fgp] = 'FG%';
  head[B.ftm] = 'FTM'; head[B.fta] = 'FTA'; head[B.ftp] = 'FT%';
  head[B.tpm] = '3PM'; head[B.pts] = 'PTS'; head[B.reb] = 'REB'; head[B.ast] = 'AST';
  head[B.stl] = 'STL'; head[B.blk] = 'BLK'; head[B.to] = 'TO';
  head[B.gp1] = 'GP\nY-1'; head[B.gp2] = 'GP\nY-2'; head[B.gp3] = 'GP\nY-3';
  head[B.myGp] = 'My GP\nEst'; head[B.gpCheck] = 'GP\nflag';
  head[B.adp] = 'ADP'; head[B.xrank] = 'XRank';
  head[B.injuries] = 'Injuries'; head[B.notes] = 'Notes';

  var hrow = [];
  for (var i = 1; i <= B_LAST; i++) hrow.push(head[i] === undefined ? '' : head[i]);
  sh.getRange(HDR, 1, 1, B_LAST).setNumberFormat('@').setValues([hrow]);

  var rows = [];
  for (var p = 0; p < PLAYERS.length; p++) {
    var d = PLAYERS[p], line = [];
    for (var c2 = 1; c2 <= B_LAST; c2++) line.push('');
    for (var m = 0; m < REFRESH_MAP.length; m++) {
      line[REFRESH_MAP[m][0] - 1] = d[REFRESH_MAP[m][1]];
    }
    rows.push(line);
  }
  sh.getRange(R0, 1, rows.length, B_LAST).setValues(rows);
}

/**
 * The Board's only two formulas. Everything else on this tab is either typed by you or
 * written by the refresh.
 */
function writeBoardFormulas(sh) {
  var mine = [], flag = [];
  for (var i = 0; i < POOL_ROWS; i++) {
    var r = R0 + i;
    // Seeded from the projection, then hand-edited. The refresh reads FORMULAS rather than
    // values to tell an override from an untouched cell, so there is no bookkeeping column.
    mine.push(['=$' + a1col(B.gp) + r]);
    flag.push(['=IF($' + a1col(B.myGp) + r + '="","",IF(ABS($' + a1col(B.gp) + r + '-$'
               + a1col(B.myGp) + r + ')>10,"CHECK",""))']);
  }
  sh.getRange(R0, B.myGp, POOL_ROWS, 1).setFormulas(mine);
  sh.getRange(R0, B.gpCheck, POOL_ROWS, 1).setFormulas(flag);
}

// ----------------------------------------------------- the calculation tabs

/**
 * One projection's working, written as numbers.
 *
 * Three header rows, and the third earns its keep: row 1 names the stage, row 2 the
 * column, and row 3 carries that column's own constant — the Yeo-Johnson lambda for the
 * transformed stage, the H2H weight for the weighted one. Those are the two things a
 * reader otherwise has to leave the tab to look up, and they are per-column facts, so
 * they belong in a per-column row.
 */
function writeCalcSheet(sh, si) {
  var src = SOURCES[si];
  var rows = VALUES[src.key];

  var head = [];
  for (var c = 1; c <= V_LAST; c++) head[c] = '';
  head[V.player] = 'Player'; head[V.poolD] = 'In\npool';
  head[V.gp] = 'GP'; head[V.mpg] = 'MPG';
  head[V.fgm] = 'FGM'; head[V.fga] = 'FGA'; head[V.ftm] = 'FTM'; head[V.fta] = 'FTA';
  head[V.tpm] = '3PM'; head[V.pts] = 'PTS'; head[V.reb] = 'REB'; head[V.ast] = 'AST';
  head[V.stl] = 'STL'; head[V.blk] = 'BLK'; head[V.to] = 'TO'; head[V.adp] = 'ADP';
  head[V.durh] = 'DURH'; head[V.durhRank] = '#'; head[V.durhDrop] = 'drops';
  head[V.zsh] = 'ZSH'; head[V.zshRank] = '#'; head[V.zshDrop] = 'drops';
  head[V.zsc] = 'ZSC'; head[V.zscRank] = '#';
  for (var b = 0; b < PUNTS.length; b++) {
    head[V.p0 + b] = PUNTS[b].label.replace('Punt ', 'P:\n');
    head[V.pr0 + b] = '#\n' + PUNTS[b].label.replace('Punt ', '');
  }
  for (var i = 0; i < CAT_LABELS.length; i++) {
    head[V.dh0 + i] = CAT_LABELS[i];
    head[V.d0 + i] = CAT_LABELS[i];
    head[V.z0 + i] = CAT_LABELS[i];
  }
  var hrow = [];
  for (var h = 1; h <= V_LAST; h++) hrow.push(head[h] === undefined ? '' : head[h]);
  sh.getRange(HDR - 1, 1, 1, V_LAST).setNumberFormat('@').setValues([hrow]);

  var units = [];
  for (var u = 1; u <= V_LAST; u++) units.push('');
  units[V.gp - 1] = 'per game';
  units[V.durh - 1] = 'mean of 7'; units[V.zsh - 1] = 'mean of 7';
  units[V.zsc - 1] = 'mean of 9';
  for (var j = 0; j < CAT_LABELS.length; j++) {
    units[V.d0 + j - 1] = 'λ ' + fmtNum(deriv('lambdas', CAT_LABELS[j]));
    units[V.dh0 + j - 1] = 'w ' + fmtNum(deriv('weights', CAT_LABELS[j]));
    units[V.z0 + j - 1] = 'SD';
  }
  sh.getRange(HDR, 1, 1, V_LAST).setNumberFormat('@').setValues([units]);

  var grid = [];
  for (var p = 0; p < PLAYERS.length; p++) {
    var raw = PLAYERS[p], val = rows[p], line = [];
    for (var k = 1; k <= V_LAST; k++) line.push('');
    line[V.player - 1] = raw[1];
    line[V.gp - 1] = raw[5]; line[V.mpg - 1] = raw[6];
    line[V.fgm - 1] = raw[7]; line[V.fga - 1] = raw[8];
    line[V.ftm - 1] = raw[10]; line[V.fta - 1] = raw[11];
    line[V.tpm - 1] = raw[13]; line[V.pts - 1] = raw[14]; line[V.reb - 1] = raw[15];
    line[V.ast - 1] = raw[16]; line[V.stl - 1] = raw[17]; line[V.blk - 1] = raw[18];
    line[V.to - 1] = raw[19];
    line[V.adp - 1] = raw[4];
    line[V.durh - 1] = val[0]; line[V.durhRank - 1] = val[1]; line[V.durhDrop - 1] = val[2];
    line[V.zsh - 1]  = val[3]; line[V.zshRank - 1]  = val[4]; line[V.zshDrop - 1]  = val[5];
    line[V.zsc - 1]  = val[6]; line[V.zscRank - 1]  = val[7];
    for (var q = 0; q < CAT_LABELS.length; q++) {
      line[V.dh0 + q - 1] = val[8 + q];
      line[V.d0 + q - 1]  = val[8 + CAT_LABELS.length + q];
      line[V.z0 + q - 1]  = val[8 + 2 * CAT_LABELS.length + q];
    }
    // Reported, not computed here: the pool is a fixed point settled in Python over this
    // source's own universe, which is far wider than these 200 rows. A rank inside Q means
    // he would be drafted; it does not mean the pool was drawn from the board.
    line[V.poolD - 1] = val[1] <= qValue() ? 1 : 0;
    // Punt builds ship for the default source only. The other tabs leave the block empty
    // rather than dropping the columns, so one V map serves all three.
    if (si === 0 && typeof PUNT_VALUES !== 'undefined') {
      for (var b = 0; b < PUNTS.length; b++) {
        var pv = PUNT_VALUES[PUNTS[b].key];
        if (!pv || !pv[p]) continue;
        line[V.p0 + b - 1] = pv[p][0];
        line[V.pr0 + b - 1] = pv[p][1];
      }
    }
    grid.push(line);
  }
  // Format the dropped-category columns as text BEFORE writing them. Sheets reads "3PM"
  // as a time -- 3:00 PM, stored as 0.625 -- so the tag beside a value would read
  // "#1 0.625" instead of "#1 3PM". It is the only category label that parses as anything
  // else, which is exactly why it survived every offline check.
  sh.getRange(R0, V.durhDrop, POOL_ROWS, 1).setNumberFormat('@');
  sh.getRange(R0, V.zshDrop, POOL_ROWS, 1).setNumberFormat('@');
  sh.getRange(R0, 1, grid.length, V_LAST).setValues(grid);
}

/** A constant the pipeline reported, by block and category label. */
function deriv(block, label) {
  try {
    if (typeof DERIV === 'undefined') return '';
    var b = DERIV[block];
    return b && b[label] !== undefined ? b[label] : '';
  } catch (e) { return ''; }
}
function qValue() {
  try { return (typeof DERIV !== 'undefined' && DERIV.q) ? DERIV.q : 156; }
  catch (e) { return 156; }
}
function fmtNum(v) {
  if (v === '' || v === null || v === undefined) return '';
  var n = Number(v);
  return isNaN(n) ? String(v) : String(Math.round(n * 1000) / 1000);
}

// ------------------------------------------------------- refreshing the data

function sameCell(a, b) {
  var aBlank = (a === '' || a === null || a === undefined);
  var bBlank = (b === '' || b === null || b === undefined);
  if (aBlank || bBlank) return aBlank && bBlank;
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-9;
  return String(a) === String(b);
}

/**
 * Bring a new export onto the board, changing as little as possible.
 *
 * Only cells whose value actually moved are written. Every hand-edited column is left
 * alone, and so is every formula, format and named range.
 *
 * More is rewritten than there used to be: the values are data now, not formulas, so all
 * three calculation tabs are part of a refresh. That makes the cell-level diff below more
 * useful, not less.
 */
function refreshData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Refresh', function () {
    requireData();
    var board = ss.getSheetByName('Board');
    if (!board) throw new Error('No Board sheet yet. Run a full build first.');

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

    // The calculation tabs are pure data: rewrite them wholesale either way.
    for (var s = 0; s < SOURCES.length; s++) {
      var sh = ss.getSheetByName(SOURCES[s].key);
      if (sh) writeCalcSheet(sh, s);
    }
    report += '  Calculation tabs rewritten (' + SOURCES.length + ').';

    SpreadsheetApp.flush();
    ss.toast(report, 'Refresh', 12);
    return report;
  });
}

/** Same players in the same rows — write only the cells that differ. */
function refreshInPlace(board) {
  var changed = 0, touchedRows = {};
  for (var m = 0; m < REFRESH_MAP.length; m++) {
    var col = REFRESH_MAP[m][0], idx = REFRESH_MAP[m][1];
    var cur = board.getRange(R0, col, POOL_ROWS, 1).getValues();
    var next = [], differs = false;
    for (var i = 0; i < POOL_ROWS; i++) {
      var want = PLAYERS[i][idx];
      next.push([want]);
      if (!sameCell(cur[i][0], want)) { differs = true; changed++; touchedRows[i] = true; }
    }
    if (differs) board.getRange(R0, col, POOL_ROWS, 1).setValues(next);
  }
  var rows = 0;
  for (var k in touchedRows) if (touchedRows.hasOwnProperty(k)) rows++;
  return changed
    ? 'Same players, same order. ' + changed + ' cells changed across ' + rows + ' players.'
    : 'Same players, same order, nothing changed.';
}

/**
 * The player set or its order moved — the ordinary case now.
 *
 * A player entering or leaving Hashtag's top 200 changes the row set even when both vendor
 * files still carry him, so this path runs on most refreshes rather than being the
 * exception it was when one source drove everything.
 *
 * Hand edits are captured by player name and put back by name.
 */
function refreshWithReorder(ss, board, oldNames, newNames) {
  var keep = {};
  for (var c = 0; c < HAND_COLS.length; c++) {
    var col = HAND_COLS[c];
    var vals = board.getRange(R0, col, POOL_ROWS, 1).getValues();
    var forms = board.getRange(R0, col, POOL_ROWS, 1).getFormulas();
    for (var i = 0; i < POOL_ROWS; i++) {
      var name = oldNames[i];
      if (!name) continue;
      keep[name] = keep[name] || {};
      if (col === B.myGp) {
        // Only counts as an override once it no longer holds its seeding formula.
        if (!forms[i][0] && vals[i][0] !== '') keep[name][col] = vals[i][0];
      } else if (vals[i][0] !== '') {
        keep[name][col] = vals[i][0];
      }
    }
  }

  writeBoardData(board);
  writeBoardFormulas(board);

  var restored = 0;
  for (var h = 0; h < HAND_COLS.length; h++) {
    var hc = HAND_COLS[h], out = [], any = false;
    for (var j = 0; j < POOL_ROWS; j++) {
      var rec = keep[newNames[j]];
      var v = rec && rec[hc] !== undefined ? rec[hc] : '';
      if (v !== '') { any = true; restored++; }
      out.push([v]);
    }
    if (any) board.getRange(R0, hc, POOL_ROWS, 1).setValues(out);
  }

  var oldSet = {}, newSet = {};
  for (var a = 0; a < oldNames.length; a++) oldSet[oldNames[a]] = true;
  for (var b = 0; b < newNames.length; b++) newSet[newNames[b]] = true;
  var added = newNames.filter(function (n) { return !oldSet[n]; });
  var dropped = oldNames.filter(function (n) { return n && !newSet[n]; });

  var sh = ss.getSheetByName('Settings');
  if (sh) {
    sh.getRange(NOTE_ROW + 3, 1).setValue('Added: ' + (added.join(', ') || 'none'));
    sh.getRange(NOTE_ROW + 4, 1).setValue('Dropped: ' + (dropped.join(', ') || 'none'));
  }
  return 'Order changed. ' + added.length + ' added, ' + dropped.length + ' dropped, '
       + restored + ' hand edits re-attached by name. Re-sort the Draft Board.';
}

// ------------------------------------------------------------ step actions

function step1_Settings() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Settings', function () {
    var sh = sheetByName(ss, 'Settings', 10, 90);
    writeSettingsSkeleton(sh);
    defineNames(ss);
    formatSettings(sh);
  });
}
function step2_Calc() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  requireData();
  for (var i = 0; i < SOURCES.length; i++) {
    (function (idx) {
      _guard('Calc ' + SOURCES[idx].key, function () {
        var sh = sheetByName(ss, SOURCES[idx].key, V_LAST, RN);
        writeCalcSheet(sh, idx);
        formatCalcSheet(sh, idx);
      });
    })(i);
  }
  _guard('Names', function () { defineNames(ss); });
}
function step3_Board() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  requireData();
  _guard('Board', function () {
    var sh = sheetByName(ss, 'Board', B_LAST, RN);
    writeBoardData(sh); writeBoardFormulas(sh); formatBoard(sh);
  });
}
function step4_DraftBoard() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Draft Board', function () {
    // Read the draft state before sheetByName wipes the tab, or the rebuild silently
    // discards every GONE and MINE tick.
    var prior = readCheckState(ss.getSheetByName('Draft Board'));
    var sh = sheetByName(ss, 'Draft Board', D_LAST, RN);
    buildDraftTab(ss, sh, ss.getSheetByName('Board'), prior);
  });
}
function step5_Rest() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Punts',   function () { buildPuntsTab(sheetByName(ss, 'Punts', PUNTS.length * 6, 60)); });
  _guard('Tracker', function () { buildTrackerTab(sheetByName(ss, TRACKER_TAB, 8, 60)); });
  _guard('README',  function () { buildReadme(sheetByName(ss, 'README', 3, 70)); });
  _guard('Tidy', function () {
    var order = ['Draft Board'];
    for (var i = 0; i < SOURCES.length; i++) order.push(SOURCES[i].key);
    reorderTabs(ss, order.concat(['Board', 'Punts', TRACKER_TAB, 'Settings', 'README']));
  });
}

// ---------------------------------------------------------------- Settings

// Settings row numbers are referenced from three places -- the skeleton, defineNames and
// the format pass -- so they are named once here rather than repeated as literals.
var S_LEAGUE = 3;        // header, then 8 rows of league constants
var S_WEIGHTS = 3;       // col D/E: the H2H weights, applied upstream
var S_ROSENOF = 3;       // col G/H: the retired multipliers, reference only
var S_TRACKER = 14;      // header, then 8 category rows: k, w, K, slope
var S_WINRATE = 25;      // header, then 3 rows
var S_POOLS = 31;        // header, then per-source reported constants
var S_SANITY = 50;
var NOTE_ROW = 60;

function writeSettingsSkeleton(sh) {
  sh.getRange('A1').setValue('Settings — constants the board is built from')
    .setFontSize(14).setFontWeight('bold').setFontColor(COLOR.identity);
  sh.getRange('A2').setValue(
    'Yellow cells are yours to type in. Grey cells are REPORTED: they record what the '
    + 'pipeline used, and editing one changes nothing. Values are computed by '
    + 'scripts/draft-board/build_data.py and arrive as numbers (ADR-0016) — to change a '
    + 'weight, a lambda or the punt weight, edit the pipeline and re-run it.');

  sh.getRange(S_LEAGUE, 1, 1, 2).setValues([['LEAGUE', '']]);
  sh.getRange(S_LEAGUE + 1, 1, 8, 2).setValues([
    ['Teams', 12],
    ['Roster spots', 13],
    ['Pool size (Q)', '=B' + (S_LEAGUE + 1) + '*B' + (S_LEAGUE + 2)],
    ['Sort by', sortLabel(0, 0)],
    ['Scoring format', 'Head-to-Head Categories'],
    ['Tier multiplier', 2],
    ['Category band', 1.00],
    ['Disagreement gap', 15]
  ]);

  sh.getRange(S_WEIGHTS, 4, 1, 2).setValues([['H2H WEIGHTS — applied upstream', '']]);
  var w = [];
  for (var i = 0; i < CAT_LABELS.length; i++) {
    w.push([CAT_LABELS[i], deriv('weights', CAT_LABELS[i])]);
  }
  w.push(['TO', 0]);
  sh.getRange(S_WEIGHTS + 1, 4, w.length, 2).setValues(w);
  sh.getRange(S_WEIGHTS + w.length + 1, 4).setValue(
    'Basketball Monster\'s DURANT H2H weights. Turnovers at zero is HOW the metric removes '
    + 'them, not a rounding. Reported here; changing a cell does nothing.');

  sh.getRange(S_ROSENOF, 7, 1, 2).setValues([['ROSENOF G-MULTIPLIERS — unused', '']]);
  sh.getRange(S_ROSENOF + 1, 7, 9, 2).setValues([
    ['FG%', 0.75], ['FT%', 0.77], ['3PM', 0.96], ['PTS', 0.87], ['REB', 0.92],
    ['AST', 1.00], ['STL', 0.59], ['BLK', 0.91], ['TO', 0.83]
  ]);
  sh.getRange(S_ROSENOF + 10, 7).setValue(
    'Rosenof, arXiv 2307.02188 Table 8, 2022-23, normalised to AST = 1.00. These drove the '
    + 'board until ADR-0015 replaced them with the weights on the left. Kept because the '
    + 'playbook\'s reasoning rests on them, and deleting them would strand that argument. '
    + 'Nothing reads these cells.');

  sh.getRange(S_TRACKER, 1, 1, 6).setValues(
    [['CATEGORY TRACKER — K = k / w, exact', '', '', '', '', '']]);
  sh.getRange(S_TRACKER + 1, 1, 1, 5).setValues([['Category', 'k (Rosenof)', 'w (H2H)', 'K', 'D-on-z slope']]);
  var rows = [];
  for (var t = 0; t < CAT_LABELS.length; t++) {
    var lab = CAT_LABELS[t];
    rows.push([lab, deriv('k_rosenof', lab), deriv('weights', lab),
               deriv('k_tracker', lab), deriv('slopes', lab)]);
  }
  sh.getRange(S_TRACKER + 2, 1, rows.length, 5).setValues(rows);

  sh.getRange(S_WINRATE, 1, 1, 2).setValues([['WIN-RATE CUTOFFS', '']]);
  sh.getRange(S_WINRATE + 1, 1, 3, 2).setValues([
    ['Weak at or below', 0.35],
    ['Strong at or above', 0.65],
    ['Banked at or above', 0.75]
  ]);
  sh.getRange(S_LEAGUE + 10, 1).setValue(
    'Disagreement gap is applied when the Draft Board is built, not live: a conditional '
    + 'format rule may not reference another sheet, so the number is baked into the rule. '
    + 'Change it, then run Rebuild & re-sort.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);

  sh.getRange(S_WINRATE + 4, 1).setValue(
    'The return on the next unit of edge peaks at a coin flip and is down to 80% of peak '
    + 'by 75%, so a nearly-lost category and a nearly-won one are both places to stop '
    + 'spending. Aim for CONTESTED, not STRONG.');

  writePoolBlock(sh);
  writeSanityBlock(sh);
}

/** Per-source pool constants, as reported by the pipeline. Numbers, not formulas. */
function writePoolBlock(sh) {
  sh.getRange(S_POOLS, 1, 1, 6).setValues(
    [['POOL CONSTANTS — reported by the pipeline, not computed here', '', '', '', '', '']]);
  sh.getRange(S_POOLS + 1, 1, 1, 6).setValues(
    [['Source', 'Universe', 'DURANT pool', 'ZSC overlap', 'Pool GP min', 'Pool GP median']]);
  var rows = [];
  for (var i = 0; i < SOURCES.length; i++) {
    var key = SOURCES[i].key, p = {}, uni = '', ov = '';
    try {
      p = DERIV.pools[key].durant;
      uni = DERIV.universe[key];
      ov = DERIV.pool_overlap[key];
    } catch (e) { p = {}; }
    rows.push([SOURCES[i].label, uni, p.size || '', ov,
               p.gp_min === undefined ? '' : p.gp_min,
               p.gp_median === undefined ? '' : p.gp_median]);
  }
  sh.getRange(S_POOLS + 2, 1, rows.length, 6).setValues(rows);
  sh.getRange(S_POOLS + rows.length + 3, 1).setValue(
    'Each source is scored against its own universe, because a value is a property of the '
    + 'pair (stat line, pool) and mixing them produces a number belonging to neither. '
    + 'Hashtag publishes only its top 200, so its pool is drawn from a truncated candidate '
    + 'set; the vendors\' pools are drawn from their full lists. "ZSC overlap" is how many '
    + 'of the DURANT pool the plain-z pool also selects — the two rank a different order, '
    + 'so they do not choose the same 156.');
  sh.getRange(S_POOLS + rows.length + 5, 1).setValue(
    'ADR-0011\'s minimum-games gate is retired: pool membership is a fixed point settled '
    + 'in Python, and rows projected at zero games are dropped before scoring. The concern '
    + 'it named stays visible as the GP columns above. If a pool minimum ever drops into '
    + 'the teens, revisit it on evidence.');
}

function writeSanityBlock(sh) {
  sh.getRange(S_SANITY, 1, 1, 2).setValues([['SANITY CHECKS', '']]);
  var mine = 'COUNTIF(' + colIndirect('Draft Board', D.mine) + ',TRUE)';
  sh.getRange(S_SANITY + 1, 1, 6, 1).setValues([
    ['Names line up across tabs'], ['Draft Board rows line up'], ['Board rows'],
    ['Players ticked Mine'], ['ADP coverage'], ['Data generated']
  ]);
  // The one live guard against the calculation tabs drifting out of row-order with the
  // Board. Every Draft Board reference assumes row i is the same player on all four tabs,
  // and nothing in Sheets would notice if that stopped being true.
  var mismatch = [];
  for (var i = 0; i < SOURCES.length; i++) {
    mismatch.push('SUMPRODUCT(--(' + colIndirect('Board', B.player)
                + '<>' + colIndirect(SOURCES[i].key, V.player) + '))');
  }
  sh.getRange(S_SANITY + 1, 2).setFormula(
    '=IF(' + mismatch.join('+') + '=0,"aligned",'
    + '"MISALIGNED — the calculation tabs are out of step with the Board. Stop.")');
  // The sibling guard, and the one that was missing. The check above compares the
  // calculation tabs against the Board spine; this compares the DRAFT BOARD's own rows
  // against the hidden block they read. Those are different failures: the tabs can be
  // perfectly aligned with each other while the Draft Board's block is left over from the
  // previous sort. Cross-sheet is fine in a cell formula -- it is conditional format
  // RULES that may not reference another sheet.
  var chk = colIndirect('Draft Board', D.rowCheck);
  var who = colIndirect('Draft Board', D.player);
  sh.getRange(S_SANITY + 2, 2).setFormula(
    '=IF(SUMPRODUCT(--(' + chk + '<>' + who + '))=0,"aligned",'
    + '"MISALIGNED — the Draft Board\'s hidden block is out of step with its rows. '
    + 'Run Rebuild & re-sort.")');
  sh.getRange(S_SANITY + 3, 2).setFormula('=COUNTA(' + colIndirect('Board', B.player) + ')');
  sh.getRange(S_SANITY + 4, 2).setFormula('=' + mine);
  sh.getRange(S_SANITY + 5, 2).setFormula(
    '=COUNT(' + colIndirect('Board', B.adp) + ')&" of "&COUNTA('
    + colIndirect('Board', B.player) + ')');
  var gen = '';
  try { gen = META.generated + (META.mixedDates ? '  *** MIXED DATES ***' : ''); } catch (e) {}
  sh.getRange(S_SANITY + 6, 2).setValue(gen);
}

// ----------------------------------------------------------- named ranges

/** `BMP_DURH`, `HBP_ZSC`, `ALT_DH_REB`. A named range may not contain a hyphen. */
function nameOf(prefix, thing) { return prefix.toUpperCase() + '_' + thing; }

function defineNames(ss) {
  var s = 'Settings';
  var names = {
    TEAMS: s + '!$B$' + (S_LEAGUE + 1),
    ROSTER: s + '!$B$' + (S_LEAGUE + 2),
    Q: s + '!$B$' + (S_LEAGUE + 3),
    SORT_BY: s + '!$B$' + (S_LEAGUE + 4),
    SCORING: s + '!$B$' + (S_LEAGUE + 5),
    TIER_MULT: s + '!$B$' + (S_LEAGUE + 6),
    CAT_BAND: s + '!$B$' + (S_LEAGUE + 7),
    DISAGREE_GAP: s + '!$B$' + (S_LEAGUE + 8),
    WEAK_WIN: s + '!$B$' + (S_WINRATE + 1),
    STRONG_WIN: s + '!$B$' + (S_WINRATE + 2),
    BANK_WIN: s + '!$B$' + (S_WINRATE + 3),

    B_PLAYER: colRange('Board', B.player),
    B_ADP: colRange('Board', B.adp),
    B_GP: colRange('Board', B.gp),
    B_MYGP: colRange('Board', B.myGp)
  };

  // One K per category, down the tracker block.
  for (var t = 0; t < CAT_LABELS.length; t++) {
    names['K_' + catKey(CAT_LABELS[t])] = s + '!$D$' + (S_TRACKER + 2 + t);
  }

  // Per source: the value columns the Draft Board and the Punts tab reference.
  for (var i = 0; i < SOURCES.length; i++) {
    var p = SOURCES[i].prefix, sheet = SOURCES[i].key;
    names[nameOf(p, 'PLAYER')] = colRange(sheet, V.player);
    names[nameOf(p, 'DURH')] = colRange(sheet, V.durh);
    names[nameOf(p, 'DURH_RANK')] = colRange(sheet, V.durhRank);
    names[nameOf(p, 'ZSH')] = colRange(sheet, V.zsh);
    names[nameOf(p, 'ZSH_RANK')] = colRange(sheet, V.zshRank);
    names[nameOf(p, 'ZSC')] = colRange(sheet, V.zsc);
    names[nameOf(p, 'ZSC_RANK')] = colRange(sheet, V.zscRank);
    names[nameOf(p, 'ADP')] = colRange(sheet, V.adp);
  }

  // Draft Board ranges the tracker reads. It cannot reach a calculation tab directly:
  // the feed columns follow whichever projection is selected.
  var db = 'Draft Board';
  names.DB_RANK = colRange(db, D.rank);
  names.DB_PLAYER = colRange(db, D.player);
  names.DB_POS = colRange(db, D.pos);
  names.DB_MINE = colRange(db, D.mine);
  names.DB_GONE = colRange(db, D.drafted);
  names.DB_FGM = colRange(db, D.hFgm); names.DB_FGA = colRange(db, D.hFga);
  names.DB_FTM = colRange(db, D.hFtm); names.DB_FTA = colRange(db, D.hFta);
  var raw = [D.h3, D.hPts, D.hReb, D.hAst, D.hStl, D.hBlk];
  var rawNames = ['3PM', 'PTS', 'REB', 'AST', 'STL', 'BLK'];
  for (var r = 0; r < raw.length; r++) {
    names['DB_' + catKey(rawNames[r])] = colRange(db, raw[r]);
  }
  for (var c = 0; c < CAT_LABELS.length; c++) {
    names['DB_DH_' + catKey(CAT_LABELS[c])] = colRange(db, D.dh0 + c);
    names['DB_D_' + catKey(CAT_LABELS[c])] = colRange(db, D.d0 + c);
  }

  var existing = ss.getNamedRanges();
  for (var e = 0; e < existing.length; e++) {
    if (names[existing[e].getName()]) existing[e].remove();
  }
  for (var n in names) if (names.hasOwnProperty(n)) ss.setNamedRange(n, ss.getRange(names[n]));
}

/** A category label as a named-range fragment: 'FG%' -> 'FGPCT', '3PM' -> 'TPM'. */
function catKey(label) {
  if (label === 'FG%') return 'FGPCT';
  if (label === 'FT%') return 'FTPCT';
  if (label === '3PM') return 'TPM';
  return label;
}

// ------------------------------------------------------------- Draft Board

/** Board row order: the selected value, descending. Ties break on the Board's own order. */
function boardOrder(ss, si, ki) {
  var sh = ss.getSheetByName(SOURCES[si].key);
  var col = V[VALUE_KINDS[ki].v];
  var vals = sh.getRange(R0, col, POOL_ROWS, 1).getValues();
  var idx = [];
  for (var i = 0; i < POOL_ROWS; i++) idx.push(i);
  idx.sort(function (a, b) {
    var x = Number(vals[a][0]), y = Number(vals[b][0]);
    if (isNaN(x)) x = -1e9;
    if (isNaN(y)) y = -1e9;
    return y === x ? a - b : y - x;
  });
  return idx.map(function (i) { return R0 + i; });
}

/**
 * Build the draft-day tab.
 *
 * `prior` is the draft state captured BEFORE the sheet was cleared. It has to be passed in
 * rather than read here: every caller that rebuilds from scratch goes through
 * `sheetByName`, which wipes the tab, so reading it at this point would find nothing and
 * silently lose every GONE and MINE tick. `Rebuild & re-sort` passes the live sheet and
 * omits it, which is why re-sorting has always kept the state and a rebuild has not.
 */
function buildDraftTab(ss, sh, board, prior) {
  if (prior === undefined) prior = readCheckState(sh);
  var sel = selectedSort(ss);
  var si = sel[0], ki = sel[1];
  var order = boardOrder(ss, si, ki);

  writeDraftHeaders(sh, si, ki);

  var f = [], names = [];
  var allNames = board.getRange(R0, B.player, POOL_ROWS, 1).getValues();

  for (var i = 0; i < order.length; i++) {
    var n = order[i], r = R0 + i, row = {};
    function bref(col) { return '=' + cellRef('Board', col, n); }
    function vref(sIdx, col) { return '=' + cellRef(SOURCES[sIdx].key, col, n); }

    // Ranked rather than read off the row number, so the column stays correct the moment
    // the sort changes and before a re-sort has run. After a re-sort the two agree.
    //
    // The COUNTIF breaks ties. Bare RANK() gives tied players the same number and then
    // skips one -- 56, 56, 58 -- so the column stops being a permutation of 1..200 and
    // disagrees with the rank on the calculation tabs, which is the invariant verify.py
    // asserts. Six pairs tie at four decimal places on the current data. The expanding
    // range counts equal values at or above this row, so ties break in board order.
    var selCol = '$' + a1col(D.sel);
    var selSpan = selCol + '$' + R0 + ':' + selCol + '$' + RN;
    row[D.rank] = '=RANK(' + selCol + r + ',' + selSpan + ')'
                + '+COUNTIF(' + selCol + '$' + R0 + ':' + selCol + r + ',' + selCol + r + ')-1';
    row[D.round] = '=IF($' + a1col(D.rank) + r + '="","",CEILING($' + a1col(D.rank) + r + '/TEAMS))';
    row[D.player] = bref(B.player); row[D.team] = bref(B.team); row[D.pos] = bref(B.pos);
    row[D.inj] = bref(B.injuries);
    row[D.projGp] = bref(B.gp); row[D.myGp] = bref(B.myGp);
    row[D.adp] = bref(B.adp); row[D.xrank] = bref(B.xrank); row[D.notes] = bref(B.notes);

    for (var s = 0; s < SOURCES.length; s++) {
      for (var k = 0; k < VALUE_KINDS.length; k++) {
        var kind = VALUE_KINDS[k];
        row[dValue(s, k)] = vref(s, V[kind.v]);
        row[dRank(s, k)] = vref(s, V[kind.rank]);
        // "#4 REB", or "#4" for ZSC, which drops nothing. BOTH halves point at the same
        // calculation row, and that is the whole point: the rank used to be read
        // positionally out of the hidden rank column ($BQ4, "whatever sits in my row")
        // while the category was pinned to the player. Let the hidden block fall out of
        // step with the rows -- one half-finished build is enough -- and every tag paired
        // one player's rank with another's dropped category, 1755 of 1800 of them wrong
        // and every one of them looking perfectly ordinary. Anchored this way a tag can
        // only be wrong when the value beside it is wrong too, which is checkable.
        row[dTag(s, k)] = kind.drop
          ? '="#"&' + cellRef(SOURCES[s].key, V[kind.rank], n)
            + '&" "&' + cellRef(SOURCES[s].key, V[kind.drop], n)
          : '="#"&' + cellRef(SOURCES[s].key, V[kind.rank], n);
      }
    }

    // One column carries whatever the board is sorted by. Rank, drop, median, break and
    // tier all read it, so changing the sort repoints this and nothing else.
    row[D.sel] = '=$' + a1col(dValue(si, ki)) + r;

    row[D.gap] = '=IF($' + a1col(D.adp) + r + '="","",$' + a1col(D.adp) + r
               + '-$' + a1col(D.rank) + r + ')';

    // Tiers cut where the value drop is large relative to what is normal nearby. Drops
    // shrink down the board, so a fixed threshold would give one huge blob at the top.
    if (i === 0) {
      row[D.drop] = ''; row[D.med] = ''; row[D.brk] = ''; row[D.tier] = 1;
    } else {
      var dS = '$' + a1col(D.sel), dI = '$' + a1col(D.drop);
      var dJ = '$' + a1col(D.med), dK = '$' + a1col(D.brk), dB = '$' + a1col(D.tier);
      row[D.drop] = '=' + dS + (r - 1) + '-' + dS + r;
      // Fifteen drops centred on this row, clamped at both ends. INDEX(range,k) resolves
      // to sheet row k+HDR, so these offsets give rows r-7 through r+7. A window skewed up
      // the board sits where drops are larger, which inflates the median and fires breaks
      // late -- exactly where the curve steepens and a tier matters most.
      var back = 'ROW()-' + (HDR + 7), fwd = 'ROW()+' + (7 - HDR);
      var dropRange = dI + '$' + R0 + ':' + dI + '$' + RN;
      row[D.med]  = '=MEDIAN(INDEX(' + dropRange + ',MAX(1,' + back + '))'
                  + ':INDEX(' + dropRange + ',MIN(' + POOL_ROWS + ',' + fwd + ')))';
      row[D.brk]  = '=IF(N(' + dJ + r + ')<=0,"",IF(' + dI + r
                  + '>TIER_MULT*' + dJ + r + ',"BREAK",""))';
      row[D.tier] = '=IF(' + dK + r + '="BREAK",' + dB + (r - 1) + '+1,' + dB + (r - 1) + ')';
    }

    row[D.gpFlag] = bref(B.gpCheck);
    row[D.best] = bestBuildFormula(n, r);
    profileFormulas(row, r);
    row[D.posLeft] = posLeftFormula(r);

    // The feeds follow the SELECTED projection, so the tracker measures your roster on the
    // same numbers the board is ranking by.
    var feedRaw = [[D.hFgm, V.fgm], [D.hFga, V.fga], [D.hFtm, V.ftm], [D.hFta, V.fta],
                   [D.h3, V.tpm], [D.hPts, V.pts], [D.hReb, V.reb], [D.hAst, V.ast],
                   [D.hStl, V.stl], [D.hBlk, V.blk]];
    for (var fr = 0; fr < feedRaw.length; fr++) {
      row[feedRaw[fr][0]] = vref(si, feedRaw[fr][1]);
    }
    for (var cc = 0; cc < CAT_LABELS.length; cc++) {
      row[D.dh0 + cc] = vref(si, V.dh0 + cc);
      row[D.d0 + cc] = vref(si, V.d0 + cc);
    }
    // Same `n` as the rest of the block, which is exactly what makes it a witness: if the
    // block is ever left over from another ordering, this name stops matching Player.
    row[D.rowCheck] = vref(si, V.player);

    var line = [];
    for (var c = 1; c <= D_LAST; c++) line.push(row[c] === undefined ? '' : row[c]);
    f.push(line);
    names.push(allNames[n - R0][0]);
  }

  writeGrid(sh, f, 1, D.mine - 1);
  writeGrid(sh, f, dValue(0, 0), D.gap);
  writeGrid(sh, f, D.best, D.posLeft);
  writeGrid(sh, f, D.notes, D_LAST);

  sh.getRange(R0, D.drafted, POOL_ROWS, 2).insertCheckboxes();
  restoreCheckState(sh, names, prior);
  formatDraftTab(sh, si, ki);
  drawTierBreaks(sh);
}

/** Rows 1-3: the control strip, the block banners, the column headers. */
function writeDraftHeaders(sh, si, ki) {
  // Row 1. Three checkboxes with their labels, then the sort dropdown. The merge ends
  // exactly at the frozen boundary, because a freeze may not split a merged cell.
  sh.getRange(1, 1, 1, D_LAST).setBackground(COLOR.chrome);
  for (var s = 0; s < SOURCES.length; s++) {
    sh.getRange(1, 1 + s * 2).insertCheckboxes().setValue(true);
    sh.getRange(1, 2 + s * 2).setValue(SOURCES[s].label)
      .setFontSize(8).setFontWeight('bold').setFontColor(COLOR.identity);
  }
  sh.getRange(1, D.drafted, 1, 2).merge();
  sh.getRange(1, D.drafted).setValue(sortLabel(si, ki))
    .setBackground(COLOR.inputBg).setFontColor(COLOR.inputText)
    .setFontSize(10).setFontWeight('bold').setHorizontalAlignment('center')
    .setDataValidation(SpreadsheetApp.newDataValidation()
      .requireValueInList(allSortLabels(), true).build());

  var head = [];
  for (var c = 1; c <= D_LAST; c++) head[c] = '';
  head[D.rank] = '#'; head[D.tier] = 'TIER'; head[D.round] = 'RND';
  head[D.player] = 'Player'; head[D.team] = 'Tm'; head[D.pos] = 'Pos'; head[D.inj] = 'INJ';
  head[D.drafted] = 'GONE'; head[D.mine] = 'MINE';
  for (var s2 = 0; s2 < SOURCES.length; s2++) {
    for (var k2 = 0; k2 < VALUE_KINDS.length; k2++) {
      head[dValue(s2, k2)] = VALUE_KINDS[k2].label;
      head[dTag(s2, k2)] = '';
    }
  }
  head[D.sel] = 'sorted by';
  head[D.drop] = 'Drop'; head[D.med] = 'Local\nmed'; head[D.brk] = 'Break';
  head[D.projGp] = 'Proj\nGP'; head[D.myGp] = 'My\nGP'; head[D.gpFlag] = 'Flag';
  head[D.adp] = 'ADP'; head[D.xrank] = 'XRank'; head[D.gap] = 'GAP';
  head[D.best] = 'Best build';
  head[D.strengths] = '▲ Strengths'; head[D.weaknesses] = '▼ Weaknesses';
  head[D.posLeft] = 'Left\n@pos'; head[D.notes] = 'Notes';
  for (var f = 0; f < CAT_LABELS.length; f++) {
    head[D.dh0 + f] = 'dh ' + CAT_LABELS[f];
    head[D.d0 + f] = 'd ' + CAT_LABELS[f];
  }
  var rawLab = ['FGM', 'FGA', 'FTM', 'FTA', '3PM', 'PTS', 'REB', 'AST', 'STL', 'BLK'];
  var rawCol = [D.hFgm, D.hFga, D.hFtm, D.hFta, D.h3, D.hPts, D.hReb, D.hAst, D.hStl, D.hBlk];
  for (var g = 0; g < rawCol.length; g++) head[rawCol[g]] = rawLab[g];
  for (var s3 = 0; s3 < SOURCES.length; s3++) {
    for (var k3 = 0; k3 < VALUE_KINDS.length; k3++) {
      head[dRank(s3, k3)] = SOURCES[s3].label + ' ' + VALUE_KINDS[k3].label + ' #';
    }
  }
  head[D.rowCheck] = 'row check';
  var hrow = [];
  for (var h = 1; h <= D_LAST; h++) hrow.push(head[h] === undefined ? '' : head[h]);
  sh.getRange(HDR, 1, 1, D_LAST).setNumberFormat('@').setValues([hrow]);
}

/** "AST+STL +21" — the build that likes this player most, and by how much. */
function bestBuildFormula(n, r) {
  var src = SOURCES[0].key;                     // punt builds ship for the default source
  var base = cellRef(src, V.durhRank, n);
  // One contiguous 1x9 range, which is why the punt rank block has to stay contiguous:
  // MATCH scans it as a single range and the labels are positional against it.
  var span = sheetRef(src) + '!$' + a1col(V.pr0) + '$' + n
           + ':$' + a1col(V.pr0 + PUNTS.length - 1) + '$' + n;
  var labels = [];
  for (var i = 0; i < PUNTS.length; i++) {
    labels.push('"' + PUNTS[i].label.replace('Punt ', '') + '"');
  }
  return '=IFERROR(IF(MIN(' + span + ')>=' + base + ',"—",'
       + 'INDEX({' + labels.join(';') + '},MATCH(MIN(' + span + '),' + span + ',0))'
       + '&"  "&TEXT(' + base + '-MIN(' + span + '),"+0")),"—")';
}

/**
 * Which categories this player actually moves, named. A descriptor, not a valuation.
 *
 * Built on the UNWEIGHTED DURANT values, divided by nothing further, because a weighted
 * column's SD is exactly its weight -- so a single band would be unreachable for the five
 * categories weighted below 1 and FG%, FT%, 3PM, STL and BLK would never fire at all.
 * The unweighted column is also the right basis by ADR-0013's own argument: the weight is
 * the how-much-is-it-worth term, and this column asks the prior question, does he have the
 * edge at all.
 *
 * Split into two columns. One 240px string forced the eye to parse before it could read;
 * apart, strengths are scanned when the tracker says a category is contested, and
 * weaknesses can carry a pale fill so damage registers without being read.
 *
 * TWO ARRAY TRAPS LIVE HERE, and neither is visible offline -- the harness compares
 * formula strings and never evaluates one.
 *
 *   1. Sheets does not array-evaluate an IF handed to another function as an argument.
 *      Without the ARRAYFORMULA wrapper, TEXTJOIN receives a single value and all 200
 *      rows return #VALUE!.
 *   2. A LET binding is evaluated OUTSIDE any enclosing ARRAYFORMULA. Binding
 *      `TRANSPOSE(punted)<>TRUE` collapses to a 1x1 FALSE the moment one box is ticked,
 *      and the whole column silently goes to the em-dash. So bind the raw TRANSPOSE --
 *      a native array function, which survives -- and do the <>TRUE inside.
 *
 * Verified against the live sheet. Nothing offline distinguishes the working form from
 * either broken one.
 */
function profileFormulas(row, r) {
  var d0 = '$' + a1col(D.d0) + r + ':$' + a1col(D.d0 + CAT_LABELS.length - 1) + r;
  var labels = [];
  for (var i = 0; i < CAT_LABELS.length; i++) labels.push('"' + CAT_LABELS[i] + '"');
  // A category ticked Punted on the tracker drops out of both lists, so these columns only
  // ever name categories still being contested. Safe from circularity ONLY because those
  // cells are literal checkboxes and never formulas.
  var punted = sheetRef(TRACKER_TAB) + '!$' + a1col(TRACK_PUNT_COL) + '$' + TRACKER_R0
             + ':$' + a1col(TRACK_PUNT_COL) + '$' + (TRACKER_R0 + CAT_LABELS.length - 1);
  var head = '=IF($' + a1col(D.player) + r + '="","",LET(d,' + d0 + ','
           + 'L,{' + labels.join(',') + '},'
           + 'punt,TRANSPOSE(' + punted + '),';
  row[D.strengths] = head
    + 's,TEXTJOIN(", ",TRUE,ARRAYFORMULA(IF((d>=CAT_BAND)*(punt<>TRUE),L,""))),'
    + 'IF(s="","—","▲ "&s)))';
  row[D.weaknesses] = head
    + 'w,TEXTJOIN(", ",TRUE,ARRAYFORMULA(IF((d<=-CAT_BAND)*(punt<>TRUE),L,""))),'
    + 'IF(w="","—","▼ "&w)))';
}

/**
 * How many players still competing for a slot THIS player can fill.
 *
 * A scarcity tiebreak, not a valuation: position stays out of the value entirely. Both
 * sides have to be multi-eligible -- a PF,C candidate counts toward centres, and a PF,C
 * subject has his centre scarcity measured too. Matching only the first-listed position
 * answered a narrower question, turning his own eligibility into a single slot.
 *
 * The one column that needs the GONE boxes ticked for other managers' picks.
 */
function posLeftFormula(r) {
  var tC = a1col(D.tier), pC = a1col(D.pos), gC = a1col(D.drafted);
  function dcol(c) { return '$' + c + '$' + R0 + ':$' + c + '$' + RN; }
  return '=IF($' + tC + r + '="","",SUMPRODUCT((' + dcol(tC) + '=$' + tC + r + ')*('
       + dcol(gC) + '=FALSE)*REGEXMATCH(' + dcol(pC) + ',SUBSTITUTE($' + pC + r + ',",","|"))))';
}

function writeGrid(sh, grid, c1, c2) {
  var out = [];
  for (var i = 0; i < grid.length; i++) out.push(grid[i].slice(c1 - 1, c2));
  var rng = sh.getRange(R0, c1, out.length, c2 - c1 + 1);
  // The tier column mixes a literal 1 with formulas; setValues handles both.
  var hasLiteral = false;
  for (var a = 0; a < out.length; a++)
    for (var b = 0; b < out[a].length; b++)
      if (out[a][b] !== '' && String(out[a][b]).charAt(0) !== '=') hasLiteral = true;
  if (hasLiteral) rng.setValues(out); else rng.setFormulas(out);
}

/**
 * Where Player / Gone / Mine / Notes / Injuries sit on the sheet AS IT CURRENTLY STANDS,
 * read from its own header row rather than from the D map.
 *
 * This is the whole point: it runs against the OLD sheet while the rest of the build uses
 * the NEW map. Insert a column ahead of Gone and the two disagree by one, so the old Mine
 * column is read as Gone -- the draft state silently corrupted rather than merely wiped,
 * on the two controls used on the clock.
 */
function draftHeaderCols(sh) {
  var want = { Player: D.player, GONE: D.drafted, MINE: D.mine,
               Notes: D.notes, INJ: D.inj };
  var out = { Player: D.player, GONE: D.drafted, MINE: D.mine,
              Notes: D.notes, INJ: D.inj };
  try {
    var wide = Math.min(sh.getMaxColumns(), D_LAST + 8);
    // The header row moved when the control strip landed, so look at both.
    var rows = [HDR, HDR - 1, 2];
    for (var q = 0; q < rows.length; q++) {
      var head = sh.getRange(rows[q], 1, 1, wide).getValues()[0];
      var hits = 0;
      for (var c = 0; c < head.length; c++) {
        var label = String(head[c] === null || head[c] === undefined ? '' : head[c]).trim();
        if (want.hasOwnProperty(label)) { out[label] = c + 1; hits++; }
      }
      if (hits) return out;
    }
  } catch (e) { /* first build: no header row yet */ }
  return out;
}

function readCheckState(sh) {
  var state = {};
  try {
    if (!sh || sh.getLastRow() < R0) return state;
    var n = Math.min(POOL_ROWS, sh.getLastRow() - HDR);
    if (n <= 0) return state;
    var at = draftHeaderCols(sh);
    var names = sh.getRange(R0, at.Player, n, 1).getValues();
    // Each column read on its own. They are no longer adjacent, and a span would
    // reintroduce exactly the positional assumption this exists to remove. Notes and
    // Injuries travel with the checkboxes because a re-sort moves every player's row;
    // without them a note stays put and ends up beside whoever landed there.
    var gone  = sh.getRange(R0, at.GONE,  n, 1).getValues();
    var mine  = sh.getRange(R0, at.MINE,  n, 1).getValues();
    var notes = sh.getRange(R0, at.Notes, n, 1).getValues();
    var inj   = sh.getRange(R0, at.INJ,   n, 1).getValues();
    for (var i = 0; i < n; i++) {
      if (names[i][0]) {
        state[names[i][0]] = {
          gone: gone[i][0] === true, mine: mine[i][0] === true,
          notes: notes[i][0] || '', inj: inj[i][0] || ''
        };
      }
    }
  } catch (e) { /* first build */ }
  return state;
}

/**
 * Put the draft state back, by name.
 *
 * Written column by column rather than as one span: Gone and Mine now sit in the frozen
 * pane and Notes at the far right, so there is no contiguous block to write.
 */
function restoreCheckState(sh, names, prior) {
  var cols = [[D.drafted, 'gone', false], [D.mine, 'mine', false],
              [D.notes, 'notes', ''], [D.inj, 'inj', '']];
  for (var c = 0; c < cols.length; c++) {
    var col = cols[c][0], key = cols[c][1], blank = cols[c][2];
    var out = [], any = false;
    for (var i = 0; i < names.length; i++) {
      var p = prior[names[i]];
      var v = p && p[key] !== undefined && p[key] !== '' && p[key] !== false ? p[key] : blank;
      if (v !== blank) any = true;
      out.push([v]);
    }
    if (any) sh.getRange(R0, col, out.length, 1).setValues(out);
  }
}

/**
 * Draw the tier cliffs. Conditional formatting cannot set borders, and a tier break has to
 * read at a glance without parsing the tier number.
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

// ------------------------------------------------------------- formatting

function formatBoard(sh) {
  var blocks = [
    [B.seed, B.pos, 'IDENTITY', COLOR.identity],
    [B.gp, B.to, 'RAW PROJECTION  (HBP, per game)', COLOR.raw],
    [B.gp1, B.gpCheck, 'AVAILABILITY  ·  context only, nothing scales by it', COLOR.avail],
    [B.adp, B.xrank, 'MARKET', COLOR.market],
    [B.injuries, B.notes, 'YOURS', COLOR.notes]
  ];
  blocks.forEach(function (b) {
    blockHeader(sh, b[0], b[1], b[2], b[3]);
    sh.getRange(HDR, b[0], 1, b[1] - b[0] + 1)
      .setBackground(b[3]).setFontColor(COLOR.headerText)
      .setFontWeight('bold').setFontSize(9).setWrap(true)
      .setHorizontalAlignment('center').setVerticalAlignment('middle');
  });

  sh.setFrozenRows(HDR);
  sh.setFrozenColumns(B.pos);
  sh.setRowHeight(HDR - 1, 22); sh.setRowHeight(HDR, 34);

  for (var c = 1; c <= B_LAST; c++) sh.setColumnWidth(c, 52);
  sh.setColumnWidth(B.seed, 44);
  sh.setColumnWidth(B.player, 170);
  sh.setColumnWidth(B.team, 48);
  sh.setColumnWidth(B.pos, 74);
  sh.setColumnWidth(B.injuries, 70);
  sh.setColumnWidth(B.notes, 260);

  sh.getRange(R0, 1, POOL_ROWS, B_LAST).setFontSize(10).setVerticalAlignment('middle');
  sh.getRange(R0, B.player, POOL_ROWS, 1).setFontWeight('bold');
  sh.getRange(R0, B.seed, POOL_ROWS, 1).setHorizontalAlignment('center');

  sh.getRange(R0, B.gp, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, B.mpg, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, B.fgm, POOL_ROWS, 2).setNumberFormat('0.0');
  sh.getRange(R0, B.fgp, POOL_ROWS, 1).setNumberFormat('0.000');
  sh.getRange(R0, B.ftm, POOL_ROWS, 2).setNumberFormat('0.0');
  sh.getRange(R0, B.ftp, POOL_ROWS, 1).setNumberFormat('0.000');
  sh.getRange(R0, B.tpm, POOL_ROWS, B.to - B.tpm + 1).setNumberFormat('0.0');
  sh.getRange(R0, B.gp1, POOL_ROWS, 4).setNumberFormat('0');
  sh.getRange(R0, B.adp, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, B.xrank, POOL_ROWS, 1).setNumberFormat('0');

  [B.gp1, B.gp2, B.gp3, B.myGp, B.xrank, B.injuries, B.notes].forEach(function (c2) {
    markInput(sh, c2);
  });

  // The projection has no player-level opinion inside the generic band.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=AND($' + a1col(B.gp) + R0 + '>=68,$' + a1col(B.gp) + R0 + '<=74)')
    .setBackground(COLOR.warnBg)
    .setRanges([sh.getRange(R0, B.gp, POOL_ROWS, 1)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo('CHECK')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(R0, B.gpCheck, POOL_ROWS, 1)]).build());
  // Banding last, so the specific rules above win where they overlap.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ISEVEN(ROW())')
    .setBackground(COLOR.band)
    .setRanges([sh.getRange(R0, 1, POOL_ROWS, B.to)]).build());

  sh.setHiddenGridlines(true);
}

/**
 * A calculation tab. Read rarely and carefully, so everything here says worksheet rather
 * than instrument: gridlines on, no banding, monospaced, uniform column widths.
 *
 * Monospace is the cheapest strong signal available. Decimal points line up down every
 * column, so an outlier reads as a shape rather than as a number you have to parse -- which
 * is exactly what an audit surface is for.
 */
function formatCalcSheet(sh, si) {
  var src = SOURCES[si];
  var blocks = [
    [V.player, V.poolD, '1 · IDENTITY', COLOR.identity],
    [V.gp, V.adp, '2 · RAW  (per game)', COLOR.raw],
    [V.durh, V.zscRank, '3 · VALUES', COLOR.value],
    [V.dh0, V.dh0 + CAT_LABELS.length - 1, '4 · DURANT H2H  (weighted)', COLOR.transform],
    [V.d0, V.d0 + CAT_LABELS.length - 1, '5 · DURANT  (unweighted)', COLOR.transform],
    [V.z0, V.z0 + CAT_LABELS.length - 1, '6 · PLAIN z  (audit)', COLOR.z],
    [V.p0, V.pr0 + PUNTS.length - 1, '7 · PUNT BUILDS', COLOR.punt]
  ];
  blocks.forEach(function (b) {
    blockHeader(sh, b[0], b[1], b[2], b[3], HDR - 2);
    sh.getRange(HDR - 1, b[0], 1, b[1] - b[0] + 1)
      .setBackground(b[3]).setFontColor(COLOR.headerText)
      .setFontWeight('bold').setFontSize(9).setWrap(true)
      .setHorizontalAlignment('center').setVerticalAlignment('middle');
  });

  sh.setFrozenRows(HDR);
  sh.setFrozenColumns(V.poolD);
  sh.setRowHeight(HDR - 2, 22); sh.setRowHeight(HDR - 1, 32); sh.setRowHeight(HDR, 16);

  for (var c = 1; c <= V_LAST; c++) sh.setColumnWidth(c, 56);
  sh.setColumnWidth(V.player, 170);
  sh.setColumnWidth(V.poolD, 40);

  var data = sh.getRange(R0, 1, POOL_ROWS, V_LAST);
  data.setFontSize(10).setFontFamily('Roboto Mono').setHorizontalAlignment('right');
  sh.getRange(R0, V.player, POOL_ROWS, 1)
    .setFontFamily('Arial').setHorizontalAlignment('left').setFontWeight('bold');
  sh.getRange(HDR, 1, 1, V_LAST)
    .setFontSize(8).setFontStyle('italic').setFontColor(COLOR.muted)
    .setHorizontalAlignment('center');

  sh.getRange(R0, V.gp, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, V.mpg, POOL_ROWS, V.to - V.mpg + 1).setNumberFormat('0.0');
  sh.getRange(R0, V.adp, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, V.durh, POOL_ROWS, 1).setNumberFormat('+0.000;−0.000;0.000');
  sh.getRange(R0, V.zsh, POOL_ROWS, 1).setNumberFormat('+0.000;−0.000;0.000');
  sh.getRange(R0, V.zsc, POOL_ROWS, 1).setNumberFormat('+0.000;−0.000;0.000');
  sh.getRange(R0, V.durhRank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, V.zshRank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, V.zscRank, POOL_ROWS, 1).setNumberFormat('0');
  sh.getRange(R0, V.dh0, POOL_ROWS, CAT_LABELS.length * 3)
    .setNumberFormat('+0.00;−0.00;0.00');
  sh.getRange(R0, V.p0, POOL_ROWS, PUNTS.length).setNumberFormat('+0.000;−0.000;0.000');
  sh.getRange(R0, V.pr0, POOL_ROWS, PUNTS.length).setNumberFormat('0');

  // Three rules, all diagnostic. No colour scales: you read numbers here, not scan them.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ISERROR(A' + R0 + ')')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText)
    .setRanges([sh.getRange(R0, 1, POOL_ROWS, V_LAST)]).build());
  // A standardised value beyond four SD is the class of bug an audit surface exists for.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ABS($' + a1col(V.d0) + R0 + ')>4')
    .setBackground(COLOR.warnBg)
    .setRanges([sh.getRange(R0, V.d0, POOL_ROWS, CAT_LABELS.length * 2)]).build());
  // Non-pool rows recede, so the replacement line is visible.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + a1col(V.poolD) + R0 + '=0')
    .setFontColor(COLOR.faint)
    .setRanges([sh.getRange(R0, V.player, POOL_ROWS, 2)]).build());

  resetColumnGroups(sh, V_LAST);
  groupAndCollapse(sh, V.z0, V.z0 + CAT_LABELS.length - 1);
  if (si !== 0) groupAndCollapse(sh, V.p0, V.pr0 + PUNTS.length - 1);
  sh.setHiddenGridlines(false);
}

/**
 * The draft-day tab.
 *
 * The colour budget goes where the information is. The board is sorted by the active value
 * column, so a gradient on it reads as a value ramp and the point where it flattens is the
 * point where the board stops mattering. The other eight value columns get no fill at all;
 * their TAGS carry the one genuinely new fact on the tab, which is where the three
 * projections disagree. Nine gradients would be noise, and eight of them would encode
 * nothing you cannot read from row position.
 */
function formatDraftTab(sh, si, ki) {
  var activeCol = dValue(si, ki);

  blockHeader(sh, D.rank, D.inj, 'WHO', COLOR.identity);
  blockHeader(sh, D.drafted, D.mine, 'CLOCK', COLOR.value);
  for (var s = 0; s < SOURCES.length; s++) {
    blockHeader(sh, dSpanStart(s), dSpanStart(s) + SPAN - 1,
                SOURCES[s].label, s === si ? SOURCES[s].head : SOURCES[s].off);
  }
  blockHeader(sh, D.sel, D.brk, 'TIERING', COLOR.z);
  blockHeader(sh, D.projGp, D.gpFlag, 'GP · context only', COLOR.avail);
  blockHeader(sh, D.adp, D.gap, 'MARKET', COLOR.market);
  blockHeader(sh, D.best, D.best, 'BUILD', COLOR.punt);
  blockHeader(sh, D.strengths, D.weaknesses, 'PROFILE', COLOR.transform);
  blockHeader(sh, D.posLeft, D.notes, 'DRAFT DAY', COLOR.identity);
  blockHeader(sh, D.hFgm, D_LAST, 'HELPERS — DO NOT READ', COLOR.notes);

  sh.getRange(HDR, 1, 1, D_LAST)
    .setFontColor(COLOR.headerText).setFontWeight('bold').setFontSize(9).setWrap(true)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');
  // Repaint each header cell in its own block colour.
  var paint = [
    [D.rank, D.inj, COLOR.identity], [D.drafted, D.mine, COLOR.value],
    [D.sel, D.brk, COLOR.z], [D.projGp, D.gpFlag, COLOR.avail],
    [D.adp, D.gap, COLOR.market], [D.best, D.best, COLOR.punt],
    [D.strengths, D.weaknesses, COLOR.transform], [D.posLeft, D.notes, COLOR.identity],
    [D.hFgm, D_LAST, COLOR.notes]
  ];
  paint.forEach(function (p) {
    sh.getRange(HDR, p[0], 1, p[1] - p[0] + 1).setBackground(p[2]);
  });
  for (var s2 = 0; s2 < SOURCES.length; s2++) {
    sh.getRange(HDR, dSpanStart(s2), 1, SPAN)
      .setBackground(s2 === si ? SOURCES[s2].head : SOURCES[s2].off);
    // One header across each value+tag pair: the strongest signal that the two columns
    // are one field.
    for (var k = 0; k < VALUE_KINDS.length; k++) {
      sh.getRange(HDR, dValue(s2, k), 1, 2).merge();
    }
  }

  sh.setFrozenRows(HDR);
  sh.setFrozenColumns(D.mine);
  sh.setRowHeight(1, 24); sh.setRowHeight(HDR - 1, 22); sh.setRowHeight(HDR, 32);

  sh.setColumnWidth(D.rank, 34); sh.setColumnWidth(D.tier, 36);
  sh.setColumnWidth(D.round, 34); sh.setColumnWidth(D.player, 168);
  sh.setColumnWidth(D.team, 40); sh.setColumnWidth(D.pos, 68); sh.setColumnWidth(D.inj, 56);
  sh.setColumnWidth(D.drafted, 46); sh.setColumnWidth(D.mine, 46);
  for (var s3 = 0; s3 < SOURCES.length; s3++) {
    for (var k3 = 0; k3 < VALUE_KINDS.length; k3++) {
      var vc = dValue(s3, k3);
      sh.setColumnWidth(vc, vc === activeCol ? 60 : 48);
      // ZSC drops nothing, so its tag is a bare rank and needs less room.
      sh.setColumnWidth(dTag(s3, k3), VALUE_KINDS[k3].drop ? 42 : 32);
    }
  }
  sh.setColumnWidth(D.sel, 56);
  sh.setColumnWidth(D.drop, 50); sh.setColumnWidth(D.med, 50); sh.setColumnWidth(D.brk, 54);
  sh.setColumnWidth(D.projGp, 44); sh.setColumnWidth(D.myGp, 44); sh.setColumnWidth(D.gpFlag, 46);
  sh.setColumnWidth(D.adp, 48); sh.setColumnWidth(D.xrank, 46); sh.setColumnWidth(D.gap, 54);
  sh.setColumnWidth(D.best, 108);
  sh.setColumnWidth(D.strengths, 132); sh.setColumnWidth(D.weaknesses, 118);
  sh.setColumnWidth(D.posLeft, 50); sh.setColumnWidth(D.notes, 300);

  sh.getRange(R0, 1, POOL_ROWS, D_LAST).setFontSize(10).setVerticalAlignment('middle');
  sh.getRange(R0, D.player, POOL_ROWS, 1).setFontSize(11).setFontWeight('bold');
  sh.getRange(R0, D.rank, POOL_ROWS, 3).setHorizontalAlignment('center');
  sh.getRange(R0, D.rank, POOL_ROWS, 1).setFontColor(COLOR.muted);
  sh.getRange(R0, D.tier, POOL_ROWS, 1).setFontWeight('bold');
  sh.getRange(R0, D.round, POOL_ROWS, 1).setNumberFormat('"R"0').setFontColor(COLOR.muted);
  sh.getRange(R0, D.team, POOL_ROWS, 1).setFontColor(COLOR.muted);
  sh.getRange(R0, D.inj, POOL_ROWS, 1).setHorizontalAlignment('center').setFontWeight('bold');

  for (var s4 = 0; s4 < SOURCES.length; s4++) {
    for (var k4 = 0; k4 < VALUE_KINDS.length; k4++) {
      var col = dValue(s4, k4), tag = dTag(s4, k4);
      var isActive = col === activeCol;
      sh.getRange(R0, col, POOL_ROWS, 1)
        .setNumberFormat('+0.000;−0.000;0.000').setHorizontalAlignment('right')
        .setFontSize(isActive ? 11 : 10).setFontWeight(isActive ? 'bold' : 'normal');
      if (isActive) {
        sh.getRange(R0, col, POOL_ROWS, 1).setBackground(COLOR.active);
      }
      // The tag carries the group's ribbon and is excluded from banding, so the three
      // projections read as unbroken vertical stripes even with the header scrolled past.
      sh.getRange(R0, tag, POOL_ROWS, 1)
        .setBackground(SOURCES[s4].band).setFontSize(8).setFontColor(COLOR.muted)
        .setHorizontalAlignment('left');
    }
    // Opening rule on each group's FIRST column, never a closing one on its last: any
    // subset of groups then stays correctly bounded when the others are hidden.
    sh.getRange(1, dSpanStart(s4), RN, 1).setBorder(
      null, true, null, null, null, null, COLOR.ruleGroup,
      SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
  }
  sh.getRange(1, D.sel, RN, 1).setBorder(
    null, true, null, null, null, null, COLOR.ruleGroup,
    SpreadsheetApp.BorderStyle.SOLID_MEDIUM);

  sh.getRange(R0, D.drop, POOL_ROWS, 2).setNumberFormat('0.000');
  sh.getRange(R0, D.sel, POOL_ROWS, 1).setNumberFormat('+0.000;−0.000;0.000');
  sh.getRange(R0, D.projGp, POOL_ROWS, 2).setNumberFormat('0');
  sh.getRange(R0, D.projGp, POOL_ROWS, 1).setFontColor(COLOR.muted);
  sh.getRange(R0, D.adp, POOL_ROWS, 1).setNumberFormat('0.0');
  sh.getRange(R0, D.xrank, POOL_ROWS, 1).setNumberFormat('0');
  // The glyphs are the non-colour channel: GAP survives greyscale and colour blindness.
  sh.getRange(R0, D.gap, POOL_ROWS, 1)
    .setNumberFormat('"▲ "+0;"▼ "−0;0').setFontWeight('bold').setHorizontalAlignment('center');
  sh.getRange(R0, D.hFgm, POOL_ROWS, 10).setNumberFormat('0.0');
  sh.getRange(R0, D.dh0, POOL_ROWS, CAT_LABELS.length * 2).setNumberFormat('+0.00;−0.00;0.00');
  sh.getRange(R0, D.rank0, POOL_ROWS, SOURCES.length * VALUE_KINDS.length).setNumberFormat('0');

  markInput(sh, D.notes);
  sh.getRange(R0, D.notes, POOL_ROWS, 1).setFontWeight('normal');
  sh.getRange(R0, D.weaknesses, POOL_ROWS, 1).setBackground(COLOR.negBg);

  addDraftRules(sh, si, ki, activeCol, disagreeGap());

  resetColumnGroups(sh, D_LAST);
  groupAndCollapse(sh, D.drop, D.med);
  groupAndCollapse(sh, D.projGp, D.gpFlag);
  groupAndCollapse(sh, D.xrank, D.xrank);
  groupAndCollapse(sh, D.hFgm, D_LAST);
  sh.hideColumns(D.sel, 1);
  sh.hideColumns(D.hFgm, D_LAST - D.hFgm + 1);
  sh.setHiddenGridlines(true);
}

/**
 * How far apart two ranks have to be before the tag is highlighted.
 *
 * Read at build time and inlined into the rule as a literal, because **a conditional
 * format rule may not reference another sheet** -- and every named range lives on
 * Settings. Referencing DISAGREE_GAP directly fails the whole rule set with
 * "Conditional format rule cannot reference a different sheet", which takes the Draft
 * Board build down with it.
 *
 * The cost is that changing the cell does not repaint until the next re-sort. Settings
 * says so beside it.
 */
function disagreeGap() {
  try {
    var v = Number(SpreadsheetApp.getActiveSpreadsheet().getRangeByName('DISAGREE_GAP').getValue());
    if (v > 0) return v;
  } catch (e) { /* first build: the named range does not exist yet */ }
  return 15;
}

/** Conditional formats, in the order they must resolve. Banding is added last. */
function addDraftRules(sh, si, ki, activeCol, gap) {
  var rowsAll = sh.getRange(R0, 1, POOL_ROWS, D.notes);

  // MINE before GONE. First match wins, and the old order rendered a player who was both
  // as grey and struck through -- while the mine rule's explicit setStrikethrough(false)
  // showed that was not the intent.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + a1col(D.mine) + R0 + '=TRUE')
    .setBackground(COLOR.mineBg).setFontColor(COLOR.mineText).setStrikethrough(false)
    .setRanges([rowsAll]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$' + a1col(D.drafted) + R0 + '=TRUE')
    .setBackground(COLOR.drafted).setFontColor(COLOR.muted).setStrikethrough(true)
    .setRanges([rowsAll]).build());

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo('OUT')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(R0, D.inj, POOL_ROWS, 1)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('GTD')
    .setBackground(COLOR.warnBg).setFontColor(COLOR.warnText)
    .setRanges([sh.getRange(R0, D.inj, POOL_ROWS, 1)]).build());

  // A striped ruler down the left edge, marking round boundaries without drawing a second
  // family of horizontal lines across a board that already draws tier breaks.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ISODD($' + a1col(D.round) + R0 + ')')
    .setBackground('#EEF1F4')
    .setRanges([sh.getRange(R0, D.round, POOL_ROWS, 1)]).build());

  // Where the projections disagree. One rule per tag column with its own absolute
  // reference, never one rule over nine ranges: a multi-range rule relies on Sheets
  // offsetting a relative reference per range, which is exactly the behaviour the harness
  // cannot verify and which has already cost this board two board-wide failures.
  for (var s = 0; s < SOURCES.length; s++) {
    for (var k = 0; k < VALUE_KINDS.length; k++) {
      var rc = '$' + a1col(dRank(s, k)) + R0;
      var mine = '$' + a1col(D.rank) + R0;
      var tagRange = [sh.getRange(R0, dTag(s, k), POOL_ROWS, 1)];
      addRule(sh, SpreadsheetApp.newConditionalFormatRule()
        .whenFormulaSatisfied('=AND(' + rc + '<>"",' + mine + '-' + rc + '>=' + gap + ')')
        .setBackground(COLOR.posBg).setFontColor(COLOR.posText).setBold(true)
        .setRanges(tagRange).build());
      addRule(sh, SpreadsheetApp.newConditionalFormatRule()
        .whenFormulaSatisfied('=AND(' + rc + '<>"",' + rc + '-' + mine + '>=' + gap + ')')
        .setBackground(COLOR.negBg).setFontColor(COLOR.negText).setBold(true)
        .setRanges(tagRange).build());
    }
  }

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=AND($' + a1col(D.projGp) + R0 + '>=68,$'
                          + a1col(D.projGp) + R0 + '<=74)')
    .setBackground(COLOR.warnBg)
    .setRanges([sh.getRange(R0, D.projGp, POOL_ROWS, 1)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo('CHECK')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(R0, D.gpFlag, POOL_ROWS, 1)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo('BREAK')
    .setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(R0, D.brk, POOL_ROWS, 1)]).build());

  gradient(sh, [sh.getRange(R0, D.gap, POOL_ROWS, 1)], -40, 40);
  // The only gradient on the value block, on the column the board is sorted by.
  gradient(sh, [sh.getRange(R0, activeCol, POOL_ROWS, 1)], -1, 1);

  // Banding last, and NOT across the tag columns, the round ruler or the input columns --
  // those carry static fills that are their identity.
  var bands = [
    sh.getRange(R0, D.rank, POOL_ROWS, 2),
    sh.getRange(R0, D.player, POOL_ROWS, D.mine - D.player + 1)
  ];
  for (var s2 = 0; s2 < SOURCES.length; s2++) {
    for (var k2 = 0; k2 < VALUE_KINDS.length; k2++) {
      bands.push(sh.getRange(R0, dValue(s2, k2), POOL_ROWS, 1));
    }
  }
  bands.push(sh.getRange(R0, D.drop, POOL_ROWS, D.best - D.drop + 1));
  bands.push(sh.getRange(R0, D.strengths, POOL_ROWS, 1));
  bands.push(sh.getRange(R0, D.posLeft, POOL_ROWS, 1));
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=ISEVEN(ROW())')
    .setBackground(COLOR.band).setRanges(bands).build());
}

function formatSettings(sh) {
  sh.setColumnWidth(1, 200); sh.setColumnWidth(2, 110); sh.setColumnWidth(3, 100);
  sh.setColumnWidth(4, 100); sh.setColumnWidth(5, 110); sh.setColumnWidth(6, 120);
  sh.setColumnWidth(7, 180); sh.setColumnWidth(8, 90);

  [[S_LEAGUE, 1, 2], [S_TRACKER, 1, 6], [S_WINRATE, 1, 2], [S_POOLS, 1, 6],
   [S_SANITY, 1, 2], [S_WEIGHTS, 4, 2], [S_ROSENOF, 7, 2]].forEach(function (p) {
    sh.getRange(p[0], p[1], 1, p[2]).setBackground(COLOR.identity)
      .setFontColor(COLOR.headerText).setFontWeight('bold').setFontSize(9);
  });

  // Yellow means you may type here. Q is a formula, so it is deliberately not tinted.
  [S_LEAGUE + 1, S_LEAGUE + 2, S_LEAGUE + 4, S_LEAGUE + 5,
   S_LEAGUE + 6, S_LEAGUE + 7, S_LEAGUE + 8].forEach(function (r) {
    sh.getRange(r, 2).setBackground(COLOR.inputBg).setFontColor(COLOR.inputText);
  });
  sh.getRange(S_WINRATE + 1, 2, 3, 1)
    .setBackground(COLOR.inputBg).setFontColor(COLOR.inputText).setNumberFormat('0%');

  // Grey, NOT input-yellow. These record what the pipeline used; editing one does nothing,
  // and eight editable-looking numbers that no longer drive anything is how someone spends
  // an hour tuning a dead cell.
  sh.getRange(S_WEIGHTS + 1, 5, CAT_LABELS.length + 1, 1)
    .setBackground(COLOR.band).setFontColor(COLOR.muted).setNumberFormat('0.00');
  sh.getRange(S_ROSENOF + 1, 8, 9, 1)
    .setBackground(COLOR.band).setFontColor(COLOR.faint).setNumberFormat('0.00');
  sh.getRange(S_TRACKER + 2, 2, CAT_LABELS.length, 4)
    .setBackground(COLOR.band).setFontColor(COLOR.muted).setNumberFormat('0.000');
  sh.getRange(S_POOLS + 2, 2, SOURCES.length, 5)
    .setBackground(COLOR.band).setFontColor(COLOR.muted);

  sh.getRange(S_LEAGUE + 3, 2).setNumberFormat('0');
  sh.getRange(S_LEAGUE + 6, 2).setNumberFormat('0.0');
  sh.getRange(S_LEAGUE + 7, 2).setNumberFormat('0.00');
  sh.getRange(S_LEAGUE + 8, 2).setNumberFormat('0');
  sh.getRange(S_LEAGUE + 5, 2).setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(['Head-to-Head Categories', 'Head-to-Head One Win'], true).build());
  sh.getRange(S_LEAGUE + 4, 2).setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(allSortLabels(), true).build());

  [S_TRACKER + 1, S_POOLS + 1].forEach(function (r) {
    sh.getRange(r, 1, 1, 6).setFontWeight('bold').setBackground(COLOR.band);
  });

  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('MISALIGNED')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(S_SANITY + 1, 2), sh.getRange(S_SANITY + 2, 2)]).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('MIXED DATES')
    .setBackground(COLOR.flagBg).setFontColor(COLOR.flagText).setBold(true)
    .setRanges([sh.getRange(S_SANITY + 6, 2)]).build());

  sh.getRange('A2').setFontColor(COLOR.muted).setFontSize(9).setWrap(true);
  sh.getRange('A2:F2').merge();
  sh.setRowHeight(2, 44);
  sh.setHiddenGridlines(true);
}

// -------------------------------------------------------------------- Punts

function buildPuntsTab(sh) {
  var src = SOURCES[0];
  sh.getRange('A1').setValue('Punt builds — who each build gets at a discount')
    .setFontSize(14).setFontWeight('bold').setFontColor(COLOR.punt);
  sh.getRange('A2').setFormula(
    '=IF(SCORING="Head-to-Head One Win",'
    + '"One Win: the week resolves to a single result, so once you have won five categories '
    + 'a sixth adds nothing — punting pays. Aim to win six or seven, not exactly five.",'
    + '"Head-to-Head Categories: every category is settled separately every week, so '
    + 'abandoning three is expensive — soft-punt at most, and stay balanced.")')
    .setFontColor(COLOR.muted).setFontSize(10);
  sh.getRange('A3').setValue(
    'Computed on ' + src.label + ' · DURH. A build discounts its categories BEFORE '
    + 'standardising and re-derives the pool, so it moves the whole field rather than one '
    + 'column (ADR-0019). Sorted by Punt Gap = ADP − rank inside that build: a big positive '
    + 'number means the room prices him normally and this build values him far higher. '
    + 'Learn the top ten of each before draft day; a build rank is not a licence to reach.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(3, 1, 1, 12).merge();
  sh.setRowHeight(3, 34);

  var top = 40;
  for (var i = 0; i < PUNTS.length; i++) {
    var c0 = 1 + i * 6;
    var sc = a1col(V.p0 + i), rc = a1col(V.pr0 + i), adpc = a1col(V.adp), pc = a1col(V.player);

    blockHeader(sh, c0, c0 + 4, PUNTS[i].label.toUpperCase(), COLOR.punt, 4);
    sh.getRange(5, c0, 1, 5).setNumberFormat('@')
      .setValues([['#', 'Player', 'Score', 'ADP', 'GAP']])
      .setBackground(COLOR.punt).setFontColor(COLOR.headerText)
      .setFontWeight('bold').setFontSize(9).setHorizontalAlignment('center');

    // A player with no ADP is one the market has not priced -- a role change, a returning
    // injury, a rookie whose situation just moved. Those are exactly the names a build most
    // wants cheap, so they sort last on a sentinel rather than being filtered away, and
    // their Gap cell stays blank rather than zero.
    function col(letter) {
      return sheetRef(src.key) + '!$' + letter + '$' + R0 + ':$' + letter + '$' + RN;
    }
    var gapExpr = 'IF(' + col(adpc) + '="","",' + col(adpc) + '-' + col(rc) + ')';
    var sortKey = 'IF(' + col(adpc) + '="",-1E9,' + col(adpc) + '-' + col(rc) + ')';
    var arr = '{' + col(rc) + ',' + col(pc) + ',' + col(sc) + ','
            + col(adpc) + ',' + gapExpr + ',' + sortKey + '}';
    sh.getRange(6, c0).setFormula(
      '=ARRAY_CONSTRAIN(SORT(FILTER(' + arr + ',' + col(rc) + '<>""),6,FALSE),' + top + ',5)');

    sh.setColumnWidth(c0, 34); sh.setColumnWidth(c0 + 1, 150);
    sh.setColumnWidth(c0 + 2, 56); sh.setColumnWidth(c0 + 3, 48);
    sh.setColumnWidth(c0 + 4, 48); sh.setColumnWidth(c0 + 5, 18);

    sh.getRange(6, c0, top, 1).setNumberFormat('0');
    sh.getRange(6, c0 + 2, top, 1).setNumberFormat('+0.000;−0.000;0.000');
    sh.getRange(6, c0 + 3, top, 1).setNumberFormat('0.0');
    sh.getRange(6, c0 + 4, top, 1)
      .setNumberFormat('"▲ "+0;"▼ "−0;0').setFontWeight('bold');

    gradient(sh, [sh.getRange(6, c0 + 4, top, 1)], 0, 60, COLOR.mid, COLOR.mid, COLOR.good);
    addRule(sh, SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=ISEVEN(ROW())')
      .setBackground(COLOR.band)
      .setRanges([sh.getRange(6, c0, top, 5)]).build());
  }
  sh.setFrozenRows(5);
  sh.getRange(6, 1, top, PUNTS.length * 6).setFontSize(10);
  sh.setHiddenGridlines(true);
}

// -------------------------------------------------------- Category Tracker

var TRACK_PUNT_COL = 7;   // the Punted checkboxes; read by the Draft Board's profile

/**
 * How likely you are to win each category, given who you have ticked.
 *
 * Eight rows. Turnovers are absent because DURANT H2H weights them zero, so a DH turnover
 * column is identically 0.0 for every player -- a row that could only ever read EVEN is
 * worse than no row (ADR-0018).
 *
 *   Z_c  = ( sum of my DH values − n × the drafted mean ) / sqrt(n)
 *   Win% = NORMSDIST(Z_c × K_c),  K_c = k_c / w_c
 *
 * The sqrt(n) is what makes the scale hold at any roster size, and dividing by the weight
 * is what makes the published k apply to a weighted column. Both are in ADR-0018.
 *
 * No LET here, and no IF passed as an argument to another function, so neither of the two
 * array traps that have bitten this board applies. NORMSDIST has never been used in this
 * workbook before -- verify row 7 in the sheet before trusting the other seven.
 */
function buildTrackerTab(sh) {
  sh.getRange('A1').setValue('Category tracker')
    .setFontSize(14).setFontWeight('bold').setFontColor(COLOR.identity);
  sh.getRange('A2').setValue(
    'Win % is the chance of taking that category against an average opponent drawn from '
    + 'the players drafted so far. Spend the next pick on a CONTESTED row: the return on '
    + 'the next unit of edge peaks at a coin flip, so a nearly-lost category and a '
    + 'nearly-won one are both places to stop. Turnovers are absent by design — DURANT H2H '
    + 'prices them at zero, so the board cannot measure them.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange('A2:G2').merge();
  sh.setRowHeight(2, 46);

  var n = 'COUNTIF(DB_MINE,TRUE)';
  // Capped at Q. Uncapped, this reached rank 168 of a 156-player pool at fourteen ticks.
  var drafted = 'DB_RANK<=MIN(Q,TEAMS*' + n + ')';

  sh.getRange(4, 1).setValue('Players ticked');
  sh.getRange(4, 2).setFormula('=' + n);

  sh.getRange(6, 1, 1, 7).setValues(
    [['Category', 'My team', 'Average team', 'Z', 'Win %', 'Read', 'Punted']]);

  var rates = { 'FG%': ['DB_FGM', 'DB_FGA'], 'FT%': ['DB_FTM', 'DB_FTA'] };
  for (var i = 0; i < CAT_LABELS.length; i++) {
    var lab = CAT_LABELS[i], r = TRACKER_R0 + i;
    var dh = 'DB_DH_' + catKey(lab);
    var mine, bench, fmt;

    if (rates[lab]) {
      // Volume-weighted, never a mean of rates: makes over attempts on both sides.
      var mk = rates[lab][0], at = rates[lab][1];
      mine  = '=IF(' + n + '=0,"",SUMIF(DB_MINE,TRUE,' + mk + ')/SUMIF(DB_MINE,TRUE,' + at + '))';
      bench = '=IF(' + n + '=0,"",SUM(FILTER(' + mk + ',' + drafted + '))'
            + '/SUM(FILTER(' + at + ',' + drafted + ')))';
      fmt = '0.000';
    } else {
      var raw = 'DB_' + catKey(lab);
      mine  = '=IF(' + n + '=0,"",SUMIF(DB_MINE,TRUE,' + raw + '))';
      bench = '=IF(' + n + '=0,"",AVERAGE(FILTER(' + raw + ',' + drafted + '))*' + n + ')';
      fmt = '0.0';
    }

    sh.getRange(r, 1).setValue(lab);
    sh.getRange(r, 2).setFormula(mine).setNumberFormat(fmt);
    sh.getRange(r, 3).setFormula(bench).setNumberFormat(fmt);
    sh.getRange(r, 4).setFormula(
      '=IF(' + n + '=0,"",(SUMIF(DB_MINE,TRUE,' + dh + ')-' + n
      + '*AVERAGE(FILTER(' + dh + ',' + drafted + ')))/SQRT(' + n + '))')
      .setNumberFormat('+0.00;−0.00;0.00');
    sh.getRange(r, 5).setFormula(
      '=IF($D' + r + '="","",NORMSDIST($D' + r + '*K_' + catKey(lab) + '))')
      .setNumberFormat('0%');
    // The glyph is the non-colour channel: the state survives greyscale, printing and any
    // colour vision. BANKED and PUNTED render identically because both mean "stop here".
    sh.getRange(r, 6).setFormula(
      '=IF($G' + r + '=TRUE,"— PUNTED",IF($E' + r + '="","",'
      + 'IF($E' + r + '>=BANK_WIN,"■ BANKED",IF($E' + r + '>=STRONG_WIN,"▲ STRONG",'
      + 'IF($E' + r + '<=WEAK_WIN,"▼ WEAK","● CONTESTED")))))');
  }

  // These MUST stay literal checkboxes. The Draft Board's profile columns read them and
  // this tab reads the Draft Board back -- safe only while nothing here is a formula.
  // Make Punted auto-detect a build and that closes a real circular reference.
  sh.getRange(TRACKER_R0, TRACK_PUNT_COL, CAT_LABELS.length, 1).insertCheckboxes();

  var last = TRACKER_R0 + CAT_LABELS.length;
  sh.getRange(last + 1, 1).setValue(
    'Tick Punted to concede a category: it stops counting toward what you still need, and '
    + 'it drops out of the Draft Board\'s Strengths and Weaknesses columns too.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(last + 1, 1, 1, 7).merge();
  sh.setRowHeight(last + 1, 30);

  sh.getRange(last + 2, 1).setValue(
    'When a row reads WEAK or CONTESTED, the Draft Board\'s ▲ Strengths column is where you '
    + 'fix it. The two measure different things on purpose: this tab compares you to the '
    + 'managers drafting alongside you, so its benchmark moves every round, while that '
    + 'column compares a player to the whole pool and never moves. Early on this can read '
    + 'REB 68% while few players show ▲ REB. Both are right.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(last + 2, 1, 1, 7).merge();
  sh.setRowHeight(last + 2, 44);

  // Raw totals and Z can point in OPPOSITE directions, and blocks is where it shows.
  // Trust the Z: it is what the board ranks on, and it is the quantity the win
  // probability is derived from.
  sh.getRange(last + 3, 1).setValue(
    'My team and Average team are raw per-game totals; Z and Win % are the DURANT H2H '
    + 'values. They can disagree in DIRECTION, and blocks is where you will see it — a '
    + 'roster can sit below the average team\'s raw blocks and still show a positive Z. '
    + 'That is the transform doing its job: blocks are compressed hardest, so a handful of '
    + 'elite shot blockers no longer drag "average" up out of reach. The Z is the number '
    + 'the board ranks on, and the one the Win % comes from.')
    .setFontSize(9).setFontColor(COLOR.muted).setWrap(true);
  sh.getRange(last + 3, 1, 1, 7).merge();
  sh.setRowHeight(last + 3, 44);

  sh.getRange(last + 5, 1).setValue('MY ROSTER').setFontWeight('bold')
    .setBackground(COLOR.identity).setFontColor(COLOR.headerText);
  sh.getRange(last + 5, 1, 1, 3).merge();
  sh.getRange(last + 6, 1, 1, 3).setValues([['#', 'Player', 'Pos']])
    .setFontWeight('bold').setBackground(COLOR.band);
  sh.getRange(last + 7, 1).setFormula(
    '=IFERROR(SORT(FILTER({DB_RANK,DB_PLAYER,DB_POS},DB_MINE=TRUE),1,TRUE),'
    + '"Nothing ticked yet")');

  formatTracker(sh);
}

function formatTracker(sh) {
  var rows = CAT_LABELS.length, r0 = TRACKER_R0;
  sh.setColumnWidth(1, 100); sh.setColumnWidth(2, 96); sh.setColumnWidth(3, 106);
  sh.setColumnWidth(4, 64); sh.setColumnWidth(5, 74); sh.setColumnWidth(6, 118);
  sh.setColumnWidth(7, 64);

  sh.getRange(6, 1, 1, 7).setFontWeight('bold').setBackground(COLOR.identity)
    .setFontColor(COLOR.headerText).setFontSize(9);
  sh.getRange(r0, 1, rows, 7).setFontSize(10).setVerticalAlignment('middle');
  sh.getRange(r0, 1, rows, 1).setFontSize(11).setFontWeight('bold');
  sh.getRange(r0, 3, rows, 1).setFontColor(COLOR.muted);
  sh.getRange(r0, 4, rows, 1).setFontColor(COLOR.muted);
  // The largest type on the tab: the only number here that is directly actionable.
  sh.getRange(r0, 5, rows, 1).setFontSize(13).setFontWeight('bold')
    .setHorizontalAlignment('center');
  sh.getRange(r0, 6, rows, 1).setFontSize(11).setFontWeight('bold');

  var verdict = [sh.getRange(r0, 5, rows, 2)];
  var whole = [sh.getRange(r0, 1, rows, 6)];

  // Order matters. A conceded or banked category goes quiet everywhere FIRST, including
  // its numbers; only then do the live states paint.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$G' + r0 + '=TRUE')
    .setFontColor(COLOR.muted).setItalic(true).setBold(false)
    .setRanges(whole).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied('=$F' + r0 + '="■ BANKED"')
    .setFontColor(COLOR.muted).setItalic(true).setBold(false)
    .setRanges(whole).build());
  // CONTESTED is the only saturated fill on the tab, because it is the only state that
  // says "spend the next pick here".
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('CONTESTED')
    .setBackground('#FFE9A8').setFontColor('#6B4E00').setBold(true)
    .setRanges(verdict).build());
  // WEAK keeps red bold text but loses the red block it used to carry: a nearly-lost
  // category is not where the next pick goes, and a red block there competes with the
  // state that is.
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('WEAK')
    .setFontColor(COLOR.flagText).setBold(true)
    .setRanges(verdict).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('STRONG')
    .setFontColor(COLOR.mineText).setBold(true)
    .setRanges(verdict).build());
  addRule(sh, SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('CONTESTED')
    .setBackground('#FFFBF0')
    .setRanges([sh.getRange(r0, 1, rows, 4)]).build());

  sh.setHiddenGridlines(true);
}

// ------------------------------------------------------------------ README

var README_SECTIONS = [
  'HOW TO USE IT',
  'THE TWO THINGS THAT ARE NOT AUTOMATIC',
  'COLOURS',
  'CHEAT SHEET — WHAT EVERY NUMBER ON THIS SHEET MEANS',
  'THINGS WORTH KNOWING'
];
var README_STEPS = [
  'THE THREE PROJECTIONS — what the board is measured against',
  'THE THREE VALUES — and what each one throws away',
  'SORTING AND FILTERING',
  'RANKS, ROUNDS AND TIERS',
  'THE MARKET',
  'PUNT BUILDS',
  'STRENGTHS AND WEAKNESSES',
  'THE CATEGORY TRACKER'
];

function readmeRowOf(L, label) {
  for (var i = 0; i < L.length; i++) if (L[i][0] === label) return i + 1;
  return 0;
}

/**
 * The README tab's content, hoisted so export_readme.js can generate the markdown copy in
 * docs/ from the same source the sheet uses.
 * [name, formula, what it actually means]. Formulas lead with a space so Sheets stores
 * them as text rather than trying to evaluate them.
 */
var README_ROWS = [
  ['9-Cat H2H Draft Board — 2026-27', '', ''],
  ['Values are computed by scripts/draft-board/build_data.py and arrive here as numbers. '
   + 'Ranks, tiers, rounds and the tracker are live formulas — click any of those and read them.', '', ''],
  ['', '', ''],

  ['HOW TO USE IT', '', ''],
  ['Before the draft', '',
   'Pick your sort in the dropdown at the top left, run Draft Board ▸ Rebuild & re-sort, '
   + 'and read down. Learn the top ten of each punt build.'],
  ['On the clock', '',
   'Tick GONE as players come off the board — for everyone, not just you. Tick MINE for '
   + 'your own picks. Both live in the frozen pane so they never scroll away.'],
  ['After each pick', '',
   'Read the Category Tracker. Spend the next pick on a CONTESTED row, not a STRONG one.'],
  ['', '', ''],

  ['THE TWO THINGS THAT ARE NOT AUTOMATIC', '', ''],
  ['GONE', '',
   'Nobody else is ticking it for you. Left @pos and the tracker benchmark are both wrong '
   + 'if it is not kept up.'],
  ['Sort by', '',
   'Changing the dropdown does NOT re-sort the board on its own. Run Rebuild & re-sort. '
   + 'Until you do, the block header says SORT STALE.'],
  ['', '', ''],

  ['COLOURS', '', ''],
  ['Pale yellow + blue text', '', 'You type here.'],
  ['Grey', '', 'Reported by the pipeline. Editing it changes nothing.'],
  ['Amber GP cell', '',
   'Projected GP is inside 68–74, the band where the projection is applying a generic '
   + 'haircut rather than a player-level opinion.'],
  ['Cream value column', '', 'The value the board is currently sorted by.'],
  ['Green or red tag', '',
   'That projection ranks him at least DISAGREE_GAP places away from where the board does. '
   + 'Green means it likes him more. These are the rows worth slowing down on.'],
  ['Thick horizontal line', '', 'A tier break.'],
  ['▲ / ▼ on GAP', '',
   'Positive means the room drafts him later than the board ranks him — he is cheap.'],
  ['', '', ''],

  ['CHEAT SHEET — WHAT EVERY NUMBER ON THIS SHEET MEANS', '', ''],

  ['THE THREE PROJECTIONS — what the board is measured against', '', ''],
  ['BMP', '', 'Basketball Monster, Josh\'s projections. The default.'],
  ['HBP', '', 'Hashtag Basketball. Supplies the 200 rows, the team, the position and the ADP.'],
  ['BMP-ALT', '', 'Basketball Monster\'s second source.'],
  ['Why three', '',
   'Identical math over two projection sets moves players about twenty rank places on '
   + 'average. Choosing the projection matters more than choosing the valuation, so the '
   + 'board shows the disagreement instead of hiding it in an average.'],
  ['The pool', '',
   'Q = Teams × Roster spots = 156. Each source is scored against its own universe, '
   + 'because a value is a property of the pair (stat line, pool).'],
  ['', '', ''],

  ['THE THREE VALUES — and what each one throws away', '', ''],
  ['DURH', ' DURANT H2H',
   'Basketball Monster\'s head-to-head value, and what this league should draft from. '
   + 'Each category is transformed, standardised, weighted, then the worst surviving '
   + 'category is dropped and the remaining seven averaged. Turnovers are weighted zero.'],
  ['ZSH', ' weighted z, minus one',
   'The same weighting and the same drop, on untransformed z. It exists to isolate what '
   + 'the transform is worth: any disagreement with DURH is the transform\'s doing.'],
  ['ZSC', ' plain z',
   'Nine z-scores averaged, turnovers inverted, nothing dropped. The industry baseline.'],
  ['Not comparable', '',
   'ZSC averages nine and the other two average seven. Compare RANKS across values, never '
   + 'magnitudes.'],
  ['The tag beside each value', '',
   'That value\'s rank, and the category it dropped. "#4 REB" means fourth best, having '
   + 'discarded his rebounding.'],
  ['', '', ''],

  ['SORTING AND FILTERING', '', ''],
  ['Sort by', '',
   'Nine choices: three projections × three values. Everything downstream — rank, tier, '
   + 'round, GAP, the tracker — follows it.'],
  ['Projection checkboxes', '',
   'Untick one to hide its six columns. All three at once is a comparison view, not a '
   + 'draft-day view; it fills the screen.'],
  ['', '', ''],

  ['RANKS, ROUNDS AND TIERS', '', ''],
  ['#', ' =RANK(sorted value)',
   'Rank by whatever you are sorted by. Correct the moment you change the dropdown, even '
   + 'before the rows move.'],
  ['RND', ' =CEILING(#/Teams)', 'Which round that rank falls in. Reads league size, nothing more.'],
  ['Drop', '', 'The value above this row, minus this one.'],
  ['Local med', '', 'The median of the fifteen drops centred here.'],
  ['Break', ' Drop > 2 × local median', 'A cliff, relative to what is normal nearby.'],
  ['TIER', '', 'A running count of the breaks above.'],
  ['', '', ''],

  ['THE MARKET', '', ''],
  ['ADP', '', 'Where the room actually drafts him. Hashtag\'s aggregate, not Yahoo\'s.'],
  ['GAP', ' = ADP − #',
   'Positive means cheap. Blank ADP means the market has not priced him, which is not the '
   + 'same as pricing him last.'],
  ['XRank', '', 'Yours to fill in, if you want a second market opinion.'],
  ['', '', ''],

  ['PUNT BUILDS', '', ''],
  ['Best build', '',
   'The build that ranks him highest, and by how many places. "AST+STL +21" means '
   + 'twenty-one places better in that build than on the main board.'],
  ['How a build is computed', '',
   'The punted categories are discounted BEFORE standardising, and the pool is re-derived. '
   + 'A punt moves the whole field, not one column.'],
  ['Punt weight', '',
   '0.25 — a conceded category is still won by accident some weeks, and those weeks are free.'],
  ['', '', ''],

  ['STRENGTHS AND WEAKNESSES', '', ''],
  ['▲ Strengths / ▼ Weaknesses', '',
   'Every category where his DURANT value clears ±1.00. A descriptor, not a second '
   + 'valuation: the value column already prices him, this says what for.'],
  ['Why unweighted', '',
   'A weighted column\'s spread IS its weight, so one band would be unreachable for the '
   + 'five categories weighted below 1. Unweighted, one band serves all eight.'],
  ['Punted categories', '', 'Drop out of both columns, on all 200 rows.'],
  ['', '', ''],

  ['THE CATEGORY TRACKER', '', ''],
  ['Win %', ' = NORMSDIST(Z × K)',
   'The chance of winning that category against an average opponent drawn from the players '
   + 'drafted so far.'],
  ['Z', '', 'Your roster\'s edge in that category, in standard deviations, scaled by √n.'],
  ['The five reads', '',
   'WEAK ≤35%. CONTESTED — spend the next pick here. STRONG ≥65%. BANKED ≥75%, stop '
   + 'looking. PUNTED, conceded on purpose.'],
  ['No turnovers row', '',
   'DURANT H2H weights turnovers zero, so the board cannot measure them. They are still on '
   + 'the Board tab as a raw number.'],
  ['', '', ''],

  ['THINGS WORTH KNOWING', '', ''],
  ['Nothing scales by games played', '',
   'Availability is the least predictable part of any projection, and Basketball Monster\'s '
   + 'method has no availability term at all. The GP columns are context for a judgement '
   + 'call, not a multiplier.'],
  ['Changing a constant does not recalculate', '',
   'Weights, lambdas and the punt weight are applied in the pipeline. Edit those and re-run '
   + 'build_data.py; the grey cells on Settings only record what was used.'],
  ['Left @pos', '',
   'How many un-GONE players in his tier could fill a slot he is eligible for. The one '
   + 'column that needs everyone\'s picks ticked.'],
  ['MPG', '', 'Carried for context and deliberately not valued — a per-game projection already is the minutes.']
];

function buildReadme(sh) {
  var rows = [];
  for (var i = 0; i < README_ROWS.length; i++) rows.push(README_ROWS[i].slice(0, 3));
  sh.getRange(1, 1, rows.length, 3).setNumberFormat('@').setValues(rows);

  sh.setColumnWidth(1, 250); sh.setColumnWidth(2, 230); sh.setColumnWidth(3, 620);
  sh.getRange(1, 1, rows.length, 3).setVerticalAlignment('top').setWrap(true).setFontSize(10);
  sh.getRange(1, 1).setFontSize(16).setFontWeight('bold').setFontColor(COLOR.identity);
  sh.getRange(2, 1, 1, 3).merge();
  sh.getRange(2, 1).setFontSize(10).setFontColor(COLOR.muted);
  sh.getRange(1, 2, rows.length, 1).setFontFamily('Roboto Mono').setFontColor(COLOR.z);

  var all = README_SECTIONS.concat(README_STEPS);
  for (var s = 0; s < all.length; s++) {
    var r = readmeRowOf(README_ROWS, all[s]);
    if (!r) continue;
    var isSection = README_SECTIONS.indexOf(all[s]) >= 0;
    sh.getRange(r, 1, 1, 3).merge();
    sh.getRange(r, 1)
      .setBackground(isSection ? COLOR.identity : COLOR.z)
      .setFontColor(COLOR.headerText).setFontWeight('bold')
      .setFontSize(isSection ? 11 : 10);
  }
  sh.setFrozenRows(1);
  sh.setHiddenGridlines(true);
}

// ------------------------------------------------------- menu and triggers

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Draft Board')
    .addItem('Refresh data (new export, keeps your edits)', 'refreshData')
    .addSeparator()
    .addItem('Rebuild & re-sort', 'rebuildAndResort')
    .addItem('Apply projection filter', 'applyProjectionFilter')
    .addSeparator()
    .addItem('Full rebuild (from Data.gs)', 'buildDraftBoard')
    .addSeparator()
    .addItem('Step 1 — Settings only', 'step1_Settings')
    .addItem('Step 2 — Calculation tabs', 'step2_Calc')
    .addItem('Step 3 — Board (spine)', 'step3_Board')
    .addItem('Step 4 — Draft Board only', 'step4_DraftBoard')
    .addItem('Step 5 — Punts, Tracker, README', 'step5_Rest')
    .addToUi();
}

/** Re-sort to whatever the dropdown says, keeping GONE / MINE / Notes / Injuries. */
function rebuildAndResort() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Re-sort', function () {
    var sel = selectedSort(ss);
    buildDraftTab(ss, ss.getSheetByName('Draft Board'), ss.getSheetByName('Board'));
    ss.toast('Sorted by ' + sortLabel(sel[0], sel[1]), 'Draft Board', 8);
  });
}

/**
 * Show or hide each projection's six value columns from the header checkboxes.
 *
 * A simple onEdit, not an installable trigger: hiding a column needs no authorisation, so
 * this requires no install step, survives a rebuild, and cannot silently fail to exist.
 *
 * It runs on EVERY edit, including each of the ~156 checkbox ticks during a draft, so the
 * range check comes first and returns before doing anything else. A failure here must
 * never surface as an error on someone's edit -- the worst case is a dead checkbox, and
 * the menu item does the same job by hand.
 */
function onEdit(e) {
  try {
    if (!e || !e.range) return;
    if (e.range.getRow() !== 1) return;
    var sh = e.range.getSheet();
    if (sh.getName() !== 'Draft Board') return;
    var col = e.range.getColumn();
    // The sort dropdown on the control strip writes through to SORT_BY, which is what
    // every build actually reads. Without this the control was decorative: it carried a
    // dropdown, the cheat sheet pointed at it, picking a value changed the label -- and
    // Rebuild & re-sort went on sorting by whatever Settings said. A control that
    // silently does nothing is worse than no control, because you believe it.
    if (col === D.drafted) {
      var picked = String(e.range.getValue() || '');
      for (var s = 0; s < SOURCES.length; s++) {
        for (var k = 0; k < VALUE_KINDS.length; k++) {
          if (picked !== sortLabel(s, k)) continue;
          sh.getParent().getRangeByName('SORT_BY').setValue(picked);
          sh.getParent().toast('Sort set to ' + picked + '. Run Draft Board ▸ Rebuild & '
                             + 're-sort to apply it.', 'Draft Board', 8);
          return;
        }
      }
      return;
    }
    for (var i = 0; i < SOURCES.length; i++) {
      if (col !== 1 + i * 2) continue;
      setProjectionVisible(sh, i, e.range.getValue() === true);
      return;
    }
  } catch (err) { /* never throw into a user's edit */ }
}

function setProjectionVisible(sh, si, visible) {
  var c0 = dSpanStart(si);
  if (visible) sh.showColumns(c0, SPAN); else sh.hideColumns(c0, SPAN);
}

/** The same job as onEdit, run by hand. Also the repair path if a checkbox drifts. */
function applyProjectionFilter() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  _guard('Filter', function () {
    var sh = ss.getSheetByName('Draft Board');
    for (var i = 0; i < SOURCES.length; i++) {
      setProjectionVisible(sh, i, sh.getRange(1, 1 + i * 2).getValue() === true);
    }
  });
}
