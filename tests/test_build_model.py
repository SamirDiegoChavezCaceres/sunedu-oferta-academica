from pathlib import Path

import polars as pl
import pytest

from sunedu import ValidationError, build_model, validate
from sunedu.build_model import build_dimensions, load_sources

SAMPLE = str(Path(__file__).resolve().parents[1] / "sample_data")


def test_model_builds_cleanly():
    result = build_model(SAMPLE)
    rates = result["report"]["orphan_rates"]
    for fact_rates in rates.values():
        assert all(rate == 0.0 for rate in fact_rates.values())


def test_pregrado_filter_drops_posgrado():
    frames = load_sources(SAMPLE)
    programs = frames["ingresantes"]["PROGRAMA"].to_list()
    assert not any("maestria" in p.lower() for p in programs)


def test_program_key_is_unique_per_university():
    # Code "01" is reused by three universities; the surrogate key must keep
    # them as three distinct programs, not collapse them into one.
    dims = build_dimensions(load_sources(SAMPLE))
    code_01 = dims["Dim_Programa"].filter(pl.col("CODIGO_PROGRAMA") == "01")
    assert code_01.height == 3
    assert code_01["ID_PROGRAMA"].n_unique() == 3


def test_ucsp_is_flagged():
    dims = build_dimensions(load_sources(SAMPLE))
    ucsp = dims["Dim_Universidad"].filter(pl.col("ES_UCSP"))
    assert ucsp.height == 1
    assert "san pablo" in ucsp["UNIVERSIDAD"][0].lower()


def test_validate_raises_on_orphan_fact():
    dim = pl.DataFrame({"ID_PROGRAMA": ["100|01"], "CODIGO_INEI": ["100"]})
    bad_fact = pl.DataFrame({
        "ID_PROGRAMA": ["999|99"],   # not in the dimension
        "CODIGO_INEI": ["100"],
        "ANIO": [2024],
        "CANTIDAD": [10],
    })
    model = {
        "Dim_Programa": dim,
        "Dim_Universidad": dim,
        "Fact_Bad": bad_fact,
    }
    with pytest.raises(ValidationError):
        validate(model)
