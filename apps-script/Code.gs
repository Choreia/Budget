/**
 * Choreia 予算 — 書き込み役
 *
 * スプレッドシートを誰にも共有せずに運用するための仕組みです。
 * このスクリプトは経理（設置した人）の権限で動きます。
 * 記入する人はスプレッドシートの権限を一切持たないまま、アプリから記入できます。
 *
 * 置き方は README.md の「書き込み役を置く」を見てください。
 *
 * デプロイの設定は必ずこの2つにしてください。
 *   次のユーザーとして実行 … 自分
 *   アクセスできるユーザー … 全員
 *
 * 「全員」にするのは、ブラウザからの呼び出しに Google のログイン情報が付かないためです。
 * 「組織内の全員」にすると、アプリにはログイン画面が返ってきて動きません。
 * 誰でも書けるわけではありません。呼ばれるたびに下の whoIsCalling で本人を確かめ、
 * ALLOWED_DOMAIN 以外の人は何もできずに終わります。
 */

/* このドメインの人だけ使えます。空にすると誰でも使えてしまうので必ず入れてください。 */
var ALLOWED_DOMAIN = 'm2-labo.jp';

/* 読み書きするスプレッドシート。
   空なら、このスクリプトが貼り付けられているスプレッドシートを使います。
   別のスプレッドシートに移すときは、ここにIDを入れてデプロイし直してください。 */
var SPREADSHEET_ID = '';

/* 設定ファイルを読めないときの保険。ここに書いた人は必ず管理者です。 */
var FALLBACK_ADMINS = ['r.yasukouchi@m2-labo.jp'];

var SHEETS = {
  '購入': ['id','記入日時','記入者メール','記入者','状態','種別','部門','発注日','項目','品名','購入理由','購入先',
           'インボイスNo','税抜','GST率','税込','TDS率','TDS額','支払額','HSNコード',
           '納品先','支払方法','立替区分','事業','検収日','納品予定日',
           '支払期限','支払日','返金日','原本郵送','備考','証憑フォルダ',
           '見積書','発注書','納品書','請求書','領収書','振込証憑','その他',
           '目的','勘定科目',
           'チェック者','チェック日時','社長承認者','社長承認日時','差戻理由','更新日時','更新者'],
  '入金': ['id','記入日時','記入者','部門','種別','項目','証憑','税込','税抜','振込期日','入金確認日','確認者','売掛入力','備考','記入者メール'],
  'マスタ': ['リスト','値','有効','並び','使用回数','最終使用'],
  '人': ['メール','名前','ロール','部門','上長メール'],
  '按分': ['id','キーワード','分け方','部門','重み','有効','更新者','更新日時','対象'],
  '履歴': ['日時','操作者','操作','対象','変更前','変更後'],
  '仕訳ルール': ['科目','目的','部門区分','勘定科目','有効','備考']
};

var SEED = {
  '部門': ['D-base','M2共通','SVL','ハード(製造原価)','事業企画(デザイン)','和泉市アグリセンター','協力隊','その他'],
  '項目': ['物品購入費','賃借料','水道光熱費','リース費','通信費','事務用品費','支払手数料','旅費交通費',
          '外注費','開発費','広告宣伝費','荷造運賃費','車両費','保険料','謝金','接待交際費','新聞図書費','その他経費'],
  '支払方法': ['銀行振込','M2クレカ','口座振替','立替','海外送金','現金払い'],
  '事業': ['なし','スマ農R7','菊川市R7','鹿児島衛星R7','牧之原市協力隊','KAGOME','JICA','GS-India'],
  '入金部門': ['【AT】アグリテック','和泉市アグリセンター','協力隊','その他']
};

/* ==================== 入口 ==================== */
function doPost(e) {
  try {
    var req = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    var email = whoIsCalling(req.token);
    if (!email) return json({ error: 'ログインを確認できませんでした。もう一度ログインしてください。' });

    var me = lookupPerson(email);
    switch (req.action) {
      case 'ping':   return json({ ok: true, email: email, role: me.role, depts: me.depts,
                                  spreadsheetId: book().getId(), spreadsheetName: book().getName() });
      case 'ensure': return json(doEnsure(me));
      case 'read':   return json(doRead(me, req.sheets));
      case 'newid':  return json({ ok: true, id: reserveId(req.prefix, numberedSheet(req.sheet)) });
      case 'append': return json(doAppend(me, req.sheet, req.row, req.prefix));
      case 'update': return json(doUpdate(me, req.sheet, req.row, req.rowIndex, req.matchId));
      default:       return json({ error: '知らない操作です: ' + req.action });
    }
  } catch (err) {
    return json({ error: String(err && err.message || err) });
  }
}
function doGet() {
  return HtmlService.createHtmlOutput(
    '<p>Choreia 予算の書き込み役です。このURLをアプリの設定に貼ってください。</p>');
}
function json(o) {
  return ContentService.createTextOutput(JSON.stringify(o))
    .setMimeType(ContentService.MimeType.JSON);
}

