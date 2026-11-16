# -*- coding: utf-8 -*-
"""
Runs the WHOLE inline <script> of index.html (logic + UI wiring) in quickjs against a
minimal DOM stub, so the page's behaviour is checked without a browser.

    python3 tests/test_ui.py
"""
import json
import os
import re
import sys

import quickjs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(HERE, "index.html")
KEY = "freelance-rate-calc-v1"

PRELUDE = r"""
var __els = {};
var __store = {};

function El(sel){
  this.sel = sel; this._html = ""; this.textContent = ""; this.value = "";
  this.hidden = false; this.style = {}; this.children = []; this.attrs = {};
  this.handlers = {}; this.className = ""; this.tagName = "div";
}
Object.defineProperty(El.prototype, "innerHTML", {
  get: function(){ return this._html; },
  set: function(v){ this._html = String(v); this.children = []; }
});
El.prototype.appendChild = function(c){ this.children.push(c); return c; };
El.prototype.addEventListener = function(t, f){
  if (!this.handlers[t]) this.handlers[t] = [];
  this.handlers[t].push(f);
};
El.prototype.fire = function(t, ev){
  var list = this.handlers[t] || [];
  for (var i = 0; i < list.length; i++) list[i].call(this, ev || {preventDefault: function(){}});
  return list.length;
};
El.prototype.setAttribute = function(k, v){ this.attrs[k] = String(v); };
El.prototype.getAttribute = function(k){ return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; };
El.prototype.select = function(){ this.selected = true; };
El.prototype.focus = function(){ this.focused = true; };

function getEl(id){
  var key = "#" + id;
  if (!__els[key]) __els[key] = new El(key);
  return __els[key];
}

var document = {
  readyState: "complete",
  getElementById: getEl,
  querySelector: function(sel){ return getEl(sel); },
  createElement: function(tag){ var e = new El("<" + tag + ">"); e.tagName = tag; return e; },
  querySelectorAll: function(sel){
    if (sel === "#presets .preset") return __els["#presets"] ? __els["#presets"].children : [];
    return [];
  },
  addEventListener: function(){},
  body: new El("body"),
  execCommand: function(){ return true; },
  documentElement: new El("html")
};
document.documentElement.setAttribute("data-theme", "light");

var navigator = {};
var localStorage = {
  getItem: function(k){ return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
  setItem: function(k, v){ __store[k] = String(v); },
  removeItem: function(k){ delete __store[k]; }
};
var __timers = [];
function setTimeout(fn, ms){ __timers.push(fn); return __timers.length; }
function clearTimeout(){}
"""


def inline_script():
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r"<script>(.*?)</script>", src, re.S)
    if not m:
        raise SystemExit("inline script not found")
    return m.group(1)


def build_ctx(seed=None):
    ctx = quickjs.Context()
    ctx.eval(PRELUDE)
    if seed is not None:
        ctx.eval(f"localStorage.setItem('{KEY}', {json.dumps(json.dumps(seed))})")
    ctx.eval(inline_script())
    return ctx


def js(ctx, expr):
    return json.loads(ctx.eval(f"JSON.stringify({expr})"))


def txt(ctx, sel):
    return ctx.eval(f"document.getElementById('{sel}').textContent")


failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'OK ' if ok else 'BAD'}  {label:<52} got={got!r}  want={want!r}")
    if not ok:
        failures.append(label)


def contains(label, hay, needle):
    ok = needle in (hay or "")
    print(f"{'OK ' if ok else 'BAD'}  {label:<52} {'contains' if ok else 'MISSING'} {needle!r}")
    if not ok:
        failures.append(label)


