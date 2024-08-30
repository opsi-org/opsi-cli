"""
test_package_helpers.py is a test file for the helpers functions used in the package plugin.
"""

from pathlib import Path
from unittest.mock import patch

from opsicommon.package import OpsiPackage

from plugins.package.python.package_helpers import map_and_sort_packages, update_product_properties

TEST_DATA_PATH = Path("tests/test_data/plugins/package")


def test_map_and_sort_packages() -> None:
	"""
	The opsi packages and their dependencies are as follows:
	- test1_1.0-5.opsi: testdependency1, testdependency2, testdependency3
	- testdependency1_1.0-5.opsi: testdependency3
	- testdependency2_1.0-2.opsi: testdependency3, testdependency4
	- testdependency3_1.0-2.opsi: testdependency4
	- testdependency4_1.0-5.opsi: testdependency5
	- testdependency5_1.2-2.opsi: None
	- test2_1.0-5.opsi: None
	"""

	packages = [
		str(TEST_DATA_PATH / package)
		for package in [
			"test1_1.0-5.opsi",
			"testdependency1_1.0-5.opsi",
			"testdependency5_1.2-2.opsi",
			"testdependency3_1.0-2.opsi",
			"testdependency2_1.0-2.opsi",
			"testdependency4_1.0-5.opsi",
			"test2_1.0-5.opsi",
		]
	]

	expected_result = {
		TEST_DATA_PATH / "testdependency5_1.2-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdependency5_1.2-2.opsi"),
		TEST_DATA_PATH / "testdependency4_1.0-5.opsi": OpsiPackage(TEST_DATA_PATH / "testdependency4_1.0-5.opsi"),
		TEST_DATA_PATH / "testdependency3_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdependency3_1.0-2.opsi"),
		TEST_DATA_PATH / "testdependency1_1.0-5.opsi": OpsiPackage(TEST_DATA_PATH / "testdependency1_1.0-5.opsi"),
		TEST_DATA_PATH / "testdependency2_1.0-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdependency2_1.0-2.opsi"),
		TEST_DATA_PATH / "test1_1.0-5.opsi": OpsiPackage(TEST_DATA_PATH / "test1_1.0-5.opsi"),
		TEST_DATA_PATH / "test2_1.0-5.opsi": OpsiPackage(TEST_DATA_PATH / "test2_1.0-5.opsi"),
	}

	result = map_and_sort_packages(packages)

	for path, expected_package in expected_result.items():
		assert path in result
		assert result[path].product.id == expected_package.product.id


def test_update_product_properties() -> None:
	"""
	The package testdependency5_1.2-2.opsi has the following properties:
	1. boolean property: editable=False, default=[False]
	2. multivalue editable property: editable=True, values=["value1", "value2"]
	"""
	path_to_opsipackage_dict = {TEST_DATA_PATH / "testdependency5_1.2-2.opsi": OpsiPackage(TEST_DATA_PATH / "testdependency5_1.2-2.opsi")}
	user_inputs = [
		"True",  # boolean property
		"new1",  # multivalue editable property
		"value1",
		"done",
	]

	with patch("builtins.input", side_effect=user_inputs):
		update_product_properties(path_to_opsipackage_dict)

	opsi_package = path_to_opsipackage_dict[TEST_DATA_PATH / "testdependency5_1.2-2.opsi"]
	for product_property in opsi_package.product_properties:
		if product_property.editable:
			assert product_property.defaultValues == ["new1", "value1"]
		else:
			assert product_property.defaultValues == [True]
