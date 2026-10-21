import os
import pandas as pd
from safe_paths import resolve_inside

DOCUMENTS_DIR = "documents"


def _find_data_file(filename: str) -> str:
    """Locate a CSV or Excel file inside the documents folder, blocking access outside it."""
    full_path = resolve_inside(DOCUMENTS_DIR, filename)

    if not os.path.isfile(full_path):
        raise FileNotFoundError(f"File '{filename}' not found in documents folder.")

    return full_path


def _load_dataframe(filename: str) -> pd.DataFrame:
    """Load a CSV or Excel file into a pandas DataFrame."""
    path = _find_data_file(filename)

    if filename.endswith(".csv"):
        return pd.read_csv(path)
    elif filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    else:
        raise ValueError("Unsupported file type. Use .csv or .xlsx")


def summarize_data_file(filename: str) -> str:
    """Return a summary of a CSV/Excel file: columns, row count, and basic statistics."""
    try:
        df = _load_dataframe(filename)

        summary = []
        summary.append(f"File: {filename}")
        summary.append(f"Rows: {len(df)}")
        summary.append(f"Columns: {', '.join(str(c) for c in df.columns)}")
        summary.append("\nNumeric column statistics:")
        summary.append(df.describe().to_string())

        return "\n".join(summary)
    except Exception as e:
        return f"Error summarizing file: {e}"


if __name__ == "__main__":
    result = summarize_data_file("sales_data.csv")
    print(result)