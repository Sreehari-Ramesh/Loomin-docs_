import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "is", "are", "on", "with", "that", "this", "it", "as",
    "be", "by", "at", "from", "if", "not", "do", "does", "can", "will", "about"
}


@dataclass
class TestCase:
    question: str
    must_include: list[str]
    max_hallucination_ratio: float = 0.35


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def load_cases(path: Path) -> list[TestCase]:
    cases: list[TestCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        cases.append(
            TestCase(
                question=payload["question"],
                must_include=payload.get("must_include", []),
                max_hallucination_ratio=float(payload.get("max_hallucination_ratio", 0.35)),
            )
        )
    return cases


def hallucination_ratio(answer: str, question: str, citations: list[dict[str, Any]]) -> float:
    answer_terms = tokenize(answer)
    if not answer_terms:
        return 0.0

    source_text = question + "\n" + "\n".join(c.get("snippet", "") for c in citations)
    source_terms = tokenize(source_text)

    unsupported = [t for t in answer_terms if t not in source_terms]
    return len(unsupported) / max(1, len(answer_terms))


def run(base_url: str, cases_path: Path) -> int:
    cases = load_cases(cases_path)
    passed = 0

    for case in cases:
        response = requests.post(
            f"{base_url}/chat",
            json={"message": case.question, "top_k": 4, "document_content": ""},
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        answer = data.get("answer", "")
        answer_l = answer.lower()
        citations = data.get("citations", [])

        includes_required = all(token.lower() in answer_l for token in case.must_include)
        has_citations = len(citations) > 0
        ratio = hallucination_ratio(answer, case.question, citations)
        faithful_enough = ratio <= case.max_hallucination_ratio

        ok = includes_required and has_citations and faithful_enough
        passed += int(ok)

        print(
            json.dumps(
                {
                    "question": case.question,
                    "pass": ok,
                    "request_id": data.get("request_id"),
                    "citation_count": len(citations),
                    "hallucination_ratio": round(ratio, 3),
                    "max_allowed": case.max_hallucination_ratio,
                }
            )
        )

    print(f"Faithfulness: {passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cases", default="tests/faithfulness_cases.jsonl")
    args = parser.parse_args()
    raise SystemExit(run(args.base_url, Path(args.cases)))
