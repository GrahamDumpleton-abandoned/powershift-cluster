#!/bin/bash

set -eo pipefail

MASTER="/var/lib/origin/openshift.local.config/master"

PATCH=`cat <<EOF
{
    "oauthConfig": {
        "identityProviders": [
            {
                "challenge": true,
                "login": true,
                "mappingMethod": "add",
                "name": "htpassword",
                "provider": {
                    "apiVersion": "v1",
                    "kind": "HTPasswdPasswordIdentityProvider",
                    "file": "$MASTER/users.htpasswd"
                }
            }
        ]
    }
}
EOF`

cp $MASTER/master-config.yaml /tmp/master-config.yaml

openshift ex config patch /tmp/master-config.yaml \
    --patch "$PATCH" > $MASTER/master-config.yaml