/* ==================== 誰が呼んでいるか ==================== */
/* アプリが持っているログインの引換券をGoogleに問い合わせて、本人を確かめます。 */
function whoIsCalling(token) {
  if (!token) return null;
  var cache = CacheService.getScriptCache();
  var key = 'tok_' + Utilities.base64Encode(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(token)));
  var hit = cache.get(key);
  if (hit) return hit;

  var res = UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/about?fields=user', {
    headers: { Authorization: 'Bearer ' + token },
    muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 200) return null;
  var user = JSON.parse(res.getContentText()).user || {};
  var email = String(user.emailAddress || '').toLowerCase();
  if (!email) return null;
  if (ALLOWED_DOMAIN && email.split('@')[1] !== ALLOWED_DOMAIN) return null;

  cache.put(key, email, 300);
  return email;
}

function lookupPerson(email) {
  var rows = readRows('人');
  var hit = null;
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i]['メール'] || '').toLowerCase() === email) { hit = rows[i]; break; }
  }
  var role = hit ? (hit['ロール'] || 'user') : 'user';
  if (FALLBACK_ADMINS.indexOf(email) >= 0) role = 'acc';
  if (!hit) {
    // はじめての人はここで登録する。最初のひとりは経理。
    var first = rows.length === 0;
    appendRaw('人', { 'メール': email, '名前': email.split('@')[0], 'ロール': first ? 'acc' : role,
                      '部門': '', '上長メール': '' });
    if (first) role = 'acc';
  }
  return {
    email: email,
    name: hit ? (hit['名前'] || email) : email.split('@')[0],
    role: role,
    depts: deptsOf(hit && hit['部門'])
  };
}
/* 部署の書き方。読点・カンマで区切れば複数。 */
function deptsOf(s) { return String(s || '').split(/[,、，]/).map(trim).filter(nonEmpty); }
/* メール → その人の部署（人とロールの「部門」欄） */
function personDepts() {
  var m = {};
  readRows('人').forEach(function (u) {
    var e = String(u['メール'] || '').toLowerCase();
    if (e && u['ロール'] !== 'off') m[e] = deptsOf(u['部門']);
  });
  return m;
}
/* 承認者が見る・チェックする記入か。
   記入した人の部署が担当部署に入っている（名波さんの考え方＝同じ部署の人の記入をチェックする）か、
   記入の費用負担部門が担当部署に入っていれば当たる。自分の記入は当たらない（自分で自分を承認しない）。 */
function inCharge(me, entry, pd) {
  if (!me.depts.length) return false;
  var who = String(entry['記入者メール'] || '').toLowerCase();
  if (who === me.email) return false;
  if (me.depts.indexOf(String(entry['部門'] || '')) >= 0) return true;
  return (pd[who] || []).some(function (d) { return me.depts.indexOf(d) >= 0; });
}
function trim(s) { return String(s).trim(); }
function nonEmpty(s) { return !!s; }

/* ==================== シートの読み書き ==================== */
function book() {
  return SPREADSHEET_ID ? SpreadsheetApp.openById(SPREADSHEET_ID) : SpreadsheetApp.getActive();
}
function sheetOf(name) {
  var ss = book();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, SHEETS[name].length).setValues([SHEETS[name]]);
  }
  return sh;
}
function headOf(name) {
  var sh = sheetOf(name);
  var last = sh.getLastColumn();
  if (last < 1) {
    sh.getRange(1, 1, 1, SHEETS[name].length).setValues([SHEETS[name]]);
    return SHEETS[name].slice();
  }
  var head = sh.getRange(1, 1, 1, last).getValues()[0].map(String);
  while (head.length && !head[head.length - 1]) head.pop();
  if (!head.length) {
    sh.getRange(1, 1, 1, SHEETS[name].length).setValues([SHEETS[name]]);
    return SHEETS[name].slice();
  }
  return head;
}
function readValues(name) {
  var sh = sheetOf(name);
  var rows = sh.getLastRow(), cols = sh.getLastColumn();
  if (rows < 1 || cols < 1) return [];
  return sh.getRange(1, 1, rows, cols).getDisplayValues();
}
function readRows(name) {
  var v = readValues(name);
  if (!v.length) return [];
  var head = v[0], out = [];
  for (var i = 1; i < v.length; i++) {
    if (!v[i].join('')) continue;
    var o = { _row: i + 1 };
    for (var j = 0; j < head.length; j++) o[head[j]] = v[i][j];
    out.push(o);
  }
  return out;
}
function appendRaw(name, obj) {
  var sh = sheetOf(name), head = headOf(name);
  var arr = head.map(function (h) { return obj[h] !== undefined && obj[h] !== null ? obj[h] : ''; });
  sh.appendRow(arr);
  return sh.getLastRow();
}

