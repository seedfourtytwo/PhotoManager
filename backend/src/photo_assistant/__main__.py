"""`python -m photo_assistant` starts the API server."""

import uvicorn

from photo_assistant.api.main import create_app
from photo_assistant.api.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
