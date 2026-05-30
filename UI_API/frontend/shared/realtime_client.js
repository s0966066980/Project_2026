export function connectRealtime(clientType, sessionId, handlers = {}) {
  let socket = null;
  let closedByUser = false;
  let reconnectTimer = null;

  const demoToken = () => {
    const params = new URLSearchParams(window.location.search || '');
    const key = clientType === 'admin' ? 'admin_demo_token' : 'pos_demo_token';
    const token = params.get('token') || params.get('ws_token') || sessionStorage.getItem(key) || '';
    if (token) sessionStorage.setItem(key, token);
    return token;
  };

  const buildUrl = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || '127.0.0.1:8000';
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

  const dispatchEvent = (event) => {
    if (!event || typeof event !== 'object') return;
    const handler = handlers[event.type];
    if (typeof handler === 'function') handler(event);
    if (typeof handlers.message === 'function') handlers.message(event);
  };

  const open = () => {
    socket = new WebSocket(buildUrl());
    socket.onopen = () => {
      if (typeof handlers.open === 'function') handlers.open();
      try {
        socket.send(JSON.stringify({ type: 'ping' }));
      } catch { }
    };
    socket.onmessage = (message) => {
      try {
        dispatchEvent(JSON.parse(message.data));
      } catch {
        if (typeof handlers.error === 'function') handlers.error(new Error('Invalid realtime JSON event'));
      }
    };
    socket.onerror = (error) => {
      if (typeof handlers.error === 'function') handlers.error(error);
    };
    socket.onclose = () => {
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
