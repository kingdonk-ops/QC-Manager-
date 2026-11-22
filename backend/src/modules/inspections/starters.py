"""Starter checklists for insulation, cladding, refractory and coatings work, seeded per project."""

from typing import Any


def _pf(text: str, guidance: str | None = None, photo: bool = True) -> dict[str, Any]:
    return {"text": text, "response_type": "pass_fail", "requires_photo_on_fail": photo, "guidance": guidance}


def _num(
    text: str, unit: str, lo: float | None, hi: float | None, guidance: str | None = None, photo: bool = True
) -> dict[str, Any]:
    return {
        "text": text,
        "response_type": "numeric",
        "unit": unit,
        "min_value": lo,
        "max_value": hi,
        "requires_photo_on_fail": photo,
        "guidance": guidance,
    }


STARTERS: list[dict[str, Any]] = [
    {
        "name": "Pipe insulation & cladding",
        "trade": "Insulation",
        "activity": "Hot/cold pipe insulation with metal cladding",
        "description": "Hold-point checklist for pipework insulation and aluminium or stainless cladding.",
        "sections": [
            {
                "title": "Preparation",
                "items": [
                    _pf("Surface clean, dry and released for insulation", "Pressure test and coating sign-off in place"),
                    _pf("Correct insulation material and grade per spec", "Check delivery note / data sheet", photo=False),
                    _num("Ambient temperature at installation", "°C", 5, 45, photo=False),
                ],
            },
            {
                "title": "Insulation",
                "items": [
                    _num("Insulation thickness", "mm", 50, 55, "Measure at three points; record the lowest"),
                    _pf("Joints staggered and tightly butted, no gaps"),
                    _pf("Bands / wires at specified spacing"),
                    _pf("Vapour barrier continuous and sealed (cold service)"),
                ],
            },
            {
                "title": "Cladding",
                "items": [
                    _num("Cladding overlap", "mm", 50, None, "Circumferential and longitudinal laps"),
                    _pf("Laps shed water (oriented downhill / away from weather)"),
                    _pf("Screws / rivets at specified pitch, no damage to insulation"),
                    _pf("Penetrations, flanges and supports sealed"),
                    _pf("Finish free of dents, sharp edges and scratches"),
                ],
            },
        ],
    },
    {
        "name": "Refractory lining",
        "trade": "Refractory",
        "activity": "Castable / gunned refractory installation",
        "description": "Anchors, mixing, placement and curing checks for monolithic refractory linings.",
        "sections": [
            {
                "title": "Anchors & preparation",
                "items": [
                    _pf("Anchor type and material per drawing"),
                    _num("Anchor spacing", "mm", 150, 300, "Centre to centre"),
                    _pf("Anchor weld test (hammer / bend) passed"),
                    _pf("Anchor tips coated / capped where specified", photo=False),
                    _pf("Shell clean and free of oil, scale and moisture"),
                ],
            },
            {
                "title": "Mixing & placement",
                "items": [
                    _pf("Material batch within shelf life", "Record batch numbers in notes", photo=False),
                    _num("Mixing water temperature", "°C", 5, 25, photo=False),
                    _num("Water addition", "%", 6, 9, "Per manufacturer's data sheet", photo=False),
                    _num("Lining thickness", "mm", 100, 110),
                    _pf("Expansion joints installed per drawing"),
                ],
            },
            {
                "title": "Curing",
                "items": [
                    _num("Curing time before dry-out", "h", 24, None, photo=False),
                    _pf("Surface free of cracks, voids and laminations"),
                    _pf("Test panels / cubes taken and labelled", photo=False),
                ],
            },
        ],
    },
    {
        "name": "Protective coating DFT",
        "trade": "Coatings",
        "activity": "Protective coating application and dry film thickness",
        "description": "Surface preparation, ambient conditions and DFT readings per coat.",
        "sections": [
            {
                "title": "Surface preparation",
                "items": [
                    _pf("Abrasive blast to Sa 2½ (ISO 8501-1)", "Compare with visual standard"),
                    _num("Surface profile", "µm", 50, 75, "Replica tape or profile gauge"),
                    _num("Soluble salts", "mg/m²", None, 20, photo=False),
                    _pf("Dust level ≤ 2 (ISO 8502-3)"),
                ],
            },
            {
                "title": "Ambient conditions",
                "items": [
                    _num("Relative humidity", "%", None, 85, photo=False),
                    _num("Steel temperature above dew point", "°C", 3, None, photo=False),
                ],
            },
            {
                "title": "Application & DFT",
                "items": [
                    _pf("Coating product and batch per spec", photo=False),
                    _num("Primer DFT", "µm", 60, 100),
                    _num("Intermediate DFT", "µm", 120, 180),
                    _num("Total system DFT", "µm", 250, 350, "Average of spot readings per 10 m²"),
                    _pf("Finish free of runs, sags, pinholes and holidays"),
                    _pf("Holiday test passed (where specified)"),
                ],
            },
        ],
    },
]
