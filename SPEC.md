# Plíce včas — SPEC (Rakathon 2026, AstraZeneca)

## Cíl
Systém, který v NIS najde pacienty vhodné pro screening karcinomu plic (Prevence pro plíce),
vyloučí ty s CT hrudníku za poslední měsíc, vysvětlí důvod, zvolí kanál, odešle neutrální
informační zprávu, eviduje doručení/reakci a nechá zdravotníka výsledek zkontrolovat/upravit.

## Vstupy (data/)
1_patients.csv, 2_smoking_history.csv, 3_chest_ct_examinations.csv,
4_patients_contact_history.csv, 5_data_dictionary.csv. UTF-8, CRLF, každý řádek obalen v uvozovkách
(nutno odstranit vnější `"` a `""` → `"` před parsováním CSV).

## Referenční datum
`REF_DATE` = datum běhu (default 2026-10-16), konfigurovatelné.

## Kritéria (POTVRZENO mentorem L. Matys, 16.10. 15:00)
- Primární uživatel: PRAKTICKÝ LÉKAŘ (cíl = správný referral). Worklist seskupený podle primary_care_provider_id.
- Věk 55–74 včetně k REF_DATE (přesný výpočet dle data narození).
- smoking_status ∈ {current, former}. Former: BEZ časového omezení od ukončení kouření.
- Pack-years ≥ 20 (alespoň 20). Pokud ALESPOŇ JEDNA z hodnot (reported / calculated) ≥ 20 → splňuje;
  při rozporu flag „rozdílné údaje“ pro lékaře (lékař může udělit výjimku, např. rodinná anamnéza).
  Obě chybí → NEEDS_REVIEW.
- Vyloučení: CT hrudníku za posledních 30 dní včetně LDCT (status=completed).
  Externí CT (is_external=true) za posledních 30 dní: NEVYLUČOVAT automaticky → NEEDS_REVIEW
  s důvodem „externí CT – ke zvážení lékařem“ (potvrzeno mentorem). V aktuálních datech žádný takový případ.

## Doporučení kanálu (dle mentora: „velmi ocení“)
- Žádné pevné pravidlo nestačí (někdo nesnáší SMS, jiný nečte poštu) → doporučení + vysvětlení
  + notifikace lékaři o způsobu odeslání + sledování, zda to mělo efekt.
- Zpětná vazba: výsledek každého kontaktu se ukládá k pacientovi a příště ovlivní doporučení
  (kanál, který u pacienta selhal, se znevýhodní; kanál s reakcí se upřednostní).
- Kanály: portal, letter, printout + navrhované SMS a telefon (phone_number v datech je).
- Reálná data z NIS a roztříštěných systémů praktiků jsou výrazně horší → robustní validace, NEEDS_REVIEW, audit.
  scheduled v budoucnu → poznámka „plánované CT“; scheduled v minulosti / cancelled → nezapočítat, flag.

## Výstupní stavy (pořadí vyhodnocení)
1. EXCLUDED_AGE
2. NEEDS_REVIEW — chybí kuřácký status nebo obě hodnoty pack-years (unknown, malformovaný řádek, chybějící záznam)
3. EXCLUDED_SMOKING_STATUS (never)
4. EXCLUDED_PACK_YEARS
5. EXCLUDED_RECENT_CT
6. ELIGIBLE
Každý pacient: status + lidsky čitelný důvod (CZ) + použité hodnoty (věk, PY, zdroj PY, datum CT).
Klinické flagy navíc: LDCT s nálezem („uzlík k další kontrole“) → upozornění pro lékaře, nekontaktovat automaticky.

## Výběr kanálu (jen ELIGIBLE)
- historie: not_interested → nekontaktovat (respektovat volbu); interested → úkol pro VPL/PNEU (dořešit), ne další zprávu;
  failed → jiný kanál (dopis/tisk); no_response/delivered → připomínka max. 1× po X dnech.
