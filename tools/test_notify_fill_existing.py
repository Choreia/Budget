"""v51 の通し試験：承認者へのメール／承認後に足りない所を埋める／すでに入っている証憑の表示と重複防止。
  node tools/gas-mock.js 8787 &   →   python3 tools/test_notify_fill_existing.py"""
import sys; sys.path.insert(0, '/data/m2labo/choreia-budget/tools')
from playwright.sync_api import sync_playwright
import manual_rig as R, demo_data as D
D.seed()
S = R.CACHE/'samples'
fa, fb = S/'見積書_サンプル照明株式会社.pdf', S/'請求書_サンプル農園株式会社.pdf'
def rows():
    d = R.gas_local('/__dump')['book']['購入']; h = d[0]
    return [dict(zip(h, r + ['']*(len(h)-len(r)))) for r in d[1:]]
def mails(): return [(m['to'], m['subject']) for m in R.gas_local('/__dump')['mails']]
def login(pw, drive, who):
    t = R.Take(pw, drive, who, '', R.CACHE/'video', R.CACHE/'shots', 'v51'); t.answers += [True]*10
    t.goto(); t.click('#btn-signin'); t.page.locator('#appmain').wait_for(state='visible', timeout=30000); t.idle(2000); return t
def fill(t, name, gross):
    t.page.fill('#f-name', name); t.page.fill('#f-why','x'); t.page.fill('#f-gross', str(gross)); t.page.locator('#ch-dept button').first.click()
with sync_playwright() as pw:
    drive = R.FakeDrive(D.CONFIG, D.PEOPLE)
    # ① 一般ユーザが出す → 担当の承認者へ
    t = login(pw, drive, D.SATO)
    fill(t, 'メール試験', 5500); t.page.locator('#f-files').set_input_files(str(fa)); t.page.click('#btn-submit')
    t.page.get_by_text('をチェックに出しました').first.wait_for(timeout=15000)
    print('①出したときの表示 :', t.page.locator('#toast').inner_text().replace('\n',' / ')[:90])
    print('  送ったメール     :', mails()[-1])
    # ③ 直す → すでに入っている証憑が出る・同じファイルは上げない
    t.idle(2500)
    t.page.locator('#my-list tr', has_text='メール試験').locator('[data-edit]').click()
    t.page.locator('#existing-ev li').first.wait_for(timeout=10000)
    print('③直す画面の一覧   :', t.page.locator('#existing-ev').inner_text().split('\n')[:3])
    t.page.locator('#f-files').set_input_files(str(fa)); t.idle(400)
    print('  同じファイル     :', t.page.locator('#filebox select').count(), '件追加 /', t.page.locator('#toast').inner_text().replace('\n',' / ')[-60:])
    t.page.locator('#f-files').set_input_files(str(fb)); t.idle(300)
    print('  別のファイル     :', t.page.locator('#filebox select').count(), '件追加')
    t.page.click('#btn-draft'); t.idle(2500)
    # 下書きから出す・10万円以上
    fill(t, '高額試験', 165000); t.page.click('#btn-submit'); t.page.get_by_text('をチェックに出しました').first.wait_for(timeout=15000)
    t.close()
    # 承認者がチェック → 社長へ
    t = login(pw, drive, D.SHONIN); t.tab('approve')
    t.page.locator('#approve-list div.card', has_text='高額試験').locator('[data-ok]').click(); t.idle(2500)
    print('①社長待ちのメール :', mails()[-1])
    t.close()
    # 承認者のいない部署（営業部の山本さん）→ 経理へ
    t = login(pw, drive, 'yamamoto@m2-labo.jp'); fill(t, '営業の試験', 3300); t.page.click('#btn-submit'); t.page.get_by_text('をチェックに出しました').first.wait_for(timeout=15000)
    print('①承認者なし→     :', mails()[-1]); t.close()
    # ② 承認後に埋める：本人はインボイスNo・検収日だけ
    t = login(pw, drive, D.SATO); t.tab('gaps')
    btn = t.page.locator('#gaps-list tr', has_text='B0006').locator('[data-fill]').first
    btn.click(); t.idle(400)
    print('②本人の埋める画面 : 項目欄', t.page.locator('#fl-item').count(), '／検収日欄', t.page.locator('#fl-acc').count())
    t.page.fill('#fl-acc', '2026-10-05'); t.page.fill('#fl-inv', 'T1111111111111'); t.page.click('#fl-save'); t.idle(2500)
    b6 = [r for r in rows() if r['id']=='B0006'][0]; print('  保存後 B0006     : 検収日', b6['検収日'], ' インボイスNo', b6['インボイスNo'], ' 状態', b6['状態'], ' 税込', b6['税込'])
    t.close()
    # 経理は項目も
    t = login(pw, drive, D.KEIRI); t.tab('ledger')
    b5 = [r for r in rows() if r['id']=='B0005'][0]
    t.page.evaluate("r => document.dispatchEvent(new Event('x'))", 0)
    t.tab('gaps')
    t.close()
    R.gas_call('update', D.KEIRI, sheet='購入', row=dict(b5, 項目='外注費'), rowIndex=[i for i,r in enumerate(rows()) if r['id']=='B0005'][0]+2, matchId='B0005')
    print('②経理が項目を変更 :', [r for r in rows() if r['id']=='B0005'][0]['項目'])
