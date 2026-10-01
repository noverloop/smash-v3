"""Placeholder smoke test — verifies the package is importable. Once
design.py and smash_state.py are moved into src/smash/, replace this
with real test_design.py / test_smash_state.py files."""

import smash


def test_package_importable():
    assert hasattr(smash, "__version__")
    assert smash.__version__ == "0.1.0"
