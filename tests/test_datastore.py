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


# get products from depot and setting locked to 'False' manually
# update depot with unlocked products
def unlock_products(admin_service_client: ServiceClient, product_id: str | list[str] | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # type:ignore[attr-defined]

	# list of products
	if type(product_id) is list[str]:
		run_cli(["datastore", "product", "unlock"] + product_id)
	# one product
	elif len(products) == 1:
		id = products[0].productId
		run_cli(["datastore", "product", "unlock", id])
	# no products
	else:
		for product in products:
			id = product.productId
			run_cli(["datastore", "product", "unlock", id])


# verify the given locked status (e.g. is product.locked = True or False?)
def verify_lock_status(admin_service_client: ServiceClient, is_locked: bool, product_id: str | None = None) -> None:
	products = admin_service_client.productOnDepot_getObjects(productId=product_id or [])  # type:ignore[attr-defined]
	for prod in products:
		assert prod.locked is is_locked


# extract opsi package -> brake it -> make a new opsi package -> failed installation
def install_broken_package() -> None:
	package_name = "gimp2_broken_1.0-1.opsi"
	broken_package = Path(f"tests/test_data/plugins/package/{package_name}")
	run_cli(["package", "install", str(broken_package)])


@pytest.mark.opsi_service
def test_product_unlock_manual(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		# str | lock one product -> verify -> unlock (CLI) -> verify
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		unlock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=False)


@pytest.mark.opsi_service
def test_product_unlock_multiple(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		# list[str] | lock list of products -> verify -> unlock (CLI) -> verify
		lock_products(admin_service_client)
		verify_lock_status(admin_service_client, is_locked=True)
		unlock_products(admin_service_client, ["gimp2", "test2", "pytest-product1", "pytest-product2", "opsi-client-agent"])
		verify_lock_status(admin_service_client, is_locked=False)


@pytest.mark.opsi_service
def test_product_unlock_installation(admin_service_client: ServiceClient) -> None:
	with tmp_product(admin_service_client, PRODUCT_ID_1), tmp_product(admin_service_client, PRODUCT_ID_2):
		# lock product (failed installation) -> verify -> unlock (CLI) -> verify
		install_broken_package()
		verify_lock_status(admin_service_client, is_locked=True, product_id="gimp2")
		unlock_products(admin_service_client, product_id="gimp2")
		verify_lock_status(admin_service_client, is_locked=False)
