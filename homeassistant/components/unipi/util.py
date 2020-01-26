"""Utilities."""


def norm_circuit(name):
    """Normalize circuit name to underscore notation."""
    return name.upper().replace(" ", "_").replace(".", "_")
