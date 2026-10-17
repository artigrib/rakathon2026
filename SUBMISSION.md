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
1. Najde pacienty, kteří splňují kritéria programu: 55 až 74 let, kuřák nebo bývalý kuřák, alespoň 20 balíčkoroků, bez CT hrudníku za posledních 30 dní. Poškozené řádky a diakritiku opraví, rozporné údaje označí a u každého rozhodnutí uvede důvod.
2. Osloví je jménem praktika. Sestra jednou týdně jedním kliknutím schválí pozvánky, nebo pacienta kontaktuje hned: SMS, hovor hlasového asistenta, WhatsApp nebo e-mail. Kanál doporučí podle historie pacienta.
3. Hlídá, aby se nikdo neztratil. Když pacient neodpoví, systém ho podle plánu kontaktuje znovu a nakonec předá sestře. Odpověď pacienta rozpozná a zařadí. Kdo se ztrácí (předán k pneumologovi a 6 týdnů bez výsledku, zpráva nedoručena, plán skončil), je nahoře v úkolech. U každého pacienta je celá komunikace na jednom místě.
Lékař má vlastní jednoduchou obrazovku: rozhodnutí o zařazení, výsledky k převzetí a kódy 01196 a 01197 k vykázání.
Cesta pacienta je stavový automat: první odmítnutí je měkké a nabídka se zopakuje za 3 měsíce, odmítnutí 01197 až napodruhé, pozdní odpověď nic nevrátí zpět. Po negativním výsledku pacienta za dva roky sám znovu zařadí k pozvání na kontrolní LDCT, protože screening funguje jen při pravidelném opakování. Výjimky rozhoduje lékař. Data čte a zapisuje přes FHIR R4 (InterSystems IRIS for Health), takže funguje nad různými systémy praktiků.

**Longer description (EN):**
The Czech lung screening programme works: 51 % of cancers found by screening are stage 1. In four years it reached only about 18 % of the target population, and almost half of those invited declined.
Plíce včas runs on GP data and does three things. It finds eligible patients by the programme criteria, repairs broken records, flags conflicting data and states the reason for every decision. It invites them in the GP's name: the nurse approves a weekly batch in one click or contacts a patient right away by SMS, AI phone call, WhatsApp or e-mail, with the channel recommended from the patient's history. It makes sure nobody gets lost: a fixed contact plan follows up and finally hands over to the nurse, replies are classified, patients who are getting lost come first, and every patient has the whole communication in one place. The journey is a state machine (soft first refusal, no going back on late replies). Data is read from and written back to a FHIR R4 server (InterSystems IRIS for Health).

## 3. Dopad a AI
**Jak využíváte AI?**
- Rozpoznání odpovědi pacienta (SMS, WhatsApp, odkaz, řeč v hovoru): pevná pravidla a volitelně jazykový model určí, co pacient chce (má zájem, už je objednaný, chce zavolat, teď ne, nechce, ptá se) a kdy. „Ano, ale až po Vánocích“ zapíše jako „teď ne“. Odhlášení („STOP“) rozhodují vždy pravidla. Nejistou odpověď dostane sestra.
- Hlasový asistent v češtině (hlas ElevenLabs, telefonie Twilio): pozve pacienta a rozumí odpovědi hlasem i klávesou. Mluví jen předem schválenými větami.
- O zařazení pacienta a o odeslání pozvánky AI nerozhoduje. Rozhodují pravidla programu a člověk.

**Jaký dopad a pro koho?**
- Pacienti 55 až 74 let s kuřáckou anamnézou: víc z nich se dozví o bezplatném vyšetření a dojde k LDCT. Rakovina plic je nejčastější příčina úmrtí na nádorová onemocnění v ČR, ročně asi 5 000 úmrtí. V datech výzvy: dnes by se oslovilo 18 ze 101 vhodných, s Plíce včas všech 101.
- Praktičtí lékaři a sestry: jeden týdenní seznam úkolů místo ručního hledání v kartotéce, nikdo se neztratí. Do programu je zatím zapojeno 62 % praktiků.
- Pojišťovny a program: přehled od dat po výsledek pro každou ordinaci a který kanál funguje.

**FHIR od InterSystems?**
Ano, oběma směry. Data výzvy i naše vyhodnocení nahráváme do InterSystems IRIS for Health jako FHIR R4 (Patient, Observation pro kouření, balíčkoroky a vyhodnocení, ImagingStudy pro CT, Communication pro kontakty, Task pro ordinaci). Původní sloupce z NIS zůstávají jako rozšíření, takže aplikace pacienty z IRIS načte zpět bez ztráty a vyhodnotí stejným enginem (ověřeno testem na všech 300 pacientech). Každý krok cesty pacienta zapisuje zpět: Communication pro pozvánku i odpověď pacienta, Task se stavem.

## 4. Odkazy a obrázek
- Titulní obrázek 16:9: `submission/title.png`
- GitHub: https://github.com/artigrib/rakathon2026
- Demo: https://watched-intermediate-perth-dns.trycloudflare.com (ověřit před odevzdáním, adresa se mění po restartu tunelu)
  Přihlášení pro porotu: uvést do pole pro porotu, ne veřejně (data výzvy).
- Video: `submission/demo.mp4` (záložní záznam ukázky)

---

## Ukázka u stolu (sobota 14:00, 3 minuty)
1. Problém (20 s): program funguje, polovina záchytů je ve stadiu 1, ale oslovilo se jen 18 % lidí a polovina odmítla.
2. Úkoly (20 s): nahoře „nikdo se neztrácí“ nebo kdo se ztrácí a proč. Sestra vidí jen to, co má udělat.
3. Čtyři kanály naostro (50 s): u čtyř pacientů Kontaktovat a pokaždé jiný kanál: Poslat SMS teď, Zavolat teď, Poslat WhatsApp teď, Poslat e-mail teď. Vše přijde na demo telefon a demo e-mail.
4. Odpověď (40 s): na SMS odpovědět „Ano“, přijde potvrzení a pacient se sám přesune do Ozvali se. V hovoru říct „ano“. Kliknout na pacienta: celá komunikace na jednom místě, odpověď doslova a co systém zapsal. Pak Předán k pneumologovi (01196).
4b. Pro lékaře (15 s): co lékař rozhodne, výsledky k převzetí, kódy 01196 a 01197 za týden.
5. Data a FHIR (30 s): Přehled programu, Dopad (18 oproti 101), který kanál funguje. Patička: data z FHIR serveru IRIS, zpět zapsáno N záznamů.
6. Další rozvoj (20 s): pravidla od roku 2027 jedním přepínačem, napojení na další systémy přes FHIR, chceme pokračovat s AstraZeneca.

Před ukázkou: otevřít demo adresu (tunel se po restartu mění), /api/health musí ukázat "mode":"live", telefon nabitý a se zvukem.

Záloha, když selže síť nebo Twilio: simulace odpovědí v panelu Ukázka a video `submission/demo.mp4`.
