# College Syllabus Buddy

A mobile-first, GitHub Pages-compatible syllabus finder for Panjab University (PU), Chandigarh. It uses official PU indexes and PDF sources, a Python update pipeline, and GitHub Actions.

## Important accuracy note

The initial JSON category files intentionally contain **zero syllabus records**. The repository does not pretend that PDF extraction has been verified. The pipeline downloads and validates official PDFs, but the first version of the extractor is conservative: it publishes only records with clearly labelled subject fields and a validated semester/session. Many university PDFs use table layouts or scanned pages, so some documents may be safely skipped and need a dedicated parser. A skipped document does not erase previous valid records.

Do not claim that every PU update is automatically parsed correctly until you have tested the extractor against each official PDF and inspected its output.

## Features

- Mobile-first responsive interface, desktop support, search and filter controls.
- Course, semester, category, subject, paper code/title filters.
- Light/dark theme with local preference.
- Print-friendly paper cards.
- Official source links, academic session, hash and last-updated fields.
- Official index crawler, SHA-256 content detection, staged PDF download and PDF validation.
- Conservative extraction, validation, update history and conditional Git commits.
- Extensible source manifest and category JSON files.

## Run locally

Python 3.12 recommended.

```bash
python -m pip install requests beautifulsoup4 pypdf
python scripts/update_sources.py
python scripts/extract_syllabus.py
python scripts/validate_data.py
python -m http.server 8000
```

Open `http://localhost:8000`. Do not open `index.html` as a `file://` URL; browsers block JSON `fetch()` in that mode.

## GitHub Pages deployment

1. Create or open the repository on GitHub and upload these files to the repository root.
2. Open **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**, select `main` and `/ (root)`, then Save.
4. Wait for deployment and open the URL shown on the Pages settings screen.
5. In **Settings → Actions → General → Workflow permissions**, allow workflows to have read/write permissions if the repository's organization settings require it. The workflow declares `contents: write`.
6. Open **Actions → Update PU Syllabus Data → Run workflow** for a first manual run.
7. Review the run log and `data/discovery-report.json`. A successful workflow means the pipeline completed; it does not mean every PDF was parsed into complete records.

## Automatic monitoring

`.github/workflows/update-syllabus.yml` checks every Monday at 02:17 UTC and supports manual runs. GitHub scheduled workflows can be delayed and may be disabled on inactive public repositories, so run manually when needed.

The crawler checks configured official index pages and the initial seed PDF URLs. It restricts source hosts to official PU domains and verifies PDF magic bytes, size and page count. SHA-256 is the authoritative content-change signal; HTTP ETag and Last-Modified are stored as hints. The pipeline does not create a commit if tracked data is unchanged.

## Adding sources and categories

Edit `data/sources.json`:
- Add official index pages to `indexes`.
- Add known official PDFs to `seedDocuments`, specifying `course`, `category`, `label`, and `url`.
- Extend `CATEGORY_FILES` in `scripts/extract_syllabus.py` for new categories.
- Add corresponding JSON paths to `DATA_FILES` in `script.js` for frontend loading.

For a scalable multi-course deployment, the next improvement should be to have the crawler emit a generated `data/catalog.json` so the frontend discovers JSON files dynamically rather than maintaining `DATA_FILES`. GitHub Pages does not provide directory listing APIs, so the catalog must be generated at build/update time.

## Data schema

See `schemas/syllabus-record.schema.json`. Fields that are not found in an official document remain `null` or absent. Every published record must contain course, semester, category, subject, official source URL, SHA-256 document hash and academic session.

## Safe publishing model

- Download to a temporary `.part` file and validate before replacing active PDF.
- Preserve prior PDF versions when the same URL's bytes change.
- Treat content hash as the main change signal, not URL or filename alone.
- Do not publish a PDF with invalid header, zero pages, or very low extracted text.
- Do not replace valid category records when extraction fails.
- Validate all published records before commit.
- No commit is made if tracked files have no differences.

## Known limitations that require honest handling

1. PU index HTML layouts may change; the crawler reports failures and keeps known sources.
2. Some PDFs have table layouts or scanned content that generic text extraction cannot safely parse. Those are skipped rather than guessed.
3. A syllabus index may link to HTML documents, DOCX files or documents on additional official subdomains; add explicit validation and parsers before accepting those formats.
4. `lastUpdated` currently means the source download/change date, not necessarily the university's publication date.
5. The source crawler discovers links that look like syllabus PDFs. New courses/categories need classification rules before their records are published.
6. GitHub Pages is static hosting. The scheduled GitHub Action updates repository JSON, which Pages then serves; no always-on backend is required.

## Official seed sources

Configured in `data/sources.json`, including the PU BA/Arts syllabus indexes, NEP index, older archives, and the eight 2026 BA PDF URLs supplied for this project.
