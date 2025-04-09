# -*- coding: utf-8 -*-

# opsi-cli is part of the device management solution opsi http://www.opsi.org
# Copyright (c) 2021-2025 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_cache
"""

import time

from opsicli.cache import cache


def test_cache_access() -> None:
	cache.set("testkey", "testvalue")
	assert cache.get("testkey") == "testvalue"
	cache.set("testkey", [1, 2, 3])
	assert cache.get("testkey") == [1, 2, 3]


def test_cache_ttl() -> None:
	cache.set("testkey", "testvalue", ttl=1)
	time.sleep(2)  # ttl checks are done in int format
	assert cache.get("testkey") is None


def test_read_write_cache() -> None:
	cache.set("testkey", "testvalue")
	cache.store()
	cache.set("testkey", "othertestvalue")
	cache.load()
	assert cache.get("testkey") == "testvalue"
