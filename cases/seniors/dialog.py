"""Jsem v pořádku: how a senior's answer to the check-in call is understood and what the assistant may say.

Intents → journey events:
  ok (also a chronic / mild health note: extra health_note) → ok | need_items → needs_help | low_mood → low_mood |
  health_problem (new or worsening) → escalated | emergency (fall, cannot breathe, chest pain, fire, gas) → escalated |
  crisis (does not want to live) → emergency → escalated, a warm sentence and a person at once |
  pause (hospital, at the daughter's, spa) → paused | schedule_change (less often, rather in the afternoon) → ok, the
  wish is stored | human (wants a person, not a robot) → escalate → escalated | callback → callback |
  opt_out (only an explicit wish to end the service, confirmed in the recap) → declined | question / unclear → callback.

Safety first: in an emergency the assistant keeps the line open ("zůstaňte na telefonu, nezavěšujte") and hands over to
a worker who calls 155 (or 150 / 112 for fire, smoke or gas). Never "zavěste a volejte 155" to a person who may be on
the floor. The assistant never gives medical advice. Anything not clearly understood goes to a person."""
import json
import re
import unicodedata
from pathlib import Path

INTENTS = ["ok", "need_items", "low_mood", "health_problem", "emergency", "crisis", "pause", "schedule_change", "human",
           "callback", "opt_out", "question", "unclear"]

# Reply intents → journey events (question / unclear: the operator calls back).
INTENT_EVENT = {"ok": "ok", "need_items": "need_items", "low_mood": "low_mood", "health_problem": "health_problem",
                "emergency": "emergency", "crisis": "emergency", "pause": "pause", "schedule_change": "ok",
                "human": "escalate", "callback": "callback", "opt_out": "opt_out", "question": "callback",
                "unclear": "callback"}

# Journey stage for each intent.
STAGE = {"ok": "ok", "need_items": "needs_help", "low_mood": "low_mood", "health_problem": "escalated",
         "emergency": "escalated", "crisis": "escalated", "pause": "paused", "schedule_change": "ok", "human": "escalated",
         "callback": "callback", "opt_out": "declined", "question": "callback", "unclear": "callback"}

# Vocabulary (shared with the web app: items.json is served as /app/content/items.json).
VOCAB = json.loads(Path(__file__).with_name("items.json").read_text(encoding="utf-8"))
ITEMS = VOCAB["items"]  # key → {label, patterns}
_ITEM_RE = {k: [re.compile(p) for p in v["patterns"]] for k, v in ITEMS.items()}
MOOD = sorted((int(k), v) for k, v in VOCAB["mood"].items())          # 1 (very bad) … 5 (very good), the lowest match wins
MOOD_DELTA = sorted((int(k), v) for k, v in VOCAB["mood_delta"].items())  # "spíš hůř než obvykle" → -1 / 0 / +1
HEALTH = VOCAB["health"]              # any mention of the senior's own health
HEALTH_ACUTE = VOCAB["health_acute"]  # new or worsening → health_problem
COMPANY_ITEMS = ("navsteva", "spolecnost")  # wishes that are a mood, not a basket need, in the reply rules

# A fall is an emergency unless the senior reassures us in the same breath ("ale nic vážného", "už je to dobré").
_REASSURED = r"(?!.*(nic vazn|nic (mi )?nen[ie]|nic se (mi )?nestalo|uz (je to|jsem) (dobr|v poradku|lepsi|zase)|ale (uz )?jsem v poradku|uz je to dobre))"
# "nevolejte" alone or with "už / vůbec / nikdy" ends the service; with a time or a frequency it is a schedule wish.
_NOT_SCHEDULE = r"(?! ?(mi |nam )?(prosim )?(tak casto|tak brzo|rano|dopoledne|odpoledne|vecer|v poledne|po obede|pred (devatou|desatou|obedem)|po (osme|sedme|sesti)|v (pondeli|utery|stredu|ctvrtek|patek|sobotu|nedeli)|o vikendu|kazdy den|denne))"

EMERGENCY_FIRE = [r"\bhori\b", r"\bpozar", r"\bkour\b", r"\bkoure\b", r"citim (tu )?(kour|plyn)", r"(unika|uchazi) (mi |nam |tu )?plyn",
                  r"smrdi (tu |mi )?plyn", r"zapach plynu", r"je tu plyn", r"\b(150|112)\b"]
EMERGENCY_BODY = [r"\b155\b", r"(zavolejte|zavolat|potrebuj[iu]|chci|prosim)( mi| hned| rychle)* (sanitku|zachranku|zachrannou|zachranare|doktora hned)",
                  r"nemuzu (vstat|vstavat|dychat|se zvednout|se hnout|se nadechnout|popadnout dech|se postavit|se hybat)",
                  r"nemohu (vstat|dychat|se zvednout|se hnout)", r"nejde mi dychat", r"lezim na (zemi|podlaze)", r"jsem na zemi",
                  r"\b(u|s)padl[a]? jsem" + _REASSURED, r"\b(u|s)padl[a]? jsem a", r"bolest na hrudi", r"boli me na hrudi",
                  r"svira me (na )?hrudi", r"tlak na hrudi", r"\bkrvacim", r"hodne krve", r"omdlel", r"omdlivam",
                  r"zlomil[a]? jsem si", r"mam zlomen", r"^\s*pomoc\s*[.!]*\s*$", r"pomozte( mi)?( rychle| hned| prosim)",
                  r"pomoc,? (rychle|hned)"]
CRISIS = [r"nechce se mi (uz )?zit", r"nechce (se mi )?(uz )?zit", r"(uz )?to nema (cenu|smysl)", r"chci umrit", r"chtel[a]? bych umrit",
          r"radeji bych (umrel|umrela|nebyl|nebyla|tu nebyl|tu nebyla)", r"skoncit se zivotem", r"skoncit to", r"zabit se",
          r"vzit si zivot", r"nechci (uz )?(tu )?(byt|zit)", r"nema smysl (dal )?zit", r"kdybych tu nebyl", r"uz nemuzu dal"]

