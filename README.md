# Taskmarket, flowing

A live, read-only view of [Taskmarket](https://taskmarket.dev)'s market data: money put up against money actually paid out, where open work piles up, who posts, when the swarm moves, and what the price of attention looks like.

**Live:** https://nicolasesanchez50.github.io/taskmarket-live-visualizer/

Built for a paid Taskmarket bounty. **Not an official Taskmarket product.**

---

## The one idea

Every Taskmarket dashboard draws the same shape: bars of tasks over time. This one is arranged around a single question the standard charts cannot answer — **where does the money stop?** Reward volume put up is drawn against reward volume released, per day, so the vertical gap between the two lines *is* escrow sitting still. The second view does the same for work rather than money: each posting week is stacked by what happened to the tasks, so cancelled and expired show up as visible mass instead of disappearing from the totals.

## What it shows

- **Headline numbers** — open tasks, registered workers, weekly actives, on-chain wallets, and all-time reward value released.
- **Money put up vs paid out** — daily, both chains summed, with range switches for 7d / 30d / 90d / all.
- **The leak** — every task in the snapshot bucketed by its posting week and split by outcome (open / completed / cancelled / expired), with the "never landed" share computed from those counts.
- **Who posts** — distinct task posters per ISO week, computed from the task list's `requester` field. Peaks are labelled.
- **When the swarm moves** — activity heatmap, weekday × hour UTC, 30 days.
- **Price of attention** — open tasks plotted as reward (log scale) against submissions already received. Tasks with zero submissions are highlighted; they are where money is still uncontested.
- **Right now** — the live activity feed.
- **The ledger of open work** — highest-reward open tasks with current submission counts.

## How the data gets here

The Taskmarket API refuses cross-origin browser requests, so the page never calls it. A GitHub Actions workflow runs `scripts/fetch.py` **hourly on the server**, writes `site/data.json`, and publishes `site/` to GitHub Pages. The browser only ever fetches its own `data.json`.

Everything on the page is either copied verbatim from an API response or arithmetic on those responses. Nothing is estimated, extrapolated or invented. Reward volumes arrive in base units (6 decimals) and are divided by 1,000,000.

Endpoints used:

```
/api/market/stats?chainId={4217,8453}
/api/stats/breakdowns?chainId={4217,8453}
/api/stats/platform-time-series?chainId={4217,8453}&range=7d|30d|90d|all&bucket=day|week
/api/stats/activity-heatmap?chainId={4217,8453}&range=7d|30d&dimension=mode|hourOfWeek
/api/stats/activity-feed?chainId={4217,8453}&limit=40
/api/tasks?chainId={4217,8453}&sort=newest&limit=100   (cursor-paginated to exhaustion)
```

### One honest limitation

The API currently returns **identical** `market/stats`, `breakdowns` and `platform-time-series` payloads for chain 4217 and 8453; only the task lists and activity feeds differ per chain. The page reports both chains and says so in its methods note rather than presenting the duplicate as two independent series. When the API starts separating them, no code change is needed.

## Run it locally

```bash
python3 scripts/fetch.py          # writes site/data.json from the live API
python3 -m http.server -d site 8080
# open http://localhost:8080
```

No dependencies beyond the Python standard library (`scripts/share.py` and `scripts/verify.py` additionally use Pillow and headless Chrome).

## Deploy it yourself

One command:

```bash
bash deploy.sh <your-github-owner>/<repo>
```

It refreshes the snapshot, commits, pushes, and turns on Pages with the workflow as the source. The hourly refresh and redeploy is then handled by `.github/workflows/deploy.yml`; nothing else to run.

Manual equivalent:

```bash
gh repo create <owner>/<repo> --public --source=. --push
gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow
```

## Verification

```bash
python3 scripts/verify.py     # headless-Chrome assertions, exit 0 = pass
```

It asserts, against a real render: the page's own "data as of" stamp matches `data.json`'s `read_at` (proving the fetch and render completed), KPI numbers are in the DOM, every chart container is non-empty, the leak and feed rows exist, and a phone-width screenshot is produced and is not blank.

`scripts/share.py` renders the 1200×630 share card from the same snapshot, so the card's figures cannot drift from the page's.

## Design

Follows the Taskmarket brand kit: ground `#12100E`, maroon glow, panel `#221E1A`, cream `#EFE9E2`, one magenta `#E74079` accent per piece; Instrument Serif for headlines, Inter Tight for body, Departure Mono for numbers and addresses. Chart series use two additional hues (salmon for money put up, cyan for money paid out) chosen to sit inside the kit's warm-dark palette without competing with the accent.

## Rules the build respects

- **Read-only.** No wallet connection, no cookies, no analytics, no third-party scripts, no personal-data collection. The only network request the page makes is for its own `data.json`.
- **No guessed identities.** Poster counts are distinct `requester` addresses; no wallet is ever named, labelled or attributed to a person or organisation.
- **Every number reproducible** from the endpoints listed above.
- **MIT licensed**, deployable in one command, so Taskmarket can host it itself at any time.
- Footer states it was made for a paid Taskmarket bounty and is not an official Taskmarket product.
- No third-party logos, no invented numbers.

## Layout

```
site/            the published site (static; what Pages serves)
  index.html     the page
  data.json      hourly server-side snapshot
  fonts/         brand fonts + lockup, with their OFL licences
  share/og.png   the 1200x630 share card
scripts/fetch.py the server-side fetch (stdlib only)
scripts/verify.py headless-Chrome render assertions
scripts/share.py share-card renderer
share.html       share-card template
deploy.sh        one-command deploy
```
