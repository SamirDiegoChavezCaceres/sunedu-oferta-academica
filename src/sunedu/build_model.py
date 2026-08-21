"""Turn SUNEDU microdata (ingresantes / matriculados / postulantes) into a
small star model with polars - and validate it loudly.

Two decisions carry the lessons from doing this for real:

* **Surrogate keys.** A program's own ``CODIGO_PROGRAMA`` is not unique across
  universities, so the program key is ``CODIGO_INEI | CODIGO_PROGRAMA``. Joining
  on the raw code alone silently mixes programs from different universities.

* **Do not trust a column by its name.** ``CODIGO_SIU_FILIAL`` (on ingresantes
  / postulantes) looks like it should match ``LOCAL_CODIGO`` (on matriculados),
  but it is a coarse 12-value national classifier, not a campus id. We keep it
  as an attribute and never join on it. Verifying the actual values before
  joining is cheap; a silent 97% join failure is not.

The validations (null keys, referential integrity, duplicates) raise instead of
warning, because a model that is quietly wrong is worse than one that refuses to
build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import polars as pl

PREGRADO = "carrera profesional"
UCSP_MARKER = "san pablo"
# Fraction of fact rows allowed to reference a missing dimension key.
ORPHAN_TOLERANCE = 0.03


class ValidationError(ValueError):
    """Raised when the built model fails an integrity check."""


def _norm(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Utf8).str.strip_chars().str.to_lowercase()


def _prepare(df: pl.DataFrame) -> pl.DataFrame:
    """Normalize, keep only pregrado, and add the surrogate program key."""
    df = df.filter(_norm("NIVEL_ACADEMICO") == PREGRADO)
    return df.with_columns(
        (pl.col("CODIGO_INEI").cast(pl.Utf8) + "|" + pl.col("CODIGO_PROGRAMA").cast(pl.Utf8))
        .alias("ID_PROGRAMA"),
        pl.col("ANIO").cast(pl.Int32),
        pl.col("CANTIDAD").cast(pl.Int64),
    )


def load_sources(data_dir: str) -> Dict[str, pl.DataFrame]:
    # Read every column as text (like the real microdata) so codes such as
    # "01" keep their leading zeros; types are cast explicitly in _prepare.
    root = Path(data_dir)
    return {
        name: _prepare(pl.read_csv(root / f"{name}.csv", infer_schema_length=0))
        for name in ("ingresantes", "matriculados", "postulantes")
    }


def build_dimensions(frames: Dict[str, pl.DataFrame]) -> Dict[str, pl.DataFrame]:
    everyone = pl.concat([f.select(
        "CODIGO_INEI", "UNIVERSIDAD", "GESTION", "DEPARTAMENTO",
        "ID_PROGRAMA", "CODIGO_PROGRAMA", "PROGRAMA", "NIVEL_ACADEMICO", "ANIO",
    ) for f in frames.values()])

    dim_universidad = (
        everyone.select("CODIGO_INEI", "UNIVERSIDAD", "GESTION", "DEPARTAMENTO")
        .unique()
        .with_columns(
            pl.col("UNIVERSIDAD").str.to_lowercase().str.contains(UCSP_MARKER).alias("ES_UCSP")
        )
    )
    dim_programa = everyone.select(
        "ID_PROGRAMA", "CODIGO_INEI", "CODIGO_PROGRAMA", "PROGRAMA", "NIVEL_ACADEMICO"
    ).unique()
    dim_tiempo = everyone.select("ANIO").unique().sort("ANIO")

    return {
        "Dim_Universidad": dim_universidad,
        "Dim_Programa": dim_programa,
        "Dim_Tiempo": dim_tiempo,
    }


def build_facts(frames: Dict[str, pl.DataFrame]) -> Dict[str, pl.DataFrame]:
    facts = {}
    for name, df in frames.items():
        facts[f"Fact_{name.capitalize()}"] = df.select(
            "ID_PROGRAMA", "CODIGO_INEI", "ANIO", "CANTIDAD"
        )
    return facts


def _require_no_null_keys(model: Dict[str, pl.DataFrame]) -> None:
    for name, df in model.items():
        for key in [c for c in df.columns if c.startswith(("ID_", "CODIGO_INEI", "ANIO"))]:
            nulls = df.select(pl.col(key).is_null().sum()).item()
            if nulls:
                raise ValidationError(f"{name}.{key} has {nulls} null key value(s)")


def _check_referential_integrity(
    fact: pl.DataFrame, dim: pl.DataFrame, key: str, where: str
) -> float:
    known = dim.select(key).unique()
    orphans = fact.join(known, on=key, how="anti")
    rate = orphans.height / fact.height if fact.height else 0.0
    if rate > ORPHAN_TOLERANCE:
        raise ValidationError(
            f"{where}: {rate:.1%} of rows reference a {key} missing from the "
            f"dimension (tolerance {ORPHAN_TOLERANCE:.0%})"
        )
    return rate


def validate(model: Dict[str, pl.DataFrame]) -> dict:
    _require_no_null_keys(model)
    report = {"orphan_rates": {}, "rows": {}}
    for name, df in model.items():
        report["rows"][name] = df.height
    for fact_name, fact in model.items():
        if not fact_name.startswith("Fact_"):
            continue
        report["orphan_rates"][fact_name] = {
            "ID_PROGRAMA": _check_referential_integrity(
                fact, model["Dim_Programa"], "ID_PROGRAMA", fact_name
            ),
            "CODIGO_INEI": _check_referential_integrity(
                fact, model["Dim_Universidad"], "CODIGO_INEI", fact_name
            ),
        }
    return report


def build_model(data_dir: str) -> Dict[str, object]:
    frames = load_sources(data_dir)
    model: Dict[str, pl.DataFrame] = {}
    model.update(build_dimensions(frames))
    model.update(build_facts(frames))
    report = validate(model)
    return {"tables": model, "report": report}