# (intent, patterns) in priority order, first match wins. Patterns run on lower-case ASCII text (no diacritics).
# Order: crisis > emergency > opt_out > human > pause > schedule_change > callback > need_items > health_problem > low_mood > ok.
RULES = [
    ("crisis", CRISIS),
    ("emergency", EMERGENCY_FIRE + EMERGENCY_BODY),
    ("opt_out", [r"\bstop\b", r"\bnevolejte\b" + _NOT_SCHEDULE, r"\bodhlas", r"nekontaktuj", r"neobtezujte", r"nechci (uz )?(zadne )?(dalsi )?hovory",
                 r"nechci,? ?abyste (mi )?(uz )?volal", r"zruste (to|mi to|tu sluzbu|sluzbu|hovory|ty hovory)", r"ukoncit (tu )?(sluzbu|to)",
                 r"uz (mi )?(to )?(prosim )?nevolejte", r"(uz )?(o to|o tu sluzbu|o hovory) (nemam zajem|nestojim)", r"zrusit (to|sluzbu|hovory)"]),
    ("human", [r"nechci (s |se )?(robotem|automatem|strojem|pocitacem|zadnym robotem) ?(mluvit|bavit)?", r"(s|se) (robotem|automatem|strojem) (mluvit |se bavit )?nechci",
               r"chci (mluvit|hovorit|se bavit) s (clovekem|nekym|pani|panem|pracovni|zivym|skutecnym|opravdovym)", r"chtel[a]? bych (mluvit|hovorit) s (clovekem|nekym|pani|panem|pracovni)",
               r"dejte mi (pani|pana|nekoho|cloveka|pracovni)", r"prepojte (me|mne)", r"(zivy|zivého|skutecny|skutecneho|opravdovy|opravdoveho|normalni|normalniho) (clovek|cloveka)",
               r"nejste clovek", r"at mi zavola (pani|pan|pracovni|nekdo)", r"radeji (s )?clovek", r"zadny robot"]),
    ("pause", [r"(?<!byl )(?<!byla )\bjsem (ted |zrovna |ted zrovna |momentalne )?(v nemocnici|v laznich|v lazn|na rehabilitaci|na lecen|v leceb|na operaci|po operaci v nemocnici)",
               r"(?<!byl )(?<!byla )\bjsem (ted |zrovna |ted zrovna )?u (dcery|syna|vnuka|vnucky|sestry|bratra|rodiny|deti|znamych|pritelkyne|kamaradky)",
               r"(?<!byl )(?<!byla )\bjsem (ted |zrovna )?(na chate|na chalupe|mimo domov|pryc|na dovolene|na vylete|na navsteve)",
               r"lezim v nemocnici", r"(jedu|jedeme|odjizdim|pojedu|odjedu) (do lazni|k dceri|k synovi|na chatu|na chalupu|pryc|do nemocnice|na dovolenou|k rodine|na navstevu|k vnuck|k vnuk)",
               r"budu (v nemocnici|pryc|u dcery|u syna|v laznich|na chate|na chalupe|mimo)", r"(odvezou|odvezli|vezmou si) me (do nemocnice|k sobe|do lazni)",
               r"jdu do nemocnice", r"nastupuji do nemocnice", r"do nemocnice (zitra|v pondeli|v utery|ve stredu|ve ctvrtek|v patek|pristi tyden)",
               r"(zatim|ted|nejaky cas|chvili|par dni|tyden|dva tydny|mesic) (mi )?nevolejte(?! vubec)", r"nevolejte (mi )?(zatim|ted|par dni|tyden|dva tydny|do nedele|do pondeli|do konce)",
               r"pozastav", r"prerus(it|te) (to|hovory)"]),
    ("schedule_change", [r"staci (mi )?(jednou|dvakrat|trikrat) (tydne|za tyden|za (dva|14) dn|mesicne|za mesic)", r"\b(jednou|dvakrat|trikrat) (tydne|za tyden|za mesic|mesicne)\b",
                         r"ne tak casto", r"(min|mene|meně) casto", r"tak casto (ne|nemusite)", r"nemusite (volat )?(kazdy den|denne|tak casto|porad)",
                         r"(volejte|zavolejte|volat|volejte mi) (mi |me )?(radeji|radsi|spis|spise|jen|pouze|vzdycky|vzdy)\b",
                         r"(radeji|radsi|spis|spise|lepsi|lepe) (mi )?(volejte|volat|zavolejte|volani) ?(mi )?(odpoledne|dopoledne|vecer|rano|po obede|v (pondeli|utery|stredu|ctvrtek|patek|sobotu|nedeli)|o vikendu|az po|pred)?",
                         r"\bnevolejte (mi |nam )?(prosim )?(tak casto|tak brzo|rano|dopoledne|odpoledne|vecer|v poledne|po obede|pred (devatou|desatou|obedem)|po (osme|sedme|sesti)|v (pondeli|utery|stredu|ctvrtek|patek|sobotu|nedeli)|o vikendu|kazdy den|denne)",
                         r"(rano|dopoledne|odpoledne|vecer|v poledne|po obede) (mi )?(to )?(nevyhovuje|se mi nehodi|nejsem doma|spim|je spatne)",
                         r"(hodilo|hodi) by se mi (spis|radeji|vic|lepe)? ?(odpoledne|dopoledne|vecer|rano|po obede)", r"casteji", r"kazdy den (mi )?(klidne )?volejte",
                         r"(vyhovuje|vyhovovalo) by mi (vic|spis|lepe)? ?(odpoledne|dopoledne|vecer|rano)", r"zmenit (cas|den|rozvrh|hovory)",
                         r"jiny (cas|den)", r"jinou (dobu|hodinu)"]),
    ("callback", [r"ted nemuzu", r"ted nemohu", r"ted se (mi )?to nehodi", r"nehodi se (mi )?(to )?(ted|teď|zrovna)", r"zavolejte (mi )?(pozdeji|zitra|za hodinu|za chvili|vecer|jindy|za)\b",
                  r"zavolejte (mi )?(odpoledne|dopoledne|rano)(?! radeji| radsi| spis)", r"volejte (az|pozdeji)", r"\bpozdeji\b", r"jsem u (lekare|doktora|doktorky|lekarky)",
                  r"nemam ted cas", r"ted nemam cas", r"mam (tu )?navstevu", r"zrovna (mam navstevu|obedvam|varim|nekoho mam)", r"zavolam (vam )?(sam|sama|pozdeji|zpet)"]),
    ("need_items", [r"^\s*2\s*$", r"\bpotreb(uji|uju|ovala bych|oval bych|ovala|oval)\b", r"dosl[ay]? mi", r"dosel mi", r"\bpomoc (s|se) ", r"\bpomoct (s|se) ",
                    r"pomohl[a]? by mi", r"pomohl[a]? byste (mi )?(s|se) ", r"kdyby (mi )?nekdo (pomohl|zasel|zaridil|donesl|nakoupil|zavolal)",
                    r"zarid(it|ila|il) (bych|byste)", r"shanim", r"nemuzu (si )?(dojit|dojet|zajit|sehnat|zaridit|zvednout|vyprat|uvarit|nakoupit)",
                    r"nikdo mi (nenakoupi|neuvari|nedonese|nezajde|nevypere)", r"nedostanu se (k|na|do) "]
     + [p for k in ITEMS for p in ITEMS[k]["patterns"] if k not in COMPANY_ITEMS]),
    ("health_problem", HEALTH_ACUTE),
    ("low_mood", [r"smutn", r"smutno", r"osamel", r"\bsam[a]? doma", r"porad (jsem )?sam[a]?\b", r"jsem (tu |tady )?(porad |uplne |jen )?sam[a]?\b", r"nikdo (mi|me|za mnou|se)\b",
                  r"nikoho nemam", r"nema to smysl", r"nechce se mi\b", r"spatn(a|ou) nalad", r"stysk", r"brecim", r"placu", r"deprese", r"depres",
                  r"nemam (na nic )?silu", r"nic me nebavi", r"je mi tezko", r"\bnavstev", r"popovidat", r"spolecnost", r"promluvit si s nekym",
                  r"chybi mi", r"(zemrel|zemrela|umrel|umrela|odesel|odesla) (mi|nam)\b", r"\bpohreb", r"ovdovel", r"\btruchl",
                  r"\b(dcera|syn|deti|vnuk|vnucka|vnoucata|rodina|sestra|bratr|sousedka|soused|nikdo) (mi |me |se |za mnou )?(nevola|nechodi|nepise|neozyv|neozve|neprijde|nenavstev|nezavola|nejezdi|neprijede|nema cas|zapomnel|zapomnela|nestoji)",
                  r"\bna nikom nezalezi", r"nikomu (na mne |na me )?nezalezi", r"\bje mi (smutno|uzko|tezko|zle u srdce)", r"bez nalady", r"nemam naladu", r"mizern", r"\bbidne\b",
                  r"\bspatne\b(?! se mi dycha)", r"\bhur\b", r"\bhure\b", r"hrozne\b", r"strasne\b"]),
    ("ok", [r"^\s*1\s*$", r"v poradku", r"\bdobre\b", r"\bdobry\b", r"\bfajn\b", r"\bok\b", r"\bjo\b", r"\bjojo\b", r"nic nepotrebuj", r"\bano\b", r"jde to",
            r"ujde to", r"vyborn", r"skvel", r"da se to", r"\bcajk", r"nic noveho", r"jak kdy", r"nic mi neni", r"nic mi nechybi", r"vsechno pri starem", r"\bpri starem\b",
            r"jako vzdycky", r"jako obvykle", r"jako jindy", r"porad stejne", r"\bcelkem\b", r"spokojen", r"\bdiky\b", r"\bdekuji\b", r"\bdekuju\b",
            r"nic moc", r"\bnapul\b", r"unaven", r"\btak nejak\b", r"zvladam", r"\bzije se\b", r"\bdrzim se\b", r"uz jsem (zase )?doma", r"jsem zase doma"]
     + HEALTH),  # a health word alone (bolí kolena, záda, jako vždycky): a note on the card, the call goes on
]
QUESTION = re.compile(r"\?|\b(kdo jste|kdo vola|odkud|proc|kolik|kdy zase|jak dlouho|co jste zac|jste robot|mluvim s robotem)\b")
WHY = {"question": "dotaz seniora", "unclear": "odpovědi nerozumíme, předáno operátorovi"}
# scripted (gather) call: after these intents nothing more is asked and no recap is said (backend/app.py VOICE_FINAL)
VOICE_FINAL = {"emergency", "crisis", "callback", "question", "unclear", "health_problem"}

