from typing import Any, Dict, List, Optional, Union

from pydantic import Field, model_validator

from datahub.configuration.git import GitInfo
from datahub.ingestion.source.aws.s3_util import is_s3_uri
from datahub.ingestion.source.common.http_connection_config import HTTPConnectionConfig
from datahub.ingestion.source.state.stale_entity_removal_handler import (
    StatefulStaleMetadataRemovalConfig,
)
from datahub.ingestion.source.state.stateful_ingestion_base import (
    StatefulIngestionConfigBase,
)

from datahub_yaml_source.loader import is_http_uri


class YamlSourceConfig(StatefulIngestionConfigBase):
    """Source configuration for the YAML metadata-as-code connector.

    This source has no connection of its own -- every platform, environment,
    and instance is declared per-entity inside the YAML files themselves.
    """

    path: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="One or more locations to scan for '*.yml' / '*.yaml' metadata "
        "files: a local directory (scanned recursively), an 's3://bucket/prefix' "
        "(scanned recursively too, requires 'aws_connection'), or an "
        "'https://.../file.yml' URL naming a single file (HTTP has no directory "
        "listing, so each URL must point at one file -- since the format is "
        "multi-document YAML, one URL can still carry a whole catalog; requires "
        "'http_connection' only for authenticated endpoints). Accepts a list to "
        "combine several locations in one recipe. When 'git_info' is not set, this "
        "is required. When 'git_info' is set, a relative local-directory entry is "
        "resolved against the cloned checkout -- use '.' (the default) to scan the "
        "whole repository, or a subdirectory to scope the scan to a subtree; "
        "'s3://'/'http(s)://' entries are not allowed together with 'git_info'.",
    )

    aws_connection: Optional[Dict[str, Any]] = Field(
        default=None,
        description="AWS credentials/config for reading 's3://' entries in 'path', "
        "in the same shape as other DataHub sources' 'aws_connection' "
        "(aws_access_key_id, aws_secret_access_key, aws_role, aws_profile, "
        "aws_region, ...). Required whenever 'path' includes an 's3://' entry -- "
        "set it to an empty mapping ('{}') to use the default boto3 credential "
        "chain (env vars, ~/.aws/credentials, instance role, ...) instead of "
        "explicit keys. Requires the 's3' extra "
        "(`pip install datahub-yaml-source[s3]`).",
    )

    http_connection: Optional[HTTPConnectionConfig] = Field(
        default=None,
        description="Authentication/TLS options for reading 'http(s)://' entries in "
        "'path' (bearer token or basic auth, TLS certificate verification). Not "
        "required for a public, unauthenticated URL.",
    )

    max_input_file_bytes: Optional[int] = Field(
        default=None,
        description="Reject (and skip, reporting a warning) any individual scanned "
        "file larger than this many bytes. Mainly a safety cap for remote "
        "('s3://'/'http(s)://') entries in 'path', where an unexpectedly large file "
        "would otherwise be pulled fully into memory before parsing. Unset "
        "(default) means no limit.",
    )

    git_info: Optional[GitInfo] = Field(
        default=None,
        description="Git repository to shallow-clone before scanning, instead of "
        "reading from an already-checked-out local directory. 'repo' accepts an "
        "https://github.com/... or https://gitlab.com/... URL (or 'org/repo' "
        "shorthand for GitHub), and should NOT end in '.git'. The clone itself "
        "always goes through 'repo_ssh_locator', which DataHub derives as an SSH "
        "URL by default -- for a PUBLIC repo with no deploy key, you must set "
        "'repo_ssh_locator' explicitly to the 'https://.../repo.git' clone URL, "
        "or the clone attempts SSH auth with no key and fails. For a PRIVATE "
        "repo, set 'deploy_key_file' or 'deploy_key' to an SSH deploy key with "
        "read access; the SSH clone URL is then inferred automatically for "
        "GitHub/GitLab. On Windows, also set 'clone_timeout: null' -- "
        "GitPython's kill_after_timeout (used to enforce the default 300s "
        "clone_timeout) is not supported on Windows and the clone fails "
        "outright otherwise. Requires the 'git' extra "
        "(`pip install datahub-yaml-source[git]`).",
    )

    fail_on_unresolved_reference: bool = Field(
        default=False,
        description="If true, a reference to a tag/domain/glossary term/container "
        "that was never declared anywhere in the scanned files raises an error "
        "instead of a warning.",
    )

    stateful_ingestion: Optional[StatefulStaleMetadataRemovalConfig] = Field(
        default=None,
        description="Stateful ingestion configuration for stale entity removal. "
        "Enable this to automatically soft-delete entities that were removed "
        "from the YAML files since the last run.",
    )

    @model_validator(mode="after")
    def _default_path_and_require_source(self) -> "YamlSourceConfig":
        if self.git_info is not None:
            if self.path is None:
                self.path = "."
        elif self.path is None:
            raise ValueError(
                "'path' is required when 'git_info' is not set."
            )
        return self

    @model_validator(mode="after")
    def _validate_path_entries(self) -> "YamlSourceConfig":
        if self.path is None:
            return self
        entries = self.path if isinstance(self.path, list) else [self.path]

        for entry in entries:
            if is_s3_uri(entry) and self.aws_connection is None:
                raise ValueError(
                    f"'aws_connection' is required when 'path' includes an s3:// "
                    f"entry: {entry}"
                )
            if self.git_info is not None and (is_s3_uri(entry) or is_http_uri(entry)):
                raise ValueError(
                    f"'path' entries cannot be s3:// or http(s):// URIs when "
                    f"'git_info' is set (they are resolved against the git "
                    f"checkout, not fetched remotely): {entry}"
                )
        return self
