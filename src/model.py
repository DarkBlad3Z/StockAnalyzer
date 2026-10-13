#!/usr/bin/env python3
"""
Stage 2 - the forward model to 2030 and 2035.

Reads data/raw/quotes_*.psv and data/raw/forecast_*.psv and writes
data/derived/forward.json plus data/derived/forward_2030_2035.csv.

WHAT IS DATA AND WHAT IS ASSUMPTION
-----------------------------------
Data:        five to six years of reported revenue, net income and gross margin per
             company, plus S&P Global consensus revenue and EPS for the current and
             next fiscal year, and the 12-month analyst price target.
Assumption:  everything past next fiscal year. No consensus revenue estimate exists
             for 2035 for any of these companies, anywhere. The four knobs below are
             the entire forecast.

THE FOUR KNOBS (edit SCENARIOS and rerun)
-----------------------------------------
gT    terminal nominal revenue growth the fade converges to
lam   annual persistence of the excess growth: g_next = gT + (g - gT) * lam
cap   ceiling on the starting growth rate taken from consensus
mfac  multiplier applied to the net margin by 2035, phased in linearly
xf    scaling of the exit multiple

Margins are held FLAT in the base case. An earlier version mean-reverted them
toward sector medians; that made McKesson's 1.1% distributor margin drift toward
the 12.3% Health Care median, quintupling its earnings and ranking it as one of the
cheapest large caps in the market. That was an artefact of the assumption, not a
finding, so the base case no longer does it.

No network access. Pure standard library.
"""
import csv
import json
import os
import re
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "derived")

ASOF = "2026-10-12"

SECTORS = {
    "IT": "Information Technology", "CS": "Communication Services",
    "CD": "Consumer Discretionary", "CST": "Consumer Staples",
    "FIN": "Financials", "HC": "Health Care", "ENE": "Energy",
    "IND": "Industrials", "MAT": "Materials", "RE": "Real Estate",
    "UTL": "Utilities",
}
INDEXES = {"sp": "S&P 500", "ndx": "Nasdaq-100", "both": "S&P 500 + Nasdaq-100"}

SCENARIOS = {
    "bear": dict(gT=0.030, lam=0.55, cap=0.20, mfac=0.85, xf=0.80),
    "base": dict(gT=0.045, lam=0.72, cap=0.35, mfac=1.00, xf=1.00),
    "bull": dict(gT=0.060, lam=0.85, cap=0.50, mfac=1.15, xf=1.25),
}

BASE_YEAR = 2026          # "today"
ANCHOR_YEAR = 2027        # consensus "revenue next year" is treated as this year
HORIZONS = {2030: 4, 2035: 9}
REQUIRED_RETURN = 0.08    # hurdle the inversion is solved against


