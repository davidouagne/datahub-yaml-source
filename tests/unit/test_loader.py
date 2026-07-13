from pathlib import Path

from datahub_yaml_source.loader import discover_yaml_files, load_repository


def test_discover_yaml_files_finds_yml_and_yaml_recursively(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.yml").write_text("kind: TAG\nname: a\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "two.yaml").write_text("kind: TAG\nname: b\n")
    (tmp_path / "ignore.txt").write_text("not yaml")

    found = discover_yaml_files(tmp_path)

    assert {p.name for p in found} == {"one.yml", "two.yaml"}


def test_load_repository_parses_multi_document_file(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: TAG\nname: pii\n---\nkind: DOMAIN\nid: d1\nname: Domain One\n"
    )

    errors = []
    repo = load_repository(tmp_path, on_error=lambda path, msg: errors.append((path, msg)))

    assert not errors
    assert len(repo.tags) == 1
    assert repo.tags[0].name == "pii"
    assert len(repo.domains) == 1
    assert repo.domains[0].id == "d1"


def test_load_repository_skips_invalid_document_but_keeps_valid_ones(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: TAG\nname: pii\n---\nkind: DATASET\nname: missing_platform\n"
    )

    errors = []
    repo = load_repository(tmp_path, on_error=lambda path, msg: errors.append((path, msg)))

    assert len(errors) == 1
    assert "Invalid document" in errors[0][1]
    assert len(repo.tags) == 1
    assert len(repo.datasets) == 0


def test_load_repository_skips_unknown_kind_and_continues(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: NOT_A_KIND\nname: mystery\n---\nkind: TAG\nname: ok\n"
    )

    errors = []
    repo = load_repository(tmp_path, on_error=lambda path, msg: errors.append((path, msg)))

    assert len(errors) == 1
    assert len(repo.tags) == 1


def test_load_repository_handles_malformed_yaml_file(tmp_path: Path):
    (tmp_path / "broken.yml").write_text("kind: TAG\nname: [unterminated\n")

    errors = []
    repo = load_repository(tmp_path, on_error=lambda path, msg: errors.append((path, msg)))

    assert len(errors) == 1
    assert "Failed to parse YAML" in errors[0][1]
    assert len(repo.tags) == 0


def test_load_repository_skips_empty_documents_between_separators(tmp_path: Path):
    (tmp_path / "assets.yml").write_text("---\nkind: TAG\nname: a\n---\n---\nkind: TAG\nname: b\n")

    errors = []
    repo = load_repository(tmp_path, on_error=lambda path, msg: errors.append((path, msg)))

    assert not errors
    assert len(repo.tags) == 2


def test_load_repository_invokes_on_file_scanned_once_per_file(tmp_path: Path):
    (tmp_path / "a.yml").write_text("kind: TAG\nname: a\n")
    (tmp_path / "b.yaml").write_text("kind: TAG\nname: b\n")

    scanned = []
    load_repository(
        tmp_path,
        on_error=lambda path, msg: None,
        on_file_scanned=lambda path: scanned.append(path),
    )

    assert len(scanned) == 2


def test_load_repository_aggregates_across_multiple_files(tmp_path: Path):
    (tmp_path / "layer1").mkdir()
    (tmp_path / "layer1" / "assets.yml").write_text("kind: TAG\nname: from_layer1\n")
    (tmp_path / "layer2").mkdir()
    (tmp_path / "layer2" / "assets.yml").write_text("kind: TAG\nname: from_layer2\n")

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert {t.name for t in repo.tags} == {"from_layer1", "from_layer2"}
