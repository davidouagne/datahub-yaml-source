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


def test_load_repository_reports_unknown_field_but_still_parses_document(tmp_path: Path):
    # `glossaryTerms` is not a valid field on TAG per the entity registry
    # (see models.py's Has* mixin matrix) -- neither is the misspelled `nam`.
    (tmp_path / "assets.yml").write_text(
        "kind: TAG\nname: pii\nglossaryTerms: [oops]\n---\nkind: TAG\nnam: typo\nname: ok\n"
    )

    unknown = []
    repo = load_repository(
        tmp_path,
        on_error=lambda path, msg: None,
        on_unknown_fields=lambda path, kind, fields: unknown.append((kind, fields)),
    )

    assert len(repo.tags) == 2
    assert unknown == [("TAG", ["glossaryTerms"]), ("TAG", ["nam"])]


def test_load_repository_does_not_flag_raw_aspect_extra_fields_as_unknown(tmp_path: Path):
    # RawAspectDoc's extra fields ARE its payload -- must never be reported.
    (tmp_path / "assets.yml").write_text(
        "aspectName: DATASET_PROFILE\n"
        "dataset: {platform: postgres, name: x, env: PROD}\n"
        "rowCount: 100\n"
    )

    unknown = []
    load_repository(
        tmp_path,
        on_error=lambda path, msg: None,
        on_unknown_fields=lambda path, kind, fields: unknown.append((kind, fields)),
    )

    assert unknown == []


def test_load_repository_parses_query(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: QUERY\nid: q_patients_actifs\nstatement: select 1\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.queries) == 1
    assert repo.queries[0].id == "q_patients_actifs"
    assert repo.queries[0].statement == "select 1"


def test_load_repository_parses_incident(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: INCIDENT\nid: inc1\ntype: OPERATIONAL\n"
        "entities: ['urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)']\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.incidents) == 1
    assert repo.incidents[0].id == "inc1"
    assert repo.incidents[0].type == "OPERATIONAL"


def test_load_repository_parses_document(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: DOCUMENT\nid: runbook_patient\ntitle: Runbook patient\ntext: '## Steps'\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.documents) == 1
    assert repo.documents[0].id == "runbook_patient"
    assert repo.documents[0].title == "Runbook patient"


def test_load_repository_parses_ml_entities(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: MLFEATURE_TABLE\nname: patient_features\nplatform: feast\n"
        "---\n"
        "kind: MLFEATURE\nfeatureNamespace: patient_features\nname: age_at_admission\n"
        "---\n"
        "kind: MLPRIMARY_KEY\nfeatureNamespace: patient_features\nname: patient_id\n"
        "sources: [{platform: postgres, name: ehr_public_patient, env: PROD, fieldPath: patient_id}]\n"
        "---\n"
        "kind: MLMODEL_GROUP\nname: readmission_risk\nplatform: mlflow\n"
        "---\n"
        "kind: MLMODEL\nname: readmission_risk_v3\nplatform: mlflow\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.ml_feature_tables) == 1
    assert repo.ml_feature_tables[0].name == "patient_features"
    assert len(repo.ml_features) == 1
    assert repo.ml_features[0].featureNamespace == "patient_features"
    assert len(repo.ml_primary_keys) == 1
    assert repo.ml_primary_keys[0].sources[0].fieldPath == "patient_id"
    assert len(repo.ml_model_groups) == 1
    assert len(repo.ml_models) == 1
    assert repo.ml_models[0].platform == "mlflow"


def test_load_repository_parses_semantic_model_and_metric(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: SEMANTIC_MODEL\nplatform: dbt\npath: models/marts\nid: patients_actifs\n"
        "---\n"
        "kind: METRIC\nplatform: dbt\npath: models/marts\nid: taux_readmission\n"
        "semanticModel: {platform: dbt, path: models/marts, id: patients_actifs}\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.semantic_models) == 1
    assert repo.semantic_models[0].id == "patients_actifs"
    assert len(repo.metrics) == 1
    assert repo.metrics[0].semanticModel.id == "patients_actifs"


def test_load_repository_parses_software_catalog(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: REPOSITORY\nid: aphp-pathling\nname: aphp/pathling\n"
        "---\n"
        "kind: API\nid: fhir-patient-search-api\nname: Recherche patients\n"
        "sourceRepository: aphp-pathling\n"
        "---\n"
        "kind: AGENT_SKILL\nid: fhir-query-skill\nname: Interrogation FHIR\n"
        "---\n"
        "kind: AI_AGENT\nid: cohort-builder-agent\nname: Agent cohorte\n"
        "dependencies: {skills: [fhir-query-skill]}\n"
        "---\n"
        "kind: SERVICE\nid: pathling-fhir-server\ndisplayName: Serveur FHIR\n"
        "apis: [fhir-patient-search-api]\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.repositories) == 1
    assert repo.repositories[0].id == "aphp-pathling"
    assert len(repo.apis) == 1
    assert repo.apis[0].sourceRepository == "aphp-pathling"
    assert len(repo.agent_skills) == 1
    assert len(repo.ai_agents) == 1
    assert repo.ai_agents[0].dependencies.skills == ["fhir-query-skill"]
    assert len(repo.services) == 1
    assert repo.services[0].apis == ["fhir-patient-search-api"]


def test_load_repository_aggregates_across_multiple_files(tmp_path: Path):
    (tmp_path / "layer1").mkdir()
    (tmp_path / "layer1" / "assets.yml").write_text("kind: TAG\nname: from_layer1\n")
    (tmp_path / "layer2").mkdir()
    (tmp_path / "layer2" / "assets.yml").write_text("kind: TAG\nname: from_layer2\n")

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert {t.name for t in repo.tags} == {"from_layer1", "from_layer2"}


def test_load_repository_parses_chart(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: CHART\nname: patients_par_mois\nplatform: superset\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.charts) == 1
    assert repo.charts[0].name == "patients_par_mois"
    assert repo.charts[0].platform == "superset"


def test_load_repository_parses_dashboard(tmp_path: Path):
    (tmp_path / "assets.yml").write_text(
        "kind: DASHBOARD\nname: cockpit_patients\nplatform: superset\n"
        "charts:\n  - {platform: superset, name: patients_par_mois}\n"
    )

    repo = load_repository(tmp_path, on_error=lambda path, msg: None)

    assert len(repo.dashboards) == 1
    assert repo.dashboards[0].name == "cockpit_patients"
    assert repo.dashboards[0].charts[0].name == "patients_par_mois"
