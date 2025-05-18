// ==UserScript==
// @name         腾讯元宝字体大小优化版
// @namespace    http://tampermonkey.net/
// @version      0.1.2
// @description  腾讯元宝字体大小控制工具（带状态切换）
// @author       sowevo
// @license      Custom License
// @match        https://yuanbao.tencent.com/*
// @grant        GM_addStyle
// @grant        GM_notification
// @downloadURL
// @updateURL
// ==/UserScript==

/*
个人使用许可：
允许在个人设备上使用和修改，禁止重新分发或用于商业用途
All rights reserved. Unauthorized commercial use prohibited.
*/

(function() {
    'use strict';

    // 配置常量
    const CONFIG = {
        BUTTON_ID: 'fontSizeChange',
        STYLE_ID: 'yuanbao-font-control',
        LARGE_FONT_SIZE: '36px',
        CODE_FONT_SIZE: '34px',
        MAX_WIDTH: 'calc(100% - 40px)'
    };

    // 状态管理
    let state = {
        isLargeFont: false,
        styleElement: null,
        observer: null
    };

    // --- 日志系统 ---
    const logger = {
        info: (msg) => console.info(`[元宝字体控制] ${msg}`),
        error: (msg, error) => {
            console.error(`[元宝字体控制] ${msg}`, error);
            GM_notification({
                text: `字体控制错误: ${msg}`,
                title: '脚本错误',
                timeout: 3000
            });
        }
    };

    // --- 样式管理 ---
    function applyCustomStyles() {
        try {
            const css = `
                :root {
                    --hunyuan-chat-list-max-width: ${CONFIG.MAX_WIDTH};
                }
                .hyc-component-reasoner__text .hyc-common-markdown-style {
                    font-size: ${CONFIG.LARGE_FONT_SIZE} !important;
                }
                .hyc-component-reasoner__text .hyc-common-markdown-style p {
                    font-size: ${CONFIG.LARGE_FONT_SIZE} !important;
                }
                .hyc-component-reasoner__text .hyc-common-markdown-style .hyc-common-markdown__code__inline {
                    font-size: ${CONFIG.CODE_FONT_SIZE} !important;
                    padding: 0.2em 0.4em !important;
                }
            `;

            state.styleElement = GM_addStyle(css);
            state.styleElement.id = CONFIG.STYLE_ID;
            logger.info('自定义样式已应用');
        } catch (e) {
            logger.error('应用样式失败', e);
        }
    }

    function removeCustomStyles() {
        try {
            if (state.styleElement?.parentNode) {
                state.styleElement.parentNode.removeChild(state.styleElement);
            }
            state.styleElement = null;
            logger.info('自定义样式已移除');
        } catch (e) {
            logger.error('移除样式失败', e);
        }
    }

    // --- 按钮管理 ---
    function createControlButton() {
        const existingBtn = document.getElementById(CONFIG.BUTTON_ID);
        if (existingBtn) existingBtn.remove();

        const button = document.createElement('button');
        button.id = CONFIG.BUTTON_ID;
        button.textContent = '改变字体大小';

        // 按钮样式
        Object.assign(button.style, {
            position: 'fixed',
            top: '190px',
            right: '10px',
            zIndex: '10001',
            padding: '8px 12px',
            backgroundColor: '#28a745',
            color: '#ffffff',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            transition: 'opacity 0.3s ease',
            fontFamily: 'Arial, sans-serif',
            fontSize: '13px',
            boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
            whiteSpace: 'nowrap',
            opacity: '0.9'
        });

        // 交互效果
        button.addEventListener('mouseover', () => button.style.opacity = '1');
        button.addEventListener('mouseout', () => button.style.opacity = '0.9');

        // 点击事件
        button.addEventListener('click', () => {
            state.isLargeFont = !state.isLargeFont;

            if (state.isLargeFont) {
                applyCustomStyles();
                button.textContent = '恢复字体大小';
            } else {
                removeCustomStyles();
                button.textContent = '改变字体大小';
            }

            logger.info(`字体状态切换为: ${state.isLargeFont ? '大号' : '默认'}`);
        });

        document.body.appendChild(button);
        logger.info('控制按钮创建成功');
    }

    // --- DOM 观察器 ---
    function setupObserver() {
        state.observer = new MutationObserver(mutations => {
            if (!document.getElementById(CONFIG.BUTTON_ID)) {
                logger.info('检测到按钮丢失，重新创建中...');
                createControlButton();
            }
        });

        state.observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: false,
            characterData: false
        });
    }

    // --- 初始化 ---
    function initialize() {
        try {
            if (document.body) {
                createControlButton();
                setupObserver();
                logger.info('脚本初始化完成');
            } else {
                setTimeout(initialize, 500);
            }
        } catch (e) {
            logger.error('初始化失败', e);
        }
    }

    // 启动脚本
    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }
})();