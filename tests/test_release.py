"""Public exports must never grow when unrelated files appear in a checkout."""
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/check_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def manifest(package, entries):
    (package / "export-manifest.json").write_text(json.dumps(["export-manifest.json", *entries]))


def test_export_ignores_unlisted_notes_and_configuration(tmp_path):
    manifest(tmp_path, ["README.md"])
    (tmp_path / "README.md").write_text("Public guide")
    (tmp_path / "private-notes.md").write_text("Must stay local")
    (tmp_path / "config.json").write_text("{}")
    assert {str(relative) for _, relative in release.source_files(tmp_path)} == {"export-manifest.json", "README.md"}


@pytest.mark.parametrize("entry", ["../outside.md", "/outside.md", "docs/../README.md", "docs\\note.md", "C:/outside.md", "./README.md", "missing.md"])
def test_export_rejects_unsafe_or_missing_paths(tmp_path, entry):
    manifest(tmp_path, [entry])
    with pytest.raises(ValueError):
        list(release.source_files(tmp_path))


def test_export_rejects_symlinked_directory(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("Must stay local")
    try:
        (package / "docs").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable for this account")
    manifest(package, ["docs/note.md"])
    with pytest.raises(ValueError, match="symlinks"):
        list(release.source_files(package))


def test_release_refuses_output_inside_source_before_creating_it(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    monkeypatch.setattr(release, "__file__", str(package / "scripts/check_release.py"))
    with pytest.raises(ValueError, match="outside"):
        release.check(package / "release")
    assert not (package / "release").exists()


def test_checked_in_manifest_has_all_required_files():
    paths = {relative.as_posix() for _, relative in release.source_files(ROOT)}
    assert {"LICENSE", "THIRD_PARTY.md", "licenses/spending-effort-with-jev.MIT.txt", "tests/test_release.py", ".github/workflows/tests.yml"} <= paths
