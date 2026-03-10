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
      return "Password is too short. Use at least 6 characters.";
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

  async function supabaseSignUp(payload){
    const cfg = await loadWebConfig();
    const response = await fetch(`${cfg.supabase_url}/auth/v1/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apikey": cfg.supabase_anon_key,
        "Authorization": `Bearer ${cfg.supabase_anon_key}`
      },
      body: JSON.stringify(payload)
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
    if(password.length < 6){
      throw new Error("Password must be at least 6 characters.");
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
            throw new Error("This account exists but email is not verified yet. Please wait a few minutes, then use Login page and resend verification.");
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
      await submitFormToBackend("guest", {
        full_name: fullName,
        address: String(data.address || "").trim(),
        phone: phone,
        email,
        dob: String(data.dob || "").trim(),
        live_account_created: "true"
      });
    } catch(_err){
      // Non-blocking.
    }

    form.reset();
    setToast(
      form,
      "Account created. Check your email to verify, then sign in at /login.",
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
    if(password.length < 6){
      throw new Error("Password must be at least 6 characters.");
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
            throw new Error("This account exists but email is not verified yet. Please wait a few minutes, then use Login page and resend verification.");
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
      "Merchant account created. Verify email, then sign in at /login.",
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

  wireForm('[data-form="guest"]', 'perknation_guest_leads', 'guest');
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

  document.querySelectorAll('[data-acc]').forEach((item)=>{
    const btn = item.querySelector('button');
    if(!btn) return;
    btn.addEventListener('click', ()=> item.classList.toggle('accOpen'));
  });
})();
