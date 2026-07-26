(function () {
  const events = Array.isArray(window.PERK_NATION_EVENTS) ? window.PERK_NATION_EVENTS : [];
  const eventBase = location.pathname.startsWith("/white/") ? "/white/events" : "/events";
  const escapeHtml = (value) => String(value || "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);

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
          <thead><tr><th scope="col">Week</th><th scope="col">Date</th><th scope="col">Matchup</th><th scope="col">Time PT</th><th scope="col">Watch</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>`;
  }

  const hub = document.querySelector("[data-events-hub]");
  if (hub) {
    const categories = ["Concerts", "Live events", "Sports", "Season openers"];
    hub.innerHTML = categories.map((category) => {
      const matches = events.filter((event) => event.category === category);
      if (!matches.length) return "";
      const id = category.toLowerCase().replace(/\s+/g, "-");
      return `<section class="eventCategorySection" id="${id}">
        <div class="eventSectionHeading"><div><span class="badge">${escapeHtml(category)}</span><h2 class="h2">${escapeHtml(category)}</h2></div><span>${matches.length} picks</span></div>
        <div class="eventGrid">${matches.map(eventCard).join("")}</div>
      </section>`;
    }).join("");
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
    if (canonical) canonical.setAttribute("href", `${eventBase}/${event.slug}`);
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
            <div><span>City</span><strong>${escapeHtml(event.city)}</strong></div>
          </div>
          <a class="btn primary" href="${escapeHtml(event.officialUrl)}" target="_blank" rel="noopener noreferrer">Official event page ↗</a>
          <div class="sharePanel" data-share-panel data-share-title="${escapeHtml(event.title)}" data-share-text="${escapeHtml(event.summary)}" data-share-url="${escapeHtml(`${location.origin}${eventBase}/${event.slug}`)}">
            <div class="shareIntro"><span>Share this event</span><strong>Send this plan to friends.</strong></div>
            <div class="shareActions" aria-label="Share options">
              <button type="button" data-share-action="instagram">Instagram</button>
              <button type="button" data-share-action="facebook">Facebook</button>
              <button type="button" data-share-action="tiktok">TikTok</button>
              <button type="button" data-share-action="sms">SMS</button>
              <button type="button" data-share-action="imessage">iMessage</button>
              <button type="button" data-share-action="email">Email</button>
              <button type="button" data-share-action="copy">Copy link</button>
            </div>
            <div class="shareStatus" data-share-status aria-live="polite"></div>
          </div>
        </div>
        <figure class="eventArticleMedia">
          <img src="${escapeHtml(event.image)}" alt="${escapeHtml(event.imageAlt)}" referrerpolicy="no-referrer" />
          <figcaption>${escapeHtml(event.credit)}. Event details may change; confirm with the organizer.</figcaption>
        </figure>
      </div>
      ${scheduleMarkup(event)}
      <div class="eventArticleBody">
        <div class="eventStory"><h2>What to know</h2>${event.paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}</div>
        <aside class="eventHighlights"><h2>Event highlights</h2><ul>${event.highlights.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><a href="${escapeHtml(event.officialUrl)}" target="_blank" rel="noopener noreferrer">Verify details on the official page ↗</a></aside>
      </div>
    </article>`;

    const schema = document.createElement("script");
    schema.type = "application/ld+json";
    schema.text = JSON.stringify({
      "@context": "https://schema.org", "@type": "Event", name: event.eventName,
      description: event.summary, image: [event.image], url: `${location.origin}${eventBase}/${event.slug}`,
      location: { "@type": "Place", name: event.venue, address: event.city },
      organizer: { "@type": "Organization", name: event.venue, url: event.officialUrl }
    });
    document.head.appendChild(schema);
  }
})();
