# Backend – Twilio (SMS + hlasový hovor)

Servíruje web aplikaci, posílá pozvánky přes Twilio a přijímá odpovědi pacientů (webhooky).
Bez klíčů běží v **testovacím režimu** – nic neodchází, vše ostatní funguje.

## Spuštění (5 min)
```bash
pip install fastapi uvicorn python-multipart twilio
python -m uvicorn backend.app:app --port 8000      # z kořene projektu
# otevřít http://localhost:8000  → patička ukáže „testovací režim“
```

## Živý režim
1. `ngrok http 8000` → zkopírovat https adresu.
2. `cp backend/.env.example backend/.env` a vyplnit: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `PUBLIC_URL` (ngrok), `DEMO_TO` (ověřený telefon pro demo).
3. Twilio Console → Phone Numbers → naše číslo → **Messaging → A message comes in** → `POST {PUBLIC_URL}/twilio/sms` (hlas nastavovat netřeba – URL posíláme při každém hovoru).
4. Twilio Console → Messaging i Voice → **Geo permissions**: povolit Česko.
5. Restart uvicornu → patička ukáže „Živý režim“.

`LIVE_LIMIT=1`: z jednoho kliknutí odejde naostro jen 1 zpráva / hovor (ostatní simulovaně), ať demo telefon nezahltíme.

## Co se děje
| Kliknutí / událost | Endpoint | Výsledek |
|---|---|---|
| „Schválit a odeslat“ | `POST /api/send` | SMS nebo hovor přes Twilio, záznam do historie |
| Pacient odpoví SMS | `POST /twilio/sms` | text → `replies.classify` → stav pacienta (zájem / objednán / zavolat / teď ne / odmítá) |
| Doručení SMS | `POST /twilio/status` | doručeno / nedoručeno v historii |
| Hovor | `POST /twilio/voice/{id}` | přečte skript, čeká na 1 / 2 nebo řeč |
| Odpověď v hovoru | `POST /twilio/voice/{id}/answer` | stejné pochopení odpovědi jako u SMS |
| Nikdo nezvedl | `POST /twilio/call-status/{id}` | „nedoručeno“ v historii |

Web se každé 3 s ptá `GET /api/state` – změna z webhooku se ukáže sama.

## Pravidla odpovědí (doktorka)
1. „nemám zájem“ → *teď ne* (jiný kanál s motivačním textem), 2. odmítnutí → *odmítá (01197)*.
„STOP / nepište / nevolejte“ → hned konec. Dotaz nebo nejasná odpověď → sestře, nikdy automatická odpověď.

## AI
- **Porozumění odpovědím** (`backend/llm.py`, `replies.understand`): LLM (Anthropic / OpenAI / Azure OpenAI dle `.env`)
  určí záměr pacienta + „kdy“ + krátké zdůvodnění pro sestru. Bezpečnost: „STOP / nepište“ rozhodují pravidla vždy,
  nejistá odpověď AI jde sestře, výpadek AI → pravidla.
- **AI hovor** (`VOICE_MODE=relay`): Twilio ConversationRelay (čeština) ↔ WebSocket `/ws/relay/{id}`. AI jen rozumí;
  asistent mluví výhradně schválenými větami (`backend/voice_ai.py`), na dotazy (cena, bolest, záření…) odpovídá z FAQ,
  jinak předá sestře. Záložní režim `gather` = přečte skript a čeká na 1 / 2.

## Hlas (ElevenLabs)
S `ELEVENLABS_API_KEY` v `.env` hovor mluví přirozenou češtinou z ElevenLabs (Twilio přehraje MP3 přes `<Play>`).
Zvuk se generuje při zahájení hovoru a ukládá do mezipaměti, každá věta jen jednou. Při chybě se použije hlas Twilio.
Hlas: v ElevenLabs Voice Library vybrat hlas, který zní dobře česky, a jeho ID dát do `ELEVENLABS_VOICE_ID`
(použije se i v režimu `VOICE_MODE=relay`). Před ukázkou předgenerovat: `python -m backend.tts`.

## Stránka pro pacienta
SMS obsahuje osobní odkaz `/p/{token}` (bez ID a zdravotních údajů v URL i na stránce):
„Ano, mám zájem · Už jsem objednaný/á · Zavolejte mi · Teď ne · Nepřeji si další zprávy“ → stejná cesta jako webhook.

## Nasazení (VPS / Azure / Render)
```bash
docker build -t plice-vcas .
docker run -d --name plice -p 8000:8000 --env-file backend/.env -v plice-data:/data plice-vcas
# HTTPS: Caddy  (caddy reverse-proxy --from demo.example.cz --to :8000)
#   nebo Cloudflare Tunnel (cloudflared tunnel --url http://localhost:8000) → PUBLIC_URL
```
Render/Railway: stačí Dockerfile; vypnout uspávání (Twilio čeká na webhook max. 15 s).

## Plán kontaktů a čas v ukázce
`POST /api/tick {"days": 1}` posune den ukázky a provede vše, co je podle plánu na řadě
(0 SMS → 3 hovor → 5 hovor → 8 WhatsApp → 12 úkol pro sestru; odpověď plán zastaví). V produkci totéž dělá cron každých 15 min.

## FHIR
`GET /api/fhir?gp=VPL-0142` → FHIR R4 transaction Bundle (Patient, Observation kouření + balíčkoroky + vyhodnocení,
ImagingStudy, Communication, Task). Nahrání do IRIS z hackathon kitu:
`python scripts/fhir_export.py --post http://localhost:52773/fhir/r4 --user _SYSTEM --password …`
