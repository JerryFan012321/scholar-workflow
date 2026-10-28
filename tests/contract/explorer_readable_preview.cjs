// Exercise the real preview service; source quotes come from the production analysis renderer.
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const fixture = JSON.parse(input), parsed = new URL(fixture.url), origin = parsed.origin;
  const token = new URLSearchParams(parsed.hash.slice(1)).get('token');
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1200}});
    page.setDefaultTimeout(3000);
    await page.addInitScript(() => {
      const create = URL.createObjectURL.bind(URL);
      window.__readablePreviewBlobs = new Map();
      URL.createObjectURL = blob => {
        const url = create(blob);
        window.__readablePreviewBlobs.set(url, blob);
        return url;
      };
    });
    const errors = [], external = [], mediaRequests = [], launches = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin !== origin) external.push(request.url());
      if (url.pathname.startsWith('/api/preview-media/')) mediaRequests.push(request);
      if (['/api/open', '/api/open-link'].includes(url.pathname)) launches.push(request.url());
    });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    await page.goto(fixture.url);
    await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
    await page.locator('.result-card').filter({hasText: '合成可读论文单元'}).click();
    const previewResponse = page.waitForResponse(response =>
      new URL(response.url()).pathname === '/api/preview/paper/body').catch(() => null);
    const mediaResponse = page.waitForResponse(response =>
      new URL(response.url()).pathname.startsWith('/api/preview-media/')).catch(() => null);
    await page.locator('.asset-card').filter({hasText: '分析正文'})
      .getByRole('button', {name: '预览', exact: true}).click();
    const host = page.locator('#preview-body');
    const direct = host.locator('details').filter({has: page.locator('summary').filter({hasText: '原文摘录（粗体：直接证据）'})});
    const inference = host.locator('details').filter({has: page.locator('summary').filter({hasText: '原文摘录（粗体：推断依据）'})});
    await direct.waitFor(); await inference.waitFor();
    assert.equal(await direct.evaluate(details => details.open), false);
    assert.equal(await inference.evaluate(details => details.open), false);
    assert.equal(await direct.getByRole('button', {name: '原文·PDF 第 4 页', exact: true}).isVisible(), true);
    assert.equal(await inference.getByRole('button', {name: '原文·PDF 第 5 页', exact: true}).isVisible(), true);
    assert.equal(await host.locator('a[href^="obsidian:"],a[href^="zotero:"]').count(), 0);
    for (const [callout, quote, emphasis] of [
      [direct, fixture.author_quote, fixture.author_emphasis],
      [inference, fixture.inference_quote, fixture.inference_emphasis],
    ]) {
      await callout.locator('summary').focus(); await callout.locator('summary').press('Enter');
      assert.equal(await callout.evaluate(details => details.open), true);
      assert.ok((await callout.textContent()).replace(/\s+/g, ' ').includes(quote));
      assert.deepEqual(await callout.locator('strong').allTextContents(), [emphasis]);
    }
    assert.equal(await host.locator('p').filter({hasText: fixture.paragraph_1}).count(), 1);
    assert.equal(await host.locator('p').filter({hasText: fixture.paragraph_2}).count(), 1);
    assert.equal(await host.locator('ul > li').count(), 2);
    assert.match(await host.locator('ul').textContent(), /共同条件.*相同的合成输入和预算/);
    assert.match(await host.locator('ul').textContent(), /变化项.*仅替换合成模块/);
    const table = host.getByRole('table');
    assert.deepEqual(await table.getByRole('columnheader').allTextContents(), ['配置', '共同条件', '差别', '合成结果']);
    assert.equal(await table.getByRole('row').count(), 3);
    assert.deepEqual(await table.getByRole('row').nth(1).getByRole('cell').allTextContents(), ['baseline', '同一合成输入、相同预算', '原模块', '42']);
    assert.deepEqual(await table.getByRole('row').nth(2).getByRole('cell').allTextContents(), ['variant', '同一合成输入、相同预算', '新模块', '36']);
    const image = host.getByRole('img', {name: '合成对比图', exact: true});
    await image.waitFor();
    assert.deepEqual(await image.evaluate(element => ({width: element.naturalWidth, height: element.naturalHeight, complete: element.complete})), {width: 320, height: 120, complete: true});
    const caption = host.getByText(fixture.caption, {exact: true}); await caption.waitFor();
    const after = host.getByText(fixture.after_image, {exact: true}); await after.waitFor();
    assert.equal(await image.evaluate((element, next) => !!(element.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING), await caption.elementHandle()), true);
    assert.equal(await caption.evaluate((element, next) => !!(element.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING), await after.elementHandle()), true);
    const response = await previewResponse, raster = await mediaResponse;
    assert.ok(response && raster, 'Declared images must use the real preview/media service');
    assert.equal(response.status(), 200); assert.equal(raster.status(), 200);
    const preview = await response.json();
    assert.equal(preview.text, fixture.text); assert.equal(preview.document_revision, fixture.document_revision);
    assert.equal(preview.images.length, 4);
    const declared = preview.images.find(entry => entry.label === '合成对比图');
    assert.equal(typeof declared.media_id, 'string');
    assert.equal(preview.text.slice(declared.start, declared.end), '![合成对比图](figures/result.png)');
    for (const label of ['未知图片', '远程图片', 'SVG图片']) {
      const unavailable = preview.images.find(entry => entry.label === label);
      assert.equal(typeof unavailable.reason_code, 'string'); assert.equal(Object.hasOwn(unavailable, 'media_id'), false);
      assert.equal(await host.getByRole('img', {name: label, exact: true}).count(), 0);
      assert.ok((await host.textContent()).includes(label));
    }
    assert.match(raster.headers()['content-type'], /^image\/png/);
    // Chrome can discard a no-store response from its network-body cache after Blob consumption.
    // Hash the actual displayed Blob instead, while retaining HTTP identity/auth/length checks.
    assert.match(await image.getAttribute('src'), /^blob:/);
    const rasterBytes = Buffer.from(await image.evaluate(async element =>
      Array.from(new Uint8Array(await window.__readablePreviewBlobs.get(element.src).arrayBuffer()))));
    assert.equal(raster.request().method(), 'GET');
    assert.equal(rasterBytes.length, Number(raster.headers()['content-length']));
    assert.equal(createHash('sha256').update(rasterBytes).digest('hex'), fixture.png_hash);
    assert.equal(mediaRequests.length, 1);
    assert.equal(mediaRequests[0].headers().authorization, 'Bearer ' + token);
    assert.equal(new URL(mediaRequests[0].url()).search, '');
    const bodyText = await host.textContent();
    assert.equal(bodyText.includes('sw_catalog_id'), false);
    assert.equal(bodyText.includes('fixture-analysis'), false);
    assert.equal(bodyText.includes('^claim-task-core'), false);
    assert.ok((await host.locator('pre').textContent()).includes('^claim-literal'));
    assert.equal(await host.getByRole('button', {name: '代码内伪原文', exact: true}).count(), 0);
    assert.equal(await host.getByRole('link', {name: '代码内伪原文', exact: true}).count(), 0);
    assert.equal(await host.locator('script').count(), 0);
    assert.equal(await page.evaluate('window.__previewXss'), undefined);
    assert.deepEqual(external, []); assert.deepEqual(launches, []); assert.deepEqual(errors, []);
    if (process.env.SCHOLAR_EXPLORER_READABLE_SCREENSHOT) {
      const screenshot = process.env.SCHOLAR_EXPLORER_READABLE_SCREENSHOT;
      await host.evaluate(element => { element.scrollTop = 0; });
      await page.screenshot({path: screenshot});
      await image.evaluate(element => {
        const host = document.getElementById('preview-body');
        host.scrollTop += element.getBoundingClientRect().top - host.getBoundingClientRect().top - 60;
      });
      const figureScreenshot = /\.png$/i.test(screenshot)
        ? screenshot.replace(/\.png$/i, '-figure.png') : screenshot + '-figure.png';
      await page.screenshot({path: figureScreenshot});
    }
    for (const callout of [direct, inference]) {
      await callout.locator('summary').focus(); await callout.locator('summary').press('Enter');
      assert.equal(await callout.evaluate(details => details.open), false);
    }
    await page.locator('#close-preview').click();
    await page.locator('.asset-card').filter({hasText: '代码原文'})
      .getByRole('button', {name: '预览', exact: true}).click();
    await host.locator('pre').waitFor();
    assert.equal(await host.locator('pre').count(), 1);
    assert.equal(await host.locator('pre').textContent(), fixture.code);
    assert.equal(await host.locator('details,img,a,button').count(), 0);
    assert.equal(await host.textContent(), fixture.code);
    assert.deepEqual(external, []); assert.deepEqual(launches, []); assert.deepEqual(errors, []);
    console.log('PASS: real renderer folded quotes/emphasis, prose/list/table, authenticated raster/caption order, inert unsupported media/HTML and unchanged assets');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
