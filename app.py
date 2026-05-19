"""
Entry point for running the AI Concierge application.

Usage:
    python app.py
    OR
    uvicorn app.main:app --reload (from project root)
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
