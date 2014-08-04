class RepositoryInfo(object):
    """
    Repository information
    """
    def __init__(self, image):
        if ':' in image:
            repository, tag = image.split(':', 1)
        else:
            repository = image
            tag = 'latest'

        if '/' in repository:
            namespace, name = repository.split('/', 1)
        else:
            name = repository
            namespace = None

        self.name = name
        self.repository = repository
        self.namespace = namespace
        self.tag = tag

    def __str__(self):
        return '%s:%s' % (self.repository, self.tag)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self)
