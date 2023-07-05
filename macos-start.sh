#!/bin/sh

contents=$(dirname $(dirname $0))
exec $contents/Resources/opsicli/opsi-cli $@
