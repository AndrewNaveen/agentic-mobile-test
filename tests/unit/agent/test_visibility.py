"""Regression coverage for audit A01: internal or hidden text cannot pass."""

from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from agentic_mobile_test.appium.observer import AppiumObserver
from agentic_mobile_test.contracts import Scenario, TextAssertion, VerificationState
from agentic_mobile_test.verification.verifier import TextVerifier


@pytest.mark.parametrize("source,passes", [
    ('<hierarchy><node displayed="false"><node text="Saved"/></node></hierarchy>', False),
    ('<hierarchy><node visible="false"><node text="Saved" displayed="true"/></node></hierarchy>', False),
    ('<hierarchy><node resource-id="Saved"/></hierarchy>', False),
    ('<hierarchy><node class="Saved" clickable="true"/></hierarchy>', False),
    ('<hierarchy><node text="Saved"/></hierarchy>', True),
    ('<hierarchy><node content-desc="Saved"/></hierarchy>', True),
])
def test_only_exposed_text_or_accessibility_label_can_pass(source, passes):
    observer = AppiumObserver(SimpleNamespace(driver=object()))
    state = SimpleNamespace(screenshot=Path("unused.png"), ui_source=Path("unused.xml"))
    observer._settled_capture = lambda: (state, ElementTree.fromstring(source), "app", "activity")
    result = TextVerifier().evaluate(
        Scenario("save", "Save", (TextAssertion("saved", "Saved"),)), observer.observe(),
    )
    assert (result.state is VerificationState.PASSED) is passes


def test_hidden_row_label_cannot_name_visible_switch():
    source = ('<hierarchy><node><node displayed="false"><node text="Expected"/></node>'
              '<node resource-id="switch" checkable="true" checked="true"/></node></hierarchy>')
    observer = AppiumObserver(SimpleNamespace(driver=object()))
    state = SimpleNamespace(screenshot=Path("unused.png"), ui_source=Path("unused.xml"))
    observer._settled_capture = lambda: (state, ElementTree.fromstring(source), "app", "activity")
    result = TextVerifier().evaluate(
        Scenario("toggle", "Check", (TextAssertion("on", "Expected", checked=True),)),
        observer.observe(),
    )
    assert result.state is VerificationState.PENDING
