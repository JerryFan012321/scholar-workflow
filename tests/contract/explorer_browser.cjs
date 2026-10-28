// Optional real-browser development smoke test; all requests stay on the fixture origin.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {url} = JSON.parse(input);
  const origin = new URL(url).origin;
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1000}});
    await page.route('**/*', route => new URL(route.request().url()).origin === origin
      ? route.continue() : route.abort());
    const errors = [];
    const savedModels = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/save') savedModels.push(request.postDataJSON().data);
    });
    await page.goto(url);
    await page.locator('#result-count').filter({hasText: /^3$/}).waitFor();
    assert.equal(await page.locator('#add-work').textContent(), '引用论文单元');
    assert.equal(await page.locator('#first-work').textContent(), '引用论文单元');
    assert.equal(await page.getByRole('button', {name: '＋ 工作', exact: true}).count(), 0);
    // An incompatible definition stays in the open form, not the live draft.
    for (const change of [
      async () => page.getByLabel('适用对象').selectOption('work'),
      async () => { await page.getByLabel('数据类型').selectOption('number'); await page.getByLabel('选项定义').fill(''); },
      async () => page.getByLabel('取值数量').selectOption('no'),
      async () => page.getByLabel('选项定义').fill('B2'),
    ]) {
      await page.getByRole('button', {name: '基座', exact: true}).click();
      await change();
      const pendingInputs = await page.locator('#editor-fields').locator('input,select,textarea').evaluateAll(inputs => inputs.map(input => input.value));
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#form-error:not([hidden])').waitFor();
      assert.equal(await page.locator('#editor').evaluate(editor => editor.open), true);
      assert.deepEqual(await page.locator('#editor-fields').locator('input,select,textarea').evaluateAll(inputs => inputs.map(input => input.value)), pendingInputs);
      assert.equal(await page.getByRole('button', {name: '保存修改', exact: true}).isDisabled(), true);
      await page.getByRole('button', {name: '取消', exact: true}).click();
      assert.equal(await page.locator('#result-count').textContent(), '3');
    }
    await page.getByRole('button', {name: '＋ 维度', exact: true}).click();
    await page.getByLabel('名称', {exact: true}).fill('输入模态');
    assert.equal(await page.locator('#editor').getByLabel('排序').isDisabled(), true);
    await page.getByText('只有单值的文字、数值或日期可以排序；选项、工作引用和多值不提供排序。', {exact: true}).waitFor();
    await page.getByLabel('选项定义').fill('视频\n图像');
    if (process.env.SCHOLAR_EXPLORER_DIMENSION_SCREENSHOT) await page.screenshot({path: process.env.SCHOLAR_EXPLORER_DIMENSION_SCREENSHOT, fullPage: true});
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.getByRole('button', {name: '保存修改', exact: true}).click();
    await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
    await page.reload();
    await page.getByRole('button', {name: '输入模态', exact: true}).waitFor();
    const originalPaper = savedModels[0].works.find(work => work.id === 'a');
    await page.locator('.result-card').filter({hasText: '示例工作 A'}).click();
    await page.getByRole('button', {name: '编辑工作', exact: true}).click();
    assert.equal(await page.getByLabel('材料类型').isDisabled(), true);
    assert.equal(await page.locator('#editor').getByRole('button', {name: '移除', exact: true}).count(), 0);
    assert.equal(await page.locator('#editor').getByRole('button', {name: '＋ 关联资产', exact: true}).count(), 0);
    await page.getByLabel('简短说明').fill('仅修改外围研究定位说明，不改论文包。');
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.locator('#editor').waitFor({state: 'hidden'});
    await page.getByRole('button', {name: '保存修改', exact: true}).click();
    await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
    const editedPaper = savedModels.at(-1).works.find(work => work.id === 'a');
    assert.deepEqual(editedPaper.entity_ref, originalPaper.entity_ref);
    assert.deepEqual(editedPaper.assets, originalPaper.assets);
    assert.equal(editedPaper.kind, 'paper');
    await page.getByRole('button', {name: '＋ 维度', exact: true}).click();
    await page.getByLabel('名称', {exact: true}).fill('响应时间');
    const sorting = page.locator('#editor').getByLabel('排序');
    await page.getByLabel('数据类型').selectOption('text');
    assert.equal(await sorting.isDisabled(), true);
    await page.getByLabel('取值数量').selectOption('no');
    assert.equal(await sorting.isDisabled(), false);
    await sorting.selectOption('yes');
    await page.getByLabel('数据类型').selectOption('reference');
    assert.equal(await sorting.isDisabled(), true);
    assert.equal(await sorting.inputValue(), 'no');
    await page.getByLabel('数据类型').selectOption('number');
    assert.equal(await sorting.isDisabled(), false);
    await sorting.selectOption('yes');
    await page.getByLabel('取值数量').selectOption('yes');
    assert.equal(await sorting.isDisabled(), true);
    assert.equal(await sorting.inputValue(), 'no');
    await page.getByLabel('取值数量').selectOption('no');
    for (const kind of ['date', 'text', 'number']) {
      await page.getByLabel('数据类型').selectOption(kind);
      assert.equal(await sorting.isDisabled(), false);
    }
    await page.getByText('按单个文字、数值或日期值排序；缺失值排在最后。', {exact: true}).waitFor();
    await sorting.selectOption('yes');
    await page.getByLabel('单位（数值可选）').fill('毫秒');
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.locator('.result-card').filter({hasText: '示例工作 A'}).click();
    await page.locator('.record-card').first().getByRole('button', {name: '编辑', exact: true}).click();
    await page.locator('#editor').getByLabel('视频', {exact: true}).check();
    await page.getByLabel('响应时间（毫秒）').fill('0.81');
    await page.getByLabel('评价与适用边界', {exact: true}).fill('只在相同数据和预算下支持当前比较。');
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.locator('#editor').waitFor({state: 'hidden'});
    // Rejecting another edit must retain the existing unsaved record and filter.
    await page.locator('#filters').getByText('B1', {exact: true}).click();
    await page.locator('#result-count').filter({hasText: /^1$/}).waitFor();
    await page.getByRole('button', {name: '基座', exact: true}).click();
    await page.getByLabel('适用对象').selectOption('work');
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.locator('#form-error:not([hidden])').waitFor();
    assert.equal(await page.getByRole('button', {name: '保存修改', exact: true}).isDisabled(), false);
    assert.equal(await page.locator('#filters').getByLabel('B1', {exact: true}).isChecked(), true);
    assert.equal(await page.getByLabel('适用对象').inputValue(), 'work');
    await page.getByRole('button', {name: '取消', exact: true}).click();
    await page.getByRole('button', {name: '清除', exact: true}).click();
    await page.locator('#result-count').filter({hasText: /^3$/}).waitFor();
    await page.getByRole('button', {name: '保存修改', exact: true}).click();
    await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
    await page.locator('#details').getByText('响应时间（毫秒）', {exact: true}).waitFor();
    await page.getByRole('tab', {name: '条件与结果', exact: true}).click();
    await page.getByRole('cell', {name: '只在相同数据和预算下支持当前比较。', exact: true}).waitFor();
    if (process.env.SCHOLAR_EXPLORER_TABLE_SCREENSHOT) await page.screenshot({path: process.env.SCHOLAR_EXPLORER_TABLE_SCREENSHOT, fullPage: true});
    // A uses B1/T1 in one record and B2/T2 in another; B1/T2 must never match.
    await page.locator('#filters').getByText('B1', {exact: true}).click();
    await page.locator('#filters').getByText('T2', {exact: true}).click();
    await page.locator('#result-count').filter({hasText: /^0$/}).waitFor();
    await page.getByRole('button', {name: '清除', exact: true}).click();
    await page.locator('#result-count').filter({hasText: /^3$/}).waitFor();
    // A denied native reader keeps a readable reason without invoking /api/open.
    const technicalReason = 'Synthetic ZotFlow local PDF mode is unverified.';
    const assetsRoute = '**/api/assets/a';
    const readerDiagnostic = async route => {
      const response = await route.fetch();
      const listing = await response.json();
      await route.fulfill({response, json: [...listing, {
        id: 'synthetic-zotflow', label: '合成 ZotFlow 阅读入口', kind: 'pdf',
        uri: 'obsidian://zotflow?type=open-attachment&libraryID=1&key=ABCDEFGH',
        local: false, available: true, native_available: false,
        native_reason_code: 'zotflow_unavailable', native_reason: technicalReason,
      }]});
    };
    let nativeOpenRequests = 0;
    const countNativeOpen = request => {
      if (new URL(request.url()).pathname === '/api/open') nativeOpenRequests++;
    };
    page.on('request', countNativeOpen);
    await page.route(assetsRoute, readerDiagnostic);
    await page.locator('.result-card').filter({hasText: '示例工作 A'}).click();
    const unavailableReader = page.locator('.asset-card').filter({hasText: '合成 ZotFlow 阅读入口'});
    await unavailableReader.getByText('ZotFlow 本地阅读条件未通过验证，请检查版本、启用状态和本地 PDF 设置。', {exact: true}).waitFor();
    assert.equal(await unavailableReader.getByRole('button').count(), 0);
    assert.equal(await unavailableReader.locator('details').filter({hasText: '技术详情'}).evaluate(details => details.open), false);
    assert.equal(await unavailableReader.getByText(technicalReason, {exact: true}).isVisible(), false);
    await unavailableReader.getByText('技术详情', {exact: true}).click();
    await unavailableReader.getByText(technicalReason, {exact: true}).waitFor();
    if (process.env.SCHOLAR_EXPLORER_READER_SCREENSHOT) {
      await unavailableReader.scrollIntoViewIfNeeded();
      await page.screenshot({path: process.env.SCHOLAR_EXPLORER_READER_SCREENSHOT, fullPage: true});
    }
    await page.locator('.asset-card').filter({hasText: '原有分析'}).getByRole('button', {name: '预览', exact: true}).click();
    await page.locator('#preview-body').getByText('Original paper content.', {exact: true}).waitFor();
    await page.locator('#close-preview').click();
    assert.equal(nativeOpenRequests, 0);
    page.off('request', countNativeOpen);
    await page.unroute(assetsRoute, readerDiagnostic);
    // The reference picker imports one whole qualified unit, never a title-only paper.
    const unitRef = {source_id: 'fixture-source', object_id: 'unit-d'};
    let fieldsAvailable = true, referenceCalls = 0;
    await page.route('**/api/unit-fields', route => fieldsAvailable ? route.continue()
      : route.fulfill({json: {fields: [], diagnostics: ['尚无已登记知识来源。']}}));
    await page.route('**/api/unit-options', route => {
      assert.deepEqual(route.request().postDataJSON(), {source_id: unitRef.source_id, field_id: 'fixture-field'});
      return route.continue();
    });
    await page.route('**/api/unit-reference', route => {
      const payload = route.request().postDataJSON();
      assert.deepEqual(payload.unit_refs, [unitRef]);
      assert.equal(payload.source_id, unitRef.source_id);
      assert.equal(payload.field_id, 'fixture-field');
      referenceCalls++;
      return route.continue();
    });
    const savesBeforeReference = savedModels.length;
    for (let attempt = 0; attempt < 2; attempt++) {
      await page.getByRole('button', {name: '引用论文单元', exact: true}).click();
      await page.getByLabel('选择知识领域').selectOption('0');
      await page.locator('#editor').getByLabel('完整论文单元 D', {exact: false}).check();
      await page.getByText('分析正文与Canvas均保留原件。', {exact: true}).waitFor();
      if (attempt === 0 && process.env.SCHOLAR_EXPLORER_UNIT_SCREENSHOT) await page.screenshot({path: process.env.SCHOLAR_EXPLORER_UNIT_SCREENSHOT, fullPage: true});
      await page.getByRole('button', {name: '应用修改', exact: true}).click();
      await page.locator('#editor').waitFor({state: 'hidden'});
      await page.locator('#result-count').filter({hasText: /^4$/}).waitFor();
    }
    assert.equal(referenceCalls, 2);
    assert.equal(savedModels.length, savesBeforeReference);
    assert.equal(await page.getByRole('button', {name: '保存修改', exact: true}).isDisabled(), false);
    fieldsAvailable = false;
    await page.getByRole('button', {name: '引用论文单元', exact: true}).click();
    await page.getByText('尚无已登记知识来源。', {exact: true}).waitFor();
    assert.equal(await page.locator('#editor').getByLabel('标题', {exact: true}).count(), 0);
    await page.getByRole('button', {name: '应用修改', exact: true}).click();
    await page.locator('#form-error:not([hidden])').waitFor();
    assert.equal(await page.locator('#editor').evaluate(editor => editor.open), true);
    await page.getByRole('button', {name: '取消', exact: true}).click();
    // Non-paper resources remain editable but cannot be relabelled as papers.
    await page.locator('.result-card').filter({hasText: '示例工作 B'}).click();
    await page.getByRole('button', {name: '编辑工作', exact: true}).click();
    assert.equal(await page.getByLabel('材料类型').isDisabled(), false);
    assert.equal(await page.getByLabel('材料类型').getByRole('option', {name: '论文', exact: true}).count(), 0);
    await page.getByRole('button', {name: '取消', exact: true}).click();
    await page.getByRole('button', {name: '保存修改', exact: true}).click();
    await page.locator('#status').filter({hasText: '修改已保存'}).waitFor();
    const referenced = savedModels.at(-1).works.filter(work => work.entity_ref?.source_id === unitRef.source_id && work.entity_ref?.object_id === unitRef.object_id);
    assert.equal(referenced.length, 1);
    assert.equal(referenced[0].assets.length, 2);
    await page.locator('#graph-tab').click();
    if (process.env.SCHOLAR_EXPLORER_SCREENSHOT) {
      await page.locator('.left-panel').evaluate(element => { element.scrollTop = 0; });
      await page.locator('.detail-panel').evaluate(element => { element.scrollTop = 0; });
      await page.screenshot({path: process.env.SCHOLAR_EXPLORER_SCREENSHOT, fullPage: true});
    }
    // A hand-edited declaration can retain sortable=true for unsupported kinds.
    // Only alter this read response; the saved fixture remains unchanged.
    await page.route('**/api/state', async route => {
      const response = await route.fetch();
      const state = await response.json();
      const definitions = state.data.dimensions;
      definitions.find(dimension => dimension.id === 'foundation').sortable = true;
      Object.assign(definitions.find(dimension => dimension.id === 'paradigm'),
        {kind: 'reference', multiple: false, sortable: true});
      Object.assign(definitions.find(dimension => dimension.id === 'problem'),
        {kind: 'text', multiple: true, sortable: true});
      await route.fulfill({response, json: state});
    });
    await page.reload();
    await page.locator('#result-count').filter({hasText: /^4$/}).waitFor();
    for (const label of ['基座', '范式', '前沿问题']) {
      assert.equal(await page.locator('#sort').getByRole('option', {name: label, exact: true}).count(), 0);
    }
    assert.equal(await page.locator('#sort').getByRole('option', {name: '响应时间', exact: true}).count(), 1);
    assert.deepEqual(errors, []);
    console.log('PASS: atomic paper references, async draft validation, paper asset boundary, native-reader diagnostics, dynamic dimensions, supported sorting, records and asset preview');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
