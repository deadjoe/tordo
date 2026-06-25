from .bridge import TordoBridge


def create_instance(c_instance):
    return TordoBridge(c_instance)
