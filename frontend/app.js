/* =========================================================
   DEBATE ARENA — pixel-art front end
   - Builds two SVG pixel characters (Valentina / Bruno)
   - Animates them while their tokens stream in
   - Keeps the original WebSocket / REST contract untouched
   ========================================================= */

const AGENT_IDS = ["agent1", "agent2"];

const state = {
  ws: null,
  activeBubble: null,
  activeAgent: null,
  running: false,
  agentMap: null,
};

const graphState = {
  rendered: false,
  activeNode: null,
  visitedNodes: new Set(),
  nodeEls: {},
};

/* =========================================================
   PIXEL CHARACTER BUILDER
   16 x 24 logical pixels, rendered as SVG <rect>s.
   Parts are grouped so CSS can animate them independently.
   ========================================================= */

const PALETTES = {
  moderator: {
    hair: "#3a2818", hairHi: "#5a3418",
    skin: "#f0c090", skinDk: "#c89868",
    eye: "#1a1226", brow: "#3a2818", mouth: "#5a1a14",
    shirt: "#d9a558", shirtDk: "#8a5e22",
    pants: "#3a2818", pantsDk: "#1a1008",
    belt: "#1a0a05", boot: "#1a0a05",
    accent: "#2f6a1a",
  },
  maximo: {
    hair:    "#1a0f0a",
    hairHi:  "#3a2818",
    skin:    "#f0c090",
    skinDk:  "#c89868",
    eye:     "#1a1226",
    brow:    "#1a0f0a",
    mouth:   "#5a1a14",
    shirt:   "#c0392b",
    shirtDk: "#8a1f15",
    pants:   "#2c3e60",
    pantsDk: "#1a2848",
    belt:    "#1a0a05",
    boot:    "#1a0a05",
    accent:  "#f0c060", // bandana / armband
  },
  libertad: {
    hair:    "#e8c060",
    hairHi:  "#fbe098",
    skin:    "#f0c090",
    skinDk:  "#c89868",
    eye:     "#1a1226",
    brow:    "#8a6020",
    mouth:   "#5a1a14",
    shirt:   "#2980b9",
    shirtDk: "#1a5a90",
    pants:   "#1a2438",
    pantsDk: "#0a121f",
    belt:    "#1a0a05",
    boot:    "#1a0a05",
    accent:  "#c0392b", // tie
  },
  valentina: {
    hair:    "#2a1240",
    hairHi:  "#4a2068",
    skin:    "#f5cba0",
    skinDk:  "#cfa078",
    eye:     "#1a1226",
    brow:    "#2a1240",
    mouth:   "#5a1a14",
    shirt:   "#7c3aed", // violeta eléctrico
    shirtDk: "#4a1f9e",
    pants:   "#1a1226",
    pantsDk: "#0a0612",
    belt:    "#1a0a05",
    boot:    "#1a0a05",
    accent:  "#22d3ee", // cyan tech
  },
  bruno: {
    hair:    "#2a1808",
    hairHi:  "#4a2818",
    skin:    "#e8b878",
    skinDk:  "#c08858",
    eye:     "#1a1226",
    brow:    "#2a1808",
    mouth:   "#5a1a14",
    shirt:   "#059669", // verde bosque
    shirtDk: "#03704c",
    pants:   "#1a2818",
    pantsDk: "#0a1408",
    belt:    "#1a0a05",
    boot:    "#1a0a05",
    accent:  "#fbbf24", // dorado cálido
  },
};

/**
 * Build the SVG markup for a character.
 * The viewBox is 16x26; a leg/foot row reaches y=25.
 */
