(function () {
  const scoreEl = document.getElementById("score");
  const timestampEl = document.getElementById("timestamp");
  const eventsEl = document.getElementById("events");

  function renderState(state) {
    scoreEl.textContent = Math.round(state.score).toString();
    if (state.updated_at) {
      const date = new Date(state.updated_at * 1000);
      timestampEl.textContent = date.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } else {
      timestampEl.textContent = "";
    }

    eventsEl.innerHTML = "";
    const active = state.active || [];
    if (!active.length) {
      eventsEl.style.display = "none";
      return;
    }
    eventsEl.style.display = "grid";

    active.slice(0, 5).forEach((item) => {
      const card = document.createElement("article");
      card.className = "event-card";

      const title = document.createElement("h2");
      title.className = "event-title";
      title.textContent = item.title;
      card.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "event-meta";

      const source = document.createElement("span");
      source.className = "event-source";
      source.textContent = item.source;

      const severity = document.createElement("span");
      severity.className = "event-severity";
      severity.textContent = `${Math.round(item.contribution)} pts`;

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

  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);

    socket.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        renderState(data);
      } catch (error) {
        console.error("Invalid payload", error);
      }
    });

    socket.addEventListener("close", () => {
      setTimeout(connect, 2000);
    });

    socket.addEventListener("error", () => {
      socket.close();
    });
  }

  connect();
})();
