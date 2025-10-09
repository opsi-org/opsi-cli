import pytest
from opsicommon.client.opsiservice import ServiceClient

from .utils import run_cli, tmp_client

CLIENT1 = "pytest-client1.test.tld"


@pytest.mark.opsi_service
def test_config_state_list(admin_service_client: ServiceClient) -> None:
	# test if tmp_client is shown in output table
	with tmp_client(admin_service_client, CLIENT1):
		exit_code, _stdout, _stderr = run_cli(["datastore", "config-state", "list", "--object-id", f"{CLIENT1}"])
		assert exit_code == 0
		print(_stdout)