# Schedule wishes: normalized phrase → what the recap and the card say.
SCHEDULE = [
    (r"(jednou|1x) (tydne|za tyden)", "jednou týdně"), (r"(dvakrat|2x) (tydne|za tyden)", "dvakrát týdně"), (r"(trikrat|3x) (tydne|za tyden)", "třikrát týdně"),
    (r"(jednou|1x) (mesicne|za mesic)", "jednou měsíčně"), (r"ne tak casto|min casto|mene casto|tak casto ne|nemusite (volat )?(kazdy den|denne|tak casto|porad)", "méně často"),
    (r"tak casto", "méně často"), (r"casteji|kazdy den", "častěji"), (r"odpoledne", "raději odpoledne"), (r"dopoledne", "raději dopoledne"), (r"\bvecer", "raději večer"),
    (r"\brano\b", "raději ráno"), (r"po obede", "raději po obědě"), (r"o vikendu", "raději o víkendu"),
    (r"v (pondeli|utery|stredu|ctvrtek|patek|sobotu|nedeli)", None),  # the day word is taken from the text
]
_DAYS = {"pondeli": "v pondělí", "utery": "v úterý", "stredu": "ve středu", "ctvrtek": "ve čtvrtek", "patek": "v pátek", "sobotu": "v sobotu", "nedeli": "v neděli"}
# Until when the calls pause ("do neděle", "do konce týdne", "na čtrnáct dní"): the phrase is kept as the senior said it.
_UNTIL = re.compile(r"\b(do|az do|na|pres|asi na|tak na) ((konce |pristiho |pristi |tohoto |toho )?(nedele|pondeli|utery|stredy|ctvrtka|patku|soboty|tydne|mesice|vikendu|svatku|vanoc|velikonoc)"
                    r"|(\d+|par|nekolik|dva|tri|ctyri|pet|sest|sedm|deset|ctrnact|tyden|dva tydny|tri tydny|mesic|dva mesice)( dni| dnu| tydny| tydnu| mesice| mesicu)?)\b")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def items_of(text: str) -> list:
    """Item keys (items.json) named in a free text, in vocabulary order."""
    t = norm(text)
    return [k for k, pats in _ITEM_RE.items() if any(p.search(t) for p in pats)]


