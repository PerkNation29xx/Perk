(function(){
  const menuBtn = document.querySelector('[data-menu-btn]');
  const mobileMenu = document.querySelector('[data-mobile-menu]');
  if(menuBtn && mobileMenu){
    menuBtn.addEventListener('click', ()=>{
      const isOpen = mobileMenu.classList.toggle('show');
      menuBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
    mobileMenu.addEventListener('click', (event)=>{
      if(event.target.closest('a')){
        mobileMenu.classList.remove('show');
        menuBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  const THEME_PREF_KEY = "perknation_site_theme";
  const VALID_THEMES = new Set(["light", "dark"]);

  function defaultTheme(){
    const declared = String(document.documentElement.dataset.theme || "").toLowerCase();
    if(VALID_THEMES.has(declared)){
      return declared;
    }
    return window.location.pathname === "/white" || window.location.pathname.startsWith("/white/")
      ? "light"
      : "dark";
  }

  function storedTheme(){
    try{
      const saved = String(localStorage.getItem(THEME_PREF_KEY) || "").toLowerCase();
      return VALID_THEMES.has(saved) ? saved : "";
    } catch(_err){
      return "";
    }
  }

  function applyTheme(theme, persist){
    const resolved = VALID_THEMES.has(theme) ? theme : defaultTheme();
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if(themeColor){
      themeColor.setAttribute("content", resolved === "dark" ? "#0d0d0d" : "#f8fafc");
    }
    if(persist){
      try{
        localStorage.setItem(THEME_PREF_KEY, resolved);
      } catch(_err){
        // Storage can be unavailable in private or restricted browser contexts.
      }
    }
    document.dispatchEvent(new CustomEvent("perknation:themechange", { detail: { theme: resolved } }));
    return resolved;
  }

  function wireThemeToggle(){
    let currentTheme = applyTheme(storedTheme() || defaultTheme(), false);

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
    text.textContent = currentTheme === "dark" ? "Dark mode" : "Light mode";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "themeSwitchInput";
    input.checked = currentTheme === "dark";
    input.setAttribute("role", "switch");
    input.setAttribute("aria-label", "Toggle dark mode");

    const track = document.createElement("span");
    track.className = "themeSwitchTrack";
    track.setAttribute("aria-hidden", "true");

    input.addEventListener("change", ()=>{
      currentTheme = applyTheme(input.checked ? "dark" : "light", true);
      text.textContent = currentTheme === "dark" ? "Dark mode" : "Light mode";
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

  function escapeHtml(value){
    const div = document.createElement("div");
    div.textContent = String(value || "");
    return div.innerHTML;
  }

  function themedDirectoryPath(path){
    const normalized = String(path || "/directory").startsWith("/") ? String(path || "/directory") : `/${path}`;
    return normalized.replace(/^\/white/, "") || "/directory";
  }

  function externalHref(url){
    const value = String(url || "").trim();
    if(!value) return "";
    if(value.startsWith("http://") || value.startsWith("https://")) return value;
    return `https://${value}`;
  }

  function businessLocationText(item){
    const cityLine = [item.search_city || item.city, item.state, item.zip_code].filter(Boolean).join(", ");
    return [item.address, cityLine].filter(Boolean).join(" ").trim();
  }

  function businessMapQuery(item){
    const location = businessLocationText(item);
    if(!location) return "";
    return [item.business_name, location].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  }

  function googleDirectionsHref(item){
    const query = businessMapQuery(item);
    return query ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}` : "";
  }

  function appleMapsHref(item){
    const query = businessMapQuery(item);
    return query ? `https://maps.apple.com/?daddr=${encodeURIComponent(query)}` : "";
  }

  function geoHref(item){
    const query = businessMapQuery(item);
    return query ? `geo:0,0?q=${encodeURIComponent(query)}` : "";
  }

  function directoryMapLinks(item){
    const directions = googleDirectionsHref(item);
    if(!directions) return "";
    const apple = appleMapsHref(item);
    const geo = geoHref(item);
    return `
      <div class="directoryResultActions">
        <a href="${escapeHtml(directions)}" target="_blank" rel="noopener">Directions</a>
        ${apple ? `<a href="${escapeHtml(apple)}" target="_blank" rel="noopener">Apple Maps</a>` : ""}
        ${geo ? `<a href="${escapeHtml(geo)}">GPS</a>` : ""}
      </div>
    `;
  }

  function wireBusinessDirectorySearch(){
    const homePanel = document.querySelector("[data-directory-home]");
    if(!homePanel){
      return;
    }
    const form = homePanel.querySelector("[data-directory-search-form]");
    const input = homePanel.querySelector("[data-directory-search-input]");
    const citySelect = homePanel.querySelector("[data-directory-city-select]");
    const typeSelect = homePanel.querySelector("[data-directory-type-select]");
    const status = homePanel.querySelector("[data-directory-status]");
    const categoryHierarchy = homePanel.querySelector("[data-directory-category-hierarchy]");
    const categoryCount = homePanel.querySelector("[data-directory-category-count]");
    const locationButton = homePanel.querySelector("[data-directory-location-button]");
    const locationStatus = homePanel.querySelector("[data-directory-location-status]");
    const results = homePanel.querySelector("[data-directory-results]");
    const previewOnly = homePanel.hasAttribute("data-directory-preview-only");
    let facetsLoaded = false;
    let searchTimer = null;
    let lastDirectoryCoords = null;

    const serviceCities = [
      ["Pasadena", 34.1478, -118.1445],
      ["South Pasadena", 34.1161, -118.1503],
      ["Alhambra", 34.0953, -118.1270],
      ["San Gabriel", 34.0961, -118.1058],
      ["Monterey Park", 34.0625, -118.1228],
      ["Glendora", 34.1361, -117.8653],
      ["Azusa", 34.1336, -117.9076],
      ["La Verne", 34.1008, -117.7678],
      ["El Monte", 34.0686, -118.0276],
      ["South El Monte", 34.0519, -118.0467],
      ["Montebello", 34.0165, -118.1138],
      ["Arcadia", 34.1397, -118.0353],
      ["Glendale", 34.1425, -118.2551],
      ["Burbank", 34.1808, -118.3090],
      ["Los Angeles", 34.0522, -118.2437],
      ["Long Beach", 33.7701, -118.1937],
      ["Vernon", 34.0039, -118.2301],
      ["Commerce", 34.0006, -118.1598],
      ["Huntington Park", 33.9817, -118.2251],
      ["Maywood", 33.9867, -118.1853],
      ["Bell", 33.9775, -118.1870],
      ["Bell Gardens", 33.9653, -118.1515],
      ["Cudahy", 33.9606, -118.1854],
      ["South Gate", 33.9547, -118.2120],
      ["Lynwood", 33.9303, -118.2115],
      ["Compton", 33.8958, -118.2201],
      ["Paramount", 33.8895, -118.1598],
      ["Carson", 33.8314, -118.2820],
      ["Signal Hill", 33.8045, -118.1678],
    ];

    function setStatus(message){
      if(status) status.textContent = message;
    }

    function setLocationStatus(message){
      if(locationStatus) locationStatus.textContent = String(message || "").trim();
    }

    function populateSelect(select, items, emptyLabel){
      if(!select) return;
      const current = select.value;
      select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
      items.forEach((item)=>{
        const option = document.createElement("option");
        option.value = item.label || "";
        option.textContent = `${item.icon ? `${item.icon} ` : ""}${item.label || ""} (${item.count || 0})`;
        if(option.value === current) option.selected = true;
        select.appendChild(option);
      });
    }

    const directoryCategoryTaxonomy = [
      ["Food, Dining & Hospitality", "🍽", [["Restaurants & Dining", ["restaurant", "cafe", "eating place", "dining", "bar", "catering", "brew", "wine"]], ["Food, Grocery & Supply", ["food", "grocery", "bakery", "beverage", "ingredient"]], ["Hotels, Travel & Events", ["hotel", "motel", "lodging", "travel", "tourism", "event", "banquet", "wedding"]]]],
      ["Home, Construction & Property", "🔧", [["Construction & Trades", ["building", "contractor", "construction", "plumbing", "electrical", "roof", "floor", "handyman", "hvac", "landscape", "repair"]], ["Real Estate & Housing", ["real estate", "apartment", "property", "mortgage", "title", "leasing", "housing"]], ["Home Services", ["cleaning", "pest", "moving", "storage", "interior", "furniture", "home service"]]]],
      ["Health, Wellness & Personal Care", "✚", [["Medical & Dental", ["medical", "health care", "healthcare", "hospital", "doctor", "dentist", "dental", "physician", "optometry", "pharmacy"]], ["Wellness & Fitness", ["wellness", "fitness", "chiropr", "massage", "therapy", "mental health", "senior care"]], ["Beauty & Personal Care", ["beauty", "barber", "salon", "nail", "spa", "cosmetic"]]]],
      ["Shopping, Automotive & Consumer", "🛍", [["Retail & Shopping", ["retail", "shopping", "store", "jewelry", "apparel", "florist"]], ["Automotive & Transportation", ["auto", "vehicle", "transport", "shuttle", "airport", "towing", " car "]], ["Consumer Services", ["laundry", "pet", "recreation", "photo booth"]]]],
      ["Business, Finance & Legal", "$", [["Finance & Insurance", ["bank", "credit union", "financial", "account", "bookkeep", "tax", "insurance", "wealth", "lending", "merchant service"]], ["Legal & Public Services", ["attorney", "legal", "law", "government", "municipal", "utilities", "water district"]], ["Consulting & Professional", ["consultant", "professional", "employment", "human resources", "business service", "broker"]]]],
      ["Technology, Media & Creative", "⌘", [["Technology & Online", ["technology", "software", "computer", "e-commerce", "internet", "telecom", "app development"]], ["Marketing & Media", ["marketing", "advertising", "media", "printing", "publishing", "magazine", "graphic", "photography"]], ["Arts & Entertainment", ["entertainment", "artist", "performing", "music", "sports", "screen printing"]]]],
      ["Education, Community & Nonprofit", "🎓", [["Education & Training", ["education", "school", "college", "university", "training", "teacher"]], ["Nonprofits & Associations", ["non-profit", "nonprofit", "association", "chamber", "foundation", "church"]], ["Community Services", ["community", "youth", "social service"]]]],
      ["Manufacturing & Other Services", "◆", [["Manufacturing & Distribution", ["manufacturing", "mfg", "wholesale", "warehouse", "distributor", "supplier", "scientific"]], ["Industrial & Environmental", ["industrial", "environment", "energy", "solar", "engineering"]], ["Other Local Businesses", []]]],
    ];

    function groupDirectoryCategories(items){
      const groups = directoryCategoryTaxonomy.map(([label, icon, levels])=> ({
        label,
        icon,
        levels: levels.map(([levelLabel, keywords])=> ({ label: levelLabel, keywords, items: [] })),
      }));
      const fallbackLevels = groups[groups.length - 1].levels;
      const fallback = fallbackLevels[fallbackLevels.length - 1].items;
      items.forEach((item)=>{
        const normalized = ` ${String(item.label || "").toLowerCase()} `;
        let destination = null;
        groups.some((group)=> group.levels.some((level)=>{
          if(level.keywords.length && level.keywords.some((keyword)=> normalized.includes(keyword))){
            destination = level.items;
            return true;
          }
          return false;
        }));
        (destination || fallback).push(item);
      });
      return groups;
    }

    function renderCategoryHierarchy(items){
      if(!categoryHierarchy) return;
      if(categoryCount){
        categoryCount.textContent = `${items.length} business types`;
      }
      categoryHierarchy.innerHTML = groupDirectoryCategories(items).map((group)=>{
        const levels = group.levels.filter((level)=> level.items.length).map((level)=>{
          const levelCount = level.items.reduce((sum, item)=> sum + Number(item.count || 0), 0);
          const links = level.items.map((item)=> `<a class="directorySubcategoryLink" href="${themedDirectoryPath(`/directory/type/${encodeURIComponent(item.slug || "")}`)}"><span>${escapeHtml(item.label || "")}</span><em>${Number(item.count || 0)}</em></a>`).join("");
          return `<details class="directoryCategoryLevel"><summary><span>${escapeHtml(level.label)}</span><em>${levelCount}</em></summary><div class="directorySubcategoryGrid">${links}</div></details>`;
        }).join("");
        const groupCount = group.levels.flatMap((level)=> level.items).reduce((sum, item)=> sum + Number(item.count || 0), 0);
        return `<section class="directoryCategoryGroup"><div class="directoryCategoryGroupHeading"><span class="directoryIcon" aria-hidden="true">${escapeHtml(group.icon)}</span><strong>${escapeHtml(group.label)}</strong><em>${groupCount}</em></div><div class="directoryCategoryLevels">${levels}</div></section>`;
      }).join("");
    }

    function toRadians(value){
      return Number(value || 0) * Math.PI / 180;
    }

    function distanceMiles(lat1, lon1, lat2, lon2){
      const radiusMiles = 3958.8;
      const dLat = toRadians(lat2 - lat1);
      const dLon = toRadians(lon2 - lon1);
      const a = Math.sin(dLat / 2) ** 2
        + Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
      return radiusMiles * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function selectNearestDirectoryCity(coords){
      if(!citySelect || !coords) return false;
      const available = new Set(Array.from(citySelect.options).map((option)=> option.value).filter(Boolean));
      const ranked = serviceCities
        .filter(([name])=> available.has(name))
        .map(([name, lat, lon])=> ({
          name,
          distance: distanceMiles(coords.latitude, coords.longitude, lat, lon),
        }))
        .sort((a, b)=> a.distance - b.distance);
      const nearest = ranked[0];
      if(!nearest || nearest.distance > 85){
        setLocationStatus("Location on");
        return false;
      }
      citySelect.value = nearest.name;
      locationButton?.setAttribute("aria-pressed", "true");
      setLocationStatus(`Near ${nearest.name}`);
      return true;
    }

    function requestDirectoryLocation({ silent = false } = {}){
      if(!("geolocation" in navigator)){
        if(!silent) setLocationStatus("Location unavailable");
        return;
      }
      if(!silent) setLocationStatus("Checking location...");
      navigator.geolocation.getCurrentPosition(
        (position)=>{
          lastDirectoryCoords = {
            latitude: Number(position.coords.latitude),
            longitude: Number(position.coords.longitude),
          };
          if(!selectNearestDirectoryCity(lastDirectoryCoords)){
            setLocationStatus("Location on");
          }
        },
        ()=>{
          if(!silent) setLocationStatus("Location off");
        },
        {
          enableHighAccuracy: false,
          timeout: 4500,
          maximumAge: 300000,
        }
      );
    }

    function checkDirectoryLocationPermission(){
      if(!locationButton) return;
      if(!("geolocation" in navigator)){
        locationButton.disabled = true;
        setLocationStatus("Location unavailable");
        return;
      }
      if(navigator.permissions && navigator.permissions.query){
        navigator.permissions.query({ name: "geolocation" })
          .then((permission)=>{
            if(permission.state === "granted"){
              requestDirectoryLocation({ silent: true });
            } else if(permission.state === "denied"){
              setLocationStatus("Location off");
            }
            permission.onchange = ()=>{
              if(permission.state === "granted"){
                requestDirectoryLocation({ silent: true });
              } else if(permission.state === "denied"){
                setLocationStatus("Location off");
                locationButton.setAttribute("aria-pressed", "false");
              } else {
                setLocationStatus("");
              }
            };
          })
          .catch(()=> null);
      }
    }

    function renderResults(items, count){
      if(!results) return;
      if(!items.length){
        results.innerHTML = '<div class="directoryEmpty">No matching businesses yet. Try another search or city.</div>';
        return;
      }
      results.innerHTML = items.map((item)=>{
        const businessPath = themedDirectoryPath(`/business/${encodeURIComponent(item.slug || "")}`);
        const typePath = item.business_type_slug ? themedDirectoryPath(`/directory/type/${encodeURIComponent(item.business_type_slug)}`) : themedDirectoryPath("/directory");
        const cityText = [item.search_city, item.state, item.zip_code].filter(Boolean).join(", ");
        const website = externalHref(item.website);
        const mapLinks = directoryMapLinks(item);
        return `
          <article class="directoryMiniCard">
            ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.business_name)}" loading="lazy" />` : ""}
            <div>
              <div class="directoryResultType">
                <span class="directoryIcon" aria-hidden="true">${escapeHtml(item.business_type_icon || "•")}</span>
                <a href="${escapeHtml(typePath)}">${escapeHtml(item.business_type || "Local business")}</a>
              </div>
              <h3><a href="${escapeHtml(businessPath)}">${escapeHtml(item.business_name || "")}</a></h3>
              <p>${escapeHtml(item.description || "")}</p>
              <div class="directoryResultMeta">
                ${item.address ? `<span>${escapeHtml(item.address)}</span>` : ""}
                ${cityText ? `<span>${escapeHtml(cityText)}</span>` : ""}
              </div>
              <div class="directoryResultContact">
                ${item.phone_number ? `<span>${escapeHtml(item.phone_number)}</span>` : ""}
                ${website ? `<span><a href="${escapeHtml(website)}" target="_blank" rel="noopener nofollow">Website</a></span>` : ""}
              </div>
              ${mapLinks}
            </div>
          </article>
        `;
      }).join("");
      setStatus(`${Number(count || items.length)} businesses found. Showing ${items.length}.`);
    }

    async function loadFacets(){
      const response = await fetch("/v1/business-directory/facets", { cache: "no-store" });
      if(!response.ok){
        throw new Error(`Directory facets failed (${response.status})`);
      }
      const body = await response.json();
      populateSelect(citySelect, body.cities || [], "All cities");
      populateSelect(typeSelect, body.business_types || [], "All business types");
      renderCategoryHierarchy(body.business_types || []);
      if(lastDirectoryCoords){
        selectNearestDirectoryCity(lastDirectoryCoords);
      }
      facetsLoaded = true;
    }

    async function runSearch(){
      const params = new URLSearchParams();
      params.set("limit", "6");
      params.set("q", input ? input.value.trim() : "");
      if(citySelect && citySelect.value) params.set("city", citySelect.value);
      if(typeSelect && typeSelect.value) params.set("business_type", typeSelect.value);
      setStatus("Searching directory...");
      const response = await fetch(`/v1/business-directory/search?${params.toString()}`, { cache: "no-store" });
      if(!response.ok){
        throw new Error(`Directory search failed (${response.status})`);
      }
      const body = await response.json();
      if(!facetsLoaded && body.facets){
        populateSelect(citySelect, body.facets.cities || [], "All cities");
        populateSelect(typeSelect, body.facets.business_types || [], "All business types");
        renderCategoryHierarchy(body.facets.business_types || []);
        facetsLoaded = true;
      }
      renderResults(body.results || [], body.count || 0);
    }

    function scheduleSearch(){
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(()=>{
        runSearch().catch(()=> setStatus("Directory search is temporarily unavailable."));
      }, 250);
    }

    if(form){
      if(previewOnly){
        loadFacets().catch(()=> null);
        return;
      }

      form.addEventListener("submit", (event)=>{
        event.preventDefault();
        runSearch().catch(()=> setStatus("Directory search is temporarily unavailable."));
      });
    }
    if(input) input.addEventListener("input", scheduleSearch);
    if(citySelect) citySelect.addEventListener("change", scheduleSearch);
    if(typeSelect) typeSelect.addEventListener("change", scheduleSearch);
    if(locationButton){
      locationButton.addEventListener("click", ()=> requestDirectoryLocation());
      checkDirectoryLocationPermission();
    }
    loadFacets()
      .catch(()=> null)
      .then(()=> runSearch())
      .catch(()=> setStatus("Directory search is temporarily unavailable."));
  }

  wireBusinessDirectorySearch();

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

  function cleanAssistantText(text){
    return String(text || "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/\*\*/g, "")
      .replace(/__/g, "")
      .trim();
  }

  function appendHomeAssistantMessage(messagesNode, role, text){
    if(!messagesNode) return;
    const bubble = document.createElement("div");
    bubble.className = `aiBubble ${role === "user" ? "user" : "assistant"}`;
    bubble.textContent = role === "user" ? String(text || "").trim() : cleanAssistantText(text);
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
          "Ask about current PerkNation promotions, business listings, nearby categories, or local restaurant picks."
        );
        setStatus("Cleared. Ask about current promotions, business listings, or local picks.");
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
      setStatus("Checking current PerkNation data...");

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
