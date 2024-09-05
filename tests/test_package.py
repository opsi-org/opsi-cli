"""
test_package.py is a test file for the package plugin.
"""

from pathlib import Path
from typing import Optional, Union

import pytest
from opsicommon.objects import LocalbootProduct, ProductOnDepot

from plugins.package.python import combine_products

from .utils import container_connection, run_cli

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


@pytest.fixture
def setup_test_product(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
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
	"setup_test_product, control_files, no_md5_zsync",
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
	indirect=["setup_test_product"],
)
def test_make(tmp_path: Path, setup_test_product: Path, control_files: Union[bool, str], no_md5_zsync: bool) -> None:
	source_dir = setup_test_product

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
	"setup_test_product, custom_name, custom_only",
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
	indirect=["setup_test_product"],
)
def test_make_with_custom(tmp_path: Path, setup_test_product: Path, custom_name: str, custom_only: bool) -> None:
	source_dir = setup_test_product

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
	"setup_test_product",
	[
		{
			"custom_dir_name": "custom",
			"custom_toml_content": CONTROL_TOML,
		}
	],
	indirect=["setup_test_product"],
)
def test_make_with_and_without_custom(tmp_path: Path, setup_test_product: Path) -> None:
	"""
	Testcase to verify that the custom package does not overwrite the non-custom package, but is created with a custom name format.
	"""
	source_dir = setup_test_product
	cli_args = ["package", "make", str(source_dir), str(tmp_path)]
	exit_code, _, _ = run_cli(cli_args)
	package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}.opsi"
	assert exit_code == 0 and package_archive.exists()

	cli_args = ["package", "make", str(source_dir), str(tmp_path), "--custom-name", "custom"]
	exit_code, _, _ = run_cli(cli_args)
	package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}~custom.opsi"
	assert exit_code == 0 and package_archive.exists()


def test_extract(tmp_path: Path, setup_test_product: Path) -> None:
	source_dir = setup_test_product
	exit_code, _stdout, _stderr = run_cli(["package", "make", str(source_dir), str(tmp_path)])
	package_archive = tmp_path / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}.opsi"
	assert exit_code == 0 and package_archive.exists()

	extract_dir = tmp_path / "extract_dir"
	exit_code, _stdout, _stderr = run_cli(["package", "extract", str(package_archive), str(extract_dir)])
	extracted_dir = extract_dir / f"{TESTPRODUCT}_{PRODUCT_VERSION}-{PACKAGE_VERSION}"
	assert exit_code == 0 and extracted_dir.exists()


@pytest.mark.parametrize("setup_test_product", [{"control_file_content": CONTROL_FILE, "control_toml_content": None}], indirect=True)
def test_control_to_toml(setup_test_product: Path) -> None:
	source_dir = setup_test_product
	exit_code, _stdout, _stderr = run_cli(["package", "control-to-toml", str(source_dir)])
	control_toml = source_dir / "OPSI" / CONTROL_TOML_FILE_NAME
	assert exit_code == 0 and control_toml.exists()


@pytest.mark.requires_testcontainer
def test_package_list() -> None:
	with container_connection():
		exit_code, _stdout, _stderr = run_cli(["package", "list"])
		assert exit_code == 0

		exit_code, _stdout, _stderr = run_cli(["package", "list", "opsi*"])
		assert exit_code == 0

		exit_code, _stdout, _stderr = run_cli(["package", "list", "--depots", "all", "opsi-client-agent"])
		assert exit_code == 0


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
		}
	]

	assert combine_products(product_dict, product_on_depot_dict) == expected


@pytest.mark.requires_testcontainer
def test_package_install_and_uninstall() -> None:
	with container_connection():
		# Test installing with a missing dependency
		exit_code, _, _stderr = run_cli(["package", "install", str(TEST_DATA_PATH / "testdependency4_1.0-5.opsi")])
		assert exit_code != 0
		assert "Dependency 'testdependency5' for package 'testdependency4' is not specified." in _stderr

		# Test with unfulfilled package dependency, this will lock the product 'testdependency4'
		exit_code, _, _stderr = run_cli(
			[
				"package",
				"install",
				str(TEST_DATA_PATH / "testdependency4_1.0-5.opsi"),
				str(TEST_DATA_PATH / "testdependency5_1.2-2.opsi"),
			]
		)
		assert exit_code != 0
		assert "Opsi rpc error:" in _stderr

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
		assert "Locked products found:" in _stderr

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
			in _stdout.replace("\n", " ").replace("  ", " ")
		)

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

		# Test uninstalling packages
		exit_code, _stdout, _stderr = run_cli(
			[
				"package",
				"uninstall",
				"testdependency4",
				"testdependency5",
			]
		)
		assert exit_code == 0
		assert "Uninstalling" in _stdout

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


@pytest.mark.requires_testcontainer
def test_custom_package_installation() -> None:
	with container_connection():
		# Test case where the package has "~custom" name and has local md5 and zsync files, which are not updated.
		exit_code, _, _ = run_cli(["package", "install", str(TEST_DATA_PATH / "test2_1.0-6~custom1.opsi")])
		assert exit_code == 0
		for file in ["test2_1.0-6.opsi", "test2_1.0-6.opsi.md5", "test2_1.0-6.opsi.zsync"]:
			assert (Path("/var/lib/opsi/repository") / file).exists()

		exit_code, _, _ = run_cli(["package", "uninstall", "test2"])
		assert exit_code == 0
