from __future__ import annotations
from pathlib import Path
import pandas as pd

def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)

def append_dedupe_csv(path: Path, df_new: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    if path.exists() and path.stat().st_size:
        df_old = pd.read_csv(path, dtype=str)
    else:
        df_old = pd.DataFrame(columns=df_new.columns)
    all_df = pd.concat([df_old, df_new], ignore_index=True)
    all_df = all_df.drop_duplicates(subset=key_cols, keep="last")
    write_csv(path, all_df)
    return all_df
