"""Package application sources and a built frontend, excluding credentials and local data."""

import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
output = root / ".local" / "release.tar.gz"
output.parent.mkdir(exist_ok=True)
paths = [
    root / "backend" / "app",
    root / "backend" / "requirements.txt",
    root / "frontend" / "dist",
    root / "deploy",
]
with tarfile.open(output, "w:gz") as archive:
    for path in paths:
        for item in [path] if path.is_file() else path.rglob("*"):
            if item.is_file() and "__pycache__" not in item.parts:
                info = archive.gettarinfo(str(item), arcname=str(item.relative_to(root)))
                info.mode = 0o755 if item.suffix == ".sh" else 0o644
                with item.open("rb") as source:
                    archive.addfile(info, source)
print(output)
