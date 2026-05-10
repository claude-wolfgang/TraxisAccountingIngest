/**
 * ProShop Message Notifier — Service Worker
 * Polls Flask API every 30s, shows chrome.notifications,
 * manages badge, and coordinates with content script.
 */

const API_BASE = 'http://10.1.1.71:5050';
const POLL_ALARM = 'pollMessages';
const MESSAGES_BASE = 'https://traxismfg.adionsystems.com/procnc/users/';

// ── Lifecycle ───────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log('ProShop Message Notifier: installed');
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 });
});

// ── Alarm Handler ───────────────────────────────────────────

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== POLL_ALARM) return;

  const { userId, userName } = await chrome.storage.local.get(['userId', 'userName']);
  if (!userId) return;

  try {
    const resp = await fetch(`${API_BASE}/api/messages/${encodeURIComponent(userId)}/check`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.has_new) {
      // Update badge
      chrome.action.setBadgeText({ text: data.count.toString() });
      chrome.action.setBadgeBackgroundColor({ color: '#22c55e' });

      // Desktop notification (only fire once per "session" of new messages)
      const { notifiedAt } = await chrome.storage.local.get('notifiedAt');
      const now = Date.now();
      if (!notifiedAt || now - notifiedAt > 60000) {
        const title = 'New ProShop Message';
        let body = data.sender ? `From: ${data.sender}` : '';
        if (data.count > 1) body += (body ? '\n' : '') + `${data.count} messages`;

        chrome.notifications.create('psn-new-msg', {
          type: 'basic',
          iconUrl: 'icons/icon128.png',
          title,
          message: body || 'You have a new message',
          priority: 2,
          requireInteraction: true
        });
        await chrome.storage.local.set({ notifiedAt: now });
      }

      // Store state + tell content scripts to show disc
      await chrome.storage.local.set({ hasNotification: true, lastSender: data.sender, lastCount: data.count });
      broadcastToTabs({ type: 'SHOW_NOTIFICATION', sender: data.sender, count: data.count });
    } else {
      // Clear badge + hide disc
      chrome.action.setBadgeText({ text: '' });
      await chrome.storage.local.set({ hasNotification: false, lastSender: '', lastCount: 0 });
      broadcastToTabs({ type: 'HIDE_NOTIFICATION' });
    }
  } catch (err) {
    console.warn('ProShop Notifier: poll error:', err.message);
  }
});

// ── Notification Click ──────────────────────────────────────

chrome.notifications.onClicked.addListener(async (notifId) => {
  if (notifId !== 'psn-new-msg') return;
  chrome.notifications.clear('psn-new-msg');
  const { userId } = await chrome.storage.local.get('userId');
  const url = userId
    ? MESSAGES_BASE + userId + '$formName=messageinbox'
    : MESSAGES_BASE;
  chrome.tabs.create({ url });
  await doAcknowledge();
});

// ── Messages from Content Script ────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'USER_DETECTED') {
    handleUserDetected(msg.name).then(sendResponse);
    return true; // async response
  }

  if (msg.type === 'ACKNOWLEDGE') {
    doAcknowledge().then(() => sendResponse({ success: true }));
    return true;
  }

  if (msg.type === 'GET_STATE') {
    chrome.storage.local.get(['userId', 'userName', 'hasNotification', 'lastSender', 'lastCount']).then((data) => {
      sendResponse({
        userId: data.userId,
        userName: data.userName,
        hasNotification: data.hasNotification || false,
        sender: data.lastSender || '',
        count: data.lastCount || 0
      });
    });
    return true;
  }
});

// ── User Detection ──────────────────────────────────────────

async function handleUserDetected(name) {
  if (!name) return { success: false, error: 'No name provided' };

  // Check if we already have this user mapped
  const { userName, userId } = await chrome.storage.local.get(['userName', 'userId']);
  if (userName === name && userId) {
    return { success: true, userId };
  }

  // Look up user by name via Flask API
  try {
    const resp = await fetch(`${API_BASE}/api/users/lookup?name=${encodeURIComponent(name)}`);
    if (!resp.ok) {
      console.warn('ProShop Notifier: user lookup failed for', name, resp.status);
      return { success: false, error: `Lookup failed: ${resp.status}` };
    }
    const user = await resp.json();
    await chrome.storage.local.set({
      userId: user.id,
      userName: `${user.firstName} ${user.lastName}`,
      notifiedAt: 0
    });
    console.log('ProShop Notifier: user mapped:', name, '→', user.id);
    return { success: true, userId: user.id };
  } catch (err) {
    console.warn('ProShop Notifier: user lookup error:', err.message);
    return { success: false, error: err.message };
  }
}

// ── Acknowledge ─────────────────────────────────────────────

async function doAcknowledge() {
  const { userId } = await chrome.storage.local.get('userId');
  if (!userId) return;

  try {
    await fetch(`${API_BASE}/api/messages/${encodeURIComponent(userId)}/acknowledge`, {
      method: 'POST'
    });
  } catch (err) {
    console.warn('ProShop Notifier: acknowledge error:', err.message);
  }

  chrome.action.setBadgeText({ text: '' });
  await chrome.storage.local.set({ notifiedAt: 0, hasNotification: false, lastSender: '', lastCount: 0 });
  broadcastToTabs({ type: 'HIDE_NOTIFICATION' });
}

// ── Helpers ─────────────────────────────────────────────────

function broadcastToTabs(message) {
  chrome.tabs.query({ url: 'https://traxismfg.adionsystems.com/*' }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, message).catch(() => {});
    }
  });
}
