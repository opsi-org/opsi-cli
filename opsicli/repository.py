# -*- coding: utf-8 -*-
"""
This modules provides functions to interact with repositories.
"""

from opsicommon.objects import OpsiDepotserver

from OPSI.Util.Repository import WebDAVRepository, getRepository  # type: ignore[import]
from opsicli import __version__


def get_repository(depot: OpsiDepotserver) -> WebDAVRepository:
	"""
	Returns a WebDAVRepository object configured for the depot.
	"""
	return getRepository(
		url=depot.repositoryRemoteUrl,
		username=depot.id,
		password=depot.opsiHostKey,
		maxBandwidth=(max(depot.maxBandwidth or 0, 0)) * 1000,
		application=f"opsi-cli/{__version__}",
		readTimeout=24 * 3600,
	)
