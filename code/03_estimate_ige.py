from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm


# ------------------------------------------------------------
# 1. Define project-relative paths and colors
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
RESULTS_TABLE_DIR = PROJECT_ROOT / "results" / "tables"
RESULTS_FIGURE_DIR = PROJECT_ROOT / "results" / "figures"

DATABASE_FILE = (
    PROCESSED_DATA_DIR
    / "blogpost6_analysis.duckdb"
)

ANALYSIS_SAMPLE_FILE = (
    PROCESSED_DATA_DIR
    / "ige_analysis_sample.csv"
)

REGRESSION_RESULTS_FILE = (
    RESULTS_TABLE_DIR
    / "ige_regression_results.csv"
)

AGE_RESULTS_FILE = (
    RESULTS_TABLE_DIR
    / "ige_age_group_results.csv"
)

SAMPLE_SUMMARY_FILE = (
    RESULTS_TABLE_DIR
    / "ige_sample_summary.csv"
)

COMPARISON_FIGURE_FILE = (
    RESULTS_FIGURE_DIR
    / "ige_comparison.png"
)

AGE_FIGURE_FILE = (
    RESULTS_FIGURE_DIR
    / "ige_by_age_group.png"
)

BRIGHT_BLUE = "#29B6F6"
PINK = "#FF5CA8"
RED = "#E63946"
DARK_GRAY = "#4D4D4D"


# ------------------------------------------------------------
# 2. Validate the database
# ------------------------------------------------------------

def validate_database(connection):
    """
    Confirm that scripts 01 and 02 created the required tables.
    """

    required_tables = {
        "individual_panel",
        "parent_child_pairs",
    }

    existing_tables = {
        row[0]
        for row in connection.execute(
            "SHOW TABLES"
        ).fetchall()
    }

    missing_tables = required_tables - existing_tables

    if missing_tables:
        raise ValueError(
            "Missing required database tables: "
            f"{sorted(missing_tables)}. "
            "Run scripts 01 and 02 first."
        )


# ------------------------------------------------------------
# 3. Identify parent-child pairs in separate households
# ------------------------------------------------------------

def create_pair_household_status(connection):
    """
    Compare child and parent family identifiers.

    A pair is classified as living separately when both family IDs
    are valid and different.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE pair_household_status AS

        SELECT
            pairs.*,

            child.family_id_2021
                AS child_family_id_2021,

            parent.family_id_2021
                AS parent_family_id_2021,

            child.family_id_2023
                AS child_family_id_2023,

            parent.family_id_2023
                AS parent_family_id_2023,

            CASE
                WHEN
                    child.family_id_2021 > 0
                    AND parent.family_id_2021 > 0
                    AND child.family_id_2021
                        <> parent.family_id_2021
                THEN 1
                ELSE 0
            END AS separate_households_2021,

            CASE
                WHEN
                    child.family_id_2023 > 0
                    AND parent.family_id_2023 > 0
                    AND child.family_id_2023
                        <> parent.family_id_2023
                THEN 1
                ELSE 0
            END AS separate_households_2023

        FROM parent_child_pairs AS pairs

        INNER JOIN individual_panel AS child
            ON pairs.child_1968_id
                = child.person_1968_id
            AND pairs.child_person_number
                = child.person_number

        INNER JOIN individual_panel AS parent
            ON pairs.parent_1968_id
                = parent.person_1968_id
            AND pairs.parent_person_number
                = parent.person_number
        """
    )


# ------------------------------------------------------------
# 4. Construct child and parental income measures
# ------------------------------------------------------------

def create_child_income_measures(connection):
    """
    Aggregate matched parent records to one row per child.

    Single-year income uses 2022 income. Multi-year income averages
    income from 2020 and 2022.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE child_income_measures AS

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

            AVG(
                CASE
                    WHEN
                        separate_households_2023 = 1
                        AND parent_income_2022 > 0
                    THEN parent_income_2022
                    ELSE NULL
                END
            ) AS parent_income_2022,

            AVG(
                CASE
                    WHEN
                        separate_households_2021 = 1
                        AND separate_households_2023 = 1
                        AND parent_income_2020 > 0
                        AND parent_income_2022 > 0
                    THEN
                        (
                            parent_income_2020
                            + parent_income_2022
                        ) / 2.0
                    ELSE NULL
                END
            ) AS parent_income_average,

            SUM(
                CASE
                    WHEN separate_households_2023 = 1
                    THEN 1
                    ELSE 0
                END
            ) AS separate_parent_count_2023

        FROM pair_household_status

        GROUP BY
            child_1968_id,
            child_person_number
        """
    )


# ------------------------------------------------------------
# 5. Create the common regression sample
# ------------------------------------------------------------

