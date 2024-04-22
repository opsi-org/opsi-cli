"""
test_plugins
"""

import time
from pathlib import Path

import pytest
from opsicommon.logging import LOG_WARNING, use_logging_config

from opsicli.utils import decrypt, encrypt, install_binary, retry


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


def test_retry() -> None:
	with use_logging_config(stderr_level=LOG_WARNING):
		caught_exceptions: list[Exception] = []

		@retry(retries=2, wait=0.5, exceptions=(ValueError,), caught_exceptions=caught_exceptions)
		def failing_function() -> None:
			raise ValueError("Test")

		start = time.time()
		with pytest.raises(ValueError):
			failing_function()
		assert time.time() - start >= 1

		assert len(caught_exceptions) == 2
		assert isinstance(caught_exceptions[0], ValueError)
		assert isinstance(caught_exceptions[1], ValueError)

		caught_exceptions = []

		@retry(retries=10, exceptions=(PermissionError, ValueError), caught_exceptions=caught_exceptions)
		def failing_function2() -> None:
			if len(caught_exceptions) < 2:
				raise PermissionError("Test")
			if len(caught_exceptions) < 4:
				raise ValueError("Test")
			raise RuntimeError("Test")

		with pytest.raises(RuntimeError):
			failing_function2()

		assert len(caught_exceptions) == 4
