import agent_lab.agents.repo_pilot
import agent_lab.core


def test_packages_import():
    assert agent_lab.core is not None
    assert agent_lab.agents.repo_pilot is not None