function buildCharacterSVG(p, kind) {
  // helper to emit a colored rect
  const r = (x, y, w, h, fill) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"/>`;

  // ----- HEAD GROUP -----
  let head = "";
  // hair back / cap shape
  head += r(4, 0, 8, 1, p.hair);
  head += r(3, 1, 10, 2, p.hair);
  // hair highlight strand
  head += r(5, 1, 2, 1, p.hairHi);
  if (kind === "libertad") head += r(10, 2, 2, 1, p.hairHi);

  // face base
  head += r(4, 3, 8, 4, p.skin);
  // ear shadows
  head += r(3, 4, 1, 2, p.skinDk);
  head += r(12, 4, 1, 2, p.skinDk);
  // jaw / chin shadow
  head += r(4, 7, 8, 1, p.skinDk);

  // hair fringe
  if (kind === "maximo") {
    head += r(4, 3, 4, 1, p.hair);   // left side bang
    head += r(10, 3, 2, 1, p.hair);
  } else {
    head += r(4, 3, 3, 1, p.hair);   // combed-over bang
    head += r(11, 3, 1, 1, p.hair);
  }

  // eyebrows
  head += r(5, 4, 2, 1, p.brow);
  head += r(9, 4, 2, 1, p.brow);

  // eyes
  head += r(6, 5, 1, 1, p.eye);
  head += r(9, 5, 1, 1, p.eye);

  // nose dot
  head += r(8, 6, 1, 1, p.skinDk);

  // mouth (animated)
  const mouth =
    `<rect class="mouth" x="7" y="7" width="2" height="2" fill="${p.mouth}"/>`;

  // neck
  head += r(7, 8, 2, 1, p.skinDk);

  // ----- BODY (shirt / suit) -----
  let body = "";
  body += r(4, 9, 8, 5, p.shirt);
  // shirt shadow underline
  body += r(4, 13, 8, 1, p.shirtDk);
  // belt
  body += r(4, 14, 8, 1, p.belt);

  if (kind === "maximo") {
    // bandana / armband on chest
    body += r(4, 10, 8, 1, p.accent);
  } else {
    // collar V
    body += r(7, 9, 1, 1, "#fff");
    body += r(8, 9, 1, 1, "#fff");
    // tie
    body += r(7, 10, 2, 3, p.accent);
    body += r(7, 13, 2, 1, "#8a1f15");
  }

  // ----- LEFT ARM (anatomical right — appears on viewer's left) -----
  // Group separately for rotation
  const armL =
    r(3, 9, 1, 4, p.shirt) +
    r(3, 12, 1, 1, p.shirtDk) +
    r(3, 13, 1, 1, p.skin);     // hand

  // ----- RIGHT ARM -----
  // For Máximo: raised fist (slightly higher hand). For Libertad: pointing up.
  let armR = "";
  if (kind === "maximo") {
    armR += r(12, 9, 1, 4, p.shirt);
    armR += r(12, 12, 1, 1, p.shirtDk);
    armR += r(12, 13, 1, 1, p.skin); // hand
  } else {
    armR += r(12, 9, 1, 4, p.shirt);
    armR += r(12, 12, 1, 1, p.shirtDk);
    armR += r(12, 13, 1, 1, p.skin);
  }

  // ----- LEGS / FEET -----
  let legs = "";
  legs += r(4, 15, 3, 6, p.pants);
  legs += r(9, 15, 3, 6, p.pants);
  // pants shadow
  legs += r(4, 20, 3, 1, p.pantsDk);
  legs += r(9, 20, 3, 1, p.pantsDk);
  // boots
  legs += r(3, 21, 4, 2, p.boot);
  legs += r(9, 21, 4, 2, p.boot);
  // boot highlight
  legs += r(3, 21, 4, 1, "#3a2418");
  legs += r(9, 21, 4, 1, "#3a2418");

  return `
    <svg class="character-svg" viewBox="0 0 16 24"
         xmlns="http://www.w3.org/2000/svg"
         shape-rendering="crispEdges"
         preserveAspectRatio="xMidYMax meet">
      <g class="legs">${legs}</g>
      <g class="arm-l">${armL}</g>
      <g class="body">${body}</g>
      <g class="head">
        ${head}
        ${mouth}
      </g>
      <g class="arm-r">${armR}</g>
    </svg>
  `;
}

function mountCharacters() {
  const c1 = document.getElementById("char-agent1");
  const c2 = document.getElementById("char-agent2");
  const cm = document.getElementById("char-moderator");
  // 2do arg: pose-kind (puño / dedo / neutral). Reusamos las poses heredadas.
  if (c1) c1.innerHTML = buildCharacterSVG(PALETTES.valentina, "maximo");
  if (c2) c2.innerHTML = buildCharacterSVG(PALETTES.bruno, "libertad");
  if (cm) cm.innerHTML = buildCharacterSVG(PALETTES.moderator, "moderator");
}

/* =========================================================
   DOM refs
   ========================================================= */
const btnStart  = document.getElementById("btn-start");
const btnStop   = document.getElementById("btn-stop");
const statusBar = document.getElementById("status-bar");

/* =========================================================
   Available models (uses your existing /api/models endpoint)
   ========================================================= */
