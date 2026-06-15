(function(){
  const menuBtn = document.querySelector('[data-menu-btn]');
  const mobileMenu = document.querySelector('[data-mobile-menu]');
  if(menuBtn && mobileMenu){
    menuBtn.addEventListener('click', ()=> mobileMenu.classList.toggle('show'));
  }

  const THEME_PREF_KEY = "perknation_site_theme";

  function isWhitePath(pathname){
    return pathname === "/white" || pathname.startsWith("/white/");
  }

  function toThemedPath(pathname, theme){
    const normalized = String(pathname || "/").startsWith("/")
      ? String(pathname || "/")
      : `/${String(pathname || "/")}`;

    if(theme === "white"){
      if(isWhitePath(normalized)){
        return normalized === "/white" ? "/white/" : normalized;
      }
      if(normalized === "/"){
        return "/white/";
      }
      return `/white${normalized}`;
    }

    if(!isWhitePath(normalized)){
      return normalized;
    }
    if(normalized === "/white" || normalized === "/white/"){
      return "/";
    }
    return normalized.replace(/^\/white/, "") || "/";
  }

  function toThemedHref(theme){
    const path = toThemedPath(window.location.pathname, theme);
    return `${path}${window.location.search || ""}${window.location.hash || ""}`;
  }

  function maybeApplySavedThemePreference(){
    const saved = localStorage.getItem(THEME_PREF_KEY);
    if(saved !== "white" && saved !== "dark"){
      return false;
    }

    const currentTheme = isWhitePath(window.location.pathname) ? "white" : "dark";
    if(saved === currentTheme){
      return false;
    }

    const href = toThemedHref(saved);
    window.location.replace(href);
    return true;
  }

  function wireThemeToggle(){
    const currentTheme = isWhitePath(window.location.pathname) ? "white" : "dark";
    if(!localStorage.getItem(THEME_PREF_KEY)){
      localStorage.setItem(THEME_PREF_KEY, currentTheme);
    }

    const nextTheme = currentTheme === "white" ? "dark" : "white";
    const toggleLabel = nextTheme === "dark" ? "Dark mode" : "Light mode";
    const toggleAriaLabel = `Switch to ${toggleLabel.toLowerCase()}`;
    const nextHref = toThemedHref(nextTheme);

    const headerContainer = document.querySelector(".header .container");
    if(!headerContainer || headerContainer.querySelector("[data-theme-switch-row]")){
      return;
    }

    const row = document.createElement("div");
    row.className = "themeSwitchRow";
    row.setAttribute("data-theme-switch-row", "1");

    const label = document.createElement("label");
    label.className = "themeSwitch";

    const text = document.createElement("span");
    text.className = "themeSwitchText";
    text.textContent = toggleLabel;

    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "themeSwitchInput";
    input.checked = currentTheme === "dark";
    input.setAttribute("role", "switch");
    input.setAttribute("aria-label", toggleAriaLabel);

    const track = document.createElement("span");
    track.className = "themeSwitchTrack";
    track.setAttribute("aria-hidden", "true");

    input.addEventListener("change", ()=>{
      localStorage.setItem(THEME_PREF_KEY, nextTheme);
      window.location.href = nextHref;
    });

    label.append(text, input, track);
    row.appendChild(label);

    const nav = headerContainer.querySelector(".nav");
    if(nav){
      nav.insertAdjacentElement("afterend", row);
      return;
    }
    headerContainer.prepend(row);
  }

  if(maybeApplySavedThemePreference()){
    return;
  }
  wireThemeToggle();

  function parseAppScriptVersion(){
    const scriptNode = Array.from(document.querySelectorAll("script[src]"))
      .find((node)=> String(node.getAttribute("src") || "").includes("assets/app.js"));
    if(!scriptNode){
      return "";
    }
    try {
      const scriptUrl = new URL(scriptNode.getAttribute("src"), window.location.origin);
      return String(scriptUrl.searchParams.get("v") || "").trim();
    } catch(_err){
      return "";
    }
  }

  function wireBuildBadge(){
    const footer = document.querySelector("footer.footer .container") || document.querySelector("footer.footer");
    if(!footer || footer.querySelector("[data-build-badge]")){
      return;
    }

    const badge = document.createElement("div");
    badge.className = "buildBadge";
    badge.setAttribute("data-build-badge", "1");
    footer.appendChild(badge);

    const fallbackVersion = parseAppScriptVersion();
    if(fallbackVersion){
      badge.textContent = `Build ${fallbackVersion}`;
    } else {
      badge.textContent = "Build loading...";
    }

    fetch("/web/build", { cache: "no-store" })
      .then((res)=>{
        if(!res.ok){
          throw new Error(`build endpoint failed (${res.status})`);
        }
        return res.json();
      })
      .then((body)=>{
        const label = String((body && body.label) || "").trim();
        const builtAt = String((body && body.built_at) || "").trim();
        if(label && builtAt){
          badge.textContent = `${label} • ${builtAt}`;
          return;
        }
        if(label){
          badge.textContent = label;
          return;
        }
        if(builtAt){
          badge.textContent = `Build ${builtAt}`;
          return;
        }
        if(!fallbackVersion){
          badge.textContent = "Build unavailable";
        }
      })
      .catch(()=>{
        if(!fallbackVersion){
          badge.textContent = "Build unavailable";
        }
      });
  }

  wireBuildBadge();

  const PUBLIC_USER_SESSION_KEY = "pk_user_portal_session_v2";
  const PUBLIC_MERCHANT_SESSION_KEY = "pk_merchant_portal_session_v1";
  const PUBLIC_SESSION_KEYS = [
    { key: PUBLIC_USER_SESSION_KEY, roleHint: "consumer" },
    { key: PUBLIC_MERCHANT_SESSION_KEY, roleHint: "merchant" },
    { key: "pk_user_portal_session_v1", roleHint: "consumer" },
    { key: "perknation_user_session", roleHint: "consumer" },
    { key: "perknation_merchant_session", roleHint: "merchant" },
  ];

  function publicPortalPathForRole(role){
    const normalized = String(role || "").toLowerCase();
    if(normalized === "merchant") return "/merchant";
    if(normalized === "admin") return "/admin";
    return "/user";
  }

  function publicAccountLabelForRole(role){
    const normalized = String(role || "").toLowerCase();
    if(normalized === "merchant") return "Merchant Dashboard";
    if(normalized === "admin") return "Admin Dashboard";
    return "My Account";
  }

  function readStoredPublicSession(key){
    try{
      const raw = localStorage.getItem(key);
      if(!raw) return null;
      const parsed = JSON.parse(raw);
      if(!parsed || typeof parsed !== "object") return null;
      const accessToken = String(
        parsed.access_token ||
        parsed.accessToken ||
        (parsed.session && parsed.session.access_token) ||
        ""
      ).trim();
      if(!accessToken) return null;
      return {
        raw: parsed,
        accessToken,
        email: String(parsed.email || "").trim().toLowerCase(),
        expiresAt: Number(parsed.expires_at || parsed.expiresAt || 0),
      };
    }catch(_err){
      return null;
    }
  }

  function isStoredPublicSessionExpired(session){
    if(!session || !session.expiresAt) return false;
    return Date.now() > ((session.expiresAt * 1000) - 30000);
  }

  async function resolveStoredPublicSession(){
    for(const candidate of PUBLIC_SESSION_KEYS){
      const session = readStoredPublicSession(candidate.key);
      if(!session || isStoredPublicSessionExpired(session)){
        continue;
      }
      try{
        const response = await fetch("/v1/auth/me", {
          cache: "no-store",
          headers: {
            "Accept": "application/json",
            "Authorization": `Bearer ${session.accessToken}`,
          },
        });
        if(!response.ok){
          if(response.status === 401 || response.status === 403){
            try{ localStorage.removeItem(candidate.key); }catch(_storageErr){}
          }
          continue;
        }
        const me = await response.json();
        const role = String(me.role || candidate.roleHint || "consumer").toLowerCase();
        return {
          ...session,
          email: String(me.email || session.email || "").trim().toLowerCase(),
          fullName: String(me.full_name || "").trim(),
          role,
        };
      }catch(_err){
        continue;
      }
    }
    return null;
  }

  function shouldReplaceWithAccountLink(link){
    if(!link) return false;
    let parsed;
    try{
      parsed = new URL(link.getAttribute("href") || "", window.location.origin);
    }catch(_err){
      return false;
    }
    if(parsed.origin !== window.location.origin) return false;
    const path = parsed.pathname.replace(/\/$/, "") || "/";
    const hash = String(parsed.hash || "").toLowerCase();
    if(path === "/login" || path === "/white/login") return true;
    if(path === "/create-account" || path === "/white/create-account") return true;
    if((path === "/members" || path === "/white/members") && hash === "#join") return true;
    return false;
  }

  function applySignedInPublicUi(session){
    const portalPath = publicPortalPathForRole(session && session.role);
    const label = publicAccountLabelForRole(session && session.role);
    document.body.setAttribute("data-public-auth-state", "signed-in");
    document.querySelectorAll("a[href]").forEach((link)=>{
      if(!shouldReplaceWithAccountLink(link)) return;
      link.setAttribute("href", portalPath);
      link.setAttribute("data-public-auth-link", "account");
      link.textContent = label;
      if(session && session.email){
        link.setAttribute("title", `Signed in as ${session.email}`);
      }
    });
  }

  function wirePublicAuthState(){
    void resolveStoredPublicSession().then((session)=>{
      if(session && session.accessToken){
        applySignedInPublicUi(session);
      }
    });
  }

  wirePublicAuthState();

  // Cookie banner consent (localStorage)
  const cookie = document.querySelector('[data-cookie]');
  const accept = document.querySelector('[data-cookie-accept]');
  const reject = document.querySelector('[data-cookie-reject]');
  const key = "perknation_cookie_choice";
  function hideCookie(){ if(cookie) cookie.style.display = "none"; }
  if(cookie){
    const choice = localStorage.getItem(key);
    if(choice) hideCookie();
  }
  if(accept) accept.addEventListener('click', ()=>{ localStorage.setItem(key, "accept"); hideCookie(); });
  if(reject) reject.addEventListener('click', ()=>{ localStorage.setItem(key, "reject"); hideCookie(); });

  function setToast(form, message, isError){
    const card = form.closest('.card');
    const toast = card ? card.querySelector('[data-toast]') : form.querySelector('[data-toast]');
    if(!toast) return;
    toast.textContent = message;
    toast.style.display = "block";
    toast.style.borderStyle = "solid";
    toast.style.borderWidth = "1px";
    toast.style.borderColor = isError ? "rgba(195,63,22,.45)" : "rgba(41,166,91,.45)";
    toast.style.background = isError ? "rgba(195,63,22,.08)" : "rgba(41,166,91,.10)";
    toast.style.color = "inherit";
  }

  function isEmailRateLimitError(message){
    const lower = String(message || "").toLowerCase();
    return lower.includes("over_email_send_rate_limit") || lower.includes("email rate limit exceeded");
  }

  function humanizeSubmissionError(rawMessage, mode){
    const message = String(rawMessage || "").trim();
    const lower = message.toLowerCase();

    if(lower.includes("over_email_send_rate_limit") || lower.includes("email rate limit exceeded")){
      if(mode === "consumer-account" || mode === "merchant-account"){
        return "Too many sign-up emails were sent recently. Please wait a few minutes and try again. This does not necessarily mean the email already has an account.";
      }
      return "Too many form emails were sent recently. Please wait a few minutes and try again.";
    }

    if(
      lower.includes("already registered") ||
      lower.includes("user already registered") ||
      lower.includes("email already registered")
    ){
      return "That email is already registered. Please log in instead.";
    }

    if(lower.includes("password") && lower.includes("least")){
      return "Password is too short. Use at least 8 characters.";
    }

    if(lower.includes("failed to fetch") || lower.includes("networkerror")){
      return "We could not reach the server. Check your connection and try again.";
    }

    if(message){
      return message;
    }

    return "Submission failed. Please try again.";
  }

  function backupToLocal(storageKey, data){
    const existing = JSON.parse(localStorage.getItem(storageKey) || "[]");
    existing.push({ ...data, ts: new Date().toISOString() });
    localStorage.setItem(storageKey, JSON.stringify(existing));
  }

  async function readJsonResponse(response){
    const raw = await response.text();
    if(!raw) return {};
    try {
      return JSON.parse(raw);
    } catch(_err){
      return {};
    }
  }

  async function submitFormToBackend(formType, data){
    const response = await fetch(`/v1/web/forms/${encodeURIComponent(formType)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify({
        source_page: window.location.pathname,
        data
      })
    });

    const payload = await readJsonResponse(response);
    if(!response.ok){
      const detail = payload.detail || payload.message || `Request failed (${response.status})`;
      throw new Error(detail);
    }

    return payload;
  }

  let webConfigPromise = null;
  async function loadWebConfig(){
    if(!webConfigPromise){
      webConfigPromise = fetch("/web/config")
        .then((res)=> res.json())
        .then((cfg)=>{
          if(cfg.error){
            throw new Error(cfg.error);
          }
          if(!cfg.supabase_url || !cfg.supabase_anon_key){
            throw new Error("Account service is not configured for web sign-up.");
          }
          return cfg;
        });
    }
    return webConfigPromise;
  }

  function withRedirectParam(url, redirectTo){
    if(!redirectTo) return url;
    try {
      const parsed = new URL(url, window.location.origin);
      parsed.searchParams.set("redirect_to", redirectTo);
      return parsed.toString();
    } catch(_err){
      return url;
    }
  }

  async function supabaseSignUp(payload){
    const cfg = await loadWebConfig();
    const redirectTo = String(cfg.auth_email_redirect_url || `${window.location.origin}/login`);
    const response = await fetch(withRedirectParam(`${cfg.supabase_url}/auth/v1/signup`, redirectTo), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apikey": cfg.supabase_anon_key,
        "Authorization": `Bearer ${cfg.supabase_anon_key}`,
        "redirect_to": redirectTo
      },
      body: JSON.stringify({
        ...payload,
        options: {
          ...(payload && payload.options ? payload.options : {}),
          data: (payload && payload.data) || {},
          emailRedirectTo: redirectTo,
          redirectTo
        }
      })
    });

    const data = await readJsonResponse(response);
    if(!response.ok){
      const detail = data.error_description || data.message || data.msg || data.error || `Signup failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }

  async function supabaseSignIn(email, password){
    const cfg = await loadWebConfig();
    const response = await fetch(`${cfg.supabase_url}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apikey": cfg.supabase_anon_key,
        "Authorization": `Bearer ${cfg.supabase_anon_key}`
      },
      body: JSON.stringify({ email, password })
    });

    const data = await readJsonResponse(response);
    if(!response.ok){
      const detail = data.error_description || data.message || data.msg || data.error || `Sign-in failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }

  async function bootstrapBackendUser(accessToken){
    if(!accessToken) return;
    try {
      await fetch("/v1/auth/me", {
        headers: {
          "Authorization": `Bearer ${accessToken}`
        }
      });
    } catch(_err){
      // Best effort only.
    }
  }

  async function submitConsumerAccountSignup(form, data){
    const fullName = String(data.full_name || "").trim();
    const email = String(data.email || "").trim();
    const phone = String(data.phone || "").trim();
    const password = String(data.password || "");
    const confirmPassword = String(data.confirm_password || "");

    if(!fullName || !email || !password){
      throw new Error("Full name, email, and password are required.");
    }
    if(password.length < 8){
      throw new Error("Password must be at least 8 characters.");
    }
    if(password !== confirmPassword){
      throw new Error("Passwords do not match.");
    }

    let result;
    try {
      result = await supabaseSignUp({
        email,
        password,
        data: {
          full_name: fullName,
          phone: phone || null,
          role: "consumer",
          reward_preference: "cash",
          notifications_enabled: true,
          location_consent: true,
          alert_radius_miles: 5,
          notification_categories: "restaurant,gas,retail",
          address: String(data.address || "").trim() || null,
          dob: String(data.dob || "").trim() || null
        }
      });
    } catch (err) {
      const msg = (err && err.message) ? err.message : "";
      if(isEmailRateLimitError(msg)){
        try {
          // If account already exists, this lets users proceed immediately.
          await supabaseSignIn(email, password);
          form.reset();
          setToast(
            form,
            "Sign-up email sending is temporarily rate-limited, but this account already exists with this password. Use Login page to continue now.",
            false
          );
          return;
        } catch(_loginErr){
          const loginMsg = String((_loginErr && _loginErr.message) ? _loginErr.message : "").toLowerCase();
          if(
            loginMsg.includes("invalid login credentials") ||
            loginMsg.includes("email or password")
          ){
            throw new Error("Sign-up email sending is temporarily rate-limited. This email may already exist with a different password. Please use Login page.");
          }
          if(
            loginMsg.includes("not verified") ||
            loginMsg.includes("not confirmed") ||
            loginMsg.includes("confirm")
          ){
            throw new Error("This account exists but email is not verified yet. Check your spam/junk folder, then use Login page to resend verification.");
          }
          throw new Error("Sign-up email sending is temporarily rate-limited. Please wait a few minutes and try again.");
        }
      }
      throw err;
    }

    // Account service can return a "user" object with no identities for existing users.
    if(result && result.user && Array.isArray(result.user.identities) && result.user.identities.length === 0){
      throw new Error("Email already registered. Please log in instead.");
    }

    const maybeAccessToken =
      (result && result.access_token) ||
      (result && result.session && result.session.access_token) ||
      null;
    await bootstrapBackendUser(maybeAccessToken);

    // Keep CRM lead capture for the marketing site.
    try {
      await submitFormToBackend("member", {
        full_name: fullName,
        phone,
        email,
        address: String(data.address || "").trim(),
        dob: String(data.dob || "").trim(),
        live_account_created: "true"
      });
    } catch(_err){
      // Non-blocking.
    }

    form.reset();
    setToast(
      form,
      "Account created. Check your inbox and spam/junk for the verification email, then sign in.",
      false
    );
  }

  async function submitMerchantAccountSignup(form, data){
    const email = String(data.email || "").trim();
    const password = String(data.password || "");
    const confirmPassword = String(data.confirm_password || "");
    const contactName = String(data.contact_name || "").trim();
    const company = String(data.company || "").trim();
    const phone = String(data.phone || "").trim();

    if(!email || !password || !contactName || !company){
      throw new Error("Company, contact name, email, and password are required.");
    }
    if(password.length < 8){
      throw new Error("Password must be at least 8 characters.");
    }
    if(password !== confirmPassword){
      throw new Error("Passwords do not match.");
    }

    let result;
    try {
      result = await supabaseSignUp({
        email,
        password,
        data: {
          full_name: contactName,
          phone: phone || null,
          role: "merchant",
          reward_preference: "cash",
          notifications_enabled: true,
          location_consent: true,
          alert_radius_miles: 5,
          notification_categories: "restaurant,gas,retail",
          company: company || null,
          website: String(data.website || "").trim() || null,
          address: String(data.address || "").trim() || null
        }
      });
    } catch (err) {
      const msg = (err && err.message) ? err.message : "";
      if(isEmailRateLimitError(msg)){
        try {
          await supabaseSignIn(email, password);
          form.reset();
          setToast(
            form,
            "Sign-up email sending is temporarily rate-limited, but this account already exists with this password. Use Login page to continue now.",
            false
          );
          return;
        } catch(_loginErr){
          const loginMsg = String((_loginErr && _loginErr.message) ? _loginErr.message : "").toLowerCase();
          if(
            loginMsg.includes("invalid login credentials") ||
            loginMsg.includes("email or password")
          ){
            throw new Error("Sign-up email sending is temporarily rate-limited. This email may already exist with a different password. Please use Login page.");
          }
          if(
            loginMsg.includes("not verified") ||
            loginMsg.includes("not confirmed") ||
            loginMsg.includes("confirm")
          ){
            throw new Error("This account exists but email is not verified yet. Check your spam/junk folder, then use Login page to resend verification.");
          }
          throw new Error("Sign-up email sending is temporarily rate-limited. Please wait a few minutes and try again.");
        }
      }
      throw err;
    }

    if(result && result.user && Array.isArray(result.user.identities) && result.user.identities.length === 0){
      throw new Error("Email already registered. Please log in instead.");
    }

    const maybeAccessToken =
      (result && result.access_token) ||
      (result && result.session && result.session.access_token) ||
      null;
    await bootstrapBackendUser(maybeAccessToken);

    try {
      await submitFormToBackend("merchant", {
        company,
        address: String(data.address || "").trim(),
        email,
        phone,
        website: String(data.website || "").trim(),
        contact_name: contactName,
        live_account_created: "true"
      });
    } catch(_err){
      // Non-blocking.
    }

    form.reset();
    setToast(
      form,
      "Merchant account created. Verify email, then sign in.",
      false
    );
  }

  function wireForm(selector, storageKey, formType){
    const form = document.querySelector(selector);
    if(!form) return;

    form.addEventListener('submit', async (e)=>{
      e.preventDefault();

      const submitBtn = form.querySelector('button[type="submit"]');
      if(submitBtn){
        submitBtn.disabled = true;
        submitBtn.dataset.originalText = submitBtn.dataset.originalText || submitBtn.textContent || "Submit";
        submitBtn.textContent = "Submitting...";
      }

      const data = Object.fromEntries(new FormData(form).entries());
      const mode = String(form.getAttribute("data-form-mode") || "lead");

      try{
        if(mode === "consumer-account"){
          await submitConsumerAccountSignup(form, data);
        } else if(mode === "merchant-account"){
          await submitMerchantAccountSignup(form, data);
        } else {
          const result = await submitFormToBackend(formType, data);
          const backupHint = result.mirrored_to_backup ? " + local DB backup" : "";
          setToast(form, `Submitted securely. Reference #${result.submission_id}${backupHint}.`, false);
          form.reset();
        }
      }catch(err){
        const msg = (err && err.message) ? err.message : "Submission failed";
        const friendly = humanizeSubmissionError(msg, mode);
        const isAccountMode = mode === "consumer-account" || mode === "merchant-account";

        if(isAccountMode){
          // Do not store account form payloads (especially passwords) in localStorage.
          setToast(form, friendly, true);
        } else {
          backupToLocal(storageKey, data);
          setToast(form, `${friendly} Saved locally as fallback.`, true);
        }
      }finally{
        if(submitBtn){
          submitBtn.disabled = false;
          submitBtn.textContent = submitBtn.dataset.originalText || "Submit";
        }
      }
    });
  }

  wireForm('[data-form="member"]', 'perknation_member_leads', 'member');
  wireForm('[data-form="merchant"]', 'perknation_merchant_leads', 'merchant');
  wireForm('[data-form="contact"]', 'perknation_contact_leads', 'contact');

  document.querySelectorAll('[data-copy]').forEach((btn)=>{
    btn.addEventListener('click', async ()=>{
      const val = btn.getAttribute('data-copy') || "";
      try{
        await navigator.clipboard.writeText(val);
        const old = btn.textContent;
        btn.textContent = "Copied ✓";
        setTimeout(()=> btn.textContent = old, 1200);
      }catch(_e){}
    });
  });

  const overlay = document.querySelector('[data-modal-overlay]');
  const closeBtn = document.querySelector('[data-modal-close]');
  function closeModal(){ if(overlay) overlay.classList.remove('modalShow'); }
  if(closeBtn) closeBtn.addEventListener('click', closeModal);
  if(overlay) overlay.addEventListener('click', (e)=>{ if(e.target === overlay) closeModal(); });
  const shouldShow = document.body.getAttribute('data-popup') === "on";
  if(shouldShow && overlay){
    const shownKey = "perknation_popup_shown_v1";
    if(!localStorage.getItem(shownKey)){
      setTimeout(()=>{
        overlay.classList.add('modalShow');
        localStorage.setItem(shownKey, "1");
      }, 12000);
    }
  }

  function collectHomeAssistantHistory(messagesNode){
    if(!messagesNode) return [];
    return Array.from(messagesNode.querySelectorAll(".aiBubble"))
      .map((node)=>{
        const role = node.classList.contains("user") ? "user" : "assistant";
        const content = String(node.textContent || "").trim();
        return { role, content };
      })
      .filter((entry)=> entry.content.length > 0)
      .slice(-20);
  }

  function appendHomeAssistantMessage(messagesNode, role, text){
    if(!messagesNode) return;
    const bubble = document.createElement("div");
    bubble.className = `aiBubble ${role === "user" ? "user" : "assistant"}`;
    bubble.textContent = String(text || "").trim();
    messagesNode.appendChild(bubble);
    messagesNode.scrollTop = messagesNode.scrollHeight;
  }

  function tryGetBrowserLocation(){
    if(!("geolocation" in navigator)){
      return Promise.resolve(null);
    }

    return new Promise((resolve)=>{
      let settled = false;
      const finish = (value)=>{
        if(settled) return;
        settled = true;
        resolve(value);
      };

      const timer = window.setTimeout(()=> finish(null), 4500);
      navigator.geolocation.getCurrentPosition(
        (position)=>{
          window.clearTimeout(timer);
          finish({
            latitude: Number(position.coords.latitude),
            longitude: Number(position.coords.longitude),
          });
        },
        ()=>{
          window.clearTimeout(timer);
          finish(null);
        },
        {
          enableHighAccuracy: false,
          timeout: 4000,
          maximumAge: 180000,
        }
      );
    });
  }

  function shouldIncludeGeoHint(message){
    const text = String(message || "").toLowerCase();
    return (
      text.includes("near") ||
      text.includes("nearby") ||
      text.includes("local") ||
      text.includes("around") ||
      text.includes("pasadena") ||
      text.includes("los angeles") ||
      text.includes("la ")
    );
  }

  function wireHomepageAssistant(){
    const form = document.querySelector("[data-home-ai-form]");
    const messages = document.querySelector("[data-home-ai-messages]");
    const status = document.querySelector("[data-home-ai-status]");
    const input = document.querySelector("[data-home-ai-input]");
    const sendBtn = document.querySelector("[data-home-ai-send]");
    const clearBtn = document.querySelector("[data-home-ai-clear]");
    if(!form || !messages || !input || !sendBtn){
      return;
    }

    const setStatus = (value)=>{
      if(status){
        status.textContent = String(value || "").trim();
      }
    };

    if(clearBtn){
      clearBtn.addEventListener("click", ()=>{
        messages.innerHTML = "";
        appendHomeAssistantMessage(
          messages,
          "assistant",
          "Ask about the current Hollywood Sports offer, El Portal World Cup happy hour, or Pasadena restaurant picks."
        );
        setStatus("Cleared. Ask about current promos or local restaurant picks.");
      });
    }

    form.addEventListener("submit", async (event)=>{
      event.preventDefault();
      const message = String(input.value || "").trim();
      if(!message) return;

      appendHomeAssistantMessage(messages, "user", message);
      input.value = "";
      input.focus();
      sendBtn.disabled = true;
      if(clearBtn) clearBtn.disabled = true;
      setStatus("Finding local recommendations...");

      try {
        const includeGeo = shouldIncludeGeoHint(message);
        const coords = includeGeo ? await tryGetBrowserLocation() : null;
        const history = collectHomeAssistantHistory(messages);

        const response = await fetch("/v1/ai/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json",
          },
          body: JSON.stringify({
            message,
            context: "home_local_guide",
            history,
            user_latitude: coords ? coords.latitude : null,
            user_longitude: coords ? coords.longitude : null,
          }),
        });

        const payload = await readJsonResponse(response);
        if(!response.ok){
          const detail = payload.detail || payload.message || `AI request failed (${response.status})`;
          throw new Error(detail);
        }

        const answer = String(payload.answer || "").trim();
        if(!answer){
          throw new Error("AI returned an empty response.");
        }

        appendHomeAssistantMessage(messages, "assistant", answer);
        setStatus("Answered by Perk Nation AI.");
      } catch(err){
        appendHomeAssistantMessage(
          messages,
          "assistant",
          "I could not complete that request right now. Try asking with your neighborhood (for example: Old Pasadena, Santa Monica, or Culver City)."
        );
        const reason = (err && err.message) ? String(err.message) : "temporary error";
        setStatus(`Assistant unavailable (${reason}).`);
      } finally {
        sendBtn.disabled = false;
        if(clearBtn) clearBtn.disabled = false;
      }
    });
  }

  wireHomepageAssistant();

  document.querySelectorAll('[data-acc]').forEach((item)=>{
    const btn = item.querySelector('button');
    if(!btn) return;
    btn.addEventListener('click', ()=> item.classList.toggle('accOpen'));
  });
})();
