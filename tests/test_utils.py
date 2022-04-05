"""
test_plugins
"""

import pytest

from opsicli.utils import decrypt, encrypt


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
def test_encrypt_decrypt(cleartext) -> None:
	enc = encrypt(cleartext)
	assert enc.startswith("{crypt}")
	dec = decrypt(enc)
	assert dec == cleartext


def test_decrypt_unencrypted() -> None:
	assert decrypt("test") == "test"
