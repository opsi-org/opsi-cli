import os
import platform
import yaml
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


def write_server_info(directory):
	pass

def write_client_info(directory):
	pass
