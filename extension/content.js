console.log("🚀 AI Memory Extension Loaded (V63 - Polling Fix & DeepSeek Stability)");

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

    // Handle logout/cleanup
    if (changes.auth_token && !changes.auth_token.newValue) globalState.auth_token = null;
    if (changes.selected_project_id && !changes.selected_project_id.newValue) globalState.selected_project_id = null;
});

// 4. SITES CONFIG
const SITES = {
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
        userMsg: ['div.fbb737a4', '.ds-markdown--user'], // Weak fallbacks
        aiMsg: ['.ds-markdown'] // Strong selector
    }
};

function getSiteConfig() {
    const hostname = window.location.hostname;
    if (hostname.includes('chatgpt.com')) return SITES['chatgpt.com'];
    if (hostname.includes('google.com')) return SITES['gemini.google.com'];
    if (hostname.includes('deepseek.com')) return SITES['chat.deepseek.com'];
    return null;
}

// Helper: Check if an element is actually visible to the user
function isVisible(elem) {
    if (!elem) return false;
    return !!(elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length);
}

// Helper: robustly identify an editable element
function getEditableElement(el) {
    if (!el) return null;
    if (el.tagName === 'TEXTAREA') return el;
    if (el.tagName === 'INPUT' && el.type !== 'password' && el.type !== 'hidden') return el;
    if (el.isContentEditable) return el;

    // Fallback: Check for ARIA role
    if (el.getAttribute('role') === 'textbox') return el;

    return el.closest('[contenteditable="true"], [role="textbox"], textarea, input');
}

// Helper: Smart Message Scraper (Resolves DeepSeek issues)
function getMessages(config) {
    let userMsgs = [];
    let aiMsgs = [];

    // 1. Try Standard Selectors
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

    // 2. DeepSeek Content-Aware Fallback
    if (window.location.hostname.includes('deepseek.com')) {
        // AI messages are usually stable (.ds-markdown)
        if (aiMsgs.length === 0) {
            aiMsgs = Array.from(document.querySelectorAll('.ds-markdown'));
        }

        if (userMsgs.length === 0 && aiMsgs.length > 0) {
            // FALLBACK STRATEGY 1: Look for "SYSTEM CONTEXT INJECTION"
            // (Only works if we actually injected)
            const allDivs = document.querySelectorAll('div');
            // Filter efficiently: text must exist and be reasonable length
            const candidate = Array.from(allDivs).find(d =>
                d.textContent.includes("SYSTEM CONTEXT INJECTION") && d.textContent.length < 10000
            );

            if (candidate) {
                userMsgs = [candidate];
                console.log("🔦 DeepSeek: Found user message via Content Search");
            } else {
                // FALLBACK STRATEGY 2: Sibling Traversal
                // Find the container of the last AI message and assume previous sibling is User
                const lastAi = aiMsgs[aiMsgs.length - 1];
                let curr = lastAi;
                // Traverse up a few levels to find the message bubble container
                // This is a heuristic guess
                for (let i = 0; i < 5; i++) {
                    if (!curr || !curr.parentElement || curr.tagName === 'BODY') break;
                    if (curr.previousElementSibling) {
                        userMsgs = [curr.previousElementSibling];
                        console.log("🔦 DeepSeek: Found user message via Sibling Traversal");
                        break;
                    }
                    curr = curr.parentElement;
                }
            }
        }
    }

    return { userMsgs, aiMsgs };
}

