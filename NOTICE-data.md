# Data provenance, and a caution about republishing it

## Where every number came from

| Field | Source | Collected |
|---|---|---|
| Price, market cap, trailing P/E, trailing revenue, 1y/5y/10y annualised total return | StockAnalysis.com stock comparison tool | 12 Oct 2026 |
| Consensus revenue and EPS (current + next fiscal year), reported revenue / net income / gross margin history, 12-month analyst price target, consensus rating, analyst count | StockAnalysis.com per-company forecast pages | 12 Oct 2026 |
| Index membership (S&P 500, Nasdaq-100) and GICS sector labels | Wikipedia "List of S&P 500 companies" and "List of Nasdaq-100 companies" | 12 Oct 2026 |

StockAnalysis.com attributes its consensus estimates and price targets to **S&P Global Market
Intelligence** and its individual analyst data to **TipRanks**. Neither Anthropic, the author of this
repository, nor StockAnalysis.com originated those estimates.

Everything in `data/derived/` is arithmetic on the two raw inputs. No other data was used — no
alternative data, no proprietary feeds, and no figures taken from the author's or a model's own
recollection.

## Accuracy

Collection was mechanical transcription from rendered pages into the pipe-delimited formats
documented in the README. A random sample of returned rows was re-fetched independently and compared
field by field; the sampled rows matched at 48/48 fields. That is evidence of faithful transcription,
not a guarantee of correctness across all 516 rows, and it says nothing about whether the underlying
figures are right.

Known data artefacts that survived into `data/raw/`, handled in `src/model.py` rather than edited at
source so the raw files stay faithful to what was published:

- **`BRK.B`** — the forecast page reports Berkshire's **Class A** EPS (~32,580). Class B is 1/1500th.
  Corrected in the model; the raw file keeps the published figure.
- **Banks** (`BAC`, `JPM`, `C`, `WFC`, `USB`, `PNC`, `TFC`, and ~11 others) — only two years of
  revenue history, because the source changed its revenue presentation for the sector. Trailing CAGR
  is therefore `null` for them.
- **Structural breaks** — 57 year-on-year moves larger than ±35–80% are genuine corporate actions,
  not errors: the Honeywell split (`HON` / `HONA`), Corteva's spin (`CTVA`), FedEx Freight (`FDXF`),
  Qnity (`Q`), accounting-basis changes at `APO` / `KKR` / `CBOE`, and gross-to-net revenue
  restatements at `MAR` / `HLT`. The model anchors on consensus rather than on extrapolated history,
  so these affect the `cagr_hist` column only.
- **`ERIE`, `L`, `NWS`** — no forecast data published; excluded from the forward model.

## The caution

**The files in `data/raw/` and `data/derived/` are a redistribution of a third party's data.**

StockAnalysis.com's terms of use, and the S&P Global Market Intelligence licence that sits behind its
consensus estimates, very likely restrict republication of that data — bulk extraction and
redistribution are commonly prohibited outright, regardless of whether the original access was free.
Publishing this directory in a public repository may breach those terms.

This is not legal advice, and the position depends on the current terms and on your jurisdiction and
purpose. Please check before you push.

### The low-risk shape for a public repo

Publish the code and documentation; keep the data private.

```bash
git rm -r --cached data/raw data/derived
printf 'data/raw/\ndata/derived/\n' >> .gitignore
```

The raw file formats are documented in the README, so anyone can repopulate them from a source they
are licensed to use and run `make` to reproduce every number and chart. The pipeline is deterministic
and needs no network access.

If you do publish the data, attribute StockAnalysis.com, S&P Global Market Intelligence and TipRanks
explicitly, state the as-of date, and keep the limitations section of the README intact — the figures
are easy to misread without it.

## Licensing summary

- **Code** (`src/`, `test/`, `Makefile`) — MIT, see `LICENSE`.
- **Documentation and charts** (`README.md`, `docs/`, slide copy) — MIT, same terms.
- **Market data** (`data/`) — **not** covered by the MIT licence. Rights belong to the original
  sources named above.
