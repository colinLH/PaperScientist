// Set COMPOSER_TEST_URL to a disposable local PaperScientist server running in demo mode.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function verify() {
  const base = new URL(process.env.COMPOSER_TEST_URL);
  assert(['localhost', '127.0.0.1'].includes(base.hostname));
  const browser = await chromium.launch({channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1366, height: 768}, reducedMotion: 'reduce'});
    const api = page.request;
    assert.equal((await (await api.get(new URL('/api/health', base).href)).json()).model, 'demo');
    const project = await (await api.post(new URL('/api/projects', base).href, {data: {name: '输入区布局验证'}})).json();
    const session = await (await api.post(new URL('/api/sessions', base).href, {params: {project_id: project.id, dedicated: true}})).json();
    await page.goto(new URL('/?session=' + session.id, base).href);
    await page.locator('.ps-session-marker[data-session="' + session.id + '"]').waitFor({state:'attached'});

    const draft = page.locator('#query textarea');
    const history = page.locator('.ps-scroll');
    const controls = ['#composer', '#query textarea', '#attach', '#settings-toggle', '#model-picker', '#send, #stop'];
    async function geometry(label, bounds) {
      const state = await page.evaluate(({controls, bounds}) => {
        const top = bounds?.top ?? 0;
        const bottom = top + (bounds?.height ?? innerHeight);
        const boxes = controls.map(selector => {
          const n = [...document.querySelectorAll(selector)].find(el => el.getBoundingClientRect().height);
          if (!n) return {selector, visible:false};
          const r = n.getBoundingClientRect();
          return {selector, visible:r.left >= -1 && r.right <= innerWidth + 1 && r.top >= top - 1 && r.bottom <= bottom + 1};
        });
        const footer = document.querySelector('#composer').getBoundingClientRect();
        return {boxes, bottomGap: bottom - footer.bottom, pageScroll: scrollY, docHeight: document.scrollingElement.scrollHeight};
      }, {controls, bounds});
      for (const box of state.boxes) assert(box.visible, label + ' ' + box.selector + ' extends outside viewport');
      assert(state.bottomGap >= 0 && state.bottomGap <= 54, label + ' composer not docked: ' + state.bottomGap);
      assert.equal(state.pageScroll, 0, label + ' document scrolled');
      return state.bottomGap;
    }
    await geometry('empty chat');
    await draft.fill(Array.from({length: 100}, (_, i) => '测试消息第 ' + i + ' 行。').join('\n'));
    await geometry('multiline draft');
    await page.locator('#send').click();
    await page.locator('.ps-turn .ps-question').first().waitFor();
    await page.locator('#send').waitFor();
    await page.waitForFunction(() => document.querySelector('.ps-scroll').scrollHeight > document.querySelector('.ps-scroll').clientHeight);
    for (const [width, height] of [[1366,768],[768,650],[390,844],[320,480],[740,360]]) {
      await page.setViewportSize({width, height});
      const bottom = await geometry(width+'px');
      const scroll = await history.evaluate(n => { n.scrollTop=n.scrollHeight; return n.scrollTop; });
      assert(scroll > 0);
      const box = await history.boundingBox();
      await page.mouse.move(box.x + box.width/2, box.y + box.height/2);
      await page.mouse.wheel(0, -480);
      await page.waitForFunction(prior => document.querySelector('.ps-scroll').scrollTop < prior, scroll);
      assert(Math.abs(await geometry('scrolled '+width)-bottom)<1);
      await draft.fill('继续验证\n'.repeat(11));
      await geometry('expanded '+width);
      await draft.fill('');
    }
    await page.setViewportSize({width:390, height:844});
    await page.locator('#settings-toggle').click();
    await page.locator('#settings-panel input[type=password]').waitFor();
    await page.locator('#settings-panel input[type=password]').focus();
    await geometry('expanded settings');
    await page.locator('#settings-toggle').click();
    await page.locator('#settings-panel').waitFor({state:'hidden'});

    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.locator('#attach').click()
    ]);
    await chooser.setFiles(Array.from({length:4}, (_,i)=>({
      name: '论文实验记录-'+i+'-非常长的附件名称.txt', mimeType: 'text/plain', buffer: Buffer.from('example')
    })));
    await page.locator('.attachment-chips span').nth(3).waitFor();
    await geometry('attachments');
    await page.locator('#model-picker input').click();
    await page.getByRole('option').first().waitFor();
    await page.keyboard.press('Escape');

    // Model a browser whose layout viewport stays tall when its visual viewport shrinks and pans.
    await draft.focus();
    await page.evaluate(() => {
      Object.defineProperties(visualViewport, {height:{configurable:true,value:350}, offsetTop:{configurable:true,value:20}});
      visualViewport.dispatchEvent(new Event('resize'));
      visualViewport.dispatchEvent(new Event('scroll'));
    });
    await draft.fill('换行\n'.repeat(15));
    await geometry('keyboard + attachments', {top:20,height:350});
    await page.evaluate(() => {
      delete visualViewport.height; delete visualViewport.offsetTop;
      visualViewport.dispatchEvent(new Event('resize'));
    });
    await geometry('keyboard closed');
    await page.locator('#clear-attachments').click();
    await page.locator('.attachment-chips span').first().waitFor({state:'hidden'});
    await page.setViewportSize({width:1366,height:768});
    await page.getByRole('tab',{name:'产物与图表'}).click();
    await page.locator('#composer').waitFor({state:'hidden'});
    await page.locator('#workspace-experiments').waitFor();
    await page.getByRole('tab',{name:'对话',exact:true}).click();
    await geometry('returned to chat');
    console.log('Verified empty and long chat, wheel scrolling, multi-line drafts, settings, attachments, model menu, visual viewport and tab switching.');
  } finally {
    await browser.close();
  }
}
verify().catch(error => { console.error(error); process.exitCode = 1; });
