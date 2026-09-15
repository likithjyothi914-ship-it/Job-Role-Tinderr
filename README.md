# Job Role Tinderr

## Live Tool

**Open the application:** [Job Role Tinderr](https://laikishjobroletinderr.s.gy/cnx2Y4)

Job Role Tinderr is a Python project that searches public job openings and creates a persistent Excel workbook with one unique opening per row. It also includes a local browser interface for exploring 520 deduplicated job roles and collecting records interactively.

## Primary output

The repository includes one combined Excel output: `output/job_role_finder_combined.xlsx`. Its first sheet contains 520 unique job roles across 13 categories. Its second sheet currently contains 567 unique, date-eligible job-opening records and grows when the collector or importer is rerun.

Run `collect_jobs.py`, enter a job role or leave it blank for all roles. The program searches all supported public feeds, rejects undated or older listings, removes duplicates and stores every returned job posted during the rolling last 30 days in the `Jobs - Last 30 Days` sheet in `output/job_role_finder_combined.xlsx`.

Leaving the keyword blank runs parallel searches across software, data/AI, cybersecurity, IT support, business, finance, marketing, sales, design, HR, healthcare, engineering, education, customer service, operations/logistics and administration.
The Arbeitnow connector checks up to five recent pages (up to 1,250 returned listings before India/date filtering). The project also uses Jobicy's public feed (up to 200 jobs) and up to twenty cursor-paginated Himalayas pages (up to 400 returned listings).

The live-opening Excel columns include collection time, job title, company, location, job details, source, application URL and a combined application-link-or-employer-email field.

### One-click Windows collector

1. Install Python 3.10 or later.
2. Double-click `run_collector_windows.bat`.
3. Enter a role such as `cybersecurity analyst`, or press Enter for all roles.
4. Wait while the program checks the public feeds.
5. Open the generated `.xlsx` file inside the `output` folder.

Internet access is required while retrieving current openings. No external Python package or API key is required.

## Main features

- 520 deduplicated job roles across 13 categories
- Search by role title, category, skill, qualification, or description
- Combine category, career-level, and work-mode filters
- View eligibility, experience requirements, role-specific skills, and qualifications
- Responsive design for desktop and mobile browsers
- Local JSON dataset and read-only REST endpoints
- Automated tests for core routes and filters
- Public-opening search using supported job feeds
- CSV and JSON import for data exported from other job websites
- Rolling 30-day collection that removes expired rows and keeps every unique verified result returned by the supported feeds
- Search buttons for LinkedIn, Internshala, Glassdoor, Indeed, Naukri, Foundit and Apna
- Application link or employer email stored for every opening when the source provides one
- Atomic JSON and Excel writes that preserve existing data if saving fails
- Excel dataset import with date filtering, title/company/location deduplication, and verification-status labeling

## Import an Excel dataset

Install the requirements, then run:

```bash
python import_jobs_excel.py path/to/job_openings.xlsx
```

Only rows dated within the rolling last 30 days are appended. Re-running the command preserves existing rows and skips duplicate URLs or matching title/company/location combinations. Imported links are marked as not independently verified unless the dataset already supplies a verification status.

## Windows setup

1. Install Python 3.10 or later from <https://www.python.org/downloads/>.
2. Extract the project ZIP.
3. Open the `Job_Role_Finder` folder.
4. Double-click `run_windows.bat`.
5. The launcher opens `http://127.0.0.1:5000`.

`run_windows.bat` starts the optional browser interface. Use `run_collector_windows.bat` when the required output is an Excel sheet.

Keep the command window open while demonstrating the project. Press `Ctrl+C` to stop it.

### Download the packaged Windows tool

Open the repository's **Actions** tab, select **Build Windows Tool**, open the latest successful run, and download the `JobRoleFinder-Windows` artifact. Extract it and run `JobRoleFinder.exe`. The tool opens automatically in the default browser; keep its command window open while using it.

## Manual setup

```bash
python app.py
```

Open <http://127.0.0.1:5000> in a browser.

## Collect public job openings

1. Scroll to `Collect India job openings into Excel`.
2. Enter a role or keyword and keep the candidate location as India.
3. Select all feeds or one supported feed, then press `Search last 30 days`.
4. Review the results and press `Save displayed rows`.
5. Press `Download Excel` to create `job_role_finder_combined.xlsx` with both sheets.

An internet connection is required only while searching a public feed or opening a platform search. The saved collection remains in `data/collected_jobs.json`. Each rerun removes jobs older than 30 days, keeps recent existing jobs, and adds all new unique results returned by the feeds. The exporter creates one Excel row per unique opening and includes the application link or employer email supplied by the source. LinkedIn, Internshala, Glassdoor, Indeed, Naukri, Foundit and Apna are opened through their own search pages rather than scraped; dated CSV/JSON exports from those platforms can be imported.

For specific job websites, use their own permitted export option and import the resulting CSV or JSON file. Arbitrary website scraping is not included. The file `data/sample_import.csv` can be used to demonstrate the import workflow without internet access; its rows are clearly marked as demonstration data.

## Tests

From the project folder, run:

```bash
python -m unittest discover -s tests -v
```

## Command-line examples

Search all roles for India:

```bash
python collect_jobs.py --query "" --location India
```

Search a specific role:

```bash
python collect_jobs.py --query "customer service" --location India
```

Choose sources and a persistent output name:

```bash
python collect_jobs.py --query "analyst" --sources remotive remoteok --output output/analyst_jobs.xlsx
```

## Project structure

```text
Job_Role_Finder/
  app.py                  Local Python server and API routes
  collect_jobs.py         Main collector that creates Excel output
  import_jobs_excel.py    Imports and deduplicates dated Excel rows
  data/jobs.json          Offline job-role catalogue
  static/css/style.css    Responsive visual design
  static/js/app.js        Search, filters, and role details
  index.html              Main application page
  tests/test_app.py       Automated tests
  tools/build_dataset.py  Rebuilds the JSON catalogue
  requirements.txt        Confirms no external package is required
  run_windows.bat         One-click Windows launcher
  run_collector_windows.bat  One-click Excel collector
```

## GitHub upload

The repository includes `.gitignore`, a license, documentation and tests. The deduplicated catalogue and persistent live-opening workbook are included as demonstration outputs.

```bash
git init
git add .
git commit -m "Add Job Role Tinderr and Excel collector"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/job-role-finder.git
git push -u origin main
```

Create an empty GitHub repository first and replace `YOUR_USERNAME` with your GitHub username.

## API endpoints

- `GET /api/jobs` returns all roles.
- `GET /api/jobs?q=python` searches the catalogue.
- `GET /api/jobs?category=Cybersecurity&level=Entry` combines filters.
- `GET /api/jobs/1` returns one role.
- `GET /health` confirms that the local server is working.
- `GET /api/public-jobs/search` searches one supported public feed.
- `GET /api/collected-jobs` returns saved opening rows.
- `POST /api/collected-jobs` adds rows and skips duplicates.
- `GET /api/collected-jobs/export.xlsx` downloads the saved rows as Excel.

## Scope

The application provides an expandable educational catalogue rather than claiming to contain every job title used worldwide. Job titles and requirements vary among employers and locations. New roles can be added to `tools/build_dataset.py`, after which the catalogue can be rebuilt by running:

```bash
python tools/build_dataset.py
```
