"""Build the star model from CSV microdata and print the validation report.

    python scripts/build.py [data_dir]

Defaults to the bundled sample_data/. Also prints the selectivity (admission
rate = ingresantes / postulantes) by university and year as a worked example.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

from sunedu import build_model

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "sample_data"

# ASCII tables so the output prints on any console encoding (e.g. Windows cp1252).
pl.Config.set_ascii_tables(True)
pl.Config.set_tbl_rows(20)


def main() -> None:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_DIR)
    result = build_model(data_dir)
    tables = result["tables"]
    report = result["report"]

    print("Tables built:")
    for name, df in tables.items():
        print(f"  {name:20s} {df.height:>4d} rows")
    print("\nOrphan rates (fact -> dimension):")
    for fact, rates in report["orphan_rates"].items():
        pretty = ", ".join(f"{k}={v:.1%}" for k, v in rates.items())
        print(f"  {fact:20s} {pretty}")

    # Worked example: admission rate = ingresantes / postulantes.
    ing = tables["Fact_Ingresantes"].group_by("CODIGO_INEI", "ANIO").agg(
        pl.col("CANTIDAD").sum().alias("ingresantes")
    )
    pos = tables["Fact_Postulantes"].group_by("CODIGO_INEI", "ANIO").agg(
        pl.col("CANTIDAD").sum().alias("postulantes")
    )
    selectivity = (
        ing.join(pos, on=["CODIGO_INEI", "ANIO"])
        .join(tables["Dim_Universidad"].select("CODIGO_INEI", "UNIVERSIDAD"), on="CODIGO_INEI")
        .with_columns((pl.col("ingresantes") / pl.col("postulantes")).alias("tasa_admision"))
        .sort(["ANIO", "tasa_admision"])
    )
    print("\nAdmission rate (lower = more selective):")
    print(selectivity.select("UNIVERSIDAD", "ANIO", "ingresantes", "postulantes", "tasa_admision"))


if __name__ == "__main__":
    main()
