# Validation status

Local validation on 27 September 2026:

- 30 Python tests passed for extraction, city/county/area/street matching, ambiguity, duplicate grouping, casualty conflicts, unknown values, date/time handling, source backoff, failed remote reservations and persistence.
- Frontend behavior tests passed for separate case/report counts, grouped sources, red/yellow pins, unresolved-report exclusion, state filtering and static refresh.
- A static build completed successfully without external requests. Production Python uses only the standard library.
- Source files contain no private account files, credentials or company branding. Runtime databases and test output are excluded from the release.

Deployment status:

- The public repository `s-atanu-spec/gunwatch` was created with its initial README.
- Upload through the connected GitHub app failed for both blob and contents operations with HTTP 403, "Resource not accessible by integration".
- GitHub Pages was configured to deploy through GitHub Actions.
- The complete source has not yet been uploaded, the workflows have not run on GitHub, and no deployed dashboard URL has been verified.
- Live source collection and geocoding have not been verified for this release. Earlier Google News testing returned HTTP 503. Offline tests cannot establish live availability.
- Full browser layout validation remains pending deployment.

The implementation is designed for a fully GitHub-hosted deployment, but that deployment is not yet live. Source-derived incident counts are intentionally conservative and incomplete; ambiguous reports remain separate for review.
