import sys, time; sys.path.insert(0, '/data/m2labo/choreia-budget/tools')
from playwright.sync_api import sync_playwright
import manual_rig as R, demo_data as D
D.seed()
S = R.CACHE/'samples'
fa, fb, fc = S/'見積書_サンプル照明株式会社.pdf', S/'請求書_サンプル農園株式会社.pdf', S/'見積書_サンプルセンサー株式会社.pdf'
def rows(sheet='購入'):
    d = R.gas_local('/__dump')['book'][sheet]; h = d[0]
    return [dict(zip(h, r + ['']*(len(h)-len(r)))) for r in d[1:]]
with sync_playwright() as pw:
    drive = R.FakeDrive(D.CONFIG, D.PEOPLE)
    t = R.Take(pw, drive, D.SATO, '', R.CACHE/'video', R.CACHE/'shots', 'v49')
    t.answers += [True]*10
    t.goto(); t.click('#btn-signin'); t.page.locator('#appmain').wait_for(state='visible', timeout=30000); t.idle(2000)
    # 1) 証憑を1つずつ足す・外す
    t.page.locator('#f-files').set_input_files(str(fa)); t.page.locator('#f-files').set_input_files(str(fb))
    print('1つずつ2回選んだ  :', t.page.locator('#filebox select').count(), '件', [x for x in t.page.locator('#filebox select').evaluate_all('a=>a.map(s=>s.value)')])
    t.page.locator('#f-files').set_input_files(str(fc)); t.page.locator('#filebox [data-fx="2"]').click()
    print('3つ目を足して外す :', t.page.locator('#filebox select').count(), '件')
    # 2) 下書きで保存 → 直す → 同じ番号のまま
    t.page.fill('#f-name','下書きテスト'); t.page.fill('#f-why','x'); t.page.fill('#f-gross','1100'); t.page.locator('#ch-dept button').first.click()
    up0 = drive.n; t.page.click('#btn-draft'); t.idle(3000)
    d = [r for r in rows() if r['品名']=='下書きテスト'][0]
    print('下書き保存         :', d['id'], d['状態'], '見積書=',d['見積書'], '請求書=',d['請求書'], '| Driveへの書込回数', drive.n-up0)
    t.idle(1500)
    t.page.locator('#my-list tr', has_text='下書きテスト').locator('[data-edit]').click(); t.idle(800)
    print('直すのバナー       :', t.page.locator('#edit-banner').inner_text()[:40].replace('\n',' '))
    t.page.fill('#f-name','下書きテスト（直した）'); t.page.click('#btn-submit'); t.idle(3000)
    d2 = [r for r in rows() if r['id']==d['id']][0]
    print('直して出した       :', d2['id'], d2['状態'], d2['品名'], '| 同じ番号の行数', sum(1 for r in rows() if r['id']==d['id']))
    # 3) 取り下げ → 写して出し直す → 新しい番号
    t.idle(1500)
    t.page.locator('#my-list tr', has_text='下書きテスト（直した）').locator('[data-wd]').click(); t.idle(3000)
    t.page.locator('#my-list tr', has_text='下書きテスト（直した）').locator('[data-copy]').click(); t.idle(800)
    print('写した後のバナー   :', t.page.locator('#edit-banner').count(), '（0=新規として出す）  品名欄=', t.page.input_value('#f-name'))
    t.page.click('#btn-submit'); t.idle(3000)
    same = [r for r in rows() if r['品名']=='下書きテスト（直した）']
    print('写して出し直した   :', [(r['id'], r['状態']) for r in same])
    # 4) 証憑を上げる画面：2回に分けて選ぶ・種類はファイルごと
    t.idle(1500)
    t.page.locator('#my-list tr', has_text='B0006').locator('[data-ev]').click(); t.idle(500)
    t.page.locator('#m-file').set_input_files(str(fb)); t.page.locator('#m-file').set_input_files(str(fa))
    print('上げる画面         :', t.page.locator('#m-files select').count(), '件', t.page.locator('#m-files select').evaluate_all('a=>a.map(s=>s.value)'))
    t.page.click('#m-up'); t.idle(3000)
    b6 = [r for r in rows() if r['id']=='B0006'][0]
    print('B0006 の証憑       : 請求書=', b6['請求書'], ' 見積書=', b6['見積書'])
    t.close()
# 5) 承認済みの記入で、証憑以外（金額・状態）を書き換えようとしても変わらないこと
b = [r for r in rows() if r['id']=='B0006'][0]
d = R.gas_local('/__dump')['book']['購入']; idx = [i for i,r in enumerate(d) if r and r[0]=='B0006'][0]
evil = dict(b); evil['税込']='1'; evil['状態']='支払済'; evil['領収書']='TRUE'
res = R.gas_call('update', D.SATO, sheet='購入', row=evil, rowIndex=idx+1, matchId='B0006')
a = [r for r in rows() if r['id']=='B0006'][0]
print('書き換え試験       :', res, '| 税込', b['税込'],'→',a['税込'], '| 状態', b['状態'],'→',a['状態'], '| 領収書', b['領収書'] or '空','→',a['領収書'])
# 6) 他人の承認済み記入には証憑も付けられないこと
k = [r for r in rows() if r['id']=='B0005'][0]
idx5 = [i for i,r in enumerate(d) if r and r[0]=='B0005'][0]
k2 = dict(k); k2['請求書']='TRUE'
print('他人の記入         :', R.gas_call('update', D.SATO, sheet='購入', row=k2, rowIndex=idx5+1, matchId='B0005'))
