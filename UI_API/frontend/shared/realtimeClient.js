// @ts-check

/** @typedef {import('../types.d.ts').RealtimeClient} RealtimeClient */
/** @typedef {import('../types.d.ts').RealtimeEvent} RealtimeEvent */
/** @typedef {import('../types.d.ts').RealtimeHandlers} RealtimeHandlers */
/** @typedef {(event: RealtimeEvent) => void} RealtimeEventHandler */

/**
 * @param {string} clientType
 * @param {string} sessionId
 * @param {RealtimeHandlers} [handlers]
 * @returns {RealtimeClient}
 */
export function createRealtimeClient(clientType, sessionId, handlers = {}) {
  /** @type {WebSocket | null} */
  let socket = null;
  let closedByUser = false;
  /** @type {number | null} */
  let reconnectTimer = null;

  const demoToken = () => {
    const params = new URLSearchParams(window.location.search || '');
    const key = clientType === 'admin' ? 'admin_demo_token' : 'pos_demo_token';
    if (clientType === 'admin') return '';
    const roleToken = params.get('kiosk_token') || params.get('pos_token');
    const token = roleToken || params.get('token') || params.get('ws_token') || sessionStorage.getItem(key) || '';
    if (token) sessionStorage.setItem(key, token);
    if (['token', 'admin_token', 'kiosk_token', 'pos_token', 'ws_token'].some(name => params.has(name))) {
      ['token', 'admin_token', 'kiosk_token', 'pos_token', 'ws_token'].forEach(name => params.delete(name));
      const query = params.toString();
      history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
    }
    return token;
  };

  const buildUrl = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:9000';
    const token = demoToken();
    const query = token ? `?token=${encodeURIComponent(token)}` : '';
    return `${protocol}//${host}/ws/${encodeURIComponent(clientType)}/${encodeURIComponent(sessionId || 'global')}${query}`;
  };

  const scheduleReconnect = () => {
    if (closedByUser || reconnectTimer) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      open();
    }, 2000);
  };

  /**
   * @param {unknown} event
   * @returns {void}
   */
  const dispatchEvent = (event) => {
    if (!event || typeof event !== 'object') return;
    const realtimeEvent = /** @type {RealtimeEvent} */ (event);
    const handler = handlers[realtimeEvent.type];
    if (typeof handler === 'function') {
      /** @type {RealtimeEventHandler} */ (handler)(realtimeEvent);
    }
    if (typeof handlers.message === 'function') handlers.message(realtimeEvent);
  };

  const open = () => {
    const currentSocket = new WebSocket(buildUrl());
    socket = currentSocket;
    currentSocket.onopen = () => {
      if (typeof handlers.open === 'function') handlers.open();
      try {
        currentSocket.send(JSON.stringify({ type: 'ping' }));
      } catch { }
    };
    currentSocket.onmessage = (message) => {
      try {
        /** @type {unknown} */
        const parsedEvent = JSON.parse(message.data);
        dispatchEvent(parsedEvent);
      } catch {
        if (typeof handlers.error === 'function') handlers.error(new Error('Invalid realtime JSON event'));
      }
    };
    currentSocket.onerror = (error) => {
      if (typeof handlers.error === 'function') handlers.error(error);
    };
    currentSocket.onclose = () => {
      if (typeof handlers.close === 'function') handlers.close();
      scheduleReconnect();
    };
  };

  open();

  return {
    send(payload = {}) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(payload));
      return true;
    },
    close() {
      closedByUser = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
      if (socket) socket.close();
    },
    get socket() {
      return socket;
    },
  };
}
