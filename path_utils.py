from pathlib import Path

DATA_FILES_DIR = Path("data_files").resolve()


def get_validated_file_path(filename: str) -> Path:
    """Resolve and validate that filename is within DATA_FILES_DIR and is a file.

    Raises:
        ValueError: If the resolved path is outside DATA_FILES_DIR.
        FileNotFoundError: If the resolved path is not an existing file.
    """
    file_path = (DATA_FILES_DIR / filename).resolve()
    try:
        file_path.relative_to(DATA_FILES_DIR)
    except ValueError as exc:  # path traversal attempt
        raise ValueError("Invalid filename") from exc

    if not file_path.is_file():
        raise FileNotFoundError("File not found")

    return file_path
