(function () {
  const scoreEl = document.getElementById("score");
  const timestampEl = document.getElementById("timestamp");
  const eventsEl = document.getElementById("events");
  const statusEl = document.getElementById("connection-status");
  const statusTextEl = statusEl ? statusEl.querySelector(".status-text") : null;

  let backendBase = null;
  let websocket = null;
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let sseSource = null;
  let pollTimer = null;
  let lastHeartbeat = Date.now();
  let fallbackMode = null;

  const HEARTBEAT_TIMEOUT = 25000;
  const RECONNECT_DELAYS = [1000, 2000, 5000, 10000];

  function setStatus(online) {
    if (!statusEl) {
      return;
    }
    statusEl.classList.toggle("status--online", Boolean(online));
    if (statusTextEl) {
      statusTextEl.textContent = online ? "En ligne" : "Hors ligne";
    }
  }

  function renderState(state) {
    if (!state) {
      return;
    }
    if (typeof state.score === "number") {
      scoreEl.textContent = Math.round(state.score).toString();
    }
    if (state.updated_at) {
      const date = new Date(state.updated_at * 1000);
      timestampEl.textContent = date.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    }

    const active = Array.isArray(state.active) ? state.active : [];
    if (!active.length) {
      eventsEl.innerHTML = "";
      eventsEl.style.display = "none";
      return;
    }

    eventsEl.style.display = "grid";
    eventsEl.innerHTML = "";

    active.slice(0, 5).forEach((item) => {
      const card = document.createElement("article");
      card.className = "event-card";

      const title = document.createElement("h2");
      title.className = "event-title";
      title.textContent = item.title || "Événement";
      card.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "event-meta";

      const source = document.createElement("span");
      source.className = "event-source";
      source.textContent = item.source || "N/A";

      const severity = document.createElement("span");
      severity.className = "event-severity";
      const contribution = typeof item.contribution === "number" ? Math.round(item.contribution) : 0;
      severity.textContent = `${contribution} pts`;

      meta.appendChild(source);
      meta.appendChild(severity);
      card.appendChild(meta);

      if (item.meta && item.meta.explanation) {
        const explanation = document.createElement("p");
        explanation.textContent = item.meta.explanation;
        card.appendChild(explanation);
      }

      eventsEl.appendChild(card);
    });
  }

  function handleRealtimeMessage(message) {
    if (!message) {
      return;
    }
    if (message.type === "heartbeat") {
      lastHeartbeat = Date.now();
      return;
    }
    if (message.type === "score_update") {
      lastHeartbeat = Date.now();
      setStatus(true);
      renderState(message.payload || {});
    }
  }

  function scheduleReconnect() {
    if (fallbackMode) {
      return;
    }
    const delay = RECONNECT_DELAYS[Math.min(reconnectAttempts, RECONNECT_DELAYS.length - 1)] || 10000;
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
    }
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      reconnectAttempts += 1;
      if (reconnectAttempts >= 3) {
        startSSE();
        return;
      }
      connectWebSocket();
    }, delay);
  }

  function connectWebSocket() {
    if (!backendBase) {
      return;
    }
    if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const protocol = backendBase.startsWith("https") ? "wss" : "ws";
    const wsUrl = `${backendBase.replace(/^http/, protocol)}/ws`;
    try {
      websocket = new WebSocket(wsUrl);
    } catch (err) {
      console.warn("WebSocket init failed", err);
      scheduleReconnect();
      return;
    }

    websocket.addEventListener("open", () => {
      reconnectAttempts = 0;
      lastHeartbeat = Date.now();
      setStatus(true);
    });

    websocket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        handleRealtimeMessage(data);
      } catch (error) {
        console.error("Invalid WebSocket payload", error);
      }
    });

    websocket.addEventListener("close", () => {
      setStatus(false);
      scheduleReconnect();
    });

    websocket.addEventListener("error", () => {
      try {
        websocket.close();
      } catch (err) {
        console.debug("WebSocket close error", err);
      }
    });
  }

  function startSSE() {
    if (!backendBase || fallbackMode) {
      return;
    }
    fallbackMode = "sse";
    if (websocket) {
      try {
        websocket.close();
      } catch (_) {
        // ignore
      }
      websocket = null;
    }
    const url = `${backendBase}/sse`;
    sseSource = new EventSource(url, { withCredentials: false });
    sseSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleRealtimeMessage(data);
      } catch (error) {
        console.error("Invalid SSE payload", error);
      }
    };
    sseSource.onerror = () => {
      console.warn("SSE déconnecté, fallback polling");
      if (sseSource) {
        sseSource.close();
        sseSource = null;
      }
      startPolling();
    };
  }

  function startPolling() {
    if (!backendBase) {
      return;
    }
    fallbackMode = "poll";
    if (sseSource) {
      sseSource.close();
      sseSource = null;
    }
    if (pollTimer) {
      window.clearInterval(pollTimer);
    }
    pollTimer = window.setInterval(async () => {
      try {
        const response = await fetch(`${backendBase}/api/score`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        lastHeartbeat = Date.now();
        setStatus(true);
        renderState(data);
      } catch (error) {
        console.error("Polling error", error);
        setStatus(false);
      }
    }, 1000);
  }

  async function detectBackendBase() {
    const host = window.location.hostname || "localhost";
    const protocol = window.location.protocol.startsWith("https") ? "https" : "http";
    const pagePort = window.location.port;
    const candidates = [];
    if (pagePort) {
      candidates.push({ protocol, port: pagePort });
    }
    ["8000", "8001", "8080", "8081"].forEach((port) => {
      if (!candidates.find((entry) => entry.port === port)) {
        candidates.push({ protocol, port });
      }
    });

    for (const candidate of candidates) {
      const base = `${candidate.protocol}://${host}${candidate.port ? `:${candidate.port}` : ""}`;
      const ok = await pingBackend(base);
      if (ok) {
        return base;
      }
    }
    return `${protocol}://${host}:8000`;
  }

  async function pingBackend(base) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 1500);
    try {
      const response = await fetch(`${base}/health`, {
        cache: "no-store",
        mode: "cors",
        signal: controller.signal,
      });
      return response.ok;
    } catch (error) {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function startHeartbeatMonitor() {
    window.setInterval(() => {
      if (Date.now() - lastHeartbeat > HEARTBEAT_TIMEOUT) {
        setStatus(false);
      }
    }, 5000);
  }

  async function init() {
    backendBase = await detectBackendBase();
    connectWebSocket();
    startHeartbeatMonitor();
  }

  window.addEventListener("load", init);
})();
