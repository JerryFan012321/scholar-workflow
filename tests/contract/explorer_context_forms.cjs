// These clients use actual loopback Store/query/CAS responses, never fake model data.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {url, scenario} = JSON.parse(input), parsed = new URL(url), origin = parsed.origin;
  const headers = {Authorization: 'Bearer ' + new URLSearchParams(parsed.hash.slice(1)).get('token'), Origin: origin};
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1000}});
    page.setDefaultTimeout(3000);
    await page.clock.install();
    const errors = [], saves = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/save') saves.push(request.postDataJSON());
    });
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    const backendState = async () => {
      const response = await page.request.get(origin + '/api/state', {headers});
      assert.equal(response.status(), 200); return response.json();
    };
    const saveDraft = async () => {
      await page.locator('#save').click();
      await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
      await page.locator('#save:not([aria-busy])').waitFor({state: 'attached'});
    };
    const applyForm = async () => {
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#editor').waitFor({state: 'hidden'});
    };
    const cancelForm = async () => {
      await page.getByRole('button', {name: '取消', exact: true}).click();
      await page.locator('#editor').waitFor({state: 'hidden'});
    };
    const filterB = async () => {
      await page.evaluate('window.__contextPreviousMatches = matches');
      await page.locator('#search').fill('工作 B'); await page.clock.runFor(201);
      await page.waitForFunction(() => matches !== window.__contextPreviousMatches);
      await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
      assert.deepEqual(await page.evaluate('matches.works.map(work => work.id)'), ['b']);
    };
    const chooseEvidence = () => page.getByLabel('工作 A · 原有分析', {exact: true}).check();
    const noPlaceholderGuess = async field => {
      assert.equal(await field.inputValue(), '', 'Ambiguous work identity must not default to a global first item');
      assert.match(await field.locator('option:checked').textContent(), /选择/);
    };
    await page.goto(url);
    await page.locator('#result-count').filter({hasText: /^3$/}).waitFor();
    const initial = await backendState();
    assert.equal(await page.evaluate('selected'), null);

    if (scenario === 'filter-defaults' || scenario === 'view-defaults') {
      if (scenario === 'filter-defaults') await filterB();
      else {
        await page.locator('#views').selectOption('only-b');
        await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
        assert.deepEqual(await page.evaluate('matches.works.map(work => work.id)'), ['b']);
      }
      assert.equal(await page.evaluate('selected'), null);
      await page.locator('#add-record').click();
      assert.equal(await page.getByLabel('所属工作').inputValue(), 'b',
        'A single filtered work is the new record context, not the first global work');
      await page.getByLabel('结果', {exact: true}).fill('唯一命中 B 的本地结果');
      await page.getByLabel('评价与适用边界').fill('仅用于合成上下文验收');
      await applyForm(); await saveDraft();
      let state = await backendState();
      const added = state.data.records.filter(record => !initial.data.records.some(old => old.id === record.id));
      assert.equal(added.length, 1); assert.equal(added[0].work_id, 'b');
      assert.equal(added[0].result, '唯一命中 B 的本地结果');
      await page.locator('#add-edge').click();
      assert.equal(await page.getByLabel('起点工作').inputValue(), 'b');
      await noPlaceholderGuess(page.getByLabel('终点工作'));
      await page.getByLabel('终点工作').selectOption('c');
      await page.getByLabel('关系含义').selectOption('competes');
      await page.getByLabel('连线简短说明').fill('B 与 C 的合成对比');
      await page.getByLabel('依据与说明').fill('人工选择 C 为比较对象，不能自动指定全库 A。');
      await chooseEvidence(); await applyForm(); await saveDraft();
      state = await backendState();
      assert.equal(state.data.edges.length, 1);
      assert.equal(state.data.edges[0].from_id, 'b'); assert.equal(state.data.edges[0].to_id, 'c');
      assert.deepEqual(state.data.edges[0].evidence, ['body']);
      assert.equal(await page.evaluate('selection.text'), '工作 B');
      assert.deepEqual(await page.evaluate('matches.works.map(work => work.id)'), ['b']);
      if (scenario === 'filter-defaults') {
        // The old unique hit is not valid context during a newer filter's debounce.
        await page.clock.pauseAt(await page.evaluate('Date.now() + 100'));
        await page.locator('#search').fill('工作 C');
        assert.deepEqual(await page.evaluate('matches.works.map(work => work.id)'), ['b']);
        await page.locator('#add-record').click();
        await noPlaceholderGuess(page.getByLabel('所属工作'));
        await cancelForm(); await page.clock.runFor(201);
        await page.waitForFunction(() => matches.works.length === 1 && matches.works[0].id === 'c');
        assert.deepEqual(await page.evaluate('matches.works.map(work => work.id)'), ['c']);
        assert.equal((await backendState()).data.records.length, state.data.records.length);
      }
    } else if (scenario === 'ambiguous-defaults') {
      await page.locator('#add-record').click();
      await noPlaceholderGuess(page.getByLabel('所属工作'));
      await page.getByLabel('结果', {exact: true}).fill('未选择工作不应产生归属');
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#form-error:not([hidden])').waitFor();
      assert.match(await page.locator('#form-error').textContent(), /选择/);
      assert.equal(await page.getByLabel('结果', {exact: true}).inputValue(), '未选择工作不应产生归属');
      assert.equal(await page.locator('#editor').evaluate(editor => editor.open), true);
      assert.deepEqual(await backendState(), initial); assert.equal(await page.evaluate('dirty'), false);
      await cancelForm(); await page.locator('#add-edge').click();
      await noPlaceholderGuess(page.getByLabel('起点工作'));
      await noPlaceholderGuess(page.getByLabel('终点工作'));
      await page.getByLabel('依据与说明').fill('没有选择端点时不能替用户决定关系。');
      await chooseEvidence();
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#form-error:not([hidden])').waitFor();
      assert.match(await page.locator('#form-error').textContent(), /选择/);
      assert.equal(await page.locator('#editor').evaluate(editor => editor.open), true);
      assert.deepEqual(await backendState(), initial); assert.equal(await page.evaluate('dirty'), false);
      assert.equal(saves.length, 0);
    } else if (scenario === 'explicit-context') {
      await page.locator('.result-card').filter({hasText: '工作 A'}).click();
      assert.equal(await page.evaluate('selected'), 'a');
      await filterB();
      assert.equal(await page.evaluate('selected'), 'a', 'A deliberate existing selection remains context');
      await page.locator('#add-record').click();
      assert.equal(await page.getByLabel('所属工作').inputValue(), 'a');
      await cancelForm(); await page.locator('#add-edge').click();
      assert.equal(await page.getByLabel('起点工作').inputValue(), 'a');
      await noPlaceholderGuess(page.getByLabel('终点工作'));
      await cancelForm();
      assert.equal(await page.evaluate('selected'), 'a'); assert.equal(await page.evaluate('selection.text'), '工作 B');
      assert.deepEqual(await backendState(), initial); assert.equal(saves.length, 0);
    } else if (scenario === 'query-notices') {
      await page.locator('#sort').selectOption('latency');
      await page.locator('#notice:not([hidden])').filter({hasText: 'narrower comparison'}).waitFor();
      await page.locator('#filters').getByLabel('条件一', {exact: true}).check();
      await page.clock.runFor(201);
      await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
      assert.deepEqual(await page.evaluate('matches.records.map(record => record.id)'), ['r1']);
      assert.equal(await page.locator('#notice').isVisible(), false,
        'A successful narrowed query must clear its obsolete sort error');
      await page.locator('.result-card').filter({hasText: '工作 B'}).click();
      await page.getByRole('button', {name: '编辑工作', exact: true}).click();
      await page.getByLabel('简短说明').fill('尚未保存的 B 本地草稿');
      await applyForm();
      assert.equal(await page.evaluate('dirty'), true);
      const oldRevision = await page.evaluate('revision');
      const current = await backendState(), external = structuredClone(current.data);
      external.works.find(work => work.id === 'a').summary = '合成第二客户端的外部更新';
      const response = await page.request.post(origin + '/api/save', {
        headers, data: {data: external, expected_revision: current.revision},
      });
      assert.equal(response.status(), 200); const committed = await response.json();
      const polled = page.waitForResponse(result => new URL(result.url()).pathname === '/api/state');
      await page.clock.runFor(5001); await polled;
      await page.locator('#notice').filter({hasText: '知识库文件已在外部修改'}).waitFor();
      const externalNotice = await page.locator('#notice').textContent();
      await filterB();
      assert.equal(await page.locator('#notice').textContent(), externalNotice,
        'A successful query must not erase external-edit conflict notices');
      assert.equal(await page.evaluate('dirty'), true); assert.equal(await page.evaluate('revision'), oldRevision);
      await page.locator('#save').click();
      await page.locator('#status').filter({hasText: '保存未完成'}).waitFor();
      await page.locator('#notice').filter({hasText: '文件已被其他编辑器修改'}).waitFor();
      const casNotice = await page.locator('#notice').textContent();
      const successful = page.waitForResponse(result => new URL(result.url()).pathname === '/api/query' && result.status() === 200);
      await page.evaluate('window.__contextPreviousMatches = matches');
      await page.locator('#sort').selectOption('title'); await successful;
      await page.waitForFunction(() => matches !== window.__contextPreviousMatches);
      assert.equal(await page.locator('#notice').textContent(), casNotice,
        'A successful query must not erase the unsaved CAS conflict');
      assert.equal(await page.evaluate('dirty'), true); assert.equal(await page.evaluate('revision'), oldRevision);
      assert.equal(await page.evaluate('data.works.find(work => work.id === "b").summary'), '尚未保存的 B 本地草稿');
      const saved = await backendState();
      assert.equal(saved.revision, committed.revision);
      assert.equal(saved.data.works.find(work => work.id === 'a').summary, '合成第二客户端的外部更新');
      assert.equal(saved.data.works.find(work => work.id === 'b').summary, '初始说明 B');
      assert.equal(saves.length, 1); assert.equal(saves[0].expected_revision, oldRevision);
    } else throw new Error('Unknown synthetic context scenario: ' + scenario);
    assert.deepEqual(errors, []);
    console.log('PASS: ' + scenario + ', real HTTP context and unchanged source unit');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
