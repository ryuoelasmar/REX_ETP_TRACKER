from __future__ import annotations
from pathlib import Path
from tqdm import tqdm
from .sec_client import SECClient
from .step2 import step2_submissions_and_prospectus
from .step3 import step3_extract_for_trust
from .step4 import step4_rollup_for_trust

def run_pipeline(ciks: list[str], overrides: dict | None = None, since: str | None = None, until: str | None = None,
                 output_root: Path | str = "outputs", cache_dir: Path | str = "http_cache",
                 user_agent: str | None = None, request_timeout: int = 45, pause: float = 0.35,
                 refresh_submissions: bool = True, refresh_max_age_hours: int = 6, refresh_force_now: bool = False) -> int:
    output_root = Path(output_root); cache_dir = Path(cache_dir)
    output_root.mkdir(parents=True, exist_ok=True); cache_dir.mkdir(parents=True, exist_ok=True)
    if not user_agent: user_agent = "REX-SEC-Filer/1.0 (contact: set USER_AGENT)"
    client = SECClient(user_agent=user_agent, request_timeout=request_timeout, pause=pause, cache_dir=cache_dir)

    trusts = step2_submissions_and_prospectus(
        client=client, output_root=output_root, cik_list=ciks, overrides=overrides or {},
        since=since, until=until, refresh_submissions=refresh_submissions,
        refresh_max_age_hours=refresh_max_age_hours, refresh_force_now=refresh_force_now
    )

    for t in tqdm(trusts, desc="Extract (Step 3)", leave=False):
        step3_extract_for_trust(client, output_root, t)

    for t in tqdm(trusts, desc="Roll-up (Step 4)", leave=False):
        step4_rollup_for_trust(output_root, t)

    return len(trusts)
