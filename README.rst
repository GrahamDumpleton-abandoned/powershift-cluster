This package provides an addon for the PowerShift CLI for managing a local
OpenShift cluster. The commands provide a layer around the ``oc cluster
up`` command, adding the ability to easily maintain persistent profiles for
multiple local instances of OpenShift running on a Docker service.

Installing this package will automatically result in the ``powershift``
package being installed, along with the ``powershift`` command line client
contained in that package. The addon commands from this package will be
automatically registered with the ``powershift`` command line tool.

Available commands
------------------

To see all available command you can use inbuilt help features of the
``powershift command``.

::

    $ powershift
    Usage: powershift [OPTIONS] COMMAND [ARGS]...

      PowerShift client for OpenShift.

      This client provides additional functionality useful to users of the
      OpenShift platform. Base functionality is minimal, but can be extended by
      installing additional plugins.

      For more details see:

          https://github.com/getwarped/powershift

    Options:
      --help  Show this message and exit.

    Commands:
      cluster     Manage a local OpenShift cluster.
      completion  Output completion script for specified shell.
      console     Open a browser on the OpenShift web console.
      server      Displays the URL for the OpenShift cluster.

    $ powershift cluster
    Usage: powershift cluster [OPTIONS] COMMAND [ARGS]...

      Manage a local OpenShift cluster.

      The OpenShift cluster will run as an all-in-one container on a local
      Docker host. Data will be preserved between restarts of the OpenShift
      cluster against a named profile. You can create multiple profiles so that
      you can setup multiple local OpenShift instances. You can though only run
      one instance at a time.

      The default routes for exposed applications in the OpenShift cluster will
      use xip.io and the local host IP of your OpenShift cluster. A different
      route suffix can be supplied when the OpenShift cluster is started up the
      first time.

    Options:
      --help  Show this message and exit.

    Commands:
      destroy  Destroys the named OpenShift cluster.
      down     Stops the active OpenShift cluster.
      list     List the available OpenShift cluster...
      ssh      Opens a shell session in the OpenShift master...
      status   Displays the status of the OpenShift cluster.
      up       Starts up an OpenShift cluster.
      volumes  Manage persistent volumes for the cluster.

    $ powershift cluster volumes
    Usage: powershift cluster volumes [OPTIONS] COMMAND [ARGS]...

      Manage persistent volumes for the cluster.

    Options:
      --help  Show this message and exit.

    Commands:
      create  Create a new persistent volume.
      list    List the available peristent volumes.

Use the ``--help`` option on individual commands to see what the command
does and what further options can be supplied.
