"""Include the prebuilt UI in Python distributions without requiring Node at install time."""
from pathlib import Path
import shutil

from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        source = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
        if not (source / 'index.html').is_file():
            raise RuntimeError('Missing frontend/dist/index.html; run npm run build in frontend first.')
        build_root = Path(self.build_lib).resolve()
        package = (build_root / 'group_watch').resolve()
        if not package.is_relative_to(build_root):
            raise RuntimeError('Frontend build destination escaped the package build directory.')
        # A previous wheel build may contain packages removed by a layout change.
        if package.exists():
            shutil.rmtree(package)
        super().run()
        destination = package / '_static'
        shutil.copytree(source, destination)

    def get_outputs(self, include_bytecode=1):
        outputs = super().get_outputs(include_bytecode)
        target = Path(self.build_lib) / 'group_watch' / '_static'
        return outputs + [str(path) for path in target.rglob('*') if path.is_file()]
