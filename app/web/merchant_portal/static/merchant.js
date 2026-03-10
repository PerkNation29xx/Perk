/* PerkNation merchant web portal */

function qs(sel, root) {
  return (root || document).querySelector(sel);
}

function fmtUsd(value) {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value ?? "");
  return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function fmtInt(value) {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value ?? "");
  return Math.round(n).toLocaleString();
}

function fmtPct(rate) {
  const n = typeof rate === "string" ? Number(rate) : rate;
  if (!Number.isFinite(n)) return String(rate ?? "");
  return `${Math.round(n * 100)}%`;
}

function showStatus(message) {
  const card = qs("#statusCard");
  qs("#statusText").textContent = message || "";
  card.hidden = !message;
}

function hideStatus() {
  showStatus("");
}

const STORAGE_KEY = "pk_merchant_portal_session_v1";
let config = null;
let state = {
  me: null,
  metrics: null,
  offers: [],
  locations: [],
  aiConversation: [],
  aiModel: null,
};

function resetAiConversation() {
  state.aiConversation = [
    {
      role: "assistant",
      text: "Hi, I am your PerkNation AI assistant. Ask me about merchant offers, activations, and growth strategy.",
    },
  ];
  state.aiModel = null;
}

function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveSession(session) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}

function isExpired(session) {
  if (!session || !session.expires_at) return true;
  return Date.now() > ((session.expires_at * 1000) - 30_000);
}

async function supabaseSignIn(email, password) {
  const url = `${config.supabase_url}/auth/v1/token?grant_type=password`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      apikey: config.supabase_anon_key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.error_description || body.error || JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Sign-in failed (${res.status})`);
  }
  const data = await res.json();
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + (data.expires_in || 3600),
    email,
  };
}

async function supabaseRefresh(refreshToken) {
  const url = `${config.supabase_url}/auth/v1/token?grant_type=refresh_token`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      apikey: config.supabase_anon_key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error(`Session refresh failed (${res.status})`);
  const data = await res.json();
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + (data.expires_in || 3600),
  };
}

async function ensureSession() {
  const session = loadSession();
  if (!session) return null;
  if (!isExpired(session)) return session;
  if (!session.refresh_token) return null;
  const refresh = await supabaseRefresh(session.refresh_token);
  const merged = { ...session, ...refresh };
  saveSession(merged);
  return merged;
}

async function apiFetch(path, options) {
  const session = await ensureSession();
  if (!session || !session.access_token) throw new Error("Not signed in.");

  const res = await fetch(path, {
    ...(options || {}),
    headers: {
      ...(options && options.headers ? options.headers : {}),
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    },
  });
  if (res.status === 401) {
    clearSession();
    updateAuthUi();
    throw new Error("Session expired. Please sign in again.");
  }
  return res;
}

async function apiJson(path, options, allowStatuses) {
  const res = await apiFetch(path, options);
  const body = await res.json().catch(() => ({}));
  const allowed = new Set(allowStatuses || []);
  if (!res.ok && !allowed.has(res.status)) {
    throw new Error(body.detail || body.message || `${path} failed (${res.status})`);
  }
  return { status: res.status, body };
}

function updateAuthUi() {
  const session = loadSession();
  const signedIn = !!(session && session.access_token);
  qs("#sessionPill").textContent = signedIn ? `Signed in: ${session.email || "merchant"}` : "Signed out";
  qs("#logoutBtn").disabled = !signedIn;
  qs("#loginCard").hidden = signedIn;
  qs("#portalSection").hidden = !signedIn;
  if (!signedIn) {
    resetAiConversation();
    renderAiAssistant();
  }
}

function table(columns, rows, emptyText) {
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const t = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c.label;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  t.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((c) => {
      const td = document.createElement("td");
      const v = c.render ? c.render(row) : row[c.key];
      if (v instanceof Node) td.appendChild(v);
      else td.textContent = v == null ? "" : String(v);
      if (c.mono) td.classList.add("mono");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  t.appendChild(tbody);
  wrap.appendChild(t);

  const out = document.createElement("div");
  out.appendChild(wrap);
  if (!rows.length) {
    const p = document.createElement("div");
    p.className = "muted small";
    p.style.marginTop = "8px";
    p.textContent = emptyText || "No data.";
    out.appendChild(p);
  }
  return out;
}

function renderMetrics() {
  const m = state.metrics || {};
  qs("#kpiImpressions").textContent = fmtInt(m.impressions_estimate || 0);
  qs("#kpiActivations").textContent = fmtInt(m.activations || 0);
  qs("#kpiTransactions").textContent = fmtInt(m.attributed_transactions || 0);
  qs("#kpiVolume").textContent = fmtUsd(m.attributed_volume_usd || 0);
}

function renderLocations() {
  const host = qs("#locationsWrap");
  host.innerHTML = "";

  const select = qs("#offerLocationSelect");
  select.innerHTML = `<option value="">No location</option>`;
  (state.locations || []).forEach((loc) => {
    const opt = document.createElement("option");
    opt.value = String(loc.id);
    opt.textContent = `${loc.name} (${loc.address})`;
    select.appendChild(opt);
  });

  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Name", key: "name" },
    { label: "Address", key: "address" },
    { label: "Latitude", key: "latitude", mono: true },
    { label: "Longitude", key: "longitude", mono: true },
    { label: "Hours", key: "hours" },
    { label: "Status", key: "status" },
  ];
  host.appendChild(table(columns, state.locations || [], "No locations yet."));
}

function renderOffers() {
  const host = qs("#offersWrap");
  host.innerHTML = "";
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Title", key: "title" },
    { label: "Type", key: "offer_type" },
    { label: "Cash rate", render: (o) => fmtPct(o.reward_rate_cash) },
    { label: "Status", key: "approval_status" },
    { label: "Start", key: "starts_at", mono: true },
    { label: "End", key: "ends_at", mono: true },
  ];
  host.appendChild(table(columns, state.offers || [], "No offers yet."));
}

function renderAiAssistant() {
  const wrap = qs("#aiConversationWrap");
  const modelPill = qs("#aiModelPill");
  if (!wrap || !modelPill) return;

  modelPill.textContent = `Model: ${state.aiModel || "-"}`;
  wrap.innerHTML = "";

  const rows = Array.isArray(state.aiConversation) ? state.aiConversation : [];
  if (!rows.length) {
    wrap.innerHTML = `<div class="muted small">No assistant messages yet.</div>`;
    return;
  }

  rows.slice(-12).forEach((entry) => {
    const role = String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant";
    const row = document.createElement("div");
    row.className = `ai-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "ai-bubble";
    bubble.textContent = String(entry.text || "");

    row.appendChild(bubble);
    wrap.appendChild(row);
  });
}

