"""Locate the built UI in a source checkout or an installed Python wheel."""
from pathlib import Path


def frontend_dist():
    package = Path(__file__).resolve().parent
    checkout = package.parents[1] / 'frontend' / 'dist'
    return checkout if (checkout / 'index.html').is_file() else package / '_static'
