/* PerkNation consumer web portal: full web parity with mobile flows. */
(function () {
  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.from((root || document).querySelectorAll(sel));
  }

  function fmtUsd(value) {
    const n = typeof value === "string" ? Number(value) : value;
    if (!Number.isFinite(n)) return "$0.00";
    return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
  }

  function fmtPct(value) {
    const n = typeof value === "string" ? Number(value) : value;
    if (!Number.isFinite(n)) return "0%";
    return `${Math.round(n * 100)}%`;
  }

  function fmtDateTime(value) {
    if (!value) return "";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString();
  }

  function safeText(value) {
    return value == null ? "" : String(value);
  }

  function splitTitle(offer) {
    const title = safeText(offer.title || "").trim();
    if (!title) return { merchant: "Merchant", headline: "" };
    const parts = title.split(":");
    if (parts.length > 1) {
      return {
        merchant: parts[0].trim() || "Merchant",
        headline: parts.slice(1).join(":").trim(),
      };
    }
    return { merchant: title, headline: "" };
  }

  function haversineMiles(lat1, lon1, lat2, lon2) {
    const toRad = (d) => (d * Math.PI) / 180;
    const R = 3958.7613;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }

  function parseNotificationCategories(raw) {
    if (!raw) return new Set();
    if (Array.isArray(raw)) {
      return new Set(raw.map((x) => String(x).trim().toLowerCase()).filter(Boolean));
    }
    return new Set(
      String(raw)
        .split(",")
        .map((x) => x.trim().toLowerCase())
        .filter(Boolean)
    );
  }

  function serializeNotificationCategories(set) {
    return Array.from(set || []).join(",");
  }

  function humanizeAuthError(rawMessage) {
    const message = String(rawMessage || "").trim();
    const lower = message.toLowerCase();

    if (lower.includes("over_email_send_rate_limit") || lower.includes("email rate limit exceeded")) {
      return "Too many verification emails were sent recently. Please wait a few minutes and try again. This does not necessarily mean your account already exists.";
    }

    if (
      lower.includes("already registered") ||
      lower.includes("user already registered") ||
      lower.includes("email already registered")
    ) {
      return "That email is already registered. Try logging in.";
    }

    if (lower.includes("invalid login credentials")) {
      return "Email or password is incorrect.";
    }

    if (lower.includes("not confirmed") || lower.includes("not verified") || lower.includes("confirm")) {
      return "Your email is not verified yet. Open the email link, then log in.";
    }

    if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
      return "Could not reach the server. Check your connection and try again.";
    }

    return message || "Request failed. Please try again.";
  }

  function isEmailRateLimitError(rawMessage) {
    const lower = String(rawMessage || "").toLowerCase();
    return lower.includes("over_email_send_rate_limit") || lower.includes("email rate limit exceeded");
  }

  function normalizeRadius(value) {
    const n = Number(value);
    if (n === 2 || n === 5 || n === 10) return n;
    return 5;
  }

  function qrImageUrl(payload) {
    return `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(payload)}`;
  }

  const OFFER_PHOTO_POOL = [
    "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1541544741938-0af808871cc0?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1559339352-11d035aa65de?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1552566626-52f8b828add9?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?auto=format&fit=crop&w=1400&q=80",
    "https://images.unsplash.com/photo-1517244683847-7456b63c5969?auto=format&fit=crop&w=1400&q=80",
  ];

  function clampHearts(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(5, Math.round(n)));
  }

  function normalizedMerchantId(offer) {
    const n = Number(offer && offer.merchant_id);
    if (Number.isFinite(n) && n > 0) return n;
    return null;
  }

  function mapReviewsByMerchant(reviews) {
    const out = {};
    (Array.isArray(reviews) ? reviews : []).forEach((review) => {
      const merchantId = Number(review && review.merchant_id);
      if (!Number.isFinite(merchantId) || merchantId <= 0) return;
      out[String(merchantId)] = review;
    });
    return out;
  }

  function reviewForOffer(offer) {
    const merchantId = normalizedMerchantId(offer);
    if (!merchantId) return null;
    return state.reviewsByMerchant[String(merchantId)] || null;
  }

  function offerPhotoUrl(offer) {
    const seed = Number((offer && offer.merchant_id) || (offer && offer.id) || 0);
    const idx = Math.abs(seed) % OFFER_PHOTO_POOL.length;
    return OFFER_PHOTO_POOL[idx];
  }

  const STORAGE_KEY = "pk_user_portal_session_v2";

  let config = null;
  let map = null;
  let mapMarkers = null;
  let locationWatchId = null;

  const state = {
    session: null,
    me: null,
    offers: [],
    transactions: [],
    rewards: [],
    investment: null,
    referral: null,
    supportTickets: [],
    currentView: "discover",
    pendingVerificationEmail: "",
    pendingVerificationPassword: "",
    currentLatitude: null,
    currentLongitude: null,
    lastGeoOffersRefreshAt: 0,
    convertAmount: 25,
    aiConversation: [],
    aiModel: null,
    reviewsByMerchant: {},
    reviewModalOffer: null,
    reviewModalOverall: 5,
  };

  function resetAiConversation() {
    state.aiConversation = [
      {
        role: "assistant",
        text: "Hi, I am your PerkNation AI assistant. Ask me about offers, wallet, referrals, or profile settings.",
      },
    ];
    state.aiModel = null;
  }

  function showStatus(message, isError) {
    const card = qs("#statusCard");
    const text = qs("#statusText");
    if (!card || !text) return;

    text.textContent = message || "";
    card.hidden = !message;

    card.style.borderColor = isError ? "rgba(184,66,48,.35)" : "var(--border)";
    card.style.background = isError ? "rgba(184,66,48,.06)" : "#fff";
  }

  function hideStatus() {
    showStatus("", false);
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
    state.session = session;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  }

  function clearSession() {
    state.session = null;
    localStorage.removeItem(STORAGE_KEY);
  }

  function isExpired(session) {
    if (!session || !session.expires_at) return true;
    return Date.now() > ((session.expires_at * 1000) - 30_000);
  }

  async function readJsonResponse(response) {
    const raw = await response.text();
    if (!raw) return {};
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }

  async function loadConfig() {
    const res = await fetch("/web/config");
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    config = data;
  }

  async function supabasePost(path, payload) {
    const url = `${config.supabase_url}${path}`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apikey": config.supabase_anon_key,
        "Authorization": `Bearer ${config.supabase_anon_key}`,
      },
      body: JSON.stringify(payload),
    });

    const body = await readJsonResponse(res);
    if (!res.ok) {
      const detail = body.error_description || body.message || body.msg || body.error || `Auth request failed (${res.status})`;
      throw new Error(humanizeAuthError(detail));
    }
    return body;
  }

  async function supabaseSignUp(email, password, metadata) {
    const body = await supabasePost("/auth/v1/signup", {
      email,
      password,
      data: metadata,
    });

    if (body.user && Array.isArray(body.user.identities) && body.user.identities.length === 0) {
      throw new Error("Email already registered. Please log in.");
    }

    return body;
  }

  async function supabaseSignIn(email, password) {
    return await supabasePost("/auth/v1/token?grant_type=password", {
      email,
      password,
    });
  }

  async function supabaseRefresh(refreshToken) {
    return await supabasePost("/auth/v1/token?grant_type=refresh_token", {
      refresh_token: refreshToken,
    });
  }

  async function supabaseResendSignupConfirmation(email) {
    await supabasePost("/auth/v1/resend", {
      type: "signup",
      email,
    });
  }

  function envelopeToSession(email, envelope) {
    const accessToken = envelope.access_token || (envelope.session && envelope.session.access_token) || null;
    const refreshToken = envelope.refresh_token || (envelope.session && envelope.session.refresh_token) || null;
    const expiresIn = Number(envelope.expires_in || (envelope.session && envelope.session.expires_in) || 3600);

    if (!accessToken) return null;
    return {
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_at: Math.floor(Date.now() / 1000) + (Number.isFinite(expiresIn) ? expiresIn : 3600),
      email,
    };
  }

  async function ensureSession() {
    const current = state.session || loadSession();
    if (!current) return null;
    if (!isExpired(current)) {
      state.session = current;
      return current;
    }

    if (!current.refresh_token) {
      clearSession();
      return null;
    }

    const refreshed = await supabaseRefresh(current.refresh_token);
    const merged = {
      ...current,
      ...envelopeToSession(current.email, refreshed),
      email: current.email,
    };
    saveSession(merged);
    return merged;
  }

  async function apiFetch(path, options) {
    const session = await ensureSession();
    if (!session || !session.access_token) {
      throw new Error("Not signed in.");
    }

    const res = await fetch(path, {
      ...(options || {}),
      headers: {
        ...(options && options.headers ? options.headers : {}),
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}`,
      },
    });

    if (res.status === 401) {
      clearSession();
      updateAuthUi();
      throw new Error("Session expired. Please sign in again.");
    }

    return res;
  }

  async function apiJson(path, options, allowedStatuses) {
    const res = await apiFetch(path, options);
    const body = await readJsonResponse(res);

    const allowed = new Set(allowedStatuses || []);
    if (!res.ok && !allowed.has(res.status)) {
      throw new Error(body.detail || body.message || `${path} failed (${res.status})`);
    }

    return { status: res.status, body };
  }

  function switchAuthMode(mode) {
    const signUpForm = qs("#signUpForm");
    const loginForm = qs("#loginForm");
    const signUpTab = qs("#signUpTabBtn");
    const logInTab = qs("#logInTabBtn");

    const signUp = mode === "signup";
    signUpForm.hidden = !signUp;
    loginForm.hidden = signUp;
    signUpTab.classList.toggle("is-active", signUp);
    logInTab.classList.toggle("is-active", !signUp);
    signUpTab.setAttribute("aria-selected", signUp ? "true" : "false");
    logInTab.setAttribute("aria-selected", !signUp ? "true" : "false");
  }

  function updateAuthUi() {
    const session = state.session || loadSession();
    const signedIn = !!(session && session.access_token);

    qs("#sessionPill").textContent = signedIn
      ? `Signed in: ${session.email || "consumer"}`
      : "Signed out";

    qs("#logoutBtn").disabled = !signedIn;
    qs("#refreshAllBtn").disabled = !signedIn;
    qs("#authCard").hidden = signedIn;
    qs("#appSection").hidden = !signedIn;

    if (!signedIn) {
      stopLocationTracking();
      qs("#nearbyBanner").hidden = true;
      resetAiConversation();
      renderAiAssistant();
    }
  }

  function switchPanel(view) {
    state.currentView = view;
    qsa(".tab-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.view === view);
    });
    qsa(".view").forEach((panel) => {
      panel.hidden = panel.dataset.panel !== view;
    });
    if (view === "discover") {
      renderMap(state.offers || []);
    }
  }

  function extractOfferLocation(offer) {
    const lat = offer.location_latitude == null ? null : Number(offer.location_latitude);
    const lng = offer.location_longitude == null ? null : Number(offer.location_longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return { lat, lng };
  }

  function maybeInitMap() {
    if (map || !window.L) return;
    const mapEl = qs("#offersMap");
    if (!mapEl) return;

    map = window.L.map(mapEl, {
      zoomControl: true,
      attributionControl: true,
    }).setView([34.1456, -118.1505], 14);

    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    mapMarkers = window.L.layerGroup().addTo(map);
  }

  function renderMap(offers) {
    const fallback = qs("#mapFallback");
    const mapEl = qs("#offersMap");
    if (!mapEl) return;

    if (!window.L) {
      fallback.hidden = false;
      return;
    }

    maybeInitMap();
    if (!map || !mapMarkers) {
      fallback.hidden = false;
      return;
    }

    fallback.hidden = true;
    mapMarkers.clearLayers();

    const pins = offers
      .map((offer) => {
        const loc = extractOfferLocation(offer);
        if (!loc) return null;
        const fallbackTitle = splitTitle(offer).merchant;
        const merchant = safeText(offer.merchant_name || fallbackTitle || "Merchant");
        return {
          id: offer.id,
          merchant,
          lat: loc.lat,
          lng: loc.lng,
        };
      })
      .filter(Boolean);

    if (!pins.length) {
      map.setView([34.1456, -118.1505], 14);
      return;
    }

    const bounds = [];
    pins.forEach((pin) => {
      const marker = window.L.marker([pin.lat, pin.lng]);
      marker.bindPopup(`<strong>${pin.merchant}</strong>`);
      marker.addTo(mapMarkers);
      bounds.push([pin.lat, pin.lng]);
    });

    if (bounds.length === 1) {
      map.setView(bounds[0], 15);
    } else {
      map.fitBounds(bounds, { padding: [24, 24] });
    }
  }

  function offerCodeFor(offer) {
    const id = Number(offer.id);
    if (Number.isInteger(id) && id > 0) {
      return `PKN-${String(id).padStart(6, "0")}`;
    }
    return `PKN-${String(id || "000000").padStart(6, "0")}`;
  }

  function offerQrPayload(code) {
    return `https://perknation.app/redeem?code=${encodeURIComponent(code)}`;
  }

  function referralPayload(code) {
    return `https://perknation.app/invite?code=${encodeURIComponent(code)}`;
  }

  function renderMerchantLogo(url, fallbackName) {
    if (url) {
      const img = document.createElement("img");
      img.className = "offer-logo";
      img.src = url;
      img.alt = `${fallbackName} logo`;
      img.loading = "lazy";
      img.onerror = () => {
        img.replaceWith(renderMerchantLogo("", fallbackName));
      };
      return img;
    }

    const div = document.createElement("div");
    div.className = "offer-logo-fallback";
    div.textContent = (fallbackName || "M").slice(0, 2).toUpperCase();
    return div;
  }

  function buildOfferCard(offer) {
    const card = document.createElement("article");
    card.className = "offer-card";

    const titleParts = splitTitle(offer);
    const merchantName = safeText(offer.merchant_name || titleParts.merchant || "Merchant");
    const merchantId = normalizedMerchantId(offer);

    const photo = document.createElement("img");
    photo.className = "offer-photo";
    photo.alt = `${merchantName} dining photo`;
    photo.loading = "lazy";
    photo.src = offerPhotoUrl(offer);
    card.appendChild(photo);

    let distanceText = "";
    const loc = extractOfferLocation(offer);
    if (loc && Number.isFinite(state.currentLatitude) && Number.isFinite(state.currentLongitude)) {
      const miles = haversineMiles(state.currentLatitude, state.currentLongitude, loc.lat, loc.lng);
      distanceText = `${miles.toFixed(1)} mi`;
    }

    const head = document.createElement("div");
    head.className = "offer-head";

    head.appendChild(renderMerchantLogo(offer.merchant_logo_url, merchantName));

    const names = document.createElement("div");
    const nameEl = document.createElement("div");
    nameEl.className = "offer-title";
    nameEl.textContent = merchantName;
    names.appendChild(nameEl);

    const subEl = document.createElement("div");
    subEl.className = "small muted";
    const locationBits = [offer.location_name, offer.location_address].filter(Boolean);
    const locText = locationBits.length ? locationBits.join(" • ") : "";
    subEl.textContent = [locText, distanceText].filter(Boolean).join(" • ");
    names.appendChild(subEl);
    head.appendChild(names);

    if (offer.is_popular) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "Popular";
      head.appendChild(badge);
    }

    const rateEl = document.createElement("div");
    rateEl.className = "offer-rate";
    rateEl.textContent = fmtPct(offer.reward_rate_cash);
    head.appendChild(rateEl);

    card.appendChild(head);

    if (offer.terms_text) {
      const terms = document.createElement("div");
      terms.className = "small muted";
      terms.textContent = offer.terms_text;
      card.appendChild(terms);
    }

    const meta = document.createElement("div");
    meta.className = "small muted";
    meta.textContent = `Reward: ${fmtPct(offer.reward_rate_cash)} cash / ${fmtPct(offer.reward_rate_stock)} stock • Expires ${fmtDateTime(offer.ends_at)}`;
    card.appendChild(meta);

    if (merchantId) {
      const review = reviewForOffer(offer);
      const myHearts = clampHearts(
        review && review.overall_hearts ? review.overall_hearts : (offer.my_review_hearts || 0)
      );
      const hasMyRating = !!(review && review.overall_hearts) || Number(offer.my_review_hearts || 0) > 0;
      const avgHearts = Number(offer.review_avg_hearts || 0);
      const reviewCount = Number(offer.review_count || 0);

      const ratingWrap = document.createElement("div");
      ratingWrap.className = "offer-rating";

      const summary = document.createElement("div");
      summary.className = "review-summary";

      const summaryLeft = document.createElement("div");
      summaryLeft.className = "small muted";
      if (reviewCount > 0) {
        summaryLeft.textContent = `${avgHearts.toFixed(1)} avg • ${reviewCount} review${reviewCount === 1 ? "" : "s"}`;
      } else {
        summaryLeft.textContent = "No reviews yet";
      }
      summary.appendChild(summaryLeft);

      const summaryRight = document.createElement("div");
      summaryRight.className = "small muted";
      summaryRight.textContent = hasMyRating ? `You: ${myHearts}/5` : "Tap hearts to rate";
      summary.appendChild(summaryRight);
      ratingWrap.appendChild(summary);

      const heartsRow = renderHeartButtons(myHearts, async (value) => {
        try {
          await submitQuickOfferReview(offer, value);
        } catch (err) {
          showStatus(err.message || String(err), true);
        }
      });
      ratingWrap.appendChild(heartsRow);

      const detailsBtn = document.createElement("button");
      detailsBtn.className = "btn btn-ghost";
      detailsBtn.type = "button";
      detailsBtn.textContent = "Detailed review";
      detailsBtn.onclick = () => openReviewModal(offer);
      ratingWrap.appendChild(detailsBtn);

      card.appendChild(ratingWrap);
    }

    const actions = document.createElement("div");
    actions.className = "offer-actions";

    if (offer.is_activated) {
      const activated = document.createElement("span");
      activated.className = "pill";
      activated.textContent = "Activated";
      actions.appendChild(activated);
    } else {
      const activateBtn = document.createElement("button");
      activateBtn.className = "btn";
      activateBtn.type = "button";
      activateBtn.textContent = "Activate";
      activateBtn.onclick = async () => {
        activateBtn.disabled = true;
        try {
          await activateOffer(offer.id);
          await refreshConsumerData();
        } catch (err) {
          showStatus(err.message || String(err), true);
        } finally {
          activateBtn.disabled = false;
        }
      };
      actions.appendChild(activateBtn);
    }

    const codeBtn = document.createElement("button");
    codeBtn.className = "btn";
    codeBtn.type = "button";
    codeBtn.textContent = "View code";
    codeBtn.onclick = () => openOfferCodeModal(offer);
    actions.appendChild(codeBtn);

    const payBtn = document.createElement("button");
    payBtn.className = "btn btn-primary";
    payBtn.type = "button";
    payBtn.textContent = "Simulate purchase";
    payBtn.disabled = !offer.is_activated;
    payBtn.onclick = async () => {
      payBtn.disabled = true;
      try {
        const amount = Number(qs("#purchaseAmountInput").value);
        if (!Number.isFinite(amount) || amount <= 0) {
          throw new Error("Enter a valid purchase amount.");
        }
        await simulatePurchase(offer.id, amount);
        await refreshConsumerData();
      } catch (err) {
        showStatus(err.message || String(err), true);
      } finally {
        payBtn.disabled = !offer.is_activated;
      }
    };
    actions.appendChild(payBtn);

    card.appendChild(actions);
    return card;
  }

  function renderOffers() {
    const host = qs("#offersWrap");
    host.innerHTML = "";

    if (!state.offers.length) {
      const empty = document.createElement("div");
      empty.className = "list-item muted";
      empty.textContent = "No active offers found.";
      host.appendChild(empty);
      return;
    }

    state.offers.forEach((offer) => {
      host.appendChild(buildOfferCard(offer));
    });
  }

  function renderTransactions() {
    const host = qs("#transactionsWrap");
    host.innerHTML = "";

    const rows = state.transactions || [];
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "list-item muted";
      empty.textContent = "No transactions yet.";
      host.appendChild(empty);
      return;
    }

    rows.forEach((tx) => {
      const item = document.createElement("div");
      item.className = "list-item";

      const merchant = safeText(tx.merchant_name || splitTitle(tx).merchant || `Merchant #${tx.merchant_id || "-"}`);

      item.innerHTML = `
        <div class="row row-space">
          <strong>${merchant}</strong>
          <strong>${fmtUsd(tx.amount)}</strong>
        </div>
        <div class="small muted">Txn #${safeText(tx.id)} • Offer #${safeText(tx.offer_id || "n/a")}</div>
        <div class="small muted">${safeText(tx.status)} • ${fmtDateTime(tx.occurred_at)}</div>
      `;
      host.appendChild(item);
    });
  }

  function renderRewards() {
    const host = qs("#rewardsWrap");
    host.innerHTML = "";

    const rows = state.rewards || [];
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "list-item muted";
      empty.textContent = "No rewards yet.";
      host.appendChild(empty);
      return;
    }

    rows.forEach((reward) => {
      const item = document.createElement("div");
      item.className = "list-item";

      const merchant = safeText(reward.merchant_name || `Merchant #${reward.merchant_id || "-"}`);
      item.innerHTML = `
        <div class="row row-space">
          <strong>${merchant}</strong>
          <strong>${fmtUsd(reward.reward_amount)}</strong>
        </div>
        <div class="small muted">${safeText(reward.reward_type)} • ${fmtPct(reward.rate_applied)} • Reward #${safeText(reward.id)}</div>
        <div class="small muted">${safeText(reward.state)} • ${fmtDateTime(reward.created_at)}</div>
      `;
      host.appendChild(item);
    });
  }

  function updateKpis() {
    const rewards = state.rewards || [];

    const available = rewards
      .filter((r) => String(r.state || "").toLowerCase() === "available" && String(r.reward_type || "").toLowerCase() === "cash")
      .reduce((sum, r) => sum + Number(r.reward_amount || 0), 0);

    const pending = rewards
      .filter((r) => String(r.state || "").toLowerCase() === "pending")
      .reduce((sum, r) => sum + Number(r.reward_amount || 0), 0);

    const inv = state.investment || {};
    const stockBalance = Number(inv.stock_balance_usd || 0);
    const convertibleNow = Number(inv.convertible_now || 0);
    const untilNext = Number(inv.until_next_unlock || 25);

    qs("#kpiAvailable").textContent = fmtUsd(available);
    qs("#kpiPending").textContent = fmtUsd(pending);
    qs("#kpiStock").textContent = fmtUsd(stockBalance);
    qs("#kpiConvertible").textContent = fmtUsd(convertibleNow);
    qs("#kpiUnlock").textContent = `Until next unlock: ${fmtUsd(untilNext)}`;

    if (!Number.isFinite(state.convertAmount) || state.convertAmount < 25) {
      state.convertAmount = 25;
    }

    if (convertibleNow >= 25 && state.convertAmount > convertibleNow) {
      state.convertAmount = Math.max(25, Math.floor(convertibleNow / 25) * 25);
    }

    qs("#convertAmountChip").textContent = fmtUsd(state.convertAmount);

    qs("#convertMinusBtn").disabled = state.convertAmount <= 25;
    qs("#convertPlusBtn").disabled = convertibleNow < state.convertAmount + 25;
    qs("#convertBtn").disabled = !(convertibleNow >= 25 && state.convertAmount <= convertibleNow);
  }

  function renderReferral() {
    const profile = state.referral;
    const codeEl = qs("#referralCodeValue");
    const invitesEl = qs("#referralInvitesValue");
    const countsEl = qs("#referralCountsValue");
    const inviteUrlEl = qs("#referralInviteUrl");
    const qrEl = qs("#referralQrImage");
    const eventsWrap = qs("#referralEventsWrap");

    if (!profile) {
      codeEl.textContent = "-";
      invitesEl.textContent = "0";
      countsEl.textContent = "0 / 0";
      inviteUrlEl.textContent = "-";
      qrEl.removeAttribute("src");
      eventsWrap.innerHTML = `<div class="list-item muted">No referral activity yet.</div>`;
      return;
    }

    codeEl.textContent = safeText(profile.referral_code || "-");
    invitesEl.textContent = String(profile.invites_sent || 0);
    countsEl.textContent = `${profile.pending_referrals || 0} / ${profile.successful_referrals || 0}`;
    inviteUrlEl.textContent = safeText(profile.invite_url || "-");

    const qrPayload = safeText(profile.qr_payload || referralPayload(profile.referral_code || ""));
    qrEl.src = qrImageUrl(qrPayload);

    const events = Array.isArray(profile.recent_events) ? profile.recent_events : [];
    if (!events.length) {
      eventsWrap.innerHTML = `<div class="list-item muted">No referral activity yet.</div>`;
    } else {
      eventsWrap.innerHTML = "";
      events.slice(0, 8).forEach((event) => {
        const item = document.createElement("div");
        item.className = "list-item";
        const eventType = safeText(event.event_type || "event");
        const channel = safeText(event.channel || "");
        item.innerHTML = `
          <div class="row row-space">
            <strong>${eventType}</strong>
            <span class="small muted">${fmtDateTime(event.created_at)}</span>
          </div>
          <div class="small muted">${channel || "n/a"}</div>
        `;
        eventsWrap.appendChild(item);
      });
    }
  }

  function renderSupportTickets() {
    const wrap = qs("#supportTicketsWrap");
    wrap.innerHTML = "";
    const tickets = state.supportTickets || [];

    if (!tickets.length) {
      wrap.innerHTML = `<div class="list-item muted">No support tickets yet.</div>`;
      return;
    }

    tickets.slice(0, 8).forEach((ticket) => {
      const item = document.createElement("div");
      item.className = "list-item";
      item.innerHTML = `
        <div class="row row-space">
          <strong>${safeText(ticket.subject)}</strong>
          <span class="small muted">${safeText(ticket.status)}</span>
        </div>
        <div class="small muted">${safeText(ticket.category)} • ${fmtDateTime(ticket.created_at)}</div>
        <div class="small muted">${safeText(ticket.message)}</div>
      `;
      wrap.appendChild(item);
    });
  }

  function renderAiAssistant() {
    const wrap = qs("#aiConversationWrap");
    const modelPill = qs("#aiModelPill");
    if (!wrap || !modelPill) return;

    modelPill.textContent = `Model: ${state.aiModel || "-"}`;
    wrap.innerHTML = "";

    const rows = Array.isArray(state.aiConversation) ? state.aiConversation : [];
    if (!rows.length) {
      wrap.innerHTML = `<div class="list-item muted">No assistant messages yet.</div>`;
      return;
    }

    rows.slice(-12).forEach((entry) => {
      const role = String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant";
      const row = document.createElement("div");
      row.className = `ai-row ${role}`;

      const bubble = document.createElement("div");
      bubble.className = "ai-bubble";
      bubble.textContent = safeText(entry.text || "");

      row.appendChild(bubble);
      wrap.appendChild(row);
    });
  }

  function renderPreferences() {
    if (!state.me) return;

    const locationToggle = qs("#locationConsentToggle");
    const notificationsToggle = qs("#notificationsToggle");
    locationToggle.checked = !!state.me.location_consent;
    notificationsToggle.checked = !!state.me.notifications_enabled;

    const radius = normalizeRadius(state.me.alert_radius_miles);
    qsa("#radiusChips .chip").forEach((chip) => {
      chip.classList.toggle("is-active", Number(chip.dataset.radius) === radius);
    });

    const categories = parseNotificationCategories(state.me.notification_categories);
    qsa("#categoryChips .chip").forEach((chip) => {
      chip.classList.toggle("is-active", categories.has(String(chip.dataset.category || "").toLowerCase()));
    });
  }

  function updateNearbyBanner() {
    const banner = qs("#nearbyBanner");
    if (!state.me || !state.offers.length) {
      banner.hidden = true;
      banner.textContent = "";
      return;
    }

    if (!state.me.location_consent || !state.me.notifications_enabled) {
      banner.hidden = true;
      banner.textContent = "";
      return;
    }

    if (!Number.isFinite(state.currentLatitude) || !Number.isFinite(state.currentLongitude)) {
      banner.hidden = true;
      banner.textContent = "";
      return;
    }

    const radius = normalizeRadius(state.me.alert_radius_miles);
    let nearest = null;

    state.offers.forEach((offer) => {
      const loc = extractOfferLocation(offer);
      if (!loc) return;
      const miles = haversineMiles(state.currentLatitude, state.currentLongitude, loc.lat, loc.lng);
      if (miles > radius) return;
      if (!nearest || miles < nearest.miles) {
        nearest = { offer, miles };
      }
    });

    if (!nearest) {
      banner.hidden = true;
      banner.textContent = "";
      return;
    }

    const merchant = safeText(nearest.offer.merchant_name || splitTitle(nearest.offer).merchant || "Offer");
    banner.textContent = `Nearby offer: ${merchant} is ${nearest.miles.toFixed(1)} mi away.`;
    banner.hidden = false;
  }

  function renderAll() {
    renderMap(state.offers || []);
    renderOffers();
    renderTransactions();
    renderRewards();
    updateKpis();
    renderReferral();
    renderSupportTickets();
    renderAiAssistant();
    renderPreferences();
    updateNearbyBanner();
  }

  async function refreshConsumerData(options) {
    const opts = options || {};

    const baseOffersPath = `${config.api_v1_prefix}/consumer/offers`;
    const params = new URLSearchParams();
    if (Number.isFinite(state.currentLatitude) && Number.isFinite(state.currentLongitude)) {
      params.set("latitude", String(state.currentLatitude));
      params.set("longitude", String(state.currentLongitude));
    }
    const offersPath = params.toString() ? `${baseOffersPath}?${params.toString()}` : baseOffersPath;

    if (opts.offersOnly) {
      const [offersRes, reviewsRes] = await Promise.all([
        apiFetch(offersPath),
        apiFetch(`${config.api_v1_prefix}/consumer/reviews?mine_only=true`),
      ]);
      if (!offersRes.ok) throw new Error(`Failed /consumer/offers (${offersRes.status})`);
      state.offers = await offersRes.json();
      if (reviewsRes.ok) {
        state.reviewsByMerchant = mapReviewsByMerchant(await reviewsRes.json());
      }
      renderMap(state.offers);
      renderOffers();
      updateNearbyBanner();
      return;
    }

    const [meRes, offersRes, txRes, rewardsRes, invRes, referralRes, supportRes, reviewsRes] = await Promise.all([
      apiFetch(`${config.api_v1_prefix}/auth/me`),
      apiFetch(offersPath),
      apiFetch(`${config.api_v1_prefix}/consumer/transactions`),
      apiFetch(`${config.api_v1_prefix}/consumer/rewards`),
      apiFetch(`${config.api_v1_prefix}/consumer/investments/summary`),
      apiFetch(`${config.api_v1_prefix}/consumer/referrals/profile`),
      apiFetch(`${config.api_v1_prefix}/consumer/support/tickets`),
      apiFetch(`${config.api_v1_prefix}/consumer/reviews?mine_only=true`),
    ]);

    if (!meRes.ok) throw new Error(`Failed /auth/me (${meRes.status})`);
    const me = await meRes.json();
    if (String(me.role || "").toLowerCase() !== "consumer") {
      throw new Error(`Signed in as ${me.role || "unknown"}. Use /merchant for merchant accounts.`);
    }

    if (!offersRes.ok) throw new Error(`Failed /consumer/offers (${offersRes.status})`);
    if (!txRes.ok) throw new Error(`Failed /consumer/transactions (${txRes.status})`);
    if (!rewardsRes.ok) throw new Error(`Failed /consumer/rewards (${rewardsRes.status})`);
    if (!invRes.ok) throw new Error(`Failed /consumer/investments/summary (${invRes.status})`);

    state.me = me;
    state.offers = await offersRes.json();
    state.transactions = await txRes.json();
    state.rewards = await rewardsRes.json();
    state.investment = await invRes.json();

    state.referral = referralRes.ok ? await referralRes.json() : null;
    state.supportTickets = supportRes.ok ? await supportRes.json() : [];
    state.reviewsByMerchant = reviewsRes.ok ? mapReviewsByMerchant(await reviewsRes.json()) : {};

    qs("#sessionPill").textContent = `Signed in: ${safeText(me.email)}`;
    renderAll();

    if (me.location_consent) {
      startLocationTracking();
    } else {
      stopLocationTracking();
    }
  }

  async function activateOffer(offerId) {
    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/offers/${offerId}/activate`, {
      method: "POST",
    });
    showStatus(body.message || "Offer activated.", false);
  }

  async function simulatePurchase(offerId, amount) {
    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/transactions`, {
      method: "POST",
      body: JSON.stringify({
        offer_id: offerId,
        amount,
        currency: "USD",
        rail_type: "card_linked",
      }),
    });
    showStatus(body.message || "Purchase simulated.", false);
  }

  async function settleRewards() {
    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/rewards/settle`, {
      method: "POST",
    });
    showStatus(body.message || "Pending rewards settled.", false);
  }

  async function redeemRewards() {
    const availableIds = (state.rewards || [])
      .filter((r) => String(r.state || "").toLowerCase() === "available" && String(r.reward_type || "").toLowerCase() === "cash")
      .map((r) => r.id);

    if (!availableIds.length) {
      showStatus("No available cash rewards to redeem.", true);
      return;
    }

    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/rewards/redeem`, {
      method: "POST",
      body: JSON.stringify({ reward_ids: availableIds }),
    });
    showStatus(body.message || "Rewards redeemed.", false);
  }

  async function convertCashToStocks(amount) {
    const normalized = Math.round(amount);
    if (normalized < 25 || normalized % 25 !== 0) {
      throw new Error("Conversion must be at least $25 and in $25 increments.");
    }

    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/investments/convert`, {
      method: "POST",
      body: JSON.stringify({ amount_usd: normalized }),
    });
    state.investment = body;
    showStatus(`Converted ${fmtUsd(normalized)} to Stock Vault.`, false);
  }

  async function updateUserPreferences(payload) {
    const { body } = await apiJson(`${config.api_v1_prefix}/auth/me`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    state.me = body;
    renderPreferences();
    updateNearbyBanner();
    return body;
  }

  async function trackReferralShare(channel) {
    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/referrals/share`, {
      method: "POST",
      body: JSON.stringify({ channel }),
    });
    state.referral = body;
    renderReferral();
  }

  async function askAiAssistant(message) {
    const prompt = String(message || "").trim();
    if (!prompt) return;

    const history = (state.aiConversation || [])
      .slice(-10)
      .map((entry) => ({
        role: String(entry.role || "").toLowerCase() === "user" ? "user" : "assistant",
        content: safeText(entry.text || "").slice(0, 1500),
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
          context: "consumer",
          history,
        }),
      });

      state.aiModel = body.model || null;
      state.aiConversation = (state.aiConversation || []).concat([
        { role: "assistant", text: safeText(body.answer || "No response.") },
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

  async function createSupportTicket(payload) {
    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/support/tickets`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showStatus(body.message || "Ticket created.", false);
  }

  async function refreshSupportTickets() {
    const res = await apiFetch(`${config.api_v1_prefix}/consumer/support/tickets`);
    if (!res.ok) throw new Error(`Support refresh failed (${res.status})`);
    state.supportTickets = await res.json();
    renderSupportTickets();
  }

  function renderHeartButtons(selectedHearts, onSelect) {
    const row = document.createElement("div");
    row.className = "heart-row";

    const selected = clampHearts(selectedHearts);
    for (let i = 1; i <= 5; i += 1) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `heart-btn${i <= selected ? " is-active" : ""}`;
      btn.textContent = i <= selected ? "♥" : "♡";
      btn.setAttribute("aria-label", `${i} heart${i > 1 ? "s" : ""}`);
      btn.onclick = () => onSelect(i);
      row.appendChild(btn);
    }
    return row;
  }

  async function upsertConsumerReview(payload) {
    const { body } = await apiJson(`${config.api_v1_prefix}/consumer/reviews`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return body;
  }

  async function listConsumerReviewsMine() {
    const res = await apiFetch(`${config.api_v1_prefix}/consumer/reviews?mine_only=true`);
    if (!res.ok) throw new Error(`Failed /consumer/reviews (${res.status})`);
    const rows = await res.json();
    return Array.isArray(rows) ? rows : [];
  }

  async function submitQuickOfferReview(offer, hearts) {
    const merchantId = normalizedMerchantId(offer);
    if (!merchantId) {
      throw new Error("This offer is missing merchant metadata for rating.");
    }

    const existing = reviewForOffer(offer);
    const overall = Math.max(1, clampHearts(hearts));
    const review = await upsertConsumerReview({
      offer_id: Number(offer.id),
      merchant_id: merchantId,
      overall_hearts: overall,
      plates_hearts: Math.max(1, clampHearts(existing ? existing.plates_hearts : overall)),
      sides_hearts: Math.max(1, clampHearts(existing ? existing.sides_hearts : overall)),
      umami_hearts: Math.max(1, clampHearts(existing ? existing.umami_hearts : overall)),
      review_text: existing && existing.review_text ? String(existing.review_text) : "",
    });

    state.reviewsByMerchant[String(merchantId)] = review;
    await refreshConsumerData({ offersOnly: true });
    showStatus("Rating saved.", false);
  }

  function renderReviewModalHearts() {
    const host = qs("#reviewOverallHearts");
    host.innerHTML = "";
    host.appendChild(
      renderHeartButtons(state.reviewModalOverall, (value) => {
        state.reviewModalOverall = clampHearts(value);
        renderReviewModalHearts();
      })
    );
  }

  function openReviewModal(offer) {
    const merchantId = normalizedMerchantId(offer);
    if (!merchantId) {
      showStatus("This offer is missing merchant metadata for review.", true);
      return;
    }

    const merchantName = safeText(offer.merchant_name || splitTitle(offer).merchant || "Merchant");
    const existing = reviewForOffer(offer);
    const fallbackOverall = clampHearts(offer.my_review_hearts || 5);

    state.reviewModalOffer = offer;
    state.reviewModalOverall = Math.max(1, clampHearts(existing ? existing.overall_hearts : fallbackOverall));

    qs("#reviewMerchantName").textContent = merchantName;
    qs("#reviewPlatesInput").value = String(clampHearts(existing ? existing.plates_hearts : state.reviewModalOverall));
    qs("#reviewSidesInput").value = String(clampHearts(existing ? existing.sides_hearts : state.reviewModalOverall));
    qs("#reviewUmamiInput").value = String(clampHearts(existing ? existing.umami_hearts : state.reviewModalOverall));
    qs("#reviewTextInput").value = safeText(existing ? existing.review_text : "");
    qs("#reviewHint").textContent = "";

    renderReviewModalHearts();
    qs("#reviewModal").hidden = false;
  }

  function closeReviewModal() {
    qs("#reviewModal").hidden = true;
    state.reviewModalOffer = null;
    qs("#reviewHint").textContent = "";
  }

  async function saveDetailedReview() {
    const offer = state.reviewModalOffer;
    if (!offer) return;

    const merchantId = normalizedMerchantId(offer);
    if (!merchantId) {
      showStatus("This offer is missing merchant metadata for review.", true);
      return;
    }

    const saveBtn = qs("#reviewSaveBtn");
    const hint = qs("#reviewHint");
    saveBtn.disabled = true;
    hint.textContent = "Saving...";

    try {
      const payload = {
        offer_id: Number(offer.id),
        merchant_id: merchantId,
        overall_hearts: Math.max(1, clampHearts(state.reviewModalOverall)),
        plates_hearts: Math.max(1, clampHearts(Number(qs("#reviewPlatesInput").value))),
        sides_hearts: Math.max(1, clampHearts(Number(qs("#reviewSidesInput").value))),
        umami_hearts: Math.max(1, clampHearts(Number(qs("#reviewUmamiInput").value))),
        review_text: safeText(qs("#reviewTextInput").value).trim(),
      };

      const review = await upsertConsumerReview(payload);
      state.reviewsByMerchant[String(merchantId)] = review;
      closeReviewModal();
      await refreshConsumerData({ offersOnly: true });
      showStatus("Review saved.", false);
    } catch (err) {
      hint.textContent = err.message || String(err);
      showStatus(err.message || String(err), true);
    } finally {
      saveBtn.disabled = false;
      if (hint.textContent === "Saving...") {
        hint.textContent = "";
      }
    }
  }

  function openOfferCodeModal(offer) {
    const modal = qs("#offerCodeModal");
    const details = qs("#offerCodeDetails");

    const code = offerCodeFor(offer);
    const payload = offerQrPayload(code);

    const merchantName = safeText(offer.merchant_name || splitTitle(offer).merchant || "Merchant");

    details.innerHTML = `
      <div class="list-item">
        <strong>${merchantName}</strong>
        <div class="small muted">${safeText(offer.terms_text)}</div>
        <div class="small muted">Reward: ${fmtPct(offer.reward_rate_cash)} cash / ${fmtPct(offer.reward_rate_stock)} stock</div>
        <div class="small muted">Expires ${fmtDateTime(offer.ends_at)}</div>
      </div>
    `;

    qs("#offerCodeValue").textContent = code;
    qs("#offerCodeHint").textContent = offer.is_activated
      ? "Scan to redeem at checkout"
      : "Activate this offer before checkout redemption";
    qs("#offerQrImage").src = qrImageUrl(payload);

    modal.hidden = false;
  }

  function closeOfferCodeModal() {
    qs("#offerCodeModal").hidden = true;
  }

  function startLocationTracking() {
    if (locationWatchId != null) return;
    if (!navigator.geolocation) return;

    locationWatchId = navigator.geolocation.watchPosition(
      async (pos) => {
        state.currentLatitude = Number(pos.coords.latitude);
        state.currentLongitude = Number(pos.coords.longitude);
        updateNearbyBanner();

        const now = Date.now();
        if ((now - state.lastGeoOffersRefreshAt) < 60_000) return;
        state.lastGeoOffersRefreshAt = now;

        try {
          await refreshConsumerData({ offersOnly: true });
        } catch (_err) {
          // Silent background update failure.
        }
      },
      () => {
        // Permission denied/unavailable.
        stopLocationTracking();
      },
      {
        enableHighAccuracy: false,
        timeout: 10_000,
        maximumAge: 60_000,
      }
    );
  }

  function stopLocationTracking() {
    if (locationWatchId != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(locationWatchId);
    }
    locationWatchId = null;
    state.currentLatitude = null;
    state.currentLongitude = null;
  }

  function openShareDialog(url, code) {
    const text = `Join me on PerkNation and get rewards. Use my referral code ${code}: ${url}`;

    if (navigator.share) {
      navigator
        .share({ text, url })
        .then(async () => {
          await trackReferralShare("share_sheet");
          showStatus("Referral link shared.", false);
        })
        .catch(async () => {
          try {
            await navigator.clipboard.writeText(text);
            await trackReferralShare("copy");
            showStatus("Share canceled. Link copied to clipboard.", false);
          } catch {
            showStatus("Share canceled.", true);
          }
        });
      return;
    }

    navigator.clipboard
      .writeText(text)
      .then(async () => {
        await trackReferralShare("copy");
        showStatus("Referral link copied to clipboard.", false);
      })
      .catch(() => {
        showStatus("Could not copy link. Please copy manually.", true);
      });
  }

  async function handleSignUp(ev) {
    ev.preventDefault();

    const fullName = qs("#signUpNameInput").value.trim();
    const email = qs("#signUpEmailInput").value.trim();
    const phone = qs("#signUpPhoneInput").value.trim();
    const password = qs("#signUpPasswordInput").value;
    const confirm = qs("#signUpPasswordConfirmInput").value;

    const hint = qs("#signUpHint");
    const submitBtn = qs("#signUpSubmitBtn");

    if (!fullName || !email || !password) {
      showStatus("Full name, email, and password are required.", true);
      return;
    }
    if (password.length < 6) {
      showStatus("Password must be at least 6 characters.", true);
      return;
    }
    if (password !== confirm) {
      showStatus("Passwords do not match.", true);
      return;
    }

    submitBtn.disabled = true;
    hint.textContent = "Creating account...";

    try {
      const envelope = await supabaseSignUp(email, password, {
        full_name: fullName,
        phone: phone || null,
        role: "consumer",
        reward_preference: "cash",
        notifications_enabled: true,
        location_consent: true,
        alert_radius_miles: 5,
        notification_categories: "restaurant,gas,retail",
      });

      const session = envelopeToSession(email, envelope);
      if (session) {
        saveSession(session);
        updateAuthUi();
        await refreshConsumerData();
        resetAiConversation();
        renderAiAssistant();
        showStatus("Account created and signed in.", false);
        state.pendingVerificationEmail = "";
        state.pendingVerificationPassword = "";
        qs("#verificationActions").hidden = true;
      } else {
        state.pendingVerificationEmail = email;
        state.pendingVerificationPassword = password;
        qs("#verificationActions").hidden = false;
        qs("#verificationHint").textContent = "Check your email for a confirmation link.";
        showStatus("Account created. Check email to verify, then log in.", false);
        switchAuthMode("login");
      }
    } catch (err) {
      const msg = err.message || String(err);
      if (isEmailRateLimitError(msg)) {
        try {
          const signInEnvelope = await supabaseSignIn(email, password);
          const session = envelopeToSession(email, signInEnvelope);
          if (!session) throw new Error("Supabase did not return an access token.");
          saveSession(session);
          updateAuthUi();
          await refreshConsumerData();
          resetAiConversation();
          renderAiAssistant();
          showStatus(
            "Signup emails are temporarily rate-limited, but your account already exists and was signed in.",
            false
          );
          state.pendingVerificationEmail = "";
          state.pendingVerificationPassword = "";
          qs("#verificationActions").hidden = true;
          return;
        } catch (signInErr) {
          const signInMsg = String((signInErr && signInErr.message) || "").toLowerCase();
          if (signInMsg.includes("not verified") || signInMsg.includes("not confirmed") || signInMsg.includes("confirm")) {
            state.pendingVerificationEmail = email;
            state.pendingVerificationPassword = password;
            qs("#verificationActions").hidden = false;
            qs("#verificationHint").textContent = "Account exists but email is not verified yet.";
            showStatus(
              "Account exists, but email is not verified yet. Wait a few minutes, then use “Resend verification email.”",
              true
            );
            return;
          }
          if (signInMsg.includes("invalid login credentials") || signInMsg.includes("email or password")) {
            showStatus(
              "Signup email sending is temporarily rate-limited. This email may already exist with a different password. Try Log in instead.",
              true
            );
            switchAuthMode("login");
            return;
          }
          showStatus(
            "Signup email sending is temporarily rate-limited. Please wait a few minutes and try again.",
            true
          );
          return;
        }
      }
      showStatus(msg, true);
    } finally {
      submitBtn.disabled = false;
      hint.textContent = "";
    }
  }

  async function handleLogIn(ev) {
    ev.preventDefault();
    const email = qs("#emailInput").value.trim();
    const password = qs("#passwordInput").value;

    const hint = qs("#loginHint");
    const loginBtn = qs("#loginBtn");
    loginBtn.disabled = true;
    hint.textContent = "Signing in...";

    try {
      const envelope = await supabaseSignIn(email, password);
      const session = envelopeToSession(email, envelope);
      if (!session) throw new Error("Supabase did not return an access token.");

      saveSession(session);
      updateAuthUi();
      await refreshConsumerData();
      resetAiConversation();
      renderAiAssistant();
      showStatus("Signed in.", false);
      state.pendingVerificationEmail = "";
      state.pendingVerificationPassword = "";
      qs("#verificationActions").hidden = true;
    } catch (err) {
      const msg = err.message || String(err);
      if (
        msg.toLowerCase().includes("not confirmed") ||
        msg.toLowerCase().includes("not verified") ||
        msg.toLowerCase().includes("confirm")
      ) {
        state.pendingVerificationEmail = email;
        state.pendingVerificationPassword = password;
        qs("#verificationActions").hidden = false;
        qs("#verificationHint").textContent = "Email not verified yet.";
      }
      showStatus(msg, true);
    } finally {
      loginBtn.disabled = false;
      hint.textContent = "";
    }
  }

  async function handleResendVerification() {
    const email = (state.pendingVerificationEmail || "").trim();
    if (!email) {
      showStatus("No pending email to verify.", true);
      return;
    }

    try {
      await supabaseResendSignupConfirmation(email);
      showStatus("Confirmation email sent.", false);
    } catch (err) {
      showStatus(err.message || String(err), true);
    }
  }

  async function handleVerifyThenLogin() {
    const email = (state.pendingVerificationEmail || "").trim();
    const password = state.pendingVerificationPassword || "";
    if (!email || !password) {
      showStatus("Missing verification login data.", true);
      return;
    }

    try {
      const envelope = await supabaseSignIn(email, password);
      const session = envelopeToSession(email, envelope);
      if (!session) throw new Error("Supabase did not return an access token.");
      saveSession(session);
      updateAuthUi();
      await refreshConsumerData();
      resetAiConversation();
      renderAiAssistant();
      showStatus("Signed in after verification.", false);
      state.pendingVerificationEmail = "";
      state.pendingVerificationPassword = "";
      qs("#verificationActions").hidden = true;
    } catch (err) {
      showStatus(err.message || String(err), true);
    }
  }

  function bindEvents() {
    qs("#statusDismissBtn").addEventListener("click", hideStatus);

    qs("#signUpTabBtn").addEventListener("click", () => switchAuthMode("signup"));
    qs("#logInTabBtn").addEventListener("click", () => switchAuthMode("login"));

    qs("#signUpForm").addEventListener("submit", handleSignUp);
    qs("#loginForm").addEventListener("submit", handleLogIn);

    qs("#resendVerificationBtn").addEventListener("click", handleResendVerification);
    qs("#verifyThenLoginBtn").addEventListener("click", handleVerifyThenLogin);

    qs("#logoutBtn").addEventListener("click", () => {
      clearSession();
      state.me = null;
      state.offers = [];
      state.transactions = [];
      state.rewards = [];
      state.investment = null;
      state.referral = null;
      state.supportTickets = [];
      state.reviewsByMerchant = {};
      state.reviewModalOffer = null;
      state.reviewModalOverall = 5;
      resetAiConversation();
      stopLocationTracking();
      updateAuthUi();
      switchAuthMode("login");
      renderAiAssistant();
      showStatus("Signed out.", false);
    });

    qs("#refreshAllBtn").addEventListener("click", async () => {
      try {
        await refreshConsumerData();
        showStatus("Refreshed.", false);
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#testBackendBtn").addEventListener("click", async () => {
      try {
        const res = await fetch(`${config.api_v1_prefix}/health`);
        showStatus(res.ok ? "Backend reachable." : `Backend check failed (${res.status})`, !res.ok);
      } catch (err) {
        showStatus(`Backend check failed: ${err.message || err}`, true);
      }
    });

    qsa(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchPanel(btn.dataset.view));
    });

    qs("#settleBtn").addEventListener("click", async () => {
      try {
        await settleRewards();
        await refreshConsumerData();
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#redeemBtn").addEventListener("click", async () => {
      try {
        await redeemRewards();
        await refreshConsumerData();
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#convertMinusBtn").addEventListener("click", () => {
      state.convertAmount = Math.max(25, state.convertAmount - 25);
      updateKpis();
    });

    qs("#convertPlusBtn").addEventListener("click", () => {
      state.convertAmount += 25;
      updateKpis();
    });

    qs("#convertBtn").addEventListener("click", async () => {
      try {
        await convertCashToStocks(state.convertAmount);
        await refreshConsumerData();
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#copyReferralBtn").addEventListener("click", async () => {
      const url = safeText(state.referral && state.referral.invite_url);
      if (!url) {
        showStatus("No referral URL available.", true);
        return;
      }
      try {
        await navigator.clipboard.writeText(url);
        await trackReferralShare("copy");
        showStatus("Referral URL copied.", false);
      } catch {
        showStatus("Unable to copy referral URL.", true);
      }
    });

    qs("#shareReferralBtn").addEventListener("click", () => {
      if (!state.referral) {
        showStatus("Referral profile unavailable.", true);
        return;
      }
      openShareDialog(state.referral.invite_url, state.referral.referral_code || "PKN");
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
        showStatus(err.message || String(err), true);
      }
    });

    qs("#aiClearBtn").addEventListener("click", () => {
      resetAiConversation();
      renderAiAssistant();
      qs("#aiHint").textContent = "";
    });

    qs("#refreshTicketsBtn").addEventListener("click", async () => {
      try {
        await refreshSupportTickets();
        showStatus("Support tickets refreshed.", false);
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#missingRewardCaseBtn").addEventListener("click", async () => {
      try {
        await createSupportTicket({
          txn_id: null,
          category: "missing_reward",
          subject: "Missing reward case",
          message: "I completed a purchase but did not receive the expected reward.",
        });
        await refreshSupportTickets();
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#supportTicketForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const category = qs("#ticketCategoryInput").value.trim() || "general";
      const subject = qs("#ticketSubjectInput").value.trim();
      const message = qs("#ticketMessageInput").value.trim();
      const txnIdText = qs("#ticketTxnIdInput").value.trim();
      const txnId = txnIdText ? Number(txnIdText) : null;

      if (!subject || !message) {
        showStatus("Subject and message are required.", true);
        return;
      }

      try {
        await createSupportTicket({
          txn_id: Number.isFinite(txnId) ? txnId : null,
          category,
          subject,
          message,
        });
        qs("#supportTicketForm").reset();
        qs("#ticketCategoryInput").value = "general";
        await refreshSupportTickets();
      } catch (err) {
        showStatus(err.message || String(err), true);
      }
    });

    qs("#locationConsentToggle").addEventListener("change", async (ev) => {
      const next = !!ev.target.checked;
      try {
        await updateUserPreferences({ location_consent: next });
        if (next) startLocationTracking();
        else stopLocationTracking();
        showStatus("Location preference updated.", false);
      } catch (err) {
        ev.target.checked = !next;
        showStatus(err.message || String(err), true);
      }
    });

    qs("#notificationsToggle").addEventListener("change", async (ev) => {
      const next = !!ev.target.checked;
      try {
        await updateUserPreferences({ notifications_enabled: next });
        showStatus("Notification preference updated.", false);
      } catch (err) {
        ev.target.checked = !next;
        showStatus(err.message || String(err), true);
      }
    });

    qsa("#radiusChips .chip").forEach((chip) => {
      chip.addEventListener("click", async () => {
        const radius = normalizeRadius(chip.dataset.radius);
        try {
          await updateUserPreferences({ alert_radius_miles: radius });
          renderPreferences();
          showStatus("Geo alert radius updated.", false);
        } catch (err) {
          showStatus(err.message || String(err), true);
        }
      });
    });

    qsa("#categoryChips .chip").forEach((chip) => {
      chip.addEventListener("click", async () => {
        if (!state.me) return;
        const key = String(chip.dataset.category || "").toLowerCase();
        const set = parseNotificationCategories(state.me.notification_categories);
        if (set.has(key)) set.delete(key);
        else set.add(key);

        try {
          await updateUserPreferences({ notification_categories: serializeNotificationCategories(set) });
          renderPreferences();
          showStatus("Notification categories updated.", false);
        } catch (err) {
          showStatus(err.message || String(err), true);
        }
      });
    });

    qs("#offerCodeCloseBtn").addEventListener("click", closeOfferCodeModal);
    qsa("[data-modal-close]").forEach((el) => {
      el.addEventListener("click", closeOfferCodeModal);
    });

    qs("#reviewSaveBtn").addEventListener("click", saveDetailedReview);
    qs("#reviewCancelBtn").addEventListener("click", closeReviewModal);
    qs("#reviewCloseBtn").addEventListener("click", closeReviewModal);
    qsa("[data-review-close]").forEach((el) => {
      el.addEventListener("click", closeReviewModal);
    });
  }

  async function bootstrapSignedIn() {
    state.session = loadSession();
    updateAuthUi();

    if (!state.session) {
      switchAuthMode("signup");
      return;
    }

    try {
      await refreshConsumerData();
    } catch (err) {
      showStatus(err.message || String(err), true);
    }
  }

  window.addEventListener("DOMContentLoaded", async () => {
    resetAiConversation();
    bindEvents();
    switchPanel("discover");
    renderAiAssistant();

    try {
      await loadConfig();
      await bootstrapSignedIn();
    } catch (err) {
      showStatus(err.message || String(err), true);
    }
  });
})();
