"""Offline request and mocked-HTTP tests; no live model calls occur here."""

import base64
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from PIL import Image

from pam.openrouter import (
    ENDPOINT, MODEL, OpenRouterError, _RejectRedirects,
    build_request, load_openrouter_config, send_request,
)


PROJECT = Path(__file__).resolve().parent.parent
FAKE_KEY = "test-only-fake-credential"


class _Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = load_openrouter_config(PROJECT / "config" / "openrouter.json")
        self.image_paths = []
        for index in range(5):
            path = self.directory / f"composite_{index}.png"
            Image.new("RGB", (4, 2), (index, 20, 40)).save(path)
            self.image_paths.append(path)
        self.bundle = self._bundle("predictor")

    def _bundle(self, role):
        count = 5 if role == "predictor" else 200
        return {
            "model": "Qwen3.5-27B", "role": role,
            "generation": {"temperature": 0.3, "enable_thinking": role == "reflector"},
            "messages": [
                {"role": "system", "content": "Original paper prompt with {literal JSON braces}."},
                {"role": "user", "content": [
                    {"type": "text", "text": "Observed frame time; no evaluation label."},
                    *[{"type": "image_file", "path": str(self.image_paths[index % 5]), "mime_type": "image/png"}
                      for index in range(count)],
                    *([{"type": "text", "text": "Current memory and chronological action summary."}]
                      if role == "reflector" else []),
                ]},
            ],
        }

    def _payload(self):
        return build_request(self.bundle, self.config)

    def _mock_send(self, body, *, status=200, key=FAKE_KEY):
        opener = Mock()
        opener.open.return_value = _Response(body, status)
        with patch("pam.openrouter.build_opener", return_value=opener):
            result = send_request(self._payload(), self.config, api_key=key)
        return result, opener

    def test_five_pngs_are_encoded_in_order_with_roles_and_text_unchanged(self):
        before = deepcopy(self.bundle)
        payload = self._payload()
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["messages"][0], self.bundle["messages"][0])
        self.assertEqual([message["role"] for message in payload["messages"]], ["system", "user"])
        parts = payload["messages"][1]["content"]
        self.assertEqual(parts[0], self.bundle["messages"][1]["content"][0])
        self.assertEqual(len(parts), 6)
        for part, path in zip(parts[1:], self.image_paths):
            prefix, encoded = part["image_url"]["url"].split(",", 1)
            self.assertEqual(prefix, "data:image/png;base64")
            self.assertEqual(base64.b64decode(encoded), path.read_bytes())
        self.assertEqual(self.bundle, before)

    def test_paper_settings_and_separate_transport_limits_are_retained(self):
        payload = self._payload()
        self.assertEqual(payload["temperature"], 0.3)
        self.assertEqual(payload["reasoning"], {"enabled": False})
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(payload["provider"], {"order": ["alibaba"], "allow_fallbacks": False, "require_parameters": True})
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["plugins"], [{"id": "context-compression", "enabled": False}])

    def test_reflector_preserves_all_200_images_and_turns_reasoning_on(self):
        bundle = self._bundle("reflector")
        payload = build_request(bundle, self.config)
        content = payload["messages"][1]["content"]
        self.assertEqual(sum(part["type"] == "image_url" for part in content), 200)
        self.assertEqual(content[-1], bundle["messages"][1]["content"][-1])
        self.assertEqual(payload["reasoning"], {"enabled": True})
        self.assertEqual(payload["max_tokens"], 16384)

    def _explicit_150_bundle(self):
        bundle = self._bundle("reflector")
        bundle["frame_count"] = 150
        bundle["frame_count_source"] = "explicit_user_override"
        content = bundle["messages"][1]["content"]
        bundle["messages"][1]["content"] = [content[0], *content[1:151], content[-1]]
        return bundle

    def test_explicit_150_reflection_preserves_original_bytes_order_and_default_detail(self):
        config = deepcopy(self.config)
        config["reflector_frame_count"] = 150
        bundle = self._explicit_150_bundle()
        original = deepcopy(bundle)
        payload = build_request(bundle, config)
        images = [part["image_url"] for part in payload["messages"][1]["content"] if part["type"] == "image_url"]
        self.assertEqual(len(images), 150)
        for index, image in enumerate(images):
            self.assertEqual(set(image), {"url"})
            self.assertEqual(base64.b64decode(image["url"].split(",", 1)[1]), self.image_paths[index % 5].read_bytes())
        self.assertEqual(bundle, original)
        self.assertEqual(payload["reasoning"], {"enabled": True})
        self.assertFalse(payload["stream"])
        self.assertEqual(build_request(self.bundle, config), self._payload())
        opener = Mock()
        opener.open.return_value = _Response(b'{"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]}')
        with patch("pam.openrouter.build_opener", return_value=opener):
            send_request(payload, config, api_key=FAKE_KEY)
        opener.open.assert_called_once()

    def test_150_reflection_requires_declaration_and_matching_configuration(self):
        config = deepcopy(self.config)
        config["reflector_frame_count"] = 150
        explicit = self._explicit_150_bundle()
        variants = []
        undeclared = deepcopy(explicit)
        del undeclared["frame_count_source"]
        variants.append((undeclared, config))
        no_count = deepcopy(explicit)
        del no_count["frame_count"]
        variants.append((no_count, config))
        variants.extend([(explicit, self.config), (self._bundle("reflector"), config)])
        for bundle, settings in variants:
            with self.subTest(count=bundle.get("frame_count")), self.assertRaises(OpenRouterError):
                build_request(bundle, settings)
        for count in (149, 151, True, 150.0, "150"):
            settings = {**self.config, "reflector_frame_count": count}
            with self.subTest(count=count), self.assertRaises(OpenRouterError):
                build_request(explicit, settings)

    def test_payload_cannot_drop_or_add_a_reflector_image_after_build(self):
        config = {**self.config, "reflector_frame_count": 150}
        for mutate in ("drop", "add"):
            payload = build_request(self._explicit_150_bundle(), config)
            parts = payload["messages"][1]["content"]
            if mutate == "drop":
                parts.pop(1)
            else:
                parts.insert(1, deepcopy(parts[1]))
            with patch("pam.openrouter.build_opener") as opener:
                with self.subTest(mutate=mutate), self.assertRaises(OpenRouterError):
                    send_request(payload, config, api_key=FAKE_KEY)
                opener.assert_not_called()

    def test_explicit_100_reflection_requires_matching_config_and_keeps_png_bytes(self):
        bundle = self._explicit_150_bundle()
        bundle["frame_count"] = 100
        content = bundle["messages"][1]["content"]
        bundle["messages"][1]["content"] = [content[0], *content[1:101], content[-1]]
        config = {**self.config, "reflector_frame_count": 100}
        payload = build_request(bundle, config)
        images = [part["image_url"] for part in payload["messages"][1]["content"] if part["type"] == "image_url"]
        self.assertEqual(len(images), 100)
        for index, image in enumerate(images):
            self.assertEqual(set(image), {"url"})
            self.assertEqual(base64.b64decode(image["url"].split(",", 1)[1]), self.image_paths[index % 5].read_bytes())
        with self.assertRaises(OpenRouterError):
            build_request(bundle, {**self.config, "reflector_frame_count": 150})
        del bundle["frame_count_source"]
        with self.assertRaises(OpenRouterError):
            build_request(bundle, config)
        opener = Mock()
        opener.open.return_value = _Response(b'{"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]}')
        with patch("pam.openrouter.build_opener", return_value=opener):
            send_request(payload, config, api_key=FAKE_KEY)
        opener.open.assert_called_once()

    def test_explicit_50_reflection_preserves_pngs_and_requires_user_override(self):
        bundle = self._explicit_150_bundle()
        bundle["frame_count"] = 50
        content = bundle["messages"][1]["content"]
        bundle["messages"][1]["content"] = [content[0], *content[1:51], content[-1]]
        config = {**self.config, "reflector_frame_count": 50}
        payload = build_request(bundle, config)
        images = [part["image_url"] for part in payload["messages"][1]["content"] if part["type"] == "image_url"]
        self.assertEqual(len(images), 50)
        for index, image in enumerate(images):
            self.assertEqual(set(image), {"url"})
            self.assertEqual(base64.b64decode(image["url"].split(",", 1)[1]), self.image_paths[index % 5].read_bytes())
        opener = Mock()
        opener.open.return_value = _Response(b'{"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]}')
        with patch("pam.openrouter.build_opener", return_value=opener):
            send_request(payload, config, api_key=FAKE_KEY)
        opener.open.assert_called_once()
        with self.assertRaises(OpenRouterError):
            build_request(bundle, {**self.config, "reflector_frame_count": 100})
        del bundle["frame_count_source"]
        with self.assertRaises(OpenRouterError):
            build_request(bundle, config)

    def test_optional_image_detail_changes_only_the_explicit_request_field(self):
        original = self._payload()
        config = deepcopy(self.config)
        config["image_detail"] = {"predictor": "auto", "reflector": "low"}
        payload = build_request(self.bundle, config)
        for part in payload["messages"][1]["content"]:
            if part["type"] == "image_url":
                self.assertEqual(part["image_url"].pop("detail"), "auto")
        self.assertEqual(payload, original)
        self.assertTrue(all("detail" not in part["image_url"] for part in original["messages"][1]["content"]
                            if part["type"] == "image_url"))
        config["image_detail"] = {"reflector": "low"}
        self.assertEqual(build_request(self.bundle, config), original)

    def test_low_detail_keeps_all_200_original_png_bytes_and_order(self):
        config = deepcopy(self.config)
        config["image_detail"] = {"predictor": "auto", "reflector": "low"}
        bundle = self._bundle("reflector")
        original = deepcopy(bundle)
        payload = build_request(bundle, config)
        images = [part["image_url"] for part in payload["messages"][1]["content"] if part["type"] == "image_url"]
        self.assertEqual(len(images), 200)
        for index, image in enumerate(images):
            self.assertEqual(image["detail"], "low")
            self.assertEqual(base64.b64decode(image["url"].split(",", 1)[1]), self.image_paths[index % 5].read_bytes())
        self.assertEqual(bundle, original)
        self.assertEqual(payload["reasoning"], {"enabled": True})
        self.assertFalse(payload["stream"])

    def test_invalid_image_detail_configuration_is_rejected(self):
        for value in (None, "low", {"other": "low"}, {"reflector": "LOW"}, {"reflector": []}, {"predictor": False}):
            config = deepcopy(self.config)
            config["image_detail"] = value
            with self.subTest(value=value), self.assertRaises(OpenRouterError):
                build_request(self.bundle, config)

    def test_image_detail_tampering_is_rejected_before_http(self):
        config = deepcopy(self.config)
        config["image_detail"] = {"reflector": "low"}
        for mutation in ("change", "delete"):
            payload = build_request(self._bundle("reflector"), config)
            image = payload["messages"][1]["content"][1]["image_url"]
            if mutation == "change":
                image["detail"] = "auto"
            else:
                del image["detail"]
            with patch("pam.openrouter.build_opener") as opener:
                with self.subTest(mutation=mutation), self.assertRaises(OpenRouterError):
                    send_request(payload, config, api_key=FAKE_KEY)
                opener.assert_not_called()
        payload = self._payload()
        payload["messages"][1]["content"][1]["image_url"]["detail"] = "low"
        with patch("pam.openrouter.build_opener") as opener:
            with self.assertRaises(OpenRouterError):
                send_request(payload, self.config, api_key=FAKE_KEY)
            opener.assert_not_called()

    def test_no_reduction_or_padding_when_image_count_is_wrong(self):
        for count in (0, 4, 6):
            bundle = deepcopy(self.bundle)
            images = bundle["messages"][1]["content"][1:]
            bundle["messages"][1]["content"] = [images[index % 5] for index in range(count)]
            with self.subTest(count=count), self.assertRaises(OpenRouterError):
                build_request(bundle, self.config)

    def test_wrong_model_thinking_temperature_or_missing_file_is_rejected(self):
        variants = []
        for field, value in (("model", "Qwen3.5-27B:free"), ("role", "other")):
            bundle = deepcopy(self.bundle)
            bundle[field] = value
            variants.append(bundle)
        for field, value in (("temperature", 0.7), ("enable_thinking", True), ("enable_thinking", 0)):
            bundle = deepcopy(self.bundle)
            bundle["generation"][field] = value
            variants.append(bundle)
        missing = deepcopy(self.bundle)
        missing["messages"][1]["content"][1]["path"] = str(self.directory / "missing.png")
        variants.append(missing)
        for bundle in variants:
            with self.subTest(bundle=bundle), self.assertRaises(OpenRouterError):
                build_request(bundle, self.config)

    def test_local_text_disguised_as_png_and_unknown_parts_are_rejected(self):
        self.image_paths[0].write_text("Not an image.", encoding="utf-8")
        with self.assertRaises(OpenRouterError):
            self._payload()
        bundle = deepcopy(self.bundle)
        bundle["messages"][1]["content"] = [{"type": "evaluation_label", "value": "act"}]
        with self.assertRaises(OpenRouterError):
            build_request(bundle, self.config)

    def test_config_rejects_secret_fields_fallbacks_and_wrong_destination(self):
        variants = []
        for field, value in (("api_key", FAKE_KEY), ("endpoint", "https://example.invalid"),
                             ("model", MODEL + ":free"), ("timeout_seconds", True), ("timeout_seconds", float("nan"))):
            config = deepcopy(self.config)
            config[field] = value
            variants.append(config)
        for field, value in (("allow_fallbacks", True), ("require_parameters", False), ("order", ["alibaba", "novita"])):
            config = deepcopy(self.config)
            config["provider"][field] = value
            variants.append(config)
        for config in variants:
            with self.subTest(config_field=set(config)), self.assertRaises(OpenRouterError):
                build_request(self.bundle, config)

    def test_loader_wraps_bad_json_without_echoing_file_contents(self):
        path = self.directory / "bad.json"
        path.write_text('{"credential": "' + FAKE_KEY, encoding="utf-8")
        with self.assertRaises(OpenRouterError) as caught:
            load_openrouter_config(path)
        self.assertNotIn(FAKE_KEY, str(caught.exception))

    def test_one_post_uses_environment_key_and_preserves_response(self):
        response = {"id": "test-response", "model": MODEL, "provider": "Alibaba",
                    "choices": [{"message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        raw = json.dumps(response, indent=2)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": FAKE_KEY}, clear=True):
            result, opener = self._mock_send(raw.encode("utf-8"), key=None)
        self.assertEqual(result["response"], response)
        self.assertEqual(result["raw_response"], raw)
        self.assertEqual(result["http_status"], 200)
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + FAKE_KEY)
        self.assertNotIn(FAKE_KEY, request.data.decode("utf-8"))
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 120)

    def test_payload_tampering_is_rejected_before_any_http_call(self):
        variants = []
        for field, value in (("model", MODEL + ":free"), ("models", [MODEL]),
                             ("reasoning", {"exclude": True}), ("plugins", [])):
            payload = self._payload()
            payload[field] = value
            variants.append(payload)
        for payload in variants:
            with patch("pam.openrouter.build_opener") as opener:
                with self.subTest(fields=set(payload)), self.assertRaises(OpenRouterError):
                    send_request(payload, self.config, api_key=FAKE_KEY)
                opener.assert_not_called()

    def test_missing_key_does_not_attempt_a_request(self):
        with patch.dict(os.environ, {}, clear=True), patch("pam.openrouter.build_opener") as opener:
            with self.assertRaises(OpenRouterError):
                send_request(self._payload(), self.config)
            opener.assert_not_called()

    def test_http_rejection_never_exposes_key_or_retries(self):
        error = HTTPError(ENDPOINT, 401, FAKE_KEY, {}, io.BytesIO(FAKE_KEY.encode()))
        opener = Mock()
        opener.open.side_effect = error
        with patch("pam.openrouter.build_opener", return_value=opener):
            with self.assertRaises(OpenRouterError) as caught:
                send_request(self._payload(), self.config, api_key=FAKE_KEY)
        self.assertEqual(caught.exception.http_status, 401)
        self.assertNotIn(FAKE_KEY, "".join(traceback.format_exception(caught.exception)))
        opener.open.assert_called_once()

    def test_http_200_error_body_is_not_a_success_or_a_wait(self):
        raw = json.dumps({"error": {"code": 503, "message": FAKE_KEY}}).encode()
        with self.assertRaises(OpenRouterError) as caught:
            self._mock_send(raw)
        self.assertEqual(caught.exception.http_status, 200)
        self.assertEqual(caught.exception.error_code, 503)
        self.assertNotIn(FAKE_KEY, str(caught.exception))
        self.assertNotIn(FAKE_KEY, json.dumps(caught.exception.diagnostic))
        self.assertEqual(caught.exception.diagnostic["error"]["code"], 503)

    def test_http_error_diagnostic_keeps_only_redacted_allowlisted_fields(self):
        image_data = "data:image/png;base64," + "A" * 200
        message = f"Input rejected: {FAKE_KEY}; Bearer another-private-token; sk-or-v1-other-secret; {image_data}"
        nested_raw = json.dumps({"error": {"message": message,
                                          "wrapped_image": "data:image/png;base64," + "B" * 80 + "\n" + "C" * 80}})
        body = json.dumps({"error": {"code": 400, "message": message, "unwanted": "DROP_THIS_FIELD",
                          "metadata": {"raw": nested_raw, "provider_name": "Alibaba", "request_id": "request-test",
                                       "authorization": "DROP_THIS_FIELD"}}, "request": "DROP_THIS_FIELD"}).encode()
        opener = Mock()
        opener.open.side_effect = HTTPError(ENDPOINT, 400, FAKE_KEY, {}, io.BytesIO(body))
        with patch("pam.openrouter.build_opener", return_value=opener):
            with self.assertRaises(OpenRouterError) as caught:
                send_request(self._payload(), self.config, api_key=FAKE_KEY)
        diagnostic = caught.exception.diagnostic
        serialized = json.dumps(diagnostic)
        for secret in (FAKE_KEY, "another-private-token", "sk-or-v1-other-secret", "A" * 200,
                       "B" * 80, "C" * 80, "DROP_THIS_FIELD"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(set(diagnostic["error"]), {"code", "message", "metadata"})
        self.assertEqual(set(diagnostic["error"]["metadata"]), {"raw", "provider_name", "request_id"})
        self.assertEqual(diagnostic["error"]["metadata"]["provider_name"], "Alibaba")
        self.assertIn("Input rejected", diagnostic["error"]["message"])
        self.assertEqual(str(caught.exception), "OpenRouter rejected the request; no retry was attempted.")
        opener.open.assert_called_once()

    def test_error_body_read_is_bounded_and_plain_preview_is_redacted(self):
        class TrackingBody(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.read_sizes = []

            def read(self, size=-1):
                self.read_sizes.append(size)
                return super().read(size)

        body = TrackingBody(("Payload too large: " + FAKE_KEY + " Bearer private-token "
                             + "data:image/png;base64," + "A" * 100000).encode())
        opener = Mock()
        opener.open.side_effect = HTTPError(ENDPOINT, 413, "Rejected", {}, body)
        with patch("pam.openrouter.build_opener", return_value=opener):
            with self.assertRaises(OpenRouterError) as caught:
                send_request(self._payload(), self.config, api_key=FAKE_KEY)
        self.assertEqual(body.read_sizes, [65536])
        diagnostic = caught.exception.diagnostic
        self.assertTrue(diagnostic["body_limit_reached"])
        self.assertEqual(diagnostic["body_bytes_read"], 65536)
        self.assertEqual(diagnostic["format"], "non_json")
        self.assertLessEqual(len(diagnostic["body_preview"]), 2048)
        self.assertIn("Payload too large", diagnostic["body_preview"])
        self.assertNotIn(FAKE_KEY, json.dumps(diagnostic))
        self.assertNotIn("private-token", json.dumps(diagnostic))
        self.assertNotIn("A" * 100, json.dumps(diagnostic))

    def test_json_diagnostic_strings_are_capped_after_redaction(self):
        body = json.dumps({"error": {"code": 400, "message": FAKE_KEY + "x" * 8000,
                          "metadata": {"raw": "y" * 8000}}}).encode()
        opener = Mock()
        opener.open.side_effect = HTTPError(ENDPOINT, 400, "Rejected", {}, io.BytesIO(body))
        with patch("pam.openrouter.build_opener", return_value=opener):
            with self.assertRaises(OpenRouterError) as caught:
                send_request(self._payload(), self.config, api_key=FAKE_KEY)
        diagnostic = caught.exception.diagnostic["error"]
        self.assertLessEqual(len(diagnostic["message"]), 2048)
        self.assertLessEqual(len(diagnostic["metadata"]["raw"]), 2048)
        self.assertNotIn(FAKE_KEY, json.dumps(diagnostic))

    def test_inference_persists_safe_diagnostics_without_replaying_request(self):
        from pam.inference import infer_bundle

        bundle_path = self.directory / "bundle.json"
        bundle_path.write_text(json.dumps(self.bundle), encoding="utf-8")
        output = self.directory / "inference"
        output.mkdir()
        diagnostic = {"error": {"code": 400, "message": "Too many images", "metadata": {"provider_name": "Alibaba"}}}
        error = OpenRouterError("OpenRouter rejected the request; no retry was attempted.",
                                http_status=400, elapsed_seconds=1.0, error_code=400, diagnostic=diagnostic)
        with patch("pam.inference._verify_prepared_images"), \
                patch("pam.inference.send_request", side_effect=error) as sender, \
                patch.dict(os.environ, {"OPENROUTER_API_KEY": FAKE_KEY}, clear=True):
            result = infer_bundle(bundle_path, PROJECT / "config" / "openrouter.json", output)
        persisted = json.loads((output / "api_error.json").read_text(encoding="utf-8"))
        self.assertEqual(result["diagnostic"], diagnostic)
        self.assertEqual(persisted["diagnostic"], diagnostic)
        self.assertNotIn(FAKE_KEY, json.dumps(persisted))
        self.assertTrue(persisted["api_request_attempted"])
        self.assertFalse(persisted["model_response_received"])
        sender.assert_called_once()

    def test_timeout_and_network_errors_are_static_and_not_retried(self):
        for error in (TimeoutError(FAKE_KEY), URLError(FAKE_KEY)):
            opener = Mock()
            opener.open.side_effect = error
            with patch("pam.openrouter.build_opener", return_value=opener):
                with self.subTest(kind=type(error).__name__), self.assertRaises(OpenRouterError) as caught:
                    send_request(self._payload(), self.config, api_key=FAKE_KEY)
            self.assertIsNone(caught.exception.http_status)
            self.assertNotIn(FAKE_KEY, "".join(traceback.format_exception(caught.exception)))
            opener.open.assert_called_once()

    def test_malformed_or_provider_error_responses_are_rejected(self):
        bodies = [b"not-json", b"null", b"{}", b'{"choices":[]}',
                  b'{"choices":[{"finish_reason":"error"}]}']
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(OpenRouterError):
                self._mock_send(body)

    def test_truncation_metadata_is_returned_for_callers_to_reject(self):
        response = {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
        result, _ = self._mock_send(json.dumps(response).encode())
        self.assertEqual(result["response"]["choices"][0]["finish_reason"], "length")

    def test_redirect_handler_does_not_forward_authorization(self):
        self.assertIsNone(_RejectRedirects().redirect_request(None, None, 307, "redirect", {}, "https://example.invalid"))


if __name__ == "__main__":
    unittest.main()
