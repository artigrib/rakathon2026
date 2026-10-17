// All user-facing UI strings (Czech). Patient message templates live in content/messages.cs.json.
// Plain words from the nurse's point of view; one name per action across button, toast and history.
const pl = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
export const plural = pl;
// Czech verbs agree with the patient's sex: g(p, "Odmítl", "Odmítla").
const g = (p, m, f) => (p?.sex === "F" ? f : m);
export const gender = g;

export const T = {
  nav: { tasks: "Úkoly", doctor: "Pro lékaře", patients: "Pacienti", overview: "Program" },

  tasks: {
    title: "Tento týden",
    allDone: "Hotovo. Systém hlídá pacienty dál.",
  },
  sections: {
    invite: { title: "Pozvat", empty: "Vše odesláno. Pozvaní jsou níže v sekci Čekáme na odpověď." },
    replied: { title: "Ozvali se a zavolat", empty: "Nikdo nečeká." },
    doctor: { title: "Rozhodne lékař", empty: "Nic nečeká." },
    results: { title: "Výsledky", empty: "Nic k zápisu." },
    waiting: { title: "Čekáme na odpověď", empty: "Nikdo." },
    lost: { title: "Ztrácejí se" },
  },
  batch: {
    approve: (n) => `Odeslat ${n} ${pl(n, "pozvánku", "pozvánky", "pozvánek")}`,
    hint: "U pacienta můžete před odesláním změnit kanál nebo text, nebo ho vynechat.",
  },

  doctor: {
    title: "Pro lékaře",
    sub: (from, to) => `Rozhodnutí a výkony za týden ${from} až ${to}`,
    decide: "Rozhodnout o zařazení",
    results: "Výsledky k posouzení",
    codes: "Vykázat tento týden",
    c96: "01196 předán k pneumologovi",
    c97: "01197 odmítá účast",
    programme: "Program v ordinaci",
    eligible: "Splňují kritéria", invited: "Pozváni", replied: "Ozvali se", referred: "Předáni k pneumologovi", ldct: "LDCT proběhlo", lost: "Ztrácejí se",
    none: "Nic nečeká.",
    waiting: (n) => `${n} ${n === 1 ? "pacient čeká" : n < 5 ? "pacienti čekají" : "pacientů čeká"} na rozhodnutí lékaře.`,
  },

  // Above the sections: everyone in the programme has an owner and a next step.
  summary: (all, yours, doc, sys, done, lost) => `${all} v programu: ${yours} čeká na vás, ${doc} na lékaře, ${sys} hlídá systém, ${done} uzavřeno, ` +
    (lost ? `<b class="is-lost">${lost} se ztrácí</b>` : "<b>nikdo se neztrácí</b>"),
  lost: {
    booked: (n, p) => `${g(p, "Předán", "Předána")} k pneumologovi před ${n} dny, výsledek LDCT chybí. Zavolejte ${g(p, "mu", "jí")}.`,
    ldct: (n) => `LDCT před ${n} dny, výsledek nezapsán. Vyžádejte zprávu.`,
    replied: (n, p) => `${g(p, "Ozval se", "Ozvala se")} před ${n} dny a nikdo nereagoval.`,
    nurse: (n, p) => `Úkol zavolat čeká ${n} dní. ${g(p, "Pacient", "Pacientka")} zatím nikoho neslyšel${g(p, "", "a")}.`,
    failed: () => "Zpráva nebyla doručena. Ověřte telefon nebo zvolte jiný kanál.",
    exhausted: () => "Plán kontaktů skončil bez odpovědi.",
    pause: () => "Pauza skončila a nikdo pacienta znovu neoslovil.",
  },

  patients: {
    title: "Pacienti",
    filters: { all: "Všichni", nurse: "Čeká na sestru", doctor: "Čeká na lékaře", system: "Hlídá systém", done: "Uzavřeno", out: "Mimo program" },
    search: "Najít pacienta",
    searchHint: "ID, věk nebo kraj",
    groups: "Kdo je teď na řadě",
    empty: "V této skupině teď nikdo není.",
  },

  who: (p) => `${{ F: "Žena", M: "Muž" }[p.sex] || "Pacient"}, ${p.age} let`,

  // One sentence: what is going on with the patient.
  state: {
    invite: (ch) => ch,
    skipped: "Vynecháno",
    edited: "Upraveno, odejde s ostatními",
    sent: (d, ch) => `Pozvánka ${d}, ${ch}`,
    sentNext: (d, ch) => `Další pokus ${d}: ${ch}`,
    sentWait: "",
    interested: "Má zájem o vyšetření",
    callback: "Prosí o zavolání",
    nurse_call: (p) => g(p, "Neozval se, zavolejte mu", "Neozvala se, zavolejte jí"),
    not_now: (d) => `Teď ne, znovu ${d}`,
    unreachable: (p, d) => `${g(p, "Nezastižen", "Nezastižena")}, znovu ${d}`,
    declined: (p) => `${g(p, "Odmítl", "Odmítla")} účast (01197)`,
    booked: (p) => `${g(p, "Předán", "Předána")} k pneumologovi (01196)`,
    selfBooked: (p) => `${g(p, "Objednal se sám", "Objednala se sama")} u pneumologa`,
    bookedNext: "Čekáme na výsledek",
    softDeclined: (p, d) => `${g(p, "Odmítl", "Odmítla")} poprvé, nabídneme znovu ${d}`,
    noShow: (p, d) => `${g(p, "Nepřišel", "Nepřišla")} k pneumologovi, nabídneme znovu ${d}`,
    ldct: "Zapište výsledek LDCT",
    result: {
      negative: (d) => `Negativní, další LDCT ${d}`,
      indeterminate: () => "Neurčitý, kontrolu určí pneumolog",
      positive: () => "Pozitivní, předáno do centra",
    },
    excluded: (p) => `${g(p, "Vyřazen", "Vyřazena")} lékařem`,
    resultAck: "Lékař převzal",
    replied: (d, via) => `${d}${via ? `, ${via}` : ""}`,
    via: { sms: "SMS", link: "odkaz v SMS", voice: "telefon", "voice-ai": "hovor s asistentem", ui: "zapsáno v ordinaci" },
  },
  status: {
    ELIGIBLE: "Splňuje kritéria", NEEDS_REVIEW: "Rozhodne lékař", EXCLUDED_AGE: "Mimo věk 55 až 74 let",
    EXCLUDED_SMOKING_STATUS: "Nikdy nekouřili", EXCLUDED_PACK_YEARS: "Méně než 20 balíčkoroků", EXCLUDED_RECENT_CT: "Nedávné CT nebo už ve screeningu",
  },

  channel: { portal: "portál", sms: "SMS", voice: "telefonát asistenta", email: "e-mail", letter: "dopis", printout: "tisk v ordinaci", whatsapp: "WhatsApp", nurse: "sestra osobně" },
  channelRecommended: "doporučeno",
  channelFailed: "dříve selhalo",
  channelNoPortal: "Pacient nemá aktivní portál se souhlasem se zprávami",

  actions: {
    edit: "Kontaktovat",
    skip: "Vynechat",
    unskip: "Vrátit do dávky",
    booked: "Předán k pneumologovi",
    noShow: (p) => g(p, "Nepřišel", "Nepřišla"),
    again: "Kontaktovat znovu",
    changedMind: (p) => `${g(p, "Rozmyslel", "Rozmyslela")} si to, má zájem`,
    ack: "Převzato",
    declined: "Odmítá",
    unreachable: "Nezastižen",
    interested: "Má zájem",
    ldct: "LDCT proběhlo",
    result: { negative: "Negativní", indeterminate: "Neurčitý", positive: "Pozitivní" },
    include: "Zařadit",
    exclude: "Vyřadit",
    exception: "Přesto zařadit",
    open: "Zobrazit podrobnosti",
    confirmSend: () => "Odeslat",
    saveDraft: "Uložit do dávky",
    sendNow: (ch) => ({ voice: "Zavolat teď", sms: "Poslat SMS teď", whatsapp: "Poslat WhatsApp teď", email: "Poslat e-mail teď" }[ch] || "Odeslat teď"),
    cancel: "Zrušit",
    details: "Podrobnosti",
    undo: "Vrátit",
  },

  journey: { steps: { sent: "Pozván", replied: "Odpověděl", booked: "Předán", ldct: "LDCT", result: "Výsledek" } },

  demo: {
    title: "Ukázka",
    intro: "Jen pro předvedení.",
    clock: (d) => `Den ukázky: ${d}`,
    next: "Další den",
    fhirSync: "Načíst pacienty z FHIR serveru",
    replies: "Simulovat odpovědi pacientů",
    replyLabel: "Odpověď pacienta:",
    reply: { interested: "Má zájem", booked: "Už se objednal", callback: "Zavolejte mi", not_now: "Teď ne" },
    // Sample texts sent through the real reply classifier in live mode.
    replyText: { interested: "Ano, mám zájem", booked: "Už jsem objednaný", callback: "Zavolejte mi prosím", not_now: "Teď ne, děkuji" },
    openLink: "Stránka pacienta",
    reset: "Obnovit ukázková data",
    to: {
      title: "Kam posílat ukázku",
      phone: "Telefon pro SMS, hovor a WhatsApp",
      email: "E-mail",
      save: "Uložit",
      reset: "Výchozí kontakt",
      hint: (r) => `Skutečné zprávy z ukázky jdou jen sem, nejvýše ${r.dailyLimit} za den. Povolená čísla: ${r.prefixes.join(", ")}.`
        + (r.whatsappJoin ? ` Pro WhatsApp nejdřív pošlete zprávu „${r.whatsappJoin}“ na číslo ${r.whatsappFrom}.` : " Pro WhatsApp se číslo musí nejdřív připojit do sandboxu Twilio."),
    },
  },

  toast: {
    recipientSaved: "Uloženo. Ukázka teď posílá na zadaný kontakt.",
    recipientReset: "Ukázka posílá zase na výchozí kontakt.",
    sent: (ch) => `Odesláno: ${ch}.`,
    draftSaved: "Uloženo do dávky.",
    approved: (n) => `Odesláno jménem ordinace: ${n} ${pl(n, "pozvánka", "pozvánky", "pozvánek")}.`,
    skipped: "Vynecháno z této dávky.",
    unskipped: "Vráceno do dávky.",
    tick: (n) => (n ? `Další den: systém sám provedl ${n} ${pl(n, "krok", "kroky", "kroků")} plánu kontaktů.` : "Další den: dnes systém nic neodesílá."),
    reply: (r) => `Odpověď pacienta: ${r}.`,
    step: {
      interested: "Zapsáno: má zájem.", not_now: "Zapsáno: nezastižen, systém to zkusí za 3 měsíce.", booked: "Zapsáno: předán k pneumologovi (01196).", no_show: "Zapsáno: nepřišel. Nabídneme znovu za 3 měsíce.", ignored: "Tento krok teď nejde, nic se nezměnilo.",
      declined: "Zapsáno: odmítá účast (01197).", softDeclined: "Zapsáno: první odmítnutí. Nabídneme znovu za 3 měsíce.", ldct: "Zapsáno: LDCT proběhlo.", result: "Výsledek zapsán, další termín je naplánován.",
    },
    exception: "Přesto zařazen. Rozhodnutí je zaznamenáno.",
    ack: "Výsledek převzat lékařem.",
    included: "Zařazen k pozvání.",
    excluded: "Vyřazen. Rozhodnutí je zaznamenáno.",
  },

  compose: {
    channel: "Kanál",
    text: "Text zprávy",
    voiceText: "Co asistent řekne",
    note: "Zpráva nesděluje diagnózu. Odeslání schvalujete vy a zapíše se do historie.",
    trial: "Zkušební účet Twilio. Odejde jen tento krátký text bez diakritiky.",
    link: "Na konec se doplní osobní odkaz pro odpověď.",
  },

  detail: {
    evaluation: "Proč", journey: "Cesta pacienta", warnings: "Upozornění", smoking: "Kouření", ct: "CT vyšetření", contacts: "Kontakty",
    phone: "Telefon", status: "Status", packYears: "Balíčkoroky", note: "Záznam", portal: "Portál", prefers: "Preferuje", pneumologist: "Pneumolog",
    portalYes: "aktivní, souhlas", portalNo: "ne", noSmoking: "Kuřácká anamnéza chybí.", noCt: "Žádné CT v záznamech.",
    noContacts: "Zatím bez kontaktu.",
    unknown: "neuvedeno",
    smokingStatus: { current: "kouří", former: "bývalý kuřák", never: "nikdy nekouřil", unknown: "neznámý" },
    quit: (y) => `přestal ${y}`,
    pySource: { calculated: "vypočteno", reported: "z dokumentace", derived: "dopočteno" },
    ctProtocol: { ldct: "LDCT hrudníku", standard_chest: "CT hrudníku", standard_abdomen: "CT břicha", standard_head: "CT hlavy" },
    ctStatus: { completed: "provedeno", scheduled: "naplánováno", cancelled: "zrušeno" },
    external: "externí",
    msgType: { lung_screening_information: "informace o screeningu plic", other_prevention_information: "jiná prevence" },
    delivery: { read: "přečteno", delivered: "doručeno", failed: "nedoručeno", undelivered: "nedoručeno" },
    response: { interested: "má zájem", not_interested: "nemá zájem", no_response: "bez odpovědi" },
    sentByPractice: (ch) => `Pozvánka, ${ch}, schválila ordinace`,
    sentAuto: (ch, n) => `Připomínka, ${ch}, automaticky (${n + 1}. pokus)`,
    said: (t) => `„${t}“`,
    byAi: (why, when) => `Rozpoznáno: ${why}${when ? ` Kdy: ${when}.` : ""}`,
    event: {
      interested: "Odpověděl: má zájem", callback: "Prosí o zavolání", not_now: "Teď ne", nurse_call: "Úkol pro sestru: zavolat osobně",
      booked: "Předán k pneumologovi (01196)", declined: "Odmítá účast (01197)", ldct: "LDCT proběhlo", result: "Výsledek zapsán",
    },
  },

  // Patient card (components/card.js).
  card: {
    close: "Zavřít",
    why: "Proč do programu",
    age: "Věk",
    lastCt: "Poslední CT hrudníku",
    more: "Všechny důvody a CT vyšetření",
    owner: { lost: "Ztrácí se, je na řadě sestra", nurse: "Je na řadě sestra", doctor: "Je na řadě lékař", system: "Hlídá systém", done: "Uzavřeno", out: "Mimo program" },
  },

  // Communication timeline of one patient (components/comm.js).
  comm: {
    title: "Komunikace",
    actor: { record: "Z kartotéky", system: "Systém", nurse: "Ordinace", patient: "Pacient", doctor: "Lékař" },
    sent: "Pozvánka odeslána",
    autoSent: (n) => `Připomínka podle plánu, ${n + 1}. pokus`,
    planned: (c) => `Naplánováno: ${c}`,
    replied: (via, p) => `${g(p, "Odpověděl", "Odpověděla")}${via ? `, ${via}` : ""}`,
    via: { sms: "SMS", link: "přes odkaz", voice: "v hovoru", "voice-ai": "v hovoru s asistentem", ui: "zapsáno v ordinaci", whatsapp: "WhatsApp" },
    understood: "Systém zapsal:",
    softDeclined: "První odmítnutí, nabídneme znovu za 3 měsíce",
    unreachable: "Sestra nezastihla, zkusíme znovu za 3 měsíce",
    ignored: "Bez změny stavu, krok už neplatí.",
    simulated: "simulováno",
    showText: "Text zprávy",
    showScript: "Co asistent řekl",
    duration: (s) => `${s} s`,
    status: { queued: "ve frontě", sent: "odesláno", delivered: "doručeno", read: "přečteno", failed: "nedoručeno", undelivered: "nedoručeno",
      completed: "hovor proběhl", "no-answer": "nezvedl", busy: "obsazeno", ringing: "vyzvání", initiated: "vytáčí", "in-progress": "probíhá" },
    event: { interested: "Má zájem", callback: "Prosí o zavolání", not_now: "Teď ne", nurse: "Úkol pro sestru: zavolat osobně",
      booked: "Předán k pneumologovi (01196)", declined: "Odmítá účast (01197)", opt_out: "Nechce další zprávy (STOP)", no_show: "Nepřišel k pneumologovi",
      ldct: "LDCT proběhlo", result: "Výsledek zapsán", exclude: "Vyřazen lékařem", include: "Znovu zařazen lékařem" },
  },

  overview: {
    title: "Přehled programu",
    sub: (n, gps, date) => `${n} pacientů, ${gps} ordinací, ${date}`,
    impact: "Dopad",
    impactCols: ["", "Dnes", "S Jsem včas"],
    impactRows: ["Oslovení pacienti", "Odesláni k pneumologovi na LDCT"],
    impactNote: (e) => `Odhad pro ${e} pacientů, kteří splňují kritéria. Dnes program osloví 18 % cílové populace, k pneumologovi odešle 54 % oslovených. Stejný podíl odeslaných předpokládáme i u nás.`,
    funnel: "Od dat k výsledku",
    channels: "Který kanál funguje",
    chCols: ["Kanál", "Kontaktů", "Mají zájem", "Úspěšnost"],
    chNote: "Zájem (ano, už objednán, zavolejte mi) se počítá kanálu posledního kontaktu před odpovědí. Zahrnuje záznamy z kartotéky i kontakty z aplikace Jsem včas.",
    funnelSteps: ["Pacienti v datech", "Splňují kritéria", "Rozhodne lékař", "Pozváni", "Mají zájem", "Předáni k pneumologovi", "Výsledek zapsán"],
    exclusions: "Proč pacienti nejsou vhodní",
    exclusionRows: [
      ["EXCLUDED_AGE", "Mimo věk 55 až 74 let"], ["EXCLUDED_PACK_YEARS", "Méně než 20 balíčkoroků"],
      ["EXCLUDED_SMOKING_STATUS", "Nikdy nekouřili"], ["EXCLUDED_RECENT_CT", "Nedávné CT nebo už ve screeningu"],
      ["NEEDS_REVIEW", "Chybí nebo nesedí údaje"],
    ],
    practices: "Ordinace",
    cols: ["Ordinace", "Pacientů", "Splňují", "K pozvání", "Ozvali se", "Pro lékaře"],
    dataQuality: "Kvalita dat",
    dq: {
      rows: (n) => `${n} poškozených řádků v kuřácké anamnéze. Opraveno, označeno k ověření.`,
      encoding: (n) => `${n} hodnot s poškozenou diakritikou. Opraveno.`,
      conflict: (n) => `${n} pacientů s rozpornými balíčkoroky. Použita vyšší hodnota, rozhoduje lékař.`,
      ct: (n) => `${n} plánovaných nebo zrušených CT. Nevylučují, jen upozorňují.`,
    },
  },

  footer: (d) => `Syntetická data Rakathon 2026, odesílání simulované, vyhodnoceno ${d}.`,
  footerLive: (d, live) => `Syntetická data Rakathon 2026, ${live ? "SMS a hovory odcházejí přes Twilio" : "odesílání simulované"}, vyhodnoceno ${d}.`,
  footerClock: (d) => ` Den ukázky ${d}.`,
  footerFhir: (f) => ` Data z FHIR serveru ${f.server}${f.sync ? `, načteno ${f.sync.at}` : ""}. Zpět zapsáno ${f.written} záznamů${f.errors ? `, ${f.errors} chyb` : ""}.`,
  apiError: "Server neodpověděl. Zkuste to prosím znovu.",
  loadError: "Data se nepodařilo načíst. Obnovte prosím stránku.",
};