// Helper: Simulate Paste (Bypasses contenteditable="false" & React locks)
function simulatePaste(element, text) {
    console.log("📋 Simulating Paste Event (V80 - execCommand Priority)...");

    element.focus();

    // 1. Try execCommand (Standard for Rich Text Editors like Gemini)
    // This is deprecated but still the most reliable way to trigger internal editor events
    const success = document.execCommand('insertText', false, text);

    if (success) {
        console.log("✅ execCommand successful");
        return;
    }

    console.warn("⚠️ execCommand failed, trying ClipboardEvent fallback...");

    // 2. Fallback: Clipboard Event
    const dataTransfer = new DataTransfer();
    dataTransfer.setData('text/plain', text);
    const event = new ClipboardEvent('paste', {
        clipboardData: dataTransfer,
        bubbles: true,
        cancelable: true
    });
    element.dispatchEvent(event);

    // 3. Fallback: Direct Value Setter (TextAreas / Inputs)
    if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
        if (nativeInputValueSetter) {
            nativeInputValueSetter.call(element, text);
        } else {
            element.value = text;
        }
        element.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

// --- PART 1: UNIVERSAL INPUT DETECTION (SHADOW DOM SUPPORT) ---
document.addEventListener('keydown', (e) => {
    if (!e.isTrusted) return;
    if (e.key !== 'Enter' || e.shiftKey) return;

    // 1. Identify Site Config
    const config = getSiteConfig();
    if (!config) return;

    // 2. Resolve Target (Shadow DOM Safe)
    const target = e.composedPath ? e.composedPath()[0] : e.target;

    console.log("🎹 Enter Key Pressed on:", target);

    // 3. Property-Based Detection
    const editableElement = getEditableElement(target);

    if (!editableElement) {
        // Not an input field, ignore.
        return;
    }

    console.log("🎯 Editable Element Resolved:", editableElement);

    // FIX: Use textContent for robust reading
    const rawInput = editableElement.textContent || editableElement.value || "";
    const cleanInput = rawInput.trim();

    // FIX: Empty Query check
    if (cleanInput.length < 2) return;

    // Loop Prevention
    if (cleanInput.includes("SYSTEM CONTEXT INJECTION")) {
        console.log("✅ User approved injection. STARTING POLL...");
        startPolling(config);
        lastCheckedInput = null;
        return;
    }

    if (cleanInput === lastCheckedInput) {
        startPolling(config);
        return;
    }

    if (!globalState.auth_token || !globalState.selected_project_id) return;

    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    handleInjection(editableElement, cleanInput);

}, { capture: true });

async function handleInjection(target, cleanInput) {
    if (cleanInput.startsWith('/delete') || cleanInput.startsWith('/unut')) {
        await handleCommand(cleanInput, target);
        return;
    }

    const originalOpacity = target.style.opacity;
    target.style.transition = 'opacity 0.1s';
    target.style.opacity = '0.5';
    const restoreUI = () => { target.style.opacity = originalOpacity || '1'; };

    try {
        const response = await fetch('http://127.0.0.1:8000/api/memories/retrieve/', {
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
                // --- ROBUST INJECTION LOGIC ---
                target.focus();

                if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
                    // NEW: Direct Value Replacement (Cleaner for Inputs)
                    // This overwrites instead of appending
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(target, finalPrompt);
                    } else {
                        target.value = finalPrompt;
                    }
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    // NEW: ContentEditable (ChatGPT, Gemini)
                    // RESTORED V31 LOGIC: Select All -> Delete -> InsertText
                    document.execCommand('selectAll', false, null);
                    document.execCommand('delete', false, null);
                    document.execCommand('insertText', false, finalPrompt);

                    // Basic input trigger
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));
                }

                console.log("✅ Memory Injected.");
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
        const response = await fetch('http://127.0.0.1:8000/api/memories/delete/', {
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

// --- PART 2: POLLING (Smart Button Detection) ---

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
    // FIX: Robust Selector Handling (No queryElement dependency)
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

    // 2. Is Streaming active?
    const isStreaming = config.streamingSelector ? document.querySelector(config.streamingSelector) : false;
    const isStreamingActive = !!isStreaming;

    // Use Helper for Messages
    const { userMsgs, aiMsgs } = getMessages(config);

    console.log(`🔍 Polling Check - StopVisible: ${isStopBtnVisible}, Streaming: ${isStreamingActive}, UserMsgs Found: ${userMsgs.length}`);

    // AI is stopped if NO stop button visible AND NO streaming happening
    const isAIStopped = !isStopBtnVisible && !isStreamingActive;

    if (isAIStopped) {
        // Ensure we have at least one pair of messages
        if (userMsgs.length > 0 && aiMsgs.length > 0) {
            console.log(`✅ Found ${userMsgs.length} user messages and ${aiMsgs.length} AI messages. capturing...`);
            captureAndSave(config);
            return true; // Stop polling
        }
    }
    return false; // Continue polling
}

async function captureAndSave(config, attempt = 1) {
    if (!globalState.auth_token || !globalState.selected_project_id) {
        console.warn("⚠️ Aborting: Missing Auth/Project ID", globalState);
        return;
    }

    // Use Helper
    const { userMsgs, aiMsgs } = getMessages(config);

    if (userMsgs.length === 0 || aiMsgs.length === 0) {
        console.warn("⚠️ captureAndSave aborted: No messages found despite passing polling check.");
        return;
    }

    // Improved Extraction: Handle innerText vs textContent + Zero-Width Spaces
    const lastUserEl = userMsgs[userMsgs.length - 1];
    const lastAiEl = aiMsgs[aiMsgs.length - 1];

    const cleanText = (el) => (el.innerText || el.textContent || "").replace(/[\u200B-\u200D\uFEFF]/g, "").trim();

    const lastUserMsg = cleanText(lastUserEl);
    const lastAiMsg = cleanText(lastAiEl);

    console.log(`📝 Extract Attempt ${attempt} - User: "${lastUserMsg.substring(0, 20)}...", AI: "${lastAiMsg.substring(0, 20)}..."`);

    // RETRY LOGIC for Empty Text (Race Condition Fix) on Gemini/DeepSeek
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
        await fetch('http://127.0.0.1:8000/api/memories/store/', {
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