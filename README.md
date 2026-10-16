# Plíce včas — engine

Identifikace pacientů pro screening karcinomu plic (Prevence pro plíce) + doporučení kontaktu.

Data výzvy (AstraZeneca) nejsou v repozitáři: zkopírujte je do `data/` a spusťte `python scripts/build_web_data.py`.

```bash
pip install openpyxl pytest
python -m engine data --ref-date 2026-10-16 -o examples/run_result.json   # JSON dle CONTRACT.md
python -m pytest -q                                                        # 82 testů (engine, backend, plán kontaktů, FHIR)
```

- `engine/loader.py` — CSV i XLSX, řádky obalené v uvozovkách, celý CSV řádek v jedné buňce, chybějící sloupec (oprava + záznam do `data_issues`).
- `engine/rules.py` — stavy dle README výzvy, české důvody, flagy (CT poblíž, plánované/zrušené CT, LDCT s nálezem, rozporné balíčkoroky). Pravidla potvrzena mentorem 16.10.
- `engine/channel.py` — další krok a kanál podle historie (selhaný kanál se znevýhodní, přečtený upřednostní; zájem → úkol pro lékaře; 1× nezájem → jiný kanál + motivační text; 2× → nekontaktovat).
- `CONTRACT.md` — formát výstupu pro backend/frontend; `examples/run_result.json` = reálný výstup nad daty výzvy.

Výsledek nad daty výzvy (16.10.2026): ELIGIBLE 101 · NEEDS_REVIEW 50 · EXCLUDED_PACK_YEARS 53 · EXCLUDED_AGE 50 · EXCLUDED_SMOKING_STATUS 23 · EXCLUDED_RECENT_CT 23.
Konfigurovatelné v `Config` (věk, balíčkoroky, okno CT 30 dní, interval LDCT 1 rok / 2 roky při negativním nálezu – dle doktorky).

Backend + Twilio (SMS, hovor, webhooky odpovědí): viz `backend/README.md` – `python -m uvicorn backend.app:app --port 8000`.
