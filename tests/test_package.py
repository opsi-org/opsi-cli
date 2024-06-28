"""
test_package.py is a test file for the package plugin.
"""

from pathlib import Path
from typing import Optional, Union

import pytest
from opsicommon.objects import LocalbootProduct, ProductOnDepot

from plugins.package.python import combine_products

from .utils import container_connection, run_cli

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
	package_archive = tmp_path / f"{TESTPRODUCT}_{product_version}-{PACKAGE_VERSION}.opsi"
	assert exit_code == 0 and package_archive.exists()

	extract_dir = tmp_path / "extract_dir"
	exit_code, _stdout, _stderr = run_cli(["package", "extract", str(package_archive), str(extract_dir)])
	extracted_dir = Path(extract_dir) / f"{TESTPRODUCT}_{product_version}-{PACKAGE_VERSION}"
	assert exit_code == 0 and extracted_dir.exists()

	opsi_custom_exists = (extracted_dir / "OPSI.custom").exists()
	opsi_exists = (extracted_dir / "OPSI").exists()
	assert opsi_custom_exists if custom_name else not opsi_custom_exists
	assert not opsi_exists if custom_only else opsi_exists


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