- portal_active ∧ consent → portál; jinak letter/printout dle preferred_contact_channel;
  none → úkol pro praktického lékaře (nebo pneumologa, je-li evidován).

## Zpráva pacientovi
Neutrální, srozumitelná CZ, bez diagnózy, netvrdí automatické zařazení do programu.
Odkaz na praktického lékaře nebo pneumologa, odkaz na prevenceproplice.cz. Varianty: první kontakt, připomínka, dopis.

## Evidence
Nový záznam do contact_history (stejné schéma) + audit (kdo schválil/změnil, kdy).
Zdravotník může status ručně přepsat s důvodem.

## Architektura MVP
- engine/ (Python): load + validate + rules + channel, čisté funkce, pytest.
- api/ (FastAPI): /patients, /patients/{id}, /run, /contacts (simulované odeslání), /override.
- web/: worklist (filtr dle stavu), karta pacienta s důvodem, schválení/odeslání, dashboard funnel.
- fhir/ (bonus InterSystems): export Patient, Observation (smoking status, pack-years), ImagingStudy/Procedure, Communication.

## Hodnocení (mentor, 16.10. 15:28) — PRIORITY
1. Správná identifikace vzorku pacientů + práce s nedokonalými daty („velké velké plus“).
2. Jednoduchost pro praktiky (často starší lidé): rychlá orientace, velké písmo, málo kroků.
3. JEDNÍM KLIKEM odeslat výzvu přes doporučený kanál.
4. Sledovat, zda k objednání / LDCT skutečně došlo (uzavřená smyčka).
Množství AI ani vzhled nejsou hlavní.

## Další upřesnění (mentor)
- Plánované CT: NEVYLUČOVAT; jakýkoli blízký záznam o CT (minulost i budoucnost) zobrazit lékaři jako upozornění.
- LDCT = screening. LDCT s nálezem k další kontrole → nezvat (už ve sledování), info lékaři.
  Okno pro předchozí LDCT (je už ve screeningu?) — čeká se na odpověď doktorky; konfigurovatelné.
- „Nemá zájem“: NEVYŘAZOVAT. Znovu oslovit jiným kanálem / jiným (motivačním) textem;
  vyřadit až při opakovaném výslovném odmítnutí.
- Data mohou přijít v .xlsx (i celý CSV řádek v jednom sloupci) → loader musí zvládnout CSV i XLSX,
  rozbitou diakritiku i posunuté sloupce.

## Schválené řešení (call s L. Matysem, 16.10. ~15:45 — zelená)
1. Jednoduchá web platforma pro netechnického (často staršího) praktického lékaře.
2. AI komunikační modul — kanály: hlasový AI asistent (Twilio), e-mail, WhatsApp, SMS
   (+ portál, dopis/tisk z dat). Lékař vždy schvaluje odeslání (jeden klik).
   Hlasový asistent: představí se jako asistent ordinace (a že je AI), nesděluje diagnózu,
   jen informuje a zjistí zájem (případně „stiskněte 1“), výsledek zapíše do historie.
   Demo: volat jen na telefony členů týmu (čísla v datech jsou syntetická).
   Fallback, kdyby realtime hlas nestihl: předem namluvený TTS skript + DTMF.
   WhatsApp: obchodně iniciované zprávy vyžadují schválené šablony → v demu sandbox.
3. Matys pomůže s komunikací s paní doktorkou.

## Odpovědi paní doktorky (přes L. Matyse, 16.10. 16:45)
- LDCT se opakuje po roce, při negativním nálezu po dvou letech → pacient s LDCT v tomto intervalu je „už ve screeningu“ (EXCLUDED_RECENT_CT s datem dalšího LDCT).
- Praktik se na seznam dívá 1× týdně → týdenní přepočet + týdenní notifikace.
- Praktik zatím žádanku na screening nevyplňuje: vyplní anamnézu a žádanku k PNEUMOLOGOVI, ten objedná LDCT. Od 1. 7. 2027 by mělo být umožněno i praktikům (pitch: připraveno).
- Praktik je informován o výsledku vyšetření → signál pro uzavření smyčky.
- Zpráva jménem praktika; jednoduchá, nestresující, informativní, motivující – pacient se nesmí leknout.
- Telefonát AI asistentem obecně v pořádku. Výjimky (ruční zařazení) ano.
- Každý praktik má jiný software → interoperabilita a škálování (napojení na EHDS) → FHIR.

