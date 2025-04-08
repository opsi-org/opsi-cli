FROM docker.uib.gmbh/opsi/dev/pybuilder:deb10-py3.13

ARG DEV_USER

ENV LC_ALL="en_US.UTF-8" \
	LANG="en_US.UTF-8" \
	LANGUAGE="en_US:en" \
	DEV_USER=${DEV_USER}

RUN apt-get update \
	&& apt-get --yes dist-upgrade\
	&& apt-get --yes install sudo zsh git openssh-client inetutils-ping \
	&& sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
	&& locale-gen \
	&& sh -c "$(wget -O- https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" \
	&& git clone https://github.com/zsh-users/zsh-autosuggestions /root/.oh-my-zsh/custom/plugins/zsh-autosuggestions \
	&& git clone https://github.com/zsh-users/zsh-syntax-highlighting.git /root/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting \
	&& git clone --depth=1 https://github.com/romkatv/powerlevel10k.git /root/.oh-my-zsh/custom/themes/powerlevel10k \
	&& usermod -s /bin/zsh root

COPY files/ /

RUN if [ -n "$DEV_USER" ] && [ "$DEV_USER" != "root" ]; then \
	useradd --create-home -s /bin/zsh ${DEV_USER} \
	&& echo "${DEV_USER} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
	&& sed -i s'#secure_path=.*#secure_path="/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"#' /etc/sudoers \
	&& cp -a /root/.zshrc /root/.oh-my-zsh /root/.p10k.zsh  /root/.zsh_history /home/${DEV_USER}/ \
	&& chown -R ${DEV_USER}:${DEV_USER} /home/${DEV_USER} \
	&& chmod -R g-rww,o-rww /home/${DEV_USER}/.oh-my-zsh \
	; fi

WORKDIR /workspace
