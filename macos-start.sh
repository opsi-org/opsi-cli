#!/bin/sh

contents=$(dirname $(dirname $0))
$contents/Resources/opsicli/opsi-cli $@
