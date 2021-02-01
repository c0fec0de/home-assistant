"""Tests for the UniPi config flow."""
from unittest.mock import patch

from homeassistant import data_entry_flow
from homeassistant.components.unipi.const import CONF_NAME, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.typing import HomeAssistantType

from .const import HOST, INVALID_HOST, NAME, PORT


async def _async_true(*args, **kwargs):
    return True


async def _async_connection_error(*args, **kwargs):
    raise ConnectionError()


async def test_user_empty(hass: HomeAssistantType):
    """Test user config start."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=None
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_invalid_port(hass: HomeAssistantType):
    """Test user config with invalid port."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_HOST: INVALID_HOST, CONF_PORT: PORT, CONF_NAME: NAME},
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {"host": "invalid_host"}


@patch("homeassistant.components.unipi.config_flow.check_connection", _async_true)
@patch("homeassistant.components.unipi.async_setup_entry", _async_true)
async def test_user_success(hass: HomeAssistantType):
    """Test user config with succeed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_NAME: NAME,
        },
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["result"].unique_id == NAME.lower()
    assert result["title"] == NAME
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_PORT] == PORT
    assert result["data"][CONF_NAME] == NAME


@patch(
    "homeassistant.components.unipi.config_flow.check_connection",
    _async_connection_error,
)
@patch("homeassistant.components.unipi.async_setup_entry", _async_true)
async def test_user_fail(hass: HomeAssistantType):
    """Test user config with succeed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_NAME: NAME,
        },
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {"host": "connection_error"}