async function loadModels() {
  try {
    const res = await fetch("/api/models");
    const { models } = await res.json();
    const sel = document.getElementById("model");
    if (models && models.length > 0) {
      sel.innerHTML = models
        .map(m => `<option value="${m}">${m}</option>`)
        .join("");
    }
  } catch {
    /* silent — keep default */
  }
}

/* =========================================================
   UI helpers
   ========================================================= */
function setStatus(msg) {
  statusBar.textContent = "▸ " + msg.toUpperCase();
}

function setAgentStatus(slotId, msg) {
  document.getElementById(`status-${slotId}`).textContent = msg;
}

function clearAllStatuses() {
  AGENT_IDS.forEach(id => setAgentStatus(id, ""));
}

function setCharacterTalking(slotId, talking) {
  const c = document.getElementById(`char-${slotId}`);
  if (c) c.classList.toggle("talking", talking);
}

function clearAllTalking() {
  AGENT_IDS.forEach(id => setCharacterTalking(id, false));
}

function setRunning(running) {
  state.running = running;
  btnStart.disabled = running;
  btnStop.disabled  = !running;
  document.getElementById("topic").disabled     = running;
  document.getElementById("max_turns").disabled = running;
  document.getElementById("max_words").disabled = running;
  document.getElementById("model").disabled     = running;
}

function clearArena() {
  document.getElementById("bubble-agent1").innerHTML = "";
  document.getElementById("bubble-agent2").innerHTML = "";
  clearAllStatuses();
  clearAllTalking();
  state.activeBubble = null;
  state.activeAgent  = null;
}

function agentColumnId(agentId) {
  return state.agentMap?.[agentId] ?? "agent1";
}

/* =========================================================
   Bubble management — visual-novel style: latest message only
   ========================================================= */
function createBubble(slotId, agentId) {
  const anchor = document.getElementById(`bubble-${slotId}`);
  anchor.innerHTML = "";

  const bubble = document.createElement("div");
  bubble.className = `bubble ${slotId} active`;
  bubble.dataset.agentId = agentId;

  const text = document.createElement("span");
  text.className = "bubble-text";
  bubble.appendChild(text);

  const caret = document.createElement("span");
  caret.className = "caret";
  bubble.appendChild(caret);

  anchor.appendChild(bubble);
  return bubble;
}

function appendToken(bubble, token) {
  const text = bubble.querySelector(".bubble-text");
  text.textContent += token;
  // auto-scroll inside bubble if it overflows
  bubble.scrollTop = bubble.scrollHeight;
}

function finalizeBubble(bubble) {
  bubble.classList.remove("active");
  const caret = bubble.querySelector(".caret");
  if (caret) caret.remove();
}

/* =========================================================
   WebSocket
   ========================================================= */
function connect() {
  const wsUrl = `ws://${location.host}/ws`;
  state.ws = new WebSocket(wsUrl);

  state.ws.onopen  = () => setStatus("Conectado. Iniciando debate...");
  state.ws.onclose = () => {
    setStatus("Desconectado.");
    setRunning(false);
    clearAllTalking();
  };
  state.ws.onerror = () => setStatus("Error de conexión.");

  state.ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  };
}

