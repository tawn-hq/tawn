"""Internal entrypoint for the background web server process.

Run as: python -m tawn._webserver <port>
Not intended for direct user invocation — use `tawn web start/stop`.
"""

import sys


def _start_auto_compiler(engine) -> None:
    import threading
    import time
    from tawn.db import session as db_session
    from tawn.compiler.compiler import run_compile as run_compiler
    from tawn.federation.merge import scan_all_sources, merge_pending
    from tawn.home import tawn_home

    # Bootstrap: ingest + merge all existing federation files on startup
    with db_session(engine) as s:
        n = scan_all_sources(tawn_home(), s)
        if n > 0:
            merge_pending(tawn_home(), s)

    def _loop():
        while True:
            try:
                with db_session(engine) as session:
                    run_compiler(tawn_home(), session)
            except Exception:
                pass
            time.sleep(30 * 60)  # 30-minute interval

    t = threading.Thread(target=_loop, name="tawn-auto-compiler", daemon=True)
    t.start()


def main(port: int = 8787) -> None:
    import uvicorn
    from tawn.db import make_engine
    from tawn.web import create_app

    from tawn.db import init_db
    from tawn.updater import start_daily_updater
    engine = make_engine(pooled=True)
    init_db(engine)
    start_daily_updater()
    _start_auto_compiler(engine)
    uvicorn.run(
        create_app(engine),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    main(port)
