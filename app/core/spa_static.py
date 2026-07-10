"""Static file serving with SPA fallback (index.html for unknown routes)."""
from __future__ import annotations

import os

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse


class SPAStaticFiles(StaticFiles):
    """Serve static assets; fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            index = os.path.join(self.directory, "index.html")
            return FileResponse(index)
