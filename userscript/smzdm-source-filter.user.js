// ==UserScript==
// @name         什么值得买｜屏蔽全网作者聚合文章
// @namespace    local.smzdm.source-filter
// @version      1.0.0
// @description  在搜索结果的卡片视图和列表视图中隐藏标注「源自 N 位全网作者」的文章。
// @match        https://search.smzdm.com/*
// @run-at       document-end
// @grant        GM_addStyle
// @noframes
// @downloadURL  https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/smzdm-source-filter.user.js
// @updateURL    https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/smzdm-source-filter.user.js
// ==/UserScript==

(() => {
    'use strict';

    const itemSelector = '.feed-masonry__item, .feed-horizontal-list__item';
    const sourceSelector = '.feed-article-card__source, .feed-horizontal-article-card__name';
    const hiddenAttribute = 'data-smzdm-source-filter-hidden';
    const aggregateSource = /^\s*源自\s*[0-9０-９]+\s*位全网作者\s*$/;

    GM_addStyle(`
        .feed-masonry__item[${hiddenAttribute}],
        .feed-horizontal-list__item[${hiddenAttribute}] {
            display: none !important;
        }
    `);

    function filterResults() {
        for (const item of document.querySelectorAll(itemSelector)) {
            const source = item.querySelector(sourceSelector);
            const isAggregate = aggregateSource.test(source?.textContent ?? '');
            item.toggleAttribute(hiddenAttribute, isAggregate);
        }
    }

    // 只隐藏结果条目，保留站点管理的 DOM、加载区和滚动监听。
    let framePending = false;
    const observer = new MutationObserver(() => {
        if (framePending) return;

        framePending = true;
        requestAnimationFrame(() => {
            framePending = false;
            filterResults();
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
    });
    filterResults();
})();
