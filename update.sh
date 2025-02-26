#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
systemctl stop litgb.service
runuser litgb -c "bash $SCRIPT_DIR/update_repo.sh $SCRIPT_DIR"
systemctl start litgb.service