"""Server-rendered ``AlertRule`` form (issue #77, Fase D2, Slice 3).

The condition is validated by the engine's own ``parse_condition`` (single
source, D8) so the UI can never persist a shape the evaluator would reject; only
the normalized dict is written. ``symbol``/``interval`` are ChoiceFields bound to
the same ``config.SYMBOLS`` / ``CANDLE_INTERVALS`` the app uses. No inline script
and no client-side JS: a plain ``ModelForm``, CSP-safe by construction.
"""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from src.alert_rules import parse_condition
from src.config import SYMBOLS
from trading.candles import CANDLE_INTERVALS
from trading.models import AlertRule


class AlertRuleForm(forms.ModelForm):
    """Create/edit an ``AlertRule``; bounds the pair and validates the condition."""

    symbol = forms.ChoiceField(choices=[(s, s) for s in SYMBOLS])
    interval = forms.ChoiceField(choices=[(i, i) for i in CANDLE_INTERVALS])

    class Meta:
        model = AlertRule
        fields = ("symbol", "interval", "condition", "telegram_chat_id", "is_active")

    def clean_condition(self) -> dict:
        """Normalize via ``parse_condition``; a breach surfaces as a form error."""
        raw = self.cleaned_data["condition"]
        try:
            return parse_condition(raw)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
