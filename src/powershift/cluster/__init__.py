from __future__ import print_function

import os
import sys
import shutil
import shlex
import subprocess
import re
import posixpath
import tempfile

from glob import glob

import docker
import click

import requests.packages.urllib3
requests.packages.urllib3.disable_warnings()

from ..cli import root, server_url, server_context, server_token

from .. import resources
from .. import endpoints

if sys.platform == 'win32':
    SAVEDIR='PowerShift'
else:
    SAVEDIR='.powershift'

DEFAULT_ROOTDIR = os.path.expanduser(os.path.join('~', SAVEDIR))
ROOTDIR = os.environ.get('POWERSHIFT_HOME_DIR', DEFAULT_ROOTDIR)

DEFAULT_PROFILES = os.path.join(ROOTDIR, 'profiles')
PROFILES = os.environ.get('POWERSHIFT_PROFILES_DIR', DEFAULT_PROFILES)

def execute(command):
    return subprocess.run(shlex.split(command))

def execute_and_capture(command):
    return subprocess.check_output(shlex.split(command),
            universal_newlines=True)

def active_instance():
    try:
        client = docker.from_env()
        instance = client.containers.get('origin')
        if instance.status == 'running':
            return instance

    except docker.errors.NotFound:
        pass

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

    ctx.obj['ROOTDIR'] = ROOTDIR
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
@click.option('--server-loglevel', default=0, type=int,
    help='Log level for the OpenShift server.')
@click.argument('profile', default='default')
@click.pass_context
def up(ctx, profile, image, version, routing_suffix, logging, metrics,
        server_loglevel):

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

    root_dir = ctx.obj['ROOTDIR']
    profiles_dir = ctx.obj['PROFILES']

    try:
        os.mkdir(root_dir)
        os.mkdir(profiles_dir)

    except IOError:
        pass

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

        if sys.platform == 'linux':
            ipaddr = execute_and_capture('which-ip docker0')
        else:
            ipaddr = '127.0.0.1'

        if routing_suffix is None:
            if ipaddr != '127.0.0.1':
                routing_suffix = 'apps.%s.%s.xip.io' % (profile, ipaddr)
            else:
                routing_suffix = ''

        command = ['oc cluster up']

        command.append('--public-hostname "%s"' % ipaddr)
        command.append('--host-data-dir "%s"' % data_dir)
        command.append('--host-config-dir "%s"' % config_dir)
        command.append('--routing-suffix "%s"' % routing_suffix)
        command.append('--use-existing-config')

        if image:
            command.append('--image "%s"' % image)

        if version:
            command.append('--version "%s"' % version)

        if logging:
            command.append('--logging')

        if metrics:
            command.append('--metrics')

        command.append('--server-loglevel %d' % server_loglevel)

        if ipaddr != '127.0.0.1':
            command.append('--forward-ports=false')

        command = ' '.join(command)

        run_file = os.path.join(profile_dir, 'run')

        with open(run_file, 'w') as fp:
            fp.write(command)

        click.echo(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: The "oc cluster up" command failed.')
            ctx.exit(result.returncode)

        context = server_context()

        project, cluster, user = context.strip().split('/')

        context = 'default/%s/system:admin' % cluster

        command = ['oc adm policy']

        command.append('add-cluster-role-to-group sudoer system:authenticated')
        command.append('--config "%s/master/admin.kubeconfig"' % config_dir)
        command.append('--context "%s"' % context)

        command = ' '.join(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: Unable to assign sudoer role to developer.')
            ctx.exit(result.returncode)

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

        run_file = os.path.join(profile_dir, 'run')

        with open(run_file) as fp:
            command = fp.read().strip()

        click.echo(command)

        result = execute(command)

        if result.returncode != 0:
            click.echo('Failed: The "oc cluster up" command failed.')
            ctx.exit(result.returncode)

    activate_profile(ctx, profile)

    click.echo('Started')

@cluster.command()
@click.pass_context
def down(ctx):
    """
    Stops the active OpenShift cluster.

    """

    instance = active_instance()

    if instance is None or instance.status != 'running':
        click.echo('Stopped')
        ctx.exit(1)

    click.echo('Stopping')

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
            print(profile + ' (active)')
        else:
            print(profile)

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

    image = instance.attrs['Config']['Image']
    built = instance.attrs['Config']['Labels']['build-date']

    click.echo('Status: Running')
    click.echo('Profile Name: %s' % profile)
    click.echo('OpenShift Image: %s' % image)
    click.echo('Build Date: %s' % built)

@cluster.command()
@click.pass_context
def ssh(ctx):
    """
    Opens a shell session in the OpenShift master node.

    """

    if not cluster_running():
        click.echo('Stopped')
        ctx.exit(1)

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

    server = server_url()
    token = server_token()

    client = endpoints.Client(server, token, user='system:admin', verify=False)

    try:
        pv = client.api.v1.persistentvolumes(name=name).get()
    except Exception:
        pass
    else:
        click.echo('Failed: Persistent volume name already in use.')
        ctx.exit(1)

    if path is None:
        path = posixpath.join(profiles, profile, 'volumes', name)

    os.makedirs(path, exist_ok=True)

    os.chmod(path, 0o777)

    pv = resources.v1_PersistentVolume(
        metadata=resources.v1_ObjectMeta(name=name),
        spec=resources.v1_PersistentVolumeSpec(
            capacity=resources.Resource(storage=size),
            host_path=resources.v1_HostPathVolumeSource(path=path),
            access_modes=['ReadWriteOnce','ReadWriteMany'],
            persistent_volume_reclaim_policy='Retain'
        )
    )

    if claim is not None:
        ref = resources.v1_ObjectReference(
            kind='PersistentVolumeClaim',
            namespace=claim[0],
            name=claim[1]
        )

        pv.spec.claim_ref = ref

    client.api.v1.persistentvolumes.post(body=pv)

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

    result = execute('oc describe pv --as system:admin')

    ctx.exit(result.returncode)
