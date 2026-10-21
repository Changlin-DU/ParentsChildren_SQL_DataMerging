from pathlib import Path

import duckdb
import pandas as pd


# ------------------------------------------------------------
# 1. Define project-relative paths
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"

EXCEL_FILE = (
    RAW_DATA_DIR
    / "blogpost6_parent_child_2021_2023.xlsx"
)

PARENT_FILE = (
    RAW_DATA_DIR
    / "parent_identification_2023.txt"
)

DATABASE_FILE = (
    PROCESSED_DATA_DIR
    / "blogpost6_analysis.duckdb"
)

INDIVIDUAL_OUTPUT_FILE = (
    PROCESSED_DATA_DIR
    / "individual_panel.csv"
)

PARENT_LINK_OUTPUT_FILE = (
    PROCESSED_DATA_DIR
    / "parent_links.csv"
)

SUMMARY_OUTPUT_FILE = (
    PROCESSED_DATA_DIR
    / "preparation_summary.csv"
)


# ------------------------------------------------------------
# 2. Required variables
# ------------------------------------------------------------

REQUIRED_MAIN_VARIABLES = [
    "ER30001",
    "ER30002",
    "ER34901",
    "ER34902",
    "ER34904",
    "ER78002",
    "ER81775",
    "ER35101",
    "ER35102",
    "ER35104",
    "ER82002",
    "ER85629",
]

REQUIRED_PARENT_VARIABLES = [
    "PID2",
    "PID3",
    "PID4",
    "PID5",
    "PID23",
    "PID24",
]


# ------------------------------------------------------------
# 3. Official fixed-width structure of the PSID
#    2023 Parent Identification File
# ------------------------------------------------------------

PID_COLUMN_NAMES = [
    f"PID{column_number}"
    for column_number in range(1, 41)
]

PID_COLUMN_WIDTHS = [
    # PID1
    1,

    # PID2-PID9: four pairs of ID fields
    4, 3,
    4, 3,
    4, 3,
    4, 3,

    # PID10-PID22: thirteen indicator fields
    1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1,

    # PID23-PID28: three pairs of ID fields
    4, 3,
    4, 3,
    4, 3,

    # PID29-PID40: twelve indicator fields
    1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1,
]


# ------------------------------------------------------------
# 4. Helper functions
# ------------------------------------------------------------

def validate_columns(data, required_columns, dataset_name):
    """
    Stop the script if any required variables are absent.
    """

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{dataset_name} is missing required variables: "
            f"{missing_columns}"
        )


def sql_path(path):
    """
    Convert a Path to a SQL-safe string.
    """

    return str(path).replace("'", "''")


# ------------------------------------------------------------
# 5. Read the Excel data
# ------------------------------------------------------------

def read_main_data():
    """
    Read the individual/family extract from Excel.
    """

    print("\nReading the Excel individual/family data...")

    main_data = pd.read_excel(
        EXCEL_FILE,
        sheet_name="Data",
        engine="calamine",
    )

    main_data.columns = (
        main_data.columns
        .astype(str)
        .str.strip()
    )

    validate_columns(
        main_data,
        REQUIRED_MAIN_VARIABLES,
        "Excel individual/family data",
    )

    # Retain only variables used in this project.
    main_data = main_data[
        REQUIRED_MAIN_VARIABLES
    ].copy()

    print(f"Rows read: {len(main_data):,}")
    print(f"Columns retained: {len(main_data.columns):,}")

    return main_data


# ------------------------------------------------------------
# 6. Read the fixed-width parent-identification data
# ------------------------------------------------------------

