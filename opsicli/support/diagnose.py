import os


def diagnose_problems():
	result = diagnose_general() + "\n"
	if os.path.exists("/etc/opsi/opsiconfd.conf"):
		result += diagnose_server() + "\n"
	if os.path.exists("/etc/opsi-client-agent/opsiclientd.conf") or os.path.exists(r"C:\opsi.org"):
		result += diagnose_client() + "\n"
	return result


def diagnose_general():
	result = "general"
	#no internet access
	return result


def diagnose_server():
	result = "server"
	#log level too high
	return result


def diagnose_client():
	result = "client"
	#log level too high
	return result
