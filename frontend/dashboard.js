// ============================================
// DASHBOARD JS — OpportUnity Hub
// ============================================

const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') && window.location.port !== '8000' 
  ? 'http://localhost:8000' 
  : (localStorage.getItem('ohub_backend_url') || window.location.origin);
const token = localStorage.getItem("ohub_token");

let opportunities     = [];
let liveOpportunities = [];   // holds results from the API
let usingLiveData     = true;
let activeTypeFilter  = "all";
let searchQuery       = "";
let sourceFilter      = "";
let deadlineFilter    = "";
let domainFilter      = "";  // empty = all domains
let locationFilter    = "all";

// ---- INIT ----
document.addEventListener("DOMContentLoaded", () => {
  if (!token) {
    window.location.href = "login.html";
    return;
  }
  loadUserInfo();
  initGreeting();
  loadDashboardData();
  initSearch();
});

function loadUserInfo() {
  const user = JSON.parse(localStorage.getItem("ohub_user") || "{}");
  const name = user.name || "Student";
  const email = user.email || "student@university.edu";
  const initials = name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();

  const sidebarName = document.getElementById("sidebarName");
  const sidebarEmail = document.getElementById("sidebarEmail");
  const sidebarAvatar = document.getElementById("sidebarAvatar");
  if (sidebarName)  sidebarName.textContent  = name;
  if (sidebarEmail) sidebarEmail.textContent = email;
  if (sidebarAvatar) sidebarAvatar.textContent = initials;

  const greetingEl = document.getElementById("greetingText");
  if (greetingEl) {
    const hour = new Date().getHours();
    const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    greetingEl.textContent = `${greeting}, ${name.split(" ")[0]} 👋`;
  }

  // Add quick log out / switch account button to sidebar
  const sidebarUser = document.querySelector(".sidebar-user");
  if (sidebarUser && !document.getElementById("switchAccountBtn")) {
    const switchBtn = document.createElement("button");
    switchBtn.id = "switchAccountBtn";
    switchBtn.title = "Log out / Switch account";
    switchBtn.style.cssText = "background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:14px;margin-left:auto;padding:4px;border-radius:4px;";
    switchBtn.innerHTML = "🚪";
    switchBtn.onclick = (e) => {
      e.stopPropagation();
      if (confirm("Log out of current account?")) {
        localStorage.clear();
        window.location.href = "login.html";
      }
    };
    sidebarUser.appendChild(switchBtn);
  }
}

function initGreeting() {}  // handled in loadUserInfo

// ============================================================
// DATA LOAD & SYNC
// ============================================================

