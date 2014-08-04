from .docker import RepositoryInfo
from os import path
import yaml

class Template(object):
    def __init__(self, filename):
        with open(filename) as f:
            self.__dict__ = yaml.load(f)

        self.base = RepositoryInfo(self.base)
        self.filename = filename
        self.base_dir = path.dirname(filename)
        self.name = path.basename(self.base_dir)
        self.image = RepositoryInfo(self['repository'])

    @classmethod
    def parse_name(cls, image_name):        
        return path.basename(image_name)

    def get(self, name, default=None):
        return self.__dict__.get(name, default)

    def __getitem__(self, name):
        return self.__dict__.get(name, None)

class TemplateManager(object):
    """
    Handle loading and caching docker dockbuilds
    """
    def __init__(self, template_dir):
        self.template_dir = template_dir
        self._templates = {}

    def get_by_image(self, image_name):
        """
        Get by image name
        """
        template_name = Template.parse_name(image_name)
        return self.get_by_name(template_name)

    def get_by_name(self, template_name):
        """
        Get by template name
        """
        if template_name not in self._templates:
            filename = path.join(self.template_dir, template_name, 'dockbuild.yml')
            if path.exists(filename):
                self._templates[template_name] = Template(filename)
            else:
                return None

        return self._templates[template_name]

    def get_dependent_images(self, template_name):
        """
        Return a list of all the images this template depends on
        """
        template = self.get_by_name(template_name)
        if not template:
            return

        dependencies = []
        if template.base:
            dependencies.append(template.base)

            base_template_name = Template.parse_name(template.base.repository)
            if base_template_name:
                base = self.get_dependent_images(base_template_name)
                if base:
                    dependencies.extend(base)

        return dependencies