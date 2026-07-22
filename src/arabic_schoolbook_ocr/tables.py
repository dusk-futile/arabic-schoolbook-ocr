from __future__ import annotations

from itertools import pairwise
from statistics import median

from .schemas import BoundingBox, OcrLine, TableCell, TableData


def _cluster_values(values: list[tuple[float, OcrLine]], threshold: float) -> list[list[OcrLine]]:
    clusters: list[tuple[list[float], list[OcrLine]]] = []
    for value, line in sorted(values, key=lambda item: item[0]):
        if not clusters or value - (sum(clusters[-1][0]) / len(clusters[-1][0])) > threshold:
            clusters.append(([value], [line]))
        else:
            clusters[-1][0].append(value)
            clusters[-1][1].append(line)
    return [lines for _, lines in clusters]


def _column_clusters(lines: list[OcrLine], table_bbox: BoundingBox) -> list[list[OcrLine]]:
    clusters = _cluster_values(
        [(line.bbox.x + line.bbox.width / 2, line) for line in lines],
        max(table_bbox.width * 0.14, 40.0),
    )
    return sorted(
        clusters,
        key=lambda cluster: (
            sum(line.bbox.x + line.bbox.width / 2 for line in cluster) / len(cluster)
        ),
        reverse=True,
    )


def _row_clusters(lines: list[OcrLine]) -> list[list[OcrLine]]:
    typical_height = median(line.bbox.height for line in lines)
    initial = _cluster_values(
        [(line.bbox.y + line.bbox.height / 2, line) for line in lines],
        max(typical_height * 0.8, 18.0),
    )
    if len(initial) < 2:
        return initial
    row_centers = [
        sum(line.bbox.y + line.bbox.height / 2 for line in cluster) / len(cluster)
        for cluster in initial
    ]
    gaps = [after - before for before, after in pairwise(row_centers)]
    typical_gap = median(gaps) if gaps else typical_height * 2
    merged: list[list[OcrLine]] = []
    merged_centers: list[float] = []
    for cluster, center in zip(initial, row_centers, strict=True):
        if merged and len(cluster) == 1 and len(merged[-1]) >= 2:
            if center - merged_centers[-1] < max(typical_gap * 0.72, typical_height * 1.7):
                merged[-1].extend(cluster)
                continue
        merged.append(cluster)
        merged_centers.append(center)
    return merged


def infer_table_data(lines: list[OcrLine], table_bbox: BoundingBox) -> TableData | None:
    """Infer a conservative RTL row/column grid from OCR line centers."""

    usable = [line for line in lines if line.text.strip()]
    if len(usable) < 4:
        return None
    columns = _column_clusters(usable, table_bbox)
    rows = _row_clusters(usable)
    if len(columns) < 2 or len(rows) < 2:
        return None

    column_centers = [
        sum(line.bbox.x + line.bbox.width / 2 for line in cluster) / len(cluster)
        for cluster in columns
    ]
    cells: list[TableCell] = []
    for row_index, row_lines in enumerate(rows):
        by_column: dict[int, list[OcrLine]] = {}
        for line in row_lines:
            center = line.bbox.x + line.bbox.width / 2
            column_index = min(
                range(len(column_centers)), key=lambda index: abs(center - column_centers[index])
            )
            by_column.setdefault(column_index, []).append(line)
        for column_index, cell_lines in by_column.items():
            ordered = sorted(cell_lines, key=lambda line: (line.bbox.y, -line.bbox.x))
            cells.append(
                TableCell(
                    row=row_index,
                    column=column_index,
                    text="\n".join(line.text for line in ordered),
                )
            )
    return TableData(rows=len(rows), columns=len(columns), cells=cells)
