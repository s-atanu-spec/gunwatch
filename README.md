# GunWatch — open-source news monitor

A lightweight US gun-violence news tracker with source-linked summaries, incident grouping, location confidence and case-based analytics. Built with Python, SQLite and plain JavaScript, with Codex assistance.

**The whole deployment runs on GitHub:** Actions collects and processes news; a dedicated `collector-state` branch persists the SQLite database and cooldown; Pages serves the dashboard. No PHP host, browser automation or paid map service is needed. Optional AI extraction uses a server-side Groq API key.

## What the numbers mean

The primary analytics count distinct news stories; strict incident groups are retained separately. Multiple matching reports attach to one case, retaining all source links. Reports without enough evidence to identify or safely compare an incident remain in **Unresolved reports**, outside the case count. Consequently these are conservative, incomplete news-derived counts, not comprehensive or independently verified official statistics.

Automatic duplicate matching requires:

- The same normalized street/address or block and city/county/state context.
- The same source-supported incident date.
- Reported local times within 30 minutes.
- Matching explicitly reported casualty fields. Unknown counts stay unknown, never zero.

All members of a group must match each other, preventing a chain of overlapping time windows from merging unrelated incidents. Different casualty figures, ambiguous matches and missing inputs are not automatically merged. Evolving casualty counts can therefore create separate candidate cases until reviewed. Matching uses source text and rules, not identity guesses from a language model.

The daily coverage chart uses publication dates and measures news coverage; publication times never become incident times. The dashboard's reporting calendar is America/New_York. Explicit local times remain as written in the source. Relative dates such as Friday are anchored to publication in that calendar, which can be uncertain around midnight for western states. The evidence is visible for review.

## Location finder

- Bundled Census data covers US cities, towns, Census-designated places, counties and state centers.
- Matches explicit city/state and county/state pairs; distinctive unambiguous city names can also be resolved.
- Extracts numbered street addresses, block descriptions, named streets and named areas. A neighborhood with no verified coordinates inherits its supported city/county area, not invented coordinates.
- Makes at most five uncached US Census address requests per accepted collection. Results, including failures, are cached. No key required.
- **Red pins:** a Census address match. Coordinates are interpolated along an address range, not a verified incident scene.
- **Yellow pins:** an approximate city, county or state center. The location evidence explains the precision.
- No defensible geographic area means no pin. Ambiguous street names or multiple locations are not resolved arbitrarily.

The default news map shows report locations using the selected publication window, independently of case linkage. Pin groups show story counts, not incident counts. A separate mode shows counted cases using today’s incident date. See [Census API documentation](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html).

## Summaries and sources

The default sources are Google News US search, CBS News US and NPR National RSS. Source coverage and availability vary; a US feed edition does not guarantee that every returned report is domestic. Cases require a matched US location.

RSS descriptions supply short, extractive summaries. For supported publisher URLs, the collector can read structured article text when robots.txt permits it. This is bounded to five new or changed articles per run, with no redirects, retries, login or paywall bypass. Only short excerpts and extraction evidence are retained; bounded source excerpts of up to 10,000 characters are retained for extraction; full article bodies are not published. Aggregator link lists are not presented as summaries. When no usable text is available, the card clearly says **headline only**.

Optional AI extraction uses Groq-hosted `openai/gpt-oss-20b`. Source quotes and Census names must pass validation before use. Missing state evidence, ambiguous places and unsupported summaries are rejected.

## Collection and persistence

`.github/workflows/collect.yml` runs at minutes 17 and 47 of each hour, on a main-branch push, or through Run workflow.

1. Restore the database and state from `collector-state`.
2. If the 30-minute gate has expired, commit and push a cooldown reservation **before** any external requests.
3. Collect feeds, extract incident facts, geocode eligible addresses and group cases.
4. Persist the SQLite database, source backoff and logs to the state branch.
5. Build static JSON and deploy it with the official GitHub Pages Actions.

Workflow concurrency serializes runs. A non-fast-forward reservation fails before collecting. A cancellation after reservation still leaves the 30-minute cooldown in Git. HTTP 403, 429 and 503 apply longer source backoff, with Retry-After honored. Errors preserve existing reports. Do not delete the state branch or reset its files to force collection.

The public dashboard refreshes published JSON every minute without a page reload. **Opening a GitHub Pages site cannot securely dispatch a privileged workflow.** Collection is scheduled on Actions; visitors read the latest published snapshot. Owners can run the workflow manually, which still respects the gate. No token is exposed to the browser.

