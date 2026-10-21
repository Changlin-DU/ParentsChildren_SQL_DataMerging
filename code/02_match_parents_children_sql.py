from pathlib import Path

import duckdb


# ------------------------------------------------------------
# 1. Define project-relative paths
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
RESULTS_TABLE_DIR = PROJECT_ROOT / "results" / "tables"

DATABASE_FILE = (
    PROCESSED_DATA_DIR
    / "blogpost6_analysis.duckdb"
)

PAIR_OUTPUT_FILE = (
    PROCESSED_DATA_DIR
    / "parent_child_pairs.csv"
)

MATCHED_SAMPLE_OUTPUT_FILE = (
    PROCESSED_DATA_DIR
    / "matched_child_sample.csv"
)

MATCHING_SUMMARY_OUTPUT_FILE = (
    RESULTS_TABLE_DIR
    / "matching_summary.csv"
)


# ------------------------------------------------------------
# 2. Helper function
# ------------------------------------------------------------

def sql_path(path):
    """
    Convert a file path to a SQL-safe string.
    """

    return str(path).replace("'", "''")


# ------------------------------------------------------------
# 3. Check that the prepared database is available
# ------------------------------------------------------------

def validate_database(connection):
    """
    Confirm that Step 1 created the required tables.
    """

    required_tables = {
        "individual_panel",
        "parent_links",
    }

    existing_tables = {
        row[0]
        for row in connection.execute(
            "SHOW TABLES"
        ).fetchall()
    }

    missing_tables = (
        required_tables - existing_tables
    )

    if missing_tables:
        raise ValueError(
            "The database is missing required tables: "
            f"{sorted(missing_tables)}. "
            "Run code/01_prepare_data.py first."
        )


# ------------------------------------------------------------
# 4. Match children to mothers and fathers
# ------------------------------------------------------------

def create_parent_child_pairs(connection):
    """
    Construct a long parent-child table.

    Each row represents one matched biological parent:
    either a mother-child pair or a father-child pair.

    The SQL uses the two-part permanent PSID identifier:
    1968 interview number + person number.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE parent_child_pairs AS

        -- Mother-child matches
        SELECT
            child.person_1968_id
                AS child_1968_id,

            child.person_number
                AS child_person_number,

            'mother'
                AS parent_type,

            mother.person_1968_id
                AS parent_1968_id,

            mother.person_number
                AS parent_person_number,

            child.age_2021
                AS child_age_2021,

            child.age_2023
                AS child_age_2023,

            mother.age_2021
                AS parent_age_2021,

            mother.age_2023
                AS parent_age_2023,

            child.family_income_2020
                AS child_income_2020,

            child.family_income_2022
                AS child_income_2022,

            mother.family_income_2020
                AS parent_income_2020,

            mother.family_income_2022
                AS parent_income_2022

        FROM parent_links AS links

        INNER JOIN individual_panel AS child
            ON links.child_1968_id
                = child.person_1968_id
            AND links.child_person_number
                = child.person_number

        INNER JOIN individual_panel AS mother
            ON links.mother_1968_id
                = mother.person_1968_id
            AND links.mother_person_number
                = mother.person_number

        WHERE
            links.mother_1968_id IS NOT NULL
            AND links.mother_person_number IS NOT NULL


        UNION ALL


        -- Father-child matches
        SELECT
            child.person_1968_id
                AS child_1968_id,

            child.person_number
                AS child_person_number,

            'father'
                AS parent_type,

            father.person_1968_id
                AS parent_1968_id,

            father.person_number
                AS parent_person_number,

            child.age_2021
                AS child_age_2021,

            child.age_2023
                AS child_age_2023,

            father.age_2021
                AS parent_age_2021,

            father.age_2023
                AS parent_age_2023,

            child.family_income_2020
                AS child_income_2020,

            child.family_income_2022
                AS child_income_2022,

            father.family_income_2020
                AS parent_income_2020,

            father.family_income_2022
                AS parent_income_2022

        FROM parent_links AS links

        INNER JOIN individual_panel AS child
            ON links.child_1968_id
                = child.person_1968_id
            AND links.child_person_number
                = child.person_number

        INNER JOIN individual_panel AS father
            ON links.father_1968_id
                = father.person_1968_id
            AND links.father_person_number
                = father.person_number

        WHERE
            links.father_1968_id IS NOT NULL
            AND links.father_person_number IS NOT NULL
        """
    )


# ------------------------------------------------------------
# 5. Aggregate parent information to the child level
# ------------------------------------------------------------

