#!/bin/bash

systemctl stop litgb.service

runuser -l  litgb -c 'git pull'

systemctl start litgb.service