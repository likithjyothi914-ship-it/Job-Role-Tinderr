const search = document.querySelector("#search");
const category = document.querySelector("#category");
const level = document.querySelector("#level");
const workMode = document.querySelector("#workMode");
const grid = document.querySelector("#jobGrid");
const count = document.querySelector("#resultCount");
const empty = document.querySelector("#emptyState");
const dialog = document.querySelector("#jobDialog");
const dialogContent = document.querySelector("#dialogContent");
let displayedOpenings = [];

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value;
  return node.innerHTML;
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}

function roleCard(job) {
  const skills = job.skills.slice(0, 3).map(skill => `<span>${escapeHtml(skill)}</span>`).join("");
  return `
    <article class="job-card">
      <div class="card-top">
        <span class="category-label">${escapeHtml(job.category)}</span>
        <span class="mode-label">${escapeHtml(job.work_mode)}</span>
      </div>
      <h3>${escapeHtml(job.title)}</h3>
      <p>${escapeHtml(job.description)}</p>
      <div class="skill-list">${skills}</div>
      <div class="card-bottom">
        <span>${escapeHtml(job.level)}</span>
        <button type="button" data-job-id="${job.id}">View details</button>
      </div>
    </article>`;
}

async function loadJobs() {
  const params = new URLSearchParams({
    q: search.value.trim(),
    category: category.value,
    level: level.value,
    work_mode: workMode.value,
  });
  grid.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/jobs?${params}`);
    const data = await response.json();
    count.textContent = `${data.count} ${data.count === 1 ? "role" : "roles"}`;
    grid.innerHTML = data.jobs.map(roleCard).join("");
    empty.hidden = data.count !== 0;
  } catch (error) {
    count.textContent = "Unable to load roles";
    grid.innerHTML = "";
    empty.hidden = false;
  } finally {
    grid.setAttribute("aria-busy", "false");
  }
}

async function initializeFilters() {
  const response = await fetch("/api/jobs");
  const data = await response.json();
  const unique = key => [...new Set(data.jobs.map(job => job[key]))].sort();
  const addOptions = (select, values) => values.forEach(value => select.add(new Option(value, value)));
  addOptions(category, unique("category"));
  addOptions(level, unique("level"));
  addOptions(workMode, unique("work_mode"));
  document.querySelector("#heroTotal").textContent = data.count;
}

async function showJob(id) {
  const response = await fetch(`/api/jobs/${id}`);
  const job = await response.json();
  dialogContent.innerHTML = `
    <p class="eyebrow">${escapeHtml(job.category)}</p>
    <h2>${escapeHtml(job.title)}</h2>
    <p class="dialog-summary">${escapeHtml(job.description)}</p>
    <dl>
      <div><dt>Career level</dt><dd>${escapeHtml(job.level)}</dd></div>
      <div><dt>Experience required</dt><dd>${escapeHtml(job.experience_required)}</dd></div>
      <div><dt>Work mode</dt><dd>${escapeHtml(job.work_mode)}</dd></div>
      <div><dt>Typical qualification</dt><dd>${escapeHtml(job.qualification)}</dd></div>
      <div><dt>Eligibility</dt><dd>${escapeHtml(job.eligibility)}</dd></div>
    </dl>
    <h3>Skills required</h3>
    <div class="skill-list large">${job.skills.map(skill => `<span>${escapeHtml(skill)}</span>`).join("")}</div>
    `;
  dialog.showModal();
}

let timer;
search.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(loadJobs, 180);
});
document.querySelector("#searchButton").addEventListener("click", loadJobs);
[category, level, workMode].forEach(control => control.addEventListener("change", loadJobs));
document.querySelector("#clearFilters").addEventListener("click", () => {
  search.value = "";
  category.value = "";
  level.value = "";
  workMode.value = "";
  loadJobs();
});
grid.addEventListener("click", event => {
  const button = event.target.closest("[data-job-id]");
  if (button) showJob(button.dataset.jobId);
});
document.querySelector("#closeDialog").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});

initializeFilters().then(loadJobs);

function openingRows(jobs) {
  if (!jobs.length) return '<tr><td colspan="8">No verified jobs from the last 30 days were returned.</td></tr>';
  return jobs.map(job => { const contact=job.application_link_or_employer_email || job.application_url || ""; const url=safeUrl(contact); const email=!url && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact) ? contact : ""; return `<tr>
    <td>${escapeHtml(job.title || "")}</td><td>${escapeHtml(job.company || "")}</td>
    <td>${escapeHtml(job.location || "")}</td><td>${escapeHtml(job.published_at || "")}</td><td>${escapeHtml(job.skills_required || job.tags || "Not supplied")}</td><td>${escapeHtml(job.job_type || job.remote || "")}</td>
    <td>${escapeHtml(job.source || "Imported")}</td>
    <td>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open job</a>` : email ? `<a href="mailto:${escapeHtml(email)}">${escapeHtml(email)}</a>` : "Not provided"}</td>
  </tr>`; }).join("");
}