def num(s):
    s = (s or "").strip()
    if s in ("", "NA", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load():
    base = {}
    for i in range(1, 5):
        with open(os.path.join(RAW, "quotes_%02d.psv" % i)) as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip() or line.startswith("ticker|"):
                    continue
                f = (line.split("|") + [""] * 10)[:10]
                base[f[0]] = dict(t=f[0], name=f[1], sec=f[2], idx=f[3],
                                  mc=num(f[4]), pe=num(f[5]), rev=num(f[6]),
                                  r1=num(f[7]), r5=num(f[8]), r10=num(f[9]))
    for i in range(1, 5):
        with open(os.path.join(RAW, "forecast_%02d.psv" % i)) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                f = line.split("|")
                assert len(f) == 12, "forecast row %s has %d fields" % (f[0], len(f))
                b = base[f[0]]
                b["rev_this"], b["rev_next"] = num(f[1]), num(f[2])
                b["eps_this"], b["eps_next"] = num(f[3]), num(f[4])
                b["ni_fc"], b["ni_fy"] = num(f[5]), f[6].strip()
                b["gm"] = num(f[7])
                hist = {}
                if f[8].strip() not in ("", "NA"):
                    for part in f[8].split(";"):
                        m = re.match(r"FY(\d{4})=(-?[\d.]+)$", part.strip())
                        if m:
                            hist[int(m.group(1))] = float(m.group(2))
                b["hist"] = hist
                b["pt"], b["rating"], b["nan"] = num(f[9]), f[10].strip(), num(f[11])
    return base


def main():
    base = load()

    # The forecast page reports Berkshire's Class A EPS; Class B is 1/1500th.
    # Does not feed the model, but leaving it would be a landmine in the CSV.
    brk = base.get("BRK.B")
    if brk and brk.get("eps_this") and brk["eps_this"] > 1000:
        brk["eps_this"] /= 1500.0
        brk["eps_next"] /= 1500.0

    # Margin anchor: prefer the forecast page's net income over the trailing figure,
    # because it normalises a year wrecked by a one-off charge (Merck, Genuine Parts).
    for b in base.values():
        b["mg_ttm"] = (100 * (b["mc"] / b["pe"]) / b["rev"]
                       if (b["pe"] and b["pe"] > 0 and b["rev"]) else None)
        m = None
        if b.get("ni_fc") is not None and b["ni_fc"] > 0 and b.get("hist"):
            fy = b["ni_fy"]
            y = int(fy[2:]) if fy.startswith("FY") else None
            rv = b["hist"].get(y) or b.get("rev_this")
            if rv and rv > 0:
                m = 100 * b["ni_fc"] / rv
        b["mg_fwd"] = m

    sec_mg, sec_pe = {}, {}
    for code in SECTORS:
        g = [b for b in base.values() if b["sec"] == code]
        mm = [b["mg_fwd"] for b in g if b["mg_fwd"] is not None and -50 < b["mg_fwd"] < 95]
        pp = [b["pe"] for b in g if b["pe"] and 0 < b["pe"] < 200]
        sec_mg[code] = statistics.median(mm) if mm else 10.0
        sec_pe[code] = statistics.median(pp) if pp else 20.0
    mkt_pe = statistics.median([b["pe"] for b in base.values()
                                if b["pe"] and 0 < b["pe"] < 200])

    def project(b, name):
        p = SCENARIOS[name]
        if not (b.get("rev_this") and b.get("rev_next") and b["rev_this"] > 0):
            return None
        g = max(-0.05, min(p["cap"], b["rev_next"] / b["rev_this"] - 1))
        g0 = g
        m0 = b["mg_fwd"]
        if m0 is None or m0 <= 0:
            m0 = sec_mg[b["sec"]]
            b["mg_assumed"] = True
        m0 = max(-5.0, min(90.0, m0))
        out, rev = {}, b["rev_next"]
        for y in range(ANCHOR_YEAR + 1, 2036):
            g = p["gT"] + (g - p["gT"]) * p["lam"]
            rev *= (1 + g)
            if y in HORIZONS:
                frac = (y - BASE_YEAR) / 9.0
                m = m0 * (1 + (p["mfac"] - 1) * frac)
                out[y] = dict(rev=rev, mg=m, ni=rev * m / 100.0, g=g)
        out["g0"], out["m0"] = g0, m0
        return out

    def exit_pe(b, name):
        own = min(b["pe"], 60.0) if (b["pe"] and b["pe"] > 0) else mkt_pe
        return max(10.0, min(32.0, 0.35 * own + 0.65 * mkt_pe)) * SCENARIOS[name]["xf"]

    rows = []
    for b in sorted(base.values(), key=lambda x: -(x["mc"] or 0)):
        hist = b.get("hist") or {}
        r = dict(t=b["t"], n=b["name"], s=b["sec"], i=b["idx"],
                 mc=round(b["mc"], 2), pe=b["pe"], rev=b["rev"],
                 mg_ttm=round(b["mg_ttm"], 2) if b["mg_ttm"] is not None else None,
                 mg_fwd=round(b["mg_fwd"], 2) if b["mg_fwd"] is not None else None,
                 pt=b.get("pt"), rating=b.get("rating"), nan=b.get("nan"),
                 r5=b.get("r5"), r10=b.get("r10"),
                 hist_yrs=len(hist), assumed_mg=False)
        ys = sorted(hist)
        r["cagr_hist"] = (round(100 * ((hist[ys[-1]] / hist[ys[0]]) ** (1 / (ys[-1] - ys[0])) - 1), 2)
                          if len(ys) >= 4 and hist[ys[0]] > 0 else None)

        ok = True
        for name in ("bear", "base", "bull"):
            pr = project(b, name)
            if pr is None:
                ok = False
                break
            if b.get("mg_assumed"):
                r["assumed_mg"] = True
            xp = exit_pe(b, name)
            r[name] = {}
            for y, nyr in HORIZONS.items():
                v = pr[y]["ni"] * xp
                r[name][str(y)] = dict(
                    rev=round(pr[y]["rev"], 2), mg=round(pr[y]["mg"], 2),
                    ni=round(pr[y]["ni"], 2), val=round(v, 1),
                    ir=round(100 * ((v / b["mc"]) ** (1 / nyr) - 1), 2) if v > 0 else None,
                    cagr=round(100 * ((pr[y]["rev"] / b["rev"]) ** (1 / nyr) - 1), 2) if b["rev"] else None)
            r[name]["xpe"] = round(xp, 1)
            r[name]["g0"] = round(100 * pr["g0"], 2)
            r[name]["m0"] = round(pr["m0"], 2)

        if not ok:
            r["modelled"] = False
            rows.append(r)
            continue
        r["modelled"] = True

        # Assumption-sensitivity flags. Holding a peak margin flat for nine years is
        # the most generous thing this model does; say so per company.
        m0 = r["base"]["m0"]
        flags = []
        if m0 > 2.0 * sec_mg[b["sec"]] and m0 > 25:
            flags.append("margin far above sector norm")
        if len(ys) >= 3 and hist[ys[-3]] > 0 and hist[ys[-1]] / hist[ys[-3]] > 1.9:
            flags.append("revenue nearly doubled in 2 years")
        if b["rev_next"] / b["rev_this"] - 1 > SCENARIOS["base"]["cap"]:
            flags.append("consensus growth above the %d%% cap" % (SCENARIOS["base"]["cap"] * 100))
        r["cyc"] = flags

        # The inversion: what 2026->2035 revenue CAGR does today's price already demand
        # to deliver REQUIRED_RETURN a year, holding margin and exit multiple fixed?
        xp = exit_pe(b, "base")
        m35 = r["base"]["2035"]["mg"]
        r["mg_used"] = round(r["base"]["m0"], 2)
        if m35 > 0 and b["rev"]:
            need_rev = (b["mc"] * (1 + REQUIRED_RETURN) ** 9 / xp) / (m35 / 100.0)
            r["req_cagr"] = round(100 * ((need_rev / b["rev"]) ** (1 / 9) - 1), 2)
            r["gap"] = round(r["base"]["2035"]["cagr"] - r["req_cagr"], 2)
        else:
            r["req_cagr"] = r["gap"] = None
        rows.append(r)

    modelled = [r for r in rows if r["modelled"]]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "forward.json"), "w") as fh:
        json.dump(dict(asof=ASOF, sectors=SECTORS, indexes=INDEXES,
                       mktPE=round(mkt_pe, 2),
                       secMg={k: round(v, 2) for k, v in sec_mg.items()},
                       secPe={k: round(v, 2) for k, v in sec_pe.items()},
                       scen=SCENARIOS, reqR=REQUIRED_RETURN, rows=rows),
                  fh, separators=(",", ":"))

    with open(os.path.join(OUT, "forward_2030_2035.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "company", "gics_sector", "index_membership",
                    "market_cap_usd_b", "trailing_pe", "revenue_ttm_usd_b",
                    "net_margin_ttm_pct", "net_margin_used_pct",
                    "revenue_cagr_reported_hist_pct", "consensus_growth_next_fy_pct",
                    "rev_2030_bear_b", "rev_2030_base_b", "rev_2030_bull_b",
                    "rev_2035_bear_b", "rev_2035_base_b", "rev_2035_bull_b",
                    "rev_cagr_to_2035_base_pct", "exit_pe_base",
                    "implied_return_2030_base_pct", "implied_return_2035_bear_pct",
                    "implied_return_2035_base_pct", "implied_return_2035_bull_pct",
                    "required_rev_cagr_for_8pct_return_pct", "gap_pp",
                    "analyst_target_usd", "analyst_rating", "n_analysts",
                    "margin_assumed_from_sector_median",
                    "assumption_sensitive_flags", "modelled"])
        for r in rows:
            if not r["modelled"]:
                w.writerow([r["t"], r["n"], SECTORS[r["s"]], INDEXES.get(r["i"], ""),
                            r["mc"]] + [""] * 23 + ["", "", "no analyst forecast data", "no"])
                continue
            g = lambda sc, y, k: r[sc][str(y)][k]
            w.writerow([r["t"], r["n"], SECTORS[r["s"]], INDEXES.get(r["i"], ""),
                        r["mc"], r["pe"], r["rev"], r["mg_ttm"], r["mg_used"],
                        r["cagr_hist"], r["base"]["g0"],
                        g("bear", 2030, "rev"), g("base", 2030, "rev"), g("bull", 2030, "rev"),
                        g("bear", 2035, "rev"), g("base", 2035, "rev"), g("bull", 2035, "rev"),
                        g("base", 2035, "cagr"), r["base"]["xpe"],
                        g("base", 2030, "ir"), g("bear", 2035, "ir"),
                        g("base", 2035, "ir"), g("bull", 2035, "ir"),
                        r["req_cagr"], r["gap"], r["pt"], r["rating"], r["nan"],
                        "yes" if r["assumed_mg"] else "no",
                        "; ".join(r.get("cyc") or []), "yes"])

    rev_now = sum(r["rev"] for r in modelled if r["rev"]) / 1000
    agg = {s: sum(r[s]["2035"]["rev"] for r in modelled) / 1000 for s in SCENARIOS}
    irs = sorted(r["base"]["2035"]["ir"] for r in modelled if r["base"]["2035"]["ir"] is not None)
    gaps = sorted(r["gap"] for r in modelled if r["gap"] is not None)
    print("rows                 : %d" % len(rows))
    print("modelled             : %d  (not modelled: %s)" % (
        len(modelled), ", ".join(r["t"] for r in rows if not r["modelled"])))
    print("margin assumed       : %d" % sum(1 for r in modelled if r["assumed_mg"]))
    print("assumption-flagged   : %d" % sum(1 for r in modelled if r.get("cyc")))
    print("market median P/E    : %.2f" % mkt_pe)
    print("revenue now          : $%.1fT" % rev_now)
    print("revenue 2035         : bear $%.1fT  base $%.1fT  bull $%.1fT" % (
        agg["bear"], agg["base"], agg["bull"]))
    print("implied return 2035  : p10 %.1f%%  median %.1f%%  p90 %.1f%%" % (
        irs[int(.1 * len(irs))], statistics.median(irs), irs[int(.9 * len(irs))]))
    print("gap (plausible-req)  : p10 %.1fpp  median %.1fpp  p90 %.1fpp  | positive %d of %d" % (
        gaps[int(.1 * len(gaps))], statistics.median(gaps), gaps[int(.9 * len(gaps))],
        sum(1 for x in gaps if x > 0), len(gaps)))
    print("wrote                : data/derived/forward.json, data/derived/forward_2030_2035.csv")


if __name__ == "__main__":
    main()
