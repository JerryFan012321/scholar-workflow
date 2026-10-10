// Offline development preview. The editable Canvas remains the actual proposal.
const fs = require('node:fs');
const path = require('node:path');
const [canvasPath, dependencies, browserExecutable, outputSuffix = ''] = process.argv.slice(2);
if (!canvasPath || !dependencies) throw new Error('Expected canvas path and bundled dependencies');
if (!/^[\p{L}\p{N}_-]*$/u.test(outputSuffix)) throw new Error('Unsafe output suffix');
const { chromium } = require(require.resolve('playwright', { paths: [dependencies] }));
const directory = path.dirname(canvasPath);
const output = name => path.join(directory, `${name}${outputSuffix}`);
const canvas = JSON.parse(fs.readFileSync(canvasPath, 'utf8'));
const textNodes = canvas.nodes.filter(n => n.type === 'text');
const nodes = new Map(canvas.nodes.map(n => [n.id, n]));
const targets = new Set(canvas.edges.map(e => e.toNode));
const root = textNodes.find(n => !targets.has(n.id));
const left = Math.min(...canvas.nodes.map(n => n.x));
const top = Math.min(...canvas.nodes.map(n => n.y));
const width = Math.max(...canvas.nodes.map(n => n.x + n.width)) - left;
const height = Math.max(...canvas.nodes.map(n => n.y + n.height)) - top;
const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const image = /!\[([^\]\r\n]*)\|([0-9]+)x([0-9]+)\]\(\.\/(attachments\/[^\r\n)]+\.png)\)/g;
function content(text) {
  const images = [];
  text = text.replace(image, (_, caption, w, h, target) => {
    const relative = decodeURIComponent(target);
    if (relative.includes('..') || path.isAbsolute(relative)) throw new Error('Unsafe image');
    const file = path.join(directory, relative);
    if (fs.lstatSync(file).isSymbolicLink()) throw new Error('Symlink image');
    const data = fs.readFileSync(file).toString('base64');
    const index = images.push(`<img alt="${escape(caption)}" width="${w}" height="${h}" src="data:image/png;base64,${data}">`) - 1;
    return `IMAGE_TOKEN_${index}`;
  });
  // Show exact visible aliases, not executable native application protocols.
  text = text.replace(/\[\[[^\]|]+\|([^\]]+)\]\]/g, (_, label) => `LINK_TOKEN_${label}_END`)
    .replace(/\[([^\]]*)\]\([^)]*\)/g, (_, label) => `LINK_TOKEN_${label}_END`);
  return escape(text).split('\n').map(line => {
    line = line.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/LINK_TOKEN_(.*?)_END/g, '<span class="link">$1</span>')
      .replace(/IMAGE_TOKEN_([0-9]+)/g, (_, index) => images[Number(index)]);
    return `<div class="line">${line || '&nbsp;'}</div>`;
  }).join('');
}
const paths = canvas.edges.map(edge => {
  const a = nodes.get(edge.fromNode), b = nodes.get(edge.toNode);
  const x1 = a.x + a.width - left + 24, x2 = b.x - left + 24;
  const y1 = a.y + a.height / 2 - top + 24, y2 = b.y + b.height / 2 - top + 24;
  const middle = (x1 + x2) / 2;
  return `<path d="M${x1} ${y1}H${middle}V${y2}H${x2}" stroke="${escape(edge.color || '#a7b4b5')}"/>`;
}).join('');
const boxes = canvas.nodes.map(node => {
  if (node.type === 'group') {
    return `<div class="group" style="left:${node.x - left + 24}px;top:${node.y - top + 24}px;width:${node.width}px;height:${node.height}px;border-color:${escape(node.color || '#a7b4b5')};"><span>${escape(node.label || '')}</span></div>`;
  }
  const isRoot = node.id === root.id;
  const background = node.color || 'transparent';
  return `<div class="node" data-id="${escape(node.id)}" style="left:${node.x - left + 24}px;top:${node.y - top + 24}px;width:${node.width}px;height:${node.height}px;background:${escape(background)};${isRoot ? 'color:white;' : ''}"><div class="content">${content(node.text)}</div></div>`;
}).join('');
const html = `<!doctype html><meta charset="utf-8"><title>布局静态预览（非Obsidian原生）</title>
<style>*{box-sizing:border-box}body{margin:0;background:#fff;color:#29383a;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}#stage{position:relative;width:${width + 48}px;height:${height + 48}px;transform-origin:top left}svg{position:absolute;inset:0;pointer-events:none}path{fill:none;stroke-width:1.5}.group{position:absolute;border:1px solid;border-radius:8px;pointer-events:none;background:transparent}.group>span{position:absolute;top:0;left:8px;font-size:16px;line-height:18px;background:white;padding:0 8px}.node{position:absolute;border-radius:5px;overflow:hidden}.content{padding:12px 14px;font-size:18px;line-height:21px;overflow-wrap:anywhere}.line{min-height:21px}.link{color:#276f8a;text-decoration:underline}img{display:block;max-width:100%;object-fit:contain}</style>
<div id="stage"><svg width="${width + 48}" height="${height + 48}">${paths}</svg>${boxes}</div>`;

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(browserExecutable ? { executablePath: browserExecutable } : {}),
    args: ['--disable-background-networking', '--disable-component-update'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 });
    await page.route('**/*', route => route.abort());
    await page.setContent(html);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('img').evaluateAll(images => Promise.all(images.map(i => i.decode())));
    const measurements = await page.locator('.node').evaluateAll(boxes => boxes.map(box => {
      const content = box.querySelector('.content');
      return { id: box.dataset.id, height: box.clientHeight,
        content_height: content.getBoundingClientRect().height,
        remaining: box.clientHeight - content.getBoundingClientRect().height };
    }));
    const clipped = measurements.filter(m => m.remaining < 0);
    const clickSpace = measurements.filter(m => m.remaining < 21);
    const scale = 1600 / (width + 48);
    await page.evaluate(({ scale, height }) => {
      document.querySelector('#stage').style.transform = `scale(${scale})`;
      document.body.style.width = '1600px';
      document.body.style.height = `${(height + 48) * scale}px`;
      document.body.style.overflow = 'hidden';
    }, { scale, height });
    await page.screenshot({ path: output('总览') + '.png', fullPage: true });
    const module = textNodes.find(n => /^\*\*(?:流程模块|Pipeline module) 1\*\*/.test(n.text));
    if (!module) throw new Error('No module 1 to preview');
    const group = [module, ...canvas.edges.filter(e => e.fromNode === module.id).map(e => nodes.get(e.toNode))];
    const crop = { x: Math.min(...group.map(n => n.x)), y: Math.min(...group.map(n => n.y)),
      right: Math.max(...group.map(n => n.x + n.width)), bottom: Math.max(...group.map(n => n.y + n.height)) };
    const detail = await browser.newPage({ viewport: {
      width: crop.right - crop.x + 48, height: crop.bottom - crop.y + 48
    }, deviceScaleFactor: 1 });
    await detail.route('**/*', route => route.abort());
    await detail.setContent(html);
    await detail.evaluate(() => document.fonts.ready);
    await detail.locator('img').evaluateAll(images => Promise.all(images.map(i => i.decode())));
    await detail.evaluate(({ crop, left, top }) => {
      document.querySelector('#stage').style.transform = `translate(${-crop.x + left}px,${-crop.y + top}px)`;
      document.body.style.width = `${crop.right - crop.x + 48}px`;
      document.body.style.height = `${crop.bottom - crop.y + 48}px`;
      document.documentElement.style.overflow = 'hidden';
      document.body.style.overflow = 'hidden';
      window.scrollTo(0, 0);
    }, { crop, left, top });
    await detail.locator('.node').evaluateAll((boxes, ids) => {
      for (const box of boxes) {
        if (!ids.includes(box.dataset.id)) box.style.visibility = 'hidden';
      }
    }, group.map(node => node.id));
    const detailBounds = await detail.locator('.node').evaluateAll((boxes, ids) => boxes
      .filter(box => ids.includes(box.dataset.id)).map(box => {
        const rect = box.getBoundingClientRect();
        return { id: box.dataset.id, x: rect.x, y: rect.y,
          right: rect.right, bottom: rect.bottom };
      }), group.map(node => node.id));
    const detailWidth = crop.right - crop.x + 48;
    const detailHeight = crop.bottom - crop.y + 48;
    if (detailBounds.some(rect => rect.x < 24 || rect.y < 24
      || rect.right > detailWidth - 24 || rect.bottom > detailHeight - 24)) {
      throw new Error('Detail crop omits a module node');
    }
    await detail.screenshot({ path: output('方法模块局部') + '.png' });
    fs.writeFileSync(output('静态预览') + '.html', html, { flag: 'wx' });
    fs.writeFileSync(output('预览检查') + '.json', JSON.stringify({
      kind: 'offline-development-preview-not-native', font: 18, line_height: 21,
      nodes: measurements.length, clipped, click_space_under_21: clickSpace,
      measurements, detail_bounds: detailBounds, native_and_human: 'pending'
    }, null, 2), { flag: 'wx' });
    console.log(JSON.stringify({ nodes: measurements.length, clipped: clipped.length,
      click_space_under_21: clickSpace.length, overview_scale: scale, detail_scale: 1 }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
