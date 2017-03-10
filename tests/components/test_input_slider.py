"""The tests for the Input slider component."""
# pylint: disable=protected-access
import asyncio
import unittest

from tests.common import get_test_home_assistant, mock_component

from homeassistant.core import CoreState, State
from homeassistant.setup import setup_component, async_setup_component
from homeassistant.components.input_slider import (DOMAIN, select_value)
from homeassistant.helpers.restore_state import DATA_RESTORE_CACHE


class TestInputSlider(unittest.TestCase):
    """Test the input slider component."""

    # pylint: disable=invalid-name
    def setUp(self):
        """Setup things to be run when tests are started."""
        self.hass = get_test_home_assistant()

    # pylint: disable=invalid-name
    def tearDown(self):
        """Stop everything that was started."""
        self.hass.stop()

    def test_config(self):
        """Test config."""
        invalid_configs = [
            None,
            {},
            {'name with space': None},
            {'test_1': {
                'min': 50,
                'max': 50,
            }},
        ]
        for cfg in invalid_configs:
            self.assertFalse(
                setup_component(self.hass, DOMAIN, {DOMAIN: cfg}))

    def test_select_value(self):
        """Test select_value method."""
        self.assertTrue(setup_component(self.hass, DOMAIN, {DOMAIN: {
            'test_1': {
                'initial': 50,
                'min': 0,
                'max': 100,
            },
        }}))
        entity_id = 'input_slider.test_1'

        state = self.hass.states.get(entity_id)
        self.assertEqual(50, float(state.state))

        select_value(self.hass, entity_id, '30.4')
        self.hass.block_till_done()

        state = self.hass.states.get(entity_id)
        self.assertEqual(30.4, float(state.state))

        select_value(self.hass, entity_id, '70')
        self.hass.block_till_done()

        state = self.hass.states.get(entity_id)
        self.assertEqual(70, float(state.state))

        select_value(self.hass, entity_id, '110')
        self.hass.block_till_done()

        state = self.hass.states.get(entity_id)
        self.assertEqual(70, float(state.state))


@asyncio.coroutine
def test_restore_state(hass):
    """Ensure states are restored on startup."""
    hass.data[DATA_RESTORE_CACHE] = {
        'input_slider.b1': State('input_slider.b1', '70'),
        'input_slider.b2': State('input_slider.b2', '200'),
    }

    hass.state = CoreState.starting
    mock_component(hass, 'recorder')

    yield from async_setup_component(hass, DOMAIN, {
        DOMAIN: {
            'b1': {
                'initial': 50,
                'min': 0,
                'max': 100,
            },
            'b2': {
                'initial': 60,
                'min': 0,
                'max': 100,
            },
        }})

    state = hass.states.get('input_slider.b1')
    assert state
    assert float(state.state) == 70

    state = hass.states.get('input_slider.b2')
    assert state
    assert float(state.state) == 60
