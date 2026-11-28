from __future__ import annotations

from collections import deque

from backend.core.contracts import JoinStep, SchemaSnapshot


class SchemaGraph:
    def __init__(self, schema: SchemaSnapshot) -> None:
        self._adj: dict[str, list[JoinStep]] = {t.name.lower(): [] for t in schema.tables}
        for table in schema.tables:
            left = table.name.lower()
            for fk in table.foreign_keys:
                right = fk.ref_table.lower()
                if right not in self._adj:
                    continue
                self._adj[left].append(JoinStep(
                    left_table=left, left_column=fk.column,
                    right_table=right, right_column=fk.ref_column,
                ))  # fmt: skip
                self._adj[right].append(JoinStep(
                    left_table=right, left_column=fk.ref_column,
                    right_table=left, right_column=fk.column,
                ))  # fmt: skip

    def shortest_path(self, source: str, target: str) -> tuple[JoinStep, ...] | None:
        source, target = source.lower(), target.lower()
        if source not in self._adj or target not in self._adj:
            return None
        if source == target:
            return ()
        prev: dict[str, JoinStep] = {}
        queue = deque([source])
        seen = {source}
        while queue:
            node = queue.popleft()
            for step in self._adj[node]:
                nxt = step.right_table
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = step
                if nxt == target:
                    path: list[JoinStep] = []
                    cur = target
                    while cur != source:
                        path.append(prev[cur])
                        cur = prev[cur].left_table
                    return tuple(reversed(path))
                queue.append(nxt)
        return None

    def connect(self, tables: tuple[str, ...]) -> tuple[JoinStep, ...] | None:
        """Greedy Steiner approximation: attach each table to the tree so far
        via its shortest path. Returns ``None`` if the tables are disconnected."""
        if not tables:
            return ()
        tree = {tables[0].lower()}
        steps: list[JoinStep] = []
        for table in tables[1:]:
            t = table.lower()
            if t in tree:
                continue
            best: tuple[JoinStep, ...] | None = None
            for node in tree:
                path = self.shortest_path(node, t)
                if path is not None and (best is None or len(path) < len(best)):
                    best = path
            if best is None:
                return None
            for step in best:
                if step.right_table not in tree:
                    steps.append(step)
                    tree.add(step.right_table)
        return tuple(steps)
