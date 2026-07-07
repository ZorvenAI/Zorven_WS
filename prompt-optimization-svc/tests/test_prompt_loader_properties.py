"""Hypothesis property tests for prompt loader (US-010)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.services.prompt_loader import _convert_mlflow_template, _PLACEHOLDER_PATTERN

_plain_text = st.text(min_size=0, max_size=200, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")))
_var_names = st.from_regex(r"context\.[a-z_]{1,20}", fullmatch=True)


class TestConvertMlflowTemplateProperties:

    @given(text=_plain_text)
    @hyp_settings(max_examples=50)
    def test_plain_text_unchanged(self, text):
        """Text without {{ }} passes through unchanged."""
        if "{{" not in text and "}}" not in text:
            assert _convert_mlflow_template(text) == text

    @given(var=_var_names)
    @hyp_settings(max_examples=30)
    def test_double_brace_becomes_single(self, var):
        """{{var}} always becomes {var}."""
        template = f"{{{{{var}}}}}"
        result = _convert_mlflow_template(template)
        assert result == f"{{{var}}}"

    @given(var=_var_names)
    @hyp_settings(max_examples=20)
    def test_single_brace_stays_single(self, var):
        """Already single-brace {var} stays as {var}."""
        template = f"{{{var}}}"
        result = _convert_mlflow_template(template)
        assert result == f"{{{var}}}"

    @given(var=_var_names)
    @hyp_settings(max_examples=20)
    def test_conversion_is_idempotent_on_single(self, var):
        """Converting single brace again doesn't change it."""
        single = f"{{{var}}}"
        assert _convert_mlflow_template(single) == single


class TestFormatProperties:

    @given(
        keys=st.lists(
            st.from_regex(r"context\.[a-z_]{1,10}", fullmatch=True),
            min_size=1, max_size=5, unique=True,
        ),
        values=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
    )
    @hyp_settings(max_examples=30)
    def test_format_replaces_all_matching_vars(self, keys, values):
        """All matching variables are replaced in the output."""
        # Build template and variables
        pairs = list(zip(keys[:len(values)], values[:len(keys)]))
        template = " ".join(f"{{{k}}}" for k, _ in pairs)
        variables = {k: v for k, v in pairs}

        # Use the regex-based replacement from the loader
        stringified = {k: str(v) for k, v in variables.items()}

        def _replace(match):
            key = match.group(1)
            return stringified.get(key, match.group(0))

        result = _PLACEHOLDER_PATTERN.sub(_replace, template)

        for k, v in pairs:
            assert str(v) in result
