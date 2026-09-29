"""マニュアルの画面写真と動画を作る。

  node tools/gas-mock.js 8787 &      # 書き込み役（本物の Code.gs）を手元で動かす
  python3 tools/make_manual.py        # manual/ に画像と動画ができる
  DRY=1 python3 tools/make_manual.py  # ナレーションなしで流れだけ確かめる

人名・取引先・金額はすべて架空。本番のデータには触れない。
"""
import os, sys, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).parent))
import manual_rig as R
import demo_data as D

DRY = os.environ.get('DRY') == '1'
OUT = R.ROOT / 'manual'
IMG = OUT / 'img'
VID_TMP = R.CACHE / 'video'
ONLY = set(filter(None, os.environ.get('ONLY', '').split(',')))

if DRY:
    def _say(self, text, action=None, after=0.35):
        start = time.time() - self.t0
        if action: action()
        self.page.wait_for_timeout(300)
        self.log.append({'start': start, 'dur': 0.3, 'text': text, 'audio': ''})
    R.Take.say = _say

# ---------------------------------------------------------------- 見本の書類（架空）
def sample_pdf(kind, company, item, amount):
    p = R.CACHE / 'samples' / f'{kind}_{company}.pdf'
    if p.exists(): return p
    p.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new('RGB', (1240, 1754), 'white')
    d = ImageDraw.Draw(img)
    f = lambda n: ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', n)
    d.text((80, 90), kind, font=f(72), fill='black')
    d.text((80, 230), f'株式会社エムスクエアラボ 御中', font=f(34), fill='black')
    d.text((760, 230), company, font=f(30), fill='black')
    d.line((80, 330, 1160, 330), fill='black', width=2)
    d.text((80, 380), f'品名　{item}', font=f(34), fill='black')
    d.text((80, 450), f'金額　{amount:,} 円（税込）', font=f(34), fill='black')
    d.text((80, 1600), '※ マニュアル用の見本です', font=f(26), fill='gray')
    img.save(p, 'PDF'); return p

# ---------------------------------------------------------------- 全体の流れ（動画の冒頭）
FLOW_CSS = """
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#faf8f5;
  font-family:'Noto Sans JP',sans-serif;color:#2c2418}
.wrap{width:1120px}
h1{font-family:'Zen Kaku Gothic New',sans-serif;font-weight:900;font-size:40px;margin:0 0 6px}
h1 b{color:#a0522d}
.sub{color:#5a5044;font-size:19px;margin:0 0 44px}
.row{display:flex;align-items:stretch;gap:0}
.box{flex:1;background:#fff;border:2px solid #d4cdc2;border-radius:16px;padding:22px 18px;text-align:center;
  transition:all .5s;position:relative}
.box .who{font-family:'Zen Kaku Gothic New',sans-serif;font-weight:900;font-size:26px}
.box .what{font-size:16px;color:#5a5044;margin-top:8px;line-height:1.6}
.box.opt{border-style:dashed}
.arr{width:54px;display:flex;align-items:center;justify-content:center;font-size:30px;color:#a0522d}
.back{margin:18px 0 0 0;height:56px;position:relative}
.back .line{position:absolute;left:11%;right:48%;top:0;height:30px;border:2px solid #a04034;border-top:none;
  border-radius:0 0 14px 14px}
.back .lbl{position:absolute;left:11%;right:48%;top:36px;text-align:center;color:#a04034;font-size:16px;font-weight:700}
.note{margin-top:28px;background:#f5ece5;border-radius:12px;padding:14px 20px;font-size:17px;color:#5a5044}
.hl .box{opacity:.38}
.hl .box.on{opacity:1;border-color:#a0522d;background:#f3e2d6;box-shadow:0 0 0 5px rgba(160,82,45,.18);transform:translateY(-4px)}
"""
def flow_html():
    return """<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&family=Zen+Kaku+Gothic+New:wght@900&display=swap">
<style>""" + FLOW_CSS + """</style></head><body><div class="wrap" id="w">
<h1>Choreia <b>予算</b>　全体の流れ</h1>
<p class="sub">仕事で使うものを買うときの申請と、証憑の置き場所をひとつに</p>
<div class="row">
  <div class="box" data-r="user"><div class="who">記入する人</div><div class="what">買うものを記入<br>証憑を上げて出す</div></div>
  <div class="arr">→</div>
  <div class="box" data-r="approver"><div class="who">承認者</div><div class="what">同じ部署の人の<br>記入をチェック</div></div>
  <div class="arr">→</div>
  <div class="box opt" data-r="president"><div class="who">社長</div><div class="what">10万円以上だけ<br>確認する</div></div>
  <div class="arr">→</div>
  <div class="box" data-r="keiri"><div class="who">経理</div><div class="what">支払・入金を管理<br>抜けを確かめる</div></div>
</div>
<div class="back"><div class="line"></div><div class="lbl">差し戻し　→　直して、同じ番号のまま出し直す</div></div>
<div class="note">入力したものは会社のスプレッドシート「予算管理」に1件1行で入り、証憑はGoogleドライブの決まったフォルダに入ります。</div>
</div></body></html>"""

