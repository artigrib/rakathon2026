# Odevzdání na submit.rakathon.cz (do soboty 13:00)

## 1. Projekt
**Název:** Plíce včas

**Krátký popis (CZ, 112 znaků):**
Najde pacienty pro screening plic, osloví je jménem praktika a pohlídá, aby došli až k výsledku.

**Short description (EN, 127 chars):**
Finds patients eligible for lung cancer screening, invites them in the GP's name and follows them to the result.

**Delší popis (CZ):**
Program Prevence pro plíce funguje: 51 % nádorů zachycených screeningem je ve stadiu 1. Za čtyři roky ale oslovil jen asi 18 % cílové populace a téměř polovina oslovených odmítla.
Plíce včas pracuje nad daty praktického lékaře a dělá tři věci:
1. Najde pacienty, kteří splňují kritéria programu: 55 až 74 let, kuřák nebo bývalý kuřák, alespoň 20 balíčkoroků, bez CT hrudníku za posledních 30 dní, interval LDCT 1 rok, po negativním výsledku 2 roky. Poškozené řádky a diakritiku opraví, rozporné údaje označí a u každého rozhodnutí uvede důvod.
2. Osloví je jménem praktika. Sestra jednou týdně jedním kliknutím schválí pozvánky. Každá jde kanálem podle historie pacienta: SMS, hlasový asistent, WhatsApp, e-mail nebo dopis.
3. Hlídá, jestli pacient došel až k výsledku. Pokud neodpoví, systém ho podle plánu kontaktuje znovu a nakonec předá sestře. Odpověď pacienta systém rozpozná a zařadí. Sestra zapíše výsledek LDCT a systém naplánuje další termín.
Výjimky a rozporné údaje vždy rozhoduje lékař. Data se předávají ve formátu FHIR R4, takže řešení funguje nad různými systémy praktiků.

**Longer description (EN):**
The Czech lung screening programme works: 51 % of cancers found by screening are stage 1. In four years it reached only about 18 % of the target population, and almost half of those invited declined.
Plíce včas runs on GP data and does three things. It finds eligible patients by the programme criteria, repairs broken records, flags conflicting data and states the reason for every decision. It invites them in the GP's name after a weekly one-click approval by the nurse, each through the channel that fits the patient's history. It follows each patient to the result: if there is no reply, a fixed contact plan tries again and finally hands over to the nurse; replies are classified automatically; the nurse records the LDCT result and the next date is scheduled. Doctors decide exceptions and conflicting data. Data is exchanged as FHIR R4.

## 3. Dopad a AI
**Jak využíváte AI?**
- Rozpoznání odpovědi pacienta (SMS, WhatsApp, odkaz, řeč v hovoru): jazykový model určí, co pacient chce (má zájem, už je objednaný, chce zavolat, teď ne, nechce, ptá se) a kdy. Odhlášení („STOP“) rozhodují vždy pevná pravidla. Nejistou odpověď dostane sestra. Když model není dostupný, použijí se pravidla.
- Hlasový asistent v češtině (Twilio ConversationRelay): pozve pacienta a odpoví na časté dotazy (cena, bolest, záření) pouze předem schválenými větami. Na ostatní dotazy odpoví sestra.
- O zařazení pacienta a o odeslání pozvánky AI nerozhoduje. Rozhodují pravidla programu a člověk.

**Jaký dopad a pro koho?**
- Pacienti 55 až 74 let s kuřáckou anamnézou: víc z nich se dozví o bezplatném vyšetření a dojde k LDCT. Rakovina plic je nejčastější příčina úmrtí na nádorová onemocnění v ČR, ročně asi 5 000 úmrtí.
- Praktičtí lékaři a sestry: jeden týdenní seznam úkolů místo ručního hledání v kartotéce. Do programu je zatím zapojeno 62 % praktiků.
- Pojišťovny a program: přehled od dat po výsledek pro každou ordinaci.

**FHIR od InterSystems?**
Ano. Data výzvy i naše vyhodnocení exportujeme jako FHIR R4 transaction Bundle (Patient, Observation pro kuřácký status, balíčkoroky a vyhodnocení, ImagingStudy pro CT, Communication pro kontakty, Task pro ordinaci) a nahráváme do IRIS z hackathon kitu (`scripts/fhir_export.py --post`). Strukturu Bundle ověřují testy proti modelům R4.

## 4. Odkazy a obrázek
- Titulní obrázek 16:9: `submission/title.png`
- GitHub: https://github.com/artigrib/rakathon2026
- Demo: https://watched-intermediate-perth-dns.trycloudflare.com (ověřit před odevzdáním, adresa se mění po restartu tunelu)
- Video: `submission/demo.mp4` (záložní záznam ukázky)

---

## Ukázka u stolu (sobota 14:00, 3 minuty)
1. Problém (20 s): program funguje, polovina záchytů je ve stadiu 1, ale oslovilo se jen 18 % lidí a polovina odmítla.
2. Dopad a data (30 s): Přehled programu, tabulka Dopad (dnes 18 oslovených, s námi 101). Kvalita dat: poškozené řádky a diakritika opraveny, rozporné balíčkoroky rozhodne lékař. U pacienta důvod každého rozhodnutí.
3. Odeslání naostro (30 s): Úkoly, Pozvat, u pacienta Upravit, SMS, Odeslat. SMS přijde na telefon Artema (zkušební účet Twilio posílá jen na ověřené číslo). Matysovi ukázat telefon.
4. Odpověď (40 s): odpovědět „Ano“. Přijde potvrzení a pacient se sám přesune do Ozvali se. Pak u dalšího pacienta telefonát asistenta: zvednout, stisknout klávesu, asistent mluví česky, odpovědět „ano“ hlasem nebo stisknout 1.
5. Další kroky (40 s): v panelu Ukázka několikrát Další den. Systém sám volá, pošle WhatsApp a nakonec předá úkol sestře. Pak objednán, LDCT, negativní výsledek, další LDCT za 2 roky.
6. Další rozvoj (20 s): export FHIR do IRIS, pravidla od roku 2027 jedním přepínačem, chceme pokračovat s AstraZeneca.

Před ukázkou: otevřít demo adresu (tunel se po restartu mění), /api/health musí ukázat "mode":"live", telefon nabitý a se zvukem.

Záloha, když selže síť nebo Twilio: simulace odpovědí v panelu Ukázka a video `submission/demo.mp4`.
