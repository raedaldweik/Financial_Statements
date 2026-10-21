"""Deterministic KPIs, ratios and chart series from the transcribed statements.

The model only tells us WHICH rows carry which concept (`keyRows`); every number shown on the
dashboard is then computed in code from the transcribed values, so nothing is re-typed by
the model.
"""
from __future__ import annotations

KEYS = ["revenue", "costOfSales", "grossProfit", "operatingIncome", "profitBeforeTax", "netIncome", "netIncomeParent", "eps",
        "totalAssets", "currentAssets", "nonCurrentAssets", "totalEquity", "totalLiabilities", "currentLiabilities", "nonCurrentLiabilities",
        "cash", "shortTermInvestments", "borrowingsCurrent", "borrowingsNonCurrent", "operatingCF", "investingCF", "financingCF",
        "capex", "dividendsPaid", "openingCash", "closingCash", "netChangeCash"]

KEYROWS_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": ["object", "null"], "properties": {"stmt": {"type": "string"}, "row": {"type": "integer"}, "note": {"type": ["string", "null"]}},
                       "required": ["stmt", "row", "note"], "additionalProperties": False} for k in KEYS}
    | {"years": {"type": "array", "items": {"type": "string"}, "description": "the two fiscal-year labels in order [current, prior]"}},
    "required": KEYS + ["years"],
    "additionalProperties": False,
}

KEYROWS_SYSTEM = """You map the transcribed primary financial statements of a company to standard concepts.
For each concept return the statement id and the 0-based row index of the line that carries it (choose the consolidated figure, not a component), or null when the statement has no such line. Use the first two value columns as [current year, prior year]. Do not invent rows."""


def compact_statements(statements: list[dict]) -> str:
    parts = []
    for st in statements:
        parts.append(f"## {st['id']} — {st['title']} | cols: {st['cols']}")
        for i, r in enumerate(st["rows"]):
            if "v" in r:
                parts.append(f"{st['id']}#{i}: {r['l']} {'[n ' + r['n'] + ']' if r.get('n') else ''} {r['v'][:4]}")
            else:
                parts.append(f"{st['id']}#{i}: ({'section' if r.get('s') else 'header'}) {r['l']}")
    return "\n".join(parts)


def _val(statements, ref, col=0):
    if not ref:
        return None
    st = next((s for s in statements if s["id"] == ref["stmt"]), None)
    if not st or not (0 <= ref["row"] < len(st["rows"])):
        return None
    v = st["rows"][ref["row"]].get("v")
    if not v or col >= len(v):
        return None
    return v[col]


def _pair(statements, keyrows, key):
    ref = keyrows.get(key)
    return _val(statements, ref, 0), _val(statements, ref, 1), (ref or {}).get("note")


def _pct(a, b):
    return None if a is None or not b else round(a / b * 100, 1)


