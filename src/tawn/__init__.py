"""Tawn — the personal digital twin. Capability-gated memory core."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Read from installed package metadata rather than hardcoding.
#
# This was a literal string, so it drifted from pyproject.toml the moment the
# project version was bumped: the update page reported 0.1.0 while 0.2.0 was
# installed and running. One fact, one source.
try:
    __version__ = _pkg_version("tawn")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0+unknown"
