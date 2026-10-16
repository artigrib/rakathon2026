# Plíce včas — backlog (Rakathon 2026, AstraZeneca)

Stav k pátku 16. 10. ~16:45. Odevzdání: sobota 17. 10. 13:00 (cíl 12:00). Finále: neděle 14:00.
Vlastníci: **A** = Artem · **BE** = backend · **DS** = designér · **CC** = Claude Code

## ✅ Hotovo
- Výběr výzvy Plíce včas (v Praze 0 týmů), rozbor Slacku a pravidel (vítěz každé výzvy jde do finále).
- Rozbor dat: 28 poškozených řádků, rozporné balíčkoroky, externí / plánovaná / zrušená CT, LDCT s nálezem, rozbitá diakritika.
- Kritéria potvrzena mentorem (Matys): bez časového limitu pro bývalé kuřáky, ≥ 20 balíčkoroků (stačí jedna hodnota), CT 30 dní vč. LDCT, externí CT → lékař, plánované CT nevylučuje, „nemá zájem“ nevyřazovat.
- Hodnoticí priority od mentora: správná identifikace + práce s nedokonalými daty, jednoduchost pro starší praktiky, výzva jedním klikem, sledování objednání.
- Call s Matysem: zelená pro řešení (web pro praktika + AI komunikační modul: hlas Twilio, e-mail, WhatsApp, SMS).
- SPEC.md, CONTRACT.md (formát výstupu enginu).
- Engine (Python): loader CSV/XLSX + oprava řádků + oprava diakritiky (1146 hodnot), pravidla se českými důvody a flagy, doporučení kanálu z historie, 32 testů. Výsledek: 101 vhodných · 52 ke kontrole · 147 nesplňuje.
- Web prototyp (Bauhaus, modulární ES moduly, data přes fetch): worklist praktika, tvar+barva+text pro stav, výzva jedním klikem s editací textu a volbou kanálu, hromadné odeslání, žádanka, kontrola/vyřazení, „Vrátit“, přehled programu (funnel, ordinace, kvalita dat). Publikováno jako artifact.
- Texty zpráv pro pacienty (CZ): první výzva, připomínka, motivační, SMS, skript hlasového asistenta – **koncept, čeká na korekturu**.
- Odpovědi doktorky zapracovány: interval LDCT 1 rok / 2 roky při negativním nálezu (engine + 34 testů), žádanka k pneumologovi, výjimky „Přesto zařadit“, týdenní cyklus, klidnější texty.
- Prezentace doktorky zapracována: texty „bezplatné“ + telefon ordinace (konfig), flag „nabídnout odvykání kouření“ u kuřáků, výkon 01196 u žádanky, předvolba pravidel 2027 (50–80 let, `--policy 2027`, 37 testů), čísla do pitche v SPEC.
- Odpovědi doktorky (SMS + telefonát): oslovuje náš systém, první kontakt sestra, pacient se objednává sám u libovolného PN, výsledek na papíře. Human in the loop = standard.
- Obrazovka ordinace v2: týdenní dávka „Schválit a odeslat“ (vynechat / upravit), přihrádky Tento týden · Odpověděli · Na cestě · Pro lékaře · Čekáme · Nesplňují, cesta pacienta (Pozván → Odpověděl → Objednán → LDCT → Výsledek), zápis výsledku → další LDCT, 01197 při odmítnutí, simulace odpovědi pacienta (místo webhooku), trychtýř v přehledu. Ověřeno Playwrightem (desktop + mobil).
- Backend (FastAPI) + Twilio: SMS a hlasový hovor (1/2 nebo řeč), webhooky odpovědí a doručení, pochopení české odpovědi (pravidla; 1. odmítnutí měkké, STOP hned), web v živém režimu s automatickým obnovením. Testovací režim bez klíčů. 58 testů. Návod `backend/README.md`.
- Plán kontaktů (SMS → hovor → hovor → WhatsApp → sestra), stop při odpovědi, pauza 90 dní po „teď ne“, max. 2× stejný kanál po sobě; „Posunout čas o den“ pro demo.
- Společné texty zpráv (JSON pro web i backend), „odpovězte ANO“ v SMS, osobní odkaz.
- Stránka pro pacienta `/p/{token}` (Mám zájem / Objednán / Zavolejte / Teď ne / Nepřeji si zprávy) – bez ID a zdravotních údajů.
- AI porozumění odpovědím (Anthropic / OpenAI / Azure OpenAI dle .env; STOP vždy pravidly, nejistá AI → sestra, výpadek → pravidla).
- AI hovor přes Twilio ConversationRelay (cs-CZ): AI jen rozumí, mluví jen schválenými větami (FAQ: cena, bolest, záření…), jinak předá sestře.
- FHIR R4 transaction Bundle (Patient, Observation, ImagingStudy, Communication, Task), validace R4B v testech, `scripts/fhir_export.py --post` do IRIS.
- Dockerfile, docker-compose (+ Cloudflare Tunnel), GitHub Actions (testy → deploy na VPS).
- Odevzdání: SUBMISSION.md (texty CZ/EN, AI a dopad, FHIR, scénář ukázky u stolu), titulní obrázek 16:9, záložní video 71 s. 82 testů.
- Redesign UX/UI (zpětná vazba designéra): švýcarský styl (mřížka, Inter Tight, černá/bílá + signální červená jen pro „čeká na vás“), úkolově orientovaná obrazovka Úkoly (pozvánky → ozvali se → rozhodne lékař → výsledky), Pacienti s filtry, stav jednou větou, jedna hlavní akce na řádek, ukázkové ovládání odděleno do panelu. Nový titulní obrázek a video.
- Kontakty: Matys (AZ), Hoferek (InterSystems – hackathon kit FHIR), Baštař (org – pozdní registrace).

