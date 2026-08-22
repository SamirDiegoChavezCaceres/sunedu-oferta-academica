# sunedu-oferta-academica

[![CI](https://github.com/SamirDiegoChavezCaceres/sunedu-oferta-academica/actions/workflows/ci.yml/badge.svg)](https://github.com/SamirDiegoChavezCaceres/sunedu-oferta-academica/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Working with Peru's public higher-education data (SUNEDU / SIU, published at
tuni.pe): a **quota-aware client** for the public data API, and a **polars
pipeline** that turns the microdata into a small star model with validations
that fail loud.

The data is public. The code here is written from scratch; the sample dataset
is synthetic (real universities, invented numbers) so everything runs offline.

## The useful lesson: know when the API is the wrong tool

The portal's API exposes each dataset through one `POST` search endpoint whose
body is just `{"page", "pageSize"}`: no server-side filters, `pageSize` caps at
1000, and the response carries `{"data", "totalPages", "totalRows"}`. Access is
capped by a **monthly request quota**.

So before pulling a table, cost it out:

```bash
python scripts/fetch.py --estimate 4100000
# 4,100,000 rows / 1000 per page = 4,100 requests vs quota 1,000:
#   does NOT fit -> use bulk microdata
```

The national *postulantes* table is ~4.1M rows, which needs ~4,100 requests and
cannot fit a 1,000/month quota. The client detects this after the first probing
page and raises `QuotaExceeded` instead of silently burning the budget on a pull
that can never finish. The API is right for small tables (an institution or a
single program); the bulk microdata download is right for the large ones.

The client also sets timeouts and retries (with backoff) on 429/5xx, because a
public API behind a quota is exactly where a blind retry loop does damage.

## The pipeline

`build_model.py` reads the three microdata files and builds a star model
(`Dim_Universidad`, `Dim_Programa`, `Dim_Tiempo` + three fact tables):

```bash
python scripts/build.py           # uses the bundled sample_data/
```

Two modelling decisions carry the scars of doing it for real:

- **Surrogate keys.** A program's `CODIGO_PROGRAMA` is not unique across
  universities (three different universities all have a program `01`), so the
  program key is `CODIGO_INEI | CODIGO_PROGRAMA`. Joining on the raw code would
  silently merge unrelated programs.
- **Never trust a column by its name.** `CODIGO_SIU_FILIAL` (on ingresantes /
  postulantes) looks like it should match `LOCAL_CODIGO` (on matriculados), but
  it is a coarse ~12-value national classifier, not a campus id. Treating them
  as the same key produced a ~97% join failure the one time it was assumed
  rather than checked. Here it stays an attribute and is never joined on.

### Validations fail loud

`validate()` raises, it does not warn: null key values, duplicate keys, and
referential integrity (how many fact rows point at a dimension key that does not
exist, against a tolerance). A model that is quietly wrong is worse than one
that refuses to build.

## Worked example

The pipeline computes admission rate (`ingresantes / postulantes`) per
university and year as a selectivity measure. Lower is more selective.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Covers the quota refusal, pagination, the pregrado filter, the surrogate-key
uniqueness, and that validation raises on an orphaned fact row.

## License

MIT.
