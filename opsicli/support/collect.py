import os
import platform
import time
import yaml
import shutil
import psutil
import netifaces

def write_general_info(directory):

	def write_system_info(filehandle):
		filehandle.write("== Operating System ==\n")
		system = {}
		os_info = platform.uname()
		for field in os_info._fields:
			system[field] = getattr(os_info, field)
		filehandle.write(yaml.dump(system, default_flow_style=False))

	def write_network_info(filehandle):
		filehandle.write("\n\n== Network ==\n")
		network = {}
		for iface in netifaces.interfaces():
			network[iface] = {}
			for address_type in ["AF_LINK", "AF_INET", "AF_INET6"]:
				value = netifaces.ifaddresses(iface).get(getattr(netifaces, address_type))
				if value:
					network[iface][address_type] = value
		filehandle.write(yaml.dump(network, default_flow_style=False))

	def write_service_info(filehandle):
		filehandle.write("\n\n== opsi Processes ==\n")
		processes = []
		for proc in psutil.process_iter():
			name = proc.name()
			if name.lower().startswith("opsi"):
				pinfo = proc.as_dict(attrs=['pid', 'username', 'cpu_percent'])
				pinfo['memory'] = proc.memory_info().rss
				processes.append({name : pinfo})
		filehandle.write(yaml.dump(processes, default_flow_style=False))

	os.makedirs(directory)
	with open(os.path.join(directory, "system_characteristics.txt"), "w") as outfile:
		write_system_info(outfile)
		write_network_info(outfile)
		write_service_info(outfile)


def copy_logs(directory, log_dir, past_days):
	if not os.path.exists(log_dir):
		print(f"Could not find any logs at {log_dir}")
		return

	if not os.path.exists(os.path.join(directory, "log")):
		os.makedirs(os.path.join(directory, "log"))
	time_threshold = time.time() - 3600*24*past_days
	for root, dirs, files in os.walk(log_dir):
		target_dir = os.path.relpath(root, log_dir)

		for source_dir in dirs:
			os.makedirs(os.path.join(directory, "log", target_dir, source_dir))

		for logfile in files:
			source = os.path.join(root, logfile)
			destination = os.path.join(directory, "log", target_dir, logfile)
			# check that file mod date is newer than now - past_days
			if os.path.getmtime(source) > time_threshold:
				shutil.copy(source, destination)


def write_server_info(directory, past_days, no_logs=False):

	def copy_server_config(directory):
		if os.path.exists("/etc/opsi/opsiconfd.conf"):
			shutil.copy("/etc/opsi/opsiconfd.conf", directory)
		if os.path.exists("/etc/opsi/opsi.conf"):
			shutil.copy("/etc/opsi/opsi.conf", directory)
		if os.path.exists("/etc/opsi/opsipxeconfd.conf"):
			shutil.copy("/etc/opsi/opsipxeconfd.conf", directory)
		if os.path.exists("/etc/opsi/opsi-package-updater.conf"):
			shutil.copy("/etc/opsi/opsi-package-updater.conf", directory)
		if os.path.exists("/etc/opsi/backends"):
			shutil.copytree("/etc/opsi/backends", os.path.join(directory, "backends"))
		if os.path.exists("/etc/opsi/backendManager"):
			shutil.copytree("/etc/opsi/backendManager", os.path.join(directory, "backendManager"))
		if os.path.exists("/etc/opsi/hwaudit/opsihwaudit.conf"):
			shutil.copy("/etc/opsi/hwaudit/opsihwaudit.conf", directory)


	os.makedirs(directory)
	copy_server_config(directory)
	if not no_logs:
		copy_logs(directory, "/var/log/opsi/", past_days)


def write_client_info(directory, past_days, no_logs=False):

	def copy_client_config(directory):
		if os.path.exists("/etc/opsi-client-agent/opsiclientd.conf"):
			shutil.copy("/etc/opsi-client-agent/opsiclientd.conf", directory)
		if os.path.exists("/etc/opsi-client-agent/opsi-client-agent.conf"):
			shutil.copy("/etc/opsi-client-agent/opsi-client-agent.conf", directory)
		if os.path.exists(r"C:\Program Files (x86)\opsi.org\opsi-client-agent\opsiclientd\opsiclientd.conf"):
			shutil.copy(r"C:\Program Files (x86)\opsi.org\opsi-client-agent\opsiclientd\opsiclientd.conf", directory)

	os.makedirs(directory)
	copy_client_config(directory)
	if not no_logs:
		if platform.system().lower() == "windows":
			copy_logs(directory, r"C:\opsi.org\log", past_days)
		else:
			copy_logs(directory, "/var/log/opsi-client-agent/", past_days)
			copy_logs(directory, "/var/log/opsi-script/", past_days)
