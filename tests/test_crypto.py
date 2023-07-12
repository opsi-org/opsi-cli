"""
test crypto plugin
"""

from passlib.hash import sha512_crypt  # type: ignore[import]

from .utils import run_cli


def test_crypto_password_to_hash() -> None:
	exit_code, output = run_cli(["crypto", "password-to-hash", "linux123"])
	assert exit_code == 0
	split_length = len("password hash is: ")
	assert sha512_crypt.verify("linux123", output.split("\n")[0][split_length:])
