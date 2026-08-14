from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from research_tree import ArtifactRef, RunLedger
from research_tree.acceptance import DeliveryAcceptance, delivery_pair_digest
from research_tree.completion_inputs import CompletionInputError, CompletionInputRegistrar
from research_tree.domain import canonical_json_bytes
from research_tree.run_ledger import LedgerIntegrityError


def test_canonical_delivery_compiler_routes_pair_through_registration(tmp_path: Path) -> None:
    from test_strict_delivery_lineage import _compile, _fixture

    fixture = _fixture(tmp_path)
    result = _compile(fixture, "registered", expected_revision=fixture["expected_revision"])
    registered = CompletionInputRegistrar(fixture["ledger"]).registered_inputs(fixture["round_id"])
    assert {item.id for item in registered} == {result.technical_package.id, result.human_research_report.id}


def _pair_payloads(run_id: str, technical_id: str, human_id: str) -> tuple[dict, dict]:
    technical = {"document": {"claims": ["canonical"]}, "markdown": "technical delivery"}
    human = {
        "technical_package_ref": ArtifactRef(run_id, technical_id, 1).to_dict(),
        "document": {"summary": "canonical"},
        "markdown": "human delivery",
    }
    return technical, human


def _manifest_digest(technical, human) -> str:
    return sha256(
        canonical_json_bytes(
            {
                "technical": {
                    "ref": ArtifactRef(technical.round_id, technical.id, technical.revision).to_dict(),
                    "hash": technical.content_hash,
                },
                "human": {
                    "ref": ArtifactRef(human.round_id, human.id, human.revision).to_dict(),
                    "hash": human.content_hash,
                },
            }
        )
    ).hexdigest()


def _acceptance(run_id: str, technical, human, *, actor: str = "human", acceptance_id: str = "acceptance-1"):
    technical_revision = f"{technical.id}@{technical.revision}"
    human_revision = f"{human.id}@{human.revision}"
    return DeliveryAcceptance.create(
        acceptance_id,
        run_id,
        technical_revision,
        human_revision,
        delivery_pair_digest(run_id, technical_revision, human_revision),
        _manifest_digest(technical, human),
        [
            {
                "feedback_id": "feedback-1",
                "classification": "presentation",
                "statement": "I accept the displayed conclusions and trade-offs.",
                "target_refs": [technical.id, human.id],
            }
        ],
        actor=actor,
    )


def _pair(tmp_path: Path, *, expected_revision: int = 0):
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-delivery")
    registrar = CompletionInputRegistrar(ledger)
    technical_payload, human_payload = _pair_payloads("run-delivery", "technical-1", "human-1")
    technical, human = registrar.write_delivery_pair(
        round_id="run-delivery",
        technical_package_id="technical-1",
        human_report_id="human-1",
        technical_payload=technical_payload,
        human_payload=human_payload,
        technical_parent_refs=(),
        human_parent_refs=(ArtifactRef("run-delivery", "technical-1", 1),),
        expected_revision=expected_revision,
    )
    return ledger, registrar, technical, human


