console.log("🚀 AI Memory Extension Loaded (V105 - Spaceholder Strategy)");

// 1. GLOBAL STATE
let globalState = { auth_token: null, selected_project_id: null };
let lastCheckedInput = null;
let pollInterval = null;

// 2. INIT STATE
chrome.storage.local.get(['auth_token', 'selected_project_id'], (data) => {
    globalState = data;
    console.log("💾 State Loaded:", globalState);
});

// 3. LISTEN FOR CHANGES
chrome.storage.onChanged.addListener((changes) => {
    if (changes.auth_token) globalState.auth_token = changes.auth_token.newValue;
    if (changes.selected_project_id) globalState.selected_project_id = changes.selected_project_id.newValue;

    if (changes.auth_token && !changes.auth_token.newValue) globalState.auth_token = null;
    if (changes.selected_project_id && !changes.selected_project_id.newValue) globalState.selected_project_id = null;
});

// 4. SITES CONFIG
const DEFAULT_SITES = {
    'chatgpt.com': {
        button: 'button[data-testid="send-button"], button[data-testid="fruitjuice-send-button"], #composer-submit-button',
        stopButtonSelector: 'button[aria-label="Stop generating"], button[data-testid="stop-button"]',
        streamingSelector: '.result-streaming',
        userMsg: 'div[data-message-author-role="user"]',
        aiMsg: 'div[data-message-author-role="assistant"]'
    },
    'gemini.google.com': {
        button: '.send-button, button:has(mat-icon[data-mat-icon-name="send"]), button:has(mat-icon[fonticon="send"])',
        stopButtonSelector: 'button[aria-label="Stop response"]',
        streamingSelector: '.streaming',
        userMsg: ['.query-text', '.user-query', 'div[data-message-author-role="user"]'],
        aiMsg: ['.markdown', '.model-response', 'message-content']
    },
    'chat.deepseek.com': {
        button: 'div[role="button"]:has(svg)',
        stopButtonSelector: ['div[role="button"]:has(svg rect)', '.ds-stop-button', '[aria-label="Stop"]'],
        streamingSelector: '.ds-markdown--assistant.streaming',
        userMsg: ['div.fbb737a4', '.ds-markdown--user'],
        aiMsg: ['.ds-markdown']
    },
    'chat.mistral.ai': {
        button: 'button[aria-label="Send query"], button:has(svg)',
        stopButtonSelector: 'button[aria-label="Stop generating"]',
        streamingSelector: '.animate-pulse',
        userMsg: ['.bg-basic-gray-alpha-4 .select-text', 'div.ms-auto .select-text', '.select-text'],
        aiMsg: ['div[data-message-part-type="answer"]', '.markdown-container-style', '.prose']
    },
    'perplexity.ai': {
        button: 'button[aria-label="Submit"], button[aria-label="Ask"]',
        stopButtonSelector: 'button[aria-label="Stop"]',
        streamingSelector: '.animate-pulse',
        userMsg: ['h1 .select-text', 'div[class*="group/query"] .select-text', '.font-display'],
        aiMsg: ['.prose', 'div[dir="auto"]']
    }
};

let activeSitesConfig = DEFAULT_SITES;

function fetchRemoteConfig() {
    console.log("🌐 Fetching Remote Site Config...");
    fetch('https://web-production-7e6a8.up.railway.app/api/config/sites/')
        .then(res => res.json())
        .then(data => {
            if (data && Object.keys(data).length > 0) {
                activeSitesConfig = data;
                console.log("✅ Remote Config Applied:", Object.keys(data));
            }
        })
        .catch(err => console.warn("⚠️ Config Fetch Failed, using Defaults:", err));
}

fetchRemoteConfig();

function getSiteConfig() {
    const hostname = window.location.hostname;
    for (const [domain, config] of Object.entries(activeSitesConfig)) {
        if (hostname.includes(domain)) return config;
    }
    return null;
}

function isVisible(elem) {
    if (!elem) return false;
    return !!(elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length);
}

function getEditableElement(el) {
    if (!el) return null;
    if (el.tagName === 'TEXTAREA') return el;
    if (el.tagName === 'INPUT' && el.type !== 'password' && el.type !== 'hidden') return el;
    if (el.isContentEditable) return el;
    if (el.getAttribute('role') === 'textbox') return el;
    return el.closest('[contenteditable="true"], [role="textbox"], textarea, input');
}

