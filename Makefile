.PHONY: help install clean

help:
	@echo "Below is a list of targets and what they do:"
	@echo ""
	@echo "make install"
	@echo "  installs into a python3 virtualenv and echoes instructions"
	@echo "  for adding ec2ssh to your path, and optionally enabling"
	@echo "  completion support"


.venv: setup.py
	virtualenv --python python3 .venv
	# explicit touch to ensure good update time relative to setup.py
	touch .venv

.venv/bin/ec2ssh: .venv
	.venv/bin/python setup.py develop
	# explicit touch, ensures good mtime relative to venv
	touch .venv/bin/ec2ssh

install: .venv/bin/ec2ssh
	@echo "\nAdd \"$(shell pwd)/.venv/bin\" to the end of your PATH\n"
	@echo "For completion support, ensure your bashrc sources bash-completion.sh\n"

clean:
	-rm -rf .venv
	-rm -rf *.egg-info
