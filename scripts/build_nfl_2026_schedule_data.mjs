import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const teams = [
  ["ari", "ARI", "Arizona Cardinals", "Cardinals", "NFC", "West", "arizona-cardinals"],
  ["atl", "ATL", "Atlanta Falcons", "Falcons", "NFC", "South", "atlanta-falcons"],
  ["bal", "BAL", "Baltimore Ravens", "Ravens", "AFC", "North", "baltimore-ravens"],
  ["buf", "BUF", "Buffalo Bills", "Bills", "AFC", "East", "buffalo-bills"],
  ["car", "CAR", "Carolina Panthers", "Panthers", "NFC", "South", "carolina-panthers"],
  ["chi", "CHI", "Chicago Bears", "Bears", "NFC", "North", "chicago-bears"],
  ["cin", "CIN", "Cincinnati Bengals", "Bengals", "AFC", "North", "cincinnati-bengals"],
  ["cle", "CLE", "Cleveland Browns", "Browns", "AFC", "North", "cleveland-browns"],
  ["dal", "DAL", "Dallas Cowboys", "Cowboys", "NFC", "East", "dallas-cowboys"],
  ["den", "DEN", "Denver Broncos", "Broncos", "AFC", "West", "denver-broncos"],
  ["det", "DET", "Detroit Lions", "Lions", "NFC", "North", "detroit-lions"],
  ["gb", "GB", "Green Bay Packers", "Packers", "NFC", "North", "green-bay-packers"],
  ["hou", "HOU", "Houston Texans", "Texans", "AFC", "South", "houston-texans"],
  ["ind", "IND", "Indianapolis Colts", "Colts", "AFC", "South", "indianapolis-colts"],
  ["jax", "JAX", "Jacksonville Jaguars", "Jaguars", "AFC", "South", "jacksonville-jaguars"],
  ["kc", "KC", "Kansas City Chiefs", "Chiefs", "AFC", "West", "kansas-city-chiefs"],
  ["lv", "LV", "Las Vegas Raiders", "Raiders", "AFC", "West", "las-vegas-raiders"],
  ["lac", "LAC", "Los Angeles Chargers", "Chargers", "AFC", "West", "los-angeles-chargers"],
  ["lar", "LA", "Los Angeles Rams", "Rams", "NFC", "West", "los-angeles-rams"],
  ["mia", "MIA", "Miami Dolphins", "Dolphins", "AFC", "East", "miami-dolphins"],
  ["min", "MIN", "Minnesota Vikings", "Vikings", "NFC", "North", "minnesota-vikings"],
  ["ne", "NE", "New England Patriots", "Patriots", "AFC", "East", "new-england-patriots"],
  ["no", "NO", "New Orleans Saints", "Saints", "NFC", "South", "new-orleans-saints"],
  ["nyg", "NYG", "New York Giants", "Giants", "NFC", "East", "new-york-giants"],
  ["nyj", "NYJ", "New York Jets", "Jets", "AFC", "East", "new-york-jets"],
  ["phi", "PHI", "Philadelphia Eagles", "Eagles", "NFC", "East", "philadelphia-eagles"],
  ["pit", "PIT", "Pittsburgh Steelers", "Steelers", "AFC", "North", "pittsburgh-steelers"],
  ["sf", "SF", "San Francisco 49ers", "49ers", "NFC", "West", "san-francisco-49ers"],
  ["sea", "SEA", "Seattle Seahawks", "Seahawks", "NFC", "West", "seattle-seahawks"],
  ["tb", "TB", "Tampa Bay Buccaneers", "Buccaneers", "NFC", "South", "tampa-bay-buccaneers"],
  ["ten", "TEN", "Tennessee Titans", "Titans", "AFC", "South", "tennessee-titans"],
  ["wsh", "WAS", "Washington Commanders", "Commanders", "NFC", "East", "washington-commanders"],
];

const featuredSlugs = {
  lac: "chargers-home-opener-2026",
  lar: "rams-home-opener-2026",
  sf: "49ers-home-opener-2026",
};

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  weekday: "short",
  month: "short",
  day: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  hour: "numeric",
  minute: "2-digit",
});

function slugFor(id, officialSlug) {
  return featuredSlugs[id] || `${officialSlug}-season-opener-2026`;
}

function normalizeNetwork(competition) {
  const networks = (competition.broadcasts || [])
    .map((broadcast) => broadcast?.media?.shortName)
    .filter(Boolean);
  const labels = networks.map((network) => ({
    "NFL Net": "NFL Network",
    "ESPN Unlmtd": "ESPN",
  })[network] || network);
  return [...new Set(labels)].join(" / ") || "TBD";
}

