from __future__ import print_function

import io
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
import passlib.apache

from ..cli import root, command_client_env
from ..cli import server_url, session_context, session_token

def execute(command):
    if not isinstance(command, (list, tuple)):
        command = shlex.split(command)
    p = subprocess.Popen(command)
    p.communicate()
    return p

def execute_with_input(command, input):
    if not isinstance(command, (list, tuple)):
        command = shlex.split(command)
    p = subprocess.Popen(command, stdin=subprocess.PIPE)
    if not isinstance(input, bytes):
        input = input.encode('UTF-8')
    p.communicate(input=input)
    return p

def execute_and_discard(command):
    if not isinstance(command, (list, tuple)):
        command = shlex.split(command)
    p = subprocess.Popen(command, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
    p.communicate()
    return p

def execute_and_capture(command):
    if not isinstance(command, (list, tuple)):
        command = shlex.split(command)
    return subprocess.check_output(command,
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

@root.group('cluster')
@click.pass_context
def group_cluster(ctx):
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

@group_cluster.command('up')
@click.option('--image', default=None,
    help='Alternate image to use for OpenShift.')
@click.option('--version', default=None,
    help='Tag for the OpenShift images.')
@click.option('--public-hostname', default=None,
    help='Alternate route for console.')
@click.option('--routing-suffix', default=None,
    help='Alternate route for applications.')
@click.option('--logging', is_flag=True,
    help='Install logging (experimental).')
@click.option('--metrics', is_flag=True,
    help='Install metrics (experimental).')
@click.option('--volumes', default=10, type=int,
    help='Number of persistent volumes.')
@click.option('--volume-size', default='10Gi', type=VolumeSize(),
    help='Size of persistent volumes.')
@click.option('--loglevel', default=0, type=int,
    help='Log level for the OpenShift client.')
@click.option('--server-loglevel', default=0, type=int,
    help='Log level for the OpenShift server.')
@click.option('--env', '-e', multiple=True,
    help='Environment variables to set.')
@click.option('--http-proxy', default=None,
    help='HTTP proxy for master/builds (1.5+).')
@click.option('--https-proxy', default=None,
    help='HTTPS proxy for master/builds (1.5+).')
@click.option('--no-proxy', '-e', multiple=True,
    help='Hosts/subnets proxy should ignore (1.5+).')
@click.option('--identity-provider', default='none',
    help='Enable use of identity provider.')
@click.argument('profile', default='default')
@click.pass_context
def command_cluster_up(ctx, profile, image, version, public_hostname,
        routing_suffix, logging, metrics, volumes, volume_size, loglevel,
        server_loglevel, env, http_proxy, https_proxy, no_proxy,
        identity_provider):

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
          --version="v1.4.1"

    Note that you can only start up one OpenShift cluster at a time. If
    you need to switch between instances you will need to shutdown the
    active instance and then startup the second instance.

    """

    # Ensure that the root directory and profiles directory exist.

    root_dir = ctx.obj['ROOTDIR']
    profiles_dir = ctx.obj['PROFILES']

    ctx.obj['PROFILE'] = profile

    try:
        os.mkdir(root_dir)
    except OSError:
        pass

    try:
        os.mkdir(profiles_dir)
    except OSError:
        pass

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

    create_profile = False

    if profile not in profile_names(ctx):
        click.echo('Creating')

        create_profile = True

        # Create the directory structure on local file system.

        try:
            data_dir = os.path.join(profile_dir, 'data')
            config_dir = os.path.join(profile_dir, 'config')
            volumes_dir = os.path.join(profile_dir, 'volumes')

            os.mkdir(profile_dir)

            os.mkdir(data_dir)
            os.mkdir(config_dir)
            os.mkdir(volumes_dir)

        except OSError:
            click.echo('Failed: Cannot create host profile directories.')
            sys.exit(1)

        # Create the directory structure inside of the container.

        container_profiles_dir = '/var/lib/powershift/profiles'
        container_profile_dir = posixpath.join(container_profiles_dir, profile)

        container_config_dir = posixpath.join(container_profile_dir, 'config')
        container_data_dir = posixpath.join(container_profile_dir, 'data')
        container_volumes_dir = posixpath.join(container_profile_dir, 'volumes')

        command = []

        command.append('docker run --rm -v /var:/var busybox mkdir -p')
        command.append(container_config_dir)
        command.append(container_data_dir)
        command.append(container_volumes_dir)

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0: 
            click.echo('Failed: Cannot create container profile directories.')
            ctx.exit(result.returncode)

        # Prompt for alternate developer account password to use.

        if identity_provider == 'htpasswd':
            password = click.prompt('Enter Password',
                    default='developer', hide_input=True,
                    confirmation_prompt=True)
        else:
            password = 'developer'

        # Construct the command for oc cluster up.

        command = ['oc cluster up']

        # On Linux the Docker service will have its own IP address, so
        # need to determine that. Windows does as well but not sure how
        # to determine what it will be. For MacOS X it is 127.0.0.1.

        if sys.platform.startswith('linux'):
            if os.path.exists('/usr/sbin/ifconfig'):
                ifconfig = execute_and_capture('/usr/sbin/ifconfig docker0')
            else:
                ifconfig = execute_and_capture('/sbin/ip addr show docker0')

            for line in ifconfig.split('\n'):
                if 'inet' in line:
                    # Can be 'inet A.B.C.D', or 'inet A.B.C.D/NN'.
                    ipaddr = line.split()[1].split('/')[0]
                    break
            else:
                ipaddr = None

        elif sys.platform == 'darwin':
            ipaddr = '127.0.0.1'

        else:
            ipaddr = None

        # Possibly only need this on MacOS X to deal with older oc
        # versions which didn't use 127.0.0.1 by default.

        if not public_hostname and ipaddr:
            command.append('--public-hostname "%s"' % ipaddr)

        # Use the same IP address for applicaton routes unless an
        # alternative is provided. We use xip.io so can easily map
        # everything back to the same IP. If an alternative hostname was
        # provided, then is up to user to create a wildcard DNS entry
        # that maps to the necessary IP address.

        if routing_suffix is None:
            if ipaddr and ipaddr != '127.0.0.1':
                routing_suffix = 'apps.%s.%s.xip.io' % (profile, ipaddr)
            else:
                routing_suffix = ''

        if routing_suffix:
            command.append('--routing-suffix "%s"' % routing_suffix)

        # Persist configuration between runs. This uses directories
        # mapped from inside of the container.

        command.append('--host-data-dir "%s"' % container_data_dir)
        command.append('--host-config-dir "%s"' % container_config_dir)

        command.append('--use-existing-config')

        # Deal with other command options passed in by user.

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

        if http_proxy:
            command.append('--http-proxy "%s"' % http_proxy)

        if https_proxy:
            command.append('--https-proxy "%s"' % https_proxy)

        if no_proxy:
            for item in no_proxy:
                command.append('--no-proxy "%s"' % item)

        if env:
            for item in env:
                command.append('--env "%s"' % item)

        if ipaddr != '127.0.0.1':
            command.append('--forward-ports=false')

        # Run 'oc cluster up' to start up the instance.

        click.echo(' '.join(command))

        result = execute(' '.join(command))

        if result.returncode != 0:
            click.echo('Failed: The "oc cluster up" command failed.')
            ctx.exit(result.returncode)

        # Save away the command line used for 'oc cluster up' so we can
        # use it for subsequent runs without needing to work out options
        # again, or supply them on the command line. First have to add
        # --public-hostname. Need to only override on subsequent runs,
        # not the first. This is a workaround for broken handling of
        # --public-hostname on MacOS X.

        if public_hostname:
            command.append('--public-hostname "%s"' % public_hostname)

        command = ' '.join(command)

        run_file = os.path.join(profile_dir, 'run')

        with open(run_file, 'w') as fp:
            fp.write(command)

        # Determine version of OpenShift being deployed.

        version_file = os.path.join(profile_dir, 'version')

        origin_version = version or 'unknown'

        try:
            result = execute_and_capture('oc version --request-timeout 1')

            origin_version = result.split('\n')[0].split()[1].split('+')[0]
            with open(version_file, 'w') as fp:
                fp.write(origin_version)

        except subprocess.CalledProcessError as e:
            try:
                origin_version = e.output.split('\n')[0].split()[1].split('+')[0]

                with open(version_file, 'w') as fp:
                    fp.write(origin_version)

            except Exception:
                click.echo('Failed: Unable to determine oc version.')
                ctx.exit(1)

        except Exception as e:
            if origin_version != 'unknown':
                with open(version_file, 'w') as fp:
                    fp.write(origin_version)

            else:
                click.echo('Failed: Unable to determine oc version.')
                ctx.exit(1)

        # Copy scripts into the container to do setup steps.

        script_dir = os.path.join(os.path.dirname(__file__), 'scripts')

        command = []

        command.extend(['docker', 'cp'])
        command.append(script_dir)
        command.append('origin:/var/lib/origin/openshift.local.config')

        result = execute(command)

        if result.returncode != 0: 
            click.echo('Failed: Cannot copy scripts into container.')
            ctx.exit(1)

        # Grant sudoer role to the developer so they do not switch to
        # the admin account. Instead can use user impersonation. We
        # actually rely on this for when creating volumes.

        context = session_context()

        project, cluster, user = context.strip().split('/')

        context = 'default/%s/system:admin' % cluster

        command = ['docker exec origin oc adm policy']

        command.append('add-cluster-role-to-group sudoer system:authenticated')

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to assign sudoer role to developer.')
            ctx.exit(result.returncode)

        # Create an initial set of volumes.

        for n in range(1, max(0, volumes)+1):
            pv = 'pv%02d' % n
            ctx.invoke(command_cluster_volumes_create, name=pv,
                    size=volume_size, reclaim_policy='Recycle')

        # Update the authentication provider.
     
        master_dir = '/var/lib/origin/openshift.local.config/master'

        if identity_provider == 'htpasswd':
            # Initialise the accounts database with default password.

            passwd_file = os.path.join(profile_dir, 'users.htpasswd')

            db = passlib.apache.HtpasswdFile(passwd_file, new=True)
            db.set_password('developer', password)
            db.save()

            command = []

            command.extend(['docker', 'cp'])
            command.append(passwd_file)
            command.append('origin:/var/lib/origin/openshift.local.config/master')

            result = execute(command)

            if result.returncode != 0: 
                click.echo('Failed: Cannot copy htpasswd into container.')
                ctx.exit(1)

            # Now set the identity provider to be htpasswd.

            command = []

            command.append('docker exec -t origin /bin/bash')
            command.append('/var/lib/origin/openshift.local.config/scripts/enable-htpasswd.sh')
            command.append(profile)

            command = ' '.join(command)

            result = execute(command)

            if result.returncode != 0:
                click.echo('Failed: Unable to enable password database.')
                ctx.exit(result.returncode)

        # Enable labels for all built images. We temporarily disable
        # this if using Origin 1.5.X and proxy settings enabled as
        # triggers bug in 'openshift ex config patch'.

        enable_labels = True

        if http_proxy or https_proxy or no_proxy:
            if origin_version.startswith('v1.5.'):
                enable_labels = False

        if enable_labels:
            command = []

            command.append('docker exec -t origin /bin/bash')
            command.append('/var/lib/origin/openshift.local.config/scripts/enable-labels.sh')
            command.append(profile)

            command = ' '.join(command)

            result = execute(command)

            if result.returncode != 0:
                click.echo('Failed: Unable to enable image labels.')
                ctx.exit(result.returncode)

        # Stop the cluster so configuration changes will take effect
        # on the restart below.

        click.echo('Restarting')
        click.echo('Stopping')

        result = execute('oc cluster down')

        if result.returncode != 0:
            click.echo('Failed: The "oc cluster down" command failed.')
            ctx.exit(result.returncode)

    # Start up the OpenShift instance using the saved startup command
    # from when the instance was first created.

    click.echo('Starting')

    run_file = os.path.join(profile_dir, 'run')

    with open(run_file) as fp:
        command = fp.read().strip()

    if env:
        for item in env:
            command += ' --env "%s"' % item

    click.echo(command)

    result = execute(command)

    if result.returncode != 0:
        click.echo('Failed: The "oc cluster up" command failed.')
        ctx.exit(result.returncode)

    if create_profile:
        # Create a context named after the profile to allow for reuse.

        command = ['oc adm config']
        command.append('set-cluster powershift-%s' % profile)

        if public_hostname:
            command.append('--server=https://%s:8443' % public_hostname)
        else:
            command.append('--server=%s' % server_url())

        command.append('--insecure-skip-tls-verify=true')
        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to setup cluster in kubeconfig.')
            ctx.exit(result.returncode)
 
        command = ['oc adm config']
        command.append('set-credentials developer@powershift-%s' % profile)
        command.append('--token=%s' % session_token())
        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to set token for context in kubeconfig.')
            ctx.exit(result.returncode)

        command = ['oc adm config']
        command.append('set-context powershift-%s' % profile)
        command.append('--cluster=powershift-%s' % profile)
        command.append('--user=developer@powershift-%s' % profile)
        command.append('--namespace=myproject')
        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to setup context in kubeconfig.')
            ctx.exit(result.returncode)

    # Switch to context for this profile.

    command = ['oc adm config']
    command.append('use-context powershift-%s' % profile)
    command = ' '.join(command)

    result = execute(command)

    if result.returncode != 0:
        click.echo('Failed: Unable to set context for profile.')
        ctx.exit(result.returncode)

    # Record what the current active profile is.

    activate_profile(ctx, profile)

    click.echo('Started')

@group_cluster.command('down')
@click.pass_context
def command_cluster_down(ctx):
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

    if result.returncode != 0:
        ctx.exit(result.returncode)

@group_cluster.command('destroy')
@click.argument('profile')
@click.pass_context
def command_cluster_destroy(ctx, profile):
    """
    Destroys the named OpenShift cluster.

    If the named OpenShift cluster is currently active, it will be stopped
    before then being detsroyed.

    """
    if profile not in profile_names(ctx):
        click.echo('Invalid: %s' % profile)
        ctx.exit(1)

    click.confirm('Destroy profile "%s"?' % profile, abort=True)

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

    # Now remove any images which were built by the cluster for this
    # profile by using label attached to images.

    click.echo('Cleaning')

    label = 'powershift-profile=%s' % profile

    command = 'docker images --filter label=%s -q' % label

    try:
        images = execute_and_capture(command)

        for image in images.strip().split():
            command = 'docker rmi %s' % image

            result = execute(command)

            if result.returncode != 0: 
                click.echo('Warning: Unable to delete image %s.' % image)

    except Exception:
        click.echo('Warning: Unable to query images for profile.')

    # Now remove any profile directory inside of the container.

    container_profiles_dir = '/var/lib/powershift/profiles'
    container_profile_dir = posixpath.join(container_profiles_dir, profile)

    command = []

    command.append('docker run --rm -v /var:/var busybox rm -rf')
    command.append(container_profile_dir)

    command = ' '.join(command)

    result = execute(command)

    if result.returncode != 0: 
        click.echo('Failed: Cannot delete container profile directory.')

    # Remove the profile directory. There may be a risk this will not
    # completely work if files were created in a volume which had
    # ownership or permissions that prevent removal.

    profiles = ctx.obj['PROFILES']

    directory = os.path.join(profiles, profile)

    click.echo('Removing: %s' % directory)

    shutil.rmtree(directory)

@group_cluster.command('list')
@click.pass_context
def command_cluster_list(ctx):
    """
    List the available OpenShift cluster profiles.

    """

    profiles_dir = ctx.obj['PROFILES']

    current = active_profile(ctx)

    profiles = profile_names(ctx)

    for profile in profiles:
        profile_dir = os.path.join(profiles_dir, profile)
        version_file = os.path.join(profile_dir, 'version')

        if os.path.exists(version_file):
            with open(version_file) as fp:
                label = '%s/%s' % (profile, fp.read().strip())
        else:
            label = profile

        if profile == current:
            click.echo(label + ' (active)')
        else:
            click.echo(label)

@group_cluster.command('status')
@click.pass_context
def command_cluster_status(ctx):
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

    click.echo('Status: Running (%s)' % profile)

@group_cluster.command('ssh')
@click.pass_context
def group_cluster_ssh(ctx):
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

@group_cluster.command('env')
@click.pass_context
@click.option('--shell', default=None,
    help='Force environment to be for specific shell.')
@click.argument('profile', default='default')
def command_cluster_env(ctx, profile, shell):
    """
    Display the commands to set up the environment.

    """

    profiles_dir = ctx.obj['PROFILES']
    profile_dir = os.path.join(profiles_dir, profile)

    version_file = os.path.join(profile_dir, 'version')

    if os.path.exists(version_file):
        with open(version_file) as fp:
            ctx.invoke(command_client_env, version=fp.read().strip(),
                    shell=shell)
    else:
        ctx.invoke(command_client_env, version='unknown', shell=shell)

@group_cluster.group('volumes')
@click.pass_context
def group_cluster_volumes(ctx):
    """
    Manage persistent volumes for the cluster.

    """

    pass

@group_cluster_volumes.command('create')
@click.option('--path', default=None, type=click.Path(resolve_path=True),
    help='Specify a path for the persistent volume')
@click.option('--size', default='10Gi', type=VolumeSize(),
    help='Specify a size for the persistent volume.')
@click.option('--access-mode', multiple=True,
    help='Specify the access mode for the volume.')
@click.option('--reclaim-policy', default='Retain',
    help='Specify the reclaim policy for the volume.')
@click.option('--claim', default=None, type=ClaimRef(),
    help='Assign the persistent volume a claim reference.')
@click.argument('name')
@click.pass_context
def command_cluster_volumes_create(ctx, name, path, size, access_mode,
        reclaim_policy, claim):

    """
    Create a new persistent volume.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    profiles = ctx.obj['PROFILES']

    # Check context object for profile as can be passed in when creating
    # volumes on cluster creation.

    profile = ctx.obj.get('PROFILE') or active_profile(ctx)

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

    container_profiles_dir = '/var/lib/powershift/profiles'
    container_profile_dir = posixpath.join(container_profiles_dir, profile)

    container_volumes_dir = posixpath.join(container_profile_dir, 'volumes')

    if path is None:
        path = posixpath.join(container_profile_dir, 'volumes', name)

        command = []
        
        command.append('docker run --rm -v /var:/var busybox mkdir -p')
        command.append(path)

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0: 
            click.echo('Failed: Cannot create container volume directory.')

        command = []

        command.append('docker run --rm -v /var:/var busybox chmod 0777')
        command.append(path)

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0: 
            click.echo('Failed: Cannot set permissions on volume directory.')

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
            'accessModes': ['ReadWriteOnce', 'ReadWriteMany', 'ReadOnlyMany'],
            'capacity': {'storage': size},
            'hostPath': {'path': container_path(path)},
            'persistentVolumeReclaimPolicy': reclaim_policy,
        }
    }

    if access_mode:
        pv['spec']['accessModes'] = access_mode

    # Add a claim reference if one is provided.

    if claim is not None:
        ref = {
            'kind': 'PersistentVolumeClaim',
            'apiVersion': 'v1',
            'namespace': claim[0],
            'name': claim[1]
        }

        pv['spec']['claimRef'] = ref

    # Create the persistent volume.

    command = 'oc create -f - --as system:admin'

    result = execute_with_input(command, json.dumps(pv))

    if result.returncode != 0:
        click.echo('Failed: Persistent volume creation failed.')
        ctx.exit(result.returncode)

