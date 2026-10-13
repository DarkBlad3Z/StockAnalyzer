#!/usr/bin/env python3
"""
Stage 1 - today's snapshot.

Reads the quote pulls in data/raw/quotes_*.psv, derives trailing net income and
net margin, ranks every company against the universe and against its own sector,
and writes data/derived/today.json for the deck plus data/derived/value_vs_quality.csv.

Net income is recovered exactly from market cap / trailing P/E:
    P/E = price / EPS,  so  mcap / (P/E) = shares * price / (price / EPS) = shares * EPS
Net margin is that figure over trailing revenue.

No network access. Pure standard library.
"""
import csv
import json
import os
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "derived")

SECTORS = {
    "IT": "Information Technology", "CS": "Communication Services",
    "CD": "Consumer Discretionary", "CST": "Consumer Staples",
    "FIN": "Financials", "HC": "Health Care", "ENE": "Energy",
    "IND": "Industrials", "MAT": "Materials", "RE": "Real Estate",
    "UTL": "Utilities",
}
INDEXES = {"sp": "S&P 500", "ndx": "Nasdaq-100", "both": "S&P 500 + Nasdaq-100"}


def num(s):
    s = (s or "").strip()
    if s in ("", "NA", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_quotes():
    rows = []
    for i in range(1, 5):
        path = os.path.join(RAW, "quotes_%02d.psv" % i)
        with open(path) as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip() or line.startswith("ticker|"):
                    continue
                f = (line.split("|") + [""] * 10)[:10]
                rows.append(dict(
                    ticker=f[0], name=f[1], sec=f[2], idx=f[3],
                    mcap=num(f[4]), pe=num(f[5]), rev=num(f[6]),
                    r1=num(f[7]), r5=num(f[8]), r10=num(f[9])))
    return rows


def pct_ranks(vals):
    """Percentile rank 0-100; ties share the midpoint of their block."""
    s = sorted(vals)
    n = len(s)
    out = []
    for v in vals:
        lo = sum(1 for x in s if x < v)
        eq = sum(1 for x in s if x == v)
        out.append(100.0 * (lo + 0.5 * eq) / n)
    return out


def main():
    rows = load_quotes()
    tickers = [r["ticker"] for r in rows]
    assert len(tickers) == len(set(tickers)), "duplicate tickers in the quote files"
    bad = [r["ticker"] for r in rows if r["sec"] not in SECTORS]
    assert not bad, "unknown sector code for %s" % bad

    usable, excluded = [], []
    for r in rows:
        if r["pe"] and r["pe"] > 0 and r["rev"] and r["rev"] > 0 and r["mcap"]:
            r["ni"] = r["mcap"] / r["pe"]
            r["margin"] = 100.0 * r["ni"] / r["rev"]
            r["ey"] = 100.0 / r["pe"]
            r["ps"] = r["mcap"] / r["rev"]
            usable.append(r)
        else:
            reason = ("no trailing earnings (negative or unavailable)"
                      if not (r["pe"] and r["pe"] > 0) else "no revenue figure")
            excluded.append(dict(ticker=r["ticker"], name=r["name"],
                                 sec=r["sec"], mcap=r["mcap"], reason=reason))

    for r, p in zip(usable, pct_ranks([x["margin"] for x in usable])):
        r["qpct"] = round(p, 1)
    for r, p in zip(usable, pct_ranks([x["pe"] for x in usable])):
        r["pepct"] = round(p, 1)

    for code in SECTORS:
        grp = [r for r in usable if r["sec"] == code]
        if len(grp) < 3:
            for r in grp:
                r["qpct_s"] = r["pepct_s"] = 50.0
            continue
        for r, p in zip(grp, pct_ranks([g["margin"] for g in grp])):
            r["qpct_s"] = round(p, 1)
        for r, p in zip(grp, pct_ranks([g["pe"] for g in grp])):
            r["pepct_s"] = round(p, 1)

    med_pe = statistics.median([r["pe"] for r in usable])
    med_mg = statistics.median([r["margin"] for r in usable])

    sector_stats = []
    for code, label in SECTORS.items():
        g = [r for r in usable if r["sec"] == code]
        if not g:
            continue
        sector_stats.append(dict(
            code=code, label=label, n=len(g),
            med_pe=round(statistics.median([x["pe"] for x in g]), 1),
            med_margin=round(statistics.median([x["margin"] for x in g]), 1),
            mcap=round(sum(x["mcap"] for x in g) / 1000, 2)))
    sector_stats.sort(key=lambda s: -s["mcap"])

    os.makedirs(OUT, exist_ok=True)
    payload = dict(
        asof=ASOF, medianPE=round(med_pe, 2), medianMargin=round(med_mg, 2),
        sectors=SECTORS, sectorStats=sector_stats,
        excluded=sorted(excluded, key=lambda e: -(e["mcap"] or 0)),
        stocks=[dict(
            t=r["ticker"], n=r["name"], s=r["sec"], i=r["idx"],
            mc=round(r["mcap"], 2), pe=round(r["pe"], 2), rev=round(r["rev"], 2),
            ni=round(r["ni"], 2), mg=round(r["margin"], 2), ey=round(r["ey"], 2),
            ps=round(r["ps"], 2), q=r["qpct"], pp=r["pepct"],
            qs=r["qpct_s"], pps=r["pepct_s"],
            r1=r["r1"], r5=r["r5"], r10=r["r10"]) for r in usable])
    with open(os.path.join(OUT, "today.json"), "w") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    with open(os.path.join(OUT, "value_vs_quality.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "company", "gics_sector", "index_membership",
                    "market_cap_usd_b", "trailing_pe", "revenue_ttm_usd_b",
                    "net_income_ttm_usd_b", "net_margin_pct", "earnings_yield_pct",
                    "price_to_sales", "margin_percentile_all", "pe_percentile_all",
                    "margin_percentile_in_sector", "pe_percentile_in_sector",
                    "total_return_1y_pct", "total_return_5y_ann_pct",
                    "total_return_10y_ann_pct", "quadrant"])
        for r in sorted(usable, key=lambda x: -x["mcap"]):
            q = ("Best value" if r["pe"] < med_pe and r["qpct"] > 50 else
                 "Premium" if r["qpct"] > 50 else
                 "Budget" if r["pe"] < med_pe else "Poor value")
            w.writerow([r["ticker"], r["name"], SECTORS[r["sec"]], INDEXES[r["idx"]],
                        r["mcap"], r["pe"], r["rev"], round(r["ni"], 2),
                        round(r["margin"], 2), round(r["ey"], 2), round(r["ps"], 2),
                        r["qpct"], r["pepct"], r["qpct_s"], r["pepct_s"],
                        r["r1"], r["r5"], r["r10"], q])
        for e in sorted(excluded, key=lambda x: -(x["mcap"] or 0)):
            w.writerow([e["ticker"], e["name"], SECTORS[e["sec"]], "",
                        e["mcap"] if e["mcap"] is not None else ""]
                       + [""] * 13 + ["excluded: " + e["reason"]])

    print("quotes parsed      : %d" % len(rows))
    print("plotted            : %d" % len(usable))
    print("excluded           : %d (%s)" % (
        len(excluded), ", ".join(e["ticker"] for e in excluded)))
    print("median trailing P/E: %.2f" % med_pe)
    print("median net margin  : %.2f%%" % med_mg)
    print("wrote              : data/derived/today.json, data/derived/value_vs_quality.csv")


ASOF = "2026-10-12"

if __name__ == "__main__":
    main()
