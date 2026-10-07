"""v53 の通し試験：項目は記入する人が入れる。空なら承認者が差し戻す（名波さん 2026-10-07 のフロー）。"""
import sys; sys.path.insert(0, '/data/m2labo/choreia-budget/tools')
from playwright.sync_api import sync_playwright
import manual_rig as R, demo_data as D
D.PURCHASES.append(D.P('B0013', '2026-10-06 10:00', D.SATO, '承認済', '企画製造部', '', '送料(5件分)', 'x', 'ヤマト', 5599))
D.PURCHASES.append(D.P('B0014', '2026-10-06 11:00', D.KOBA, 'チェック待ち', 'D-base', '', '古い記入（項目なし）', 'x', 'サンプル', 2200))
D.seed()
def row(i):
    d = R.gas_local('/__dump')['book']['購入']; h = d[0]
    return [dict(zip(h, r + ['']*(len(h)-len(r)))) for r in d[1:] if r and r[0]==i][0]
def login(pw, who):
    t = R.Take(pw, R.FakeDrive(D.CONFIG, D.PEOPLE), who, '', R.CACHE/'video', R.CACHE/'shots', 'rf')
    t.goto(); t.click('#btn-signin'); t.page.locator('#appmain').wait_for(state='visible', timeout=30000); t.idle(2000); return t
with sync_playwright() as pw:
    t = login(pw, D.SATO)
    t.page.fill('#f-name','項目なしで出す'); t.page.fill('#f-why','x'); t.page.fill('#f-gross','1100'); t.page.locator('#ch-dept button').first.click()
    t.page.click('#btn-submit'); t.idle(800)
    print('①項目なしで出す   :', t.page.locator('#form-err').inner_text().strip())
    t.close()
    t = login(pw, D.SHONIN)
    t.tab('approve'); c = t.page.locator('#approve-list div.card', has_text='B0014')
    print('②古い記入の確認   : チェック済ボタン有効=', c.locator('button', has_text='チェック済にする').is_enabled(), '|', c.locator('.p-bad').inner_text())
    t.tab('ledger'); print('③台帳のB0013      : 差し戻すボタン', t.page.locator('#ledger tr', has_text='B0013').locator('[data-rej]').count())
    t.tab('gaps'); g = t.page.locator('#gaps-list tr', has_text='B0013'); print('  抜けているもの   :', g.locator('[data-rej]').count(), '差し戻す /', g.locator('[data-fill]').count(), '埋める')
    t.answers.append('項目が入っていないので、選んで出し直してください'); g.locator('[data-rej]').first.click(); t.idle(2500)
    print('  差し戻した後     :', row('B0013')['状態'], '/', row('B0013')['差戻理由'])
    t.close()
    t = login(pw, D.SATO)
    r = t.page.locator('#my-list tr', has_text='B0013'); print('④浅田さん側       :', r.inner_text().replace('\t',' | ').replace('\n',' / ')[:110])
    r.locator('[data-edit]').click(); t.idle(600)
    t.page.locator('#ch-item [data-more]').click(); t.page.locator('#ch-item select').select_option('備品消耗品_その他'); t.idle(300)
    t.page.click('#btn-submit'); t.idle(2500)
    print('  直して出した後   :', row('B0013')['状態'], '/ 項目=', row('B0013')['項目'])
    t.close()
    t = login(pw, D.SHONIN); t.tab('approve')
    c = t.page.locator('#approve-list div.card', has_text='B0013')
    print('⑤承認者がもう一度 : チェック済ボタン有効=', c.locator('button', has_text='チェック済にする').is_enabled())
    t.close()
