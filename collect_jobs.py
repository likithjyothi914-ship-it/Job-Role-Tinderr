"""Collect every unique, verifiably dated job returned from the last 30 days."""
from argparse import ArgumentParser
from pathlib import Path
import os

from app import PUBLIC_SOURCES, build_combined_xlsx, fetch_all_department_jobs, fetch_public_jobs, load_collected, merge_unique, save_collected

DEFAULT_SOURCES = list(PUBLIC_SOURCES)


def collect(query, location, sources):
    jobs = []
    errors = []
    seen = set()
    for source in sources:
        try:
            results = fetch_public_jobs(source, query, location)
            for job in results:
                key = (
                    job.get("application_url", "").strip().lower().rstrip("/"),
                    job.get("title", "").strip().lower(),
                    job.get("company", "").strip().lower(),
                )
                if key not in seen:
                    jobs.append(job)
                    seen.add(key)
            print(f"{source}: {len(results)} matching openings")
        except Exception as error:
            errors.append(f"{source}: {error}")
            print(f"{source}: unavailable")
    return jobs, errors


def write_xlsx_safely(output_path, rows):
    """Write to a temporary file and replace the workbook only after success."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        content = build_combined_xlsx(rows)
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output_path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Could not safely update Excel workbook: {error}") from error


def main():
    parser = ArgumentParser(description="Collect jobs posted in the last 30 days and save one unique opening per Excel row.")
    parser.add_argument("--query", help="Role or keyword, for example cybersecurity analyst")
    parser.add_argument("--location", default="India", help="Candidate location (default: India)")
    parser.add_argument("--sources", nargs="+", choices=DEFAULT_SOURCES, default=DEFAULT_SOURCES)
    parser.add_argument("--output", help="Persistent output .xlsx path")
    args = parser.parse_args()

    query = args.query if args.query is not None else input("Enter a job role or keyword (leave blank for all roles): ").strip()
    location = args.location or "India"
    print(f"\nSearching jobs posted in the last 30 days for '{query or 'all roles'}' in {location}...")
    if query:
        jobs, errors = collect(query, location, args.sources)
    else:
        print("Searching all major departments in parallel...")
        jobs, errors = fetch_all_department_jobs(location, args.sources)

    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(exist_ok=True)
    filename = args.output or str(output_dir / "job_role_finder_combined.xlsx")
    output_path = Path(filename).expanduser().resolve()
    try:
        existing = load_collected()
        combined, added = merge_unique(existing, jobs)
        save_collected(combined)
        write_xlsx_safely(output_path, combined)
    except Exception as error:
        print(f"\nERROR: Existing data was not intentionally deleted. {error}")
        return 1

    print(f"\nExcel output updated: {output_path}")
    print(f"New recent rows added: {added}")
    print(f"Total unique jobs from the last 30 days: {len(combined)}")
    if not jobs:
        print("No new dated matches were returned. Previously saved recent rows were preserved.")
    if errors:
        print("Unavailable sources: " + "; ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
