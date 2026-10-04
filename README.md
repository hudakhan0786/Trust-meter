# TRUSTMETER

**Verify Before You Believe.** TRUSTMETER is an explainable news credibility analysis demonstration. It reviews source-list matches, headline language, vocabulary signals, article structure, headline/body term overlap, and candidate claims. It does not determine whether an article is true.

> A credibility score estimates credibility from the signals available. It is not a definitive determination of truth. Independent verification is recommended for consequential claims.

## Run locally

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The server binds to loopback by default. Use the **Article URL** mode to fetch a public publisher page, **Paste article** to analyze text manually, or **Explore the demo** for a bundled offline sample. The CLI remains available:

```bash
python main.py --demo
python main.py --url https://publisher.example/article
python main.py --url https://publisher.example/article --headline "Headline" --body "Article text"
python main.py --history
```

## Product behavior

- Score bands are configured in `src/config.py`: 80–100 High Credibility, 60–79 Generally Credible, 40–59 Needs Verification, and 0–39 Low Credibility.
- Score weights are defined in one location. Source lists and explainable text signals contribute to a transparent aggregate; they are not trained probabilities or calibrated confidence.
- Unknown publishers receive a neutral source prior with limited confidence. An unknown publisher is not treated as misinformation.
- Candidate claim sentences are shown as **UNVERIFIED**. `src/evidence.py` defines an `EvidenceProvider` interface and a safe empty provider. No citation or external evidence is fabricated.
- The report shows a confidence label and a limitation for each component. “Confidence” is qualitative and is not a statistical probability.
- Text pasted by a user and analysis results are stored in the local SQLite database. History lists every saved check; selecting an entry opens its report inside TRUSTMETER, with the recorded score, source, and exact UTC check time. New checks retain an article snapshot so a later recheck does not change earlier report details.

## Analysis flow

```text
Input → validation → bounded article fetch → metadata and body extraction
      → source/headline/text/quality/consistency signals
      → candidate claims → weighted credibility assessment → SQLite + report
```

### Signals and limitations

| Component | What it indicates | Important limitation |
| --- | --- | --- |
| Source reliability | Match against illustrative local domain lists | A list match is not editorial or factual verification |
| Claim evidence | Current score uses a neutral prior until a provider is configured | The bundled provider performs no external search |
| Headline neutrality | All-caps words, trigger phrases and punctuation | Heuristics can miss context and produce false positives |
| Linguistic quality | Vocabulary diversity (TTR/MATTR) | Vocabulary diversity does not establish truth or writing quality |
| Article quality | Available text length, attribution cues and source record | Signals are incomplete and are not all publisher metadata |
| Headline consistency | Headline term overlap with body text | This is not semantic entailment or contradiction detection |

The score is an engineering demonstration, not an empirically validated model. The bundled whitelist and blacklist are small illustrative seed lists; they require editorial review and regular maintenance before any consequential use.

## URL-fetching protections

The scraper accepts only HTTP(S), rejects credentials, localhost, private/reserved IP addresses and non-public DNS answers, disables environment proxies, checks each redirect destination, limits redirects, uses connection/read timeouts, streams with a 2 MB cap, and only parses HTML. Metadata extraction supports common Open Graph, article metadata, JSON-LD, canonical links, headings, article containers and paragraph fallbacks. A publisher may still block access, require JavaScript or a subscription, or expose an incomplete page; users can paste text instead.

The Flask app caps request bodies at 600 KB, validates headline/body lengths, avoids debug mode, binds locally, and sets basic browser security headers. For an internet-facing deployment, add authentication, CSRF protections, request throttling, a hardened egress proxy/DNS pinning, secrets management, retention controls, and production WSGI hosting.

## Web routes and API

- `GET /` — landing page and URL/text workspace
- `POST /analyze` — form report; accepts JSON for the API
- `GET /demo` — offline sample report
- `GET /history` — saved analysis history
- `GET /history/<log_id>` — one saved report, opened inside the app
- `GET /api/history` — JSON history

Example API request:

```json
{
  "input_mode": "text",
  "source_url": "https://publisher.example/story",
  "headline": "A sample headline",
  "body": "Paste article text here."
}
```

The JSON report contains `credibility_score`, `verdict`, component explanations and limitations, candidate claims, source details, and a qualitative confidence label. Validation failures return a human-readable `error` and HTTP 400.

## Database

The existing SQLite schema is preserved: `Articles` stores submitted article material and `Scoring_Log` stores score components and serialized explanations. Analysis components, claims, and the checked article snapshot are included in the existing JSON `lexical_breakdown` field, so no destructive migration is needed. Data lives in `data/fake_news_detector.db`.

## Tests

```bash
python -m unittest discover tests -v
```

Tests cover scoring modules, database persistence, public URL validation, local/private address rejection, extraction metadata, home/demo/history/API routes, and response security headers. They do not make live network requests.

## Project layout

```text
app.py                 Flask routes and JSON API
main.py                CLI demo, URL analysis and history
src/config.py          score weights, thresholds and paths
src/scraper.py         SSRF-aware bounded fetch and metadata extraction
src/source_reputation.py  normalized local publisher lookup
src/evidence.py        claim surfacing and evidence-provider interface
src/pipeline.py        explainable credibility component aggregation
src/database.py        SQLite article and scoring history
templates/             landing, report, in-app history and saved reports
static/                responsive styling and reduced-motion-aware UI
tests/                 scoring, scraper and web route tests
```