async function refreshMerchantData() {
  const me = await apiJson(`${config.api_v1_prefix}/auth/me`);
  const role = String(me.body.role || "").toLowerCase();
  if (role !== "merchant") {
    throw new Error(`Signed in as ${me.body.role}. Use a merchant account for /merchant portal.`);
  }
  state.me = me.body;
  qs("#sessionPill").textContent = `Signed in: ${state.me.email}`;

  const [metrics, offers, locations] = await Promise.all([
    apiJson(`${config.api_v1_prefix}/merchant/metrics`, {}, [404]),
    apiJson(`${config.api_v1_prefix}/merchant/offers`, {}, [404]),
    apiJson(`${config.api_v1_prefix}/merchant/locations`, {}, [404]),
  ]);

  if (metrics.status === 404) {
    state.metrics = {
      impressions_estimate: 0,
      activations: 0,
      attributed_transactions: 0,
      attributed_volume_usd: 0,
    };
  } else {
    state.metrics = metrics.body;
  }

  state.offers = offers.status === 404 ? [] : offers.body;
  state.locations = locations.status === 404 ? [] : locations.body;

  renderMetrics();
  renderOffers();
  renderLocations();
  renderAiAssistant();
}

async function askAiAssistant(message) {
  const prompt = String(message || "").trim();
  if (!prompt) return;

  const history = (state.aiConversation || [])
    .slice(-10)
    .map((entry) => ({
      role: String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant",
      content: String(entry.text || "").slice(0, 1500),
    }));

  state.aiConversation = (state.aiConversation || []).concat([{ role: "user", text: prompt }]);
  renderAiAssistant();

  const hint = qs("#aiHint");
  const sendBtn = qs("#aiSendBtn");
  if (hint) hint.textContent = "Thinking...";
  if (sendBtn) sendBtn.disabled = true;

  try {
    const { body } = await apiJson(`${config.api_v1_prefix}/ai/chat`, {
      method: "POST",
      body: JSON.stringify({
        message: prompt,
        context: "merchant",
        history,
      }),
    });

    state.aiModel = body.model || null;
    state.aiConversation = (state.aiConversation || []).concat([
      { role: "assistant", text: String(body.answer || "No response.") },
    ]);
    renderAiAssistant();
    if (hint) hint.textContent = "";
  } catch (err) {
    state.aiConversation = (state.aiConversation || []).concat([
      { role: "assistant", text: `I could not reach the AI service. ${err.message || err}` },
    ]);
    renderAiAssistant();
    if (hint) hint.textContent = "";
    throw err;
  } finally {
    if (sendBtn) sendBtn.disabled = false;
  }
}

