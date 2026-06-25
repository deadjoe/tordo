from .bridge import AbletonAgentBridge


def create_instance(c_instance):
    return AbletonAgentBridge(c_instance)
