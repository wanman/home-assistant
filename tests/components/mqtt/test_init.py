"""The tests for the MQTT component."""
import asyncio
from collections import namedtuple, OrderedDict
import unittest
from unittest import mock
import socket

import voluptuous as vol

from homeassistant.core import callback
from homeassistant.setup import setup_component, async_setup_component
import homeassistant.components.mqtt as mqtt
from homeassistant.const import (
    EVENT_CALL_SERVICE, ATTR_DOMAIN, ATTR_SERVICE, EVENT_HOMEASSISTANT_STOP)
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from tests.common import (
    get_test_home_assistant, mock_mqtt_component, fire_mqtt_message, mock_coro)


@asyncio.coroutine
def mock_mqtt_client(hass, config=None):
    """Mock the MQTT paho client."""
    if config is None:
        config = {
            mqtt.CONF_BROKER: 'mock-broker'
        }

    with mock.patch('paho.mqtt.client.Client') as mock_client:
        mock_client().connect = lambda *args: 0
        result = yield from async_setup_component(hass, mqtt.DOMAIN, {
            mqtt.DOMAIN: config
        })
        assert result
        return mock_client()


# pylint: disable=invalid-name
class TestMQTT(unittest.TestCase):
    """Test the MQTT component."""

    def setUp(self):  # pylint: disable=invalid-name
        """Setup things to be run when tests are started."""
        self.hass = get_test_home_assistant()
        mock_mqtt_component(self.hass)
        self.calls = []

    def tearDown(self):  # pylint: disable=invalid-name
        """Stop everything that was started."""
        self.hass.stop()

    @callback
    def record_calls(self, *args):
        """Helper for recording calls."""
        self.calls.append(args)

    def test_client_starts_on_home_assistant_mqtt_setup(self):
        """Test if client is connect after mqtt init on bootstrap."""
        assert self.hass.data['mqtt'].async_connect.called

    def test_client_stops_on_home_assistant_start(self):
        """Test if client stops on HA launch."""
        self.hass.bus.fire(EVENT_HOMEASSISTANT_STOP)
        self.hass.block_till_done()
        self.assertTrue(self.hass.data['mqtt'].async_disconnect.called)

    def test_publish_calls_service(self):
        """Test the publishing of call to services."""
        self.hass.bus.listen_once(EVENT_CALL_SERVICE, self.record_calls)

        mqtt.publish(self.hass, 'test-topic', 'test-payload')

        self.hass.block_till_done()

        self.assertEqual(1, len(self.calls))
        self.assertEqual(
            'test-topic',
            self.calls[0][0].data['service_data'][mqtt.ATTR_TOPIC])
        self.assertEqual(
            'test-payload',
            self.calls[0][0].data['service_data'][mqtt.ATTR_PAYLOAD])

    def test_service_call_without_topic_does_not_publish(self):
        """Test the service call if topic is missing."""
        self.hass.bus.fire(EVENT_CALL_SERVICE, {
            ATTR_DOMAIN: mqtt.DOMAIN,
            ATTR_SERVICE: mqtt.SERVICE_PUBLISH
        })
        self.hass.block_till_done()
        self.assertTrue(not self.hass.data['mqtt'].async_publish.called)

    def test_service_call_with_template_payload_renders_template(self):
        """Test the service call with rendered template.

        If 'payload_template' is provided and 'payload' is not, then render it.
        """
        mqtt.publish_template(self.hass, "test/topic", "{{ 1+1 }}")
        self.hass.block_till_done()
        self.assertTrue(self.hass.data['mqtt'].async_publish.called)
        self.assertEqual(
            self.hass.data['mqtt'].async_publish.call_args[0][1], "2")

    def test_service_call_with_payload_doesnt_render_template(self):
        """Test the service call with unrendered template.

        If both 'payload' and 'payload_template' are provided then fail.
        """
        payload = "not a template"
        payload_template = "a template"
        self.hass.services.call(mqtt.DOMAIN, mqtt.SERVICE_PUBLISH, {
            mqtt.ATTR_TOPIC: "test/topic",
            mqtt.ATTR_PAYLOAD: payload,
            mqtt.ATTR_PAYLOAD_TEMPLATE: payload_template
        }, blocking=True)
        self.assertFalse(self.hass.data['mqtt'].async_publish.called)

    def test_service_call_with_ascii_qos_retain_flags(self):
        """Test the service call with args that can be misinterpreted.

        Empty payload message and ascii formatted qos and retain flags.
        """
        self.hass.services.call(mqtt.DOMAIN, mqtt.SERVICE_PUBLISH, {
            mqtt.ATTR_TOPIC: "test/topic",
            mqtt.ATTR_PAYLOAD: "",
            mqtt.ATTR_QOS: '2',
            mqtt.ATTR_RETAIN: 'no'
        }, blocking=True)
        self.assertTrue(self.hass.data['mqtt'].async_publish.called)
        self.assertEqual(
            self.hass.data['mqtt'].async_publish.call_args[0][2], 2)
        self.assertFalse(self.hass.data['mqtt'].async_publish.call_args[0][3])

    def test_subscribe_topic(self):
        """Test the subscription of a topic."""
        unsub = mqtt.subscribe(self.hass, 'test-topic', self.record_calls)

        fire_mqtt_message(self.hass, 'test-topic', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(1, len(self.calls))
        self.assertEqual('test-topic', self.calls[0][0])
        self.assertEqual('test-payload', self.calls[0][1])

        unsub()

        fire_mqtt_message(self.hass, 'test-topic', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(1, len(self.calls))

    def test_subscribe_topic_not_match(self):
        """Test if subscribed topic is not a match."""
        mqtt.subscribe(self.hass, 'test-topic', self.record_calls)

        fire_mqtt_message(self.hass, 'another-test-topic', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(0, len(self.calls))

    def test_subscribe_topic_level_wildcard(self):
        """Test the subscription of wildcard topics."""
        mqtt.subscribe(self.hass, 'test-topic/+/on', self.record_calls)

        fire_mqtt_message(self.hass, 'test-topic/bier/on', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(1, len(self.calls))
        self.assertEqual('test-topic/bier/on', self.calls[0][0])
        self.assertEqual('test-payload', self.calls[0][1])

    def test_subscribe_topic_level_wildcard_no_subtree_match(self):
        """Test the subscription of wildcard topics."""
        mqtt.subscribe(self.hass, 'test-topic/+/on', self.record_calls)

        fire_mqtt_message(self.hass, 'test-topic/bier', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(0, len(self.calls))

    def test_subscribe_topic_subtree_wildcard_subtree_topic(self):
        """Test the subscription of wildcard topics."""
        mqtt.subscribe(self.hass, 'test-topic/#', self.record_calls)

        fire_mqtt_message(self.hass, 'test-topic/bier/on', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(1, len(self.calls))
        self.assertEqual('test-topic/bier/on', self.calls[0][0])
        self.assertEqual('test-payload', self.calls[0][1])

    def test_subscribe_topic_subtree_wildcard_root_topic(self):
        """Test the subscription of wildcard topics."""
        mqtt.subscribe(self.hass, 'test-topic/#', self.record_calls)

        fire_mqtt_message(self.hass, 'test-topic', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(1, len(self.calls))
        self.assertEqual('test-topic', self.calls[0][0])
        self.assertEqual('test-payload', self.calls[0][1])

    def test_subscribe_topic_subtree_wildcard_no_match(self):
        """Test the subscription of wildcard topics."""
        mqtt.subscribe(self.hass, 'test-topic/#', self.record_calls)

        fire_mqtt_message(self.hass, 'another-test-topic', 'test-payload')

        self.hass.block_till_done()
        self.assertEqual(0, len(self.calls))


class TestMQTTCallbacks(unittest.TestCase):
    """Test the MQTT callbacks."""

    def setUp(self):  # pylint: disable=invalid-name
        """Setup things to be run when tests are started."""
        self.hass = get_test_home_assistant()

        with mock.patch('paho.mqtt.client.Client') as client:
            client().connect = lambda *args: 0
            assert setup_component(self.hass, mqtt.DOMAIN, {
                mqtt.DOMAIN: {
                    mqtt.CONF_BROKER: 'mock-broker',
                }
            })

    def tearDown(self):  # pylint: disable=invalid-name
        """Stop everything that was started."""
        self.hass.stop()

    def test_receiving_mqtt_message_fires_hass_event(self):
        """Test if receiving triggers an event."""
        calls = []

        @callback
        def record(topic, payload, qos):
            """Helper to record calls."""
            data = {
                'topic': topic,
                'payload': payload,
                'qos': qos,
            }
            calls.append(data)

        async_dispatcher_connect(
            self.hass, mqtt.SIGNAL_MQTT_MESSAGE_RECEIVED, record)

        MQTTMessage = namedtuple('MQTTMessage', ['topic', 'qos', 'payload'])
        message = MQTTMessage('test_topic', 1, 'Hello World!'.encode('utf-8'))

        self.hass.data['mqtt']._mqtt_on_message(
            None, {'hass': self.hass}, message)
        self.hass.block_till_done()

        self.assertEqual(1, len(calls))
        last_event = calls[0]
        self.assertEqual('Hello World!', last_event['payload'])
        self.assertEqual(message.topic, last_event['topic'])
        self.assertEqual(message.qos, last_event['qos'])

    def test_mqtt_failed_connection_results_in_disconnect(self):
        """Test if connection failure leads to disconnect."""
        for result_code in range(1, 6):
            self.hass.data['mqtt']._mqttc = mock.MagicMock()
            self.hass.data['mqtt']._mqtt_on_connect(
                None, {'topics': {}}, 0, result_code)
            self.assertTrue(self.hass.data['mqtt']._mqttc.disconnect.called)

    def test_mqtt_disconnect_tries_no_reconnect_on_stop(self):
        """Test the disconnect tries."""
        self.hass.data['mqtt']._mqtt_on_disconnect(None, None, 0)
        self.assertFalse(self.hass.data['mqtt']._mqttc.reconnect.called)

    @mock.patch('homeassistant.components.mqtt.time.sleep')
    def test_mqtt_disconnect_tries_reconnect(self, mock_sleep):
        """Test the re-connect tries."""
        self.hass.data['mqtt'].topics = {
            'test/topic': 1,
            'test/progress': None
        }
        self.hass.data['mqtt'].progress = {
            1: 'test/progress'
        }
        self.hass.data['mqtt']._mqttc.reconnect.side_effect = [1, 1, 1, 0]
        self.hass.data['mqtt']._mqtt_on_disconnect(None, None, 1)
        self.assertTrue(self.hass.data['mqtt']._mqttc.reconnect.called)
        self.assertEqual(
            4, len(self.hass.data['mqtt']._mqttc.reconnect.mock_calls))
        self.assertEqual([1, 2, 4],
                         [call[1][0] for call in mock_sleep.mock_calls])

        self.assertEqual({'test/topic': 1}, self.hass.data['mqtt'].topics)
        self.assertEqual({}, self.hass.data['mqtt'].progress)

    def test_invalid_mqtt_topics(self):
        """Test invalid topics."""
        self.assertRaises(vol.Invalid, mqtt.valid_publish_topic, 'bad+topic')
        self.assertRaises(vol.Invalid, mqtt.valid_subscribe_topic, 'bad\0one')

    def test_receiving_non_utf8_message_gets_logged(self):
        """Test receiving a non utf8 encoded message."""
        calls = []

        @callback
        def record(topic, payload, qos):
            """Helper to record calls."""
            data = {
                'topic': topic,
                'payload': payload,
                'qos': qos,
            }
            calls.append(data)

        async_dispatcher_connect(
            self.hass, mqtt.SIGNAL_MQTT_MESSAGE_RECEIVED, record)

        payload = 0x9a
        topic = 'test_topic'
        MQTTMessage = namedtuple('MQTTMessage', ['topic', 'qos', 'payload'])
        message = MQTTMessage(topic, 1, payload)
        with self.assertLogs(level='ERROR') as test_handle:
            self.hass.data['mqtt']._mqtt_on_message(
                None,
                {'hass': self.hass},
                message)
            self.hass.block_till_done()
            self.assertIn(
                "ERROR:homeassistant.components.mqtt:Illegal utf-8 unicode "
                "payload from MQTT topic: %s, Payload: " % topic,
                test_handle.output[0])


@asyncio.coroutine
def test_setup_embedded_starts_with_no_config(hass):
    """Test setting up embedded server with no config."""
    client_config = ('localhost', 1883, 'user', 'pass', None, '3.1.1')

    with mock.patch('homeassistant.components.mqtt.server.async_start',
                    return_value=mock_coro(
                        return_value=(True, client_config))
                    ) as _start:
        yield from mock_mqtt_client(hass, {})
        assert _start.call_count == 1


@asyncio.coroutine
def test_setup_embedded_with_embedded(hass):
    """Test setting up embedded server with no config."""
    client_config = ('localhost', 1883, 'user', 'pass', None, '3.1.1')

    with mock.patch('homeassistant.components.mqtt.server.async_start',
                    return_value=mock_coro(
                        return_value=(True, client_config))
                    ) as _start:
        _start.return_value = mock_coro(return_value=(True, client_config))
        yield from mock_mqtt_client(hass, {'embedded': None})
        assert _start.call_count == 1


@asyncio.coroutine
def test_setup_fails_if_no_connect_broker(hass):
    """Test for setup failure if connection to broker is missing."""
    test_broker_cfg = {mqtt.DOMAIN: {mqtt.CONF_BROKER: 'test-broker'}}

    with mock.patch('homeassistant.components.mqtt.MQTT',
                    side_effect=socket.error()):
        result = yield from async_setup_component(hass, mqtt.DOMAIN,
                                                  test_broker_cfg)
        assert not result

    with mock.patch('paho.mqtt.client.Client') as mock_client:
        mock_client().connect = lambda *args: 1
        result = yield from async_setup_component(hass, mqtt.DOMAIN,
                                                  test_broker_cfg)
        assert not result


@asyncio.coroutine
def test_setup_uses_certificate_on_mqtts_port(hass):
    """Test setup uses bundled certificates when mqtts port is requested."""
    test_broker_cfg = {mqtt.DOMAIN: {mqtt.CONF_BROKER: 'test-broker',
                                     'port': 8883}}

    with mock.patch('homeassistant.components.mqtt.MQTT') as mock_MQTT:
        yield from async_setup_component(hass, mqtt.DOMAIN, test_broker_cfg)

    assert mock_MQTT.called
    assert mock_MQTT.mock_calls[0][1][2] == 8883

    import requests.certs
    expectedCertificate = requests.certs.where()
    assert mock_MQTT.mock_calls[0][1][7] == expectedCertificate


@asyncio.coroutine
def test_setup_uses_certificate_not_on_mqtts_port(hass):
    """Test setup doesn't use bundled certificates when not mqtts port."""
    test_broker_cfg = {mqtt.DOMAIN: {mqtt.CONF_BROKER: 'test-broker',
                                     'port': 1883}}

    with mock.patch('homeassistant.components.mqtt.MQTT') as mock_MQTT:
        yield from async_setup_component(hass, mqtt.DOMAIN, test_broker_cfg)

    assert mock_MQTT.called
    assert mock_MQTT.mock_calls[0][1][2] == 1883

    import requests.certs
    mqttsCertificateBundle = requests.certs.where()
    assert mock_MQTT.mock_calls[0][1][7] != mqttsCertificateBundle


@asyncio.coroutine
def test_birth_message(hass):
    """Test sending birth message."""
    mqtt_client = yield from mock_mqtt_client(hass, {
        mqtt.CONF_BROKER: 'mock-broker',
        mqtt.CONF_BIRTH_MESSAGE: {mqtt.ATTR_TOPIC: 'birth',
                                  mqtt.ATTR_PAYLOAD: 'birth'}
    })
    calls = []
    mqtt_client.publish = lambda *args: calls.append(args)
    hass.data['mqtt']._mqtt_on_connect(None, None, 0, 0)
    yield from hass.async_block_till_done()
    assert calls[-1] == ('birth', 'birth', 0, False)


@asyncio.coroutine
def test_mqtt_subscribes_topics_on_connect(hass):
    """Test subscription to topic on connect."""
    mqtt_client = yield from mock_mqtt_client(hass)

    prev_topics = OrderedDict()
    prev_topics['topic/test'] = 1,
    prev_topics['home/sensor'] = 2,
    prev_topics['still/pending'] = None

    hass.data['mqtt'].topics = prev_topics
    hass.data['mqtt'].progress = {1: 'still/pending'}

    # Return values for subscribe calls (rc, mid)
    mqtt_client.subscribe.side_effect = ((0, 2), (0, 3))

    hass.add_job = mock.MagicMock()
    hass.data['mqtt']._mqtt_on_connect(None, None, 0, 0)

    yield from hass.async_block_till_done()

    assert not mqtt_client.disconnect.called

    expected = [(topic, qos) for topic, qos in prev_topics.items()
                if qos is not None]

    assert [call[1][1:] for call in hass.add_job.mock_calls] == expected
