"""libDiff exception hierarchy.

Library code must raise these instead of calling sys.exit.
"""


class LibDiffError(Exception):
    """Base error for libDiff."""


class ParseError(LibDiffError):
    """Liberty parse or I/O failure."""


class UnitConflictError(LibDiffError):
    """Incompatible units between libraries block numeric compare."""

    def __init__(self, message, unit_name=None, left=None, right=None):
        super().__init__(message)
        self.unit_name = unit_name
        self.left = left
        self.right = right
