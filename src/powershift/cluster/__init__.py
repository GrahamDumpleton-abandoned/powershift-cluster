from __future__ import print_function

import os
import sys
import shutil
import shlex
import subprocess
import re
import posixpath
import tempfile
import ssl
import json

from glob import glob

import click

from ..cli import root, server_url, session_context, session_token

def execute(command):
    return subprocess.run(shlex.split(command))

def execute_with_input(command, input):
    p = subprocess.Popen(shlex.split(command),  stdin=subprocess.PIPE)
    if not isinstance(input, bytes):
        input = input.encode('UTF-8')
    p.communicate(input=input)
    return p

def execute_and_discard(command):
    return subprocess.run(shlex.split(command), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

def execute_and_capture(command):
    return subprocess.check_output(shlex.split(command),
            universal_newlines=True)

def container_path(path):
    # On Windows, the DOS style path needs to be converted to POSIX
    # style path separators and a UNC style drive definition when the
    # path is used inside of the container.

    if sys.platform == 'win32':
        drive, path = os.path.splitdrive(path)
        path = '/%s%s' % (drive[:-1], path.replace('\\', '/'))

    return path

def active_instance():
    container = execute_and_capture('docker ps -f name=origin -q')
    container = container.strip()

    if container:
        return container

def cluster_running():
    return active_instance() is not None

def active_profile(ctx):
    try:
        rootdir = ctx.obj['ROOTDIR']
        with open(os.path.join(rootdir, 'active_profile')) as fp:
            return fp.read().strip()

    except Exception:
        pass

def activate_profile(ctx, profile):
    try:
        rootdir = ctx.obj['ROOTDIR']
        with open(os.path.join(rootdir, 'active_profile'), 'w') as fp:
            return fp.write(profile)

    except Exception:
        pass

def cleanup_profile(ctx):
    try:
        rootdir = ctx.obj['ROOTDIR']
        os.unlink(os.path.join(rootdir, 'active_profile'))
    except Exception:
        pass

def profile_names(ctx):
    profiles = ctx.obj['PROFILES']

    return map(os.path.basename, glob(os.path.join(profiles, '*')))

@root.group()
@click.pass_context
def cluster(ctx):
    """
    Manage a local OpenShift cluster.

    The OpenShift cluster will run as an all-in-one container on a local
    Docker host. Data will be preserved between restarts of the OpenShift
    cluster against a named profile. You can create multiple profiles so
    that you can setup multiple local OpenShift instances. You can though
    only run one instance at a time.

    The default routes for exposed applications in the OpenShift cluster
    will use xip.io and the local host IP of your OpenShift cluster. A
    different route suffix can be supplied when the OpenShift cluster is
    started up the first time.

    """

    ROOTDIR = ctx.obj['ROOTDIR']
    DEFAULT_PROFILES = os.path.join(ROOTDIR, 'profiles')
    PROFILES = os.environ.get('POWERSHIFT_PROFILES_DIR', DEFAULT_PROFILES)

    ctx.obj['PROFILES'] = PROFILES

@cluster.command()
@click.option('--image', default=None,
    help='Specify alternate image to use for OpenShift.')
@click.option('--version', default=None,
    help='Specify the tag for the OpenShift images.')
@click.option('--routing-suffix', default=None,
    help='Specify alternate route for applications.')
@click.option('--logging', is_flag=True,
    help='Install logging (experimental).')
@click.option('--metrics', is_flag=True,
    help='Install metrics (experimental).')
@click.option('--loglevel', default=0, type=int,
    help='Log level for the OpenShift client.')
@click.option('--server-loglevel', default=0, type=int,
    help='Log level for the OpenShift server.')
@click.argument('profile', default='default')
@click.pass_context
def up(ctx, profile, image, version, routing_suffix, logging, metrics,
        loglevel, server_loglevel):

    """
    Starts up an OpenShift cluster.

    Starts the OpenShift cluster with the named profile. If no profile
    name is supplied the 'default' profile is used. Additional options
    can be used to configure the OpenShift cluster the first time that
    the named profile is started. These options will be remembered and
    passed automatically each time the same named profile is started.

    # Start cluster with the default profile name.

      powershift cluster up

    # Start cluster with a named profile.

      powershift cluster up research

    # Start cluster with an alternate route for applications.

      powershift cluster up --routing-suffix apps.example.com

    # Start cluster with an alternate set of OpenShift images.

    \b
      powershift cluster up --image="registry.example.com/origin" \\
          --version="v1.1"

    Note that you can only start up one OpenShift cluster at a time. If
    you need to switch between instances you will need to shutdown the
    active instance and then startup the second instance.

    """

    # Ensure that the root directory and profiles directory exist.

    root_dir = ctx.obj['ROOTDIR']
    profiles_dir = ctx.obj['PROFILES']

    os.makedirs(root_dir, exist_ok=True)
    os.makedirs(profiles_dir, exist_ok=True)

    # Check if there is an instance already running for a different
    # profile or of the request profile.

    instance = active_instance()

    if instance is not None:
        current = active_profile(ctx)

        if profile != current:
            click.echo('Failed: Already running "%s".' % current)
            ctx.exit(1)

        click.echo('Running')
        ctx.exit(0)

    profile_dir = os.path.join(profiles_dir, profile)

    if profile not in profile_names(ctx):
        click.echo('Creating')

        # Create the directory structure for a specific profile.

        try:
            data_dir = os.path.join(profile_dir, 'data')
            config_dir = os.path.join(profile_dir, 'config')
            volumes_dir = os.path.join(profile_dir, 'volumes')

            os.mkdir(profile_dir)
            os.mkdir(data_dir)
            os.mkdir(config_dir)
            os.mkdir(volumes_dir)

        except IOError:
            click.echo('Failed: Cannot create profile directories.')
            sys.exit(1)

        # On Linux the Docker service will have its own IP address, so
        # need to determine that. Otherwise use 127.0.0.1 as the IP
        # for the OpenShift instance.

        if sys.platform == 'linux':
            ifconfig = execute_and_capture('/usr/sbin/ifconfig docker0')
            for line in ifconfig.split('\n'):
                if 'inet' in line:
                    ipaddr = line.split()[1]
                    break
            else:
                ipaddr = '127.0.0.1'
        else:
            ipaddr = '127.0.0.1'

        # Use the same IP address for applicaton routes unless an
        # alternative is provided. We use xip.io so can easily map
        # everything back to the same IP. If an alternative hostname was
        # provided, then is up to user to create a wildcard DNS entry
        # that maps to the necessary IP address.

        if routing_suffix is None:
            if ipaddr != '127.0.0.1':
                routing_suffix = 'apps.%s.%s.xip.io' % (profile, ipaddr)
            else:
                routing_suffix = ''

        command = ['oc cluster up']

        # Don't pass through any IP address by default for Windows as it
        # will allocate one itself based on what the VM is that Docker is
        # running. Too much mucking around to work out what it is and the
        # default system to be secure enough as is an internal IP.

        if sys.platform == 'win32':
            if ipaddr != '127.0.0.1':
                command.append('--public-hostname "%s"' % ipaddr)
        else:
            command.append('--public-hostname "%s"' % ipaddr)

        command.append('--host-data-dir "%s"' % container_path(data_dir))
        command.append('--host-config-dir "%s"' % container_path(config_dir))

        command.append('--use-existing-config')

        if routing_suffix:
            command.append('--routing-suffix "%s"' % routing_suffix)

        if image:
            command.append('--image "%s"' % image)

        if version:
            command.append('--version "%s"' % version)

        if logging:
            command.append('--logging')

        if metrics:
            command.append('--metrics')

        if loglevel:
            command.append('--loglevel %d' % loglevel)

        if server_loglevel:
            command.append('--server-loglevel %d' % server_loglevel)

        if ipaddr != '127.0.0.1':
            command.append('--forward-ports=false')

        command = ' '.join(command)

        # Save away the command line used for 'oc cluster up' so we can
        # use it for subsequent runs without needing to work out options
        # again, or supply them on the command line.

        run_file = os.path.join(profile_dir, 'run')

        with open(run_file, 'w') as fp:
            fp.write(command)

        click.echo(command)

        # Run 'oc cluster up' to start up the instance.

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: The "oc cluster up" command failed.')
            ctx.exit(result.returncode)

        # Grant sudoer role to the developer so they do not switch to
        # the admin account. Instead can use user impersonation. We
        # actually rely on this for when creating volumes. Note that on
        # Linux we have to temporarily make the 'admin.kubeconfig' file
        # readable to others so we can access it from the local system.

        master = '/var/lib/origin/openshift.local.config/master'
        kubeconfig = '%s/admin.kubeconfig' % master

        if sys.platform == 'linux':
            result = execute('docker exec origin chmod o+r %s' % kubeconfig)

            if result.returncode != 0:
                click.echo('Failed: Unable to adjust kubeconfig access.')
                ctx.exit(result.returncode)

        context = session_context()

        project, cluster, user = context.strip().split('/')

        context = 'default/%s/system:admin' % cluster

        local_kubeconfig = os.path.join(config_dir, 'master', 'admin.kubeconfig')

        command = ['oc adm policy']

        command.append('add-cluster-role-to-group sudoer system:authenticated')
        command.append('--config "%s"' % local_kubeconfig)
        command.append('--context "%s"' % context)

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to assign sudoer role to developer.')
            ctx.exit(result.returncode)

        if sys.platform == 'linux':
            result = execute('docker exec origin chmod o-r %s' % kubeconfig)

            if result.returncode != 0:
                click.echo('Failed: Unable to restore kubeconfig access.')
                ctx.exit(result.returncode)

        # Setup an admin account that can be used from the web console.

        command = ['oc adm policy']

        command.append('add-cluster-role-to-user cluster-admin admin')
        command.append('--as system:admin')

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to create admin user.')
            ctx.exit(result.returncode)

    else:
        click.echo('Starting')

        # Start up the OpenShift instance using the saved startup
        # command from when the instance was first created.

        run_file = os.path.join(profile_dir, 'run')

        with open(run_file) as fp:
            command = fp.read().strip()

        click.echo(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: The "oc cluster up" command failed.')
            ctx.exit(result.returncode)

    # Record what the current active profile is.

    activate_profile(ctx, profile)

    click.echo('Started')

@cluster.command()
@click.pass_context
def down(ctx):
    """
    Stops the active OpenShift cluster.

    """

    instance = active_instance()

    if instance is None:
        click.echo('Stopped')
        ctx.exit(1)

    click.echo('Stopping')

    # Stop activate instance with 'oc cluster down' and remove the
    # record of what the active profile is.

    result = execute('oc cluster down')

    cleanup_profile(ctx)

    if result.returncode == 0:
        click.echo('Stopped')
    else:
        click.echo('Failed: The "oc cluster down" command failed.')

    ctx.exit(result.returncode)

@cluster.command()
@click.argument('profile')
@click.pass_context
def destroy(ctx, profile):
    """
    Destroys the named OpenShift cluster.

    If the named OpenShift cluster is currently active, it will be stopped
    before then being detsroyed.

    """
    if profile not in profile_names(ctx):
        click.echo('Invalid: %s' % profile)
        ctx.exit(1)

    click.confirm('Destroy profile %r?' % profile, abort=True)

    # If the profile to be destroyed is the current active one then we
    # need to make sure it is stopped before removing anything.

    if profile == active_profile(ctx):
        click.echo('Stopping')

        result = execute('oc cluster down')

        cleanup_profile(ctx)

        if result.returncode == 0:
            click.echo('Stopped')
        else:
            click.echo('Failed: The "oc cluster down" command failed.')
            ctx.exit(result.returncode)

    profiles = ctx.obj['PROFILES']

    directory = os.path.join(profiles, profile)

    click.echo('Removing: %s' % directory)

    # Remove the profile directory. There may be a risk this will not
    # completely work if files were created in a volume which had
    # ownership or permissions that prevent removal.

    shutil.rmtree(directory)

@cluster.command()
@click.pass_context
def list(ctx):
    """
    List the available OpenShift cluster profiles.

    """

    current = active_profile(ctx)

    profiles = profile_names(ctx)

    for profile in profiles:
        if profile == current:
            click.echo(profile + ' (active)')
        else:
            click.echo(profile)

@cluster.command()
@click.pass_context
def status(ctx):
    """
    Displays the status of the OpenShift cluster.

    """

    instance = active_instance()

    if instance is None:
        click.echo('Status: Stopped')
        ctx.exit(1)

    profile = active_profile(ctx)

    if profile is None:
        click.echo('Failed: Cannot find active profile.')
        ctx.exit(1)

    click.echo('Status: Running')

@cluster.command()
@click.pass_context
def ssh(ctx):
    """
    Opens a shell session in the OpenShift master node.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    # Use the docker command to do this as the 'docker' module does not
    # seem to work when executing an interactive shell bound to a tty.

    result = execute('docker exec -it origin /bin/bash')

    ctx.exit(result.returncode)

@cluster.group()
@click.pass_context
def volumes(ctx):
    """
    Manage persistent volumes for the cluster.

    """

    pass

class ClaimRef(click.ParamType):
    name = 'claim-ref'

    def convert(self, value, param, ctx):
        try:
            project, name = value.split('/')
            return (project, name)
        except ValueError:
            self.fail('%s is not a valid claim reference' % value, param, ctx)

class VolumeSize(click.ParamType):
    name = 'volume-size'

    def convert(self, value, param, ctx):
        if not re.match('^\d+[GM]i$', value):
            self.fail('%s is not a valid volume size' % value, param, ctx)
        return value

@volumes.command('create')
@click.option('--path', default=None, type=click.Path(resolve_path=True),
    help='Specify a path for the persistent volume')
@click.option('--size', default='10Gi', type=VolumeSize(),
    help='Specify a size for the persistent volume.')
@click.option('--claim', default=None, type=ClaimRef(),
    help='Assign the persistent volume a claim reference.')
@click.argument('name')
@click.pass_context
def volumes_create(ctx, name, path, size, claim):
    """
    Create a new persistent volume.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    profiles = ctx.obj['PROFILES']
    profile = active_profile(ctx)

    # Need to make sure the named persistent volume doesn't already
    # exist so we try and query details for it and if that fails we
    # should be good to go.

    command = 'oc get pv %s --as system:admin' % name

    result = execute_and_discard(command)

    if result.returncode == 0:
        click.echo('Failed: Persistent volume name already in use.')
        ctx.exit(1)

    # If we are generating the path for a volume ourselves, then we also
    # create the directory and set the permissions. If the path is
    # supplied then expect the directory to exist. When creating the
    # directory we make it writable to everyone else an arbitrary user
    # in the container will not be able to write to it.

    if path is None:
        path = posixpath.join(profiles, profile, 'volumes', name)
        os.makedirs(path, exist_ok=True)
        os.chmod(path, 0o777)

    else:
        path = os.path.abspath(path)

    # Define the persistent volume.

    pv = {
        'kind': 'PersistentVolume',
        'apiVersion': 'v1',
        'metadata': {
            'name': name
        },
        'spec': {
            'accessModes': ['ReadWriteOnce', 'ReadWriteMany'],
            'capacity': {'storage': size},
            'hostPath': {'path': container_path(path)},
            'persistentVolumeReclaimPolicy': 'Retain'
        }
    }

    # Add a claim reference if one is provided.

    if claim is not None:
        ref = {
            'kind': 'PersistentVolumeClaim',
            'apiVersion': 'v1',
            'namespace': claim[0],
            'name': claim[1]
        }

        pv['spec']['claim_ref'] = ref

    # Create the persistent volume.

    command = 'oc create -f - --as system:admin'

    result = execute_with_input(command, json.dumps(pv))

    if result.returncode != 0:
        click.echo('Failed: Persistent volume creation failed.')
        ctx.exit(result.returncode)

    # Output the details of the persistent volume created.

    result = execute('oc describe pv "%s" --as system:admin' % name)

    ctx.exit(result.returncode)

@volumes.command('list')
@click.pass_context
def volumes_list(ctx):
    """
    List the available peristent volumes.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    # Output the details of all persistent volumes.

    result = execute('oc describe pv --as system:admin')

    ctx.exit(result.returncode)
