"""マニュアルの撮影用の仕組み。本物の index.html を、偽物の Google につないで動かす。

- ログイン（Google Identity）・ドライブ・書き込み役を偽物に差し替える
- 書き込み役は tools/gas-mock.js が apps-script/Code.gs をそのまま動かす（先に起動しておく）
- 画面の操作に合わせてナレーションを流し、字幕と音声を動画に焼き込む
本番のデータには一切触れない（送り先はすべてこの手元の偽物）。
"""
import hashlib, json, os, re, subprocess, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'tools' / '.cache'
CACHE.mkdir(parents=True, exist_ok=True)
GAS_LOCAL = 'http://127.0.0.1:8787'
APP_URL = 'https://choreia.github.io/Budget/'
GAS_URL = 'https://script.google.com/macros/s/DEMO/exec'
VOICE = 'ja-JP-KeitaNeural'
W, H = 1280, 800

FAKE_GIS = """
window.google = {accounts:{oauth2:{
  initTokenClient: function(cfg){ return { requestAccessToken: function(){
    setTimeout(function(){ cfg.callback({access_token:'demo:'+localStorage.getItem('demo_email'), expires_in:3600}); }, 400);
  }}; },
  revoke: function(t, cb){ cb && cb(); }
}}};
"""

CURSOR = """
addEventListener('DOMContentLoaded', function(){
  var c = document.createElement('div'); c.id='__cur';
  c.style.cssText='position:fixed;z-index:2147483647;width:26px;height:26px;border-radius:50%;'+
    'background:rgba(205,131,84,.28);border:2px solid #a0522d;pointer-events:none;left:-60px;top:-60px;'+
    'transform:translate(-50%,-50%);transition:left .35s ease,top .35s ease,background .15s';
  document.body.appendChild(c);
  addEventListener('mousemove', function(e){ c.style.left=e.clientX+'px'; c.style.top=e.clientY+'px'; }, true);
  addEventListener('mousedown', function(){ c.style.background='rgba(160,82,45,.75)'; }, true);
  addEventListener('mouseup',   function(){ c.style.background='rgba(205,131,84,.28)'; }, true);
});
"""

# ---------------------------------------------------------------- 書き込み役（偽物）
def gas_local(path, body=None):
    data = json.dumps(body).encode() if body is not None else b''
    req = urllib.request.Request(GAS_LOCAL + path, data=data, method='POST' if body is not None or path == '/__reset' else 'GET')
    return json.loads(urllib.request.urlopen(req).read())

def gas_call(action, email, **kw):
    kw.update(action=action, token='demo:' + email)
    req = urllib.request.Request(GAS_LOCAL + '/', data=json.dumps(kw).encode(), method='POST')
    return json.loads(urllib.request.urlopen(req).read())

