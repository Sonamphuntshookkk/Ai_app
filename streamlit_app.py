"""
AgriAdvisor: single-file Streamlit app (agent + web UI). No other .py or notebook is needed.
Run locally:  streamlit run streamlit_app.py
Deploy:       main file = streamlit_app.py, plus requirements.txt containing: streamlit
"""
import streamlit as st
import uuid
import os
os.environ.setdefault("AGRI_DB", "/tmp/agri_memory.db")   # writable location on Streamlit Cloud

import os, re, sys, json, math, time, sqlite3, datetime, urllib.request, urllib.parse
from collections import Counter

DB_PATH = os.environ.get("AGRI_DB", "agri_memory.db")

# ----------------------------------------------------------------------------
# Static data
# ----------------------------------------------------------------------------
LOCATIONS = {  # approximate dzongkhag / town coordinates
    "thimphu": (27.47, 89.64), "paro": (27.43, 89.41), "punakha": (27.59, 89.86),
    "wangdue": (27.49, 89.90), "bumthang": (27.55, 90.75), "haa": (27.39, 89.28),
    "trashigang": (27.33, 91.55), "mongar": (27.28, 91.24), "trongsa": (27.50, 90.51),
    "samdrup jongkhar": (26.80, 91.50), "phuentsholing": (26.85, 89.39), "gelephu": (26.87, 90.49),
}
CROPS = {"paddy": ["paddy", "rice"], "maize": ["maize", "corn"], "potato": ["potato", "potatoes"],
         "apple": ["apple", "apples"]}
UNSUPPORTED = ["dragon fruit", "tomato", "chilli", "cardamom", "orange", "mandarin", "wheat",
               "barley", "buckwheat", "ginger", "banana"]
BANNED_CHEMICALS = ["paraquat", "endosulfan", "ddt", "monocrotophos", "carbofuran"]  # demo list
AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(acres?|ha|hectares?)\b")

# (id, crop, title, text) - SAMPLE knowledge base. Replace/extend with MoAL / NCOA / RNR documents.
KB = [
    ("paddy-blast", "paddy", "Rice blast", "Rice blast shows diamond or spindle shaped lesions with grey centres on leaves, and can attack the neck of the panicle. It is favoured by high humidity, cool nights and excess nitrogen. Use resistant varieties, avoid over-applying nitrogen, keep fertiliser balanced, and use a fungicide only as recommended by the local extension office."),
    ("paddy-water", "paddy", "Water management", "Keep 2 to 5 cm of standing water after transplanting and avoid long dry spells during tillering and flowering. Drain the field about 10 to 14 days before harvest."),
    ("paddy-calendar", "paddy", "Planting time", "Paddy nursery is sown in spring and seedlings are transplanted at about 25 to 30 days. Exact timing depends on altitude and water availability, so confirm with the Dzongkhag agriculture office."),
    ("paddy-nutrition", "paddy", "Nutrient timing", "Split nitrogen into basal, tillering and panicle initiation doses rather than one large application. Apply phosphorus and potash at transplanting."),
    ("maize-armyworm", "maize", "Fall armyworm", "Fall armyworm causes ragged feeding holes in leaves and sawdust-like frass in the whorl. Scout fields early, hand-pick egg masses and young larvae, and treat the whorl early with a recommended product or neem-based spray."),
    ("maize-blight", "maize", "Northern leaf blight", "Northern leaf blight appears as long elliptical grey-green lesions on leaves and is worse in humid weather. Rotate crops, bury residue and choose tolerant varieties."),
    ("maize-nutrition", "maize", "Nutrient timing", "Apply phosphorus and potash at sowing with part of the nitrogen, then top-dress the rest of the nitrogen when plants are about knee high."),
    ("potato-lateblight", "potato", "Late blight", "Late blight causes dark water-soaked brown lesions on leaves, with white fuzzy growth on the underside in cool wet humid weather, and it spreads fast. Use certified seed tubers, earth up ridges, remove infected foliage, avoid overhead irrigation and apply a protectant fungicide only as recommended locally before rain risk periods."),
    ("potato-wilt", "potato", "Bacterial wilt", "Bacterial wilt causes sudden wilting of green plants, with a brown ring and bacterial ooze in the cut stem. There is no cure: remove and destroy affected plants, rotate with a non-host crop for several seasons and do not plant in the same infected plot."),
    ("potato-nutrition", "potato", "Fertiliser and seed", "Use certified seed tubers, well-rotted farmyard manure and a balanced NPK basal dose. Avoid excess nitrogen, which encourages leafy growth and disease."),
    ("apple-scab", "apple", "Apple scab", "Apple scab shows olive-green velvety spots on leaves and scabby cracked spots on fruit, and is worse in wet springs. Collect and destroy fallen leaves, prune for airflow and use fungicide only as locally recommended."),
    ("apple-woolly-aphid", "apple", "Woolly aphid", "Woolly aphid appears as white cottony masses on twigs and branches and may cause galls and sticky honeydew. Prune heavily infested shoots and protect natural enemies."),
    ("apple-pruning", "apple", "Pruning", "Prune apple trees in the dormant season in winter, removing dead, crossing and overcrowded branches so light and air reach the canopy."),
    ("general-pesticide-safety", "general", "Pesticide safety", "Only use registered products, read the label, never exceed the label dose, wear protective gear, respect the pre-harvest interval and keep sprays away from water sources."),
    ("general-spray-weather", "general", "Spray timing", "Avoid spraying if rain is expected within 24 hours or in strong wind because the product washes off or drifts. Spray in calm, dry conditions in the early morning or evening."),
    ("general-soil", "general", "Soil testing", "Test soil every 2 to 3 years. Lime acidic soils with pH below about 5.5 and add compost or farmyard manure to improve structure."),
    ("general-ipm", "general", "Integrated pest management", "Scout regularly, use resistant varieties, rotate crops, keep fields clean and use chemicals only as a last resort."),
]
KB = [dict(id=i, crop=c, title=t, text=x, source="Sample KB (replace with MoAL/NCOA documents)") for i, c, t, x in KB]

