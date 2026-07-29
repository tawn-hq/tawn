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

    def _bootstrap_then_loop():
        # Bootstrap: ingest + merge all existing federation files on startup.
        # Runs in this background thread, not before uvicorn.run() — a
        # source directory can hold thousands of files (a size cap on
        # individual files exists, but the walk itself over many entries
        # still takes real time), and the web server must bind its port
        # immediately regardless of how long that one-time scan takes.
        try:
            with db_session(engine) as s:
                n = scan_all_sources(tawn_home(), s)
                if n > 0:
                    merge_pending(tawn_home(), s)
        except Exception:
            pass

        while True:
            try:
                with db_session(engine) as session:
                    run_compiler(tawn_home(), session)
            except Exception:
                pass

            # Enrichment runs after compile and in its own try: it is
            # best-effort by contract, so a missing local model must degrade
            # quality without stopping the loop that also drives compile and
            # federation merge.
            try:
                from tawn.compiler.enrich import run_enrich
                with db_session(engine) as session:
                    run_enrich(tawn_home(), session, limit=200)
            except Exception:
                pass

            try:
                from tawn.model.rollup import reconcile
                with db_session(engine) as session:
                    reconcile(tawn_home(), session)
            except Exception:
                # Observability is best-effort and must never stop the loop
                # that also drives compile, enrich and federation merge.
                pass

            try:
                # Parsed attachment text is kept on disk so a turn can
                # reference it by id. Without a sweep every document ever
                # dragged into chat stays there in full, indefinitely.
                from tawn.memory.attachments import sweep as sweep_attachments

                sweep_attachments(tawn_home())
            except Exception:
                pass

            try:
                import datetime as _dt

                from tawn.observer.config import load_observer_config
                from tawn.observer.review import process_pending
                from tawn.observer.sessions import close_idle_sessions

                with db_session(engine) as session:
                    close_idle_sessions(
                        session,
                        load_observer_config(tawn_home()),
                        _dt.datetime.now(_dt.timezone.utc),
                    )
                    process_pending(session, tawn_home())
            except Exception:
                # The Observer is best-effort like enrichment: a failure here
                # must not stop the loop that also drives compile and merge.
                # Sweeping here as well as in the watcher means sessions still
                # close when the watcher is not running.
                pass

            time.sleep(30 * 60)  # 30-minute interval

    t = threading.Thread(target=_bootstrap_then_loop, name="tawn-auto-compiler", daemon=True)
    t.start()


def _start_observer(engine) -> None:
    """Run the ambient observer in a daemon thread, if it is granted at all."""
    import threading
    import time

    from sqlalchemy.orm import Session
    from tawn.capability.grants import Grants
    from tawn.home import tawn_home
    from tawn.observer.watch import ObserverWatcher

    home = tawn_home()
    # Deny-all by default: with no `observe:` entries the thread is never
    # started, so the Observer costs nothing until it is asked for.
    try:
        if not Grants.load(home / "grants.yaml").observe:
            return
    except Exception:
        return

    def _loop():
        backoff = 5
        while True:
            try:
                ObserverWatcher(home, lambda: Session(engine)).run()
                backoff = 5
            except Exception:
                # A crashed watcher must not take the web server with it, and
                # must not spin: back off, cap, retry.
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)

    threading.Thread(target=_loop, name="tawn-observer", daemon=True).start()


def main(port: int = 8787) -> None:
    import uvicorn
    from tawn.db import make_engine
    from tawn.web import create_app
    from tawn.staleness import clear_running_fingerprint, write_running_fingerprint

    from tawn.db import init_db
    from tawn.updater import start_daily_updater
    engine = make_engine(pooled=True)
    init_db(engine)

    # Record which code this process started with, so a later CLI invocation
    # can tell the user their daemon is older than the files on disk instead
    # of leaving them to conclude a fix did not work.
    from tawn.home import tawn_home as _th
    write_running_fingerprint(_th(), "web")
    start_daily_updater()
    _start_auto_compiler(engine)
    _start_observer(engine)
    try:
        uvicorn.run(
            create_app(engine),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    finally:
        # A stopped daemon must not leave a fingerprint behind, or the next
        # staleness check would report on a process that no longer exists.
        clear_running_fingerprint(_th(), "web")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    main(port)
