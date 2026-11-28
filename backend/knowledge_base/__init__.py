"""Enterprise knowledge store: business rules, metric definitions and
few-shot examples, owned and approved by the institution (not by the model).
"""

from backend.knowledge_base.store import InMemoryKnowledgeBase, load_knowledge_base

__all__ = ["InMemoryKnowledgeBase", "load_knowledge_base"]
