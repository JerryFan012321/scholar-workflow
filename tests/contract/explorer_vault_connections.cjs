// Run against an actual isolated server whose picker selects one synthetic Vault.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {url, title, documentPath, expectedText, screenshotPath, inspectionScreenshotPath} = JSON.parse(input);
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1550, height: 1000}});
    page.setDefaultTimeout(5000);
    const errors = [], writes = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.method() === 'POST') writes.push({path: new URL(request.url()).pathname, body: request.postDataJSON()});
    });
    page.on('dialog', dialog => { throw new Error('Unexpected native browser dialog: ' + dialog.type()); });
    await page.route('**/*', route => new URL(route.request().url()).origin === new URL(url).origin
      ? route.continue() : route.abort());
    await page.goto(url);
    await page.locator('#environment-label').filter({hasText: '测试'}).waitFor();
    await page.waitForFunction(() => typeof data === 'object' && Array.isArray(data.works));
    await page.locator('#add-dimension').click();
    await page.getByLabel('名称', {exact: true}).fill('未保存的测试维度');
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.locator('#editor').waitFor({state: 'hidden'});
    const original = await page.evaluate('JSON.stringify({data,revision,dirty,selected,selection})');
    assert.equal(await page.evaluate('dirty'), true);

    await page.locator('#add-vault').click();
    await page.locator('#vault-dialog[open]').waitFor();
    await page.locator('#vault-title').filter({hasText: title}).waitFor();
    await page.locator('#vault-layers').getByText('安全阅读', {exact: true}).waitFor();
    await page.locator('#vault-layers').getByText('论文单元引用', {exact: true}).waitFor();
    await page.locator('#vault-layers').getByText('插件维护', {exact: true}).waitFor();
    const layerText = await page.locator('#vault-layers').textContent();
    assert.match(layerText, /文档现在可以阅读/);
    assert.equal(layerText.includes('Documents can be read now'), false);
    assert.equal(layerText.includes('Existing accepted packages remain unchanged'), false);
    await page.locator('#vault-adjustments').click();
    await page.locator('#vault-changes').waitFor({state: 'visible'});
    const changesText = await page.locator('#vault-changes').textContent();
    assert.match(changesText, /登记只读连接 · 本机连接登记/);
    assert.match(changesText, /准备领域登记/);
    assert.equal(changesText.includes('host-registry'), false);
    assert.equal(changesText.includes('Record the selected folder'), false);
    if (inspectionScreenshotPath) await page.screenshot({path: inspectionScreenshotPath, fullPage: true});
    assert.equal(await page.evaluate('JSON.stringify({data,revision,dirty,selected,selection})'), original);
    await page.locator('#vault-connect').click();
    await page.locator('#vault-dialog').waitFor({state: 'hidden'});
    await page.locator('#vault-connections button').filter({hasText: title}).click();
    await page.locator('#vault-documents[open]').waitFor();
    await page.locator('#vault-document-list button').filter({hasText: documentPath}).click();
    await page.locator('#vault-document-body').filter({hasText: expectedText}).waitFor();
    if (screenshotPath) await page.screenshot({path: screenshotPath, fullPage: true});
    assert.equal(await page.evaluate('JSON.stringify({data,revision,dirty,selected,selection})'), original,
      'Vault connections and reading must preserve the current research draft');
    assert.equal(writes.filter(request => request.path === '/api/save').length, 0);
    for (const request of writes.filter(request => request.path.startsWith('/api/vaults/'))) {
      assert.equal(JSON.stringify(request.body).includes('/Users/'), false,
        'Browser requests must use candidate/connection IDs, not host absolute paths');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: isolated Vault onboarding, three layers, preview, read-only documents and preserved draft');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