function handleMessage(msg) {
  switch (msg.type) {
    case "scouting_start": {
      setStatus("▸ Analizando tema y preparando contexto…");
      setAgentStatus("moderator", "scouting...");
      break;
    }

    case "scouting_completed": {
      const concepts = (msg.key_concepts || []).slice(0, 3).join(" • ");
      if (concepts) {
        setStatus(`▸ Contexto listo: ${concepts}`);
      } else {
        setStatus("▸ Contexto listo.");
      }
      setAgentStatus("moderator", "");
      break;
    }

    case "tool_call_start": {
      const toolLabel = msg.tool === "web_search" ? "buscando en web" : `usando ${msg.tool}`;
      setStatus(`🔍 ${toolLabel}…`);
      setAgentStatus("moderator", "buscando...");
      break;
    }

    case "tool_call_end": {
      if (msg.success) {
        setStatus(`🔍 ${msg.tool}: OK (${msg.latency_ms || 0}ms)`);
      } else {
        setStatus(`🔍 ${msg.tool}: ${msg.error || "sin resultados"}`);
      }
      setAgentStatus("moderator", "");
      break;
    }

    case "agent_planning": {
      const slot = agentColumnId(msg.agent);
      if (msg.phase === "start") {
        setAgentStatus(slot, "pensando...");
        const displayName = document.getElementById(`name-${slot}`)?.textContent || msg.agent;
        setStatus(`${displayName} está pensando...`);
      } else {
        // 'end': el speak inmediatamente despues va a setear "hablando..."
        setAgentStatus(slot, "");
      }
      break;
    }

    case "moderator_evaluating": {
      // El moderador empezo a evaluar el ultimo turno (puede tardar 30-90s con 1b)
      setAgentStatus("moderator", "evaluando...");
      setStatus("⚖ Moderador evaluando el turno…");
      break;
    }

    case "moderator_evaluation": {
      const slot = agentColumnId(msg.agent);
      const total = (msg.score && typeof msg.score.total === "number") ? msg.score.total : null;
      if (total !== null) {
        const el = document.getElementById(`score-${slot}`);
        if (el) {
          const last = (total).toFixed(2);
          el.dataset.last = last;
          el.classList.remove("last-low", "last-mid", "last-high");
          el.classList.add(total < 0.5 ? "last-low" : total < 0.75 ? "last-mid" : "last-high");
          // mostramos: turno (last) | acumulado se setea en score_update
          const cum = el.dataset.cum || "0.00";
          el.textContent = `★ ${cum}  (turno ${last})`;
        }
      }
      setAgentStatus("moderator", "evaluando...");
      break;
    }

    case "score_update": {
      const scores = msg.scores || {};
      Object.entries(scores).forEach(([agentId, value]) => {
        const slot = agentColumnId(agentId);
        const el = document.getElementById(`score-${slot}`);
        if (el) {
          const cum = Number(value).toFixed(2);
          el.dataset.cum = cum;
          const last = el.dataset.last || "—";
          el.textContent = `★ ${cum}  (turno ${last})`;
        }
      });
      setAgentStatus("moderator", "");
      break;
    }

    case "warning": {
      const sev = msg.severity ? `[${msg.severity}]` : "";
      setStatus(`⚠ ${sev} ${msg.message || msg.code || "advertencia del moderador"}`);
      break;
    }

    case "moderator_intervention_pending": {
      // El moderador decidio intervenir â viene un turno hablado
      const sev = (msg.severity || "warning").toUpperCase();
      const reason = msg.reason || "moderation";
      setStatus(`⚖ Intervención del moderador (${sev} • ${reason})…`);
      break;
    }

    case "moderator_intervention": {
      if (msg.phase === "start") {
        const sev = (msg.severity || "warning").toUpperCase();
        setStatus(`⚖ Moderador interviene [${sev}]…`);
      } else if (msg.phase === "end") {
        // el turn_end del moderador ya limpio la burbuja; aca solo dejamos rastro
        setStatus("⚖ Intervención del moderador finalizada.");
      }
      break;
    }

    case "summary_start": {
      setStatus("▸ Generando resumen del debate…");
      setAgentStatus("moderator", "resumiendo...");
      break;
    }

    case "debate_summary": {
      renderSummaryPanel(msg);
      setAgentStatus("moderator", "");
      break;
    }

    case "turn_start": {
      const slot = agentColumnId(msg.agent);
      // make the OTHER one stop talking
      AGENT_IDS.forEach(id => setCharacterTalking(id, id === slot));
      state.activeAgent  = msg.agent;
      state.activeBubble = createBubble(slot, msg.agent);
      const displayName = document.getElementById(`name-${slot}`).textContent;
      setAgentStatus(slot, "pensando...");
      setStatus(`${displayName} está respondiendo...`);
      break;
    }

    case "token": {
      if (state.activeBubble && state.activeAgent === msg.agent) {
        appendToken(state.activeBubble, msg.content);
        const slot = agentColumnId(msg.agent);
        setAgentStatus(slot, "hablando...");
        setCharacterTalking(slot, true);
      }
      break;
    }

    case "turn_end": {
      if (state.activeBubble) {
        finalizeBubble(state.activeBubble);
        state.activeBubble = null;
      }
      const slot = agentColumnId(msg.agent);
      setAgentStatus(slot, "");
      setCharacterTalking(slot, false);
      break;
    }

    case "conversation_end": {
      setStatus("Debate finalizado.");
      setRunning(false);
      clearAllStatuses();
      clearAllTalking();
      break;
    }

    case "node_active": {
      graphState.activeNode = msg.node;
      graphState.visitedNodes.add(msg.node);
      const gp = document.getElementById("graph-panel");
      if (gp && !gp.classList.contains("hidden") && graphState.rendered) {
        applyGraphHighlights();
      }
      break;
    }

    case "error": {
      setStatus(`Error: ${msg.message}`);
      setRunning(false);
      clearAllTalking();
      break;
    }
  }
}

