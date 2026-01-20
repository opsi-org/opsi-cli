# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_package.py is a test file for the package plugin.
"""

import re
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import patch

import pytest
from opsicommon.client.opsiservice import DAVFileInfo, ServiceClient
from opsicommon.logging import get_logger
from opsicommon.objects import (
	LocalbootProduct,
	NetbootProduct,
	OpsiClient,
	OpsiDepotserver,
	ProductOnClient,
	ProductOnDepot,
	ProductPropertyState,
)
from opsicommon.package import OpsiPackage
from opsicommon.testing.helpers import http_test_server

from plugins.package.python import combine_products

from .conftest import get_admin_service_client
from .utils import run_cli, tmp_product

TEST_DATA_PATH = Path("tests/test_data/plugins/package")

CONTROL_FILE_NAME = "control"
CONTROL_TOML_FILE_NAME = "control.toml"

TESTPRODUCT = "testproduct"
PACKAGE_VERSION = "1"
PRODUCT_VERSION = "1.0"
NEW_PRODUCT_VERSION = "1.1"

BASE_CONTROL_FILE = f"""[Package]
version: {PACKAGE_VERSION}

[Product]
type: localboot
id: {TESTPRODUCT}
version: {{}}
"""

CONTROL_FILE = BASE_CONTROL_FILE.format(PRODUCT_VERSION)
CONTROL_FILE_LEGACY = BASE_CONTROL_FILE.format(NEW_PRODUCT_VERSION)

BASE_CONTROL_TOML = f"""[Package]
version = {PACKAGE_VERSION}