@group_cluster_volumes.command('list')
@click.pass_context
def command_cluster_volumes_list(ctx):
    """
    List the available peristent volumes.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    # Output the details of all persistent volumes.

    result = execute('oc describe pv --as system:admin')

    ctx.exit(result.returncode)

@group_cluster.group('users')
@click.pass_context
def group_cluster_users(ctx):
    """
    Manage accounts database for the cluster.

    """

    pass

@group_cluster_users.command('passwd')
@click.option('--password', prompt=True, hide_input=True,
    confirmation_prompt=True, help='The new password for the user.')
@click.argument('user')
@click.pass_context
def command_cluster_users_passwd(ctx, user, password):
    """
    Change the password for an account.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    profile = active_profile(ctx)

    profiles_dir = ctx.obj['PROFILES']
    profile_dir = os.path.join(profiles_dir, profile)
    passwd_file = os.path.join(profile_dir, 'users.htpasswd')

    if not os.path.exists(passwd_file):
        click.echo('Failed: The password file does not exist.')
        ctx.exit(1)

    db = passlib.apache.HtpasswdFile(passwd_file)

    if db.get_hash(user) is None:
        click.echo('Failed: No such user exists.')
        ctx.exit(1)

    db.set_password(user, password)
    db.save()

    command = []

    command.extend(['docker', 'cp'])
    command.append(passwd_file)
    command.append('origin:/var/lib/origin/openshift.local.config/master')

    result = execute(command)

    if result.returncode != 0: 
        click.echo('Failed: Cannot copy htpasswd into container.')
        ctx.exit(1)

