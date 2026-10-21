# Raw data

This directory contains the two course-provided PSID source files used in the analysis:

```text
blogpost6_parent_child_2021_2023.xlsx
parent_identification_2023.txt
```

## File descriptions

### `blogpost6_parent_child_2021_2023.xlsx`

This file contains individual identifiers, family identifiers, ages, and family income variables from the 2021 and 2023 PSID waves.

The analysis uses:

- `ER30001` and `ER30002` as the permanent individual identifier;
- `ER34904` and `ER35104` for age;
- `ER78002` and `ER82002` for family identifiers;
- `ER81775` for 2020 family income;
- `ER85629` for 2022 family income.

### `parent_identification_2023.txt`

This is the 2023 PSID Parent Identification File. It is a fixed-width text file with no header row.

The relevant identifiers are:

| Person | 1968 interview number | Person number |
|---|---|---|
| Child | `PID2` | `PID3` |
| Biological mother | `PID4` | `PID5` |
| Biological father | `PID23` | `PID24` |

`code/01_prepare_data.py` assigns the official `PID1`–`PID40` field names when reading this file.

## Using this directory

Keep both filenames unchanged and place the files directly in `data/raw/`. Then run:

```bash
python code/01_prepare_data.py
```

The raw files are excluded from Git and are not included in this repository. Users must obtain authorized copies of the course data before reproducing the analysis. Do not edit the source files manually.