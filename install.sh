#!/bin/sh

#could be part of server-package postinst

mkdir -p ~/.local/lib/opsicli
mkdir -p ~/.local/lib/opsicli/shell-complete

if bash --version > /dev/null 2> /dev/null; then
	_OPSI_COMPLETE=source_bash dist/opsi > ~/.local/lib/opsicli/shell-complete/opsi-complete-bash.sh
	if ! grep -q "opsicli/shell-complete/opsi-complete-bash.sh" ~/.bashrc; then
		echo "adding opsi-complete-bash.sh to .bashrc"
		echo "source ~/.local/lib/opsicli/shell-complete/opsi-complete-bash.sh" >> ~/.bashrc
	fi
fi

if zsh --version > /dev/null 2> /dev/null; then
	_OPSI_COMPLETE=source_zsh dist/opsi > ~/.local/lib/opsicli/shell-complete/opsi-complete-zsh.sh
	if ! grep -q "opsicli/shell-complete/opsi-complete-zsh.sh" ~/.bashrc; then
		echo "adding opsi-complete-zsh.sh to .zshrc"
		echo "source ~/.local/lib/opsicli/shell-complete/opsi-complete-zsh.sh" >> ~/.zshrc
	fi
fi

if fish --version > /dev/null 2> /dev/null; then
	echo "adding opsi-complete.sh to ~/.config/fish/completions/"
	_OPSI_COMPLETE=source_fish dist/opsi > ~/.config/fish/completions/opsi-complete.fish
fi
