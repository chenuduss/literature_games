#!/bin/bash

systemctl stop litgb.service

runuser litgb -p -c 'git pull'

systemctl start litgb.service