## Očekávaný výsledek (REF_DATE 2026-10-16)
ELIGIBLE 101 · EXCLUDED_PACK_YEARS 53 · EXCLUDED_AGE 50 · NEEDS_REVIEW 50 ·
EXCLUDED_SMOKING_STATUS 23 · EXCLUDED_RECENT_CT 23 (sanity check pro testy).

## Zbývající otázky
1. Externí CT a plánované CT — započítat do vyloučení?
2. Diakritika v datech je poškozená (`_`, `�`) — záměr, nebo chyba exportu?

## Prezentace doktorky (MUDr. Čierná Peterová, 16. 10.) – co z ní plyne
- **Zadání (slide 20):** oslovit rizikovou populaci různými cestami; informovat, že program existuje a je **bezplatný**; pozvat k PL či pneumologovi; SMS / e-mail; uvést **telefon PL nebo regionálního pneumologa**; **současně informovat registrujícího PL**, že jeho rizikový pacient byl osloven.
- **Cesta pacienta (slide 10):** PL osloví → ambulantní pneumolog → radiologické screeningové centrum (KOC) → výsledek negativní (opakovaný screening v intervalu) / neurčitý (opakované CT) / pozitivní (POCH). Součástí je **krátká intervence k odvykání kouření**. Ve specifických případech může PL poslat přímo na radiologii.
- **Vykazované výkony PL:** 01196 = pacient odeslán k pneumologovi, 01197 = pacient účast odmítá.
- **Od 2027 (slide 22):** věk **50–80 let**; od 1. 7. 2027 může zařadit L2/L3 libovolné odbornosti, vazba na **sdílený zdravotní záznam**. → engine `Config.policy("2027")` / `--policy 2027`: 122 vhodných místo 101.
- **Problémy (slide 19):** malá účast, riziková populace je větší, nerovnoměrná síť CT, dlouhé čekací doby na CT i u pneumologa.

### Čísla do pitche (NRHZS, 1. 1. 2022 – 31. 3. 2026, věk 55–74)
- Cílová populace ~390 000 (HTA; ~0,5 mil. kuřáků splňuje kritéria). Osloveno **69 925 (~18 %)**, z toho 76,6 % praktikem.
- PL oslovili 53 528 → 54,4 % odesláno k PN (01196), **45,6 % odmítlo (01197)**.
- U pneumologa 35 220, LDCT provedeno 26 411.
- Zapojeno jen **62 % praktiků** (2 698 / 4 328), pneumologů 99 %.
- Výsledky prvního LDCT (N = 23 946): 90 % negativní, 6 % neurčitý, 3 % pozitivní (742). Z pozitivních se záznamem v NOR **51 % ve stadiu 1** – časný záchyt funguje.
- Rakovina plic = nejčastější příčina úmrtí mezi onkologickými diagnózami; ~6 580 nových případů a ~5 010 úmrtí ročně.

## Hranice systému (16. 10. večer)
**Jsme vrstva oslovení a sledování mezi daty praktika a existujícími systémy. Neobjednáváme CT, nerozhodujeme medicínsky.**

