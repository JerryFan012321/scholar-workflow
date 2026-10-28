// All state changes use this fixture's real loopback API; no model response is invented.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {url, scenario} = JSON.parse(input);
  const parsed = new URL(url), origin = parsed.origin;
  const token = new URLSearchParams(parsed.hash.slice(1)).get('token');
  const headers = {Authorization: 'Bearer ' + token, Origin: origin};
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  const releases = [];
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1000}});
    page.setDefaultTimeout(3000);
    await page.clock.install();
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    const errors = [], saves = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/save') saves.push(request.postDataJSON());
    });
    const backendState = async () => {
      const response = await page.request.get(origin + '/api/state', {headers});
      assert.equal(response.status(), 200);
      return response.json();
    };
    const externalSave = async mutate => {
      const current = await backendState();
      const candidate = structuredClone(current.data);
      mutate(candidate.works.find(work => work.id === 'editable'));
      const response = await page.request.post(origin + '/api/save', {
        headers, data: {data: candidate, expected_revision: current.revision},
      });
      assert.equal(response.status(), 200);
      return response.json();
    };
    const selectedWork = state => state.data.works.find(work => work.id === 'editable');
    const openEditor = async () => {
      await page.locator('.result-card').filter({hasText: '合成网页工作'}).click();
      await page.getByRole('button', {name: '编辑工作', exact: true}).click();
      await page.getByLabel('简短说明').waitFor();
    };
    const applyForm = async () => {
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#editor').waitFor({state: 'hidden'});
    };
    const saveDraft = async () => {
      await page.locator('#save').click();
      await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
    };
    const poll = async () => {
      const response = page.waitForResponse(result => new URL(result.url()).pathname === '/api/state');
      await page.clock.runFor(5001);
      await response;
      await page.clock.runFor(20);
    };
    const holdRealResponse = async pattern => {
      let release, captured, completed;
      const gate = new Promise(resolve => { release = resolve; });
      const ready = new Promise(resolve => { captured = resolve; });
      const done = new Promise(resolve => { completed = resolve; });
      releases.push(release);
      let pending = true;
      const handler = async route => {
        if (!pending) return route.continue();
        pending = false;
        const response = await route.fetch();
        const body = await response.body();
        captured(JSON.parse(body.toString()));
        await gate;
        try { await route.fulfill({response, body}); } finally { completed(); }
      };
      await page.route(pattern, handler);
      return {ready, release, done, remove: () => page.unroute(pattern, handler)};
    };
    await page.goto(url);
    await page.locator('#result-count').filter({hasText: /^2$/}).waitFor();

    if (scenario === 'reload-draft') {
      const initial = await backendState(), nativeDialogs = [];
      page.on('dialog', async dialog => {
        nativeDialogs.push(dialog.type()); await dialog.dismiss();
      });
      await openEditor();
      await page.getByLabel('简短说明').fill('未保存的独立草稿');
      await applyForm();
      const draft = await page.evaluate(() => JSON.stringify(data));
      const confirmation = page.getByRole('dialog', {name: '重新读取知识库'});
      await page.locator('#reload').click();
      await confirmation.waitFor({state: 'visible'});
      await confirmation.getByRole('button', {name: '保留修改', exact: true}).click();
      assert.equal(await page.evaluate(() => JSON.stringify(data)), draft);
      assert.equal(await page.locator('#save').isDisabled(), false);
      assert.deepEqual(await backendState(), initial);
      await page.locator('#reload').click();
      await confirmation.waitFor({state: 'visible'});
      await page.keyboard.press('Escape');
      await confirmation.waitFor({state: 'hidden'});
      assert.equal(await page.evaluate(() => JSON.stringify(data)), draft);
      await page.locator('#reload').click();
      await confirmation.waitFor({state: 'visible'});
      await confirmation.getByRole('button', {name: '放弃草稿并读取', exact: true}).click();
      await page.locator('#status').filter({hasText: '知识库已连接'}).waitFor();
      assert.equal(await page.locator('#save').isDisabled(), true);
      assert.deepEqual(await page.evaluate('data'), initial.data);
      assert.deepEqual(await backendState(), initial);
      assert.deepEqual(nativeDialogs, [], 'Reload must use a page dialog, not a blocking native confirm');
      assert.deepEqual(saves, [], 'Keeping or discarding a draft must not save it');
    } else if (scenario === 'open-form') {
      await openEditor();
      assert.equal(await page.getByLabel('简短说明').inputValue(), '初始说明');
      await page.getByLabel('发表年份（可选）').fill('2030');
      const external = await externalSave(work => { work.summary = '外部更新后的说明'; });
      await poll();
      assert.equal((await backendState()).revision, external.revision);
      assert.equal(selectedWork(await backendState()).summary, '外部更新后的说明');
      const saveCount = saves.length;
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#form-error:not([hidden])').waitFor();
      assert.match(await page.locator('#form-error').textContent(), /当前输入已保留/);
      assert.equal(await page.locator('#editor').evaluate(editor => editor.open), true);
      assert.equal(await page.getByLabel('发表年份（可选）').inputValue(), '2030');
      assert.equal(await page.getByLabel('简短说明').inputValue(), '初始说明');
      assert.equal(saves.length, saveCount);
      assert.equal(selectedWork(await backendState()).summary, '外部更新后的说明');
      assert.equal((await backendState()).revision, external.revision);
      if (process.env.SCHOLAR_EXPLORER_EDIT_CONFLICT_SCREENSHOT) {
        await page.screenshot({path: process.env.SCHOLAR_EXPLORER_EDIT_CONFLICT_SCREENSHOT, fullPage: true});
      }
      await page.getByRole('button', {name: '取消', exact: true}).click();
      page.once('dialog', dialog => dialog.accept());
      await page.locator('#reload').click();
      await page.locator('#status').filter({hasText: '知识库已连接'}).waitFor();
      await openEditor();
      assert.equal(await page.getByLabel('简短说明').inputValue(), '外部更新后的说明');
      await page.getByLabel('发表年份（可选）').fill('2030');
      await applyForm(); await saveDraft();
      const saved = selectedWork(await backendState());
      assert.equal(saved.summary, '外部更新后的说明');
      assert.equal(saved.year, 2030);
    } else if (scenario === 'save-pending') {
      await openEditor();
      await page.getByLabel('简短说明').fill('正在保存的本地说明');
      await applyForm();
      const held = await holdRealResponse('**/api/save');
      await page.locator('#save').click();
      const committed = await held.ready;
      assert.equal(selectedWork(committed).summary, '正在保存的本地说明');
      const count = saves.length;
      const edit = page.getByRole('button', {name: '编辑工作', exact: true});
      if (!await edit.isDisabled()) await edit.click();
      assert.equal(await page.locator('#editor').evaluate(editor => editor.open), false);
      if (!await page.locator('#save').isDisabled()) await page.locator('#save').click();
      assert.equal(saves.length, count);
      assert.equal(await page.evaluate('data.works.find(work => work.id === "editable").summary'), '正在保存的本地说明');
      held.release(); await held.done; await held.remove();
      await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
      assert.equal(await page.evaluate('revision'), committed.revision);
      assert.equal(await page.evaluate('dirty'), false);
      assert.equal(selectedWork(await backendState()).summary, '正在保存的本地说明');
      await openEditor(); await page.getByLabel('发表年份（可选）').fill('2031');
      await applyForm(); await saveDraft();
      const saved = selectedWork(await backendState());
      assert.equal(saved.summary, '正在保存的本地说明'); assert.equal(saved.year, 2031);
    } else if (scenario === 'load-form') {
      const initial = await backendState();
      const external = await externalSave(work => { work.summary = '待读取的外部新说明'; });
      const held = await holdRealResponse('**/api/state');
      await page.locator('#reload').click();
      const fetched = await held.ready;
      assert.equal(fetched.revision, external.revision);
      assert.equal(selectedWork(fetched).summary, '待读取的外部新说明');
      await openEditor();
      await page.getByLabel('简短说明').fill('重新读取等待期间输入的说明');
      const before = await page.evaluate(() => {
        window.__conflictTestData = data;
        return {data: JSON.stringify(data), revision, dirty};
      });
      assert.equal(before.revision, initial.revision);
      held.release(); await held.done; await held.remove();
      await page.clock.runFor(20);
      assert.equal(await page.locator('#editor').evaluate(editor => editor.open), true);
      assert.equal(await page.getByLabel('简短说明').inputValue(), '重新读取等待期间输入的说明');
      assert.equal(await page.evaluate('data === window.__conflictTestData'), true);
      assert.deepEqual(await page.evaluate(() => ({data: JSON.stringify(data), revision, dirty})), before);
      assert.equal((await backendState()).revision, external.revision);
      assert.equal(selectedWork(await backendState()).summary, '待读取的外部新说明');
      assert.equal(saves.length, 0);
    } else if (scenario === 'stale-query') {
      const initial = await backendState();
      // An actual old search result must not enter the new search's debounce window.
      const oldResult = await holdRealResponse('**/api/query');
      await page.locator('#search').fill('不存在的旧搜索');
      await page.clock.runFor(201);
      assert.equal((await oldResult.ready).works.length, 0);
      assert.equal(await page.locator('#result-count').textContent(), '2');
      await page.locator('#search').fill('合成网页');
      oldResult.release(); await oldResult.done; await oldResult.remove();
      await page.clock.runFor(20);
      assert.equal(await page.locator('#search').inputValue(), '合成网页');
      assert.equal(await page.evaluate('selection.text'), '合成网页');
      assert.equal(await page.locator('#result-count').textContent(), '2');
      assert.equal(await page.evaluate('matches.works.length'), 2);
      await page.clock.runFor(201);
      await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
      assert.deepEqual(await page.evaluate('matches.works.map(work => work.id)'), ['editable']);
      await page.locator('#search').fill(''); await page.clock.runFor(201);
      await page.locator('#result-count').filter({hasText: /^2$/}).waitFor();
      // This error is real: one work has two latency values until a condition is chosen.
      const oldError = await holdRealResponse('**/api/query');
      await page.locator('#sort').selectOption('latency');
      assert.match((await oldError.ready).error, /narrower comparison/);
      assert.equal(await page.locator('#notice').isVisible(), false);
      await page.locator('#filters').getByText('条件A', {exact: true}).click();
      oldError.release(); await oldError.done; await oldError.remove();
      await page.clock.runFor(20);
      assert.equal(await page.locator('#filters').getByLabel('条件A', {exact: true}).isChecked(), true);
      assert.equal(await page.locator('#notice').isVisible(), false);
      assert.equal(await page.locator('#result-count').textContent(), '2');
      await page.clock.runFor(201);
      await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
      assert.deepEqual(await page.evaluate('matches.records.map(record => record.id)'), ['r1']);
      assert.equal(await page.locator('#notice').isVisible(), false);
      assert.deepEqual(await backendState(), initial);
      assert.equal(saves.length, 0);
    } else if (scenario === 'stale-poll-and-dirty') {
      const held = await holdRealResponse('**/api/state');
      await page.clock.runFor(5001);
      const old = await held.ready;
      await openEditor();
      await page.getByLabel('简短说明').fill('新保存的说明');
      await applyForm(); await saveDraft();
      const current = await backendState();
      assert.notEqual(current.revision, old.revision);
      assert.equal(selectedWork(current).summary, '新保存的说明');
      held.release(); await held.done; await held.remove();
      await page.clock.runFor(20);
      assert.equal(await page.evaluate('revision'), current.revision);
      assert.equal(await page.evaluate('data.works.find(work => work.id === "editable").summary'), '新保存的说明');
      assert.equal((await backendState()).revision, current.revision);
      await openEditor();
      await page.getByLabel('简短说明').fill('尚未保存的本地草稿');
      await applyForm();
      const external = await externalSave(work => { work.summary = '外部同期修改'; work.year = 2040; });
      await poll();
      assert.equal(await page.evaluate('dirty'), true);
      assert.equal(await page.evaluate('revision'), current.revision);
      assert.equal(await page.evaluate('data.works.find(work => work.id === "editable").summary'), '尚未保存的本地草稿');
      await page.locator('#save').click();
      await page.locator('#status').filter({hasText: '保存未完成'}).waitFor();
      await page.locator('#notice').filter({hasText: '文件已被其他编辑器修改'}).waitFor();
      assert.equal(saves.at(-1).expected_revision, current.revision);
      assert.equal(await page.evaluate('dirty'), true);
      assert.equal(await page.evaluate('revision'), current.revision);
      assert.equal(selectedWork(await backendState()).summary, '外部同期修改');
      assert.equal((await backendState()).revision, external.revision);
      await openEditor();
      assert.equal(await page.getByLabel('简短说明').inputValue(), '尚未保存的本地草稿');
    } else throw new Error('Unknown synthetic scenario: ' + scenario);
    assert.deepEqual(errors, []);
    console.log('PASS: ' + scenario + ', real HTTP CAS and unchanged paper unit');
  } finally {
    releases.forEach(release => release());
    await browser.close();
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
