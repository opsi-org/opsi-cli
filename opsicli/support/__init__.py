import logging
import os
import zipfile
import tempfile
import click

from .collect import write_general_info, write_server_info, write_client_info

__version__ = "0.1.0"
logger = logging.getLogger()


def get_plugin_name():
	return "support"


@click.group(name="support", short_help="short help for support")
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi support, version %(version)s")
def cli():
	"""
	opsi support subcommand.
	This is the long help.
	"""
	logger.info("support subcommand")


@cli.command(short_help='short help for collect')
def collect():
	"""
	opsi support collect subsubcommand.
	This is the long help.
	"""
	logger.info("collect subsubcommand")
	with tempfile.TemporaryDirectory() as tmpdir:
		write_general_info(os.path.join(tmpdir, "general"))
		if os.path.exists("/etc/opsi/opsiconfd.conf"):
			write_server_info(os.path.join(tmpdir, "server"))
		if os.path.exists("/etc/opsi-client-agent/opsiclientd.conf"):	#TODO: windows clients
			write_client_info(os.path.join(tmpdir, "client"))

		with zipfile.ZipFile("collected_infos.zip", "w", zipfile.ZIP_DEFLATED) as zfile:
			for root, _, files in os.walk(tmpdir):
				base = os.path.relpath(root, start=tmpdir)
				for single_file in files:
					zfile.write(os.path.join(root, single_file), arcname=os.path.join("collected_infos", base, single_file))



"""
concept
support collect --make-ticket --day-span <days> (default 7) --remote <url>

collect logs: everything at most <days> days old
inspect self unless --remote <url> is given

# server
/var/log/opsi
/etc/opsi
ip a
lsb_release -a

# client
/var/log/opsi-client-agent	|| C:\opsi.org\log
/var/log/opsi-script		|| C:\opsi.org\applog
/etc/opsi-client-agent		|| C:\opsi.org\opsiclientd
/etc/opsi-script			|| C:\Program Files (x86)\opsi.org\opsi-client-agent
ip a						|| ipconfig
lsb_release -a				|| systeminfo
"""
