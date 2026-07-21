import shutil
import subprocess

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildFrontend(build_py):
    def run(self):
        if shutil.which("npm"):
            subprocess.run(["npm", "ci"], cwd="frontend", check=True)
            subprocess.run(["npm", "run", "build"], cwd="frontend", check=True)
        super().run()


setup(cmdclass={"build_py": BuildFrontend})
