"""Sphinx configuration for The Newsroom documentation."""
import os
import sys

import django

# Make the project importable and load the Django settings so autodoc can
# import models, views and other Django modules.
sys.path.insert(0, os.path.abspath(".."))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
django.setup()

# Autodoc prints class attributes; printing a QuerySet would query the
# database, which the docs build does not need. Show the model name instead.
from django.db.models.query import QuerySet  # noqa: E402

QuerySet.__repr__ = lambda self: f"<QuerySet of {self.model.__name__}>"

# -- Project information -----------------------------------------------------
project = "The Newsroom"
copyright = "2026, Jason Pretorius"
author = "Jason Pretorius"
release = "1.0.0"

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
]
autodoc_member_order = "bysource"
templates_path = ["_templates"]
# The Markdown design notes in this folder are not part of the Sphinx site.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "*.md"]
language = "en"

# -- Options for HTML output -------------------------------------------------
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
