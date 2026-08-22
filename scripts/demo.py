"""Walkthrough: the API quota insight, then the star model and a result.

    python scripts/demo.py
"""

from __future__ import annotations

import polars as pl

from sunedu import build_model, estimate_requests

pl.Config.set_ascii_tables(True)
pl.Config.set_tbl_rows(8)

DATA = "sample_data"


def rule(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    rule("1. Know when the API is the wrong tool (quota = 1000 req/month)")
    for name, rows in [("one institution", 5_000), ("national postulantes", 4_100_000)]:
        needed = estimate_requests(rows)
        verdict = "fits" if needed <= 1000 else "does NOT fit -> use bulk microdata"
        print(f"  {name:<22} {rows:>9,} rows = {needed:>5,} requests -> {verdict}")

    rule("2. Build the star model (validations fail loud)")
    result = build_model(DATA)
    tables, report = result["tables"], result["report"]
    for tname, df in tables.items():
        print(f"  {tname:<18} {df.height:>3} rows")
    worst = max(max(r.values()) for r in report["orphan_rates"].values())
    print(f"  max orphan rate across facts: {worst:.1%}")

    rule("3. Result: admission rate (lower = more selective)")
    ing = tables["Fact_Ingresantes"].group_by("CODIGO_INEI").agg(pl.col("CANTIDAD").sum().alias("ingresantes"))
    pos = tables["Fact_Postulantes"].group_by("CODIGO_INEI").agg(pl.col("CANTIDAD").sum().alias("postulantes"))
    out = (
        ing.join(pos, on="CODIGO_INEI")
        .join(tables["Dim_Universidad"].select("CODIGO_INEI", "UNIVERSIDAD"), on="CODIGO_INEI")
        .with_columns((pl.col("ingresantes") / pl.col("postulantes")).round(3).alias("tasa_admision"))
        .select("UNIVERSIDAD", "ingresantes", "postulantes", "tasa_admision")
        .sort("tasa_admision")
    )
    print(out)


if __name__ == "__main__":
    main()