[Product]
type = "LocalbootProduct"
id = "{TESTPRODUCT}"
name = "{{}}"
version = {{}}
"""

CONTROL_TOML = BASE_CONTROL_TOML.format("Test Product", PRODUCT_VERSION)
CONTROL_TOML_CUSTOM = BASE_CONTROL_TOML.format("Test Product Custom Config", NEW_PRODUCT_VERSION)

logger = get_logger("opsi-cli-test")


@pytest.fixture
def test_product_source(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
	params = {
		"control_file_content": CONTROL_FILE,
		"control_toml_content": CONTROL_TOML,
		"custom_dir_name": None,
		"custom_toml_content": CONTROL_TOML_CUSTOM,
	}
	if hasattr(request, "param") and request.param is not None:
		params.update(request.param)

	source_dir = tmp_path / TESTPRODUCT
	opsi_dir = source_dir / "OPSI"

	create_dir_and_write_files(opsi_dir, params["control_file_content"], params["control_toml_content"])

	if params["custom_dir_name"] is not None:
		custom_dir_path = source_dir / f"OPSI.{params['custom_dir_name']}"
		create_dir_and_write_files(custom_dir_path, CONTROL_FILE, params["custom_toml_content"])

	return source_dir


def create_dir_and_write_files(
	dir_path: Path,
	control_file_content: Optional[str] = None,
	control_toml_content: Optional[str] = None,
) -> None:
	dir_path.mkdir(parents=True, exist_ok=True)
	if control_file_content is not None:
		(dir_path / CONTROL_FILE_NAME).write_text(control_file_content)
	if control_toml_content is not None:
		(dir_path / CONTROL_TOML_FILE_NAME).write_text(control_toml_content)


@pytest.mark.parametrize(
	"test_product_source, control_files, no_md5_zsync",
	[
		(
			{
				"control_file_content": None,
				"control_toml_content": None,
			},
			False,
			False,
		),
		(
			{},
			True,
			False,
		),
		(
			{
				"control_file_content": CONTROL_FILE_LEGACY,
			},
			"legacy",
			False,
		),
		(
			{},
			True,
			True,
		),
	],
	indirect=["test_product_source"],
)
def test_make(tmp_path: Path, test_product_source: Path, control_files: bool | str, no_md5_zsync: bool) -> None:
	source_dir = test_product_source

	cli_args = ["package", "make", str(source_dir), str(tmp_path)]
	if no_md5_zsync:
		cli_args.extend(["--no-md5", "--no-zsync"])

	exit_code, _stdout, _stderr = run_cli(cli_args)

	if control_files == "legacy":
		assert "Control file is newer. Please update the control.toml file." in _stderr
	elif control_files:
		package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}.opsi"
		assert exit_code == 0 and package_archive.exists()

		package_archive_md5 = package_archive.with_suffix(".opsi.md5")
		package_archive_zsync = package_archive.with_suffix(".opsi.zsync")

		if no_md5_zsync:
			assert not package_archive_md5.exists()
			assert not package_archive_zsync.exists()
		else:
			assert package_archive_md5.exists()
			assert package_archive_zsync.exists()

	else:
		assert "No control file found." in _stderr


@pytest.mark.parametrize(
	"test_product_source, custom_name, custom_only",
	[
		(
			{
				"custom_dir_name": "custom",
			},
			"custom",
			True,
		),
		(
			{
				"custom_dir_name": "custom",
			},
			"custom",
			False,
		),
		(
			{},
			None,
			False,
		),
	],
	indirect=["test_product_source"],
)
def test_make_with_custom(tmp_path: Path, test_product_source: Path, custom_name: str, custom_only: bool) -> None:
	source_dir = test_product_source

	cli_args = ["package", "make", str(source_dir), str(tmp_path)]
	if custom_name:
		cli_args.extend(["--custom-name", custom_name])
	if custom_only:
		cli_args.extend(["--custom-only"])
	exit_code, _stdout, _stderr = run_cli(cli_args)

	product_version = NEW_PRODUCT_VERSION if custom_name else PRODUCT_VERSION
	package_archive_name = f"{TESTPRODUCT}_{product_version}-{PACKAGE_VERSION}"
	if custom_name:
		package_archive_name += f"~{custom_name}"
	package_archive = tmp_path / f"{package_archive_name}.opsi"
	assert exit_code == 0 and package_archive.exists()

	extract_dir = tmp_path / "extract_dir"
	exit_code, _stdout, _stderr = run_cli(["package", "extract", str(package_archive), str(extract_dir)])
	extracted_dir_name = f"{TESTPRODUCT}_{product_version}-{PACKAGE_VERSION}"
	if custom_name:
		extracted_dir_name += f"~{custom_name}"
	extracted_dir = extract_dir / extracted_dir_name
	assert exit_code == 0 and extracted_dir.exists()

	opsi_custom_exists = (extracted_dir / "OPSI.custom").exists()
	opsi_exists = (extracted_dir / "OPSI").exists()
	assert opsi_custom_exists if custom_name else not opsi_custom_exists
	assert not opsi_exists if custom_only else opsi_exists


@pytest.mark.parametrize(
	"test_product_source",
	[
		{
			"custom_dir_name": "custom",
			"custom_toml_content": CONTROL_TOML,
		}
	],
	indirect=["test_product_source"],
)
def test_make_with_and_without_custom(tmp_path: Path, test_product_source: Path) -> None:
	"""
	Testcase to verify that the custom package does not overwrite the non-custom package, but is created with a custom name format.
	"""
	source_dir = test_product_source
	cli_args = ["package", "make", str(source_dir), str(tmp_path)]
	exit_code, _, _ = run_cli(cli_args)
	package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}.opsi"
	assert exit_code == 0 and package_archive.exists()

	cli_args = ["package", "make", str(source_dir), str(tmp_path), "--custom-name", "custom"]
	exit_code, _, _ = run_cli(cli_args)
	package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}~custom.opsi"
	assert exit_code == 0 and package_archive.exists()


def test_extract(tmp_path: Path, test_product_source: Path) -> None:
	source_dir = test_product_source
	exit_code, _stdout, _stderr = run_cli(["package", "make", str(source_dir), str(tmp_path)])
	package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}.opsi"
	assert exit_code == 0 and package_archive.exists()

	extract_dir = tmp_path / "extract_dir"
	exit_code, _stdout, _stderr = run_cli(["package", "extract", str(package_archive), str(extract_dir)])
	extracted_dir = extract_dir / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}"
	assert exit_code == 0 and extracted_dir.exists()


def test_combine_products() -> None:
	product = LocalbootProduct(
		id="testproduct", name="Test Product", productVersion="1.0", packageVersion="1", description="Test Product Description"
	)

	product_on_depot = ProductOnDepot(
		productId="testproduct", depotId="depot1.test.local", productType="LocalbootProduct", productVersion="1.0", packageVersion="1"
	)

	product_dict = {"testproduct": {"1.0": {"1": product}}}
	product_on_depot_dict = {"depot1.test.local": {"testproduct": product_on_depot}}

	expected = [
		{
			"depot_id": "depot1.test.local",
			"product_id": "testproduct",
			"name": "Test Product",
			"description": "Test Product Description",
			"product_version": "1.0",
			"package_version": "1",
			"product_type": "LocalbootProduct",
		}
	]

	assert combine_products(product_dict, product_on_depot_dict) == expected


@pytest.mark.parametrize("test_product_source", [{"control_file_content": CONTROL_FILE, "control_toml_content": None}], indirect=True)
def test_control_to_toml(test_product_source: Path) -> None:
	source_dir = test_product_source
	exit_code, _stdout, _stderr = run_cli(["package", "control-to-toml", str(source_dir)])
	control_toml = source_dir / "OPSI" / CONTROL_TOML_FILE_NAME
	assert exit_code == 0 and control_toml.exists()


@pytest.mark.opsi_service
def test_package_list() -> None:
	exit_code, _stdout, _stderr = run_cli(["package", "list"])
	assert exit_code == 0

	exit_code, _stdout, _stderr = run_cli(["package", "list", "opsi*"])
	assert exit_code == 0

	exit_code, _stdout, _stderr = run_cli(["package", "list", "--depots", "all", "opsi-client-agent"])
	assert exit_code == 0


@pytest.mark.opsi_service
def test_package_list_filter_by_product_type(admin_service_client: ServiceClient) -> None:
	with (
		tmp_product(admin_service_client, "pytest-product1"),
		tmp_product(admin_service_client, "pytest-product2", product_type=NetbootProduct),
	):
		exit_code, _stdout, _ = run_cli(["package", "list", "--product-type", "netboot"])
		assert exit_code == 0
		assert "pytest-product2" in _stdout
		assert "pytest-product1" not in _stdout

		exit_code, _stdout, _ = run_cli(["package", "list", "--product-type", "localboot"])
		assert exit_code == 0
		assert "pytest-product1" in _stdout
		assert "pytest-product2" not in _stdout


@pytest.mark.opsi_service
def test_package_install_and_uninstall(admin_service_client: ServiceClient) -> None:
	admin_service_client.connect()
	hosts = [
		OpsiDepotserver(id="depot1.opsi.test"),
		OpsiDepotserver(id="depot2.opsi.test"),
		OpsiClient(id="client1.opsi.test"),
		OpsiClient(id="client2.opsi.test"),
		OpsiClient(id="client3.opsi.test"),
	]
	# Cleanup
	admin_service_client.host_deleteObjects(hosts)  # type: ignore[unresolved-attribute]
	admin_service_client.product_delete(id=["testdependency4", "testdependency5", "opsi-client-agent"])  # type: ignore[unresolved-attribute]

	admin_service_client.host_createObjects(hosts)  # type: ignore[unresolved-attribute]
	admin_service_client.configState_create(configId="clientconfig.depot.id", objectId="client1.opsi.test", values=["depot1.opsi.test"])  # type: ignore[unresolved-attribute]
	admin_service_client.configState_create(configId="clientconfig.depot.id", objectId="client2.opsi.test", values=["depot2.opsi.test"])  # type: ignore[unresolved-attribute]
	configserver_id = admin_service_client.host_getIdents(type="OpsiConfigserver")[0]  # type: ignore[unresolved-attribute]

	client_ids_by_depot = {}
	for c2d in admin_service_client.configState_getClientToDepotserver():  # type: ignore[unresolved-attribute]
		if c2d["depotId"] not in client_ids_by_depot:
			client_ids_by_depot[c2d["depotId"]] = []
		client_ids_by_depot[c2d["depotId"]].append(c2d["clientId"])
	assert client_ids_by_depot["depot1.opsi.test"] == ["client1.opsi.test"]
	assert client_ids_by_depot["depot2.opsi.test"] == ["client2.opsi.test"]
	assert client_ids_by_depot[configserver_id] == ["client3.opsi.test"]

	def mock_get_depot_connection(depot: OpsiDepotserver) -> ServiceClient:
		logger.debug("depot: %s", depot.id)
		if depot.id == configserver_id:
			return admin_service_client

		class MockServiceClient(ServiceClient):
			def __init__(self, depot: OpsiDepotserver) -> None:
				super().__init__()
				self.depot = depot

			def connect(self, connect_messagebus: bool = False) -> None:
				pass

			def webdav_content(self, path: str, include_base_path: bool = False) -> list[DAVFileInfo]:
				return []

			def upload(self, source: Path, path: str, *, progress_callback: Callable | None = None) -> None:
				pass

			def jsonrpc(
				self,
				method: str,
				params: tuple[Any, ...] | list[Any] | dict[str, Any] | None = None,
				*,
				connect_timeout: float | None = None,
				read_timeout: float | None = None,
				return_result_only: bool = True,
				create_objects: bool | None = None,
				assert_connected: bool = True,
			) -> Any:
				logger.info("Mock JSON-RPC call: %s %s", method, params)
				if method == "depot_getDiskSpaceUsage":
					return {"available": 1_000_000_000, "usage": 0.5}
				if method == "depot_getMD5Sum":
					if params and "testdependency5_1.2-2.opsi" in params[0]:
						return "16c33c4939db6dc27e219bb381ee9b94"
					if params and "testdependency4_1.0-5.opsi" in params[0]:
						return "458bd972fd0e7d975474469da75cd4f1"
					if params and "opsi-client-agent_4.3.9.2-2.opsi" in params[0]:
						return "b76932c930256e90b32847a2d4a1d65d"
				if method == "depot_installPackage":
					assert params
					product_id, version = params[0].split("/")[-1].split("_", 1)
					product = LocalbootProduct(
						id=product_id,
						productVersion=version.split("-", 1)[0],
						packageVersion=version.split("-", 1)[1],
					)
					product_on_depot = ProductOnDepot(
						productId=product_id,
						productType=product.getType(),
						productVersion=product.productVersion,
						packageVersion=product.packageVersion,
						depotId=self.depot.id,
						locked=True,
					)
					admin_service_client.product_updateObjects([product])  # type: ignore[unresolved-attribute]
					admin_service_client.productOnDepot_createObjects([product_on_depot])  # type: ignore[unresolved-attribute]
				if method == "depot_uninstallPackage":
					assert params
					product_id = params[0]
					admin_service_client.productOnDepot_delete(productId=[product_id], depotId=[self.depot.id])  # type: ignore[unresolved-attribute]

		return MockServiceClient(depot)

	with patch("opsicli.opsiservice.get_depot_connection", mock_get_depot_connection):
		# Test installing with a missing dependency
		exit_code, _, _stderr = run_cli(["package", "install", str(TEST_DATA_PATH / "testdependency4_1.0-5.opsi")])
		assert exit_code != 0
		_stderr = re.sub(r"\s+", " ", re.sub(r"[\n│]", "", _stderr))
		assert (
			"Failed to analyze package 'tests/test_data/plugins/package/testdependency4_1.0-5.opsi': "
			"Dependency 'testdependency5' for package 'testdependency4' is not specified." in _stderr
		)

		# Test with unfulfilled package dependency, this will lock the product 'testdependency4'
		exit_code, _stdout, _stderr = run_cli(
			[
				"package",
				"install",
				str(TEST_DATA_PATH / "testdependency4_1.0-5.opsi"),
				str(TEST_DATA_PATH / "testdependency5_1.2-2.opsi"),
			]
		)
		assert exit_code != 0
		assert "Opsi rpc error:" in _stderr

		if Path("/var/lib/opsi/repository").exists():  # we are probably running on the opsi-server itself (not just on same docker host)
			# Verify files exist after failed install
			for file in [
				"testdependency4_1.0-5.opsi",
				"testdependency4_1.0-5.opsi.md5",
				"testdependency4_1.0-5.opsi.zsync",
				"testdependency5_1.2-2.opsi",
				"testdependency5_1.2-2.opsi.md5",
				"testdependency5_1.2-2.opsi.zsync",
			]:
				assert (Path("/var/lib/opsi/repository") / file).exists()

		# Test with correct dependency version
		exit_code, _, _stderr = run_cli(
			[
				"package",
				"install",
				str(TEST_DATA_PATH / "testdependency4_1.0-5.opsi"),
				str(TEST_DATA_PATH / "testdependency5_2-0.opsi"),
			]
		)
		assert exit_code != 0
		assert "Locked products found" in _stderr

		# Force install with correct dependency version
		exit_code, _stdout, _stderr = run_cli(
			[
				"package",
				"install",
				str(TEST_DATA_PATH / "testdependency4_1.0-5.opsi"),
				str(TEST_DATA_PATH / "testdependency5_2-0.opsi"),
				"--force",
			]
		)
		assert exit_code == 0
		assert (
			"Package 'testdependency4_1.0-5.opsi' already exists in the repository with matching size and checksum. Skipping upload"
			in _stderr.replace("\n", " ").replace("  ", " ")
		)

		if Path("/var/lib/opsi/repository").exists():  # we are probably running on the opsi-server itself (not just on same docker host)
			# Verify correct files exist after successful install
			for file in [
				"testdependency4_1.0-5.opsi",
				"testdependency4_1.0-5.opsi.md5",
				"testdependency4_1.0-5.opsi.zsync",
				"testdependency5_2-0.opsi",
				"testdependency5_2-0.opsi.md5",
				"testdependency5_2-0.opsi.zsync",
			]:
				assert (Path("/var/lib/opsi/repository") / file).exists()

			# Verify incorrect files do not exist
			for file in ["testdependency5_1.2-2.opsi", "testdependency5_1.2-2.opsi.md5", "testdependency5_1.2-2.opsi.zsync"]:
				assert not (Path("/var/lib/opsi/repository") / file).exists()

		pods = sorted(
			admin_service_client.productOnDepot_getObjects(productId=["testdependency4", "testdependency5", "opsi-client-agent"]),  # type: ignore[unresolved-attribute]
			key=lambda p: (p.productId, p.depotId),
		)
		assert len(pods) == 2
		assert pods[0].productId == "testdependency4"
		assert pods[0].depotId == configserver_id
		assert pods[0].productType == "LocalbootProduct"
		assert pods[0].productVersion == "1.0"
		assert pods[0].packageVersion == "5"
		assert pods[1].productId == "testdependency5"
		assert pods[1].depotId == configserver_id
		assert pods[1].productType == "LocalbootProduct"
		assert pods[1].productVersion == "2"
		assert pods[1].packageVersion == "0"

		exit_code, _stdout, _stderr = run_cli(
			[
				"package",
				"install",
				str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"),
				"--depots",
				"depot1.opsi.test",
			]
		)
		assert exit_code == 0
		pods = sorted(
			admin_service_client.productOnDepot_getObjects(productId=["testdependency4", "testdependency5", "opsi-client-agent"]),  # type: ignore[unresolved-attribute]
			key=lambda p: (p.productId, p.depotId),
		)
		assert len(pods) == 3
		assert pods[0].productId == "opsi-client-agent"
		assert pods[0].depotId == "depot1.opsi.test"
		assert pods[1].productId == "testdependency4"
		assert pods[1].depotId == configserver_id
		assert pods[2].productId == "testdependency5"
		assert pods[2].depotId == configserver_id

		exit_code, _stdout, _stderr = run_cli(
			[
				"package",
				"install",
				str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"),
				"--force",
				"--depots",
				"all",
			]
		)
		assert exit_code == 0
		pods = sorted(
			admin_service_client.productOnDepot_getObjects(productId=["testdependency4", "testdependency5", "opsi-client-agent"]),  # type: ignore[unresolved-attribute]
			key=lambda p: (p.productId, p.depotId),
		)
		assert len(pods) == 5
		assert pods[0].productId == "opsi-client-agent"
		assert pods[0].depotId == "depot1.opsi.test"
		assert pods[1].productId == "opsi-client-agent"
		assert pods[1].depotId == "depot2.opsi.test"
		assert pods[2].productId == "opsi-client-agent"
		assert pods[2].depotId == configserver_id
		assert pods[3].productId == "testdependency4"
		assert pods[3].depotId == configserver_id
		assert pods[4].productId == "testdependency5"
		assert pods[4].depotId == configserver_id

		# Test uninstalling packages
		exit_code, _stdout, _stderr = run_cli(["package", "uninstall", "testdependency4", "testdependency5"])
		assert exit_code == 0
		assert "Uninstalling" in _stderr

		if Path("/var/lib/opsi/repository").exists():  # we are probably running on the opsi-server itself (not just on same docker host)
			# Verify files do not exist after uninstall
			for file in [
				"testdependency4_1.0-5.opsi",
				"testdependency4_1.0-5.opsi.md5",
				"testdependency4_1.0-5.opsi.zsync",
				"testdependency5_2-0.opsi",
				"testdependency5_2-0.opsi.md5",
				"testdependency5_2-0.opsi.zsync",
			]:
				assert not (Path("/var/lib/opsi/repository") / file).exists()

		assert exit_code == 0
		pods = sorted(
			admin_service_client.productOnDepot_getObjects(productId=["testdependency4", "testdependency5", "opsi-client-agent"]),  # type: ignore[unresolved-attribute]
			key=lambda p: (p.productId, p.depotId),
		)
		assert len(pods) == 3
		assert pods[0].productId == "opsi-client-agent"
		assert pods[0].depotId == "depot1.opsi.test"
		assert pods[1].productId == "opsi-client-agent"
		assert pods[1].depotId == "depot2.opsi.test"
		assert pods[2].productId == "opsi-client-agent"
		assert pods[2].depotId == configserver_id

		# Add some states
		pocs = [
			ProductOnClient(
				productId="opsi-client-agent",
				productType="LocalbootProduct",
				clientId=client_id,
				installationStatus="installed",
			)
			for client_id in ["client1.opsi.test", "client2.opsi.test", "client3.opsi.test"]
		]
		pps = [
			ProductPropertyState(productId="opsi-client-agent", objectId=client_id, propertyId="allow_reboot", values=[True])
			for client_id in ["client1.opsi.test", "client2.opsi.test", "client3.opsi.test"]
		]
		admin_service_client.productOnClient_createObjects(pocs)  # type: ignore[unresolved-attribute]
		admin_service_client.productPropertyState_createObjects(pps)  # type: ignore[unresolved-attribute]

		###########################################
		# Uninstall opsi-client-agent
		###########################################
		exit_code, _stdout, _stderr = run_cli(["package", "uninstall", "opsi-client-agent", "--depots", configserver_id])
		assert exit_code == 0

		# Verify that product is not removed
		product = admin_service_client.product_getObjects(id=["opsi-client-agent"])[0]  # type: ignore[unresolved-attribute]
		assert product.id == "opsi-client-agent"

		# Verify that productOnDepot is removed only from configserver depot
		pods = sorted(
			admin_service_client.productOnDepot_getObjects(productId=["opsi-client-agent"]),  # type: ignore[unresolved-attribute]
			key=lambda p: (p.productId, p.depotId),
		)
		assert len(pods) == 2
		assert pods[0].productId == "opsi-client-agent"
		assert pods[0].depotId == "depot1.opsi.test"
		assert pods[1].productId == "opsi-client-agent"
		assert pods[1].depotId == "depot2.opsi.test"

		# Verify that productOnClient and productPropertyState are not removed
		pocs = sorted(
			admin_service_client.productOnClient_getObjects(productId=["opsi-client-agent"]),  # type: ignore[unresolved-attribute]
			key=lambda p: (p.productId, p.clientId),
		)
		assert len(pocs) == 3
		assert pocs[0].clientId == "client1.opsi.test"
		assert pocs[1].clientId == "client2.opsi.test"
		assert pocs[2].clientId == "client3.opsi.test"

		ppss = sorted(
			admin_service_client.productPropertyState_getObjects(  # type: ignore[unresolved-attribute]
				productId=["opsi-client-agent"], objectId=["client1.opsi.test", "client2.opsi.test", "client3.opsi.test"]
			),
			key=lambda p: (p.productId, p.objectId),
		)
		assert len(ppss) == 3
		assert ppss[0].objectId == "client1.opsi.test"
		assert ppss[0].propertyId == "allow_reboot"
		assert ppss[0].values == [True]
		assert ppss[1].objectId == "client2.opsi.test"
		assert ppss[1].propertyId == "allow_reboot"
		assert ppss[1].values == [True]
		assert ppss[2].objectId == "client3.opsi.test"
		assert ppss[2].propertyId == "allow_reboot"
		assert ppss[2].values == [True]


@pytest.mark.opsi_service
def test_custom_package_installation() -> None:
	# Test case where the package has "~custom" name and has local md5 and zsync files, which are not updated.
	exit_code, _, _ = run_cli(["package", "install", str(TEST_DATA_PATH / "test2_1.0-6~custom1.opsi")])
	assert exit_code == 0
	if Path("/var/lib/opsi/repository").exists():  # we are probably running on the opsi-server itself (not just on same docker host)
		for file in ["test2_1.0-6.opsi", "test2_1.0-6.opsi.md5", "test2_1.0-6.opsi.zsync"]:
			assert (Path("/var/lib/opsi/repository") / file).exists()

	exit_code, _, _ = run_cli(["package", "uninstall", "test2"])
	assert exit_code == 0


@pytest.mark.opsi_service
def test_package_installation_new_id() -> None:
	exit_code, _, _ = run_cli(["package", "install", str(TEST_DATA_PATH / "testdependency5_2-0.opsi"), "--new-product-id", "newid"])
	assert exit_code == 0
	if Path("/var/lib/opsi/repository").exists():  # we are probably running on the opsi-server itself (not just on same docker host)
		for file in ["newid_1.0-5.opsi", "newid_1.0-5.opsi.md5", "newid_1.0-5.opsi.zsync"]:
			assert (Path("/var/lib/opsi/repository") / file).exists()

	exit_code, _, _ = run_cli(["package", "uninstall", "newid"])  # This also checks if newid is installed
	assert exit_code == 0


@pytest.mark.opsi_service
def test_package_installation_product_lock() -> None:
	broken_package = Path("tests/test_data/plugins/package/gimp2_broken_1.0-1.opsi")
	working_package = Path("tests/test_data/plugins/package/gimp2_1.0-1.opsi")

	# install broken package to lock the product
	exitcode, _, _ = run_cli(["package", "install", str(broken_package)])
	assert exitcode != 0

	# try to install working package, should fail due to locked product
	exitcode, _, _ = run_cli(["package", "install", str(working_package)])
	assert exitcode != 0

	# install product under new name
	exitcode, _, _ = run_cli(["package", "install", str(working_package), "--new-product-id", "gimp2_new"])
	assert exitcode == 0

	exit_code, _, _ = run_cli(["package", "uninstall", "gimp2_new"])
	assert exit_code == 0

	# forcing installation of working package
	exitcode, _, _ = run_cli(["package", "install", str(working_package), "--force"])
	assert exitcode == 0

	exit_code, _, _ = run_cli(["package", "uninstall", "gimp2"])
	assert exit_code == 0


@pytest.mark.opsi_service
def test_package_installation_from_urls() -> None:
	with http_test_server(serve_directory=TEST_DATA_PATH) as server:
		base_url = f"http://localhost:{server.port}"

		for file in ["test2_1.0-6~custom1.opsi", "7zip_all_all_19.00-2.tar.gz"]:
			file_url = f"{base_url}/{file}"
			exit_code, _, _ = run_cli(["package", "install", file_url])
			assert exit_code == 0

		exit_code, _, _ = run_cli(["package", "uninstall", "test2", "7zip"])
		assert exit_code == 0


@pytest.mark.opsi_service
def test_package_installation_with_action_request_setup() -> None:
	exit_code, _, _ = run_cli(["package", "install", str(TEST_DATA_PATH / "testdependency5_2-0.opsi"), "--setup-where-installed"])
	assert exit_code == 0

	exit_code, _, _ = run_cli(["package", "uninstall", "testdependency5"])
	assert exit_code == 0


@pytest.mark.opsi_service
def test_package_installation_with_properties() -> None:
	package = OpsiPackage()
	package.from_package_archive(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi")
	package_defaults = {p.propertyId: p.defaultValues for p in package.product_properties}

	with get_admin_service_client() as service_client:
		depot_id = service_client.jsonrpc("host_getObjects", [[], {"type": "OpsiConfigserver"}])[0].id

		# Test default properties
		exit_code, _, _ = run_cli(
			["package", "install", str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"), "--properties", "package"]
		)
		assert exit_code == 0

		depot_defaults = {
			p.propertyId: p.values
			for p in service_client.jsonrpc(
				"productPropertyState_getObjects", [[], {"productId": "opsi-client-agent", "objectId": depot_id}]
			)
		}
		assert depot_defaults == package_defaults

		# Test interactive properties
		interactive_defaults: dict[str, list[str | bool]] = {
			"allow_reboot": [False],
			"loginblockerstart": ["off"],
			"setup_after_install": ["p1", "p2"],
			"systray_check_interval": ["300"],
			"systray_install": [False],
			"systray_request_notify_format": ["productname : request"],
		}
		stdin = []
		for property_id, values in interactive_defaults.items():
			stdin.extend([str(v) for v in values])
			if len(values) > 1:
				stdin.append("done")
		exit_code, _stdout, _stderr = run_cli(
			["--interactive", "package", "install", str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"), "--properties", "ask"],
			stdin=stdin,
		)
		assert exit_code == 0

		depot_defaults = {
			p.propertyId: p.values
			for p in service_client.jsonrpc(
				"productPropertyState_getObjects", [[], {"productId": "opsi-client-agent", "objectId": depot_id}]
			)
		}
		assert depot_defaults == interactive_defaults

		# Test keep properties
		exit_code, _stdout, _stderr = run_cli(
			["package", "install", str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"), "--properties", "keep"]
		)
		assert exit_code == 0
		depot_defaults = {
			p.propertyId: p.values
			for p in service_client.jsonrpc(
				"productPropertyState_getObjects", [[], {"productId": "opsi-client-agent", "objectId": depot_id}]
			)
		}
		assert depot_defaults == interactive_defaults

		# Test package properties
		exit_code, _stdout, _stderr = run_cli(
			["package", "install", str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"), "--properties", "package"]
		)
		assert exit_code == 0
		depot_defaults = {
			p.propertyId: p.values
			for p in service_client.jsonrpc(
				"productPropertyState_getObjects", [[], {"productId": "opsi-client-agent", "objectId": depot_id}]
			)
		}
		assert depot_defaults == package_defaults


@pytest.mark.opsi_service
def test_package_fetch(tmp_path: Path) -> None:
	exit_code, _, _ = run_cli(["package", "install", str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi")])
	assert exit_code == 0

	# Test interactive properties
	interactive_defaults: dict[str, list[str | bool]] = {
		"allow_reboot": [False],
		"loginblockerstart": ["off"],
		"setup_after_install": ["p1", "p2"],
		"systray_check_interval": ["300"],
		"systray_install": [False],
		"systray_request_notify_format": ["productname : request"],
	}
	stdin = []
	for property_id, values in interactive_defaults.items():
		stdin.extend([str(v) for v in values])
		if len(values) > 1:
			stdin.append("done")

	exit_code, _, _ = run_cli(
		[
			"--interactive",
			"package",
			"fetch",
			"opsi-client-agent",
			"--overwrite",
			"--destination-dir",
			str(tmp_path),
			"--properties",
			"ask",
		],
		stdin=stdin,
	)
	assert exit_code == 0
	assert Path(tmp_path / "opsi-client-agent_4.3.9.2-2.opsi").exists()

	exit_code, _, _ = run_cli(["package", "uninstall", "opsi-client-agent"])
	assert exit_code == 0


def test_package_info() -> None:
	exit_code, stdout, _stderr = run_cli(
		[
			"package",
			"info",
			str(TEST_DATA_PATH / "testdependency5_1.2-2.opsi"),
			str(TEST_DATA_PATH / "opsi-client-agent_4.3.9.2-2.opsi"),
		]
	)
	assert exit_code == 0
	assert not _stderr

	assert "package_filename: testdependency5_1.2-2.opsi" in stdout
	assert "product_id: testdependency5" in stdout
	assert "product_version: 1.2" in stdout

	assert "package_filename: opsi-client-agent_4.3.9.2-2.opsi" in stdout
	assert "product_id: opsi-client-agent" in stdout
	assert "product_version: 4.3.9.2" in stdout


@pytest.mark.parametrize("dry_run", (True, False))
def test_meta_edit_add_product_dependency(tmp_path: Path, test_product_source: Path, dry_run: bool) -> None:
	source_dir = test_product_source
	exit_code, _stdout, stderr = run_cli(
		(["--dry-run"] if dry_run else [])
		+ [
			"package",
			"meta-edit",
			"add-product-dependency",
			str(source_dir),
			"--product-action",
			"setup",
			"--required-product-id",
			"dep1",
			"--required-product-version",
			"1.2",
			"--required-package-version",
			"3",
			"--required-action",
			"setup",
			"--requirement-type",
			"before",
		]
	)
	stderr = re.sub(r"\s\s+", " ", stderr.replace("\n", " ").replace("│", " "))
	assert exit_code == 0
	if dry_run:
		assert "Product dependency would be added to the control file." in stderr
	else:
		assert "Product dependency has been successfully added to the control file." in stderr

	package = OpsiPackage()
	package.parse_control_file(source_dir / "OPSI" / "control.toml")
	dependencies = [dep for dep in package.product_dependencies if dep.requiredProductId == "dep1"]

	if dry_run:
		assert len(dependencies) == 0
	else:
		assert len(dependencies) == 1
		assert dependencies[0].productId == package.product.id
		assert dependencies[0].productAction == "setup"
		assert dependencies[0].requiredProductId == "dep1"
		assert dependencies[0].requiredProductVersion == "1.2"
		assert dependencies[0].requiredPackageVersion == "3"
		assert dependencies[0].requiredAction == "setup"
		assert dependencies[0].requirementType == "before"


@pytest.mark.parametrize(
	"arguments, expected_error",
	[
		(
			["--required-product-id", "dep1", "--product-action", "invalid"],
			"Invalid value for '--product-action': 'invalid' is not one of 'setup', 'uninstall', 'update', 'always', 'once', 'custom'.",
		),
		(
			["--required-product-id", "dep1", "--product-action", "setup", "--required-action", "invalid"],
			"Invalid value for '--required-action': 'invalid' is not one of 'setup', 'uninstall', 'update', 'always', 'once', 'custom'.",
		),
		(
			[
				"--required-product-id",
				"dep1",
				"--product-action",
				"setup",
				"--required-action",
				"uninstall",
				"--requirement-type",
				"invalid",
			],
			"Invalid value for '--requirement-type': 'invalid' is not one of 'before', 'after'.",
		),
		(
			["--required-product-id", "dep1", "--product-action", "setup"],
			"You must specify either a required action or a required installation status.",
		),
	],
)
def test_meta_edit_add_product_dependency_errors(
	tmp_path: Path, test_product_source: Path, arguments: list[str], expected_error: str
) -> None:
	source_dir = test_product_source
	exit_code, _stdout, stderr = run_cli(
		[
			"package",
			"meta-edit",
			"add-product-dependency",
			str(source_dir),
		]
		+ arguments
	)
	assert exit_code == 2
	stderr = re.sub(r"\s\s+", " ", stderr.replace("\n", " ").replace("│", " "))
	assert expected_error in stderr


@pytest.mark.parametrize("dry_run", (True, False))
@pytest.mark.parametrize("ignore_missing", (True, False))
def test_meta_edit_remove_product_dependency(tmp_path: Path, test_product_source: Path, dry_run: bool, ignore_missing: bool) -> None:
	source_dir = test_product_source
	exit_code, _stdout, _stderr = run_cli(
		[
			"package",
			"meta-edit",
			"add-product-dependency",
			str(source_dir),
			"--product-action",
			"setup",
			"--required-product-id",
			"dep1",
			"--required-product-version",
			"1.2",
			"--required-package-version",
			"3",
			"--required-installation-status",
			"installed",
		]
	)
	assert exit_code == 0
	for call_num in (1, 2):
		exit_code, _stdout, stderr = run_cli(
			(["--dry-run"] if dry_run else [])
			+ [
				"package",
				"meta-edit",
				"remove-product-dependency",
				str(source_dir),
				"--product-action",
				"setup",
				"--required-product-id",
				"dep1",
			]
			+ (["--ignore-missing"] if ignore_missing else [])
		)
		stderr = re.sub(r"\s\s+", " ", stderr.replace("\n", " ").replace("│", " "))

		if call_num == 2 and not ignore_missing and not dry_run:
			assert exit_code == 1
			assert "No product dependency found for action 'setup' and required product ID 'dep1'." in stderr
			continue

		assert exit_code == 0

		package = OpsiPackage()
		package.parse_control_file(source_dir / "OPSI" / "control.toml")
		dependencies = [dep for dep in package.product_dependencies if dep.requiredProductId == "dep1"]

		if dry_run:
			assert "The product dependency would be removed from the control file." in stderr
			assert len(dependencies) == 1
			continue

		if call_num == 1:
			assert "Product dependency has been successfully removed from the control file." in stderr
		else:
			assert "No product dependency found for action 'setup' and required product ID 'dep1'." in stderr
		assert len(dependencies) == 0
