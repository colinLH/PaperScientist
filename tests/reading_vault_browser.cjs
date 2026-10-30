// Run against an isolated local test server: this exercises real settings writes.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path');
(async()=>{
  const base=process.env.READING_BASE_URL;
  assert.ok(base && process.env.READING_ALLOW_CONFIG_TEST==='1','Use an isolated local server and READING_ALLOW_CONFIG_TEST=1');
  const output=process.env.READING_SCREENSHOTS || '.test-output/reading-portable';fs.mkdirSync(output,{recursive:true});
  const vault=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'Obsidian 本地仓库 ')));
  fs.writeFileSync(path.join(vault,'已有论文.md'),'---\ntype: paper\ntitle: 已有本地论文\narxiv_id: 2601.12345v1\n---\n# 已有笔记\n![[figure.png]]');
  fs.writeFileSync(path.join(vault,'figure.png'),Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=','base64'));
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let original;
  try {
    original=(await (await page.request.get(base+'/api/reading/status')).json()).config;
    await page.route('**/api/reading/vaults',route=>route.fulfill({json:{config:original,vaults:[{name:'我的仓库',path:vault}]}}));
    await page.goto(base+'/reading');
    await page.locator('#configure-vault').click();
    await page.locator('#detected-vaults').selectOption(vault);
    await page.locator('#vault-prefix').fill('.');
    assert.equal(await page.locator('#include-notes').isChecked(),true);
    await page.locator('#preview-vault').click();
    await page.getByText('可阅读 1 篇笔记，1 篇论文参与去重。').waitFor();
    await page.screenshot({path:output+'/connect-desktop.png'});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.locator('#vault-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth));
    await page.screenshot({path:output+'/connect-mobile.png'});
    await page.locator('#save-vault').click();
    await page.locator('#vault-dialog').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'已有本地论文',exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('#report-body img')].length===1&&document.querySelector('#report-body img').naturalWidth>0);
    await page.locator('#close-report').click();
    fs.writeFileSync(path.join(vault,'新增.md'),'# 刚加入 Obsidian 的笔记');
    await page.locator('#refresh').click();
    await page.getByRole('button',{name:'新增',exact:true}).waitFor();
    await page.reload();
    await page.getByRole('button',{name:'新增',exact:true}).waitFor();
    assert.equal(await page.locator('#paper-total').innerText(),'1');
    await page.locator('#configure-vault').click();
    await page.locator('#vault-root').fill(vault+'/not-found');
    await page.locator('#preview-vault').click();
    await page.getByText('请选择运行 PaperScientist 的电脑上已存在的仓库绝对路径').waitFor();
    assert.equal(await page.locator('#save-vault').isEnabled(),false);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({real_preview_save:true,dynamic_notes:true,wikilink_image:true,reload:true,mobile:true,errors}));
  } finally {
    if(original) {const restore=await page.request.post(base+'/api/reading/archive',{data:original});assert.equal(restore.ok(),true);}
    await browser.close();fs.rmSync(vault,{recursive:true,force:true});
  }
})().catch(e=>{console.error(e);process.exit(1)});