# ---------------------------------------------------------------- ドライブ（偽物）
class FakeDrive:
    def __init__(self, config, people):
        self.config = dict(config)
        self.people = people            # email -> 表示名
        self.n = 0
        self.names = {}                 # id -> name
        self.parents = {}               # id -> 親フォルダid

    def new_id(self, p):
        self.n += 1
        return f'{p}{self.n:024d}'   # 本物と同じく20文字以上（アプリはURLからこの長さのIDを拾う）

    def handle(self, route):
        req = route.request
        url, method = req.url, req.method
        auth = req.headers.get('authorization', '')
        email = auth.replace('Bearer demo:', '') if 'demo:' in auth else ''
        j = lambda o, code=200: route.fulfill(status=code, content_type='application/json',
                                              headers={'Access-Control-Allow-Origin': '*'}, body=json.dumps(o))
        if method == 'OPTIONS':
            return route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'})
        if '/drive/v3/about' in url:
            return j({'user': {'emailAddress': email, 'displayName': self.people.get(email, email.split('@')[0])}})
        if '/upload/drive/v3/files/cfg' in url:                       # 設定ファイルの保存
            try: self.config.update(json.loads(req.post_data or '{}'))
            except Exception: pass
            return j({'id': 'cfg'})
        if '/upload/drive/v3/files' in url:                           # 証憑のアップロード
            fid = self.new_id('U')
            buf = req.post_data_buffer or b''
            m = re.search(rb'"name":"([^"]+)"', buf)
            if m: self.names[fid] = m.group(1).decode('utf-8', 'ignore')
            m = re.search(rb'"parents":\["([^"]+)"', buf)
            if m: self.parents[fid] = m.group(1).decode()
            return j({'id': fid})
        if re.search(r'/drive/v3/files/[^/?]+/permissions', url):
            return j({})
        if '/drive/v3/files/cfg' in url and 'alt=media' in url:
            return j(self.config)
        m = re.search(r'/drive/v3/files/([^/?]+)\?', url)
        if m and method == 'GET':
            fid = m.group(1)
            return j({'id': fid, 'name': self.names.get(fid, 'アプリ_請求書'), 'mimeType': 'application/vnd.google-apps.folder'})
        if m and method == 'PATCH':
            return j({'id': m.group(1)})
        if '/drive/v3/files' in url and method == 'GET':
            q = urllib.request.unquote(url)
            m = re.search(r"'([^']+)' in parents", q)
            if m:
                return j({'files': [{'id': k, 'name': self.names.get(k, k), 'webViewLink': 'https://drive.google.com/file/d/' + k}
                                    for k, v in self.parents.items() if v == m.group(1)]})
            if 'choreia-budget-config.json' in q: return j({'files': [{'id': 'cfg', 'name': 'choreia-budget-config.json'}]})
            return j({'files': [{'id': 'DEMO_ROOT', 'name': 'Choreia 予算 証憑'}]})
        if '/drive/v3/files' in url and method == 'POST':             # フォルダを作る
            fid = self.new_id('F')
            try: self.names[fid] = json.loads(req.post_data or '{}').get('name', '')
            except Exception: pass
            return j({'id': fid, 'webViewLink': 'https://drive.google.com/drive/folders/' + fid})
        return j({})

# ---------------------------------------------------------------- 読み上げ
def tts(text):
    key = hashlib.sha1((VOICE + '|' + text).encode()).hexdigest()[:16]
    out = CACHE / f'tts_{key}.mp3'
    if not out.exists():
        subprocess.run(['edge-tts', '--voice', VOICE, '--rate=+5%', '--text', text, '--write-media', str(out)],
                       check=True, capture_output=True, timeout=120)
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(out)],
                               capture_output=True, text=True).stdout.strip())
    return out, dur

