This package provides a plugin for the ``powershift`` command line client
for managing a local OpenShift cluster. The commands provide a layer around
the ``oc cluster up`` command, adding the ability to easily maintain
persistent profiles for multiple local instances of OpenShift running on a
Docker service.

To enhance security, a user database will also be configured so that the
default password for the developer account can be changed. Additional user
accounts can also be created, with system admin rights if necessary.

Finally a set of persistent volumes will also be associated with each
profile. Additional persistent volumes can also be declared, including
pre claimed volumes associated with an existing directory on the host
containing code or data files.

To install this package, along with the ``powershift-cli`` package, and the
``powershift`` command line program contained in that package, you should
use ``pip`` to install the package ``powershift-cluster[cli]``, rather than
just ``powershift-cluster``. Alternatively, you can install
``powershift-cli[all]``, which will install the ``powershift-cli`` package
along with all plugins currently available for the ``powershift`` command
line program.

For more details on how to install the ``powershift`` command line program
and available plugins see:

* https://github.com/getwarped/powershift-cli

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
      client      Install/update oc command line tool.
      cluster     Manage a local OpenShift cluster.
      completion  Output completion script for specified shell.
      console     Open a browser on the OpenShift web console.
      server      Displays the URL for the OpenShift cluster.
      session     Display information about current session.

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
      users    Manage accounts database for the cluster.
      volumes  Manage persistent volumes for the cluster.

    $ powershift cluster volumes
    Usage: powershift cluster volumes [OPTIONS] COMMAND [ARGS]...

      Manage persistent volumes for the cluster.

    Options:
      --help  Show this message and exit.

    Commands:
      create  Create a new persistent volume.
      list    List the available peristent volumes.

    $ powershift cluster users
    Usage: powershift cluster users [OPTIONS] COMMAND [ARGS]...

      Manage accounts database for the cluster.

    Options:
      --help  Show this message and exit.

    Commands:
      add     Adds a new user account.
      list    List active user accounts.
      passwd  Change the password for an account.
      remove  Removes a user account.

Use the ``--help`` option on individual commands to see what the command
does and what further options can be supplied.
