import shutil
import subprocess
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = Path(__file__).parent
FRONTEND = HERE / "frontend"
DIST_SRC = FRONTEND / "dist"
# frontend dist lands inside the package so it's included in the wheel
DIST_DST = HERE / "src" / "tawn" / "web" / "dist"


class BuildFrontend(build_py):
    def run(self):
        # `python -m build`'s default flow builds the wheel from an
        # isolated copy of the *sdist*, not the working tree — and the
        # sdist never contains the top-level frontend/ dir (it's not part
        # of the Python package, so nothing declares it for inclusion).
        # `src/tawn/web/dist` DOES ship in the sdist (it's inside the
        # package, matched by package-data), so if the workflow already
        # populated it — build the frontend, then `cp -r dist/. ../src/
        # tawn/web/dist/`, exactly like publish.yml — there's nothing left
        # to do here and no reason to expect frontend/ to exist at all.
        already_bundled = DIST_DST.is_dir() and any(DIST_DST.iterdir())
        if not already_bundled:
            if FRONTEND.is_dir():
                if not DIST_SRC.is_dir():
                    if shutil.which("npm"):
                        subprocess.run(["npm", "ci"], cwd=str(FRONTEND), check=True)
                        subprocess.run(["npm", "run", "build"], cwd=str(FRONTEND), check=True)
                    else:
                        import warnings
                        warnings.warn("npm not found — web dashboard will not be bundled", stacklevel=2)
                if DIST_SRC.is_dir():
                    if DIST_DST.exists():
                        shutil.rmtree(DIST_DST)
                    shutil.copytree(DIST_SRC, DIST_DST)
            else:
                import warnings
                warnings.warn(
                    "frontend/ not present (isolated sdist build?) and no "
                    "pre-built web/dist — web dashboard will not be bundled",
                    stacklevel=2,
                )

        super().run()


setup(cmdclass={"build_py": BuildFrontend})
