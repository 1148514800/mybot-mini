// Untrusted Markdown becomes DOM text nodes only. Raw HTML/images are never inserted.
const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
export function inline(parent, text) {
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\s)]+\))/g;
  let end = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(end, match.index)));
    const value = match[0]; let node;
    if (value.startsWith('`')) node = el('code', value.slice(1, -1));
    else if (value.startsWith('**')) node = el('strong', value.slice(2, -2));
    else {
      const split = value.indexOf(']('); const label = value.slice(1, split); const href = value.slice(split + 2, -1);
      try { const url = new URL(href); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || href.length > 2000) throw Error();
        node = el('a', label); node.href = url.href; node.target = '_blank'; node.rel = 'noopener noreferrer';
      } catch { node = el('span', value); }
    }
    parent.append(node); end = match.index + value.length;
  }
  parent.append(document.createTextNode(text.slice(end)));
}
function highlight(code, text) {
  const pattern = /("[^"\n]*"|'[^'\n]*'|#[^\n]*|\/\/[^\n]*|\b(?:def|class|return|import|from|as|if|else|elif|for|while|try|except|raise|async|await|with|True|False|None|const|let|function|export|new|throw|true|false|null)\b)/g;
  let end = 0;
  for (const match of text.matchAll(pattern)) { code.append(document.createTextNode(text.slice(end, match.index))); const value = match[0]; code.append(el('span', value, /^['"]/.test(value) ? 'syntax-string' : /^(#|\/\/)/.test(value) ? 'syntax-comment' : 'syntax-keyword')); end = match.index + value.length; }
  code.append(document.createTextNode(text.slice(end)));
}
export function markdown(text) {
  const root = el('div'); const lines = String(text).slice(0, 32768).split('\n'); let i = 0;
  while (i < lines.length) {
    let line = lines[i];
    if (line.startsWith('```')) {
      const language = line.slice(3).trim().slice(0, 32) || 'text'; const body = [];
      for (i++; i < lines.length && !lines[i].startsWith('```'); i++) body.push(lines[i]); i++;
      const wrap = el('div', undefined, 'code-block'), header = el('div', undefined, 'code-header'), copy = el('button', '复制代码'); copy.type = 'button';
      const source = body.join('\n'); copy.addEventListener('click', () => copyText(source, copy)); header.append(el('span', language), copy);
      const pre = el('pre'), code = el('code'); highlight(code, source); pre.append(code); wrap.append(header, pre); root.append(wrap); continue;
    }
    if (!line.trim()) { i++; continue; }
    if (i + 1 < lines.length && line.includes('|') && /^\|?\s*:?-{3,}/.test(lines[i+1].trim())) {
      const wrap = el('div', undefined, 'table-wrap'), table = el('table');
      const cells = row => row.replace(/^\s*\||\|\s*$/g, '').split('|');
      const row = (source, tag) => { const tr = el('tr'); for (const value of cells(source)) { const td = el(tag); inline(td, value.trim()); tr.append(td); } return tr; };
      const head = el('thead'); head.append(row(line, 'th')); table.append(head); const body = el('tbody'); i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) body.append(row(lines[i++], 'td'));
      table.append(body); wrap.append(table); root.append(wrap); continue;
    }
    const heading = /^(#{1,3})\s+(.+)/.exec(line);
    if (heading) { const h = el('h' + heading[1].length); inline(h, heading[2]); root.append(h); i++; continue; }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const list = el(/^\s*\d/.test(line) ? 'ol' : 'ul');
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) { const li = el('li'); inline(li, lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, '')); list.append(li); }
      root.append(list); continue;
    }
    const node = el(line.startsWith('> ') ? 'blockquote' : 'p'); inline(node, line.startsWith('> ') ? line.slice(2) : line); root.append(node); i++;
  }
  return root;
}
export async function copyText(text, button) {
  try { await navigator.clipboard.writeText(text); const old = button.textContent; button.textContent = '已复制'; setTimeout(() => { button.textContent = old; }, 1400); }
  catch { button.textContent = '复制失败，请手动选择'; }
}
