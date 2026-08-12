// ============================================
// DATA JS — OpportUnity Hub
// ============================================

const MOCK_OPPORTUNITIES = [
  {
    id: "opp_001",
    organization: "Edunexus",
    type: "internship",
    role: "Sales intership",
    stipend: "-",
    deadline: daysFromNow(1),
    eligibility: "B.Tech CS / IT, 3rd / 4th year",
    applyLink: "https://unstop.com/o/ri8lIMn?lb=WKlccLR5&utm_medium=Share&utm_source=internships&utm_campaign=Kundukar86324",
    source: "unstop",
    logo: "U",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_002",
    organization: "Devpost × MLH",
    type: "hackathon",
    role: "HackMIT 2025 — AI & Machine Learning",
    stipend: "$10,000 prize pool",
    deadline: daysFromNow(4),
    eligibility: "All students worldwide",
    applyLink: "https://hackathons.mlh.io",
    source: "devpost",
    logo: "D",
    verified: true,
    saved: true,
    applied: false,
  },
  {
    id: "opp_003",
    organization: "Skill india",
    type: "internship",
    role: "shop track: smart billing & invetory",
    stipend: "₹4000",
    deadline: daysFromNow(10),
    eligibility: "Any branch",
    applyLink: "https://share.google/qYF0cyiZhQBUeiWLu",
    source: "skill india",
    logo: "SK",
    verified: true,
    saved: false,
    applied: true,
  },
  {
    id: "opp_004",
    organization: "Amazon",
    type: "internship",
    role: "SDE Intern — Amazon Pay",
    stipend: "₹90,000/mo",
    deadline: daysFromNow(0),
    eligibility: "B.Tech / M.Tech CS, 2025 passout",
    applyLink: "https://amazon.jobs",
    source: "linkedin",
    logo: "A",
    verified: true,
    saved: true,
    applied: false,
  },
  {
    id: "opp_005",
    organization: "Smart India Hackathon",
    type: "hackathon",
    role: "SIH 2025 — Government Problem Statements",
    stipend: "₹1,00,000 prize",
    deadline: daysFromNow(18),
    eligibility: "Indian college students",
    applyLink: "https://sih.gov.in",
    source: "devpost",
    logo: "S",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_006",
    organization: "Flipkart",
    type: "internship",
    role: "Product Management Intern",
    stipend: "₹50,000/mo",
    deadline: daysFromNow(6),
    eligibility: "MBA / B.Tech, Penultimate year",
    applyLink: "https://careers.flipkart.com",
    source: "internshala",
    logo: "F",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_007",
    organization: "ETHIndia",
    type: "hackathon",
    role: "ETHIndia 2025 — Web3 & DeFi",
    stipend: "$50,000 total prizes",
    deadline: daysFromNow(2),
    eligibility: "Open to all, 18+",
    applyLink: "https://ethindia.co",
    source: "devpost",
    logo: "E",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_008",
    organization: "Adobe",
    type: "internship",
    role: "UX Design Intern — Creative Cloud",
    stipend: "₹70,000/mo",
    deadline: daysFromNow(14),
    eligibility: "Design / CS students, Portfolio required",
    applyLink: "https://adobe.com/careers",
    source: "linkedin",
    logo: "A",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_009",
    organization: "Internshala × NASSCOM",
    type: "internship",
    role: "Full Stack Developer Intern",
    stipend: "₹15,000/mo",
    deadline: daysFromNow(21),
    eligibility: "Any branch, freshers welcome",
    applyLink: "https://internshala.com",
    source: "internshala",
    logo: "N",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_010",
    organization: "Unstop × BITS",
    type: "hackathon",
    role: "Apogee Hackathon 2025",
    stipend: "₹75,000 prize",
    deadline: daysFromNow(7),
    eligibility: "BITS students + external",
    applyLink: "https://unstop.com",
    source: "devpost",
    logo: "U",
    verified: true,
    saved: true,
    applied: false,
  },
  {
    id: "opp_011",
    organization: "Razorpay",
    type: "internship",
    role: "Backend Engineering Intern",
    stipend: "₹55,000/mo",
    deadline: daysFromNow(9),
    eligibility: "B.Tech CS/EC, 3rd year+",
    applyLink: "https://razorpay.com/careers",
    source: "linkedin",
    logo: "R",
    verified: true,
    saved: false,
    applied: false,
  },
  {
    id: "opp_012",
    organization: "Zepto",
    type: "internship",
    role: "Data Analyst Intern",
    stipend: "₹40,000/mo",
    deadline: daysFromNow(13),
    eligibility: "Statistics / CS, Excel / SQL",
    applyLink: "https://zeptonow.com/careers",
    source: "internshala",
    logo: "Z",
    verified: true,
    saved: false,
    applied: false,
  },
];

function daysFromNow(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

function getDaysLeft(dateStr) {
  if (!dateStr || dateStr === "N/A" || dateStr === "null") return NaN;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  // Parse YYYY-MM-DD as LOCAL date (not UTC) to avoid timezone off-by-one issues.
  // new Date("2026-07-30") is parsed as UTC midnight, which is wrong in UTC+5:30.
  const parts = String(dateStr).slice(0, 10).split("-");
  if (parts.length !== 3) return NaN;
  const target = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  if (isNaN(target.getTime())) return NaN;
  const diff = Math.round((target - today) / (1000 * 60 * 60 * 24));
  return diff;
}

function formatDeadline(dateStr) {
  if (!dateStr || dateStr === "N/A") return "N/A";
  // Parse as local date to avoid UTC shift
  const parts = String(dateStr).slice(0, 10).split("-");
  if (parts.length !== 3) return dateStr;
  const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function getUrgencyBadge(daysLeft) {
  if (daysLeft < 0) return { label: "Expired", class: "badge-critical", emoji: "✗" };
  if (daysLeft === 0) return { label: "Today!", class: "badge-critical", emoji: "🔥" };
  if (daysLeft <= 2) return { label: `${daysLeft}d left`, class: "badge-critical", emoji: "🔥" };
  if (daysLeft <= 7) return { label: `${daysLeft}d left`, class: "badge-urgent", emoji: "⚡" };
  if (daysLeft <= 14) return { label: `${daysLeft}d left`, class: "badge internship", emoji: "📅" };
  return { label: `${daysLeft}d left`, class: "", emoji: "🗓️" };
}

const SOURCE_ICONS = {
  internshala: "🎓",
  devpost:     "💻",
  linkedin:    "💼",
  unstop:      "🚀",
  remotive:    "🌍",
  gmail:       "📧",
  email:       "📧",
};

const SOURCE_LABELS = {
  internshala: "Internshala",
  devpost:     "Devpost",
  linkedin:    "LinkedIn",
  unstop:      "Unstop",
  remotive:    "Remotive",
  gmail:       "Gmail",
  email:       "Email",
};
