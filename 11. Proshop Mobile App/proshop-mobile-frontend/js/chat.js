/**
 * Chat module — manages conversation state and rendering.
 */

const Chat = {
  messages: [],
  inputEl: null,
  messagesEl: null,

  init(messagesEl, inputEl) {
    this.messagesEl = messagesEl;
    this.inputEl = inputEl;
    this.messages = [];
    this.addAssistantMessage(
      'Welcome to ProShop Assistant! Ask me anything about work orders, parts, or operations.\n\n' +
      'Try: "Show me all open work orders" or "What\'s the status of WO 25-0001?"'
    );
  },

  addUserMessage(text) {
    this.messages.push({ role: 'user', text });
    this._render();
  },

  addAssistantMessage(text) {
    this.messages.push({ role: 'assistant', text });
    this._render();
  },

  addLoadingMessage() {
    this.messages.push({ role: 'assistant', text: '...', loading: true });
    this._render();
  },

  removeLoadingMessage() {
    this.messages = this.messages.filter(m => !m.loading);
  },

  async send(message) {
    if (!message.trim()) return;

    this.addUserMessage(message);
    this.addLoadingMessage();

    try {
      const result = await API.chat(message);
      this.removeLoadingMessage();
      this.addAssistantMessage(result.response || 'No response received.');
    } catch (err) {
      this.removeLoadingMessage();
      this.addAssistantMessage(`Error: Could not reach the server. Is the backend running?\n\n${err.message}`);
    }
  },

  _render() {
    if (!this.messagesEl) return;

    this.messagesEl.innerHTML = this.messages.map(m => {
      const cls = m.role === 'user' ? 'user' : 'assistant';
      const text = this._escapeHtml(m.text);
      return `<div class="chat-bubble ${cls}">${text}</div>`;
    }).join('');

    // Scroll to bottom
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
  },

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
};
