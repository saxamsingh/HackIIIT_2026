"""uvicorn entry point:  uvicorn app.main:app --reload"""

from .factory import create_app

app = create_app()