def create_matched_child_sample(connection):
    """
    Create one row per child.

    When both biological parents are matched, their incomes are
    averaged. When only one parent is matched, that parent's
    income is used.

    The multi-year measures require positive income in both
    2020 and 2022.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE matched_child_sample AS

        SELECT
            child_1968_id,
            child_person_number,

            MAX(child_age_2021)
                AS child_age_2021,

            MAX(child_age_2023)
                AS child_age_2023,

            MAX(child_income_2020)
                AS child_income_2020,

            MAX(child_income_2022)
                AS child_income_2022,

            CASE
                WHEN
                    MAX(child_income_2020) > 0
                    AND MAX(child_income_2022) > 0
                THEN
                    (
                        MAX(child_income_2020)
                        + MAX(child_income_2022)
                    ) / 2.0
                ELSE NULL
            END AS child_income_average,

            COUNT(*)
                AS matched_parent_count,

            MAX(
                CASE
                    WHEN parent_type = 'mother'
                    THEN 1
                    ELSE 0
                END
            ) AS matched_mother,

            MAX(
                CASE
                    WHEN parent_type = 'father'
                    THEN 1
                    ELSE 0
                END
            ) AS matched_father,

            AVG(
                CASE
                    WHEN parent_age_2021 > 0
                    THEN parent_age_2021
                    ELSE NULL
                END
            ) AS average_parent_age_2021,

            AVG(
                CASE
                    WHEN parent_age_2023 > 0
                    THEN parent_age_2023
                    ELSE NULL
                END
            ) AS average_parent_age_2023,

            AVG(
                CASE
                    WHEN parent_income_2020 > 0
                    THEN parent_income_2020
                    ELSE NULL
                END
            ) AS parent_income_2020,

            AVG(
                CASE
                    WHEN parent_income_2022 > 0
                    THEN parent_income_2022
                    ELSE NULL
                END
            ) AS parent_income_2022,

            AVG(
                CASE
                    WHEN
                        parent_income_2020 > 0
                        AND parent_income_2022 > 0
                    THEN
                        (
                            parent_income_2020
                            + parent_income_2022
                        ) / 2.0
                    ELSE NULL
                END
            ) AS parent_income_average

        FROM parent_child_pairs

        GROUP BY
            child_1968_id,
            child_person_number
        """
    )


# ------------------------------------------------------------
# 6. Produce matching diagnostics
# ------------------------------------------------------------

def create_matching_summary(connection):
    """
    Count the matches and usable income observations.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE matching_summary AS

        SELECT
            'matched parent-child pairs'
                AS statistic,
            COUNT(*)
                AS value
        FROM parent_child_pairs

        UNION ALL

        SELECT
            'mother-child pairs',
            COUNT(*)
        FROM parent_child_pairs
        WHERE parent_type = 'mother'

        UNION ALL

        SELECT
            'father-child pairs',
            COUNT(*)
        FROM parent_child_pairs
        WHERE parent_type = 'father'

        UNION ALL

        SELECT
            'unique matched children',
            COUNT(*)
        FROM matched_child_sample

        UNION ALL

        SELECT
            'children matched to mother',
            COUNT(*)
        FROM matched_child_sample
        WHERE matched_mother = 1

        UNION ALL

        SELECT
            'children matched to father',
            COUNT(*)
        FROM matched_child_sample
        WHERE matched_father = 1

        UNION ALL

        SELECT
            'children matched to both parents',
            COUNT(*)
        FROM matched_child_sample
        WHERE
            matched_mother = 1
            AND matched_father = 1

        UNION ALL

        SELECT
            'usable 2020 income pairs',
            COUNT(*)
        FROM matched_child_sample
        WHERE
            child_income_2020 > 0
            AND parent_income_2020 > 0

        UNION ALL

        SELECT
            'usable 2022 income pairs',
            COUNT(*)
        FROM matched_child_sample
        WHERE
            child_income_2022 > 0
            AND parent_income_2022 > 0

        UNION ALL

        SELECT
            'usable multi-year income pairs',
            COUNT(*)
        FROM matched_child_sample
        WHERE
            child_income_average > 0
            AND parent_income_average > 0
        """
    )


# ------------------------------------------------------------
# 7. Save SQL-generated results
# ------------------------------------------------------------

def save_results(connection):
    """
    Save the matched datasets and summary to CSV files.
    """

    connection.execute(
        f"""
        COPY parent_child_pairs
        TO '{sql_path(PAIR_OUTPUT_FILE)}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )

    connection.execute(
        f"""
        COPY matched_child_sample
        TO '{sql_path(MATCHED_SAMPLE_OUTPUT_FILE)}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )

    connection.execute(
        f"""
        COPY matching_summary
        TO '{sql_path(MATCHING_SUMMARY_OUTPUT_FILE)}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )


# ------------------------------------------------------------
# 8. Main program
# ------------------------------------------------------------

def main():
    if not DATABASE_FILE.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_FILE}. "
            "Run code/01_prepare_data.py first."
        )

    RESULTS_TABLE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = duckdb.connect(
        str(DATABASE_FILE)
    )

    try:
        validate_database(connection)

        create_parent_child_pairs(connection)
        create_matched_child_sample(connection)
        create_matching_summary(connection)
        save_results(connection)

        summary = connection.execute(
            """
            SELECT
                statistic,
                value
            FROM matching_summary
            ORDER BY statistic
            """
        ).df()

        print("\n" + "=" * 70)
        print("PARENT-CHILD MATCHING SUMMARY")
        print("=" * 70)
        print(summary.to_string(index=False))

        print("\n" + "=" * 70)
        print("FILES CREATED")
        print("=" * 70)
        print(PAIR_OUTPUT_FILE)
        print(MATCHED_SAMPLE_OUTPUT_FILE)
        print(MATCHING_SUMMARY_OUTPUT_FILE)

    finally:
        connection.close()

    print("\nParent-child matching completed successfully.")


if __name__ == "__main__":
    main()