def create_regression_sample(connection):
    """
    Use the same observations in the single-year and multi-year
    regressions so that their coefficients are comparable.
    """

    connection.execute(
        """
        CREATE OR REPLACE TABLE ige_analysis_sample AS

        SELECT
            child_1968_id,
            child_person_number,
            child_age_2021,
            child_age_2023,
            child_income_2020,
            child_income_2022,
            child_income_average,
            parent_income_2022,
            parent_income_average,
            separate_parent_count_2023

        FROM child_income_measures

        WHERE
            child_age_2023 BETWEEN 25 AND 55
            AND child_income_2022 > 0
            AND parent_income_2022 > 0
            AND child_income_average > 0
            AND parent_income_average > 0
            AND separate_parent_count_2023 >= 1
        """
    )


# ------------------------------------------------------------
# 6. Estimate a log-log regression
# ------------------------------------------------------------

def estimate_log_log_regression(
    data,
    child_income_column,
    parent_income_column,
    model_name,
):
    """
    Estimate:

        log(child income)
            = beta_0
            + beta_1 log(parent income)
            + error

    beta_1 is the estimated IGE.
    """

    regression_data = data[
        [
            child_income_column,
            parent_income_column,
        ]
    ].dropna().copy()

    regression_data = regression_data[
        (regression_data[child_income_column] > 0)
        & (regression_data[parent_income_column] > 0)
    ]

    log_child_income = np.log(
        regression_data[child_income_column]
    )

    log_parent_income = np.log(
        regression_data[parent_income_column]
    )

    explanatory_variables = sm.add_constant(
        log_parent_income
    )

    model = sm.OLS(
        log_child_income,
        explanatory_variables,
    ).fit(cov_type="HC1")

    coefficient = model.params[parent_income_column]
    standard_error = model.bse[parent_income_column]

    return {
        "model": model_name,
        "observations": int(model.nobs),
        "intercept": model.params["const"],
        "ige_estimate": coefficient,
        "standard_error": standard_error,
        "confidence_interval_low": (
            coefficient - 1.96 * standard_error
        ),
        "confidence_interval_high": (
            coefficient + 1.96 * standard_error
        ),
        "r_squared": model.rsquared,
    }


# ------------------------------------------------------------
# 7. Estimate the optional rank-rank model
# ------------------------------------------------------------

def estimate_rank_rank_regression(data):
    """
    Estimate the optional relationship between parental income rank
    and child income rank using multi-year income.
    """

    rank_data = data[
        [
            "child_income_average",
            "parent_income_average",
        ]
    ].dropna().copy()

    rank_data["child_income_rank"] = (
        rank_data["child_income_average"]
        .rank(method="average", pct=True)
    )

    rank_data["parent_income_rank"] = (
        rank_data["parent_income_average"]
        .rank(method="average", pct=True)
    )

    explanatory_variables = sm.add_constant(
        rank_data["parent_income_rank"]
    )

    model = sm.OLS(
        rank_data["child_income_rank"],
        explanatory_variables,
    ).fit(cov_type="HC1")

    coefficient = model.params["parent_income_rank"]
    standard_error = model.bse["parent_income_rank"]

    return {
        "model": "Multi-year rank-rank",
        "observations": int(model.nobs),
        "intercept": model.params["const"],
        "ige_estimate": coefficient,
        "standard_error": standard_error,
        "confidence_interval_low": (
            coefficient - 1.96 * standard_error
        ),
        "confidence_interval_high": (
            coefficient + 1.96 * standard_error
        ),
        "r_squared": model.rsquared,
    }


# ------------------------------------------------------------
# 8. Estimate models by child age group
# ------------------------------------------------------------

def estimate_by_age_group(data):
    """
    Compare IGE estimates across three child age groups.
    """

    age_data = data.copy()

    age_data["age_group"] = pd.cut(
        age_data["child_age_2023"],
        bins=[24, 34, 44, 55],
        labels=[
            "25-34",
            "35-44",
            "45-55",
        ],
        ordered=True,
    )

    results = []

    for age_group in [
        "25-34",
        "35-44",
        "45-55",
    ]:
        group_data = age_data[
            age_data["age_group"].astype("string")
            == age_group
        ].copy()

        single_year_result = estimate_log_log_regression(
            group_data,
            child_income_column="child_income_2022",
            parent_income_column="parent_income_2022",
            model_name=f"Single-year: age {age_group}",
        )

        single_year_result["age_group"] = age_group
        single_year_result["income_measure"] = "Single-year"
        results.append(single_year_result)

        multi_year_result = estimate_log_log_regression(
            group_data,
            child_income_column="child_income_average",
            parent_income_column="parent_income_average",
            model_name=f"Multi-year: age {age_group}",
        )

        multi_year_result["age_group"] = age_group
        multi_year_result["income_measure"] = "Multi-year"
        results.append(multi_year_result)

    return pd.DataFrame(results)