function getMessages(config) {
    let userMsgs = [];
    let aiMsgs = [];

    if (Array.isArray(config.userMsg)) {
        for (const sel of config.userMsg) {
            const found = document.querySelectorAll(sel);
            if (found.length > 0) { userMsgs = Array.from(found); break; }
        }
    } else {
        userMsgs = Array.from(document.querySelectorAll(config.userMsg));
    }

    if (Array.isArray(config.aiMsg)) {
        for (const sel of config.aiMsg) {
            const found = document.querySelectorAll(sel);
            if (found.length > 0) { aiMsgs = Array.from(found); break; }
        }
    } else {
        aiMsgs = Array.from(document.querySelectorAll(config.aiMsg));
    }

    // DeepSeek Fallback
    if (window.location.hostname.includes('deepseek.com')) {
        if (aiMsgs.length === 0) aiMsgs = Array.from(document.querySelectorAll('.ds-markdown'));
        if (userMsgs.length === 0 && aiMsgs.length > 0) {
            const allDivs = document.querySelectorAll('div');
            const candidate = Array.from(allDivs).find(d =>
                d.textContent.includes("SYSTEM CONTEXT INJECTION") && d.textContent.length < 10000
            );
            if (candidate) userMsgs = [candidate];
        }
    }
    return { userMsgs, aiMsgs };
}

// --- PART 1: UNIVERSAL INPUT DETECTION ---
document.addEventListener('keydown', (e) => {
    if (!e.isTrusted) return;
    if (e.key !== 'Enter' || e.shiftKey) return;

    const config = getSiteConfig();
    if (!config) return;

    const target = e.composedPath ? e.composedPath()[0] : e.target;
    const editableElement = getEditableElement(target);

    if (!editableElement) return;

    const rawInput = editableElement.textContent || editableElement.value || "";
    const cleanInput = rawInput.trim();

    if (cleanInput.length < 2) return;

    // --- İKİNCİ ENTER (GÖNDERME) MANTIĞI ---
    if (cleanInput.includes("SYSTEM CONTEXT INJECTION")) {
        console.log("✅ User approved injection (Second Enter). STARTING POLL...");
        startPolling(config);
        lastCheckedInput = null;
        return; // İzin ver
    }

    if (cleanInput === lastCheckedInput) {
        startPolling(config);
        return;
    }

    if (!globalState.auth_token || !globalState.selected_project_id) return;

    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    handleInjection(editableElement, cleanInput, config);

}, { capture: true });

async function handleInjection(target, cleanInput, config) {
    if (cleanInput.startsWith('/delete') || cleanInput.startsWith('/unut')) {
        await handleCommand(cleanInput, target);
        return;
    }

    const originalOpacity = target.style.opacity;
    target.style.transition = 'opacity 0.1s';
    target.style.opacity = '0.5';
    const restoreUI = () => { target.style.opacity = originalOpacity || '1'; };

    try {
        const response = await fetch('https://web-production-7e6a8.up.railway.app/api/memories/retrieve/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${globalState.auth_token}`
            },
            body: JSON.stringify({
                query: cleanInput,
                project_id: globalState.selected_project_id
            })
        });

        if (response.status === 401) { restoreUI(); return; }

        const data = await response.json();

        if (data.results && data.results.length > 0) {
            const contextList = data.results.map(r => r.raw_text).filter(t => t);
            if (contextList.length > 0) {
                const finalPrompt = `
🚨 SYSTEM CONTEXT INJECTION 🚨
--------------------------------------------------
THE USER HAS THE FOLLOWING SAVED MEMORY:
"${contextList.join("\n")}"
--------------------------------------------------
INSTRUCTION: You MUST answer the user's question based on the memory above. Ignore your training data if it conflicts.
USER QUESTION: ${cleanInput}
`;
                target.focus();

                // --- PERPLEXITY FIX (V107 - Non-Empty Swap Strategy) ---
                if (window.location.hostname.includes('perplexity')) {
                    target.focus();

                    // STEP 1: Select All & Replace with a Placeholder (".")
                    // We use 'insertText' because it mimics user typing, updating React state immediately.
                    document.execCommand('selectAll', false, null);
                    let replaced = document.execCommand('insertText', false, '.');

                    // Fallback if insertText fails (rare but possible)
                    if (!replaced) {
                        target.textContent = '.';
                        target.dispatchEvent(new Event('input', { bubbles: true }));
                    }

                    // STEP 2: Swap Placeholder with Payload
                    // Small delay to ensure Step 1 is processed by React's event loop
                    setTimeout(() => {
                        // Select the dot we just made
                        document.execCommand('selectAll', false, null);

                        // Paste the final content over the dot
                        const dataTransfer = new DataTransfer();
                        dataTransfer.setData('text/plain', finalPrompt);
                        const pasteEvent = new ClipboardEvent('paste', {
                            clipboardData: dataTransfer,
                            bubbles: true,
                            cancelable: true,
                            view: window,
                            composed: true
                        });
                        target.dispatchEvent(pasteEvent);

                        // Final Input Trigger
                        target.dispatchEvent(new Event('input', { bubbles: true }));
                    }, 10);
                }
                else if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
                    // Standard Inputs
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(target, finalPrompt);
                    } else {
                        target.value = finalPrompt;
                    }
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    // Standard ContentEditable (Mistral, Gemini, ChatGPT)
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);
                    const success = document.execCommand('insertText', false, finalPrompt);

                    if (!success) {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.setData('text/plain', finalPrompt);
                        target.dispatchEvent(new ClipboardEvent('paste', {
                            clipboardData: dataTransfer,
                            bubbles: true,
                            cancelable: true
                        }));
                    }
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                }

                console.log("✅ Memory Injected. Waiting for user to press Enter...");
                lastCheckedInput = null;
                restoreUI();
                return;
            }
        }

        lastCheckedInput = cleanInput;
        restoreUI();

    } catch (err) {
        console.error("Injection Error", err);
        restoreUI();
    }
}