DISEASES = [  # symptom keyword matching tool
    ("paddy", "Rice blast", "paddy-blast", ["diamond", "spindle", "grey", "gray", "centre", "center", "neck", "spot", "lesion"]),
    ("maize", "Fall armyworm", "maize-armyworm", ["ragged", "hole", "whorl", "frass", "sawdust", "caterpillar", "chewed", "worm"]),
    ("maize", "Northern leaf blight", "maize-blight", ["elliptical", "elongated", "cigar", "grey", "gray", "lesion", "blight"]),
    ("potato", "Late blight", "potato-lateblight", ["water", "soaked", "brown", "dark", "fuzz", "fuzzy", "white", "blight", "rot", "spot", "leave", "leaf"]),
    ("potato", "Bacterial wilt", "potato-wilt", ["wilt", "wilting", "sudden", "ring", "ooze", "stem"]),
    ("apple", "Apple scab", "apple-scab", ["olive", "velvety", "scab", "scabby", "cracked", "spot", "fruit"]),
    ("apple", "Woolly aphid", "apple-woolly-aphid", ["cottony", "woolly", "aphid", "gall", "sticky", "white"]),
]

RATES = {  # ILLUSTRATIVE kg nutrient per ha (N, P2O5, K2O) - verify with local recommendations
    "paddy": (80, 40, 40), "maize": (100, 50, 40), "potato": (100, 80, 100), "apple": (100, 50, 100)}
SPLIT = {
    "paddy": "Basal: all DAP and MOP plus 1/3 urea; tillering: 1/3 urea; panicle initiation: 1/3 urea.",
    "maize": "Sowing: all DAP and MOP plus 1/3 urea; knee-high stage: remaining 2/3 urea.",
    "potato": "Planting: all DAP and MOP plus half the urea; earthing-up: the rest of the urea.",
    "apple": "Spread over the tree drip line: DAP and MOP before bud break, urea split before bud break and after fruit set.",
}

INTENT_WORDS = {
    "weather": "weather rain forecast spray temperature humid humidity frost",
    "disease": "disease spot lesion wilt blight pest worm insect yellow symptom sign scab aphid rot hole fungus caterpillar frass wilting leaf leave problem",
    "fertilizer": "fertilizer fertiliser urea dap npk manure nutrient",
}
INTENT_WORDS = {k: {w.rstrip("s") for w in v.split()} for k, v in INTENT_WORDS.items()}
AGRI_WORDS = {w.rstrip("s") for w in """crop farm soil seed harvest plant irrigation field yield orchard tree grow
    pesticide fungicide herbicide cultivation nursery transplanting prune pruning water lime compost paddy rice maize
    corn potato apple vegetable agriculture farmer dzongkhag""".split()}
