/* 書き込み役（apps-script/Code.gs）を、そのままローカルで動かすための偽物のGoogle。
   マニュアルの撮影と、通しの動作確認に使う。本番には関係しない。
   起動: node tools/gas-mock.js [port]
   POST /           … 本物の doPost に渡す（アプリからの呼び出し）
   POST /__reset    … 中身を空にする。本文が JSON なら { シート名: [[見出し], [行]...] } で入れる
   GET  /__dump     … いまの中身を JSON で返す */
const fs = require('fs'), path = require('path'), http = require('http'), vm = require('vm'), crypto = require('crypto');

let BOOK = {};           // シート名 → 2次元配列（文字列）
let PROPS = {}, CACHE = {};

function pad(a, n){ while(a.length < n) a.push(''); return a; }
function sheetObj(name){
  const d = () => BOOK[name];
  const lastRow = () => { const a = d(); let r = a.length; while(r > 0 && !a[r-1].some(x => String(x) !== '')) r--; return r; };
  const lastCol = () => d().reduce((m, row) => { let c = row.length; while(c > 0 && String(row[c-1]) === '') c--; return Math.max(m, c); }, 0);
  return {
    getName: () => name,
    getLastRow: lastRow, getLastColumn: lastCol,
    appendRow(arr){ const r = lastRow(); BOOK[name].splice(r, 0, arr.map(v => v == null ? '' : String(v))); BOOK[name].length = Math.max(BOOK[name].length, r + 1); },
    getRange(r, c, nr, nc){
      nr = nr || 1; nc = nc || 1;
      const get = () => { const out = []; for(let i = 0; i < nr; i++){ const row = BOOK[name][r-1+i] || []; out.push(pad(row.slice(c-1, c-1+nc).map(v => v == null ? '' : String(v)), nc)); } return out; };
      return {
        getValues: get, getDisplayValues: get,
        getDisplayValue: () => get()[0][0], getValue: () => get()[0][0],
        setValues(v){ for(let i = 0; i < v.length; i++){ const ri = r-1+i; while(BOOK[name].length <= ri) BOOK[name].push([]); const row = BOOK[name][ri]; pad(row, c-1+v[i].length); for(let j = 0; j < v[i].length; j++) row[c-1+j] = v[i][j] == null ? '' : String(v[i][j]); } },
        setValue(x){ this.setValues([[x]]); }
      };
    }
  };
}
const book = {
  getId: () => 'DEMO_SS', getName: () => '予算管理（デモ）',
  getSheetByName: n => BOOK[n] ? sheetObj(n) : null,
  insertSheet: n => { BOOK[n] = []; return sheetObj(n); }
};
const ctx = {
  console,
  SpreadsheetApp: { openById: () => book, getActive: () => book },
  LockService: { getScriptLock: () => ({ waitLock(){}, releaseLock(){} }) },
  PropertiesService: { getScriptProperties: () => ({ getProperty: k => (k in PROPS ? PROPS[k] : null), setProperty: (k, v) => { PROPS[k] = String(v); }, deleteProperty: k => { delete PROPS[k]; }, getKeys: () => Object.keys(PROPS) }) },
  CacheService: { getScriptCache: () => ({ get: k => CACHE[k] || null, put: (k, v) => { CACHE[k] = v; } }) },
  UrlFetchApp: { fetch(url, opt){
    const tok = String(((opt || {}).headers || {}).Authorization || '').replace(/^Bearer\s+/, '');
    const email = tok.indexOf('demo:') === 0 ? tok.slice(5) : '';
    return { getResponseCode: () => email ? 200 : 401,
             getContentText: () => JSON.stringify({ user: { emailAddress: email, displayName: email.split('@')[0] } }) };
  } },
  Utilities: {
    DigestAlgorithm: { SHA_256: 'sha256' },
    computeDigest: (alg, s) => Array.from(crypto.createHash('sha256').update(String(s)).digest()),
    base64Encode: b => Buffer.from(b.map(x => (x + 256) % 256)).toString('base64'),
    formatDate(d, tz, fmt){ const t = new Date(d.getTime() + 9*3600*1000), p = n => String(n).padStart(2, '0');
      return fmt.replace('yyyy', t.getUTCFullYear()).replace('MM', p(t.getUTCMonth()+1)).replace('dd', p(t.getUTCDate()))
                .replace('HH', p(t.getUTCHours())).replace('mm', p(t.getUTCMinutes())).replace('ss', p(t.getUTCSeconds())); }
  },
  ContentService: { MimeType: { JSON: 'json' }, createTextOutput: s => ({ content: s, setMimeType(){ return this; } }) },
  HtmlService: { createHtmlOutput: s => ({ content: s }) }
};
vm.createContext(ctx);
let src = fs.readFileSync(process.env.CODE_GS || path.join(__dirname, '..', 'apps-script', 'Code.gs'), 'utf8');
src = src.replace(/var SPREADSHEET_ID = '[^']*';/, "var SPREADSHEET_ID = 'DEMO_SS';");
vm.runInContext(src, ctx, { filename: 'Code.gs' });

const port = Number(process.argv[2] || 8787);
http.createServer((req, res) => {
  let body = '';
  req.on('data', c => body += c);
  req.on('end', () => {
    const delay = req.url.startsWith('/__') ? 0 : Number(process.env.DELAY_MS || 0);   // 本物の書き込み役の遅さをまねる
    const send = (code, obj) => setTimeout(() => { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' }); res.end(typeof obj === 'string' ? obj : JSON.stringify(obj)); }, delay);
    try {
      if(req.url.startsWith('/__reset')){ BOOK = body ? JSON.parse(body) : {}; PROPS = {}; CACHE = {}; return send(200, { ok: true }); }
      if(req.url.startsWith('/__dump'))  return send(200, { book: BOOK, props: PROPS });
      if(req.method === 'POST'){ const out = ctx.doPost({ postData: { contents: body } }); return send(200, out.content); }
      return send(200, ctx.doGet().content);
    } catch(e){ return send(500, { error: String(e && e.stack || e) }); }
  });
}).listen(port, '127.0.0.1', () => console.log('gas-mock on ' + port));
