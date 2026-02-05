# ETP Filing Tracker (Modular)

This refactors the monolithic engine into logical modules:

- `config.py` — constants and global config
- `utils.py` — helpers and normalization
- `csvio.py` — robust CSV IO
- `paths.py` — output file layout + SEC URL builders
- `sec_client.py` — cached HTTP client + submissions JSON loader
- `sgml.py` — **authoritative** SGML parser for `<NEW-SERIES>` / `<SERIES>`
- `body_extractors.py` — HTML/PDF text helpers, document iterators
- `step2.py` — submissions and prospectus subset
- `step3.py` — fund extraction (series-anchored ticker detection, effective date capture)
- `step4.py` — roll-up (BPOS > APOS, APOS+75 fallback)

Run the pipeline:

```python
from etp_tracker.run_pipeline import run_pipeline
run_pipeline(
    ciks=["2043954"],  # REX ETF Trust
    user_agent="REX-SEC-Filer/1.0 (contact: your-email)"
)
```