for _v in INTENT_WORDS.values():
    AGRI_WORDS |= _v

STOP = set("a an the of and or to in on is are for with my i it this that how what should do can be at by from as have has when".split())


def tok(text):
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w
            for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 1]


# ----------------------------------------------------------------------------
# Retrieval (TF-IDF cosine, stdlib only)
# ----------------------------------------------------------------------------
class Retriever:
    def __init__(self, docs):
        self.docs = docs
        self.tf = [Counter(tok(d["title"] + " " + d["text"])) for d in docs]
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {w: math.log((n + 1) / (df[w] + 1)) + 1 for w in df}
        self.norm = [math.sqrt(sum((v * self.idf[w]) ** 2 for w, v in c.items())) for c in self.tf]

    def search(self, query, crop=None, k=3):
        q = Counter(tok(query))
        qn = math.sqrt(sum((v * self.idf.get(w, 1)) ** 2 for w, v in q.items())) or 1.0
        scored = []
        for d, c, nm in zip(self.docs, self.tf, self.norm):
            if crop and d["crop"] not in (crop, "general"):
                continue
            s = sum(v * self.idf.get(w, 1) * c[w] * self.idf[w] for w, v in q.items() if w in c) / (qn * nm)
            scored.append((s, d))
        scored.sort(key=lambda x: -x[0])
        return [dict(id=d["id"], title=d["title"], text=d["text"], source=d["source"], score=round(s, 3))
                for s, d in scored[:k] if s > 0]


RETRIEVER = Retriever(KB)


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------
def tool_farm_profile(db, farmer_id):
    row = db.execute("SELECT location, crop, area_ha FROM profiles WHERE farmer_id=?", (farmer_id,)).fetchone()
    return {"location": row[0], "crop": row[1], "area_ha": row[2]} if row else {}


def weather_fallback(location):
    month = datetime.date.today().month
    wet = 6 <= month <= 9
    return {"source": "offline seasonal estimate", "tmax": 24 if wet else 17, "tmin": 15 if wet else 5,
            "rain_mm_3d": 40.0 if wet else 2.0, "humidity": 85 if wet else 60}


def tool_get_weather(location, lat, lon):
    if os.environ.get("AGRI_OFFLINE") == "1":
        raise OSError("offline mode")
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "forecast_days": 3, "timezone": "auto",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "hourly": "relative_humidity_2m"})
    with urllib.request.urlopen(url, timeout=6) as r:
        d = json.load(r)
    hum = d["hourly"]["relative_humidity_2m"]
    return {"source": "open-meteo", "tmax": max(d["daily"]["temperature_2m_max"]),
            "tmin": min(d["daily"]["temperature_2m_min"]),
            "rain_mm_3d": round(sum(d["daily"]["precipitation_sum"]), 1), "humidity": round(sum(hum) / len(hum))}


def tool_search_knowledge(query, crop, top_k=3):
    return {"hits": RETRIEVER.search(query, crop, top_k)}


def tool_diagnose(crop, symptoms):
    toks = set(tok(symptoms))
    cands = []
    for c, name, kb_id, kws in DISEASES:
        if crop and c != crop:
            continue
        m = sum(1 for k in kws if k in toks)
        if m:
            cands.append({"name": name, "crop": c, "kb_id": kb_id, "matches": m, "confidence": round(min(1.0, m / 3), 2)})
    cands.sort(key=lambda x: -x["matches"])
    return {"candidates": cands[:2]}


def tool_fertilizer(crop, area_ha):
    if crop not in RATES:
        raise ValueError(f"no fertiliser rates for crop '{crop}'")
    if area_ha is None or area_ha <= 0:
        raise ValueError("area must be greater than 0")
    n, p, k = RATES[crop]
    dap = p / 0.46                         # DAP = 18-46-0
    urea = max(0.0, n - dap * 0.18) / 0.46  # urea = 46% N
    mop = k / 0.60                         # MOP = 60% K2O
    return {"per_ha_kg": {"urea": round(urea, 1), "dap": round(dap, 1), "mop": round(mop, 1)},
            "total_kg": {"urea": round(urea * area_ha, 1), "dap": round(dap * area_ha, 1), "mop": round(mop * area_ha, 1)},
            "area_ha": round(area_ha, 2), "schedule": SPLIT[crop],
            "note": "Illustrative rates; confirm with a soil test and your extension officer."}