def intro(t, role, name):
    t.say('はじめに、全体の流れです。記入する人が出したものを、承認者がチェックします。10万円以上のものは社長も確認し、最後に経理が支払います。',
          lambda: (t.page.set_content(flow_html()), t.idle(1200)))
    t.say('直してほしいところがあれば差し戻され、直して同じ番号のまま出し直します。',
          lambda: t.move_to(t.page.locator('.back .lbl')))
    t.say(f'この動画では、{name}の使い方をご説明します。',
          lambda: t.page.evaluate("r => { document.getElementById('w').classList.add('hl'); "
                                  "document.querySelectorAll('.box').forEach(b => b.classList.toggle('on', b.dataset.r===r)); }", role))
    t.idle(600)

# ---------------------------------------------------------------- 共通
def login(t):
    t.goto()
    if t.page.locator('#region-pick').is_visible():
        t.click('#ch-region [data-r="jp"]')
    t.click('#btn-signin')
    t.page.locator('#appmain').wait_for(state='visible', timeout=20000)
    t.idle(2200)

def chip(t, box, label):
    t.click(t.page.locator(f'#{box} button', has_text=label))

def fill_date(t, sel, v):
    loc = t.page.locator(sel)
    t.move_to(loc)
    loc.fill(v)
    t.idle(300)

def card_btn(t, entry_id, attr):
    return t.page.locator('#approve-list div.card', has_text=entry_id).locator(f'[{attr}]')

def top(t):
    t.page.evaluate("window.scrollTo({top:0, behavior:'smooth'})"); t.idle(700)

def row_btn(t, container, entry_id, attr):
    return t.page.locator(f'#{container} tr', has_text=entry_id).locator(f'[{attr}]')

# ---------------------------------------------------------------- 1. 記入する人
def take_user(pw, drive):
    t = R.Take(pw, drive, D.SATO, D.PEOPLE[D.SATO], VID_TMP, IMG, 'user')
    mitsumori = sample_pdf('見積書', 'サンプル照明株式会社', 'LED照明 育苗用 5本', 27500)
    mitsu2 = sample_pdf('見積書', 'サンプルセンサー株式会社', '温湿度センサー 10個', 22000)
    intro(t, 'user', '記入する人')
    t.shot('00-flow')
    t.say('アプリを開くと、この画面になります。', lambda: t.goto())
    t.shot('01-login')
    t.say('会社のGoogleアカウントでログインします。「Googleでログイン」を押してください。', lambda: login(t))
    t.say('開くと「わたしの記入」の画面です。自分が出したものだけが並びます。ほかの人の分は見えません。',
          lambda: t.move_to(t.page.locator('#my-list')))
    t.shot('02-home')
    t.say('差し戻されたものには、理由が書いてあります。この例では「見積書を付けてください」と戻ってきています。',
          lambda: t.move_to(t.page.locator('#my-list tr', has_text='B0008')))
    t.say('では、新しく記入してみます。まず品名と、何のために買うのかを書きます。',
          lambda: (t.type('#f-name', 'LED照明 育苗用 5本'), t.type('#f-why', '育苗棚の明るさをそろえて、苗の生育のばらつきを減らすため')))
    t.say('金額は、請求書や見積書に書いてある税込の金額をそのまま入れます。税抜は自動で計算されます。',
          lambda: (t.type('#f-gross', '27500'), t.move_to(t.page.locator('#f-net'))))
    t.say('費用を負担する部門と、項目を選びます。',
          lambda: (chip(t, 'ch-dept', 'D-base'), chip(t, 'ch-item', '備品消耗品_研究開発(新製品)')))
    t.say('購入先と支払方法を入れます。インボイス番号が分かれば入れてください。',
          lambda: (t.type('#f-vendor', 'サンプル照明株式会社'), t.page.locator('#f-pay').select_option('銀行振込'),
                   t.move_to(t.page.locator('#f-pay')), t.type('#f-invoice', 'T1234567890123')))
    t.shot('03-form', '#apply .card:has(#f-name)')
    t.say('発注した日や、納品の予定日は、分かっている範囲で大丈夫です。',
          lambda: (fill_date(t, '#f-order', '2026-09-29'), fill_date(t, '#f-plan', '2026-10-06')))
    t.say('見積書や請求書などの証憑は、ここから上げます。上げたファイルの横で、書類の種類を選べます。',
          lambda: (t.move_to(t.page.locator('#f-files')), t.page.locator('#f-files').set_input_files(str(mitsumori)), t.idle(600),
                   t.page.locator('#filebox select').first.select_option('見積書')))
    t.shot('04-evidence', '#f-files >> xpath=ancestor::div[contains(@class,"field")]')
    t.say('最後に「チェックに出す」を押します。番号が振られて、承認者のところに届きます。',
          lambda: (t.click('#btn-submit'), t.wait_text('をチェックに出しました'), t.idle(1200)))
    t.say('出したものは上に並びます。いまどこにあるかは「いまどこ」の欄で分かります。チェックの前なら、自分で取り下げることもできます。',
          lambda: t.move_to(t.page.locator('#my-list tr', has_text='LED照明')))
    t.shot('05-list', '#my-list')
    t.say('差し戻されたものは「直して出す」を押すと、内容が下の欄に写ります。',
          lambda: (t.click(row_btn(t, 'my-list', 'B0008', 'data-edit')), t.idle(900)))
    t.shot('06-fix', '#apply .card:has(#f-name)')
    t.say('言われたとおり見積書を付けて、もう一度「チェックに出す」を押します。番号と証憑フォルダは、そのままです。',
          lambda: (t.move_to(t.page.locator('#f-files')), t.page.locator('#f-files').set_input_files(str(mitsu2)), t.idle(600),
                   t.page.locator('#filebox select').first.select_option('見積書'),
                   t.click('#btn-submit'), t.wait_text('をチェックに出しました'), t.idle(1000)))
    t.say('「抜けているもの」には、足りない証憑などが自動で出ます。ここから、そのまま上げることもできます。',
          lambda: (t.tab('gaps'), top(t), t.move_to(t.page.locator('#gaps-list tr').nth(1))))
    t.shot('07-gaps')
    t.say('使い方は以上です。分からないことは、経理までお気軽にお尋ねください。', lambda: t.tab('apply'))
    return t.close()

