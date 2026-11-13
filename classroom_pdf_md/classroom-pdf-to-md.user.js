// ==UserScript==
// @name         Classroom PDF → Markdown
// @namespace    https://github.com/donats-cl/python_scripts_donats
// @version      1.0.0
// @description  Кнопка «MD» рядом с PDF-вложениями Google Classroom: скачивает файл и сохраняет его как Markdown
// @author       donats_cl
// @match        https://classroom.google.com/*
// @require      https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/legacy/build/pdf.min.js
// @grant        GM_xmlhttpRequest
// @connect      drive.google.com
// @connect      drive.usercontent.google.com
// @connect      cdn.jsdelivr.net
// @run-at       document-idle
// @noframes
// ==/UserScript==

(function () {
  'use strict';

  // ---------------------------------------------------------------- константы

  const PDFJS_VER = '3.11.174';
  const CDN = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@' + PDFJS_VER;
  const PDFJS_URL = CDN + '/legacy/build/pdf.min.js';
  const WORKER_URL = CDN + '/legacy/build/pdf.worker.min.js';
  const CMAP_URL = CDN + '/cmaps/';
  const STD_FONT_URL = CDN + '/standard_fonts/';

  const HAS_GM = typeof GM_xmlhttpRequest === 'function';
  const IS_CLASSROOM = /(^|\.)classroom\.google\.com$/.test(location.hostname);

  // ------------------------------------------------------------------ утилиты

  function gmRequest(o) {
    return new Promise((resolve, reject) => {
      if (!HAS_GM) return reject(new Error('GM_xmlhttpRequest недоступен'));
      GM_xmlhttpRequest({
        method: o.method || 'GET',
        url: o.url,
        headers: o.headers,
        data: o.data,
        responseType: o.responseType || 'arraybuffer',
        timeout: 120000,
        onload: (r) => resolve({ status: r.status, headers: r.responseHeaders || '', data: r.response }),
        onerror: () => reject(new Error('Сетевая ошибка: ' + o.url)),
        ontimeout: () => reject(new Error('Таймаут: ' + o.url)),
        onabort: () => reject(new Error('Запрос отменён')),
      });
    });
  }

  async function loadText(url) {
    if (HAS_GM) return (await gmRequest({ url, responseType: 'text' })).data;
    const r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status + ': ' + url);
    return r.text();
  }

  const LIGATURES = {
    '\uFB00': 'ff', '\uFB01': 'fi', '\uFB02': 'fl',
    '\uFB03': 'ffi', '\uFB04': 'ffl', '\uFB05': 'ft', '\uFB06': 'st',
  };

  function clean(s) {
    return String(s)
      .replace(/[\u200B-\u200D\uFEFF\u00AD]/g, '')
      .replace(/\u00A0/g, ' ')
      .replace(/[\uFB00-\uFB06]/g, (c) => LIGATURES[c] || c)
      .replace(/[ \t\r\n]+/g, ' ')
      .trim();
  }

  // ------------------------------------------------------------------- PDF.js

  let pdfjsPromise = null;

  function getPdfjs() {
    if (pdfjsPromise) return pdfjsPromise;
    pdfjsPromise = (async () => {
      let lib = (typeof pdfjsLib !== 'undefined' && pdfjsLib) || globalThis.pdfjsLib;
      if (!lib) lib = await injectScript(PDFJS_URL);
      await setupWorker(lib);
      return lib;
    })();
    return pdfjsPromise;
  }

  function injectScript(url) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = url;
      s.onload = () => {
        const lib = globalThis.pdfjsLib;
        lib ? resolve(lib) : reject(new Error('pdf.js загрузился, но pdfjsLib не найден'));
      };
      s.onerror = () => reject(new Error('Не удалось загрузить pdf.js: ' + url));
      document.head.appendChild(s);
    });
  }

  // pdf.js v3 создаёт Worker из workerSrc только для same-origin URL,
  // поэтому blob отдаём напрямую как workerPort.
  async function setupWorker(lib) {
    if (lib.GlobalWorkerOptions.workerSrc || lib.GlobalWorkerOptions.workerPort) return;
    let blobUrl = WORKER_URL;
    try {
      const code = await loadText(WORKER_URL);
      blobUrl = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }));
    } catch (e) {
      /* нет доступа к CDN — попробуем напрямую */
    }
    try {
      lib.GlobalWorkerOptions.workerPort = new Worker(blobUrl);
    } catch (e) {
      lib.GlobalWorkerOptions.workerSrc = blobUrl;
    }
  }

  // ------------------------------------------------------- скачивание из Drive

  function driveIdFromUrl(href) {
    if (!href) return null;
    let m = href.match(/drive\.google\.com\/file\/(?:u\/\d+\/)?d\/([-\w]{20,})/);
    if (m) return m[1];
    m = href.match(/drive\.google\.com\/(?:open|uc)\?(?:[^#]*?&)?id=([-\w]{20,})/);
    if (m) return m[1];
    m = href.match(/drive\.usercontent\.google\.com\/download\?(?:[^#]*?&)?id=([-\w]{20,})/);
    return m ? m[1] : null;
  }

  function looksLikePdf(data) {
    const bytes =
      data instanceof Uint8Array ? data : new Uint8Array(data instanceof ArrayBuffer ? data : []);
    return bytes.length > 4 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46;
  }

  function nameFromHeaders(headers) {
    const m = /filename\*=UTF-8''([^;\r\n]+)/i.exec(headers) || /filename="?([^";\r\n]+)"?/i.exec(headers);
    if (!m) return '';
    try {
      return decodeURIComponent(m[1].trim());
    } catch (e) {
      return m[1].trim();
    }
  }

  // Drive отдаёт HTML-заглушку «не удалось проверить на вирусы» с формой подтверждения.
  function parseConfirmForm(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const form = doc.querySelector('form#download-form') || doc.querySelector('form[action*="download"]');
    if (!form) return null;
    const params = new URLSearchParams();
    form.querySelectorAll('input[name]').forEach((i) => {
      if (i.value !== undefined && i.value !== null) params.set(i.name, i.value);
    });
    const action = form.getAttribute('action') || 'https://drive.usercontent.google.com/download';
    return action + '?' + params.toString();
  }

  async function downloadPdf(id) {
    const urls = [
      'https://drive.usercontent.google.com/download?id=' + id + '&export=download&confirm=t',
      'https://drive.google.com/uc?export=download&id=' + id,
    ];
    let lastErr = null;

    for (const url of urls) {
      try {
        const r = await gmRequest({ url, responseType: 'arraybuffer' });
        if (r.status !== 200) {
          lastErr = new Error('Drive ответил HTTP ' + r.status);
          continue;
        }
        if (looksLikePdf(r.data)) {
          return { buf: r.data, name: nameFromHeaders(r.headers) };
        }
        const html = new TextDecoder('utf-8').decode(new Uint8Array(r.data));
        const confirmUrl = parseConfirmForm(html);
        if (confirmUrl) {
          const r2 = await gmRequest({ url: confirmUrl, responseType: 'arraybuffer' });
          if (r2.status === 200 && looksLikePdf(r2.data)) {
            return { buf: r2.data, name: nameFromHeaders(r2.headers) };
          }
        }
        lastErr = new Error('Drive вернул не PDF — вероятно, файл закрыт для скачивания');
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error('Не удалось скачать файл с Drive');
  }

  // ------------------------------------------------------- PDF → строки текста

  // Склеивает текстовые фрагменты pdf.js в строки по базовой линии.
  function collectItems(textContent, pageWidth) {
    const items = [];
    for (const it of textContent.items) {
      if (!it.str || !it.str.trim()) continue;
      const tr = it.transform || [1, 0, 0, 1, 0, 0];
      const h = it.height || Math.abs(tr[3]) || 10;
      const style = textContent.styles[it.fontName] || {};
      items.push({
        str: it.str,
        x: tr[4],
        y: tr[5],
        w: it.width || 0,
        h,
        bold: /bold|black|heavy|semibold/i.test(style.fontFamily || ''),
      });
    }
    return items;
  }

  function groupRows(items, pageWidth) {
    items.sort((a, b) => b.y - a.y || a.x - b.x);
    const rows = [];
    for (const it of items) {
      let row = null;
      for (let i = rows.length - 1; i >= Math.max(0, rows.length - 3); i--) {
        const cand = rows[i];
        if (Math.abs(cand.y - it.y) > Math.max(2, it.h * 0.45)) continue;
        // далёкие куски на одной высоте — соседняя колонка или ячейка таблицы
        const ext = rowExtent(cand);
        const gap = it.x > ext.xEnd ? it.x - ext.xEnd : ext.x - (it.x + it.w);
        if (gap > Math.max(it.h * 3, 8)) continue;
        row = cand;
        break;
      }
      if (!row) {
        row = { y: it.y, items: [] };
        rows.push(row);
      }
      row.items.push(it);
    }
    return rows;
  }

  function rowsToLines(rows, pageWidth) {
    const lines = [];
    for (const row of rows) {
      row.items.sort((a, b) => a.x - b.x);
      let text = '';
      let prevEnd = null;
      for (const it of row.items) {
        if (prevEnd !== null) {
          const gap = it.x - prevEnd;
          if (gap > Math.max(1.5, it.h * 0.18) && !/\s$/.test(text) && !/^\s/.test(it.str)) text += ' ';
        }
        text += it.str;
        prevEnd = it.x + it.w;
      }
      text = clean(text);
      if (!text) continue;

      let sizeSum = 0;
      let weight = 0;
      let boldChars = 0;
      let x = Infinity;
      let xEnd = -Infinity;
      for (const it of row.items) {
        const n = it.str.trim().length || 1;
        sizeSum += it.h * n;
        weight += n;
        if (it.bold) boldChars += n;
        x = Math.min(x, it.x);
        xEnd = Math.max(xEnd, it.x + it.w);
      }
      lines.push({
        text,
        size: sizeSum / weight,
        bold: boldChars >= weight * 0.6,
        x,
        xEnd,
        y: row.y,
        width: pageWidth,
      });
    }
    return lines;
  }

  function rowExtent(row) {
    let x = Infinity;
    let xEnd = -Infinity;
    for (const it of row.items) {
      x = Math.min(x, it.x);
      xEnd = Math.max(xEnd, it.x + it.w);
    }
    return { x, xEnd };
  }

  // Двухколоночная вёрстка: ни одна широкая строка не пересекает середину страницы,
  // а строки слева и справа примерно уравновешены.
  function buildLines(textContent, pageWidth) {
    const items = collectItems(textContent, pageWidth);
    if (!items.length) return [];

    const rows = groupRows(items, pageWidth);
    const mid = pageWidth / 2;

    let leftRows = 0;
    let rightRows = 0;
    let wideCrossing = 0;
    const kind = rows.map((row) => {
      const { x, xEnd } = rowExtent(row);
      if (x < mid && xEnd > mid) {
        if (xEnd - x > pageWidth * 0.45) wideCrossing++;
        return 'span';
      }
      if (xEnd <= mid) {
        leftRows++;
        return 'left';
      }
      rightRows++;
      return 'right';
    });

    const twoColumn =
      wideCrossing === 0 &&
      leftRows >= 3 &&
      rightRows >= 3 &&
      Math.min(leftRows, rightRows) / Math.max(leftRows, rightRows) >= 0.25;
    if (!twoColumn) return rowsToLines(rows, pageWidth);

    const left = [];
    const right = [];
    const spanning = [];
    rows.forEach((row, i) => {
      const k = kind[i];
      if (k === 'span') spanning.push(row);
      else (k === 'left' ? left : right).push(row);
    });

    const leftLines = rowsToLines(left, pageWidth);
    const rightLines = rowsToLines(right, pageWidth);
    const colTop = Math.max(
      leftLines.length ? leftLines[0].y : -Infinity,
      rightLines.length ? rightLines[0].y : -Infinity
    );
    const top = [];
    const bottom = [];
    for (const line of rowsToLines(spanning, pageWidth)) {
      (line.y >= colTop - 1 ? top : bottom).push(line);
    }
    return top.concat(leftLines, rightLines, bottom);
  }

  const PAGE_NUMBER_RE = /^[\s\-–—_.·]*(\d{1,3}|[ivxlcdm]{1,6})[\s\-–—_.·]*$/i;
  const BULLET_RE = /^([•·‣▪◦∙*\-–—])\s+/;
  const NUMBERED_RE = /^(\d{1,2})[.)]\s+/;

  function isPageNumber(text) {
    return PAGE_NUMBER_RE.test(text) || /^(стр\.?|page)\s*\d+$/i.test(text);
  }

  // Повторяющиеся колонтитулы: строка в начале/конце страницы, встречающаяся на 3+ страницах.
  function collectRepeats(pages) {
    const counts = new Map();
    for (const lines of pages) {
      const edge = new Set();
      lines.slice(0, 2).concat(lines.slice(-2)).forEach((l) => edge.add(l.text));
      for (const t of edge) counts.set(t, (counts.get(t) || 0) + 1);
    }
    const repeats = new Set();
    for (const [text, n] of counts) {
      if (n >= 3 && text.length <= 120) repeats.add(text);
    }
    return repeats;
  }

  function bodyFontSize(pages) {
    const hist = new Map();
    for (const lines of pages) {
      for (const l of lines) {
        const key = Math.round(l.size * 2) / 2;
        hist.set(key, (hist.get(key) || 0) + l.text.length);
      }
    }
    let best = 10;
    let bestWeight = -1;
    for (const [size, weight] of hist) {
      if (weight > bestWeight) {
        bestWeight = weight;
        best = size;
      }
    }
    return best || 10;
  }

  function median(values) {
    if (!values.length) return 0;
    const s = values.slice().sort((a, b) => a - b);
    const m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  // Метрики страницы по «естественному» порядку строк (сверху вниз).
  function pageMetrics(lines, body) {
    let maxWidth = 0;
    const gaps = [];
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      maxWidth = Math.max(maxWidth, l.xEnd - l.x);
      if (i > 0) {
        const gap = lines[i - 1].y - l.y;
        if (gap > 0 && gap < body * 4) gaps.push(gap);
      }
    }
    return { maxWidth: maxWidth || 1, leading: median(gaps) || body * 1.2 };
  }

  function headingLevel(line, body) {
    const ratio = line.size / body;
    if (ratio >= 1.45) return 1;
    if (ratio >= 1.2) return 2;
    if (ratio >= 1.08) return 3;
    if (line.bold && line.text.length <= 80 && !/[.:;,]$/.test(line.text)) return 3;
    return 0;
  }

  // Собирает markdown-блоки одной страницы.
  function pageToBlocks(lines, ctx) {
    const { body, leading, maxWidth, repeats } = ctx;
    const out = [];

    // Продолжение абзаца: тот же вертикальный ритм и предыдущая строка «полная»
    // (короткая строка почти всегда завершает абзац).
    const sameParagraph = (prev, line) => {
      if (!prev || prev.type !== 'p') return false;
      // перенос через дефис — всегда продолжение слова
      if (/[a-zа-яё]-$/i.test(prev.text)) return true;
      const gap = prev.lastY - line.y;
      const shortPrev = prev.lastXEnd - prev.x < maxWidth * 0.8;
      return gap <= leading * 1.6 && !shortPrev;
    };

    for (const line of lines) {
      const text = line.text;
      if (!text || isPageNumber(text) || repeats.has(text)) continue;

      const prev = out[out.length - 1];
      const joinable = sameParagraph(prev, line);

      // Сначала заголовки: «1. Основные определения» — это раздел, а не пункт списка
      const level = headingLevel(line, body);
      if (level) {
        out.push({ type: 'h', level, text });
        continue;
      }

      const bullet = BULLET_RE.exec(text);
      const numbered = !bullet && NUMBERED_RE.exec(text);
      const dashBullet = bullet && /^[—–-]$/.test(bullet[1]);

      // «— это связный граф…» в русском тексте — тире, а не пункт списка
      if ((bullet || numbered) && !(dashBullet && joinable)) {
        const cut = bullet ? bullet[0].length : numbered[0].length;
        out.push({
          type: 'li',
          ordered: !!numbered,
          marker: numbered ? numbered[1] + '. ' : '- ',
          text: text.slice(cut).trim(),
        });
        continue;
      }

      if (joinable) {
        const hyphenated = /[a-zа-яё]-$/i.test(prev.text);
        prev.text = hyphenated ? prev.text.slice(0, -1) + text : prev.text + ' ' + text;
        prev.lastY = line.y;
        prev.lastXEnd = line.xEnd;
        prev.size = Math.max(prev.size, line.size);
      } else {
        out.push({ type: 'p', text, size: line.size, x: line.x, lastXEnd: line.xEnd, lastY: line.y });
      }
    }

    return out;
  }

  function blocksToMarkdown(blocks) {
    const chunks = [];
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (b.type === 'h') chunks.push('#'.repeat(b.level) + ' ' + b.text);
      else if (b.type === 'li') {
        // пункты одного списка идут подряд без пустых строк
        let group = b.marker + b.text;
        while (
          i + 1 < blocks.length &&
          blocks[i + 1].type === 'li' &&
          blocks[i + 1].ordered === b.ordered
        ) {
          i++;
          group += '\n' + blocks[i].marker + blocks[i].text;
        }
        chunks.push(group);
      } else chunks.push(b.text);
    }
    return chunks.join('\n\n').replace(/\n{3,}/g, '\n\n').trim();
  }

  // ------------------------------------------------------------------- главное

  async function pdfToMarkdown(buf, meta) {
    const lib = await getPdfjs();
    const data = buf instanceof Uint8Array ? buf : new Uint8Array(buf);

    const doc = await lib.getDocument({
      data,
      cMapUrl: CMAP_URL,
      cMapPacked: true,
      standardFontDataUrl: STD_FONT_URL,
      isEvalSupported: false,
      useSystemFonts: true,
    }).promise;

    try {
      const pages = [];
      for (let p = 1; p <= doc.numPages; p++) {
        const page = await doc.getPage(p);
        const viewport = page.getViewport({ scale: 1 });
        const width = Math.abs(viewport.width);
        const tc = await page.getTextContent();
        pages.push({ lines: buildLines(tc, width) });
        page.cleanup();
      }

      const natural = pages.map((p) => p.lines);
      const chars = natural.reduce(
        (n, lines) => n + lines.reduce((m, l) => m + l.text.length, 0),
        0
      );
      if (chars < 20) {
        throw new Error('В PDF нет текстового слоя — похоже, это скан или фото');
      }

      const body = bodyFontSize(natural);
      const repeats = collectRepeats(natural);

      const blocks = [];
      for (const { lines } of pages) {
        const ctx = { body, repeats, ...pageMetrics(lines, body) };
        blocks.push(...pageToBlocks(lines, ctx));
      }

      const text = blocksToMarkdown(blocks);
      return {
        markdown: frontMatter(meta) + text + '\n',
        pages: doc.numPages,
        title: meta.title,
      };
    } finally {
      doc.destroy();
    }
  }

  function yamlString(s) {
    return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
  }

  function frontMatter(meta) {
    const lines = ['---', 'title: ' + yamlString(meta.title || '')];
    if (meta.source) lines.push('source: ' + yamlString(meta.source));
    lines.push('converted: ' + new Date().toISOString().slice(0, 10));
    lines.push('---', '');
    return lines.join('\n');
  }

  function safeFileName(name) {
    let s = String(name || '').replace(/\.pdf$/i, '').replace(/[\\/:*?"<>|\u0000-\u001F]/g, '_');
    s = s.replace(/\s+/g, ' ').trim().replace(/^\.+/, '').slice(0, 120).trim();
    return (s || 'document') + '.md';
  }

  function saveMarkdown(name, text) {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function convertAttachment(anchor) {
    const id = driveIdFromUrl(anchor.href);
    if (!id) throw new Error('Не нашёл ID файла в ссылке');

    const { buf, name } = await downloadPdf(id);
    const meta = {
      title: (name || anchor.getAttribute('aria-label') || anchor.textContent || id).replace(/\.pdf$/i, '').trim(),
      source: anchor.href.split('?')[0],
    };
    const result = await pdfToMarkdown(buf, meta);
    saveMarkdown(safeFileName(name || meta.title), result.markdown);
    return result;
  }

  // ---------------------------------------------------------------- интерфейс

  function makeButton(anchor) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cpdm-btn';
    btn.textContent = 'MD';
    btn.title = 'Скачать этот PDF как Markdown';
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (btn.dataset.busy) return;
      btn.dataset.busy = '1';
      btn.dataset.state = 'busy';
      btn.textContent = '···';
      try {
        const res = await convertAttachment(anchor);
        btn.dataset.state = 'ok';
        btn.textContent = '✓';
        toast('Готово: ' + res.pages + ' стр. → .md', false);
      } catch (err) {
        console.error('[Classroom PDF→MD]', err);
        btn.dataset.state = 'err';
        btn.textContent = 'MD';
        toast(String(err && err.message ? err.message : err), true);
      } finally {
        setTimeout(() => {
          delete btn.dataset.busy;
          delete btn.dataset.state;
          btn.textContent = 'MD';
        }, 4000);
      }
    });
    return btn;
  }

  let toastBox = null;
  function toast(text, isError) {
    if (!toastBox) {
      toastBox = document.createElement('div');
      toastBox.className = 'cpdm-toast';
      document.body.appendChild(toastBox);
    }
    const item = document.createElement('div');
    item.className = 'cpdm-toast-item' + (isError ? ' cpdm-error' : '');
    item.textContent = text;
    toastBox.appendChild(item);
    setTimeout(() => item.remove(), isError ? 9000 : 4000);
  }

  function enhance(root) {
    const anchors = root.querySelectorAll('a[href*="drive.google.com/"]');
    for (const a of anchors) {
      if (a.dataset.cpdm) continue;
      if (!driveIdFromUrl(a.href)) continue;
      a.dataset.cpdm = '1';
      try {
        a.insertAdjacentElement('afterend', makeButton(a));
      } catch (e) {
        /* разметка неожиданная — молча пропускаем */
      }
    }
  }

  const CSS = [
    '.cpdm-btn{all:unset;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;',
    'min-width:30px;height:22px;margin:0 4px;padding:0 6px;border-radius:6px;cursor:pointer;',
    'font:600 11px/1 Roboto,Arial,sans-serif;letter-spacing:.3px;position:relative;z-index:10;',
    'color:#0b57d0;background:rgba(11,87,208,.08);border:1px solid rgba(11,87,208,.35);',
    'transition:background .15s,color .15s,transform .15s}',
    '.cpdm-btn:hover{background:#0b57d0;color:#fff;transform:translateY(-1px)}',
    '.cpdm-btn[data-state="busy"]{opacity:.75;cursor:progress}',
    '.cpdm-btn[data-state="ok"]{background:#1e8e3e;border-color:#1e8e3e;color:#fff}',
    '.cpdm-btn[data-state="err"]{background:#d93025;border-color:#d93025;color:#fff}',
    '.cpdm-toast{position:fixed;right:20px;bottom:20px;z-index:2147483647;display:flex;flex-direction:column;gap:8px;',
    'max-width:420px;font:13px/1.4 Roboto,Arial,sans-serif}',
    '.cpdm-toast-item{padding:10px 14px;border-radius:8px;background:#1e8e3e;color:#fff;',
    'box-shadow:0 4px 16px rgba(0,0,0,.25)}',
    '.cpdm-toast-item.cpdm-error{background:#d93025}',
  ].join('');

  function initUi() {
    const style = document.createElement('style');
    style.textContent = CSS;
    (document.head || document.documentElement).appendChild(style);

    enhance(document);
    let timer = null;
    const schedule = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        enhance(document);
      }, 150);
    };
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
    // Classroom — SPA: наблюдатель ловит не всё, дешёвый опрос как страховка
    setInterval(schedule, 2000);
  }

  // ------------------------------------------------------------ публичный API

  globalThis.__cpdm = {
    pdfToMarkdown,
    convertAttachment,
    downloadPdf,
    driveIdFromUrl,
    saveMarkdown,
    safeFileName,
    // для отладки через dev.html
    buildLines,
    pageMetrics,
    pageToBlocks,
    blocksToMarkdown,
    bodyFontSize,
    version: '1.0.0',
  };

  if (IS_CLASSROOM || globalThis.__CPDM_FORCE_UI) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initUi, { once: true });
    } else {
      initUi();
    }
  }
})();
