"""v54 の通し試験：書き込み役の版ずれ（2026-10-27 ta.suzukiさんの「チェックする」が空だった件）。
本番の書き込み役が 9/29 朝の版（3d8236e）のままで、承認者への振り分けが「費用負担部門の一致」だけだった。
古い版と今の版で同じデータを流し、承認者に届くか・管理者に「古い版」が出るか・版が上がったら列が足されるかを見る。
gas-mock はこの試験が自分で起動・停止する（8787 番を空けておくこと）。"""
import os, subprocess, sys, time
sys.path.insert(0, '/data/m2labo/choreia-budget/tools')
from playwright.sync_api import sync_playwright
import manual_rig as R, demo_data as D

ROOT = '/data/m2labo/choreia-budget'
OLD = os.path.join(R.CACHE, 'Code_3d8236e.gs')
# 承認者=企画開発、記入者=企画開発。記入の費用負担部門は企画製造部（承認者の部署と違う）
D.PURCHASES.append(D.P('B0090', '2026-10-27 10:00', D.SATO, 'チェック待ち', '企画製造部', '備品消耗品_その他',
                       '部署違いの記入', 'x', 'サンプル', 3300, 請求書='TRUE'))

def mock(code):
    env = dict(os.environ, CODE_GS=code)
    p = subprocess.Popen(['node', 'tools/gas-mock.js', '8787'], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5); D.seed(); return p

def login(pw, who, keep=None):
    t = R.Take(pw, R.FakeDrive(D.CONFIG, D.PEOPLE), who, '', R.CACHE/'video', R.CACHE/'shots', 'gv')
    # 前の起動の「準備済み」の印を持ち越す（実際のブラウザと同じ）
    if keep: t.page.add_init_script('(function(k){ for(var n in k) localStorage.setItem(n, k[n]); })(%s)' % keep)
    t.goto(); t.click('#btn-signin'); t.page.locator('#appmain').wait_for(state='visible', timeout=30000); t.idle(2000); return t

def heads(sheet): return R.gas_local('/__dump')['book'][sheet][0]

subprocess.run('git show 3d8236e:apps-script/Code.gs > ' + OLD, shell=True, cwd=ROOT, check=True)
with sync_playwright() as pw:
    for label, code in (('古い版(9/29朝)', OLD), ('今の版', os.path.join(ROOT, 'apps-script', 'Code.gs'))):
        p = mock(code)
        try:
            t = login(pw, D.SHONIN); t.tab('approve')
            print(label, '承認者のチェックする :', t.page.locator('#approve-list div.card', has_text='B0090').count(), '件（部署違いの記入）')
            t.close()
            t = login(pw, D.KEIRI)
            msg = t.page.locator('#toast').inner_text()
            print(label, '管理者への知らせ     :', '古い版と出る' if '古い版' in msg else '出ない')
            t.close()
        finally:
            p.terminate(); p.wait()
    # 版が上がったら準備をやり直して、足りない列を足す（貼り直したあと誰も何もしなくてよい）
    p = mock(os.path.join(ROOT, 'apps-script', 'Code.gs'))
    try:
        book = R.gas_local('/__dump')['book']
        book['入金'][0] = [h for h in book['入金'][0] if h != '記入者メール']
        R.gas_local('/__reset', book)
        print('貼り直し前の入金の列 : 記入者メール', '有' if '記入者メール' in heads('入金') else '無')
        t = login(pw, D.SATO, keep='{"cb_ready_4_DEMO_SS":"1","cb_ready_4_0_DEMO_SS":"1"}')
        print('貼り直し後に開いた後 : 記入者メール', '有' if '記入者メール' in heads('入金') else '無')
        t.close()
    finally:
        p.terminate(); p.wait()
