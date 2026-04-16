/* PerkNation Admin Portal (no-build static client)
 *
 * Auth: Supabase email/password (publishable anon key)
 * API: FastAPI backend, same origin, /v1/admin/*
 */

function qs(sel, root) {
  return (root || document).querySelector(sel);
}

function qsa(sel, root) {
  return Array.from((root || document).querySelectorAll(sel));
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

function tag(text, kind) {
  const span = document.createElement("span");
  span.className = `tag ${kind ? `tag--${kind}` : ""}`.trim();
  span.textContent = text;
  return span;
}

function setStatus(message) {
  const card = qs("#statusCard");
  const text = qs("#statusText");
  if (!card || !text) return;
  text.textContent = message || "";
  card.hidden = !message;
}

function clearStatus() {
  setStatus("");
}

const storageKey = "pk_admin_session_v1";

function loadSession() {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveSession(session) {
  localStorage.setItem(storageKey, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(storageKey);
}

function isTokenExpired(session) {
  if (!session || !session.expires_at) return true;
  const ms = session.expires_at * 1000;
  return Date.now() > (ms - 30_000); // refresh a bit early
}

function decodeJwtPayload(token) {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

let config = null;
let currentView = "overview";
let aiConversation = [];
let aiModel = null;
let messageBoxConversation = [];
let messageBoxModel = null;

function resetAiConversation() {
  aiConversation = [
    {
      role: "assistant",
      text: "Hi, I am your PerkNation AI assistant. Ask me about approvals, disputes, risk, or analytics.",
    },
  ];
  aiModel = null;
}

function resetMessageBoxConversation() {
  messageBoxConversation = [];
  messageBoxModel = null;
}

async function loadConfig() {
  const res = await fetch("/admin/config");
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  config = data;
  qs("#topbarSubtitle").textContent = `${data.project_name} • API ${data.api_v1_prefix}`;
}

async function supabasePasswordLogin(email, password) {
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
      const err = await res.json();
      detail = err.error_description || err.msg || err.error || JSON.stringify(err);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Login failed (${res.status})`);
  }

  const data = await res.json();
  // data: {access_token, refresh_token, expires_in, token_type, user...}
  const expiresAt = Math.floor(Date.now() / 1000) + (data.expires_in || 3600);
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: expiresAt,
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

  if (!res.ok) {
    throw new Error(`Refresh failed (${res.status})`);
  }
  const data = await res.json();
  const expiresAt = Math.floor(Date.now() / 1000) + (data.expires_in || 3600);
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: expiresAt,
  };
}

async function ensureFreshSession() {
  const session = loadSession();
  if (!session) return null;
  if (!isTokenExpired(session)) return session;

  if (!session.refresh_token) return null;
  const refreshed = await supabaseRefresh(session.refresh_token);
  const merged = { ...session, ...refreshed };
  saveSession(merged);
  return merged;
}

async function apiFetch(path, opts) {
  const session = await ensureFreshSession();
  if (!session || !session.access_token) {
    throw new Error("Not signed in.");
  }

  const res = await fetch(path, {
    ...(opts || {}),
    headers: {
      ...(opts && opts.headers ? opts.headers : {}),
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    },
  });

  // If token is rejected, force re-login.
  if (res.status === 401) {
    clearSession();
    updateUiAuthState();
    throw new Error("Session expired. Please sign in again.");
  }

  return res;
}

function setActiveNav(view) {
  qsa(".navitem").forEach((btn) => {
    const isActive = btn.dataset.view === view;
    btn.classList.toggle("is-active", isActive);
  });
}

function setViewTitle(title, subtitle) {
  qs("#viewTitle").textContent = title;
  qs("#viewSubtitle").textContent = subtitle || "";
}

function svgSparkline(series, options) {
  const width = (options && options.width) || 640;
  const height = (options && options.height) || 120;
  const stroke = (options && options.stroke) || "rgba(124, 240, 195, 0.95)";
  const fill = (options && options.fill) || "rgba(124, 240, 195, 0.12)";

  const values = series.map((p) => Number(p.value) || 0);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);

  const pad = 6;
  const w = width - pad * 2;
  const h = height - pad * 2;

  const points = values.map((v, idx) => {
    const x = pad + (idx / Math.max(values.length - 1, 1)) * w;
    const t = (v - min) / (max - min || 1);
    const y = pad + (1 - t) * h;
    return [x, y];
  });

  const dLine = points.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const dArea = `${pad},${height - pad} ${dLine} ${width - pad},${height - pad}`;

  return `
<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Chart">
  <polyline points="${dArea}" fill="${fill}" stroke="none"></polyline>
  <polyline points="${dLine}" fill="none" stroke="${stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>
</svg>`;
}

function renderTable(columns, rows, options) {
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      const cell = col.render ? col.render(row) : row[col.key];
      if (cell instanceof Node) {
        td.appendChild(cell);
      } else {
        td.textContent = cell == null ? "" : String(cell);
      }
      if (col.mono) td.classList.add("mono");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  const wrap = document.createElement("div");
  wrap.className = "tableWrap";
  wrap.appendChild(table);

  const empty = document.createElement("div");
  empty.className = "muted small";
  empty.style.marginTop = "10px";
  empty.textContent = rows.length ? "" : ((options && options.emptyText) || "No data.");

  const out = document.createElement("div");
  out.appendChild(wrap);
  out.appendChild(empty);
  return out;
}

async function loadMe() {
  const res = await apiFetch(`${config.api_v1_prefix}/auth/me`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Failed to load /auth/me (${res.status})`);
  }
  return await res.json();
}

async function loadOverview() {
  const days = Number(qs("#daysSelect").value) || 30;
  const res = await apiFetch(`${config.api_v1_prefix}/admin/overview?days=${days}`);
  if (res.status === 403) {
    throw new Error("Forbidden. Your account is not an admin in the backend database.");
  }
  if (!res.ok) throw new Error(`Overview failed (${res.status})`);
  return await res.json();
}

async function loadUsers() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/users?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Users failed (${res.status})`);
  return await res.json();
}

async function loadMerchants() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/merchants?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Merchants failed (${res.status})`);
  return await res.json();
}

