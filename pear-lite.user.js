// ==UserScript==
// @name         Pear Lite — тема по обложке + тексты во вкладке «Текст» (YouTube Music)
// @namespace    https://github.com/pear-devs/pear-desktop
// @version      1.1.0
// @description  Порт album-color-theme и synced-lyrics из Pear Desktop для music.youtube.com (без блокировщика рекламы)
// @match        https://music.youtube.com/*
// @run-at       document-idle
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addStyle
// @grant        GM_registerMenuCommand
// @connect      lrclib.net
// @connect      genius.com
// @connect      googleusercontent.com
// @connect      ggpht.com
// @connect      ytimg.com
// @license      MIT
// ==/UserScript==

/*
 * Основано на плагинах album-color-theme и synced-lyrics из pear-devs/pear-desktop (MIT).
 * Тексты: сначала https://lrclib.net (синхронизированные), если там нет — https://genius.com.
 * Показываются во вкладке «ТЕКСТ» плеера (родной текст скрывается).
 *
 * Управление:
 *   Alt+L — открыть вкладку «Текст»
 *   Меню Tampermonkey — тема вкл/выкл, интенсивность, seekbar
 */

(function () {
  'use strict';

  /* ------------------------------------------------------------------ *
   *  Настройки
   * ------------------------------------------------------------------ */
  const DEFAULTS = {
    theme: true, // тема по обложке
    ratio: 0.5, // интенсивность 0..1
    seekbar: true, // цветной seekbar
    offset: 0, // сдвиг текста, мс (+ = текст раньше)
    fontSize: 20, // размер шрифта текста, px
  };
  const cfg = {};
  for (const k of Object.keys(DEFAULTS)) cfg[k] = GM_getValue(k, DEFAULTS[k]);
  const save = (k, v) => {
    cfg[k] = v;
    GM_setValue(k, v);
  };

  /* ------------------------------------------------------------------ *
   *  Утилиты
   * ------------------------------------------------------------------ */
  const gm = (opts) =>
    new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        timeout: 15000,
        ...opts,
        onload: resolve,
        onerror: () => reject(new Error('Ошибка сети')),
        ontimeout: () => reject(new Error('Таймаут запроса')),
      });
    });

  // Безопасное создание DOM (на странице включены Trusted Types — без innerHTML)
  const h = (tag, props = {}, ...children) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    for (const c of children) {
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  };

  const addStyle = (css) => {
    if (typeof GM_addStyle === 'function') return GM_addStyle(css);
    const s = document.createElement('style');
    s.textContent = css;
    document.head.append(s);
    return s;
  };

  const getVideo = () => document.querySelector('video');

  /* ------------------------------------------------------------------ *
   *  Текущий трек
   * ------------------------------------------------------------------ */
  function readTrack() {
    const md = navigator.mediaSession && navigator.mediaSession.metadata;
    if (md && md.title) {
      const art = md.artwork && md.artwork.length ? md.artwork[md.artwork.length - 1].src : '';
      return { title: md.title, artist: md.artist || '', album: md.album || '', art };
    }

    // Запасной вариант — из DOM плеера
    const bar = document.querySelector('ytmusic-player-bar');
    if (!bar) return null;
    const title = (bar.querySelector('.title') || {}).textContent;
    if (!title) return null;
    const byline = ((bar.querySelector('.byline') || {}).textContent || '').split('•').map((s) => s.trim());
    const img = bar.querySelector('img');
    return {
      title: title.trim(),
      artist: byline[0] || '',
      album: byline[1] || '',
      art: img ? img.src : '',
    };
  }

  /* ================================================================== *
   *  ТЕМА ПО ОБЛОЖКЕ
   * ================================================================== */
  const COLOR_KEY = '--ytmusic-album-color';
  const DARK_COLOR_KEY = '--ytmusic-album-color-dark';
  const RATIO_KEY = '--ytmusic-album-color-ratio';
  const root = document.documentElement;

  const THEME_CSS = `
yt-page-navigation-progress {
  --yt-page-navigation-container-color: #00000046 !important;
  --yt-page-navigation-progress-color: white !important;
}
#player-page {
  transition: transform 300ms, background-color 300ms cubic-bezier(0.2, 0, 0.6, 1) !important;
}
#nav-bar-background {
  transition: opacity 200ms, background-color 300ms cubic-bezier(0.2, 0, 0.6, 1) !important;
}
#mini-guide-background {
  transition: opacity 200ms, background-color 300ms cubic-bezier(0.2, 0, 0.6, 1) !important;
  border-right: 0px !important;
}
#guide-wrapper {
  transition: opacity 200ms, background-color 300ms cubic-bezier(0.2, 0, 0.6, 1) !important;
}
#items {
  border-radius: 10px !important;
}
ytmusic-app-layout > [slot='player-page']:not([is-mweb-modernization-enabled]):not(:has(ytmusic-player[player-ui-state='FULLSCREEN'])) {
  padding-top: 90px;
  margin-top: calc(-90px + var(--menu-bar-height, 0px)) !important;
}
.duration.ytmusic-player-queue-item,
.byline.ytmusic-player-queue-item {
  color: rgba(255, 255, 255, 0.5) !important;
  --yt-endpoint-color: rgba(255, 255, 255, 0.5) !important;
  --yt-endpoint-hover-color: rgba(255, 255, 255, 0.5) !important;
  --yt-endpoint-visited-color: rgba(255, 255, 255, 0.5) !important;
}
.icon.ytmusic-menu-navigation-item-renderer {
  color: rgba(255, 255, 255, 0.5) !important;
}
.menu.ytmusic-player-bar {
  --iron-icon-fill-color: rgba(255, 255, 255, 0.5) !important;
}
ytmusic-player-bar {
  color: rgba(255, 255, 255, 0.5) !important;
}
.time-info.ytmusic-player-bar {
  color: rgba(255, 255, 255, 0.5) !important;
}
.volume-slider.ytmusic-player-bar,
.expand-volume-slider.ytmusic-player-bar {
  --paper-slider-container-color: rgba(255, 255, 255, 0.5) !important;
}
ytmusic-fullbleed-thumbnail-renderer img {
  mask: linear-gradient(to bottom, #000 0%, #000 50%, transparent 100%);
}
.background-gradient.style-scope,
ytmusic-app-layout[is-bauhaus-sidenav-enabled] #mini-guide-background.ytmusic-app-layout {
  background: var(--ytmusic-background) !important;
}
ytmusic-browse-response[has-background]:not([disable-gradient]) .background-gradient.ytmusic-browse-response {
  background: unset !important;
}
#background.immersive-background.style-scope.ytmusic-browse-response {
  opacity: 0.6;
}
ytmusic-search-box[is-bauhaus-sidenav-enabled] {
  --ytmusic-search-background: var(--ytmusic-color-black3) !important;
}
.seekbar-theme #progress-bar.ytmusic-player-bar {
  --paper-slider-active-color: linear-gradient(
    to right,
    var(--paper-progress-active-color-1) 80%,
    var(--paper-progress-active-color-2) 100%
  ) !important;
  --paper-slider-knob-color: var(--paper-progress-active-color-1) !important;
  --paper-slider-knob-start-color: var(--paper-progress-active-color-2) !important;
}
`;

  const VARIABLE_MAP = {
    '--ytmusic-color-black1': '#212121',
    '--ytmusic-color-black2': '#181818',
    '--ytmusic-color-black3': '#030303',
    '--ytmusic-color-black4': '#030303',
    '--ytmusic-color-blackpure': '#000',
    '--dark-theme-background-color': '#212121',
    '--yt-spec-base-background': '#0f0f0f',
    '--yt-spec-raised-background': '#212121',
    '--yt-spec-menu-background': '#282828',
    '--yt-spec-static-brand-black': '#212121',
    '--yt-spec-static-overlay-background-solid': '#000',
    '--yt-spec-static-overlay-background-heavy': 'rgba(0,0,0,0.8)',
    '--yt-spec-static-overlay-background-medium': 'rgba(0,0,0,0.6)',
    '--yt-spec-static-overlay-background-medium-light': 'rgba(0,0,0,0.3)',
    '--yt-spec-static-overlay-background-light': 'rgba(0,0,0,0.1)',
    '--yt-spec-general-background-a': '#181818',
    '--yt-spec-general-background-b': '#0f0f0f',
    '--yt-spec-general-background-c': '#030303',
    '--yt-spec-snackbar-background': '#030303',
    '--yt-spec-filled-button-text': '#030303',
    '--yt-spec-black-1': '#282828',
    '--yt-spec-black-2': '#1f1f1f',
    '--yt-spec-black-3': '#161616',
    '--yt-spec-black-4': '#0d0d0d',
    '--yt-spec-black-pure': '#000',
    '--yt-spec-black-pure-alpha-5': 'rgba(0,0,0,0.05)',
    '--yt-spec-black-pure-alpha-10': 'rgba(0,0,0,0.1)',
    '--yt-spec-black-pure-alpha-15': 'rgba(0,0,0,0.15)',
    '--yt-spec-black-pure-alpha-30': 'rgba(0,0,0,0.3)',
    '--yt-spec-black-pure-alpha-60': 'rgba(0,0,0,0.6)',
    '--yt-spec-black-pure-alpha-80': 'rgba(0,0,0,0.8)',
    '--yt-spec-black-1-alpha-98': 'rgba(40,40,40,0.98)',
    '--yt-spec-black-1-alpha-95': 'rgba(40,40,40,0.95)',
    '--paper-toast-background-color': '#323232',
    '--ytmusic-search-background': '#030303',
    '--paper-slider-knob-color': '#f03',
    '--paper-dialog-background-color': '#212121',
    '--paper-progress-active-color-1': '#f03',
    '--paper-progress-active-color-2': '#ff2791',
    '--yt-spec-inverted-background': '#f3f3f3',
    'background': 'rgba(3, 3, 3)',
    '--ytmusic-background': 'rgba(3, 3, 3)',
  };
  const COLOR_KEY_MAP = {
    'background': DARK_COLOR_KEY,
    '--ytmusic-background': DARK_COLOR_KEY,
  };
  const RATIO_MAP = {
    '--paper-progress-active-color-1': 1.75,
    '--paper-progress-active-color-2': 1.75,
    '--yt-spec-inverted-background': 1.75,
  };

  // --- цветовая математика (замена библиотеки "color") ---
  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let hue = 0;
    let s = 0;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) hue = (g - b) / d + (g < b ? 6 : 0);
      else if (max === g) hue = (b - r) / d + 2;
      else hue = (r - g) / d + 4;
      hue /= 6;
    }
    return [hue, s, l];
  }

  function hslToRgb(hue, s, l) {
    if (s === 0) {
      const v = Math.round(l * 255);
      return [v, v, v];
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    const f = (t) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    return [f(hue + 1 / 3), f(hue), f(hue - 1 / 3)].map((x) => Math.round(x * 255));
  }

  const darken = (rgb, ratio) => {
    const [hue, s, l] = rgbToHsl(...rgb);
    return hslToRgb(hue, s, l * (1 - ratio));
  };

  const luminosity = ([r, g, b]) => {
    const f = (c) => {
      c /= 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };

  // --- средний цвет обложки ---
  async function averageColor(url) {
    const res = await gm({ method: 'GET', url, responseType: 'blob' });
    const bmp = await createImageBitmap(res.response);
    const size = 24;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0, size, size);
    const data = ctx.getImageData(0, 0, size, size).data;

    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 25) continue;
      r += data[i] * data[i];
      g += data[i + 1] * data[i + 1];
      b += data[i + 2] * data[i + 2];
      n++;
    }
    if (!n) return null;
    return [Math.round(Math.sqrt(r / n)), Math.round(Math.sqrt(g / n)), Math.round(Math.sqrt(b / n))];
  }

  // --- применение темы ---
  let themeStyleEl = null;

  function mixedColor(color, key, ratioMultiply) {
    const keyColor = `rgba(var(${key}), 1)`;
    let colorRatio = `var(${RATIO_KEY}, 50%)`;
    let originalRatio = `calc(100% - var(${RATIO_KEY}, 50%))`;
    if (ratioMultiply) {
      colorRatio = `calc(var(${RATIO_KEY}, 50%) * ${ratioMultiply})`;
      originalRatio = `calc(100% - calc(var(${RATIO_KEY}, 50%) * ${ratioMultiply}))`;
    }
    return `color-mix(in srgb, ${color} ${originalRatio}, ${keyColor} ${colorRatio})`;
  }

  function applyRatio() {
    root.style.setProperty(RATIO_KEY, `${Math.round(cfg.ratio * 100)}%`);
  }

  function applySeekbar() {
    document.body.classList.toggle('seekbar-theme', cfg.theme && cfg.seekbar);
  }

  function enableTheme() {
    if (!themeStyleEl) themeStyleEl = addStyle(THEME_CSS);
    for (const [variable, color] of Object.entries(VARIABLE_MAP)) {
      const key = COLOR_KEY_MAP[variable] || COLOR_KEY;
      root.style.setProperty(variable, mixedColor(color, key, RATIO_MAP[variable]), 'important');
    }
    applyRatio();
    applySeekbar();
    if (!root.style.getPropertyValue(COLOR_KEY)) {
      root.style.setProperty(COLOR_KEY, '0, 0, 0');
      root.style.setProperty(DARK_COLOR_KEY, '0, 0, 0');
    }
    if (lastTrack) updateThemeColor(lastTrack, true);
  }

  function disableTheme() {
    if (themeStyleEl) {
      themeStyleEl.remove();
      themeStyleEl = null;
    }
    for (const variable of Object.keys(VARIABLE_MAP)) root.style.removeProperty(variable);
    root.style.removeProperty(COLOR_KEY);
    root.style.removeProperty(DARK_COLOR_KEY);
    root.style.removeProperty(RATIO_KEY);
    applySeekbar();
  }

  let themeToken = 0;
  async function updateThemeColor(track, force) {
    if (!cfg.theme) return;
    const token = ++themeToken;
    let rgb = null;
    if (track.art) {
      try {
        rgb = await averageColor(track.art);
      } catch (e) {
        console.warn('[Pear Lite] не удалось получить цвет обложки:', e);
      }
    }
    if (token !== themeToken || !cfg.theme) return;

    if (!rgb) {
      root.style.setProperty(COLOR_KEY, '0, 0, 0');
      root.style.setProperty(DARK_COLOR_KEY, '0, 0, 0');
      return;
    }

    let dark = darken(rgb, 0.3);
    let color = darken(rgb, 0.15);
    for (let i = 0; i < 100 && luminosity(color) > 0.5; i++) {
      color = darken(color, 0.05);
      dark = darken(dark, 0.05);
    }
    root.style.setProperty(COLOR_KEY, color.join(', '));
    root.style.setProperty(DARK_COLOR_KEY, dark.join(', '));
  }

  /* ================================================================== *
   *  ТЕКСТЫ ПЕСЕН: LRCLib → Genius
   * ================================================================== */

  // --- LRC-парсер (упрощённо по parsers/lrc.ts) ---
  function parseLRC(text) {
    const lines = [];
    let offset = 0;
    const stampRe = /\[(\d+):(\d+)(?:[.:](\d+))?\]/g;

    for (const raw of text.split('\n')) {
      const line = raw.trim();
      if (!line.startsWith('[')) continue;

      const stamps = [];
      let m;
      stampRe.lastIndex = 0;
      while ((m = stampRe.exec(line)) !== null) {
        if (m.index !== 0 && stamps.length === 0) break;
        const ms = (m[3] || '0').padEnd(3, '0').slice(0, 3);
        stamps.push(parseInt(m[1], 10) * 60000 + parseInt(m[2], 10) * 1000 + parseInt(ms, 10));
      }

      if (!stamps.length) {
        const tag = line.match(/^\[offset:\s*(-?\d+)\s*\]$/i);
        if (tag) offset = parseInt(tag[1], 10);
        continue;
      }

      const body = line
        .replace(/\[\d+:\d+(?:[.:]\d+)?\]/g, '')
        .replace(/<\d+:\d+(?:[.:]\d+)?>/g, '')
        .trim();
      for (const t of stamps) lines.push({ t, text: body });
    }

    lines.sort((a, b) => a.t - b.t);
    if (offset) for (const l of lines) l.t += offset;
    return lines;
  }

  // --- сопоставление исполнителей и названий ---
  const norm = (s) =>
    (s || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^\p{L}\p{N}\s]/gu, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  const splitArtists = (s) =>
    (s || '')
      .split(/[&,]|\bfeat\.?\b|\bft\.?\b/i)
      .map(norm)
      .filter(Boolean);
  const artistMatch = (a, b) => {
    const A = splitArtists(a);
    const B = splitArtists(b);
    return A.some((x) => B.some((y) => x === y || x.includes(y) || y.includes(x)));
  };
  // "Song (feat. X) - Remastered 2011" -> "song"
  const coreTitle = (s) => norm((s || '').replace(/\(.*?\)|\[.*?\]|\s[-–—]\s.*$/g, ''));
  const titleMatch = (a, b) => {
    const x = coreTitle(a);
    const y = coreTitle(b);
    return !!x && !!y && (x === y || x.includes(y) || y.includes(x));
  };

  // ------------------------------ LRCLib ------------------------------
  async function lrclibJSON(path, params) {
    const url = `https://lrclib.net/api/${path}?${new URLSearchParams(params)}`;
    const res = await gm({ method: 'GET', url, headers: { Accept: 'application/json' } });
    if (res.status === 404) return null;
    if (res.status < 200 || res.status >= 300) throw new Error(`LRCLib: HTTP ${res.status}`);
    return JSON.parse(res.responseText);
  }

  const lrclibToResult = (item) => {
    if (!item || item.instrumental) return null;
    const synced = item.syncedLyrics ? parseLRC(item.syncedLyrics) : null;
    const plain = item.plainLyrics || null;
    if ((!synced || !synced.length) && !plain) return null;
    return { source: 'LRCLib', synced: synced && synced.length ? synced : null, plain };
  };

  function lrclibPickBest(list, track, duration) {
    if (!Array.isArray(list)) return null;
    const ok = list
      .filter((it) => artistMatch(track.artist, it.artistName))
      .filter((it) => !duration || Math.abs(it.duration - duration) <= 15)
      .filter((it) => it.syncedLyrics || it.plainLyrics);
    ok.sort((a, b) => {
      const da = duration ? Math.abs(a.duration - duration) : 0;
      const db = duration ? Math.abs(b.duration - duration) : 0;
      if (da !== db) return da - db;
      return (b.syncedLyrics ? 1 : 0) - (a.syncedLyrics ? 1 : 0);
    });
    return ok[0] || null;
  }

  async function fetchFromLRCLib(track, duration) {
    const dur = duration ? Math.round(duration) : 0;

    // 1) точное совпадение
    try {
      const params = { track_name: track.title, artist_name: track.artist };
      if (track.album) params.album_name = track.album;
      if (dur) params.duration = String(dur);
      const r = lrclibToResult(await lrclibJSON('get', params));
      if (r) return r;
    } catch (_) {
      /* переходим к поиску */
    }

    // 2) поиск по названию и исполнителю
    let list = await lrclibJSON('search', { track_name: track.title, artist_name: track.artist });
    let best = lrclibPickBest(list, track, dur);
    if (best) return lrclibToResult(best);

    // 3) свободный поиск
    list = await lrclibJSON('search', { q: `${track.title} ${track.artist}`.trim() });
    best = lrclibPickBest(list, track, dur);
    return best ? lrclibToResult(best) : null;
  }

  // ------------------------------ Genius ------------------------------
  const decodeEntities = (s) =>
    s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (m, e) => {
      e = e.toLowerCase();
      if (e[0] === '#') {
        const code = e[1] === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return Number.isFinite(code) ? String.fromCodePoint(code) : m;
      }
      return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }[e] || m;
    });

  // Достаёт текст из HTML страницы Genius без DOMParser
  // (на странице включены Trusted Types, parseFromString со строкой может быть запрещён).
  function extractGeniusLyrics(html) {
    const parts = [];
    const startRe = /<div[^>]*data-lyrics-container="true"[^>]*>/g;
    let m;
    while ((m = startRe.exec(html)) !== null) {
      const tagRe = /<(\/?)(div|br)\b([^>]*)>/gi;
      tagRe.lastIndex = m.index + m[0].length;
      let last = tagRe.lastIndex;
      let depth = 1;
      let skipDepth = 0;
      let buf = '';
      let t;
      while (depth > 0 && (t = tagRe.exec(html)) !== null) {
        if (!skipDepth) buf += html.slice(last, t.index);
        last = tagRe.lastIndex;

        const closing = t[1] === '/';
        const name = t[2].toLowerCase();
        if (name === 'br') {
          if (!skipDepth) buf += '\n';
          continue;
        }
        if (closing) {
          if (skipDepth && depth === skipDepth) skipDepth = 0;
          depth--;
        } else {
          depth++;
          if (!skipDepth && /data-exclude-from-selection\s*=\s*"true"/.test(t[3])) skipDepth = depth;
        }
      }
      parts.push(buf);
      startRe.lastIndex = Math.max(startRe.lastIndex, last);
    }

    if (!parts.length) return null;
    const text = decodeEntities(parts.join('\n').replace(/<[^>]+>/g, ''))
      .replace(/\r/g, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    return text || null;
  }

  async function fetchFromGenius(track) {
    const q = new URLSearchParams({ q: `${track.artist} ${track.title}`.trim(), page: '1', per_page: '10' });
    const res = await gm({
      method: 'GET',
      url: `https://genius.com/api/search/song?${q}`,
      headers: { Accept: 'application/json' },
    });
    if (res.status < 200 || res.status >= 300) throw new Error(`Genius: HTTP ${res.status}`);

    const data = JSON.parse(res.responseText);
    const hits = ((data.response && data.response.sections) || [])
      .flatMap((s) => s.hits || [])
      .filter((x) => x && x.result);

    const scored = hits
      .map((x) => x.result)
      .filter((r) => r.primary_artist && !/Deleted-artist/i.test(r.primary_artist.url || ''))
      .filter((r) => artistMatch(track.artist, `${r.artist_names || ''} ${r.primary_artist.name || ''}`))
      .filter((r) => titleMatch(track.title, r.title))
      .sort((a, b) => {
        const ea = coreTitle(a.title) === coreTitle(track.title) ? 1 : 0;
        const eb = coreTitle(b.title) === coreTitle(track.title) ? 1 : 0;
        return eb - ea;
      });

    const best = scored[0];
    if (!best) return null;

    const page = await gm({ method: 'GET', url: `https://genius.com${best.path}` });
    if (page.status < 200 || page.status >= 300) throw new Error(`Genius: HTTP ${page.status}`);

    const lyrics = extractGeniusLyrics(page.responseText);
    if (!lyrics) return null;
    if (lyrics.toLowerCase().replace(/[[\]\s]/g, '') === 'instrumental') return null;

    return { source: 'Genius', synced: null, plain: lyrics };
  }

  // ------------------------------ общий поиск ------------------------------
  async function findLyrics(track, duration, progress) {
    try {
      const r = await fetchFromLRCLib(track, duration);
      if (r) return r;
    } catch (e) {
      console.warn('[Pear Lite] LRCLib:', e);
    }
    progress('Не найдено на LRCLib — ищу на Genius…');
    return fetchFromGenius(track);
  }

  /* ================================================================== *
   *  UI: вкладка «ТЕКСТ»
   * ================================================================== */
  const HEAD_SELECTOR = '#tabsContent > .tab-header:nth-of-type(2)';
  const TAB_RENDERER_SELECTOR = '#tab-renderer[page-type="MUSIC_PAGE_TYPE_TRACK_LYRICS"]';

  const LYRICS_CSS = `
/* прячем родной текст YouTube Music, показываем свой */
#tab-renderer[page-type='MUSIC_PAGE_TYPE_TRACK_LYRICS'] > * {
  display: none !important;
}
#tab-renderer[page-type='MUSIC_PAGE_TYPE_TRACK_LYRICS'] > #pl-container {
  display: flex !important;
  height: 100%;
}
#tab-renderer[page-type='MUSIC_PAGE_TYPE_TRACK_LYRICS'] {
  scrollbar-width: none;
}
#pl-container {
  flex-direction: column; box-sizing: border-box; width: 100%;
  color: #fff; font-family: Roboto, Arial, sans-serif;
}
#pl-bar { display: flex; align-items: center; gap: 6px; padding: 6px 4px 10px; flex: none; }
#pl-title { flex: 1; min-width: 0; font-size: 12px; opacity: .65; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#pl-bar button {
  background: rgba(255,255,255,.1); color: #fff; border: 0; border-radius: 6px;
  min-width: 28px; height: 26px; padding: 0 6px; font-size: 12px; cursor: pointer;
}
#pl-bar button:hover { background: rgba(255,255,255,.22); }
#pl-offset-group { display: flex; align-items: center; gap: 6px; }
#pl-offset { font-size: 11px; opacity: .7; min-width: 44px; text-align: center; }
#pl-body {
  position: relative; flex: 1; min-height: 0; max-height: calc(100vh - 230px);
  overflow-y: auto; padding: 30% 8px; scroll-behavior: smooth; scrollbar-width: none;
}
#pl-body::-webkit-scrollbar { display: none; }
#pl-body.plain { padding: 8px; scroll-behavior: auto; }
.pl-line { font-weight: 700; line-height: 1.35; margin: 14px 0; opacity: .38; cursor: pointer; transition: opacity .25s, transform .25s; transform-origin: left center; }
.pl-line:hover { opacity: .7; }
.pl-line.current { opacity: 1; transform: scale(1.04); }
.pl-line.past { opacity: .5; }
.pl-plain { line-height: 1.55; min-height: 1.55em; opacity: .92; white-space: pre-wrap; }
.pl-sec { opacity: .55; font-size: .8em; font-weight: 700; margin-top: 1.1em; }
.pl-state { padding: 30px 10px; text-align: center; opacity: .6; font-size: 14px; }
`;

  let containerEl, bodyEl, titleEl, offsetEl, offsetGroupEl;
  let curLines = null; // [{t, text}] — синхронизированный текст
  let lineEls = [];
  let curIdx = -1;
  let tabVisible = false;

  function buildUI() {
    addStyle(LYRICS_CSS);

    const mk = (label, title, fn) => h('button', { title, onclick: fn }, label);
    titleEl = h('div', { id: 'pl-title' }, 'Тексты');
    offsetEl = h('div', { id: 'pl-offset' });
    offsetGroupEl = h(
      'div',
      { id: 'pl-offset-group' },
      mk('−', 'Текст позже на 0.5 с', () => setOffset(cfg.offset - 500)),
      offsetEl,
      mk('+', 'Текст раньше на 0.5 с', () => setOffset(cfg.offset + 500)),
    );

    const bar = h(
      'div',
      { id: 'pl-bar' },
      titleEl,
      mk('A−', 'Меньше шрифт', () => setFont(cfg.fontSize - 2)),
      mk('A+', 'Больше шрифт', () => setFont(cfg.fontSize + 2)),
      offsetGroupEl,
    );
    bodyEl = h('div', { id: 'pl-body' });
    containerEl = h('div', { id: 'pl-container' }, bar, bodyEl);

    setFont(cfg.fontSize);
    setOffset(cfg.offset);
  }

  function setFont(px) {
    px = Math.max(12, Math.min(40, px));
    save('fontSize', px);
    bodyEl.style.fontSize = `${px}px`;
  }

  function setOffset(ms) {
    save('offset', ms);
    offsetEl.textContent = `${ms >= 0 ? '+' : ''}${(ms / 1000).toFixed(1)} c`;
  }

  function resetView() {
    curLines = null;
    lineEls = [];
    curIdx = -1;
  }

  function showState(text) {
    resetView();
    offsetGroupEl.style.display = 'none';
    bodyEl.classList.remove('plain');
    bodyEl.replaceChildren(h('div', { class: 'pl-state' }, text));
  }

  function showResult(result) {
    if (!result) return showState('Текст не найден 😔');
    resetView();
    titleEl.textContent = `${titleEl.dataset.song || ''} · ${result.source}`.replace(/^ · /, '');

    if (result.synced) {
      curLines = result.synced;
      offsetGroupEl.style.display = 'flex';
      bodyEl.classList.remove('plain');
      lineEls = curLines.map((l) =>
        h(
          'div',
          {
            class: 'pl-line',
            onclick: () => {
              const v = getVideo();
              if (v) v.currentTime = Math.max(0, (l.t - cfg.offset) / 1000);
            },
          },
          l.text || '♪',
        ),
      );
      bodyEl.replaceChildren(...lineEls);
      bodyEl.scrollTop = 0;
      syncLyrics(true);
    } else {
      offsetGroupEl.style.display = 'none';
      bodyEl.classList.add('plain');
      const frag = document.createDocumentFragment();
      for (const line of result.plain.split('\n')) {
        const isSection = /^\s*\[.*\]\s*$/.test(line);
        frag.append(h('div', { class: isSection ? 'pl-plain pl-sec' : 'pl-plain' }, line || '\u00a0'));
      }
      bodyEl.replaceChildren(frag);
      bodyEl.scrollTop = 0;
    }
  }

  function scrollToCurrent(instant) {
    if (curIdx < 0 || !lineEls[curIdx]) return;
    const el = lineEls[curIdx];
    const top = el.offsetTop - bodyEl.clientHeight / 2 + el.offsetHeight / 2;
    bodyEl.scrollTo({ top, behavior: instant ? 'instant' : 'smooth' });
  }

  function syncLyrics(forceScroll) {
    if (!curLines || !tabVisible || !containerEl.isConnected) return;
    const v = getVideo();
    if (!v) return;
    const t = v.currentTime * 1000 + cfg.offset;

    // бинарный поиск последней строки с t_line <= t
    let lo = 0, hi = curLines.length - 1, idx = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (curLines[mid].t <= t) {
        idx = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }

    if (idx === curIdx && !forceScroll) return;
    curIdx = idx;
    for (let i = 0; i < lineEls.length; i++) {
      lineEls[i].classList.toggle('current', i === idx);
      lineEls[i].classList.toggle('past', i < idx);
    }
    scrollToCurrent(forceScroll);
  }

  // --- загрузка текста для трека ---
  let lyricsToken = 0;
  let lyricsLoadedFor = null;

  async function loadLyricsFor(track) {
    const token = ++lyricsToken;
    lyricsLoadedFor = trackKey(track);
    titleEl.dataset.song = `${track.artist} — ${track.title}`;
    titleEl.textContent = titleEl.dataset.song;
    showState('Загрузка…');

    // небольшая задержка: дать <video> обновить длительность нового трека
    await new Promise((r) => setTimeout(r, 700));
    if (token !== lyricsToken) return;

    const v = getVideo();
    const duration = v && isFinite(v.duration) ? v.duration : 0;

    try {
      const result = await findLyrics(track, duration, (msg) => {
        if (token === lyricsToken) showState(msg);
      });
      if (token !== lyricsToken) return;
      showResult(result);
    } catch (e) {
      if (token !== lyricsToken) return;
      console.warn('[Pear Lite] ошибка получения текста:', e);
      showState(`Ошибка: ${e.message}`);
    }
  }

  // --- интеграция с вкладкой ---
  let observedHeader = null;
  const tabObserver = new MutationObserver(() => ensureTab());

  function onTabShown() {
    const t = readTrack();
    if (t && lyricsLoadedFor !== trackKey(t)) loadLyricsFor(t);
    else scrollToCurrent(true);
  }

  function ensureTab() {
    const header = document.querySelector(HEAD_SELECTOR);
    if (!header) {
      tabVisible = false;
      return;
    }

    // YouTube Music отключает вкладку, если у трека нет своего текста — включаем всегда
    if (header.hasAttribute('disabled')) header.removeAttribute('disabled');

    if (observedHeader !== header) {
      tabObserver.disconnect();
      tabObserver.observe(header, { attributes: true, attributeFilter: ['disabled', 'aria-selected'] });
      observedHeader = header;
    }

    const selected = header.getAttribute('aria-selected') === 'true';
    if (selected) {
      const renderer = document.querySelector(TAB_RENDERER_SELECTOR);
      if (renderer && containerEl.parentNode !== renderer) renderer.append(containerEl);
    }

    if (selected && !tabVisible) {
      tabVisible = true;
      onTabShown();
    } else if (!selected) {
      tabVisible = false;
    }
  }

  function openLyricsTab() {
    const layout = document.querySelector('ytmusic-app-layout');
    const playerOpen = !!layout && (layout.hasAttribute('player-page-open_') || layout.hasAttribute('player-page-open'));
    if (!playerOpen) {
      const expand = document.querySelector('ytmusic-player-bar .toggle-player-page-button');
      if (expand) expand.click();
    }
    setTimeout(
      () => {
        const header = document.querySelector(HEAD_SELECTOR);
        if (header) {
          header.removeAttribute('disabled');
          header.click();
        }
      },
      playerOpen ? 0 : 500,
    );
  }

  /* ================================================================== *
   *  Основной цикл
   * ================================================================== */
  const trackKey = (t) => `${t.title}|${t.artist}|${t.art}`;
  let lastTrack = null;
  let lastKey = '';

  function tick() {
    ensureTab();

    const t = readTrack();
    if (!t) return;
    const key = trackKey(t);
    if (key === lastKey) return;
    lastKey = key;
    lastTrack = t;

    updateThemeColor(t);

    if (tabVisible) loadLyricsFor(t);
    else {
      lyricsLoadedFor = null; // загрузим, когда откроют вкладку
      lyricsToken++;
    }
  }

  function init() {
    buildUI();

    if (cfg.theme) enableTheme();

    setInterval(tick, 500);
    setInterval(() => syncLyrics(false), 100);
    tick();

    document.addEventListener('keydown', (e) => {
      if (!e.altKey || e.ctrlKey || e.metaKey || e.code !== 'KeyL') return;
      const el = document.activeElement;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return;
      e.preventDefault();
      openLyricsTab();
    });

    GM_registerMenuCommand('Тема по обложке: вкл/выкл', () => {
      save('theme', !cfg.theme);
      if (cfg.theme) enableTheme();
      else disableTheme();
    });
    GM_registerMenuCommand('Интенсивность темы (0–100)…', () => {
      const v = prompt('Интенсивность цвета обложки, 0–100:', String(Math.round(cfg.ratio * 100)));
      if (v === null) return;
      const n = Number(v);
      if (!isFinite(n)) return;
      save('ratio', Math.max(0, Math.min(100, n)) / 100);
      if (cfg.theme) applyRatio();
    });
    GM_registerMenuCommand('Цветной seekbar: вкл/выкл', () => {
      save('seekbar', !cfg.seekbar);
      applySeekbar();
    });
    GM_registerMenuCommand('Открыть вкладку «Текст» (Alt+L)', openLyricsTab);
  }

  if (document.body) init();
  else window.addEventListener('DOMContentLoaded', init, { once: true });
})();
