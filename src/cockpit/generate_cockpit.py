"""Generate the Phoenix R6 Program Cockpit HTML.

The page layout, styling and behaviour live in TEMPLATE below. Every hard-coded
value (titles, dates, footnotes, workstream/org lists, the DATA blob, ...) is read
from a JSON file, so refreshing the cockpit means editing/replacing that file only.

Usage:  python generate_cockpit.py [data.json] [output.html]
"""
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "cockpit_data.json"

# {{key}} -> raw text from the data file; {{json:key}} -> JSON literal for use inside <script>;
# {{footnotes}} -> one <span> per entry of data["footnotes"]
PLACEHOLDER = re.compile(r"\{\{(json:)?([A-Za-z0-9_]+)\}\}")

TEMPLATE = r"""<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}html{scroll-padding-top:env(safe-area-inset-top,0px)}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#fff;color:#000}img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style></head><body>
<title>{{title}}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Source+Sans+3:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* Layout: executive slide. Header + KPI tiles, slicer strip, four lineage panels left→right, traceability chain, L4 drill table */
:root{
  --bg:#EEF1F6; --surface:#FFFFFF; --surface-2:#F5F7FB; --line:#DCE2EC; --line-2:#C9D2E0;
  --ink:#0E1B3D; --ink-2:#3A4766; --muted:#6A7590;
  --brand:#1B2C6B; --brand-2:#6E7FBF; --accent:#0091A8; --accent-soft:#CDEBF0; --plan:#9AA7C2;
  --good:#1E8E5E; --good-soft:#D6F0E3; --warn:#C27C00; --warn-soft:#FBEBCB; --crit:#C8323F; --crit-soft:#F8DADD; --ns:#D9DFEA; --planned:#AFC3E6;
  --on-solid:#FFFFFF;
  --lv1:#1B2C6B; --lv2:#0091A8; --lv3:#8A5CC2; --lv4:#D06A2B;
  --display:"Archivo","Helvetica Neue",Arial,sans-serif; --body:"Source Sans 3","Segoe UI",system-ui,sans-serif; --mono:"JetBrains Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0A1022; --surface:#121A33; --surface-2:#18213D; --line:#26314F; --line-2:#334063;
  --ink:#E8EDF8; --ink-2:#C0C9DD; --muted:#8B96B2;
  --brand:#A9B9F2; --brand-2:#6577B8; --accent:#3CC4D8; --accent-soft:#163B48; --plan:#5C6888;
  --good:#3FBF86; --good-soft:#163A2C; --warn:#E5A53A; --warn-soft:#3E3016; --crit:#F0656F; --crit-soft:#45202A; --ns:#2B3554; --planned:#4A5F8F;
  --on-solid:#0A1022; --lv1:#A9B9F2; --lv2:#3CC4D8; --lv3:#B99BEA; --lv4:#F0995E; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0A1022; --surface:#121A33; --surface-2:#18213D; --line:#26314F; --line-2:#334063;
  --ink:#E8EDF8; --ink-2:#C0C9DD; --muted:#8B96B2;
  --brand:#A9B9F2; --brand-2:#6577B8; --accent:#3CC4D8; --accent-soft:#163B48; --plan:#5C6888;
  --good:#3FBF86; --good-soft:#163A2C; --warn:#E5A53A; --warn-soft:#3E3016; --crit:#F0656F; --crit-soft:#45202A; --ns:#2B3554; --planned:#4A5F8F;
  --on-solid:#0A1022; --lv1:#A9B9F2; --lv2:#3CC4D8; --lv3:#B99BEA; --lv4:#F0995E; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:14px;line-height:1.4;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px}
.slide{max-width:1520px;margin:0 auto;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:20px 22px 18px;display:flex;flex-direction:column;gap:14px}
.num{font-variant-numeric:tabular-nums}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
.eyebrow{font:600 11px/1 var(--body);letter-spacing:.14em;text-transform:uppercase;color:var(--accent);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.eyebrow .sep{width:4px;height:4px;background:var(--line-2);border-radius:50%}
h1{font:800 28px/1.1 var(--display);letter-spacing:-.01em;margin:6px 0 4px;color:var(--ink);text-wrap:balance}
h1 span{color:var(--brand)}
.sub{color:var(--muted);font-size:13px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.tag{font:500 11px/1 var(--mono);padding:4px 7px;border:1px solid var(--line-2);border-radius:4px;color:var(--muted)}
.kpis{display:flex;gap:10px}
.kpi{min-width:160px;border:1px solid var(--line);border-radius:6px;padding:10px 14px;background:var(--surface-2);display:grid;grid-template-columns:auto 1fr;column-gap:12px;align-items:center}
.kpi .dot{width:10px;height:38px;border-radius:3px;grid-row:span 2}
.kpi.risk .dot{background:var(--crit)} .kpi.act .dot{background:var(--warn)}
.kpi b{font:800 30px/1 var(--display)}
.kpi b.na{color:var(--muted)}
.kpi .lbl{font:600 11px/1.2 var(--body);text-transform:uppercase;letter-spacing:.08em;color:var(--ink-2)}
.kpi .meta{grid-column:2;font-size:12px;color:var(--muted);margin-top:2px}
.slicers{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:10px 12px;background:var(--surface-2);border:1px solid var(--line);border-radius:6px}
.slicers .ttl{font:600 11px/1 var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-right:4px}
.ms{position:relative}
.ms>button{font:inherit;font-size:13px;display:flex;gap:8px;align-items:center;background:var(--surface);color:var(--ink);border:1px solid var(--line-2);border-radius:5px;padding:7px 10px;cursor:pointer;min-width:200px;justify-content:space-between}
.ms>button:hover{border-color:var(--accent)}
.ms>button .k{color:var(--muted);font-weight:500}
.ms>button .v{font-weight:600}
.ms>button.on{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.ms .chev{width:8px;height:8px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(45deg) translateY(-2px)}
.pop{position:absolute;top:calc(100% + 4px);left:0;z-index:20;background:var(--surface);border:1px solid var(--line-2);border-radius:6px;box-shadow:0 10px 30px rgba(10,20,50,.18);padding:6px;min-width:270px;max-height:360px;overflow:auto}
.pop label{display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:4px;cursor:pointer;font-size:13px}
.pop label:hover{background:var(--surface-2)}
.pop label .c{margin-left:auto;font:500 11px var(--mono);color:var(--muted)}
.pop input{accent-color:var(--accent)}
.pop .row{display:flex;justify-content:space-between;padding:4px 8px 6px;border-bottom:1px solid var(--line);margin-bottom:4px}
.lnk{background:none;border:0;color:var(--accent);font:600 12px var(--body);cursor:pointer;padding:2px}
.reset{margin-left:auto;font:600 12px var(--body);background:none;border:1px solid var(--line-2);color:var(--ink-2);border-radius:5px;padding:7px 12px;cursor:pointer}
.reset:hover{color:var(--accent);border-color:var(--accent)}
button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.scope{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:1.15fr 1fr 1fr 1.3fr;gap:12px}
.panel{border:1px solid var(--line);border-radius:6px;padding:14px;display:flex;flex-direction:column;gap:12px;min-width:0;background:var(--surface)}
.ph{display:flex;justify-content:space-between;align-items:baseline;gap:8px;border-bottom:1px solid var(--line);padding-bottom:8px}
.ph h2{font:700 14px/1.2 var(--display);margin:0;letter-spacing:.01em;text-transform:uppercase}
.ph .step{font:500 11px var(--mono);color:var(--accent);margin-right:6px}
.ph .hint{font-size:11px;color:var(--muted);text-align:right}
.big{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.big b{font:800 34px/1 var(--display)}
.big .of{font:600 15px var(--display);color:var(--muted)}
.big .pct{font:700 12px var(--body);padding:3px 7px;border-radius:10px;background:var(--accent-soft);color:var(--accent)}
.facts{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.facts strong{color:var(--ink);font-weight:700}
.facts strong.w{color:var(--warn)} .facts strong.r{color:var(--crit)}
.sect{font:600 11px/1 var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap}
.legend{display:flex;gap:10px;flex-wrap:wrap;font:500 11px var(--body);letter-spacing:0;text-transform:none;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:8px;border-radius:2px;margin-right:4px;vertical-align:middle}
.phases{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.phase{border:1px solid var(--line);border-radius:4px;padding:6px 8px;background:var(--surface-2)}
.phase .k{font:600 10px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.phase .v{font:700 14px var(--mono)} .phase .v small{font-weight:400;color:var(--muted)}
.ctrows{display:flex;flex-direction:column;gap:7px;max-height:300px;overflow:auto;padding-right:4px}
.ctr{display:grid;grid-template-columns:minmax(0,1fr) 54px;gap:8px;align-items:center}
.ctr .name{font-size:12px;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:3px}
.ctr .name .l4{color:var(--muted);font:400 10px var(--mono);margin-left:4px}
.track{position:relative;height:10px}
.track .sc{position:absolute;inset:0 auto 0 0;background:var(--surface-2);border:1px solid var(--line);border-radius:2px}
.track .ptd{position:absolute;top:-2px;bottom:-2px;left:0;border-right:2px solid var(--plan);border-top:1px dashed var(--plan);border-bottom:1px dashed var(--plan)}
.track .act{position:absolute;top:1px;bottom:1px;left:1px;background:var(--accent);border-radius:1px}
.ctr .v{font:600 12px var(--mono);text-align:right;color:var(--ink)}
.ctr .v small{color:var(--muted);font-weight:400}
.ctr.lag .v{color:var(--warn)}
.stack{display:flex;height:16px;border-radius:3px;overflow:hidden;background:var(--ns)}
.stack span{display:block;height:100%}
.states{display:grid;grid-template-columns:1fr 1fr;gap:6px 10px}
.st{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ink-2);padding:5px 7px;border-radius:4px;border:1px solid transparent;cursor:pointer;background:none;font-family:inherit;text-align:left}
.st:hover{border-color:var(--line-2)}
.st.on{border-color:var(--accent);background:var(--accent-soft)}
.st i{width:10px;height:10px;border-radius:2px;flex:none}
.st b{margin-left:auto;font:700 13px var(--mono);color:var(--ink)}
.list{display:flex;flex-direction:column;border-top:1px solid var(--line)}
.li{display:grid;grid-template-columns:56px minmax(0,1fr) auto;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);align-items:center;font-size:12px}
.li .id{font:500 11px var(--mono);color:var(--muted)}
.li .t{overflow:hidden;color:var(--ink-2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;line-height:1.3}
.li small{display:block;color:var(--muted);font:400 10px var(--mono)}
.pill{font:600 10px/1 var(--body);padding:3px 6px;border-radius:9px;white-space:nowrap;letter-spacing:.02em}
.pill.g{background:var(--good-soft);color:var(--good)} .pill.a{background:var(--warn-soft);color:var(--warn)} .pill.r{background:var(--crit-soft);color:var(--crit)} .pill.n{background:var(--surface-2);color:var(--muted);border:1px solid var(--line)}
.empty{font-size:12px;color:var(--muted);padding:8px 0}
.split{display:flex;height:34px;border-radius:4px;overflow:hidden;font:700 11px var(--body);background:var(--ns)}
.split div{display:flex;align-items:center;padding:0 6px;color:var(--on-solid);white-space:nowrap;min-width:0;overflow:hidden}
.c-oob{background:var(--brand-2)} .c-cfg{background:var(--brand)} .c-gap{background:var(--accent)} .c-tbd{background:var(--plan)}
.cov{display:flex;flex-direction:column;gap:6px}
.covr{display:grid;grid-template-columns:minmax(0,1fr) 60px;gap:8px;font-size:12px;align-items:center;color:var(--ink-2)}
.covr .bar{grid-column:1/-1;height:6px;background:var(--ns);border-radius:2px;overflow:hidden}
.covr .bar span{display:block;height:100%;background:var(--good)}
.covr .n{font:600 12px var(--mono);text-align:right}
.wsrows{display:flex;flex-direction:column;gap:6px}
.wsr{display:grid;grid-template-columns:76px minmax(0,1fr) 40px;gap:8px;align-items:center;font-size:12px}
.wsr .w{font:600 11px var(--mono);color:var(--ink-2)}
.wsr .bar{display:flex;height:9px;background:var(--surface-2);border-radius:2px;overflow:hidden}
.wsr .n{font:500 11px var(--mono);text-align:right;color:var(--muted)}
.tree{border:1px solid var(--line);border-radius:5px;padding:10px 12px;display:flex;flex-direction:column;gap:8px;background:var(--surface-2)}
.root{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.root .kind{font:700 10px/1 var(--body);letter-spacing:.08em;text-transform:uppercase;padding:4px 6px;border-radius:3px;color:var(--on-solid)}
.root .kind.fit{background:var(--brand)} .root .kind.gap{background:var(--accent)}
.root h3{font:700 14px var(--display);margin:0}
.root .cnt{font:700 14px var(--mono);margin-left:auto}
.types{display:flex;gap:4px;flex-wrap:wrap}
.types span{font:500 10px var(--mono);border:1px solid var(--line-2);border-radius:3px;padding:2px 5px;color:var(--ink-2);background:var(--surface)}
.types span b{color:var(--accent)}
.child{display:grid;grid-template-columns:14px 92px minmax(0,1fr) 92px;gap:6px;align-items:center;font-size:12px}
.child .elbow{width:12px;height:14px;border-left:1.5px solid var(--line-2);border-bottom:1.5px solid var(--line-2);margin-top:-8px;margin-left:4px}
.child .nm{font:600 11px var(--mono);color:var(--ink-2)}
.child .pct{font:600 11px var(--mono);text-align:right;color:var(--muted)}
.child .pct b{color:var(--ink)}
.sbar{display:flex;height:10px;border-radius:2px;overflow:hidden;background:var(--ns)}
.sbar span{display:block;height:100%}
.slegend{display:flex;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--muted)}
.slegend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.chain{display:flex;align-items:stretch;border:1px solid var(--line);border-radius:6px;overflow-x:auto;background:var(--surface-2)}
.link{flex:1 1 0;min-width:130px;padding:9px 14px;position:relative;display:flex;flex-direction:column;gap:2px}
.link+.link{border-left:1px solid var(--line)}
.link+.link::before{content:"";position:absolute;left:-6px;top:50%;width:10px;height:10px;background:var(--surface-2);border-top:1px solid var(--line-2);border-right:1px solid var(--line-2);transform:translateY(-50%) rotate(45deg)}
.link .k{font:600 10px/1 var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.link .v{font:700 17px/1.1 var(--display)}
.link .v small{font:500 12px var(--body);color:var(--muted)}
.link .u{font-size:11px;color:var(--warn);font-weight:600}
.link .u.ok{color:var(--good)}
.tblhead{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.tblhead h2{font:700 14px var(--display);text-transform:uppercase;margin:0}
.search{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--line-2);border-radius:5px;background:var(--surface);color:var(--ink);min-width:240px}
.tblwrap{overflow:auto;border:1px solid var(--line);border-radius:6px;max-height:560px}
table{border-collapse:collapse;width:100%;min-width:1180px;font-size:12px}
th{font:600 10px/1.2 var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);text-align:left;padding:8px 10px;background:var(--surface-2);border-bottom:1px solid var(--line);white-space:nowrap;position:sticky;top:0;z-index:1}
td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:middle;color:var(--ink-2)}
tr:last-child td{border-bottom:0}
td.r,th.r{text-align:right}
td .code{font:500 11px var(--mono);color:var(--muted);display:block}
td .nm{color:var(--ink);font-weight:600}
td.m{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.mini{display:inline-flex;width:56px;height:7px;background:var(--ns);border-radius:2px;overflow:hidden;vertical-align:middle;margin-right:6px}
.mini span{background:var(--good)}
.ctag{font-size:11px;color:var(--accent);font-weight:600}
.ctag.none{color:var(--muted);font-weight:400}
.foot{display:flex;flex-direction:column;gap:3px;font-size:11px;color:var(--muted)}
@media (max-width:1240px){.grid{grid-template-columns:1fr 1fr}}
@media (max-width:680px){.grid{grid-template-columns:1fr}.kpis{width:100%}.kpi{flex:1;min-width:0}.ms,.ms>button,.search{width:100%;min-width:0}.reset{margin-left:0}h1{font-size:22px}.slide{padding:14px}.child{grid-template-columns:14px 80px minmax(0,1fr) 80px}}
@media (prefers-reduced-motion:no-preference){.track .act,.sbar span,.stack span,.split div{transition:width .35s ease}}

#pvCards.gcards{grid-template-columns:repeat(3,minmax(0,1fr))}
@media (max-width:1000px){#pvCards.gcards{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){#pvCards.gcards{grid-template-columns:1fr}}

.gcard.gclick{cursor:pointer;transition:box-shadow .15s,border-color .15s}.gcard.gclick:hover{box-shadow:0 0 0 2px var(--accent)}.gcard.gclick:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

.bid{font:600 11px var(--mono);color:var(--accent);margin-left:4px}.btag{font:700 9px var(--body);padding:0 5px;border-radius:7px;border:1px solid var(--line-2);color:var(--muted);vertical-align:1px}.btag.r{border-color:var(--warn);color:var(--warn)}.btag.c{border-color:var(--accent);color:var(--accent)}

.ejtiles{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}
.ejt{border:1px solid var(--line);border-radius:6px;padding:8px 12px;background:var(--surface-2);display:flex;flex-direction:column;gap:1px;min-width:0}
.ejt span{font:600 11px var(--body);color:var(--muted);text-transform:uppercase;letter-spacing:.04em} .ejt b{font:800 26px/1.1 var(--display);color:var(--ink)} .ejt small{font-size:11px;color:var(--muted)}
.ejt.r{border-color:var(--crit)} .ejt.r b{color:var(--crit)} .ejt.a{border-color:var(--warn)} .ejt.a b{color:var(--warn)} .ejt.g b{color:var(--good)}
.ejstrip{display:grid;grid-template-columns:repeat(11,minmax(0,1fr));gap:4px}
.ejs{position:relative;border:1px solid var(--line);border-top:3px solid var(--accent);border-radius:4px;padding:5px 6px;display:flex;flex-direction:column;gap:3px;min-width:0}
.ejs.r{border-top-color:var(--brand-2)} .ejs.first{margin-left:6px}
.ejs .n{font:700 10px var(--body);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis} .ejs .b{height:5px;border-radius:3px;background:var(--ns);overflow:hidden} .ejs .b i{display:block;height:100%;background:var(--good)}
.ejs .v{font:500 10px var(--mono);color:var(--muted)} .ejs .v b{color:var(--ink)} .ejs .dot{position:absolute;top:5px;right:5px;width:7px;height:7px;border-radius:50%} .ejs .dot.r{background:var(--crit)} .ejs .dot.a{background:var(--warn)}
.ejlg{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted)} .ejlg i{display:inline-block;width:14px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px;border:1px solid var(--line-2);background:var(--surface)} .ejlg i.r{background:var(--crit-soft);border-color:var(--crit)} .ejlg i.a{background:var(--warn-soft);border-color:var(--warn)}
.tk{color:var(--good);font-weight:800}
.ejA,.ejB{min-width:0;width:100%;border-collapse:separate;border-spacing:2px}
.ejA th,.ejB th{position:static;text-transform:none;letter-spacing:0;font:700 10.5px var(--body);color:var(--ink-2);background:none;padding:4px 6px;text-align:center;white-space:nowrap}
.ejA thead th.gC,.ejB thead th{border-bottom:2px solid var(--line-2)} .ejA thead th.gC{color:var(--accent)} .ejA thead th.gR{color:var(--brand-2)} .ejA th.first,.ejA td.first{border-left:2px solid var(--line-2)}
.ejA tbody th{text-align:left;font:700 13px var(--display);color:var(--ink)}
.ejc{text-align:center;font:500 12px var(--mono);color:var(--ink-2);border:1px solid var(--line);border-radius:4px;padding:7px 4px;cursor:pointer;background:var(--surface)} .ejc b{color:var(--ink)}
.ejc.r{background:var(--crit-soft);border-color:var(--crit)} .ejc.r b{color:var(--crit)} .ejc.a{background:var(--warn-soft);border-color:var(--warn)} .ejc.a b{color:var(--warn)}
.ejc.nd{color:var(--muted);cursor:default;border-style:dashed} .ejc.sel{outline:3px solid var(--accent);outline-offset:-1px} .ejc:hover:not(.nd){border-color:var(--accent)}
.ejblk{display:flex;flex-direction:column;gap:6px;margin-top:6px} .ejbh{display:flex;gap:10px;align-items:baseline} .ejbh b{font:800 13px var(--display);text-transform:uppercase;letter-spacing:.04em}
.ejwrap{max-height:720px;overflow:auto}
.ejB thead th{position:sticky;top:0;background:var(--surface);z-index:1}
.ejB td{padding:3px 5px;font-size:11.5px;border:0}
.ejB td.bi{min-width:280px;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:left} .ejB td.bi a{font:600 11px var(--mono);color:var(--accent)} .ejB th.bi{text-align:left}
.ejb{text-align:center;font:500 11px var(--mono);border:1px solid var(--line);border-radius:3px;background:var(--surface);min-width:62px;white-space:nowrap} .ejb a{color:var(--ink-2);text-decoration:none;display:block} .ejb a:hover{text-decoration:underline}
.ejb.r{background:var(--crit-soft);border-color:var(--crit)} .ejb.r a,.ejb.r span{color:var(--crit);font-weight:700} .ejb.a{background:var(--warn-soft);border-color:var(--warn)} .ejb.a a,.ejb.a span{color:var(--warn);font-weight:700}
.ejb.nd{border:1px dashed var(--line);background:none} .ejb.hk,.ejB th.hk{box-shadow:inset 0 0 0 2px var(--accent)}
tr.ejg td{background:var(--surface-2);font:700 12px var(--display);color:var(--ink);padding:6px 8px;cursor:pointer;text-align:left} tr.ejg .note{font-weight:400;margin-left:6px}
tr.ejg .cv{display:inline-block;width:0;height:0;border:5px solid transparent;border-top-color:var(--ink-2);margin-right:6px;vertical-align:1px} tr.ejg[aria-expanded="false"] .cv{transform:rotate(-90deg)}
.pg{min-width:110px} .pgb{display:inline-block;width:60px;height:6px;border-radius:3px;background:var(--ns);overflow:hidden;vertical-align:1px;margin-right:6px} .pgb i{display:block;height:100%;background:var(--good)}
.ejpop label.yr{font-weight:700;border-top:1px solid var(--line);margin-top:2px;padding-top:4px} .ejpop label.mo{padding-left:22px}
@media (max-width:1100px){.ejtiles{grid-template-columns:repeat(3,minmax(0,1fr))}.ejstrip{grid-template-columns:repeat(4,minmax(0,1fr))}.ejs.first{margin-left:0}}
@media (max-width:640px){.ejtiles{grid-template-columns:repeat(2,minmax(0,1fr))}.ejstrip{grid-template-columns:repeat(2,minmax(0,1fr))}.ejB td.bi{min-width:180px}}

.ejB{width:auto!important}.ejB td.bi{display:block;width:420px;max-width:420px}.ejn{font-size:11.5px;color:var(--ink)}.ejc,.ejA td{text-align:center!important}.ejB td{vertical-align:middle}
@media (max-width:640px){.ejB td.bi{width:200px;max-width:200px}}
</style><style>
.kpi .meta b{font-weight:700;color:var(--ink)}
.kpi .meta b.r{color:var(--crit)}
.kpi .meta b.w{color:var(--warn)}
.red{color:var(--crit)!important;font-weight:700}
.facts strong.r,.link .u.r{color:var(--crit)}
td.zero{color:var(--crit);font-weight:700}
tr.unl td{background:var(--crit-soft)}
tr.unl td:first-child{box-shadow:inset 3px 0 0 var(--crit)}
.tabs{display:flex;gap:4px;border:1px solid var(--line-2);border-radius:6px;padding:3px;background:var(--surface-2)}
.tabs button{font:600 12px var(--body);border:0;background:none;color:var(--ink-2);padding:6px 12px;border-radius:4px;cursor:pointer}
.tabs button[aria-pressed="true"]{background:var(--surface);color:var(--ink);box-shadow:0 0 0 1px var(--line-2)}
.tabs button .cnt{font:600 11px var(--mono);color:var(--crit);margin-left:4px}
.tchip{font:700 10px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;padding:3px 6px;border-radius:3px;background:var(--crit-soft);color:var(--crit);white-space:nowrap}
.utypes{display:flex;gap:6px;flex-wrap:wrap}
.utypes button{font:600 11px var(--body);border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);border-radius:12px;padding:4px 10px;cursor:pointer}
.utypes button.on{border-color:var(--crit);background:var(--crit-soft);color:var(--crit)}
.utypes button b{font-family:var(--mono);margin-left:4px}
td.reason{color:var(--crit);font-size:11px}
td .tt{display:block;max-width:520px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.l2{font-size:11px;color:var(--ink-2);max-width:200px}
.note{font-size:11px;color:var(--muted)}
.mo-sep{border-top:1px solid var(--line);margin:4px 0}
.needbtn{font:700 11px var(--body);letter-spacing:0;text-transform:none;border:1px solid var(--crit);color:var(--crit);background:var(--crit-soft);border-radius:12px;padding:3px 9px;cursor:pointer}
.needbtn[aria-pressed="true"]{background:var(--crit);color:var(--on-solid)}
.plan{display:grid;grid-template-columns:auto 1fr auto auto;gap:4px 10px;font-size:12px;align-items:center}
.plan .h{font:600 10px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.plan .w{font:600 11px var(--mono);color:var(--ink-2)}
.plan .bar{display:flex;height:8px;background:var(--crit-soft);border-radius:2px;overflow:hidden}
.plan .bar span{background:var(--good)}
.plan .n{font:500 11px var(--mono);text-align:right;color:var(--muted)}
.plan .n.r{color:var(--crit);font-weight:700}
.reg{gap:10px}
.regbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tog{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--ink-2);cursor:pointer}
.tog input{accent-color:var(--crit)}
.regwrap{max-height:640px}
.regt{min-width:1180px}
.regt tr.grp td{background:var(--surface-2);cursor:pointer;font-weight:600;color:var(--ink);border-bottom:1px solid var(--line-2)}
.regt tr.grp td .cv{display:inline-block;width:7px;height:7px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(45deg);margin:0 10px 2px 2px;transition:transform .15s}
.regt tr.grp.closed td .cv{transform:rotate(-45deg)}
.regt tr.grp .gm{font:500 11px var(--mono);color:var(--muted);margin-left:10px}
.regt tr.grp .gm b{color:var(--crit)}
.regt tr.grp.nol2 td{background:var(--crit-soft);color:var(--crit)}
.regt a{color:var(--accent);font:600 12px var(--mono);text-decoration:none;border-bottom:1px solid currentColor}
.regt a:hover{color:var(--brand)}
td.late{color:var(--crit);font-weight:800;font-family:var(--mono)}
td .tt2{display:block;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.regbar .ms>button{min-width:220px}
.regbar .pop{min-width:320px}
.ribbon{display:grid;grid-template-columns:auto minmax(0,1.3fr) minmax(0,1.2fr);gap:14px;align-items:stretch}
.rtot{display:flex;gap:16px;align-items:center;padding:10px 14px;border:1px solid var(--line);border-radius:6px;background:var(--surface-2)}
.rtot div{display:flex;flex-direction:column}
.rtot b{font:800 24px/1 var(--display)}
.rtot span{font:600 10px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-top:4px}
.rtot .r b{color:var(--crit)}
.rgrp{display:flex;flex-direction:column;gap:6px;min-width:0}
.rlab{font:600 10px var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.firms{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:6px}
.firm,.top{font:inherit;text-align:left;border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:8px 10px;cursor:pointer;display:flex;flex-direction:column;gap:4px;color:var(--ink)}
.firm:hover,.top:hover{border-color:var(--crit)}
.firm.on,.top.on{border-color:var(--crit);box-shadow:0 0 0 1px var(--crit) inset;background:var(--crit-soft)}
.firm .fn{font:700 12px var(--body)}
.firm .fv{font:700 15px var(--mono)} .firm .fv b{color:var(--crit)} .firm .fv small{font-weight:400;color:var(--muted)}
.firm .fb{height:5px;background:var(--ns);border-radius:2px;overflow:hidden} .firm .fb span{display:block;height:100%;background:var(--crit)}
.firm .fp{font:500 10px var(--mono);color:var(--muted)}
.tops{display:flex;flex-direction:column;gap:5px}
.top{flex-direction:row;align-items:center;gap:8px;padding:6px 10px}
.top .rk{font:700 11px var(--mono);color:var(--muted);width:14px}
.top .tn{font:600 12px var(--body);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.top .tv{font:700 12px var(--mono);color:var(--crit);white-space:nowrap}
.top .tv small{font-weight:400;color:var(--muted)}
.rat tr.pd td{background:var(--crit-soft)}
.rat tr.pd td:first-child{box-shadow:inset 3px 0 0 var(--crit)}
.rat tr.cl td{color:var(--muted);opacity:.6}
.rat tr.cl td .tt2{color:var(--muted)}
.ty{font:700 10px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;padding:3px 6px;border-radius:3px;white-space:nowrap}
.ty.A{background:var(--accent-soft);color:var(--accent)} .ty.R{background:var(--warn-soft);color:var(--warn)} .ty.I{background:var(--crit-soft);color:var(--crit)}
.fmt{font:600 11px var(--body);color:var(--ink-2)}
@media (max-width:1100px){.ribbon{grid-template-columns:1fr}}
.top .org{font-weight:400;color:var(--muted)}
.firms{grid-template-columns:repeat(auto-fit,minmax(104px,1fr))}
.amb{color:var(--warn);font-weight:700}
.amb-t input{accent-color:var(--warn)}
.pvbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.health{margin-left:auto;display:flex;align-items:center;gap:10px;border:1px solid var(--line-2);border-radius:6px;padding:7px 12px;background:var(--surface-2)}
.health .hdot{width:22px;height:22px;border-radius:50%;flex:none}
.health b{font:700 13px var(--display)} .health small{display:block;font-size:11px;color:var(--muted)}
.health.r{border-color:var(--crit);background:var(--crit-soft)} .health.a{border-color:var(--warn);background:var(--warn-soft)} .health.g{border-color:var(--good);background:var(--good-soft)}
.health.r .hdot{background:var(--crit)} .health.a .hdot{background:var(--warn)} .health.g .hdot{background:var(--good)}
.gcards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) minmax(0,2.1fr);gap:10px;align-items:stretch}
.dgrp{border:1px dashed var(--line-2);border-radius:8px;padding:8px;display:flex;flex-direction:column;gap:6px;min-width:0}
.dgrp>.dl{font:600 10px var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);text-align:center}
.dgrp>.dc{display:grid;grid-template-columns:1fr 1fr;gap:10px;flex:1}
.gcard{border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:10px 10px 12px;display:flex;flex-direction:column;gap:8px;min-width:0}
.gcard.behind{border-top:3px solid var(--crit)} .gcard.ahead{border-top:3px solid var(--good)}
.gcard h3{margin:0;text-align:center;font:700 13px var(--display);color:var(--ink)}
.gcard svg{width:100%;max-width:230px;margin:0 auto;display:block}
.gcard .gt{fill:var(--muted);font:600 9px var(--mono)}
.gcard .gv{fill:var(--ink);font:800 20px var(--display)}
.gmet{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}
.gm{background:var(--surface-2);border-radius:4px;padding:6px 4px;text-align:center;display:flex;flex-direction:column;gap:2px}
.gm small{font-size:10px;color:var(--muted);line-height:1.2;min-height:24px}
.gm b{font:800 19px var(--display);color:var(--ink)}
.gm em{font:700 10px var(--body);font-style:normal}
.gm.good{background:var(--good-soft)} .gm.good b,.gm.good em{color:var(--good)}
.gm.bad{background:var(--crit-soft)} .gm.bad b,.gm.bad em{color:var(--crit)}
.ov{display:flex;flex-direction:column;gap:4px}
.ov .ol{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)} .ov .ol b{color:var(--ink);font-family:var(--mono)}
.ov .ob{position:relative;height:8px;background:var(--ns);border-radius:2px}
.ov .ob span{position:absolute;left:0;top:0;bottom:0;background:var(--accent);border-radius:2px}
.ov .ob i{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink)}
.hleg{display:flex;gap:8px 18px;flex-wrap:wrap;font-size:11px;color:var(--ink-2);align-items:center}
.hleg .hd{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.hd.g{background:var(--good)} .hd.a{background:var(--warn)} .hd.r{background:var(--crit)}
@media (max-width:1240px){.gcards{grid-template-columns:repeat(3,minmax(0,1fr))}.dgrp{grid-column:1/-1}}
@media (max-width:760px){.gcards{grid-template-columns:1fr}.dgrp>.dc{grid-template-columns:1fr}.health{margin-left:0}}
.gcards{grid-template-columns:repeat(4,minmax(0,1fr))}
.gcard svg{max-width:260px}
.gcard .gt{fill:var(--muted);font:600 9px var(--mono)}
.gcard .od{fill:var(--surface);font:700 14px var(--mono)}
.gcard .ol2{fill:var(--muted);font:600 9px var(--body);letter-spacing:.1em;text-transform:uppercase}
.vpill{align-self:center;font:700 11px var(--body);padding:4px 10px;border-radius:12px;background:var(--surface-2);color:var(--muted)}
.vpill.good{background:var(--good-soft);color:var(--good)} .vpill.bad{background:var(--crit-soft);color:var(--crit)}
.gm.act{box-shadow:inset 0 -3px 0 var(--ink)} .gm.pl{box-shadow:inset 0 -3px 0 var(--planned)}
.glg{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;font-size:10px;color:var(--muted)}
.glg i{display:inline-block;width:10px;height:6px;border-radius:2px;margin-right:4px;vertical-align:1px}
.glg .ga{background:var(--ink)} .glg .gp{background:var(--planned)} .glg .go{background:var(--ns)}
@media (max-width:1240px){.gcards{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.gcards{grid-template-columns:1fr}}

.gcard{cursor:pointer;transition:box-shadow .15s}
.gcard:hover{box-shadow:0 0 0 1px var(--accent)}
.gcard.sel{box-shadow:0 0 0 2px var(--accent)}
.ptabs{display:flex;gap:0;align-items:stretch;flex-wrap:wrap;border-bottom:2px solid var(--brand);margin-top:4px}
.ptab{font:600 13px var(--body);border:0;background:var(--surface-2);color:var(--ink-2);padding:10px 22px;cursor:pointer;border-right:2px solid var(--surface);border-radius:5px 5px 0 0}
.ptab[aria-selected="true"]{background:var(--brand);color:var(--on-solid)}
.ptabs .search{margin-left:auto;align-self:center;margin-bottom:6px}
.lanes{display:flex;flex-direction:column;gap:8px}
.lane{border:1px solid var(--line);border-radius:6px;overflow:hidden}
.lane-head{display:flex;align-items:center;gap:8px;padding:9px 12px;background:var(--surface-2);font:700 13px var(--display);color:var(--ink);cursor:pointer}
.lane-head .cv{display:inline-block;width:7px;height:7px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(45deg);margin:0 4px 3px 2px;transition:transform .15s}
.lane-head[aria-expanded="false"] .cv{transform:rotate(-45deg)}
.lane-head .lic{width:20px;height:20px;border-radius:50%;display:inline-grid;place-items:center;font:800 12px var(--body);color:var(--on-solid)}
.ldone .lic{background:var(--good)} .lup .lic{background:var(--accent)} .llate .lic{background:var(--crit)}
.llate{background:var(--crit-soft);color:var(--crit)}
.lane-head .badge{margin-left:auto;font:600 11px var(--mono);padding:3px 8px;border-radius:4px;background:var(--surface);color:var(--ink-2);border:1px solid var(--line)}
.lanewrap{border:0;border-radius:0;max-height:520px}
.lanet{min-width:1100px}
.lanet tr.pd td{background:var(--crit-soft)}
.lanet tr.pd td:first-child{box-shadow:inset 3px 0 0 var(--crit)}
.lanet td.late{color:var(--crit);font-weight:700}
b.late{color:var(--crit);font:800 12px var(--mono)}
.tt3{display:block;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:var(--ink-2)}
.dpl{font:700 10px var(--body);padding:3px 6px;border-radius:3px;white-space:nowrap;color:var(--on-solid)}
.dpl.FIT-OOB{background:var(--brand-2)} .dpl.FIT-CFG{background:var(--brand)} .dpl.GAP{background:var(--accent)} .dpl.TBD{background:var(--plan)}
.more{padding:6px 0}
@media (max-width:640px){.ptab{flex:1;padding:9px 6px}.ptabs .search{margin:6px 0;width:100%}}

.lnk2{text-align:center;font-size:11px;color:var(--muted)} .lnk2 b{font-family:var(--mono);color:var(--ink)} .lnk2 b.red{color:var(--crit)}
.seg{display:flex;align-self:center;margin:0 8px 6px auto;border:1px solid var(--line-2);border-radius:6px;overflow:hidden}
.seg button{font:600 12px var(--body);border:0;background:var(--surface);color:var(--ink-2);padding:6px 10px;cursor:pointer}
.seg button+button{border-left:1px solid var(--line-2)}
.seg button[aria-pressed="true"]{background:var(--brand);color:var(--on-solid)}
.seg:not([hidden])+.search{margin-left:0}
.uchip{font:700 10px/1 var(--body);letter-spacing:.04em;padding:3px 6px;border-radius:3px;background:var(--warn-soft);color:var(--warn);white-space:nowrap}

.kpi .meta b{font:700 12px var(--body)}
.seg[hidden]{display:none!important}

.tcard{border:1px solid var(--line);border-left:4px solid var(--ns);border-radius:6px;background:var(--surface);padding:10px 12px;display:flex;flex-direction:column;gap:6px;margin-top:8px}
.tcard.o-r{border-left-color:var(--crit)} .tcard.o-a{border-left-color:var(--warn)} .tcard.o-g{border-left-color:var(--good)}
.tcard p{font-size:14px!important} .tcard p a,.wl a{color:var(--accent);font-family:var(--mono);font-size:12px}
.tch{display:flex;gap:8px;align-items:center;flex-wrap:wrap} .tch b{font:700 15px var(--display);color:var(--ink)}
.stg{font:700 10px var(--body);text-transform:uppercase;letter-spacing:.05em;padding:2px 8px;border-radius:9px;background:var(--surface-2);border:1px solid var(--line-2);color:var(--ink-2)}
.stg.s0{color:var(--muted)} .stg.s1{color:var(--brand-2)} .stg.s2{color:var(--accent);border-color:var(--accent)} .stg.s3{color:var(--brand);border-color:var(--brand)} .stg.s4{color:var(--good);border-color:var(--good)}
.olk{display:inline-flex;align-items:center;gap:5px;font:700 11px var(--body)} .olk i{width:9px;height:9px;border-radius:50%;background:var(--ns)}
.olk.r{color:var(--crit)} .olk.r i{background:var(--crit)} .olk.a{color:var(--warn)} .olk.a i{background:var(--warn)} .olk.g{color:var(--good)} .olk.g i{background:var(--good)}
.twhy{font-size:12px;color:var(--muted)}
.sboard{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px}
.scol{display:flex;flex-direction:column;gap:5px;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:6px;min-height:220px}
.sch{font:700 10px var(--body);text-transform:uppercase;letter-spacing:.05em;color:var(--muted);display:flex;justify-content:space-between;gap:4px;padding-bottom:4px;border-bottom:1px solid var(--line)} .sch span{font-family:var(--mono);color:var(--ink-2)}
.bchip{display:flex;gap:5px;align-items:flex-start;font:600 11px/1.25 var(--body);color:var(--ink);padding:5px 6px;border-radius:5px;background:var(--surface-2);border:1px solid var(--line);transition:opacity .4s,filter .4s}
.bchip i{flex:none;width:8px;height:8px;border-radius:50%;margin-top:3px;background:var(--ns)} .bchip.r i{background:var(--crit)} .bchip.a i{background:var(--warn)} .bchip.g i{background:var(--good)}
.bchip.r{border-color:var(--crit-soft)} .bchip.dim{opacity:.28;filter:grayscale(1)}
.sempty{font-size:11px;color:var(--muted);text-align:center;padding-top:6px}
.slg i.o{border-radius:50%;width:9px;height:9px} .slg i.o.r{background:var(--crit)} .slg i.o.a{background:var(--warn)} .slg i.o.g{background:var(--good)}
.wl{display:flex;flex-direction:column;gap:6px}
.wli{display:grid;grid-template-columns:90px minmax(0,1fr) auto;gap:2px 10px;align-items:baseline;border-bottom:1px solid var(--line);padding:6px 0}
.wli b{font:700 13px var(--display);color:var(--ink)} .wli .note{grid-column:3;text-align:right} .wli .twhy{grid-column:2/4} .wli .wnx{grid-column:2/4;font:600 11px var(--mono);color:var(--ink-2)}
.ocard{border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:8px 12px;margin-top:8px;display:flex;flex-direction:column;gap:4px} .ocard>b{font:700 14px var(--display)} .ocard p{font-size:14px!important}
.olg{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--muted)} .olg i{display:inline-block;width:12px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.orow{display:grid;grid-template-columns:90px minmax(0,1fr);gap:10px;align-items:center;padding:4px 0;border-bottom:1px solid var(--line)}
.obars{display:flex;flex-direction:column;gap:4px} .obr{display:grid;grid-template-columns:38px minmax(0,1fr) 70px;gap:8px;align-items:center}
.obl{font:600 10px var(--body);color:var(--muted);text-transform:uppercase} .obr em{font:600 11px var(--mono);font-style:normal;color:var(--ink-2)}
.otrack{display:flex;height:12px;border-radius:3px;overflow:hidden;background:var(--surface)} .otrack i{display:block;height:100%;width:0;transition:width .7s ease} .svp.on .otrack i{width:var(--w)}
@media (max-width:900px){.sboard{grid-template-columns:minmax(0,1fr)}.scol{min-height:0}.wli{grid-template-columns:80px minmax(0,1fr)}.wli .note{grid-column:2;text-align:left}.orow{grid-template-columns:minmax(0,1fr)}}
@media (prefers-reduced-motion:reduce){.bchip,.otrack i{transition:none!important}}

.sty-prog{position:sticky;top:0;z-index:5;display:flex;gap:4px;padding:8px 0;background:var(--surface);border-bottom:1px solid var(--line);overflow-x:auto;scrollbar-width:none}
.sty-prog .rdot{width:auto;height:auto;border-radius:0;border:0;border-top:3px solid var(--line);background:none;flex:1 1 0;min-width:44px;padding:6px 4px 0;font:700 10px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);display:block;text-align:left}
.sty-prog .rdot.done{border-top-color:var(--brand-2);color:var(--ink-2)} .sty-prog .rdot.on{border-top-color:var(--accent);color:var(--accent);background:none}
.sty-prog .rdot:hover{color:var(--accent)}
.sty .sty-stick{top:64px}
.sty .sty-stage{min-height:540px;background:var(--surface)}
.sstep{min-height:78vh;padding:28px 6px 28px 18px}
.sstep h3{font-size:24px;line-height:1.2}
.sstep h3.hero{font:800 40px/1.08 var(--display);letter-spacing:-.015em} .sstep h3.hero.sm{font-size:30px}
.sstep p.stand{font-size:18px;line-height:1.5;color:var(--ink-2)}
.sstep p.prose{font-size:16px;line-height:1.65;color:var(--ink-2)}
.pq{margin:6px 0;padding:6px 0 6px 16px;border-left:4px solid var(--accent);display:flex;flex-direction:column;gap:2px}
.pq b{font:800 34px/1 var(--display);color:var(--ink)} .pq span{font-size:13px;color:var(--muted)}
.nx{font-size:14px!important;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap} .nx>span:first-child{font:700 10px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--accent);border:1px solid var(--accent);border-radius:9px;padding:1px 7px}
.tdet summary{cursor:pointer;font:600 13px var(--body);color:var(--accent);padding:4px 0} .tdet[open] summary{margin-bottom:2px}
.olist{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:14px;color:var(--ink-2)}
.jmap{position:relative;height:400px;margin-top:4px}
.jroad{position:absolute;left:2%;right:2%;top:50%;height:10px;margin-top:-5px;border-radius:5px;background:linear-gradient(90deg,var(--ns),var(--planned) 45%,var(--accent-soft) 80%,var(--good-soft))}
.jtick{position:absolute;top:50%;width:2px;height:22px;margin:-11px 0 0 -1px;background:var(--line-2)}
.jst{position:absolute;top:0;transform:translateX(-50%);text-align:center;display:flex;flex-direction:column;align-items:center;gap:2px;width:18%}
.jst .js{display:none}
.jst b{font:700 10px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.jcnt{font:800 22px var(--display);color:var(--ink);opacity:0;transform:translateY(-4px);transition:opacity .4s,transform .4s} .m-cnt .jcnt{opacity:1;transform:none}
.jdot{position:absolute;width:0;height:0;transition:opacity .5s,filter .5s}
.jdot i{position:absolute;left:-9px;top:-9px;width:18px;height:18px;border-radius:50%;border:3px solid var(--surface);background:var(--ns);box-shadow:0 1px 3px rgba(0,0,0,.18);transition:transform .5s}
.jdot.r i{background:var(--crit)} .jdot.a i{background:var(--warn)} .jdot.g i{background:var(--good)}
.jdot span{position:absolute;left:14px;top:-8px;width:max-content;max-width:104px;font:600 11px/1.2 var(--body);color:var(--ink);background:var(--surface);padding:1px 4px;border-radius:3px;opacity:0;transform:translateX(-4px);transition:opacity .4s,transform .4s;pointer-events:none}
.jdot.lab span{opacity:1;transform:none} .jdot.lab i{transform:scale(1.25)}
.jdot.dim{opacity:.18;filter:grayscale(1)}
.jdot:nth-child(n){} .jlg{margin-top:4px}
.cal{display:flex;flex-direction:column;gap:4px;margin-top:4px}
.crow{display:grid;grid-template-columns:150px minmax(0,1fr);gap:8px;align-items:center}
.crow .sl{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px}
.cgrid{display:grid;grid-template-columns:repeat(14,minmax(0,1fr));height:26px;align-items:center;border-bottom:1px solid var(--line)}
.cgrid>span{display:grid;place-items:center;height:100%}
.chd .cgrid{height:30px;border-bottom:1px solid var(--line-2)} .chd .cgrid span{font:700 11px var(--mono);color:var(--ink-2);display:flex;flex-direction:column;line-height:1.1} .chd em{font:500 9px var(--body);font-style:normal;color:var(--muted)} .chd .wk{opacity:.5}
.cev{display:block;width:var(--s);height:var(--s);border-radius:50%;background:var(--ns);opacity:.85} .cev.r{background:var(--crit)} .cev.a{background:var(--warn)} .cev.g{background:var(--good)}
.cev.km{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--ink-2)}
.slg i.cring{width:10px;height:10px;border-radius:50%;background:var(--ns);box-shadow:0 0 0 2px var(--surface),0 0 0 3px var(--ink-2)}
.svp.on .cev.pulse{animation:cpulse 1.8s ease-in-out infinite}
@keyframes cpulse{0%,100%{transform:scale(1)}50%{transform:scale(1.25)}}
.prb{display:flex;flex-direction:column;gap:6px;margin:10px 0 18px}
.prh{display:flex;gap:10px;align-items:baseline} .prh b{font:800 40px/1 var(--display);color:var(--accent)} .prh span{font-size:13px;color:var(--muted)}
.prt{display:flex;height:34px;border-radius:5px;overflow:hidden;background:var(--surface-2)} .prt i{display:block;height:100%;width:0;transition:width .9s ease} .svp.on .prt i{width:var(--w)}
.prt i.in{background:var(--accent)} .prt i.out{background:var(--ns)}
.prl{display:flex;justify-content:space-between;font:600 11px var(--mono);color:var(--ink-2)}
@media (max-width:900px){.sstep{min-height:0;padding:20px 4px 20px 12px}.sstep h3.hero{font-size:30px}.sstep h3.hero.sm{font-size:24px}.jmap{height:380px}.jdot span{max-width:70px;font-size:10px}.jst b{font-size:8px}.jst .jl{display:none}.jst .js{display:inline}.crow{grid-template-columns:80px minmax(0,1fr)}.sty-prog .rdot{min-width:52px}}
@media (prefers-reduced-motion:reduce){.jdot,.jdot i,.jdot span,.jcnt,.prt i{transition:none!important}.svp.on .cev.pulse{animation:none}}

.deck{gap:10px}
.dkfil{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dkpre{font:600 12px var(--body);padding:5px 11px;border-radius:14px;border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);cursor:pointer} .dkpre:hover{border-color:var(--accent);color:var(--accent)}
.dkf{font-weight:700;color:var(--warn)}
.dtab tr.unlr th,.dtab tr.unlr td{background:var(--warn-soft)} .dtab tr.unlr th{color:var(--warn);font-style:italic}
.l2t.dense th,.l2t.dense td{padding:3px 8px} .l2t.dense .dbar{margin-top:2px}
.dl2.unl{color:var(--warn);font-style:italic}
.ftag{display:inline-block;font:700 9px var(--body);text-transform:uppercase;letter-spacing:.03em;padding:0 5px;border-radius:7px;background:var(--accent-soft);color:var(--accent);vertical-align:1px} .tt-fl{position:absolute;right:80px;bottom:30px;font:700 13px var(--body);color:#FFD27A}
.kp.x{border-color:var(--crit);color:var(--crit);text-decoration:line-through}
.deck.fs .dkfil{display:none}
.dkbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dkbtn{width:32px;height:32px;border-radius:50%;border:1px solid var(--line-2);background:var(--surface);color:var(--ink);font:700 18px/1 var(--body);cursor:pointer}
.dkbtn:hover:not(:disabled){border-color:var(--accent);color:var(--accent)} .dkbtn:disabled{opacity:.35;cursor:default}
.dkcount{font:700 12px var(--mono);color:var(--ink-2);min-width:52px;text-align:center}
.dkthumbs{display:flex;gap:4px;flex:1;min-width:0;overflow-x:auto;scrollbar-width:thin;padding:2px}
.dth{flex:none;display:flex;gap:6px;align-items:center;font:600 11px var(--body);color:var(--ink-2);background:var(--surface-2);border:1px solid var(--line);border-radius:5px;padding:5px 9px;cursor:pointer;white-space:nowrap}
.dth b{font:700 10px var(--mono);color:var(--muted)} .dth.on{background:var(--brand);border-color:var(--brand);color:var(--on-solid)} .dth.on b{color:var(--on-solid)}
.dth:focus-visible,.dkbtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.dkstage{position:relative;width:100%;overflow:hidden;--sc:1}
.dslide{display:none} .dslide.on{display:block}
.dkstage:not(.flow) .slide-d{width:1280px;height:720px;transform:scale(var(--sc));transform-origin:top left}
.slide-d{background:var(--surface);border:1px solid var(--line-2);border-radius:6px;box-shadow:0 2px 10px rgba(14,27,61,.08);overflow:hidden;position:relative}
.slide-d::before{content:"";position:absolute;left:0;top:0;right:0;height:6px;background:linear-gradient(90deg,var(--brand),var(--accent))}
.sd-in{height:100%;display:flex;flex-direction:column;padding:30px 40px 18px;gap:12px}
.sd-h{display:flex;flex-direction:column;gap:6px}
.sd-k{font:700 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--accent)}
.sd-h h2{margin:0;font:800 34px/1.05 var(--display);color:var(--ink);letter-spacing:-.01em} .sd-h h2 span{font-size:20px;font-weight:600;color:var(--muted)}
.sd-t{margin:0;font-size:15px;color:var(--ink-2)} .sd-t b.r,.kv .late,.late{color:var(--crit)}
.sd-b{flex:1;min-height:0;overflow:hidden}
.sd-f{display:flex;justify-content:space-between;gap:16px;font-size:11px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px}
.kpis-d{display:flex;gap:6px;align-items:stretch;margin-top:4px}
.kpis-d>div{flex:1;border:1px solid var(--line);border-radius:6px;padding:6px 10px;display:flex;flex-direction:column;background:var(--surface-2)}
.kpis-d>div b{font:800 24px/1.1 var(--display);color:var(--ink)} .kpis-d>div span{font-size:11px;color:var(--muted)} .kpis-d>div.r b{color:var(--crit)} .kpis-d>div.r{border-color:var(--crit)}
.kpis-d>.sep{flex:0 0 1px;padding:0;border:0;background:var(--line-2)}
.wsgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.08fr);gap:22px;height:100%;align-items:start}
.kcols{height:100%} .kcols .kpan{column-count:2;column-gap:26px;height:100%}
.dtab{width:100%;min-width:0;border-collapse:collapse;font-size:13px;table-layout:fixed}
.dtab th{position:static;background:none;letter-spacing:0;text-transform:none;font:600 12.5px/1.25 var(--body);color:var(--ink);padding:6px 8px}
.l2t col.c1{width:46%} .l2t col.c2{width:22%} .ovt col.c1{width:22%} .ovt col.c2{width:8%} .ovt col.c3{width:30%}
.dtab th,.dtab td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
.dtab thead th{font:700 10px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);border-bottom:2px solid var(--line-2)}
.dtab tbody th{font:600 12.5px/1.25 var(--body);color:var(--ink);white-space:normal;overflow-wrap:anywhere} .dtab .m{text-align:center;font-family:var(--mono)}
.dtab tr.emp th,.dtab tr.emp td{color:var(--muted);opacity:.55}
.l2t tbody tr td:nth-child(2){white-space:nowrap}
.kv{font:600 12px var(--mono);color:var(--ink-2);white-space:nowrap} .kv b{color:var(--ink)} .kv .late,.dk .late{font:700 10px var(--body);text-transform:uppercase;letter-spacing:.04em;margin-left:4px}
.dbar{display:flex;height:7px;border-radius:4px;overflow:hidden;background:var(--ns);margin-top:4px;min-width:120px}
.dbar i{display:block;height:100%} .dbar .ba,.dlg .ba{background:var(--good)} .dbar .br,.dlg .br{background:var(--accent)} .dlg .bo{background:var(--ns)}
.dlg{display:flex;gap:14px;font-size:11px;color:var(--muted);margin-top:10px} .dlg i{display:inline-block;width:12px;height:8px;border-radius:2px;margin-right:4px;vertical-align:0}
.ovt tbody th{font:800 18px var(--display)} .ovt tbody th span{display:block;font:500 11px var(--body);color:var(--muted)} .ovt td{padding:12px 10px} .ovt .kv{font-size:14px} .ovt .dbar{height:10px}
.kpan{display:flex;flex-direction:column;gap:2px;min-width:0;font-size:12px}
.kcols .kpan{display:block}
.kph{font:700 10px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);border-bottom:2px solid var(--line-2);padding:6px 0;display:flex;justify-content:space-between;gap:8px;column-span:all;margin-bottom:4px} .kph span{text-transform:none;letter-spacing:0;font-weight:500}
.dl2{font:700 12.5px var(--display);color:var(--brand);margin-top:6px;padding-top:4px;break-after:avoid} .dl2 span{font:500 11px var(--body);color:var(--muted)}
.dl4{font:600 11px var(--body);color:var(--ink-2);padding-left:8px;border-left:2px solid var(--line-2);margin:2px 0 1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;break-after:avoid} .dl4 span{color:var(--muted);font-weight:500}
.dk{display:grid;grid-template-columns:118px 56px minmax(0,1fr) auto auto;gap:6px;align-items:center;padding:2px 0 2px 16px;line-height:1.35;break-inside:avoid}
.dk a{font:600 11px var(--mono);color:var(--accent)} .dkt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)} .dkd{font:500 10.5px var(--mono);color:var(--muted);white-space:nowrap}
.dk.ok .dkt{color:var(--ink-2)} .tick{color:var(--good);font-size:13px}
.kp{font:700 9.5px var(--body);text-transform:uppercase;letter-spacing:.03em;padding:1px 6px;border-radius:8px;border:1px solid var(--line-2);color:var(--ink-2);white-space:nowrap}
.kp.a{border-color:var(--warn);color:var(--warn)} .kp.p{border-color:var(--accent);color:var(--accent)} .kp.n{color:var(--muted)}
.chk{font:700 9px var(--body);color:var(--warn);text-transform:uppercase}
.slide-d.title{background:#1B2C6B} .slide-d.title::before{background:#0091A8}
.slide-d.title .sd-in{justify-content:center;padding:60px 80px;gap:16px;color:#fff}
.tt-k{font:700 14px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:#7FD6E3}
.slide-d.title h2{margin:0;font:800 64px/1.02 var(--display);color:#fff;letter-spacing:-.02em} .slide-d.title h2 span{font-weight:600;font-size:40px;opacity:.85}
.tt-m{font-size:20px;opacity:.85} .tt-ws{display:flex;gap:10px;margin-top:18px} .tt-ws span{font:800 18px var(--display);border:2px solid currentColor;border-radius:8px;padding:6px 14px;opacity:.9}
.tt-f{position:absolute;left:80px;bottom:30px;font-size:12px;opacity:.7}
.dfl{margin:6px 0 0;padding-left:20px;display:flex;flex-direction:column;gap:14px;font-size:15px;line-height:1.5;color:var(--ink-2);max-width:1080px} .dfl b{color:var(--ink)}
.deck.fs{background:var(--bg);padding:12px 20px;display:flex;flex-direction:column;justify-content:center} .deck.fs .vsh{display:none} .deck.fs .dkstage{display:flex;justify-content:center} .deck.fs .dslide.on{width:calc(1280px*var(--sc))}
.dkstage.flow .slide-d{width:auto;height:auto} .dkstage.flow .sd-in{padding:20px 16px 12px} .dkstage.flow .wsgrid{grid-template-columns:minmax(0,1fr)} .dkstage.flow .kcols .kpan{column-count:1}
.dkstage.flow .kpis-d{flex-wrap:wrap} .dkstage.flow .kpis-d>div{flex:1 1 30%} .dkstage.flow .kpis-d>.sep{display:none}
.dkstage.flow .sd-h h2{font-size:24px} .dkstage.flow .slide-d.title h2{font-size:38px} .dkstage.flow .slide-d.title h2 span{font-size:24px} .dkstage.flow .slide-d.title .sd-in{padding:36px 20px 60px} .dkstage.flow .tt-f{left:20px}
.dkstage.flow .dk{grid-template-columns:auto auto minmax(0,1fr);padding-left:6px} .dkstage.flow .dkt{grid-column:1/-1;white-space:normal}
.dkstage.flow .l2t colgroup,.dkstage.flow .l2t thead{display:none} .dkstage.flow .l2t,.dkstage.flow .l2t tbody{display:block} .dkstage.flow .l2t tr{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr);gap:4px 10px;border-bottom:1px solid var(--line);padding:8px 0} .dkstage.flow .l2t th{grid-column:1/-1;padding:0;border:0} .dkstage.flow .l2t td{padding:0;border:0} .dkstage.flow .l2t td::before{content:attr(data-l);display:block;font:600 9px var(--body);text-transform:uppercase;letter-spacing:.05em;color:var(--muted)} .dkstage.flow .sd-f{flex-direction:column;gap:2px} .dkstage.flow .dbar{min-width:60px}
.dkstage.flow .dtab{font-size:12px} .dkstage.flow .kv{white-space:normal}
.lv1{background:var(--lv1)} .lv2{background:var(--lv2)} .lv3{background:var(--lv3)} .lv4{background:var(--lv4)}
.story{gap:10px}
.sty{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:28px;align-items:start}
.sty-vis{align-self:stretch}
.sty-stick{position:sticky;top:12px;display:flex;gap:12px;align-items:stretch}
.sty-rail{display:flex;flex-direction:column;gap:8px;padding-top:6px}
.rdot{width:26px;height:26px;border-radius:50%;border:1px solid var(--line-2);background:var(--surface);color:var(--muted);font:700 11px var(--mono);cursor:pointer;display:grid;place-items:center;transition:background .25s,color .25s,border-color .25s}
.rdot:hover{border-color:var(--accent);color:var(--accent)} .rdot.on{background:var(--brand);border-color:var(--brand);color:var(--on-solid)}
.rdot:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.sty-stage{position:relative;flex:1;min-height:420px;border:1px solid var(--line);border-radius:8px;background:var(--surface-2);overflow:hidden}
.sty-stage>.svp{position:absolute;inset:0;padding:16px 18px;opacity:0;transform:translateY(10px);transition:opacity .45s ease,transform .45s ease;pointer-events:none;overflow:auto}
.sty-stage>.svp.on{opacity:1;transform:none;pointer-events:auto}
.svp{display:flex;flex-direction:column;gap:10px}
.svm{display:none}
.sty-steps{display:flex;flex-direction:column}
.sstep{min-height:62vh;padding:18px 4px 18px 14px;border-left:3px solid var(--line);display:flex;flex-direction:column;justify-content:center;gap:8px;opacity:.45;transition:opacity .35s,border-color .35s}
.sstep:last-child{min-height:50vh}
.sstep.act{opacity:1;border-left-color:var(--accent)}
.sstep h3{margin:0;font:800 20px/1.2 var(--display);color:var(--ink);text-wrap:balance}
.sstep p{margin:0;font-size:15px;line-height:1.5;color:var(--ink-2)} .sstep p b{color:var(--ink)}
.sstep b.g,.svp b.g{color:var(--good)} .sstep b.a,.svp b.a{color:var(--warn)} .sstep b.r,.svp b.r{color:var(--crit)}
.skick{font:700 11px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.sty-key{padding:8px 10px;border-radius:6px;background:var(--surface-2);border:1px solid var(--line)}
.vh{display:flex;align-items:baseline;gap:10px} .vbig{font:800 26px var(--display)} .vbig.g{color:var(--good)} .vbig.a{color:var(--warn)} .vbig.r{color:var(--crit)}
.sgrp{display:flex;flex-direction:column;gap:6px;padding-top:4px}
.sgt{font:700 11px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.srow,.prow{display:grid;grid-template-columns:110px minmax(0,1fr) 64px;gap:10px;align-items:center}
.sl{font:600 12px var(--body);color:var(--ink-2)} .sv-n{font:700 12px var(--mono);color:var(--ink);text-align:right}
.sstack{display:flex;height:22px;border-radius:3px;overflow:hidden;background:var(--surface)}
.sstack i{display:block;height:100%;width:0;transition:width .7s ease}
.svp.on .sstack i{width:var(--w)} .sstack i+i{box-shadow:inset 1px 0 0 var(--surface-2)}
.slg{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--muted)} .slg i{display:inline-block;width:12px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.pbars{display:flex;flex-direction:column;gap:3px;min-width:0}
.xbar{position:relative;height:13px;margin-right:52px}
.xbar i{display:block;height:100%;width:0;border-radius:2px;transition:width .7s ease}
.svp.on .xbar i{width:var(--w)}
.xbar em{position:absolute;top:50%;transform:translateY(-50%);line-height:1;left:calc(var(--w,0%) + 6px);font:600 10px var(--mono);font-style:normal;color:var(--ink-2);white-space:nowrap}
.svp .xbar em{left:auto;right:-52px;width:46px;text-align:left}
.pp,.slg i.pp{background:var(--planned)} .pa{background:var(--brand)} .pa.g,.slg i.pa.g{background:var(--good)} .pa.m,.slg i.pa.m{background:var(--brand-2)} .pa.a,.slg i.pa.a{background:var(--warn)} .pa.r,.slg i.pa.r{background:var(--crit)} .pa.u{background:var(--accent)} .pa.n{background:var(--ns)}
.prow .sv-n{font-weight:600;color:var(--muted)}
.zone{display:none}
.chips{display:flex;gap:6px;flex-wrap:wrap} .chip{font-size:11px;padding:3px 8px;border-radius:10px;border:1px solid var(--line-2);color:var(--ink-2);background:var(--surface)}
.chip.g{border-color:var(--good);color:var(--good)} .chip.a{border-color:var(--warn);color:var(--warn)} .chip.r{border-color:var(--crit);color:var(--crit)}
.dplot{display:flex;flex-direction:column;gap:12px;padding-top:14px}
.drow{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px;align-items:center}
.dtrack{position:relative;height:12px;border-radius:6px;margin-right:14px;background:linear-gradient(to right,var(--crit-soft) 0 var(--z1),var(--warn-soft) var(--z1) var(--z2),var(--good-soft) var(--z2) 100%)}
.dtrack::after{content:"";position:absolute;left:var(--z3);top:-4px;bottom:-4px;border-left:2px dashed var(--ink-2);opacity:.55}
.dot{position:absolute;top:50%;left:0;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;background:var(--ns);border:2px solid var(--surface);transition:left .8s ease;z-index:1}
.svp.on .dot{left:var(--x)} .dot.g{background:var(--good)} .dot.a{background:var(--warn)} .dot.r{background:var(--crit)} .dot.hi{width:20px;height:20px;margin:-10px 0 0 -10px;box-shadow:0 0 0 3px var(--crit-soft)}
.dtrack em{position:absolute;top:-19px;left:var(--x);transform:translateX(-50%);font:700 10px var(--mono);font-style:normal;color:var(--ink-2);white-space:nowrap}
.dtrack em.rt{transform:translateX(calc(-100% - 10px));top:-6px}
.dax .dtrack{background:none;height:12px} .dax .dtrack::after{display:none} .dax .dtrack span{position:absolute;top:0;transform:translateX(-50%);font:500 10px var(--mono);color:var(--muted);white-space:nowrap} .dax .dtrack span:first-child{transform:none} .dax .dtrack span:last-child{transform:translateX(-100%)}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.tile{border:1px solid var(--line);border-radius:6px;background:var(--surface);padding:8px 10px;display:flex;flex-direction:column}
.tile b{font:800 22px var(--display);color:var(--ink)} .tile span{font-size:11px;color:var(--muted)} .tile.r{border-color:var(--crit)} .tile.r b{color:var(--crit)}
.ccard{border:1px solid var(--crit);border-left-width:4px;border-radius:6px;background:var(--surface);padding:7px 10px;display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 10px;font-size:12px}
.ccard a{font:700 12px var(--mono);color:var(--accent)} .ccard .tt2{color:var(--ink)} .ccard .note{grid-column:2}
@media (max-width:900px){.sty{grid-template-columns:minmax(0,1fr)}.sty-vis{display:none}.svm{display:flex;margin-top:8px;border:1px solid var(--line);border-radius:8px;background:var(--surface-2);padding:12px}.sstep{min-height:0;opacity:1}.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.srow,.prow{grid-template-columns:72px minmax(0,1fr) 40px;gap:6px}.drow{grid-template-columns:72px minmax(0,1fr);gap:6px}.xbar{margin-right:40px}.svp .xbar em{right:-40px;width:36px}.ccard{grid-template-columns:1fr}.ccard .note{grid-column:1}.ccard .tt2{overflow-wrap:anywhere}.sty-stage,.svm{min-width:0}}
@media (prefers-reduced-motion:reduce){.sty-stage>.svp,.sstack i,.xbar i,.dot,.sstep,.rdot{transition:none!important}.sty-stage>.svp{transform:none}}

.ovr{display:inline-block;margin-left:6px;font:700 10px var(--body);padding:1px 6px;border-radius:8px;border:1px dashed var(--crit);color:var(--crit);white-space:nowrap;vertical-align:1px}
.actlink{font:600 11px var(--body);border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);border-radius:10px;padding:2px 8px;cursor:pointer;text-align:left;white-space:nowrap}
.actlink:hover{border-color:var(--accent);color:var(--accent)} .actlink .note{font-weight:400}
.wsn{font-size:11px;color:var(--ink-2)}
.fchip{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:3px 4px 3px 10px;border-radius:12px;background:var(--accent-soft);color:var(--accent)}
.fchip button{border:0;background:var(--surface);color:var(--accent);border-radius:50%;width:20px;height:20px;cursor:pointer;font:700 13px var(--body);line-height:1}
.vsec{border:1px solid var(--line);border-radius:6px;padding:12px;display:flex;flex-direction:column;gap:8px}
.vsh{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap} .vsh b{font:800 13px var(--display);text-transform:uppercase;letter-spacing:.04em}
.vlg{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted);align-items:center}
.vlg i.lp,.vlg i.la{display:inline-block;width:14px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.vlg i.lp{background:var(--planned)} .vlg i.la{background:var(--brand)}
.vdot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px;background:var(--ns)}
.vdot.g{background:var(--good)} .vdot.a{background:var(--warn)} .vdot.r{background:var(--crit)}
.heatwrap{border:0;max-height:none}
.heat{border-collapse:separate;border-spacing:4px;width:100%;min-width:720px}
.heat th{font:700 11px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);text-align:center;padding:4px 6px;background:none;border:0;position:static}
.heat tbody th,.heat tfoot th{text-align:left;font:700 13px var(--display);letter-spacing:0;text-transform:none;color:var(--ink);padding-right:12px;white-space:nowrap}
.heat td.hc{text-align:center;padding:8px 6px;border-radius:5px;border:0;cursor:default;min-width:110px}
.heat td.hc[data-w]{cursor:pointer} .heat td.hc[data-w]:hover,.heat td.hc[data-w]:focus-visible{outline:2px solid var(--brand);outline-offset:1px}
.heat .hv{display:block;font:800 14px var(--mono)} .heat .hs{display:block;font:600 10px var(--body);margin-top:2px}
.heat td.g{background:var(--good-soft);color:var(--good)} .heat td.a{background:var(--warn-soft);color:var(--warn)} .heat td.r{background:var(--crit-soft);color:var(--crit)}
.heat td.nz{background:var(--surface-2);color:var(--muted)} .heat td.nd{background:none;color:var(--muted);border:1px dashed var(--line)}
.heat td.pool{box-shadow:inset 0 0 0 2px currentColor} .heat th.pool{color:var(--ink)}
.heat.hfix{table-layout:fixed} .heat.hfix col.c0{width:130px}
.hprogbox{border:2px solid var(--brand);border-radius:8px;background:var(--accent-soft);background:color-mix(in srgb,var(--brand) 7%,var(--surface));margin:2px 0 8px;min-width:900px}
.hprogbox .heat{margin:0}
.heat tr.hprog th{font-size:15px;font-weight:800;color:var(--brand)}
.vrow{display:grid;grid-template-columns:120px minmax(0,1fr) 190px;gap:12px;align-items:center}
.vlab{font:700 13px var(--display);color:var(--ink)}
.vbars{display:flex;flex-direction:column;gap:2px}
.vb{display:flex;align-items:center;height:13px;border-radius:2px;min-width:2px;position:relative}
.vb em{position:absolute;left:calc(100% + 6px);font:600 10px var(--mono);font-style:normal;color:var(--ink-2);white-space:nowrap}
.vb.vp{background:var(--planned)} .vb.va{background:var(--brand)} .vb.va.g{background:var(--good)} .vb.va.a{background:var(--warn)} .vb.va.r{background:var(--crit)}
.vnum{font-size:12px;color:var(--muted)} .vnum b{font-family:var(--mono)} .vnum b.g{color:var(--good)} .vnum b.a{color:var(--warn)} .vnum b.r{color:var(--crit)}
.vcharts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.heat{min-width:900px}
.vcard{border:1px solid var(--line);border-radius:6px;padding:10px 12px;min-width:0}
.vch{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap} .vch h3{margin:0;font:700 14px var(--display)}
.vch b.g{color:var(--good)} .vch b.a{color:var(--warn)} .vch b.r{color:var(--crit)}
.vsvg{width:100%;display:block}
.vsvg .vg{stroke:var(--line)} .vsvg .vax{stroke:var(--line-2)} .vsvg .vt{fill:var(--muted);font:500 9px var(--mono)}
.vsvg .cp{fill:var(--planned)} .vsvg .ca{fill:var(--brand)} .vsvg .ca.g{fill:var(--good)} .vsvg .ca.a{fill:var(--warn)} .vsvg .ca.r{fill:var(--crit)}
.vsvg .cv{fill:var(--ink-2);font:700 10px var(--mono)} .vsvg .cv.g{fill:var(--good)} .vsvg .cv.a{fill:var(--warn)} .vsvg .cv.r{fill:var(--crit)}
.vsvg .cx{fill:var(--ink);font:700 11px var(--body)} .vsvg .ch{fill:var(--muted);font:700 10px var(--mono)} .vsvg .ch.g{fill:var(--good)} .vsvg .ch.a{fill:var(--warn)} .vsvg .ch.r{fill:var(--crit)}
@media (max-width:900px){.vcharts{grid-template-columns:1fr}.vrow{grid-template-columns:90px minmax(0,1fr)}.vnum{grid-column:1/-1}}
.buc .tlab rect{stroke-width:1} .buc .tlab text{font:700 9px var(--mono)}
.buc .tlab.tp rect{fill:var(--surface);stroke:var(--brand)} .buc .tlab.tp text{fill:var(--brand)}
.buc .tlab.ta rect{fill:var(--accent-soft);stroke:var(--accent)} .buc .tlab.ta text{fill:var(--accent)}
.buc .tlab.tz rect{fill:var(--surface-2);stroke:var(--line-2)} .buc .tlab.tz text{fill:var(--muted)}
.buc .pdot{fill:var(--brand);stroke:var(--surface);stroke-width:1.5}
.buc .gbr{stroke-width:2.5} .buc .gbr.gbad{stroke:var(--crit)} .buc .gbr.gok{stroke:var(--good)}
.buc .gtx{font:800 9px var(--mono)} .buc .gtx.gbad{fill:var(--crit)} .buc .gtx.gok{fill:var(--good)}
.bugrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.bubox{border:1px solid var(--line);border-radius:6px;padding:10px;display:flex;flex-direction:column;gap:8px;min-width:0;background:var(--surface)}
.bubox h3{margin:0;font:700 13px var(--display);text-align:center}
.buc{width:100%;display:block}
.buc .bg{stroke:var(--line);stroke-width:1} .buc .bt{fill:var(--muted);font:500 9px var(--mono)} .buc .btl{fill:var(--brand);font-weight:700}
.buc .bs{stroke:var(--plan);stroke-width:1.5;stroke-dasharray:2 3} .buc .btd{stroke:var(--brand);stroke-width:1.2;stroke-dasharray:3 3}
.buc .bp{fill:none;stroke:var(--brand);stroke-width:2;stroke-dasharray:6 4} .buc .ba{fill:none;stroke:var(--accent);stroke-width:2.5}
.buc .ba0{fill:none;stroke:var(--accent);stroke-width:1.5;stroke-dasharray:2 3} .buc .bd{fill:var(--accent);stroke:var(--surface);stroke-width:2}
.buc .bh{fill:transparent} .buc .bh:hover{fill:var(--accent-soft);opacity:.5}
.bunote{font-size:11px;text-align:center} .bunote a{color:var(--warn);font-weight:700}
.bulg{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted);align-items:center}
.bulg i{display:inline-block;width:18px;height:0;margin-right:5px;vertical-align:3px;border-top:2px solid}
.bulg .lp{border-color:var(--brand);border-top-style:dashed} .bulg .la{border-color:var(--accent);border-top-width:3px} .bulg .ls{border-color:var(--plan);border-top-style:dotted} .bulg .lt{border-color:var(--brand);border-top-style:dotted;width:2px;height:12px;border-top:0;border-left:2px dotted var(--brand);vertical-align:-1px}
.hint.amb{color:var(--warn);font-weight:700}
@media (max-width:1240px){.bugrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.bugrid{grid-template-columns:1fr}}
.ribbon{grid-template-columns:minmax(240px,280px) minmax(0,1.3fr) minmax(0,1.2fr)}
.rfilt{display:flex;flex-direction:column;gap:6px;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--surface-2)}
.rfilt .ms,.rfilt .ms>button{width:100%;min-width:0}
.rfilt .pop{min-width:300px}
.rfilt .reset{margin:2px 0 0;align-self:stretch}
@media (max-width:1100px){.ribbon{grid-template-columns:1fr}}
.rbars{border:1px solid var(--line);border-radius:6px;padding:10px 12px;display:flex;flex-direction:column;gap:8px;background:var(--surface)}
.bhead{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap} .bhead b{font:800 13px var(--display);letter-spacing:.04em;text-transform:uppercase;color:var(--ink)}
.brow{display:grid;grid-template-columns:120px minmax(0,1fr) 330px;gap:12px;align-items:center;border-radius:5px;padding:3px 4px}
.brow.clk{cursor:pointer} .brow.clk:hover{background:var(--surface-2)} .brow.on{background:var(--accent-soft)}
.blab{font-size:13px;color:var(--ink-2)} .blab b{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:4px;background:var(--brand);color:var(--on-solid);font:800 12px var(--display);margin-right:6px}
.bbar{display:flex;height:22px;border-radius:4px;overflow:hidden;background:var(--ns)}
.bseg{display:flex;align-items:center;justify-content:center;font:700 11px var(--mono);color:var(--on-solid);min-width:0;overflow:hidden;white-space:nowrap}
.bseg.ov{background:var(--crit)} .bseg.nd{background:var(--plan);color:var(--ink)} .bseg.cl{background:var(--good-soft);color:var(--good)}
.bempty{font-size:11px;color:var(--muted);padding:3px 8px}
.bnum{font-size:12px;color:var(--muted)} .bnum b{font-family:var(--mono);color:var(--ink)} .bnum b.red{color:var(--crit)}
.bleg{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted);align-items:center}
.bleg i{display:inline-block;width:12px;height:8px;border-radius:2px;margin-right:4px;vertical-align:0}
.bleg i.ov{background:var(--crit)} .bleg i.nd{background:var(--plan)} .bleg i.cl{background:var(--good-soft);border:1px solid var(--good)}
@media (max-width:760px){.brow{grid-template-columns:100px minmax(0,1fr)}.bnum{grid-column:1/-1}}
.ochip{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--crit);border-radius:12px;padding:1px 4px 1px 2px;background:var(--surface)}
.ochip.on{background:var(--crit-soft);box-shadow:0 0 0 1px var(--crit) inset}
.oname{font:700 11px var(--body);border:0;background:var(--crit);color:var(--on-solid);border-radius:10px;padding:2px 8px;cursor:pointer}
.oname b{font-family:var(--mono)}
.ows{font-size:11px;color:var(--ink-2)}
.wchip.inl{border:0;background:none;padding:0 1px;font:600 11px var(--body);color:var(--crit);box-shadow:none}
.wchip.inl:hover{text-decoration:underline}
.ogc{font:600 10px var(--mono);color:var(--muted)} .ogc.na{color:var(--warn)}
/* full titles everywhere */
.tt,.tt2,.tt3,td .tt,td .tt2{display:block;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;max-width:none!important;min-width:260px;line-height:1.35;overflow-wrap:anywhere}
.tt3{min-width:180px}
.li .t{display:block!important;-webkit-line-clamp:unset!important;overflow:visible!important}
.crit td .tt2{min-width:360px}
.crit{border:2px solid var(--crit);border-radius:6px;overflow:hidden;background:var(--surface)}
.crit-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 12px;background:var(--crit-soft);color:var(--crit)}
.crit-h b{font:800 13px var(--display);letter-spacing:.04em;text-transform:uppercase}
.crit-h span{font-size:11px;color:var(--ink-2)}
.crit-h .cbadge{margin-left:auto;font:700 11px var(--mono);padding:3px 9px;border-radius:10px;background:var(--surface);color:var(--muted);border:1px solid var(--line)}
.crit-h .cbadge.on{background:var(--crit);color:var(--on-solid);border-color:var(--crit)}
.critwrap{border:0;border-radius:0;max-height:none}
.critwrap table{min-width:1100px}
.crit-e{padding:10px 12px}
.gcard{position:relative}
.gcard h3{padding:0 26px}
.tl{position:absolute;top:8px;right:8px;display:flex;flex-direction:column;gap:3px;padding:4px;border-radius:6px;background:var(--ink)}
.tl i{display:block;width:11px;height:11px;border-radius:50%;opacity:.22}
.tl .lr{background:var(--crit)} .tl .la{background:var(--warn)} .tl .lg{background:var(--good)}
.tl.r .lr,.tl.a .la,.tl.g .lg{opacity:1;box-shadow:0 0 6px currentColor}
.tl.r .lr{color:var(--crit)} .tl.a .la{color:var(--warn)} .tl.g .lg{color:var(--good)}
.gcard .hit rect{stroke-width:1.5} .gcard .hit text{font:800 11px var(--mono)}
.gcard .hit.ok rect{fill:var(--good-soft);stroke:var(--good)} .gcard .hit.ok text{fill:var(--good)}
.gcard .hit.bad rect{fill:var(--crit-soft);stroke:var(--crit)} .gcard .hit.bad text{fill:var(--crit)}
.rbox{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:5px;overflow:hidden}
.rrow{display:flex;justify-content:space-between;align-items:center;gap:8px;font:600 12px var(--body);color:var(--ink-2);background:var(--surface);border:0;padding:7px 10px;cursor:pointer;text-align:left}
.rrow+.rrow{border-top:1px solid var(--line)}
.rrow small{font-weight:400;color:var(--muted)}
.rrow b{font:800 16px var(--display);color:var(--accent)}
.rrow.bad{background:var(--crit-soft)} .rrow.bad b{color:var(--crit)}
.rrow:hover{box-shadow:inset 3px 0 0 var(--accent)} .rrow.bad:hover{box-shadow:inset 3px 0 0 var(--crit)}
.mtabs{display:flex;gap:4px;border-bottom:2px solid var(--brand);flex-wrap:wrap}
.mtab{font:700 14px var(--display);border:1px solid var(--line);border-bottom:0;background:var(--surface-2);color:var(--ink-2);padding:11px 26px;border-radius:6px 6px 0 0;cursor:pointer;letter-spacing:.01em}
.mtab:hover{color:var(--brand)}
.mtab[aria-selected="true"]{background:var(--brand);color:var(--on-solid);border-color:var(--brand)}
.tabpane{display:flex;flex-direction:column;gap:14px}
.tabpane[hidden]{display:none!important}
@media (max-width:640px){.mtab{flex:1;padding:10px 6px;font-size:12px;text-align:center}}

.kbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 10px;background:var(--surface-2);border:1px solid var(--line);border-radius:6px}
.kbar[hidden]{display:none}
.ftag{font:700 10px var(--body);letter-spacing:.04em;padding:3px 8px;border-radius:10px;background:var(--accent-soft);color:var(--accent)}
.ptabs .ms{align-self:center;margin:0 8px 6px auto}
.ptabs .ms:not([hidden])~.search{margin-left:0}
.ptabs .ms[hidden]{display:none}

.wchips{display:inline-flex;gap:5px;flex-wrap:wrap;margin-left:auto;align-items:center;justify-content:flex-end}
.wchips .tlab{font:600 10px var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-right:3px}
.lane-head .badge{margin-left:10px}
.wchip{font:600 11px var(--body);border:1px solid transparent;border-radius:11px;padding:2px 8px;cursor:pointer;line-height:1.4}
.wchip b{font-family:var(--mono);margin-left:2px}
.wchip.done{background:var(--good-soft);color:var(--good)} .wchip.up{background:var(--accent-soft);color:var(--accent)} .wchip.late{background:var(--surface);color:var(--crit);border-color:var(--crit)}
.wchip:hover,.wchip.on{border-color:currentColor;box-shadow:0 0 0 1px currentColor inset}
@media (max-width:640px){.wchips{margin-left:0;width:100%;order:3;justify-content:flex-end}.lane-head{flex-wrap:wrap}}
</style>
<div class="slide">
  <div class="top">
    <div>
      <div class="eyebrow">{{eyebrow_html}}</div>
      <h1>{{heading_html}}</h1>
      <div class="sub"><span>{{lineage}}</span><span class="tag">{{sources_tag_html}}</span></div>
    </div>
    <div class="kpis">
      <div class="kpi risk" title="Big number = open risks. Open issues are shown below."><span class="dot"></span><div><div class="lbl">Open Risks &amp; Issues</div><b class="num" id="kRisk">0</b></div><div class="meta" id="kRiskM"></div></div>
      <div class="kpi act"><span class="dot"></span><div><div class="lbl">Open Actions</div><b class="num" id="kAct">0</b></div><div class="meta" id="kActM"></div></div>
    </div>
  </div>

  <nav class="mtabs" id="mtabs" role="tablist" aria-label="Cockpit views">
    <button type="button" role="tab" class="mtab" data-v="wsview" id="mt-wsview" aria-controls="tab-wsview">Executive View</button>
    <button type="button" role="tab" class="mtab" data-v="progress" id="mt-progress" aria-controls="tab-progress">Progress vs Plan</button>
    <button type="button" role="tab" class="mtab" data-v="l4" id="mt-l4" aria-controls="tab-l4">L4 Traceability</button>
    <button type="button" role="tab" class="mtab" data-v="raid" id="mt-raid" aria-controls="tab-raid">RAID Tracker</button>
    <button type="button" role="tab" class="mtab" data-v="burnup" id="mt-burnup" aria-controls="tab-burnup">PBI Burn-up</button>
    <button type="button" role="tab" class="mtab" data-v="e2e" id="mt-e2e" aria-controls="tab-e2e">E2E Build Journey</button>
  </nav>
  <div class="tabpane" id="tab-wsview" role="tabpanel" aria-labelledby="mt-wsview" hidden>
    <section class="panel reg">
      <div class="ph"><h2>Executive View</h2><span class="hint">{{hint_exec}}</span></div>
      <div class="regbar">
        <div class="ms" id="msVws"></div>
        <div class="ms" id="msVct"></div>
        <button type="button" class="reset" id="vReset">Reset filters</button>
      </div>
      <div class="vsec"><div class="vsh"><b>Workstream heatmap</b><span class="note">Actual / plan to date · % behind · rows in order D2D, S2P, O2C, R2R, M2O · click a cell to open it in Progress vs Plan</span></div>
        <div class="vlg"><span><i class="vdot g"></i>&lt; 10% behind or ahead</span><span><i class="vdot a"></i>10–30% behind</span><span><i class="vdot r"></i>&gt; 30% behind</span><span><i class="vdot"></i>Nothing due yet</span><span>— no items</span></div>
        <div class="tblwrap heatwrap" id="vScore"></div></div>
      <div class="vsec deck" id="deck"><div class="vsh"><b>Program Executive Summary</b><span class="note">Slides by workstream and L2 · KDDs and requirements · program-wide, ignores the slicers above · ‹ › or arrow keys to move</span></div>
        <div class="dkbar"><button type="button" class="dkbtn" id="dkPrev" aria-label="Previous slide">‹</button><span class="dkcount" id="dkCount" aria-live="polite"></span><button type="button" class="dkbtn" id="dkNext" aria-label="Next slide">›</button>
          <div class="dkthumbs" id="dkThumbs" role="tablist" aria-label="Slides"></div><button type="button" class="reset" id="dkPresent">Present</button></div>
        <div class="dkfil"><div class="ms" id="msDks"></div><button type="button" class="dkpre" data-p="open">Open only</button><button type="button" class="dkpre" data-p="appr">Approved only</button><button type="button" class="dkpre reset" data-p="all">Reset</button><span class="note">KDD state filters the KDD lists, tiles and counts on every slide; requirements are not affected.</span></div>
        <div class="dkstage" id="dkStage"></div>
      </div>
      <div class="note">{{note_exec}}</div>
    </section>
  </div>
  <div class="tabpane" id="tab-progress" role="tabpanel" aria-labelledby="mt-progress">
<section class="panel reg" id="pvp">
    <div class="ph"><h2><span class="step">01</span>Progress vs Plan</h2><span class="hint">{{hint_progress}}</span></div>
    <div class="pvbar">
      <div class="ms" id="msGws"></div>
      <div class="ms" id="msGct"></div>
      <div class="health" id="pvHealth"></div>
    </div>
    <div class="gcards" id="pvCards"></div>
    <div class="ptabs" id="pvTabs" role="tablist" aria-label="Detail view">
      <button type="button" class="ptab" role="tab" data-t="KDD">KDDs</button>
      <button type="button" class="ptab" role="tab" data-t="REQ">Requirements</button>
      <button type="button" class="ptab" role="tab" data-t="PBI">Build PBIs</button>
      <button type="button" class="ptab" role="tab" data-t="WS">Workshops</button>
      <button type="button" class="ptab" role="tab" data-t="DM">Data Migration</button>
      <button type="button" class="ptab" role="tab" data-t="OCM">OCM</button>
      <div class="seg" id="pvLink" role="group" aria-label="Link status" hidden><button type="button" data-l="ALL">All</button><button type="button" data-l="L">Linked only</button><button type="button" data-l="U">Unlinked only</button></div>
      <input class="search" id="pvq" type="search" placeholder="Search ID, title or owner">
    </div>
    <div class="kbar" id="kbar" hidden><div class="ms" id="msPkty"></div><span class="note">Filters the KDD gauge and the KDD lanes</span></div>
    <div class="kbar" id="pbar" hidden><div class="ms" id="msPbt"></div><span class="note">Filters the Build PBIs gauge and the Build PBI lanes</span></div>
    <div class="lanes" id="pvLanes"></div>
    <div class="hleg"><span><b>Program Health</b> (all levers pooled):</span><span><i class="hd g"></i><b>Green · On track</b> &lt; 10% behind plan to date</span><span><i class="hd a"></i><b>Amber · At risk</b> 10–30% behind</span><span><i class="hd r"></i><b>Red · Off track</b> &gt; 30% behind</span><span class="note">Shortfall = (Σ plan to date − Σ actual) ÷ Σ plan to date across KDDs, Requirements, Build PBIs, Workshops, Data Migration and OCM; a lever ahead of plan offsets the others. Dial runs from 0 to overall planned; needle and milometer show actual; the blue zone and marker show plan to date.</span></div>
  </section>

<section class="panel reg">
    <div class="ph"><h2><span class="step">02</span>KDD Register by L2</h2><span class="hint" id="regHint"></span></div>
    <div class="regbar">
      <div class="ms" id="msKws"></div>
      <div class="ms" id="msKty"></div>
      <div class="ms" id="msL2"></div>
      <input class="search" id="rq" type="search" placeholder="Search KDD ID, title, L4 or assignee">
      <label class="tog"><input type="checkbox" id="lateOnly"> Late only</label>
      <label class="tog amb-t"><input type="checkbox" id="chkOnly"> Check date</label>
      <button type="button" class="lnk" id="regExp">Collapse all</button>
      <span class="scope" id="regCount"></span>
    </div>
    <div class="tblwrap regwrap"><table class="regt">
      <thead><tr><th>L4 Epic</th><th>KDD ID</th><th>Title</th><th>Workstream</th><th>Status</th><th>Target date</th><th>Target status</th><th class="r">Days late</th><th>Assignee</th></tr></thead>
      <tbody id="regBody"></tbody>
    </table></div>
  </section>
  </div>
  <div class="tabpane" id="tab-l4" role="tabpanel" aria-labelledby="mt-l4" hidden>
  <div class="slicers">
    <span class="ttl">Slicers</span>
    <div class="ms" id="msWs"></div>
    <div class="ms" id="msMo"></div>
    <div class="ms" id="msKdd"></div>
    <div class="ms" id="msLkty"></div>
    <div class="ms" id="msL1"></div>
    <div class="ms" id="msCt"></div>
    <span class="scope" id="scope"></span>
    <button class="reset" id="reset" type="button">Reset filters</button>
  </div>

  <div class="grid">
    <section class="panel">
      <div class="ph"><h2><span class="step">01</span>Workshops</h2><span class="hint">Linked to L4 · completed vs in scope</span></div>
      <div class="big"><b class="num" id="wDone">0</b><span class="of num" id="wPtd"></span><span class="pct num" id="wPct">0%</span></div>
      <div class="facts" id="wFacts"></div>
      <div class="phases" id="wPhase"></div>
      <div class="sect">L4 workshop plan <button type="button" class="needbtn" id="needBtn"></button></div>
      <div class="plan" id="wPlan"></div>
      <div class="sect">Complex topics <span class="legend"><span><i style="background:var(--accent)"></i>Completed</span><span><i style="border:1px dashed var(--plan);border-right:2px solid var(--plan)"></i>Plan to date</span><span><i style="background:var(--surface-2);border:1px solid var(--line)"></i>In scope</span></span></div>
      <div class="ctrows" id="ctRows"></div>
    </section>

    <section class="panel">
      <div class="ph"><h2><span class="step">02</span>Key Design Decisions</h2><span class="hint" id="kL4"></span></div>
      <div class="big"><b class="num" id="kTot">0</b><span class="of">KDDs</span><span class="pct num" id="kAppr">0% approved</span></div>
      <div class="stack" id="kStack"></div>
      <div class="states" id="kStates"></div>
      <div class="sect">Open decisions by target date</div>
      <div class="list" id="kList"></div>
    </section>

    <section class="panel">
      <div class="ph"><h2><span class="step">03</span>Requirements</h2><span class="hint" id="rSrc"></span></div>
      <div class="big"><b class="num" id="rTot">0</b><span class="of">R6 requirements</span></div>
      <div class="sect">Solution disposition <span class="legend"><span><i class="c-oob"></i>Fit OOB</span><span><i class="c-cfg"></i>Fit Config</span><span><i class="c-gap"></i>Gap</span><span><i class="c-tbd"></i>TBD</span></span></div>
      <div class="split" id="rSplit"></div>
      <div class="sect">Linked to a delivery object</div>
      <div class="cov" id="rCov"></div>
      <div class="sect">By workstream</div>
      <div class="wsrows" id="rWs"></div>
    </section>

    <section class="panel">
      <div class="ph"><h2><span class="step">04</span>Delivery Backlog</h2><span class="hint">Child PBIs per object</span></div>
      <div class="tree" id="tCfg"></div>
      <div class="tree" id="tRic"></div>
      <div class="slegend"><span><i style="background:var(--good)"></i>Completed / RFA</span><span><i style="background:var(--accent)"></i>In progress</span><span><i style="background:var(--crit)"></i>Blocked</span><span><i style="background:var(--planned)"></i>Planned</span><span><i style="background:var(--ns)"></i>New</span></div>
    </section>
  </div>

  <div class="chain" id="chain"></div>

  <div class="tblhead">
    <div class="tabs" role="group" aria-label="Table view"><button type="button" id="tabL4" aria-pressed="true">L4 traceability</button><button type="button" id="tabUn" aria-pressed="false">Unlinked items<span class="cnt" id="unCnt"></span></button></div>
    <input class="search" id="q" type="search" placeholder="Search number, title or ID">
    <span class="scope" id="tCount"></span>
  </div>
  <div class="utypes" id="uTypes" hidden></div>
  <div class="tblwrap"><table>
    <thead id="thead"></thead>
    <tbody id="tbody"></tbody>
  </table></div>
  </div>
  <div class="tabpane" id="tab-raid" role="tabpanel" aria-labelledby="mt-raid" hidden>
<section class="panel reg">
    <div class="ph"><h2>RAID Tracker</h2><span class="hint" id="raHint"></span></div>
    <div class="rbars" id="raBars"></div>
    <div class="crit" id="raCrit"></div>
    <div class="ribbon">
      <div class="rfilt"><div class="rlab">Filters</div>
        <div class="ms" id="msRws"></div>
        <div class="ms" id="msRmo"></div>
        <div class="ms" id="msRty"></div>
        <div class="ms" id="msRst"></div>
        <div class="ms" id="msRfm"></div>
        <div class="ms" id="msRas"></div>
        <div class="ms" id="msRwl"></div>
        <button type="button" class="reset" id="raReset">Reset RAID filters</button>
      </div>
      <div class="rgrp"><div class="rlab">Past due / total due by organization</div><div class="firms" id="raFirm"></div></div>
      <div class="rgrp"><div class="rlab">Top 5 past-due assignees</div><div class="tops" id="raTop"></div></div>
    </div>
    <div class="regbar">
      <input class="search" id="raq" type="search" placeholder="Search ID, title or assignee">
      <label class="tog"><input type="checkbox" id="raLate"> Past due only</label>
      <span id="raFocus"></span>
      <button type="button" class="lnk" id="raExp">Collapse all</button>
    </div>
    <div class="tblwrap regwrap"><table class="regt rat">
      <thead><tr><th>Type</th><th>ADO ID</th><th>Title</th><th>Workshop</th><th>Sub-area</th><th>Type PHX</th><th>Target date</th><th>Assigned to</th><th>Organization</th><th>State</th><th class="r">Days late</th></tr></thead>
      <tbody id="raBody"></tbody>
    </table></div>
  </section>
  </div>
    <div class="tabpane" id="tab-e2e" role="tabpanel" aria-labelledby="mt-e2e" hidden>
    <section class="panel reg">
      <div class="ph"><h2>E2E Build Journey</h2><span class="hint">{{hint_e2e}}</span></div>
      <div class="regbar">
        <div class="ms" id="msEws"></div>
        <div class="ms" id="msEjm"></div>
        <div class="ms" id="msEbt"></div>
        <input class="search" id="ejq" type="search" placeholder="Search build item ID, title or PBI ID">
        <button type="button" class="reset" id="ejReset">Reset filters</button>
      </div>
      <div class="ejtiles" id="ejTiles"></div>
      <div class="ejstrip" id="ejStrip"></div>
      <div class="vsec"><div class="vsh"><b>Workstream × stage</b><span class="note">PBIs done / total · click a cell to filter the build items below</span></div>
        <div class="ejlg"><span><i class="r"></i>Past due or blocked</span><span><i class="a"></i>Due in the next 5 days</span><span><i></i>Due later or no target date</span><span><b class="tk">✓</b> Done (Completed or Ready for Acceptance)</span></div>
        <div class="tblwrap" id="ejHeatA"></div></div>
      <div class="vsec"><div class="vsh"><b>Build item × stage</b><span class="note">Each cell is that stage's PBI: target date, coloured by status · click to open in ADO · click a workstream row to collapse</span><span id="ejSel"></span></div>
        <div id="ejHeatB"></div></div>
      <div class="note">{{note_e2e}}</div>
    </section>
  </div>
  <div class="tabpane" id="tab-burnup" role="tabpanel" aria-labelledby="mt-burnup" hidden>
    <section class="panel reg">
      <div class="ph"><h2>PBI Burn-up</h2><span class="hint">{{hint_burnup}}</span></div>
      <div class="regbar">
        <div class="ms" id="msBws"></div>
        <div class="ms" id="msBst"></div>
        <div class="ms" id="msBot"></div>
        <div class="ms" id="msBse"></div>
        <button type="button" class="reset" id="buReset">Reset filters</button>
      </div>
      <div class="bulg"><span><i class="lp"></i>Plan (cumulative by target-date week)</span><span><i class="la"></i>Actual completed</span><span><i class="ls"></i>Total PBIs (scope)</span><span><i class="lt"></i>Today</span><span class="note">{{note_burnup}}</span></div>
      <div class="bugrid" id="buGrid"></div>
    </section>
    <section class="panel reg" id="buNoDate">
      <div class="ph"><h2>PBIs with no target date</h2><span class="hint amb" id="buNdCount"></span></div>
      <div class="regbar"><input class="search" id="buq" type="search" placeholder="Search ID, title or owner"><span class="note">Follows the slicers above. These PBIs count in each chart's total but are not on the plan line.</span></div>
      <div class="tblwrap regwrap"><table class="regt"><thead><tr><th>ADO ID</th><th>Title</th><th>Series</th><th>Parent Config / RICEFW</th><th>Object type</th><th>Object state</th><th>Workstream</th><th>Owner</th><th>State</th><th>Build type</th></tr></thead><tbody id="buNdBody"></tbody></table></div>
    </section>
  </div>

  <div class="foot">
{{footnotes}}
    <span>Hierarchy (L1 → L2 → L3 → L4 Epic) comes from the L1-L4 mapping file (BPH_Epic_Match, Epic rows only). Epics without a BPH match take L1/L2/L3 from their number; levels not found show as UNKNOWN. Workshop links and states come from the Epic_Workshop_Links tab (Signavio process flows excluded).</span>
    <span>L4 Traceability KDD totals leave out rejected KDDs (shown separately). In the L4 table, a KDD linked to two L4s counts under both.</span>
    <span>Red marks anything unlinked: zero-count links in the L4 table, and items in the Unlinked view. Config/RICEFW objects without a requirement are taken from the parents of PBIs in "PBIs Not Linked".</span>
  </div>
</div>
<script>
const DATA={{json:data}};
(function(){
const ASOF={{json:asof}};
const WSO={{json:workstream_order}};
const KST={{json:kdd_states}};
const KCOL={'New':'var(--plan)','In Analysis':'var(--accent)','Pending Approval':'var(--warn)','Approved':'var(--good)','Rejected':'var(--crit)'};
const NOCT='No complex topic',NOL4='Not linked to an L4',NOD='none';
const RAID_CLOSED=new Set({{json:raid_closed_states}});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pct=(a,b)=>b?Math.round(a/b*100):0;
const $=id=>document.getElementById(id);
const mo=d=>d?d.slice(0,7):NOD;
const moLabel=m=>m===NOD?'No target date':new Date(m+'-15T12:00:00').toLocaleDateString('en-US',{month:'short',year:'numeric'});

/* hydrate */
const E=DATA.E.map((e,i)=>({i,n:e[0],t:e[1],l2:e[2]||'L2 UNKNOWN',ws:e[3],id:e[4],bph:!!e[5],l1:e[6]||'L1 UNKNOWN',l3:e[7]||'L3 UNKNOWN',ct:new Set(),w:[],k:[],q:[],qo:[]}));
const W=DATA.W.map(w=>({id:w[0],ws:w[1],t:w[2],s:w[3],ct:w[4]||NOCT,d:w[5],e:w[6],ph:/Initiate/i.test(w[2])?'Initiate':/Validate/i.test(w[2])?'Validate':/Align/i.test(w[2])?'Align':'Other'}));
const K=DATA.K.map(k=>({id:k[0],ws:k[1],t:k[2],s:k[3],d:k[4],e:k[5],a:(k[6]||'').replace(/\s*\([^)]*(Employee|Limited|Ltd|Inc|LLP)[^)]*\)/ig,'').trim(),f:k[7]||'',dc:k[8]||null,b:k[9]||'',ad:k[10]||null,ty:k[11]||'',og:k[12]||''}));
const C=DATA.C.map(c=>({id:c[0],ty:c[1]==='R'?'RICEFW':'Configuration',t:c[2],s:c[3],ws:c[4],d:c[5],tg:c[6]||'',fl:c[7]||'',nb:!!c[8],q:[],p:[]}));
const Q=DATA.Q.map(q=>({id:q[0],ws:q[1],s:q[2],dp:q[3],d:q[4],e:q[5],rc:q[6],t:q[7],nw:!!q[8],o:q[9]||'',oe:q[10]||[],vw:!!q[11],og:q[12]||''}));
const P=DATA.P.map(p=>({id:p[0],c:p[1],s:p[2],ws:p[3],d:p[4],rc:p[5],t:p[6],o:p[7]||'',lr:p[8]||'',og:p[9]||''}));
const R=DATA.R.map(r=>({id:r[0],ty:r[1],t:r[2],s:r[3],ws:r[4],d:r[5],a:r[6],fm:r[7],sub:r[8],tg:r[9]||'',tp:r[10]||'',wsl:[]}));
const CRIT_OVR={{json:raid_critical_overrides}};R.forEach(r=>{if(CRIT_OVR.includes(r.id)&&!/raid-critical/i.test(r.tg)){r.tg=r.tg?r.tg+'; RAID-Critical':'RAID-Critical';r.ovr=1}});
const RBY=Object.fromEntries(R.map(r=>[r.id,r])),WBY=Object.fromEntries(W.map(w=>[w.id,w]));W.forEach(w=>{w.acts=[];w.nx=[]});
(DATA.AL||[]).forEach(([a,wid])=>{const w=WBY[wid];if(!w)return;const r=RBY[a];if(r){r.wsl.push(w);w.acts.push(r)}else w.nx.push(a)});
const wsShort=w=>{const p=(w.t||'').split(/\s*-\s*/);return p.length>2?p[0]+' · '+p.slice(2).join(' - '):w.t};
let RFOCUS=null;const isOpenA=r=>!['Completed','Closed','Archived'].includes(r.s),isPdA=r=>isOpenA(r)&&r.d&&r.d<ASOF;
const actCell=(acts,nx,label,key)=>{const t=acts.length,o=acts.filter(isOpenA).length,od=acts.filter(isPdA).length;if(!t&&!nx)return '<span class="ctag none">—</span>';
  return `<button type="button" class="actlink" data-k="${esc(key)}" data-lab="${esc(label)}" title="Open these actions in the RAID Tracker">${o} open / ${t}${od?` · <b class="red">${od} overdue</b>`:''}${nx?` <span class="note">+${nx} not in RAID export</span>`:''}</button>`};
const ACTSETS={};
W.forEach(w=>w.e.forEach(i=>{E[i].w.push(w);if(w.ct!==NOCT)E[i].ct.add(w.ct)}));
K.forEach(k=>k.e.forEach(i=>E[i].k.push(k)));
Q.forEach(q=>{q.e.forEach(i=>E[i].q.push(q));if(q.s!=='Rejected')q.oe.forEach(i=>E[i].qo.push(q));q.rc.forEach(i=>C[i].q.push(q))});
P.forEach(p=>{if(p.rc>=0)C[p.rc].p.push(p)});
const ctOfEpics=ids=>{if(!ids.length)return new Set([NOL4]);const s=new Set();ids.forEach(i=>E[i].ct.forEach(c=>s.add(c)));if(!s.size)s.add(NOCT);return s};
E.forEach(e=>{e.cts=e.ct.size?e.ct:new Set([NOCT])});
W.forEach(w=>w.cts=w.e.length?new Set([w.ct]):new Set([w.ct,NOL4]));
K.forEach(k=>k.cts=ctOfEpics(k.e));
Q.forEach(q=>q.cts=ctOfEpics(q.e));
C.forEach(c=>{const s=new Set();c.q.forEach(q=>q.cts.forEach(x=>s.add(x)));c.cts=s.size?s:new Set([NOL4])});
P.forEach(p=>p.cts=p.rc>=0?C[p.rc].cts:new Set([NOL4]));
const NOL1='Not linked to an L4';const l1Of=ids=>ids.length?new Set(ids.map(i=>E[i].l1)):new Set([NOL1]);
W.forEach(w=>w.l1s=l1Of(w.e));K.forEach(k=>k.l1s=l1Of(k.e));Q.forEach(q=>q.l1s=l1Of(q.oe||q.e));C.forEach(c=>{const s=new Set();c.q.forEach(q=>q.l1s.forEach(x=>s.add(x)));c.l1s=s.size?s:new Set([NOL1])});P.forEach(p=>p.l1s=p.rc>=0?C[p.rc].l1s:new Set([NOL1]));E.forEach(e=>e.l1s=new Set([e.l1]));
const L1S=[...new Set(E.map(e=>e.l1))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
const CTS=[...new Set(W.map(w=>w.ct))].filter(c=>c!==NOCT).sort();
const MONTHS=[...new Set([...W,...K,...Q,...C,...P,...R].map(x=>mo(x.d)))].filter(m=>m!==NOD).sort();

/* unlinked definitions */
const UN=[
  {k:'L4',lab:'L4 with no Epic',rows:()=>E.filter(e=>e.bph).map(e=>({ty:'L4',id:e.n,t:e.t,ws:e.ws,s:'BPH only',d:null,why:'L4 BPH has no matching Epic',x:{ws:e.ws,cts:e.cts,d:null}}))},
  {k:'WS',lab:'Workshops',rows:()=>W.filter(w=>!w.e.length&&w.s!=='Cancelled').map(w=>({ty:'Workshop',id:w.id,t:w.t,ws:w.ws,s:w.s,d:w.d,why:'No L4 Epic linked',x:w}))},
  {k:'KDD',lab:'KDDs',rows:()=>K.filter(k=>!k.e.length&&k.s!=='Rejected').map(k=>({ty:'KDD',id:k.id,t:k.t,ws:k.ws,s:k.s,d:k.d,why:'No L4 Epic linked',x:k,isK:1}))},
  {k:'REQ',lab:'Requirements',rows:()=>Q.filter(q=>q.nw&&q.s!=='Rejected').map(q=>({ty:'Requirement',id:q.id,t:q.t,ws:q.ws,s:q.s,d:q.d,why:'No workshop linked',x:q}))},
  {k:'RC',lab:'Config / RICEFW',rows:()=>C.filter(c=>!c.q.length).map(c=>({ty:c.ty,id:c.id,t:c.t,ws:c.ws,s:c.s,d:c.d,why:'No requirement linked'+(c.nb?' · not in build list':'')+(c.nb?'':(c.fl.includes('P')?' · has PBIs':' · no PBI')+(c.fl.includes('E')?'':' · no Epic'))+(c.tg?' · '+c.tg:''),x:c}))},
  {k:'PBI',lab:'PBIs',rows:()=>P.filter(p=>p.rc<0).map(p=>({ty:'PBI',id:p.id,t:p.t,ws:p.ws,s:p.s,d:p.d,why:'No parent',x:p}))}
];
UN.forEach(u=>u.all=u.rows());

/* filters */
const F={ws:new Set(),mo:new Set(),kdd:new Set(),ct:new Set(),l1:new Set(),rwl:new Set(),l2:new Set(),kws:new Set(),kty:new Set(),pkty:new Set(),pbt:new Set(),lkty:new Set(),rws:new Set(),rmo:new Set(),rty:new Set(),rst:new Set(),rfm:new Set(),ras:new Set(),gws:new Set(),gct:new Set()};
const RA_OPEN=[...new Set(R.map(r=>r.s))].filter(s=>!RAID_CLOSED.has(s));RA_OPEN.forEach(s=>F.rst.add(s));
const TYN={A:'Action',R:'Risk',I:'Issue'};const FIRMS={{json:raid_firms}};
const okWs=x=>!F.ws.size||F.ws.has(x.ws);
const okMo=x=>!F.mo.size||F.mo.has(mo(x.d));
const okCt=x=>!F.ct.size||[...x.cts].some(c=>F.ct.has(c));
const okL1=x=>!F.l1.size||!x.l1s||[...x.l1s].some(c=>F.l1.has(c));
const ok=x=>okWs(x)&&okMo(x)&&okCt(x)&&okL1(x);
const okKt=k=>!F.lkty.size||F.lkty.has(k.ty);
const okK=k=>ok(k)&&okKt(k)&&(!F.kdd.size||F.kdd.has(k.s));

function MS(el,key,label,opts){
  const btn=document.createElement('button');btn.type='button';btn.id='btn-'+key;
  const pop=document.createElement('div');pop.className='pop';pop.hidden=true;el.append(btn,pop);
  const optLabel=v=>{const o=opts().find(o=>o.v===v);return o?o.t:v};
  function draw(){
    const s=F[key];btn.classList.toggle('on',s.size>0);
    const v=!s.size?'All':s.size===1?optLabel([...s][0]):s.size+' selected';
    btn.innerHTML=`<span><span class="k">${label}:</span> <span class="v">${esc(v)}</span></span><span class="chev"></span>`;
    pop.innerHTML=`<div class="row"><button type="button" class="lnk" data-a="all">Select all</button><button type="button" class="lnk" data-a="clr">Clear</button></div>`+
      opts().map((o,i)=>`${o.sep?'<div class="mo-sep"></div>':''}<label><input type="checkbox" id="${key}-${i}" value="${esc(o.v)}" ${s.has(o.v)?'checked':''}> ${esc(o.t)}<span class="c">${o.c??''}</span></label>`).join('');
  }
  btn.addEventListener('click',e=>{e.stopPropagation();const open=pop.hidden;document.querySelectorAll('.pop').forEach(p=>p.hidden=true);pop.hidden=!open;});
  pop.addEventListener('click',e=>{e.stopPropagation();const a=e.target.dataset&&e.target.dataset.a;
    if(a==='all'){opts().forEach(o=>F[key].add(o.v));update(true);}
    if(a==='clr'){F[key].clear();update(true);}});
  pop.addEventListener('change',e=>{const v=e.target.value;e.target.checked?F[key].add(v):F[key].delete(v);update(true);});
  return {draw};
}
document.addEventListener('click',()=>document.querySelectorAll('.pop').forEach(p=>p.hidden=true));
const NOL2K='No L2 / L4 linked';const kL2=k=>k.e.length?((E[k.e[0]].l1||'L1 UNKNOWN')+' › '+(E[k.e[0]].l2||'L2 UNKNOWN')):NOL2K;
const KTYPES=[...new Set(K.map(k=>k.ty).filter(Boolean))].sort((a,b)=>K.filter(k=>k.ty===b).length-K.filter(k=>k.ty===a).length);
const ALLITEMS=[...W,...K,...Q,...C,...P,...R];
const sl=[
  MS($('msWs'),'ws','Workstream',()=>WSO.map(w=>({v:w,t:w,c:Q.filter(q=>q.ws===w).length+' reqs'}))),
  MS($('msMo'),'mo','Target month',()=>[...MONTHS.map(m=>({v:m,t:moLabel(m),c:ALLITEMS.filter(x=>mo(x.d)===m).length})),{v:NOD,t:'No target date',c:ALLITEMS.filter(x=>!x.d).length,sep:1}]),
  MS($('msKdd'),'kdd','KDD state',()=>KST.map(s=>({v:s,t:s,c:K.filter(k=>k.s===s).length}))),
  MS($('msL2'),'l2','L2 BPH',()=>{const c={};K.forEach(k=>{const l=kL2(k);c[l]=(c[l]||0)+1});return Object.keys(c).sort((a,b)=>a===NOL2K?1:b===NOL2K?-1:a.localeCompare(b,undefined,{numeric:true})).map(l=>({v:l,t:l,c:c[l]}))}),
  MS($('msKty'),'kty','KDD type',()=>KTYPES.map(t=>({v:t,t,c:K.filter(k=>k.ty===t).length}))),
  MS($('msL1'),'l1','L1',()=>[...L1S.map(l=>({v:l,t:l,c:E.filter(e=>e.l1===l).length+' L4'})),{v:NOL1,t:NOL1,sep:1}]),
  MS($('msRwl'),'rwl','Workshop link',()=>[{v:'L',t:'Linked to a workshop',c:R.filter(r=>r.wsl.length).length},{v:'N',t:'Not linked',c:R.filter(r=>!r.wsl.length).length}]),
  MS($('msLkty'),'lkty','KDD type',()=>KTYPES.map(t=>({v:t,t,c:K.filter(k=>k.ty===t).length}))),
  MS($('msPkty'),'pkty','KDD type',()=>KTYPES.map(t=>({v:t,t,c:K.filter(k=>k.ty===t).length}))),
  MS($('msPbt'),'pbt','Build type',()=>['Configuration','RICEFW','No parent'].map(t=>({v:t,t,c:P.filter(p=>isBuildPBI(p)&&btype(p)===t).length})).filter(o=>o.c||o.v!=='No parent')),
  MS($('msKws'),'kws','Workstream',()=>WSO.map(w=>({v:w,t:w,c:K.filter(k=>k.ws===w).length})).filter(o=>o.c)),
  MS($('msRws'),'rws','Workstream',()=>{const c={};R.forEach(r=>c[r.ws]=(c[r.ws]||0)+1);return WSO.filter(w=>c[w]).map(w=>({v:w,t:w==='Cross-stream'?'Technical':w,c:c[w]}))}),
  MS($('msRmo'),'rmo','Target month',()=>{const c={};R.forEach(r=>{const m=mo(r.d);c[m]=(c[m]||0)+1});return [...Object.keys(c).filter(m=>m!==NOD).sort().map(m=>({v:m,t:moLabel(m),c:c[m]})),...(c[NOD]?[{v:NOD,t:'No target date',c:c[NOD],sep:1}]:[])]}),
  MS($('msRty'),'rty','Type',()=>['A','R','I'].map(t=>({v:t,t:TYN[t],c:R.filter(r=>r.ty===t).length}))),
  MS($('msRst'),'rst','State',()=>{const c={};R.forEach(r=>c[r.s]=(c[r.s]||0)+1);return [...RA_OPEN.sort(),...[...RAID_CLOSED].filter(s=>c[s])].map((s,i)=>({v:s,t:s+(RAID_CLOSED.has(s)?' (closed)':''),c:c[s]||0,sep:RAID_CLOSED.has(s)&&!RAID_CLOSED.has([...RA_OPEN.sort(),...RAID_CLOSED][i-1])}))}),
  MS($('msRfm'),'rfm','Organization',()=>FIRMS.map(f=>({v:f,t:f,c:R.filter(r=>r.fm===f).length}))),
  MS($('msRas'),'ras','Assignee',()=>{const c={};R.forEach(r=>c[r.a]=(c[r.a]||0)+1);return Object.keys(c).sort().map(a=>({v:a,t:a,c:c[a]}))}),
  MS($('msGws'),'gws','Workstream',()=>WSO.map(w=>({v:w,t:w}))),
  MS($('msGct'),'gct','Complex topic',()=>[...CTS.map(c=>({v:c,t:c})),{v:NOCT,t:NOCT,sep:1},{v:NOL4,t:NOL4}]),
  MS($('msCt'),'ct','Complex topic',()=>[...CTS.map(c=>({v:c,t:c,c:W.filter(w=>w.ct===c).length+' ws'})),{v:NOCT,t:NOCT,sep:1},{v:NOL4,t:NOL4}])
];
let VIEW='L4',UT='ALL',NEED=false;
const ADO={{json:ado_workitem_url}};
const hasWs=e=>e.w.some(w=>w.s!=='Cancelled');
$('reset').addEventListener('click',()=>{Object.values(F).forEach(s=>s.clear());RA_OPEN.forEach(s=>F.rst.add(s));$('q').value='';NEED=false;update();});
$('needBtn').addEventListener('click',()=>{NEED=!NEED;VIEW='L4';render();if(NEED)$('tabL4').scrollIntoView?.({behavior:'smooth',block:'start'})});
$('rq').addEventListener('input',()=>renderReg());$('lateOnly').addEventListener('change',()=>renderReg());$('chkOnly').addEventListener('change',()=>renderReg());
const CLOSED=new Set(),RCLOSED=new Set();
$('raq').addEventListener('input',()=>renderRaid());
$('raReset').addEventListener('click',()=>{RFOCUS=null;['rws','rmo','rty','rfm','ras','rwl'].forEach(k=>F[k].clear());F.rst.clear();RA_OPEN.forEach(s=>F.rst.add(s));$('raq').value='';$('raLate').checked=false;update()});$('raLate').addEventListener('change',()=>renderRaid());
$('raBody').addEventListener('click',e=>{const g=e.target.closest('tr.grp');if(!g)return;const k=g.dataset.g;RCLOSED.has(k)?RCLOSED.delete(k):RCLOSED.add(k);renderRaid()});
$('raExp').addEventListener('click',()=>{if(RCLOSED.size)RCLOSED.clear();else RAGROUPS.forEach(g=>RCLOSED.add(g));renderRaid()});
$('raFirm').addEventListener('click',e=>{const b=e.target.closest('.firm');if(!b)return;const f=b.dataset.f;F.rfm.has(f)&&F.rfm.size===1?F.rfm.clear():(F.rfm.clear(),F.rfm.add(f));update()});
$('raTop').addEventListener('click',e=>{const b=e.target.closest('.top');if(!b)return;const a=b.dataset.a;F.ras.has(a)&&F.ras.size===1?F.ras.clear():(F.ras.clear(),F.rfm.clear(),F.ras.add(a));update()});
$('regBody').addEventListener('click',e=>{const g=e.target.closest('tr.grp');if(!g)return;const k=g.dataset.g;CLOSED.has(k)?CLOSED.delete(k):CLOSED.add(k);renderReg()});
$('regExp').addEventListener('click',()=>{if(CLOSED.size){CLOSED.clear()}else{REGGROUPS.forEach(g=>CLOSED.add(g))}renderReg()});
$('q').addEventListener('input',()=>renderTable());
$('kStates').addEventListener('click',e=>{const b=e.target.closest('.st');if(!b)return;const s=b.dataset.s;F.kdd.has(s)?F.kdd.delete(s):F.kdd.add(s);update();});
$('tabL4').addEventListener('click',()=>{VIEW='L4';renderTable()});
$('tabUn').addEventListener('click',()=>{VIEW='UN';renderTable()});
$('uTypes').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;UT=b.dataset.t;renderTable()});

function update(keepPop){
  const openIdx=[...document.querySelectorAll('.pop')].findIndex(p=>!p.hidden);
  sl.forEach(s=>s.draw());
  if(keepPop&&openIdx>=0)document.querySelectorAll('.pop')[openIdx].hidden=false;
  render();
}
const SCAT=s=>s==='Completed'||s==='Ready for Acceptance'?'done':s==='In Progress'?'prog':s==='Blocked'?'blk':s==='Planned'?'pln':'new';
function sbar(items){
  const n=items.length,c={done:0,prog:0,blk:0,pln:0,new:0};items.forEach(i=>c[SCAT(i.s)]++);
  const seg=(k,col,lab)=>n&&c[k]?`<span style="width:${c[k]/n*100}%;background:${col}" title="${lab}: ${c[k]}"></span>`:'';
  return {html:`<div class="sbar">${seg('done','var(--good)','Completed / RFA')}${seg('prog','var(--accent)','In progress')}${seg('blk','var(--crit)','Blocked')}${seg('pln','var(--planned)','Planned')}</div>`,c,n};
}
const fmtD=d=>new Date(d+'T12:00:00').toLocaleDateString('en-US',{day:'numeric',month:'short',year:'2-digit'});
const days=(a,b)=>Math.round((new Date(a+'T12:00:00')-new Date(b+'T12:00:00'))/864e5);
const epicVisible=e=>okWs(e)&&okCt(e)&&okL1(e)&&(!F.mo.size||e.w.some(okMo)||e.k.some(okMo)||e.q.some(okMo));

let FE=[];
function render(){
  const fw=W.filter(ok),fkAll=K.filter(k=>ok(k)&&okKt(k)),fk=fkAll.filter(okK),fq=Q.filter(q=>q.s!=='Rejected'&&ok(q)),nRejQ=Q.filter(q=>q.s==='Rejected'&&ok(q)).length,fc=C.filter(ok),fp=P.filter(ok);
  FE=E.filter(epicVisible);
  $('scope').textContent=`${FE.length} of ${E.length} L4 Epics in view`;

  /* RAID */
  const fr=R.filter(r=>!RAID_CLOSED.has(r.s));
  const risks=fr.filter(r=>r.ty==='R'),iss=fr.filter(r=>r.ty==='I'),acts=fr.filter(r=>r.ty==='A');
  const od=a=>a.filter(r=>r.d&&r.d<ASOF).length;
  $('kRisk').textContent=risks.length;
  $('kRiskM').innerHTML=`<b class="w">${iss.length}</b> open issue${iss.length===1?'':'s'} · <b class="r">${od(risks)}</b> overdue`;
  $('kAct').textContent=acts.length;
  $('kActM').innerHTML=`<b class="r">${od(acts)}</b> overdue · <b>${acts.filter(a=>a.s==='Blocked'||a.s==='On Hold').length}</b> blocked/on hold`;

  /* workshops */
  const live=fw.filter(w=>w.s!=='Cancelled'),canc=fw.length-live.length;
  const comp=live.filter(w=>w.s==='Completed'),ptd=live.filter(w=>w.d&&w.d<=ASOF);
  const overdue=ptd.filter(w=>w.s!=='Completed').length;
  $('wDone').textContent=comp.length;$('wPtd').textContent=`completed / ${live.length} in scope`;$('wPct').textContent=pct(comp.length,live.length)+'%';
  const l4w=new Set();live.forEach(w=>w.e.forEach(i=>l4w.add(i)));
  $('wFacts').innerHTML=`<span>Post-workshop alignment <strong>${live.filter(w=>w.s==='Post Workshop Alignment').length}</strong></span><span>Planned to date <strong>${ptd.length}</strong></span><span>Past target, not completed <strong class="w">${overdue}</strong></span><span>L4s with workshops <strong>${l4w.size}</strong></span><span>No L4 link <strong class="r">${live.filter(w=>!w.e.length).length}</strong></span>`;
  $('wPhase').innerHTML=['Initiate','Validate','Align'].map(p=>{const a=live.filter(w=>w.ph===p);const h=a.filter(w=>w.s==='Completed').length;return `<div class="phase"><div class="k">${p}</div><div class="v num">${h}<small> / ${a.length}</small></div></div>`}).join('');
  const needL=FE.filter(e=>!hasWs(e));
  $('needBtn').textContent=`${needL.length} of ${FE.length} L4s need a workshop plan`;$('needBtn').setAttribute('aria-pressed',NEED);
  $('wPlan').innerHTML='<span class="h">Stream</span><span class="h">With workshops</span><span class="h" style="text-align:right">Have</span><span class="h" style="text-align:right">Need</span>'+WSO.map(s=>{const a=FE.filter(e=>e.ws===s);if(!a.length)return '';const h=a.filter(hasWs).length;
    return `<span class="w">${s}</span><div class="bar"><span style="width:${h/a.length*100}%"></span></div><span class="n num">${h}/${a.length}</span><span class="n num ${a.length-h?'r':''}">${a.length-h}</span>`}).join('');
  const groups=CTS.map(c=>{const g=live.filter(w=>w.ct===c);const l=new Set();g.forEach(w=>w.e.forEach(i=>l.add(i)));return{c,scope:g.length,ptd:g.filter(w=>w.d&&w.d<=ASOF).length,done:g.filter(w=>w.s==='Completed').length,l4:l.size}}).filter(g=>g.scope).sort((a,b)=>b.scope-a.scope);
  const mx=Math.max(1,...groups.map(g=>g.scope));
  const noct=live.filter(w=>w.ct===NOCT);
  $('ctRows').innerHTML=(groups.length?groups.map(g=>`<div class="ctr ${g.done<g.ptd?'lag':''}"><div><div class="name" title="${esc(g.c)}">${esc(g.c)}<span class="l4">${g.l4} L4</span></div>
    <div class="track"><div class="sc" style="width:${g.scope/mx*100}%"></div>${g.ptd?`<div class="ptd" style="width:${g.ptd/mx*100}%"></div>`:''}<div class="act" style="width:max(0px,calc(${g.done/mx*100}% - 2px))"></div></div></div>
    <div class="v num">${g.done}<small>/${g.scope}</small></div></div>`).join(''):'<div class="empty">No complex-topic workshops in this filter.</div>')+
    (noct.length?`<div class="facts" style="margin-top:2px"><span>${NOCT}: <strong>${noct.filter(w=>w.s==='Completed').length}</strong> completed of <strong>${noct.length}</strong></span></div>`:'');

  /* KDDs */
  const fkN=fk.filter(k=>k.s!=='Rejected'),nRej=fk.length-fkN.length;
  const appr=fkN.filter(k=>k.s==='Approved').length,kLk=fkN.filter(k=>k.e.length);
  $('kTot').textContent=fkN.length;$('kAppr').innerHTML=pct(appr,fkN.length)+'% approved'+(nRej?` <span class="note">+${nRej} rejected</span>`:'');
  $('kL4').innerHTML=`${kLk.length} KDDs linked to ${new Set(kLk.flatMap(k=>k.e)).size} L4s · <span class="red">${fkN.length-kLk.length} KDDs with no L4</span>`;
  const kc=Object.fromEntries(KST.map(s=>[s,fk.filter(k=>k.s===s).length]));
  $('kStack').innerHTML=KST.map(s=>kc[s]&&fk.length?`<span style="width:${kc[s]/fk.length*100}%;background:${KCOL[s]}" title="${s}: ${kc[s]}"></span>`:'').join('');
  $('kStates').innerHTML=KST.map(s=>`<button type="button" class="st ${F.kdd.has(s)?'on':''}" data-s="${s}"><i style="background:${KCOL[s]}"></i>${s}<b>${fkAll.filter(k=>k.s===s).length}</b></button>`).join('');
  const open=fk.filter(k=>k.s!=='Approved'&&k.s!=='Rejected').sort((a,b)=>(a.d||'9999')<(b.d||'9999')?-1:1).slice(0,5);
  $('kList').innerHTML=open.length?open.map(k=>{const l4=k.e.length?esc(E[k.e[0]].n):'<span class="red">No L4</span>';let pill='<span class="pill n">No date</span>';
      if(k.d){const dd=days(k.d,ASOF);pill=dd<0?`<span class="pill r">${-dd}d late</span>`:`<span class="pill ${dd<=14?'a':'n'}">Due ${fmtD(k.d)}</span>`}
      return `<div class="li"><span class="id">${esc(k.id)}</span><span><span class="t" title="${esc(k.t)}">${esc(k.t)}</span><small>${esc(k.ws)} · ${l4} · ${esc(k.s)}</small></span>${pill}</div>`}).join(''):'<div class="empty">No open decisions in this filter.</div>';

  /* requirements */
  const n=fq.length,dc={'FIT-OOB':0,'FIT-CFG':0,'GAP':0,'TBD':0};fq.forEach(q=>dc[q.dp]++);
  $('rTot').innerHTML=n.toLocaleString()+(nRejQ?` <span class="note" style="font-size:12px">+${nRejQ} rejected</span>`:'');
  const nw=fq.filter(q=>q.nw).length;
  $('rSrc').innerHTML=`${pct(n-nw,n)}% traced to a workshop · <span class="red">${nw} unlinked</span>`;
  const seg=(k,cls,lab)=>dc[k]?`<div class="${cls}" style="width:${dc[k]/n*100}%" title="${lab}: ${dc[k]}">${dc[k]/n>.1?lab+' '+dc[k]:''}</div>`:'';
  $('rSplit').innerHTML=n?seg('FIT-OOB','c-oob','OOB')+seg('FIT-CFG','c-cfg','Config')+seg('GAP','c-gap','Gap')+seg('TBD','c-tbd','TBD'):'<div style="color:var(--muted)">No requirements</div>';
  const cfgQ=fq.filter(q=>q.dp==='FIT-CFG'),gapQ=fq.filter(q=>q.dp==='GAP');
  const cfgL=cfgQ.filter(q=>q.rc.some(i=>C[i].ty==='Configuration')).length,gapL=gapQ.filter(q=>q.rc.some(i=>C[i].ty==='RICEFW')).length;
  $('rCov').innerHTML=`<div class="covr"><span>Fit Config with a Configuration item · <span class="red">${cfgQ.length-cfgL} without</span></span><span class="n num">${cfgL}/${cfgQ.length}</span><div class="bar"><span style="width:${pct(cfgL,cfgQ.length)}%"></span></div></div>
    <div class="covr"><span>Gap with a RICEFW object · <span class="red">${gapQ.length-gapL} without</span></span><span class="n num">${gapL}/${gapQ.length}</span><div class="bar"><span style="width:${pct(gapL,gapQ.length)}%"></span></div></div>`;
  const wsl=WSO.filter(w=>fq.some(q=>q.ws===w));const wmx=Math.max(1,...wsl.map(w=>fq.filter(q=>q.ws===w).length));
  $('rWs').innerHTML=wsl.map(w=>{const a=fq.filter(q=>q.ws===w),c={'FIT-OOB':0,'FIT-CFG':0,'GAP':0,'TBD':0};a.forEach(q=>c[q.dp]++);
    return `<div class="wsr"><span class="w">${w}</span><div class="bar" style="width:${a.length/wmx*100}%" title="OOB ${c['FIT-OOB']} · Config ${c['FIT-CFG']} · Gap ${c.GAP} · TBD ${c.TBD}">${['FIT-OOB','FIT-CFG','GAP','TBD'].map((k,j)=>`<span class="${['c-oob','c-cfg','c-gap','c-tbd'][j]}" style="width:${c[k]/a.length*100}%"></span>`).join('')}</div><span class="n num">${a.length}</span></div>`}).join('')||'<div class="empty">—</div>';

  /* backlog */
  const cfg=fc.filter(c=>c.ty==='Configuration'),ric=fc.filter(c=>c.ty==='RICEFW');
  const pc=cat=>fp.filter(p=>p.c===cat);
  const rsub=p=>{const pre=(p.t||'').split(' - ')[0].trim();if(pre==='FDD'||pre==='FUT')return pre;const m=pre.match(/^(Source|Middleware|Target)\s+(Design|Build)$/i);return m?(m[1][0].toUpperCase()+m[1].slice(1).toLowerCase()+' '+m[2][0].toUpperCase()+m[2].slice(1).toLowerCase()):'OTHER'};
  const fpr=fp.filter(p=>p.rc>=0&&C[p.rc].ty==='RICEFW');const rp=k=>fpr.filter(p=>rsub(p)===k);
  const RLN=[['FDD','PBI FDD'],['Source Design','PBI Source Design'],['Middleware Design','PBI Middleware Design'],['Target Design','PBI Target Design'],['Source Build','PBI Source Build'],['Middleware Build','PBI Middleware Build'],['Target Build','PBI Target Build'],['FUT','PBI FUT'],['OTHER','<span title="ETL, Technical, PI/PO and DnA design and build PBIs">PBI Other ⓘ</span>']];
  const child=(nm,b)=>`<div class="child"><span class="elbow"></span><span class="nm">${nm}</span>${b.html}<span class="pct num"><b>${b.c.done}</b> / ${b.n}${b.c.blk?` · <span style="color:var(--crit)">${b.c.blk} blk</span>`:''}</span></div>`;
  const stchips=arr=>{const m={};arr.filter(c=>c.s!=='—').forEach(c=>m[c.s]=(m[c.s]||0)+1);return Object.entries(m).sort((a,b)=>b[1]-a[1]).map(([s,v])=>`<span>${esc(s)} <b>${v}</b></span>`).join('')};
  const cfgUn=cfg.filter(c=>!c.q.length).length,ricUn=ric.filter(c=>!c.q.length).length;
  $('tCfg').innerHTML=`<div class="root"><span class="kind fit">Fit</span><h3>Configuration items</h3><span class="cnt num">${cfg.length}</span></div>
    <div class="types">${stchips(cfg)}<span class="red">No requirement <b class="red">${cfgUn}</b></span></div>
    ${child('PBI CRD',sbar(pc('CRD')))}${child('PBI Config & CUT',sbar(pc('CUT')))}`;
  $('tRic').innerHTML=`<div class="root"><span class="kind gap">Gap</span><h3>RICEFW objects</h3><span class="cnt num">${ric.length}</span></div>
    <div class="types">${stchips(ric)}<span class="red">No requirement <b class="red">${ricUn}</b></span></div>
    ${RLN.map(([k,nm])=>child(nm,sbar(rp(k)))).join('')}`;

  /* chain */
  const pd=fp.filter(p=>SCAT(p.s)==='done').length;
  const L=(k,v,s,u,txt)=>`<div class="link"><span class="k">${k}</span><span class="v num">${v} <small>${s}</small></span><span class="u ${u?'r':'ok'}">${txt||(u?u+' unlinked':'all linked')}</span></div>`;
  const epW=FE.filter(e=>e.w.some(w=>w.s!=='Cancelled')).length,bph=FE.filter(e=>e.bph).length;
  $('chain').innerHTML=
    L('L4 Epics',FE.length,`· ${epW} with workshops`,FE.length-epW,`${FE.length-epW} need workshop plan`)+
    L('Workshops',comp.length,`of ${live.length} completed`,live.filter(w=>!w.e.length).length)+
    L('KDDs',appr,`of ${fkN.length} approved`,fkN.filter(k=>!k.e.length).length)+
    L('Requirements',n.toLocaleString(),'in R6',nw)+
    L('Fit / Gap / TBD',`${dc['FIT-OOB']+dc['FIT-CFG']} / ${dc.GAP} / ${dc.TBD}`,'',0,`${pct(dc.TBD,n)}% still TBD`)+
    L('Config / RICEFW',`${cfg.length} / ${ric.length}`,'',cfgUn+ricUn)+
    (()=>{const np=fp.filter(p=>p.rc<0).length;return L('PBIs',pd,`of ${fp.length.toLocaleString()} done`,np,np?np.toLocaleString()+' no parent':'all have a parent')})();
  renderTable();renderReg();renderRaid();renderPvp();if(typeof renderBurnup==='function')renderBurnup();if(typeof renderWsView==='function')renderWsView();if(typeof renderE2E==='function')renderE2E();
}

function renderTable(){
  $('tabL4').setAttribute('aria-pressed',VIEW==='L4');$('tabUn').setAttribute('aria-pressed',VIEW==='UN');
  const term=$('q').value.trim().toLowerCase();
  // unlinked counts under current filters
  const uf=UN.map(u=>({u,rows:u.all.filter(r=>ok(r.x)&&(!r.isK||((!F.kdd.size||F.kdd.has(r.s))&&okKt(r.x))))}));
  const utot=uf.reduce((a,b)=>a+b.rows.length,0);
  $('unCnt').textContent=utot.toLocaleString();
  $('uTypes').hidden=VIEW!=='UN';
  if(VIEW==='UN'){
    $('uTypes').innerHTML=`<button type="button" data-t="ALL" class="${UT==='ALL'?'on':''}">All<b>${utot}</b></button>`+uf.map(x=>`<button type="button" data-t="${x.u.k}" class="${UT===x.u.k?'on':''}">${x.u.lab}<b>${x.rows.length}</b></button>`).join('');
    let rows=uf.filter(x=>UT==='ALL'||x.u.k===UT).flatMap(x=>x.rows);
    if(term)rows=rows.filter(r=>(r.id+' '+r.t).toLowerCase().includes(term));
    $('tCount').textContent=`${rows.length.toLocaleString()} unlinked items`;
    $('thead').innerHTML='<tr><th>Type</th><th>ID</th><th>Title</th><th>Workstream</th><th>State</th><th>Target date</th><th>Why it is unlinked</th></tr>';
    const cap=600;
    $('tbody').innerHTML=rows.length?rows.slice(0,cap).map(r=>`<tr><td><span class="tchip">${esc(r.ty)}</span></td><td class="m">${esc(r.id)}</td><td><span class="tt" title="${esc(r.t)}">${esc(r.t)}</span></td><td class="m">${esc(r.ws)}</td><td>${esc(r.s)}</td><td class="m">${r.d?fmtD(r.d):'—'}</td><td class="reason">${esc(r.why)}</td></tr>`).join('')+(rows.length>cap?`<tr><td colspan="7" class="empty">Showing first ${cap} of ${rows.length.toLocaleString()}. Narrow with the slicers, type filter or search.</td></tr>`:''):'<tr><td colspan="7" class="empty">No unlinked items in this filter.</td></tr>';
    return;
  }
  const rows=FE.filter(e=>(!NEED||!hasWs(e))&&(!term||(e.n+' '+e.t+' '+e.l1+' '+e.l2+' '+e.l3+' '+e.id).toLowerCase().includes(term)));
  $('tCount').innerHTML=NEED?`<span class="red">${rows.length} L4s need a workshop plan</span>`:`${rows.length} L4s`;
  $('thead').innerHTML='<tr><th>L1</th><th>L2</th><th>L3</th><th>L4 Epic</th><th>Workstream</th><th>Complex topic</th><th class="r">Workshops<br>completed / scope</th><th class="r">KDDs<br>appr / total</th><th class="r">Reqs</th><th class="r">Fit</th><th class="r">Gap</th><th class="r">TBD</th><th class="r">Config</th><th class="r">RICEFW</th><th>PBIs done</th><th>Actions<br>via workshops</th><th>Flag</th></tr>';
  const mini=(a,b)=>b?`<span class="mini"><span style="width:${pct(a,b)}%"></span></span>${a}/${b}`:'—';
  $('tbody').innerHTML=rows.length?rows.map(e=>{
    const w=e.w.filter(x=>x.s!=='Cancelled'&&okMo(x)),wc=w.filter(x=>x.s==='Completed').length,wod=w.filter(x=>x.d&&x.d<=ASOF&&x.s!=='Completed').length;
    const k=e.k.filter(x=>x.s!=='Rejected'&&okMo(x)&&okKt(x)&&(!F.kdd.size||F.kdd.has(x.s))),ka=k.filter(x=>x.s==='Approved').length;
    const q=e.qo.filter(okMo),qvw=q.filter(x=>x.vw).length,fit=q.filter(x=>x.dp==='FIT-OOB'||x.dp==='FIT-CFG').length,gap=q.filter(x=>x.dp==='GAP').length,tbd=q.filter(x=>x.dp==='TBD').length;
    const rcs=new Set();q.forEach(x=>x.rc.forEach(i=>rcs.add(i)));
    let nc=0,nr=0;const pb=[];rcs.forEach(i=>{C[i].ty==='Configuration'?nc++:nr++;pb.push(...C[i].p.filter(okMo))});
    const pdn=pb.filter(p=>SCAT(p.s)==='done').length,blk=pb.filter(p=>p.s==='Blocked').length;
    const needRC=q.some(x=>x.dp==='FIT-CFG'||x.dp==='GAP');
    const h=e.bph?['r','No Epic']:!hasWs(e)?['r','Needs workshop plan']:!w.length?['n','No workshop this month']:!q.length?['r','No requirements']:(needRC&&!rcs.size)?['r','No Config/RICEFW']:blk?['r',`${blk} blocked PBI${blk>1?'s':''}`]:wod?['a',`${wod} workshop${wod>1?'s':''} past target`]:tbd?['a',`${tbd} TBD`]:['g','On track'];
    const cts=[...e.ct];const z=v=>v?'':' zero';
    const UK=v=>/UNKNOWN/.test(v)?`<span class="amb">${esc(v)}</span>`:esc(v);
    return `<tr class="${e.bph?'unl':''}"><td class="l2">${UK(e.l1)}</td><td class="l2">${UK(e.l2)}</td><td class="l2">${UK(e.l3)}</td><td><span class="code">${esc(e.n||'—')}${e.id?' · '+esc(e.id):''}</span><span class="nm">${esc(e.t)}</span></td><td class="m">${e.ws}</td>
      <td>${cts.length?`<span class="ctag" title="${esc(cts.join(', '))}">${esc(cts[0])}${cts.length>1?` +${cts.length-1}`:''}</span>`:'<span class="ctag none">—</span>'}</td>
      <td class="r m${z(w.length)}">${wc} / ${w.length}</td><td class="r m${z(k.length)}">${ka} / ${k.length}</td><td class="r m${z(q.length)}">${q.length}${qvw?`<span class="note" title="Requirement ID has no R6 L4 number, so it is attributed through workshop links"> +${qvw} via workshop</span>`:''}</td><td class="r m">${fit}</td><td class="r m">${gap}</td><td class="r m">${tbd||''}</td>
      <td class="r m${needRC&&!rcs.size?' zero':''}">${nc}</td><td class="r m${needRC&&!rcs.size?' zero':''}">${nr}</td><td class="m${rcs.size&&!pb.length?' zero':''}">${mini(pdn,pb.length)}</td><td>${(()=>{const s=new Map();let nx=new Set();e.w.forEach(w=>{w.acts.forEach(a=>s.set(a.id,a));w.nx.forEach(x=>nx.add(x))});const k='L4:'+e.i;ACTSETS[k]=new Set(s.keys());return actCell([...s.values()],nx.size,'L4 '+(e.n||e.t),k)})()}</td><td><span class="pill ${h[0]}">${h[1]}</span></td></tr>`}).join(''):'<tr><td colspan="17" class="empty">No L4s match these filters.</td></tr>';
}
let REGGROUPS=[];
function renderReg(){
  const term=$('rq').value.trim().toLowerCase(),lateOnly=$('lateOnly').checked,chkOnly=$('chkOnly').checked;
  const NOL2='No L2 / L4 linked';
  let ks=K.filter(k=>(!F.kws.size||F.kws.has(k.ws))&&(!F.kty.size||F.kty.has(k.ty))).map(k=>{
    const eps=k.e.map(i=>E[i]);const l2=eps.length?((eps[0].l1||'L1 UNKNOWN')+' › '+(eps[0].l2||'L2 UNKNOWN')):NOL2;
    const open=k.s!=='Approved'&&k.s!=='Rejected';
    const dl=k.d&&open?days(ASOF,k.d):0;
    const ts=k.f==='C'?['a','Check date']:k.f==='N'?['n','No date']:!open?['n','Decided']:!k.d?['n','No date']:dl>0?['r','Late']:(-dl<=14?['a','Due in 14 days']:['g','On track']);
    return {k,eps,l2,open,dl:dl>0?dl:0,ts};
  });
  if(F.l2.size)ks=ks.filter(x=>F.l2.has(x.l2));
  if(lateOnly||chkOnly)ks=ks.filter(x=>(lateOnly&&x.dl>0)||(chkOnly&&x.k.f==='C'));
  if(term)ks=ks.filter(x=>(x.k.id+' '+x.k.t+' '+x.k.a+' '+x.eps.map(e=>e.n+' '+e.t).join(' ')).toLowerCase().includes(term));
  const g={};ks.forEach(x=>(g[x.l2]=g[x.l2]||[]).push(x));
  REGGROUPS=Object.keys(g).sort((a,b)=>a===NOL2?1:b===NOL2?-1:a.localeCompare(b,undefined,{numeric:true}));
  const late=ks.filter(x=>x.dl>0).length;
  const chk=ks.filter(x=>x.k.f==='C').length;$('regHint').innerHTML=`${ks.length} KDDs · ${REGGROUPS.length} L2s · <span class="red">${late} late</span>${chk?` · <span class="amb">${chk} check date</span>`:''}`;
  $('regCount').textContent=`${ks.length} KDDs`;
  $('regExp').textContent=CLOSED.size?'Expand all':'Collapse all';
  const SP={'Approved':'g','Rejected':'r','Pending Approval':'a','In Analysis':'n','New':'n'};
  $('regBody').innerHTML=REGGROUPS.length?REGGROUPS.map(name=>{
    const arr=g[name].sort((a,b)=>b.dl-a.dl||(a.k.d||'9999').localeCompare(b.k.d||'9999'));
    const lt=arr.filter(x=>x.dl>0).length,op=arr.filter(x=>x.open).length,closed=CLOSED.has(name);
    const head=`<tr class="grp${closed?' closed':''}${name===NOL2?' nol2':''}" data-g="${esc(name)}"><td colspan="9"><span class="cv"></span>${esc(name)}<span class="gm">${arr.length} KDDs · ${op} open${lt?` · <b>${lt} late</b>`:''}</span></td></tr>`;
    if(closed)return head;
    return head+arr.map(x=>{const k=x.k;
      const l4=x.eps.length?x.eps.map(e=>`<span class="code">${esc(e.n)} · L3: ${/UNKNOWN/.test(e.l3)?'<span class="amb">L3 UNKNOWN</span>':esc(e.l3)}</span><span class="nm">${esc(e.t)}</span>`).join('<br>'):'<span class="red">No L4 linked</span>';
      return `<tr><td>${l4}</td><td><a href="${ADO}${encodeURIComponent(k.id)}" target="_blank" rel="noopener noreferrer">${esc(k.id)}</a></td><td><span class="tt2" title="${esc(k.t)}">${esc(k.t)}</span></td><td class="m">${esc(k.ws)}</td><td><span class="pill ${SP[k.s]||'n'}">${esc(k.s)}</span></td><td class="m">${k.f==='C'?`<span class="amb" title="Placeholder date; confirm with the owner">${fmtD(k.d||k.dc)}?</span>`:k.d?fmtD(k.d):k.f==='C'?`<span class="amb" title="Stored as a placeholder date; confirm with the owner">${fmtD(k.dc)}?</span>`:k.f==='N'?'<span class="note" title="Date lookup failed (#N/A) in the source file">#N/A</span>':'—'}</td><td><span class="pill ${x.ts[0]}"${k.f==='N'?' title="Date lookup failed in the source file"':''}>${x.ts[1]}</span></td><td class="r ${x.dl?'late':'m'}">${x.dl?x.dl+'d':''}</td><td>${k.a?esc(k.a):'<span class="ctag none">—</span>'}</td></tr>`}).join('');
  }).join(''):'<tr><td colspan="9" class="empty">No KDDs match these filters.</td></tr>';
}
let RAGROUPS=[];
function renderCrit(){
  const L=R.filter(r=>(r.ty==='R'||r.ty==='I')&&!RAID_CLOSED.has(r.s)&&/raid-critical/i.test(r.tg));
  const isPD=r=>r.d&&r.d<ASOF,ld=r=>isPD(r)?days(ASOF,r.d):0;
  L.sort((a,b)=>ld(b)-ld(a)||(a.d||'9999').localeCompare(b.d||'9999'));
  const head=`<div class="crit-h"><b>Risk/Issues-Critical</b><span>Open risks &amp; issues tagged RAID-Critical in ADO, plus cockpit overrides · always shows every open item, whatever the filters</span><span class="cbadge ${L.length?'on':''}">${L.length} open</span></div>`;
  if(!L.length){$('raCrit').innerHTML=head+'<div class="empty crit-e">No open critical risks or issues.</div>';return}
  $('raCrit').innerHTML=head+`<div class="tblwrap critwrap"><table class="regt"><thead><tr><th>ADO ID</th><th>Type</th><th>Title</th><th>Owner (Org)</th><th>Workstream · Sub-area</th><th>Type PHX</th><th>Target date</th><th>State</th><th class="r">Days overdue</th></tr></thead><tbody>${L.map(r=>{const x=ld(r);const pc=r.s==='Blocked'?'r':r.s==='On Hold'?'a':r.s==='In Progress'||r.s==='Monitoring'?'g':'n';
    return `<tr class="${x?'pd':''}"><td><a href="${ADO}${encodeURIComponent(r.id)}" target="_blank" rel="noopener noreferrer">${esc(r.id)}</a></td><td><span class="ty ${r.ty}">${TYN[r.ty]}</span></td><td><span class="tt2" title="${esc(r.t)}">${esc(r.t)}</span>${r.ovr?' <span class="ovr" title="Flagged critical in the cockpit; not tagged RAID-Critical in ADO">Critical (cockpit override)</span>':''}</td><td>${esc(r.a)} <span class="note">(${esc(r.fm)})</span></td><td>${esc(r.ws==='Cross-stream'?'Technical':r.ws)}${r.sub?` <span class="note">· ${esc(r.sub)}</span>`:''}</td><td>${esc(r.tp)||'—'}</td><td class="m${x?' late':''}">${r.d?fmtD(r.d):'—'}</td><td><span class="pill ${pc}">${esc(r.s)}</span></td><td class="r">${x?`<b class="late">${x}d</b>`:'—'}</td></tr>`}).join('')}</tbody></table></div>`;
}
function renderBars(){
  const RL=R.filter(r=>(!F.rws.size||F.rws.has(r.ws))&&(!F.rmo.size||F.rmo.has(mo(r.d)))&&(!F.rfm.size||F.rfm.has(r.fm))&&(!F.ras.size||F.ras.has(r.a)));
  const KL=K.filter(k=>!F.rws.size||F.rws.has(k.ws));
  const row=(L,name,items,isOpen,isOver,click)=>{const t=items.length,op=items.filter(isOpen),ov=op.filter(isOver).length,nd=op.length-ov,cl=t-op.length;
    const pc=v=>t?v/t*100:0,seg=(v,cls,txt)=>v?`<span class="bseg ${cls}" style="width:${pc(v)}%" title="${txt}: ${v.toLocaleString()} (${Math.round(pc(v))}%)">${pc(v)>=7?v.toLocaleString():''}</span>`:'';
    return `<div class="brow ${click?'clk':''} ${click&&F.rty.size===1&&F.rty.has(click)?'on':''}" ${click?`data-t="${click}" role="button" tabindex="0"`:''}><span class="blab"><b>${L}</b> ${name}</span><span class="bbar">${t?seg(ov,'ov','Open · overdue')+seg(nd,'nd','Open · not yet due')+seg(cl,'cl','Closed'):'<span class="bempty">No items</span>'}</span><span class="bnum"><b>${t.toLocaleString()}</b> total · <b>${op.length.toLocaleString()}</b> open (${t?Math.round(op.length/t*100):0}%) · <b class="${ov?'red':''}">${ov.toLocaleString()}</b> overdue</span></div>`};
  const rOpen=r=>!RAID_CLOSED.has(r.s),rOver=r=>r.d&&r.d<ASOF;
  $('raBars').innerHTML=`<div class="bhead"><b>RAID overview</b><span class="note">Total vs open · each bar is 100% of its type</span></div>`
   +row('R','Risks',RL.filter(r=>r.ty==='R'),rOpen,rOver,'R')+row('A','Actions',RL.filter(r=>r.ty==='A'),rOpen,rOver,'A')+row('I','Issues',RL.filter(r=>r.ty==='I'),rOpen,rOver,'I')
   +row('D','Decisions',KL,k=>k.s!=='Approved'&&k.s!=='Rejected',k=>k.d&&k.d<=ASOF,null)
   +`<div class="bleg"><span><i class="ov"></i>Open · overdue</span><span><i class="nd"></i>Open · not yet due</span><span><i class="cl"></i>Closed</span><span class="note">D = KDDs from the KDD export (open = New, In Analysis, Pending Approval); follows the Workstream slicer only.</span></div>`;
}
$('raBars').addEventListener('click',e=>{const r=e.target.closest('.brow.clk');if(!r)return;const t=r.dataset.t;if(F.rty.size===1&&F.rty.has(t))F.rty.clear();else{F.rty.clear();F.rty.add(t)}update(false)});
$('raBars').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('clk')){e.preventDefault();e.target.click()}});
function renderRaid(){renderBars();renderCrit();
  const term=$('raq').value.trim().toLowerCase(),lateOnly=$('raLate').checked;
  const base=R.filter(r=>(!F.rws.size||F.rws.has(r.ws))&&(!F.rmo.size||F.rmo.has(mo(r.d)))&&(!F.rty.size||F.rty.has(r.ty))&&(!F.rwl.size||(F.rwl.has('L')&&r.wsl.length)||(F.rwl.has('N')&&!r.wsl.length))&&(!RFOCUS||RFOCUS.ids.has(r.id)));
  $('raFocus').innerHTML=RFOCUS?`<span class="fchip">Showing actions linked to <b>${esc(RFOCUS.label)}</b> <button type="button" id="raFocusX" aria-label="Clear">×</button></span>`:'';
  const isPD=r=>!RAID_CLOSED.has(r.s)&&r.d&&r.d<ASOF;
  const lateD=r=>isPD(r)?days(ASOF,r.d):0;
  // ribbon (type + page slicers; ignores firm/assignee/state so tiles stay comparable)
  const op=base.filter(r=>!RAID_CLOSED.has(r.s)),pd=op.filter(isPD);
  
  $('raFirm').innerHTML=FIRMS.map(f=>{const o=op.filter(r=>r.fm===f),p=o.filter(isPD).length;if(!base.some(r=>r.fm===f))return '';
    return `<button type="button" class="firm ${F.rfm.has(f)?'on':''}" data-f="${esc(f)}"><span class="fn">${esc(f)}</span><span class="fv num"><b>${p}</b><small> / ${o.length} due</small></span><span class="fb"><span style="width:${pct(p,o.length)}%"></span></span><span class="fp">${o.length?pct(p,o.length)+'% past due':'nothing open'}</span></button>`}).join('');
  const ac={};pd.forEach(r=>{const x=ac[r.a]=ac[r.a]||{n:0,m:0,fm:r.fm};x.n++;x.m=Math.max(x.m,lateD(r))});
  const top=Object.entries(ac).sort((a,b)=>b[1].n-a[1].n||b[1].m-a[1].m).slice(0,5);
  $('raTop').innerHTML=top.length?top.map(([a,x],i)=>`<button type="button" class="top ${F.ras.has(a)?'on':''}" data-a="${esc(a)}" title="${esc(a)} · ${esc(x.fm)}"><span class="rk">${i+1}</span><span class="tn">${esc(a)} <span class="org">(${esc(x.fm)})</span></span><span class="tv num">${x.n}<small> · oldest ${x.m}d</small></span></button>`).join(''):'<span class="empty">No past-due items.</span>';
  // list
  let rows=base.filter(r=>(!F.rst.size||F.rst.has(r.s))&&(!F.rfm.size||F.rfm.has(r.fm))&&(!F.ras.size||F.ras.has(r.a)));
  if(lateOnly)rows=rows.filter(isPD);
  if(term)rows=rows.filter(r=>(r.id+' '+r.t+' '+r.a+' '+r.sub+' '+r.wsl.map(w=>w.id+' '+w.t).join(' ')).toLowerCase().includes(term));
  const WN=w=>w==='Cross-stream'?'Technical':w;
  const g={};rows.forEach(r=>(g[WN(r.ws)]=g[WN(r.ws)]||[]).push(r));
  RAGROUPS=['O2C','M2O','D2D','S2P','R2R','OCM','Unassigned','Technical'].filter(w=>g[w]);
  $('raHint').innerHTML=`${rows.length} items · <span class="red">${rows.filter(isPD).length} past due</span>`;
  $('raExp').textContent=RCLOSED.size?'Expand all':'Collapse all';
  const SPc=s=>RAID_CLOSED.has(s)?'n':s==='Blocked'?'r':s==='On Hold'?'a':s==='In Progress'||s==='Monitoring'?'g':'n';
  $('raBody').innerHTML=RAGROUPS.length?RAGROUPS.map(w=>{
    const arr=g[w].sort((a,b)=>lateD(b)-lateD(a)||(RAID_CLOSED.has(a.s)-RAID_CLOSED.has(b.s))||(a.d||'9999').localeCompare(b.d||'9999'));
    const o=arr.filter(r=>!RAID_CLOSED.has(r.s)).length,p=arr.filter(isPD).length,closed=RCLOSED.has(w);
    const head=`<tr class="grp${closed?' closed':''}" data-g="${w}"><td colspan="11"><span class="cv"></span>${w}<span class="gm">${arr.length} items · ${o} open${p?` · <b>${p} past due</b>`:''} · ${arr.length-o} closed</span></td></tr>`;
    if(closed)return head;
    return head+arr.map(r=>{const cl=RAID_CLOSED.has(r.s),ld=lateD(r);
      return `<tr class="${cl?'cl':ld?'pd':''}"><td><span class="ty ${r.ty}">${TYN[r.ty]}</span></td><td><a href="${ADO}${encodeURIComponent(r.id)}" target="_blank" rel="noopener noreferrer">${esc(r.id)}</a></td><td><span class="tt2" title="${esc(r.t)}">${esc(r.t)}</span></td><td>${r.wsl.length?r.wsl.map(w=>`<a href="${ADO}${encodeURIComponent(w.id)}" target="_blank" rel="noopener noreferrer">${esc(w.id)}</a> <span class="wsn">${esc(wsShort(w))}</span>`).join('<br>'):'<span class="ctag none">—</span>'}</td><td class="note">${esc(r.sub)||'—'}</td><td class="note">${esc(r.tp)||'—'}</td><td class="m${ld?' late':''}">${r.d?fmtD(r.d):'—'}</td><td>${esc(r.a)}</td><td class="fmt">${esc(r.fm)}</td><td><span class="pill ${SPc(r.s)}">${esc(r.s)}</span></td><td class="r ${ld?'late':'m'}">${ld?ld+'d':''}</td></tr>`}).join('');
  }).join(''):'<tr><td colspan="11" class="empty">No RAID items match these filters.</td></tr>';
}
function gaugeSVG(c){
  const cx=120,cy=108,R=84,W=18,T=Math.max(c.t,1);
  const ang=v=>Math.PI*(1-Math.max(0,Math.min(1,v/T)));
  const pt=(v,rad)=>[cx+rad*Math.cos(ang(v)),cy-rad*Math.sin(ang(v))];
  const arc=(a,b,col,w)=>{if(b<=a)return '';const [x1,y1]=pt(a,R),[x2,y2]=pt(b,R);return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} A${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}" stroke="${col}" stroke-width="${w||W}" fill="none"/>`};
  const ticks=[0,.25,.5,.75,1].map(f=>{const v=f*T,[x,y]=pt(v,R+17),[a1,b1]=pt(v,R-W/2-1),[a2,b2]=pt(v,R-W/2-6);
    return `<line x1="${a1.toFixed(1)}" y1="${b1.toFixed(1)}" x2="${a2.toFixed(1)}" y2="${b2.toFixed(1)}" stroke="var(--muted)" stroke-width="1"/><text class="gt" x="${x.toFixed(1)}" y="${(y+3).toFixed(1)}" text-anchor="middle">${Math.round(f*c.t).toLocaleString()}</text>`}).join('');
  const ok=c.a>=c.p,nc=ok?'var(--good)':'var(--crit)';
  const [mx,my]=pt(c.p,R+W/2+2),[mx2,my2]=pt(c.p,R-W/2-2),a=ang(c.p);
  const tri=[[0,0],[-6,-9],[6,-9]].map(([dx,dy])=>{const ca=Math.cos(a),sa=Math.sin(a);const ox=mx+(-dy)*ca+dx*sa,oy=my-(-dy)*sa+dx*ca;return ox.toFixed(1)+','+oy.toFixed(1)}).join(' ');
  const [nx,ny]=pt(c.a,R-10);
  const hit=c.p?Math.round(c.a/c.p*100):null;let hitSvg='';
  if(hit!==null){const th=ang(Math.min(c.a,T));const [hx0,hy0]=pt(Math.min(c.a,T),R-34);let hx=hx0+Math.sin(th)*15,hy=hy0+Math.cos(th)*15;
    hx=Math.max(26,Math.min(240-26,hx));hy=Math.max(14,Math.min(cy-6,hy));const txt=hit+'%',w=txt.length*7+10;
    hitSvg=`<g class="hit ${ok?'ok':'bad'}"><rect x="${(hx-w/2).toFixed(1)}" y="${(hy-9).toFixed(1)}" width="${w}" height="17" rx="8.5"/><text x="${hx.toFixed(1)}" y="${(hy+4).toFixed(1)}" text-anchor="middle">${txt}</text></g>`}
  const digits=String(c.a).padStart(Math.max(4,String(c.a).length),'0').split('');
  const dw=15,dx0=cx-digits.length*dw/2;
  const odo=digits.map((d,i)=>`<rect x="${dx0+i*dw}" y="${cy+16}" width="${dw-2}" height="20" rx="2" fill="var(--ink)"/><text class="od" x="${dx0+i*dw+(dw-2)/2}" y="${cy+31}" text-anchor="middle">${d}</text>`).join('');
  return `<svg viewBox="0 0 240 168" role="img" aria-label="${c.a} ${c.lab}, plan to date ${c.p}, overall planned ${c.t}">
    ${arc(0,T,'var(--ns)')}${arc(0,c.p,'var(--planned)')}${arc(0,Math.min(c.a,T),nc,6)}${ticks}
    <line x1="${mx.toFixed(1)}" y1="${my.toFixed(1)}" x2="${mx2.toFixed(1)}" y2="${my2.toFixed(1)}" stroke="var(--brand)" stroke-width="2.5"/>
    <polygon points="${tri}" fill="var(--brand)"/>
    <line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" stroke="${nc}" stroke-width="3.5" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="7" fill="${nc}" stroke="var(--surface)" stroke-width="2"/>
    ${hitSvg}${odo}<text class="ol2" x="${cx}" y="${cy+50}" text-anchor="middle">${c.lab}</text></svg>`;
}
const isDMp=p=>/ - Conversion\b/.test(p.t||'')||/^ETL /.test(p.t||'');
const isOCMp=p=>{const pre=(p.t||'').split(' - ')[0].trim();return !(pre==='CRD'||pre.startsWith('Config & CUT')||pre==='FDD'||pre==='FUT'||/design/i.test(pre)||/build/i.test(pre)||/^PI ?\/ ?PO/i.test(pre))};
const isBuildPBI=p=>!isDMp(p)&&!isOCMp(p);
const pbiUnl=p=>p.rc<0;const btype=p=>p.rc>=0?C[p.rc].ty:'No parent';
const pbiWhy=p=>'No parent build item (Configuration or RICEFW)';
let PVLINK='ALL';
let PVTAB='KDD';const PVSHOW={},PVCLOSED=new Set();
const UPTO=(()=>{const d=new Date(ASOF+'T12:00:00');d.setDate(d.getDate()+14);return d.toISOString().slice(0,10)})();
const pbiType=p=>{const pre=(p.t||'').split(' - ')[0].trim();if(pre==='CRD')return 'CRD';if(pre.startsWith('Config & CUT'))return 'Config & CUT';if(pre==='FDD'||pre==='FUT')return pre;if(/design/i.test(pre))return 'Design';if(/build/i.test(pre)||/^PI ?\/ ?PO/i.test(pre))return 'Build';return 'OCM / Training'};
const topWs=(rows,k)=>{const c={};rows.forEach(x=>c[x.ws]=(c[x.ws]||0)+1);const t=Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,5);
  return t.length?`<span class="wchips"><span class="tlab">Top 5</span>${t.map(([w,n])=>`<button type="button" class="wchip ${k} ${F.gws.size===1&&F.gws.has(w)?'on':''}" data-w="${esc(w)}" title="Filter the panel to ${esc(w==='Cross-stream'?'Technical':w)}">${esc(w==='Cross-stream'?'Technical':w)} <b>${n.toLocaleString()}</b></button>`).join('')}</span>`:''};
let PVORG='';const ORGS={{json:org_codes}},ORGN={{json:org_names}};
const OW=(a,og,lk)=>(a?esc(a):'<span class="ctag none">—</span>')+(lk==='late'?(og?` <span class="ogc" title="${ORGN[og]}">(${og})</span>`:' <span class="ogc na">(Unassigned)</span>'):'');
const orgChips=rows=>{const g={};rows.forEach(x=>{const o=x.og||'NA';(g[o]=g[o]||{n:0,w:{}}).n++;g[o].w[x.ws]=(g[o].w[x.ws]||0)+1});
  const keys=ORGS.filter(o=>g[o]);if(!keys.length)return '';
  return `<span class="wchips"><span class="tlab">By organization</span>${keys.map(o=>{const ws=Object.entries(g[o].w).sort((a,b)=>b[1]-a[1]).slice(0,5);
    return `<span class="ochip ${PVORG===o?'on':''}"><button type="button" class="oname" data-o="${o}" title="Show only ${ORGN[o]} items">${o==='NA'?'Unassigned':o} <b>${g[o].n}</b></button><span class="ows">(${ws.map(([w,n])=>`<button type="button" class="wchip late inl" data-w="${esc(w)}" title="Filter the panel to ${esc(w==='Cross-stream'?'Technical':w)}">${esc(w==='Cross-stream'?'Technical':w)} ${n}</button>`).join(' · ')})</span></span>`}).join('')}</span>`};
function renderPvTabs(okG){
  document.querySelectorAll('#pvTabs .ptab').forEach(b=>b.setAttribute('aria-selected',b.dataset.t===PVTAB));
  document.querySelectorAll('#pvCards .gcard').forEach((c,i)=>c.classList.toggle('sel',['KDD','REQ','PBI','WS','DM','OCM'][i]===PVTAB));
  const term=$('pvq').value.trim().toLowerCase();
  const L=id=>`<a href="${ADO}${encodeURIComponent(id)}" target="_blank" rel="noopener noreferrer">${esc(id)}</a>`;
  const TT=t=>`<span class="tt2" title="${esc(t)}">${esc(t)}</span>`;
  const D=d=>d?fmtD(d):'—';
  const late=(x,isDone)=>!isDone(x)&&x.d&&x.d<=ASOF?days(ASOF,x.d):0;
  const pill=s=>`<span class="pill ${/Completed|Approved/.test(s)?'g':/Blocked|Rejected/.test(s)?'r':/Progress|Pending|Post Workshop|Partial|Ready/.test(s)?'a':'n'}">${esc(s)}</span>`;
  const DASH='<span class="ctag none">—</span>';
  let cfg;
  if(PVTAB==='WS')cfg={items:W.filter(w=>w.s!=='Cancelled'&&okG(w)),done:w=>w.s==='Completed',doneLab:'Completed',
    cols:['ADO ID','Title','Workstream','Complex topic','Linked L4s','Actions','Target date','State','Days overdue'],
    row:(w,ld)=>[L(w.id),TT(w.t),esc(w.ws),w.ct===NOCT?DASH:`<span class="ctag">${esc(w.ct)}</span>`,w.e.length?`<span class="note" title="${esc(w.e.map(i=>E[i].n+' '+E[i].t).join('\n'))}">${esc(w.e.slice(0,2).map(i=>E[i].n).join(', '))}${w.e.length>2?' +'+(w.e.length-2):''}</span>`:'<span class="red">No L4</span>',(()=>{const k='W:'+w.id;ACTSETS[k]=new Set(w.acts.map(a=>a.id));return actCell(w.acts,w.nx.length,'workshop '+w.id,k)})(),D(w.d),pill(w.s),ld],
    srch:w=>w.id+' '+w.t};
  else if(PVTAB==='KDD'){const KTS=t=>`<span class="note" title="${esc(t)}">${esc((t||'').replace(/ Decisions?$/,''))||'—'}</span>`;
    const TD=k=>k.f==='C'?`<span class="amb" title="Placeholder date; confirm with the owner">${fmtD(k.d||k.dc)}?</span>`:k.d?fmtD(k.d):'—';
    cfg={items:K.filter(k=>k.s!=='Rejected'&&okG(k)&&(!F.pkty.size||F.pkty.has(k.ty))),done:k=>k.s==='Approved',doneLab:'Approved',
    cols:['ADO ID','Title','KDD Type','Workstream','Owner','Target date','State','Days overdue'],
    colsFor:lk=>lk==='done'?['ADO ID','Title','KDD Type','Workstream','Owner','Approved date','State']:lk==='up'?['ADO ID','Title','KDD Type','Workstream','Owner','Target date','State']:['ADO ID','Title','KDD Type','Workstream','Owner','Target date','State','Days overdue'],
    row:(k,ld,lk)=>{const base=[L(k.id),TT(k.t),KTS(k.ty),esc(k.ws==='Cross-stream'?'Technical':k.ws),OW(k.a,k.og,lk)];
      if(lk==='done')return [...base,k.ad?fmtD(k.ad):DASH,pill(k.s)];
      if(lk==='up')return [...base,TD(k),pill(k.s)];
      return [...base,TD(k),pill(k.s),ld]},
    doneSort:(a,b)=>(b.ad||'').localeCompare(a.ad||''),
    srch:k=>k.id+' '+k.t+' '+k.a+' '+k.ty};}
  else if(PVTAB==='REQ')cfg={items:Q.filter(q=>q.s!=='Rejected'&&okG(q)),done:q=>q.s==='Approved',doneLab:'Approved',
    cols:['ADO ID','Title','Workstream','Solution disposition','Owner','Target date','State','Days overdue'],
    row:(q,ld,lk)=>[L(q.id),TT(q.t),esc(q.ws),`<span class="dpl ${q.dp}">${{'FIT-OOB':'Fit · OOB','FIT-CFG':'Fit · Config','GAP':'Gap','TBD':'TBD'}[q.dp]}</span>`,OW(q.o,q.og,lk),D(q.d),pill(q.s),ld],
    srch:q=>q.id+' '+q.t+' '+q.o};
  else cfg={items:P.filter(p=>(PVTAB==='DM'?isDMp(p):PVTAB==='OCM'?isOCMp(p):isBuildPBI(p)&&(!F.pbt.size||F.pbt.has(btype(p))))&&okG(p)),done:p=>p.s==='Completed',doneLab:'Completed',
    cols:['ADO ID','Title','Type','Parent Config / RICEFW','Parent ID','Build type','Workstream','Owner','Target date','State','Days overdue'],
    row:(p,ld,lk)=>[L(p.id),TT(p.t),`<span class="note">${esc(pbiType(p))}</span>`,p.rc>=0?`<span class="tt3" title="${esc(C[p.rc].id+' · '+C[p.rc].t)}">${esc(C[p.rc].t)}</span>`:'<span class="red">No parent</span>',p.rc>=0?`<a class="bid" href="${ADO}${encodeURIComponent(C[p.rc].id)}" target="_blank" rel="noopener noreferrer" title="${esc(C[p.rc].t)}">${esc(C[p.rc].id)}</a>`:'<span class="red">No parent</span>',p.rc>=0?`<span class="btag ${C[p.rc].ty==='RICEFW'?'r':'c'}">${esc(C[p.rc].ty)}</span>`:'<span class="ctag none">—</span>',p.ws==='Unassigned'?'<span class="uchip" title="Area path is GFPhoenix (no workstream)">Unassigned</span>':esc(p.ws),OW(p.o,p.og,lk),D(p.d),pill(p.s),ld],
    srch:p=>p.id+' '+p.t+' '+p.o+(p.rc>=0?' '+C[p.rc].id+' '+C[p.rc].ty:'')};
  $('pvLink').hidden=true;$('pbar').hidden=PVTAB!=='PBI';$('kbar').hidden=PVTAB!=='KDD';$('pvLink').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.l===PVLINK));
  let it=cfg.items;if(term)it=it.filter(x=>cfg.srch(x).toLowerCase().includes(term));
  const lanes=[
    {k:'done',ic:'✓',lab:cfg.doneLab,cls:'ldone',rows:it.filter(cfg.done).sort(cfg.doneSort||((a,b)=>(b.d||'').localeCompare(a.d||'')))},
    {k:'up',ic:'→',lab:'Upcoming (next 14 days, to '+fmtD(UPTO)+')',cls:'lup',rows:it.filter(x=>!cfg.done(x)&&x.d&&x.d>ASOF&&x.d<=UPTO).sort((a,b)=>a.d.localeCompare(b.d))},
    (()=>{const all=it.filter(x=>!cfg.done(x)&&x.d&&x.d<=ASOF).sort((a,b)=>a.d.localeCompare(b.d));return {k:'late',ic:'!',lab:'Delayed',cls:'llate',allRows:all,rows:PVORG&&PVTAB!=='WS'?all.filter(x=>(x.og||'NA')===PVORG):all}})()];
  $('pvLanes').innerHTML=lanes.map(ln=>{const cols=cfg.colsFor?cfg.colsFor(ln.k):cfg.cols,nc=cols.length;const key=PVTAB+ln.k,closed=PVCLOSED.has(key),lim=PVSHOW[key]||200;
    const head=`<div class="lane-head ${ln.cls}" data-k="${key}" role="button" tabindex="0" aria-expanded="${!closed}"><span class="cv"></span><span class="lic">${ln.ic}</span>${ln.lab}<span class="badge">${ln.rows.length.toLocaleString()} item${ln.rows.length===1?'':'s'}</span>${ln.k==='late'&&PVTAB!=='WS'?orgChips(ln.allRows||ln.rows):topWs(ln.rows,ln.k)+(PVTAB==='WS'&&ln.k==='late'?'<span class="note" title="Workshops have no owner in the export, so they cannot be split by organization" style="margin-left:6px">ⓘ</span>':'')}</div>`;
    if(closed)return `<article class="lane">${head}</article>`;
    const body=ln.rows.length?ln.rows.slice(0,lim).map(x=>{const ld=ln.k==='late'?late(x,cfg.done):0;const cells=cfg.row(x,ld?`<b class="late">${ld}d</b>`:'',ln.k);
      return `<tr class="${ln.k==='late'?'pd':''}">${cells.map((c,i)=>`<td class="${cols[i]==='Days overdue'?'r':''}${cols[i]==='Target date'&&ld?' late':''}">${c}</td>`).join('')}</tr>`}).join('')
      +(ln.rows.length>lim?`<tr><td colspan="${nc}"><button type="button" class="lnk more" data-k="${key}">Show ${Math.min(200,ln.rows.length-lim)} more of ${(ln.rows.length-lim).toLocaleString()} remaining</button></td></tr>`:'')
      :`<tr><td colspan="${nc}" class="empty">Nothing in this lane.</td></tr>`;
    return `<article class="lane">${head}<div class="tblwrap lanewrap"><table class="regt lanet"><thead><tr>${cols.map(c=>`<th class="${c==='Days overdue'?'r':''}">${c}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div></article>`}).join('');
}
$('pvTabs').addEventListener('click',e=>{const b=e.target.closest('.ptab');if(!b)return;PVTAB=b.dataset.t;PVORG='';renderPvp()});
$('pvCards').addEventListener('click',e=>{const c=e.target.closest('.gcard');if(!c)return;PVTAB=['WS','KDD','REQ','PBI'][[...c.parentNode.children].indexOf(c)];renderPvp();$('pvTabs').scrollIntoView?.({behavior:'smooth',block:'start'})});
$('pvq').addEventListener('input',()=>renderPvp());
$('pvLink').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;PVLINK=b.dataset.l;renderPvp()});
$('pvLanes').addEventListener('click',e=>{const on=e.target.closest('.oname');if(on){e.stopPropagation();PVORG=PVORG===on.dataset.o?'':on.dataset.o;renderPvp();return}const wc=e.target.closest('.wchip');if(wc){e.stopPropagation();const w=wc.dataset.w;if(F.gws.size===1&&F.gws.has(w))F.gws.clear();else{F.gws.clear();F.gws.add(w)}update(false);return}const m=e.target.closest('.more');if(m){PVSHOW[m.dataset.k]=(PVSHOW[m.dataset.k]||200)+200;renderPvp();return}const h=e.target.closest('.lane-head');if(!h)return;const k=h.dataset.k;PVCLOSED.has(k)?PVCLOSED.delete(k):PVCLOSED.add(k);renderPvp()});
$('pvLanes').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('lane-head')){e.preventDefault();e.target.click()}});
function renderPvp(){
  const okG=x=>(!F.gws.size||F.gws.has(x.ws))&&(!F.gct.size||[...x.cts].some(c=>F.gct.has(c)));
  const due=x=>x.d&&x.d<=ASOF;
  const U30=(()=>{const d=new Date(ASOF+'T12:00:00');d.setDate(d.getDate()+30);return d.toISOString().slice(0,10)})();
  const mk=(name,lab,items,isDone)=>{const a=items.filter(isDone).length,p=items.filter(due).length,op=items.filter(x=>!isDone(x));return {name,lab,a,p,t:items.length,v:a-p,up:op.filter(x=>x.d&&x.d>ASOF&&x.d<=U30).length,rec:op.filter(x=>x.d&&x.d<=ASOF).length,u30:U30}};
  const ws=W.filter(w=>w.s!=='Cancelled'&&okG(w)),ks=K.filter(k=>k.s!=='Rejected'&&okG(k)&&(!F.pkty.size||F.pkty.has(k.ty))),qs=Q.filter(q=>q.s!=='Rejected'&&okG(q)),ps=P.filter(p=>isBuildPBI(p)&&okG(p)&&(!F.pbt.size||F.pbt.has(btype(p))));
  const dms=P.filter(p=>isDMp(p)&&okG(p)),ocs=P.filter(p=>isOCMp(p)&&okG(p));
  const cards=[mk('KDDs','approved',ks,k=>k.s==='Approved'),mk('Requirements','approved',qs,q=>q.s==='Approved'),mk('Build PBIs','completed',ps,p=>p.s==='Completed'),mk('Workshops','completed',ws,w=>w.s==='Completed'),mk('Data Migration','completed',dms,p=>p.s==='Completed'),mk('OCM','completed',ocs,p=>p.s==='Completed')];
  if(F.pkty.size)cards[0].extra=`<div class="lnk2"><span class="ftag">Filtered: ${esc([...F.pkty].map(t=>t.replace(/ Decisions?$/,'')).join(', '))}</span></div>`;
  {const u=ps.filter(pbiUnl).length;cards[2].extra=`<div class="lnk2">${F.pbt.size?`<span class="ftag">Filtered: ${esc([...F.pbt].join(', '))}</span> `:''}No parent: <b class="${u?'red':''}">${u.toLocaleString()}</b> PBI${u===1?'':'s'}</div>`;}
  const PVK=['KDD','REQ','PBI','WS','DM','OCM'];cards.forEach((c,i)=>c.tab=PVK[i]);
  const card=c=>{const ok=c.v>=0,none=!c.p&&!c.a;
    const sf=c.p?(c.p-c.a)/c.p:null,tl=sf===null?'none':sf<0.10?'g':sf<0.30?'a':'r',tlTxt=sf===null?'No plan to date':`${c.name}: ${sf<=0?Math.round(-sf*100)+'% ahead of':Math.round(sf*100)+'% behind'} plan (${c.a.toLocaleString()} of ${c.p.toLocaleString()}) → ${{g:'Green',a:'Amber',r:'Red'}[tl]}`;
    return `<article class="gcard gclick ${none?'':ok?'ahead':'behind'}" data-t="${c.tab}" role="button" tabindex="0" title="Open the ${esc(c.name)} details" aria-label="${esc(c.name)} gauge, open the ${esc(c.name)} details"><div class="tl ${tl}" role="img" aria-label="${esc(tlTxt)}" title="${esc(tlTxt)}"><i class="lr"></i><i class="la"></i><i class="lg"></i></div><h3>${c.name} Progress vs Plan</h3>${gaugeSVG(c)}
    <div class="vpill ${none?'':ok?'good':'bad'}">${none?'Nothing due yet':`${c.v>0?'+':c.v<0?'−':''}${Math.abs(c.v).toLocaleString()} ${ok?(c.v?'ahead of':'on'):'behind'} plan to date`}</div>
    <div class="gmet"><div class="gm act"><small>Actual<br>${c.lab}</small><b class="num">${c.a.toLocaleString()}</b></div><div class="gm pl"><small>Plan<br>to date</small><b class="num">${c.p.toLocaleString()}</b></div><div class="gm"><small>Overall<br>planned</small><b class="num">${c.t.toLocaleString()}</b></div></div>
    ${c.extra||''}<div class="glg"><span><i class="ga"></i>Actual</span><span><i class="gp"></i>Plan to date</span><span><i class="go"></i>Overall planned</span></div></article>`};
  $('pvCards').innerHTML=cards.map(card).join('');
  const SA=cards.reduce((s,c)=>s+c.a,0),SP_=cards.reduce((s,c)=>s+c.p,0);
  const sh=SP_?(SP_-SA)/SP_:0,shp=Math.round(sh*1000)/10;
  const h=!SP_?['g','On Track']:sh<0.10?['g','On Track']:sh<=0.30?['a','At Risk']:['r','Off Track'];
  const brk=cards.map(c=>`${c.name}: ${c.a.toLocaleString()} of ${c.p.toLocaleString()} (${c.v>0?'+':''}${c.v.toLocaleString()})`).join('\n');
  $('pvHealth').className='health '+h[0];
  $('pvHealth').title=`Pooled across ${cards.length} levers\n${brk}\nTotal: ${SA.toLocaleString()} of ${SP_.toLocaleString()}`;
  $('pvHealth').innerHTML=`<i class="hdot"></i><div><b>Program Health · ${h[1]}</b><small>${!SP_?'Nothing planned to date':sh<=0?`${Math.abs(shp)}% ahead of plan to date`:`${shp}% behind plan to date`} (${SA.toLocaleString()} of ${SP_.toLocaleString()} across ${cards.length} levers)</small></div>`;
  renderPvTabs(okG);
}
/* ---------- PBI burn-up ---------- */
const BHIST=Object.assign({{json:burnup_history}},{[{{json:burnup_latest_export}}]:P.filter(p=>p.s==='Completed').map(p=>p.id)});const BLAST=BHIST[Object.keys(BHIST).sort().pop()];
const BSER=['CRD','CUT','FDD','TDD','BUILD','FUT','OCM'],BSN={CRD:'CRD',CUT:'Config & CUT',FDD:'FDD',TDD:'TDD · Technical design',BUILD:'Build',FUT:'FUT',OCM:'OCM / Training'};
const pSer=p=>{const pre=(p.t||'').split(' - ')[0].trim();if(pre==='CRD')return 'CRD';if(pre.startsWith('Config & CUT'))return 'CUT';if(pre==='FDD'||pre==='FUT')return pre;if(/design/i.test(pre))return 'TDD';if(/build/i.test(pre)||/^PI ?\/ ?PO/i.test(pre))return 'BUILD';return 'OCM'};
const pOst=p=>p.rc<0?'No parent':(C[p.rc].s&&C[p.rc].s!=='—'?C[p.rc].s:'Unknown');
const pOty=p=>{if(p.rc<0)return 'No parent';if(C[p.rc].ty==='Configuration')return 'Configuration';const m=(p.t||'').match(/ - (Interface|Conversion)\b/);return m?'RICEFW · '+m[1]:'RICEFW · Other'};
P.forEach(p=>{p.ser=pSer(p);p.ost=pOst(p);p.oty=pOty(p)});
F.bws=new Set();F.bst=new Set();F.bot=new Set();F.bse=new Set();
const BST=['New','In Progress','Design Draft','Design Signoff','Unknown','No parent'],BOT=['Configuration','RICEFW · Interface','RICEFW · Conversion','RICEFW · Other','No parent'];
const cnt=(f)=>{const c={};P.forEach(p=>{const k=f(p);c[k]=(c[k]||0)+1});return c};
const bsl=[
  MS($('msBws'),'bws','Workstream',()=>{const c=cnt(p=>p.ws);return WSO.filter(w=>c[w]).map(w=>({v:w,t:w,c:c[w]}))}),
  MS($('msBst'),'bst','Object state',()=>{const c=cnt(p=>p.ost);return BST.filter(s=>c[s]).map(s=>({v:s,t:s,c:c[s]}))}),
  MS($('msBot'),'bot','Object type',()=>{const c=cnt(p=>p.oty);return BOT.filter(s=>c[s]).map(s=>({v:s,t:s,c:c[s]}))}),
  MS($('msBse'),'bse','Series',()=>{const c=cnt(p=>p.ser);return BSER.map(s=>({v:s,t:BSN[s],c:c[s]||0}))})];
sl.push(...bsl);
$('buReset').addEventListener('click',()=>{['bws','bst','bot','bse'].forEach(k=>F[k].clear());$('buq').value='';update()});
$('buq').addEventListener('input',()=>renderNoDate());
let BUSHOW=200;$('buNoDate').addEventListener('click',e=>{if(e.target.closest('.bumore')){BUSHOW+=200;renderNoDate()}});
$('buGrid').addEventListener('click',e=>{const a=e.target.closest('.nodlink');if(a){e.preventDefault();$('buNoDate').scrollIntoView?.({behavior:'smooth',block:'start'})}});
const okB=p=>(!F.bws.size||F.bws.has(p.ws))&&(!F.bst.size||F.bst.has(p.ost))&&(!F.bot.size||F.bot.has(p.oty));
const W0={{json:burnup_start}},W1={{json:burnup_end}};
const WEEKS=(()=>{const a=[];let d=new Date(W0+'T12:00:00');const e=new Date(W1+'T12:00:00');while(d<=e){a.push(d.toISOString().slice(0,10));d.setDate(d.getDate()+7)}return a})();
const wEnd=w=>{const d=new Date(w+'T12:00:00');d.setDate(d.getDate()+6);return d.toISOString().slice(0,10)};
function buChart(items,tot){
  const Wd=360,Ht=190,l=38,r=10,t=12,b=26,iw=Wd-l-r,ih=Ht-t-b,n=WEEKS.length;
  const X=i=>l+i*iw/(n-1),Y=v=>t+ih-(tot?v/tot*ih:0);
  const plan=WEEKS.map(w=>{const e=wEnd(w);return items.filter(p=>p.d&&p.d<=e).length});
  const ids=new Set(items.map(p=>p.id));
  const snaps=Object.keys(BHIST).sort().map(dt=>({dt,v:BHIST[dt].filter(id=>ids.has(id)).length}));
  const wi=dt=>{const k=WEEKS.findIndex(w=>dt>=w&&dt<=wEnd(w));return k<0?(dt<W0?0:n-1):k};
  const ti=wi(ASOF);
  const todayLab=()=>{const pT=items.filter(p=>p.d&&p.d<=ASOF).length,aT=snaps.length?snaps[snaps.length-1].v:0,x=X(ti),yP=Y(pT),yA=Y(aT),lx=x+8;
    const tag=(y,txt,cls)=>{const w=txt.length*5.6+10;return `<g class="tlab ${cls}"><rect x="${lx.toFixed(1)}" y="${(y-8).toFixed(1)}" width="${w.toFixed(1)}" height="15" rx="3"/><text x="${(lx+5).toFixed(1)}" y="${(y+3).toFixed(1)}">${txt}</text></g>`};
    if(!pT&&!aT)return tag(yP-10,'Plan 0 · Actual 0','tz');
    const bot=t+ih-9,top=t+18;let lo=Math.min(bot,Math.max(yP,yA)),hi=Math.min(yP,yA);if(lo-hi<18)hi=lo-18;if(hi<top){hi=top;lo=Math.max(lo,hi+18)}
    let ty,ay;if(pT>=aT){ty=hi;ay=lo}else{ty=lo;ay=hi}
    const g=aT-pT,gc=g<0?'gbad':'gok';
    const br=g?`<line x1="${(x+3).toFixed(1)}" x2="${(x+3).toFixed(1)}" y1="${yP.toFixed(1)}" y2="${yA.toFixed(1)}" class="gbr ${gc}"/><text x="${(x-4).toFixed(1)}" y="${((yP+yA)/2+3).toFixed(1)}" text-anchor="end" class="gtx ${gc}">${g>0?'+':'−'}${Math.abs(g)}</text>`:'';
    return `<circle cx="${x.toFixed(1)}" cy="${yP.toFixed(1)}" r="3.5" class="pdot"/>${br}${tag(ty,'Plan '+pT.toLocaleString(),'tp')}${tag(ay,'Actual '+aT.toLocaleString(),'ta')}`};
  const yt=[0,.25,.5,.75,1].map(f=>Math.round(f*tot)).filter((v,i,a)=>a.indexOf(v)===i);
  const grid=yt.map(v=>`<line x1="${l}" x2="${Wd-r}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" class="bg"/><text x="${l-5}" y="${(Y(v)+3).toFixed(1)}" text-anchor="end" class="bt">${v.toLocaleString()}</text>`).join('');
  const xl=WEEKS.map((w,i)=>i%4===0?`<text x="${X(i).toFixed(1)}" y="${Ht-8}" text-anchor="middle" class="bt">${new Date(w+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric'})}</text>`:'').join('');
  const pl=plan.map((v,i)=>`${i?'L':'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`).join(' ');
  const act=snaps.map(s=>[X(wi(s.dt)),Y(s.v),s]);
  const actPath=act.length?`<path d="M${X(0).toFixed(1)} ${Y(0).toFixed(1)} L${act[0][0].toFixed(1)} ${act[0][1].toFixed(1)}" class="ba0"/>`+(act.length>1?`<path d="${act.map((a,i)=>`${i?'L':'M'}${a[0].toFixed(1)} ${a[1].toFixed(1)}`).join(' ')}" class="ba"/>`:''):'';
  const dots=act.map(a=>`<circle cx="${a[0].toFixed(1)}" cy="${a[1].toFixed(1)}" r="4" class="bd"><title>Actual ${a[2].v} completed (${fmtD(a[2].dt)})</title></circle>`).join('');
  const hov=WEEKS.map((w,i)=>`<rect x="${(X(i)-iw/(n-1)/2).toFixed(1)}" y="${t}" width="${(iw/(n-1)).toFixed(1)}" height="${ih}" class="bh"><title>Week of ${fmtD(w)}\nPlan (cumulative): ${plan[i]}${i===ti?`\nActual: ${act.length?act[act.length-1][2].v:0}\nGap: ${(act.length?act[act.length-1][2].v:0)-plan[i]}`:''}</title></rect>`).join('');
  return `<svg viewBox="0 0 ${Wd} ${Ht}" class="buc" role="img" aria-label="Burn-up chart">${grid}${xl}
    <line x1="${l}" x2="${Wd-r}" y1="${Y(tot).toFixed(1)}" y2="${Y(tot).toFixed(1)}" class="bs"/>
    <line x1="${X(ti).toFixed(1)}" x2="${X(ti).toFixed(1)}" y1="${t}" y2="${t+ih}" class="btd"/><text x="${(X(ti)+3).toFixed(1)}" y="${t+9}" class="bt btl">Today</text>
    <path d="${pl}" class="bp"/>${actPath}${dots}${todayLab()}${hov}</svg>`;
}
function renderBurnup(){
  const base=P.filter(okB);
  const sers=BSER.filter(s=>!F.bse.size||F.bse.has(s));
  $('buGrid').innerHTML=sers.map(s=>{const it=base.filter(p=>p.ser===s),tot=it.length,nod=it.filter(p=>!p.d).length,out=it.filter(p=>p.d&&p.d>wEnd(W1)).length;
    const a=it.filter(p=>BLAST.includes(p.id)).length,pd=it.filter(p=>p.d&&p.d<=ASOF).length,v=a-pd;
    return `<article class="bubox"><h3>${BSN[s]}</h3>${tot?buChart(it,tot):'<div class="empty">No PBIs in this filter.</div>'}
      <div class="gmet"><div class="gm act"><small>Actual<br>completed</small><b class="num">${a.toLocaleString()}</b></div><div class="gm pl"><small>Plan<br>to date</small><b class="num">${pd.toLocaleString()}</b></div><div class="gm"><small>Total<br>PBIs</small><b class="num">${tot.toLocaleString()}</b></div></div>
      <div class="vpill ${!pd&&!a?'':v>=0?'good':'bad'}">${!pd&&!a?'Nothing due yet':`${v>0?'+':v<0?'−':''}${Math.abs(v)} ${v>=0?(v?'ahead of':'on'):'behind'} plan to date`}</div>
      ${nod||out?`<div class="bunote">${nod?`<a href="#burnup" class="nodlink amb">${nod} of ${tot} have no target date</a>`:''}${nod&&out?' · ':''}${out?`${out} targeted after Apr 2027`:''}</div>`:''}</article>`}).join('')||'<div class="empty">Pick at least one series.</div>';
  renderNoDate();
}
function renderNoDate(){
  const term=$('buq').value.trim().toLowerCase();
  let L=P.filter(p=>!p.d&&okB(p)&&(!F.bse.size||F.bse.has(p.ser)));
  if(term)L=L.filter(p=>(p.id+' '+p.t+' '+p.o).toLowerCase().includes(term));
  L.sort((a,b)=>a.ws.localeCompare(b.ws)||BSER.indexOf(a.ser)-BSER.indexOf(b.ser)||a.id.localeCompare(b.id));
  $('buNdCount').textContent=`${L.length.toLocaleString()} PBI${L.length===1?'':'s'} with no target date`;
  $('buNdBody').innerHTML=L.length?L.slice(0,BUSHOW).map(p=>`<tr><td><a href="${ADO}${encodeURIComponent(p.id)}" target="_blank" rel="noopener noreferrer">${esc(p.id)}</a></td><td><span class="tt2">${esc(p.t)}</span></td><td><span class="note">${BSN[p.ser]}</span></td><td>${p.rc>=0?`<span class="tt3" title="${esc(C[p.rc].id)}">${esc(C[p.rc].t)}</span>`:'<span class="red">No parent</span>'}</td><td class="note">${esc(p.oty)}</td><td>${p.ost==='Unknown'?'<span class="ctag none">Unknown</span>':esc(p.ost)}</td><td>${p.ws==='Unassigned'?'<span class="uchip">Unassigned</span>':esc(p.ws)}</td><td>${p.o?esc(p.o)+(p.og?` <span class="ogc">(${p.og})</span>`:''):'<span class="ctag none">—</span>'}</td><td><span class="pill ${p.s==='Completed'?'g':p.s==='Blocked'?'r':/Progress|Ready/.test(p.s)?'a':'n'}">${esc(p.s)}</span></td><td>${pbiUnl(p)?`<span class="tchip" title="${esc(pbiWhy(p))}">No parent</span>`:`<span class="pill g">${esc(btype(p))}</span>`}</td></tr>`).join('')+(L.length>BUSHOW?`<tr><td colspan="10"><button type="button" class="lnk bumore">Show ${Math.min(200,L.length-BUSHOW)} more of ${(L.length-BUSHOW).toLocaleString()} remaining</button></td></tr>`:''):'<tr><td colspan="10" class="empty">No undated PBIs in this filter.</td></tr>';
}

/* ---------- Workstream view ---------- */
F.vws=new Set();F.vct=new Set();
const vsl=[MS($('msVws'),'vws','Workstream',()=>WSO.map(w=>({v:w,t:w==='Cross-stream'?'Technical':w}))),
  MS($('msVct'),'vct','Complex topic',()=>[...CTS.map(c=>({v:c,t:c})),{v:NOCT,t:NOCT,sep:1},{v:NOL4,t:NOL4}])];
sl.push(...vsl);
$('vReset').addEventListener('click',()=>{F.vws.clear();F.vct.clear();update()});
const vGo=td=>{const w=td.dataset.w;if(!w)return;F.gws.clear();F.gws.add(w);F.gct.clear();F.vct.forEach(c=>F.gct.add(c));if(td.dataset.t)PVTAB=td.dataset.t;showView('progress',true);update();$('pvp')?.scrollIntoView?.({block:'start'})};
$('vScore').addEventListener('click',e=>{const td=e.target.closest('td[data-w]');if(td)vGo(td)});
$('vScore').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('td[data-w]')){e.preventDefault();vGo(e.target)}});
const VWN=w=>w==='Cross-stream'?'Technical':w;
const VORD=['D2D','S2P','O2C','R2R','M2O','Cross-stream','OCM','Unassigned'];
function wsLevers(){
  const okV=x=>(!F.vws.size||F.vws.has(x.ws))&&(!F.vct.size||[...x.cts].some(c=>F.vct.has(c)));
  const due=x=>x.d&&x.d<=ASOF;
  const mk=(name,lab,items,done)=>{const by={};items.filter(okV).forEach(x=>{const b=by[x.ws]=by[x.ws]||{a:0,p:0,t:0};b.t++;if(done(x))b.a++;if(due(x))b.p++});return {name,lab,by}};
  const T=(o,t)=>(o.tab=t,o);
  return [T(mk('KDDs','approved',K.filter(k=>k.s!=='Rejected'),k=>k.s==='Approved'),'KDD'),
    T(mk('Requirements','approved',Q.filter(q=>q.s!=='Rejected'),q=>q.s==='Approved'),'REQ'),
    T(mk('Build PBIs','completed',P.filter(isBuildPBI),p=>p.s==='Completed'),'PBI'),
    T(mk('Data Migration','completed',P.filter(isDMp),p=>p.s==='Completed'),'DM'),
    T(mk('OCM','completed',P.filter(isOCMp),p=>p.s==='Completed'),'OCM'),
    T(mk('Workshops','completed',W.filter(w=>w.s!=='Cancelled'),w=>w.s==='Completed'),'WS')];
}
const shortCls=(a,p)=>{if(!p)return 'none';const s=(p-a)/p;return s<0.10?'g':s<0.30?'a':'r'};
function renderWsView(){
  const lv=wsLevers();
  // heatmap: Pooled first, Program row on top, OCM workstream row hidden
  const TAB=lv.map(l=>l.tab),allW=VORD.filter(w=>lv.some(l=>l.by[w]&&l.by[w].t));
  const pool={};allW.forEach(w=>{const x=pool[w]={a:0,p:0,t:0};lv.forEach(l=>{const b=l.by[w];if(b){x.a+=b.a;x.p+=b.p;x.t+=b.t}})});
  const lt=lv.map(l=>{const s={a:0,p:0,t:0};Object.values(l.by).forEach(b=>{s.a+=b.a;s.p+=b.p;s.t+=b.t});return s});
  const tot=lt.reduce((s,b)=>({a:s.a+b.a,p:s.p+b.p,t:s.t+b.t}),{a:0,p:0,t:0});
  const rows=allW.filter(w=>w!=='OCM').map(w=>({w,...pool[w],sh:pool[w].p?(pool[w].p-pool[w].a)/pool[w].p:null}));
  const cell=(b,tip,attrs,cls)=>{if(!b||!b.t)return `<td class="hc nd ${cls||''}"><span class="hv">—</span></td>`;
    if(!b.p&&!b.a)return `<td class="hc nz ${cls||''}" ${attrs} title="${esc(tip)}"><span class="hv">0/0</span><span class="hs">nothing due</span></td>`;
    const c=shortCls(b.a,b.p),sh=b.p?(b.p-b.a)/b.p:-1;const st=!b.p?'ahead':sh<0?'ahead':sh===0?'on plan':Math.round(sh*100)+'% behind';
    return `<td class="hc ${c} ${cls||''}" ${attrs} title="${esc(tip)}"><span class="hv">${b.a.toLocaleString()}/${b.p.toLocaleString()}</span><span class="hs">${st}</span></td>`};
  const att=(w,i)=>`data-w="${esc(w)}"${i===undefined?'':` data-t="${TAB[i]}"`} role="button" tabindex="0"`;
  const where=i=>'Progress vs Plan';
  const prog=`<tr class="hprog"><th scope="row">Program</th>${cell(tot,`Program pooled: ${tot.a} done of ${tot.p} due · ${tot.t.toLocaleString()} overall`,'','pool')}${lt.map((b,i)=>cell(b,`Program · ${lv[i].name}: ${b.a} ${lv[i].lab} of ${b.p} due · ${b.t.toLocaleString()} overall`,'')).join('')}</tr>`;
  const body=rows.map(r=>`<tr><th scope="row">${esc(VWN(r.w))}</th>${cell(r,`${VWN(r.w)} pooled: ${r.a} done of ${r.p} due · ${r.t.toLocaleString()} overall\nClick to open in Progress vs Plan`,att(r.w),'pool')}${lv.map((l,i)=>{const b=l.by[r.w];
      return cell(b,b?`${VWN(r.w)} · ${l.name}: ${b.a} ${l.lab} of ${b.p} due · ${b.t.toLocaleString()} overall\nClick to open in ${where(i)}`:'',att(r.w,i))}).join('')}</tr>`).join('');
  const cg=`<colgroup><col class="c0">${'<col>'.repeat(lv.length+1)}</colgroup>`;
  $('vScore').innerHTML=rows.length?`<table class="heat hfix">${cg}<thead><tr><th>Workstream</th><th class="pool">Pooled</th>${lv.map(l=>`<th>${l.name}</th>`).join('')}</tr></thead></table><div class="hprogbox"><table class="heat hfix">${cg}<tbody>${prog}</tbody></table></div><table class="heat hfix">${cg}<tbody>${body}</tbody></table>`:'<div class="empty">No items in this filter.</div>';
  renderDeck();
}

/* ---------- Program Executive Summary (slide deck by workstream & L2) ---------- */
let DK_I=0,DK_N=0;
const dmy=d=>d?new Date(d+'T12:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short'}):'—';
const nf=n=>n.toLocaleString();
const DK_WS=[['3','D2D'],['5','S2P'],['6','O2C'],['7','R2R'],['4','M2O'],['1','Cross-stream']];
const NWD=n=>['zero','one','two','three','four','five','six','seven','eight'][n]||String(n),CAPW=s=>s[0].toUpperCase()+s.slice(1);
const DK_FIVE=['D2D','S2P','O2C','R2R','M2O'];const wsIn=(x,ws)=>ws==='Cross-stream'?!DK_FIVE.includes(x):x===ws;
const l1num=s=>((s||'').match(/^\s*(\d+)/)||[])[1]||'';
const l2num=s=>{const m=(s||'').match(/(\d+\.\d+)/);return m?m[1]:'99.99'};
const l2sort=(a,b)=>{const x=l2num(a).split('.').map(Number),y=l2num(b).split('.').map(Number);return x[0]-y[0]||x[1]-y[1]||a.localeCompare(b)};
const kLate=k=>k.s!=='Approved'&&k.s!=='Rejected'&&k.d&&k.d<=ASOF;
F.dks=new Set();const DK_OPEN=['New','In Analysis','Pending Approval'];
const kOK=k=>F.dks.size?F.dks.has(k.s):k.s!=='Rejected';
const dkFilt=()=>F.dks.size?[...F.dks].join(', '):'';
const KST_CLS={'New':'n','In Analysis':'a','Pending Approval':'p','Rejected':'x'};
function deckData(){
  const qBy=new Map();Q.filter(q=>q.s!=='Rejected').forEach(q=>{(q.oe&&q.oe.length?q.oe:q.e||[]).forEach(i=>{if(!qBy.has(i))qBy.set(i,[]);qBy.get(i).push(q)})});
  return DK_WS.map(([n,ws])=>{
    const eps=E.filter(e=>l1num(e.l1)===n);const l2m=new Map();eps.forEach(e=>{if(!l2m.has(e.l2))l2m.set(e.l2,[]);l2m.get(e.l2).push(e)});
    const L2=[...l2m.entries()].sort((a,b)=>l2sort(a[0],b[0])).map(([l2,es])=>{
      const ks=new Map(),qs=new Map();const l4=[];
      es.forEach(e=>{const kk=(e.k||[]).filter(kOK);kk.forEach(k=>ks.set(k.id,k));(qBy.get(e.i)||[]).forEach(q=>qs.set(q.id,q));if(kk.length)l4.push({e,k:kk.sort((a,b)=>(a.s==='Approved'?1:0)-(b.s==='Approved'?1:0)||(a.d||'9').localeCompare(b.d||'9'))})});
      const k=[...ks.values()],q=[...qs.values()];
      return {l2,ws,es,l4,k,ka:k.filter(x=>x.s==='Approved').length,kl:k.filter(kLate).length,q,qa:q.filter(x=>x.s==='Approved').length,qr:q.filter(x=>x.s==='Ready for Acceptance').length}});
    const U=K.filter(k=>kOK(k)&&!(k.e||[]).length&&wsIn(k.ws,ws)).sort((a,b)=>(a.s==='Approved'?1:0)-(b.s==='Approved'?1:0)||(a.d||'9').localeCompare(b.d||'9'));
    const UQ=Q.filter(q=>q.s!=='Rejected'&&!(q.oe&&q.oe.length?q.oe:q.e||[]).length&&wsIn(q.ws,ws));
    if(U.length||UQ.length)L2.push({l2:'Not linked to an L4',ws,unl:1,es:[],l4:U.length?[{e:null,k:U}]:[],k:U,ka:U.filter(x=>x.s==='Approved').length,kl:U.filter(kLate).length,q:UQ,qa:UQ.filter(x=>x.s==='Approved').length,qr:UQ.filter(x=>x.s==='Ready for Acceptance').length});
    const ks=new Map(),qs=new Map();L2.forEach(r=>{r.k.forEach(k=>ks.set(k.id,k));r.q.forEach(q=>qs.set(q.id,q))});const k=[...ks.values()],q=[...qs.values()];
    return {ws,nm:VWN(ws),n,L1:ws==='Cross-stream'?'Cross-stream · '+((eps[0]||{}).l1||''):(eps[0]||{}).l1||ws,L2,k,ka:k.filter(x=>x.s==='Approved').length,kl:k.filter(kLate).length,q,qa:q.filter(x=>x.s==='Approved').length,qr:q.filter(x=>x.s==='Ready for Acceptance').length};
  });
}
const dsbar=(a,r,t)=>{const p=v=>t?(v/t*100).toFixed(1):0;return `<span class="dbar" title="Approved ${a} · RfA ${r} · Total ${t}"><i class="ba" style="width:${p(a)}%"></i><i class="br" style="width:${p(r)}%"></i></span>`};
const kRow=(k,ws)=>{const ap=k.s==='Approved',lt=kLate(k),fw=ws&&k.ws!==ws&&DK_WS.some(x=>x[1]===k.ws);return `<div class="dk ${ap?'ok':''}"><span class="dks">${ap?'<b class="tick">✓</b>':`<span class="kp ${KST_CLS[k.s]||'n'}">${esc(k.s)}</span>`}</span><a href="${ADO}${encodeURIComponent(k.id)}" target="_blank" rel="noopener noreferrer">${esc(k.id)}</a><span class="dkt" title="${esc(k.t)}">${fw?`<span class="ftag" title="KDD belongs to ${esc(k.ws)}; listed under the L4 it is linked to">${esc(k.ws)} KDD</span> `:''}${esc((k.t||'').replace(/[​]/g,''))}</span><span class="dkd">${ap?(k.ad?'Approved '+dmy(k.ad):'Approved'):k.d?(lt?'Due ':'Due ')+dmy(k.d):'No date'}${k.f==='C'?' <span class="chk">check date</span>':''}</span>${lt?'<span class="late">Late</span>':''}</div>`};
function kLines(W){const out=[];W.L2.forEach(r=>{if(!r.l4.length)return;out.push({t:'l2',r});r.l4.forEach(x=>{if(x.e)out.push({t:'l4',x,r});x.k.forEach(k=>out.push({t:'k',k,x,r}))})});return out}
function paginate(lines,first,rest){const pages=[];let cur=[],cap=first;lines.forEach(l=>{if(cur.length>=cap||(l.t!=='k'&&cur.length>=cap-(l.t==='l2'?2:1))){const carry=[];while(cur.length&&cur[cur.length-1].t!=='k')carry.unshift(cur.pop());if(cur.length)pages.push(cur);cur=carry;if(cur.length&&(cur[0].t==='l4'||(cur[0].t==='k'&&cur[0].r.unl)))cur.unshift({t:'l2',r:cur[0].r,cont:1});cap=rest}
  if(!cur.length&&pages.length){if(l.t!=='l2')cur.push({t:'l2',r:l.r,cont:1});if(l.t==='k'&&l.x.e)cur.push({t:'l4',x:l.x,r:l.r,cont:1})}cur.push(l)});if(cur.length)pages.push(cur);return pages}
const lineHTML=l=>l.t==='l2'?`<div class="dl2${l.r.unl?' unl':''}">${esc(l.r.l2)}${l.cont?' <span>(cont.)</span>':''}</div>`:l.t==='l4'?`<div class="dl4">L4 ${esc(l.x.e.n||'')} · ${esc(l.x.e.t)}${l.cont?' <span>(cont.)</span>':''}</div>`:kRow(l.k,l.r.ws);
const slideFrame=(cls,head,body,foot)=>`<section class="slide-d ${cls}"><div class="sd-in"><header class="sd-h">${head}</header><div class="sd-b">${body}</div><footer class="sd-f">${foot}${dkFilt()?`<span class="dkf">KDD state: ${esc(dkFilt())}</span>`:''}</footer></div></section>`;
function renderDeck(){
  const D=deckData(),asof=`${dmy(ASOF)} ${ASOF.slice(0,4)}`;const S=[];
  const kpi=W=>`<div class="kpis-d"><div><b>${W.ka}</b><span>KDDs approved</span></div><div><b>${W.k.length-W.ka}</b><span>KDDs not approved</span></div><div class="${W.kl?'r':''}"><b>${W.kl}</b><span>KDDs late</span></div><div class="sep"></div><div><b>${nf(W.qa)}</b><span>Reqs approved</span></div><div><b>${nf(W.qr)}</b><span>Ready for acceptance</span></div><div><b>${nf(W.q.length)}</b><span>Reqs total</span></div></div>`;
  const take=W=>{const big=[...W.L2].sort((a,b)=>b.q.length-a.q.length)[0];const sh=W.q.length?Math.round((W.qa+W.qr)/W.q.length*100):0;
    return `${W.k.length?`${W.ka} of ${W.k.length} KDDs approved${W.kl?`, <b class="r">${W.kl} late</b>`:''}`:'No KDDs linked to L4s'}. ${W.q.length?`${sh}% of requirements approved or ready for acceptance`:'No requirements sit in this workstream'}${big&&big.q.length?`; largest L2 by volume is ${esc(l2num(big.l2))} ${esc(big.l2.replace(/^[^-]*-\s*/,''))} (${nf(big.q.length)})`:''}.`};
  /* 1 title */
  S.push({lab:'Title',html:`<section class="slide-d title"><div class="sd-in">{{deck_title_html}}<div class="tt-m">KDDs and requirements · as of ${asof}</div><div class="tt-ws">${D.map(W=>`<span>${W.nm}</span>`).join('')}</div>${dkFilt()?`<div class="tt-fl">Filtered · KDD state: ${esc(dkFilt())}</div>`:''}<div class="tt-f">{{deck_sources}}</div></div></section>`});
  /* 2 overview */
  {const KM=new Map(),QM=new Map();D.forEach(W=>{W.k.forEach(k=>KM.set(k.id,k));W.q.forEach(q=>QM.set(q.id,q))});const KA=[...KM.values()],QA=[...QM.values()];const T={k:KA.length,ka:KA.filter(x=>x.s==='Approved').length,kl:KA.filter(kLate).length,q:QA.length,qa:QA.filter(x=>x.s==='Approved').length,qr:QA.filter(x=>x.s==='Ready for Acceptance').length};
   const rows=D.map(W=>`<tr><th>${W.nm}<span>${esc(W.L1)}</span></th><td class="m">${W.L2.filter(r=>!r.unl).length}</td><td><div class="kv"><b>${W.ka}</b> / ${W.k.length}${W.kl?` <span class="late">${W.kl} late</span>`:''}</div>${dsbar(W.ka,0,W.k.length)}</td><td><div class="kv"><b>${nf(W.qa)}</b> · ${nf(W.qr)} RfA · ${nf(W.q.length)}</div>${dsbar(W.qa,W.qr,W.q.length)}</td></tr>`).join('');
   S.push({lab:'Overview',html:slideFrame('ov',`<div class="sd-k">Overview</div><h2>${CAPW(NWD(D.length))} workstreams at a glance</h2><p class="sd-t">${T.ka} of ${T.k} KDDs approved${T.kl?`, <b class="r">${T.kl} late</b>`:''}; ${nf(T.qa)} of ${nf(T.q)} requirements approved and ${nf(T.qr)} ready for acceptance.</p>`,
     `<table class="dtab ovt"><colgroup><col class="c1"><col class="c2"><col class="c3"><col></colgroup><thead><tr><th>Workstream</th><th class="m">L2s</th><th>KDDs approved / total</th><th>Requirements approved · RfA · total</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="dlg"><span><i class="ba"></i>Approved</span><span><i class="br"></i>Ready for acceptance</span><span><i class="bo"></i>Not yet approved</span></div>`,
     `<span>As of ${asof}</span><span>Program totals count each item once; a requirement linked to L4s in two workstreams appears on both rows; ${F.dks.has('Rejected')?'rejected requirements excluded':'rejected KDDs and requirements excluded'}</span>`)});}
  /* workstream slides */
  D.forEach(W=>{const lines=kLines(W),pages=paginate(lines,19,38);
    const tbl=`<table class="dtab l2t${W.L2.length>10?' dense':''}"><colgroup><col class="c1"><col class="c2"><col></colgroup><thead><tr><th>L2</th><th>KDDs ✓ / open</th><th>Reqs ✓ · RfA · total</th></tr></thead><tbody>${W.L2.map(r=>{const empty=!r.k.length&&!r.q.length;
      return `<tr class="${r.unl?'unlr':empty?'emp':''}"><th>${esc(r.l2)}</th><td class="kv" data-l="KDDs ✓ / open">${r.k.length?`<b>${r.ka}</b> / ${r.k.length-r.ka}${r.kl?` <span class="late">${r.kl} late</span>`:''}`:'—'}</td><td data-l="Reqs ✓ · RfA · total">${r.q.length?`<div class="kv"><b>${nf(r.qa)}</b> · ${nf(r.qr)} · ${nf(r.q.length)}</div>${dsbar(r.qa,r.qr,r.q.length)}`:'—'}</td></tr>`}).join('')}</tbody></table>`;
    const head=cont=>`<div class="sd-k">${W.nm} · ${esc(W.L1)}${cont?' · KDDs (cont.)':''}</div><h2>${W.nm}${cont?` <span>KDDs by L2 → L4, continued</span>`:''}</h2>${cont?'':kpi(W)}${cont?'':`<p class="sd-t">${take(W)}</p>`}`;
    const kp=p=>`<div class="kpan"><div class="kph">KDDs by L2 → L4 <span><b class="tick">✓</b> approved · state, target date and Late for the rest</span></div>${p?p.map(lineHTML).join(''):'<div class="empty">No KDDs are linked to L4s in this workstream.</div>'}</div>`;
    const foot=`<span>As of ${asof}</span><span>Requirements counted under their own L4 (workshop link as fallback); greyed rows have no KDDs or requirements</span>`;
    S.push({lab:W.nm,html:slideFrame('ws',head(false),`<div class="wsgrid">${tbl}${kp(pages[0])}</div>`,foot)});
    pages.slice(1).forEach((p,i)=>S.push({lab:`${W.nm} cont.`,html:slideFrame('ws cont',head(true),`<div class="kcols">${kp(p)}</div>`,foot)}));
  });
  /* definitions */
  S.push({lab:'Definitions',html:slideFrame('defs','<div class="sd-k">Notes</div><h2>Definitions and data sources</h2>',
    `<ul class="dfl"><li><b>Workstream and L2.</b> L2s are placed by their L1 number: 3.x D2D, 4.x M2O, 5.x S2P, 6.x O2C, 7.x R2R, 1.x Technical (cross-stream). L1/L2/L4 come from the L1–L4 mapping file (Epic rows).</li>
     <li><b>KDDs.</b> From the R6 KDD export ({{deck_kdd_src}}), linked to L4 Epics. Approved = state Approved; not approved = New, In Analysis or Pending Approval. Late = not approved with target date on or before ${asof}. Rejected KDDs are left out. A KDD linked to several L4s is listed under each but counted once per L2 and per workstream.</li>
     <li><b>Requirements.</b> From the requirements export ({{deck_req_src}}). Approved = state Approved; RfA = Ready for Acceptance. Each requirement counts under its own L4 (the 4-level number in its ID), or under the L4s of its workshops when it has none. Rejected requirements are left out.</li>
     <li><b>Unlinked KDDs and requirements.</b> KDDs and requirements with no L4 link sit in a “Not linked to an L4” line on their own workstream’s slide (workstream from the KDD area path) and count in that slide’s totals. Technical collects everything outside the five value streams (cross-stream and unassigned area paths). KDDs linked to an L4 in another workstream stay under that L4, tagged with their own workstream (for example “O2C KDD”).</li>
     <li><b>Not on these slides.</b> Workshops, PBIs and RAID; see the heatmap above and the other tabs.</li></ul>`,`<span>As of ${asof}</span>{{deck_footer_name_html}}`)});
  DK_N=S.length;DK_I=Math.min(DK_I,DK_N-1);
  $('dkStage').innerHTML=S.map((s,i)=>`<div class="dslide${i===DK_I?' on':''}" data-i="${i}" role="group" aria-roledescription="slide" aria-label="${i+1} of ${S.length}: ${esc(s.lab)}">${s.html}</div>`).join('');
  $('dkThumbs').innerHTML=S.map((s,i)=>`<button type="button" class="dth${i===DK_I?' on':''}" data-i="${i}"><b>${i+1}</b>${esc(s.lab)}</button>`).join('');
  dkGo(DK_I);dkFit();
}
function dkGo(i){DK_I=Math.max(0,Math.min(DK_N-1,i));document.querySelectorAll('#dkStage .dslide').forEach(s=>s.classList.toggle('on',+s.dataset.i===DK_I));
  document.querySelectorAll('#dkThumbs .dth').forEach(b=>{const on=+b.dataset.i===DK_I;b.classList.toggle('on',on);b.setAttribute('aria-current',on?'true':'false');if(on&&b.scrollIntoView&&b.parentElement.scrollWidth>b.parentElement.clientWidth){const p=b.parentElement;p.scrollLeft=b.offsetLeft-p.clientWidth/2+b.clientWidth/2}});
  const c=$('dkCount');if(c)c.textContent=`${DK_I+1} / ${DK_N}`;$('dkPrev').disabled=DK_I===0;$('dkNext').disabled=DK_I===DK_N-1}
function dkFit(){const st=$('dkStage');if(!st)return;const fs=document.fullscreenElement===$('deck');const w=fs?window.innerWidth:st.clientWidth,h=fs?window.innerHeight-56:Infinity;
  const flow=!fs&&w<700;st.classList.toggle('flow',flow);if(flow){st.style.height='';st.querySelectorAll('.sd-in,.slide-d.title .sd-in').forEach(x=>x.style.transform='');return}
  const sc=Math.min(w/1280,h/720);st.style.setProperty('--sc',sc);st.style.height=(720*sc)+'px';}
const KSTO=['New','In Analysis','Pending Approval','Approved','Rejected'];
sl.push(MS($('msDks'),'dks','KDD state',()=>KSTO.map(s=>({v:s,t:s+(s==='Rejected'?' (off by default)':''),c:K.filter(k=>k.s===s).length}))));
document.querySelectorAll('.dkpre').forEach(b=>b.addEventListener('click',()=>{F.dks.clear();if(b.dataset.p==='open')DK_OPEN.forEach(s=>F.dks.add(s));else if(b.dataset.p==='appr')F.dks.add('Approved');DK_I=Math.min(DK_I,1);update()}));
$('dkPrev').addEventListener('click',()=>dkGo(DK_I-1));$('dkNext').addEventListener('click',()=>dkGo(DK_I+1));
$('dkThumbs').addEventListener('click',e=>{const b=e.target.closest('.dth');if(b)dkGo(+b.dataset.i)});
$('dkPresent').addEventListener('click',()=>{const d=$('deck');try{if(document.fullscreenElement)document.exitFullscreen();else if(d.requestFullscreen)d.requestFullscreen()}catch(e){}});
document.addEventListener('fullscreenchange',()=>{$('deck').classList.toggle('fs',document.fullscreenElement===$('deck'));$('dkPresent').textContent=document.fullscreenElement?'Exit presentation':'Present';dkFit()});
document.addEventListener('keydown',e=>{const pane=$('tab-wsview');if(!pane||pane.hidden||/INPUT|TEXTAREA|SELECT/.test((e.target.tagName||'')))return;
  if(e.key==='ArrowRight'||e.key==='PageDown'){if(document.fullscreenElement||$('deck').matches(':hover')||$('deck').contains(document.activeElement)){e.preventDefault();dkGo(DK_I+1)}}
  else if(e.key==='ArrowLeft'||e.key==='PageUp'){if(document.fullscreenElement||$('deck').matches(':hover')||$('deck').contains(document.activeElement)){e.preventDefault();dkGo(DK_I-1)}}});
window.addEventListener('resize',dkFit);
try{new ResizeObserver(dkFit).observe($('dkStage'))}catch(e){}

document.addEventListener('click',e=>{const b=e.target.closest('.actlink');if(b){e.preventDefault();e.stopPropagation();RFOCUS={label:b.dataset.lab,ids:ACTSETS[b.dataset.k]||new Set()};F.rst.clear();RA_OPEN.forEach(s=>F.rst.add(s));['Completed','Closed','Archived'].forEach(s=>F.rst.add(s));showView('raid',true);update();return}
  if(e.target.id==='raFocusX'){RFOCUS=null;F.rst.clear();RA_OPEN.forEach(s=>F.rst.add(s));update()}},true);
{const go=card=>{const b=document.querySelector(`#pvTabs .ptab[data-t="${card.dataset.t}"]`);if(!b)return;b.click();const t=$('pvTabs');let rm=false;try{rm=matchMedia('(prefers-reduced-motion: reduce)').matches}catch(e){}t&&t.scrollIntoView&&t.scrollIntoView({behavior:rm?'auto':'smooth',block:'start'})};
  $('pvCards').addEventListener('click',e=>{if(e.target.closest('.tl,.lnk2'))return;const c=e.target.closest('.gcard[data-t]');if(c)go(c)});
  $('pvCards').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('.gcard[data-t]')){e.preventDefault();go(e.target)}});}
/* ---------- E2E Build Journey ---------- */
F.ews=new Set();F.ebt=new Set();F.ejm=new Set();
let EJSEL=null;const EJCLOSED=new Set(),EJSHOW={};
const EJ_U5=(()=>{const d=new Date(ASOF+'T12:00:00');d.setDate(d.getDate()+5);return d.toISOString().slice(0,10)})();
const EJST=[['CRD','CRD','C'],['CUT','Config & CUT','C'],['FDD','FDD','R'],['SD','Source Design','R'],['MD','Middleware Design','R'],['TD','Target Design','R'],['SB','Source Build','R'],['MB','Middleware Build','R'],['TB','Target Build','R'],['FUT','FUT','R'],['OTH','Other','R']];
const EJSN=Object.fromEntries(EJST.map(s=>[s[0],s[1]]));
const ejStage=p=>{const pre=(p.t||'').split(' - ')[0].trim();if(pre==='CRD')return 'CRD';if(pre.startsWith('Config & CUT'))return 'CUT';if(pre==='FDD'||pre==='FUT')return pre;
  const m=pre.match(/^(Source|Middleware|Target)\s+(Design|Build)$/i);if(m)return m[1][0].toUpperCase()+m[2][0].toUpperCase();return 'OTH'};
const ejDone=p=>p.s==='Completed'||p.s==='Ready for Acceptance';
const ejCls=p=>ejDone(p)?'ok':(p.s==='Blocked'||(p.d&&p.d<=ASOF))?'r':(p.d&&p.d>ASOF&&p.d<=EJ_U5)?'a':'';
const ejWorst=ps=>ps.some(p=>ejCls(p)==='r')?'r':ps.some(p=>ejCls(p)==='a')?'a':'';
const ejMo=d=>d?d.slice(0,7):'none';
const EJKIDS=C.map(()=>[]);P.forEach(p=>{if(p.rc>=0){p.ejs=ejStage(p);EJKIDS[p.rc].push(p)}});
const EJMONTHS=[...new Set(P.filter(p=>p.rc>=0&&p.d).map(p=>p.d.slice(0,7)))].sort();
const ejMoLab=m=>new Date(m+'-15T12:00:00').toLocaleDateString('en-US',{month:'short'});
/* month hierarchy slicer */
function MSH(el,key,label){
  const btn=document.createElement('button');btn.type='button';btn.id='btn-'+key;const pop=document.createElement('div');pop.className='pop ejpop';pop.hidden=true;el.append(btn,pop);
  const yrs=()=>[...new Set(EJMONTHS.map(m=>m.slice(0,4)))];
  const cnt=m=>P.filter(p=>p.rc>=0&&ejMo(p.d)===m).length;
  function draw(){const s=F[key];btn.classList.toggle('on',s.size>0);
    const v=!s.size?'All months':s.size===1?([...s][0]==='none'?'No target date':ejMoLab([...s][0])+' '+[...s][0].slice(0,4)):s.size+' selected';
    btn.innerHTML=`<span><span class="k">${label}:</span> <span class="v">${esc(v)}</span></span><span class="chev"></span>`;
    pop.innerHTML=`<div class="row"><button type="button" class="lnk" data-a="all">Select all</button><button type="button" class="lnk" data-a="clr">Clear</button></div>`+
      yrs().map(y=>{const ms=EJMONTHS.filter(m=>m.startsWith(y)),all=ms.every(m=>s.has(m)),some=ms.some(m=>s.has(m));
        return `<label class="yr"><input type="checkbox" data-y="${y}" ${all?'checked':''} ${!all&&some?'data-mixed="1"':''}> <b>${y}</b><span class="c">${ms.reduce((a,m)=>a+cnt(m),0)}</span></label>`+
          ms.map(m=>`<label class="mo"><input type="checkbox" value="${m}" ${s.has(m)?'checked':''}> ${ejMoLab(m)}<span class="c">${cnt(m)}</span></label>`).join('')}).join('')+
      `<div class="mo-sep"></div><label><input type="checkbox" value="none" ${s.has('none')?'checked':''}> No target date<span class="c">${cnt('none')}</span></label>`;
    pop.querySelectorAll('input[data-mixed]').forEach(i=>i.indeterminate=true)}
  btn.addEventListener('click',e=>{e.stopPropagation();const open=pop.hidden;document.querySelectorAll('.pop').forEach(p=>p.hidden=true);pop.hidden=!open});
  pop.addEventListener('click',e=>{e.stopPropagation();const a=e.target.dataset&&e.target.dataset.a;if(a==='all'){EJMONTHS.forEach(m=>F[key].add(m));F[key].add('none');update(true)}if(a==='clr'){F[key].clear();update(true)}});
  pop.addEventListener('change',e=>{const t=e.target;if(t.dataset.y){const ms=EJMONTHS.filter(m=>m.startsWith(t.dataset.y));ms.forEach(m=>t.checked?F[key].add(m):F[key].delete(m))}else{t.checked?F[key].add(t.value):F[key].delete(t.value)}update(true)});
  return {draw};
}
sl.push(MS($('msEws'),'ews','Workstream',()=>VORD.filter(w=>C.some(c=>c.ws===w)).map(w=>({v:w,t:VWN(w),c:C.filter(c=>c.ws===w).length+' items'}))),
  MS($('msEbt'),'ebt','Build type',()=>['Configuration','RICEFW'].map(t=>({v:t,t,c:C.filter(c=>c.ty===t).length}))),MSH($('msEjm'),'ejm','Due date'));
$('ejReset').addEventListener('click',()=>{F.ews.clear();F.ebt.clear();F.ejm.clear();EJSEL=null;$('ejq').value='';update()});
$('ejq').addEventListener('input',()=>renderE2E());
function renderE2E(){
  if(!$('ejTiles'))return;
  const term=$('ejq').value.trim().toLowerCase();
  const pOK=p=>!F.ejm.size||F.ejm.has(ejMo(p.d));
  const items=C.map((c,i)=>({c,ps:EJKIDS[i].filter(pOK)})).filter(x=>(!F.ews.size||F.ews.has(x.c.ws))&&(!F.ebt.size||F.ebt.has(x.c.ty))&&(!F.ejm.size||x.ps.length)
    &&(!term||(x.c.id+' '+x.c.t+' '+x.ps.map(p=>p.id).join(' ')).toLowerCase().includes(term)));
  const ps=items.flatMap(x=>x.ps);
  const nC=items.filter(x=>x.c.ty==='Configuration').length,nR=items.length-nC,noP=items.filter(x=>!EJKIDS[C.indexOf(x.c)].length).length;
  const done=ps.filter(ejDone).length,od=ps.filter(p=>!ejDone(p)&&p.d&&p.d<=ASOF).length,blk=ps.filter(p=>p.s==='Blocked').length,d5=ps.filter(p=>!ejDone(p)&&p.d&&p.d>ASOF&&p.d<=EJ_U5).length;
  const fd=d=>new Date(d+'T12:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short'});
  const d1=(()=>{const d=new Date(ASOF+'T12:00:00');d.setDate(d.getDate()+1);return d.toISOString().slice(0,10)})();
  $('ejTiles').innerHTML=[
    ['Build items',items.length.toLocaleString(),`${nC} Configuration · ${nR} RICEFW${noP?` · ${noP} with no PBIs`:''}`,''],
    ['PBIs under build items',ps.length.toLocaleString(),F.ejm.size?'in the selected months':'all target dates',''],
    ['Done',done.toLocaleString(),'Completed + Ready for Acceptance','g'],
    ['Past due',od.toLocaleString(),`open, target on or before ${fd(ASOF)}`,od?'r':''],
    ['Blocked',blk.toLocaleString(),'state Blocked',blk?'r':''],
    ['Due in next 5 days',d5.toLocaleString(),`${fd(d1)} – ${fd(EJ_U5)}`,d5?'a':'']].map(([k,v,s,c])=>`<div class="ejt ${c}"><span>${k}</span><b>${v}</b><small>${s}</small></div>`).join('');
  $('ejStrip').innerHTML=EJST.map(([k,n,t])=>{const a=ps.filter(p=>p.ejs===k),dn=a.filter(ejDone).length,pc=a.length?Math.round(dn/a.length*100):0,w=ejWorst(a);
    return `<div class="ejs ${t==='C'?'c':'r'}${k==='FDD'?' first':''}"><span class="n">${n}</span><div class="b"><i style="width:${pc}%"></i></div><span class="v"><b>${pc}%</b> ${dn}/${a.length}</span>${w?`<i class="dot ${w}"></i>`:''}</div>`}).join('');
  /* heatmap A */
  const wsL=VORD.filter(w=>items.some(x=>x.c.ws===w));
  const cellA=(w,k)=>{const a=items.filter(x=>x.c.ws===w).flatMap(x=>x.ps).filter(p=>p.ejs===k);if(!a.length)return `<td class="ejc nd">—</td>`;
    const dn=a.filter(ejDone).length,c=ejWorst(a),r=a.filter(p=>ejCls(p)==='r').length,am=a.filter(p=>ejCls(p)==='a').length,sel=EJSEL&&EJSEL.w===w&&EJSEL.k===k;
    return `<td class="ejc ${c}${sel?' sel':''}" data-w="${esc(w)}" data-k="${k}" role="button" tabindex="0" title="${esc(VWN(w))} · ${EJSN[k]}: ${dn} of ${a.length} done${r?` · ${r} past due/blocked`:''}${am?` · ${am} due in 5 days`:''}\nClick to filter the build items below"><b>${dn}</b>/${a.length}</td>`};
  $('ejHeatA').innerHTML=wsL.length?`<table class="ejA"><thead><tr><th rowspan="2">Workstream</th><th colspan="2" class="gC">Configuration</th><th colspan="9" class="gR">RICEFW</th></tr><tr>${EJST.map(([k,n,t])=>`<th class="${t==='C'?'gC':'gR'}${k==='FDD'?' first':''}">${n}</th>`).join('')}</tr></thead>
    <tbody>${wsL.map(w=>`<tr><th>${esc(VWN(w))}</th>${EJST.map(([k])=>cellA(w,k)).join('')}</tr>`).join('')}</tbody></table>`:'<div class="empty">No build items match these filters.</div>';
  /* heatmap B */
  const selF=x=>!EJSEL||(x.c.ws===EJSEL.w&&x.ps.some(p=>p.ejs===EJSEL.k));
  $('ejSel').innerHTML=EJSEL?`<span class="fchip">Showing <b>${esc(VWN(EJSEL.w))} · ${EJSN[EJSEL.k]}</b> <button type="button" id="ejSelX" aria-label="Clear">×</button></span>`:'';
  const block=(ty,cols,title)=>{const its=items.filter(x=>x.c.ty===ty&&selF(x));if(!its.length)return '';
    const groups=VORD.filter(w=>its.some(x=>x.c.ws===w));
    const cell=(x,k)=>{const a=x.ps.filter(p=>p.ejs===k);if(!a.length)return `<td class="ejb nd"></td>`;
      const hi=EJSEL&&EJSEL.k===k?' hk':'';
      if(a.length===1){const p=a[0],c=ejCls(p);return `<td class="ejb ${c}${hi}"><a href="${ADO}${encodeURIComponent(p.id)}" target="_blank" rel="noopener noreferrer" title="${esc(p.id+' · '+p.t+'\n'+p.s+(p.d?' · due '+fmtD(p.d):' · no target date')+(p.o?' · '+p.o:''))}">${c==='ok'?'<span class="tk">✓</span>':''}${p.d?fd(p.d):'no date'}</a></td>`}
      const dn=a.filter(ejDone).length,c=ejWorst(a);return `<td class="ejb ${c}${hi}"><span title="${esc(a.map(p=>p.id+' · '+p.s+(p.d?' · '+fmtD(p.d):'')+' · '+p.t).join('\n'))}">${dn}/${a.length} done</span></td>`};
    return `<div class="ejblk"><div class="ejbh"><b>${title}</b><span class="note">${its.length} items</span></div><div class="tblwrap ejwrap"><table class="ejB"><thead><tr><th class="bi">Build item</th><th>State</th>${cols.map(k=>`<th class="${EJSEL&&EJSEL.k===k?'hk':''}">${EJSN[k]}</th>`).join('')}<th>Progress</th></tr></thead><tbody>${groups.map(w=>{
      const g=its.filter(x=>x.c.ws===w).sort((a,b)=>a.c.id.localeCompare(b.c.id)),key=ty+w,closed=EJCLOSED.has(key),lim=EJSHOW[key]||50;
      const gp=g.flatMap(x=>x.ps),gr=gp.filter(p=>ejCls(p)==='r').length;
      return `<tr class="ejg" data-g="${esc(key)}" role="button" tabindex="0" aria-expanded="${!closed}"><td colspan="${cols.length+3}"><span class="cv"></span>${esc(VWN(w))} <span class="note">${g.length} items · ${gp.filter(ejDone).length}/${gp.length} PBIs done${gr?` · <b class="red">${gr} past due / blocked</b>`:''}</span></td></tr>`+
        (closed?'':g.slice(0,lim).map(x=>{const all=x.ps,dn=all.filter(ejDone).length,pc=all.length?dn/all.length*100:0;
          return `<tr><td class="bi"><a href="${ADO}${encodeURIComponent(x.c.id)}" target="_blank" rel="noopener noreferrer">${esc(x.c.id)}</a> <span class="ejn" title="${esc(x.c.t)}">${esc(x.c.t)}</span>${!EJKIDS[C.indexOf(x.c)].length?' <span class="ctag none">No PBIs</span>':''}</td><td><span class="note">${esc(x.c.s)}</span></td>${cols.map(k=>cell(x,k)).join('')}<td class="pg"><span class="pgb"><i style="width:${pc.toFixed(0)}%"></i></span><span class="note">${dn}/${all.length}</span></td></tr>`}).join('')+
        (g.length>lim?`<tr><td colspan="${cols.length+3}"><button type="button" class="lnk ejmore" data-g="${esc(key)}">Show ${Math.min(50,g.length-lim)} more of ${g.length-lim} remaining</button></td></tr>`:''))}).join('')}</tbody></table></div></div>`};
  $('ejHeatB').innerHTML=(block('Configuration',['CRD','CUT'],'Configuration items')+block('RICEFW',['FDD','SD','MD','TD','SB','MB','TB','FUT','OTH'],'RICEFW objects'))||'<div class="empty">No build items match these filters.</div>';
}
$('ejHeatA').addEventListener('click',e=>{const td=e.target.closest('td[data-k]');if(!td)return;EJSEL=EJSEL&&EJSEL.w===td.dataset.w&&EJSEL.k===td.dataset.k?null:{w:td.dataset.w,k:td.dataset.k};renderE2E();$('ejHeatB').scrollIntoView&&$('ejHeatB').scrollIntoView({block:'start',behavior:'smooth'})});
$('ejHeatA').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('td[data-k]')){e.preventDefault();e.target.click()}});
$('ejSel').addEventListener('click',e=>{if(e.target.id==='ejSelX'){EJSEL=null;renderE2E()}});
$('ejHeatB').addEventListener('click',e=>{const g=e.target.closest('tr.ejg');if(g){const k=g.dataset.g;EJCLOSED.has(k)?EJCLOSED.delete(k):EJCLOSED.add(k);renderE2E();return}const m=e.target.closest('.ejmore');if(m){EJSHOW[m.dataset.g]=(EJSHOW[m.dataset.g]||50)+50;renderE2E()}});
$('ejHeatB').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('tr.ejg')){e.preventDefault();e.target.click()}});

const VIEWS=['wsview','progress','l4','raid','burnup','e2e'];
function showView(v,push){if(!VIEWS.includes(v))v='wsview';
  VIEWS.forEach(x=>{$('tab-'+x).hidden=x!==v;$('mt-'+x).setAttribute('aria-selected',x===v);$('mt-'+x).tabIndex=x===v?0:-1});
  try{localStorage.setItem('phx-view',v)}catch(e){}
  if(push){try{history.replaceState(null,'','#'+v)}catch(e){}}}
$('mtabs').addEventListener('click',e=>{const b=e.target.closest('.mtab');if(b)showView(b.dataset.v,true)});
$('mtabs').addEventListener('keydown',e=>{if(e.key!=='ArrowRight'&&e.key!=='ArrowLeft')return;const cur=VIEWS.findIndex(x=>!$('tab-'+x).hidden);const n=VIEWS[(cur+(e.key==='ArrowRight'?1:VIEWS.length-1))%VIEWS.length];showView(n,true);$('mt-'+n).focus()});
window.addEventListener('hashchange',()=>showView(location.hash.slice(1)));
(function(){let v=location.hash.slice(1);if(!VIEWS.includes(v)){try{v=localStorage.getItem('phx-view')||''}catch(e){v=''}}showView(v)})();
update();
})();</script>

</body></html>"""


def render(template: str, data: dict) -> str:
    def fill(m: re.Match) -> str:
        as_json, key = m.group(1), m.group(2)
        if key == "footnotes":
            return "\n".join(f"    <span>{f}</span>" for f in data[key])
        if key not in data:
            raise KeyError(f"'{key}' is used in the template but missing from the data file")
        if as_json:
            # compact separators and no ASCII escaping keep the 1.5MB DATA blob small;
            # escape "</" so the JSON can never close the <script> element
            return json.dumps(data[key], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        return str(data[key])

    return PLACEHOLDER.sub(fill, template)


def main(argv: list[str]) -> None:
    data_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_DATA
    data = json.loads(data_path.read_text(encoding="utf-8"))
    out_path = Path(argv[2]) if len(argv) > 2 else HERE / f"{html.unescape(data['title'])}.html"
    out_path.write_text(render(TEMPLATE, data), encoding="utf-8", newline="")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv)
