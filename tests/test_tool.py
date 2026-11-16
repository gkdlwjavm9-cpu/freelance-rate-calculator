# -*- coding: utf-8 -*-
"""
Runs the pure calculation logic inside index.html with quickjs (no browser needed).

    python3 tests/test_tool.py
"""
import json
import os
import re
import sys

import quickjs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(HERE, "index.html")


def load_logic():
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r"/\* PURE_LOGIC_START \*/(.*?)/\* PURE_LOGIC_END \*/", src, re.S)
    if not m:
        raise SystemExit("PURE_LOGIC block not found")
    ctx = quickjs.Context()
    ctx.eval(m.group(1))
    return ctx


def js(ctx, expr):
    return json.loads(ctx.eval(f"JSON.stringify({expr})"))


failures = []


def check(label, got, want, tol=1e-6):
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol * max(1.0, abs(want))
    else:
        ok = got == want
    print(f"{'OK ' if ok else 'BAD'}  {label:<56} got={got!r}  want={want!r}")
    if not ok:
        failures.append(label)


def near(label, got, want, tol=1e-6):
    check(label, round(float(got), 6) if got is not None else None, round(float(want), 6), tol)


def model(ctx, **kw):
    base = dict(target=80000, tax=25, hours=25, weeks=5, costs=1000, day=8, project=40)
    base.update(kw)
    ctx.eval("var __i = " + json.dumps(base) + ";")
    return js(ctx, "computeModel(__i)")


