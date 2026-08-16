"""S3 and HTTP(S) support in loader.py: discovery, reads, and size enforcement.

Uses hand-rolled fakes rather than boto3/moto or a real HTTP server -- both
`_discover_s3_files`/`_read_s3_bytes` and `_read_http_bytes` are written
against a narrow duck-typed interface (an object with `.get_s3_client()`
returning something with `.get_paginator()`/`.get_object()`; `requests.get()`
returning something with `.raise_for_status()`/`.headers`/`.iter_content()`),
so a fake exercising exactly that interface is simpler and faster than a real
S3/HTTP stack and keeps the 's3' extra out of the base test dependencies.
"""

import io

import pytest
import requests

from datahub_yaml_source.loader import discover_yaml_files, load_repository


# --- S3 fakes -------------------------------------------------------------


class _FakePaginator:
    def __init__(self, keys, page_size=2):
        self._keys = keys
        self._page_size = page_size

    def paginate(self, Bucket, Prefix):
        matching = [k for k in self._keys if k.startswith(Prefix)]
        for i in range(0, len(matching), self._page_size):
            yield {"Contents": [{"Key": k} for k in matching[i : i + self._page_size]]}


class _FakeS3Client:
    def __init__(self, keys, bodies=None):
        self._keys = keys
        self._bodies = bodies or {}

    def get_paginator(self, operation_name):
        assert operation_name == "list_objects_v2"
        return _FakePaginator(self._keys)

    def get_object(self, Bucket, Key):
        body = self._bodies[Key]
        return {"Body": io.BytesIO(body), "ContentLength": len(body)}


class _FakeAwsConnection:
    def __init__(self, keys, bodies=None):
        self._client = _FakeS3Client(keys, bodies)

    def get_s3_client(self):
        return self._client


# --- HTTP fakes -------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, content: bytes, headers=None, ok=True):
        self._content = content
        self.headers = headers or {}
        self._ok = ok

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if not self._ok:
            raise requests.HTTPError("simulated HTTP failure")

    def iter_content(self, chunk_size):
        data = self._content
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]


# --- discover_yaml_files: s3:// ---------------------------------------------


def test_discover_yaml_files_s3_lists_prefix_recursively_across_pages():
    aws_connection = _FakeAwsConnection(
        keys=[
            "layer1/a.yml",
            "layer1/nested/b.yaml",
            "layer2/c.yml",
            "layer1/ignore.txt",
        ]
    )

    found = discover_yaml_files("s3://bucket/layer1", aws_connection=aws_connection)

    assert found == ["s3://bucket/layer1/a.yml", "s3://bucket/layer1/nested/b.yaml"]


def test_discover_yaml_files_s3_extension_match_is_case_insensitive():
    aws_connection = _FakeAwsConnection(keys=["a.YML", "b.Yaml", "c.txt"])

    found = discover_yaml_files("s3://bucket/", aws_connection=aws_connection)

    assert found == ["s3://bucket/a.YML", "s3://bucket/b.Yaml"]


def test_discover_yaml_files_s3_requires_aws_connection():
    with pytest.raises(ValueError, match="aws_connection"):
        discover_yaml_files("s3://bucket/prefix", aws_connection=None)


# --- discover_yaml_files: http(s):// ----------------------------------------


def test_discover_yaml_files_http_returns_single_url_unchanged():
    found = discover_yaml_files("https://example.com/catalog.yml")

    assert found == ["https://example.com/catalog.yml"]


def test_discover_yaml_files_http_rejects_glob_pattern():
    with pytest.raises(ValueError, match="Glob patterns"):
        discover_yaml_files("https://example.com/*.yml")


# --- load_repository: s3:// --------------------------------------------------


def test_load_repository_reads_s3_object(monkeypatch):
    body = b"kind: TAG\nname: from_s3\n"
    aws_connection = _FakeAwsConnection(keys=["assets.yml"], bodies={"assets.yml": body})

    repo = load_repository(
        "s3://bucket/",
        on_error=lambda path, msg: (_ for _ in ()).throw(AssertionError(msg)),
        aws_connection=aws_connection,
    )

    assert len(repo.tags) == 1
    assert repo.tags[0].name == "from_s3"


