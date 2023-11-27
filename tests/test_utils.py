"""
test_plugins
"""

from pathlib import Path

import pytest

from opsicli.utils import decrypt, encrypt, replace_binary


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


def test_replace_binary(tmp_path: Path) -> None:
	current = tmp_path / "testfile"
	current.touch()
	new = tmp_path / "newfile"
	new.touch()
	replace_binary(current=current, new=new)
	assert current.exists()
	assert not new.exists()
	assert current.with_suffix(current.suffix + ".old").exists()

	new.touch()
	replace_binary(current=current, new=new)
	assert current.exists()
	assert current.with_suffix(current.suffix + ".old").exists()
