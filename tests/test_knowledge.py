from harvestops.domain import User
from harvestops.knowledge import KnowledgeService


def test_local_search_is_permission_filtered():
    service = KnowledgeService()
    viewer = User("viewer", "Viewer", {"viewer"})
    approver = User("approver", "Approver", {"approver"})
    assert service.search("purchase approval", viewer) == []
    assert service.search("purchase approval", approver)[0].source == "knowledge/purchasing.md"


def test_claude_mode_is_graceful_without_credentials():
    result = KnowledgeService().answer_with_claude("What is fill rate?", KnowledgeService().search("fill rate", User("v", "Viewer", {"viewer"})))
    assert result["status"] == "unavailable"
    assert "Local search" in result["message"]
