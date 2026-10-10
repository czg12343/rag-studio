"""Export public source files without Git metadata or local runtime data."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "dist" / "rag-studio-source.zip"
# Explicit paths prevent new private files from silently entering a release.
REQUIRED = (
    "README.md", ".gitignore", ".env.example", "main.py", "app.py",
    "eval_rag.py", "requirements.txt", "requirements-dev.txt",
    "requirements-semantic.txt", "start_all.bat", "start_all.ps1",
    "install_and_start.bat", "frontend/.env.example", "frontend/index.html",
    "frontend/package.json", "frontend/package-lock.json",
    "frontend/tsconfig.json", "frontend/tsconfig.node.json",
    "frontend/vite.config.ts", "data/eval_questions.json",
    "data/db/.gitkeep", "data/uploads/.gitkeep", "data/vector_store/.gitkeep",
    "docs/AUDIT.md", "docs/UPLOAD_FIX.md", "docs/VALIDATION.md",
    "docs/screenshots/README.md", "docs/evaluation.json",
)
SOURCE_GLOBS = (
    "modules/*.py", "tests/*.py", "scripts/*.py",
    "frontend/src/**/*.vue", "frontend/src/**/*.ts", "frontend/src/**/*.css",
    "examples/corpus/*.md",
)


def source_files() -> list[Path]:
    paths = {ROOT / name for name in REQUIRED}
    missing = sorted(str(path.relative_to(ROOT)) for path in paths if not path.is_file())
    if missing:
        raise RuntimeError("Required release files are missing: " + ", ".join(missing))
    for pattern in SOURCE_GLOBS:
        paths.update(ROOT.glob(pattern))
    # Never follow a symlink to a private file, inside or outside the repository.
    for path in paths:
        if not path.is_file() or any(part.is_symlink() for part in (path, *path.parents)):
            raise RuntimeError("Unsupported release path: " + str(path.relative_to(ROOT)))
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def main() -> None:
    files = source_files()
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(ARCHIVE, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Created dist/{ARCHIVE.name}: {len(files)} public source files")
    print("Excluded Git metadata, API configuration, uploads, databases, indices and logs.")


if __name__ == "__main__":
    main()
