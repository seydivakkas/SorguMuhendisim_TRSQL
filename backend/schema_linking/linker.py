from __future__ import annotations

from collections.abc import Mapping

from backend.core.contracts import (
    LinkedSchema,
    MentionKind,
    ParsedQuestion,
    SchemaLink,
    SchemaSnapshot,
)
from backend.schema_intelligence import SchemaGraph


class LexiconSchemaLinker:
    """Links mentions through a curated lexicon.

    ``lexicon`` maps a Turkish lemma to ``"table"`` or ``"table.column"``.
    Entries that point at tables or columns absent from the scoped schema are
    ignored, so the linker can never reveal a hidden object.
    """

    def __init__(self, lexicon: Mapping[str, str]) -> None:
        self._lexicon = dict(lexicon)

    def link(self, question: ParsedQuestion, schema: SchemaSnapshot) -> LinkedSchema:
        links: list[SchemaLink] = []
        for mention in question.mentions:
            key = mention.lemma or mention.text
            if mention.kind is MentionKind.LOCATION:
                key = "__location__"
            target = self._lexicon.get(key)
            if target is None:
                continue
            table, _, column = target.partition(".")
            info = schema.table(table)
            if info is None or (column and info.column(column) is None):
                continue
            links.append(SchemaLink(
                mention=mention.text, table=info.name, column=column or None, score=1.0,
            ))  # fmt: skip

        tables = tuple(dict.fromkeys(link.table for link in links))
        join_path = SchemaGraph(schema).connect(tables) or ()
        return LinkedSchema(tables=tables, links=tuple(links), join_path=join_path)
