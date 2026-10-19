// All user-facing UI strings of Jsem v pořádku (Czech). Texts for seniors live in ../messages.cs.json.
// Words of an operator and a social worker: short, concrete, one name per action across button, toast and history.
const pl = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
export const plural = pl;
// Czech verbs agree with the senior's sex: g(p, "Odpověděl", "Odpověděla").
const g = (p, m, f) => (p?.sex === "F" ? f : m);
export const gender = g;
const seniorN = (n) => `${n} ${pl(n, "senior", "senioři", "seniorů")}`;

const DAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"];

export const T = {
  // short in the header; the full names (Kartotéka seniorů, Kartotéka hovorů, Košík pro sociální službu) are the page titles
  nav: { today: "Dnes", seniors: "Senioři", calls: "Hovory", basket: "Košík", overview: "Přehled" },

  today: {
    title: (d) => `Dnes, ${d}`,
    summary: (due, alerts, noAnswer, needs) => `${due} ${pl(due, "hovor", "hovory", "hovorů")} podle rozvrhu, ` +
      (alerts ? `<b class="is-lost">${alerts} ${pl(alerts, "upozornění", "upozornění", "upozornění")}</b>` : "<b>bez upozornění</b>") +
      `, ${noAnswer} bez odpovědi, ${needs} ${pl(needs, "potřebuje", "potřebují", "potřebuje")} pomoc.`,
    allDone: "Hotovo. Všichni na dnešek jsou obvoláni.",
    batch: (n) => `Zavolat ${n} ${pl(n, "seniorovi", "seniorům", "seniorům")} podle rozvrhu`,
    batchHint: "Asistent zavolá každému v jeho okně. Kdo nezvedne, tomu systém zavolá znovu, pak napíše příbuznému a nakonec pošle sociálního pracovníka.",
    toBasket: "Otevřít košík",
  },
  sections: {
    alerts: { title: "Naléhavé", hint: "Tíseň, zdravotní potíže, smutná nálada a kdo se ztrácí. Řeší člověk.", empty: "Nic naléhavého." },
    due: { title: "Dnes zavolat", empty: "Dnes už nikdo na řadě není." },
    noAnswer: { title: "Nezvedají", hint: "Systém zkouší znovu podle plánu. Po třetím pokusu jde úkol sociálnímu pracovníkovi.", empty: "Všichni zvedli." },
    needs: { title: "Potřebují pomoc", hint: "Potřeby se sbírají v košíku pro sociální službu.", empty: "Nikdo nic nepotřebuje." },
    ok: { title: "Dnes v pořádku", empty: "Zatím nikdo neodpověděl.", show: "Zobrazit" },
  },

  lost: {
    noAnswer: (n, p) => `${g(p, "Nezastižen", "Nezastižena")} ${n} ${pl(n, "den", "dny", "dní")} a plán pokusů skončil. Zavolejte příbuznému.`,
    silent: (n, p) => `Už ${n} ${pl(n, "den", "dny", "dní")} jsme ${g(p, "ho", "ji")} neslyšeli.`,
    escalated: (n) => `Předáno před ${n} ${pl(n, "dnem", "dny", "dny")} a stále nevyřešeno.`,
  },

  seniors: {
    title: "Kartotéka seniorů",
    search: "Najít seniora",
    searchHint: "Jméno, ulice nebo příbuzný",
    groups: "Kdo je teď na řadě",
    empty: "V této skupině teď nikdo není.",
    filters: { all: "Všichni", social: "Sociální pracovník", operator: "Operátor", system: "Hlídá systém", paused: "Pozastaveno", done: "Odhlášeni" },
    mood7: "Nálada za 30 dní",
  },
  // core/views/patients.js (not in the menu, kept for the contract)
  patients: {
    title: "Kartotéka seniorů", search: "Najít seniora", searchHint: "Jméno, ulice nebo příbuzný", groups: "Kdo je teď na řadě",
    empty: "V této skupině teď nikdo není.",
    filters: { all: "Všichni", social: "Sociální pracovník", operator: "Operátor", system: "Hlídá systém", paused: "Pozastaveno", done: "Odhlášeni" },
  },

  calls: {
    title: "Kartotéka hovorů",
    sub: (n, from) => `${n} ${pl(n, "záznam", "záznamy", "záznamů")} od ${from}. Přepis odpovědi, nálada a potřeby, které systém rozpoznal.`,
    filters: { all: "Vše", noanswer: "Nezvedl", needs: "S potřebami", mood: "Smutná nálada", health: "Zdraví a tíseň" },
    range: { 7: "7 dní", 30: "30 dní" },
    cols: ["Kdy", "Senior", "Výsledek", "Nálada", "Potřeby", "Co řekl"],
    empty: "Žádné hovory v tomto výběru.",
    live: "z ukázky",
    relative: "SMS příbuznému",
  },

  basket: {
    title: "Košík pro sociální službu",
    sub: (d, n) => `${d}: ${n} ${pl(n, "otevřená položka", "otevřené položky", "otevřených položek")}. Potřeby z hovorů, seskupené podle sociálního pracovníka.`,
    filters: { open: "Otevřené", new: "Nové", ordered: "Objednáno", done: "Vyřízeno", all: "Vše" },
    status: { new: "nové", ordered: "objednáno", done: "vyřízeno" },
    order: "Objednáno",
    done: "Vyřízeno",
    reopen: "Vrátit",
    csv: "Exportovat CSV",
    summary: "Souhrn podle druhu",
    sumCols: ["Potřeba", "Nové", "Objednáno", "Vyřízeno"],
    worker: (w, n) => `${w}`,
    workerSub: (n) => `${n} ${pl(n, "položka", "položky", "položek")}`,
    empty: "V košíku nic není.",
    districts: "Všechny obvody",
    distCols: ["Obvod", "Seniorů", "Otevřené potřeby", "Nové"],
    csvCols: ["Obvod", "Sociální pracovník", "Senior", "Adresa", "Telefon", "Potřeba", "Ze dne", "Stav"],
  },

  overview: {
    title: "Přehled",
    sub: (n, d) => `${seniorN(n)} v obvodu, stav k ${d}`,
    coverage: "Pokrytí za 7 dní",
    stats: ["Aktivních v programu", "Zastiženo za 7 dní", "Poslední hovor v pořádku", "Průměrná nálada za 7 dní", "Otevřené potřeby", "Naléhavé"],
    trend: "Trend nálady",
    trendNote: "Průměrná nálada zastižených seniorů za den, 1 velmi špatná, 5 výborná.",
    needs: "Co senioři potřebují za 30 dní",
    moods: "Nálada při posledním hovoru",
    districts: "Obvody",
    cols: ["Obvod", "Seniorů", "Zastiženo za 7 dní", "V pořádku", "Nálada", "Otevřené potřeby", "Naléhavé"],
    none: "bez údaje",
  },

  who: (p) => `${p.name}, ${p.age}`,

  mood: { 1: "velmi špatná", 2: "smutná", 3: "ujde to", 4: "dobrá", 5: "výborná" },
  moodShort: (m) => (m ? `nálada ${m} z 5` : ""),
  intent: {
    ok: "V pořádku", need_items: "Potřebuje pomoc", low_mood: "Smutná nálada", health_problem: "Zdravotní potíž",
    emergency: "Tíseň", callback: "Zavolat později", opt_out: "Nepřeje si hovory", question: "Dotaz", unclear: "Nerozumíme",
  },
  mobility: { independent: "chodí bez pomoci", cane: "chodí o holi", walker: "chodítko", wheelchair: "vozík", homebound: "nevychází z bytu" },
  schedule: {
    daily: "denně", weekdays: "v pracovní dny", mwf: "Po, St, Pá", tt: "Út, Čt",
    days: (days) => days.map((d) => DAYS[d]).join(", "),
    window: (s) => `${s.from} až ${s.to}`,
  },

  // One sentence: what is going on with the senior.
  state: {
    due: (s, ch) => `Dnes volat ${s.from} až ${s.to}, ${ch}`,
    dueSkipped: "Dnes vynecháno",
    edited: "Upravený text, odejde s ostatními",
    noAnswer: (n, d) => `Nezvedá: ${n} ${pl(n, "pokus", "pokusy", "pokusů")} bez odpovědi, ${d}`,
    next: (d, ch) => `Další krok ${d}: ${ch}`,
    relativeSent: "SMS příbuznému odeslána",
    planDone: "Plán pokusů skončil",
    ok: (m) => `V pořádku${m ? `, nálada ${m} z 5` : ""}`,
    needs: (items) => `Potřebuje: ${items}`,
    needsAny: "Potřebuje pomoc, upřesnit",
    lowMood: (m) => `Smutná nálada${m ? `, ${m} z 5` : ""}`,
    emergency: "Tíseň: ověřit hned, zda volal 155",
    health: "Zdravotní potíž, ozvat se ještě dnes",
    visit: (p) => `${g(p, "Nezastižen", "Nezastižena")} třikrát, navštívit`,
    escalated: "Předáno sociálnímu pracovníkovi",
    callback: "Prosí zavolat později",
    question: "Má dotaz, zavolat",
    resolved: (d) => `Vyřešeno ${d}`,
    paused: (r, d) => `Pozastaveno${r ? `: ${r.toLowerCase()}` : ""}${d ? `, do ${d}` : ""}`,
    declined: "Nepřeje si hovory",
    enrolled: (p, s) => `${g(p, "Zapsán", "Zapsána")} do programu${s ? `, první hovor ${s}` : ""}`,
    answered: (d, t, via) => `${d}${t ? ` v ${t}` : ""}${via ? `, ${via}` : ""}`,
    via: { sms: "SMS", link: "odkaz v SMS", voice: "telefon", "voice-ai": "hovor s asistentem", "voice-agent": "hovor s asistentem", ui: "zapsal operátor", whatsapp: "WhatsApp" },
  },

  channel: { sms: "SMS", voice: "hovor asistenta", whatsapp: "WhatsApp", email: "e-mail", letter: "dopis", portal: "portál", visit: "návštěva sociálního pracovníka" },
  channelRecommended: "doporučeno",
  channelFailed: "dříve selhalo",
  channelNoPortal: "Senior nemá portál",

  actions: {
    call: "Zavolat teď",
    skip: "Dnes vynechat",
    unskip: "Vrátit do dnešních",
    visit: "Poslat na návštěvu",
    reached: "Je v pořádku",
    resolve: "Vyřešeno",
    escalate: "Předat sociálnímu pracovníkovi",
    basket: "Košík",
    pause: "Pozastavit",
    resume: "Obnovit hovory",
    enroll: "Znovu zapsat",
    open: "Zobrazit kartu",
    confirmSend: () => "Odeslat",
    saveDraft: "Uložit k dnešním",
    sendNow: (ch) => ({ voice: "Zavolat teď", sms: "Poslat SMS teď", whatsapp: "Poslat WhatsApp teď", email: "Poslat e-mail teď" }[ch] || "Odeslat teď"),
    cancel: "Zrušit",
    undo: "Vrátit",
    result: {},
  },

  journey: { steps: { called: "Voláno", answered: "Odpověděl", escalated: "Řeší člověk", resolved: "Vyřešeno" } },

  demo: {
    title: "Ukázka",
    intro: "Jen pro předvedení. Senioři i čísla jsou smyšlení.",
    clock: (d) => `Den ukázky: ${d}`,
    next: "Další den",
    fhirSync: "",
    replies: "Simulovat odpovědi seniorů",
    replyLabel: "Odpověď seniora:",
    reply: { ok: "V pořádku", need_items: "Nákup a léky", low_mood: "Smutno", health_problem: "Bolí koleno", emergency: "Upadla", callback: "Později" },
    // Sample sentences sent through the real reply understanding in live mode.
    replyText: {
      ok: "Dobře, děkuji, všechno v pořádku.",
      need_items: "Došly mi léky a potřebovala bych nakoupit.",
      low_mood: "Ale nic moc, jsem pořád sama a je mi smutno.",
      health_problem: "Od včera mě bolí koleno a točí se mi hlava.",
      emergency: "Upadla jsem a nemůžu vstát.",
      callback: "Teď nemůžu, zavolejte mi odpoledne.",
    },
    openLink: "Stránka seniora",
    reset: "Obnovit ukázková data",
    hall: "",
    to: {
      title: "Kam posílat ukázku",
      phone: "Telefon pro SMS, hovor a WhatsApp",
      email: "E-mail",
      save: "Uložit",
      reset: "Výchozí kontakt",
      logout: "Odhlásit",
      hint: (r) => `Skutečné zprávy z ukázky jdou jen sem, nejvýše ${r.dailyLimit} za den. Povolená čísla: ${r.prefixes.join(", ")}.`
        + (r.whatsappJoin ? ` Pro WhatsApp nejdřív pošlete zprávu „${r.whatsappJoin}“ na číslo ${r.whatsappFrom}.` : ""),
    },
  },

  toast: {
    recipientSaved: "Uloženo. Ukázka teď posílá na zadaný kontakt.",
    recipientReset: "Ukázka posílá zase na výchozí kontakt.",
    sent: (ch) => `Odesláno: ${ch}.`,
    draftSaved: "Uloženo, odejde s dnešními hovory.",
    approved: (n) => `Asistent volá: ${n} ${pl(n, "senior", "senioři", "seniorů")}.`,
    skipped: "Dnes vynecháno.",
    unskipped: "Vráceno do dnešních hovorů.",
    tick: (n) => (n ? `Další den: systém sám provedl ${n} ${pl(n, "krok", "kroky", "kroků")} plánu pokusů.` : "Další den: dnes systém nic neodesílá."),
    reply: (r) => `Odpověď seniora: ${r}.`,
    step: {
      ok: "Zapsáno: je v pořádku.", visit: "Úkol pro sociálního pracovníka: návštěva.", escalate: "Předáno sociálnímu pracovníkovi.",
      resolve: "Zapsáno: vyřešeno.", pause: "Hovory pozastaveny.", resume: "Hovory obnoveny.", decline: "Odhlášen z programu.",
      enroll: "Znovu zapsán do programu.", softDeclined: "", ignored: "Tento krok teď nejde, nic se nezměnilo.",
    },
    basket: { ordered: "Označeno jako objednané.", done: "Označeno jako vyřízené.", new: "Vráceno mezi nové." },
    csv: (n) => `Staženo ${n} ${pl(n, "položka", "položky", "položek")} do CSV.`,
  },

  compose: {
    channel: "Kanál",
    text: "Text zprávy",
    voiceText: "Co asistent řekne",
    note: "Asistent nedává zdravotní rady. V nouzi vždy odkáže na 155 a předá hovor člověku.",
    trial: "Zkušební účet Twilio. Odejde jen tento krátký text bez diakritiky.",
    link: "Na konec se doplní osobní odkaz pro odpověď.",
  },

  detail: {
    journey: "Cesta seniora",
    noContacts: "Zatím bez kontaktu.",
    msgType: {},
    delivery: { read: "přečteno", delivered: "doručeno", failed: "nedoručeno", undelivered: "nedoručeno" },
    response: {},
    event: {
      ok: "V pořádku", needs_help: "Potřebuje pomoc", low_mood: "Smutná nálada", escalated: "Předáno člověku", callback: "Zavolat později",
      resolved: "Vyřešeno", paused: "Pozastaveno", declined: "Nepřeje si hovory", enrolled: "Zapsán do programu",
    },
  },

  // Senior card (core/components/card.js + web/card.js).
  card: {
    close: "Zavřít",
    owner: { lost: "Ztrácí se, je na řadě operátor", operator: "Je na řadě operátor", social: "Je na řadě sociální pracovník", system: "Hlídá systém", paused: "Pozastaveno", done: "Odhlášen z programu" },
    facts: "Senior",
    age: "Věk", address: "Adresa", alone: "Domácnost", aloneYes: (p) => g(p, "žije sám", "žije sama"), mobility: "Pohyblivost",
    schedule: "Hovory", worker: "Sociální pracovník", since: "V programu od", phone: "Telefon",
    mood: "Nálada za 30 dní", moodNone: "Zatím bez údaje o náladě.", moodAvg: (a) => `průměr ${a}`,
    needs: "Otevřené potřeby", needsNone: "Nic nepotřebuje.",
    relative: "Příbuzný", calls: "Historie hovorů", more: (n) => `Starší hovory (${n})`,
    noAnswer: "nezvedl", noAnswerF: "nezvedla", relativeSms: "SMS příbuznému",
  },

  // Communication timeline (core/components/comm.js).
  comm: {
    title: "Komunikace",
    actor: { record: "Z kartotéky", system: "Systém", nurse: "Operátor", patient: "Senior", doctor: "Sociální pracovník" },
    sent: "Hovor nebo zpráva odeslána",
    autoSent: (n) => `Pokus podle plánu, ${n + 1}. krok`,
    planned: (c) => `Naplánováno: ${c}`,
    replied: (via, p) => `${g(p, "Odpověděl", "Odpověděla")}${via ? `, ${via}` : ""}`,
    via: { sms: "SMS", link: "přes odkaz", voice: "v hovoru", "voice-ai": "v hovoru s asistentem", "voice-agent": "v hovoru s asistentem", ui: "zapsal operátor", whatsapp: "WhatsApp" },
    understood: "Systém zapsal:",
    softDeclined: "",
    unreachable: "Nezastižen",
    ignored: "Bez změny stavu.",
    simulated: "simulováno",
    showText: "Text zprávy",
    showScript: "Co asistent řekl",
    duration: (s) => `${s} s`,
    status: { queued: "ve frontě", sent: "odesláno", delivered: "doručeno", read: "přečteno", failed: "nedoručeno", undelivered: "nedoručeno",
      completed: "hovor proběhl", "no-answer": "nezvedl", busy: "obsazeno", ringing: "vyzvání", initiated: "vytáčí", "in-progress": "probíhá" },
    event: {
      ok: "V pořádku", need_items: "Potřebuje pomoc", low_mood: "Smutná nálada", health_problem: "Zdravotní potíž", emergency: "Tíseň, odkázán na 155",
      callback: "Zavolat později", opt_out: "Nepřeje si hovory", visit: "Třikrát nezvedl: úkol návštěva", escalate: "Předáno sociálnímu pracovníkovi",
      resolve: "Vyřešeno", pause: "Hovory pozastaveny", resume: "Hovory obnoveny", decline: "Odhlášen z programu", enroll: "Zapsán do programu",
    },
  },

  footer: (d) => `Syntetická data, odesílání simulované, stav k ${d}.`,
  footerLive: (d, live) => `Syntetická data, ${live ? "SMS a hovory odcházejí přes Twilio" : "odesílání simulované"}, stav k ${d}.`,
  footerClock: (d) => ` Den ukázky ${d}.`,
  footerFhir: () => "",
  apiError: "Server neodpověděl. Zkuste to prosím znovu.",
  loadError: "Data se nepodařilo načíst. Obnovte prosím stránku.",
};