function showOpenings(jobs, label) {
  displayedOpenings = jobs;
  document.querySelector("#openingRows").innerHTML = openingRows(jobs);
  document.querySelector("#searchJobCount").textContent = `${jobs.length} ${label}`;
  document.querySelector("#saveSearchResults").disabled = jobs.length === 0;
}

async function refreshCollectionTotal() {
  const response = await fetch("/api/collected-jobs");
  const data = await response.json();
  document.querySelector("#collectionTotal").textContent = `${data.count} ${data.count === 1 ? "row" : "rows"}`;
}

document.querySelector("#publicSearch").addEventListener("click", async () => {
  const status = document.querySelector("#collectorStatus");
  const button = document.querySelector("#publicSearch");
  const params = new URLSearchParams({q: document.querySelector("#publicQuery").value.trim(), location: document.querySelector("#publicLocation").value.trim(), source: document.querySelector("#publicSource").value});
  button.disabled = true;
  status.textContent = "Searching for verified jobs posted during the last 30 days...";
  try {
    const response = await fetch(`/api/public-jobs/search?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Search failed");
    showOpenings(data.jobs, data.count === 1 ? "opening found" : "openings found");
    const warning = data.warnings?.length ? ` ${data.warnings.length} source(s) were unavailable.` : "";
    status.textContent = data.count ? `Found ${data.count} recent verified jobs.${warning} Review and save them.` : `No dated matches were found.${warning}`;
  } catch (error) {
    showOpenings([], "openings found");
    status.textContent = error.message;
  } finally { button.disabled = false; }
});

document.querySelector("#saveSearchResults").addEventListener("click", async () => {
  const response = await fetch("/api/collected-jobs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({jobs: displayedOpenings})});
  const data = await response.json();
  document.querySelector("#collectorStatus").textContent = `${data.added || 0} new rows saved. ${data.rejected || 0} old or undated rows rejected. Duplicates were skipped.`;
  await refreshCollectionTotal();
});

function parseCsv(text) {
  const rows=[]; let row=[]; let value=""; let quoted=false;
  for (let i=0;i<text.length;i++) {
    const char=text[i];
    if (char==='"' && quoted && text[i+1]==='"') { value+='"'; i++; }
    else if (char==='"') quoted=!quoted;
    else if (char===',' && !quoted) { row.push(value); value=""; }
    else if ((char==='\n' || char==='\r') && !quoted) { if (char==='\r' && text[i+1]==='\n') i++; row.push(value); if (row.some(cell=>cell.trim())) rows.push(row); row=[]; value=""; }
    else value+=char;
  }
  row.push(value); if (row.some(cell=>cell.trim())) rows.push(row);
  if (rows.length < 2) return [];
  const headers=rows[0].map(header=>header.trim().toLowerCase().replaceAll(" ","_"));
  return rows.slice(1).map(values=>Object.fromEntries(headers.map((header,index)=>[header,(values[index]||"").trim()])));
}

function normalizeImported(item) {
  const get=(...keys)=>keys.map(key=>item[key]).find(Boolean)||"";
  const applicationUrl=get("application_url","url","job_url","link");
  const employerEmail=get("employer_email","contact_email","email");
  return {title:get("title","job_title","position","role"), company:get("company","company_name","employer"), location:get("location","job_location"), remote:get("remote"), job_type:get("job_type","employment_type","type"), category:get("category"), tags:get("tags","skills"), skills_required:get("skills_required","required_skills","skills","tags"), experience_required:get("experience_required","experience"), eligibility:get("eligibility","qualification","qualifications"), published_at:get("published_at","publication_date","date_posted","date"), source:get("source","website")||"Imported file", application_url:applicationUrl, employer_email:employerEmail, application_link_or_employer_email:applicationUrl||employerEmail, description:get("description","summary")};
}

document.querySelector("#jobFile").addEventListener("change", async event => {
  const file=event.target.files[0]; if (!file) return;
  const status=document.querySelector("#collectorStatus");
  try {
    const text=await file.text();
    const parsed=file.name.toLowerCase().endsWith(".json") ? JSON.parse(text) : parseCsv(text);
    const list=Array.isArray(parsed) ? parsed : parsed.jobs || parsed.data || [];
    const jobs=list.map(normalizeImported).filter(job=>job.title);
    showOpenings(jobs, jobs.length===1 ? "imported row" : "imported rows");
    status.textContent=`Loaded ${jobs.length} valid rows from ${file.name}. Review and save them.`;
  } catch (error) { status.textContent=`Could not import the file: ${error.message}`; }
  event.target.value="";
});

refreshCollectionTotal();

async function refreshPlatformLinks() {
  const params = new URLSearchParams({q: document.querySelector("#publicQuery").value.trim(), location: document.querySelector("#publicLocation").value.trim()});
  const response = await fetch(`/api/platform-links?${params}`);
  const data = await response.json();
  document.querySelector("#platformLinks").innerHTML = data.links.map(item => `<a href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.name)}</a>`).join("");
}
document.querySelector("#publicQuery").addEventListener("input", refreshPlatformLinks);
document.querySelector("#publicLocation").addEventListener("input", refreshPlatformLinks);
refreshPlatformLinks();
