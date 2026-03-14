from __future__ import annotations

from core.app_factory import create_app
from core.runtime import init_db


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        init_db()

    app.run(host="127.0.0.1", port=5000)
