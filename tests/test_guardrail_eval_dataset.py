import pathlib
import pytest
from scripts.validate_guardrail_eval import validate

def test_guardrail_eval_dataset(tmp_path):
    path = pathlib.Path('data') / 'guardrail_eval.jsonl'
    assert validate(path), "Validation failed"