## 🔴 P0 – dnes do 19:00 (organizační, blokuje vše)
- [ ] **A** Kolegové (BE + DS) osobně na místě; pozdní registrace přes Baštaře.
- [ ] **A** Vyřešit vlastní visačku / registraci.
- [ ] **A (kapitán)** Formulář výběru výzvy → Plíce včas, členové týmu (submit.rakathon.cz/vyzvy/vybrat).
- [ ] **A (kapitán)** Formulář přístupů Azure + portál účastníka.
- [ ] **A** Účet Twilio (trial) + ověřit telefony týmu.
- [ ] **A** Před telefonátem doktorce poslat SMS, že volá někdo z Rakathonu.
- [ ] **A** Schůzka s Matysem na místě (+ Hoferek) – ukázat prototyp.
- [ ] **A** Veřejný odkaz pro doktorku na zítřek (sdílet artifact / nasadit backend).
- [ ] **A + DS** Záložní video dema (Matys: live demo se může vymstít).

## ⏳ Čeká na odpověď
- [ ] Matys: kompletní data v XLSX (loader už XLSX umí), formát napojení na NIS.
- [ ] Hoferek: co nejvíc ocení na ceně InterSystems.

## 🟠 P1 – noc (jádro demo)
- [ ] **CC** Volba plně automatického režimu (vypínač v nastavení ordinace) – zatím jen dávka se schválením.
- [ ] **CC** Zprávy: 2 cesty (rovnou PN / ordinace), bezplatné; ověřit správný odkaz na seznam pneumologů.
- [ ] **CC** Mock „data pojišťovny“: vykázané výkony 25507 / 89663–5 → automaticky posune stav (ukázka centrálního sledování).
- [ ] **A** Twilio účet + dobít ~20 $ (bez omezení triálu), číslo SMS+hlas, Geo permissions CZ, WhatsApp sandbox → klíče do `backend/.env`.
- [ ] **BE** Spustit backend s ngrok, nastavit webhook čísla, otestovat SMS tam a zpět + hovor na DEMO_TO.
- [ ] **A** Klíč k modelu (Azure OpenAI z formuláře Azure / OpenAI / Anthropic) → `LLM_PROVIDER` v .env.
- [ ] **BE** Ověřit naostro: SMS tam a zpět, hovor `VOICE_MODE=gather`, pak `relay`; WhatsApp sandbox.
- [ ] **A** GitHub repozitář (prázdný) → CC pushne; secrets VPS_HOST/VPS_USER/VPS_SSH_KEY/APP_ENV; Cloudflare Tunnel token.
- [ ] **CC** E-mail kanál (SMTP/SendGrid).
- [ ] **BE** Notifikace lékaři: „odesláno přes X“, „bez reakce N dní → návrh jiného kanálu“.
- [ ] **BE** Týdenní přepočet (cron) + týdenní souhrn pro praktika.
- [ ] **BE** Spustit IRIS z hackathon kitu a nahrát `examples/fhir_bundle.json` (`scripts/fhir_export.py --post`).
- [ ] **BE** Souběžná notifikace registrujícímu PL „Váš pacient byl osloven“ (slide 20) – i pro režim, kdy oslovuje pojišťovna / program centrálně.
- [ ] **CC** Akce „Pacient odmítá“ (výkon 01197) vedle „Odeslat k pneumologovi“ (01196) – PL rovnou vidí, co vykázat.
- [ ] **A** Telefon ordinace / regionálního pneumologa do zpráv (`PRACTICES` v config.js; v produkci z profilu PL).
- [ ] **DS** Projít UI s ohledem na staršího praktika (velikost, kontrast, počet kroků); ladění Bauhaus vizuálu, logo.
- [ ] **A / rodilý mluvčí** Korektura českých textů pro pacienty + skript hlasu.