/* =========================================================
   Graph panel
   ========================================================= */
function buildNodeIndex() {
  graphState.nodeEls = {};
  document.querySelectorAll("#graph-mermaid g.node").forEach(el => {
    const id = el.getAttribute("id") || "";
    let name = "";
    // Mermaid ≥10 generates IDs like "flowchart-scout-0" or "L-scout-0"
    const m = id.match(/(?:flowchart-|L-)([a-zA-Z_][a-zA-Z0-9_]*)-\d+/);
    if (m) {
      name = m[1].toLowerCase();
    } else {
      const textEl = el.querySelector("span, foreignObject span, text, p");
      name = (textEl?.textContent || "").trim().toLowerCase().replace(/\s+/g, "_");
    }
    if (name && !name.startsWith("__")) {
      graphState.nodeEls[name] = el;
    }
  });
}

function applyGraphHighlights() {
  Object.values(graphState.nodeEls).forEach(el => {
    el.classList.remove("node-active", "node-visited");
  });
  graphState.visitedNodes.forEach(name => {
    if (name !== graphState.activeNode) {
      const el = graphState.nodeEls[name];
      if (el) el.classList.add("node-visited");
    }
  });
  if (graphState.activeNode) {
    const el = graphState.nodeEls[graphState.activeNode];
    if (el) el.classList.add("node-active");
  }
}

async function openGraphPanel() {
  const panel = document.getElementById("graph-panel");
  if (!panel) return;
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");

  if (graphState.rendered) {
    applyGraphHighlights();
    return;
  }

  const container = document.getElementById("graph-mermaid");
  container.textContent = "Cargando...";

  try {
    const res = await fetch("/api/graph/diagram");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const { mermaid: mermaidText } = await res.json();

    mermaid.initialize({
      startOnLoad: false,
      theme: "base",
      themeVariables: {
        background: "#050610",
        primaryColor: "#1a0f08",
        primaryBorderColor: "#d9a558",
        primaryTextColor: "#f0c060",
        lineColor: "#5a3418",
        fontSize: "11px",
      },
    });

    const { svg } = await mermaid.render("debate-flow-graph", mermaidText);
    container.innerHTML = svg;
    graphState.rendered = true;
    buildNodeIndex();
    applyGraphHighlights();
  } catch (e) {
    container.innerHTML = `<span style="color:#ff8a6a">Error: ${e.message}</span>`;
  }
}

function hideGraphPanel() {
  const panel = document.getElementById("graph-panel");
  if (panel) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
}

/* =========================================================
   Start / Stop
   ========================================================= */
function startDebate() {
  graphState.activeNode = null;
  graphState.visitedNodes.clear();
  if (graphState.rendered) applyGraphHighlights();
  clearArena();
  hideSummaryPanel();

  const topic    = document.getElementById("topic").value.trim()
                || "el rol del Estado en la economía";
  const maxTurns = parseInt(document.getElementById("max_turns").value, 10);
  const maxWords = parseInt(document.getElementById("max_words").value, 10);
  const model    = document.getElementById("model").value;

  state.agentMap = {
    valentina: "agent1",
    bruno:     "agent2",
    moderator: "moderator",
  };

  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    connect();
    state.ws.addEventListener("open", () => {
      sendStart({ topic, maxTurns, maxWords, model });
    }, { once: true });
  } else {
    sendStart({ topic, maxTurns, maxWords, model });
  }

  setRunning(true);
  setStatus("Conectando...");
}

/* =========================================================
   Summary panel rendering
   ========================================================= */
function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function displayNameForAgent(agentId) {
  const slot = state.agentMap?.[agentId];
  if (slot) {
    const el = document.getElementById(`name-${slot}`);
    if (el) return el.textContent;
  }
  return agentId || "—";
}

