# opsi-cli is part of the device management solution OPSI http://www.opsi.org
# Copyright (c) 2021-2026 uib GmbH <info@uib.de>
# All rights reserved.
# License: AGPL-3.0-only

"""
test_plugins
"""

from pathlib import Path

import pytest
from opsi.opsi.service.model.object import LocalbootProduct

from opsicli.utils import create_nested_dict, decrypt, encrypt, install_binary


@pytest.mark.parametrize(
	"cleartext",
	(
		"password",
		"ß239ündw6327hd",
		"::::::::",
		" : : : . ",
		"u3heequeish9uuphei4aemich4yeonahGee2ohphe8aedaeb1iphoo7yahRahsh9eibea1chahsaika5ieshiegogu6AhG7meipooB4yulung1xeil",
	),
)
def test_encrypt_decrypt(cleartext: str) -> None:
	enc = encrypt(cleartext)
	assert enc.startswith("{crypt}")
	dec = decrypt(enc)
	assert dec == cleartext


def test_decrypt_unencrypted() -> None:
	assert decrypt("test") == "test"


def test_install_binary(tmp_path: Path) -> None:
	current = tmp_path / "testfile"
	new = tmp_path / "newfile"
	new.touch()

	install_binary(source=new, destination=current)
	assert current.exists()
	assert new.exists()
	assert not current.with_suffix(current.suffix + ".old").exists()

	install_binary(source=new, destination=current)
	assert current.exists()
	assert new.exists()
	assert not current.with_suffix(current.suffix + ".old").exists()


def test_create_nested_dict() -> None:
	product1 = LocalbootProduct(id="product1", name="Product 1", productVersion="1.0.0", packageVersion="1")
	product2 = LocalbootProduct(id="product2", name="Product 2", productVersion="1.0", packageVersion="3")
	product3 = LocalbootProduct(id="product3", name="Product 3", productVersion="4.6.3.2172", packageVersion="3")

	list_of_objects: list[object] = [product1, product2, product3]
	keys = ["id", "productVersion", "packageVersion"]

	expected = {
		"product1": {"1.0.0": {"1": product1}},
		"product2": {"1.0": {"3": product2}},
		"product3": {"4.6.3.2172": {"3": product3}},
	}

	assert create_nested_dict(list_of_objects, keys) == expected
