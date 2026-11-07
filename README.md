# Currency_exchange — Waypoint

A completed local currency/reference-rate and travel-budget planning website. The existing public Currency_exchange repository was empty when inspected; no old code was overwritten or fabricated as a historical implementation.

## Product scope

- Nine supported fiat currencies: USD, EUR, INR, GBP, JPY, AUD, CAD, SGD and CHF.
- Conversion with percentage/fixed fees deducted from the source amount.
- A multi-line travel budget with an aggregate fee and visible gross line-item conversions.
- Persistent recent calculations with source and rate date on every result.
- An explicit fictional demo mode, plus an optional no-key Frankfurter reference-rate adapter.
- Live-cache/stale warnings and **no silent fallback to made-up rates**.

## Architecture

```text
Browser form → validate currency/decimal/fee input
 → explicit demo OR fixed Frankfurter reference endpoint
 → dated rate + source + stale flag
 → Decimal conversion and target rounding
 → SQLite history → receipt and budget breakdown
```

### Decimal arithmetic and fee model

Amounts are plain decimal strings without commas, signs or exponents, at most six fractional places and bounded in size. NaN/Infinity, negative/zero amounts and unsupported currencies are rejected. Percentage fee is 0–20%; fixed fee is expressed in the source currency. Total fees must be below the amount.

fee = source_amount × fee_percent / 100 + fixed_fee

net_source = source_amount − fee

converted = round_half_up(net_source × reference_rate, target_minor_unit)

JPY rounds to zero decimals; other supported currencies round to two. Decimal is used for conversion/fees, not binary floating-point money arithmetic. A budget sums its source line items first and applies one aggregate fee. Individual budget rows show gross converted amounts and can differ from the net receipt total; the UI labels that distinction.

### Rate modes and provenance

**Demo:** hard-coded fictional ratios dated 2026-01-02, visibly labeled FICTIONAL DEMO. They are not downloaded data, not current quotes and not suitable for decisions. The demonstration is usable without network access.

**Reference:** server-side requests only to the documented fixed Frankfurter v2 pair route. Official documentation: https://frankfurter.dev. Endpoint shape is /v2/rate/{base}/{quote}; responses contain date, base, quote and rate. No key is required. A provider response was inspected separately during development, but the application’s network adapter was tested with mocks because sandbox outbound networking was unavailable.

A fresh local rate cache is reused for up to one hour. Provider failure can return an existing rate with an explicit stale-cache source/warning; with no cache, conversion fails clearly. It never switches live mode to fictional demo data. A rate observation older than four days is marked stale. Rates may update daily and not match bank execution, spreads or holidays. Same-currency conversion uses the mathematical identity rate 1 and needs no external quote.

### Storage model

| Table | Contents |
|---|---|
| cache | pair primary key, exact rate text, rate observation date and fetched timestamp |
| history | source/target, exact input/output strings, rate/date/source and calculation timestamp |

The API returns at most the last 12 calculations; the compact UI displays six. No wallet balance, bank token, payment card or actual transaction is stored. The local database is shared by this server’s visitors and is not an authenticated financial account.

## API examples

```json
{"action":"convert","amount":"100","base":"USD","quote":"INR","mode":"demo","fee_percent":"2","fixed_fee":"1"}
```

```json
{"action":"budget","base":"USD","quote":"INR","mode":"demo","items":[{"name":"Stay","amount":"400"},{"name":"Food","amount":"180"}],"fee_percent":"1.5","fixed_fee":"0"}
```

GET /api returns supported currencies and history. POST actions convert/budget return a result receipt and updated history. Results include rate, rate_date, source, stale, fee_source, net_source, converted, gross_converted and optional breakdown. Budgets require 1–20 named items. Failed updates leave the last successful receipt explicitly labeled as not refreshed.

## Test matrix

Tests cover demo-source honesty, exact decimal behavior, fees, identity conversion, JPY rounding, invalid/exponent/non-finite input, unsupported currencies, excessive fees, budget aggregation, persistence, no fake live fallback, full-precision caching, stale-cache behavior, provider pair validation and five HTTP guards. Desktop/mobile browser checks cover initial/empty state, conversion, budget bars, validation errors and reload persistence.

## Safety and extension roadmap

This is not financial advice, rate forecasting, a live trading terminal or a money-transfer service. Fees are user-entered estimates. It does not compare actual bank quotes or promise the amount a recipient will receive. No AI financial adviser is invented just to add an AI label.

Future work, not implemented: provider-supported historical charts, an explicit multi-provider comparison policy, date/time-zone alignment, localized amount input, additional currency minor units and authenticated private history with retention/deletion controls. Any real transfer/payment feature requires a separately designed regulated provider integration and security/compliance review.

## Local setup and file map

Requires Python 3.11+; no pip/npm dependencies, API keys or Docker are required for default local operation.

```bash
python server.py --port 8000
python -m unittest discover -s tests -v
```

Open http://127.0.0.1:8000. Do not open index.html directly: the browser calls the same-origin Python API. Use another --port if occupied. Tests use temporary SQLite files and synthetic data.

| File | Responsibility |
|---|---|
| index.html / styles.css | Responsive accessible website structure and presentation |
| app.js | Browser events, safe DOM text rendering, same-origin API client |
| core.py | Domain logic, validation and persistent state |
| server.py | Loopback HTTP transport and bounded JSON/static routing |
| tests/test_core.py | Domain algorithms, invalid input, persistence and mocked provider checks |
| tests/test_http.py | Origin/header/JSON/static-path guard checks |
| .github/workflows/tests.yml | Reviewable CI configuration; not proof it has run remotely |

## HTTP contract and safety

GET /health returns liveness JSON. GET /api returns the local catalog/configuration/history. POST /api accepts one JSON action and requires Content-Type: application/json and X-Local-Client: 1. Foreign Origin or untrusted Host is rejected. The server defaults to 127.0.0.1 and serves only explicit static paths; runtime .data files are never a static route.

This is a single-user **local reference app**, not a public authenticated service. Host/Origin checks do not replace login, authorization, TLS, rate limiting or CSRF/abuse review for a real internet deployment. No shell strings are executed. Frontend user/provider strings use textContent, not innerHTML.

Runtime data persists in .data/app.sqlite3 unless PROJECT_DB is set. Back up before resets. Do not commit databases, real user records, logs or environment files. SQLite concurrency is a local-machine design choice, not a cross-region scaling plan.

## Verification and deployment boundary

The domain and HTTP suite passed 20 tests locally on Python 3.13.15. Desktop 1440px and mobile 390px Chromium workflows verified successful, empty/error and persistence states. No public deployment or GitHub push was possible from the build sandbox; no remote Actions run is claimed. Python 3.11 is a compatibility target, not a locally executed version.

Use publish.sh only after review and restored network/GitHub access. It creates a separate completed-web-app branch rather than overwriting the existing main history. The website needs its Python backend; uploading only these HTML files to static hosting will not make the API work. No paid cloud service is configured or required by this package.

## Troubleshooting

- **API unavailable:** start server.py and visit its HTTP URL; file:// and static-only hosting do not provide /api.
- **Port occupied:** choose a different --port and open that address.
- **Old local data:** verify PROJECT_DB, stop the server, back up and deliberately reset only the intended .data folder.
- **Validation error:** read the inline message; a failed request is not a saved successful result.
- **Provider/network unavailable:** default offline functionality remains available and explicitly labeled; never treat a fixture as current external data.