# ------------------------------------------------------------
# 9. Create the red-point IGE comparison figure
# ------------------------------------------------------------

def create_comparison_figure(regression_results):
    """
    Plot the two main estimates as red points with 95% confidence
    intervals.
    """

    model_order = [
        "Single-year income",
        "Multi-year average income",
    ]

    plot_data = (
        regression_results[
            regression_results["model"].isin(
                model_order
            )
        ]
        .set_index("model")
        .loc[model_order]
        .reset_index()
    )

    positions = np.arange(
        len(plot_data)
    )

    labels = [
        "Single-year income\n(2022)",
        "Two-year average income\n(2020 and 2022)",
    ]

    figure, axis = plt.subplots(
        figsize=(8.5, 5.5)
    )

    for position, row in zip(
        positions,
        plot_data.to_dict("records"),
    ):
        estimate = row["ige_estimate"]

        lower_error = (
            estimate
            - row["confidence_interval_low"]
        )

        upper_error = (
            row["confidence_interval_high"]
            - estimate
        )

        axis.errorbar(
            position,
            estimate,
            yerr=[
                [lower_error],
                [upper_error],
            ],
            fmt="o",
            color=RED,
            markerfacecolor=RED,
            markeredgecolor="white",
            markeredgewidth=1.2,
            ecolor=DARK_GRAY,
            capsize=7,
            markersize=11,
            linewidth=2,
        )

        axis.annotate(
            f"{estimate:.3f}",
            xy=(
                position,
                row["confidence_interval_high"],
            ),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=11,
            fontweight="bold",
            color=RED,
        )

    sample_size = int(
        plot_data["observations"].iloc[0]
    )

    axis.set_title(
        "Intergenerational Income Elasticity",
        fontsize=17,
        fontweight="bold",
        pad=25,
    )

    axis.text(
        0.5,
        1.01,
        (
            f"Common sample: {sample_size:,} children "
            "ages 25–55 in separate households"
        ),
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=10.5,
        color="#444444",
    )

    axis.set_xticks(
        positions,
        labels,
    )

    axis.set_xlabel(
        "Income measurement",
        fontsize=12,
    )

    axis.set_ylabel(
        "Estimated IGE coefficient",
        fontsize=12,
    )

    axis.set_ylim(
        0,
        max(
            plot_data["confidence_interval_high"]
        ) + 0.06,
    )

    axis.grid(
        axis="y",
        alpha=0.25,
    )

    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)

    figure.text(
        0.5,
        0.015,
        (
            "Notes: Red points show OLS coefficients; bars show "
            "95% confidence intervals using HC1 robust standard errors."
        ),
        ha="center",
        fontsize=9,
        color="#555555",
    )

    figure.tight_layout(
        rect=[0, 0.06, 1, 1]
    )

    figure.savefig(
        COMPARISON_FIGURE_FILE,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(figure)


# ------------------------------------------------------------
# 10. Create the blue-and-pink age-group figure
# ------------------------------------------------------------

def create_age_figure(age_results):
    """
    Plot multi-year estimates in bright blue and single-year
    estimates in pink, with 95% confidence intervals.
    """

    age_order = [
        "25-34",
        "35-44",
        "45-55",
    ]

    positions = np.arange(
        len(age_order)
    )

    styles = {
        "Single-year": {
            "color": PINK,
            "marker": "o",
            "offset": -0.06,
        },
        "Multi-year": {
            "color": BRIGHT_BLUE,
            "marker": "s",
            "offset": 0.06,
        },
    }

    figure, axis = plt.subplots(
        figsize=(9, 5.8)
    )

    sample_sizes = {}

    for income_measure in [
        "Single-year",
        "Multi-year",
    ]:
        group = (
            age_results[
                age_results["income_measure"]
                == income_measure
            ]
            .set_index("age_group")
            .loc[age_order]
            .reset_index()
        )

        sample_sizes.update(
            dict(
                zip(
                    group["age_group"],
                    group["observations"],
                )
            )
        )

        x_values = (
            positions
            + styles[income_measure]["offset"]
        )

        lower_error = (
            group["ige_estimate"]
            - group["confidence_interval_low"]
        )

        upper_error = (
            group["confidence_interval_high"]
            - group["ige_estimate"]
        )

        axis.errorbar(
            x_values,
            group["ige_estimate"],
            yerr=[
                lower_error,
                upper_error,
            ],
            color=styles[income_measure]["color"],
            marker=styles[income_measure]["marker"],
            markerfacecolor=styles[
                income_measure
            ]["color"],
            markeredgecolor="white",
            markeredgewidth=1,
            markersize=9,
            linewidth=2.4,
            capsize=5,
            label=income_measure,
        )

    tick_labels = [
        (
            f"{age_group}\n"
            f"(n={int(sample_sizes[age_group]):,})"
        )
        for age_group in age_order
    ]

    axis.set_title(
        "IGE Estimates Across the Child Life Cycle",
        fontsize=17,
        fontweight="bold",
        pad=25,
    )

    axis.text(
        0.5,
        1.01,
        (
            "Multi-year estimates exceed single-year estimates "
            "in every age group"
        ),
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=10.5,
        color="#444444",
    )

    axis.set_xticks(
        positions,
        tick_labels,
    )

    axis.set_xlabel(
        "Child age in 2023",
        fontsize=12,
    )

    axis.set_ylabel(
        "Estimated IGE coefficient",
        fontsize=12,
    )

    axis.set_ylim(
        0.20,
        0.43,
    )

    axis.legend(
        title="Income measure",
        frameon=False,
    )

    axis.grid(
        axis="y",
        alpha=0.25,
    )

    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)

    figure.text(
        0.5,
        0.015,
        (
            "Notes: Multi-year estimates are shown in bright blue "
            "and single-year estimates in pink. Bars show 95% "
            "confidence intervals using HC1 robust standard errors."
        ),
        ha="center",
        fontsize=9,
        color="#555555",
    )

    figure.tight_layout(
        rect=[0, 0.07, 1, 1]
    )

    figure.savefig(
        AGE_FIGURE_FILE,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(figure)


# ------------------------------------------------------------
# 11. Run the analysis
# ------------------------------------------------------------

def main():
    if not DATABASE_FILE.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_FILE}"
        )

    RESULTS_TABLE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RESULTS_FIGURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = duckdb.connect(
        str(DATABASE_FILE)
    )

    try:
        validate_database(connection)

        create_pair_household_status(connection)
        create_child_income_measures(connection)
        create_regression_sample(connection)

        analysis_data = connection.execute(
            """
            SELECT *
            FROM ige_analysis_sample
            ORDER BY
                child_1968_id,
                child_person_number
            """
        ).df()

        sample_summary = connection.execute(
            """
            SELECT
                'all matched children'
                    AS statistic,
                COUNT(*)
                    AS value
            FROM child_income_measures

            UNION ALL

            SELECT
                'children age 25-55',
                COUNT(*)
            FROM child_income_measures
            WHERE child_age_2023 BETWEEN 25 AND 55

            UNION ALL

            SELECT
                'common regression sample',
                COUNT(*)
            FROM ige_analysis_sample
            """
        ).df()

        single_year_result = (
            estimate_log_log_regression(
                analysis_data,
                child_income_column="child_income_2022",
                parent_income_column="parent_income_2022",
                model_name="Single-year income",
            )
        )

        multi_year_result = (
            estimate_log_log_regression(
                analysis_data,
                child_income_column="child_income_average",
                parent_income_column="parent_income_average",
                model_name="Multi-year average income",
            )
        )

        rank_result = estimate_rank_rank_regression(
            analysis_data
        )

        regression_results = pd.DataFrame(
            [
                single_year_result,
                multi_year_result,
                rank_result,
            ]
        )

        age_results = estimate_by_age_group(
            analysis_data
        )

        analysis_data.to_csv(
            ANALYSIS_SAMPLE_FILE,
            index=False,
        )

        regression_results.to_csv(
            REGRESSION_RESULTS_FILE,
            index=False,
        )

        age_results.to_csv(
            AGE_RESULTS_FILE,
            index=False,
        )

        sample_summary.to_csv(
            SAMPLE_SUMMARY_FILE,
            index=False,
        )

        create_comparison_figure(
            regression_results
        )

        create_age_figure(
            age_results
        )

        print("\n" + "=" * 70)
        print("IGE SAMPLE SUMMARY")
        print("=" * 70)
        print(
            sample_summary.to_string(
                index=False
            )
        )

        print("\n" + "=" * 70)
        print("MAIN REGRESSION RESULTS")
        print("=" * 70)
        print(
            regression_results[
                [
                    "model",
                    "observations",
                    "ige_estimate",
                    "standard_error",
                    "r_squared",
                ]
            ].to_string(
                index=False
            )
        )

        print("\n" + "=" * 70)
        print("AGE-GROUP RESULTS")
        print("=" * 70)
        print(
            age_results[
                [
                    "age_group",
                    "income_measure",
                    "observations",
                    "ige_estimate",
                ]
            ].to_string(
                index=False
            )
        )

        print("\n" + "=" * 70)
        print("FIGURES UPDATED")
        print("=" * 70)
        print(COMPARISON_FIGURE_FILE)
        print(AGE_FIGURE_FILE)

    finally:
        connection.close()

    print("\nIGE analysis completed successfully.")


if __name__ == "__main__":
    main()
