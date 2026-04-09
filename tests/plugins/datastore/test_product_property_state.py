# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only


import time

import pytest
from opsicommon.client.opsiservice import ServiceClient

from tests.utils import run_cli, stdout_into_list, tmp_client, tmp_product

CLIENT_ID_1 = "pytest-client1.test.tld"
CLIENT_ID_2 = "pytest-client2.test.tld"

PRODUCT_ID_1 = "pytest-product1"
PRODUCT_ID_2 = "pytest-product2"
PROPERTY_ID_1 = "property1"
PROPERTY_ID_2 = "property2"


@pytest.mark.opsi_service
def test_product_property_list(admin_service_client: ServiceClient) -> None:
	start = time.perf_counter()
	with (
		tmp_client(admin_service_client, CLIENT_ID_1),
		tmp_client(admin_service_client, CLIENT_ID_2),
		tmp_product(admin_service_client, PRODUCT_ID_1),
		tmp_product(admin_service_client, PRODUCT_ID_2),
	):
		client_to_depot_objects = admin_service_client.configState_getClientToDepotserver()  # type:ignore[attr-defined]
		DEPOT_ID = client_to_depot_objects[0]["depotId"]

		# add PRODUCT-PROPERTIES
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_1,
			productVersion="1",
			packageVersion="1",
			propertyId=PROPERTY_ID_1,
		)
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_2, productVersion="1", packageVersion="1", propertyId=PROPERTY_ID_2
		)
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_1,
			productVersion="1",
			packageVersion="1",
			propertyId=PROPERTY_ID_2,
		)
		admin_service_client.productProperty_create(  # type:ignore[attr-defined]
			productId=PRODUCT_ID_2, productVersion="1", packageVersion="1", propertyId=PROPERTY_ID_1
		)

		# add PRODUCT-PROPERTY-STATES for client 1 & 2
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_1, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]

		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_1, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_1)  # type:ignore[attr-defined]
		admin_service_client.productPropertyState_create(productId=PRODUCT_ID_2, propertyId=PROPERTY_ID_2, objectId=CLIENT_ID_2)  # type:ignore[attr-defined]

		# One productId, one propertyId, no object-id
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--where",
				"objectId=all",
				"--where",
				f"productId={PRODUCT_ID_1}",
				"--where",
				f"propertyId={PROPERTY_ID_1}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == PRODUCT_ID_1
		assert stdout_into_list(_stdout)[1][2] == PROPERTY_ID_1
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert stdout_into_list(_stdout)[2][1] == PRODUCT_ID_1
		assert stdout_into_list(_stdout)[2][2] == PROPERTY_ID_1
		assert len(stdout_into_list(_stdout)) - 1 == 2

		# One productId, one propertyId, object-id=py*
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--where",
				"objectId=py*",
				"--where",
				f"productId={PRODUCT_ID_2}",
				"--where",
				f"propertyId={PROPERTY_ID_2}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[1][2] == PROPERTY_ID_2
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert stdout_into_list(_stdout)[2][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[2][2] == PROPERTY_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 2

		# One productId, one propertyId, object-id=comma separated
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--where",
				f"objectId={CLIENT_ID_1},{CLIENT_ID_2}",
				"--where",
				f"productId={PRODUCT_ID_2}",
				"--where",
				f"propertyId={PROPERTY_ID_2}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][0] == CLIENT_ID_1
		assert stdout_into_list(_stdout)[1][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[1][2] == PROPERTY_ID_2
		assert stdout_into_list(_stdout)[2][0] == CLIENT_ID_2
		assert stdout_into_list(_stdout)[2][1] == PRODUCT_ID_2
		assert stdout_into_list(_stdout)[2][2] == PROPERTY_ID_2
		assert len(stdout_into_list(_stdout)) - 1 == 2

		# product-id=pytest*, property-id=proper*, object-id=py*
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--where",
				"objectId=py*",
				"--where",
				"productId=pytest*",
				"--where",
				"propertyId=proper*",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[2][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[3][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[4][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[5][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[6][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[7][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[8][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_2]
		assert len(stdout_into_list(_stdout)) - 1 == 8

		# product-id=comma-separated, property-id=comma-separated, object-id=comma-separated
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--where",
				f"objectId={CLIENT_ID_1},{CLIENT_ID_2}",
				"--where",
				f"productId={PRODUCT_ID_1},{PRODUCT_ID_2}",
				"--where",
				f"propertyId={PROPERTY_ID_1},{PROPERTY_ID_2}",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[2][:3] == [CLIENT_ID_1, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[3][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[4][:3] == [CLIENT_ID_1, PRODUCT_ID_2, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[5][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[6][:3] == [CLIENT_ID_2, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[7][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[8][:3] == [CLIENT_ID_2, PRODUCT_ID_2, PROPERTY_ID_2]
		assert len(stdout_into_list(_stdout)) - 1 == 8
		"""
		# object-id is a depot-id
		exit_code, _stdout, _stderr = run_cli(
			[
				"--output-format",
				"csv",
				"--sort-by",
				"objectId",
				"datastore",
				"product-property-state",
				"list",
				"--object-ids",
				f"{DEPOT_ID}",
				"--product-ids",
				"pytest*",
				"--property-ids",
				"all",
			]
		)
		assert exit_code == 0
		assert stdout_into_list(_stdout)[1][:3] == [DEPOT_ID, PRODUCT_ID_1, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[2][:3] == [DEPOT_ID, PRODUCT_ID_1, PROPERTY_ID_2]
		assert stdout_into_list(_stdout)[3][:3] == [DEPOT_ID, PRODUCT_ID_2, PROPERTY_ID_1]
		assert stdout_into_list(_stdout)[4][:3] == [DEPOT_ID, PRODUCT_ID_2, PROPERTY_ID_2]
		assert len(stdout_into_list(_stdout)) - 1 == 4
		"""
	diff = time.perf_counter() - start
	print(diff)