TOOL_NAMES = ["farm_profile", "get_weather", "search_knowledge", "diagnose_problem", "fertilizer_calculator"]


# ----------------------------------------------------------------------------
# LLM (optional, Gemini REST via urllib)
# ----------------------------------------------------------------------------
def llm(prompt, key, timeout=20):
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]


# ----------------------------------------------------------------------------
# Agent
# ----------------------------------------------------------------------------
class AgriAgent:
    def __init__(self, farmer_id="demo", use_llm=True, mode="agent"):
        """mode='agent' = full agent; mode='baseline' = retrieval-only (no planning/guardrails) for evaluation."""
        self.farmer_id, self.mode = farmer_id, mode
        self.key = os.environ.get("GEMINI_API_KEY") if use_llm else None
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)  # Streamlit may run reruns in different threads
        self.db.execute("CREATE TABLE IF NOT EXISTS profiles(farmer_id TEXT PRIMARY KEY, location TEXT, crop TEXT, area_ha REAL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY AUTOINCREMENT, farmer_id TEXT, ts TEXT, "
                        "query TEXT, crop TEXT, intents TEXT, tools TEXT, answer TEXT, feedback INTEGER)")
        self.db.commit()

    # ---- guardrails (input) ----
    def _guard_in(self, query):
        q = query.lower()
        if re.search(r"ignore (all |any )?(previous|prior|above) instructions|system prompt|jailbreak", q):
            return "I can only help with farming questions, and I can't act on instructions that try to change my rules."
        hit = next((c for c in BANNED_CHEMICALS if c in q), None)
        if hit:
            return (f"I can't advise on {hit}: it is banned or highly restricted. Please contact your Dzongkhag agriculture "
                    "office for registered alternatives, and consider non-chemical options such as resistant varieties and crop rotation.")
        if re.search(r"(double|triple|exceed|more than|higher than).{0,25}(dose|label|rate)", q):
            return "I can't recommend exceeding the label dose; it harms crops, people and water. I can help you plan a correct, label-based spray programme instead."
        words = {w.rstrip("s") for w in re.findall(r"[a-z]+", q)}
        if not (words & AGRI_WORDS) and not any(u in q for u in UNSUPPORTED):
            return "I'm an agriculture advisory agent, so I can only help with crops, soil, pests, fertiliser and farm weather. Could you ask a farming question?"
        return None

    # ---- perception ----
    def _extract(self, query):
        q = query.lower()
        words = {w.rstrip("s") for w in re.findall(r"[a-z]+", q)}
        crop = next((c for c, syn in CROPS.items() if any(re.search(rf"\b{s}\b", q) for s in syn)), None)
        loc = next((l for l in LOCATIONS if re.search(rf"\b{l}\b", q)), None)
        m = AREA_RE.search(q)
        area = None
        if m:
            area = float(m.group(1)) * (0.4047 if m.group(2).startswith("acre") else 1.0)
        return {"crop": crop, "location": loc, "area_ha": area,
                "unsupported": next((u for u in UNSUPPORTED if u in q), None),
                "intents": {k for k, w in INTENT_WORDS.items() if words & w},
                "open_advice": bool(re.search(r"\b(what|which)\b.*\b(plant|grow)\b", q))}

    # ---- reflection (adaptation from farmer feedback) ----
    def _low_rated(self, crop, intents):
        rows = self.db.execute("SELECT intents FROM episodes WHERE farmer_id=? AND crop IS ? AND feedback<=2",
                               (self.farmer_id, crop)).fetchall()
        return sum(1 for (i,) in rows if set(i.split(",")) & set(intents))

    # ---- planning ----
    def _rule_plan(self, ctx):
        steps, it = [], ctx["intents"]
        if "weather" in it or ("disease" in it and ctx["location"]):
            steps.append("get_weather")
        if "disease" in it and ctx["crop"]:
            steps.append("diagnose_problem")
        if "fertilizer" in it:
            steps.append("fertilizer_calculator")
        if it != {"fertilizer"}:
            steps.append("search_knowledge")
        return steps

    def _llm_plan(self, query, ctx, trace):
        prompt = ("You are the planner of a farm advisory agent. Tools: get_weather (needs location), search_knowledge, "
                  "diagnose_problem (needs crop + symptoms), fertilizer_calculator (needs crop + area).\n"
                  f"Farmer query: {query}\nKnown context: crop={ctx['crop']}, location={ctx['location']}, area_ha={ctx['area_ha']}\n"
                  'Return ONLY JSON like {"steps": ["tool1", "tool2"]} using the fewest tools needed, in order.')
        try:
            raw = llm(prompt, self.key)
            steps = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["steps"]
            steps = [s for s in steps if s in TOOL_NAMES and s != "farm_profile"]
            if not steps:
                raise ValueError("empty plan")
            trace.append({"step": "planner", "detail": "llm plan " + str(steps)})
            return steps
        except Exception as e:
            trace.append({"step": "planner", "detail": f"llm planner failed ({type(e).__name__}); using rule planner"})
            return None

    # ---- execution with retry + fallback ----
    def _call(self, tool, args, trace):
        fn = {"get_weather": tool_get_weather, "search_knowledge": tool_search_knowledge,
              "diagnose_problem": tool_diagnose, "fertilizer_calculator": tool_fertilizer}[tool]
        last = None
        for attempt in (1, 2):
            t0 = time.time()
            try:
                res = fn(**args)
                trace.append({"step": tool, "detail": "ok", "ms": round((time.time() - t0) * 1000, 1)})
                return res
            except OSError as e:           # transient network error -> retry once
                last = e
                trace.append({"step": tool, "detail": f"network error attempt {attempt}: {e}", "ms": round((time.time() - t0) * 1000, 1)})
            except Exception as e:         # logic error -> no retry
                last = e
                trace.append({"step": tool, "detail": f"error: {e}", "ms": round((time.time() - t0) * 1000, 1)})
                break
        if tool == "get_weather":          # graceful degradation
            trace.append({"step": tool, "detail": "fallback: seasonal estimate"})
            return weather_fallback(args.get("location"))
        return {"error": str(last)}

    # ---- main loop ----
    def run(self, query):
        t0 = time.time()
        trace, tools_used = [], []
        flags = {"blocked": False, "needs_info": False, "escalated": False, "adapted": False}
        if self.mode == "baseline":
            res = self._call("search_knowledge", {"query": query, "crop": None, "top_k": 3}, trace)
            ans = "\n".join(f"- {h['text']} [{h['id']}]" for h in res.get("hits", [])) or "No information found."
            return self._finish(query, None, set(), ["search_knowledge"], ans, trace, flags, t0, {"search_knowledge": res})

        block = self._guard_in(query)
        if block:
            flags["blocked"] = True
            trace.append({"step": "guardrail_in", "detail": "blocked"})
            return self._finish(query, None, set(), [], block, trace, flags, t0, {})

        ctx = self._extract(query)
        prof = tool_farm_profile(self.db, self.farmer_id)
        trace.append({"step": "memory", "detail": f"profile={prof}"})
        crop = ctx["crop"] or prof.get("crop")
        loc = ctx["location"] or prof.get("location")
        area = ctx["area_ha"] if ctx["area_ha"] is not None else prof.get("area_ha")
        ctx.update(crop=crop, location=loc, area_ha=area)

        # decide whether we must ask the farmer for more information
        missing = []
        if "fertilizer" in ctx["intents"] and not crop and not ctx["unsupported"]:
            missing.append("which crop")
        if "fertilizer" in ctx["intents"] and crop and area is None:
            missing.append("the field area (acres or hectares)")
        if "weather" in ctx["intents"] and not loc:
            missing.append("your location (dzongkhag)")
        if ctx["open_advice"] and not crop:
            missing.append("your location, altitude and season of interest")
        if missing:
            flags["needs_info"] = True
            ans = "To help properly I need to know " + " and ".join(missing) + ". Could you tell me?"
            return self._finish(query, ctx, ctx["intents"], [], ans, trace, flags, t0, {})

        # plan
        steps = (self._llm_plan(query, ctx, trace) if self.key else None) or self._rule_plan(ctx)
        if ctx["unsupported"]:
            steps, flags["escalated"] = ["search_knowledge"], True
            trace.append({"step": "planner", "detail": f"unsupported crop '{ctx['unsupported']}': general advice + escalate"})
        top_k = 3
        if self._low_rated(crop, ctx["intents"]):       # reflection -> adapted behaviour
            flags["adapted"] = flags["escalated"] = True
            top_k = 5
            if "get_weather" not in steps and loc:
                steps.insert(0, "get_weather")
            if "search_knowledge" not in steps:
                steps.append("search_knowledge")
            trace.append({"step": "reflection", "detail": "earlier advice rated low: widened retrieval (top_k=5) + escalation"})
        # drop steps whose preconditions are not met
        if "diagnose_problem" in steps and not crop:
            steps.remove("diagnose_problem")
        if "get_weather" in steps and not loc:
            steps.remove("get_weather")
        if "fertilizer_calculator" in steps and not crop:
            steps.remove("fertilizer_calculator")
        trace.append({"step": "plan", "detail": steps})

        # execute
        results = {}
        for s in steps:
            if s == "get_weather":
                lat, lon = LOCATIONS[loc]
                args = {"location": loc, "lat": lat, "lon": lon}
            elif s == "search_knowledge":
                args = {"query": query, "crop": None if ctx["unsupported"] else crop, "top_k": top_k}
            elif s == "diagnose_problem":
                args = {"crop": crop, "symptoms": query}
            else:
                args = {"crop": crop, "area_ha": area}
            results[s] = self._call(s, args, trace)
            tools_used.append(s)

        # escalation on weak evidence
        hits = results.get("search_knowledge", {}).get("hits", [])
        if "search_knowledge" in results and (not hits or hits[0]["score"] < 0.12):
            flags["escalated"] = True
        diag = results.get("diagnose_problem", {}).get("candidates", [])
        if "diagnose_problem" in results and (not diag or diag[0]["confidence"] < 0.34):
            flags["escalated"] = True

        answer = self._synthesise(query, ctx, results, flags, trace)
        if crop or loc or area:  # remember farm context
            self.db.execute("INSERT INTO profiles VALUES(?,?,?,?) ON CONFLICT(farmer_id) DO UPDATE SET "
                            "location=COALESCE(excluded.location,location), crop=COALESCE(excluded.crop,crop), "
                            "area_ha=COALESCE(excluded.area_ha,area_ha)", (self.farmer_id, loc, crop, area))
        return self._finish(query, ctx, ctx["intents"], tools_used, answer, trace, flags, t0, results)

    # ---- synthesis + output guardrails ----
    def _template(self, ctx, results, flags):
        L = []
        where = f" in {ctx['location'].title()}" if ctx["location"] else ""
        L.append(f"Advice for {ctx['crop'] or 'your farm'}{where}:")
        w = results.get("get_weather")
        if w:
            rain = w["rain_mm_3d"]
            L.append(f"- Weather (next 3 days, {w['source']}): max {w['tmax']}C, min {w['tmin']}C, rain {rain} mm, humidity {w['humidity']}%.")
            L.append("- Rain is likely: delay any spraying until you have a dry window of at least 24 hours." if rain >= 5
                     else "- Little rain expected: spraying is feasible in calm conditions, early morning or evening.")
            if w["humidity"] >= 80:
                L.append("- High humidity raises fungal disease risk, so scout your field more often.")
            if "estimate" in w["source"]:
                L.append("- (Live forecast unavailable, so this is an offline estimate. Please check a local forecast.)")
        d = results.get("diagnose_problem", {}).get("candidates")
        if d:
            L.append("- Likely problem: " + "; ".join(f"{c['name']} (confidence {c['confidence']})" for c in d) + ".")
        f = results.get("fertilizer_calculator")
        if f and "error" not in f:
            t = f["total_kg"]
            L.append(f"- Fertiliser for {f['area_ha']} ha: urea {t['urea']} kg, DAP {t['dap']} kg, MOP {t['mop']} kg. {f['schedule']} ({f['note']})")
        elif f:
            L.append(f"- Could not calculate fertiliser: {f['error']}. Please check the crop and field area.")
        for h in results.get("search_knowledge", {}).get("hits", [])[:3 if not flags["adapted"] else 5]:
            L.append(f"- {h['text']} [{h['id']}]")
        if ctx and ctx.get("unsupported"):
            L.append(f"- I don't have verified guidance for {ctx['unsupported']}; the general advice above is limited.")
        if flags["adapted"]:
            L.append("- Earlier advice on this crop was rated poorly, so I searched more widely this time.")
        if flags["escalated"]:
            L.append("- Confidence is limited here: please confirm with your Dzongkhag agriculture / extension officer before applying any chemical.")
        return "\n".join(L)

    def _synthesise(self, query, ctx, results, flags, trace):
        template = self._template(ctx, results, flags)
        if not self.key:
            return template
        try:
            prompt = ("You are a careful agriculture advisor. Using ONLY the evidence below, write a short, practical answer for a smallholder "
                      "farmer. Cite knowledge entries as [id]. Do not invent doses or products.\n"
                      f"Question: {query}\nEvidence:\n{template}")
            ans = llm(prompt, self.key)
            has_kb = bool(results.get("search_knowledge", {}).get("hits"))
            if has_kb and not re.search(r"\[[a-z\-]+\]", ans):  # grounding guardrail
                trace.append({"step": "guardrail_out", "detail": "llm answer lacked citations; using template"})
                return template
            return ans
        except Exception as e:
            trace.append({"step": "synthesis", "detail": f"llm failed ({type(e).__name__}); using template"})
            return template

    def _finish(self, query, ctx, intents, tools_used, answer, trace, flags, t0, results):
        cur = self.db.execute("INSERT INTO episodes(farmer_id, ts, query, crop, intents, tools, answer) VALUES(?,?,?,?,?,?,?)",
                              (self.farmer_id, datetime.datetime.now().isoformat(timespec="seconds"), query,
                               ctx["crop"] if ctx else None, ",".join(sorted(intents)), ",".join(tools_used), answer))
        self.db.commit()
        return {"episode_id": cur.lastrowid, "answer": answer, "tools_used": tools_used, "flags": flags, "trace": trace,
                "results": results, "latency_s": round(time.time() - t0, 3)}

    def feedback(self, episode_id, score):
        """score 1 (bad) to 5 (good). Low scores change the next plan for the same crop/intent."""
        self.db.execute("UPDATE episodes SET feedback=? WHERE id=?", (int(score), episode_id))
        self.db.commit()


