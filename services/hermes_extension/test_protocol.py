import json

import pytest

from services.hermes_extension.protocol import PluginRequest, decode_message, encode_message


pytestmark = pytest.mark.unit


def valid_message():
    return {
        "version": 1,
        "type": "task.submit",
        "request_id": "req-1",
        "task": {
            "prompt": "inspect",
            "project_id": "default",
            "priority": "normal",
            "source": "mobile",
            "requires_approval": False,
        },
    }


def test_plugin_request_round_trip_preserves_auth_token():
    request = PluginRequest.from_message({**valid_message(), "auth_token": "secret"})

    assert request.auth_token == "secret"
    assert PluginRequest.from_message(request.to_message()) == request


@pytest.mark.parametrize(
    "mutate, error",
    [
        (lambda message: message["task"].update(prompt=""), "must not be blank"),
        (lambda message: message["task"].update(priority="urgent"), "priority is invalid"),
        (lambda message: message["task"].update(requires_approval="false"), "must be boolean"),
        (lambda message: message["task"].update(project_id=3), "string fields are invalid"),
        (lambda message: message.pop("request_id"), "requires request_id"),
    ],
)
def test_plugin_request_rejects_malformed_payloads(mutate, error):
    message = valid_message()
    mutate(message)

    with pytest.raises(ValueError, match=error):
        PluginRequest.from_message(message)


def test_decode_message_rejects_non_object_json():
    with pytest.raises(ValueError, match="JSON object"):
        decode_message(json.dumps(["not", "an", "object"]).encode())


def test_encode_message_is_single_newline_delimited_record():
    encoded = encode_message(valid_message())

    assert encoded.endswith(b"\n")
    assert encoded.count(b"\n") == 1