async function loadDashboardData() {
  try {
    // 1. Fetch Stats
    let stats = {};
    try {
      const statsRes = await fetch(`${API_BASE}/api/opportunities/stats`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (statsRes.status === 401) {
        localStorage.clear();
        window.location.href = "login.html";
        return;
      }
      if (statsRes.ok) {
        stats = await statsRes.json();
      }
    } catch (e) {
      console.warn("Stats API call failed, using local count:", e);
    }

    // 2. Fetch Opportunities from Database
    let fetchedOpps = [];
    try {
      const oppsRes = await fetch(`${API_BASE}/api/opportunities`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (oppsRes.ok) {
        const oppsData = await oppsRes.json();
        fetchedOpps = (oppsData.opportunities || []).map(o => ({
          ...o,
          role: o.title || o.role,
          applyLink: o.application_link || o.apply_link || o.applyLink,
          logo: o.organization ? o.organization.charAt(0).toUpperCase() : "?",
          type: (o.category || o.type || "internship").toLowerCase(),
          source: detectSource(o),
          verified: true
        }));
      }
    } catch (e) {
      console.warn("Opportunities API call failed:", e);
    }
    
    // Priority: DB records > Cached live scraped records > Mock records
    if (fetchedOpps.length > 0) {
      opportunities = fetchedOpps;
    } else {
      const cache = localStorage.getItem("ohub_scraped_cache");
      if (cache) {
        try {
          const cachedList = JSON.parse(cache);
          if (Array.isArray(cachedList) && cachedList.length > 0) {
            opportunities = cachedList;
          }
        } catch (e) {
          console.warn("Invalid cached opportunities:", e);
        }
      }
      if (opportunities.length === 0 && typeof MOCK_OPPORTUNITIES !== "undefined") {
        opportunities = MOCK_OPPORTUNITIES.map(o => ({
          ...o,
          type: (o.type || "internship").toLowerCase(),
          source: detectSource(o),
          verified: true
        }));
      }
    }
    
    window.opportunities = opportunities;
    
    // Update metric counters
    const totalEl      = document.getElementById("totalCount");
    const internEl     = document.getElementById("internshipCount");
    const hackEl       = document.getElementById("hackathonCount");
    const savedEl      = document.getElementById("savedCount");
    const appliedSubEl = document.getElementById("appliedCountSub");
    if (totalEl)      totalEl.textContent      = stats.total || opportunities.length || 0;
    if (internEl)     internEl.textContent     = stats.internships || opportunities.filter(o => o.type === "internship").length || 0;
    if (hackEl)       hackEl.textContent       = stats.hackathons || opportunities.filter(o => o.type === "hackathon" || o.type === "job").length || 0;
    if (savedEl)      savedEl.textContent      = stats.saved || opportunities.filter(o => o.saved).length || 0;
    if (appliedSubEl) appliedSubEl.textContent = `applied: ${stats.applied || opportunities.filter(o => o.applied).length || 0}`;

    // Separate live-synced
    liveOpportunities = opportunities.filter(o => o.source === "gmail" || o.source_email || o.source !== "unknown");

    renderStatsRow();
    renderDeadlineTimeline();
    renderCards();
    
    // Update data status banner
    if (opportunities.length > 0) {
      setDataStatusBanner("live", opportunities.length, "database");
    } else {
      setDataStatusBanner("empty");
      // Auto-trigger live fetch on initial page load if no opportunities exist
      if (!window._autoFetchTriggered) {
        window._autoFetchTriggered = true;
        fetchLiveOpportunities();
      }
    }
  } catch (err) {
    console.error("Dashboard load failed:", err);
    if (opportunities.length === 0) {
      setDataStatusBanner("offline");
      showToast("⚠️ Could not fetch data from server.", "warning");
    }
  }
}

// ============================================================
// LIVE FETCH — calls the FastAPI backend
// ============================================================

async function fetchLiveOpportunities() {
  const btn   = document.getElementById("liveFetchBtn");
  const icon  = document.getElementById("liveFetchIcon");
  const label = document.getElementById("liveFetchLabel");
  const overlay = document.getElementById("scrapeOverlay");
  const sub   = document.getElementById("scrapeOverlaySub");
  const fill  = document.getElementById("scrapeProgressFill");

  // Disable button
  if (btn) btn.disabled = true;
  if (icon) icon.textContent = "⏳";
  if (label) label.textContent = "Fetching…";

  // Show overlay
  if (overlay) overlay.style.display = "flex";
  if (fill) fill.style.width = "0%";
  if (sub) sub.textContent = "Connecting to scraper engine…";

  // Animate progress bar
  const progressSteps = [
    [15, "🎓 Scraping Internshala…"],
    [35, "💻 Scraping Devpost hackathons…"],
    [55, "🚀 Scraping Unstop…"],
    [75, "🌍 Fetching Remotive jobs…"],
    [90, "🧹 Cleaning & deduplicating…"],
  ];
  let stepIdx = 0;
  const progressInterval = setInterval(() => {
    if (stepIdx < progressSteps.length) {
      const [pct, msg] = progressSteps[stepIdx];
      if (fill) fill.style.width = pct + "%";
      if (sub) sub.textContent = msg;
      stepIdx++;
    }
  }, 1200);

  try {
    const typeVal = document.getElementById("typeFilter") ? document.getElementById("typeFilter").value : "all";
    const domainVal = document.getElementById("domainFilter") ? document.getElementById("domainFilter").value : "general";
    const locVal = document.getElementById("locationFilter") ? document.getElementById("locationFilter").value : "all";

    const filters = {
      type:     typeVal || "all",
      domain:   domainVal || "general",
      location: locVal || "all",
    };

    const resp = await fetch(`${API_BASE}/api/scrape`, {
      method:  "POST",
      headers: { 
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body:    JSON.stringify(filters),
      signal:  AbortSignal.timeout(60000),  // 60s timeout
    });

    if (!resp.ok) throw new Error(`API error ${resp.status}`);
    const data = await resp.json();

    clearInterval(progressInterval);
    if (fill) fill.style.width = "100%";
    if (sub) sub.textContent = `✅ Done! ${data.count} opportunities found.`;

    await new Promise(r => setTimeout(r, 600));

    let scrapedList = (data.opportunities && data.opportunities.length > 0) ? data.opportunities : [];
    if (scrapedList.length === 0 && typeof MOCK_OPPORTUNITIES !== "undefined") {
      scrapedList = MOCK_OPPORTUNITIES;
    }

    opportunities = scrapedList.map(o => ({
      ...o,
      role: o.title || o.role,
      applyLink: o.application_link || o.apply_link || o.applyLink,
      logo: o.organization ? o.organization.charAt(0).toUpperCase() : (o.company ? o.company.charAt(0).toUpperCase() : "?"),
      type: (o.category || o.type || "internship").toLowerCase(),
      source: detectSource(o),
      verified: true
    }));

    // Cache scraped opportunities in localStorage for persistence across pages
    try {
      localStorage.setItem("ohub_scraped_cache", JSON.stringify(opportunities));
    } catch (e) {
      console.warn("Could not save to localStorage cache:", e);
    }

    window.opportunities = opportunities;
    liveOpportunities = opportunities;

    // Update counters in UI
    const internships = opportunities.filter(o => o.type === "internship");
    const hackathons  = opportunities.filter(o => o.type === "hackathon" || o.type === "job");
    const saved       = opportunities.filter(o => o.saved);
    const applied     = opportunities.filter(o => o.applied);

    const totalEl      = document.getElementById("totalCount");
    const internEl     = document.getElementById("internshipCount");
    const hackEl       = document.getElementById("hackathonCount");
    const savedEl      = document.getElementById("savedCount");
    const appliedSubEl = document.getElementById("appliedCountSub");
    if (totalEl)      totalEl.textContent      = opportunities.length;
    if (internEl)     internEl.textContent     = internships.length;
    if (hackEl)       hackEl.textContent       = hackathons.length;
    if (savedEl)      savedEl.textContent      = saved.length;
    if (appliedSubEl) appliedSubEl.textContent = `applied: ${applied.length}`;

    renderStatsRow();
    renderDeadlineTimeline();
    renderCards();
    setDataStatusBanner("live", opportunities.length, "scraped");
    showToast(`✅ Loaded ${opportunities.length} live opportunities!`, "success");

  } catch (err) {
    clearInterval(progressInterval);
    console.error("[fetchLive] Error:", err);

    // Graceful fallback
    const isOffline = err.name === "TypeError" || err.message.includes("fetch");
    if (sub) {
      sub.textContent = isOffline
        ? "⚠️ Backend offline — showing saved database opportunities"
        : `⚠️ ${err.message}`;
    }
    await new Promise(r => setTimeout(r, 1200));
    if (opportunities.length === 0) {
      setDataStatusBanner("offline");
    }
    if (isOffline) {
      showToast("⚠️ Could not run scraping. Backend offline.", "warning");
    } else {
      showToast(`⚠️ Scraping failed: ${err.message || err}`, "warning");
    }
  }

  // Hide overlay & reset button
  if (overlay) overlay.style.display = "none";
  if (btn) btn.disabled = false;
  if (icon) icon.textContent = "🌐";
  if (label) label.textContent = "Fetch Live Opportunities";
}

function setDataStatusBanner(mode, count = 0, source = "") {
  const dot  = document.getElementById("dsbDot");
  const text = document.getElementById("dsbText");
  const banner = document.getElementById("dataStatusBanner");

  if (mode === "live") {
    dot.style.background = "#22c55e";
    dot.style.boxShadow  = "0 0 6px #22c55e";
    text.innerHTML = `🟢 Database synced — <strong>${count}</strong> real opportunities active from Gmail, Internshala, Devpost, Unstop & Remotive`;
    banner.style.borderColor = "rgba(34,197,94,.3)";
  } else if (mode === "empty") {
    dot.style.background = "#f59e0b";
    text.innerHTML = "🟡 Database is empty. Click <strong>Fetch Live Opportunities</strong> or sync Gmail to search listings.";
    banner.style.borderColor = "rgba(245,158,11,.3)";
  } else if (mode === "offline") {
    dot.style.background = "#ef4444";
    dot.style.boxShadow  = "0 0 6px #ef4444";
    text.innerHTML = "🔴 Connection to backend API failed. Please launch <code>start.bat</code> to connect database.";
    banner.style.borderColor = "rgba(239,68,68,.3)";
  }
}

// ============================================================
// STATS + COUNTERS
// ============================================================

function updateStats() {
  const internships = opportunities.filter(o => o.type === "internship");
  const hackathons  = opportunities.filter(o => o.type === "hackathon" || o.type === "job");
  const saved       = opportunities.filter(o => o.saved);
  const applied     = opportunities.filter(o => o.applied);

  document.getElementById("totalCount").textContent      = opportunities.length;
  document.getElementById("internshipCount").textContent = internships.length;
  document.getElementById("hackathonCount").textContent  = hackathons.length;
  document.getElementById("savedCount").textContent      = saved.length;
  document.getElementById("appliedCountSub").textContent = `applied: ${applied.length}`;
}

function animateCounters() {
  const counters = document.querySelectorAll(".stat-card-value");
  counters.forEach(el => {
    const target = parseInt(el.textContent);
    if (isNaN(target)) return;
    let start = 0;
    const step = Math.ceil(target / 20);
    const interval = setInterval(() => {
      start = Math.min(start + step, target);
      el.textContent = start;
      if (start >= target) clearInterval(interval);
    }, 40);
  });
}

// ============================================================
// DEADLINE TIMELINE
// ============================================================

function renderDeadlineTimeline() {
  // opportunities.html doesn't have a deadlineTimeline element — guard against null
  const timeline = document.getElementById("deadlineTimeline");
  if (!timeline) return;

  const groups = [
    { key: "today",    title: "Today",        filter: d => d === 0,           countClass: "today"     },
    { key: "week",     title: "This Week",    filter: d => d > 0 && d <= 7,   countClass: "week"      },
    { key: "twoweeks", title: "Next 2 Weeks", filter: d => d > 7 && d <= 14,  countClass: "two-weeks" },
    { key: "future",   title: "Future",       filter: d => d > 14,            countClass: "future"    },
  ];

  // Only include opportunities that actually have a valid deadline
  const withDeadline = opportunities.filter(o => o.deadline && o.deadline !== "N/A" && o.deadline !== "null");

  timeline.innerHTML = groups.map(group => {
    const items = withDeadline.filter(o => {
      const days = getDaysLeft(o.deadline);
      return !isNaN(days) && group.filter(days);
    });

    const itemsHTML = items.length === 0
      ? `<div style="color:var(--text-muted);font-size:12px;text-align:center;padding:12px 0">Nothing here 🎉</div>`
      : items.slice(0, 3).map(o => {
          const days = getDaysLeft(o.deadline);
          const urgency = getUrgencyBadge(days);
          const org = o.organization || o.company || "Unknown";
          const role = o.role || o.title || "";
          return `
            <div class="dg-item">
              <div class="dg-item-company">${org}</div>
              <div class="dg-item-role">${role}</div>
              <div class="dg-item-badge">${urgency.emoji} ${urgency.label}</div>
            </div>`;
        }).join("");

    return `
      <div class="deadline-group">
        <div class="dg-header">
          <div class="dg-title">${group.title}</div>
          <div class="dg-count ${group.countClass}">${items.length}</div>
        </div>
        <div class="dg-items">${itemsHTML}</div>
      </div>`;
  }).join("");
}

// ============================================================
// FILTERING
// ============================================================

// Domain keyword map for fuzzy matching
const DOMAIN_KEYWORDS = {
  ai:     ["ai", "ml", "machine learning", "deep learning", "artificial intelligence", "nlp", "computer vision", "data science", "neural"],
  web:    ["web", "frontend", "backend", "fullstack", "full stack", "react", "node", "django", "flask", "html", "css", "javascript", "typescript"],
  data:   ["data", "analytics", "sql", "python", "tableau", "power bi", "statistics", "excel", "etl", "warehouse"],
  design: ["design", "ui", "ux", "figma", "sketch", "adobe", "graphic", "product design", "wireframe"],
  mobile: ["mobile", "android", "ios", "flutter", "react native", "swift", "kotlin", "app development"],
};

// Helper to detect source from item fields when missing
function detectSource(o) {
  if (!o) return "unknown";
  if (o.source_email || o.email_id) return "gmail";

  let rawSource = (o.source || o.source_sender || "").toLowerCase();
  if (rawSource && rawSource !== "unknown" && rawSource !== "null" && rawSource !== "undefined") {
    return rawSource;
  }

  const link = (o.application_link || o.apply_link || o.applyLink || o.official_website || "").toLowerCase();
  const desc = (o.description || "").toLowerCase();
  const org = (o.organization || o.company || "").toLowerCase();
  const combined = `${link} ${desc} ${org}`;

  if (combined.includes("internshala")) return "internshala";
  if (combined.includes("devpost")) return "devpost";
  if (combined.includes("unstop")) return "unstop";
  if (combined.includes("remotive")) return "remotive";
  if (combined.includes("linkedin")) return "linkedin";

  return "unknown";
}

function renderStatsRow() {
  const statsRow = document.getElementById("statsRow");
  if (!statsRow) return;

  const internships = opportunities.filter(o => o.type === "internship").length;
  const hackathons  = opportunities.filter(o => o.type === "hackathon" || o.type === "job").length;
  const closingToday = opportunities.filter(o => {
    if (!o.deadline || o.deadline === "N/A" || o.deadline === "null") return false;
    return getDaysLeft(o.deadline) === 0;
  }).length;

  statsRow.innerHTML = `
    <div class="stat-card" style="--accent-color:var(--accent)">
      <div class="stat-card-label">Total</div>
      <div class="stat-card-value">${opportunities.length}</div>
      <div class="stat-card-sub">opportunities</div>
    </div>
    <div class="stat-card" style="--accent-color:var(--accent2)">
      <div class="stat-card-label">Internships</div>
      <div class="stat-card-value">${internships}</div>
      <div class="stat-card-sub">available</div>
    </div>
    <div class="stat-card" style="--accent-color:var(--accent3)">
      <div class="stat-card-label">Hackathons</div>
      <div class="stat-card-value">${hackathons}</div>
      <div class="stat-card-sub">open</div>
    </div>
    <div class="stat-card" style="--accent-color:var(--accent-warn)">
      <div class="stat-card-label">Closing Today</div>
      <div class="stat-card-value">${closingToday}</div>
      <div class="stat-card-sub">urgent</div>
    </div>`;
}

function getFilteredOpportunities() {
  return opportunities.filter(o => {
    const org   = (o.organization || o.company || "").toLowerCase();
    const role  = (o.role || o.title || "").toLowerCase();
    const elig  = (o.eligibility || o.description || "").toLowerCase();
    const loc   = (o.location || "").toLowerCase();
    const combined = `${org} ${role} ${elig}`;

    // Normalize type comparison — DB may store "Internship", filter uses "internship"
    const oType = (o.type || "").toLowerCase();
    const matchType = activeTypeFilter === "all" || oType === activeTypeFilter.toLowerCase();

    const matchSearch = !searchQuery ||
      org.includes(searchQuery) ||
      role.includes(searchQuery) ||
      elig.includes(searchQuery);

    // Normalize source for comparison using intelligent detection
    const oSource = detectSource(o);
    const matchSource = !sourceFilter || oSource === sourceFilter.toLowerCase();

    const matchDeadline = (() => {
      if (!deadlineFilter) return true;
      if (!o.deadline || o.deadline === "N/A" || o.deadline === "null") return false;
      const days = getDaysLeft(o.deadline);
      if (isNaN(days)) return false;
      if (deadlineFilter === "today")    return days === 0;
      if (deadlineFilter === "week")     return days >= 0 && days <= 7;
      if (deadlineFilter === "twoweeks") return days >= 0 && days <= 14;
      return true;
    })();

    const matchLocation = (() => {
      if (!locationFilter || locationFilter === "all") return true;
      if (locationFilter === "remote") return loc.includes("remote") || loc.includes("work from home") || loc.includes("wfh");
      if (locationFilter === "onsite") return loc.length > 0 && !loc.includes("remote") && !loc.includes("work from home");
      return true;
    })();

    const matchDomain = (() => {
      // domainFilter is "" when "All Domains" is selected
      if (!domainFilter || domainFilter === "general") return true;
      const keywords = DOMAIN_KEYWORDS[domainFilter] || [];
      return keywords.some(kw => combined.includes(kw));
    })();

    return matchType && matchSearch && matchSource && matchDeadline && matchLocation && matchDomain;
  });
}

// ============================================================
// CARD RENDERING
// ============================================================

function renderCards() {
  const grid  = document.getElementById("cardsGrid");
  const empty = document.getElementById("emptyState");
  const filtered = getFilteredOpportunities();

  document.getElementById("resultCount").textContent =
    filtered.length === opportunities.length
      ? `${filtered.length} total`
      : `${filtered.length} of ${opportunities.length}`;

  if (filtered.length === 0) {
    grid.style.display  = "none";
    empty.style.display = "block";
    return;
  }

  grid.style.display  = "grid";
  empty.style.display = "none";

  grid.innerHTML = filtered.map((o, i) => buildCard(o, i)).join("");

  grid.querySelectorAll(".opp-card").forEach((card, i) => {
    card.style.opacity   = "0";
    card.style.transform = "translateY(16px)";
    setTimeout(() => {
      card.style.transition = "opacity 0.3s ease, transform 0.3s ease";
      card.style.opacity    = "1";
      card.style.transform  = "translateY(0)";
    }, i * 60);
  });
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function stripHtml(html) {
  if (!html) return "";
  let text = html.replace(/<[^>]*>?/g, "");
  text = text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
  return text.trim();
}

function buildCard(o, idx) {
  const days   = getDaysLeft(o.deadline);
  const urgency = getUrgencyBadge(days);
  const type = o.type || "internship";
  const isInternship = type === "internship";
  const isJob = type === "job";
  const accentStart = isInternship ? "var(--accent)" : isJob ? "var(--accent3)" : "var(--accent2)";
  const accentEnd   = isInternship ? "var(--accent2)" : isJob ? "var(--accent)" : "var(--accent3)";

  const org  = escapeHtml(o.organization || o.company || "Unknown");
  const role = escapeHtml(o.role || o.title || "Opportunity");
  // Logo: use first letter of org text content (already HTML-escaped), not re-escaped
  const logoText = (o.organization || o.company || "?").charAt(0).toUpperCase();
  const logo = escapeHtml(logoText);
  // Link: encode & as HTML entity (correct for href attribute), but don't double-escape
  const rawLink = (o.apply_link || o.applyLink || "#").replace(/"/g, "%22").replace(/'/g, "%27");
  const link = rawLink.replace(/&(?!amp;|lt;|gt;|quot;|#\d+;)/g, "&amp;");
  const typeLabel = isInternship ? "Internship" : isJob ? "Job" : "Hackathon";
  const source = escapeHtml(o.source || "unknown");
  const isLive = liveOpportunities.some(l => l.id === o.id);
  // Safe ID for use in HTML attributes and JS callbacks
  const safeId = String(o.id || "").replace(/[^a-zA-Z0-9_-]/g, "");

  const rawStipend = o.stipend || "N/A";
  let stipend = rawStipend;
  if (stipend.toLowerCase() === "null" || stipend.toLowerCase() === "undefined" || stipend.toLowerCase() === "none") {
    stipend = "N/A";
  }
  stipend = escapeHtml(stipend);

  let rawLocation = o.location || "";
  if (rawLocation.toLowerCase() === "null" || rawLocation.toLowerCase() === "undefined" || rawLocation.toLowerCase() === "none") {
    rawLocation = "";
  }
  const location = escapeHtml(rawLocation);

  let rawAbout = stripHtml(o.eligibility || o.description || "");
  const lowerAbout = rawAbout.toLowerCase();
  if (lowerAbout === "null" || lowerAbout === "undefined" || lowerAbout === "none" || lowerAbout === "n/a") {
    rawAbout = "";
  }
  const cleanAbout = escapeHtml(rawAbout);

  return `
    <div class="opp-card${isLive ? ' live-card' : ''}" style="--card-accent-start:${accentStart};--card-accent-end:${accentEnd}" data-id="${safeId}">
      <div class="opp-card-header">
        <div class="opp-card-badges">
          <span class="badge badge-${type}">${typeLabel}</span>
          ${o.verified ? '<span class="badge badge-verified">✓ Verified</span>' : ""}
          ${isLive ? '<span class="badge badge-live">🌐 Live</span>' : ""}
        </div>
        <div class="opp-card-actions">
          <button class="card-action-btn ${o.saved ? 'bookmarked' : ''}" onclick="toggleSave('${safeId}')" title="${o.saved ? 'Remove bookmark' : 'Bookmark'}">
            ${o.saved ? "🔖" : "○"}
          </button>
          <button class="card-action-btn ${o.applied ? 'applied' : ''}" onclick="toggleApplied('${safeId}')" title="${o.applied ? 'Mark unapplied' : 'Mark applied'}">
            ${o.applied ? "✓" : "✗"}
          </button>
        </div>
      </div>

      <div class="opp-company">
        <div class="company-logo">${logo}</div>
        <div class="company-info">
          <div class="company-name">${org}</div>
          <div class="role-title">${role}</div>
        </div>
      </div>

      <div class="opp-details">
        <div class="opp-detail">
          <span class="detail-label">Stipend / Prize</span>
          <span class="detail-value">${stipend}</span>
        </div>
        <div class="opp-detail">
          <span class="detail-label">Deadline</span>
          <span class="detail-value">${o.deadline !== "N/A" ? formatDeadline(o.deadline) : "N/A"}</span>
        </div>
        ${location ? `
        <div class="opp-detail" style="grid-column:span 2">
          <span class="detail-label">📍 Location</span>
          <span class="detail-value">${location}</span>
        </div>` : ""}
        ${cleanAbout ? `
        <div class="opp-detail" style="grid-column:span 2">
          <span class="detail-label">Eligibility / About</span>
          <span class="detail-value">${cleanAbout.slice(0, 120)}${cleanAbout.length > 120 ? "…" : ""}</span>
        </div>` : ""}
      </div>

      <div class="opp-footer">
        <div class="source-tag">
          ${SOURCE_ICONS[source] || "🌐"} ${SOURCE_LABELS[source] || source}
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          ${days <= 14 && days >= 0 ? `<span class="badge ${urgency.class}" style="font-size:10px">${urgency.emoji} ${urgency.label}</span>` : ""}
          <a href="${link}" target="_blank" class="apply-btn">Apply →</a>
        </div>
      </div>
    </div>`;
}

// ============================================================
// TOGGLE SAVE / APPLIED
// ============================================================

async function toggleSave(safeId) {
  const opp = opportunities.find(o => {
    const oid = String(o.id || "").replace(/[^a-zA-Z0-9_-]/g, "");
    return oid === safeId;
  });
  if (!opp) return;
  const newSaved = !opp.saved;
  try {
    const res = await fetch(`${API_BASE}/api/opportunities/${opp.id}/status?saved=${newSaved}`, {
      method: "PUT",
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (res.ok) {
      opp.saved = newSaved;
      await loadDashboardData();
      showToast(opp.saved ? "🔖 Bookmarked!" : "Bookmark removed", opp.saved ? "success" : "");
    }
  } catch (err) {
    console.error("Failed to toggle bookmark:", err);
    showToast("Failed to update bookmark status", "error");
  }
}

async function toggleApplied(safeId) {
  const opp = opportunities.find(o => {
    const oid = String(o.id || "").replace(/[^a-zA-Z0-9_-]/g, "");
    return oid === safeId;
  });
  if (!opp) return;
  const newApplied = !opp.applied;
  try {
    const res = await fetch(`${API_BASE}/api/opportunities/${opp.id}/status?applied=${newApplied}`, {
      method: "PUT",
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (res.ok) {
      opp.applied = newApplied;
      await loadDashboardData();
      showToast(opp.applied ? "✅ Marked as Applied!" : "Marked as not applied", opp.applied ? "success" : "");
    }
  } catch (err) {
    console.error("Failed to toggle applied status:", err);
    showToast("Failed to update application status", "error");
  }
}

// ============================================================
// FILTER CONTROLS
// ============================================================

function setFilter(type, btn) {
  activeTypeFilter = type;
  // Sync the type dropdown to match
  const typeDropdown = document.getElementById("typeFilter");
  if (typeDropdown) typeDropdown.value = type === "all" ? "" : type;
  // Update button active states (only the quick filter buttons, not the dropdown)
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderCards();
}

function initSearch() {
  // Search input
  document.getElementById("searchInput").addEventListener("input", e => {
    searchQuery = e.target.value.toLowerCase().trim();
    renderCards();
  });

  // Type filter dropdown — sync with quick filter buttons
  document.getElementById("typeFilter").addEventListener("change", e => {
    const val = e.target.value; // "" | "internship" | "hackathon" | "job"
    activeTypeFilter = val || "all";
    // Update quick filter button active states
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    if (val === "") {
      const allBtn = document.getElementById("allBtn");
      if (allBtn) allBtn.classList.add("active");
    }
    renderCards();
  });

  // Source filter
  document.getElementById("sourceFilter").addEventListener("change", e => {
    sourceFilter = e.target.value;
    renderCards();
  });

  // Deadline filter
  document.getElementById("deadlineFilter").addEventListener("change", e => {
    deadlineFilter = e.target.value;
    renderCards();
  });

  // Domain filter — now actually applied in getFilteredOpportunities
  document.getElementById("domainFilter").addEventListener("change", e => {
    domainFilter = e.target.value === "general" ? "" : e.target.value;
    renderCards();
  });

  // Location filter
  document.getElementById("locationFilter").addEventListener("change", e => {
    locationFilter = e.target.value || "all";
    renderCards();
  });
}

// ============================================================
// QUICK REFRESH (mock simulation — kept for compat)
// ============================================================

function triggerScrape() {
  if (usingLiveData) {
    fetchLiveOpportunities();
    return;
  }
  showToast("💡 Click 'Fetch Live Opportunities' to load real data.", "");
}

// ============================================================
// TOAST
// ============================================================

function showToast(message, type = "") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.transition = "opacity 0.3s ease, transform 0.3s ease";
    toast.style.opacity    = "0";
    toast.style.transform  = "translateX(20px)";
    setTimeout(() => toast.remove(), 350);
  }, 3200);
}
