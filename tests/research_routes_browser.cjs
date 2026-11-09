// Run against an isolated app instance with a disposable PS_DATA_DIR.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.ROUTE_TEST_URL;
if (!base) throw Error('Set ROUTE_TEST_URL to a disposable PaperScientist server.');

(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1360,height:900},reducedMotion:'reduce'});
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    const projectRequest = await page.request.post(base+'/api/projects',{data:{name:'路线界面验证'}});
    assert(projectRequest.ok()); const project = await projectRequest.json();
    const sessionRequest = await page.request.post(base+'/api/sessions?project_id='+project.id);
    assert(sessionRequest.ok()); const session=await sessionRequest.json();
    await page.goto(base+'/?session='+session.id,{waitUntil:'domcontentloaded'});
    await page.locator('.ps-session-marker[data-session="'+session.id+'"]').waitFor({state:'attached'});
    const tab=page.getByRole('tab',{name:'研究路线',exact:true});
    await tab.click();
    const panel=page.getByRole('region',{name:'项目研究路线'}), info=panel.getByRole('article');
    await panel.getByRole('button',{name:'从此分叉'}).click();
    await panel.getByLabel('新路线要验证什么？').fill('检查分层阈值能否降低误报');
    await panel.getByRole('button',{name:'创建分叉'}).click();
    await info.getByText('检查分层阈值能否降低误报',{exact:true}).waitFor();
    await panel.getByRole('button',{name:'编辑记录'}).click();
    await panel.getByLabel('路线状态').selectOption('stopped');
    await panel.getByLabel('结论或停止原因').fill('压力组的误报没有改善');
    await panel.getByLabel('下一步',{exact:true}).fill('回到固定阈值');
    await panel.getByRole('button',{name:'保存记录'}).click();
    await info.getByText('压力组的误报没有改善',{exact:true}).waitFor();
    assert.equal(await panel.getByLabel('基线会话').inputValue(),session.id);
    await panel.getByRole('button',{name:'比较',exact:true}).click();
    await panel.getByText(/完整独立运行/).waitFor();
    await panel.locator('.ps-route-files summary').waitFor();
    const childUrl = await info.getByRole('link',{name:'打开对话'}).getAttribute('href');
    const child = new URL(childUrl,base).searchParams.get('session');
    assert(child && child!==session.id);
    if (process.env.ROUTE_SCREENSHOTS) await panel.screenshot({path:process.env.ROUTE_SCREENSHOTS+'/desktop.png'});
    await page.setViewportSize({width:390,height:844});
    await info.scrollIntoViewIfNeeded();
    const width=await panel.evaluate(node => ({width:node.clientWidth,scroll:node.scrollWidth}));
    assert(width.scroll<=width.width+1,'route panel overflow at mobile width');
    if (process.env.ROUTE_SCREENSHOTS) await panel.screenshot({path:process.env.ROUTE_SCREENSHOTS+'/mobile.png'});
    await info.getByRole('link',{name:'打开对话'}).click();
    await page.locator('.ps-session-marker[data-session="'+child+'"]').waitFor({state:'attached'});
    await page.getByRole('tab',{name:'研究路线',exact:true}).click();
    await page.getByRole('article').getByText('压力组的误报没有改善',{exact:true}).waitFor();
    if (process.env.ROUTE_BASELINE_FIXTURE) {
      const [sourceId, receiverId] = process.env.ROUTE_BASELINE_FIXTURE.split(',');
      async function openLibrary(id) {
        await page.goto(base+'/?session='+encodeURIComponent(id));
        await page.locator('.ps-session-marker[data-session="'+id+'"]').waitFor({state:'attached'});
        await page.getByRole('tab',{name:'研究路线',exact:true}).click();
        await panel.getByText('跨项目基线',{exact:true}).click();
      }
      await openLibrary(sourceId);
      await panel.getByRole('button',{name:'生成基线引用'}).click();
      const reference = await panel.getByLabel('可复制的基线引用').inputValue();
      assert(reference.startsWith(sourceId+'/'));
      await openLibrary(receiverId);
      await panel.getByLabel('基线引用',{exact:true}).fill(reference);
      await panel.getByRole('button',{name:'引用基线',exact:true}).click();
      await panel.getByRole('button',{name:'对照已引用基线'}).click();
      await panel.getByRole('cell',{name:'0',exact:true}).waitFor();
      assert.equal(await panel.getByRole('cell',{name:'1 (n=1)',exact:true}).count(),2);
      console.log('Verified cross-project baseline selection, attachment and an independent equal-score run.');
    }
    assert.deepEqual(errors,[]);
    console.log('Passed desktop and mobile fork, notes, paired comparison, continue and persisted reload.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
