#!/bin/bash

#set -eo pipefail

PROFILE=$1

MASTER="/var/lib/origin/openshift.local.config/master"

PATCH=`cat <<EOF
{
    "admissionConfig": {
        "pluginConfig": {
            "BuildDefaults": {
                "configuration": {
                    "apiVersion": "v1",
                    "kind": "BuildDefaultsConfig",
                    "imageLabels": [
                        {
                            "name": "powershift-profile",
                            "value": "$PROFILE"
                        }
                    ]
                }
            }
        }
    }
}
EOF`

cp $MASTER/master-config.yaml /tmp/master-config.yaml

openshift ex --help > /dev/null 2>&1

if [ "$?" = "1" ]; then
    oc ex config patch /tmp/master-config.yaml \
        --patch "$PATCH" > $MASTER/master-config.yaml
else
    openshift ex config patch /tmp/master-config.yaml \
        --patch "$PATCH" > $MASTER/master-config.yaml
fi
