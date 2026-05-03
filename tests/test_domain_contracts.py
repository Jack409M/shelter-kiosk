from __future__ import annotations


def test_domain_contracts_exist():
    import core.domain_contracts as dc

    assert hasattr(dc, "PASS_DOMAIN_CONTRACTS")
    assert hasattr(dc, "INTAKE_DOMAIN_CONTRACTS")
    assert hasattr(dc, "PROMOTION_DOMAIN_CONTRACTS")
    assert hasattr(dc, "BACKUP_DOMAIN_CONTRACTS")
    assert hasattr(dc, "ROUTE_BOUNDARY_CONTRACTS")


def test_pass_contracts_locked():
    import core.domain_contracts as dc

    contracts = dc.PASS_DOMAIN_CONTRACTS

    assert contracts["no_get_state_change"] is True
    assert contracts["passes_move_with_resident_on_transfer"] is True


def test_intake_contracts_locked():
    import core.domain_contracts as dc

    contracts = dc.INTAKE_DOMAIN_CONTRACTS

    assert contracts["draft_not_reportable"] is True
    assert contracts["final_submit_single_write"] is True


def test_route_boundary_contracts_locked():
    import core.domain_contracts as dc

    contracts = dc.ROUTE_BOUNDARY_CONTRACTS

    assert contracts["routes_do_not_own_business_logic"] is True
    assert contracts["services_own_lifecycle_decisions"] is True