@group_cluster_users.command('add')
@click.option('--password', prompt=True, hide_input=True,
    confirmation_prompt=True, help='The password for the user.')
@click.option('--admin', is_flag=True,
    help='Make the user a system admin.')
@click.argument('user')
@click.pass_context
def command_cluster_users_add(ctx, user, password, admin):
    """
    Adds a new user account.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    profile = active_profile(ctx)

    profiles_dir = ctx.obj['PROFILES']
    profile_dir = os.path.join(profiles_dir, profile)
    passwd_file = os.path.join(profile_dir, 'users.htpasswd')

    if not os.path.exists(passwd_file):
        click.echo('Failed: The password file does not exist.')
        ctx.exit(1)

    db = passlib.apache.HtpasswdFile(passwd_file)

    if db.get_hash(user) is not None:
        click.echo('Failed: User already exists.')
        ctx.exit(1)

    db.set_password(user, password)
    db.save()

    command = []

    command.extend(['docker', 'cp'])
    command.append(passwd_file)
    command.append('origin:/var/lib/origin/openshift.local.config/master')

    result = execute(command)

    if result.returncode != 0: 
        click.echo('Failed: Cannot copy htpasswd into container.')
        ctx.exit(1)

    if admin:
        command = ['oc adm policy']

        command.append('add-cluster-role-to-user cluster-admin %s' % user)
        command.append('--as system:admin')

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to make user a system admin.')
            ctx.exit(result.returncode)

@group_cluster_users.command('remove')
@click.argument('user')
@click.pass_context
def command_cluster_users_remove(ctx, user):
    """
    Removes a user account.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

    profile = active_profile(ctx)

    profiles_dir = ctx.obj['PROFILES']
    profile_dir = os.path.join(profiles_dir, profile)
    passwd_file = os.path.join(profile_dir, 'users.htpasswd')

    if not os.path.exists(passwd_file):
        click.echo('Failed: The password file does not exist.')
        ctx.exit(1)

    if user == 'developer':
        click.echo('Failed: Cannot remove developer account.')
        ctx.exit(1)

    click.confirm('Remove user "%s"?' % user, abort=True)

    db = passlib.apache.HtpasswdFile(passwd_file)

    if db.get_hash(user) is None:
        click.echo('Failed: User does not exist.')
        ctx.exit(1)

    db.delete(user)
    db.save()

    command = []

    command.extend(['docker', 'cp'])
    command.append(passwd_file)
    command.append('origin:/var/lib/origin/openshift.local.config/master')

    result = execute(command)

    if result.returncode != 0: 
        click.echo('Failed: Cannot copy htpasswd into container.')
        ctx.exit(1)

@group_cluster_users.command('list')
@click.pass_context
def command_cluster_users_list(ctx):
    """
    List active user accounts.

    """

    if not cluster_running():
        ctx.exit(1)

    profile = active_profile(ctx)

    profiles_dir = ctx.obj['PROFILES']
    profile_dir = os.path.join(profiles_dir, profile)
    passwd_file = os.path.join(profile_dir, 'users.htpasswd')

    if not os.path.exists(passwd_file):
        ctx.exit(1)

    db = passlib.apache.HtpasswdFile(passwd_file)

    for user in db.users():
        click.echo(user)