async function saveProfile() {
  const payload = {
    legal_name: qs("#legalNameInput").value.trim(),
    dba_name: qs("#dbaNameInput").value.trim(),
    category: qs("#categoryInput").value.trim(),
  };
  if (!payload.legal_name || !payload.dba_name || !payload.category) {
    showStatus("Profile fields are required.");
    return;
  }
  const { body } = await apiJson(`${config.api_v1_prefix}/merchant/profile`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showStatus(body.message || "Merchant profile saved.");
  await refreshMerchantData();
}

async function addLocation() {
  const payload = {
    name: qs("#locationNameInput").value.trim(),
    address: qs("#locationAddressInput").value.trim(),
    latitude: Number(qs("#locationLatitudeInput").value),
    longitude: Number(qs("#locationLongitudeInput").value),
    hours: qs("#locationHoursInput").value.trim() || null,
  };
  if (!payload.name || !payload.address || !Number.isFinite(payload.latitude) || !Number.isFinite(payload.longitude)) {
    showStatus("Location name, address, latitude, and longitude are required.");
    return;
  }
  await apiJson(`${config.api_v1_prefix}/merchant/locations`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showStatus("Location added.");
  qs("#locationForm").reset();
  await refreshMerchantData();
}

function maybeNumber(raw) {
  const s = String(raw || "").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function normalizeIsoInput(raw) {
  const text = String(raw || "").trim();
  if (!text) return null;
  // Allow plain dates.
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return `${text}T00:00:00Z`;
  }
  return text;
}

async function createOffer() {
  const start = normalizeIsoInput(qs("#offerStartInput").value);
  const end = normalizeIsoInput(qs("#offerEndInput").value);
  const cashRate = Number(qs("#offerCashRateInput").value);

  if (!start || !end || !Number.isFinite(cashRate)) {
    showStatus("Title, terms, cash rate, start, and end are required.");
    return;
  }

  const locationRaw = qs("#offerLocationSelect").value;
  const locationId = locationRaw ? Number(locationRaw) : null;

  const payload = {
    title: qs("#offerTitleInput").value.trim(),
    offer_type: qs("#offerTypeInput").value.trim() || "boost",
    terms_text: qs("#offerTermsInput").value.trim(),
    reward_rate_cash: cashRate,
    reward_rate_stock: cashRate,
    starts_at: start,
    ends_at: end,
    location_id: Number.isFinite(locationId) ? locationId : null,
    schedule_rules: qs("#offerScheduleInput").value.trim() || null,
    daily_cap: maybeNumber(qs("#offerDailyCapInput").value),
    total_cap: maybeNumber(qs("#offerTotalCapInput").value),
    per_user_limit: maybeNumber(qs("#offerPerUserLimitInput").value),
  };

  if (!payload.title || !payload.terms_text) {
    showStatus("Title and terms are required.");
    return;
  }

  await apiJson(`${config.api_v1_prefix}/merchant/offers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  showStatus("Offer created (pending admin approval).");
  await refreshMerchantData();
}

async function loadConfig() {
  const res = await fetch("/web/config");
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  config = data;
}

function seedDefaultOfferDates() {
  const now = new Date();
  const end = new Date(now.getTime() + (30 * 24 * 60 * 60 * 1000));
  qs("#offerStartInput").value = now.toISOString();
  qs("#offerEndInput").value = end.toISOString();
}

async function bootstrapSignedIn() {
  updateAuthUi();
  if (!loadSession()) return;
  await refreshMerchantData();
}

window.addEventListener("DOMContentLoaded", async () => {
  resetAiConversation();
  renderAiAssistant();
  qs("#statusDismissBtn").addEventListener("click", hideStatus);
  qs("#logoutBtn").addEventListener("click", () => {
    clearSession();
    updateAuthUi();
    showStatus("Signed out.");
  });

  qs("#refreshAllBtn").addEventListener("click", async () => {
    try {
      await refreshMerchantData();
      showStatus("Refreshed.");
    } catch (err) {
      showStatus(err.message || String(err));
    }
  });
  qs("#reloadMetricsBtn").addEventListener("click", async () => {
    try {
      await refreshMerchantData();
      showStatus("Metrics reloaded.");
    } catch (err) {
      showStatus(err.message || String(err));
    }
  });

  qs("#profileForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await saveProfile();
    } catch (err) {
      showStatus(err.message || String(err));
    }
  });
  qs("#locationForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await addLocation();
    } catch (err) {
      showStatus(err.message || String(err));
    }
  });
  qs("#offerForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await createOffer();
    } catch (err) {
      showStatus(err.message || String(err));
    }
  });

  qs("#aiAssistantForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = qs("#aiPromptInput");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    try {
      await askAiAssistant(message);
    } catch (err) {
      showStatus(err.message || String(err));
    }
  });

  qs("#aiClearBtn").addEventListener("click", () => {
    resetAiConversation();
    renderAiAssistant();
    qs("#aiHint").textContent = "";
  });

  qs("#loginForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = qs("#emailInput").value.trim();
    const password = qs("#passwordInput").value;
    qs("#loginBtn").disabled = true;
    qs("#loginHint").textContent = "Signing in...";
    try {
      const session = await supabaseSignIn(email, password);
      saveSession(session);
      updateAuthUi();
      await refreshMerchantData();
      showStatus("Signed in.");
    } catch (err) {
      showStatus(err.message || String(err));
    } finally {
      qs("#loginBtn").disabled = false;
      qs("#loginHint").textContent = "";
    }
  });

  seedDefaultOfferDates();

  try {
    await loadConfig();
    await bootstrapSignedIn();
  } catch (err) {
    showStatus(err.message || String(err));
  }
});