def read_parent_data():
    """
    Read the official fixed-width PSID parent-identification file.
    """

    print("\nReading the parent-identification data...")

    if len(PID_COLUMN_NAMES) != len(PID_COLUMN_WIDTHS):
        raise ValueError(
            "The number of PID column names does not match "
            "the number of fixed-width fields."
        )

    parent_data = pd.read_fwf(
        PARENT_FILE,
        widths=PID_COLUMN_WIDTHS,
        names=PID_COLUMN_NAMES,
        header=None,
        dtype="string",
    )

    # Convert all fixed-width fields to nullable integers.
    for column in PID_COLUMN_NAMES:
        parent_data[column] = pd.to_numeric(
            parent_data[column],
            errors="coerce",
        ).astype("Int64")

    validate_columns(
        parent_data,
        REQUIRED_PARENT_VARIABLES,
        "Parent-identification data",
    )

    # Retain only the child, mother, and father identifiers.
    parent_data = parent_data[
        REQUIRED_PARENT_VARIABLES
    ].copy()

    print(f"Rows read: {len(parent_data):,}")
    print(f"Columns retained: {len(parent_data.columns):,}")

    return parent_data


# ------------------------------------------------------------
# 7. Create cleaned analysis tables with SQL
# ------------------------------------------------------------

def create_analysis_tables(
    connection,
    main_data,
    parent_data,
):
    """
    Register the pandas data frames in DuckDB and use SQL to
    construct clean analysis tables.
    """

    connection.register(
        "raw_individual_data",
        main_data,
    )

    connection.register(
        "raw_parent_data",
        parent_data,
    )

    # --------------------------------------------------------
    # Individual panel
    # --------------------------------------------------------

    connection.execute(
        """
        CREATE OR REPLACE TABLE individual_panel AS

        SELECT
            TRY_CAST(ER30001 AS BIGINT)
                AS person_1968_id,

            TRY_CAST(ER30002 AS BIGINT)
                AS person_number,

            TRY_CAST(ER34901 AS BIGINT)
                AS family_interview_2021,

            TRY_CAST(ER34902 AS BIGINT)
                AS sequence_number_2021,

            TRY_CAST(ER34904 AS BIGINT)
                AS age_2021,

            TRY_CAST(ER78002 AS BIGINT)
                AS family_id_2021,

            TRY_CAST(ER81775 AS DOUBLE)
                AS family_income_2020,

            TRY_CAST(ER35101 AS BIGINT)
                AS family_interview_2023,

            TRY_CAST(ER35102 AS BIGINT)
                AS sequence_number_2023,

            TRY_CAST(ER35104 AS BIGINT)
                AS age_2023,

            TRY_CAST(ER82002 AS BIGINT)
                AS family_id_2023,

            TRY_CAST(ER85629 AS DOUBLE)
                AS family_income_2022

        FROM raw_individual_data
        """
    )

    # --------------------------------------------------------
    # Parent-child identifier table
    # --------------------------------------------------------

    connection.execute(
        """
        CREATE OR REPLACE TABLE parent_links AS

        SELECT
            TRY_CAST(PID2 AS BIGINT)
                AS child_1968_id,

            TRY_CAST(PID3 AS BIGINT)
                AS child_person_number,

            NULLIF(
                TRY_CAST(PID4 AS BIGINT),
                0
            ) AS mother_1968_id,

            NULLIF(
                TRY_CAST(PID5 AS BIGINT),
                0
            ) AS mother_person_number,

            NULLIF(
                TRY_CAST(PID23 AS BIGINT),
                0
            ) AS father_1968_id,

            NULLIF(
                TRY_CAST(PID24 AS BIGINT),
                0
            ) AS father_person_number

        FROM raw_parent_data
        """
    )


# ------------------------------------------------------------
# 8. Validate identifiers and create a summary
# ------------------------------------------------------------