| Vlastníme (stavíme) | Napojujeme (předáváme odkazem / API) | Mimo nás |
|---|---|---|
| Identifikace (engine) + důvody, kvalita dat | Data z SW praktika (FHIR in) | Medicínské rozhodnutí (rozhoduje PL) |
| Pracovní seznam PL, výjimky, override | Objednání u PL – existující online rezervace / tel. ordinace (demo: mock stránka termínů) | Objednání LDCT (pneumolog) |
| Oslovení: SMS, e-mail, AI hlas, (WhatsApp) | Objednání u pneumologa – odkaz / telefon regionálního PN | Interpretace výsledku, péče o pozitivní nález (POCH) |
| Porozumění odpovědi pacienta (AI) | Výsledky zpět: FHIR ImagingStudy / DiagnosticReport | Léčba závislosti (jen připomínka PL) |
| Stav cesty pacienta + připomínky | Vykázání 01196 / 01197 v SW praktika (my jen navrhujeme kód) | Vykazování pojišťovně |
| Notifikace + týdenní souhrn pro PL | Sdílený zdravotní záznam / EHDS (od 2027) | |

**Jak víme, že se pacient objednal (kritérium 4), od nejsilnějšího:** webhook z rezervačního systému → událost ve FHIR (Appointment / ServiceRequest / ImagingStudy) → odpověď pacienta („objednal jsem se“) rozpoznaná AI → ruční označení praktikem.

## Odpovědi doktorky na SMS (16. 10. večer) – mění model
1. **Oslovuje centrální systém = náš systém** (automaticky, jménem praktika), ne praktik ručně. Ordinace dostává informaci.
2. **První kontakt v ordinaci je sestra**, předává informace lékaři.
3. **K pneumologovi se pacient objednává sám, u libovolného pneumologa**; pneumologové mají většinou vlastní online objednávání.
4. **Ano** – ve zprávě můžeme nabídnout cestu rovnou k pneumologovi.
5. **Výsledek:** pacient si pro něj většinou přijde a dostane ho do ruky (od radiologa, v budoucnu eŽádanka). Elektronicky jen část praxí, jinak papír / snímky a sestra to přepíše.

### Důsledky pro produkt
- **Role:** **Systém** (každý týden sám najde vhodné a pošle pozvánky; ordinace jen jedním klikem schválí týdenní dávku, plně automatický režim jako volba) → **Sestra** (hlavní uživatel: odpovědi, telefonáty, zápis výsledku) → **Lékař** (jen rozhodnutí: kontrola, výjimky, vyřazení). Přehled programu za všechny ordinace zůstává jako pohled pro pojišťovnu / koordinátora, nikoho neoslovuje.
- **Zpráva pacientovi nabízí 2 cesty:** objednat se rovnou u pneumologa (odkaz na seznam center, např. VZP) nebo zavolat do své ordinace.
- **Sledování bez webhooku od pneumologa:** (a) pacient sám klikne „Už jsem objednaný/á“ v odkazu nebo odpoví SMS (AI rozpozná), (b) centrálně vykázané výkony z dat pojišťovny (25507 pneumolog, 89663–89665 LDCT) – zpoždění týdny, ale spolehlivé, (c) sestra zapíše ručně.
- **Výsledek zapisuje sestra jedním klikem:** negativní / neurčitý / pozitivní → engine spočítá další termín (2 roky / dle PN / mimo program).

## Odpovědi Matyse (16. 10. 17:41)
- Hodnotí se **aplikace**, ne detail dat; víkend = prototyp. Skutečná práce začne po víkendu s týmem, který bude chtít pokračovat – AZ podá pomocnou ruku. **Vlastníkem řešení jsme my.**
- Živá SMS / AI hovor v demu: ano, klidně na Matyse nebo doktorku – „live demo se občas může vymstít“ → mít záložní video.
- Stejný telefon a e-mail u všech pacientů je záměr (randomizace). Patient portal = ideální stav, teď ignorovat.
- **Zákazník: praktičtí lékaři**, později nemocnice. **Plátce: pojišťovny.**
- Hranice systému (najít, oslovit, hlídat; objednání a CT existujícím systémům, FHIR) – potvrzeno.
- Doktorka uvidí rozhraní zítra jen **online** (přijede až v neděli) → potřebujeme veřejný odkaz.
- Výzva se v systému jmenuje **„Cesta ke screeningu plic“ (AstraZeneca)**; v Praze ji k 16. 10. odpoledne neměl žádný tým.