function scheduleEntry(event, teamName) {
  const competition = event.competitions?.[0] || {};
  const competitors = competition.competitors || [];
  const team = competitors.find((entry) => entry.team?.displayName === teamName);
  const opponent = competitors.find((entry) => entry.team?.displayName !== teamName);
  const isTbd = Boolean(competition.status?.isTBDFlex)
    || /TBD/i.test(competition.status?.type?.detail || "")
    || (Number(event.week?.number) === 18 && String(event.date || "").endsWith("05:00Z"));
  const start = new Date(event.date);
  const week = Number(event.week?.number);
  return {
    week,
    date: week === 18 && isTbd ? "Jan 9 or 10" : dateFormatter.format(start),
    site: team?.homeAway === "home" ? "home" : "away",
    opponent: opponent?.team?.displayName || "Opponent TBD",
    time: isTbd ? "TBD" : `${timeFormatter.format(start)} PT`,
    network: normalizeNetwork(competition),
    venue: competition.venue?.fullName || "Venue TBD",
  };
}

function preseasonEntry(event, teamName, index) {
  const game = scheduleEntry(event, teamName);
  return {
    ...game,
    week: index + 1,
  };
}

async function loadTeam(meta) {
  const [id, nflAbbreviation, name, shortName, conference, division, officialSlug] = meta;
  const regularEndpoint = `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/${id}/schedule?season=2026&seasontype=2`;
  const preseasonEndpoint = `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/${id}/schedule?season=2026&seasontype=1`;
  const [regularResponse, preseasonResponse] = await Promise.all([
    fetch(regularEndpoint),
    fetch(preseasonEndpoint),
  ]);
  if (!regularResponse.ok) throw new Error(`${name} regular season: ${regularResponse.status} ${regularResponse.statusText}`);
  if (!preseasonResponse.ok) throw new Error(`${name} preseason: ${preseasonResponse.status} ${preseasonResponse.statusText}`);
  const [payload, preseasonPayload] = await Promise.all([
    regularResponse.json(),
    preseasonResponse.json(),
  ]);
  const games = (payload.events || [])
    .map((event) => scheduleEntry(event, name))
    .sort((left, right) => left.week - right.week);
  const byWeek = new Map(games.map((game) => [game.week, game]));
  const schedule = Array.from({ length: 18 }, (_, index) => {
    const week = index + 1;
    return byWeek.get(week) || {
      week,
      date: "Bye",
      site: "bye",
      opponent: "Bye week",
      time: "—",
      network: "—",
      venue: "—",
    };
  });
  const preseason = (preseasonPayload.events || [])
    .sort((left, right) => new Date(left.date) - new Date(right.date))
    .map((event, index) => preseasonEntry(event, name, index));
  const opener = schedule[0];
  const firstHome = schedule.find((game) => game.site === "home");
  return {
    id,
    abbreviation: nflAbbreviation,
    name,
    shortName,
    city: payload.team?.location || name.replace(new RegExp(`\\s+${shortName}$`), ""),
    conference,
    division,
    slug: slugFor(id, officialSlug),
    officialUrl: `https://www.nfl.com/schedules/2026/by-team/${officialSlug}`,
    logo: `https://static.www.nfl.com/league/api/clubs/logos/${nflAbbreviation}`,
    color: `#${payload.team?.color || "013369"}`,
    alternateColor: `#${payload.team?.alternateColor || "d50a0a"}`,
    venue: firstHome?.venue || "Venue TBD",
    featured: Object.hasOwn(featuredSlugs, id),
    opener,
    preseason,
    schedule,
  };
}

const output = {
  season: 2026,
  sourceLabel: "Official NFL 2026 team schedules",
  sourceUrl: "https://www.nfl.com/schedules/2026/by-team",
  preseasonSourceLabel: "Official NFL 2026 preseason opponents and club schedule announcements",
  preseasonSourceUrl: "https://www.nfl.com/news/2026-nfl-preseason-complete-team-by-team-opponents",
  teams: await Promise.all(teams.map(loadTeam)),
};

output.teams.sort((left, right) => (
  left.conference.localeCompare(right.conference)
  || left.division.localeCompare(right.division)
  || left.name.localeCompare(right.name)
));

const currentFile = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(currentFile), "..");
const destination = path.join(root, "app", "web", "home_portal", "assets", "nfl-2026-schedules.json");
await fs.writeFile(destination, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(`Wrote ${output.teams.length} teams to ${destination}`);