function renderSummaryPanel(payload) {
  const panel    = document.getElementById("summary-panel");
  const verdict  = document.getElementById("summary-verdict");
  const scoresEl = document.getElementById("summary-scores");
  const overall  = document.getElementById("summary-overall");
  const agentsEl = document.getElementById("summary-agents");
  const momentsEl = document.getElementById("summary-key-moments");
  if (!panel) return;

  const winner = payload.winner_id;
  const verdictText = payload.verdict || "";
  verdict.innerHTML = winner
    ? `🏆 <strong>${escapeHtml(displayNameForAgent(winner))}</strong> — ${escapeHtml(verdictText)}`
    : `⚖ ${escapeHtml(verdictText || "Empate")}`;

  // scores
  const scores = payload.cumulative_scores || {};
  scoresEl.innerHTML = Object.entries(scores)
    .map(([aid, val]) => {
      const slot = state.agentMap?.[aid] || "";
      const winnerCls = aid === winner ? "winner" : "";
      const color = slot === "agent1" ? "#7c3aed"
                  : slot === "agent2" ? "#059669"
                  : "#d9a558";
      return `<span class="summary-score-pill ${winnerCls}" style="color:${color}">
                ${escapeHtml(displayNameForAgent(aid))} ★ ${Number(val).toFixed(2)}
              </span>`;
    })
    .join("");

  // overall narrative
  const narrative = payload.narrative || {};
  overall.textContent = narrative.overall || "(sin narrativa disponible)";

  // per-agent assessments
  const perAgent = narrative.per_agent || {};
  agentsEl.innerHTML = Object.entries(perAgent)
    .map(([aid, blk]) => {
      const highlights = (blk?.highlights || []).map(h => `<li>${escapeHtml(h)}</li>`).join("");
      const weaknesses = (blk?.weaknesses || []).map(w => `<li>${escapeHtml(w)}</li>`).join("");
      return `
        <div class="summary-agent-block">
          <h4>${escapeHtml(displayNameForAgent(aid))}</h4>
          ${highlights ? `<div class="label">Fortalezas</div><ul>${highlights}</ul>` : ""}
          ${weaknesses ? `<div class="label">Debilidades</div><ul>${weaknesses}</ul>` : ""}
        </div>
      `;
    })
    .join("");

  // key moments
  const moments = (narrative.key_moments || []).map(m => `<li>${escapeHtml(m)}</li>`).join("");
  momentsEl.innerHTML = moments
    ? `<h4>Momentos clave</h4><ul>${moments}</ul>`
    : "";

  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
}

function hideSummaryPanel() {
  const panel = document.getElementById("summary-panel");
  if (panel) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
}

function sendStart({ topic, maxTurns, maxWords, model }) {
  state.ws.send(JSON.stringify({
    type: "start",
    topic,
    max_turns: maxTurns,
    max_words: maxWords,
    agent1_id: "valentina",
    agent2_id: "bruno",
    model,
  }));
}

function stopDebate() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: "stop" }));
  }
  if (state.activeBubble) {
    finalizeBubble(state.activeBubble);
    state.activeBubble = null;
  }
  setRunning(false);
  clearAllStatuses();
  clearAllTalking();
  setStatus("Debate detenido.");
}

/* =========================================================
   Demo / preview mode — when there's no backend, run a fake
   conversation so the UI is visible standalone. Trigger by
   ?demo=1 in the URL, or auto-fallback if /api/models 404s.
   ========================================================= */
function runDemo() {
  state.agentMap = { valentina: "agent1", bruno: "agent2" };
  setRunning(true);

  const script = [
    { agent: "valentina", text: "El progreso tecnológico acelerado es nuestra mejor apuesta: frenar la IA hoy es condenar el futuro." },
    { agent: "bruno",     text: "Cada gran tecnología prometió liberar y terminó concentrando poder. La pregunta es quién decide." },
    { agent: "valentina", text: "Regular antes de entender es captura de incumbentes disfrazada de prudencia." },
    { agent: "bruno",     text: "La explicabilidad y la auditoría no son frenos: son la base de cualquier sistema legítimo." },
  ];

  let i = 0;
  const next = () => {
    if (i >= script.length) {
      handleMessage({ type: "conversation_end" });
      return;
    }
    const { agent, text } = script[i++];
    handleMessage({ type: "turn_start", agent });
    let pos = 0;
    const stream = setInterval(() => {
      if (pos >= text.length) {
        clearInterval(stream);
        handleMessage({ type: "turn_end", agent });
        setTimeout(next, 600);
        return;
      }
      handleMessage({ type: "token", agent, content: text[pos++] });
    }, 35);
  };
  next();
}

/* =========================================================
   Init
   ========================================================= */
/* =========================================================
   History panel (list + detail)
   ========================================================= */