// --- COMMAND HANDLER ---
async function handleCommand(command, target) {
    const parts = command.split(/\s+(.*)/s);
    const targetText = parts[1] || "";
    target.innerText = "⏳ Siliniyor...";

    try {
        const response = await fetch('https://web-production-7e6a8.up.railway.app/api/memories/delete/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${globalState.auth_token}`
            },
            body: JSON.stringify({
                project_id: globalState.selected_project_id,
                target_text: targetText
            })
        });
        const data = await response.json();
        if (data.success) {
            alert(`✅ Deleted: "${data.deleted_text}"`);
            if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
                target.value = "";
                target.dispatchEvent(new Event('input', { bubbles: true }));
            } else {
                target.innerText = "";
            }
        } else {
            alert(`⚠️ Error: ${data.message}`);
        }
    } catch (err) { alert("❌ Server Error"); }
}

// --- PART 2: POLLING ---

function startPolling(config) {
    if (pollInterval) clearInterval(pollInterval);
    console.log("⏳ Polling started...");

    const safetyStop = setTimeout(() => {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
            console.log("🛑 Polling timed out.");
        }
    }, 120000);

    pollInterval = setInterval(() => {
        const isDone = checkResponseState(config);
        if (isDone) {
            clearInterval(pollInterval);
            clearTimeout(safetyStop);
            pollInterval = null;
            console.log("✅ Cycle complete.");
        }
    }, 500);
}

function checkResponseState(config) {
    let stopBtn = null;
    if (Array.isArray(config.stopButtonSelector)) {
        for (const sel of config.stopButtonSelector) {
            stopBtn = document.querySelector(sel);
            if (stopBtn) break;
        }
    } else {
        stopBtn = document.querySelector(config.stopButtonSelector);
    }

    const isStopBtnVisible = isVisible(stopBtn);
    const isStreaming = config.streamingSelector ? document.querySelector(config.streamingSelector) : false;
    const isStreamingActive = !!isStreaming;

    const { userMsgs, aiMsgs } = getMessages(config);

    console.log(`🔍 Check - Stop: ${isStopBtnVisible}, Stream: ${isStreamingActive}, Msgs: ${userMsgs.length}/${aiMsgs.length}`);

    const isAIStopped = !isStopBtnVisible && !isStreamingActive;

    if (isAIStopped && userMsgs.length > 0 && aiMsgs.length > 0) {
        captureAndSave(config);
        return true;
    }
    return false;
}

async function captureAndSave(config, attempt = 1) {
    if (!globalState.auth_token || !globalState.selected_project_id) return;

    const { userMsgs, aiMsgs } = getMessages(config);
    if (userMsgs.length === 0 || aiMsgs.length === 0) return;

    const lastUserEl = userMsgs[userMsgs.length - 1];
    const lastAiEl = aiMsgs[aiMsgs.length - 1];

    const cleanText = (el) => (el.innerText || el.textContent || "").replace(/[\u200B-\u200D\uFEFF]/g, "").trim();

    const lastUserMsg = cleanText(lastUserEl);
    const lastAiMsg = cleanText(lastAiEl);

    console.log(`📝 Extract Attempt ${attempt} - User: "${lastUserMsg.substring(0, 20)}...", AI: "${lastAiMsg.substring(0, 20)}..."`);

    if (!lastUserMsg || !lastAiMsg) {
        if (attempt < 3) {
            console.warn(`⚠️ Empty text detected. Retrying in 500ms... (Attempt ${attempt}/3)`);
            setTimeout(() => captureAndSave(config, attempt + 1), 500);
            return;
        } else {
            console.warn("❌ Aborting: Text still empty after 3 attempts.");
            return;
        }
    }

    try {
        await fetch('https://web-production-7e6a8.up.railway.app/api/memories/store/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${globalState.auth_token}`
            },
            body: JSON.stringify({
                text: `User: ${lastUserMsg}\n\nAI: ${lastAiMsg}`,
                project_id: globalState.selected_project_id
            })
        });
        console.log("🎉 MEMORY SAVED!");
    } catch (err) { console.error("Save Error:", err); }
}