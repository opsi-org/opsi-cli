from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pipreqs import pipreqs

from opsicli import plugin


@pytest.mark.parametrize(
	"requirement",
	[
		"requests @ git+https://github.com/psf/requests",
		"requests @ https://example.org/requests-2.32.3-py3-none-any.whl",
	],
)
def test_install_dependencies_installs_direct_reference(
	tmp_path: Path,
	monkeypatch: pytest.MonkeyPatch,
	requirement: str,
) -> None:
	plugin_dir = tmp_path / "plugin"
	plugin_dir.mkdir()
	requirements_file = plugin_dir / "requirements.txt"
	requirements_file.write_text(f"{requirement}\n", encoding="utf-8")
	target_dir = tmp_path / "lib"
	target_dir.mkdir()

	dependency = {"name": requirement, "version": ""}
	monkeypatch.setattr(
		pipreqs,
		"parse_requirements",
		Mock(return_value=[dependency]),
	)
	import_module = Mock(return_value=SimpleNamespace(__version__="999.0"))
	monkeypatch.setattr(plugin.importlib, "import_module", import_module)
	install_package = Mock()
	monkeypatch.setattr(plugin, "install_python_package", install_package)

	plugin.install_dependencies(plugin_dir, target_dir)

	import_module.assert_not_called()
	install_package.assert_called_once_with(target_dir, dependency)
	assert (target_dir / "requirements.txt").read_text(encoding="utf-8") == f"{requirement}\n"