## 🟡 P2 – pokud zbude čas
- [ ] **CC** LLM pomocník pro NEEDS_REVIEW (návrh doplnění z volného textu anamnézy, lékař potvrzuje).
- [ ] **CC** Učení preferovaného kanálu per pacient z výsledků kontaktů (váhy místo pevných pravidel).
- [ ] **BE** Přihlášení lékaře (demo účty per VPL) – reálně SSO / systém praktika (dle odpovědi doktorky).
- [ ] **CC** Přepínač pravidel 2026 / 2027 v UI (dopad: +21 pacientů na 300).
- [ ] **CC** Export výsledků pro pojišťovnu / koordinátora (CSV).
- [ ] **DS** Náhled zprávy tak, jak ji uvidí pacient (telefon / dopis).

## 🎤 Sobota – odevzdání a pitch
Pravidla z úvodní prezentace: odevzdání do 13:00 (pak formulář nic nepřijme); 14:00 zadavatel (Matys) obchází své týmy u stolů → demo u stolu; 16:00 zadavatelé hlásí vítěze; postupuje jen vítěz výzvy. Konkurence ve výzvě: tým MSFZ (stůl 13).
Kritéria semifinále: 1) AI technologie a provedení (co reálně funguje, technická kvalita, práce s AI a daty) · 2) využitelnost u zadavatele (sedí na výzvu, reálně nasaditelné, bezpečnost / data / regulace / integrace) · 3) inovativnost. Finále navíc: 4) škálovatelnost a pokračování po hackathonu · 5) prezentace a tým.
- [ ] **A** Formulář odevzdání – vše připravené v SUBMISSION.md + submission/ (doplnit GitHub a URL dema).
- [ ] **A + DS** 3min demo u stolu pro Matyse (14:00) – ne jen pitch.
- [ ] **A** Pitch (3–5 min): problém (osloveno jen ~18 % cílové populace, 46 % odmítne, zapojeno 62 % PL) → špinavá data → 1 klik → smyčka → FHIR / napojení → dopad.
- [ ] **A + DS** Demo scénář na 1 ordinaci (VPL-0142) + záložní video demo.
- [ ] **ALL** Freeze 12:00, odevzdání do 13:00; v neděli přijet i bez postupu (cena hackerů se hlasuje v Praze).
