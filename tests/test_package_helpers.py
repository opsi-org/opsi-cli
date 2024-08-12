"""
test_package_helpers.py is a test file for the helpers functions used in the package plugin.
"""

from pathlib import Path

from opsicommon.package import OpsiPackage

from plugins.package.python.install_helpers import fix_custom_package_name, map_and_sort_packages

TEST_DATA_PATH = Path("tests/test_data/plugins/package")


def test_map_and_sort_packages() -> None:
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
		str(TEST_DATA_PATH / package)
		for package in [
			"test-opsi-package_1.0-5.opsi",
			"testdepends1_1.0-2.opsi",
			"testdepends5_1.0-2.opsi",
			"testdepends3_1.0-2.opsi",
			"testdepends2_1.0-2.opsi",
			"testdepends4_1.0-2.opsi",
			"testdepends6_1.0-2.opsi",
		]
	]

	expected_result = {
		TEST_DATA_PATH / "testdepends5_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdepends5_1.0-2.opsi"),
		TEST_DATA_PATH / "testdepends4_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdepends4_1.0-2.opsi"),
		TEST_DATA_PATH / "testdepends3_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdepends3_1.0-2.opsi"),
		TEST_DATA_PATH / "testdepends1_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdepends1_1.0-2.opsi"),
		TEST_DATA_PATH / "testdepends2_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdepends2_1.0-2.opsi"),
		TEST_DATA_PATH / "test-opsi-package_1.0-5.opsi": OpsiPackage(TEST_DATA_PATH / "test-opsi-package_1.0-5.opsi"),
		TEST_DATA_PATH / "testdepends6_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdepends6_1.0-2.opsi"),
	}

	result = map_and_sort_packages(packages)

	for path, expected_package in expected_result.items():
		assert path in result
		assert result[path].product.id == expected_package.product.id


def test_fix_custom_package_name() -> None:
	package_path = TEST_DATA_PATH / "testpackage_1.0-2~custom.opsi"
	expected_package_name = "testpackage_1.0-2.opsi"
	assert fix_custom_package_name(package_path) == expected_package_name
