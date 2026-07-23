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
        # Only run npm if the dist hasn't been built yet.
        # Pre-built dist is used as-is so npm ci never nukes node_modules.
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

        super().run()


setup(cmdclass={"build_py": BuildFrontend})
