"""Process-local outreach kill-switch.

Independent of `Settings`. `get_settings()` is `lru_cache`d and reads a
`.env` file, so a misconfigured override, a cache warmed before the
override landed, or a future refactor could all silently re-enable
dialling. This module reads the environment directly on every call and
never caches, so the guard cannot be defeated by import order.

It is deliberately *in addition to* `outbound_calls_enabled` +
`outbound_call_allowlist`, not a replacement for them. Those two express
product policy ("is this system allowed to dial, and whom"). This
expresses an operational boundary ("this process must not contact
anybody, whatever the policy says") -- used by the test suite, by the
no-contact verification harness, and by any unattended session.

Enabled when either is true:
  * `FIXI_NO_CONTACT` is set to a truthy value, or
  * the process is running under pytest (`PYTEST_CURRENT_TEST`).

The pytest clause means the default test suite can never dial, message or
email anyone even if a test constructs real settings by accident.
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}

#: Channels that reach a human outside this process.
OUTREACH_CHANNELS = ("voice_call", "sms", "email", "provider_booking_request")


class NoContactViolation(RuntimeError):
    """Raised instead of performing real outreach while no-contact is on."""

    def __init__(self, channel: str, target: str | None = None) -> None:
        self.channel = channel
        self.target = target
        super().__init__(
            f"no-contact mode is active: refused to use the {channel} transport"
            + (f" for {target}" if target else "")
            + ". Unset FIXI_NO_CONTACT (and run outside pytest) to allow real outreach."
        )


def no_contact_enabled() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return os.environ.get("FIXI_NO_CONTACT", "").strip().lower() in _TRUTHY


def assert_contact_allowed(channel: str, target: str | None = None) -> None:
    """Call immediately before any network write that reaches a person.

    Raises `NoContactViolation` when the process is in no-contact mode.
    Callers should let it propagate: every outreach path in this codebase
    already records a durable failure event for an exception, so the
    refusal is audited rather than swallowed.
    """
    if no_contact_enabled():
        raise NoContactViolation(channel, target)


# --- test-substitute bookkeeping -------------------------------------------
#
# A verification harness needs the *downstream* call-handling path to run
# (request accepted -> conversation retrieved -> transcript parsed ->
# state transitions -> UI reads) without a phone ringing. That means the
# job body must be allowed to proceed while real outreach stays forbidden.
#
# These are two different questions, so they are two different flags:
#
#   no_contact_enabled()   "is real outreach forbidden?"      -- never relaxed
#   substitute_installed() "has a test replaced the transport?"
#
# `place_call()` proceeds when a substitute is installed. The real
# `place_outbound_call()` still asserts unconditionally, so a harness that
# sets this flag but forgets to patch the transport hits the guard and
# raises instead of dialling. Fail-closed: there is no path where a
# missing fixture falls through to the real client.

_substitute_depth = 0


def substitute_installed() -> bool:
    return _substitute_depth > 0


class provider_substitute:  # noqa: N801 -- used as a context manager, reads as one
    """Marks that the caller has replaced the outbound transport in-process.

    Does not install anything itself: patching is the harness's job, so
    that this module never holds a reference to a fake that could be
    reached from production code.
    """

    def __enter__(self) -> "provider_substitute":
        global _substitute_depth
        if not no_contact_enabled():
            raise RuntimeError(
                "refusing to arm a provider substitute outside no-contact mode: "
                "set FIXI_NO_CONTACT=1 (or run under pytest) first"
            )
        _substitute_depth += 1
        return self

    def __exit__(self, *_exc: object) -> None:
        global _substitute_depth
        _substitute_depth -= 1
