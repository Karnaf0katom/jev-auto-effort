"""Freeze this standalone package, test the export, build it and check a clean wheel.

Only package-owned source files are copied. No VCS checkout, host configuration,
decision ledger, session logs, provider credentials or CCC sources are exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile


def source_files(package):
    """Export reviewed paths only; adding a file never silently publishes it."""
    package = package.resolve()
    if (package / "export-manifest.json").is_symlink():
        raise ValueError("the standalone source export may not contain symlinks")
    entries = json.loads((package / "export-manifest.json").read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries or any(not isinstance(entry, str) for entry in entries):
        raise ValueError("export manifest must be a nonempty list of file paths")
    if len(set(entries)) != len(entries) or "export-manifest.json" not in entries:
        raise ValueError("export manifest must include itself without duplicate paths")
    for entry in sorted(entries):
        relative = PurePosixPath(entry)
        if relative.is_absolute() or ".." in relative.parts or "\\" in entry or ":" in entry or relative.as_posix() != entry:
            raise ValueError("export paths must be normalized relative paths")
        path = package.joinpath(*relative.parts)
        if any(part.is_symlink() for part in (path, *path.parents) if part != package and package in part.parents):
            raise ValueError("the standalone source export may not contain symlinks")
        if not path.is_file() or not path.resolve().is_relative_to(package):
            raise ValueError("export manifest entry must be a package file")
        yield path, Path(*relative.parts)


def check(output):
    package = Path(__file__).resolve().parents[1]
    output = output.resolve()
    if output == package or output.is_relative_to(package):
        raise ValueError("release output must be outside the package source tree")
    if output.exists() and any(output.iterdir()):
        raise ValueError("release output must be a fresh empty directory")
    output.mkdir(parents=True, exist_ok=True)
    environment = {key: value for key, value in os.environ.items() if key in (
        "PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL", "SSL_CERT_FILE",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "PIP_CACHE_DIR",
    )}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["SOURCE_DATE_EPOCH"] = "1792022400"
    manifest = []
    with tempfile.TemporaryDirectory(prefix="auto-effort-release-") as directory:
        work = Path(directory)
        export = work / "source"
        export.mkdir()
        for source, relative in source_files(package):
            destination = export / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            # These are portable source assets. Host umasks and group-write bits
            # must not become different wheel member permissions after pip
            # unpacks the source archive.
            destination.chmod(0o644)
            manifest.append({"path": relative.as_posix(), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
        environment["AUTO_EFFORT_LEDGER"] = str(work / "checks.sqlite3")

        def run(name, command):
            result = subprocess.run(command, cwd=export, env=environment, text=True, capture_output=True,
                                    timeout=180, umask=0o022 if os.name == "posix" else -1)
            (output / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                print((result.stdout + result.stderr)[-6000:], file=sys.stderr)
                raise RuntimeError(f"{name} failed; inspect its retained log")
            return result.stdout

        tests = run("tests", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
        run("build", [sys.executable, "-m", "build"])
        wheels = list((export / "dist").glob("*.whl"))
        sdists = list((export / "dist").glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise ValueError("expected exactly one wheel and one source distribution")
        with zipfile.ZipFile(wheels[0]) as archive:
            names = archive.namelist()
            if any(name.startswith(("ccc_server/", ".agent/", ".codex/")) for name in names):
                raise ValueError("wheel contains files outside the standalone package")
            if not any(name.endswith("licenses/spending-effort-with-jev.MIT.txt") for name in names):
                raise ValueError("wheel is missing the required third-party license")
        install = run("installation", [sys.executable, "scripts/check_install.py", "--wheel", str(wheels[0])])
        run("sdist-wheel", [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", "sdist-wheels", str(sdists[0])])
        rebuilt = list((export / "sdist-wheels").glob("*.whl"))
        artifacts = []
        for source in wheels + sdists:
            destination = output / source.name
            shutil.copy2(source, destination)
            artifacts.append({"file": destination.name, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
        if len(rebuilt) != 1:
            raise ValueError("source distribution did not produce exactly one wheel")
        if rebuilt[0].read_bytes() != wheels[0].read_bytes():
            diagnostic = output / "reproduction-failure"
            diagnostic.mkdir()
            shutil.copy2(rebuilt[0], diagnostic / rebuilt[0].name)
            with zipfile.ZipFile(wheels[0]) as first, zipfile.ZipFile(rebuilt[0]) as second:
                differences = []
                for name in sorted(set(first.namelist()) | set(second.namelist())):
                    if name not in first.namelist() or name not in second.namelist():
                        differences.append({"path": name, "reason": "missing_entry"})
                        continue
                    a, b = first.getinfo(name), second.getinfo(name)
                    if first.read(name) != second.read(name):
                        differences.append({"path": name, "reason": "content"})
                    elif (a.date_time, a.external_attr, a.compress_type, a.create_system) != (b.date_time, b.external_attr, b.compress_type, b.create_system):
                        differences.append({"path": name, "reason": "archive_metadata",
                                            "first": [a.date_time, a.external_attr, a.compress_type, a.create_system],
                                            "rebuilt": [b.date_time, b.external_attr, b.compress_type, b.create_system]})
                if first.namelist() != second.namelist():
                    differences.append({"reason": "entry_order"})
            (diagnostic / "differences.json").write_text(json.dumps(differences, indent=2) + "\n")
            print(json.dumps({"reproduction_differences": differences}), file=sys.stderr)
            raise ValueError("source distribution did not reproduce the checked wheel; both artifacts and differences were retained")
        # The editable standalone tree is reviewable before any publication.
        target = output / "source"
        if target.exists():
            raise ValueError("release output already contains a source export; choose a fresh output directory")
        shutil.copytree(export, target, ignore=shutil.ignore_patterns("dist", "build", "sdist-wheels", "*.egg-info", "__pycache__", ".pytest_cache"))
        result = {"schema_version": 1, "python": sys.version.split()[0], "platform": sys.platform,
                  "source_manifest": manifest, "artifacts": artifacts,
                  "tests": tests.strip().splitlines()[-1],
                  "clean_install": json.loads(install.strip().splitlines()[-1]),
                  "sdist_reproduces_wheel": True,
                  "publication": "not_performed"}
        (output / "RELEASE-MANIFEST.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({key: result[key] for key in ("python", "platform", "artifacts", "tests", "clean_install", "publication")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.output)


if __name__ == "__main__":
    main()
