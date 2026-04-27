# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_main
"""

import pytest

from opsicli.__main__ import LogLevel


@pytest.mark.parametrize(
	("part, complete"),
	(("deb", "debug"), ("er", "error"), ("5", 5), ("0", 0)),
)
def test_log_level(part: str, complete: str | int) -> None:
	log_level = LogLevel()
	completion = log_level.shell_complete(None, None, part)  # ty: ignore[invalid-argument-type]
	assert complete == completion.pop().value
