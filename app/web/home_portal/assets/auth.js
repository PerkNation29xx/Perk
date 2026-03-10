(function () {
  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  const USER_SESSION_KEY = "pk_user_portal_session_v2";
  const MERCHANT_SESSION_KEY = "pk_merchant_portal_session_v1";

  const state = {
    apiPrefix: "/api/v1",
    supabaseUrl: "",
    supabaseAnonKey: "",
  };

  function showMessage(el, message, isError) {
    if (!el) return;
    el.hidden = !message;
    if (!message) {
      el.textContent = "";
      return;
    }

    el.textContent = message;
    el.style.borderStyle = "solid";
    el.style.borderWidth = "1px";
    el.style.borderColor = isError
      ? "rgba(195,63,22,.45)"
      : "rgba(41,166,91,.45)";
    el.style.background = isError
      ? "rgba(195,63,22,.08)"
      : "rgba(41,166,91,.10)";
  }

  function humanizeError(raw) {
    const message = String(raw || "").trim();
    const lower = message.toLowerCase();

    if (!message) {
      return "Request failed. Please try again.";
    }

    if (
      lower.includes("invalid login credentials") ||
      lower.includes("invalid credentials")
    ) {
      return "Email or password is incorrect.";
    }

    if (
      lower.includes("not confirmed") ||
      lower.includes("not verified") ||
      lower.includes("confirm your email")
    ) {
      return "Email is not verified yet. Check your inbox, then sign in again.";
    }

    if (
      lower.includes("over_email_send_rate_limit") ||
      lower.includes("email rate limit exceeded")
    ) {
      return "Too many sign-up emails were sent recently. Please wait a few minutes and try again.";
    }

    if (
      lower.includes("already registered") ||
      lower.includes("email address has already been registered")
    ) {
      return "This email already has an account. Use Login instead.";
    }

    if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
      return "Could not reach the server. Check your connection and try again.";
    }

    return message;
  }

  function normalizeSupabaseEnvelope(email, envelope) {
    if (!envelope || typeof envelope !== "object") return null;

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

  function decodeJwtRole(token) {
    try {
      const parts = String(token || "").split(".");
      if (parts.length < 2) return null;
      const payloadBase64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const decoded = atob(payloadBase64.padEnd(Math.ceil(payloadBase64.length / 4) * 4, "="));
      const payload = JSON.parse(decoded);
      const role = payload && payload.role;
      return role ? String(role).toLowerCase() : null;
    } catch {
      return null;
    }
  }

  async function loadConfig() {
    try {
      const res = await fetch("/web/config", { cache: "no-store" });
      if (!res.ok) return;
      const body = await res.json();
      if (body && typeof body === "object") {
        if (typeof body.api_v1_prefix === "string" && body.api_v1_prefix.trim()) {
          state.apiPrefix = body.api_v1_prefix.trim();
        }
        if (typeof body.supabase_url === "string") {
          state.supabaseUrl = body.supabase_url.trim();
        }
        if (typeof body.supabase_anon_key === "string") {
          state.supabaseAnonKey = body.supabase_anon_key.trim();
        }
      }
    } catch {
      // Keep defaults.
    }
  }

  function assertConfig() {
    if (!state.supabaseUrl || !state.supabaseAnonKey) {
      throw new Error("Account service is not configured on the backend. Please contact support.");
    }
  }

  async function parseErrorBody(res) {
    try {
      const json = await res.json();
      return json.error_description || json.error || json.detail || JSON.stringify(json);
    } catch {
      try {
        return await res.text();
      } catch {
        return `Request failed (${res.status})`;
      }
    }
  }

  async function supabaseSignIn(email, password) {
    assertConfig();
    const url = `${state.supabaseUrl}/auth/v1/token?grant_type=password`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        apikey: state.supabaseAnonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      throw new Error(await parseErrorBody(res));
    }
    return await res.json();
  }

  async function supabaseSignUp(email, password, metadata) {
    assertConfig();
    const url = `${state.supabaseUrl}/auth/v1/signup`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        apikey: state.supabaseAnonKey,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email,
        password,
        options: {
          data: metadata || {},
        },
      }),
    });
    if (!res.ok) {
      throw new Error(await parseErrorBody(res));
    }
    return await res.json();
  }

  async function fetchMe(accessToken) {
    const res = await fetch(`${state.apiPrefix}/auth/me`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });
    if (!res.ok) {
      throw new Error(await parseErrorBody(res));
    }
    return await res.json();
  }

  function roleToLabel(role) {
    if (role === "consumer") return "User";
    if (role === "merchant") return "Merchant";
    if (role === "admin") return "Admin";
    return role || "Unknown";
  }

  function saveSessionForRole(role, session) {
    if (!session || !session.access_token) return;

    if (role === "merchant") {
      localStorage.setItem(MERCHANT_SESSION_KEY, JSON.stringify(session));
      localStorage.removeItem(USER_SESSION_KEY);
      return;
    }

    if (role === "consumer") {
      localStorage.setItem(USER_SESSION_KEY, JSON.stringify(session));
      localStorage.removeItem(MERCHANT_SESSION_KEY);
      return;
    }

    // For admin/unknown we keep both clear to avoid stale role state.
    localStorage.removeItem(USER_SESSION_KEY);
    localStorage.removeItem(MERCHANT_SESSION_KEY);
  }

  function portalRouteForRole(role) {
    if (role === "merchant") return "/merchant";
    if (role === "admin") return "/admin";
    return "/user";
  }

  function setActiveRole(buttons, activeRole, attrName) {
    buttons.forEach((btn) => {
      const role = btn.getAttribute(attrName);
      const active = role === activeRole;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function bindLoginPage() {
    const form = qs("#loginForm");
    if (!form) return;

    const message = qs("#loginMessage");
    const submitBtn = qs("#loginSubmitBtn");
    const roleInput = qs("#loginRoleInput");
    const roleButtons = qsa("[data-login-role]");

    roleButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const role = btn.getAttribute("data-login-role") || "consumer";
        roleInput.value = role;
        setActiveRole(roleButtons, role, "data-login-role");
        showMessage(message, "", false);
      });
    });

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();

      const selectedRole = (roleInput.value || "consumer").toLowerCase();
      const email = String(qs("#loginEmailInput")?.value || "").trim();
      const password = String(qs("#loginPasswordInput")?.value || "");

      if (!email || !password) {
        showMessage(message, "Email and password are required.", true);
        return;
      }

      submitBtn.disabled = true;
      showMessage(message, "Signing in...", false);

      try {
        const envelope = await supabaseSignIn(email, password);
        const session = normalizeSupabaseEnvelope(email, envelope);
        if (!session) {
          throw new Error("Login succeeded but no access token was returned.");
        }

        let me = null;
        try {
          me = await fetchMe(session.access_token);
        } catch {
          // Fallback to JWT role when /auth/me is temporarily unavailable.
        }

        const actualRole =
          (me && typeof me.role === "string" && me.role.toLowerCase()) ||
          decodeJwtRole(session.access_token) ||
          "consumer";

        if (selectedRole === "consumer" && actualRole !== "consumer") {
          showMessage(
            message,
            `This account is ${roleToLabel(actualRole)}. Select ${roleToLabel(actualRole)} to continue.`,
            true
          );
          return;
        }

        if (selectedRole === "merchant" && actualRole !== "merchant") {
          showMessage(
            message,
            `This account is ${roleToLabel(actualRole)}. Select ${roleToLabel(actualRole)} to continue.`,
            true
          );
          return;
        }

        saveSessionForRole(actualRole, session);
        showMessage(message, "Signed in. Redirecting...", false);
        window.location.href = portalRouteForRole(actualRole);
      } catch (err) {
        showMessage(message, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  function validatePasswordPair(password, confirm) {
    if (String(password || "").length < 8) {
      return "Password must be at least 8 characters.";
    }
    if (password !== confirm) {
      return "Passwords do not match.";
    }
    return "";
  }

  function bindCreateAccountPage() {
    const consumerForm = qs("#consumerRegisterForm");
    const merchantForm = qs("#merchantRegisterForm");
    if (!consumerForm || !merchantForm) return;

    const roleButtons = qsa("[data-register-role]");

    function setRegisterRole(role) {
      const normalized = role === "merchant" ? "merchant" : "consumer";
      consumerForm.hidden = normalized !== "consumer";
      merchantForm.hidden = normalized !== "merchant";
      setActiveRole(roleButtons, normalized, "data-register-role");
    }

    roleButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        setRegisterRole(btn.getAttribute("data-register-role") || "consumer");
      });
    });

    consumerForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();

      const message = qs("#consumerRegisterMessage");
      const submitBtn = qs("#consumerCreateBtn");

      const fullName = String(qs("#consumerFullNameInput")?.value || "").trim();
      const email = String(qs("#consumerEmailInput")?.value || "").trim();
      const phone = String(qs("#consumerPhoneInput")?.value || "").trim();
      const password = String(qs("#consumerPasswordInput")?.value || "");
      const confirm = String(qs("#consumerPasswordConfirmInput")?.value || "");

      if (!fullName || !email) {
        showMessage(message, "Full name and email are required.", true);
        return;
      }

      const passwordError = validatePasswordPair(password, confirm);
      if (passwordError) {
        showMessage(message, passwordError, true);
        return;
      }

      submitBtn.disabled = true;
      showMessage(message, "Creating user account...", false);

      try {
        await supabaseSignUp(email, password, {
          full_name: fullName,
          phone: phone || null,
          role: "consumer",
          reward_preference: "cash",
          notifications_enabled: true,
          location_consent: true,
          alert_radius_miles: 5,
          notification_categories: "restaurant,gas,retail",
        });

        showMessage(message, "Account created. Check email to verify, then use Login.", false);
        consumerForm.reset();
      } catch (err) {
        showMessage(message, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        submitBtn.disabled = false;
      }
    });

    merchantForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();

      const message = qs("#merchantRegisterMessage");
      const submitBtn = qs("#merchantCreateBtn");

      const businessName = String(qs("#merchantBusinessNameInput")?.value || "").trim();
      const contactName = String(qs("#merchantContactNameInput")?.value || "").trim();
      const email = String(qs("#merchantEmailInput")?.value || "").trim();
      const phone = String(qs("#merchantPhoneInput")?.value || "").trim();
      const password = String(qs("#merchantPasswordInput")?.value || "");
      const confirm = String(qs("#merchantPasswordConfirmInput")?.value || "");

      if (!businessName || !contactName || !email) {
        showMessage(message, "Business name, contact name, and email are required.", true);
        return;
      }

      const passwordError = validatePasswordPair(password, confirm);
      if (passwordError) {
        showMessage(message, passwordError, true);
        return;
      }

      submitBtn.disabled = true;
      showMessage(message, "Creating merchant account...", false);

      try {
        await supabaseSignUp(email, password, {
          full_name: `${contactName} (${businessName})`,
          business_name: businessName,
          phone: phone || null,
          role: "merchant",
          reward_preference: "cash",
          notifications_enabled: true,
          location_consent: true,
          alert_radius_miles: 5,
          notification_categories: "restaurant,gas,retail",
        });

        showMessage(message, "Merchant account created. Check email to verify, then use Login.", false);
        merchantForm.reset();
      } catch (err) {
        showMessage(message, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        submitBtn.disabled = false;
      }
    });

    setRegisterRole("consumer");
  }

  async function init() {
    await loadConfig();
    bindLoginPage();
    bindCreateAccountPage();
  }

  init();
})();
