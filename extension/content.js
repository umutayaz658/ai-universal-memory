console.log("🚀 AI Memory Extension Loaded (V31 - Smart Button Detection)");

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

const SITES = {
    'chatgpt.com': {
        input: '#prompt-textarea',
        // Broader button detection as fallback, though logic now relies mostly on Stop/Streaming state
        button: 'button[data-testid="send-button"], button[data-testid="fruitjuice-send-button"], #composer-submit-button, button[aria-label*="voice"]',
        stopButtonSelector: 'button[aria-label="Stop generating"], button[data-testid="stop-button"]',
        streamingSelector: '.result-streaming',
        userMsg: 'div[data-message-author-role="user"]',
        aiMsg: 'div[data-message-author-role="assistant"]'
    },
    'gemini.google.com': {
        input: '.ql-editor, div[contenteditable="true"], textarea',
        button: 'button[aria-label*="Send"]',
        stopButtonSelector: 'button[aria-label="Stop response"]',
        streamingSelector: '.streaming',
        userMsg: '.user-query',
        aiMsg: '.model-response'
    }
};

function getSiteConfig() {
    const hostname = window.location.hostname;
    if (hostname.includes('chatgpt.com')) return SITES['chatgpt.com'];
    if (hostname.includes('google.com')) return SITES['gemini.google.com'];
    return null;
}

// Helper: Check if an element is actually visible to the user
function isVisible(elem) {
    if (!elem) return false;
    return !!(elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length);
}

// --- PART 1: INJECTION LOGIC ---
document.addEventListener('keydown', (e) => {
    if (!e.isTrusted) return;
    if (e.key !== 'Enter' || e.shiftKey) return;

    const config = getSiteConfig();
    if (!config) return;

    const target = e.target;
    // Check if target is input or inside input
    const isInput = target.matches(config.input) || target.closest(config.input);

    if (isInput) {
        const rawInput = target.innerText || target.value || "";
        const cleanInput = rawInput.trim();

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
        handleInjection(target, cleanInput);
    }
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
                target.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                document.execCommand('insertText', false, finalPrompt);
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
            target.innerText = "";
            target.dispatchEvent(new Event('input', { bubbles: true }));
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
    const stopBtn = document.querySelector(config.stopButtonSelector);
    const isStreaming = config.streamingSelector ? document.querySelector(config.streamingSelector) : false;

    // KEY FIX: Only rely on "Stop" button absence and "Streaming" class absence.
    // We ignore the "Send" button state because it often turns into a Voice button on Desktop.

    // 1. Is Stop Button visible?
    const isStopBtnVisible = isVisible(stopBtn);

    // 2. Is Streaming active?
    const isStreamingActive = !!isStreaming;

    // AI is stopped if NO stop button visible AND NO streaming happening
    const isAIStopped = !isStopBtnVisible && !isStreamingActive;

    if (isAIStopped) {
        const userMsgs = document.querySelectorAll(config.userMsg);
        const aiMsgs = document.querySelectorAll(config.aiMsg);

        // Ensure we have at least one pair of messages
        if (userMsgs.length > 0 && aiMsgs.length > 0) {
            captureAndSave(config);
            return true; // Stop polling
        }
    }
    return false; // Continue polling
}

async function captureAndSave(config) {
    if (!globalState.auth_token || !globalState.selected_project_id) return;

    const userMsgs = document.querySelectorAll(config.userMsg);
    const aiMsgs = document.querySelectorAll(config.aiMsg);

    if (userMsgs.length === 0 || aiMsgs.length === 0) return;

    const lastUserMsg = userMsgs[userMsgs.length - 1].innerText;
    const lastAiMsg = aiMsgs[aiMsgs.length - 1].innerText;

    if (!lastUserMsg.trim() || !lastAiMsg.trim()) return;

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