def test_load_repository_enforces_max_input_file_bytes_for_s3():
    body = b"kind: TAG\nname: too_big\n"
    aws_connection = _FakeAwsConnection(keys=["assets.yml"], bodies={"assets.yml": body})

    errors = []
    repo = load_repository(
        "s3://bucket/",
        on_error=lambda path, msg: errors.append((path, msg)),
        aws_connection=aws_connection,
        max_input_file_bytes=5,
    )

    assert len(errors) == 1
    assert "max_input_file_bytes" in errors[0][1]
    assert len(repo.tags) == 0


# --- load_repository: http(s):// --------------------------------------------


def test_load_repository_reads_http_url(monkeypatch):
    body = b"kind: TAG\nname: from_http\n"

    def fake_get(url, timeout, stream, **kwargs):
        assert url == "https://example.com/catalog.yml"
        return _FakeHttpResponse(body, headers={"Content-Length": str(len(body))})

    monkeypatch.setattr(requests, "get", fake_get)

    repo = load_repository(
        "https://example.com/catalog.yml",
        on_error=lambda path, msg: (_ for _ in ()).throw(AssertionError(msg)),
    )

    assert len(repo.tags) == 1
    assert repo.tags[0].name == "from_http"


def test_load_repository_reports_http_error_status(monkeypatch):
    def fake_get(url, timeout, stream, **kwargs):
        return _FakeHttpResponse(b"", ok=False)

    monkeypatch.setattr(requests, "get", fake_get)

    errors = []
    load_repository(
        "https://example.com/missing.yml",
        on_error=lambda path, msg: errors.append((path, msg)),
    )

    assert len(errors) == 1
    assert "Failed to read file" in errors[0][1]


def test_load_repository_enforces_max_input_file_bytes_for_http_via_content_length(monkeypatch):
    body = b"kind: TAG\nname: too_big\n"

    def fake_get(url, timeout, stream, **kwargs):
        return _FakeHttpResponse(body, headers={"Content-Length": str(len(body))})

    monkeypatch.setattr(requests, "get", fake_get)

    errors = []
    load_repository(
        "https://example.com/catalog.yml",
        on_error=lambda path, msg: errors.append((path, msg)),
        max_input_file_bytes=5,
    )

    assert len(errors) == 1
    assert "max_input_file_bytes" in errors[0][1]


def test_load_repository_enforces_max_input_file_bytes_for_http_via_streaming_cap(monkeypatch):
    # No Content-Length header -- the cap must still be enforced while streaming.
    body = b"kind: TAG\nname: too_big\n"

    def fake_get(url, timeout, stream, **kwargs):
        return _FakeHttpResponse(body, headers={})

    monkeypatch.setattr(requests, "get", fake_get)

    errors = []
    load_repository(
        "https://example.com/catalog.yml",
        on_error=lambda path, msg: errors.append((path, msg)),
        max_input_file_bytes=5,
    )

    assert len(errors) == 1
    assert "max_input_file_bytes" in errors[0][1]


# --- load_repository: mixed roots -------------------------------------------


def test_load_repository_combines_local_s3_and_http_roots(tmp_path, monkeypatch):
    (tmp_path / "local.yml").write_text("kind: TAG\nname: from_local\n")

    aws_connection = _FakeAwsConnection(
        keys=["s3asset.yml"], bodies={"s3asset.yml": b"kind: TAG\nname: from_s3\n"}
    )

    def fake_get(url, timeout, stream, **kwargs):
        return _FakeHttpResponse(b"kind: TAG\nname: from_http\n")

    monkeypatch.setattr(requests, "get", fake_get)

    repo = load_repository(
        [str(tmp_path), "s3://bucket/", "https://example.com/extra.yml"],
        on_error=lambda path, msg: (_ for _ in ()).throw(AssertionError(msg)),
        aws_connection=aws_connection,
    )

    assert {t.name for t in repo.tags} == {"from_local", "from_s3", "from_http"}