async function openHistory() {
  const panel = document.getElementById("history-panel");
  const list  = document.getElementById("history-list");
  if (!panel || !list) return;

  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
  list.textContent = "Cargando...";

  try {
    const res = await fetch("/api/debates?limit=50");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const { debates } = await res.json();

    if (!debates || !debates.length) {
      list.innerHTML = '<div class="history-empty">Todavía no hay debates registrados.</div>';
      return;
    }

    list.innerHTML = debates.map(d => {
      const started = (d.started_at || "").replace("T", " ").slice(0, 16);
      const status = d.status || "?";
      const winnerLabel = d.winner_id
        ? `🏆 ${escapeHtml(d.winner_id)}`
        : (status === "completed" ? "⚖ empate" : "—");
      const statusCls = status === "completed" ? "" : "stopped";
      return `
        <div class="history-item" data-id="${escapeHtml(d.id)}">
          <div class="topic">${escapeHtml(d.topic || "(sin tema)")}</div>
          <div class="meta">
            <span>${escapeHtml(started)}</span>
            <span>${escapeHtml(d.agent1_id)} vs ${escapeHtml(d.agent2_id)}</span>
            <span>${escapeHtml(d.model || "?")}</span>
            <span class="${statusCls}">${escapeHtml(status)}</span>
            <span class="winner">${winnerLabel}</span>
          </div>
        </div>
      `;
    }).join("");

    list.querySelectorAll(".history-item").forEach(el => {
      el.addEventListener("click", () => openDetail(el.dataset.id));
    });
  } catch (e) {
    list.innerHTML = `<div class="history-empty">Error: ${escapeHtml(e.message)}</div>`;
  }
}

function hideHistory() {
  const panel = document.getElementById("history-panel");
  if (panel) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
}

let _currentDetailId = null;