def main():
    src = open(HTML, encoding="utf-8").read()
    ctx = build_ctx()

    # ---------------------------------------------------------------- first paint
    print("--- first paint")
    check("hourly rate on first paint", txt(ctx, "out-hourly"), "$104.40")
    check("day rate on first paint", txt(ctx, "out-day"), "$835")
    check("monthly target on first paint", txt(ctx, "out-monthly"), "$10,222")
    check("billable hours on first paint", txt(ctx, "out-hours"), "1,175")
    check("hours sub-line mentions weeks", txt(ctx, "out-hours-sub"), "a year · 47 weeks")
    contains("quote hint offers the +15% rate", ctx.eval("document.getElementById('quote-hint').innerHTML"), "$120/h")
    check("project hours echoed", txt(ctx, "out-proj-hours"), "40")
    check("three preset chips", js(ctx, "document.getElementById('presets').children.length"), 8)
    check("no preset marked on first visit",
          js(ctx, "document.getElementById('presets').children[0].className"), "preset")
    check("three tiers rendered", js(ctx, "document.getElementById('tiers').children.length"), 3)
    contains("basic tier price", ctx.eval("document.getElementById('tiers').children[0].innerHTML"), "$2,550")
    contains("standard tier price", ctx.eval("document.getElementById('tiers').children[1].innerHTML"), "$4,200")
    contains("premium tier price", ctx.eval("document.getElementById('tiers').children[2].innerHTML"), "$6,250")
    contains("standard tier is highlighted", js(ctx, "document.getElementById('tiers').children[1].className"), "mid")
    contains("standard tier badge", ctx.eval("document.getElementById('tiers').children[1].innerHTML"), "Most picked")
    contains("deposit shown", ctx.eval("document.getElementById('tiers').children[1].innerHTML"), "deposit <b>$2,100</b>")
    check("sensitivity has three rows", js(ctx, "document.getElementById('sens-rows').innerHTML.split('<tr>').length - 1"), 3)
    contains("sensitivity names the hour load", ctx.eval("document.getElementById('sens-rows').innerHTML"), "80% of my hours")
    check("theme starts light", js(ctx, "document.documentElement.getAttribute('data-theme')"), "light")

    # ---------------------------------------------------------------- presets
    print("\n--- presets")
    ctx.eval("document.getElementById('presets').children[5].fire('click')")
    check("preset fills take-home target", js(ctx, "document.getElementById('in-target').value"), 120000)
    check("preset fills billable hours", js(ctx, "document.getElementById('in-hours').value"), 22)
    check("preset fills weeks off", js(ctx, "document.getElementById('in-weeks').value"), 6)
    check("preset rate recomputed", txt(ctx, "out-hourly"), "$194.81")
    check("preset monthly target", txt(ctx, "out-monthly"), "$16,429")
    check("preset day rate", txt(ctx, "out-day"), "$1,558")
    check("preset chip marked active",
          js(ctx, "document.getElementById('presets').children[5].className"), "preset on")
    check("preset toast", txt(ctx, "toast"), "AI Automation Consultant numbers loaded")
    contains("premium tier repriced", ctx.eval("document.getElementById('tiers').children[2].innerHTML"), "$11,650")
    check("preset saved to storage", js(ctx, f"JSON.parse(localStorage.getItem('{KEY}')).target"), 120000)

    # ---------------------------------------------------------------- manual input
    print("\n--- manual input")
    ctx.eval("""document.getElementById('in-hours').value = '30';
                document.getElementById('in-hours').fire('input')""")
    check("rate follows a new billable load", txt(ctx, "out-hourly"), "$142.86")
    check("active preset cleared",
          js(ctx, "document.getElementById('presets').children[5].className"), "preset")
    ctx.eval("""document.getElementById('in-tax').value = '40';
                document.getElementById('in-tax').fire('input')""")
    check("tax change lifts the rate", txt(ctx, "out-hourly"), "$166.67")
    ctx.eval("""document.getElementById('in-hours').value = 'abc';
                document.getElementById('in-hours').fire('input')""")
    check("junk input falls back to a number", txt(ctx, "out-hourly"), "$200.00")

    # ---------------------------------------------------------------- currency
    print("\n--- currency")
    ctx.eval("""var s = document.getElementById('cur'); s.value = 'EUR'; s.fire('change')""")
    contains("hourly switches to euro", txt(ctx, "out-hourly"), "€")
    contains("target symbol switches", txt(ctx, "sym-target"), "€")
    check("currency saved", js(ctx, f"JSON.parse(localStorage.getItem('{KEY}')).cur"), "EUR")
    ctx.eval("""var s = document.getElementById('cur'); s.value = 'USD'; s.fire('change')""")

    # ---------------------------------------------------------------- copy
    print("\n--- copy")
    ctx.eval("document.getElementById('copy-btn').fire('click')")
    contains("copy reports success", txt(ctx, "toast"), "Copied")

    # ---------------------------------------------------------------- theme
    print("\n--- theme")
    ctx.eval("document.getElementById('theme-toggle').fire('click')")
    check("theme toggles to dark", js(ctx, "document.documentElement.getAttribute('data-theme')"), "dark")
    check("toggle label flips", txt(ctx, "theme-toggle"), "☀️ Light")
    check("theme persisted", ctx.eval(f"localStorage.getItem('{KEY}:theme')"), "dark")
    ctx.eval("document.getElementById('theme-toggle').fire('click')")
    check("theme toggles back", js(ctx, "document.documentElement.getAttribute('data-theme')"), "light")

    # ---------------------------------------------------------------- reset
    print("\n--- reset")
    ctx.eval("document.getElementById('reset-btn').fire('click')")
    check("reset restores target", js(ctx, "document.getElementById('in-target').value"), 80000)
    check("reset restores rate", txt(ctx, "out-hourly"), "$104.40")
    check("reset toast", txt(ctx, "toast"), "Back to the default numbers")
    check("reset saved", js(ctx, f"JSON.parse(localStorage.getItem('{KEY}')).hours"), 25)

    # ---------------------------------------------------------------- persistence across visits
    print("\n--- second visit")
    ctx2 = build_ctx(seed={"target": 64000, "tax": 20, "hours": 20, "weeks": 4,
                           "costs": 300, "day": 6, "project": 12, "cur": "GBP", "preset": ""})
    check("stored target restored", js(ctx2, "document.getElementById('in-target').value"), 64000)
    check("stored currency restored", js(ctx2, "document.getElementById('cur').value"), "GBP")
    contains("restored rate uses the stored numbers", txt(ctx2, "out-hourly"), "£")
    check("welcome-back toast", txt(ctx2, "toast"), "Welcome back — your numbers were restored")
    check("restored project hours", txt(ctx2, "out-proj-hours"), "12")
    contains("restored tiers priced", ctx2.eval("document.getElementById('tiers').children[0].innerHTML"), "£")

    # ---------------------------------------------------------------- CTA + static requirements
    print("\n--- CTA and page requirements")
    m = re.search(r'<a class="cta-btn" id="gumroad-link" href="([^"]+)"(.*?)>', src, re.S)
    check("CTA url is the second Gumroad product",
          m.group(1), "https://rwg4002.gumroad.com/l/freelance-rate-quote-kit")
    check("CTA opens in a new tab safely", 'target="_blank"' in m.group(2) and 'rel="noopener"' in m.group(2), True)
    check("CTA carries the price", "$14" in src, True)
    check("CTA carries the launch code", "LAUNCH25" in src, True)
    check("two ad slots", src.count('class="adslot"'), 2)
    check("no external script/stylesheet/font",
          bool(re.search(r'<script[^>]+src=', src)) or bool(re.search(r'<link[^>]+rel="stylesheet"', src))
          or "@import" in src or "fonts.googleapis" in src, False)
    check("no fetch/XHR", bool(re.search(r"fetch\s*\(|XMLHttpRequest", src)), False)
    check("viewport meta present", 'name="viewport"' in src, True)
    check("canonical url present",
          'rel="canonical" href="https://gkdlwjavm9-cpu.github.io/freelance-rate-calculator/"' in src, True)

    print("\n" + ("All UI checks passed" if not failures else f"{len(failures)} failed: {failures}"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