async function loadOffers() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/offers?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Offers failed (${res.status})`);
  return await res.json();
}

async function loadApprovals() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/approvals`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Approvals failed (${res.status})`);
  return await res.json();
}

async function decideOffer(offerId, status) {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/approvals/${offerId}`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`Offer decision failed (${res.status})`);
  return await res.json();
}

async function loadTransactions() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/transactions?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Transactions failed (${res.status})`);
  return await res.json();
}

async function loadRewards() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/rewards?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Rewards failed (${res.status})`);
  return await res.json();
}

async function adjustReward(rewardId, state, reason) {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/rewards/${rewardId}/adjust`, {
    method: "POST",
    body: JSON.stringify({ state, reason }),
  });
  if (!res.ok) throw new Error(`Reward adjust failed (${res.status})`);
  return await res.json();
}

async function loadSupportTickets() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/support/tickets?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Support tickets failed (${res.status})`);
  return await res.json();
}

async function loadContactInbox() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/contact-inbox?limit=300`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Contact inbox failed (${res.status})`);
  return await res.json();
}

async function loadOrders() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/orders?limit=300`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Orders failed (${res.status})`);
  return await res.json();
}

async function loadDisputes() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/disputes`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Disputes failed (${res.status})`);
  return await res.json();
}

async function resolveDispute(disputeId) {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/disputes/${disputeId}/resolve`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Dispute resolve failed (${res.status})`);
  return await res.json();
}

async function loadStockConversions() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/stock_conversions?limit=200`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Stock conversions failed (${res.status})`);
  return await res.json();
}

async function loadAuditLogs() {
  const res = await apiFetch(`${config.api_v1_prefix}/admin/audit?limit=300`);
  if (res.status === 403) throw new Error("Forbidden (admin only).");
  if (!res.ok) throw new Error(`Audit failed (${res.status})`);
  return await res.json();
}

async function loadMessageBoxMessages() {
  const res = await apiFetch(`${config.api_v1_prefix}/ai/messages`);
  if (res.status === 403) {
    throw new Error("Message Box access is limited to the owner admin account.");
  }
  if (!res.ok) throw new Error(`Message box failed (${res.status})`);
  return await res.json();
}