# ---------------------------------------------------------------- 撮影
class Take:
    """1人ぶんの撮影。ブラウザを開き、操作とナレーションを記録する。"""
    def __init__(self, pw, drive, email, name, video_dir, shots_dir, prefix):
        self.drive, self.email, self.shots_dir, self.prefix = drive, email, Path(shots_dir), prefix
        self.browser = pw.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--lang=ja-JP'])
        self.ctx = self.browser.new_context(viewport={'width': W, 'height': H}, locale='ja-JP',
                                            timezone_id='Asia/Tokyo', record_video_dir=str(video_dir),
                                            record_video_size={'width': W, 'height': H})
        self.ctx.add_init_script(f"try{{localStorage.setItem('demo_email', {json.dumps(email)});}}catch(e){{}}")
        self.ctx.add_init_script(CURSOR)
        self.ctx.route('https://accounts.google.com/**', lambda r: r.fulfill(status=200, content_type='text/javascript', body=FAKE_GIS))
        self.ctx.route('https://www.googleapis.com/**', drive.handle)
        self.ctx.route(GAS_URL + '*', self._gas)
        self.ctx.route(APP_URL + '*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8',
                                                          body=(ROOT / 'index.html').read_text('utf-8')))
        self.answers = []
        self.page = self.ctx.new_page()
        self.t0 = time.time()
        self.page.on('dialog', self._dialog)
        self.log = []
        self.shot_n = 0

    def _gas(self, route):
        req = urllib.request.Request(GAS_LOCAL + '/', data=(route.request.post_data or '').encode(), method='POST')
        body = urllib.request.urlopen(req).read()
        route.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'}, body=body)

    def _dialog(self, d):
        time.sleep(0.6)
        if self.answers:
            a = self.answers.pop(0)
            if a is False: return d.dismiss()
            return d.accept(a if isinstance(a, str) else (d.default_value or ''))
        return d.accept(d.default_value or '')

    # --- 操作 ---
    def goto(self):
        self.page.goto(APP_URL)
        self.page.wait_for_timeout(600)

    def scroll_to(self, loc):
        loc.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'center'})")
        self.page.wait_for_timeout(700)

    def move_to(self, loc):
        self.scroll_to(loc)
        b = loc.bounding_box()
        if b: self.page.mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2, steps=18)
        self.page.wait_for_timeout(250)

    def click(self, target):
        loc = self.page.locator(target) if isinstance(target, str) else target
        loc = loc.first
        self.move_to(loc)
        loc.click()
        self.page.wait_for_timeout(500)

    def type(self, target, text, delay=45):
        loc = (self.page.locator(target) if isinstance(target, str) else target).first
        self.move_to(loc)
        loc.click()
        loc.press_sequentially(text, delay=delay)
        self.page.wait_for_timeout(250)

    def tab(self, name):
        self.click(f'#tabs button[data-t="{name}"]')
        self.page.wait_for_timeout(700)

    def idle(self, ms=800):
        self.page.wait_for_timeout(ms)

    def wait_text(self, text, timeout=15000):
        self.page.get_by_text(text).first.wait_for(timeout=timeout)

    def shot(self, name, target=None, full=False):
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self.page.wait_for_timeout(350)
        p = self.shots_dir / f'{self.prefix}-{name}.png'
        cur = self.page.locator('#__cur')
        if cur.count(): cur.evaluate("e => e.style.visibility='hidden'")
        self.page.evaluate("() => { var t = document.getElementById('toast'); if(t) t.style.visibility='hidden'; }")
        if target:
            loc = (self.page.locator(target) if isinstance(target, str) else target).first
            loc.screenshot(path=str(p))
        else:
            self.page.screenshot(path=str(p), full_page=full)
        if cur.count(): cur.evaluate("e => e.style.visibility='visible'")
        self.page.evaluate("() => { var t = document.getElementById('toast'); if(t) t.style.visibility=''; }")
        return p

    # --- ナレーション ---
    def say(self, text, action=None, after=0.35):
        audio, dur = tts(text)
        start = time.time() - self.t0
        if action: action()
        left = start + dur + after - (time.time() - self.t0)
        if left > 0: self.page.wait_for_timeout(int(left * 1000))
        self.log.append({'start': start, 'dur': dur, 'text': text, 'audio': str(audio)})

    def close(self):
        self.page.wait_for_timeout(800)
        video = self.page.video.path()
        self.ctx.close(); self.browser.close()
        return Path(video), self.log

# ---------------------------------------------------------------- 動画の仕上げ
def _ass_time(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'

def _wrap(text, n=34):
    out, line = [], ''
    for ch in text:
        line += ch
        if len(line) >= n and ch in '、。）」':
            out.append(line); line = ''
    if line: out.append(line)
    return r'\N'.join(out)

def finish(video, log, out_mp4, title):
    out_mp4 = Path(out_mp4)
    ass = out_mp4.with_suffix('.ass')
    ev = []
    for L in log:
        ev.append(f"Dialogue: 0,{_ass_time(L['start'])},{_ass_time(L['start'] + L['dur'] + 0.25)},Sub,,0,0,0,,{_wrap(L['text'])}")
    end = max(L['start'] + L['dur'] for L in log) if log else 3
    ass.write_text("""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 800

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Noto Sans CJK JP,30,&H00FFFFFF,&H000000FF,&H00000000,&HA0222222,1,0,0,0,100,100,0,0,3,14,0,2,60,60,30,1
Style: Title,Noto Sans CJK JP,38,&H00FFFFFF,&H000000FF,&H002D52A0,&HD02D52A0,1,0,0,0,100,100,0,0,3,22,0,8,60,60,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + '\n'.join(ev) + '\n', 'utf-8')
    inputs = ['-i', str(video)]
    filt, labels = [], []
    for i, L in enumerate(log):
        inputs += ['-i', L['audio']]
        ms = int(L['start'] * 1000)
        filt.append(f'[{i+1}:a]adelay={ms}|{ms},aresample=44100[a{i}]')
        labels.append(f'[a{i}]')
    filt.append(''.join(labels) + f'amix=inputs={len(labels)}:normalize=0:dropout_transition=0[aout]')
    filt.append(f"[0:v]ass={ass}[vout]")
    subprocess.run(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', ';'.join(filt),
                    '-map', '[vout]', '-map', '[aout]', '-c:v', 'libx264', '-preset', 'medium', '-crf', '26',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart',
                    '-shortest', str(out_mp4)], check=True)
    ass.unlink()
    return out_mp4
