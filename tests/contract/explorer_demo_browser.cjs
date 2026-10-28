// Synthetic fixture provider, production HTTP/UI/Store, no native app or personal library.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const fixture = JSON.parse(input), parsed = new URL(fixture.url), origin = parsed.origin;
  const headers = {Authorization: 'Bearer ' + new URLSearchParams(parsed.hash.slice(1)).get('token'), Origin: origin};
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1700, height: 1100}});
    page.setDefaultTimeout(4000);
    const errors = [], external = [], uiLaunches = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      const address = new URL(request.url());
      if (address.origin !== origin) external.push(request.url());
      if (['/api/open', '/api/open-link'].includes(address.pathname)) uiLaunches.push(address.pathname);
    });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    const state = async () => {
      const response = await page.request.get(origin + '/api/state', {headers});
      assert.equal(response.status(), 200); return response.json();
    };
    const apply = async () => {
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#editor').waitFor({state: 'hidden'});
    };
    const save = async () => {
      await page.locator('#save').click();
      await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
      await page.locator('#save:not([aria-busy])').waitFor({state: 'attached'});
    };
    const waitCount = async value => page.locator('#result-count').filter({hasText: new RegExp('^' + value + '$')}).waitFor();
    const shot = suffix => page.screenshot({path: fixture.screenshot_prefix + '-' + suffix + '.png'});
    await page.goto(fixture.url);
    await waitCount(3);
    assert.match(await page.locator('.brand').textContent(), /合成演示/);
    assert.match(await page.title(), /合成开发演示/);
    const initial = (await state()).data;
    assert.deepEqual([initial.works.length, initial.records.length, initial.edges.length], [3, 4, 2]);
    assert.equal(await page.locator('.graph-click').count(), 3);
    assert.equal(await page.locator('.graph-edge').count(), 2);
    assert.equal(new URL(page.url()).hash, '', 'The session credential must leave the visible address');
    await page.locator('.result-card').filter({hasText: '合成论文 A'}).click();
    await page.locator('.asset-card').filter({hasText: '解析树（本演示未生成）'}).waitFor();
    assert.match(await page.locator('#details').textContent(), /合成开发演示.*不含真实研究结论/);
    assert.equal(await page.locator('.asset-card').count(), 5);
    assert.match(await page.locator('.asset-card').filter({hasText: '解析树（本演示未生成）'}).textContent(), /文件缺失/);
    assert.equal(await page.locator('#details .record-card').count(), 2);
    assert.equal(await page.locator('#details').getByRole('button', {name: /Obsidian 打开|原生打开/}).count(), 0);
    await shot('relationships');

    await page.locator('#table-tab').click();
    const table = page.locator('#comparison table');
    assert.deepEqual(await table.getByRole('columnheader').allTextContents(),
      ['工作与研究定位', '比较条件', '结果', '评价与适用边界', '依据与来源']);
    assert.equal(await table.locator('tbody tr').count(), 4);
    const first = table.locator('tbody tr').first();
    assert.match(await first.textContent(), /共同输入：同一合成输入与划分/);
    assert.match(await first.textContent(), /共同预算：相同合成预算/);
    assert.match(await first.textContent(), /变化项：原预测模块/);
    assert.match(await first.textContent(), /合成误差 42/);
    assert.match(await table.textContent(), /替换预测模块.*合成误差 36/s);
    await shot('conditions-results');

    await page.locator('.asset-card').filter({hasText: '分析阅读片段（合成）'})
      .getByRole('button', {name: '预览', exact: true}).click();
    const host = page.locator('#preview-body'), callout = host.locator('details.quote-callout');
    await callout.waitFor();
    assert.equal(await callout.evaluate(element => element.open), false);
    await callout.locator('summary').click();
    assert.equal(await callout.evaluate(element => element.open), true);
    assert.deepEqual(await callout.locator('strong').allTextContents(), ['the variant reduces the example error']);
    assert.match(await callout.textContent(), /Under the same synthetic input and budget.*does not establish performance on real data/s);
    assert.equal(await host.getByRole('table').getByRole('row').count(), 3);
    const image = host.getByRole('img', {name: '合成条件对比图', exact: true});
    await image.waitFor();
    await image.evaluate(element => element.complete || new Promise(resolve => element.addEventListener('load', resolve, {once: true})));
    assert.deepEqual(await image.evaluate(element => [element.naturalWidth, element.naturalHeight]), [640, 220]);
    assert.match(await host.textContent(), /蓝色为 baseline、绿色为 variant.*不是真实实验/s);
    assert.equal(await page.locator('#preview-native').isDisabled(), true);
    await host.evaluate(element => { element.scrollTop = 0; });
    await shot('body');
    await image.evaluate(element => {
      const host = document.getElementById('preview-body');
      host.scrollTop += element.getBoundingClientRect().top - host.getBoundingClientRect().top - 45;
    });
    await shot('body-figure');
    await page.locator('#close-preview').click();

    await page.locator('#views').selectOption('demo-prediction');
    await page.waitForFunction(() => matches.records.length === 3);
    await waitCount(3);
    assert.equal(await table.locator('tbody tr').count(), 3);
    assert.equal(await page.locator('#descending').isChecked(), false);
    await page.locator('#filters').getByLabel('合成基座 A', {exact: true}).uncheck();
    await page.locator('#filters').getByLabel('合成基座 B', {exact: true}).check();
    await waitCount(0);
    assert.match(await page.locator('#results').textContent(), /没有满足这组联合条件/);
    assert.equal(await table.locator('tbody tr').count(), 0,
      'A base-B/control record must not combine with its separate base-A/prediction record');
    await page.locator('#clear-filter').click(); await waitCount(3);

    await page.locator('#add-work').click();
    await page.locator('#editor').waitFor();
    await page.getByLabel('选择知识领域').selectOption('0');
    await page.getByLabel('合成论文 D · 待引用单元', {exact: false}).check();
    assert.equal(await page.locator('#editor input[type=checkbox]').count(), 4);
    await apply();
    assert.equal((await state()).data.works.length, 3, 'Reference proposal stays a draft until explicit save');
    await save(); await waitCount(4);
    const afterReference = (await state()).data;
    assert.equal(afterReference.works.length, 4);
    const added = afterReference.works.find(work => work.entity_ref.object_id === 'synthetic-paper:d');
    assert.ok(added); assert.equal(added.assets.length, 5);
    assert.equal(afterReference.records.length, 4);
    await page.locator('#details .asset-card').nth(4).waitFor();
    assert.equal(await page.locator('#details .asset-card').count(), 5);
    await page.locator('#add-dimension').click();
    await page.getByLabel('名称', {exact: true}).fill('演示扩展 · 复核状态');
    await page.getByLabel('选项定义').fill('尚未复核\n人工已复核');
    await page.getByLabel('含义说明', {exact: true}).fill('仅演示可增维度，不要求所有领域必须有这个维度。');
    await apply(); await save();
    const final = (await state()).data;
    assert.equal(final.dimensions.length, 5);
    assert.ok(final.dimensions.some(dimension => dimension.label === '演示扩展 · 复核状态'));
    assert.deepEqual(final.dimensions.slice(0, 4), initial.dimensions);
    assert.deepEqual(final.works.slice(0, 3), initial.works);
    assert.deepEqual(final.records, initial.records); assert.deepEqual(final.edges, initial.edges);
    assert.deepEqual(errors, []); assert.deepEqual(external, []); assert.deepEqual(uiLaunches, []);

    for (const work of final.works) {
      const listing = await page.request.get(origin + '/api/assets/' + encodeURIComponent(work.id), {headers});
      assert.equal(listing.status(), 200);
      for (const asset of await listing.json()) {
        assert.equal(asset.native_available, false);
        const refused = await page.request.post(origin + '/api/open', {
          headers, data: {work_id: work.id, asset_id: asset.id},
        });
        assert.equal(refused.status(), 403);
      }
    }
    assert.deepEqual(errors, []); assert.deepEqual(external, []);
    console.log('PASS: demo whole-unit navigation, readable prose/media, same-record filters, saved view, whole D reference/save, extensible dimension and all native opens denied');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
