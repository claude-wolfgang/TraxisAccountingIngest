/**
 * ProShop Mobile API Client
 * Handles all communication with the FastAPI backend.
 */

const API = {
  // Auto-detect base URL — same host as the page, port 8000
  baseUrl: window.location.port === '8000'
    ? window.location.origin
    : `${window.location.protocol}//${window.location.hostname}:8000`,

  async fetch(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    try {
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (err) {
      console.error(`API error: ${endpoint}`, err);
      throw err;
    }
  },

  // Health
  health() {
    return this.fetch('/api/health');
  },

  // Work Orders
  getWorkOrders(status) {
    const params = status ? `?status=${encodeURIComponent(status)}` : '';
    return this.fetch(`/api/workorders${params}`);
  },

  getWorkOrder(woNumber) {
    return this.fetch(`/api/workorders/${encodeURIComponent(woNumber)}`);
  },

  getWorkOrderOps(woNumber) {
    return this.fetch(`/api/workorders/${encodeURIComponent(woNumber)}/ops`);
  },

  getWorkOrderCurrentOp(woNumber) {
    return this.fetch(`/api/workorders/${encodeURIComponent(woNumber)}/current-op`);
  },

  getWorkOrderTime(woNumber) {
    return this.fetch(`/api/workorders/${encodeURIComponent(woNumber)}/time`);
  },

  getDueThisWeek() {
    return this.fetch('/api/workorders/due-this-week');
  },

  getLateWorkOrders() {
    return this.fetch('/api/workorders/late');
  },

  getOpenCount() {
    return this.fetch('/api/workorders/count');
  },

  // Parts
  getParts() {
    return this.fetch('/api/parts');
  },

  getPart(partNumber) {
    return this.fetch(`/api/parts/${encodeURIComponent(partNumber)}`);
  },

  getPartOps(partNumber) {
    return this.fetch(`/api/parts/${encodeURIComponent(partNumber)}/ops`);
  },

  getPartOpDetail(partNumber, opNumber) {
    return this.fetch(`/api/parts/${encodeURIComponent(partNumber)}/ops/${encodeURIComponent(opNumber)}`);
  },

  // Dashboard (single fast endpoint)
  getDashboard() {
    return this.fetch('/api/dashboard');
  },

  // Search
  search(query) {
    return this.fetch(`/api/search?q=${encodeURIComponent(query)}`);
  },

  // Chat
  chat(message) {
    return this.fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },

  // Count Parts (Vision)
  countParts(imageDataUrl, context) {
    // Strip the data:image/jpeg;base64, prefix
    const base64 = imageDataUrl.includes(',') ? imageDataUrl.split(',')[1] : imageDataUrl;
    return this.fetch('/api/count-parts', {
      method: 'POST',
      body: JSON.stringify({ image_base64: base64, context: context || null }),
    });
  },
};
