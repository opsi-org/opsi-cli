"""
test_package_helpers.py is a test file for the helpers functions used in the package plugin.
"""

from pathlib import Path

from plugins.package.python.install_helpers import sort_packages_by_dependency

TEST_DATA_PATH = Path("tests/test_data/plugins/package")


def test_sort_packages_by_dependency() -> None:
	"""
	The opsi packages and their dependencies are as follows:
	- test-opsi-package_1.0-5.opsi: testdepends1, testdepends2, testdepends3
	- testdepends1_1.0-2.opsi: testdepends3
	- testdepends2_1.0-2.opsi: testdepends3, testdepends4
	- testdepends3_1.0-2.opsi: testdepends4
	- testdepends4_1.0-2.opsi: testdepends5
	- testdepends5_1.0-2.opsi: None
	- testdepends6_1.0-2.opsi: None
	"""
	packages = [
		"test-opsi-package_1.0-5.opsi",
		"testdepends1_1.0-2.opsi",
		"testdepends5_1.0-2.opsi",
		"testdepends3_1.0-2.opsi",
		"testdepends2_1.0-2.opsi",
		"testdepends4_1.0-2.opsi",
		"testdepends6_1.0-2.opsi",
	]
	packages = [str(TEST_DATA_PATH / pkg) for pkg in packages]

	expected_order = [
		"testdepends5_1.0-2.opsi",
		"testdepends4_1.0-2.opsi",
		"testdepends3_1.0-2.opsi",
		"testdepends1_1.0-2.opsi",
		"testdepends2_1.0-2.opsi",
		"test-opsi-package_1.0-5.opsi",
		"testdepends6_1.0-2.opsi",
	]
	expected_order = [(TEST_DATA_PATH / pkg) for pkg in expected_order]

	assert sort_packages_by_dependency(packages) == expected_order
