from setuptools import Distribution, setup


class BinaryDistribution(Distribution):
    """Tag the wheel for the CPython/platform-specific live bridge it contains."""

    def has_ext_modules(self) -> bool:
        return True


setup(distclass=BinaryDistribution)
