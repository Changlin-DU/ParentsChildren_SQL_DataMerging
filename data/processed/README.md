# Processed data

This directory stores intermediate datasets created by the Python scripts. The files are generated from the source data in `data/raw/` and should not be edited manually.

## Generated files

| File | Created by | Contents |
|---|---|---|
| `blogpost6_analysis.duckdb` | `01_prepare_data.py` | DuckDB database used throughout the analysis |
| `individual_panel.csv` | `01_prepare_data.py` | Standardized individual, family, age, and income variables |
| `parent_links.csv` | `01_prepare_data.py` | Child, biological mother, and biological father identifiers |
| `preparation_summary.csv` | `01_prepare_data.py` | Data preparation and identifier checks |
| `parent_child_pairs.csv` | `02_match_parents_children_sql.py` | Long-form mother-child and father-child matches |
| `matched_child_sample.csv` | `02_match_parents_children_sql.py` | One record per matched child with aggregated parental income |
| `ige_analysis_sample.csv` | `03_estimate_ige.py` | Final common sample used for the IGE regressions |

## Recreating the files

From the repository root, run:

```bash
python code/01_prepare_data.py
python code/02_match_parents_children_sql.py
python code/03_estimate_ige.py
```

Each script replaces its earlier outputs, so this directory can be rebuilt from the raw data and code.

Processed files are excluded from Git because they contain individual identifiers and can be reproduced locally. Shareable summary tables and figures are saved in `results/`.