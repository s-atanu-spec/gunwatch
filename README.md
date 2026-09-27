# GunWatch

A lightweight US gun-violence news tracker with source-linked summaries, incident grouping, location confidence and case-based analytics. Built with Python, SQLite and plain JavaScript, with Codex assistance.

**The whole deployment runs on GitHub:** Actions collects and processes news; a dedicated `collector-state` branch persists the SQLite database and cooldown; Pages serves the dashboard. No PHP host, browser automation, paid map service or AI API key is needed.

## What the numbers mean

The primary analytics count **tracked cases**, not articles. Multiple matching reports attach to one case, retaining all source links. Reports without enough evidence to identify or safely compare an incident remain in **Unresolved reports**, outside the case count. Consequently these are conservative, incomplete news-derived counts, not comprehensive or independently verified official statistics.

Automatic duplicate matching requires:

- The same normalized street/address or block and city/county/state context.
- The same source-supported incident date.
- Reported local times within 30 minutes.
- Matching explicitly reported casualty fields. Unknown counts stay unknown, never zero.

All members of a group must match each other, preventing a chain of overlapping time windows from merging unrelated incidents. Different casualty figures, ambiguous matches and missing inputs are not automatically merged. Evolving casualty counts can therefore create separate candidate cases until reviewed. Matching uses source text and rules, not identity guesses from a language model.

The month-to-date chart uses incident dates; publication times never become incident times. The dashboard's reporting calendar is America/New_York. Explicit local times remain as written in the source. Relative dates such as Friday are anchored to publication in that calendar, which can be uncertain around midnight for western states. The evidence is visible for review.

## Location finder

- Bundled Census data covers US cities, towns, Census-designated places, counties and state centers.
- Matches explicit city/state and county/state pairs; distinctive unambiguous city names can also be resolved.
- Extracts numbered street addresses, block descriptions, named streets and named areas. A neighborhood with no verified coordinates inherits its supported city/county area, not invented coordinates.
- Makes at most five uncached US Census address requests per accepted collection. Results, including failures, are cached. No key required.
- **Red pins:** a Census address match. Coordinates are interpolated along an address range, not a verified incident scene.
- **Yellow pins:** an approximate city, county or state center. The location evidence explains the precision.
- No defensible geographic area means no pin. Ambiguous street names or multiple locations are not resolved arbitrarily.

The current-day map uses incident dates from counted cases. Unresolved reports remain in the feed even when they cannot be placed on that map. See [Census API documentation](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html).

## Summaries and sources

The default sources are Google News US search, CBS News US and NPR National RSS. Source coverage and availability vary; a US feed edition does not guarantee that every returned report is domestic. Cases require a matched US location.

RSS descriptions supply short, extractive summaries. For supported publisher URLs, the collector can read structured article text when robots.txt permits it. This is bounded to five new or changed articles per run, with no redirects, retries, login or paywall bypass. Only short excerpts and extraction evidence are retained; full article bodies are not stored or published. Aggregator link lists are not presented as summaries. When no usable text is available, the card clearly says **headline only**.

No language model or borrowed API key is used. This avoids free-tier quotas and hallucinated locations or casualty figures. Source availability can still prevent a complete summary or incident match.

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

No external secret or API key is required. The job uses the repository-scoped, temporary GitHub Actions token to update its data branch and deploy Pages. Branch rules or account restrictions can require an owner setting change. All source errors are visible in the dashboard log even when the site itself deploys successfully.

## Run locally

Python 3.12+ on Linux/macOS, using only the standard library:

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

News belongs to its publishers. Geographic and library notices are in THIRD_PARTY.md. No general software reuse license has been selected for this project yet.