def mood_of(text: str):
    """Absolute mood 1–5 from mood words (the lowest match wins). None when only a relative answer was given."""
    t = norm(text)
    if mood_delta_of(text) is not None:
        return None
    found = [m for m, pats in MOOD if any(re.search(p, t) for p in pats)]
    return min(found) if found else None


def mood_delta_of(text: str):
    """-1 / 0 / +1 when the senior compares with usual ("spíš hůř než obvykle", "jako vždycky", "už je to lepší")."""
    t = norm(text)
    found = [d for d, pats in MOOD_DELTA if any(re.search(p, t) for p in pats)]
    return min(found) if found else None


_FIRST_PERSON = re.compile(r"\b(mi|me|mne|jsem|mam|nemam|nemuzu|nemohu|moje|moji|muj|ma)\b")


def emergency_kind(text: str):
    """fire (hoří, kouř, plyn) | medical | None."""
    t = norm(text)
    if any(re.search(p, t) for p in EMERGENCY_FIRE):
        return "fire"
    if any(re.search(p, t) for p in EMERGENCY_BODY):
        return "medical"
    return None


def schedule_of(text: str):
    t = norm(text)
    for pat, label in SCHEDULE:
        m = re.search(pat, t)
        if m:
            return label or _DAYS.get(m.group(1), m.group(0))
    return None


def until_of(text: str):
    """The 'until when' phrase of a pause, as said (with diacritics when possible), e.g. 'do neděle'."""
    m = _UNTIL.search(norm(text))
    if not m:
        return None
    # take the same span from the original text so diacritics survive (lengths are equal: NFKD only drops marks)
    raw = re.sub(r"\s+", " ", text or "").strip()
    plain = norm(raw)
    if len(plain) == len(raw):
        return raw[m.start():m.end()]
    return m.group(0)


def extract(text: str) -> dict:
    """Deterministic fields from a reply: mood 1–5 or mood_delta -1/0/+1, items [keys of items.json], health_flag
    (any own health mention), health_note (mild / chronic, no acute marker), health_acute, emergency_kind,
    pause_until, schedule. {} = nothing found."""
    if not text or not text.strip():
        return {}
    t = norm(text)
    out = {}
    delta = mood_delta_of(text)
    if delta is not None:
        out["mood_delta"] = delta
    else:
        mood = mood_of(text)
        if mood:
            out["mood"] = mood
    items = items_of(text)
    if items:
        out["items"] = items
    acute = any(re.search(p, t) for p in HEALTH_ACUTE) or any(re.search(p, t) for p in EMERGENCY_BODY)
    health = acute or any(re.search(p, t) for p in HEALTH)
    if health and "pet" in items and not _FIRST_PERSON.search(t):
        health = acute = False  # "pes je nemocný, potřebuje k veterináři": the animal, not the senior
    if health:
        out["health_flag"] = True
        if acute:
            out["health_acute"] = True
        else:
            out["health_note"] = True
    kind = emergency_kind(text)
    if kind:
        out["emergency_kind"] = kind
    sched = schedule_of(text)
    if sched:
        out["schedule"] = sched
    until = until_of(text)
    if until:
        out["pause_until"] = until
    return out


