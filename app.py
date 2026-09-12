"""Local server for Job Role Finder using only the Python standard library."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.sax.saxutils import escape as xml_escape
import csv
import gzip
import html
import io
import json
import os
import re
import shutil
import zipfile
import xlsxwriter

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "jobs.json"
DATA_GZIP_FILE = BASE_DIR / "data" / "jobs.json.gz"
COLLECTED_FILE = BASE_DIR / "data" / "collected_jobs.json"
COLLECTED_GZIP_FILE = BASE_DIR / "data" / "collected_jobs.json.gz"
PUBLIC_SOURCES = {
    "remotive": "https://remotive.com/api/remote-jobs",
    "remoteok": "https://remoteok.com/api",
    "arbeitnow": "https://www.arbeitnow.com/api/job-board-api",
    "jobicy": "https://jobicy.com/api/v2/remote-jobs",
    "himalayas": "https://himalayas.app/jobs/api",
}
RECENT_DAYS = 30
PLATFORM_SEARCH_URLS = {
    "LinkedIn": "https://www.linkedin.com/jobs/search/",
    "Internshala": "https://internshala.com/jobs/",
    "Glassdoor": "https://www.glassdoor.co.in/Job/india-jobs-SRCH_IL.0,5_IN115.htm",
    "Indeed": "https://in.indeed.com/jobs",
    "Naukri": "https://www.naukri.com/jobs-in-india",
    "Foundit": "https://www.foundit.in/srp/results",
    "Apna": "https://apna.co/jobs/jobs-in-india",
}
DEPARTMENT_QUERIES = {
    "Software Development": "developer",
    "Data and Artificial Intelligence": "data",
    "Cybersecurity": "security",
    "Cloud and IT Infrastructure": "IT support",
    "Business and Management": "business",
    "Finance and Accounting": "finance",
    "Marketing": "marketing",
    "Sales": "sales",
    "Design and Creative": "design",
    "Human Resources": "human resources",
    "Healthcare": "healthcare",
    "Engineering and Manufacturing": "engineer",
    "Education": "education",
    "Customer Service": "customer service",
    "Operations and Logistics": "operations",
    "Administration": "administrative",
}
INDIA_LOCATION_TERMS = {
    "india", "bengaluru", "bangalore", "hyderabad", "mumbai", "delhi", "new delhi",
    "gurugram", "gurgaon", "noida", "pune", "chennai", "kolkata", "ahmedabad", "jaipur",
    "kochi", "cochin", "coimbatore", "chandigarh", "lucknow", "indore", "bhubaneswar",
    "visakhapatnam", "vijayawada", "nagpur", "surat", "vadodara", "mysuru", "mysore",
}

def load_jobs():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    with gzip.open(DATA_GZIP_FILE, "rt", encoding="utf-8") as handle:
        return json.load(handle)

def filter_jobs(jobs, query="", category="", level="", work_mode=""):
    query = query.strip().lower()
    results = jobs
    if query:
        results = [job for job in results if query in " ".join([
            job["title"], job["category"], job["description"],
            job["qualification"], job.get("eligibility", ""),
            job.get("experience_required", ""), " ".join(job["skills"]),
        ]).lower()]
    if category:
        results = [job for job in results if job["category"] == category]
    if level:
        results = [job for job in results if job["level"] == level]
    if work_mode:
        results = [job for job in results if job["work_mode"] == work_mode]
    return results

def clean_text(value):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()

def load_collected():
    if not COLLECTED_FILE.exists():
        if not COLLECTED_GZIP_FILE.exists():
            return []
        try:
            with gzip.open(COLLECTED_GZIP_FILE, "rt", encoding="utf-8") as handle:
                return recent_jobs(deduplicate_rows(json.load(handle)))
        except (json.JSONDecodeError, OSError, ValueError) as error:
            raise RuntimeError(f"Could not read bundled job collection: {error}") from error
    try:
        rows = json.loads(COLLECTED_FILE.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("saved collection must contain a JSON list")
        return recent_jobs(deduplicate_rows(rows))
    except (json.JSONDecodeError, OSError, ValueError) as error:
        backup = COLLECTED_FILE.with_name(
            f"{COLLECTED_FILE.stem}.corrupt-{datetime.now():%Y%m%d-%H%M%S}.json"
        )
        try:
            shutil.copy2(COLLECTED_FILE, backup)
        except OSError:
            pass
        raise RuntimeError(f"Could not read saved collection; original preserved at {backup.name}: {error}") from error

def save_collected(rows):
    rows = recent_jobs(deduplicate_rows(rows))
    COLLECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = COLLECTED_FILE.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(COLLECTED_FILE)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Could not safely save collected jobs: {error}") from error

def normalized_identity_value(value):
    return clean_text(value).strip().lower()

def job_identity(row):
    url = normalized_identity_value(row.get("application_url", "")).rstrip("/")
    if url:
        return ("url", url)
    return (
        "details",
        normalized_identity_value(row.get("title", "")),
        normalized_identity_value(row.get("company", "")),
        normalized_identity_value(row.get("location", "")),
    )

def job_identity_keys(row):
    """Return every stable key that can identify the same opening."""
    keys = []
    url = normalized_identity_value(row.get("application_url", "")).rstrip("/")
    if url:
        keys.append(("url", url))
    details = (
        "details",
        normalized_identity_value(row.get("title", "")),
        normalized_identity_value(row.get("company", "")),
        normalized_identity_value(row.get("location", "")),
    )
    if all(details[1:]):
        keys.append(details)
    return keys or [job_identity(row)]

def deduplicate_rows(rows):
    unique = []
    seen = set()
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        keys = job_identity_keys(row)
        if not normalized_identity_value(row.get("title", "")) or any(key in seen for key in keys):
            continue
        if not clean_text(row.get("verification_status", "")):
            row["verification_status"] = "Public API feed - verify before applying"
        row["application_link_or_employer_email"] = application_contact(row)
        unique.append(row)
        seen.update(keys)
    return unique

def merge_unique(existing, incoming):
    merged = recent_jobs(deduplicate_rows(existing))
    positions = {}
    for index, row in enumerate(merged):
        for key in job_identity_keys(row):
            positions[key] = index
    added = 0
    for row in recent_jobs(deduplicate_rows(incoming)):
        keys = job_identity_keys(row)
        match = next((positions[key] for key in keys if key in positions), None)
        if match is None:
            index = len(merged)
            for key in keys:
                positions[key] = index
            merged.append(row)
            added += 1
        else:
            current = merged[match]
            for field, value in row.items():
                if clean_text(value) and not clean_text(current.get(field, "")):
                    current[field] = value
    merged.sort(key=lambda row: parse_published_at(row.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return merged, added

def parse_published_at(value):
    """Parse common API/export date formats as an aware UTC datetime."""
    text = clean_text(value)
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%b %d, %Y"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def recent_jobs(rows, now=None, days=RECENT_DAYS):
    """Keep only verifiable postings from the inclusive rolling date window."""
    now = now or datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).date()
    kept = []
    for row in rows or []:
        published = parse_published_at(row.get("published_at", ""))
        if published and cutoff_date <= published.date() <= now.date():
            kept.append(row)
    return kept

def platform_search_links(query="", location="India"):
    query = clean_text(query)
    location = clean_text(location) or "India"
    return [
        {"name": "LinkedIn", "url": PLATFORM_SEARCH_URLS["LinkedIn"] + "?" + urlencode({"keywords": query, "location": location, "f_TPR": "r2592000"})},
        {"name": "Internshala", "url": PLATFORM_SEARCH_URLS["Internshala"]},
        {"name": "Glassdoor", "url": PLATFORM_SEARCH_URLS["Glassdoor"] + "?fromAge=30"},
        {"name": "Indeed", "url": PLATFORM_SEARCH_URLS["Indeed"] + "?" + urlencode({"q": query, "l": location, "fromage": 30})},
        {"name": "Naukri", "url": PLATFORM_SEARCH_URLS["Naukri"] + "?" + urlencode({"k": query, "l": location, "jobAge": 30})},
        {"name": "Foundit", "url": PLATFORM_SEARCH_URLS["Foundit"] + "?" + urlencode({"query": query, "locations": location})},
        {"name": "Apna", "url": PLATFORM_SEARCH_URLS["Apna"]},
    ]

def application_contact(row):
    url = clean_text(row.get("application_url", ""))
    if url:
        return url
    existing = clean_text(row.get("application_link_or_employer_email", ""))
    if existing and existing != "Not provided by source":
        return existing
    for key in ("employer_email", "contact_email", "email"):
        email = clean_text(row.get(key, ""))
        if email:
            return email
    description = clean_text(row.get("description", ""))
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", description, re.IGNORECASE)
    return match.group(0) if match else "Not provided by source"

def extract_experience(description):
    text = clean_text(description)
    match = re.search(r"\b(?:minimum\s+)?\d+\s*(?:\+|to|-|–)?\s*\d*\s+years?(?:\s+of\s+experience)?\b", text, re.IGNORECASE)
    if match:
        return match.group(0)
    if re.search(r"\bfreshers?\b|\bentry[- ]level\b", text, re.IGNORECASE):
        return "Freshers/entry-level mentioned"
    return ""

def extract_eligibility(description):
    text = clean_text(description)
    patterns = [
        r"(?:bachelor'?s|master'?s) degree[^.]{0,140}",
        r"(?:degree|diploma) in [^.]{1,140}",
        r"(?:12th|intermediate|graduate|postgraduate)[^.]{0,120}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return ""

def normalize_job(item, source):
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if source == "remotive":
        description = clean_text(item.get("description", ""))
        row = {"title": item.get("title", ""), "company": item.get("company_name", ""), "location": item.get("candidate_required_location", ""), "remote": "Yes", "job_type": item.get("job_type", ""), "category": item.get("category", ""), "tags": ", ".join(item.get("tags", [])), "skills_required": ", ".join(item.get("tags", [])), "experience_required": extract_experience(description), "eligibility": extract_eligibility(description), "published_at": item.get("publication_date", ""), "source": "Remotive", "application_url": item.get("url", ""), "description": description[:1200], "collected_at": collected_at}
        row["application_link_or_employer_email"] = application_contact(row)
        return row
    if source == "remoteok":
        description = clean_text(item.get("description", ""))
        row = {"title": item.get("position", ""), "company": item.get("company", ""), "location": item.get("location", "Worldwide"), "remote": "Yes", "job_type": "Remote", "category": "", "tags": ", ".join(item.get("tags", [])), "skills_required": ", ".join(item.get("tags", [])), "experience_required": extract_experience(description), "eligibility": extract_eligibility(description), "published_at": item.get("date", ""), "source": "Remote OK", "application_url": item.get("url", ""), "description": description[:1200], "collected_at": collected_at}
        row["application_link_or_employer_email"] = application_contact(row)
        return row
    if source == "jobicy":
        description = clean_text(item.get("jobDescription", ""))
        industries = item.get("jobIndustry", [])
        job_types = item.get("jobType", [])
        row = {"title": item.get("jobTitle", ""), "company": item.get("companyName", ""), "location": item.get("jobGeo", "Worldwide"), "remote": "Yes", "job_type": ", ".join(job_types) if isinstance(job_types, list) else job_types, "category": ", ".join(industries) if isinstance(industries, list) else industries, "tags": ", ".join(industries) if isinstance(industries, list) else industries, "skills_required": ", ".join(industries) if isinstance(industries, list) else industries, "experience_required": item.get("jobLevel", "") or extract_experience(description), "eligibility": extract_eligibility(description), "published_at": item.get("pubDate", ""), "source": "Jobicy", "application_url": item.get("url", ""), "description": description[:1200], "collected_at": collected_at}
        row["application_link_or_employer_email"] = application_contact(row)
        return row
    if source == "himalayas":
        description = clean_text(item.get("description", ""))
        locations = item.get("locationRestrictions", [])
        categories = item.get("categories", []) or item.get("parentCategories", [])
        seniority = item.get("seniority", [])
        published = item.get("pubDate", "")
        if isinstance(published, (int, float)):
            published = datetime.fromtimestamp(published, timezone.utc).isoformat()
        row = {"title": item.get("title", ""), "company": item.get("companyName", ""), "location": ", ".join(locations) if locations else "Worldwide", "remote": "Yes", "job_type": item.get("employmentType", ""), "category": ", ".join(item.get("parentCategories", [])), "tags": ", ".join(categories), "skills_required": ", ".join(categories), "experience_required": ", ".join(seniority) if seniority else extract_experience(description), "eligibility": extract_eligibility(description), "published_at": published, "source": "Himalayas", "application_url": item.get("applicationLink", "") or item.get("guid", ""), "description": description[:1200], "collected_at": collected_at}
        row["application_link_or_employer_email"] = application_contact(row)
        return row
    description = clean_text(item.get("description", ""))
    row = {"title": item.get("title", ""), "company": item.get("company_name", ""), "location": item.get("location", ""), "remote": "Yes" if item.get("remote") else "No", "job_type": ", ".join(item.get("job_types", [])), "category": "", "tags": ", ".join(item.get("tags", [])), "skills_required": ", ".join(item.get("tags", [])), "experience_required": extract_experience(description), "eligibility": extract_eligibility(description), "published_at": datetime.fromtimestamp(item.get("created_at", 0), timezone.utc).date().isoformat() if item.get("created_at") else "", "source": "Arbeitnow", "application_url": item.get("url", ""), "description": description[:1200], "collected_at": collected_at}
    row["application_link_or_employer_email"] = application_contact(row)
    return row

def fetch_public_jobs(source, query, location="India"):
    if source not in PUBLIC_SOURCES:
        raise ValueError("Unsupported public source")
    url = PUBLIC_SOURCES[source]
    if source == "remotive" and query:
        url += "?" + urlencode({"search": query})
    def download_json(target):
        request = Request(target, headers={"User-Agent": "JobRoleFinder/2.0 (local educational project)", "Accept": "application/json"})
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    if source == "arbeitnow":
        page_urls = [f"{url}?page={page}" for page in range(1, 6)]
        raw = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            for payload in executor.map(download_json, page_urls):
                raw.extend(payload.get("data", []))
    elif source == "himalayas":
        raw = []
        next_url = url
        for _ in range(20):
            payload = download_json(next_url)
            raw.extend(payload.get("jobs", []))
            cursor = payload.get("nextCursor")
            if not cursor:
                break
            next_url = url + "?" + urlencode({"cursor": cursor})
    else:
        if source == "jobicy":
            url += "?" + urlencode({"count": 200})
        payload = download_json(url)
        raw = payload.get("jobs", []) if source in {"remotive", "jobicy"} else payload[1:] if isinstance(payload, list) else []
    results = [normalize_job(item, source) for item in raw]
    query_words = [word for word in query.lower().split() if word]
    location = location.strip().lower()
    def matches(job):
        haystack = " ".join([job["title"], job["company"], job["category"], job["tags"], job["description"]]).lower()
        query_ok = not query_words or all(word in haystack for word in query_words)
        job_location = job["location"].lower()
        india_match = any(term in job_location for term in INDIA_LOCATION_TERMS)
        worldwide_match = any(term in job_location for term in ["worldwide", "anywhere", "global"])
        location_ok = not location or location in job_location or (location == "india" and (india_match or worldwide_match))
        return query_ok and location_ok
    return recent_jobs([job for job in results if matches(job)])

def fetch_all_department_jobs(location="India", sources=None):
    """Search all department groups efficiently and return unique recent jobs."""
    sources = sources or list(PUBLIC_SOURCES)
    tasks = []
    for source in sources:
        if source == "remotive":
            tasks.extend((source, department, query) for department, query in DEPARTMENT_QUERIES.items())
        else:
            tasks.append((source, "All Departments", ""))
    jobs, errors = [], []
    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as executor:
        future_map = {executor.submit(fetch_public_jobs, source, query, location): (source, department) for source, department, query in tasks}
        for future in as_completed(future_map):
            source, department = future_map[future]
            try:
                results = future.result()
                for row in results:
                    if not row.get("category"):
                        row["category"] = department
                jobs.extend(results)
            except Exception as error:
                errors.append(f"{source} ({department}): {clean_text(error)}")
    jobs, _ = merge_unique([], jobs)
    return jobs, errors

EXCEL_COLUMNS = ["collected_at", "title", "company", "location", "published_at", "remote", "job_type", "category", "skills_required", "experience_required", "eligibility", "source", "verification_status", "application_url", "application_link_or_employer_email", "description"]

def excel_safe(value):
    value = str(value or "")
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value

def build_xlsx(rows):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    _write_openings_sheet(workbook, deduplicate_rows(rows), "Job Openings")
    workbook.close()
    return output.getvalue()

def build_combined_xlsx(opening_rows, role_rows=None):
    """Create a standard Excel workbook with the catalogue and recent openings."""
    role_rows = role_rows if role_rows is not None else load_jobs()
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    header = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#176B87", "border": 1, "text_wrap": True, "valign": "vcenter"})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
    sheet = workbook.add_worksheet("Job Role Catalogue")
    headers = ["ID", "Job Title", "Category", "Career Level", "Experience Required", "Eligibility", "Typical Qualification", "Work Mode", "Description", "Skills Required"]
    sheet.write_row(0, 0, headers, header)
    for index, role in enumerate(role_rows, 1):
        values = [role.get("id", ""), role.get("title", ""), role.get("category", ""), role.get("level", ""), role.get("experience_required", ""), role.get("eligibility", ""), role.get("qualification", ""), role.get("work_mode", ""), role.get("description", ""), ", ".join(role.get("skills", []))]
        sheet.write_row(index, 0, [excel_safe(value) for value in values], wrap)
    sheet.freeze_panes(1, 2)
    sheet.autofilter(0, 0, max(1, len(role_rows)), len(headers) - 1)
    sheet.set_column("A:A", 8); sheet.set_column("B:C", 28); sheet.set_column("D:H", 24); sheet.set_column("I:J", 48)
    _write_openings_sheet(workbook, recent_jobs(deduplicate_rows(opening_rows)), "Jobs - Last 30 Days")
    workbook.close()
    return output.getvalue()

def _write_openings_sheet(workbook, rows, name):
    sheet = workbook.add_worksheet(name)
    header = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#176B87", "border": 1, "text_wrap": True, "valign": "vcenter"})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})
    link = workbook.add_format({"font_color": "blue", "underline": True, "text_wrap": True, "valign": "top"})
    headers = [column.replace("_", " ").title() for column in EXCEL_COLUMNS]
    sheet.write_row(0, 0, headers, header)
    for row_index, row in enumerate(rows, 1):
        for column_index, column in enumerate(EXCEL_COLUMNS):
            value = excel_safe(row.get(column, ""))
            if column in {"application_url", "application_link_or_employer_email"} and value.startswith(("http://", "https://")):
                sheet.write_url(row_index, column_index, value, link, value)
            else:
                sheet.write(row_index, column_index, value, wrap)
    if not rows:
        sheet.write(1, 1, "No verified jobs from the last 30 days saved yet", wrap)
        sheet.write(1, 13, "Run collect_jobs.py or import a dated CSV/JSON file", wrap)
    sheet.freeze_panes(1, 3)
    sheet.autofilter(0, 0, max(1, len(rows)), len(headers) - 1)
    sheet.set_column("A:A", 22); sheet.set_column("B:C", 28); sheet.set_column("D:L", 20); sheet.set_column("M:O", 48)

class JobRoleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/jobs":
            params = parse_qs(parsed.query)
            jobs = filter_jobs(load_jobs(), params.get("q", [""])[0], params.get("category", [""])[0], params.get("level", [""])[0], params.get("work_mode", [""])[0])
            return self.send_json({"count": len(jobs), "jobs": jobs})
        if parsed.path.startswith("/api/jobs/"):
            try:
                job_id = int(parsed.path.rsplit("/", 1)[-1])
            except ValueError:
                return self.send_json({"error": "Invalid job role ID"}, 400)
            job = next((item for item in load_jobs() if item["id"] == job_id), None)
            return self.send_json(job if job else {"error": "Job role not found"}, 200 if job else 404)
        if parsed.path == "/health":
            return self.send_json({"status": "ok", "roles": len(load_jobs())})
        if parsed.path == "/api/public-jobs/search":
            params = parse_qs(parsed.query)
            source = params.get("source", ["all"])[0]
            query = params.get("q", [""])[0]
            location = params.get("location", ["India"])[0]
            try:
                if source == "all":
                    if query:
                        jobs, warnings = [], []
                        for source_name in PUBLIC_SOURCES:
                            try:
                                jobs.extend(fetch_public_jobs(source_name, query, location))
                            except Exception as error:
                                warnings.append(f"{source_name}: {clean_text(error)}")
                        jobs, _ = merge_unique([], jobs)
                    else:
                        jobs, warnings = fetch_all_department_jobs(location)
                    return self.send_json({"count": len(jobs), "jobs": jobs, "warnings": warnings, "days": RECENT_DAYS})
                jobs = fetch_public_jobs(source, query, location)
                return self.send_json({"count": len(jobs), "jobs": jobs, "warnings": [], "days": RECENT_DAYS})
            except Exception as error:
                return self.send_json({"error": f"The public source could not be reached: {clean_text(error)}"}, 502)
        if parsed.path == "/api/platform-links":
            params = parse_qs(parsed.query)
            return self.send_json({"links": platform_search_links(params.get("q", [""])[0], params.get("location", ["India"])[0])})
        if parsed.path == "/api/collected-jobs":
            try:
                rows = load_collected()
                return self.send_json({"count": len(rows), "jobs": rows})
            except RuntimeError as error:
                return self.send_json({"error": clean_text(error)}, 500)
        if parsed.path == "/api/collected-jobs/export.xlsx":
            try:
                body = build_combined_xlsx(load_collected())
            except RuntimeError as error:
                return self.send_json({"error": clean_text(error)}, 500)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="job_role_finder_combined.xlsx"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/collected-jobs":
            return self.send_json({"error": "Route not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            incoming = payload.get("jobs", [])
            if not isinstance(incoming, list): raise ValueError("jobs must be a list")
            current = load_collected()
            prepared = []
            for raw in incoming[:1000]:
                row = {column: clean_text(raw.get(column, "")) for column in EXCEL_COLUMNS + ["description"]}
                row["collected_at"] = row["collected_at"] or datetime.now(timezone.utc).isoformat(timespec="seconds")
                row["application_link_or_employer_email"] = application_contact(row)
                prepared.append(row)
            valid = recent_jobs(prepared)
            rejected = len(prepared) - len(valid)
            current, added = merge_unique(current, valid)
            save_collected(current)
            return self.send_json({"added": added, "rejected": rejected, "count": len(current), "days": RECENT_DAYS})
        except Exception as error:
            return self.send_json({"error": clean_text(error)}, 400)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

def create_server(host="127.0.0.1", port=5000):
    return ThreadingHTTPServer((host, port), JobRoleHandler)

if __name__ == "__main__":
    server = create_server()
    print("Job Role Finder is running at http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the application.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nApplication stopped.")
    finally:
        server.server_close()
