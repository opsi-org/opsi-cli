# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_package_helpers.py is a test file for the helpers functions used in the package plugin.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from opsi.opsi.package import OpsiPackage
from opsi.opsi.service.client import ServiceClient
from opsi.opsi.service.model.object import Product, ProductOnClient, ProductOnDepot, ProductProperty, ProductPropertyState

from plugins.package.python.package_helpers import (
	check_locked_products,
	handle_action_request,
	initialize_opsi_package,
	map_and_sort_packages,
	update_product_property_defaults_interactively,
)

TEST_DATA_PATH = Path("tests/test_data/plugins/package")


def test_check_locked_products_rejects_empty_depot_selection() -> None:
	service_client = MagicMock()

	with pytest.raises(ValueError, match="No depots found"):
		check_locked_products(service_client, [], {})

	service_client.jsonrpc.assert_not_called()


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
		update_product_property_defaults_interactively(path_to_opsipackage_dict)

	opsi_package = path_to_opsipackage_dict[TEST_DATA_PATH / "testdependency5_1.2-2.opsi"]
	for product_property in opsi_package.product_properties:
		if product_property.editable:
			assert product_property.defaultValues == ["new1", "value1"]
		else:
			assert product_property.defaultValues == [True]


def test_handle_action_request() -> None:
	service_client = MagicMock()
	service_client.jsonrpc.side_effect = [
		[{"depotId": "pytest-depot1.test.tld", "clientId": "pytest-client1.test.tld"}],  # get_clients_from_depot
		[
			ProductOnClient(
				clientId="pytest-client1.test.tld",
				productId="testproduct",
				installationStatus="installed",
				productType="LocalbootProduct",
				productVersion="1.0",
				packageVersion="1",
			)
		],  # get_product_on_clients
		[],  # call to productOnClient_updateObjects
	]
	product = Product(id="testproduct", productVersion="1.0", packageVersion="1")
	product.setSetupScript("setup_script")

	handle_action_request(
		service_client=service_client, depot_id="pytest-depot1.test.tld", product=product, action_request="setup", dependency=False
	)

	service_client.jsonrpc.assert_any_call("configState_getClientToDepotserver", ["pytest-depot1.test.tld"])
	service_client.jsonrpc.assert_any_call(
		"productOnClient_getObjects",
		[[], {"clientId": ["pytest-client1.test.tld"], "productId": "testproduct", "installationStatus": "installed"}],
	)
	service_client.jsonrpc.assert_any_call(
		"productOnClient_updateObjects",
		[
			[
				ProductOnClient(
					clientId="pytest-client1.test.tld",
					productId="testproduct",
					installationStatus="installed",
					actionRequest="setup",
					productType="LocalbootProduct",
				)
			]
		],
	)


@pytest.mark.parametrize("properties", ["keep", "package"])
def test_initialize_opsi_package(properties) -> None:
	"""
	Test the initialize_opsi_package function.
	"""

	def mock_jsonrpc(self, method: str, params: list | None = None) -> list:
		if method == "productProperty_getObjects":
			return [
				ProductProperty(
					productId="opsi-client-agent",
					propertyId="allow_reboot",
					defaultValues=[True],
					editable=False,
					productVersion="4.3.9.2",
					packageVersion="2",
				)
			]
		if method == "productPropertyState_getObjects":
			return [ProductPropertyState(productId="opsi-client-agent", propertyId="allow_reboot", values=[False], objectId="foo.bar.baz")]
		return [Product("dummy", productVersion="1.0", packageVersion="1")]

	pod = ProductOnDepot(
		productId="opsi-client-agent",
		productType="LocalbootProduct",
		productVersion="4.3.9.2",
		packageVersion="2",
		depotId="foo.bar.baz",
	)
	service_client = ServiceClient()
	with patch("plugins.package.python.package_helpers.ServiceClient.jsonrpc", mock_jsonrpc):
		opsi_package = initialize_opsi_package(service_client, pod, "foo.bar.baz", properties=properties)
	if properties == "keep":
		assert opsi_package.product_properties[0].propertyId == "allow_reboot"
		assert opsi_package.product_properties[0].defaultValues == [False]
	elif properties == "package":
		assert opsi_package.product_properties[0].propertyId == "allow_reboot"
		assert opsi_package.product_properties[0].defaultValues == [True]
