from setuptools import setup, find_packages

setup(
    name = 'dockbuild',
    version = '0.1.0',
    packages = find_packages(),
    install_requires = [
        'docker-py>=0.3.1,<0.4',
        'PyYaml'
    ],
    author = 'Mike Thornton',
    author_email = 'six8@devdetails.com',
    description = 'Build docker containers with Python',
    license = 'MIT',
    url='https://github.com/six8/dockbuild'
)