/* ==================== 操作 ==================== */
/* 同じ名前の別物のタブに書き込まないための確認。
   もともと別の用途で使われているタブを、このアプリが上書きしてしまわないようにします。 */
function looksLikeOurs(name, head) {
  return head.length > 0 && head[0] === SHEETS[name][0];
}
function doEnsure(me) {
  // 誰が呼んでも通します。足りない列を足して、マスタが空なら初期値を入れるだけで、
  // 既にあるデータには触りません。ここで止めると、新しく入った人がアプリを開けなくなります。
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var conflicts = [];
    for (var name in SHEETS) {
      var ss = book();
      var exists = ss.getSheetByName(name);
      if (exists && exists.getLastRow() > 0) {
        var h0 = headOf(name);
        if (!looksLikeOurs(name, h0)) { conflicts.push(name); continue; }
      }
      var sh = sheetOf(name);
      var head = headOf(name);
      var add = SHEETS[name].filter(function (h) { return head.indexOf(h) < 0; });
      if (add.length) {
        var merged = head.concat(add);
        sh.getRange(1, 1, 1, merged.length).setValues([merged]);
      }
    }
    if (conflicts.length) {
      return { error: 'このスプレッドシートには、同じ名前で別の用途に使われているタブがあります（' +
        conflicts.join('、') + '）。中身を壊さないよう、何もしていません。' +
        'このアプリ専用のスプレッドシートを新しく作って、そちらにつないでください。' };
    }
    // マスタが空なら初期値を入れる
    var m = sheetOf('マスタ');
    if (m.getLastRow() < 2) {
      var rows = [], i = 0;
      for (var list in SEED) {
        SEED[list].forEach(function (v) { rows.push([list, v, 'TRUE', String(++i), '0', '']); });
      }
      m.getRange(2, 1, rows.length, 6).setValues(rows);
    }
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function doRead(me, names) {
  names = names || Object.keys(SHEETS);
  var out = {};
  names.forEach(function (name) {
    if (!SHEETS[name]) return;
    if (name === '履歴' && me.role !== 'acc') return;
    var v = readValues(name);
    // 一般ユーザに他人の購入は渡さない。画面で隠すのではなく、そもそも送らない。
    // 入金予定は全員に見せる（名波さん 2026-09-30「危機意識を持たせるため、みんなの分が見えてよい」）。
    if (me.role === 'user' && name === '購入') {
      v = filterOwn(v, name, me);
    } else if (me.role === 'mgr' && name === '購入') {
      v = filterDept(v, me);
    }
    out[name] = v;
  });
  return { values: out };
}
function filterOwn(v, name, me) {
  if (!v.length) return v;
  var head = v[0];
  var col = head.indexOf(name === '購入' ? '記入者メール' : '記入者');
  if (col < 0) return [head];
  var keep = [head];
  for (var i = 1; i < v.length; i++) {
    if (String(v[i][col] || '').toLowerCase() === me.email) keep.push(v[i]);
    else keep.push(blankRow(head.length, i));
  }
  return keep;
}
function filterDept(v, me) {
  if (!v.length) return v;
  var head = v[0];
  var dc = head.indexOf('部門'), ec = head.indexOf('記入者メール');
  var pd = personDepts();
  var keep = [head];
  for (var i = 1; i < v.length; i++) {
    var entry = { '部門': dc >= 0 ? v[i][dc] : '', '記入者メール': ec >= 0 ? v[i][ec] : '' };
    // 担当部署が空の承認者は、自分の記入だけ（以前は全員分が見えてしまっていた）
    var ok = String(entry['記入者メール'] || '').toLowerCase() === me.email || inCharge(me, entry, pd);
    keep.push(ok ? v[i] : blankRow(head.length, i));
  }
  return keep;
}
/* 行番号がずれないように、隠す行は空で埋める */
function blankRow(n) {
  var a = []; for (var i = 0; i < n; i++) a.push('');
  return a;
}

function doAppend(me, name, row, prefix) {
  if (!SHEETS[name]) return { error: '知らないシートです' };
  var guard = canWrite(me, name, row, null);
  if (guard) return { error: guard };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (name === '購入') {
      row['記入者メール'] = me.email;
      row['記入者'] = row['記入者'] || me.name;
      // 番号はここで最終確認する。空のとき、もう使われているときは取り直す。
      if (!row['id'] || idExists(row['id'], '購入')) {
        row['id'] = reserveId(prefix || String(row['id'] || '').replace(/\d+$/, ''), '購入');
      }
    }
    if (name === '入金') row['記入者メール'] = me.email;
    if (name === '入金' && (!row['id'] || idExists(row['id'], '入金'))) {
      row['id'] = reserveId(prefix || String(row['id'] || '').replace(/\d+$/, ''), '入金');
    }
    var r = appendRaw(name, row);
    logIt(me, '追加', name + ' ' + (row['id'] || row['値'] || ''), '', String(row['品名'] || row['項目'] || ''));
    return { ok: true, row: r, id: row['id'] || '' };
  } finally {
    lock.releaseLock();
  }
}

