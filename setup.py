from setuptools import find_packages, setup

setup(
    name="datahub-yaml-source",
    version="0.1.0",
    description="DataHub ingestion source that reads declarative YAML metadata files.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        # >=1.6.0 for the SDK V2 constructor kwargs the cross-cutting aspect
        # helpers in builders/common.py depend on (e.g. DataFlow/DataJob's
        # `parent_container=`, `links=`, `structured_properties=`).
        "acryl-datahub>=1.7.0",
        "pyyaml>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "deepdiff>=6.0.0",
            "jsonschema>=4.0.0",
        ],
    },
    entry_points={
        "datahub.ingestion.source.plugins": [
            "yaml = datahub_yaml_source.yaml_source:YamlSource",
        ],
    },
)