# ============================ Web UI ============================

try:  # Streamlit Cloud: put GEMINI_API_KEY in the app's Secrets (optional)
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass


st.set_page_config(page_title="AgriAdvisor", page_icon="🌾", layout="centered")
st.title("🌾 AgriAdvisor")
st.caption("AI agriculture advisory agent for paddy, maize, potato and apple. "
           "Advice is general guidance: confirm with your local extension officer before applying chemicals.")

if "farmer_id" not in st.session_state:
    st.session_state.farmer_id = "web-" + uuid.uuid4().hex[:8]
    st.session_state.messages = []
    st.session_state.agent = AgriAgent(farmer_id=st.session_state.farmer_id)
agent = st.session_state.agent

with st.sidebar:
    st.subheader("About")
    st.write("Plans tool use (weather, knowledge search, diagnosis, fertiliser calculator), "
             "remembers your farm during the session, and adapts when you rate answers poorly.")
    st.write("LLM: **%s**" % ("Gemini" if agent.key else "offline rules"))
    show_trace = st.toggle("Show agent trace", value=False)
    st.subheader("Try an example")
    examples = ["How much fertiliser for 2 acres of maize?",
                "My potato leaves in Bumthang have dark water-soaked spots with white fuzz, should I spray?",
                "Is it a good day to spray my potatoes in Paro?",
                "Fertilizer for my crop",
                "How much paraquat should I spray on my potato?"]
    clicked = None
    for i, ex in enumerate(examples):
        if st.button(ex, key=f"ex{i}", use_container_width=True):
            clicked = ex
    st.caption("Known places: " + ", ".join(p.title() for p in LOCATIONS))

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            st.caption(f"Tools used: {', '.join(m['tools']) or 'none'}")
            if show_trace:
                with st.expander("Agent trace"):
                    st.json(m["trace"])
            if m.get("rateable"):
                val = st.feedback("stars", key=f"fb{i}")
                if val is not None and not m.get("rated"):
                    agent.feedback(m["episode_id"], val + 1)
                    m["rated"] = True
                    st.caption("Thanks. Your rating helps the agent adapt.")

prompt = st.chat_input("Ask a farming question...") or clicked
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.spinner("Thinking..."):
        r = agent.run(prompt)
    st.session_state.messages.append({
        "role": "assistant", "content": r["answer"], "tools": r["tools_used"], "trace": r["trace"],
        "episode_id": r["episode_id"],
        "rateable": not (r["flags"]["blocked"] or r["flags"]["needs_info"])})
    st.rerun()
