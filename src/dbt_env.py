"""Turn DATABASE_URL into the DBT_* variables read by dbt/profiles.yml.

The pipeline stores a single connection string; dbt needs host, port, user... separately.

    GitHub Actions:  python -m src.dbt_env            (writes to $GITHUB_ENV, password masked)
    PowerShell:      python -m src.dbt_env | Invoke-Expression
"""
import os

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

from src.db import DEFAULT_URL


def dbt_variables(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    local = url.host in ("localhost", "127.0.0.1")
    return {
        "DBT_HOST": url.host or "localhost",
        "DBT_PORT": str(url.port or 5432),
        "DBT_USER": url.username or "",
        "DBT_PASSWORD": url.password or "",
        "DBT_DBNAME": url.database or "",
        "DBT_SSLMODE": "prefer" if local else "require",
    }


def main() -> None:
    load_dotenv()
    variables = dbt_variables(os.getenv("DATABASE_URL", DEFAULT_URL))
    github_env = os.getenv("GITHUB_ENV")
    if github_env:
        print(f"::add-mask::{variables['DBT_PASSWORD']}")
        with open(github_env, "a", encoding="utf-8") as f:
            for key, value in variables.items():
                f.write(f"{key}={value}\n")
        print("dbt connection variables set for host", variables["DBT_HOST"])
    else:
        for key, value in variables.items():
            print(f"$env:{key} = '{value}'")


if __name__ == "__main__":
    main()
