"""Write the API's OpenAPI document to a file, for the frontend's typed client.

uv run python -m scripts.export_openapi ../frontend/src/api/openapi.json
"""

import json
import sys
from pathlib import Path


def main(target: str) -> None:
    from src.interfaces.main import app  # noqa: PLC0415 - importing the app starts logging and reads settings

    Path(target).write_text(json.dumps(app.openapi(), indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