# ---------------------------------------------------------------- 2. 承認者
def take_approver(pw, drive):
    t = R.Take(pw, drive, D.SHONIN, D.PEOPLE[D.SHONIN], VID_TMP, IMG, 'approver')
    seikyu = sample_pdf('請求書', 'サンプル農園株式会社', '栽培指導 業務委託 10月分', 330000)
    intro(t, 'approver', '承認者')
    t.say('承認者は、担当する部署の人が出したものをチェックします。', lambda: t.goto())
    t.say('会社のGoogleアカウントでログインします。', lambda: login(t))
    t.say('「チェックする」を開くと、担当の部署の人が出したものが溜まっています。自分が出したものは、ここには来ません。',
          lambda: t.tab('approve'))
    t.shot('01-approve')
    t.say('品名、購入理由、金額、証憑がそろっているかを確かめます。証憑は「証憑フォルダを開く」から見られます。',
          lambda: t.move_to(t.page.locator('#approve-list div.card', has_text='B0008')))
    t.say('問題がなければ「チェック済にする」を押します。これで経理に回ります。',
          lambda: (t.click(card_btn(t, 'B0008', 'data-ok')), t.idle(1500)))
    t.say('直してほしいところがあれば「差し戻す」を押して、理由を書きます。理由は、出した本人にそのまま届きます。',
          lambda: (t.answers.append('回線の契約期間を、購入理由に書いてください'),
                   t.click(card_btn(t, 'B0009', 'data-rej')), t.idle(1500)))
    t.say('10万円以上のものは、チェック済にすると、社長の確認に回ります。社長も同じ画面で、同じように押すだけです。',
          lambda: t.move_to(t.page.locator('#approve-list div.card', has_text='B0010')))
    t.say('「台帳」では、担当の部署の記入を一覧で見られます。状態や部門で絞り込めます。',
          lambda: (t.tab('ledger'), t.move_to(t.page.locator('#ledger table').first)))
    t.shot('02-ledger')
    t.say('「課のコスト」では、部門ごとに、いくら使ったかを月ごとに確かめられます。', lambda: t.tab('cost'))
    t.shot('03-cost')
    t.say('入金の予定がある場合は「入金予定」から登録します。請求書も一緒に上げられます。',
          lambda: (t.tab('income'), t.click('#btn-income-new'), t.type('#i-title', '栽培指導 業務委託 10月分'),
                   t.type('#i-gross', '330000'), fill_date(t, '#i-due', '2026-11-30')))
    t.say('請求書を選んで「登録する」を押すと、番号が振られ、請求書は経理のフォルダに、番号付きの名前で入ります。',
          lambda: (t.move_to(t.page.locator('#i-files')), t.page.locator('#i-files').set_input_files(str(seikyu)), t.idle(500),
                   t.shot('04-income-form', '#income-form'),
                   t.click('#btn-income-save'), t.wait_text('入金予定と請求書を登録しました'), t.idle(1200)))
    t.shot('05-income')
    t.say('使い方は以上です。チェックが溜まると、記入した人と経理の仕事が止まってしまうので、こまめに見ていただけると助かります。',
          lambda: t.tab('approve'))
    return t.close()