def test_generic_delivery_artifacts_do_not_register_and_typed_pair_does(tmp_path: Path) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-delivery")
    technical_payload, human_payload = _pair_payloads("run-delivery", "technical-generic", "human-generic")
    technical = ledger.append_artifact(
        "run-delivery", "technical-generic", "technical-research-package", technical_payload, expected_revision=0
    )
    human = ledger.append_artifact(
        "run-delivery",
        "human-generic",
        "human-research-report",
        {
            **human_payload,
            "technical_package_ref": ArtifactRef("run-delivery", technical.id, technical.revision).to_dict(),
        },
        parent_refs=(ArtifactRef("run-delivery", technical.id, technical.revision),),
        expected_revision=1,
    )
    registrar = CompletionInputRegistrar(ledger)
    assert registrar.registered_inputs("run-delivery") == ()

    technical, human = registrar.write_delivery_pair(
        round_id="run-delivery",
        technical_package_id="technical-typed",
        human_report_id="human-typed",
        technical_payload=technical_payload,
        human_payload={
            **human_payload,
            "technical_package_ref": ArtifactRef("run-delivery", "technical-typed", 1).to_dict(),
        },
        technical_parent_refs=(),
        human_parent_refs=(ArtifactRef("run-delivery", "technical-typed", 1),),
        expected_revision=2,
    )
    assert {item.id for item in registrar.registered_inputs("run-delivery")} == {technical.id, human.id}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: {**payload, "technical_package_ref": ArtifactRef("other-run", "technical-1", 1).to_dict()},
        lambda payload: {**payload, "technical_package_ref": ArtifactRef("run-delivery", "technical-1", 2).to_dict()},
    ],
)
def test_delivery_pair_rejects_cross_run_or_mismatched_lineage_atomically(tmp_path: Path, mutate) -> None:
    ledger = RunLedger(tmp_path)
    ledger.create_run("run-delivery")
    registrar = CompletionInputRegistrar(ledger)
    technical_payload, human_payload = _pair_payloads("run-delivery", "technical-1", "human-1")
    with pytest.raises((CompletionInputError, LedgerIntegrityError)):
        registrar.write_delivery_pair(
            round_id="run-delivery",
            technical_package_id="technical-1",
            human_report_id="human-1",
            technical_payload=technical_payload,
            human_payload=mutate(human_payload),
            technical_parent_refs=(),
            human_parent_refs=(ArtifactRef("run-delivery", "technical-1", 1),),
            expected_revision=0,
        )
    assert ledger.load_run("run-delivery").artifacts == ()
    assert registrar.registered_inputs("run-delivery") == ()


def test_acceptance_registration_binds_pair_manifest_actor_and_is_idempotent(tmp_path: Path) -> None:
    ledger, registrar, technical, human = _pair(tmp_path)
    acceptance = _acceptance("run-delivery", technical, human)
    registered = registrar.write_delivery_acceptance(
        round_id="run-delivery",
        technical_package=technical,
        human_research_report=human,
        acceptance=acceptance,
        expected_revision=2,
    )
    duplicate = registrar.write_delivery_acceptance(
        round_id="run-delivery",
        technical_package=technical,
        human_research_report=human,
        acceptance=acceptance,
        expected_revision=2,
    )
    assert registered == duplicate
    assert [item.id for item in registrar.registered_inputs("run-delivery")] == [
        "acceptance-1",
        "human-1",
        "technical-1",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"actor": "worker"},
        {"displayed_digest": "0" * 64},
        {"manifest_digest": "1" * 64},
    ],
)
def test_acceptance_rejects_wrong_actor_or_digest_without_partial_write(tmp_path: Path, kwargs) -> None:
    ledger, registrar, technical, human = _pair(tmp_path)
    base = _acceptance("run-delivery", technical, human)
    forged = replace(base, **kwargs)
    with pytest.raises(CompletionInputError):
        registrar.write_delivery_acceptance(
            round_id="run-delivery",
            technical_package=technical,
            human_research_report=human,
            acceptance=forged,
            expected_revision=2,
        )
    assert [item.id for item in registrar.registered_inputs("run-delivery")] == ["human-1", "technical-1"]


def test_acceptance_rejects_replacement_or_quarantined_pair(tmp_path: Path) -> None:
    ledger, registrar, technical, human = _pair(tmp_path)
    replacement = ledger.append_artifact(
        "run-delivery",
        technical.id,
        technical.kind,
        {"document": {"replacement": True}, "markdown": "replacement"},
        expected_revision=2,
    )
    acceptance = _acceptance("run-delivery", technical, human, acceptance_id="stale")
    with pytest.raises((CompletionInputError, LedgerIntegrityError)):
        registrar.write_delivery_acceptance(
            round_id="run-delivery",
            technical_package=technical,
            human_research_report=human,
            acceptance=acceptance,
            expected_revision=3,
        )
    assert replacement.revision == 2
    assert all(item.kind != "delivery-acceptance" for item in ledger.load_run("run-delivery").artifacts)