LLM_USER = "Odpověď seniora: «{text}»"
LLM_SYSTEM = """Jsi asistent pečovatelské služby. Osamělému seniorovi pravidelně voláme, abychom věděli, že je v pořádku,
jak se cítí a zda něco nepotřebuje. Senior odpověděl. Urči, co odpověď znamená.

Vrať POUZE JSON: {"intent": "...", "when": "...", "confidence": "high|low", "why": "...", "extra": {"mood": 1-5 nebo null, "mood_delta": -1|0|1 nebo null, "items": [...], "health_note": true|false, "pause_until": "...", "schedule": "..."}}
intent:
- ok: je v pořádku, nic nepotřebuje; sem patří i dlouhodobá nebo mírná potíž ("bolí mě kolena", "jen ta záda", "jako vždycky"), pak extra.health_note = true
- need_items: potřebuje praktickou pomoc (nákup, léky z lékárny, obědy, dopravu, doprovod, úklid, topení, prádlo, opravu, peníze, úřad a dopisy, zvíře, hygienu, pomůcky)
- low_mood: je smutný, osamělý, truchlí, bez nálady, chybí mu společnost
- health_problem: nová nebo zhoršená zdravotní potíž (od včera, teplota, zvracení, je mu hůř, upadl ale nic vážného), bez akutního ohrožení
- emergency: akutní ohrožení života nebo zdraví (leží na zemi a nemůže vstát, nemůže dýchat, bolest na hrudi, krvácí, hoří, cítí plyn)
- crisis: mluví o tom, že nechce žít, že to nemá cenu, chce umřít
- pause: na čas není doma nebo nemůže přijímat hovory (nemocnice, lázně, u dcery do neděle); extra.pause_until = do kdy, pokud řekl
- schedule_change: chce volat jindy nebo méně často ("stačí jednou týdně", "volejte raději odpoledne"), ale službu chce dál; extra.schedule = přání
- human: nechce mluvit s robotem, chce člověka nebo konkrétní pracovnici
- callback: teď nemůže mluvit, chce zavolat později
- opt_out: výslovně chce službu ukončit, žádné další hovory ("už mi nevolejte", "zrušte to")
- question: ptá se na něco (kdo volá, proč, kolik to stojí)
- unclear: nedá se poznat
when: časový údaj, pokud nějaký je (např. "odpoledne", "zítra"), jinak "".
extra.mood: nálada 1 (velmi špatná) až 5 (výborná): výborně 5, dobře 4, ujde to / jak kdy / nic moc 3, špatně / smutno 2, hrozně 1; null když se nedá poznat.
extra.mood_delta: když srovnává s obvyklým stavem: spíš hůř než obvykle -1, jako vždycky 0, spíš lépe 1; jinak null.
extra.items: seznam klíčů z: nakup, leky, obed, doprava, doprovod, uklid, otop, pradlo, oprava, finance, urad, pet, hygiena, pomucky, navsteva, spolecnost, jine. Prázdný seznam, když nic.
why: jedna krátká česká věta pro sociálního pracovníka.
Při jakékoli známce ohrožení zvol emergency, při řeči o nechuti žít crisis. Při pochybnosti zvol unclear, odpověď pak vyřeší člověk. Nikdy neradíš zdravotně."""

# ---------- phone call: only these approved sentences are ever said (relay: backend/voice_ai.py; agent: agent_prompt) ----------
# The agent's first message is a constant (no placeholders reach ElevenLabs); the identity check is its only question.
# The scripted (gather) call uses messages.cs.json voice.CHECKIN with {name} and {worker}.
GREETING = ("Dobrý den, tady pečovatelská služba, pravidelný hovor, který Vám domluvila Vaše sociální pracovnice. "
            "Jsem automatická asistentka. Můžu se zeptat, s kým mluvím?")
ASK_AGAIN = "Jak se dnes cítíte?"
ASK_MOOD_2 = "Spíš dobře, nebo spíš hůř než obvykle?"
ASK_NEEDS = "Potřebujete dnes s něčím pomoct?"
ASK_WHAT = "Co přesně potřebujete? Nákup, léky z lékárny, obědy, dopravu, nebo něco jiného?"
ASK_UNTIL = "Do kdy Vám nemáme volat?"
ASK_SCHEDULE = "Kdy nebo jak často Vám máme volat?"
# did not understand: slower and louder, with the keys; after MAX_UNCLEAR a person takes over (never a switch to SMS)
NOT_UNDERSTOOD = ("Promiňte, špatně jsem Vám rozuměla, zkusím to pomaleji. Stiskněte prosím jedničku, když je u Vás všechno v pořádku, "
                  "nebo dvojku, když něco potřebujete.")
MAX_UNCLEAR = 2
WRONG_PERSON = "Omlouvám se, voláme někomu jinému. Děkuji Vám a na shledanou."

FAQ = [
    (("kdo jste", "kdo vola", "odkud", "kdo to je", "co jste zac"), "Volám z pečovatelské služby, pravidelný hovor Vám domluvila Vaše sociální pracovnice. Jsem automatická asistentka."),
    (("robot", "automat", "stroj", "nahravk"), "Ano, jsem automatická asistentka pečovatelské služby. Kdykoli řeknete, předám Vás pracovnici."),
    (("kolik", "stoji", "plati", "zdarma", "penize za"), "Hovory jsou pro Vás zdarma."),
    (("proc", "k cemu"), "Voláme pravidelně, abychom věděli, že jste v pořádku a jestli něco nepotřebujete."),
    (("kdy zase", "pristi", "zase zavolate"), "Zavolám Vám znovu podle domluveného rozvrhu, obvykle v tu samou dobu."),
]

# Emergency: the line stays open, a worker calls the rescue service. Never "zavěste".
EMERGENCY = "Zůstaňte prosím na telefonu, nezavěšujte. Předávám Vás pracovnici, která Vám zavolá záchrannou službu."
EMERGENCY_FIRE_SAY = ("Zůstaňte prosím na telefonu, nezavěšujte. Předávám Vás pracovnici, která hned volá hasiče a záchranáře na linky 150 a 112. "
                      "Pokud můžete, jděte ke dveřím nebo ven.")
CRISIS_SAY = ("To mě moc mrzí, že je Vám tak těžko. Nejste na to sami. Zůstaňte prosím na telefonu, hned Vás předávám pracovnici, "
              "která si s Vámi promluví.")
