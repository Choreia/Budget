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
           'チェック者','チェック日時','社長承認者','社長承認日時','差戻理由','更新日時','更新者'],
  '入金': ['id','記入日時','記入者','部門','種別','項目','証憑','税込','税抜','振込期日','入金確認日','確認者','売掛入力','備考'],
  'マスタ': ['リスト','値','有効','並び','使用回数','最終使用'],
  '人': ['メール','名前','ロール','部門','上長メール'],
  '按分': ['id','キーワード','分け方','部門','重み','有効','更新者','更新日時'],
  '履歴': ['日時','操作者','操作','対象','変更前','変更後']
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
      case 'append': return json(doAppend(me, req.sheet, req.row));
      case 'update': return json(doUpdate(me, req.sheet, req.row, req.rowIndex));
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
    depts: String((hit && hit['部門']) || '').split(/[,、]/).map(trim).filter(nonEmpty)
  };
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
    // 一般ユーザに他人の購入・入金は渡さない。画面で隠すのではなく、そもそも送らない。
    if (me.role === 'user' && (name === '購入' || name === '入金')) {
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
  if (!v.length || !me.depts.length) return v;
  var head = v[0];
  var dc = head.indexOf('部門'), ec = head.indexOf('記入者メール');
  if (dc < 0) return v;
  var keep = [head];
  for (var i = 1; i < v.length; i++) {
    var mine = me.depts.indexOf(String(v[i][dc])) >= 0 ||
               (ec >= 0 && String(v[i][ec] || '').toLowerCase() === me.email);
    keep.push(mine ? v[i] : blankRow(head.length, i));
  }
  return keep;
}
/* 行番号がずれないように、隠す行は空で埋める */
function blankRow(n) {
  var a = []; for (var i = 0; i < n; i++) a.push('');
  return a;
}

function doAppend(me, name, row) {
  if (!SHEETS[name]) return { error: '知らないシートです' };
  var guard = canWrite(me, name, row, null);
  if (guard) return { error: guard };
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    if (name === '購入') {
      row['記入者メール'] = me.email;
      row['記入者'] = row['記入者'] || me.name;
      if (!row['id']) row['id'] = nextId();
    }
    var r = appendRaw(name, row);
    logIt(me, '追加', name + ' ' + (row['id'] || row['値'] || ''), '', String(row['品名'] || row['項目'] || ''));
    return { ok: true, row: r, id: row['id'] || '' };
  } finally {
    lock.releaseLock();
  }
}

function doUpdate(me, name, row, rowIndex) {
  if (!SHEETS[name]) return { error: '知らないシートです' };
  rowIndex = Number(rowIndex || row._row);
  if (!rowIndex || rowIndex < 2) return { error: '行が分かりません' };
  var sh = sheetOf(name), head = headOf(name);
  var before = sh.getRange(rowIndex, 1, 1, head.length).getDisplayValues()[0];
  var old = {};
  head.forEach(function (h, i) { old[h] = before[i]; });

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
function canWrite(me, name, row, old) {
  if (me.role === 'acc') return null;

  if (name === 'マスタ' || name === '人' || name === '按分') {
    return 'これを変えられるのは経理だけです。';
  }
  if (name === '履歴') return '履歴は書き換えられません。';

  if (name === '購入') {
    if (!old) return null;                      // 新しく出すのは誰でもできる
    var mine = String(old['記入者メール'] || '').toLowerCase() === me.email;
    var st = String(old['状態'] || '');
    if (mine && (st === '下書き' || st === '差し戻し' || st === 'チェック待ち')) return null;
    if (me.role === 'mgr' && me.depts.indexOf(String(old['部門'])) >= 0) return null;
    if (me.role === 'pres') return null;
    return '出したあとは直せません。経理に直してもらってください。';
  }
  if (name === '入金') {
    if (me.role === 'mgr' || me.role === 'pres') return null;
    return '入金を書けるのは課長と経理です。';
  }
  return null;
}

function nextId() {
  var rows = readValues('購入');
  if (!rows.length) return 'G0001';
  var head = rows[0], c = head.indexOf('id'), mx = 0;
  for (var i = 1; i < rows.length; i++) {
    var m = String(rows[i][c] || '').match(/^G(\d+)$/);
    if (m) mx = Math.max(mx, Number(m[1]));
  }
  return 'G' + ('0000' + (mx + 1)).slice(-4);
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