async function sendMessageBoxMessage(message) {
  const res = await apiFetch(`${config.api_v1_prefix}/ai/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 403) {
    throw new Error("Message Box access is limited to the owner admin account.");
  }
  if (!res.ok) {
    throw new Error(body.detail || body.message || `Message send failed (${res.status})`);
  }
  return body;
}

function updateUiAuthState() {
  const session = loadSession();
  const sessionPill = qs("#sessionPill");
  const logoutBtn = qs("#logoutBtn");
  const loginCard = qs("#loginCard");
  const portal = qs("#portal");

  if (session && session.access_token) {
    sessionPill.textContent = session.email ? `Signed in: ${session.email}` : "Signed in";
    logoutBtn.disabled = false;
    loginCard.hidden = true;
    portal.hidden = false;
  } else {
    sessionPill.textContent = "Signed out";
    logoutBtn.disabled = true;
    loginCard.hidden = false;
    portal.hidden = true;
  }
}

async function renderOverviewView(container) {
  setViewTitle("Overview", "KPIs and recent activity");
  const data = await loadOverview();

  const grid = document.createElement("div");
  grid.className = "grid";

  const kpis = [
    { label: "Users (total)", value: fmtInt(data.users_total), hint: `${fmtInt(data.users_new)} new / ${data.days}d` },
    { label: "Offers (active)", value: fmtInt(data.offers_active), hint: `${fmtInt(data.offers_pending)} pending approvals` },
    { label: "Txn volume", value: fmtUsd(data.transactions_volume_window_usd), hint: `${data.days}d window` },
    { label: "Rewards (available)", value: fmtUsd(data.rewards_available_usd), hint: `Pending ${fmtUsd(data.rewards_pending_usd)}` },
    { label: "Stock converted", value: fmtUsd(data.stock_converted_total_usd), hint: "Stock Vault (demo)" },
    { label: "Tickets (open)", value: fmtInt(data.tickets_open), hint: "Support" },
    { label: "Disputes (open)", value: fmtInt(data.disputes_open), hint: "Risk" },
    { label: "Transactions (total)", value: fmtInt(data.transactions_total), hint: `All-time ${fmtUsd(data.transactions_volume_usd)}` },
  ];

  kpis.forEach((k) => {
    const div = document.createElement("div");
    div.className = "kpi";
    div.innerHTML = `
      <div class="kpi__label">${k.label}</div>
      <div class="kpi__value">${k.value}</div>
      <div class="kpi__hint">${k.hint || ""}</div>
    `;
    grid.appendChild(div);
  });

  const charts = document.createElement("div");
  charts.className = "row";
  charts.style.marginTop = "10px";
  charts.style.gap = "12px";

  const volumeCard = document.createElement("div");
  volumeCard.className = "chart";
  volumeCard.style.flex = "1 1 520px";
  volumeCard.innerHTML = `
    <div class="h2">Txn volume (${data.days}d)</div>
    <div class="muted small">Sum of transaction amounts by day (UTC).</div>
    ${svgSparkline(data.volume_by_day, { stroke: "rgba(124, 240, 195, 0.95)", fill: "rgba(124, 240, 195, 0.12)" })}
  `;

  const usersCard = document.createElement("div");
  usersCard.className = "chart";
  usersCard.style.flex = "1 1 520px";
  usersCard.innerHTML = `
    <div class="h2">New users (${data.days}d)</div>
    <div class="muted small">User records created by day (UTC).</div>
    ${svgSparkline(data.new_users_by_day.map(p => ({date: p.date, value: p.value})), { stroke: "rgba(124, 167, 255, 0.95)", fill: "rgba(124, 167, 255, 0.12)" })}
  `;

  charts.appendChild(volumeCard);
  charts.appendChild(usersCard);

  container.appendChild(grid);
  container.appendChild(charts);
}

async function renderUsersView(container) {
  setViewTitle("Users", "All users in the backend database");
  const users = await loadUsers();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Email", key: "email" },
    { label: "Name", key: "full_name" },
    { label: "Role", key: "role", render: (u) => tag(u.role, u.role === "admin" ? "warn" : "") },
    { label: "Status", key: "status", render: (u) => tag(u.status, u.status === "active" ? "ok" : "danger") },
    { label: "Verified", key: "email_verified", render: (u) => tag(u.email_verified ? "yes" : "no", u.email_verified ? "ok" : "warn") },
    { label: "Created", key: "created_at", mono: true },
    { label: "Supabase user id", key: "supabase_user_id", mono: true },
  ];
  container.appendChild(renderTable(columns, users, { emptyText: "No users found." }));
}

async function renderMerchantsView(container) {
  setViewTitle("Merchants", "Merchant profiles");
  const merchants = await loadMerchants();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "DBA", key: "dba_name" },
    { label: "Legal", key: "legal_name" },
    { label: "Category", key: "category" },
    { label: "Status", key: "status", render: (m) => tag(m.status, m.status === "approved" ? "ok" : "warn") },
    { label: "Locations", key: "locations_count", render: (m) => fmtInt(m.locations_count) },
    { label: "Offers", key: "offers_count", render: (m) => fmtInt(m.offers_count) },
    { label: "Logo URL", key: "logo_url", mono: true },
  ];
  container.appendChild(renderTable(columns, merchants, { emptyText: "No merchants found." }));
}

async function renderOffersView(container) {
  setViewTitle("Offers", "All offers");
  const offers = await loadOffers();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Merchant", key: "merchant_name" },
    { label: "Title", key: "title" },
    { label: "Cash rate", key: "reward_rate_cash", render: (o) => `${Math.round((Number(o.reward_rate_cash) || 0) * 100)}%` },
    { label: "Status", key: "approval_status", render: (o) => tag(o.approval_status, o.approval_status === "approved" ? "ok" : (o.approval_status === "pending" ? "warn" : "danger")) },
    { label: "Starts", key: "starts_at", mono: true },
    { label: "Ends", key: "ends_at", mono: true },
  ];
  container.appendChild(renderTable(columns, offers, { emptyText: "No offers found." }));
}

async function renderApprovalsView(container) {
  setViewTitle("Approvals", "Approve or deny pending offers");
  const offers = await loadApprovals();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Merchant", key: "merchant_name" },
    { label: "Title", key: "title" },
    { label: "Cash rate", key: "reward_rate_cash", render: (o) => `${Math.round((Number(o.reward_rate_cash) || 0) * 100)}%` },
    { label: "Actions", key: "_actions", render: (o) => {
        const wrap = document.createElement("div");
        wrap.className = "row";
        const approve = document.createElement("button");
        approve.className = "btn btn--primary";
        approve.textContent = "Approve";
        approve.onclick = async () => {
          approve.disabled = true;
          try {
            await decideOffer(o.id, "approved");
            await renderCurrentView();
          } catch (e) {
            setStatus(e.message || String(e));
          } finally {
            approve.disabled = false;
          }
        };
        const deny = document.createElement("button");
        deny.className = "btn btn--danger";
        deny.textContent = "Deny";
        deny.onclick = async () => {
          if (!confirm("Deny this offer?")) return;
          deny.disabled = true;
          try {
            await decideOffer(o.id, "denied");
            await renderCurrentView();
          } catch (e) {
            setStatus(e.message || String(e));
          } finally {
            deny.disabled = false;
          }
        };
        wrap.appendChild(approve);
        wrap.appendChild(deny);
        return wrap;
      }
    },
  ];
  container.appendChild(renderTable(columns, offers, { emptyText: "No pending offers." }));
}

async function renderTransactionsView(container) {
  setViewTitle("Transactions", "Recent transactions");
  const txns = await loadTransactions();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "User", key: "user_email" },
    { label: "Merchant", key: "merchant_name" },
    { label: "Amount", key: "amount", render: (t) => fmtUsd(t.amount) },
    { label: "Status", key: "status", render: (t) => tag(t.status, t.status === "authorized" ? "warn" : "ok") },
    { label: "Occurred", key: "occurred_at", mono: true },
  ];
  container.appendChild(renderTable(columns, txns, { emptyText: "No transactions." }));
}

async function renderRewardsView(container) {
  setViewTitle("Rewards", "Rewards ledger (admin can adjust state)");
  const rewards = await loadRewards();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "User", key: "user_email" },
    { label: "Merchant", key: "merchant_name" },
    { label: "Type", key: "reward_type", render: (r) => tag(r.reward_type, r.reward_type === "cash" ? "ok" : "warn") },
    { label: "Amount", key: "reward_amount", render: (r) => fmtUsd(r.reward_amount) },
    { label: "State", key: "state", render: (r) => tag(r.state, r.state === "available" ? "ok" : (r.state === "pending" ? "warn" : "")) },
    { label: "Created", key: "created_at", mono: true },
    { label: "Adjust", key: "_adjust", render: (r) => {
        const wrap = document.createElement("div");
        wrap.className = "row";

        const select = document.createElement("select");
        select.className = "select";
        ["pending","available","paid","reversed"].forEach((s) => {
          const o = document.createElement("option");
          o.value = s;
          o.textContent = s;
          if (s === r.state) o.selected = true;
          select.appendChild(o);
        });

        const btn = document.createElement("button");
        btn.className = "btn btn--ghost";
        btn.textContent = "Set";
        btn.onclick = async () => {
          const reason = prompt("Reason for adjustment:", "Admin adjustment via portal");
          if (!reason) return;
          btn.disabled = true;
          try {
            await adjustReward(r.id, select.value, reason);
            await renderCurrentView();
          } catch (e) {
            setStatus(e.message || String(e));
          } finally {
            btn.disabled = false;
          }
        };

        wrap.appendChild(select);
        wrap.appendChild(btn);
        return wrap;
      }
    },
  ];
  container.appendChild(renderTable(columns, rewards, { emptyText: "No rewards found." }));
}

async function renderSupportView(container) {
  setViewTitle("Support", "Support tickets");
  const tickets = await loadSupportTickets();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "User", key: "user_email" },
    { label: "Category", key: "category" },
    { label: "Subject", key: "subject" },
    { label: "Status", key: "status", render: (t) => tag(t.status, t.status === "open" ? "warn" : "ok") },
    { label: "Created", key: "created_at", mono: true },
  ];
  container.appendChild(renderTable(columns, tickets, { emptyText: "No tickets found." }));
}

async function renderContactInboxView(container) {
  setViewTitle("Lead Inbox", "Website contact and checkout submissions");
  const submissions = await loadContactInbox();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Created", key: "created_at", mono: true },
    { label: "Type", key: "form_type", render: (s) => tag(s.form_type, s.form_type === "checkout" ? "ok" : "") },
    { label: "Name", key: "name" },
    { label: "Email", key: "email" },
    { label: "Phone", key: "phone" },
    { label: "Source", key: "source_page", mono: true },
    { label: "Inquiry", key: "inquiry" },
  ];
  container.appendChild(renderTable(columns, submissions, { emptyText: "No website submissions found." }));
}

function orderStatusTag(order) {
  const statusText = order.payment_status || "submitted";
  let kind = "";
  if (statusText === "paid") kind = "ok";
  else if (statusText === "failed") kind = "danger";
  else if (statusText === "checkout_created" || statusText === "expired") kind = "warn";
  return tag(statusText, kind);
}

async function renderOrdersView(container) {
  setViewTitle("Orders", "Checkout submissions and payment status");
  const orders = await loadOrders();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Created", key: "created_at", mono: true },
    { label: "Customer", key: "customer_name" },
    { label: "Email", key: "email" },
    { label: "Phone", key: "phone" },
    { label: "Offer", key: "offer_choice" },
    { label: "Park", key: "selected_park" },
    { label: "Qty", key: "package_quantity" },
    { label: "Payment", key: "payment_option", render: (o) => o.payment_option || "not selected" },
    { label: "Status", key: "payment_status", render: (o) => orderStatusTag(o) },
    { label: "Amount", key: "payment_amount_usd", render: (o) => (o.payment_amount_usd ? fmtUsd(o.payment_amount_usd) : "") },
    { label: "Stripe session", key: "stripe_checkout_session_id", mono: true },
    { label: "Summary", key: "summary" },
  ];
  container.appendChild(renderTable(columns, orders, { emptyText: "No orders found." }));
}

async function renderDisputesView(container) {
  setViewTitle("Disputes", "Dispute cases");
  const disputes = await loadDisputes();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "User ID", key: "user_id", mono: true },
    { label: "Txn ID", key: "txn_id", mono: true },
    { label: "Reason", key: "reason" },
    { label: "Status", key: "status", render: (d) => tag(d.status, d.status === "open" ? "warn" : "ok") },
    { label: "Created", key: "created_at", mono: true },
    { label: "Action", key: "_action", render: (d) => {
        if (d.status !== "open") return document.createTextNode("");
        const btn = document.createElement("button");
        btn.className = "btn btn--primary";
        btn.textContent = "Resolve";
        btn.onclick = async () => {
          btn.disabled = true;
          try {
            await resolveDispute(d.id);
            await renderCurrentView();
          } catch (e) {
            setStatus(e.message || String(e));
          } finally {
            btn.disabled = false;
          }
        };
        return btn;
      }
    },
  ];
  container.appendChild(renderTable(columns, disputes, { emptyText: "No disputes found." }));
}

async function renderStockView(container) {
  setViewTitle("Stock Vault", "Cash-to-stocks conversions (MVP demo)");
  const conversions = await loadStockConversions();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "User", key: "user_email" },
    { label: "Amount", key: "amount_usd", render: (c) => fmtUsd(c.amount_usd) },
    { label: "Created", key: "created_at", mono: true },
  ];
  container.appendChild(renderTable(columns, conversions, { emptyText: "No conversions yet." }));
}

async function renderAuditView(container) {
  setViewTitle("Audit", "Administrative and system actions");
  const logs = await loadAuditLogs();
  const columns = [
    { label: "ID", key: "id", mono: true },
    { label: "Actor", key: "actor_email" },
    { label: "Role", key: "actor_role" },
    { label: "Action", key: "action" },
    { label: "Object", key: "object_type" },
    { label: "Object ID", key: "object_id", mono: true },
    { label: "Created", key: "created_at", mono: true },
  ];
  container.appendChild(renderTable(columns, logs, { emptyText: "No audit logs." }));
}

function renderAiThread(threadEl, modelEl) {
  if (!threadEl || !modelEl) return;
  modelEl.textContent = aiModel ? `AI model: ${aiModel}` : "AI assistant";
  threadEl.innerHTML = "";

  const rows = Array.isArray(aiConversation) ? aiConversation : [];
  rows.slice(-12).forEach((entry) => {
    const role = String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant";
    const row = document.createElement("div");
    row.className = `ai-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "ai-bubble";
    bubble.textContent = String(entry.text || "");

    row.appendChild(bubble);
    threadEl.appendChild(row);
  });
}

