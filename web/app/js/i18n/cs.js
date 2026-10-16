// All user-facing UI strings (Czech). Patient message templates live in content/messages.cs.json.
// Plain words from the nurse's point of view; one name per action across button, toast and history.
const pl = (n, one, few, many) => (n === 1 ? one : n >= 2 && n <= 4 ? few : many);
export const plural = pl;

export const T = {
  nav: { tasks: "Úkoly", patients: "Pacienti", overview: "Přehled programu" },

  tasks: {
    title: "Úkoly na tento týden",
    sub: (n, date) => `${n} pacientů ordinace, vyhodnoceno ${date}. Seznam se obnovuje každý týden.`,
    allDone: "Na tento týden je hotovo. Systém hlídá pacienty dál a ozve se, až bude co dělat.",
  },
  sections: {
    invite: { title: "Pozvánky k odeslání", what: "Splňují kritéria programu a ještě nebyli pozváni.", empty: "Pozvánky na tento týden jsou odeslané." },
    replied: { title: "Ozvali se", what: "Domluvte další krok. Pacient se může objednat sám u kteréhokoli pneumologa v programu.", empty: "Nikdo nečeká na odpověď." },
    doctor: { title: "Rozhodne lékař", what: "Chybějící nebo rozporné údaje. Pacienta neoslovíme, dokud lékař nerozhodne.", empty: "Nic nečeká na lékaře." },
    results: { title: "Výsledky vyšetření", what: "Pacient si výsledek LDCT přinese. Zapište ho a systém naplánuje další termín.", empty: "Žádný výsledek nečeká na zápis." },
  },
  batch: {
    text: (mix) => `Odejdou jménem lékaře, každá kanálem podle historie pacienta (${mix}). Kteroukoli můžete upravit nebo vynechat.`,
    approve: (n) => `Schválit a odeslat ${n} ${pl(n, "pozvánku", "pozvánky", "pozvánek")}`,
    mix: (n, ch) => `${ch} ${n}×`,
  },

  patients: {
    title: "Pacienti",
    sub: (n) => `${n} registrovaných pacientů ordinace.`,
    filters: { all: "Všichni", todo: "Čeká na vás", running: "Probíhá", done: "Uzavřeno", excluded: "Nesplňují kritéria" },
    empty: "V této skupině teď nikdo není.",
  },

  who: (p) => `${{ F: "Žena", M: "Muž" }[p.sex] || "Pacient"}, ${p.age} let`,

  // One sentence: what is going on with the patient.
  state: {
    invite: (ch) => `Pozvánka připravena – ${ch}`,
    skipped: "Vynecháno z této dávky",
    sent: (d, ch) => `Pozván ${d} – ${ch}`,
    sentNext: (d, ch) => `Zatím bez odpovědi. Další pokus ${d}: ${ch}.`,
    sentWait: "Zatím bez odpovědi.",
    interested: "Má zájem o vyšetření",
    callback: "Prosí o zavolání",
    nurse_call: "Neozval se na čtyři pokusy – zavolejte osobně",
    not_now: (d) => `Teď nechce. Systém se znovu ozve ${d}.`,
    declined: "Odmítl účast – vykázat 01197",
    booked: "Objednán u pneumologa",
    bookedNext: "Až LDCT proběhne, potvrďte to.",
    ldct: "LDCT proběhlo – zapište výsledek",
    result: {
      negative: (d) => `Výsledek negativní. Další LDCT od ${d}.`,
      indeterminate: () => "Výsledek neurčitý. Kontrolu určí pneumolog.",
      positive: () => "Výsledek pozitivní. Péči převzalo specializované centrum.",
    },
    excluded: "Vyřazen lékařem",
    replied: (d, via) => `Odpověď ${d}${via ? ` (${via})` : ""}`,
    via: { sms: "SMS", link: "odkaz v SMS", voice: "telefon", "voice-ai": "hovor s asistentem", ui: "zapsáno v ordinaci" },
  },
  status: {
    ELIGIBLE: "Splňuje kritéria", NEEDS_REVIEW: "Ke kontrole", EXCLUDED_AGE: "Mimo věk 55–74",
    EXCLUDED_SMOKING_STATUS: "Nekuřák", EXCLUDED_PACK_YEARS: "Méně než 20 balíčkoroků", EXCLUDED_RECENT_CT: "Nedávné CT nebo už ve screeningu",
  },

  channel: { portal: "portál", sms: "SMS", voice: "telefonát asistenta", email: "e-mail", letter: "dopis", printout: "tisk v ordinaci", whatsapp: "WhatsApp", nurse: "sestra osobně" },
  channelRecommended: "doporučeno",
  channelFailed: "dříve selhalo",
  channelNoPortal: "Pacient nemá aktivní portál se souhlasem se zprávami",

  actions: {
    edit: "Upravit text",
    skip: "Vynechat",
    unskip: "Vrátit do dávky",
    booked: "Objednán",
    declined: "Odmítá",
    unreachable: "Nezastižen",
    interested: "Má zájem",
    ldct: "LDCT proběhlo",
    result: { negative: "Negativní", indeterminate: "Neurčitý", positive: "Pozitivní" },
    include: "Zařadit",
    exclude: "Vyřadit",
    exception: "Přesto zařadit",
    confirmSend: (ch) => `Odeslat – ${ch}`,
    cancel: "Zrušit",
    details: "Podrobnosti",
    undo: "Vrátit",
  },

  journey: { steps: { sent: "Pozván", replied: "Odpověděl", booked: "Objednán", ldct: "LDCT", result: "Výsledek" } },

  demo: {
    title: "Ukázka",
    intro: "Ovládání jen pro předvedení. V provozu tyto kroky dělají pacienti a čas.",
    clock: (d) => `Den ukázky: ${d}`,
    next: "Další den",
    replies: "Ukázat simulaci odpovědí pacientů",
    replyLabel: "Odpověď pacienta:",
    reply: { interested: "Má zájem", booked: "Už se objednal", callback: "Zavolejte mi", not_now: "Teď ne" },
    // Sample texts sent through the real reply classifier in live mode.
    replyText: { interested: "Ano, mám zájem", booked: "Už jsem objednaný", callback: "Zavolejte mi prosím", not_now: "Teď ne, děkuji" },
    openLink: "Stránka pacienta",
    reset: "Obnovit ukázková data",
  },

  toast: {
    sent: (ch) => `Odesláno – ${ch}.`,
    approved: (n) => `Odesláno jménem lékaře: ${n} ${pl(n, "pozvánka", "pozvánky", "pozvánek")}.`,
    skipped: "Vynecháno z této dávky.",
    unskipped: "Vráceno do dávky.",
    tick: (n) => (n ? `Další den: systém sám provedl ${n} ${pl(n, "krok", "kroky", "kroků")} plánu kontaktů.` : "Další den: dnes systém nic neodesílá."),
    reply: (r) => `Odpověď pacienta: ${r}.`,
    step: {
      interested: "Zapsáno: má zájem.", not_now: "Zapsáno: nezastižen, systém to zkusí za 3 měsíce.", booked: "Zapsáno: objednán u pneumologa.",
      declined: "Zapsáno: odmítá účast (01197).", ldct: "Zapsáno: LDCT proběhlo.", result: "Výsledek zapsán, další termín je naplánován.",
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
  },

  detail: {
    evaluation: "Proč", journey: "Cesta pacienta", warnings: "Upozornění", smoking: "Kouření", ct: "CT vyšetření", contacts: "Kontakty",
    status: "Status", packYears: "Balíčkoroky", note: "Záznam", portal: "Portál", prefers: "Preferuje", pneumologist: "Pneumolog",
    portalYes: "aktivní, souhlas", portalNo: "ne", noSmoking: "Kuřácká anamnéza chybí.", noCt: "Žádné CT v záznamech.",
    noContacts: "Zatím bez kontaktu.",
    smokingStatus: { current: "kouří", former: "bývalý kuřák", never: "nikdy nekouřil", unknown: "neznámý" },
    quit: (y) => `přestal ${y}`,
    pySource: { calculated: "vypočteno", reported: "z dokumentace", derived: "dopočteno" },
    ctProtocol: { ldct: "LDCT hrudníku", standard_chest: "CT hrudníku", standard_abdomen: "CT břicha", standard_head: "CT hlavy" },
    ctStatus: { completed: "provedeno", scheduled: "naplánováno", cancelled: "zrušeno" },
    external: "externí",
    msgType: { lung_screening_information: "informace o screeningu plic", other_prevention_information: "jiná prevence" },
    delivery: { read: "přečteno", delivered: "doručeno", failed: "nedoručeno", undelivered: "nedoručeno" },
    response: { interested: "má zájem", not_interested: "nemá zájem", no_response: "bez odpovědi" },
    sentByPractice: (ch) => `Pozvánka – ${ch}, schváleno ordinací`,
    sentAuto: (ch, n) => `Připomínka – ${ch}, automaticky (krok ${n + 1} plánu)`,
    said: (t) => `„${t}“`,
    byAi: (why, when) => `AI: ${why}${when ? ` (kdy: ${when})` : ""}`,
    event: {
      interested: "Odpověděl: má zájem", callback: "Prosí o zavolání", not_now: "Teď ne", nurse_call: "Úkol pro sestru: zavolat osobně",
      booked: "Objednán u pneumologa", declined: "Odmítá účast (01197)", ldct: "LDCT proběhlo", result: "Výsledek zapsán",
    },
  },

  overview: {
    title: "Přehled programu",
    sub: (n, gps, date) => `${n} pacientů u ${gps} praktických lékařů, vyhodnoceno ${date}.`,
    funnel: "Od dat k výsledku",
    funnelWhat: "Kolik pacientů je v jakém kroku programu.",
    funnelSteps: ["Pacienti v datech", "Splňují kritéria", "Ke kontrole lékařem", "Pozváni", "Ozvali se se zájmem", "Objednáni u pneumologa", "Výsledek zapsán"],
    exclusions: "Proč pacienti nejsou vhodní",
    exclusionsWhat: "Každé rozhodnutí má uvedený důvod.",
    exclusionRows: [
      ["EXCLUDED_AGE", "Mimo věk 55–74"], ["EXCLUDED_PACK_YEARS", "Méně než 20 balíčkoroků"],
      ["EXCLUDED_SMOKING_STATUS", "Nikdy nekouřili"], ["EXCLUDED_RECENT_CT", "Nedávné CT nebo už ve screeningu"],
      ["NEEDS_REVIEW", "Chybí nebo nesedí údaje"],
    ],
    practices: "Ordinace",
    practicesWhat: "Kliknutím otevřete úkoly ordinace.",
    cols: ["Ordinace", "Pacientů", "Splňují", "K pozvání", "Ozvali se", "Pro lékaře"],
    dataQuality: "Kvalita dat",
    dataQualityWhat: "Co engine v datech opravil a co nechal na lékaři.",
    dq: {
      rows: (n) => `${n} poškozených řádků v kuřácké anamnéze – opraveno a označeno k ověření.`,
      encoding: (n) => `${n} hodnot s poškozenou diakritikou – opraveno.`,
      conflict: (n) => `${n} pacientů s rozpornými balíčkoroky – použita vyšší hodnota, rozhoduje lékař.`,
      ct: (n) => `${n} plánovaných nebo zrušených CT – nevylučují, jen upozorňují.`,
    },
  },

  footer: (d) => `Ukázka nad syntetickými daty výzvy Rakathon 2026. Odesílání zpráv je simulované. Vyhodnoceno ${d}.`,
  footerLive: (d, live, ai) => (live
    ? "Živý režim: SMS a hovory odcházejí přes Twilio na ukázkový telefon. Data jsou syntetická."
    : "Server běží v testovacím režimu bez Twilio, odesílání je simulované.")
    + (ai ? ` Odpovědím pacientů rozumí AI (${ai}), bezpečnostní pravidla mají přednost.` : "")
    + ` Vyhodnoceno ${d}.`,
  apiError: "Server neodpověděl. Zkuste to prosím znovu.",
  loadError: "Data se nepodařilo načíst. Obnovte prosím stránku.",
};
