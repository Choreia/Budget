"""保存にかかる時間を測る。書き込み役（本物のCode.gs, tools/gas-mock.js）とドライブに遅れを入れて、ボタンが戻るまでの秒数を出す。
  node tools/gas-mock.js 8787 &
  python3 tools/speed_test.py 版の名前
"""
import sys, time, json, re, asyncio, urllib.request; sys.path.insert(0, '/data/m2labo/choreia-budget/tools')
from playwright.async_api import async_playwright
import manual_rig as R, demo_data as D
GAS_DELAY, DRIVE_DELAY = 2.0, 0.5
def post_gas(body): return urllib.request.urlopen(urllib.request.Request(R.GAS_LOCAL + '/', data=body.encode(), method='POST')).read()
async def run(who, label):
    D.seed()
    loop = asyncio.get_running_loop()
    calls = []; n = {'i': 0}
    async with async_playwright() as pw:
        b = await pw.chromium.launch(executable_path='/usr/bin/google-chrome')
        ctx = await b.new_context(viewport={'width':1280,'height':800})
        await ctx.add_init_script(f"localStorage.setItem('demo_email', {json.dumps(who)})")
        async def gis(r): await r.fulfill(status=200, content_type='text/javascript', body=R.FAKE_GIS)
        async def app(r): await r.fulfill(status=200, content_type='text/html; charset=utf-8', body=(R.ROOT/'index.html').read_text('utf-8'))
        async def gas(r):
            body = r.request.post_data or ''; calls.append((round(time.time()-T0[0],1) if T0[0] else -1, json.loads(body).get('action')))
            await asyncio.sleep(GAS_DELAY)
            out = await loop.run_in_executor(None, post_gas, body)
            await r.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin':'*'}, body=out)
        async def drive(r):
            await asyncio.sleep(DRIVE_DELAY)
            u, m = r.request.url, r.request.method
            j = lambda o: r.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin':'*'}, body=json.dumps(o))
            if m == 'OPTIONS': return await r.fulfill(status=204, headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'})
            if '/about' in u: return await j({'user':{'emailAddress':who,'displayName':D.PEOPLE[who]}})
            if 'alt=media' in u: return await j(D.CONFIG)
            if '/upload/' in u: n['i']+=1; return await j({'id':'U%d'%n['i']})
            if m=='GET' and '/files?' in u:
                return await j({'files':[{'id':'cfg'}]} if 'choreia-budget-config' in urllib.request.unquote(u) else {'files':[{'id':'ROOT'}]})
            if m=='POST' and re.search(r'/files\?', u): n['i']+=1; return await j({'id':'F%d'%n['i'],'webViewLink':'https://drive.google.com/drive/folders/F%d'%n['i']})
            return await j({})
        await ctx.route('https://accounts.google.com/**', gis); await ctx.route(R.APP_URL+'*', app)
        await ctx.route(R.GAS_URL+'*', gas); await ctx.route('https://www.googleapis.com/**', drive)
        p = await ctx.new_page()
        await p.goto(R.APP_URL); await p.click('#btn-signin')
        await p.locator('#appmain').wait_for(state='visible', timeout=90000); await p.wait_for_timeout(9000)
        await p.fill('#f-name','速度テスト'); await p.fill('#f-why','x'); await p.fill('#f-gross','2200')
        await p.locator('#ch-dept button').first.click()
        await p.locator('#f-files').set_input_files(str(R.CACHE/'samples'/'請求書_サンプル農園株式会社.pdf'))
        calls.clear(); T0[0] = time.time(); labels = []
        await p.click('#btn-submit')
        while True:
            l = await p.locator('#btn-submit').inner_text()
            if not labels or labels[-1][1] != l: labels.append((round(time.time()-T0[0],1), l))
            if await p.locator('#btn-submit').is_enabled() and (await p.input_value('#f-name'))=='': break
            await asyncio.sleep(0.1)
        t1 = time.time()-T0[0]
        await p.locator('#my-list tr', has_text='速度テスト').first.wait_for(timeout=60000)
        t2 = time.time()-T0[0]
        await p.wait_for_timeout(9000)
        print(f'[{label}] {who:22s} 戻るまで {t1:4.1f}秒 / 一覧に出るまで {t2:4.1f}秒')
        print('     ボタンの表示:', labels)
        print('     書き込み役:', calls)
        await b.close()
T0 = [0]
async def main():
    for who in (D.KEIRI, D.SATO): await run(who, sys.argv[1])
asyncio.run(main())
