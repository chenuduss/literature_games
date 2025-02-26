#!/bin/sh

CURRENT_DIR = $(PWD)
systemctl stop litgb.service
runuser litgb -c 'bash $CURRENT_DIR/update_repo.sh'
systemctl start litgb.service