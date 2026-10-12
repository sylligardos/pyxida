"""Marks src/app as a package so the demo can `from app.utils import ...`.

The exploratory app's own pages keep importing `utils` directly -- their
directory comes first on sys.path when Streamlit runs them -- so both import
styles work and neither app has to copy the other's helpers.
"""
