// Keep Markdown/source locators real; only the Python fixture replaces external applications.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const fixture = JSON.parse(input), origin = new URL(fixture.url).origin;
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1000}});
    page.setDefaultTimeout(3000);
    const errors = [], requests = [], externalRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin !== origin) externalRequests.push(request.url());
      if (url.pathname.startsWith('/api/reading-link/') || url.pathname === '/api/open-link') {
        requests.push({method: request.method(), pathname: url.pathname, search: url.search,
          body: request.method() === 'POST' ? request.postDataJSON() : null});
      }
    });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    await page.goto(fixture.url);
    await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
    await page.locator('.result-card').filter({hasText: '合成论文单元'}).click();
    const previewResponse = page.waitForResponse(response =>
      new URL(response.url()).pathname === '/api/preview/paper/body').catch(() => null);
    await page.locator('.asset-card').filter({hasText: '论文分析正文'})
      .getByRole('button', {name: '预览', exact: true}).click();
    const host = page.locator('#preview-body');
    const source = host.getByRole('button', {name: fixture.source_label, exact: true});
    await source.waitFor();
    const response = await previewResponse;
    assert.ok(response, 'Markdown preview must use the snapshot/link service');
    assert.equal(response.status(), 200);
    const preview = await response.json();
    assert.equal(preview.text, fixture.text);
    assert.equal(preview.document_revision, fixture.document_revision);
    const native = preview.links.filter(link => link.kind === 'native');
    assert.equal(native.length, 1);
    assert.equal(preview.text.slice(native[0].start, native[0].end), fixture.source_link);
    assert.equal(native[0].label, fixture.source_label);
    assert.equal(typeof native[0].link_id, 'string');
    assert.equal(Object.hasOwn(native[0], 'uri'), false);
    assert.equal(await host.locator('a[href^="obsidian:"],a[href^="zotero:"]').count(), 0);
    const position = await source.evaluate(button => ({
      tag: button.tagName, href: button.getAttribute('href'),
      before: button.previousSibling?.textContent, after: button.nextSibling?.textContent,
    }));
    assert.equal(position.tag, 'BUTTON'); assert.equal(position.href, null);
    assert.match(position.before, /中文 🧪 证据位于前文，😀 $/);
    assert.match(position.after, /^，这里继续解释。/);
    assert.equal(await host.getByRole('link', {name: '研究官网', exact: true}).getAttribute('href'),
      'https://example.test/research');
    for (const label of ['行内代码伪链接', '代码块伪链接', '图片伪链接']) {
      assert.equal(await host.getByRole('button', {name: label, exact: true}).count(), 0);
      assert.equal(await host.getByRole('link', {name: label, exact: true}).count(), 0);
      assert.ok((await host.textContent()).includes(label));
    }
    assert.equal(await host.locator('img[src^="obsidian:"],img[src^="zotero:"]').count(), 0);
    const unavailable = host.locator('p').filter({hasText: '不允许的动作'});
    assert.equal(await unavailable.getByRole('link').count(), 0);
    const blockedButton = unavailable.getByRole('button', {name: '不允许的动作', exact: true});
    if (await blockedButton.count()) assert.equal(await blockedButton.isDisabled(), true);
    assert.match(await unavailable.textContent(), /不可|不支持|拒绝|禁止|未通过/);
    assert.deepEqual(requests, []);
    if (process.env.SCHOLAR_EXPLORER_PREVIEW_SCREENSHOT) {
      await page.screenshot({path: process.env.SCHOLAR_EXPLORER_PREVIEW_SCREENSHOT, fullPage: true});
    }
    const opened = page.waitForResponse(result => new URL(result.url()).pathname === '/api/open-link');
    await source.click();
    assert.equal((await opened).status(), 200);
    assert.deepEqual(requests, [
      {method: 'GET', pathname: '/api/reading-link/' + native[0].link_id, search: '', body: null},
      {method: 'POST', pathname: '/api/open-link', search: '', body: {link_id: native[0].link_id}},
    ]);
    assert.equal(JSON.stringify(requests).includes(fixture.expected_uri), false);
    assert.deepEqual(externalRequests, []);
    assert.deepEqual(errors, []);
    console.log('PASS: in-place UTF16 source link, prepare/open opaque identity, exact ZotFlow navigation and inert pseudo-links');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