/* 番号でその行を探す。見つからなければ 0。 */
function findRowById(name, id) {
  var rows = readValues(name);
  if (!rows.length) return 0;
  var c = rows[0].indexOf('id');
  if (c < 0) return 0;
  for (var i = 1; i < rows.length; i++) if (String(rows[i][c] || '') === String(id)) return i + 1;
  return 0;
}
function doUpdate(me, name, row, rowIndex, matchId) {
  if (!SHEETS[name]) return { error: '知らないシートです' };
  rowIndex = Number(rowIndex || row._row);
  if (!rowIndex || rowIndex < 2) return { error: '行が分かりません' };
  var sh = sheetOf(name), head = headOf(name);
  // 行番号だけを信じない。シートで行を消されると、画面が覚えている行番号がずれて
  // 別の記入を上書きしてしまう。番号（id）が合っているか確かめ、ずれていたら番号で探し直す。
  var want = String(matchId || row['id'] || '');
  if (want && (name === '購入' || name === '入金')) {
    var atRow = String(sh.getRange(rowIndex, head.indexOf('id') + 1).getDisplayValue() || '');
    if (atRow !== want) {
      rowIndex = findRowById(name, want);
      if (!rowIndex) return { error: want + ' がシートに見つかりません。画面を読み直してください。' };
    }
  }
  var before = sh.getRange(rowIndex, 1, 1, head.length).getDisplayValues()[0];
  var old = {};
  head.forEach(function (h, i) { old[h] = before[i]; });

  // 承認のあとに本人が証憑を足すとき：証憑の列だけを今の行に重ねる。ほかの列はシートの値のまま。
  delete row.__evidenceOnly;
  var ownRow = String(old['記入者メール'] || '').toLowerCase() === me.email;
  if (name === '購入' && ownRow && OPEN_STATES.indexOf(String(old['状態'] || '')) < 0 &&
      me.role !== 'acc' && me.role !== 'pres') {
    var raw = sh.getRange(rowIndex, 1, 1, head.length).getValues()[0];
    var merged = { _row: rowIndex, __evidenceOnly: true };
    head.forEach(function (h, i) { merged[h] = (EVIDENCE_COLS.indexOf(h) >= 0 && (h in row)) ? row[h] : raw[i]; });
    row = merged;
  }

  var guard = canWrite(me, name, row, old);
  if (guard) return { error: guard };

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (name === '購入') row['記入者メール'] = old['記入者メール'] || me.email;
    var arr = head.map(function (h) { return row[h] !== undefined && row[h] !== null ? row[h] : ''; });
    sh.getRange(rowIndex, 1, 1, head.length).setValues([arr]);
    logIt(me, '更新', name + ' ' + (row['id'] || rowIndex), String(old['状態'] || ''), String(row['状態'] || ''));
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

/* 誰が何を書けるか。画面ではなく、ここで決めます。 */
var EVIDENCE_COLS = ['見積書', '発注書', '納品書', '請求書', '領収書', '振込証憑', 'その他', '証憑フォルダ', '更新日時', '更新者'];
var OPEN_STATES = ['下書き', '差し戻し', 'チェック待ち'];
function canWrite(me, name, row, old) {
  if (me.role === 'acc') return null;

  if (name === 'マスタ' || name === '人' || name === '按分' || name === '仕訳ルール') {
    return 'これを変えられるのは経理だけです。';
  }
  if (name === '履歴') return '履歴は書き換えられません。';

  if (name === '購入') {
    if (!old) return null;                      // 新しく出すのは誰でもできる
    var mine = String(old['記入者メール'] || '').toLowerCase() === me.email;
    var st = String(old['状態'] || '');
    var next = String(row['状態'] || '');
    if (mine && next !== st && ['承認済', '社長待ち', '支払済'].indexOf(next) >= 0 && me.role !== 'pres') {
      return '自分の記入は自分で承認できません。';
    }
    if (mine && (st === '下書き' || st === '差し戻し' || st === 'チェック待ち')) return null;
    // 承認のあとでも、本人が証憑を足すのは認める（請求書があとから届くことが多い）。
    // doUpdate が証憑の列だけを取り込んだ行にしてから渡す（__evidenceOnly）。ほかの列は変わらない。
    if (mine && row.__evidenceOnly) return null;
    if (me.role === 'mgr' && inCharge(me, old, personDepts())) return null;
    if (me.role === 'pres') return null;
    return '出したあとは直せません。経理に直してもらってください。';
  }
  if (name === '入金') {
    if (me.role === 'mgr' || me.role === 'pres') return null;
    if (!old) return null;                      // 入金予定を足すのは誰でもできる
    // 一般ユーザが直せるのは自分が足したものだけ。入金の確認は経理がする
    var own = String(old['記入者メール'] || '').toLowerCase() === me.email;
    if (!own) return '人が足した入金予定は直せません。';
    if (String(row['入金確認日'] || '') !== String(old['入金確認日'] || '')) return '入金の確認は経理がします。';
    return null;
  }
  return null;
}

/* 管理番号の頭文字。アプリの設定で決め、呼び出しのたびに渡してもらう。
   過去の手作業の番号（No / t / g / G / MM）と重ならないよう、既定は B。 */
function cleanPrefix(p, fallback) {
  p = String(p || '').toUpperCase();
  return /^[A-Z]{1,4}$/.test(p) ? p : (fallback || 'B');
}
/* 番号を振るシート。購入（既定 B）と入金（既定 R）。 */
function numberedSheet(name) { return name === '入金' ? '入金' : '購入'; }
function defaultPrefix(sheet) { return sheet === '入金' ? 'R' : 'B'; }
/* シートにある、その頭文字の一番大きい番号 */
function maxIdInSheet(prefix, sheet) {
  var rows = readValues(sheet || '購入');
  if (!rows.length) return 0;
  var head = rows[0], c = head.indexOf('id'), mx = 0;
  for (var i = 1; i < rows.length; i++) {
    var m = String(rows[i][c] || '').match(new RegExp('^' + prefix + '(\\d+)$'));
    if (m) mx = Math.max(mx, Number(m[1]));
  }
  return mx;
}
function idExists(id, sheet) {
  var rows = readValues(sheet || '購入');
  if (!rows.length) return false;
  var head = rows[0], c = head.indexOf('id');
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][c] || '') === String(id)) return true;
  }
  return false;
}
/* 番号を1つ取り置く。
   ブラウザ側で数えてはいけない。一般ユーザには他人の記入を渡していないので、
   手元の一番大きい番号は自分の分だけになり、初めての人は必ず G0001 になる。
   ここはシート全部を見られるので、正しい番号を出せる。
   ここで鍵をかけて、シートの最大値と取り置き済みの大きいほうに1を足して返す。
   出すのをやめたときは番号が飛ぶが、同じ番号が2つできるより飛ぶほうがよい。 */
function reserveId(prefix, sheet) {
  sheet = numberedSheet(sheet);
  prefix = cleanPrefix(prefix, defaultPrefix(sheet));
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var props = PropertiesService.getScriptProperties();
    var key = 'last_id_' + prefix;          // 頭文字ごとに数える
    var kept = Number(props.getProperty(key) || 0);
    var n = Math.max(kept, maxIdInSheet(prefix, sheet)) + 1;
    props.setProperty(key, String(n));
    return prefix + ('0000' + n).slice(-4);
  } finally {
    lock.releaseLock();
  }
}

function logIt(me, action, target, before, after) {
  try {
    appendRaw('履歴', {
      '日時': Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm'),
      '操作者': me.name + '（' + me.email + '）',
      '操作': action, '対象': target, '変更前': before, '変更後': after
    });
  } catch (e) {}
}
