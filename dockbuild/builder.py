from __future__ import absolute_import
from .template import TemplateManager
from docker import Client
from docker.client import APIError
import json
import tempfile
from os import path
import os
from datetime import datetime

class DockBuilder(object):
    def __init__(self, template_dir, docker_host=None, shared_dir_map=None):
        """
        :param template_dir: Base directory for dockbuild templates
        """
        self.template_dir = path.abspath(path.expanduser(template_dir))
        self.templates = TemplateManager(self.template_dir)
        self.shared_dir_map = shared_dir_map
        self._docker = Client(base_url=docker_host)

    def _get_image_id(self, repo):
        images = self._docker.images(repo.repository)
        repo_str = str(repo)
        if images:
            for i in images:                
                if repo_str in i.get('RepoTags', ''):
                    return i['Id']                

    def build(self, template_name, output=None):
        dockbuild = self.templates.get_by_name(template_name)
        if not dockbuild:
            raise Exception('Could not find template %s' % template_name)

        dependencies = self.templates.get_dependent_images(dockbuild.name)
        if dependencies:
            # Make sure base images exist
            missing_images = [
                base_image
                for base_image in reversed(dependencies)
                if not self._get_image_id(base_image)
            ]

            if missing_images:
                raise Exception('Can not find base images %s' % ', '.join(map(str, missing_images)))
                # if confirm('Could not find %s; would you like to build now?' % ', '.join(map(str, missing_images))):
                #     for base_image in missing_images:
                #         _build(templates.get_by_image(base_image.repository))
                # else:
                #     abort('Aborted by user')

        self._build(dockbuild, output)

    def _build(self, dockbuild, output):
        if output:
            wrapped = output
            def output(**kwargs):
                wrapped(template_name=dockbuild.name, **kwargs)
        else:
            output = lambda **_: None


        base = dockbuild['base']

        temp_dir = path.join(dockbuild.base_dir, '.dockbuilder')

        build_volumes = {
            dockbuild.base_dir: '/dockbuild',
        }

        for volume in dockbuild.get('build_volumes', []):
            s, d = volume.split(':', 1)
            build_volumes[s] = d

        run_command = None

        if dockbuild.get('scripts') or dockbuild.get('files') or dockbuild.get('directories'):            
            build_volumes[temp_dir] = '/dockbuilder'

            script_dir = path.join(temp_dir, dockbuild.name)
            if not path.exists(script_dir):
                os.makedirs(script_dir)

            with open(path.join(script_dir, 'build.sh'), 'w') as run_script:
                run_script.write('#!/bin/bash\n')
                run_script.write('set -e\n')
                run_script.write('sleep 1\n')
                run_script.write('export BUILD_DIR=/dockbuilder\n')

                def write_header(msg, line='='):
                    msg = '  ' + msg + '  '
                    run_script.write('echo "%s"\n' % (line * len(msg)))
                    run_script.write('echo "%s"\n' % msg)
                    run_script.write('echo "%s"\n' % (line * len(msg)))

                for dirspec in dockbuild.get('directories', []):
                    if isinstance(dirspec, basestring):
                        source, destination = dirspec.split(':', 1)
                        dirspec = {
                            'source': source,
                            'destination': destination,
                        }

                    write_header('Copying directory {source} to {destination}...'.format(**dirspec))
                    run_script.write('mkdir -p {destination_dir}\n'.format(
                        destination_dir=path.dirname(dirspec['destination']))
                    )
                    run_script.write('cp -Rv /dockbuild/{source}/* {destination}\n'.format(**dirspec))

                for filespec in dockbuild.get('files', []):
                    if isinstance(filespec, basestring):
                        source, destination = filespec.split(':', 1)
                        filespec = {
                            'source': source,
                            'destination': destination,
                        }

                    write_header('Copying file {source} to {destination}...'.format(**filespec))
                    run_script.write('mkdir -p {destination_dir}\n'.format(
                        destination_dir=path.dirname(filespec['destination']))
                    )
                    run_script.write('cp /dockbuild/{source} {destination}\n'.format(**filespec))
                    if filespec.get('mode'):
                        run_script.write('chmod {mode} {destination}\n'.format(**filespec))

                for script in dockbuild.get('scripts', []):
                    write_header('Running %s...' % script)
                    run_script.write('source /dockbuild/%s\n' % script)

                write_header('Scripts Done.', 'x')

            os.chmod(path.join(script_dir, 'build.sh'), 0755)

            run_command = '/dockbuilder/%s/build.sh' % dockbuild.name

        try:
            # if dockbuild.get('pre'):
            #     header('Executing preflight scripts...')
            #     for script in dockbuild['pre']:
            #         script = path.join(dockbuild.base_dir, script)
            #         with shell_env(BUILD_DIR=temp_dir):
            #             local(script, capture=False)

            container_name = 'dockbuild-%s' % dockbuild.name
            output(type='info', message='Starting container...')

            if self.shared_dir_map:
                # Re-write src for shared paths
                new_build_volumes = {}
                for src, dst in build_volumes.iteritems():
                    for f, t in self.shared_dir_map.iteritems():
                        if src[:len(f)] == f:
                            src = t + src[len(f) - 1:]
                            break
                    new_build_volumes[src] = dst
                build_volumes = new_build_volumes            


            # Find existing container
            try:
                self._docker.remove_container(container_name, v=True)
            except APIError as e:
                if e.response.status_code == 404:
                    # Ignore, container didn't exit
                    pass
                else:
                    raise

            # Create build container
            container_id = self._docker.create_container(
                image=str(base),
                command=run_command,
                volumes=build_volumes.values(),
                name=container_name
            )['Id']            

            container = self._docker.inspect_container(container_id)
            
            self._docker.start(container_id, binds=build_volumes)

            container = self._docker.inspect_container(container_id)
            
            for chunk in self._docker.attach(container_id, stream=True):
                output(type='stdout', message=chunk.rstrip())

            container = self._docker.inspect_container(container_id)
            if container['State']['ExitCode'] != 0:
                raise Exception('Build failed')

            output(type='info', message='Saving container state...')
            image_id = self._docker.commit(container_id)['Id']

            # Create new container that will have final settings
            self._docker.remove_container(container_name, v=True)
            container_id = self._docker.create_container(
                image=image_id,
                command=dockbuild.get('cmd'),
                volumes=dockbuild.get('volumes'),
                name=container_name
            )['Id']            
           
            container = self._docker.inspect_container(container_id)
            print json.dumps(container, indent=2)


            output(type='info', message='Committing container...')
            self._docker.commit(container_id, repository=dockbuild['repository'], tag='latest')

            for tag in dockbuild['tags']:
                tag = tag.format(today=datetime.now().strftime('%Y%m%d'))
                self._docker.tag(dockbuild['repository'] + ':latest', dockbuild['repository'], tag)

            self._docker.remove_container(container_id, v=True)

            output(type='info', message='Done')

        except KeyboardInterrupt:            
            if container_id:
                self._docker.kill(container_id)