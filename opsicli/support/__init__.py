import logging
import os
import zipfile
import tempfile
import click

from opsicli.support.collect import write_general_info, write_diagnose_file, write_server_info, write_client_info
from opsicli.support.diagnose import diagnose_problems

__version__ = "0.1.0"
logger = logging.getLogger()


def get_plugin_name():
	return "support"


@click.group(name="support", short_help="support command for troubleshoot and help")
#@click.version_option(f"{__version__}", message="%(package)s, version %(version)s")
@click.version_option(__version__, message="opsi support, version %(version)s")
@click.pass_context
def cli(ctx):
	"""
	opsi support command.
	This is the long help.
	"""
	logger.info("support command")


@cli.command(short_help='collect information about system and opsi environment')
@click.option("--past-days", default=7, help="number of days to collect logs for")
@click.option("--no-logs", default=False, help="if True, do not collect logfiles")
@click.pass_context
def collect(ctx, past_days, no_logs):
	"""
	opsi-cli support collect subcommand.
	This is the long help.
	"""
	logger.info("collect subcommand")
	with tempfile.TemporaryDirectory() as tmpdir:
		write_general_info(os.path.join(tmpdir, "general"))
		write_diagnose_file(os.path.join(tmpdir, "general"), ctx.obj.get("server_interface"), ctx.obj.get("user"), ctx.obj.get("password"))
		if os.path.exists("/etc/opsi/opsiconfd.conf"):
			write_server_info(os.path.join(tmpdir, "server"), past_days, no_logs)
		if os.path.exists("/etc/opsi-client-agent/opsiclientd.conf") or os.path.exists(r"C:\opsi.org"):
			write_client_info(os.path.join(tmpdir, "client"), past_days, no_logs)

		with zipfile.ZipFile("collected_infos.zip", "w", zipfile.ZIP_DEFLATED) as zfile:
			for root, _, files in os.walk(tmpdir):
				base = os.path.relpath(root, start=tmpdir)
				for single_file in files:
					zfile.write(os.path.join(root, single_file), arcname=os.path.join("collected_infos", base, single_file))


@cli.command(short_help='identify possible problems')
@click.pass_context
def diagnose(ctx):
	"""
	opsi-cli support diagnose subcommand.
	This is the long help.
	"""
	logger.info("diagnose subcommand")
	result = diagnose_problems(ctx.obj.get("server_interface"), ctx.obj.get("user"), ctx.obj.get("password"))
	print(result)


#concept
#support collect --make-ticket --past-days <days> (default 7) --remote <url>
#	collect logs: everything at most <days> days old
#	inspect self unless --remote <url> is given