def main():
    ctx = load_logic()

    # ---------------------------------------------------------------- presets
    print("--- presets")
    presets = js(ctx, "PRESETS")
    check("preset count", len(presets), 8)
    check("unique keys", len({p["key"] for p in presets}), 8)
    names = [p["name"] for p in presets]
    for want in ["Web Developer", "UI/UX Designer", "Video Editor", "Copywriter",
                 "Data Analyst", "AI Automation Consultant", "Motion Designer", "Social Media Manager"]:
        check(f"preset present: {want}", want in names, True)
    for p in presets:
        good = (20000 <= p["target"] <= 300000 and 0 < p["tax"] <= 50 and 5 <= p["hours"] <= 40
                and 0 <= p["weeks"] <= 12 and 0 <= p["costs"] <= 5000 and 4 <= p["day"] <= 10
                and 5 <= p["project"] <= 200)
        check(f"preset plausible: {p['name']}", good, True)
    # every preset produces a sensible rate
    for p in presets:
        ctx.eval("var __p = " + json.dumps(p) + ";")
        m = js(ctx, "computeModel({target:__p.target,tax:__p.tax,hours:__p.hours,weeks:__p.weeks,costs:__p.costs,day:__p.day})")
        hourly = m["hourly"]
        check(f"rate sane: {p['name']}", 20 <= hourly <= 500, True)

    # ---------------------------------------------------------------- default model
    print("\n--- default model")
    m = model(ctx)
    hours_year = 25 * 47
    fixed = 1000 * 12
    gross = (80000 + fixed) / 0.75
    hourly = gross / hours_year
    near("hours a year", m["hoursYear"], hours_year)
    near("weeks", m["weeks"], 47)
    near("fixed a year", m["fixedYear"], fixed)
    near("gross revenue", m["gross"], gross)
    near("monthly target", m["monthly"], gross / 12)
    near("real hourly rate", m["hourly"], hourly)
    near("quote rate (+15%)", m["marginHourly"], hourly * 1.15)
    near("day rate", m["dayRate"], hourly * 8)
    near("weekly revenue", m["weekly"], gross / 47)

    # formula identity: hourly x billable hours == gross
    near("hourly x hours == gross", m["hourly"] * m["hoursYear"], m["gross"])

    # ---------------------------------------------------------------- tiers
    print("\n--- three tiers")
    t = js(ctx, "tierQuote(computeModel({target:80000,tax:25,hours:25,weeks:5,costs:1000,day:8}), 40)")
    check("standard tier more than basic", t["standard"]["price"] > t["basic"]["price"], True)
    check("premium more than standard", t["premium"]["price"] > t["standard"]["price"], True)
    near("basic hours = 60%", t["basic"]["hours"], 24)
    near("standard hours = 100%", t["standard"]["hours"], 40)
    near("premium hours = 130%", t["premium"]["hours"], 52)
    near("basic price rounds up to 50", t["basic"]["price"], round_up(24 * hourly, 50))
    near("standard price rounds up to 50", t["standard"]["price"], round_up(40 * hourly, 50))
    near("premium price uses priority rate", t["premium"]["price"], round_up(52 * hourly * 1.15, 50))
    near("deposit is half", t["standard"]["deposit"], round_up(40 * hourly, 50) / 2)
    check("price always a multiple of 50",
          all(t[k]["price"] % 50 == 0 for k in ("basic", "standard", "premium")), True)

    t1 = js(ctx, "tierQuote(computeModel({target:80000,tax:25,hours:25,weeks:5,costs:1000,day:8}), 1)")
    check("tiny project still prices above zero", t1["basic"]["price"] >= 50, True)

    # ---------------------------------------------------------------- alternative scenarios
    print("\n--- scenarios")
    m2 = model(ctx, tax=0)
    near("no tax: gross = target + costs", m2["gross"], 80000 + 12000)
    m3 = model(ctx, tax=90)
    near("90% tax nearly triples revenue", m3["gross"], (80000 + 12000) / 0.1)
    m4 = model(ctx, weeks=0)
    near("no weeks off: 52 weeks", m4["hoursYear"], 25 * 52)
    m5 = model(ctx, costs=0)
    near("no costs: gross = target/(1-tax)", m5["gross"], 80000 / 0.75)
    m6 = model(ctx, hours=1)
    near("one billable hour a week is costly", m6["hourly"], (92000 / 0.75) / 47)
    m7 = model(ctx, tax=-5, hours=0, weeks=-3)
    check("negative tax clamped to 0", m7["taxRate"], 0)
    near("hours floor 0.5", m7["hoursWeek"], 0.5)   # 0 clamps to 0.5 ...
    check("negative weeks off clamped", m7["weeks"], 52)

    # ---------------------------------------------------------------- helpers
    print("\n--- formatting")
    check("money format", js(ctx, "fmtMoney(1234567.4,'USD')"), "$1,234,567")
    check("money euro", js(ctx, "fmtMoney(500,'EUR')"), "€500")
    check("rate format keeps cents", js(ctx, "fmtRate(104.397,'USD')"), "$104.40")
    check("rate format thousands", js(ctx, "fmtRate(1234.5,'USD')"), "$1,234.50")
    check("hours format", js(ctx, "fmtHours(1175)"), "1,175")
    check("hours format keeps a decimal", js(ctx, "fmtHours(24.25)"), "24.3")
    check("num parses junk to fallback", js(ctx, "num('abc', 7)"), 7)
    check("num parses '$1,200'", js(ctx, "num('$1,200', 0)"), 1200)
    check("clamp low", js(ctx, "clamp(-4, 0, 10)"), 0)
    check("clamp high", js(ctx, "clamp(44, 0, 10)"), 10)
    check("clamp NaN", js(ctx, "clamp(NaN, 3, 10)"), 3)
    check("roundUpTo 0", js(ctx, "roundUpTo(0, 50)"), 0)
    check("roundUpTo exact stays", js(ctx, "roundUpTo(2500, 50)"), 2500)
    check("roundUpTo floats up", js(ctx, "roundUpTo(2506.3, 50)"), 2550)

    # ---------------------------------------------------------------- summary text
    print("\n--- copy summary")
    ctx.eval("var __i = {target:80000,tax:25,hours:25,weeks:5,costs:1000,day:8,project:40,cur:'USD'};"
             "var __m = computeModel(__i); var __t = tierQuote(__m, 40);")
    txt = ctx.eval("summaryText(__i, __m, __t, 'USD')")
    for needle in ["Take-home target: $80,000", "Real hourly rate: $104.40", "1,175 h / year",
                   "Revenue to invoice: $122,667", "Basic $2,550", "Standard $4,200", "Premium $6,250"]:
        check(f"summary contains {needle!r}", needle in txt, True)

    print("\n" + ("All logic checks passed" if not failures else f"{len(failures)} failed: {failures}"))
    return 0 if not failures else 1


def round_up(v, step):
    import math
    return math.ceil(v / step - 1e-9) * step


if __name__ == "__main__":
    sys.exit(main())
