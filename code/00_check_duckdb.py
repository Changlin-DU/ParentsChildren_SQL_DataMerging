import duckdb
import pandas as pd


def main():
    # Synthetic data used only to test Python and SQL.
    toy_pairs = pd.DataFrame(
        {
            "child_id": [1, 2, 3, 4],
            "parent_id": [101, 102, 103, 104],
            "child_income": [45_000, 60_000, 72_000, 90_000],
            "parent_income": [40_000, 55_000, 80_000, 100_000],
        }
    )

    connection = duckdb.connect(database=":memory:")
    connection.register("toy_parent_child_pairs", toy_pairs)

    query = """
        SELECT
            COUNT(*) AS number_of_pairs,
            AVG(child_income) AS mean_child_income,
            AVG(parent_income) AS mean_parent_income
        FROM toy_parent_child_pairs
    """

    result = connection.execute(query).df()

    print("DuckDB SQL test completed successfully.")
    print(result)

    connection.close()


if __name__ == "__main__":
    main()