CRISIS_LINES = "Linka seniorů 800 200 007 a Senior telefon 800 157 157, zdarma, kdykoli ve dne i v noci."
# intent → closing sentence; "handoff" = a person takes over. No placeholders: the relay and the agent say them as they are.
CLOSING = {
    "ok": "To ráda slyším. Děkuji Vám a zavolám zase příště, podle naší domluvy. Mějte se hezky, na shledanou.",
    "need_items": "Děkuji. Předám to pečovatelské službě a ozveme se Vám. Mějte se hezky, na shledanou.",
    "low_mood": "Děkuji, že jste mi to řekli. Brzy se Vám ozve někdo z naší služby. Držte se, na shledanou.",
    "health_problem": "Děkuji, že jste mi to řekli. Předám to pracovnici, která se Vám dnes ozve. Na shledanou.",
    "emergency": EMERGENCY,
    "crisis": CRISIS_SAY,
    "pause": "Rozumím, zatím Vám volat nebudeme a pak se zase ozveme. Přeji brzké uzdravení a hezké dny, na shledanou.",
    "schedule_change": "Dobře, poznamenám si to a pracovnice Vám hovory přenastaví. Děkuji Vám, na shledanou.",
    "human": "Rozumím. Předám Vás pracovnici naší služby, která se Vám hned ozve. Děkuji Vám, na shledanou.",
    "callback": "Dobře, zavolám Vám později. Na shledanou.",
    "opt_out": "Rozumím, další hovory Vám volat nebudeme. Kdybyste si to rozmysleli, stačí říct Vaší sociální pracovnici. Na shledanou.",
    "handoff": "Děkuji. Předám to pracovnici naší služby, která se Vám ozve. Na shledanou.",
}
DTMF = {"1": "v pořádku", "2": "potřebuji pomoc"}  # keys in a call → words for the reply rules

# ---------- ElevenLabs voice agent (backend/agent_call.py, scripts/elevenlabs_agent.py) ----------
DECISIONS = {"ok", "need_items", "low_mood", "health_problem", "emergency", "crisis", "pause", "schedule_change", "human",
             "callback", "opt_out", "unclear"}
AGENT_NAME = "Pečovatelská služba, pravidelný hovor se seniorem"
# Voice for seniors: slower; a Czech-native female voice from the ElevenLabs library (Hana - Feminine and Reassuring,
# cs, middle-aged, calm). The voice must be in the account's library before the agent is updated
# (POST /v1/voices/add/5fa0bbb2c8817659d8e1cd94ba0bbc81b66db4611d5e92d1d1e039a92fd58ef9/2qbJHyAaz7tHCfVZS6z3);
# scripts/elevenlabs_agent.py merges this over its default tts settings.
AGENT_TTS = {"speed": 0.9}  # a Czech voice (e.g. "Hana" 2qbJHyAaz7tHCfVZS6z3) once it is added to the ElevenLabs library: "voice_id": "..."
AGENT_DECISIONS = {
    "ok": "je v pořádku a nic nepotřebuje (i s dlouhodobou mírnou potíží, pak health_note = ano)",
    "need_items": "potřebuje praktickou pomoc (nákup, léky, obědy, dopravu, doprovod, úklid, topení, prádlo, opravu, peníze, úřad, zvíře, hygienu, pomůcky)",
    "low_mood": "je smutný, osamělý nebo truchlí, chce, aby se někdo ozval",
    "health_problem": "nová nebo zhoršená zdravotní potíž bez akutního ohrožení (od včera, teplota, zvracení, je mu hůř, upadl ale nic vážného)",
    "emergency": "akutní ohrožení (leží na zemi, nemůže vstát, nemůže dýchat, bolest na hrudi, krvácí, hoří, cítí plyn)",
    "crisis": "mluví o tom, že nechce žít nebo že to nemá cenu",
    "pause": "na čas není doma nebo nemůže přijímat hovory (nemocnice, lázně, u rodiny)",
    "schedule_change": "chce volat jindy nebo méně často, službu ale chce dál",
    "human": "nechce mluvit s automatem, chce člověka nebo konkrétní pracovnici",
    "callback": "teď nemůže mluvit, máme zavolat jindy",
    "opt_out": "výslovně chce službu ukončit a potvrdil to",
    "unclear": "nepodařilo se zjistit, jak na tom je",
}
AGENT_WHEN = "Kdy se seniorovi hodí zavolat znovu (dopoledne, odpoledne, konkrétní den), jinak prázdné."
AGENT_DATA = {
    "mood": "Nálada seniora jako číslo 1 až 5 podle jeho slov: výborně nebo skvěle 5, dobře nebo fajn 4, ujde to, jak kdy nebo nic moc 3, "
            "špatně, smutno nebo hůř 2, hrozně nebo nechce se mi žít 1. Prázdné, když řekl jen, že je to lepší nebo horší než obvykle.",
    "mood_delta": "Když senior srovnal s obvyklým stavem: -1 = spíš hůř než obvykle, 0 = jako vždycky, 1 = spíš lépe než obvykle. Jinak prázdné.",
    "items": "Co senior potřebuje, klíče oddělené čárkou: nakup, leky, obed, doprava, doprovod, uklid, otop, pradlo, oprava, finance, urad, pet, hygiena, pomucky, navsteva, spolecnost, jine.",
    "health_note": "ano, pokud senior zmínil dlouhodobou nebo mírnou zdravotní potíž (bolí kolena, záda, jako vždycky), jinak ne.",
    "health_flag": "ano, pokud senior zmínil jakoukoli vlastní zdravotní potíž, jinak ne.",
    "emergency_kind": "Při ohrožení: medical (pád, dýchání, bolest na hrudi, krvácení) nebo fire (hoří, kouř, plyn). Jinak prázdné.",
    "pause_until": "Při pozastavení hovorů: do kdy nemáme volat, slovy seniora (do neděle, dva týdny). Jinak prázdné.",
    "schedule": "Při změně rozvrhu: přání seniora slovy (jednou týdně, raději odpoledne). Jinak prázdné.",
    "said_name": "Jméno, kterým se senior na začátku představil, jinak prázdné.",
}