def derive(statements: list[dict], keyrows: dict, scale: float) -> dict:
    g = lambda k: _pair(statements, keyrows, k)
    rev, rev_p, rev_n = g("revenue")
    ni, ni_p, ni_n = g("netIncome")
    ta, ta_p, ta_n = g("totalAssets")
    te, te_p, te_n = g("totalEquity")
    ocf, ocf_p, ocf_n = g("operatingCF")
    ca, ca_p, _ = g("currentAssets")
    cl, cl_p, _ = g("currentLiabilities")
    nca, nca_p, _ = g("nonCurrentAssets")
    ncl, ncl_p, _ = g("nonCurrentLiabilities")
    tl, tl_p, _ = g("totalLiabilities")
    cash, cash_p, cash_n = g("cash")
    sti, sti_p, _ = g("shortTermInvestments")
    bc, bc_p, b_n = g("borrowingsCurrent")
    bnc, bnc_p, _ = g("borrowingsNonCurrent")
    gp, gp_p, _ = g("grossProfit")
    oi, oi_p, _ = g("operatingIncome")
    capex, capex_p, capex_n = g("capex")
    div, div_p, div_n = g("dividendsPaid")
    eps, eps_p, eps_n = g("eps")
    icf, icf_p, _ = g("investingCF")
    fcf, fcf_p, _ = g("financingCF")
    oc, _, _ = g("openingCash")
    cc, _, _ = g("closingCash")

    # fill gaps from identities
    if nca is None and ta is not None and ca is not None:
        nca, nca_p = ta - ca, (ta_p - ca_p if ta_p is not None and ca_p is not None else None)
    if tl is None and ta is not None and te is not None:
        tl, tl_p = ta - te, (ta_p - te_p if ta_p is not None and te_p is not None else None)
    if ncl is None and tl is not None and cl is not None:
        ncl, ncl_p = tl - cl, (tl_p - cl_p if tl_p is not None and cl_p is not None else None)
    borrow = (bc or 0) + (bnc or 0) if (bc is not None or bnc is not None) else None
    borrow_p = (bc_p or 0) + (bnc_p or 0) if (bc_p is not None or bnc_p is not None) else None
    net_debt = borrow - (cash or 0) - (sti or 0) if borrow is not None else None
    net_debt_p = borrow_p - (cash_p or 0) - (sti_p or 0) if borrow_p is not None else None

    kpis = []
    if rev is not None: kpis.append({"label": "Revenue", "v": rev, "p": rev_p, "kind": "money", "note": rev_n})
    if ni is not None: kpis.append({"label": "Net income" if ni >= 0 else "Net loss", "v": ni, "p": ni_p, "kind": "money", "note": ni_n})
    if ta is not None: kpis.append({"label": "Total assets", "v": ta, "p": ta_p, "kind": "money", "note": ta_n})
    if te is not None: kpis.append({"label": "Total equity", "v": te, "p": te_p, "kind": "money", "note": te_n})
    if ocf is not None: kpis.append({"label": "Operating cash flow", "v": ocf, "p": ocf_p, "kind": "money", "note": ocf_n})
    if net_debt is not None and te:
        kpis.append({"label": "Net debt / equity", "v": round(net_debt / te * 100, 1), "p": (round(net_debt_p / te_p * 100, 1) if net_debt_p is not None and te_p else None), "kind": "pct", "note": b_n, "lowerIsBetter": True})
    elif tl is not None and ta:
        kpis.append({"label": "Liabilities / assets", "v": round(tl / ta * 100, 1), "p": (round(tl_p / ta_p * 100, 1) if tl_p is not None and ta_p else None), "kind": "pct", "lowerIsBetter": True})

    ratios = []
    if gp is not None and rev: ratios.append({"label": "Gross margin", "v": _pct(gp, rev), "p": _pct(gp_p, rev_p), "unit": "%", "desc": "Gross profit / revenue"})
    if ni is not None and rev: ratios.append({"label": "Net margin", "v": _pct(ni, rev), "p": _pct(ni_p, rev_p), "unit": "%", "desc": "Net result / revenue"})
    if oi is not None and rev: ratios.append({"label": "Operating margin", "v": _pct(oi, rev), "p": _pct(oi_p, rev_p), "unit": "%", "desc": "Operating result / revenue"})
    if ca is not None and cl: ratios.append({"label": "Current ratio", "v": round(ca / cl, 2), "p": (round(ca_p / cl_p, 2) if ca_p is not None and cl_p else None), "unit": "x", "desc": "Current assets / current liabilities"})
    if borrow is not None: ratios.append({"label": "Total borrowings", "v": borrow, "p": borrow_p, "unit": "money", "desc": "Current + non-current borrowings", "note": b_n})
    if net_debt is not None: ratios.append({"label": "Net debt / (cash)", "v": net_debt, "p": net_debt_p, "unit": "money", "desc": "Borrowings less cash and short-term investments", "note": b_n})
    if capex is not None: ratios.append({"label": "Capex", "v": abs(capex), "p": (abs(capex_p) if capex_p is not None else None), "unit": "money", "desc": "Purchase of property, plant and equipment", "note": capex_n})
    if div is not None: ratios.append({"label": "Dividends paid", "v": abs(div), "p": (abs(div_p) if div_p is not None else None), "unit": "money", "desc": "Dividends paid to shareholders", "note": div_n})
    if eps is not None: ratios.append({"label": "EPS", "v": eps, "p": eps_p, "unit": "SAR", "desc": "Earnings per share", "note": eps_n})
    if te is not None and ta: ratios.append({"label": "Equity ratio", "v": _pct(te, ta), "p": _pct(te_p, ta_p), "unit": "%", "desc": "Equity / total assets"})

    charts = {}
    if ta is not None and ca is not None and te is not None and cl is not None:
        charts["balance"] = {"labels": ["prior", "current"], "nonCurrentAssets": [nca_p, nca], "currentAssets": [ca_p, ca], "equity": [te_p, te], "nonCurrentLiab": [ncl_p, ncl], "currentLiab": [cl_p, cl]}
    if ocf is not None and icf is not None and fcf is not None:
        open_c = oc if oc is not None else (cash_p if cash_p is not None else 0)
        close_c = cc if cc is not None else (cash if cash is not None else open_c + ocf + icf + fcf)
        charts["cashBridge"] = {"operating": ocf, "investing": icf, "financing": fcf, "net": ocf + icf + fcf, "open": open_c, "close": close_c}
    return {"kpis": kpis, "ratios": ratios, "charts": charts}
