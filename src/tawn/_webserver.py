"""Internal entrypoint for the background web server process.

Run as: python -m tawn._webserver <port>
Not intended for direct user invocation — use `tawn web start/stop`.
"""

import sys


def main(port: int = 8787) -> None:
    import uvicorn
    from tawn.db import make_engine
    from tawn.web import create_app

    engine = make_engine()
    uvicorn.run(
        create_app(engine),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    main(port)
