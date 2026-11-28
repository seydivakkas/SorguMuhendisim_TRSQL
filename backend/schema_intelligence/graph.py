from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from backend.core.contracts import JoinStep, SchemaSnapshot


class SchemaGraph:
    """Undirected PK/FK graph view over a (scoped) :class:`SchemaSnapshot`."""

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

    def has_table(self, table: str) -> bool:
        return table.lower() in self._adj

    def neighbors(self, table: str) -> tuple[str, ...]:
        steps = self._adj.get(table.lower(), [])
        return tuple(dict.fromkeys(step.right_table for step in steps))

    def neighborhood(self, tables: Iterable[str], hops: int = 1) -> tuple[str, ...]:
        """Return tables within ``hops`` FK edges of ``tables`` (deterministic BFS)."""
        if hops < 0:
            raise ValueError("hops must be non-negative")
        seeds = [t.lower() for t in tables if t.lower() in self._adj]
        if not seeds:
            return ()
        seen: dict[str, None] = dict.fromkeys(seeds)
        queue: deque[tuple[str, int]] = deque((s, 0) for s in seen)
        while queue:
            node, depth = queue.popleft()
            if depth >= hops:
                continue
            for nxt in sorted(self.neighbors(node)):
                if nxt not in seen:
                    seen[nxt] = None
                    queue.append((nxt, depth + 1))
        return tuple(seen.keys())

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
        first = tables[0].lower()
        if first not in self._adj:
            return None
        tree = {first}
        steps: list[JoinStep] = []
        for table in tables[1:]:
            t = table.lower()
            if t not in self._adj:
                return None
            if t in tree:
                continue
            best: tuple[JoinStep, ...] | None = None
            for node in sorted(tree):
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

    def connected_tables(self, tables: tuple[str, ...]) -> tuple[str, ...] | None:
        """Return all tables (including intermediate Steiner bridge tables)
        needed to join ``tables``, or ``None`` if disconnected."""
        if not tables:
            return ()
        steps = self.connect(tables)
        if steps is None:
            return None
        ordered: dict[str, None] = {}
        for t in tables:
            ordered[t.lower()] = None
        for step in steps:
            ordered[step.left_table.lower()] = None
            ordered[step.right_table.lower()] = None
        return tuple(ordered.keys())
