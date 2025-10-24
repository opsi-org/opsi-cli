from pathlib import Path

import pytest
from opsicommon.client.opsiservice import ServiceClient

from .utils import run_cli, tmp_product

PRODUCT_ID_1 = "pytest-product1"
PRODUCT_ID_2 = "pytest-product2"


# get products from depot and setting locked to 'True' manually
# update depot with locked products
def lock_products(admin_service_client: ServiceClient, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # type:ignore[attr-defined]
	for product in products:
		product.locked = True
	admin_service_client.productOnDepot_updateObjects(products)  # type:ignore[attr-defined]


# unlock products with given product-id and depot-id
def unlock_products(product_id: list[str] = [], depot_id: list[str] = []) -> tuple[int, str, str]:
	if depot_id:
		return run_cli(["datastore", "product", "unlock"] + product_id + ["--depot-id"] + depot_id)
	else:
		return run_cli(["datastore", "product", "unlock"] + product_id)


# verify the given locked status (e.g. is product.locked = True or False?)
def verify_lock_status(admin_service_client: ServiceClient, is_locked: bool, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # type:ignore[attr-defined]
	for prod in products:
		assert prod.locked is is_locked


# install broken package -> failed installation
def install_broken_package() -> None:
	package_name = "gimp2_broken_1.0-1.opsi"
	broken_package = Path(f"tests/test_data/plugins/package/{package_name}")
	run_cli(["package", "install", str(broken_package)])


# TESTS
# ------------------------------------------------------------------
# str -> lock one product -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_manual(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		unlock_products()
		verify_lock_status(admin_service_client, is_locked=False)


# list[str] -> lock list of products -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_multiple(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		unlock_products(["gimp2", "test2", "pytest-product1", "pytest-product2", "opsi-client-agent"])
		verify_lock_status(admin_service_client, is_locked=False)


# lock product (failed installation) -> verify -> unlock (CLI) -> verify
@pytest.mark.opsi_service
def test_product_unlock_installation(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		install_broken_package()
		verify_lock_status(admin_service_client, is_locked=True, product_id="gimp2")
		unlock_products(product_id=["gimp2"])
		verify_lock_status(admin_service_client, is_locked=False)


# one producst -> verify -> try unlock (wrong/mutliple depot-ids) -> verify error message
@pytest.mark.opsi_service
def test_wrong_depot_id(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		exitcode, _stdout, stderr = unlock_products(depot_id=["hallo,test"])
		print(stderr)
		assert exitcode != 0
		assert "No such depot(s)" in stderr
