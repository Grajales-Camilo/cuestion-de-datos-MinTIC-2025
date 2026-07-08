import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="Las pruebas de integracion reales empiezan en T-104A/T-201.")
def test_integration_suite_is_registered() -> None:
    pass
