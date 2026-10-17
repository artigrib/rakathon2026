// All user-facing UI strings (Czech). Patient message templates live in content/messages.cs.json.
// Plain words from the nurse's point of view; one name per action across button, toast and history.
const pl = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
export const plural = pl;

export const T = {
  nav: { tasks: "Úkoly", doctor: "Pro lékaře", patients: "Pacienti", overview: "Přehled" },

  tasks: {
    title: "Tento týden",
    allDone: "Hotovo. Systém hlídá pacienty dál.",
  },
  sections: {
    invite: { title: "Pozvat", empty: "Vše odesláno. Pozvaní jsou níže v sekci Čekáme na odpověď." },
    replied: { title: "Ozvali se", empty: "Nikdo nečeká." },
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
    booked: (n) => `Předán k pneumologovi před ${n} dny, výsledek LDCT chybí. Zavolejte pacientovi.`,
    ldct: (n) => `LDCT před ${n} dny, výsledek nezapsán. Vyžádejte zprávu.`,
    replied: (n) => `Ozval se před ${n} dny a nikdo nereagoval.`,
    failed: () => "Zpráva nebyla doručena. Ověřte telefon nebo zvolte jiný kanál.",
    exhausted: () => "Plán kontaktů skončil bez odpovědi.",
    pause: () => "Pauza skončila a nikdo pacienta znovu neoslovil.",
  },

  patients: {
    title: "Pacienti",
    filters: { all: "Všichni", todo: "Čeká na vás", running: "Probíhá", done: "Uzavřeno", excluded: "Nesplňují kritéria" },
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
    nurse_call: "Neozval se, zavolejte mu",
    not_now: (d) => `Teď ne, znovu ${d}`,
    declined: "Odmítl (01197)",
    booked: "Předán k pneumologovi (01196)",
    bookedNext: "Čekáme na výsledek",
    softDeclined: (d) => `Odmítl poprvé, nabídneme znovu ${d}`,
    noShow: (d) => `Nepřišel k pneumologovi, nabídneme znovu ${d}`,
    ldct: "Zapište výsledek LDCT",
    result: {
      negative: (d) => `Negativní, další LDCT ${d}`,
      indeterminate: () => "Neurčitý, kontrolu určí pneumolog",
      positive: () => "Pozitivní, předáno do centra",
    },
    excluded: "Vyřazen lékařem",
    replied: (d, via) => `${d}${via ? `, ${via}` : ""}`,
    via: { sms: "SMS", link: "odkaz v SMS", voice: "telefon", "voice-ai": "hovor s asistentem", ui: "zapsáno v ordinaci" },
  },
  status: {
    ELIGIBLE: "Splňuje kritéria", NEEDS_REVIEW: "Ke kontrole", EXCLUDED_AGE: "Mimo věk 55 až 74 let",
    EXCLUDED_SMOKING_STATUS: "Nekuřák", EXCLUDED_PACK_YEARS: "Méně než 20 balíčkoroků", EXCLUDED_RECENT_CT: "Nedávné CT nebo už ve screeningu",
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
    noShow: "Nepřišel",
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
  },

  toast: {
    sent: (ch) => `Odesláno: ${ch}.`,
    draftSaved: "Uloženo do dávky.",
    approved: (n) => `Odesláno jménem lékaře: ${n} ${pl(n, "pozvánka", "pozvánky", "pozvánek")}.`,
    skipped: "Vynecháno z této dávky.",
    unskipped: "Vráceno do dávky.",
    tick: (n) => (n ? `Další den: systém sám provedl ${n} ${pl(n, "krok", "kroky", "kroků")} plánu kontaktů.` : "Další den: dnes systém nic neodesílá."),
    reply: (r) => `Odpověď pacienta: ${r}.`,
    step: {
      interested: "Zapsáno: má zájem.", not_now: "Zapsáno: nezastižen, systém to zkusí za 3 měsíce.", booked: "Zapsáno: předán k pneumologovi (01196).", no_show: "Zapsáno: nepřišel. Nabídneme znovu za 3 měsíce.", ignored: "Tento krok teď nejde, nic se nezměnilo.",
      declined: "Zapsáno: odmítá účast (01197).", softDeclined: "Zapsáno: první odmítnutí. Nabídneme znovu za 3 měsíce.", ldct: "Zapsáno: LDCT proběhlo.", result: "Výsledek zapsán, další termín je naplánován.",
    },
    exception: "Přesto zařazen. Rozhodnutí je zaznamenáno.",
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
    status: "Status", packYears: "Balíčkoroky", note: "Záznam", portal: "Portál", prefers: "Preferuje", pneumologist: "Pneumolog",
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

  // Communication timeline of one patient (components/comm.js).
  comm: {
    title: "Komunikace",
    actor: { record: "Z kartotéky", system: "Systém", nurse: "Ordinace", patient: "Pacient", doctor: "Lékař" },
    sent: "Pozvánka odeslána",
    autoSent: (n) => `Připomínka podle plánu, ${n + 1}. pokus`,
    planned: (c) => `Naplánováno: ${c}`,
    replied: (via) => `Odpověděl${via ? `, ${via}` : ""}`,
    via: { sms: "SMS", link: "přes odkaz", voice: "v hovoru", "voice-ai": "v hovoru s asistentem", ui: "zapsáno v ordinaci", whatsapp: "WhatsApp" },
    understood: "Systém zapsal:",
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
    impactCols: ["", "Dnes", "S Plíce včas"],
    impactRows: ["Oslovení pacienti", "Odesláni k pneumologovi na LDCT"],
    impactNote: (e) => `Odhad pro ${e} pacientů, kteří splňují kritéria. Dnes program osloví 18 % cílové populace, k pneumologovi odešle 54 % oslovených. Stejný podíl odeslaných předpokládáme i u nás.`,
    funnel: "Od dat k výsledku",
    channels: "Který kanál funguje",
    chCols: ["Kanál", "Kontaktů", "Odpověděli", "Úspěšnost"],
    chNote: "Odpověď se počítá kanálu posledního kontaktu před ní. Zahrnuje záznamy z kartotéky i kontakty z Plíce včas.",
    funnelSteps: ["Pacienti v datech", "Splňují kritéria", "Ke kontrole lékařem", "Pozváni", "Ozvali se se zájmem", "Předáni k pneumologovi", "Výsledek zapsán"],
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
  footerFhir: (f) => ` Data z FHIR serveru ${f.server}${f.sync ? `, načteno ${f.sync.at}` : ""}. Zpět zapsáno ${f.written} záznamů${f.errors ? `, ${f.errors} chyb` : ""}.`,
  apiError: "Server neodpověděl. Zkuste to prosím znovu.",
  loadError: "Data se nepodařilo načíst. Obnovte prosím stránku.",
};
