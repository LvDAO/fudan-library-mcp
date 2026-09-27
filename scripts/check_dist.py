"""Check release archives and write a SHA-256 manifest, without extracting files."""

import hashlib
import os
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path


def main():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and tag != f"v{version}":
        raise ValueError(f"Tag {tag} does not match package version {version}")
    wheel = Path(f"dist/fudan_library_mcp-{version}-py3-none-any.whl")
    sdist = Path(f"dist/fudan_library_mcp-{version}.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_path = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        if metadata["Name"] != project["name"] or metadata["Version"] != version:
            raise ValueError("Wheel metadata does not match project")
        if metadata["License-Expression"] != "MIT":
            raise ValueError("Wheel license metadata is missing")
        if "fudan_library_mcp/server.py" not in names:
            raise ValueError("Wheel does not contain server")
        if not any(n.endswith("/licenses/LICENSE") for n in names):
            raise ValueError("Wheel does not contain license")
        entry_points = next(n for n in names if n.endswith(".dist-info/entry_points.txt"))
        if b"fudan-library-mcp = fudan_library_mcp.server:main" not in archive.read(entry_points):
            raise ValueError("Wheel console entry point is missing")
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        forbidden = {".research", ".venv", ".env", ".git", "__pycache__"}
        if any(forbidden.intersection(Path(m.name).parts) or m.issym() for m in members):
            raise ValueError("Unexpected private/runtime files in source archive")
        root = f"fudan_library_mcp-{version}/"
        names = {m.name for m in members}
        for required in ["LICENSE", "README.md", "uv.lock", "src/fudan_library_mcp/server.py"]:
            if root + required not in names:
                raise ValueError(f"Source archive missing {required}")
    manifest = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in [wheel, sdist]
    )
    Path("dist/SHA256SUMS").write_text(manifest, encoding="utf-8", newline="\n")
    print(manifest, end="")


if __name__ == "__main__":
    main()