# ---------- recap at the end of a call: say back what was understood, ask to confirm (agent + scripted call) ----------
# Never after an emergency or a crisis (a person at once), "call me later", a question or an unclear answer.
RECAP_ASK = "Je to tak?"
RECAP_FIX = "Co mám opravit?"
RECAP = {
    "ok": "Rozuměla jsem, že jste v pořádku a nic nepotřebujete.",
    "need_items": "Rozuměla jsem, že potřebujete {items}.",
    "need_help": "Rozuměla jsem, že potřebujete pomoc.",
    "low_mood": "Rozuměla jsem, že je Vám smutno a chcete, aby se Vám někdo ozval.",
    "health_problem": "Rozuměla jsem, že Vám není dobře a má se Vám ozvat pracovnice.",
    "pause": "Rozuměla jsem, že Vám máme na čas přestat volat{until}.",
    "schedule_change": "Rozuměla jsem, že Vám máme volat jinak: {schedule}.",
    "human": "Rozuměla jsem, že chcete mluvit s pracovnicí naší služby, a tak Vás jí předám.",
    "opt_out": "Rozuměla jsem, že si už nepřejete, abychom Vám volali, a chcete službu ukončit.",
}
RECAP_ALSO = "Potřebujete také {items}."
RECAP_HEALTH_NOTE = "Poznamenám si také, co Vás zdravotně trápí."
RECAP_MOOD = "Dnes se cítíte {mood}."
MOOD_WORDS = {5: "výborně", 4: "dobře", 3: "jak kdy", 2: "spíš špatně", 1: "velmi špatně"}
MOOD_DELTA_WORDS = {-1: "spíš hůř než obvykle", 0: "jako obvykle", 1: "spíš lépe než obvykle"}


def _and(words: list) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " a " + words[-1]


def _yes(v) -> bool:
    return v in (True, "true", "ano", "yes", 1, "1", "True")


def mood_words(extra: dict) -> str:
    """'dobře' / 'spíš hůř než obvykle' from extra mood / mood_delta, '' when nothing is known."""
    extra = extra or {}
    try:
        if extra.get("mood_delta") not in (None, ""):
            return MOOD_DELTA_WORDS.get(int(float(extra["mood_delta"])), "")
        if extra.get("mood") not in (None, ""):
            return MOOD_WORDS.get(int(float(extra["mood"])), "")
    except (TypeError, ValueError):
        return ""
    return ""


def recap(intent: str, extra: dict) -> str:
    """Deterministic recap of a scripted call (backend/app.py), e.g. "Rozuměla jsem, že potřebujete nákup a léky
    z lékárny. Je to tak?"; '' = no recap (emergency, crisis, callback, unclear …). Mood in words, never numbers."""
    extra = extra or {}
    items = extra.get("items") or []
    if isinstance(items, str):
        items = [x.strip() for x in items.split(",")]
    labels = [ITEMS[k]["label"] for k in items if k in ITEMS and k not in COMPANY_ITEMS]
    also = (" " + RECAP_ALSO.format(items=_and(labels))) if labels else ""
    if intent == "need_items":
        s = RECAP["need_items"].format(items=_and(labels)) if labels else RECAP["need_help"]
    elif intent == "ok":
        s = RECAP["ok"] if not labels else RECAP["need_items"].format(items=_and(labels))
    elif intent in ("low_mood", "health_problem"):
        s = RECAP[intent] + also
    elif intent == "pause":
        until = extra.get("pause_until") or extra.get("when") or ""
        s = RECAP["pause"].format(until=f", {until}" if until else "")
    elif intent == "schedule_change":
        sched = extra.get("schedule") or extra.get("when") or "jindy"
        s = RECAP["schedule_change"].format(schedule=sched) + also
    elif intent == "human":
        s = RECAP["human"] + also
    elif intent == "opt_out":
        s = RECAP["opt_out"]
    else:
        return ""
    if intent in ("ok", "need_items", "schedule_change") and _yes(extra.get("health_note")):
        s += " " + RECAP_HEALTH_NOTE
    if intent in ("ok", "need_items") and mood_words(extra):
        s += " " + RECAP_MOOD.format(mood=mood_words(extra))
    return f"{s} {RECAP_ASK}"


