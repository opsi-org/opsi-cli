from pathlib import Path

import pytest
from opsicommon.client.opsiservice import ServiceClient

from .utils import run_cli, tmp_product

PRODUCT_ID_1 = "pytest-product1"
PRODUCT_ID_2 = "pytest-product2"


@pytest.mark.opsi_service
def test_product_unlock(admin_service_client: ServiceClient, tmp_path: Path) -> None:
	with (
		tmp_product(admin_service_client, PRODUCT_ID_1),
		tmp_product(admin_service_client, PRODUCT_ID_2),
	):
		# get products from depot
		# setting locked to 'True' manually
		products = admin_service_client.productOnDepot_getObjects()  # ignore [attr-defined]
		for product in products:
			product.locked = True

		# update depot with locked products
		admin_service_client.productOnDepot_updateObjects(products)  # ignore [attr-defined]

		# get locked products from depot (locked = True)
		locked_products = admin_service_client.productOnDepot_getObjects()  # ignore [attr-defined]

		# try unlocking them with 'opsi-cli datastore product unlock'
		for product in locked_products:
			id = product.productId
			run_cli(["datastore", "product", "unlock", id])

		# get unlocked products from depot (locked = False)
		unlocked_products = admin_service_client.productOnDepot_getObjects()  # ignore [attr-defined]
		for product in unlocked_products:
			assert product.locked is False
