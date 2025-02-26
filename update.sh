#!/bin/sh

CURRENT_DIR = $(cwd)
systemctl stop litgb.service
runuser litgb -c 'sh $CURRENT_DIR/update_repo.sh'
systemctl start litgb.service