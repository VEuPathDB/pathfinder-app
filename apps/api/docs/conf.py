"""Sphinx configuration for Pathfinder API documentation."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Autodoc copies source annotation text onto every class in a documented
# class's MRO, which restores BaseModel.__pydantic_extra__. A model with
# extra="allow" must be built before that happens.
for _early in (
    "fastapi.openapi.models",
    "langchain_core.messages",
    "pathfinder.transport.http.schemas.sites",
):
    importlib.import_module(_early)

# -- Project information -----------------------------------------------------

project = "PathFinder API"
copyright = "2026, Ahmed Muharram"  # noqa: A001
author = "Ahmed Muharram"
version = "0.1.0-alpha"
release = "0.1.0-alpha"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinxcontrib.mermaid",
    "sphinx_inline_tabs",
]

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "show-inheritance": True,
}
python_use_unqualified_type_names = True

# A third-party base class docstring is not this project's API contract.
autodoc_inherit_docstrings = False

# Include type hints in parameter descriptions for clarity.
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented_params"

templates_path = ["_templates"]
exclude_patterns = []

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
}

# -- HTML output -------------------------------------------------------------

html_theme = "furo"

html_logo = "_static/pathfinder-logo.png"
html_favicon = "_static/pathfinder-logo.png"

html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#2563eb",
        "color-brand-content": "#1d4ed8",
        "color-admonition-background": "#f0f9ff",
        "color-announcement-background": "#1e3a5f",
        "color-announcement-text": "#ffffff",
    },
    "dark_css_variables": {
        "color-brand-primary": "#60a5fa",
        "color-brand-content": "#93bbfd",
        "color-admonition-background": "#1e293b",
        "color-announcement-background": "#1e3a5f",
        "color-announcement-text": "#e2e8f0",
    },
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
    "top_of_page_buttons": ["view", "edit"],
    "source_repository": "https://github.com/VEuPathDB/pathfinder-app",
    "source_branch": "main",
    "source_directory": "apps/api/docs/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/VEuPathDB/pathfinder-app",
            "html": (
                '<svg stroke="currentColor" fill="currentColor" stroke-width="0" '
                'viewBox="0 0 16 16"><path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 '
                "3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37"
                "-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 "
                "1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64"
                "-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 "
                "2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82"
                ".44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95"
                ".29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013"
                ' 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>'
            ),
            "class": "",
        },
    ],
}

html_static_path = ["_static"]
html_css_files = ["custom.css"]

# Announcement banner
html_theme_options["announcement"] = (
    "PathFinder is a research prototype for "
    "<b>VEuPathDB strategy construction via LLM agents</b>. "
    '<a href="https://github.com/VEuPathDB/pathfinder-app">View on GitHub</a>'
)

# -- Copy button settings ----------------------------------------------------

copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

# -- Mermaid settings --------------------------------------------------------

mermaid_version = "11"
mermaid_d3_zoom = False