async function openDetail(debateId) {
  const panel = document.getElementById("detail-panel");
  if (!panel) return;
  _currentDetailId = debateId;

  hideHistory();
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");

  const titleEl  = document.getElementById("detail-title");
  const metaEl   = document.getElementById("detail-meta");
  const verdictEl = document.getElementById("detail-verdict");
  const scoresEl = document.getElementById("detail-scores");
  const overallEl = document.getElementById("detail-overall");
  const turnsEl  = document.getElementById("detail-turns");
  const intervEl = document.getElementById("detail-interventions");

  titleEl.textContent = "Cargando...";
  metaEl.innerHTML = verdictEl.innerHTML = scoresEl.innerHTML = overallEl.innerHTML = "";
  turnsEl.innerHTML = intervEl.innerHTML = "";

  try {
    const res = await fetch(`/api/debates/${debateId}/full`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();

    titleEl.textContent = data.topic || "(sin tema)";

    const started = (data.started_at || "").replace("T", " ").slice(0, 16);
    metaEl.innerHTML = [
      `<span>${escapeHtml(started)}</span>`,
      `<span>${escapeHtml(data.agent1_id)} vs ${escapeHtml(data.agent2_id)}</span>`,
      `<span>modelo: ${escapeHtml(data.model || "?")}</span>`,
      `<span>turnos: ${data.turns?.length || 0}</span>`,
      `<span>estado: ${escapeHtml(data.status || "?")}</span>`,
    ].join("");

    const summary = data.summary || {};
    const cumulative = summary.cumulative_scores || {};
    const winner = data.winner_id || summary.winner_id;

    verdictEl.innerHTML = winner
      ? `🏆 <strong>${escapeHtml(winner)}</strong> — ${escapeHtml(summary.verdict || "")}`
      : `⚖ ${escapeHtml(summary.verdict || (data.status === "completed" ? "Empate" : "Debate incompleto"))}`;

    scoresEl.innerHTML = Object.entries(cumulative).map(([aid, val]) => {
      const winnerCls = aid === winner ? "winner" : "";
      const color = aid === data.agent1_id ? "#7c3aed"
                  : aid === data.agent2_id ? "#059669"
                  : "#d9a558";
      return `<span class="summary-score-pill ${winnerCls}" style="color:${color}">
                ${escapeHtml(aid)} ★ ${Number(val).toFixed(2)}
              </span>`;
    }).join("");

    if (summary.narrative?.overall) {
      overallEl.textContent = summary.narrative.overall;
    }

    // turnos en orden, mezclados con interventions por turn_number
    const turns = data.turns || [];
    const interventions = data.interventions || [];
    const events = [];
    for (const t of turns) {
      events.push({ kind: "turn", turn_number: t.turn_number, payload: t });
      const matching = interventions.filter(i => i.turn_number === t.turn_number);
      for (const i of matching) events.push({ kind: "intervention", payload: i });
    }

    turnsEl.innerHTML = events.map(ev => {
      if (ev.kind === "turn") {
        const t = ev.payload;
        const slot = state.agentMap?.[t.agent_id]
                    || (t.agent_id === data.agent1_id ? "agent1"
                       : t.agent_id === data.agent2_id ? "agent2" : "");
        const score = t.evaluation?.total != null
          ? `★ ${Number(t.evaluation.total).toFixed(2)}`
          : "";
        return `
          <div class="detail-turn ${slot}">
            <div class="turn-head">
              <span>#${t.turn_number} · ${escapeHtml(t.agent_id)}</span>
              <span>${score}</span>
            </div>
            <div class="turn-text">${escapeHtml(t.response_text || "")}</div>
          </div>
        `;
      } else {
        const i = ev.payload;
        return `
          <div class="detail-turn moderator">
            <div class="turn-head">
              <span><span class="sev">[${escapeHtml((i.severity || "").toUpperCase())}]</span> moderador · turno ${i.turn_number}</span>
              <span>${escapeHtml(i.reason || "")}</span>
            </div>
            <div class="turn-text">${escapeHtml(i.message || "")}</div>
          </div>
        `;
      }
    }).join("") || '<div class="history-empty">Sin turnos registrados.</div>';

    intervEl.innerHTML = "";

  } catch (e) {
    titleEl.textContent = `Error: ${e.message}`;
  }
}

function hideDetail() {
  const panel = document.getElementById("detail-panel");
  if (panel) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
  _currentDetailId = null;
}

function exportCurrentDetail() {
  if (!_currentDetailId) return;
  // navegamos a la URL del export para que el browser dispare la descarga
  window.location.href = `/api/debates/${_currentDetailId}/export`;
}

btnStart.addEventListener("click", startDebate);
btnStop.addEventListener("click", stopDebate);

const btnHistory = document.getElementById("btn-history");
if (btnHistory) btnHistory.addEventListener("click", openHistory);

const historyCloseBtn = document.getElementById("history-close");
if (historyCloseBtn) historyCloseBtn.addEventListener("click", hideHistory);
const historyPanelEl = document.getElementById("history-panel");
if (historyPanelEl) historyPanelEl.addEventListener("click", (ev) => {
  if (ev.target === historyPanelEl) hideHistory();
});

const detailCloseBtn = document.getElementById("detail-close");
if (detailCloseBtn) detailCloseBtn.addEventListener("click", hideDetail);
const detailBackBtn = document.getElementById("detail-back");
if (detailBackBtn) detailBackBtn.addEventListener("click", () => {
  hideDetail();
  openHistory();
});
const detailExportBtn = document.getElementById("detail-export");
if (detailExportBtn) detailExportBtn.addEventListener("click", exportCurrentDetail);
const detailPanelEl = document.getElementById("detail-panel");
if (detailPanelEl) detailPanelEl.addEventListener("click", (ev) => {
  if (ev.target === detailPanelEl) hideDetail();
});

const summaryCloseBtn = document.getElementById("summary-close");
if (summaryCloseBtn) summaryCloseBtn.addEventListener("click", hideSummaryPanel);
const summaryPanelEl = document.getElementById("summary-panel");
if (summaryPanelEl) summaryPanelEl.addEventListener("click", (ev) => {
  // click en el backdrop (no dentro de la card) cierra el panel
  if (ev.target === summaryPanelEl) hideSummaryPanel();
});

const btnGraph = document.getElementById("btn-graph");
if (btnGraph) btnGraph.addEventListener("click", openGraphPanel);
const graphCloseBtn = document.getElementById("graph-close");
if (graphCloseBtn) graphCloseBtn.addEventListener("click", hideGraphPanel);
const graphPanelEl = document.getElementById("graph-panel");
if (graphPanelEl) graphPanelEl.addEventListener("click", (ev) => {
  if (ev.target === graphPanelEl) hideGraphPanel();
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    hideSummaryPanel();
    hideHistory();
    hideDetail();
    hideGraphPanel();
  }
});

mountCharacters();
loadModels();
setStatus("Listo para debatir.");

// Auto-demo when opened standalone (file://) or with ?demo=1
const params = new URLSearchParams(location.search);
if (params.has("demo") || location.protocol === "file:" ||
    location.hostname === "" || location.hostname === "localhost" && params.get("demo") === "1") {
  if (params.has("demo")) setTimeout(runDemo, 600);
}
