#!/bin/bash
echo 'Starting celery in shell'
celery worker -A atomica_apps.apptasks_tb -l info $@
