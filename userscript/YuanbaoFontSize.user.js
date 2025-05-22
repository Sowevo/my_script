// ==UserScript==
// @name         腾讯元宝优化
// @namespace    http://tampermonkey.net/
// @version      0.2.1
// @description  腾讯元宝优化
// @author       sowevo
// @license      Custom License
// @match        https://yuanbao.tencent.com/*
// @grant        GM_addStyle
// @grant        GM_notification
// @grant        GM_setValue
// @grant        GM_getValue
// @downloadURL  https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/YuanbaoFontSize.user.js
// @updateURL    https://github.com/Sowevo/my_script/raw/refs/heads/main/userscript/YuanbaoFontSize.user.js
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
        SIZE_CHANGE_BUTTON_ID: 'fontSizeChange',
        SPLIT_INPUT_BUTTON_ID: 'splitInput',
        STYLE_ID: 'yuanbao-font-control',
        LARGE_FONT_SIZE: '36px',
        CODE_FONT_SIZE: '34px',
        MAX_WIDTH: 'calc(100% - 40px)',
        POLLING_INTERVAL: 1000,
        INPUT_DELAY: 300,
        SPLIT_MARKER: '~~~'
    };

    // 状态管理
    const state = {
        isLargeFont: GM_getValue('isLargeFont', false),
        isSplitInput: false,
        styleElement: null,
        observer: null,
        previousState: null,
        pollingInterval: null,
        inputList: [],
        buttonElements: {}
    };

    // --- 日志系统 ---
    const logger = {
        info: (msg) => console.info(`[元宝优化] ${msg}`),
        error: (msg, error) => {
            console.error(`[元宝优化] ${msg}`, error);
            GM_notification({
                text: `控制错误: ${msg}`,
                title: '脚本错误',
                timeout: 3000
            });
        },
        debug: (msg) => console.debug(`[元宝优化] ${msg}`)
    };

    // --- 样式管理 ---
    const styleManager = {
        applyCustomStyles() {
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
        },

        removeCustomStyles() {
            try {
                if (state.styleElement?.parentNode) {
                    state.styleElement.parentNode.removeChild(state.styleElement);
                }
                state.styleElement = null;
                logger.info('自定义样式已移除');
            } catch (e) {
                logger.error('移除样式失败', e);
            }
        },

        toggleFontSize() {
            state.isLargeFont = !state.isLargeFont;
            GM_setValue('isLargeFont', state.isLargeFont);

            if (state.isLargeFont) {
                this.applyCustomStyles();
            } else {
                this.removeCustomStyles();
            }

            return state.isLargeFont;
        }
    };

    // --- 编辑器操作 ---
    const editorManager = {
        getEditor() {
            return document.querySelector('.ql-editor');
        },

        getText() {
            const editor = this.getEditor();
            if (editor) {
                return editor.innerText;
            }
            return '';
        },

        setText(text) {
            const editor = this.getEditor();
            if (editor) {
                editor.innerText = text;
            }
        },

        clearText() {
            this.setText('');
        }
    };

    // --- 按钮状态管理 ---
    const buttonManager = {
        getSendButton() {
            return document.querySelector('a.style__send-btn___ZsLmU');
        },

        getSendButtonState(btn) {
            if (!btn) return '未找到按钮';

            const hasDisabledClass = btn.classList.contains('style__send-btn--disabled___agMBn');
            const hasSvg = btn.querySelector('svg') !== null;
            const hasSpan = btn.querySelector('span') !== null;

            if (hasSvg) return '输出中';
            if (hasDisabledClass && hasSpan) return '输出完成';
            if (!hasDisabledClass && hasSpan) return '输入中';
            return '未知状态';
        },

        handleStateChange(newState) {
            if (newState === state.previousState) return;

            logger.debug(`按钮状态变化：${state.previousState} → ${newState}`);

            if (newState === '输出完成') {
                if (state.previousState === '输入中') {
                    logger.debug('⚠️ 从"输入中"直接切换到"输出完成"！');
                } else if (state.previousState === '输出中') {
                    logger.debug('✅ 输出完成，准备下一轮');
                    this.processNextInput();
                }
            }

            state.previousState = newState;
        },

        processNextInput() {
            if (state.inputList.length > 0) {
                const text = state.inputList.shift();
                this.inputText(text);
            } else {
                this.stopBatchInput();
            }
        },

        inputText(text) {
            setTimeout(() => {
                editorManager.setText(text);
                setTimeout(() => {
                    const btn = this.getSendButton();
                    if (btn) btn.click();
                }, CONFIG.INPUT_DELAY);
            }, CONFIG.INPUT_DELAY);
        },

        startBatchInput() {
            const text = editorManager.getText();
            if (text) {
                state.inputList = text.split(CONFIG.SPLIT_MARKER);
                editorManager.clearText();
            }

            if (state.inputList.length > 0) {
                state.pollingInterval = setInterval(() => {
                    const btn = this.getSendButton();
                    const currentState = this.getSendButtonState(btn);
                    this.handleStateChange(currentState);
                }, CONFIG.POLLING_INTERVAL);

                this.inputText(state.inputList.shift());
                return true;
            }
            return false;
        },

        stopBatchInput() {
            if (state.pollingInterval) {
                clearInterval(state.pollingInterval);
                state.pollingInterval = null;
            }
            state.inputList = [];
            state.isSplitInput = false;
            this.updateButtonText();
        },

        toggleBatchInput() {
            if (state.isSplitInput) {
                this.stopBatchInput();
            } else {
                state.isSplitInput = this.startBatchInput();
            }
            this.updateButtonText();
            return state.isSplitInput;
        },

        updateButtonText() {
            if (state.buttonElements.splitInput) {
                state.buttonElements.splitInput.textContent =
                    state.isSplitInput ? '取消批量输入' : '开启批量输入';
            }
            if (state.buttonElements.fontSizeChange) {
                state.buttonElements.fontSizeChange.textContent =
                    state.isLargeFont ? '恢复字体大小' : '改变字体大小';
            }
        }
    };

    // --- UI 控制 ---
    const uiManager = {
        createControlButton() {
            // 清除旧按钮
            this.removeControlButtons();

            // 创建按钮
            state.buttonElements.fontSizeChange = this.createButton(
                CONFIG.SIZE_CHANGE_BUTTON_ID,
                state.isLargeFont ? '恢复字体大小' : '改变字体大小',
                '190px',
                () => {
                    styleManager.toggleFontSize();
                    buttonManager.updateButtonText();
                }
            );

            state.buttonElements.splitInput = this.createButton(
                CONFIG.SPLIT_INPUT_BUTTON_ID,
                '开启批量输入',
                '235px',
                () => {
                    buttonManager.toggleBatchInput();
                }
            );

            logger.info('控制按钮创建成功');
        },

        createButton(id, text, top, onClick) {
            const button = document.createElement('button');
            button.id = id;
            button.textContent = text;

            Object.assign(button.style, {
                position: 'fixed',
                top: top,
                right: '10px',
                zIndex: '10001',
                padding: '8px 12px',
                backgroundColor: '#28a745',
                color: '#ffffff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                transition: 'all 0.3s ease',
                fontFamily: 'Arial, sans-serif',
                fontSize: '13px',
                boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
                whiteSpace: 'nowrap',
                opacity: '0.9'
            });

            // 交互效果
            button.onmouseover = () => { if (!button.disabled) button.style.opacity = '1'; };
            button.onmouseout = () => { if (!button.disabled) button.style.opacity = '0.9'; };
            button.addEventListener('click', onClick);

            document.body.appendChild(button);
            return button;
        },

        removeControlButtons() {
            Object.values(state.buttonElements).forEach(btn => {
                if (btn && btn.parentNode) {
                    btn.parentNode.removeChild(btn);
                }
            });
            state.buttonElements = {};
        },

        setupObserver() {
            state.observer = new MutationObserver(() => {
                if (!document.getElementById(CONFIG.SIZE_CHANGE_BUTTON_ID) ||
                    !document.getElementById(CONFIG.SPLIT_INPUT_BUTTON_ID)) {
                    logger.info('检测到按钮丢失，重新创建中...');
                    this.createControlButton();
                }
            });

            state.observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    };

    // --- 初始化 ---
    function initialize() {
        try {
            if (document.body) {
                // 恢复字体状态
                if (state.isLargeFont) {
                    styleManager.applyCustomStyles();
                }

                uiManager.createControlButton();
                uiManager.setupObserver();
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