# ---------------------------------------------------------------- 3. 経理
def take_keiri(pw, drive):
    t = R.Take(pw, drive, D.KEIRI, D.PEOPLE[D.KEIRI], VID_TMP, IMG, 'keiri')
    t.ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin='https://choreia.github.io')
    intro(t, 'keiri', '経理')
    t.say('経理は、すべての記入を見て、支払いまでを管理します。', lambda: t.goto())
    t.say('ログインします。', lambda: login(t))
    t.say('「チェックする」には、承認者がまだ見ていないものや、承認者のいない部署の記入、社長の確認待ちが来ます。',
          lambda: t.tab('approve'))
    t.shot('01-approve')
    t.say('経理が代わりにチェックすることもできます。押し方は承認者と同じです。',
          lambda: (t.click(card_btn(t, 'B0010', 'data-ok')), t.idle(1500)))
    t.say('「台帳」では、すべての記入を見られます。承認済みのものは「支払依頼の文面」を押すと、Slackに貼る文面がコピーされます。',
          lambda: (t.tab('ledger'), t.click(row_btn(t, 'ledger', 'B0010', 'data-payreq')), t.idle(1200)))
    t.shot('02-ledger')
    t.say('支払ったら「支払済に」を押して、支払日を入れます。',
          lambda: (t.answers.append('2026-09-30'), t.click(row_btn(t, 'ledger', 'B0010', 'data-pay')), t.idle(1500)))
    t.say('記入を消したいときは、シートから行を消さずに「取り下げる」を使ってください。番号と記録は残り、集計と支払いからは外れます。',
          lambda: t.move_to(row_btn(t, 'ledger', 'B0009', 'data-wd')))
    t.say('「入金予定」では、期日の順に並びます。期日を過ぎたものは赤く出ます。入金を確かめたら「入金を確認」を押します。',
          lambda: (t.tab('income'), t.answers.append('2026-09-30'),
                   t.click(t.page.locator('#income-list tr', has_text='R0001').locator('[data-paid]')), t.idle(1500)))
    t.shot('03-income')
    t.say('「抜けているもの」には、証憑のない記入や、仕訳に必要な項目が空の記入が、自動で集まります。',
          lambda: (t.tab('gaps'), top(t)))
    t.shot('04-gaps')
    t.say('D-baseのように、いくつかの部署で使う費用は、「課のコスト」の下にある按分のルールで、自動で分けられます。',
          lambda: (t.tab('cost'), t.move_to(t.page.locator('#alloc-box'))))
    t.say('選択肢は「マスタ」で足したり、止めたりできます。止めた選択肢は新しい記入に出なくなるだけで、過去の記録は残ります。',
          lambda: t.tab('master'))
    t.shot('05-master')
    t.say('使う人とロールは「設定」で決めます。承認者には、チェックする部署を書きます。書き方が合っていないときは、ここに注意が出ます。',
          lambda: (t.tab('settings'), t.move_to(t.page.locator('#users-box'))))
    t.shot('06-settings', '#users-box')
    t.say('使い方は以上です。', lambda: t.tab('approve'))
    return t.close()

# ---------------------------------------------------------------- 実行
def main():
    IMG.mkdir(parents=True, exist_ok=True); VID_TMP.mkdir(parents=True, exist_ok=True)
    D.seed()
    drive = R.FakeDrive(D.CONFIG, D.PEOPLE)
    takes = [('user', take_user, '記入する人の使い方'), ('approver', take_approver, '承認者の使い方'),
             ('keiri', take_keiri, '経理の使い方')]
    with sync_playwright() as pw:
        for key, fn, title in takes:
            if ONLY and key not in ONLY: continue
            print('撮影中:', title, flush=True)
            video, log = fn(pw, drive)
            if DRY:
                print('  ok', len(log), 'steps'); continue
            out = R.finish(video, log, OUT / f'{key}.mp4', title)
            print('  →', out, flush=True)

if __name__ == '__main__':
    main()
