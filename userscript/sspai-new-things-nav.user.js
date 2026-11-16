// ==UserScript==
// @name         少数派「编辑部的新玩意」上一篇 / 下一篇
// @namespace    local.sspai.new-things
// @version      1.3.4
// @description  在栏目文章页显示相邻文章导航，支持历史文章、目录缓存和站内路由切换。
// @match        https://sspai.com/*
// @run-at       document-start
// @grant        none
// @downloadURL  https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/sspai-new-things-nav.user.js
// @updateURL    https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/sspai-new-things-nav.user.js
// ==/UserScript==

(() => {
  'use strict';
  const TAG = '编辑部的新玩意';
  const TAG_URL = `/tag/${encodeURIComponent(TAG)}`;
  const CACHE_KEY = 'sspai-new-things-nav-v2';
  let cache = { items: [], total: null, complete: false };
  let route = '';
  let generation = 0;
  let host;
  const nativeFetch = window.fetch.bind(window);
  const isTagPage = () => {
    try { return decodeURIComponent(location.pathname).replace(/\/$/, '') === `/tag/${TAG}`; }
    catch (_) { return false; }
  };
  try {
    const saved = JSON.parse(localStorage.getItem(CACHE_KEY));
    if (saved && Array.isArray(saved.items) && saved.items.every(
      x => /^\d+$/.test(x.id) && typeof x.title === 'string')) cache = saved;
  } catch (_) { /* 存储不可用时保留内存缓存。 */ }
  function save() {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(cache)); }
    catch (_) { /* 忽略存储写入失败。 */ }
  }
  function normalize(data) {
    if (!Array.isArray(data)) throw new Error('目录数据格式异常');
    return data.map(x => {
      if (!/^\d+$/.test(String(x.id)) || typeof x.title !== 'string') throw new Error('文章数据格式异常');
      return { id: String(x.id), title: x.title };
    });
  }
  function updateFirst(items, total) {
    // 新首页与旧缓存末端有交集时，保留已知的历史目录。
    const overlap = items.length ? cache.items.findIndex(x => x.id === items.at(-1).id) : -1;
    const tail = overlap >= 0 ? cache.items.slice(overlap + 1) : [];
    const merged = [...items, ...tail];
    cache = { items: merged, total, complete: Number.isFinite(total) && merged.length >= total };
    save();
  }
  function observeResponse(input, result) {
    try {
      const url = new URL(input, location.origin);
      if (!isTagPage() || url.pathname !== '/api/v1/article/tag/page/get' ||
          url.searchParams.get('tag') !== TAG || Number(url.searchParams.get('offset') || 0) !== 0 ||
          result.error !== 0) return;
      updateFirst(normalize(result.data), Number.isFinite(result.total) ? result.total : null);
    } catch (_) { /* 页面请求不受缓存处理影响。 */ }
  }
  // 复用网站自身的请求响应，不为目录页额外发请求。
  window.fetch = async function (...args) {
    const response = await nativeFetch(...args);
    const input = typeof args[0] === 'string' ? args[0] : args[0]?.url || String(args[0]);
    if (isTagPage() && input.includes('/api/v1/article/tag/page/get')) {
      response.clone().json().then(data => observeResponse(input, data)).catch(() => {});
    }
    return response;
  };
  const xhrOpen = XMLHttpRequest.prototype.open;
  const xhrSend = XMLHttpRequest.prototype.send;
  const xhrUrls = new WeakMap();
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    xhrUrls.set(this, String(url));
    return xhrOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener('load', () => {
      try {
        if (this.status >= 200 && this.status < 300) {
          observeResponse(xhrUrls.get(this), this.responseType === 'json' ? this.response : JSON.parse(this.responseText));
        }
      } catch (_) { /* 非 JSON 响应不处理。 */ }
    }, { once: true });
    return xhrSend.apply(this, args);
  };
  // 首屏服务端渲染的数据也直接复用，作为请求监听的补充。
  function readTagDom() {
    if (!isTagPage()) return;
    const items = [];
    const seen = new Set();
    for (const a of document.querySelectorAll('a[href]')) {
      const match = a.getAttribute('href').match(/^\/post\/(\d+)$/);
      const title = a.textContent.trim();
      if (match && title && !seen.has(match[1])) {
        seen.add(match[1]); items.push({ id: match[1], title });
      }
    }
    if (items.length) {
      const total = document.body.innerText.match(/相关文章\s*(\d+)\s*篇/);
      updateFirst(items, total ? Number(total[1]) : null);
    }
  }
  async function requestPage(offset) {
    const url = new URL('/api/v1/article/tag/page/get', location.origin);
    url.search = new URLSearchParams({ tag: TAG, limit: '40', offset: String(offset) });
    const response = await nativeFetch(url, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error(`目录请求失败：HTTP ${response.status}`);
    const result = await response.json();
    if (result.error !== 0) throw new Error('栏目接口返回异常');
    return { items: normalize(result.data), total: Number.isFinite(result.total) ? result.total : null };
  }
  async function resolveNeighbor(id, direction) {
    let index = cache.items.findIndex(x => x.id === id);
    if (index >= 0 && cache.items[index + direction]) return cache.items[index + direction];
    if (index >= 0 && direction === 1 && cache.complete) return null;
    // 没有相邻文章时，从首页定位当前文章，逐页查询至找到目标或目录结束。
    // 重新定位可避免新一期发布后，沿用旧 offset 导致文章错位。
    const items = [];
    const seen = new Set();
    for (let pageNumber = 0; pageNumber < 100; pageNumber++) {
      const page = await requestPage(items.length);
      if (!page.items.length && (!items.length ||
          (Number.isFinite(page.total) && items.length < page.total))) {
        throw new Error('目录返回为空，未能完成查询');
      }
      for (const item of page.items) {
        if (seen.has(item.id)) throw new Error('目录在查询期间发生变化，请重试');
        seen.add(item.id);
      }
      items.push(...page.items);
      const complete = !page.items.length || (Number.isFinite(page.total) && items.length >= page.total);
      cache = { items: [...items], total: page.total, complete };
      save();
      index = items.findIndex(x => x.id === id);
      if (index >= 0 && items[index + direction]) return items[index + direction];
      if (index === 0 && direction === -1) return null;
      if (complete) {
        if (index < 0) throw new Error('未在该栏目中找到当前文章');
        return null;
      }
    }
    throw new Error('目录查询未完成，请重试');
  }

  function isColumnArticle(id) {
    if (cache.items.some(item => item.id === id)) return true;
    return [...document.querySelectorAll('a[href]')].some(a => {
      try { return decodeURIComponent(new URL(a.href).pathname).replace(/\/$/, '') === `/tag/${TAG}`; }
      catch (_) { return false; }
    });
  }

  function createPanel() {
    host?.remove();
    host = document.createElement('div');
    host.id = 'sspai-new-things-nav';
    const root = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = `
      :host { position:fixed; right:20px; bottom:24px; z-index:9999;
        font:14px/1.5 system-ui,sans-serif; color:#222; }
      nav { box-sizing:border-box; width:max-content; max-width:calc(100vw - 40px); padding:8px; border:1px solid #ddd;
        border-radius:8px; background:#fff; box-shadow:0 4px 22px #0002; }
      header { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:4px; }
      header a { color:#777; font-size:12px; }
      a { color:#bd392d; text-decoration:none; } a:hover { text-decoration:underline; }
      .content { display:grid; grid-template-columns:minmax(0,1fr); gap:6px; }
      .entry { display:block; min-width:0; padding:10px; border-radius:6px; background:#f6f6f6; }
      .entry span { display:block; max-width:160px; margin-top:4px; font-size:12px; color:#666; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .disabled { color:#999; }
      button { border:0; background:transparent; color:#777; cursor:pointer; font:inherit; padding:4px; }
      footer:empty { display:none; }
      footer { max-width:160px; grid-column:1 / -1; display:flex; align-items:center; justify-content:space-between; font-size:12px; color:#777; }
      nav.collapsed .content { display:none; }
      @media(max-width:600px) { :host { right:10px; bottom:12px; } }
    `;
    const nav = document.createElement('nav');
    nav.setAttribute('aria-label', `${TAG}文章导航`);
    const header = document.createElement('header');
    const label = document.createElement('a');
    label.href = TAG_URL;
    label.textContent = '新玩意';
    label.title = TAG;
    const toggle = document.createElement('button');
    toggle.textContent = '收起';
    toggle.setAttribute('aria-expanded', 'true');
    toggle.onclick = () => {
      const collapsed = nav.classList.toggle('collapsed');
      toggle.textContent = collapsed ? '展开' : '收起';
      toggle.setAttribute('aria-expanded', String(!collapsed));
    };
    header.append(label, toggle);
    const content = document.createElement('div');
    content.className = 'content';
    content.textContent = '正在加载栏目目录…';
    nav.append(header, content);
    root.append(style, nav);
    document.body.append(host);
    return content;
  }

  function render() {
    const token = ++generation;
    host?.remove();
    const match = location.pathname.match(/^\/post\/(\d+)\/?$/);
    if (!match) return;
    const id = match[1];
    const index = cache.items.findIndex(x => x.id === id);
    if (!isColumnArticle(id)) return;
    const content = createPanel();
    content.replaceChildren();
    let busy = false;
    const status = document.createElement('footer');
    status.textContent = '';
    for (const [label, direction] of [['← 上一篇', -1], ['下一篇 →', 1]]) {
      const item = index >= 0 ? cache.items[index + direction] : null;
      const el = document.createElement('a');
      el.className = 'entry';
      el.href = item ? `/post/${item.id}` : '#';
      el.textContent = label;
      const title = document.createElement('span');
      title.textContent = item ? item.title.split(/[｜|]/, 1)[0].trim() : '点击自动查找';
      el.append(title);
      el.addEventListener('click', async event => {
        if (item) return;
        event.preventDefault();
        if (busy) return;
        busy = true;
        status.textContent = '正在查找相邻文章…';
        try {
          const target = await resolveNeighbor(id, direction);
          if (token !== generation) return;
          if (target) location.assign(`/post/${target.id}`);
          else {
            title.textContent = direction === 1 ? '已经是最早一篇' : '已经是最新一篇';
            status.textContent = '';
          }
        } catch (error) {
          if (token === generation) status.textContent = `${error.message}，可再次点击重试`;
        } finally { busy = false; }
      });
      content.append(el);
    }
    content.append(status);
  }

  // 这里只检测站内路由变化，不定时发起网络请求。
  function checkRoute() {
    if (!document.body || route === location.pathname) return;
    route = location.pathname;
    if (isTagPage()) readTagDom();
    render();
  }
  function start() {
    readTagDom();
    checkRoute();
    setInterval(checkRoute, 800);
    // 站内切换后的文章标签可能稍晚才渲染完成。
    let scheduled = false;
    new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      setTimeout(() => {
        scheduled = false;
        if (!document.getElementById('sspai-new-things-nav') && /^\/post\/\d+/.test(location.pathname)) render();
      }, 300);
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
