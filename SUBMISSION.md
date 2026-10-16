# Odevzdání – submit.rakathon.cz (do soboty 13:00)

## 1 · Projekt
**Název:** Plíce včas

**Krátký popis (CZ, 112 znaků):**
Najde pacienty pro screening plic, osloví je jménem praktika (SMS, AI hovor) a pohlídá, aby došli až k výsledku.

**Short description (EN, 127 chars):**
Finds patients eligible for lung cancer screening, invites them in the GP's name (SMS, AI call) and follows them to the result.

**Delší popis (CZ):**
Program Prevence pro plíce funguje – 51 % zachycených nádorů je ve stadiu 1 – ale za čtyři roky oslovil jen asi 18 % cílové populace a téměř polovina oslovených odmítne. Plíce včas je tenká vrstva nad daty praktika:
1. **Najde** vhodné pacienty podle kritérií programu (55–74 let, kuřák/bývalý kuřák, ≥ 20 balíčkoroků, bez CT hrudníku za 30 dní, LDCT interval 1 / 2 roky) i v nedokonalých datech – opraví poškozené řádky a diakritiku, rozporné údaje označí a u každého rozhodnutí ukáže důvod.
2. **Osloví** je jménem praktika: sestra jednou týdně jedním klikem schválí dávku pozvánek, každá jde kanálem doporučeným podle historie pacienta (SMS, AI hovor, WhatsApp, e-mail, dopis). Texty jsou klidné a nestresující (dle garantky výzvy).
3. **Pohlídá** cestu pacienta: plán kontaktů (SMS → hovor → hovor → WhatsApp → sestra osobně) běží sám, dokud pacient neodpoví; AI porozumí odpovědi („ano, ale až po Vánocích“), pacient může odpovědět i přes osobní odkaz; sestra vidí Pozván → Odpověděl → Objednán → LDCT → Výsledek a zapíše výsledek z papírové zprávy, systém naplánuje další LDCT.
Výjimky a kontrolu rozporných údajů má vždy lékař. Data se napojují přes FHIR R4, takže řešení funguje nad různými systémy praktiků a je připravené na sdílený zdravotní záznam (EHDS, změny od 2027 – věk 50–80 je jen přepínač).

**Longer description (EN):**
The Czech lung screening programme works – 51 % of detected cancers are stage 1 – yet in four years it reached only ~18 % of the target population and almost half of those invited decline. Plíce včas is a thin layer on top of GP data: it **finds** eligible patients even in messy records (repairs broken rows and encoding, flags conflicts, explains every decision), **invites** them in the GP's name after a one-click weekly approval by the nurse, choosing the channel from each patient's history (SMS, AI phone call, WhatsApp, e-mail, letter), and **follows** each patient until the result: an automatic contact plan runs until the patient answers, AI understands free-text and spoken replies, and the nurse sees Invited → Replied → Booked → LDCT → Result. Doctors keep control of exceptions and conflicting data. FHIR R4 export makes it work across different GP systems and ready for EHDS.

## 3 · Dopad a AI
**Jak využíváte AI?**
- **Porozumění odpovědím pacientů** (SMS, WhatsApp, odkaz, řeč v hovoru): LLM určí záměr (zájem / objednán / zavolat / teď ne / nechci / dotaz) a „kdy“, a sestře napíše krátké zdůvodnění. Bezpečnost: odhlášení („STOP“) rozhodují pravidla vždy, nejistá odpověď jde sestře, výpadek AI → pravidla.
- **AI telefonní asistent v češtině** (Twilio ConversationRelay): pozve pacienta, odpoví na časté dotazy (cena, bolest, záření) – ale **jen schválenými větami**, nic si nevymýšlí; co nezná, předá sestře.
- **Doporučení kanálu** podle historie kontaktů (co pacient čte, co selhalo) a plán kontaktů, který se zastaví při první odpovědi.
- AI nikdy nerozhoduje o zařazení ani o oslovení – to dělají pravidla programu a člověk (human in the loop).

**Jaký dopad a pro koho?**
- **Pacienti 55–74 let s kuřáckou anamnézou** – víc z nich se dozví o bezplatném vyšetření a dojde až k LDCT; rakovina plic je nejčastější příčina úmrtí mezi nádory (≈ 5 000 úmrtí ročně v ČR), včasný záchyt vede k vyléčení.
- **Praktičtí lékaři a sestry** – místo ručního hledání v kartotéce jeden týdenní seznam, jedno kliknutí, přehled kdo došel; kód výkonu 01196/01197 na jednom místě. Zapojeno je zatím jen 62 % praktiků.
- **Pojišťovny a program** – měřitelný trychtýř od dat k výsledku, škálovatelné přes FHIR.

**FHIR od InterSystems?**
Ano. Data výzvy i naše vyhodnocení exportujeme jako FHIR R4 transaction Bundle (Patient, Observation – kuřácký status, balíčkoroky, vyhodnocení kritérií; ImagingStudy – CT; Communication – kontakty; Task – úkol pro ordinaci) a nahráváme do IRIS z hackathon kitu (`scripts/fhir_export.py --post`). Bundle je validovaný proti modelům R4 v testech.

## 4 · Odkazy a obrázek
- Titulní obrázek 16:9: `submission/title.png`
- GitHub: _doplnit po vytvoření repozitáře_
- Demo: _veřejná adresa po nasazení_
- Video: `submission/demo.webm` (záložní záznam ukázky)

---

## Ukázka u stolu (sobota 14:00, 3 minuty) – scénář
1. **Problém (20 s):** „Program funguje – polovina záchytů ve stadiu 1 – ale oslovilo se jen 18 % lidí a polovina odmítne. Praktik nemá čas hledat v kartotéce.“
2. **Data (30 s):** Přehled programu → kvalita dat: 28 poškozených řádků, 1 146 opravených hodnot, rozporné balíčkoroky → u pacienta „Podrobnosti“: důvod každého rozhodnutí.
3. **Jedno kliknutí (30 s):** Ordinace → „Tento týden odejde 5 pozvánek“ → Schválit a odeslat. *(Naostro: SMS / AI hovor na telefon Luboše Matyse.)*
4. **Odpověď (40 s):** Matys odpoví „Ano, ale až po Vánocích“ nebo v hovoru se zeptá „kolik to stojí?“ → na obrazovce se sám přesune pacient, AI ukáže proč.
5. **Smyčka (40 s):** „Posunout čas o den“ ×3 → systém sám volá, píše WhatsApp, nakonec úkol pro sestru → objednán → LDCT → Negativní → „další LDCT od 2028“.
6. **Škálování (20 s):** FHIR export do IRIS, pravidla 2027 jedním přepínačem, „chceme v tom pokračovat s AstraZeneca“.

**Záloha, když selže síť nebo Twilio:** tlačítka „Ukázka – odpověď pacienta“ (stejná cesta jako webhook) + video `submission/demo.webm`.
