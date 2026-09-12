from __future__ import annotations

import json
from pathlib import Path

from app.enrichment import DocumentEnrichmentRequest, EnrichmentError, LlmDocumentEnricher


def main() -> None:
    cases_path = Path("evaluation/document_cases.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    enricher = LlmDocumentEnricher()

    total = len(cases)
    type_matches = 0
    field_checks = 0
    field_matches = 0
    review_count = 0
    failures = 0

    for case in cases:
        try:
            result = enricher.enrich(DocumentEnrichmentRequest(text=case["text"]))
        except EnrichmentError as exc:
            failures += 1
            print(f"FAIL {case['id']}: {exc}")
            continue

        if result.document_type == case["expected_document_type"]:
            type_matches += 1

        required_fields = case.get("required_fields", [])
        field_checks += len(required_fields)
        field_matches += sum(
            1 for field in required_fields if result.extracted_fields.get(field) not in (None, "")
        )

        if result.requires_human_review:
            review_count += 1

        print(
            f"{case['id']}: type={result.document_type} "
            f"confidence={result.confidence:.2f} review={result.requires_human_review}"
        )

    completed = total - failures
    print("\nEvaluation summary")
    print(f"cases={total} completed={completed} failures={failures}")
    print(f"document_type_accuracy={type_matches / total:.2%}" if total else "document_type_accuracy=n/a")
    if field_checks:
        print(f"required_field_recall={field_matches / field_checks:.2%}")
    else:
        print("required_field_recall=n/a")
    print(f"human_review_rate={review_count / completed:.2%}" if completed else "human_review_rate=n/a")


if __name__ == "__main__":
    main()