GitHub schedules are best-effort and may run late or be dropped. Scheduled runs only use the default branch and may be disabled in inactive public repositories. See [GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The SQLite database lives in a public data branch, so it must contain only public news metadata and snippets. Never import personal files, credentials or private reports. Git history grows with snapshots; monitor repository size and archive responsibly before it becomes large. Git is sufficient for this initial small deployment, not a high-volume long-term database service.

## Enable the deployment

1. Keep this code on the public repository's `main` branch.
2. In Settings → Pages, select **GitHub Actions** as the source.
3. Enable Actions and run **Collect and publish**.
4. Open the Pages URL shown by the successful deployment.

Core collection works without an API key. AI extraction needs the optional `GROQ_API_KEY` repository Actions secret. The job uses the repository-scoped, temporary GitHub Actions token to update its data branch and deploy Pages. Branch rules or account restrictions can require an owner setting change. All source errors are visible in the dashboard log even when the site itself deploys successfully.

## Run locally

Python 3.12+ on Linux/macOS, with the OpenAI Python client required only for optional Groq extraction:

```sh
python scripts/run.py --build-only
python -m http.server 8080 --directory output
```

This produces a valid empty dashboard without collecting. To collect once using the same local cooldown:

```sh
python scripts/run.py
```

Do not run independent live collectors simultaneously on a local machine and GitHub. Separate state directories cannot share a cooldown. The GitHub deployment is the authoritative collector.

## Tests

```sh
python -m unittest discover -s tests -v
npm ci
npm run test:ui
```

Node 24/jsdom is used only for UI tests. Tests use local fixtures, never live sources. The Python suite checks feed validation, persistent cooldown, source backoff, address and county matching, ambiguity, incident grouping, conflicts, missing values and failed remote reservations. The UI test checks case/report totals, red/yellow pins, grouped sources, review exclusion and filtering.

## Reviewed corrections

`config.json` supports explicit reviewed case membership:

```json
{"id":"reviewed-case-001","report_ids":["REPORT_ID_1","REPORT_ID_2"],"date":"2026-09-26","state":"TX","reason":"Sources reviewed and confirmed to describe the same incident"}
```

Put entries in `overrides`. Each listed report is assigned once to that reviewed case on the next build. Use separate entries to split an incorrect grouping. Keep the reason specific and verify source evidence before overriding. Report IDs are available in the published JSON and database. Never use overrides to manufacture evidence or inflate totals.

## Files

- `src/collector.py`: bounded RSS/publisher collection, storage, summaries and export
- `src/incidents.py`: evidence extraction, grouping and reviewed corrections
- `src/locations.py`: conservative Census location matching and address lookup
- `scripts/run.py`: durable reservation, state branch and static build
- `site/`: responsive single-page dashboard and local map libraries/assets
- `reference/`: Census geographic reference data
- `.github/workflows/`: scheduled collection, publishing and tests

News belongs to its publishers. Geographic and library notices are in THIRD_PARTY.md. Original project code is available under the MIT license (LICENSE). Third-party assets retain their notices and terms; news articles are not relicensed.

## News desk and relevance review

The default feed is a bounded, scrollable news desk with headline, source excerpt (or explicitly labelled headline-only brief), and source links. Identical headlines on the same publication day are grouped for reading only; incident matching remains separate. The map sidebar summarizes report coverage, publishers and location confidence without turning publication dates into incident dates.

See [REVIEW.md](REVIEW.md) and [NEWS_REVIEW.json](NEWS_REVIEW.json) for the initial 99-record relevance review. The Google News query now uses explicit gun-event phrases and exclusions. US edition settings alone do not prove US incident geography; unknown locations stay unresolved. Filters cannot guarantee exhaustive or error-free coverage.

## Direct Google News search

RSS sources remain enabled. A fourth source makes one direct HTTPS request to the user-supplied Google search query (`tbm=nws`, English, US region, date sorting, `qdr:h1` last-hour window). Tracking/session/display parameters are removed; search terms and functional filters are preserved. The broad phrases “developing story” and “deputies say” can match unrelated news, so the same gun-event relevance filter applies after parsing. Region settings do not prove incident geography.

The HTML parser accepts recognizable headline cards, publisher links and available snippets. Search snippets are labelled separately from publisher excerpts. Unsupported markup, JavaScript-only pages, consent screens and challenges are logged as errors, never an empty successful feed. There is no Selenium, page execution, pagination, retry, proxy rotation or challenge bypass. The shared durable 30-minute reservation applies to every source; 403/429/503 and challenge responses trigger backoff. RSS results continue when direct search fails. Missing search publication dates remain unknown.

Redirect errors report only the destination host and a recognized route (such as `/sorry/`); query strings and arbitrary paths are omitted. Redirects are not followed. The last-hour search window filters search results, not the dashboard archive or the actual incident date. RSS retains its existing coverage window.

## AI setup and location confidence

Optional provider: Groq, model: `openai/gpt-oss-20b` (Apache 2.0 model license). The provider has separate account terms and quotas. Create an account at https://console.groq.com and store the key only in the repository Actions secret `GROQ_API_KEY`. Never put it in config.json, Pages, logs or the state branch. Missing credentials are logged as `waiting for GROQ_API_KEY`; RSS and offline location matching continue.

At most four uncached records are processed per eligible collection; identical inputs are cached across sources. Any provider or validation failure stops AI for the run with a one-hour backoff and no automatic retries. Only the public headline and available bounded source excerpt are sent. Summary sentences must occur verbatim in the excerpt. Place evidence must occur in the source; ambiguous place names need explicit source state evidence. Coordinates come from Census, never the model. This reduces invented facts but does not independently verify the incident.

AI cannot fetch inaccessible articles or invent missing details. Headline-only records remain labelled. A city can be mapped approximately even when event time or casualties are unknown. Existing records are reprocessed without new publisher requests.

Documentation: https://console.groq.com/docs/model/openai/gpt-oss-20b and https://console.groq.com/docs/structured-outputs . Model license: https://github.com/openai/gpt-oss/blob/main/LICENSE .


## Interactive coverage release
The default analytics now count distinct news stories by publication date, with day/state/publisher filtering. They do not claim to count all incidents or victims. The Leaflet street map uses real geographic coordinates and zooms to level 19; zoom never upgrades the precision of an approximate city/county/state point. Click pins for source links. The sidebar contains location counts above publisher counts. The CDC 2014–2024 panel provides separately labelled annual mortality context.

Publisher reads: up to five public HTTPS links per eligible run, robots-aware, at most two validated redirects, no challenge/paywall bypass, and no video transcription. JSON-LD articleBody or main/article paragraphs provide text. Private IPs, credentials in URLs, non-HTTPS links, videos and Google aggregator links are rejected. Source availability is recorded per report. Only bounded text is retained; not every news link provides a readable article.

Briefs follow casualty → source event time → street/area/city/county/state, followed by a source-quoted public-safety update where available. With no incident time reference, they begin with the source publication date/time explicitly labelled as publication. Missing quantities and details remain unknown. AI evidence must occur in the input; formatted briefs are assembled from extracted facts, not free-form invented descriptions.

AI: at most four new requests per run, forty per UTC day, forty-second pacing, cached by input and model version. These caps are not a billing-plan detector. Free accounts remain subject to provider quotas; paid accounts may incur usage fees. This project does not upgrade plans or supply payment information.

Run workflow with `enrich_only` checked to process stored reports and rebuild Pages without querying news feeds or Google. It has a separate 30-minute durable reservation and honors AI backoff. Push events build from saved data only. Scheduled collection preserves its existing cooldown.


### September 27 follow-up
Groq now uses the official OpenAI Python client with Groq's Responses API, no automatic retries, at most four article extractions/run and 40/day. Install `pip install -r scripts/requirements.txt`. Headline-only entries do not spend model calls. A single SDK compatibility check is allowed on migration from the original failed client; subsequent errors retain the one-hour backoff. API status and extraction diagnostics are excluded from the published dashboard JSON.

Publisher articles: direct links are read subject to robots and access restrictions. For aggregator links, publisher homepage/RSS discovery uses an exact headline match and cached results; newly collected RSS records preserve publisher home URLs. This cannot resolve every opaque aggregator link. User-provided article excerpts may be recorded with explicit provenance in `reference/source-supplements.json`; these are never represented as automated fetches. Cleveland + WKYC uses a labelled publisher-context inference for the approximate Ohio city center; generic ambiguous city names remain unpinned.

The incident watchlist shows located news stories with source-supported incident dates/casualties and map navigation. It does not equate story counts with verified incidents. Identical-headline grouping chooses the newest publication timestamp. The browser refreshes saved news each minute; Actions collection is scheduled twice hourly, subject to GitHub scheduling delays and source backoff.

CDC data is checked once daily during collection/enrichment, validated for all 50 states plus DC, cached persistently and published automatically. Later complete annual releases appear without code edits. Missing/partial years are not invented; retrieval errors retain the previous valid snapshot.
