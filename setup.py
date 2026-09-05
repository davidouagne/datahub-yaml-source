from pathlib import Path

from setuptools import find_packages, setup

_long_description = Path(__file__).parent.joinpath("README.md").read_text(encoding="utf-8")

setup(
    name="datahub-yaml-source",
    # Version is derived from Git tags by setuptools-scm; see
    # [tool.setuptools_scm] in pyproject.toml. Do not add a static
    # version= here -- the presence of that table is what activates the
    # plugin, and a static value would shadow it.
    description="DataHub ingestion source that reads declarative YAML metadata files.",
    long_description=_long_description,
    long_description_content_type="text/markdown",
    author="David Ouagne",
    author_email="david.ouagne@aphp.fr",
    license="Apache-2.0",
    license_files=["LICENSE"],
    url="https://github.com/davidouagne/datahub-yaml-source",
    project_urls={
        "Homepage": "https://github.com/davidouagne/datahub-yaml-source",
        "Issues": "https://github.com/davidouagne/datahub-yaml-source/issues",
        "Changelog": "https://github.com/davidouagne/datahub-yaml-source/releases",
    },
    keywords=["datahub", "metadata", "ingestion", "yaml", "metadata-as-code", "data-catalog"],
    classifiers=[
        # An untagged pre-1.0 connector maintained by one person, outside the
        # DataHub Ingestion team -- mirrors yaml_source.py's @support_status.
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    # acryl-datahub>=1.7.0 itself requires Python >=3.10 (its PyPI
    # classifiers list only 3.10/3.11/3.12) -- this floor tracks that,
    # not an independent choice; CI matrices 3.10-3.12 accordingly.
    python_requires=">=3.10",
    install_requires=[
        # >=1.6.0 for the SDK V2 constructor kwargs the cross-cutting aspect
        # helpers in builders/common.py depend on (e.g. DataFlow/DataJob's
        # `parent_container=`, `links=`, `structured_properties=`).
        #
        # Upper bound <1.7.0.5: the (still ExperimentalWarning) datahub.sdk.*
        # surface this connector builds on takes undeprecated breaks inside
        # the 1.7.0.x series --
        #   * 1.7.0.5: SemanticModel.add_dataset stops accepting bare
        #     dataset URNs (now needs a SemanticModelDataset), breaking
        #     builders/semantic.py and the integration golden;
        #   * 1.7.0.8: the SupportStatus enum is renamed
        #     (CERTIFIED/INCUBATING/TESTING -> ALPHA/BETA/GA), breaking
        #     yaml_source.py's @support_status at import.
        # 1.7.0.4 is the last release the suite passes on. Lifting this cap
        # means migrating both call sites (and regenerating the golden) --
        # tracked as its own task, not folded in here.
        "acryl-datahub>=1.7.0,<1.7.0.5",
        "pyyaml>=6.0",
        # models.py/loader.py/yaml_source_config.py import pydantic directly
        # for the config schema and validation. Only ever a transitive dep
        # today (acryl-datahub itself requires pydantic>=2.4.0,<3.0.0
        # unconditionally); declared explicitly so our own use of it isn't
        # silently dependent on that staying true. Same range as upstream's
        # own floor, to avoid a resolver conflict.
        "pydantic>=2.4.0,<3.0.0",
        # loader.py/yaml_source.py lazily import requests for the http(s)://
        # 'path' code path. Only ever a *two-hop* transitive dep today
        # (acryl-datahub unconditionally requires requests_file, which in
        # turn requires requests>=1.0.0 -- an essentially unconstrained
        # floor); declared explicitly with a floor actually exercised by
        # our own requests.get(..., stream=True)/requests.head(...) calls.
        "requests>=2.28.0,<3",
    ],
    extras_require={
        # GitInfo.clone() (datahub.configuration.git) lazily imports GitPython;
        # it's in the base acryl-datahub wheel but the dependency isn't, so
        # 'git_info' in a recipe needs this extra installed.
        "git": [
            "GitPython>=3.1.37,<4",
        ],
        # 'aws_connection' + an s3:// entry in 'path' needs boto3, which DataHub's
        # AwsConnectionConfig (datahub.ingestion.source.aws.aws_common) hard-imports
        # at module level -- lazily imported only inside YamlSource's S3 code paths,
        # so local-only/git-only/http-only recipes never need this extra.
        "s3": [
            "boto3>=1.35.0,<2",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "deepdiff>=6.0.0",
            "jsonschema>=4.0.0",
            "GitPython>=3.1.37,<4",
            "boto3>=1.35.0,<2",
            # Lint/format and type-check, run by .github/workflows/quality.yml
            # (see spec/spec-process-cicd-quality.md). Ruff is capped to a
            # minor because its lint rules shift between minors; local and CI
            # must agree on the exact ruleset.
            "ruff>=0.12,<0.13",
            "mypy>=1.17",
        ],
    },
    entry_points={
        "datahub.ingestion.source.plugins": [
            "yaml = datahub_yaml_source.yaml_source:YamlSource",
        ],
    },
)
