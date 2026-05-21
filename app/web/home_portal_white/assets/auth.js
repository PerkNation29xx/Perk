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
    authEmailRedirectUrl: `${window.location.origin}/login`,
    authPasswordResetRedirectUrl: `${window.location.origin}/reset-password`,
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
        if (typeof body.auth_email_redirect_url === "string" && body.auth_email_redirect_url.trim()) {
          state.authEmailRedirectUrl = body.auth_email_redirect_url.trim();
        }
        if (typeof body.auth_password_reset_redirect_url === "string" && body.auth_password_reset_redirect_url.trim()) {
          state.authPasswordResetRedirectUrl = body.auth_password_reset_redirect_url.trim();
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

  function withRedirectParam(url, redirectTo) {
    if (!redirectTo) return url;
    try {
      const parsed = new URL(url, window.location.origin);
      parsed.searchParams.set("redirect_to", redirectTo);
      return parsed.toString();
    } catch {
      return url;
    }
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

  async function submitFormToBackend(formType, data) {
    const response = await fetch(`/v1/web/forms/${encodeURIComponent(formType)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        source_page: window.location.pathname,
        data,
      }),
    });

    const payload = await readJsonResponse(response);
    if (!response.ok) {
      const detail = payload.detail || payload.message || `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return payload;
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
    const redirectTo = state.authEmailRedirectUrl;
    const url = withRedirectParam(`${state.supabaseUrl}/auth/v1/signup`, redirectTo);
    const profileData = metadata || {};
    const res = await fetch(url, {
      method: "POST",
      headers: {
        apikey: state.supabaseAnonKey,
        "Content-Type": "application/json",
        redirect_to: redirectTo,
      },
      body: JSON.stringify({
        email,
        password,
        options: {
          data: profileData,
          emailRedirectTo: redirectTo,
          redirectTo,
        },
        data: profileData,
      }),
    });
    if (!res.ok) {
      throw new Error(await parseErrorBody(res));
    }
    return await res.json();
  }

  async function supabaseRequestPasswordReset(email) {
    assertConfig();
    const redirectTo = state.authPasswordResetRedirectUrl;
    const url = withRedirectParam(`${state.supabaseUrl}/auth/v1/recover`, redirectTo);
    const res = await fetch(url, {
      method: "POST",
      headers: {
        apikey: state.supabaseAnonKey,
        "Content-Type": "application/json",
        redirect_to: redirectTo,
      },
      body: JSON.stringify({
        email,
        options: {
          emailRedirectTo: redirectTo,
          redirectTo,
        },
      }),
    });
    if (!res.ok) {
      throw new Error(await parseErrorBody(res));
    }
    return await readJsonResponse(res);
  }

  async function supabaseUpdatePassword(accessToken, password) {
    assertConfig();
    const url = `${state.supabaseUrl}/auth/v1/user`;
    const res = await fetch(url, {
      method: "PUT",
      headers: {
        apikey: state.supabaseAnonKey,
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      throw new Error(await parseErrorBody(res));
    }
    return await readJsonResponse(res);
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

  function readSafeNextPath() {
    try {
      const params = new URLSearchParams(window.location.search || "");
      const raw = String(params.get("next") || "").trim();
      if (!raw) return "";
      if (!raw.startsWith("/")) return "";
      if (raw.startsWith("//")) return "";
      if (raw.includes("://")) return "";
      return raw;
    } catch {
      return "";
    }
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
    const forgotBtn = qs("#forgotPasswordBtn");
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
        window.location.href = readSafeNextPath() || portalRouteForRole(actualRole);
      } catch (err) {
        showMessage(message, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        submitBtn.disabled = false;
      }
    });

    if (forgotBtn) {
      forgotBtn.addEventListener("click", async () => {
        const email = String(qs("#loginEmailInput")?.value || "").trim();
        if (!email) {
          showMessage(message, "Enter your email, then tap Forgot password.", true);
          return;
        }

        forgotBtn.disabled = true;
        showMessage(message, "Sending password reset email...", false);
        try {
          await supabaseRequestPasswordReset(email);
          showMessage(
            message,
            "Password reset email sent. Check your inbox for a secure reset link.",
            false
          );
        } catch (err) {
          showMessage(message, humanizeError(err && err.message ? err.message : err), true);
        } finally {
          forgotBtn.disabled = false;
        }
      });
    }
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

  function bindPasswordToggleButtons(root) {
    qsa("[data-password-toggle]", root || document).forEach((toggleBtn) => {
      if (!toggleBtn || toggleBtn.dataset.bound === "1") return;
      const targetId = String(toggleBtn.getAttribute("data-password-target") || "").trim();
      if (!targetId) return;
      const input = document.getElementById(targetId);
      if (!input) return;

      const setState = (visible) => {
        input.setAttribute("type", visible ? "text" : "password");
        toggleBtn.textContent = visible ? "Hide" : "Show";
        toggleBtn.setAttribute("aria-pressed", visible ? "true" : "false");
      };

      setState(String(toggleBtn.getAttribute("aria-pressed")) === "true");
      toggleBtn.addEventListener("click", () => {
        setState(input.type === "password");
        if (typeof input.focus === "function") {
          input.focus({ preventScroll: true });
        }
      });
      toggleBtn.dataset.bound = "1";
    });
  }

  function bindLivePasswordPairValidation(messageEl, passwordInput, confirmInput) {
    if (!messageEl || !passwordInput || !confirmInput) return;

    const update = () => {
      const password = String(passwordInput.value || "");
      const confirm = String(confirmInput.value || "");
      if (!password && !confirm) {
        showMessage(messageEl, "", false);
        return;
      }
      if (password && password.length < 8) {
        showMessage(messageEl, "Password must be at least 8 characters.", true);
        return;
      }
      if (confirm && password !== confirm) {
        showMessage(messageEl, "Passwords do not match.", true);
        return;
      }
      showMessage(messageEl, "", false);
    };

    passwordInput.addEventListener("input", update);
    confirmInput.addEventListener("input", update);
    passwordInput.addEventListener("blur", update);
    confirmInput.addEventListener("blur", update);
  }

  async function tryImmediateSignInAfterSignup(email, password) {
    try {
      const envelope = await supabaseSignIn(email, password);
      return normalizeSupabaseEnvelope(email, envelope);
    } catch {
      return null;
    }
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

    bindPasswordToggleButtons(consumerForm);
    bindPasswordToggleButtons(merchantForm);

    bindLivePasswordPairValidation(
      qs("#consumerRegisterMessage"),
      qs("#consumerPasswordInput"),
      qs("#consumerPasswordConfirmInput")
    );
    bindLivePasswordPairValidation(
      qs("#merchantRegisterMessage"),
      qs("#merchantPasswordInput"),
      qs("#merchantPasswordConfirmInput")
    );

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

        try {
          await submitFormToBackend("member", {
            full_name: fullName,
            email,
            phone,
            live_account_created: "true",
          });
        } catch {
          // Lead mirroring is best effort.
        }

        const session = await tryImmediateSignInAfterSignup(email, password);
        if (session) {
          let role = "consumer";
          try {
            const me = await fetchMe(session.access_token);
            role = String((me && me.role) || "consumer").toLowerCase();
          } catch {
            role = "consumer";
          }

          saveSessionForRole(role, session);
          showMessage(message, "Account created and signed in. Redirecting...", false);
          window.location.href = portalRouteForRole(role);
          return;
        }

        showMessage(message, "Account created. You can log in now.", false);
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
      const address = String(qs("#merchantAddressInput")?.value || "").trim();
      const website = String(qs("#merchantWebsiteInput")?.value || "").trim();
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
          address: address || null,
          website: website || null,
          role: "merchant",
          reward_preference: "cash",
          notifications_enabled: true,
          location_consent: true,
          alert_radius_miles: 5,
          notification_categories: "restaurant,gas,retail",
        });

        try {
          await submitFormToBackend("merchant", {
            company: businessName,
            contact_name: contactName,
            email,
            phone,
            address,
            website,
            live_account_created: "true",
          });
        } catch {
          // Lead mirroring is best effort.
        }

        const session = await tryImmediateSignInAfterSignup(email, password);
        if (session) {
          let role = "merchant";
          try {
            const me = await fetchMe(session.access_token);
            role = String((me && me.role) || "merchant").toLowerCase();
          } catch {
            role = "merchant";
          }

          saveSessionForRole(role, session);
          showMessage(message, "Merchant account created and signed in. Redirecting...", false);
          window.location.href = portalRouteForRole(role);
          return;
        }

        showMessage(message, "Merchant account created. You can log in now.", false);
        merchantForm.reset();
      } catch (err) {
        showMessage(message, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        submitBtn.disabled = false;
      }
    });

    setRegisterRole("consumer");
  }

  function readRecoveryAccessToken() {
    const hashParams = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
    const queryParams = new URLSearchParams(window.location.search || "");
    return (
      hashParams.get("access_token") ||
      queryParams.get("access_token") ||
      ""
    ).trim();
  }

  function bindResetPasswordPage() {
    const requestForm = qs("#passwordResetRequestForm");
    const resetForm = qs("#passwordResetForm");
    if (!requestForm || !resetForm) return;

    const requestMessage = qs("#passwordResetRequestMessage");
    const resetMessage = qs("#resetPasswordMessage");
    const requestSubmitBtn = qs("#passwordResetRequestSubmitBtn");
    const resetSubmitBtn = qs("#resetPasswordSubmitBtn");
    const tokenHint = qs("#resetTokenHint");

    function setResetMode(hasToken) {
      requestForm.hidden = hasToken;
      resetForm.hidden = !hasToken;
      if (tokenHint) {
        tokenHint.textContent = hasToken
          ? "Secure reset link detected. Set your new password."
          : "Use your account email to request a secure reset link.";
      }
    }

    setResetMode(Boolean(readRecoveryAccessToken()));

    requestForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const email = String(qs("#passwordResetEmailInput")?.value || "").trim();
      if (!email) {
        showMessage(requestMessage, "Email is required.", true);
        return;
      }

      requestSubmitBtn.disabled = true;
      showMessage(requestMessage, "Sending reset email...", false);
      try {
        await supabaseRequestPasswordReset(email);
        showMessage(
          requestMessage,
          "Reset email sent. Open the link in your inbox to set a new password.",
          false
        );
      } catch (err) {
        showMessage(requestMessage, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        requestSubmitBtn.disabled = false;
      }
    });

    resetForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const token = readRecoveryAccessToken();
      const password = String(qs("#newPasswordInput")?.value || "");
      const confirm = String(qs("#confirmNewPasswordInput")?.value || "");

      if (!token) {
        showMessage(resetMessage, "Reset token is missing. Request a new reset email.", true);
        setResetMode(false);
        return;
      }

      if (password.length < 8) {
        showMessage(resetMessage, "Password must be at least 8 characters.", true);
        return;
      }

      if (password !== confirm) {
        showMessage(resetMessage, "Passwords do not match.", true);
        return;
      }

      resetSubmitBtn.disabled = true;
      showMessage(resetMessage, "Updating password...", false);
      try {
        await supabaseUpdatePassword(token, password);
        showMessage(
          resetMessage,
          "Password updated. You can now sign in from the login page.",
          false
        );
        resetForm.reset();
        window.history.replaceState({}, document.title, window.location.pathname);
        setResetMode(false);
      } catch (err) {
        showMessage(resetMessage, humanizeError(err && err.message ? err.message : err), true);
      } finally {
        resetSubmitBtn.disabled = false;
      }
    });
  }

  async function init() {
    await loadConfig();
    bindPasswordToggleButtons(document);
    bindLoginPage();
    bindCreateAccountPage();
    bindResetPasswordPage();
  }

  init();
})();