async function askAiAssistant(message) {
  const prompt = String(message || "").trim();
  if (!prompt) return;

  const history = (aiConversation || [])
    .slice(-10)
    .map((entry) => ({
      role: String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant",
      content: String(entry.text || "").slice(0, 1500),
    }));

  aiConversation = (aiConversation || []).concat([{ role: "user", text: prompt }]);

  const res = await apiFetch(`${config.api_v1_prefix}/ai/chat`, {
    method: "POST",
    body: JSON.stringify({
      message: prompt,
      context: "admin",
      history,
    }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || body.message || `AI request failed (${res.status})`);
  }

  aiModel = body.model || null;
  aiConversation = (aiConversation || []).concat([
    { role: "assistant", text: String(body.answer || "No response.") },
  ]);
}

async function renderAiView(container) {
  setViewTitle("AI Assistant", "Role-aware assistant for admin operations");

  const card = document.createElement("section");
  card.className = "card";

  const top = document.createElement("div");
  top.className = "row row--space";
  top.innerHTML = `
    <div class="h2">PerkNation AI Assistant</div>
    <div class="pill pill--muted" id="aiModelLabel">AI assistant</div>
  `;
  card.appendChild(top);

  const thread = document.createElement("div");
  thread.className = "ai-thread";
  card.appendChild(thread);

  const form = document.createElement("form");
  form.className = "form";
  form.innerHTML = `
    <label class="field">
      <span>Ask PerkNation AI</span>
      <textarea id="aiPromptInput" rows="4" maxlength="2000" placeholder="Ask about approvals, disputes, fraud checks, or platform KPIs."></textarea>
    </label>
    <div class="row">
      <button class="btn btn--primary" id="aiSendBtn" type="submit">Send</button>
      <button class="btn btn--ghost" id="aiClearBtn" type="button">Clear</button>
      <span class="muted small" id="aiHint"></span>
    </div>
  `;
  card.appendChild(form);
  container.appendChild(card);

  const modelEl = form.parentElement.querySelector("#aiModelLabel");
  const hint = form.querySelector("#aiHint");
  const sendBtn = form.querySelector("#aiSendBtn");
  const promptInput = form.querySelector("#aiPromptInput");
  const clearBtn = form.querySelector("#aiClearBtn");

  renderAiThread(thread, modelEl);

  clearBtn.addEventListener("click", () => {
    resetAiConversation();
    renderAiThread(thread, modelEl);
    hint.textContent = "";
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const message = promptInput.value.trim();
    if (!message) return;
    promptInput.value = "";
    sendBtn.disabled = true;
    hint.textContent = "Thinking...";

    try {
      await askAiAssistant(message);
      renderAiThread(thread, modelEl);
      hint.textContent = "";
    } catch (e) {
      aiConversation = (aiConversation || []).concat([
        { role: "assistant", text: `I could not reach the AI service. ${e.message || e}` },
      ]);
      renderAiThread(thread, modelEl);
      hint.textContent = "";
      setStatus(e.message || String(e));
    } finally {
      sendBtn.disabled = false;
    }
  });
}

function renderMessageBoxThread(threadEl, modelEl) {
  if (!threadEl || !modelEl) return;
  modelEl.textContent = messageBoxModel ? `Assistant model: ${messageBoxModel}` : "Private thread";
  threadEl.innerHTML = "";

  const rows = Array.isArray(messageBoxConversation) ? messageBoxConversation : [];
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "muted small";
    empty.textContent = "No messages yet.";
    threadEl.appendChild(empty);
    return;
  }

  rows.slice(-80).forEach((entry) => {
    const role = String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant";
    const row = document.createElement("div");
    row.className = `ai-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "ai-bubble";
    bubble.textContent = String(entry.text || "");

    row.appendChild(bubble);
    threadEl.appendChild(row);
  });
}

async function refreshMessageBoxConversation() {
  const rows = await loadMessageBoxMessages();
  messageBoxConversation = (Array.isArray(rows) ? rows : []).map((row) => ({
    role: String(row.author || "").toLowerCase() === "user" ? "user" : "assistant",
    text: String(row.message || ""),
    createdAt: row.created_at || row.createdAt || null,
    model: row.model || null,
  }));

  const lastWithModel = [...messageBoxConversation]
    .reverse()
    .find((entry) => entry.role === "assistant" && entry.model);
  messageBoxModel = lastWithModel ? String(lastWithModel.model) : null;
}

async function askMessageBoxAssistant(message) {
  const prompt = String(message || "").trim();
  if (!prompt) return;

  const response = await sendMessageBoxMessage(prompt);
  const userMessage = response && response.user_message ? response.user_message : null;
  const assistantMessage = response && response.assistant_message ? response.assistant_message : null;
  const model = response && response.model ? String(response.model) : null;

  if (userMessage) {
    messageBoxConversation.push({
      role: "user",
      text: String(userMessage.message || ""),
      createdAt: userMessage.created_at || userMessage.createdAt || null,
      model: null,
    });
  }

  if (assistantMessage) {
    messageBoxConversation.push({
      role: "assistant",
      text: String(assistantMessage.message || ""),
      createdAt: assistantMessage.created_at || assistantMessage.createdAt || null,
      model: assistantMessage.model || model || null,
    });
  }

  messageBoxModel = model || (assistantMessage ? assistantMessage.model || null : null);
}

async function renderMessageBoxView(container) {
  setViewTitle("Message Box", "Private owner channel");

  const card = document.createElement("section");
  card.className = "card";

  const top = document.createElement("div");
  top.className = "row row--space";
  top.innerHTML = `
    <div class="h2">Private assistant thread</div>
    <div class="pill pill--muted" id="messageBoxModelLabel">Private thread</div>
  `;
  card.appendChild(top);

  const meta = document.createElement("div");
  meta.className = "muted small";
  meta.style.marginTop = "6px";
  meta.textContent = "Only the owner admin account can view and send messages in this box.";
  card.appendChild(meta);

  const thread = document.createElement("div");
  thread.className = "ai-thread";
  card.appendChild(thread);

  const form = document.createElement("form");
  form.className = "form";
  form.innerHTML = `
    <label class="field">
      <span>Message</span>
      <textarea id="messageBoxPromptInput" rows="4" maxlength="2000" placeholder="Type your message here."></textarea>
    </label>
    <div class="row">
      <button class="btn btn--primary" id="messageBoxSendBtn" type="submit">Send</button>
      <button class="btn btn--ghost" id="messageBoxRefreshBtn" type="button">Refresh</button>
      <span class="muted small" id="messageBoxHint"></span>
    </div>
  `;
  card.appendChild(form);
  container.appendChild(card);

  const modelEl = form.parentElement.querySelector("#messageBoxModelLabel");
  const hint = form.querySelector("#messageBoxHint");
  const sendBtn = form.querySelector("#messageBoxSendBtn");
  const refreshBtn = form.querySelector("#messageBoxRefreshBtn");
  const promptInput = form.querySelector("#messageBoxPromptInput");

  await refreshMessageBoxConversation();
  renderMessageBoxThread(thread, modelEl);

  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    hint.textContent = "Refreshing...";
    try {
      await refreshMessageBoxConversation();
      renderMessageBoxThread(thread, modelEl);
      hint.textContent = "";
    } catch (e) {
      hint.textContent = "";
      setStatus(e.message || String(e));
    } finally {
      refreshBtn.disabled = false;
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const message = promptInput.value.trim();
    if (!message) return;
    promptInput.value = "";
    sendBtn.disabled = true;
    hint.textContent = "Sending...";

    try {
      await askMessageBoxAssistant(message);
      renderMessageBoxThread(thread, modelEl);
      hint.textContent = "";
    } catch (e) {
      hint.textContent = "";
      setStatus(e.message || String(e));
    } finally {
      sendBtn.disabled = false;
    }
  });
}

async function renderCurrentView() {
  const container = qs("#viewContainer");
  container.innerHTML = "";

  try {
    switch (currentView) {
      case "users":
        await renderUsersView(container);
        break;
      case "merchants":
        await renderMerchantsView(container);
        break;
      case "offers":
        await renderOffersView(container);
        break;
      case "approvals":
        await renderApprovalsView(container);
        break;
      case "transactions":
        await renderTransactionsView(container);
        break;
      case "rewards":
        await renderRewardsView(container);
        break;
      case "support":
        await renderSupportView(container);
        break;
      case "contactInbox":
        await renderContactInboxView(container);
        break;
      case "orders":
        await renderOrdersView(container);
        break;
      case "disputes":
        await renderDisputesView(container);
        break;
      case "stock":
        await renderStockView(container);
        break;
      case "audit":
        await renderAuditView(container);
        break;
      case "ai":
        await renderAiView(container);
        break;
      case "messageBox":
        await renderMessageBoxView(container);
        break;
      case "overview":
      default:
        await renderOverviewView(container);
        break;
    }

    clearStatus();
  } catch (e) {
    setStatus(e.message || String(e));
  }
}

function wireNav() {
  qsa(".navitem").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const view = btn.dataset.view;
      if (!view) return;
      currentView = view;
      setActiveNav(view);
      await renderCurrentView();
    });
  });
}

async function init() {
  resetAiConversation();
  resetMessageBoxConversation();
  qs("#dismissStatusBtn").addEventListener("click", clearStatus);

  qs("#logoutBtn").addEventListener("click", () => {
    clearSession();
    updateUiAuthState();
    resetAiConversation();
    resetMessageBoxConversation();
    setStatus("Signed out.");
  });

  qs("#refreshBtn").addEventListener("click", async () => {
    await renderCurrentView();
  });

  qs("#daysSelect").addEventListener("change", async () => {
    if (currentView === "overview") await renderCurrentView();
  });

  qs("#testConnectionBtn").addEventListener("click", async () => {
    try {
      const res = await fetch(`${config.api_v1_prefix}/health`);
      const ok = res.ok;
      setStatus(ok ? "Backend reachable." : `Backend not reachable (${res.status}).`);
    } catch (e) {
      setStatus(`Backend test failed: ${e.message || e}`);
    }
  });

  qs("#loginForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = qs("#emailInput").value.trim();
    const password = qs("#passwordInput").value;

    qs("#loginBtn").disabled = true;
    qs("#loginHint").textContent = "Signing in…";

    try {
      const session = await supabasePasswordLogin(email, password);
      saveSession(session);
      updateUiAuthState();

      // Confirm backend sees the user (and role).
      const me = await loadMe();
      const role = me.role || "unknown";
      const pill = qs("#sessionPill");
      pill.textContent = `Signed in: ${me.email} (${role})`;

      if (role !== "admin") {
        setStatus("Signed in, but not an admin. Promote this user to admin in the backend DB, then refresh.");
      } else {
        setStatus("Signed in as admin.");
      }

      setActiveNav(currentView);
      await renderCurrentView();
    } catch (e) {
      setStatus(e.message || String(e));
    } finally {
      qs("#loginBtn").disabled = false;
      qs("#loginHint").textContent = "";
    }
  });

  wireNav();

  updateUiAuthState();
  if (loadSession()) {
    try {
      const me = await loadMe();
      qs("#sessionPill").textContent = `Signed in: ${me.email} (${me.role || "unknown"})`;
      setActiveNav(currentView);
      await renderCurrentView();
    } catch (e) {
      setStatus(e.message || String(e));
    }
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadConfig();
    await init();
  } catch (e) {
    setStatus(e.message || String(e));
  }
});
