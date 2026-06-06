// ==UserScript==
// @name         京东订单导出
// @namespace    http://tampermonkey.net/
// @version      0.1.0
// @description  导出京东订单列表，按当前年份和筛选条件自动翻页抓取
// @author       sowevo
// @license      Custom License
// @match        https://order.jd.com/center/list.action*
// @grant        GM_addStyle
// @downloadURL  https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/JDOrderExport.user.js
// @updateURL    https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/JDOrderExport.user.js
// ==/UserScript==

(function() {
    'use strict';

    const CONFIG = {
        PANEL_ID: 'jd-order-export-panel',
        REQUEST_DELAY: 500,
        CSV_BOM: '\ufeff'
    };

    const logger = {
        info: (msg) => console.info(`[京东订单导出] ${msg}`),
        error: (msg, error) => console.error(`[京东订单导出] ${msg}`, error)
    };

    function text(el) {
        return (el?.textContent || '').replace(/\s+/g, ' ').trim();
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function absUrl(href, base = location.href) {
        if (!href) return '';
        return new URL(href, base).toString();
    }

    function getCurrentFilterUrl(yearValue = '') {
        const url = new URL(location.href);
        url.searchParams.delete('page');

        if (yearValue) {
            url.searchParams.set('d', yearValue);
        }

        return url.toString();
    }

    function normalizeUrl(url) {
        const normalized = new URL(url, location.href);
        normalized.hash = '';
        return normalized.toString();
    }

    function getNextUrl(doc, baseUrl) {
        const next = doc.querySelector('.pagin a.next');
        return next ? absUrl(next.getAttribute('href'), baseUrl) : '';
    }

    async function fetchDoc(url) {
        const response = await fetch(url, {
            credentials: 'include',
            cache: 'no-store'
        });

        if (!response.ok) {
            throw new Error(`请求失败：${response.status} ${url}`);
        }

        const html = await response.text();
        return new DOMParser().parseFromString(html, 'text/html');
    }

    function parseOrderHeader(tbody) {
        const header = tbody.querySelector('.tr-th, .tr-th-02');
        const headerText = text(header);
        const time = headerText.match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)?.[0] || '';
        const orderId = tbody.id.replace(/^tb-/, '');
        const shopLink = header?.querySelector('.order-shop .shop-txt, .shop-txt, .order-shop a[href*="mall.jd.com"]');
        const shop = text(shopLink) || text(header?.querySelector('.order-shop')) || headerText
            .replace(time, '')
            .replace(/订单号：\s*\d+/, '')
            .trim();

        return { time, orderId, shop };
    }

    function parseProducts(tbody) {
        return [...tbody.querySelectorAll('.tr-bd')]
            .filter(row => !row.classList.contains('sep-tr-bd'))
            .map(row => {
                const firstCell = row.children[0];
                const name = text(firstCell?.querySelector('.p-name')) || text(firstCell);
                const quantity = text(firstCell?.querySelector('.goods-number'));
                const skuMatch = firstCell?.querySelector('.goods-item')?.className.match(/\bp-(\d+)/);

                return {
                    name,
                    quantity,
                    skuId: skuMatch?.[1] || ''
                };
            })
            .filter(item => item.name);
    }

    function getOrderConfigValue(doc, key) {
        const pattern = new RegExp(`\\$ORDER_CONFIG\\['${key}'\\]='([^']*)';`);

        for (const script of doc.scripts) {
            const match = script.textContent.match(pattern);
            if (match) return match[1];
        }

        return '';
    }

    function getHiddenVenderOrderIds(doc) {
        return new Set(
            getOrderConfigValue(doc, 'hideVender')
                .split(',')
                .map(item => item.trim())
                .filter(Boolean)
        );
    }

    function getOrderSiteIdMap(doc) {
        const orderIds = getOrderConfigValue(doc, 'orderIds').split(',');
        const siteIds = getOrderConfigValue(doc, 'orderSiteIds').split(',');
        const siteIdMap = new Map();

        orderIds.forEach((orderId, index) => {
            if (!orderId) return;

            const siteId = siteIds[index] || '';
            const existingSiteId = siteIdMap.get(orderId);

            if (!existingSiteId || siteId === '597') {
                siteIdMap.set(orderId, siteId);
            }
        });

        return siteIdMap;
    }

    function getShopId(doc, orderId) {
        const pair = getOrderConfigValue(doc, 'allShopIds')
            .split(',')
            .find(item => item.endsWith(`-${orderId}`));

        return pair ? pair.split('-')[0] : '';
    }

    function getJdGoHomeSiteIds(doc) {
        return new Set(
            getOrderConfigValue(doc, 'jdGoHomeSiteIds')
                .split(',')
                .map(item => item.trim())
                .filter(Boolean)
        );
    }

    function getVenderId(tbody) {
        const shopLink = tbody.querySelector('.shop-txt, .order-shop a');
        const className = shopLink?.className || '';

        return className.match(/\bvenderName(\d+)/)?.[1] || '';
    }

    function getOrderCategory(siteId) {
        if (siteId === '597') return '京东外卖';
        if (siteId === '18') return '京东大药房';
        return '';
    }

    function inferOrderCategory(siteId, shop, shopId, isJdGoHome) {
        const category = getOrderCategory(siteId);

        if (category) return category;
        if (isJdGoHome) return '京东外卖';
        if (shop === '京东' || shopId === '0') return '京东自营';
        if (shopId) return '第三方店铺';

            return '普通订单';
    }

    async function fetchVenderInfo(functionId, body) {
        const url = new URL('https://api.m.jd.com/api');
        const uuid = document.cookie.match(/__jdu=([^;]+)/)?.[1] || '';

        url.searchParams.set('functionId', functionId);
        url.searchParams.set('appid', 'order-jd-com');
        url.searchParams.set('client', 'pc');
        url.searchParams.set('clientVersion', '1.0.0');
        url.searchParams.set('uuid', uuid);
        url.searchParams.set('loginType', '3');
        url.searchParams.set('t', String(Date.now()));
        url.searchParams.set('body', JSON.stringify(body));

        try {
            const response = await fetch(url.toString(), {
                credentials: 'include',
                cache: 'no-store'
            });

            if (!response.ok) return new Map();

            const data = await response.json();
            return new Map(
                Object.entries(data)
                    .map(([id, value]) => [id, value?.venderName || ''])
                    .filter(([, venderName]) => venderName)
            );
        } catch (error) {
            logger.error(`获取店铺信息失败：${functionId}`, error);
            return new Map();
        }
    }

    async function fetchPageVenderInfo(doc) {
        const jdGoHomeVenderIds = getOrderConfigValue(doc, 'jdGoHomeSiteIds')
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);
        const popVenderIds = getOrderConfigValue(doc, 'popVenderIds')
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);
        const merged = new Map();

        if (jdGoHomeVenderIds.length > 0) {
            const jdGoHomeInfo = await fetchVenderInfo('pcorder_getJdGoHomeTelInfo', {
                jdGoHomeVenderIds: jdGoHomeVenderIds.join(',')
            });

            jdGoHomeInfo.forEach((value, key) => merged.set(key, value));
        }

        if (popVenderIds.length > 0) {
            const popInfo = await fetchVenderInfo('pcorder_getPopTelInfo', {
                popVenderIds: popVenderIds.join(','),
                czOrderShopIds: getOrderConfigValue(doc, 'czOrderShopIds')
            });

            popInfo.forEach((value, key) => merged.set(key, value));
        }

        return merged;
    }

    function getDynamicOrderQueries(doc) {
        const raw = getOrderConfigValue(doc, 'pop_gw_new');
        if (!raw) return [];

        try {
            return JSON.parse(raw).flatMap(group => (
                group.orderIds || []
            ).map(orderId => ({
                orderType: group.orderType,
                erpOrderId: String(orderId)
            })));
        } catch (error) {
            logger.error('解析动态订单配置失败', error);
            return [];
        }
    }

    async function fetchDynamicOrderInfo(doc) {
        const queryList = getDynamicOrderQueries(doc);
        if (queryList.length === 0) return new Map();

        return new Promise(resolve => {
            jQuery.ajax({
                type: 'GET',
                url: 'https://ordergw.jd.com/orderCenter/app/1.0/',
                data: {
                    queryList: JSON.stringify(queryList)
                },
                dataType: 'jsonp',
                timeout: 8000,
                success(result) {
                    const orders = result?.orderInfoMainList || result?.appOrderInfoList || [];
                    resolve(new Map(
                        orders.map(order => [String(order.orderInfo?.erpOrderId || ''), order])
                            .filter(([orderId]) => orderId)
                    ));
                },
                error(_xhr, _status, error) {
                    logger.error('获取动态订单信息失败', error);
                    resolve(new Map());
                }
            });
        });
    }

    function applyDynamicOrderInfo(order, dynamicInfo) {
        if (!dynamicInfo) return order;

        const productList = dynamicInfo.productList || [];
        const payInfoList = dynamicInfo.payInfoList || [];
        const status = dynamicInfo.orderStatus?.statusList?.[0]?.name || '';
        const detailUrl = dynamicInfo.orderStatus?.operationList
            ?.find(item => item.name === '订单详情')?.url || '';
        const totalAmount = payInfoList.reduce((sum, item) => sum + Number(item.payAmount || 0), 0);
        const payment = payInfoList.length > 1
            ? '混合支付'
            : payInfoList[0]?.name || order.payment;

        return {
            ...order,
            category: dynamicInfo.orderInfo?.orderType === 108 ? '京东服务' : order.category,
            products: productList.length > 0 ? productList.map(product => ({
                name: product.name || '',
                quantity: `${product.amount?.name || 'x'}${product.amount?.value || ''}`,
                skuId: String(product.id || '')
            })).filter(product => product.name) : order.products,
            receiver: dynamicInfo.receiverInfo?.receiver || order.receiver,
            amount: `¥${(totalAmount / 100).toFixed(2)}`,
            payment,
            status: status || order.status,
            detailUrl: detailUrl ? absUrl(detailUrl, location.href) : order.detailUrl
        };
    }

    function parseOrders(doc, pageUrl, venderInfo = new Map(), dynamicOrderInfo = new Map()) {
        const url = new URL(pageUrl);
        const year = url.searchParams.get('d') || '';
        const hiddenVenderOrderIds = getHiddenVenderOrderIds(doc);
        const orderSiteIdMap = getOrderSiteIdMap(doc);
        const jdGoHomeSiteIds = getJdGoHomeSiteIds(doc);

        return [...doc.querySelectorAll('table.order-tb > tbody')]
            .filter(tbody => /^tb-/.test(tbody.id))
            .map(tbody => {
                const header = parseOrderHeader(tbody);
                const siteId = orderSiteIdMap.get(header.orderId) || '';
                const shopId = getShopId(doc, header.orderId);
                const venderId = getVenderId(tbody);
                const isJdGoHome = jdGoHomeSiteIds.has(venderId);
                const shop = venderInfo.get(venderId)
                    || header.shop
                    || (hiddenVenderOrderIds.has(header.orderId) ? '隐藏店铺' : '');
                const bodyRows = [...tbody.querySelectorAll('.tr-bd')]
                    .filter(row => !row.classList.contains('sep-tr-bd'));
                const firstCells = [...(bodyRows[0]?.children || [])];
                const amountAndPay = text(firstCells[2]);
                const amount = amountAndPay.match(/¥\s*[\d.]+/)?.[0] || '';
                const payment = amountAndPay.replace(amount, '').trim();
                const statusCell = firstCells[3];
                const detailUrl = [...tbody.querySelectorAll('a[href]')]
                    .map(a => absUrl(a.getAttribute('href'), pageUrl))
                    .find(href => href.includes(`orderid=${header.orderId}`)
                        || href.includes(`/order/detail/${header.orderId}`)) || '';
                const parentOrderId = [...tbody.classList]
                    .find(name => name.startsWith('parent-'))
                    ?.replace(/^parent-/, '') || '';

                const order = {
                    year,
                    orderId: header.orderId,
                    parentOrderId,
                    category: inferOrderCategory(siteId, shop, shopId, isJdGoHome),
                    time: header.time,
                    shop,
                    products: parseProducts(tbody),
                    receiver: text(firstCells[1]),
                    amount,
                    payment,
                    status: text(statusCell?.querySelector('.order-status')) || text(statusCell),
                    detailUrl,
                    sourceUrl: pageUrl
                };

                return applyDynamicOrderInfo(order, dynamicOrderInfo.get(header.orderId));
            });
    }

    async function collectOrders(startUrl, onProgress) {
        const orders = [];
        const visited = new Set();
        let url = startUrl;
        let pageIndex = 1;

        while (url && !visited.has(url)) {
            visited.add(url);
            onProgress(`正在读取第 ${pageIndex} 页...`);

            const shouldUseCurrentDocument = normalizeUrl(url) === normalizeUrl(location.href);
            const doc = shouldUseCurrentDocument ? document : await fetchDoc(url);
            const venderInfo = await fetchPageVenderInfo(doc);
            const dynamicOrderInfo = await fetchDynamicOrderInfo(doc);
            const pageOrders = parseOrders(doc, url, venderInfo, dynamicOrderInfo);
            orders.push(...pageOrders);
            logger.info(`第 ${pageIndex} 页读取 ${pageOrders.length} 个订单`);

            url = getNextUrl(doc, url);
            pageIndex += 1;

            if (url) {
                await sleep(CONFIG.REQUEST_DELAY);
            }
        }

        return orders;
    }

    function csvEscape(value) {
        const str = String(value ?? '');
        return `"${str.replace(/"/g, '""')}"`;
    }

    function formatProducts(products) {
        return products
            .map(product => `${product.name}${product.quantity ? ` ${product.quantity}` : ''}`)
            .join('；');
    }

    function ordersToCsv(orders) {
        const headers = [
            '年份',
            '订单号',
            '父订单号',
            '订单类型',
            '下单时间',
            '店铺',
            '商品',
            '收货信息',
            '金额',
            '支付方式',
            '状态',
            '详情链接'
        ];
        const rows = orders.map(order => [
            order.year,
            order.orderId,
            order.parentOrderId,
            order.category,
            order.time,
            order.shop,
            formatProducts(order.products),
            order.receiver,
            order.amount,
            order.payment,
            order.status,
            order.detailUrl
        ]);

        return [headers, ...rows]
            .map(row => row.map(csvEscape).join(','))
            .join('\n');
    }

    function download(filename, content, type) {
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');

        link.href = url;
        link.download = filename;
        link.click();

        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    function getFilenameBase(yearValue) {
        const year = yearValue === '3' ? 'before-2014' : yearValue || 'current';
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        return `jd-orders-${year}-${timestamp}`;
    }

    function setButtonsDisabled(buttons, disabled) {
        buttons.forEach(button => {
            button.disabled = disabled;
        });
    }

    async function runExport(format, yearSelect, statusEl, buttons) {
        try {
            setButtonsDisabled(buttons, true);

            const yearValue = yearSelect.value;
            const orders = await collectOrders(getCurrentFilterUrl(yearValue), message => {
                statusEl.textContent = message;
            });
            const filenameBase = getFilenameBase(yearValue);

            if (format === 'csv') {
                download(
                    `${filenameBase}.csv`,
                    CONFIG.CSV_BOM + ordersToCsv(orders),
                    'text/csv;charset=utf-8'
                );
            } else {
                download(
                    `${filenameBase}.json`,
                    JSON.stringify(orders, null, 2),
                    'application/json;charset=utf-8'
                );
            }

            statusEl.textContent = `完成：${orders.length} 个订单`;
        } catch (error) {
            logger.error('导出失败', error);
            statusEl.textContent = `失败：${error.message}`;
        } finally {
            setButtonsDisabled(buttons, false);
        }
    }

    function createButton(label) {
        const button = document.createElement('button');
        button.textContent = label;
        button.className = 'jd-order-export-button';
        return button;
    }

    function createYearSelect() {
        const select = document.createElement('select');
        const currentYear = new Date().getFullYear();
        const currentD = new URL(location.href).searchParams.get('d') || String(currentYear);

        select.className = 'jd-order-export-year';

        for (let year = currentYear; year >= 2014; year -= 1) {
            const option = document.createElement('option');
            option.value = String(year);
            option.textContent = year === currentYear ? `${year}年（今年）` : `${year}年`;
            select.appendChild(option);
        }

        const before2014 = document.createElement('option');
        before2014.value = '3';
        before2014.textContent = '2014年以前';
        select.appendChild(before2014);

        select.value = [...select.options].some(option => option.value === currentD)
            ? currentD
            : String(currentYear);

        return select;
    }

    function createPanel() {
        if (document.getElementById(CONFIG.PANEL_ID)) return;

        const panel = document.createElement('div');
        panel.id = CONFIG.PANEL_ID;

        const status = document.createElement('div');
        status.className = 'jd-order-export-status';
        status.textContent = '京东订单导出';

        const yearSelect = createYearSelect();
        const csvButton = createButton('导出 CSV');
        const jsonButton = createButton('导出 JSON');
        const buttons = [csvButton, jsonButton];

        csvButton.addEventListener('click', () => runExport('csv', yearSelect, status, buttons));
        jsonButton.addEventListener('click', () => runExport('json', yearSelect, status, buttons));

        panel.append(status, yearSelect, csvButton, jsonButton);
        document.body.appendChild(panel);
    }

    GM_addStyle(`
        #${CONFIG.PANEL_ID} {
            position: fixed;
            right: 16px;
            bottom: 16px;
            z-index: 999999;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            background: #fff;
            box-shadow: 0 4px 16px rgba(0, 0, 0, .15);
            color: #333;
            font-size: 12px;
        }

        #${CONFIG.PANEL_ID} .jd-order-export-status {
            max-width: 260px;
            margin-bottom: 8px;
            line-height: 1.5;
        }

        #${CONFIG.PANEL_ID} .jd-order-export-button {
            margin-right: 6px;
            padding: 4px 8px;
            cursor: pointer;
        }

        #${CONFIG.PANEL_ID} .jd-order-export-year {
            max-width: 120px;
            margin-right: 6px;
            padding: 3px 6px;
        }

        #${CONFIG.PANEL_ID} .jd-order-export-button:disabled {
            cursor: not-allowed;
            opacity: .6;
        }
    `);

    createPanel();
})();
