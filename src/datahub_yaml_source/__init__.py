from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from datahub_yaml_source.yaml_source import YamlSource

__all__ = ["YamlSource"]

try:
    __version__ = _version("datahub-yaml-source")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0"
