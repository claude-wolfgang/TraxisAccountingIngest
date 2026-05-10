/**
 * ProShop Message Notifier — Content Script
 * Detects logged-in user from DOM, injects pulsing disc overlay,
 * plays chime sound on new messages.
 */

const MESSAGES_BASE = 'https://traxismfg.adionsystems.com/procnc/users/';

// ── User Detection (3 strategies from traxis-ipc) ───────────

function detectUserFromDOM() {
  // Strategy 1: "Record Modified/Created by: First Last"
  const body = document.body.innerText;
  const modifiedMatch = body.match(/Record (?:Modified|Created).*?by:\s*([A-Z][a-z]+ [A-Z][a-z]+)/);
  if (modifiedMatch) return modifiedMatch[1];

  // Strategy 2: Name near logout/signout links
  const logoutLinks = document.querySelectorAll(
    'a[href*="logout" i], a[href*="signout" i], [onclick*="logout" i]'
  );
  for (const link of logoutLinks) {
    const parent = link.parentElement;
    if (!parent) continue;
    for (const node of parent.childNodes) {
      if (node === link) continue;
      const text = (node.textContent || '').trim();
      if (text.length >= 3 && text.length < 40 && /^[A-Z][a-z]+ [A-Z]/.test(text)) {
        return text.replace(/[|·•\-,]+$/, '').trim();
      }
    }
  }

  // Strategy 3: Elements with user-related classes
  const userEls = document.querySelectorAll(
    '[class*="username" i], [class*="user-name" i], [class*="currentUser" i], ' +
    '[id*="username" i], [id*="currentUser" i], [class*="memberName" i]'
  );
  for (const el of userEls) {
    const text = (el.textContent || '').trim();
    if (text.length >= 3 && text.length < 40 && /[A-Za-z]/.test(text)) {
      return text;
    }
  }

  // Strategy 4: "Current Work Orders, First Last is ..." on home page
  const woMatch = body.match(/Current Work Orders,\s+([A-Z][a-z]+ [A-Z][a-z]+)\s+is\s/);
  if (woMatch) return woMatch[1];

  // Strategy 5: "Jump to User" dropdown showing "001 (First Last)"
  const userDropdowns = document.querySelectorAll('select option');
  for (const opt of userDropdowns) {
    const text = (opt.textContent || '').trim();
    const m = text.match(/^\d+\s*\(([A-Z][a-z]+ [A-Z][a-z]+)\)$/);
    if (m && opt.selected) return m[1];
  }

  return null;
}

async function detectAndReportUser() {
  const name = detectUserFromDOM();
  if (!name) {
    console.log('ProShop Notifier: no user detected from DOM');
    return;
  }
  console.log('ProShop Notifier: detected user:', name);
  try {
    const result = await chrome.runtime.sendMessage({ type: 'USER_DETECTED', name });
    if (result?.success) {
      console.log('ProShop Notifier: user mapped to ID:', result.userId);
    } else {
      console.warn('ProShop Notifier: user mapping failed:', result?.error);
    }
  } catch (err) {
    console.warn('ProShop Notifier: could not send user to service worker:', err.message);
  }
}

// ── Disc Overlay ────────────────────────────────────────────

let discElement = null;

function showDisc(sender, count) {
  if (discElement) {
    // Update existing disc
    updateDiscContent(sender, count);
    return;
  }

  const container = document.createElement('div');
  container.id = 'psn-overlay';
  container.className = 'psn-overlay';
  container.innerHTML = `
    <div class="psn-disc-container">
      <div class="psn-sonar-ring psn-ring-1"><span>CLICK HERE</span></div>
      <div class="psn-sonar-ring psn-ring-2"><span>CLICK HERE</span></div>
      <div class="psn-sonar-ring psn-ring-3"><span>CLICK HERE</span></div>
      <div class="psn-disc">
        <span class="psn-disc-new">NEW</span>
        <span class="psn-disc-message">MESSAGE</span>
        <hr class="psn-disc-sep">
        <span class="psn-disc-sender">${escapeHtml(sender || '')}</span>
        <span class="psn-disc-count">${count > 1 ? count + ' messages' : ''}</span>
      </div>
    </div>
  `;

  container.addEventListener('click', handleDiscClick);
  document.body.appendChild(container);
  discElement = container;

  // Play chime on first show
  playChime();
}

function updateDiscContent(sender, count) {
  if (!discElement) return;
  const senderEl = discElement.querySelector('.psn-disc-sender');
  const countEl = discElement.querySelector('.psn-disc-count');
  if (senderEl) senderEl.textContent = sender || '';
  if (countEl) countEl.textContent = count > 1 ? count + ' messages' : '';
}

function hideDisc() {
  if (discElement) {
    discElement.remove();
    discElement = null;
  }
}

async function handleDiscClick() {
  const { userId } = await chrome.storage.local.get('userId');
  const url = userId
    ? MESSAGES_BASE + userId + '$formName=messageinbox'
    : MESSAGES_BASE;
  window.open(url, '_blank');
  hideDisc();
  chrome.runtime.sendMessage({ type: 'ACKNOWLEDGE' }).catch(() => {});
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Chime Sound (Web Audio API) ─────────────────────────────

function playChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    playNote(ctx, 523, 0, 0.25);      // C5
    playNote(ctx, 659, 0.12, 0.25);    // E5
    playNote(ctx, 784, 0.24, 0.35);    // G5
  } catch (e) {
    // Audio may be blocked by autoplay policy — silently ignore
  }
}

function playNote(ctx, freq, delay, dur) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.frequency.value = freq;
  osc.type = 'sine';
  gain.gain.setValueAtTime(0.15, ctx.currentTime + delay);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + dur);
  osc.start(ctx.currentTime + delay);
  osc.stop(ctx.currentTime + delay + dur);
}

// ── Message Listener ────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'SHOW_NOTIFICATION') {
    showDisc(msg.sender, msg.count);
  } else if (msg.type === 'HIDE_NOTIFICATION') {
    hideDisc();
  }
});

// ── Bootstrap ───────────────────────────────────────────────

console.log('ProShop Message Notifier: content script loaded');

// Detect user on page load
detectAndReportUser();

// Check if there's already an active notification we missed
chrome.runtime.sendMessage({ type: 'GET_STATE' }, (state) => {
  if (state?.hasNotification) {
    showDisc(state.sender, state.count);
  }
});

// Re-detect on AJAX navigation (ProShop uses partial page loads)
let lastUrl = window.location.href;
const observer = new MutationObserver(() => {
  if (window.location.href !== lastUrl) {
    lastUrl = window.location.href;
    detectAndReportUser();
  }
});
observer.observe(document.body, { childList: true, subtree: true });
