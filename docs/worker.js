// Runs pubfingerprint (Python) in the browser with Pyodide, inside a Web Worker so the page stays responsive.
// Data are fetched from the public ORCID and OpenAlex APIs; nothing is sent anywhere else or stored.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
importScripts(PYODIDE + "pyodide.js");
let py = null;
const say = (msg) => postMessage({ type: "status", msg });

async function init() {
  if (py) return py;
  say("Loading Python in your browser (first time ~20 s, then cached)…");
  py = await loadPyodide({ indexURL: PYODIDE });
  await py.loadPackage(["numpy", "matplotlib", "networkx"]);
  for (const f of ["publication_map.py", "pubfingerprint.py", "web_adapter.py"]) {
    let r = await fetch("py/" + f + "?v=" + Date.now());
    if (!r.ok) r = await fetch("py/" + f + ".txt?v=" + Date.now());   // hosts that do not serve .py
    if (!r.ok) throw new Error("Could not load " + f);
    py.FS.writeFile(f, await r.text());
  }
  await py.runPythonAsync(`
import os, sys
os.environ["MPLBACKEND"] = "AGG"
import matplotlib; matplotlib.use("Agg")
sys.path.insert(0, ".")
import publication_map as pm, pubfingerprint as pf, web_adapter as wa
`);
  return py;
}

async function getJSON(url, headers = {}) {
  for (let k = 0; k < 3; k++) {
    try {
      const r = await fetch(url, { headers });
      if (r.status === 404) return null;
      if (r.ok) return await r.json();
    } catch (e) { /* retry */ }
    await new Promise((res) => setTimeout(res, 1500 * (k + 1)));
  }
  throw new Error("Request failed: " + url.split("?")[0]);
}

onmessage = async (ev) => {
  const { orcid, mailto, includePreprints, demo } = ev.data;
  try {
    const py = await init();
    const H = { Accept: "application/json" };
    say(demo ? "Loading the example record…" : "Reading the ORCID record…");
    const person = await getJSON(demo ? "demo/person.json" : `https://pub.orcid.org/v3.0/${orcid}/person`, H);
    const works = await getJSON(demo ? "demo/works.json" : `https://pub.orcid.org/v3.0/${orcid}/works`, H);
    if (!works) throw new Error("No public ORCID record found for " + orcid + ".");
    py.globals.set("works_json", JSON.stringify(works));
    const dois = py.runPython("import json; json.dumps(wa.all_dois(json.loads(works_json)))");
    const list = JSON.parse(dois);
    if (!list.length) throw new Error("The ORCID record lists no works with a DOI.");
    const oa = demo ? await getJSON("demo/openalex.json") : [];
    const sel = "id,doi,title,publication_year,type,authorships,primary_topic,primary_location";
    for (let i = 0; !demo && i < list.length; i += 50) {
      say(`Fetching details from OpenAlex: ${Math.min(i + 50, list.length)} of ${list.length} DOIs…`);
      const f = encodeURIComponent("doi:" + list.slice(i, i + 50).join("|"));
      const url = `https://api.openalex.org/works?filter=${f}&per-page=50&select=${sel}` + (mailto ? `&mailto=${encodeURIComponent(mailto)}` : "");
      const j = await getJSON(url);
      if (j && j.results) oa.push(...j.results);
    }
    say("Computing the profile (large records can take a minute or two)…");
    py.globals.set("person_json", JSON.stringify(person || {}));
    py.globals.set("oa_json", JSON.stringify(oa));
    py.globals.set("orcid", orcid);
    py.globals.set("incl", !!includePreprints);
    const report = await py.runPythonAsync(`
import json, io, contextlib, os
papers, me, display, report = wa.build_papers(orcid, json.loads(person_json), json.loads(works_json), json.loads(oa_json), incl)
if not papers:
    raise ValueError("None of the ORCID works could be matched to a peer-reviewed article in OpenAlex.")
os.makedirs("/out", exist_ok=True)
for f in os.listdir("/out"):
    os.remove("/out/" + f)
out = "/out/" + orcid
pm.write_csv(papers, out + "_from_orcid.csv")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rec, res = pf.run(papers, me, out, None, True, name=display, source=f"ORCID {orcid} via OpenAlex")
report["display"] = display
report["me"] = me
report["summary"] = res["summary"]
report["roles"] = [dict(period=r["period"], label=r["label"]) for r in res["roles"]]
report["temporal"] = {k: res["temporal_lines"][k] for k in ("switches", "expected_switches_random", "random_order_95")}
report["diversity"] = {k: dict(richness=v["richness"], q1=v["q1"]) for k, v in res["diversity"].items()}
json.dumps(report)
`);
    const files = {};
    for (const f of py.FS.readdir("/out")) {
      if (f.startsWith(".")) continue;
      files[f] = py.FS.readFile("/out/" + f);
    }
    postMessage({ type: "done", report: JSON.parse(report), files });
  } catch (e) {
    postMessage({ type: "error", msg: String(e.message || e).split("\n").filter(Boolean).slice(-1)[0] });
  }
};
