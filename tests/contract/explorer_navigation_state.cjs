// Keep the Store, HTTP responses and reader checks real; only external apps are fixtures.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {url, scenario} = JSON.parse(input), parsed = new URL(url), origin = parsed.origin;
  const headers = {Authorization: 'Bearer ' + new URLSearchParams(parsed.hash.slice(1)).get('token'), Origin: origin};
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  const releases = [];
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1000}});
    page.setDefaultTimeout(3000);
    await page.clock.install();
    const errors = [], navigation = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/api/assets/') || path === '/api/open') {
        navigation.push({method: request.method(), path,
          body: request.method() === 'POST' ? request.postDataJSON() : null});
      }
    });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    const responseAt = path => page.waitForResponse(response => new URL(response.url()).pathname === path);
    const pick = async letter => {
      await page.locator('.result-card').filter({hasText: '合成论文 ' + letter.toUpperCase()}).click();
      await page.locator('#details .detail-title').filter({hasText: '合成论文 ' + letter.toUpperCase()}).waitFor();
    };
    const backendState = async () => {
      const response = await page.request.get(origin + '/api/state', {headers});
      assert.equal(response.status(), 200); return response.json();
    };
    const removeA = async () => {
      const current = await backendState(), candidate = structuredClone(current.data);
      candidate.works = candidate.works.filter(work => work.id !== 'a');
      candidate.records = candidate.records.filter(record => record.work_id !== 'a');
      candidate.edges = candidate.edges.filter(edge => edge.from_id !== 'a' && edge.to_id !== 'a');
      const response = await page.request.post(origin + '/api/save', {
        headers, data: {data: candidate, expected_revision: current.revision},
      });
      assert.equal(response.status(), 200); return response.json();
    };
    await page.goto(url);
    await page.locator('#result-count').filter({hasText: /^2$/}).waitFor();

    if (scenario.startsWith('comparison-native')) {
      assert.equal(await page.evaluate('selected'), null, 'The comparison must start without preparing any detail panel');
      assert.deepEqual(navigation, []);
      await page.locator('#table-tab').click();
      const firstAction = page.waitForResponse(response => {
        const path = new URL(response.url()).pathname;
        return path === '/api/assets/a' || path === '/api/open';
      });
      const opened = responseAt('/api/open').catch(() => null);
      await page.locator('#comparison').getByRole('button', {name: 'A 原文 PDF', exact: true}).click();
      const first = await firstAction;
      assert.equal(new URL(first.url()).pathname, '/api/assets/a',
        'A comparison evidence action must prepare the selected unit before launch: ' + JSON.stringify(navigation));
      assert.equal(first.status(), 200);
      if (scenario === 'comparison-native') {
        const response = await opened;
        assert.ok(response, 'The verified action should reach the controlled native boundary');
        assert.equal(response.status(), 200, await response.text());
        await page.locator('#notice').filter({hasText: '已提交'}).waitFor();
        assert.deepEqual(navigation, [
          {method: 'GET', path: '/api/assets/a', body: null},
          {method: 'POST', path: '/api/open', body: {work_id: 'a', asset_id: 'a-pdf'}},
        ]);
      } else {
        await page.locator('#notice:not([hidden])').waitFor();
        assert.match(await page.locator('#notice').textContent(), /归属|核实|核对|不可用/);
        assert.deepEqual(navigation, [{method: 'GET', path: '/api/assets/a', body: null}],
          'A failed reader preparation must not submit a launch');
      }
      assert.equal(await page.locator('#table-view').isVisible(), true);
      assert.deepEqual(await page.evaluate('selection.filters'), {});
    } else if (scenario.startsWith('removed-')) {
      const assets = responseAt('/api/assets/a'); await pick('a'); await assets;
      await page.locator('#details .asset-card').filter({hasText: 'A 分析正文'}).waitFor();
      const saved = await removeA();
      if (scenario === 'removed-poll') await page.clock.runFor(5001);
      else await page.locator('#reload').click();
      await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
      assert.equal(await page.evaluate('revision'), saved.revision);
      assert.notEqual(await page.evaluate('selected'), 'a', 'An externally removed unit must not remain selected');
      assert.equal(await page.locator('#details .detail-title').filter({hasText: '合成论文 A'}).count(), 0,
        'Following a new revision must clear the previous unit detail');
      assert.equal(await page.locator('#details .asset-card').filter({hasText: 'A 分析正文'}).count(), 0);
      assert.equal(await page.locator('#details .asset-card').filter({hasText: 'A 原文 PDF'}).count(), 0);
      if (await page.evaluate('selected') === null) {
        assert.equal(await page.locator('#details').getByRole('button', {name: '编辑工作', exact: true}).count(), 0);
      }
      const available = responseAt('/api/assets/b'); await pick('b'); await available;
      await page.locator('#details .asset-card').filter({hasText: 'B 分析正文'})
        .getByRole('button', {name: '预览', exact: true}).click();
      await page.locator('#preview-body').getByRole('heading', {name: 'Synthetic unit B', exact: true}).waitFor();
      await page.locator('#close-preview').click();
      assert.equal(await page.locator('#details .detail-title').textContent(), '合成论文 B');
      assert.equal(await page.locator('#result-count').textContent(), '1');
      assert.deepEqual(await page.evaluate('selection.filters'), {});
      assert.equal(await page.evaluate('dirty'), false);
    } else if (scenario === 'late-assets') {
      let release, captured, completed;
      const gate = new Promise(resolve => { release = resolve; });
      const ready = new Promise(resolve => { captured = resolve; });
      const done = new Promise(resolve => { completed = resolve; }); releases.push(release);
      await page.route('**/api/assets/a', async route => {
        const response = await route.fetch(), body = await response.body(); captured();
        await gate;
        try { await route.fulfill({response, body}); } finally { completed(); }
      });
      await pick('a'); await ready;
      const available = responseAt('/api/assets/b'); await pick('b'); await available;
      await page.locator('#details .asset-card').filter({hasText: 'B 分析正文'}).waitFor();
      release(); await done; await page.clock.runFor(20);
      assert.equal(await page.locator('#details .detail-title').textContent(), '合成论文 B');
      assert.equal(await page.locator('#details .asset-card').filter({hasText: 'A 分析正文'}).count(), 0);
      assert.equal(await page.locator('#details .asset-card').filter({hasText: 'A 原文 PDF'}).count(), 0);
      assert.equal(await page.locator('#details .asset-card').count(), 2);
      assert.equal(await page.evaluate('selected'), 'b');
    } else throw new Error('Unknown synthetic scenario: ' + scenario);
    assert.deepEqual(errors, []);
    console.log('PASS: ' + scenario + ', real HTTP/Store navigation and intact source files');
  } finally {
    releases.forEach(release => release());
    await browser.close();
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
