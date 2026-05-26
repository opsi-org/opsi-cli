# Guide for External Contributors

The opsi project is primarily developed by [uib GmbH](https://www.uib.de).
Its development workflow is highly automated and depends on several internal UIB systems.
Although efforts are underway to simplify contributions from outside the company, this guide by opsi user @JanMalte provides practical steps to overcome the current limitations.

## Setup development environment

### Adjust `pyproject.toml`

The included `pyproject.toml` is configured for the internal UIB GmbH development infrastructure.
Two adjustment are needed for public development and contribution.

1. Remove the `extra-index-url` from the `tool.uv` section:

```toml
# Before
[tool.uv]
extra-index-url = [ "https://pypi.uib.gmbh/simple",]
index-strategy = "unsafe-best-match"
package = true

# After
[tool.uv]
index-strategy = "unsafe-best-match"
package = true
```

2. Add the pip source repository for `python-opsi`

```toml
# Add anywhere in the pyproject.toml
[tool.uv.sources]
python-opsi = { git = "https://github.com/opsi-org/python-opsi.git" }
```

### Setup virtual environment using `uv`

```shell
uv sync
```

### Run `opsi-cli` commands

```shell
uv run opsi-cli --help
# or
uv run opsi-cli client-action reboot
```

### Commit changes

Make sure the following changed files are not included in your commit.

* `pyproject.toml`
* `uv.lock`