def create_preparation_summary(connection):
    """
    Generate reproducible data-quality statistics with SQL.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE preparation_summary AS

        SELECT
            'individual_panel' AS dataset,
            'total_rows' AS metric,
            COUNT(*) AS value
        FROM individual_panel

        UNION ALL

        SELECT
            'individual_panel',
            'distinct_person_ids',
            COUNT(
                DISTINCT
                CONCAT(
                    person_1968_id,
                    '-',
                    person_number
                )
            )
        FROM individual_panel
        WHERE
            person_1968_id IS NOT NULL
            AND person_number IS NOT NULL

        UNION ALL

        SELECT
            'individual_panel',
            'duplicate_person_ids',
            COUNT(*) - COUNT(
                DISTINCT
                CONCAT(
                    person_1968_id,
                    '-',
                    person_number
                )
            )
        FROM individual_panel
        WHERE
            person_1968_id IS NOT NULL
            AND person_number IS NOT NULL

        UNION ALL

        SELECT
            'parent_links',
            'total_rows',
            COUNT(*)
        FROM parent_links

        UNION ALL

        SELECT
            'parent_links',
            'distinct_child_ids',
            COUNT(
                DISTINCT
                CONCAT(
                    child_1968_id,
                    '-',
                    child_person_number
                )
            )
        FROM parent_links
        WHERE
            child_1968_id IS NOT NULL
            AND child_person_number IS NOT NULL

        UNION ALL

        SELECT
            'parent_links',
            'children_with_mother_id',
            COUNT(*)
        FROM parent_links
        WHERE
            mother_1968_id IS NOT NULL
            AND mother_person_number IS NOT NULL

        UNION ALL

        SELECT
            'parent_links',
            'children_with_father_id',
            COUNT(*)
        FROM parent_links
        WHERE
            father_1968_id IS NOT NULL
            AND father_person_number IS NOT NULL

        UNION ALL

        SELECT
            'individual_panel',
            'positive_income_2020',
            COUNT(*)
        FROM individual_panel
        WHERE family_income_2020 > 0

        UNION ALL

        SELECT
            'individual_panel',
            'positive_income_2022',
            COUNT(*)
        FROM individual_panel
        WHERE family_income_2022 > 0
        """
    )


# ------------------------------------------------------------
# 9. Save processed tables
# ------------------------------------------------------------

def save_processed_tables(connection):
    """
    Save the SQL-generated tables as CSV files.
    """

    connection.execute(
        f"""
        COPY individual_panel
        TO '{sql_path(INDIVIDUAL_OUTPUT_FILE)}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )

    connection.execute(
        f"""
        COPY parent_links
        TO '{sql_path(PARENT_LINK_OUTPUT_FILE)}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )

    connection.execute(
        f"""
        COPY preparation_summary
        TO '{sql_path(SUMMARY_OUTPUT_FILE)}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )


# ------------------------------------------------------------
# 10. Main program
# ------------------------------------------------------------

def main():
    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"Excel file not found: {EXCEL_FILE}"
        )

    if not PARENT_FILE.exists():
        raise FileNotFoundError(
            f"Parent-identification file not found: "
            f"{PARENT_FILE}"
        )

    PROCESSED_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    main_data = read_main_data()
    parent_data = read_parent_data()

    connection = duckdb.connect(
        str(DATABASE_FILE)
    )

    try:
        create_analysis_tables(
            connection,
            main_data,
            parent_data,
        )

        create_preparation_summary(connection)
        save_processed_tables(connection)

        summary = connection.execute(
            """
            SELECT
                dataset,
                metric,
                value
            FROM preparation_summary
            ORDER BY
                dataset,
                metric
            """
        ).df()

        print("\n" + "=" * 70)
        print("PREPARATION SUMMARY")
        print("=" * 70)
        print(summary.to_string(index=False))

        print("\n" + "=" * 70)
        print("FILES CREATED")
        print("=" * 70)
        print(DATABASE_FILE)
        print(INDIVIDUAL_OUTPUT_FILE)
        print(PARENT_LINK_OUTPUT_FILE)
        print(SUMMARY_OUTPUT_FILE)

    finally:
        connection.close()

    print("\nData preparation completed successfully.")


if __name__ == "__main__":
    main()
