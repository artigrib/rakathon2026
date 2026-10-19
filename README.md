# Jsem včas — jedno jádro, tři případy

Jedno jádro (`backend/`, `web/app/`, `engine/`) a balíčky případů v `cases/<id>/` (texty, journey, dialog, kadence,
obrazovky, data; kontrakt v [`cases/README.md`](cases/README.md)). Jeden proces = jeden případ, volí ho proměnná `CASE`
(výchozí `screening`).

| Případ | `CASE` | Lokálně (`make run`) | Docker (`deploy/docker-compose.yml`) | Veřejně (návrh, viz `deploy/OPERATIONS.md`) |
|---|---|---|---|---|
| Plíce včas — screening karcinomu plic | `screening` | http://localhost:8000/app/ | `app`, 127.0.0.1:8000 | https://jsemvcas.cz/app/ (produkce) |
| Senioři — pravidelný kontakt | `seniors` | http://localhost:8001/app/ | `app-seniors`, 127.0.0.1:8001 (profil `cases`) | https://seniori.jsemvcas.cz/app/ |
| Vymáhání — dlužníci | `collections` | http://localhost:8002/app/ | `app-collections`, 127.0.0.1:8002 (profil `cases`) | https://vymahani.jsemvcas.cz/app/ |

Každý případ jedním příkazem (z kořene repozitáře, Python z `.venv`, jinak `PY=python3`):

```bash
make data CASE=seniors && make run CASE=seniors     # data případu + server na :8001
make test CASE=seniors                               # jádro + kontrakt všech případů + cases/seniors/tests
make test-all                                        # testy všech cases/*/case.json
make up-all                                          # docker: screening + seniors + collections (make up = jen screening)
make agent CASE=seniors                              # hlasový agent ElevenLabs z cases/seniors/dialog.py
```

Bez Makefile: `CASE=seniors python -m cases.seniors.build`, `CASE=seniors python -m uvicorn backend.app:app --port 8001`.
Vlastní klíče případu (`PUBLIC_URL`, `DEMO_PASSWORD`, `ELEVENLABS_AGENT_ID` …) patří do `cases/<id>/.env` (gitignored),
společné do `backend/.env`.

---

## Plíce včas (screening) — engine

Identifikace pacientů pro screening karcinomu plic (Prevence pro plíce) + doporučení kontaktu.

Data výzvy (AstraZeneca) nejsou v repozitáři: zkopírujte je do `data/` a spusťte `make data` (= `python -m cases.screening.build`, dříve `python scripts/build_web_data.py`).

```bash
pip install openpyxl pytest
python -m engine data --ref-date 2026-10-16 -o examples/run_result.json   # JSON dle CONTRACT.md
python -m pytest -q                                                        # CASE=screening: engine, backend, plán kontaktů, FHIR, kontrakt případů
```

- `engine/loader.py` — CSV i XLSX, řádky obalené v uvozovkách, celý CSV řádek v jedné buňce, chybějící sloupec (oprava + záznam do `data_issues`).
- `engine/rules.py` — stavy dle README výzvy, české důvody, flagy (CT poblíž, plánované/zrušené CT, LDCT s nálezem, rozporné balíčkoroky). Pravidla potvrzena mentorem 16.10.
- `engine/channel.py` — další krok a kanál podle historie (selhaný kanál se znevýhodní, přečtený upřednostní; zájem → úkol pro lékaře; 1× nezájem → jiný kanál + motivační text; 2× → nekontaktovat).
- `CONTRACT.md` — formát výstupu pro backend/frontend; `examples/run_result.json` = reálný výstup nad daty výzvy.

Výsledek nad daty výzvy (16.10.2026): ELIGIBLE 101 · NEEDS_REVIEW 50 · EXCLUDED_PACK_YEARS 53 · EXCLUDED_AGE 50 · EXCLUDED_SMOKING_STATUS 23 · EXCLUDED_RECENT_CT 23.
Konfigurovatelné v `Config` (věk, balíčkoroky, okno CT 30 dní, interval LDCT 1 rok / 2 roky při negativním nálezu – dle doktorky).

Backend + Twilio (SMS, hovor, webhooky odpovědí): viz `backend/README.md` – `make run` (= `python -m uvicorn backend.app:app --port 8000`).