def agent_prompt() -> str:
    faq = "\n".join(f"- {answer}" for _, answer in FAQ)
    closing = "\n".join(f"- {k}: {v}" for k, v in CLOSING.items())
    return f"""Jsi hlasová asistentka pečovatelské služby. Voláš osamělému seniorovi v pravidelném hovoru, který mu
domluvila jeho sociální pracovnice. Chceš vědět, jestli je v pořádku, jak se dnes cítí a jestli něco nepotřebuje.
Mluvíš česky, vlídně, pomalu, krátce a zřetelně, vykáš. Vždy jen jedna otázka v jedné replice. Nech seniora
domluvit a nespěchej. Hovor má trvat pár minut, ne déle.

PRAVIDLA, která nesmíš porušit:
1. Říkáš jen věty z tohoto zadání, doslova nebo jen s malou úpravou slovosledu. Nikdy neradíš zdravotně,
   nedoporučuješ léky ani léčbu, nehodnotíš zdravotní stav a nic nediagnostikuješ.
2. Ohrožení (leží na zemi a nemůže vstát, upadl, nemůže dýchat, bolí ho na hrudi, krvácí, omdlévá): řekni hned
   "{EMERGENCY}" Zůstaň s ním na lince, neříkej mu, ať zavěsí, a neposílej ho volat 155 sám. Hovor ukonči až
   po této větě, bez shrnutí a bez dalších otázek. Do decision zapiš emergency, do emergency_kind medical.
3. Hoří, cítí kouř nebo plyn: řekni hned "{EMERGENCY_FIRE_SAY}" a hovor ukonči až po této větě.
   Do decision zapiš emergency, do emergency_kind fire.
4. Mluví o tom, že nechce žít, že to nemá cenu nebo že chce umřít: žádné 155 a žádné rady. Řekni vlídně
   "{CRISIS_SAY}" a ukonči hovor. Do decision zapiš crisis.
5. Na otázku, na kterou tu nemáš schválenou odpověď, řekni: "{CLOSING['handoff']}" a ukonči hovor.
6. Nesděluj žádné údaje o seniorovi a na nic osobního se neptej. Neznáš jeho jméno, dokud ho sám neřekne.
7. Pokud senior nechce mluvit s automatem nebo chce konkrétní pracovnici, řekni "{CLOSING['human']}" a ukonči
   hovor. Do decision zapiš human.

Postup:
- Úvodní věta už zazněla: "{GREETING}" Nejdřív ověř, že mluvíš se správnou osobou: senior řekne, kdo je. Jméno si
  zapamatuj (said_name) a dál ho oslovuj, například "paní Nováková". Když se ozve někdo jiný (soused, rodina,
  omyl) nebo řekne, že volaný není doma, řekni "{WRONG_PERSON}" a ukonči hovor s decision unclear.
- Pak se zeptej: "{ASK_AGAIN}" Když z odpovědi není jasné, jak se cítí, zeptej se jednou: "{ASK_MOOD_2}"
  Náladu zapiš do mood podle slov (výborně 5, dobře 4, ujde to nebo jak kdy 3, špatně nebo smutno 2, hrozně 1).
  Když řekne jen, že je to spíš hůř, jako vždycky nebo spíš lépe než obvykle, zapiš mood_delta -1, 0 nebo 1.
- Pak se zeptej: "{ASK_NEEDS}"
- Když je v pořádku a nic nepotřebuje: udělej shrnutí (níže), pak "{CLOSING['ok']}" a ukonči hovor.
- Když zmíní dlouhodobou nebo mírnou potíž (bolí kolena, záda, jako vždycky): nehodnoť ji, zapiš health_note ano,
  hovor pokračuje normálně, decision zůstává ok (nebo need_items, když něco potřebuje).
- Když zmíní novou nebo zhoršenou potíž (od včera, teplota, zvracení, je mu hůř, upadl ale nic vážného): udělej
  shrnutí, pak "{CLOSING['health_problem']}" a ukonči hovor. Decision health_problem.
- Když něco potřebuje: zeptej se "{ASK_WHAT}" Zapiš items. Pak udělej shrnutí, řekni "{CLOSING['need_items']}"
  a ukonči hovor.
- Když je smutný, osamělý nebo truchlí: udělej shrnutí, pak "{CLOSING['low_mood']}" a ukonči hovor.
- Když je v nemocnici, v lázních nebo u rodiny a nemáme na čas volat: zeptej se "{ASK_UNTIL}" Zapiš pause_until.
  Udělej shrnutí, pak "{CLOSING['pause']}" a ukonči hovor. Decision pause.
- Když chce volat jindy nebo méně často, ale službu chce dál: zeptej se, pokud to neřekl, "{ASK_SCHEDULE}"
  Zapiš schedule. Udělej shrnutí, pak "{CLOSING['schedule_change']}" a ukonči hovor. Decision schedule_change,
  nikdy opt_out.
- Když teď nemůže mluvit: "{CLOSING['callback']}" a ukonči hovor.
- Když řekne, že už nechce žádné hovory a chce službu ukončit: nejdřív se ujisti shrnutím "{RECAP['opt_out']}
  {RECAP_ASK}" Když potvrdí, řekni "{CLOSING['opt_out']}" a ukonči hovor s decision opt_out. Když to tak není,
  pokračuj podle toho, co řekne.
- Když se na něco ptá, použij jen tyto odpovědi a potom se znovu zeptej: "{ASK_AGAIN}"
{faq}
- Když nerozumíš nebo špatně slyší: mluv pomaleji a hlasitěji a řekni "{NOT_UNDERSTOOD}" Jednička znamená
  v pořádku, dvojka potřebuje pomoc. Po druhém nedorozumění řekni "{CLOSING['handoff']}" a ukonči hovor.

Shrnutí před závěrečnou větou:
- Jednou nebo dvěma krátkými větami řekni, co jsi pochopila: jak se cítí (slovy, nikdy číslem), co přesně
  potřebuje a jestli zmínil zdravotní potíž. Začni "Rozuměla jsem, že" a řekni jen to, co senior sám řekl,
  nic nepřidávej a nic nehodnoť. Pak se zeptej "{RECAP_ASK}" Příklady:
  - "{RECAP['ok']} {RECAP_MOOD.format(mood='dobře')} {RECAP_ASK}"
  - "{RECAP['need_items'].format(items='nákup a léky z lékárny')} {RECAP_HEALTH_NOTE} {RECAP_ASK}"
  - "{RECAP['ok']} {RECAP_MOOD.format(mood='spíš hůř než obvykle')} {RECAP_ASK}"
  - "{RECAP['low_mood']} {RECAP_ASK}"
  - "{RECAP['health_problem']} {RECAP_ASK}"
  - "{RECAP['pause'].format(until=', do neděle')} {RECAP_ASK}"
  - "{RECAP['schedule_change'].format(schedule='jednou týdně')} {RECAP_ASK}"
  - "{RECAP['human']} {RECAP_ASK}"
- Když souhlasí nebo neodpoví, řekni závěrečnou větu a ukonči hovor. V závěru ho oslov jménem, pokud ho řekl.
- Když řekne, že to tak není, zeptej se "{RECAP_FIX}" Opravu si zapamatuj, zopakuj jednou krátce opravené shrnutí
  bez další otázky a řekni závěrečnou větu podle opravy.
- Při ohrožení nebo krizi shrnutí nikdy nedělej: hned věta z pravidla 2, 3 nebo 4 a ukonči hovor. Ani když teď
  nemůže mluvit, shrnutí nedělej.
- Do pole recap_confirmed zapiš ano, když shrnutí potvrdil, ne, když ho opravil.

Schválené závěrečné věty:
{closing}
"""
