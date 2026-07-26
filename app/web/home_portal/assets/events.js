(async function () {
  const editorialEvents = Array.isArray(window.PERK_NATION_EVENTS) ? window.PERK_NATION_EVENTS : [];
  const eventBase = location.pathname.startsWith("/white/") ? "/white/events" : "/events";
  const directoryBase = location.pathname.startsWith("/white/") ? "/white/directory" : "/directory";
  const escapeHtml = (value) => String(value || "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
  const safeColor = (value, fallback) => /^#[0-9a-f]{6}$/i.test(String(value || "")) ? value : fallback;

  async function loadNflTeams() {
    const script = document.querySelector('script[src*="/assets/events.js"]');
    let version = "";
    try {
      const build = script ? new URL(script.src, location.origin).searchParams.get("v") : "";
      version = build ? `?v=${encodeURIComponent(build)}` : "";
    } catch (_) {
      version = "";
    }
    const response = await fetch(`/assets/nfl-2026-schedules.json${version}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`NFL schedule data failed (${response.status})`);
    const payload = await response.json();
    return Array.isArray(payload.teams) ? payload.teams : [];
  }

  function nflEvent(team) {
    const opener = team.opener || {};
    const siteWord = opener.site === "home" ? "host" : "visit";
    const matchupWord = opener.site === "home" ? "against" : "at";
    return {
      slug: team.slug,
      category: "Season openers",
      title: `${team.name} 2026 season opener and full schedule`,
      eventName: `${team.name} 2026 season opener`,
      date: opener.date,
      time: opener.time,
      venue: opener.venue,
      city: team.city,
      summary: `${team.shortName} ${siteWord} ${opener.opponent} in Week 1. See all 18 weeks, kickoff times, networks, venues, and the bye.`,
      intro: `${team.name} open the 2026 regular season ${matchupWord} ${opener.opponent} on ${opener.date} at ${opener.time}.`,
      paragraphs: [
        `The opening matchup is set for ${opener.venue} and is scheduled on ${opener.network}. The table below keeps every announced regular-season week in one place, with Pacific kickoff times for PerkNation readers.`,
        `This guide is best for fans planning watch parties, game-day dining, travel, and weekends around the ${team.shortName}. Week 18 timing and other eligible games can move under NFL flexible-scheduling procedures, so verify the official schedule before booking.`,
      ],
      highlights: [
        `Week 1 ${opener.site === "home" ? "vs" : "at"} ${opener.opponent}`,
        `${team.conference} ${team.division}`,
        "18 weeks including the bye",
        "Kickoff times shown in Pacific Time",
      ],
      scheduleTitle: `${team.name} 2026 regular-season schedule`,
      scheduleNote: "Times are shown in Pacific Time. Week 18 and eligible games may change; confirm on the official NFL schedule before making plans.",
      schedule: team.schedule,
      officialUrl: team.officialUrl,
      image: team.logo,
      imageAlt: `${team.name} official club mark`,
      credit: "Official NFL club schedule",
      isNfl: true,
      usesTeamLogo: true,
      teamName: team.name,
      conference: team.conference,
      division: team.division,
      color: team.color,
      alternateColor: team.alternateColor,
    };
  }

  let nflTeams = [];
  try {
    nflTeams = await loadNflTeams();
  } catch (error) {
    console.error(error);
  }

  const editorialBySlug = new Map(editorialEvents.map((event) => [event.slug, event]));
  const nflEvents = nflTeams.map((team) => {
    const generated = nflEvent(team);
    const editorial = editorialBySlug.get(team.slug);
    if (!editorial) return generated;
    return {
      ...generated,
      ...editorial,
      schedule: team.schedule,
      scheduleTitle: `${team.name} 2026 regular-season schedule`,
      scheduleNote: generated.scheduleNote,
      isNfl: true,
      usesTeamLogo: false,
      teamName: team.name,
      conference: team.conference,
      division: team.division,
      color: team.color,
      alternateColor: team.alternateColor,
    };
  });
  const nflSlugs = new Set(nflEvents.map((event) => event.slug));
  const events = [...editorialEvents.filter((event) => !nflSlugs.has(event.slug)), ...nflEvents];

  function eventCard(event) {
    return `<article class="eventCard">
      <a class="eventCardMedia" href="${eventBase}/${encodeURIComponent(event.slug)}">
        <img src="${escapeHtml(event.image)}" alt="${escapeHtml(event.imageAlt)}" loading="lazy" referrerpolicy="no-referrer" />
        <span class="eventCategory">${escapeHtml(event.category)}</span>
      </a>
      <div class="eventCardBody">
        <div class="eventMeta">${escapeHtml(event.date)} · ${escapeHtml(event.city)}</div>
        <h3><a href="${eventBase}/${encodeURIComponent(event.slug)}">${escapeHtml(event.title)}</a></h3>
        <p>${escapeHtml(event.summary)}</p>
        <div class="eventCardActions">
          <a class="btn small primary" href="${eventBase}/${encodeURIComponent(event.slug)}">Read article</a>
          <a class="btn small" href="${escapeHtml(event.officialUrl)}" target="_blank" rel="noopener noreferrer">Official page ↗</a>
        </div>
      </div>
    </article>`;
  }

  function teamLink(team) {
    const opener = team.opener || {};
    const site = opener.site === "home" ? "vs" : "at";
    return `<a class="nflTeamLink" href="${eventBase}/${encodeURIComponent(team.slug)}">
      <img src="${escapeHtml(team.logo)}" alt="" loading="lazy" referrerpolicy="no-referrer" />
      <span><strong>${escapeHtml(team.shortName)}</strong><small>Week 1 ${escapeHtml(site)} ${escapeHtml(opener.opponent)} · ${escapeHtml(opener.time)}</small></span>
      <span aria-hidden="true">→</span>
    </a>`;
  }

  function conferenceMarkup(conference) {
    const divisions = ["East", "North", "South", "West"];
    return `<section class="nflConference" aria-labelledby="${conference.toLowerCase()}-teams">
      <div class="nflConferenceHeading"><span>${escapeHtml(conference)}</span><strong id="${conference.toLowerCase()}-teams">${conference === "AFC" ? "American" : "National"} Football Conference</strong></div>
      <div class="nflDivisionGrid">${divisions.map((division) => {
        const teams = nflTeams.filter((team) => team.conference === conference && team.division === division);
        return `<div class="nflDivision"><h3>${escapeHtml(conference)} ${escapeHtml(division)}</h3>${teams.map(teamLink).join("")}</div>`;
      }).join("")}</div>
    </section>`;
  }

  function seasonOpenersMarkup() {
    const featured = nflTeams
      .filter((team) => team.featured)
      .map((team) => events.find((event) => event.slug === team.slug))
      .filter(Boolean);
    return `<section class="eventCategorySection" id="season-openers">
      <div class="eventSectionHeading"><div><span class="badge">Season openers</span><h2 class="h2">Featured California teams</h2><p class="muted">Start with the three featured teams, then expand the league guide for every AFC and NFC club.</p></div><span>3 featured · 32 teams</span></div>
      <div class="eventGrid">${featured.map(eventCard).join("")}</div>
      <details class="nflLeagueExplorer">
        <summary><span><strong>Explore all 32 NFL teams</strong><small>Organized by AFC, NFC, and division</small></span><span class="nflExplorerAction">Expand league guide</span></summary>
        <div class="nflLeagueBody">
          <div class="nflLeagueIntro"><div><span class="badge">2026 regular season</span><h2>Every team. Every announced week.</h2></div><a href="https://www.nfl.com/schedules/2026/by-team" target="_blank" rel="noopener noreferrer">Official NFL team schedules ↗</a></div>
          ${conferenceMarkup("AFC")}
          ${conferenceMarkup("NFC")}
        </div>
      </details>
    </section>`;
  }

  function scheduleMarkup(event) {
    const schedule = Array.isArray(event.schedule) ? event.schedule : [];
    if (!schedule.length) return "";
    const rows = schedule.map((game) => {
      const site = String(game.site || "").toLowerCase();
      const siteLabel = site === "home" ? "vs" : site === "away" ? "at" : site === "neutral" ? "neutral" : "";
      const matchup = site === "bye"
        ? `<strong>${escapeHtml(game.opponent)}</strong>`
        : `<span class="eventScheduleSite ${escapeHtml(site)}">${escapeHtml(siteLabel)}</span><strong>${escapeHtml(game.opponent)}</strong>`;
      return `<tr>
        <th scope="row">${escapeHtml(game.week)}</th>
        <td>${escapeHtml(game.date)}</td>
        <td><div class="eventScheduleMatchup">${matchup}</div></td>
        <td>${escapeHtml(game.time)}</td>
        <td>${escapeHtml(game.network)}</td>
        <td>${escapeHtml(game.venue || "—")}</td>
      </tr>`;
    }).join("");

    return `<section class="eventSchedule" aria-labelledby="event-schedule-title">
      <div class="eventScheduleHeading">
        <div><span class="badge">Full announced season</span><h2 id="event-schedule-title">${escapeHtml(event.scheduleTitle || "Regular-season schedule")}</h2></div>
        <a class="btn small" href="${escapeHtml(event.officialUrl)}" target="_blank" rel="noopener noreferrer">Official schedule ↗</a>
      </div>
      <p class="eventScheduleNote">${escapeHtml(event.scheduleNote || "Schedule details may change. Confirm with the team before making plans.")}</p>
      <div class="eventScheduleTableWrap">
        <table class="eventScheduleTable">
          <thead><tr><th scope="col">Week</th><th scope="col">Date</th><th scope="col">Matchup</th><th scope="col">Time PT</th><th scope="col">Watch</th><th scope="col">Venue</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>`;
  }

  const hub = document.querySelector("[data-events-hub]");
  if (hub) {
    const categories = ["Concerts", "Live events", "Sports"];
    const standardSections = categories.map((category) => {
      const matches = events.filter((event) => event.category === category);
      if (!matches.length) return "";
      const id = category.toLowerCase().replace(/\s+/g, "-");
      return `<section class="eventCategorySection" id="${id}">
        <div class="eventSectionHeading"><div><span class="badge">${escapeHtml(category)}</span><h2 class="h2">${escapeHtml(category)}</h2></div><span>${matches.length} picks</span></div>
        <div class="eventGrid">${matches.map(eventCard).join("")}</div>
      </section>`;
    }).join("");
    hub.innerHTML = `${standardSections}${seasonOpenersMarkup()}`;
  }

  const article = document.querySelector("[data-event-article]");
  if (article) {
    const slug = location.pathname.split("/").filter(Boolean).pop();
    const event = events.find((item) => item.slug === slug);
    if (!event) {
      article.innerHTML = `<div class="eventNotFound"><span class="badge">Events</span><h1 class="h1">Event article not found.</h1><a class="btn primary" href="${eventBase}">Browse events</a></div>`;
      document.title = "Event not found | Perk Nation";
      return;
    }
    document.title = `${event.title} | Perk Nation Events`;
    const description = document.querySelector('meta[name="description"]');
    if (description) description.setAttribute("content", event.summary);
    const canonical = document.querySelector('link[rel="canonical"]');
    if (canonical) canonical.setAttribute("href", `/events/${event.slug}`);
    const media = event.usesTeamLogo
      ? `<figure class="eventArticleMedia nflTeamMedia" style="--team-color:${safeColor(event.color, "#013369")};--team-alt:${safeColor(event.alternateColor, "#d50a0a")}">
          <div class="nflTeamHero"><span>${escapeHtml(event.conference)} ${escapeHtml(event.division)}</span><img src="${escapeHtml(event.image)}" alt="${escapeHtml(event.imageAlt)}" referrerpolicy="no-referrer" /><strong>${escapeHtml(event.teamName)}</strong></div>
          <figcaption>${escapeHtml(event.credit)}. Schedule details may change; confirm with the NFL.</figcaption>
        </figure>`
      : `<figure class="eventArticleMedia">
          <img src="${escapeHtml(event.image)}" alt="${escapeHtml(event.imageAlt)}" referrerpolicy="no-referrer" />
          <figcaption>${escapeHtml(event.credit)}. Event details may change; confirm with the organizer.</figcaption>
        </figure>`;
    article.innerHTML = `<article class="eventArticle">
      <a class="eventBack" href="${eventBase}">← All events</a>
      <div class="eventArticleHero">
        <div class="eventArticleCopy">
          <span class="badge">${escapeHtml(event.category)}</span>
          <h1 class="h1">${escapeHtml(event.title)}</h1>
          <p class="eventArticleLead">${escapeHtml(event.intro)}</p>
          <div class="eventFacts">
            <div><span>Date</span><strong>${escapeHtml(event.date)}</strong></div>
            <div><span>Time</span><strong>${escapeHtml(event.time)}</strong></div>
            <div><span>Venue</span><strong>${escapeHtml(event.venue)}</strong></div>
            <div><span>${event.isNfl ? "Team" : "City"}</span><strong>${escapeHtml(event.isNfl ? event.teamName : event.city)}</strong></div>
          </div>
          <a class="btn primary" href="${escapeHtml(event.officialUrl)}" target="_blank" rel="noopener noreferrer">Official event page ↗</a>
          <div class="sharePanel" data-share-panel data-share-title="${escapeHtml(event.title)}" data-share-text="${escapeHtml(event.summary)}" data-share-url="${escapeHtml(`${location.origin}/events/${event.slug}`)}">
            <div class="shareIntro"><span>Share this event</span><strong>Send this plan to friends.</strong></div>
            <div class="shareActions" aria-label="Share options">
              <button type="button" data-share-action="instagram">Instagram</button><button type="button" data-share-action="facebook">Facebook</button><button type="button" data-share-action="tiktok">TikTok</button><button type="button" data-share-action="sms">SMS</button><button type="button" data-share-action="imessage">iMessage</button><button type="button" data-share-action="email">Email</button><button type="button" data-share-action="copy">Copy link</button>
            </div>
            <div class="shareStatus" data-share-status aria-live="polite"></div>
          </div>
        </div>
        ${media}
      </div>
      ${scheduleMarkup(event)}
      <div class="eventArticleBody">
        <div class="eventStory"><h2>What to know</h2>${event.paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
          ${event.isNfl ? `<div class="eventInternalLinks"><h3>Plan around game day</h3><a href="${eventBase}">Browse the 32-team NFL guide</a><a href="${directoryBase}?q=sports%20bar">Find sports bars</a><a href="${directoryBase}?q=restaurant">Find restaurants</a><a href="${directoryBase}?q=hotel">Find hotels</a></div>` : ""}
        </div>
        <aside class="eventHighlights"><h2>${event.isNfl ? "Best for & key details" : "Event highlights"}</h2><ul>${event.highlights.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><a href="${escapeHtml(event.officialUrl)}" target="_blank" rel="noopener noreferrer">Verify details on the official page ↗</a></aside>
      </div>
    </article>`;

    const schema = document.createElement("script");
    schema.type = "application/ld+json";
    schema.text = JSON.stringify({
      "@context": "https://schema.org", "@type": "Event", name: event.eventName,
      description: event.summary, image: [event.image], url: `${location.origin}/events/${event.slug}`,
      location: { "@type": "Place", name: event.venue, address: event.city },
      organizer: { "@type": "Organization", name: event.isNfl ? event.teamName : event.venue, url: event.officialUrl }
    });
    document.head.appendChild(schema);
  }
})();
