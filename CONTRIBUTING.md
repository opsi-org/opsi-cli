# Contribute

## Setup development environment

### Adjust `pyproject.toml`

The included `pyproject.toml` is configured for the internal UIB GmbH development infrastructure.
Two adjustment are needed for public development and contribution.

1. Remove the `extra-index-url` from the `tool.uv` section:

```toml
# before
[tool.uv]
extra-index-url = [ "https://pypi.uib.gmbh/simple",]
index-strategy = "unsafe-best-match"
package = true

# after
[tool.uv]
index-strategy = "unsafe-best-match"
package = true
```

2. Add the pip source repository for `python-opsi-common`

```toml
# add anywhere in the pyproject.toml
[tool.uv.sources]
python-opsi-common = { git = "https://github.com/opsi-org/python-opsi-common.git" }
```

### Setup virtual environment using `uv`

```shell
uv sync
```

### Run `opsi-cli` commands

```shell
uv run python run-opsicli --help
# or
uv run python run-opsicli client-action reboot
```

### Commit changes

Make sure the following changed files are not included in your commit.

* `pyproject.toml`
* `uv.lock`
