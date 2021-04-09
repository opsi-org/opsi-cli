import os
import requests
from requests.auth import HTTPBasicAuth


def diagnose_problems(server_interface, user, password):
	result = diagnose_general() + "\n"
	if os.path.exists("/etc/opsi/opsiconfd.conf"):
		result += diagnose_server(server_interface, user, password) + "\n"
	if os.path.exists("/etc/opsi-client-agent/opsiclientd.conf") or os.path.exists(r"C:\opsi.org"):
		result += diagnose_client() + "\n"
	return result


def diagnose_general():
	result = "general\n"
	check_url = "https://www.opsi.org"
	response = requests.get(check_url)
	if response.status_code < 200 or response.status_code > 299:
		result += f"No Internet connection (could not reach {check_url})"
	return result


def diagnose_server(server_interface, user, password):
	result = "server\n"
	config_url = f"{server_interface}/admin/config"
	print(user, password)
	response = requests.get(config_url, verify=False, auth=HTTPBasicAuth(user, password))
	if response.status_code < 200 or response.status_code > 299:
		result += f"Config Page could not be reached ({config_url})"
	else:
		data = response.json()["data"]
		if not data.get("config") or data["config"].get("log_level") is None:
			result += "Could not find log_level configuration"
		else:
			if data["config"]["log_level"] > 6:
				result += f'log_level is set to {data["config"]["log_level"]}. This could impact performance.'
			if data["config"]["log_level_file"] > 6:
				result += f'log_level_file is set to {data["config"]["log_level_file"]}. This could impact performance.'
			if data["config"]["log_level_stderr"] > 6:
				result += f'log_level_stderr is set to {data["config"]["log_level_stderr"]}. This could impact performance.'
	return result


def diagnose_client():
	result = "client\n"
	#log level too high
	return result
